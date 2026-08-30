#!/usr/bin/env python3
"""Lean, development-only HANNA v4 DSPy/Optuna empirical pilot."""
from __future__ import annotations

import base64
import csv
import hashlib
import json
import os
import stat
import statistics
from pathlib import Path
from types import ModuleType
from typing import Any, Callable, Mapping, Sequence


HERE = Path(__file__).resolve().parent
NATIVE_PATH = HERE.parent / "hbq-human-alignment-optimizer-v4-native-subscription-v1" / "executor.py"
NATIVE_CONTRACT_PATH = NATIVE_PATH.with_name("study-contract.json")
NATIVE_SHA256 = "6d93f69216d62bd0847aa6b338b6e2360587c82608669f78fbad245a34ba1c49"
NATIVE_CONTRACT_SHA256 = "aac0c8952894a2501bd364fcf7fff392399633de8f310be1b97108061e78bbe9"
STUDY_ID = "hbq-human-alignment-optimizer-v4-lean-development-v1"
DIMENSIONS = ("Relevance", "Coherence", "Empathy", "Surprise", "Engagement", "Complexity")
PROMPT_FIELDS = (
    "task_payload_sha256",
    "candidate_instruction_sha256",
    "candidate_profile_sha256",
    "response_schema_sha256",
    "prompt_sha256",
    "story_sha256",
)
CELL_KEYS = frozenset({"cell_id", "evidence_kind", "execution_root", "proof_path", "queue_root"})
ADMISSION_PATH = HERE.parent / "hbq-human-alignment-optimizer-v4-native-admission-v1" / "admit.py"
ADMISSION_SHA256 = "a1c18d224c40e51a822cf2a46b2da273fef37d47df0fe207d1abe8b49bc75304"
SOL_EXEC_V3_PATH = HERE.parent / "hbq-human-alignment-optimizer-v4-native-subscription-exec-v3" / "executor.py"
SOL_EXEC_V3_SHA256 = "cea177b5185a84b682bd5271ae7384cd7742add872d31b45227433d72c7f7e90"


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256(value: Any) -> str:
    return sha256_bytes(canonical(value))


def _stable_bytes(path: Path) -> bytes:
    absolute = Path(os.path.abspath(path))
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current /= part
        info = os.lstat(current)
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & getattr(
            stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400
        ):
            raise ValueError(f"HANNA lean pilot pinned path is reparsed: {current}")
    before = os.lstat(absolute)
    with absolute.open("rb") as handle:
        opened = os.fstat(handle.fileno())
        if (before.st_dev, before.st_ino, before.st_size) != (opened.st_dev, opened.st_ino, opened.st_size):
            raise ValueError("HANNA lean pilot pinned file identity drifted")
        raw = handle.read()
        after = os.fstat(handle.fileno())
        if (opened.st_dev, opened.st_ino, opened.st_size) != (after.st_dev, after.st_ino, after.st_size):
            raise ValueError("HANNA lean pilot pinned file changed during read")
    return raw


def _load_native() -> ModuleType:
    raw = _stable_bytes(NATIVE_PATH)
    contract = _stable_bytes(NATIVE_CONTRACT_PATH)
    if sha256_bytes(raw) != NATIVE_SHA256 or sha256_bytes(contract) != NATIVE_CONTRACT_SHA256:
        raise ValueError("HANNA lean pilot native predecessor bytes drifted")
    module = ModuleType("_hanna_v4_lean_pinned_native")
    module.__file__ = str(NATIVE_PATH)
    exec(compile(raw, str(NATIVE_PATH), "exec"), module.__dict__)
    module.contract()
    if sha256_bytes(_stable_bytes(NATIVE_PATH)) != NATIVE_SHA256:
        raise ValueError("HANNA lean pilot native predecessor changed during load")
    return module


def _load_pinned_module(path: Path, expected_sha256: str, name: str) -> ModuleType:
    raw = _stable_bytes(path)
    if sha256_bytes(raw) != expected_sha256:
        raise ValueError("HANNA lean pilot persisted-evidence verifier bytes drifted")
    module = ModuleType(name)
    module.__file__ = str(path)
    exec(compile(raw, str(path), "exec"), module.__dict__)
    if sha256_bytes(_stable_bytes(path)) != expected_sha256:
        raise ValueError("HANNA lean pilot persisted-evidence verifier changed during load")
    return module


def _row_copy(row: Mapping[str, Any]) -> dict[str, Any]:
    return json.loads(json.dumps(dict(row)))


