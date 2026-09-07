"""Immutable Grok TRAIN/DEV selection freezes for the WPB native recovery."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType
from typing import Any

HERE = Path(__file__).resolve().parent
CORE_STUDY = HERE.parent / "hbq-human-alignment-wpb-compact-family-v1" / "study.py"
CORE_STUDY_SHA256 = "ef1f8d5e45da1700283ef351ab943ec39abedb103ad1ef979d731d4934d32caf"
CORE_CONTRACT = HERE.parent / "hbq-human-alignment-wpb-compact-family-v1" / "experiment-contract.json"
CORE_CONTRACT_SHA256 = "dd1638d917b32c5de2423ab58aba9d952fbca906722807b8079c1fbb72967e96"
RECOVERY_HELPER = HERE / "recovery.py"
RECOVERY_HELPER_SHA256 = "3bd13df9f27f71563e3a0bf444b22e5bdc3741ca5b3ef278a2254227a155f5ec"
STUDY_ID = "hbq-human-alignment-wpb-compact-family-v1"
RECOVERY_CELLS = 40
LEGACY_CELLS = 89
NATIVE_MEASUREMENT_COUNT = 129
NORMALIZED_NAME = "grok-normalized-measurements.json"
FIT_NAME = "grok-core-fit-result.json"
FREEZE_NAME = "grok-selection-freeze.json"
_HEX = set("0123456789abcdef")


def _require(value: bool, message: str) -> None:
    if not value:
        raise ValueError(message)


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _hex(value: Any, label: str) -> str:
    _require(isinstance(value, str) and len(value) == 64 and set(value) <= _HEX, f"{label} must be a lowercase SHA-256")
    return value


def _module(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    _require(spec is not None and spec.loader is not None, f"cannot load pinned {name}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _pinned_core() -> ModuleType:
    _require(_sha256(CORE_STUDY.read_bytes()) == CORE_STUDY_SHA256, "frozen WPB core study source drifted")
    _require(_sha256(CORE_CONTRACT.read_bytes()) == CORE_CONTRACT_SHA256, "frozen WPB core contract drifted")
    return _module(CORE_STUDY, "wpb_grok_selection_core")


def _pinned_recovery() -> ModuleType:
    _require(_sha256(RECOVERY_HELPER.read_bytes()) == RECOVERY_HELPER_SHA256, "pinned WPB recovery helper source drifted")
    return _module(RECOVERY_HELPER, "wpb_grok_selection_recovery")


def _canonical(core: ModuleType, value: Any) -> bytes:
    raw = core.canonical(value)
    _require(isinstance(raw, bytes) and raw.endswith(b"\n"), "frozen core canonical JSON must use LF termination")
    return raw


def _json(path: Path, label: str) -> tuple[dict[str, Any], bytes]:
    raw = path.read_bytes()
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{label} is not UTF-8 JSON") from error
    _require(isinstance(value, dict), f"{label} must be a JSON object")
    return value, raw


def _write_new(path: Path, raw: bytes) -> str:
    with path.open("xb") as handle:
        handle.write(raw)
    return _sha256(raw)


def _source_bindings(core: ModuleType, recovery: ModuleType, recovery_root: Path, plan: Mapping[str, Any], plan_raw: bytes) -> dict[str, Any]:
    freeze_root = Path(str(plan.get("freeze_root", ""))).resolve()
    _require(freeze_root.is_dir(), "recovery plan freeze root is unavailable")
    _require(plan.get("study_id") == STUDY_ID and getattr(core, "STUDY_ID", None) == STUDY_ID and getattr(recovery, "STUDY_ID", None) == STUDY_ID, "study identity drifted")
    _hex(plan.get("schedule_sha256"), "recovery schedule hash")
    return {
        "core_study": {"path": str(CORE_STUDY.resolve()), "sha256": CORE_STUDY_SHA256},
        "core_contract": {"path": str(CORE_CONTRACT.resolve()), "sha256": CORE_CONTRACT_SHA256},
        "recovery_helper": {"path": str(RECOVERY_HELPER.resolve()), "sha256": RECOVERY_HELPER_SHA256},
        "recovery_plan": {"path": str((recovery_root / recovery.PLAN_NAME).resolve()), "sha256": _sha256(plan_raw)},
        "freeze_root": str(freeze_root),
        "legacy_executor": dict(plan.get("legacy_executor", {})),
    }


def _schedule(core: ModuleType, recovery: ModuleType, plan: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, dict[str, Any]], list[dict[str, Any]]]:
    freeze_root = Path(str(plan["freeze_root"]))
    legacy = recovery._load_legacy()
    resolution, rows = recovery._rows(legacy, freeze_root)
    _require(resolution.get("schedule_sha256") == plan.get("schedule_sha256"), "recovery schedule drifted")
    tasks = core.build_tasks(freeze_root)
    task_rows = {str(item.get("cell_id")): dict(item) for item in tasks.get("tasks", []) if isinstance(item, Mapping)}
    _require(len(rows) == NATIVE_MEASUREMENT_COUNT and len(task_rows) == NATIVE_MEASUREMENT_COUNT and set(rows) == set(task_rows), "WPB full schedule geometry drifted")
    for cell_id, row in rows.items():
        _require(task_rows[cell_id].get("payload_sha256") == row.get("payload_sha256"), "core and recovery payload bindings differ")
    return resolution, rows, [task_rows[cell_id] for cell_id in sorted(task_rows)]


def _legacy_measurements(core: ModuleType, recovery: ModuleType, plan: Mapping[str, Any]) -> tuple[list[dict[str, Any]], set[str]]:
    measurements, identifiers = recovery._legacy_prefix(plan=plan)
    _require(len(measurements) == LEGACY_CELLS and len(identifiers) == LEGACY_CELLS, "historical Grok prefix is not exactly 89 admitted cells")
    return [dict(item) for item in measurements], set(identifiers)


def _recovery_measurements(core: ModuleType, recovery: ModuleType, plan: Mapping[str, Any], recovery_root: Path, resolution: Mapping[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    cells = plan.get("cells")
    _require(isinstance(cells, list) and len(cells) == RECOVERY_CELLS, "recovery plan must contain exactly 40 replacement cells")
    plan_cells = [dict(item) for item in cells if isinstance(item, Mapping)]
    _require(len(plan_cells) == RECOVERY_CELLS and len({str(item.get("cell_id")) for item in plan_cells}) == RECOVERY_CELLS, "recovery plan has duplicate or malformed cells")
    admissions = [recovery._verify_admission(plan, recovery_root, item) for item in plan_cells]
    _require(len(admissions) == RECOVERY_CELLS, "recovery native admissions are incomplete")
    normalized = []
    for item in admissions:
        cell_id, payload_sha, response = item.get("cell_id"), item.get("payload_sha256"), item.get("response")
        _require(isinstance(cell_id, str) and isinstance(payload_sha, str) and isinstance(response, Mapping), "recovery admission lacks a normalized response")
        normalized.append(
            {
                "endpoint": "grok",
                "cell_id": cell_id,
                "payload_sha256": payload_sha,
                "measurement_provenance": {
                    "endpoint": "grok",
                    "cell_id": cell_id,
                    "payload_sha256": payload_sha,
                    "parsed_response_sha256": core.sha256(_canonical(core, response)),
                },
                "response": dict(response),
            }
        )
    return normalized, admissions


def _validate_measurements(core: ModuleType, freeze_root: Path, schedule_sha256: str, rows: Mapping[str, Mapping[str, Any]], measurements: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    result = [dict(item) for item in measurements]
    _require(len(result) == NATIVE_MEASUREMENT_COUNT and {str(item.get("endpoint")) for item in result} == {"grok"}, "selection freeze requires exactly 129 Grok measurements")
    by_cell = {str(item.get("cell_id")): item for item in result}
    _require(len(by_cell) == NATIVE_MEASUREMENT_COUNT and set(by_cell) == set(rows), "selection measurements do not cover the full unique schedule")
    for cell_id, item in by_cell.items():
        _require(item.get("payload_sha256") == rows[cell_id].get("payload_sha256"), "selection measurement payload drifted")
        provenance = item.get("measurement_provenance")
        _require(isinstance(provenance, Mapping) and provenance.get("endpoint") == "grok" and provenance.get("cell_id") == cell_id and provenance.get("payload_sha256") == item["payload_sha256"] and provenance.get("parsed_response_sha256") == core.sha256(_canonical(core, item.get("response"))), "selection response commitment must use frozen core LF canonical JSON")
    baseline = {family: 1.0 for family in ("core", "craft", "form")}
    analysis = core.analyze(freeze_root, result, baseline)
    _require(analysis.get("native_admission") == "not_claimed" and analysis.get("mae") == "not_applicable_pairwise_preference_target", "frozen core analysis contract drifted")
    _require(analysis.get("ordered_measurement_commitment_sha256") == core.sha256([{key: by_cell[cell_id][key] for key in ("endpoint", "cell_id", "payload_sha256", "measurement_provenance")} for cell_id in sorted(by_cell)]), "frozen core measurement commitment drifted")
    return [by_cell[cell_id] for cell_id in sorted(by_cell)]


def _native_inputs(core: ModuleType, recovery: ModuleType, recovery_root: Path, expected_plan_sha256: str) -> tuple[dict[str, Any], bytes, dict[str, Any], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    root = Path(recovery_root).resolve()
    plan = recovery._read_plan(root, _hex(expected_plan_sha256, "expected recovery plan hash"))
    plan_value, plan_raw = _json(root / recovery.PLAN_NAME, "recovery plan")
    _require(plan == plan_value and _sha256(plan_raw) == expected_plan_sha256, "recovery plan reader and immutable bytes disagree")
    recovery._verify_origin(plan)
    resolution, rows, _tasks = _schedule(core, recovery, plan)
    legacy, legacy_ids = _legacy_measurements(core, recovery, plan)
    recovered, admissions = _recovery_measurements(core, recovery, plan, root, resolution)
    recovered_ids = {str(item["cell_id"]) for item in recovered}
    _require(len(recovered_ids) == RECOVERY_CELLS and not (legacy_ids & recovered_ids), "replacement cells overlap historical Grok votes")
    _require(len({str(item.get("request_id_sha256")) for item in admissions}) == RECOVERY_CELLS and len({str(item.get("session_id_sha256")) for item in admissions}) == RECOVERY_CELLS, "recovery native identities are not unique")
    measurements = _validate_measurements(core, Path(str(plan["freeze_root"])), str(plan["schedule_sha256"]), rows, legacy + recovered)
    return plan, plan_raw, _source_bindings(core, recovery, root, plan, plan_raw), measurements, admissions, legacy


def _normalized_document(source_bindings: Mapping[str, Any], schedule_sha256: str, measurements: Sequence[Mapping[str, Any]], admissions: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return {
        "format_version": 1,
        "kind": "wpb_grok_normalized_native_measurements",
        "study_id": STUDY_ID,
        "authority": "development_screening_only",
        "endpoint": "grok",
        "native_measurement_count": NATIVE_MEASUREMENT_COUNT,
        "native_measurement_classification": "completed_native_evidence_replayed_local_grok_requested_model_and_effort_only",
        "inner_core_native_admission": "not_claimed",
        "schedule_sha256": schedule_sha256,
        "source_bindings": dict(source_bindings),
        "recovery_admission_commitments": [
            {key: item[key] for key in ("cell_id", "payload_sha256", "result_sha256", "envelope_sha256", "identity_sha256", "request_id_sha256", "session_id_sha256")}
            for item in sorted(admissions, key=lambda value: str(value["cell_id"]))
        ],
        "measurements": [dict(item) for item in measurements],
    }


def _evidence_descriptor(path: Path, raw: bytes) -> dict[str, Any]:
    return {"path": path.name, "sha256": _sha256(raw), "byte_length": len(raw), "canonicalization": "frozen_core_json_lf"}


def _freeze_document(*, source_bindings: Mapping[str, Any], schedule_sha256: str, normalized: Path, normalized_raw: bytes, fit: Path, fit_raw: bytes, fit_result: Mapping[str, Any], selection_frozen_at: str, plan: Mapping[str, Any]) -> dict[str, Any]:
    selected = fit_result.get("selected_profile")
    _require(isinstance(selected, Mapping), "core fit did not select a profile")
    return {
        "format_version": 1,
        "kind": "wpb_grok_train_dev_selection_freeze",
        "study_id": STUDY_ID,
        "authority": "development_only_no_runtime_or_confirmation_authority",
        "selection_frozen_at": selection_frozen_at,
        "schedule_sha256": schedule_sha256,
        "selected_profile": dict(selected),
        "selected_profile_name": fit_result.get("selected_profile_name"),
        "native_measurement_count": NATIVE_MEASUREMENT_COUNT,
        "native_measurement_classification": "completed_native_evidence_replayed_local_grok_requested_model_and_effort_only",
        "inner_core_native_admission": "not_claimed",
        "source_bindings": dict(source_bindings),
        "evidence_files": {NORMALIZED_NAME: _evidence_descriptor(normalized, normalized_raw), FIT_NAME: _evidence_descriptor(fit, fit_raw)},
        "old_failure_replacement_lineage": {
            "original_root": plan["origin"]["root"],
            "original_terminal_cell": plan["origin"]["ambiguous_terminal_cell"],
            "original_ambiguous_claim_sha256": plan["origin"]["ambiguous_claim_sha256"],
            "original_successful_cells": LEGACY_CELLS,
            "replacement_cells": RECOVERY_CELLS,
            "automatic_retry_or_resend": False,
            "duplicate_logical_votes": False,
        },
        "release_or_promotion_authority": "none",
        "mae": "not_applicable_pairwise_preference_target",
    }


def create_freeze(recovery_root: Path | str, expected_plan_sha256: str, output_root: Path | str) -> dict[str, Any]:
    """Create a fresh immutable selection freeze after all native evidence validates."""
    core, recovery = _pinned_core(), _pinned_recovery()
    output = Path(output_root).resolve()
    _require(not output.exists(), "selection freeze output root already exists")
    plan, plan_raw, bindings, measurements, admissions, _legacy = _native_inputs(core, recovery, Path(recovery_root), expected_plan_sha256)
    normalized_value = _normalized_document(bindings, str(plan["schedule_sha256"]), measurements, admissions)
    normalized_raw = _canonical(core, normalized_value)
    fit_result = core.fit_train_select_dev(Path(str(plan["freeze_root"])), measurements, trials=128)
    _require(isinstance(fit_result, Mapping) and fit_result.get("study_id") == STUDY_ID and fit_result.get("optuna") == {"version": "4.9.0", "seed": 20260904, "trials": 128}, "frozen core fit contract drifted")
    fit_raw = _canonical(core, dict(fit_result))
    post_plan, post_plan_raw, post_bindings, post_measurements, post_admissions, _post_legacy = _native_inputs(core, recovery, Path(recovery_root), expected_plan_sha256)
    _require(plan_raw == post_plan_raw and bindings == post_bindings and normalized_raw == _canonical(core, _normalized_document(post_bindings, str(post_plan["schedule_sha256"]), post_measurements, post_admissions)), "native inputs drifted during TRAIN/DEV selection")
    output.mkdir(parents=True, exist_ok=False)
    normalized_path, fit_path, freeze_path = output / NORMALIZED_NAME, output / FIT_NAME, output / FREEZE_NAME
    _write_new(normalized_path, normalized_raw)
    _write_new(fit_path, fit_raw)
    frozen_at = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    freeze_raw = _canonical(core, _freeze_document(source_bindings=bindings, schedule_sha256=str(plan["schedule_sha256"]), normalized=normalized_path, normalized_raw=normalized_raw, fit=fit_path, fit_raw=fit_raw, fit_result=fit_result, selection_frozen_at=frozen_at, plan=plan))
    freeze_sha256 = _write_new(freeze_path, freeze_raw)
    return {"freeze_path": str(freeze_path), "freeze_sha256": freeze_sha256}


def _verify_static(core: ModuleType, recovery: ModuleType, freeze_path: Path, expected_sha256: str) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any], bytes, bytes]:
    freeze, freeze_raw = _json(freeze_path, "selection freeze")
    _require(_sha256(freeze_raw) == _hex(expected_sha256, "expected selection freeze hash") and freeze_raw == _canonical(core, freeze), "selection freeze bytes drifted")
    _require(freeze.get("kind") == "wpb_grok_train_dev_selection_freeze" and freeze.get("native_measurement_count") == NATIVE_MEASUREMENT_COUNT and freeze.get("inner_core_native_admission") == "not_claimed", "selection freeze contract is malformed")
    evidence = freeze.get("evidence_files")
    _require(isinstance(evidence, Mapping) and set(evidence) == {NORMALIZED_NAME, FIT_NAME}, "selection freeze evidence inventory is malformed")
    normalized_path, fit_path = freeze_path.parent / NORMALIZED_NAME, freeze_path.parent / FIT_NAME
    normalized, normalized_raw = _json(normalized_path, "normalized measurements")
    fit, fit_raw = _json(fit_path, "core fit result")
    _require(normalized_raw == _canonical(core, normalized) and fit_raw == _canonical(core, fit), "selection evidence must use frozen core LF canonical JSON")
    for path, raw in ((normalized_path, normalized_raw), (fit_path, fit_raw)):
        descriptor = evidence[path.name]
        _require(isinstance(descriptor, Mapping) and descriptor == _evidence_descriptor(path, raw), "selection evidence commitment drifted")
    bindings = freeze.get("source_bindings")
    _require(isinstance(bindings, Mapping), "selection source bindings are malformed")
    return freeze, normalized, fit, dict(bindings), normalized_raw, fit_raw


def _verify_bindings(core: ModuleType, recovery: ModuleType, bindings: Mapping[str, Any], schedule_sha256: str) -> tuple[dict[str, Any], bytes]:
    expected = {
        "core_study": {"path": str(CORE_STUDY.resolve()), "sha256": CORE_STUDY_SHA256},
        "core_contract": {"path": str(CORE_CONTRACT.resolve()), "sha256": CORE_CONTRACT_SHA256},
        "recovery_helper": {"path": str(RECOVERY_HELPER.resolve()), "sha256": RECOVERY_HELPER_SHA256},
    }
    for key, value in expected.items():
        _require(bindings.get(key) == value, f"selection {key} binding drifted")
    plan_binding = bindings.get("recovery_plan")
    _require(isinstance(plan_binding, Mapping), "selection recovery plan binding is absent")
    plan_path = Path(str(plan_binding.get("path", "")))
    plan, plan_raw = _json(plan_path, "bound recovery plan")
    _require(plan_path == plan_path.resolve() and _sha256(plan_raw) == plan_binding.get("sha256") and plan.get("schedule_sha256") == schedule_sha256 and bindings.get("freeze_root") == str(Path(str(plan.get("freeze_root"))).resolve()) and bindings.get("legacy_executor") == plan.get("legacy_executor"), "selection bound recovery plan drifted")
    return plan, plan_raw


def verify_freeze(freeze_path: Path | str, expected_sha256: str, replay_native: bool = True) -> dict[str, Any]:
    """Verify immutable freeze bindings; replay native evidence and core fit when requested."""
    _require(type(replay_native) is bool, "replay_native must be boolean")
    core, recovery = _pinned_core(), _pinned_recovery()
    path = Path(freeze_path).resolve()
    freeze, normalized, fit, bindings, _normalized_raw, fit_raw = _verify_static(core, recovery, path, expected_sha256)
    plan, plan_raw = _verify_bindings(core, recovery, bindings, str(freeze.get("schedule_sha256")))
    _require(normalized.get("source_bindings") == bindings and normalized.get("schedule_sha256") == freeze.get("schedule_sha256") and normalized.get("endpoint") == "grok" and normalized.get("native_measurement_count") == NATIVE_MEASUREMENT_COUNT, "normalized export binding drifted")
    measurements = normalized.get("measurements")
    _require(isinstance(measurements, list), "normalized export lacks measurements")
    _resolution, rows, _tasks = _schedule(core, recovery, plan)
    validated_measurements = _validate_measurements(core, Path(str(plan["freeze_root"])), str(plan["schedule_sha256"]), rows, measurements)
    _require(measurements == validated_measurements, "normalized measurement order drifted")
    if replay_native:
        recovery_root = Path(str(bindings["recovery_plan"]["path"])).parent
        _plan, _raw, actual_bindings, actual_measurements, _admissions, _legacy = _native_inputs(core, recovery, recovery_root, str(bindings["recovery_plan"]["sha256"]))
        _require(_raw == plan_raw and actual_bindings == bindings and _canonical(core, normalized) == _canonical(core, _normalized_document(actual_bindings, str(plan["schedule_sha256"]), actual_measurements, _admissions)), "selection native replay differs from frozen export")
        replayed_fit = core.fit_train_select_dev(Path(str(plan["freeze_root"])), actual_measurements, trials=128)
        _require(_canonical(core, dict(replayed_fit)) == fit_raw, "selection core TRAIN/DEV fit replay differs from frozen result")
    selected = freeze.get("selected_profile")
    _require(isinstance(selected, Mapping) and fit.get("selected_profile") == selected and fit.get("selected_profile_name") == freeze.get("selected_profile_name"), "selection profile binding drifted")
    return {"freeze_sha256": expected_sha256, "selection_frozen_at": freeze.get("selection_frozen_at"), "selected_profile": dict(selected), "schedule_sha256": freeze.get("schedule_sha256"), "source_bindings": dict(bindings), "evidence_files": dict(freeze["evidence_files"]), "native_measurement_count": NATIVE_MEASUREMENT_COUNT}