def freeze_lean_schedule(*, frozen_successor_path: Path, hanna_csv_path: Path) -> dict[str, Any]:
    native = _load_native()
    parent = native.derive_schedule(
        frozen_successor_path=Path(frozen_successor_path),
        hanna_csv_path=Path(hanna_csv_path),
    )
    candidates = list(parent["candidate_ids"])
    if len(candidates) != 5 or len(set(candidates)) != 5:
        raise ValueError("HANNA lean pilot frozen candidate geometry drifted")
    pool = parent["optional_training_pool"]["cells"]
    by_item: dict[str, list[dict[str, Any]]] = {}
    for row in pool:
        by_item.setdefault(row["item_id"], []).append(row)
    matched: list[tuple[str, str]] = []
    used_groups: set[str] = set()
    for item_id in sorted(by_item):
        rows = by_item[item_id]
        routes = {row["route_name"] for row in rows}
        group = rows[0]["prompt_group_id"]
        if routes == {"grok_primary", "sol_validation"} and group not in used_groups:
            matched.append((group, item_id))
            used_groups.add(group)
    selected_items = [item_id for _group, item_id in sorted(matched)[:5]]
    if len(selected_items) != 5:
        raise ValueError("HANNA lean pilot cannot freeze five matched training groups")
    grok_train = [
        _row_copy(row)
        for row in pool
        if row["route_name"] == "grok_primary" and row["item_id"] in selected_items
    ]
    sol_train_items = selected_items[:2]
    sol_train = [
        _row_copy(row)
        for row in pool
        if row["route_name"] == "sol_validation" and row["item_id"] in sol_train_items
    ]
    dev_grok = [
        _row_copy(row)
        for row in parent["mandatory_development"]
        if row["route_name"] == "grok_primary"
    ]
    dev_sol_templates = [
        _row_copy(row)
        for row in parent["mandatory_development"]
        if row["route_name"] == "sol_validation"
    ]
    if (len(grok_train), len(sol_train), len(dev_grok), len(dev_sol_templates)) != (25, 10, 65, 35):
        raise ValueError("HANNA lean pilot frozen cell geometry drifted")
    train_ids = {row["cell_id"] for row in [*grok_train, *sol_train]}
    dev_ids = {row["cell_id"] for row in [*dev_grok, *dev_sol_templates]}
    train_items = {row["item_id"] for row in [*grok_train, *sol_train]}
    dev_items = {row["item_id"] for row in [*dev_grok, *dev_sol_templates]}
    train_groups = {row["prompt_group_id"] for row in [*grok_train, *sol_train]}
    dev_groups = {row["prompt_group_id"] for row in [*dev_grok, *dev_sol_templates]}
    if train_ids & dev_ids or train_items & dev_items or train_groups & dev_groups:
        raise ValueError("HANNA lean pilot train/development partitions overlap")
    grok_train_index = {(row["item_id"], row["candidate_id"]): row for row in grok_train}
    for sol in sol_train:
        grok = grok_train_index.get((sol["item_id"], sol["candidate_id"]))
        if grok is None or any(grok[field] != sol[field] for field in PROMPT_FIELDS):
            raise ValueError("HANNA lean pilot sprinkled Sol training prompt bytes drifted")
    grok_dev_index = {(row["item_id"], row["candidate_id"]): row for row in dev_grok}
    for sol in dev_sol_templates:
        grok = grok_dev_index[(sol["item_id"], sol["candidate_id"])]
        if any(grok[field] != sol[field] for field in PROMPT_FIELDS):
            raise ValueError("HANNA lean pilot matched Grok/Sol validation prompt bytes drifted")
    result = {
        "format_version": 1,
        "study_id": STUDY_ID,
        "kind": "provider_free_lean_development_schedule",
        "parent_schedule_sha256": parent["schedule_sha256"],
        "candidate_ids": candidates,
        "partitions": {
            "training": {"grok": grok_train, "sol_sprinkled": sol_train},
            "grok_development": dev_grok,
            "sol_validation_templates": dev_sol_templates,
            "confirmation": {"status": "unopened", "cells": []},
        },
        "geometry": {
            "training": {"grok_cells": 25, "sol_cells": 10, "items": 5, "prompt_groups": 5},
            "grok_development": {"cells": 65, "items": 13, "prompt_groups": 7},
            "sol_validation_after_freeze": {"cells": 7, "items": 7, "prompt_groups": 7},
            "confirmation": {"cells": 0, "status": "unopened"},
        },
        "selection_policy": {
            "optuna_inputs": "independently_verified_training_cells_only",
            "grok_development": "validation_only_no_candidate_substitution",
            "sol_validation": "seven_exact_parent_rows_for_training_frozen_candidate",
            "confirmation": "no_surface",
        },
    }
    result["schedule_sha256"] = sha256(result)
    return result


def _load_provider_route_inspector() -> Callable[[Mapping[str, Any]], Mapping[str, Any]]:
    raise ValueError("HANNA lean pilot has no enabled live provider route inspector")


def preflight_live_execution(
    *, frozen_successor_path: Path, hanna_csv_path: Path,
    route_inspector: Callable[[Mapping[str, Any]], Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    schedule = freeze_lean_schedule(
        frozen_successor_path=Path(frozen_successor_path), hanna_csv_path=Path(hanna_csv_path)
    )
    inspect = route_inspector or _load_provider_route_inspector()
    routes = {
        row["route_name"]: row["route"]
        for row in [
            schedule["partitions"]["training"]["grok"][0],
            schedule["partitions"]["training"]["sol_sprinkled"][0],
        ]
    }
    evidence: dict[str, Any] = {}
    for route_name, route in routes.items():
        outcome = inspect(route)
        if not isinstance(outcome, Mapping) or outcome.get("accepted") is not True:
            raise ValueError(f"HANNA lean pilot provider route is unavailable: {route_name}")
        if outcome.get("route_sha256") != sha256(route) or outcome.get("provider_calls_made") != 0:
            raise ValueError("HANNA lean pilot provider preflight evidence is misbound")
        evidence[route_name] = dict(outcome)
    return {
        "format_version": 1,
        "study_id": STUDY_ID,
        "kind": "lean_live_execution_preflight",
        "schedule_sha256": schedule["schedule_sha256"],
        "provider_calls_made": 0,
        "routes": evidence,
        "dispatch_authority": "none_preflight_only",
    }


def _decode(value: Any, *, label: str) -> bytes:
    if not isinstance(value, str):
        raise ValueError(f"HANNA lean pilot {label} is not base64")
    try:
        return base64.b64decode(value.encode("ascii"), validate=True)
    except (ValueError, UnicodeEncodeError) as error:
        raise ValueError(f"HANNA lean pilot {label} is not base64") from error


def prepare_training_collection(*, frozen_successor_path: Path, hanna_csv_path: Path) -> dict[str, Any]:
    """Return immutable training-cell bindings for a governed runner; this never dispatches."""
    schedule = freeze_lean_schedule(
        frozen_successor_path=Path(frozen_successor_path), hanna_csv_path=Path(hanna_csv_path)
    )
    native = _load_native()
    cells = []
    for row in _expected_rows(schedule, "training"):
        payload = native._payload(
            native._load_v3(), row,
            frozen_successor_path=Path(frozen_successor_path), hanna_csv_path=Path(hanna_csv_path),
        )
        cells.append({
            "cell_id": row["cell_id"], "route_name": row["route_name"],
            "task_payload_sha256": row["task_payload_sha256"],
            "payload_sha256": sha256_bytes(payload), "payload_base64": base64.b64encode(payload).decode("ascii"),
        })
    return {
        "format_version": 1, "study_id": STUDY_ID, "kind": "lean_training_collection_prepare",
        "schedule_sha256": schedule["schedule_sha256"], "provider_calls_made": 0,
        "dispatch_authority": "none_governed_runner_or_adapter_required", "cells": cells,
    }


def _expected_rows(schedule: Mapping[str, Any], stage: str) -> list[dict[str, Any]]:
    partitions = schedule["partitions"]
    if stage == "training":
        return [*partitions["training"]["grok"], *partitions["training"]["sol_sprinkled"]]
    if stage == "grok_development":
        return list(partitions["grok_development"])
    raise ValueError("HANNA lean pilot accepts only training or Grok-development evidence")


def _targets(native: ModuleType, rows: Sequence[Mapping[str, Any]], *, frozen_successor_path: Path,
             hanna_csv_path: Path) -> dict[str, dict[str, float]]:
    v3 = native._load_v3()
    parent_study = v3.v2_module().parent_modules()[0]
    eligible = parent_study.derive_eligible_map(
        Path(frozen_successor_path), Path(hanna_csv_path)
    )
    wanted = {row["item_id"] for row in rows}
    selected = {row["item_id"]: row for row in eligible if row["item_id"] in wanted}
    if set(selected) != wanted:
        raise ValueError("HANNA lean pilot target item identities drifted")
    by_story = {row["story_id"]: row["item_id"] for row in selected.values()}
    ratings: dict[str, list[Mapping[str, str]]] = {item_id: [] for item_id in wanted}
    with Path(hanna_csv_path).open("r", encoding="utf-8-sig", newline="") as handle:
        for record in csv.DictReader(handle):
            item_id = by_story.get(record.get("Story ID", ""))
            if item_id is not None:
                ratings[item_id].append(record)
    targets: dict[str, dict[str, float]] = {}
    for item_id, item in selected.items():
        records = ratings[item_id]
        if len(records) != 3 or any(record.get("Model") != item["source_model"] for record in records):
            raise ValueError("HANNA lean pilot pinned human ratings drifted")
        targets[item_id] = {
            dimension: statistics.fmean(float(record[dimension]) for record in records)
            for dimension in DIMENSIONS
        }
    return targets


def _canonical_object(path: Path, *, label: str) -> dict[str, Any]:
    try:
        raw = _stable_bytes(Path(path))
    except OSError as error:
        raise ValueError(f"HANNA lean pilot {label} is unavailable") from error
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"HANNA lean pilot {label} is invalid") from error
    if not isinstance(value, dict) or canonical(value) != raw:
        raise ValueError(f"HANNA lean pilot {label} is noncanonical")
    return value


def _verify_admitted_grok_reference(
    reference: Mapping[str, Any], row: Mapping[str, Any], *, frozen_successor_path: Path, hanna_csv_path: Path,
) -> tuple[bytes, bytes, dict[str, Any]]:
    if reference.get("queue_root") is not None or not isinstance(reference.get("proof_path"), str):
        raise ValueError("HANNA lean pilot admitted Grok reference shape is invalid")
    root, proof_path = Path(reference["execution_root"]), Path(reference["proof_path"])
    proof = _canonical_object(proof_path, label="admitted Grok proof")
    admission = _load_pinned_module(ADMISSION_PATH, ADMISSION_SHA256, "_hanna_lean_admission")
    admission.contract()
    required = {
        "format_version", "study_id", "kind", "provider_calls_made", "cell_id", "source_execution_root",
        "source_cell_root", "source_exec_executor_sha256", "predecessor_executor_sha256",
        "predecessor_contract_sha256", "admit_py_sha256", "admission_contract_sha256", "source_inventory",
        "destination_root", "destination_inventory", "source_receipt_sha256", "source_identity_sha256",
        "native_request_sha256", "native_response_sha256", "destination_result_sha256", "deduplication_key",
    }
    if (set(proof) != required or proof.get("format_version") != 1
            or proof.get("study_id") != admission.STUDY_ID or proof.get("kind") != "completed_grok_admission_proof"
            or proof.get("provider_calls_made") != 0 or proof.get("cell_id") != row["cell_id"]
            or proof.get("admit_py_sha256") != ADMISSION_SHA256 or Path(proof.get("destination_root", "")) != root):
        raise ValueError("HANNA lean pilot admitted Grok proof is misbound")
    predecessor, execution = admission._load_pinned()
    inventory = admission._plain_inventory(root, admission.DESTINATION_FILES)
    if inventory != proof.get("destination_inventory"):
        raise ValueError("HANNA lean pilot admitted Grok destination inventory drifted")
    prepared = predecessor._read_canonical(root / "prepared.json", label="lean admitted prepared")
    predecessor._validate_persisted_result(root, row=row, prepared=prepared, inventory_state="native_returned_unprojected")
    source_row, _payload, request, _settings, source = admission._historical_grok_receipt(
        execution=execution, predecessor=predecessor, source_root=Path(proof["source_execution_root"]),
        cell_id=row["cell_id"], frozen_successor_path=Path(frozen_successor_path), hanna_csv_path=Path(hanna_csv_path),
    )
    response = _stable_bytes(root / "native-response.bin")
    result = predecessor._read_canonical(root / "result.json", label="lean admitted result")
    identity = result.get("identity")
    if (source_row != dict(row) or response != source["response"] or not isinstance(identity, dict)
            or identity != source["identity"] or proof.get("native_request_sha256") != sha256_bytes(request)
            or proof.get("native_response_sha256") != sha256_bytes(response)
            or proof.get("destination_result_sha256") != sha256_bytes(canonical(result))):
        raise ValueError("HANNA lean pilot admitted Grok native bindings drifted")
    return request, response, identity


def _verify_sol_v3_reference(
    reference: Mapping[str, Any], row: Mapping[str, Any], *, frozen_successor_path: Path, hanna_csv_path: Path,
) -> tuple[bytes, bytes, dict[str, Any]]:
    if reference.get("proof_path") is not None or not isinstance(reference.get("queue_root"), str):
        raise ValueError("HANNA lean pilot Sol receipt reference shape is invalid")
    root, queue_root = Path(reference["execution_root"]), Path(reference["queue_root"])
    execution = _load_pinned_module(SOL_EXEC_V3_PATH, SOL_EXEC_V3_SHA256, "_hanna_lean_sol_exec_v3")
    receipt = _canonical_object(root / "execution-receipt.json", label="Sol execution receipt")
    identity = receipt.get("identity")
    if not isinstance(identity, dict):
        raise ValueError("HANNA lean pilot Sol receipt lacks identity")
    execution.verify_predecessor_receipt(
        {"cell": dict(row), "identity": identity}, execution_root=root.parent, queue_root=queue_root,
        frozen_successor_path=Path(frozen_successor_path), hanna_csv_path=Path(hanna_csv_path),
    )
    predecessor = execution._load_predecessor()
    prepared, _payload, request, _schema, fresh_row = execution._read_prepared(
        predecessor, root, cell_id=row["cell_id"], frozen_successor_path=Path(frozen_successor_path),
        hanna_csv_path=Path(hanna_csv_path), require_pristine=False,
    )
    response = _stable_bytes(root / "raw-codex-final-response.bin")
    if fresh_row != dict(row) or prepared.get("route_status") != "SOL_PREPARED_NO_CONTACT":
        raise ValueError("HANNA lean pilot Sol prepared row drifted")
    return request, response, identity


def _validate_sol_v3_identity(value: Any, row: Mapping[str, Any]) -> dict[str, Any]:
    keys = {
        "provider", "route_name", "requested_model", "requested_reasoning_effort", "effective_model",
        "provider_reported_model", "identity_evidence", "reasoning_attested", "transport_identity",
        "contact_id", "session_id",
    }
    route = row["route"]
    expected = {
        "provider": route["provider"], "route_name": route["route_name"],
        "requested_model": route["requested_model"], "requested_reasoning_effort": route["requested_reasoning_effort"],
        "effective_model": route["effective_model"], "provider_reported_model": None,
        "identity_evidence": "requested_and_local_effective_settings_only_stderr_labels_may_be_absent_not_provider_attested",
        "reasoning_attested": False, "transport_identity": "codex_chatgpt_subscription_exec_tool_free_v3",
    }
    if (not isinstance(value, Mapping) or set(value) != keys
            or any(value.get(key) != expected_value for key, expected_value in expected.items())
            or not isinstance(value.get("contact_id"), str) or not value["contact_id"].startswith("unproven-native-endpoint-contact-for-local-thread:")
            or not isinstance(value.get("session_id"), str) or not value["session_id"].startswith("local-codex-thread-session:")):
        raise ValueError("HANNA lean pilot Sol exec-v3 local-lifecycle identity drifted")
    return dict(value)


def _extract_sol_v3(native: ModuleType, response: bytes) -> tuple[dict[str, float], dict[str, bool]]:
    try:
        value = json.loads(response.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("HANNA lean pilot Sol final response is not strict JSON") from error
    v2 = native._load_v3().v2_module()
    if not isinstance(value, dict) or set(value) != {"scores", "evidence", "coverage"}:
        raise ValueError("HANNA lean pilot Sol final response shape drifted")
    scores = v2._validate_scores(value)
    coverage = value.get("coverage")
    if not isinstance(coverage, Mapping) or set(coverage) != set(DIMENSIONS) or any(type(coverage[name]) is not bool for name in DIMENSIONS):
        raise ValueError("HANNA lean pilot Sol final response coverage drifted")
    return scores, {name: coverage[name] for name in DIMENSIONS}


def _verify_persisted_cell(
    reference: Mapping[str, Any], row: Mapping[str, Any], *, frozen_successor_path: Path, hanna_csv_path: Path,
) -> tuple[bytes, bytes, dict[str, Any]]:
    if (not isinstance(reference, Mapping) or set(reference) != CELL_KEYS
            or reference.get("cell_id") != row["cell_id"] or not isinstance(reference.get("execution_root"), str)):
        raise ValueError("HANNA lean pilot persisted cell reference is invalid")
    kind = reference.get("evidence_kind")
    if kind == "admitted_grok":
        if row["route_name"] != "grok_primary":
            raise ValueError("HANNA lean pilot Grok reference route drifted")
        return _verify_admitted_grok_reference(reference, row, frozen_successor_path=frozen_successor_path, hanna_csv_path=hanna_csv_path)
    if kind == "sol_exec_v3":
        if row["route_name"] != "sol_validation":
            raise ValueError("HANNA lean pilot Sol reference route drifted")
        return _verify_sol_v3_reference(reference, row, frozen_successor_path=frozen_successor_path, hanna_csv_path=hanna_csv_path)
    raise ValueError("HANNA lean pilot persisted cell evidence kind is unsupported")


def _validate_evidence(
    *, evidence_path: Path, schedule: Mapping[str, Any], stage: str, native: ModuleType,
    frozen_successor_path: Path, hanna_csv_path: Path,
    expected_rows: Sequence[Mapping[str, Any]] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, dict[str, float]]]:
    raw = Path(evidence_path).read_bytes()
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("HANNA lean pilot evidence is invalid") from error
    if not isinstance(value, dict) or canonical(value) != raw:
        raise ValueError("HANNA lean pilot evidence is noncanonical")
    if set(value) != {"format_version", "study_id", "kind", "schedule_sha256", "stage", "cells"}:
        raise ValueError("HANNA lean pilot caller aggregates or synthetic results are rejected")
    if (
        value["format_version"] != 1
        or value["study_id"] != STUDY_ID
        or value["kind"] != "verified_persisted_native_cells"
        or value["schedule_sha256"] != schedule["schedule_sha256"]
        or value["stage"] != stage
    ):
        raise ValueError("HANNA lean pilot evidence identity drifted")
    expected_rows = [dict(row) for row in (expected_rows or _expected_rows(schedule, stage))]
    cells = value["cells"]
    if not isinstance(cells, list) or len(cells) != len(expected_rows):
        raise ValueError("HANNA lean pilot evidence geometry is incomplete")
    if any(not isinstance(cell, Mapping) or set(cell) != CELL_KEYS for cell in cells):
        raise ValueError("HANNA lean pilot caller aggregates, raw bytes, or synthetic results are rejected")
    if [cell["cell_id"] for cell in cells] != [row["cell_id"] for row in expected_rows]:
        raise ValueError("HANNA lean pilot evidence cell order or partition binding drifted")
    observations: list[dict[str, Any]] = []
    contacts: set[tuple[str, str, str]] = set()
    for cell, row in zip(cells, expected_rows, strict=True):
        request, response, identity = _verify_persisted_cell(
            cell, row, frozen_successor_path=Path(frozen_successor_path), hanna_csv_path=Path(hanna_csv_path)
        )
        if sha256_bytes(request) != row["task_payload_sha256"]:
            raise ValueError("HANNA lean pilot native request is not the frozen prompt bytes")
        if row["route_name"] == "grok_primary":
            identity = native._validate_identity(identity, row)
            scores, coverage = native._extract_native(response, row=row, identity=identity)
        else:
            identity = _validate_sol_v3_identity(identity, row)
            scores, coverage = _extract_sol_v3(native, response)
        contact = (identity["provider"], identity["contact_id"], identity["session_id"])
        if contact in contacts:
            raise ValueError("HANNA lean pilot duplicate native contact identity")
        contacts.add(contact)
        observations.append({**dict(row), "scores": scores, "coverage": coverage, "request_bytes": len(request)})
    targets = _targets(
        native, expected_rows,
        frozen_successor_path=Path(frozen_successor_path), hanna_csv_path=Path(hanna_csv_path),
    )
    return observations, targets


def _candidate_endpoints(
    native: ModuleType, observations: Sequence[Mapping[str, Any]], targets: Mapping[str, Mapping[str, float]],
    *, route_name: str, expected_items: int, expected_groups: int, candidate_ids: Sequence[str],
) -> list[dict[str, Any]]:
    v2 = native._load_v3().v2_module()
    result = []
    for candidate_id in candidate_ids:
        rows = [
            row for row in observations
            if row["route_name"] == route_name and row["candidate_id"] == candidate_id
        ]
        endpoint = v2._candidate_endpoint(
            rows, targets, expected_items=expected_items, expected_groups=expected_groups
        )
        if endpoint["macro_spearman"] is None:
            raise ValueError("HANNA lean pilot endpoint correlation is undefined")
        result.append({
            "candidate_id": candidate_id,
            "endpoint": endpoint,
            "mean_request_bytes": statistics.fmean(float(row["request_bytes"]) for row in rows),
        })
    return result


def optimize_training_evidence(
    *, frozen_successor_path: Path, hanna_csv_path: Path, training_evidence_path: Path,
    seed: int = 20260829,
) -> dict[str, Any]:
    if not isinstance(seed, int) or isinstance(seed, bool):
        raise ValueError("HANNA lean pilot Optuna seed is invalid")
    schedule = freeze_lean_schedule(
        frozen_successor_path=Path(frozen_successor_path), hanna_csv_path=Path(hanna_csv_path)
    )
    native = _load_native()
    observations, targets = _validate_evidence(
        evidence_path=Path(training_evidence_path), schedule=schedule, stage="training", native=native,
        frozen_successor_path=Path(frozen_successor_path), hanna_csv_path=Path(hanna_csv_path),
    )
    candidate_ids = schedule["candidate_ids"]
    grok = _candidate_endpoints(
        native, observations, targets, route_name="grok_primary", expected_items=5,
        expected_groups=5, candidate_ids=candidate_ids,
    )
    sol = _candidate_endpoints(
        native, observations, targets, route_name="sol_validation", expected_items=2,
        expected_groups=2, candidate_ids=candidate_ids,
    )
    grok_by_id = {row["candidate_id"]: row for row in grok}
    sol_by_id = {row["candidate_id"]: row for row in sol}
    try:
        import optuna  # type: ignore[import-not-found]
    except ImportError as error:
        raise ValueError("HANNA lean pilot requires Optuna 4.9.0 for development") from error
    if optuna.__version__ != "4.9.0":
        raise ValueError("HANNA lean pilot Optuna version drifted")
    sampler = optuna.samplers.GridSampler({"candidate_id": sorted(candidate_ids)}, seed=seed)
    study = optuna.create_study(direction="maximize", sampler=sampler)

    def objective(trial: Any) -> float:
        candidate_id = trial.suggest_categorical("candidate_id", sorted(candidate_ids))
        grok_alignment = float(grok_by_id[candidate_id]["endpoint"]["macro_spearman"])
        sol_alignment = float(sol_by_id[candidate_id]["endpoint"]["macro_spearman"])
        request_bytes = float(grok_by_id[candidate_id]["mean_request_bytes"])
        value = 0.8 * grok_alignment + 0.2 * sol_alignment - request_bytes / 1_000_000_000.0
        trial.set_user_attr("grok_alignment", grok_alignment)
        trial.set_user_attr("sol_sprinkled_alignment", sol_alignment)
        trial.set_user_attr("mean_grok_request_bytes", request_bytes)
        return value

    study.optimize(objective, n_trials=len(candidate_ids), catch=())
    best = study.best_trial
    evidence_raw = Path(training_evidence_path).read_bytes()
    result = {
        "format_version": 1,
        "study_id": STUDY_ID,
        "kind": "lean_training_only_optuna_selection",
        "schedule_sha256": schedule["schedule_sha256"],
        "training_evidence_sha256": sha256_bytes(evidence_raw),
        "seed": seed,
        "optimizer": "optuna.GridSampler@4.9.0",
        "objective": "0.8_grok_macro_spearman_plus_0.2_sol_sprinkled_macro_spearman_minus_request_byte_tiebreak",
        "endpoints": {"grok": grok, "sol_sprinkled": sol},
        "frozen_candidate_id": best.params["candidate_id"],
        "best_trial": {
            "number": best.number,
            "objective": best.value,
            "grok_alignment": best.user_attrs["grok_alignment"],
            "sol_sprinkled_alignment": best.user_attrs["sol_sprinkled_alignment"],
        },
        "grok_development_authority": "validate_or_veto_only_no_substitution",
        "sol_validation_status": "unopened_until_training_candidate_frozen",
        "confirmation": {"status": "unopened", "cells": 0},
        "runtime_authority": "none",
    }
    result["result_sha256"] = sha256(result)
    return result


def freeze_training_selection(
    *, frozen_successor_path: Path, hanna_csv_path: Path, training_evidence_path: Path, seed: int = 20260829,
) -> dict[str, Any]:
    """Freeze the training-only winner from persisted evidence; no route is contacted."""
    return optimize_training_evidence(
        frozen_successor_path=Path(frozen_successor_path), hanna_csv_path=Path(hanna_csv_path),
        training_evidence_path=Path(training_evidence_path), seed=seed,
    )


def _require_successful_grok_validation(
    *, schedule: Mapping[str, Any], training_result: Mapping[str, Any], grok_development_result: Mapping[str, Any],
    frozen_successor_path: Path, hanna_csv_path: Path, training_evidence_path: Path,
    grok_development_evidence_path: Path, minimum_macro_spearman: float, seed: int,
) -> None:
    recomputed = validate_grok_development(
        frozen_successor_path=Path(frozen_successor_path), hanna_csv_path=Path(hanna_csv_path),
        training_evidence_path=Path(training_evidence_path), training_result=training_result,
        grok_development_evidence_path=Path(grok_development_evidence_path),
        minimum_macro_spearman=minimum_macro_spearman, seed=seed,
    )
    if canonical(recomputed) != canonical(grok_development_result) or recomputed["status"] != "validated_no_substitution":
        raise ValueError("HANNA lean pilot Sol validation remains closed until successful Grok-development validation")
    if (recomputed["schedule_sha256"] != schedule["schedule_sha256"]
            or recomputed["frozen_candidate_id"] != training_result["frozen_candidate_id"]):
        raise ValueError("HANNA lean pilot Grok-development gate is misbound")


def sol_validation_rows(
    schedule: Mapping[str, Any], training_result: Mapping[str, Any], *,
    frozen_successor_path: Path, hanna_csv_path: Path, training_evidence_path: Path, seed: int = 20260829,
    grok_development_result: Mapping[str, Any], grok_development_evidence_path: Path,
    minimum_macro_spearman: float,
) -> list[dict[str, Any]]:
    if (
        training_result.get("study_id") != STUDY_ID
        or training_result.get("kind") != "lean_training_only_optuna_selection"
        or training_result.get("schedule_sha256") != schedule.get("schedule_sha256")
    ):
        raise ValueError("HANNA lean pilot training selection is misbound")
    body = dict(training_result)
    result_sha = body.pop("result_sha256", None)
    if result_sha != sha256(body):
        raise ValueError("HANNA lean pilot training result hash drifted")
    recomputed = freeze_training_selection(
        frozen_successor_path=Path(frozen_successor_path), hanna_csv_path=Path(hanna_csv_path),
        training_evidence_path=Path(training_evidence_path), seed=seed,
    )
    if canonical(recomputed) != canonical(training_result):
        raise ValueError("HANNA lean pilot training winner is not bound to verified Optuna evidence")
    _require_successful_grok_validation(
        schedule=schedule, training_result=training_result, grok_development_result=grok_development_result,
        frozen_successor_path=Path(frozen_successor_path), hanna_csv_path=Path(hanna_csv_path),
        training_evidence_path=Path(training_evidence_path), grok_development_evidence_path=Path(grok_development_evidence_path),
        minimum_macro_spearman=minimum_macro_spearman, seed=seed,
    )
    candidate_id = training_result.get("frozen_candidate_id")
    if candidate_id not in schedule.get("candidate_ids", []):
        raise ValueError("HANNA lean pilot frozen candidate is invalid")
    rows = [
        _row_copy(row) for row in schedule["partitions"]["sol_validation_templates"]
        if row["candidate_id"] == candidate_id
    ]
    if len(rows) != 7 or len({row["item_id"] for row in rows}) != 7:
        raise ValueError("HANNA lean pilot Sol validation geometry drifted")
    return rows


def validate_grok_development(
    *, frozen_successor_path: Path, hanna_csv_path: Path, training_evidence_path: Path,
    training_result: Mapping[str, Any], grok_development_evidence_path: Path,
    minimum_macro_spearman: float, seed: int = 20260829,
) -> dict[str, Any]:
    """Evaluate only the frozen training winner on the disjoint Grok-development endpoint."""
    if type(minimum_macro_spearman) not in {int, float} or not -1 <= float(minimum_macro_spearman) <= 1:
        raise ValueError("HANNA lean pilot Grok-development veto threshold is invalid")
    schedule = freeze_lean_schedule(frozen_successor_path=Path(frozen_successor_path), hanna_csv_path=Path(hanna_csv_path))
    frozen = freeze_training_selection(
        frozen_successor_path=Path(frozen_successor_path), hanna_csv_path=Path(hanna_csv_path),
        training_evidence_path=Path(training_evidence_path), seed=seed,
    )
    if canonical(frozen) != canonical(training_result):
        raise ValueError("HANNA lean pilot Grok development is not bound to frozen training selection")
    native = _load_native()
    observations, targets = _validate_evidence(
        evidence_path=Path(grok_development_evidence_path), schedule=schedule, stage="grok_development", native=native,
        frozen_successor_path=Path(frozen_successor_path), hanna_csv_path=Path(hanna_csv_path),
    )
    candidate = frozen["frozen_candidate_id"]
    endpoint = _candidate_endpoints(
        native, observations, targets, route_name="grok_primary", expected_items=13, expected_groups=7,
        candidate_ids=[candidate],
    )[0]["endpoint"]
    passed = float(endpoint["macro_spearman"]) >= float(minimum_macro_spearman)
    raw = Path(grok_development_evidence_path).read_bytes()
    result = {
        "format_version": 1, "study_id": STUDY_ID, "kind": "lean_grok_development_validation",
        "schedule_sha256": schedule["schedule_sha256"], "training_result_sha256": training_result["result_sha256"],
        "grok_development_evidence_sha256": sha256_bytes(raw), "frozen_candidate_id": candidate,
        "minimum_macro_spearman": float(minimum_macro_spearman), "endpoint": endpoint,
        "status": "validated_no_substitution" if passed else "vetoed_no_substitution",
        "candidate_substitution": "forbidden", "confirmation": {"status": "unopened", "cells": 0},
        "runtime_authority": "none",
    }
    result["result_sha256"] = sha256(result)
    return result


def analyze_sol_validation(
    *, frozen_successor_path: Path, hanna_csv_path: Path, training_evidence_path: Path,
    training_result: Mapping[str, Any], grok_development_result: Mapping[str, Any],
    grok_development_evidence_path: Path, minimum_macro_spearman: float,
    sol_validation_evidence_path: Path, seed: int = 20260829,
) -> dict[str, Any]:
    """Analyze seven late-bound Sol rows without treating its local lifecycle as native endpoint proof."""
    schedule = freeze_lean_schedule(frozen_successor_path=Path(frozen_successor_path), hanna_csv_path=Path(hanna_csv_path))
    rows = sol_validation_rows(
        schedule, training_result, frozen_successor_path=Path(frozen_successor_path), hanna_csv_path=Path(hanna_csv_path),
        training_evidence_path=Path(training_evidence_path), seed=seed, grok_development_result=grok_development_result,
        grok_development_evidence_path=Path(grok_development_evidence_path), minimum_macro_spearman=minimum_macro_spearman,
    )
    native = _load_native()
    observations, targets = _validate_evidence(
        evidence_path=Path(sol_validation_evidence_path), schedule=schedule, stage="sol_validation", native=native,
        frozen_successor_path=Path(frozen_successor_path), hanna_csv_path=Path(hanna_csv_path), expected_rows=rows,
    )
    endpoint = _candidate_endpoints(
        native, observations, targets, route_name="sol_validation", expected_items=7, expected_groups=7,
        candidate_ids=[training_result["frozen_candidate_id"]],
    )[0]["endpoint"]
    raw = Path(sol_validation_evidence_path).read_bytes()
    result = {
        "format_version": 1, "study_id": STUDY_ID, "kind": "lean_sol_validation_readout",
        "schedule_sha256": schedule["schedule_sha256"], "training_result_sha256": training_result["result_sha256"],
        "sol_validation_evidence_sha256": sha256_bytes(raw), "frozen_candidate_id": training_result["frozen_candidate_id"],
        "endpoint": endpoint,
        "evidence_class": "local_codex_lifecycle_received_native_contact_unproven",
        "training_sol_caveat": "The sprinkled two-item Sol training correlation is an optimizer component only, not a stable alignment estimate.",
        "claim_limits": ["No native endpoint-contact cardinality claim", "No Grok/Sol agreement or generalization claim", "No confirmation or runtime claim"],
        "confirmation": {"status": "unopened", "cells": 0}, "runtime_authority": "none",
    }
    result["result_sha256"] = sha256(result)
    return result


def load_dspy() -> Any:
    try:
        import dspy  # type: ignore[import-not-found]
    except ImportError as error:
        raise ValueError("HANNA lean pilot requires DSPy 3.3.1 for development") from error
    if dspy.__version__ != "3.3.1":
        raise ValueError("HANNA lean pilot DSPy version drifted")
    return dspy


def dspy_training_context(
    *, frozen_successor_path: Path, hanna_csv_path: Path, training_evidence_path: Path, seed: int = 20260829,
) -> dict[str, Any]:
    """Recompute the only diagnostics a DSPy descendant proposal may receive."""
    result = freeze_training_selection(
        frozen_successor_path=Path(frozen_successor_path), hanna_csv_path=Path(hanna_csv_path),
        training_evidence_path=Path(training_evidence_path), seed=seed,
    )
    native = _load_native()
    candidates = native._load_v3().candidate_pack()
    parents = [candidate for candidate in candidates if candidate["candidate_id"] == result["frozen_candidate_id"]]
    if len(parents) != 1:
        raise ValueError("HANNA lean pilot DSPy frozen parent candidate drifted")
    diagnostics = {
        "format_version": 1, "study_id": STUDY_ID, "kind": "verified_optuna_training_diagnostics",
        "training_result_sha256": result["result_sha256"], "best_trial": result["best_trial"],
        "endpoints": result["endpoints"], "seed": result["seed"], "optimizer": result["optimizer"],
    }
    diagnostics_raw = canonical(diagnostics)
    return {
        "parent": parents[0], "training_result": result, "training_result_bytes": canonical(result),
        "training_diagnostics": diagnostics, "training_diagnostics_bytes": diagnostics_raw,
        "training_diagnostics_sha256": sha256_bytes(diagnostics_raw),
    }


def build_dspy_descendant_program() -> Any:
    dspy = load_dspy()

    class LeanDescendantSignature(dspy.Signature):
        """Propose versioned candidate bytes from frozen training-only diagnostics."""

        parent_candidate_id: str = dspy.InputField()
        parent_instruction_base64: str = dspy.InputField()
        parent_profile_base64: str = dspy.InputField()
        training_result_base64: str = dspy.InputField()
        training_diagnostics_base64: str = dspy.InputField()
        descendant_instruction_base64: str = dspy.OutputField()
        descendant_profile_base64: str = dspy.OutputField()

    class LeanDescendantProgram(dspy.Module):
        signature = LeanDescendantSignature

        def __init__(self) -> None:
            super().__init__()
            self.predict = dspy.Predict(LeanDescendantSignature)

        def forward(self, *, frozen_successor_path: Path, hanna_csv_path: Path,
                    training_evidence_path: Path, seed: int = 20260829) -> dict[str, Any]:
            context = dspy_training_context(
                frozen_successor_path=Path(frozen_successor_path), hanna_csv_path=Path(hanna_csv_path),
                training_evidence_path=Path(training_evidence_path), seed=seed,
            )
            parent = context["parent"]
            training_result = context["training_result"]
            training_result_sha256 = training_result["result_sha256"]
            if (
                not isinstance(parent, Mapping)
                or not isinstance(parent.get("instruction_bytes"), bytes)
                or not isinstance(parent.get("profile_bytes"), bytes)
                or sha256_bytes(parent["instruction_bytes"]) != parent.get("instruction_sha256")
                or sha256_bytes(parent["profile_bytes"]) != parent.get("profile_sha256")
                or not isinstance(training_result_sha256, str)
                or len(training_result_sha256) != 64
            ):
                raise ValueError("HANNA lean pilot DSPy parent or training lineage is invalid")
            inputs = {
                "parent_candidate_id": parent["candidate_id"],
                "parent_instruction_base64": base64.b64encode(parent["instruction_bytes"]).decode("ascii"),
                "parent_profile_base64": base64.b64encode(parent["profile_bytes"]).decode("ascii"),
                "training_result_base64": base64.b64encode(context["training_result_bytes"]).decode("ascii"),
                "training_diagnostics_base64": base64.b64encode(context["training_diagnostics_bytes"]).decode("ascii"),
            }
            prediction = self.predict(**inputs)
            instruction = _decode(getattr(prediction, "descendant_instruction_base64", None), label="DSPy instruction")
            profile = _decode(getattr(prediction, "descendant_profile_base64", None), label="DSPy profile")
            if not instruction or (instruction == parent["instruction_bytes"] and profile == parent["profile_bytes"]):
                raise ValueError("HANNA lean pilot DSPy descendant is not a distinct version")
            try:
                profile_value = json.loads(profile.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                raise ValueError("HANNA lean pilot DSPy descendant profile is invalid") from error
            if not isinstance(profile_value, dict):
                raise ValueError("HANNA lean pilot DSPy descendant profile is invalid")
            lineage = {
                "format_version": 1,
                "study_id": STUDY_ID,
                "kind": "dspy_predict_versioned_descendant",
                "dspy_program": "Predict(LeanDescendantSignature)@3.3.1",
                "parent_candidate_id": parent["candidate_id"],
                "parent_candidate_sha256": parent["candidate_sha256"],
                "training_result_sha256": training_result_sha256,
                "training_result_bytes_sha256": sha256_bytes(context["training_result_bytes"]),
                "training_diagnostics_sha256": context["training_diagnostics_sha256"],
                "instruction_sha256": sha256_bytes(instruction),
                "proposed_profile_sha256": sha256_bytes(profile),
                "runtime_authority": "none",
                "confirmation_authority": "none",
            }
            lineage["descendant_candidate_sha256"] = sha256(lineage)
            return {
                "descendant_instruction_base64": base64.b64encode(instruction).decode("ascii"),
                "descendant_profile_base64": base64.b64encode(profile).decode("ascii"),
                "instruction_sha256": sha256_bytes(instruction),
                "profile_sha256": sha256_bytes(profile),
                "lineage": lineage,
                "descendant_candidate_sha256": lineage["descendant_candidate_sha256"],
                "predictor_invoked": True,
            }

    return LeanDescendantProgram()
