"""Provider-free selected100 analysis over the split-root Dryad Grok replay."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import math
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType
from typing import Any

ROOT = Path(__file__).resolve().parent
REPOSITORY = ROOT.parents[1]
READER_PATH = ROOT / "baseline_grok_selected_collection_replay.py"
COMPOSITE_PATH = ROOT / "baseline_composite_admission_v5.py"
ANALYSIS_PATH = ROOT / "baseline_composite_analysis_v5.py"
ENGINE_PATH = ROOT / "baseline_selected_analysis_runtime.py"
PIN_KEYS = frozenset({
    "analysis", "reader", "composite", "composite_analysis", "selected_engine", "workflow",
    "v1_runtime_loader", "v5_runtime_loader", "recovery_controller",
})
EXPECTED_COUNTS = {"stories": 100, "logical_requests": 2300, "native_requests": 2299,
                   "study_recovered_requests": 1, "criterion_verdicts": 17800}
TRAIN_COUNT, DEV_COUNT, QUESTION_COUNT = 70, 30, 178
ORIGINAL_COUNTS = {"TRAIN": 176, "DEV": 60}
CANONICAL_VERDICTS = frozenset({"YES", "NO", "NOT_APPLICABLE", "CANNOT_ASSESS"})


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canonical(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False) + "\n").encode()


def _hash(value: Any, label: str) -> str:
    if type(value) is not str or len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError(f"{label} must be a lowercase SHA-256")
    return value


def _strict_json(raw: bytes, label: str) -> Any:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise ValueError(f"{label} has duplicate keys")
            result[key] = value
        return result

    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=pairs,
                          parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise ValueError(f"{label} is not strict JSON") from error


def _read(path: Path | str, expected: str, label: str) -> tuple[Path, bytes]:
    checked = Path(path).resolve()
    raw = checked.read_bytes()
    if _sha(raw) != _hash(expected, label + " expected hash") or checked.read_bytes() != raw:
        raise ValueError(f"{label} hash drift")
    return checked, raw


def _load(path: Path, raw: bytes, label: str) -> ModuleType:
    spec = importlib.util.spec_from_loader(f"_dryad_grok_recovery_{label}", loader=None)
    if spec is None:
        raise ValueError(f"Cannot load {label}")
    module = importlib.util.module_from_spec(spec)
    module.__file__ = str(path)
    exec(compile(raw, str(path), "exec"), module.__dict__)  # noqa: S102 - exact hash-pinned local helper.
    return module


def _pins(value: Mapping[str, Any]) -> dict[str, str]:
    if not isinstance(value, Mapping) or set(value) != PIN_KEYS:
        raise ValueError("Split-root source pins differ")
    return {key: _hash(value[key], "Split-root source pin " + key) for key in PIN_KEYS}


def _capture(source_pins: Mapping[str, Any]) -> tuple[dict[Path, bytes], ModuleType, ModuleType, ModuleType, ModuleType]:
    pins = _pins(source_pins)
    paths = ((Path(__file__).resolve(), pins["analysis"], "analysis"), (READER_PATH, pins["reader"], "reader"),
             (COMPOSITE_PATH, pins["composite"], "composite"), (ANALYSIS_PATH, pins["composite_analysis"], "composite_analysis"),
             (ENGINE_PATH, pins["selected_engine"], "selected_engine"))
    captured: dict[Path, bytes] = {}
    loaded: dict[str, ModuleType] = {}
    for path, expected, label in paths:
        checked, raw = _read(path, expected, label)
        captured[checked] = raw
        loaded[label] = _load(checked, raw, label)
    if getattr(loaded["reader"], "RECOVERY_SHA256", None) != pins["recovery_controller"]:
        raise ValueError("Recovery controller source pin differs")
    return captured, loaded["reader"], loaded["composite"], loaded["composite_analysis"], loaded["selected_engine"]


def _unchanged(captured: Mapping[Path, bytes]) -> None:
    if any(path.read_bytes() != raw for path, raw in captured.items()):
        raise ValueError("Pinned split-root analysis source changed during execution")


def _endpoint_view(record: Mapping[str, Any]) -> dict[str, Any]:
    selection = record["selection"]
    return {"selection": {"schedule": selection["schedule"], "source": selection["source"],
                           "train_pass_ids": list(selection["train_pass_ids"]), "dev_pass_ids": list(selection["dev_pass_ids"])},
            "endpoint_grok_rows": [{"pass_id": row["pass_id"], "opaque_story_id": row["opaque_story_id"],
                                    "verdicts": row["verdict_rows"]} for row in record["collection_record"]["rows"]]}


class SelectedBaselineAdmission:
    """A new split-root admission, deliberately distinct from composite v5 admission."""

    def __init__(self, *, record: dict[str, Any], sha256: str) -> None:
        self.record = record
        self.sha256 = sha256

    @property
    def endpoint_view(self) -> dict[str, Any]:
        return _endpoint_view(self.record)


def _selection(composite: ModuleType, *, plan_root: Path, predecessor_path: Path | str, suffix_root: Path | str,
               expected_plan_sha256: str, expected_predecessor_sha256: str, expected_suffix_epoch_sha256: str,
               expected_suffix_source_sha256: str, expected_public_inputs_sha256: str) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    _raw, predecessor = composite._predecessor(predecessor_path, expected_predecessor_sha256)
    context = composite._actual_replay_context(suffix_root=Path(suffix_root), plan_root=plan_root,
                                                expected_epoch_sha256=expected_suffix_epoch_sha256,
                                                expected_suffix_source_sha256=expected_suffix_source_sha256,
                                                predecessor=predecessor)
    initialization, original, ledger = composite._predecessor_bindings(
        context, predecessor, expected_plan_sha256=expected_plan_sha256,
        expected_public_inputs_sha256=expected_public_inputs_sha256,
    )
    schedule = composite._descriptor_with_bytes(context.epoch["selected_schedule"], "Selected schedule")
    source = composite._descriptor(context.epoch["selected_schedule_source"], "Selected schedule source")
    verifier = composite._load_module(Path(source["path"]), source["sha256"], "Selected schedule source")
    verified = verifier.verify_selected_schedule(
        descriptor=composite._json(composite._read(Path(schedule["path"]), schedule["sha256"], "Selected schedule"), "Selected schedule"),
        plan_root=plan_root, expected_plan_sha256=expected_plan_sha256)
    historical_requests, historical_sessions = composite._identity_exclusions(predecessor["identity_exclusion"])
    return ({"schedule": schedule, "source": source, "verified": verified},
            {"initialization": predecessor["initialization"], "initialization_record": initialization,
             "ledger_head": predecessor["ledger_head"], "ledger_head_record": ledger,
             "original_initialization": original, "recovery_manifest": predecessor["recovery_manifest"]},
            {"requests": historical_requests, "sessions": historical_sessions})


def _admit_collection(collection: Mapping[str, Any], reader: ModuleType, composite: ModuleType, *, source_pins: Mapping[str, str],
                      reader_inputs: Mapping[str, Any], selection: Mapping[str, Any], predecessor: Mapping[str, Any],
                      exclusions: Mapping[str, set[str]]) -> SelectedBaselineAdmission:
    if (not isinstance(collection, Mapping) or collection.get("schema_version") != 1
            or collection.get("evidence_class") != "selected100_grok_collection_replay_only"
            or collection.get("counts") != EXPECTED_COUNTS or collection.get("recovered_ordinals") != [70]
            or collection.get("coverage_failures") != [] or collection.get("full_study_admitted") is not False
            or collection.get("provider_calls_made") != 0):
        raise ValueError("Complete selected collection replay is required")
    commitments = collection.get("input_commitments")
    if not isinstance(commitments, Mapping) or commitments.get("reader_sha256") != source_pins["reader"]:
        raise ValueError("Selected collection reader binding differs")
    expected_commitments = {
        "plan_sha256": reader_inputs["expected_plan_sha256"],
        "predecessor_sha256": reader_inputs["expected_predecessor_sha256"],
        "old_suffix_epoch_sha256": reader_inputs["expected_old_epoch_sha256"],
        "suffix_helper_sha256": reader_inputs["expected_suffix_source_sha256"],
        "composite_helper_sha256": source_pins["composite"],
        "recovery_controller_sha256": source_pins["recovery_controller"],
        "recovery_manifest_sha256": reader_inputs["expected_recovery_manifest_sha256"],
    }
    if any(commitments.get(key) != value for key, value in expected_commitments.items()):
        raise ValueError("Selected collection recovery controller differs")
    rows = collection.get("rows")
    identities = collection.get("native_identities")
    if not isinstance(rows, list) or len(rows) != 100 or not isinstance(identities, list) or len(identities) != 2299:
        raise ValueError("Selected collection cardinality differs")
    if collection.get("native_identity_commitment_sha256") != reader._sha(reader._canonical(identities)):
        raise ValueError("Selected collection identity commitment differs")
    expected_ordinals = [*range(1, 1611), *range(4049, 4739)]
    verified = selection["verified"]
    train_passes, dev_passes = verified["selected_train_ids"], verified["selected_dev_ids"]
    if (not isinstance(train_passes, list) or not isinstance(dev_passes, list) or len(train_passes) != TRAIN_COUNT
            or len(dev_passes) != DEV_COUNT or len(set(train_passes + dev_passes)) != 100
            or verified.get("selected_request_ordinals") != expected_ordinals):
        raise ValueError("Original selected schedule differs")
    if ([row.get("pass_id") for row in rows] != train_passes + dev_passes
            or [row.get("partition") for row in rows] != ["TRAIN"] * TRAIN_COUNT + ["DEV"] * DEV_COUNT
            or [ordinal for row in rows for ordinal in row.get("ordinals", [])] != expected_ordinals):
        raise ValueError("Selected collection schedule differs")
    if (len({row.get("opaque_story_id") for row in rows}) != 100
            or any(not isinstance(row.get("source"), Mapping) or type(row.get("score")) not in (int, float)
                   or not math.isfinite(row["score"]) or not 0 <= row["score"] <= 100
                   or type(row.get("coverage")) not in (int, float) or not math.isfinite(row["coverage"])
                   or not .88 <= row["coverage"] <= 1 for row in rows)):
        raise ValueError("Selected collection score or coverage differs")
    question_ids = verified.get("question_ids")
    if not isinstance(question_ids, list) or len(question_ids) != QUESTION_COUNT or len(set(question_ids)) != QUESTION_COUNT:
        raise ValueError("Selected schedule question inventory differs")
    for row in rows:
        verdicts = row.get("verdict_rows")
        if (not isinstance(verdicts, list) or len(verdicts) != QUESTION_COUNT
                or any(not isinstance(item, Mapping) or item.get("verdict") not in CANONICAL_VERDICTS for item in verdicts)
                or [item.get("question_id") for item in verdicts] != question_ids):
            raise ValueError("Selected collection verdict rows differ")
    if (commitments.get("selected_schedule_sha256") != selection["schedule"]["sha256"]
            or commitments.get("selected_schedule_source_sha256") != selection["source"]["sha256"]):
        raise ValueError("Selected collection schedule binding differs")
    composite._identity_sets(identities, exclusions["requests"], exclusions["sessions"])
    recovered_88 = [row for row in rows if 88 in row["ordinals"]]
    if (len(recovered_88) != 1 or reader.source_for_ordinal(88) != "recovery"
            or recovered_88[0].get("provenance") != "v4_recovered70_old_v5_replacement88"):
        raise ValueError("Historical one-shot ordinal 88 replacement differs")
    record = {"schema_version": 1, "evidence_class": "selected100_dryad_grok_split_root_admission_v1",
              "selected_baseline_admitted": True, "original_full_study_admitted": False,
              "provider_calls_made": 0, "execution_authority": False, "promotion_authority": False,
              "confirmation_authority": False, "source_pins": dict(source_pins),
              "collection_record": dict(collection), "collection_sha256": reader._sha(reader._canonical(collection)),
              "predecessor": dict(predecessor),
              "selection": {"schedule": selection["schedule"], "source": selection["source"],
                            "train_pass_ids": list(train_passes), "dev_pass_ids": list(dev_passes),
                            "request_ordinals": expected_ordinals},
              "native_identity_commitment_sha256": collection["native_identity_commitment_sha256"]}
    return SelectedBaselineAdmission(record=record, sha256=_sha(_canonical(record)))


def admit_selected_baseline(*, reader_inputs: Mapping[str, Any], source_pins: Mapping[str, Any]) -> SelectedBaselineAdmission:
    """Admit the complete replay before either TRAIN or DEV target file is opened."""
    pins = _pins(source_pins)
    required = {"plan_root", "predecessor_path", "old_suffix_root", "recovery_root", "expected_plan_sha256",
                "expected_predecessor_sha256", "expected_old_epoch_sha256", "expected_suffix_source_sha256",
                "expected_recovery_manifest_sha256", "expected_public_inputs_sha256", "approved_v4_routes", "approved_v5_routes"}
    if not isinstance(reader_inputs, Mapping) or set(reader_inputs) != required:
        raise ValueError("Selected reader inputs differ")
    captured, reader, composite, _analysis, _engine = _capture(pins)
    inputs = dict(reader_inputs)
    inputs["expected_recovery_controller_sha256"] = pins["recovery_controller"]
    reader_call = {key: value for key, value in inputs.items() if key != "expected_public_inputs_sha256"}
    collection = reader.read_selected_collection(**reader_call)
    plan_root = Path(inputs["plan_root"]).resolve()
    selection, predecessor, exclusions = _selection(
        composite, plan_root=plan_root, predecessor_path=inputs["predecessor_path"], suffix_root=inputs["old_suffix_root"],
        expected_plan_sha256=inputs["expected_plan_sha256"], expected_predecessor_sha256=inputs["expected_predecessor_sha256"],
        expected_suffix_epoch_sha256=inputs["expected_old_epoch_sha256"], expected_suffix_source_sha256=inputs["expected_suffix_source_sha256"],
        expected_public_inputs_sha256=inputs["expected_public_inputs_sha256"])
    admitted = _admit_collection(collection, reader, composite, source_pins=pins, reader_inputs=inputs, selection=selection,
                                 predecessor=predecessor, exclusions=exclusions)
    _unchanged(captured)
    return admitted


def _runtime(analysis: ModuleType, *, source_pins: Mapping[str, str], scoring_inputs: Mapping[str, Any], captured: dict[Path, bytes]) -> dict[str, Any]:
    required = {"scoring_manifest_path", "v5_runtime_manifest_path", "v5_runtime_package_root",
                "expected_scoring_manifest_sha256", "expected_v5_runtime_manifest_sha256", "expected_v5_runtime_package_manifest_sha256"}
    if not isinstance(scoring_inputs, Mapping) or set(scoring_inputs) != required:
        raise ValueError("Scoring inputs differ")
    _captured, _composer, _pure, _engine, v1_loader, v5_loader = analysis._capture(
        expected_analysis_sha256=source_pins["composite_analysis"], expected_composer_sha256=source_pins["composite"],
        expected_workflow_sha256=source_pins["workflow"], expected_engine_sha256=source_pins["selected_engine"],
        engine_label="Selected engine", expected_scoring_runtime_loader_sha256=source_pins["v1_runtime_loader"],
        expected_v5_runtime_loader_sha256=source_pins["v5_runtime_loader"])
    captured.update(_captured)
    scoring, scoring_captured = analysis._runtime_parity(
        v1_loader, v5_loader, scoring_manifest_path=scoring_inputs["scoring_manifest_path"],
        expected_scoring_manifest_sha256=scoring_inputs["expected_scoring_manifest_sha256"],
        v5_runtime_manifest_path=scoring_inputs["v5_runtime_manifest_path"],
        expected_v5_runtime_manifest_sha256=scoring_inputs["expected_v5_runtime_manifest_sha256"],
        v5_runtime_package_root=scoring_inputs["v5_runtime_package_root"],
        expected_v5_runtime_package_manifest_sha256=scoring_inputs["expected_v5_runtime_package_manifest_sha256"])
    captured.update(scoring_captured)
    return scoring


def _stage(admission: SelectedBaselineAdmission, analysis: ModuleType, *, public_inputs_path: Path | str,
           expected_public_inputs_sha256: str) -> tuple[dict[str, set[str]], dict[str, list[dict[str, Any]]], dict[str, Any], dict[str, Any]]:
    view = admission.endpoint_view
    _path, _raw, partitions = analysis._partitions(public_inputs_path, expected_public_inputs_sha256, view)
    projected, projection = analysis._project_rows(view, partitions)
    return partitions, projected, projection, analysis._engine_binding(view, partitions)


def _reader_public(reader_inputs: Mapping[str, Any], expected_public_inputs_sha256: str) -> None:
    if reader_inputs.get("expected_public_inputs_sha256") != expected_public_inputs_sha256:
        raise ValueError("Selected admission public-input binding differs")


def _protected_inputs(reader_inputs: Mapping[str, Any], scoring_inputs: Mapping[str, Any]) -> tuple[Any, ...]:
    return (reader_inputs["plan_root"], reader_inputs["predecessor_path"], reader_inputs["old_suffix_root"],
            reader_inputs["recovery_root"], scoring_inputs["scoring_manifest_path"],
            scoring_inputs["v5_runtime_manifest_path"], scoring_inputs["v5_runtime_package_root"])


def _freeze(stage: str, admission: SelectedBaselineAdmission, *, source_pins: Mapping[str, str], scoring: Mapping[str, Any],
            engine_binding: Mapping[str, Any], projection: Mapping[str, Any], target_projection: Mapping[str, Any],
            inner_raw: bytes, inner: Mapping[str, Any], train: Mapping[str, str] | None = None) -> dict[str, Any]:
    result = {"schema_version": 1, "evidence_class": f"selected100_dryad_grok_recovery_{stage.lower()}_freeze_v1",
              "stage": stage, "provider_calls_made": 0, "execution_authority": False, "promotion_authority": False,
              "confirmation_authority": False, "admission": {"sha256": admission.sha256,
                                                                 "collection_sha256": admission.record["collection_sha256"],
                                                                 "record": admission.record},
              "source_pins": dict(source_pins), "scoring_commitment_sha256": scoring["commitment_sha256"],
              "engine_binding": dict(engine_binding), "verdict_projection": dict(projection),
              "target_projection": dict(target_projection), "inner": {"sha256": _sha(inner_raw),
                                                                           "evidence_class": inner.get("evidence_class")}}
    if train is not None:
        result["train"] = dict(train)
    return result


def fit_selected_train(*, reader_inputs: Mapping[str, Any], public_inputs_path: Path | str,
                       expected_public_inputs_sha256: str, train_targets_path: Path | str, output_root: Path | str,
                       source_pins: Mapping[str, Any], scoring_inputs: Mapping[str, Any]) -> dict[str, Any]:
    """Run the unchanged 128-trial engine only after selected split-root admission."""
    pins = _pins(source_pins)
    _reader_public(reader_inputs, expected_public_inputs_sha256)
    admission = admit_selected_baseline(reader_inputs=reader_inputs, source_pins=pins)
    output = _load(ANALYSIS_PATH, _read(ANALYSIS_PATH, pins["composite_analysis"], "composite analysis")[1], "output")._output_preflight(
        output_root, *_protected_inputs(reader_inputs, scoring_inputs), public_inputs_path, train_targets_path)
    captured, _reader, _composite, analysis, engine = _capture(pins)
    partitions, projected, projection, binding = _stage(admission, analysis, public_inputs_path=public_inputs_path,
                                                          expected_public_inputs_sha256=expected_public_inputs_sha256)
    scoring = _runtime(analysis, source_pins=pins, scoring_inputs=scoring_inputs, captured=captured)
    pure = _load(analysis.WORKFLOW_PATH, _read(analysis.WORKFLOW_PATH, pins["workflow"], "workflow")[1], "workflow")
    target_path, target_raw, targets, target_projection = analysis._selected_targets(
        pure, train_targets_path, pure.TRAIN_TARGETS_SHA256, "TRAIN", partitions["TRAIN"],
        _read(public_inputs_path, expected_public_inputs_sha256, "public inputs")[1])
    captured[target_path] = target_raw
    _unchanged(captured)
    fit = engine.fit_train(projected["TRAIN"], targets, selection_binding=binding,
                           expected_successor_sha256=pins["selected_engine"],
                           baseline_manifest_path=scoring_inputs["scoring_manifest_path"],
                           baseline_manifest_sha256=scoring_inputs["expected_scoring_manifest_sha256"])
    if not isinstance(fit, Mapping) or fit.get("evidence_class") != "selected100_amended_fit_unadmitted":
        raise ValueError("Unchanged selected TRAIN engine class differs")
    pure._inner_commitments(fit, projected["TRAIN"], targets, target_projection["selected_target_sha256"])
    fit_raw = _canonical(fit)
    _unchanged(captured)
    freeze = _freeze("TRAIN", admission, source_pins=pins, scoring=scoring, engine_binding=binding,
                     projection=projection, target_projection=target_projection, inner_raw=fit_raw, inner=fit)
    return {"artifacts": analysis._write(output, {"selected100-grok-recovery-fit-v1.json": fit_raw,
                                                     "selected100-grok-recovery-train-freeze-v1.json": _canonical(freeze)}),
            "freeze": freeze}


def _train_binding(fit_raw: bytes, freeze_raw: bytes, *, admission: SelectedBaselineAdmission, source_pins: Mapping[str, str],
                   scoring: Mapping[str, Any], binding: Mapping[str, Any], projection: Mapping[str, Any],
                   expected_train_target_sha256: str) -> None:
    fit = _strict_json(fit_raw, "Frozen selected TRAIN fit")
    freeze = _strict_json(freeze_raw, "Frozen selected TRAIN freeze")
    if (not isinstance(fit, Mapping) or not isinstance(freeze, Mapping)
            or freeze.get("evidence_class") != "selected100_dryad_grok_recovery_train_freeze_v1"
            or freeze.get("stage") != "TRAIN" or freeze.get("admission") != {"sha256": admission.sha256,
                                                                                "collection_sha256": admission.record["collection_sha256"],
                                                                                "record": admission.record}
            or freeze.get("source_pins") != dict(source_pins) or freeze.get("scoring_commitment_sha256") != scoring["commitment_sha256"]
            or freeze.get("engine_binding") != dict(binding) or freeze.get("verdict_projection") != dict(projection)
            or freeze.get("inner", {}).get("sha256") != _sha(fit_raw)
            or fit.get("input_commitments", {}).get("verdict_rows_sha256") != projection["projected_rows_sha256"]["TRAIN"]):
        raise ValueError("Selected TRAIN freeze binding differs")
    target = freeze.get("target_projection")
    commitments = fit.get("input_commitments", {})
    if (not isinstance(target, Mapping) or target.get("original_target_sha256") != expected_train_target_sha256
            or target.get("original_count") != ORIGINAL_COUNTS["TRAIN"]
            or target.get("selected_count") != TRAIN_COUNT or target.get("selected_target_sha256") != commitments.get("target_rows_sha256")
            or any(_hash(target.get(name), "Selected TRAIN target " + name) != target[name]
                   for name in ("original_target_sha256", "selected_target_sha256"))):
        raise ValueError("Selected TRAIN target projection differs")


def _compute_dev(*, reader_inputs: Mapping[str, Any], public_inputs_path: Path | str, expected_public_inputs_sha256: str,
                 dev_targets_path: Path | str, fit_path: Path | str, train_freeze_path: Path | str,
                 expected_fit_sha256: str, expected_train_freeze_sha256: str, source_pins: Mapping[str, Any],
                 scoring_inputs: Mapping[str, Any]) -> tuple[dict[str, Any], bytes, dict[str, Any], dict[Path, bytes]]:
    pins = _pins(source_pins)
    _reader_public(reader_inputs, expected_public_inputs_sha256)
    admission = admit_selected_baseline(reader_inputs=reader_inputs, source_pins=pins)
    captured, _reader, _composite, analysis, engine = _capture(pins)
    partitions, projected, projection, binding = _stage(admission, analysis, public_inputs_path=public_inputs_path,
                                                          expected_public_inputs_sha256=expected_public_inputs_sha256)
    scoring = _runtime(analysis, source_pins=pins, scoring_inputs=scoring_inputs, captured=captured)
    fit_checked, fit_raw = _read(fit_path, expected_fit_sha256, "Frozen selected TRAIN fit")
    freeze_checked, freeze_raw = _read(train_freeze_path, expected_train_freeze_sha256, "Frozen selected TRAIN freeze")
    captured[fit_checked], captured[freeze_checked] = fit_raw, freeze_raw
    pure = _load(analysis.WORKFLOW_PATH, _read(analysis.WORKFLOW_PATH, pins["workflow"], "workflow")[1], "workflow")
    _train_binding(fit_raw, freeze_raw, admission=admission, source_pins=pins, scoring=scoring, binding=binding,
                   projection=projection, expected_train_target_sha256=pure.TRAIN_TARGETS_SHA256)
    _unchanged(captured)
    engine.validate_frozen_fit(fit_raw, expected_fit_sha256=expected_fit_sha256, selection_binding=binding,
                               expected_successor_sha256=pins["selected_engine"],
                               baseline_manifest_path=scoring_inputs["scoring_manifest_path"],
                               baseline_manifest_sha256=scoring_inputs["expected_scoring_manifest_sha256"])
    _unchanged(captured)
    target_path, target_raw, targets, target_projection = analysis._selected_targets(
        pure, dev_targets_path, pure.DEV_TARGETS_SHA256, "DEV", partitions["DEV"],
        _read(public_inputs_path, expected_public_inputs_sha256, "public inputs")[1])
    captured[target_path] = target_raw
    result = engine.evaluate_dev(projected["DEV"], targets, fit_raw, expected_fit_sha256=expected_fit_sha256,
                                 selection_binding=binding, expected_successor_sha256=pins["selected_engine"],
                                 baseline_manifest_path=scoring_inputs["scoring_manifest_path"],
                                 baseline_manifest_sha256=scoring_inputs["expected_scoring_manifest_sha256"])
    if not isinstance(result, Mapping) or result.get("evidence_class") != "selected100_amended_dev_comparison_unadmitted":
        raise ValueError("Unchanged selected DEV engine class differs")
    pure._inner_commitments(result, projected["DEV"], targets, target_projection["selected_target_sha256"])
    raw = _canonical(result)
    _unchanged(captured)
    freeze = _freeze("DEV", admission, source_pins=pins, scoring=scoring, engine_binding=binding, projection=projection,
                     target_projection=target_projection, inner_raw=raw, inner=result,
                     train={"fit_sha256": expected_fit_sha256, "freeze_sha256": expected_train_freeze_sha256})
    return dict(result), raw, freeze, captured


def compare_selected_dev(*, reader_inputs: Mapping[str, Any], public_inputs_path: Path | str,
                         expected_public_inputs_sha256: str, dev_targets_path: Path | str, fit_path: Path | str,
                         train_freeze_path: Path | str, output_root: Path | str, expected_fit_sha256: str,
                         expected_train_freeze_sha256: str, source_pins: Mapping[str, Any],
                         scoring_inputs: Mapping[str, Any]) -> dict[str, Any]:
    """Open DEV targets only after full re-admission and frozen-fit semantic validation."""
    pins = _pins(source_pins)
    _reader_public(reader_inputs, expected_public_inputs_sha256)
    analysis = _load(ANALYSIS_PATH, _read(ANALYSIS_PATH, pins["composite_analysis"], "composite analysis")[1], "output")
    output = analysis._output_preflight(output_root, *_protected_inputs(reader_inputs, scoring_inputs), public_inputs_path,
                                         dev_targets_path, fit_path, train_freeze_path)
    result, raw, freeze, _captured = _compute_dev(reader_inputs=reader_inputs, public_inputs_path=public_inputs_path,
        expected_public_inputs_sha256=expected_public_inputs_sha256, dev_targets_path=dev_targets_path, fit_path=fit_path,
        train_freeze_path=train_freeze_path, expected_fit_sha256=expected_fit_sha256,
        expected_train_freeze_sha256=expected_train_freeze_sha256, source_pins=pins, scoring_inputs=scoring_inputs)
    freeze["selection_frozen_at"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    return {"artifacts": analysis._write(output, {"selected100-grok-recovery-dev-comparison-v1.json": raw,
                                                     "selected100-grok-recovery-dev-freeze-v1.json": _canonical(freeze)}),
            "freeze": freeze, "comparison": result}


def replay_selected_dev(*, reader_inputs: Mapping[str, Any], public_inputs_path: Path | str,
                        expected_public_inputs_sha256: str, dev_targets_path: Path | str, fit_path: Path | str,
                        train_freeze_path: Path | str, dev_comparison_path: Path | str, dev_freeze_path: Path | str,
                        expected_fit_sha256: str, expected_train_freeze_sha256: str, expected_dev_comparison_sha256: str,
                        expected_dev_freeze_sha256: str, source_pins: Mapping[str, Any],
                        scoring_inputs: Mapping[str, Any]) -> dict[str, Any]:
    """Reconstruct fixed DEV bytes without writes or fresh selection timestamps."""
    _reader_public(reader_inputs, expected_public_inputs_sha256)
    comparison_path, comparison_raw = _read(dev_comparison_path, expected_dev_comparison_sha256, "Stored DEV comparison")
    freeze_path, freeze_raw = _read(dev_freeze_path, expected_dev_freeze_sha256, "Stored DEV freeze")
    stored = _strict_json(freeze_raw, "Stored DEV freeze")
    timestamp = stored.get("selection_frozen_at") if isinstance(stored, Mapping) else None
    try:
        parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00")) if type(timestamp) is str else None
    except ValueError as error:
        raise ValueError("Stored DEV timestamp differs") from error
    if parsed is None or parsed.tzinfo != timezone.utc or parsed.isoformat().replace("+00:00", "Z") != timestamp:
        raise ValueError("Stored DEV timestamp differs")
    result, raw, freeze, captured = _compute_dev(reader_inputs=reader_inputs, public_inputs_path=public_inputs_path,
        expected_public_inputs_sha256=expected_public_inputs_sha256, dev_targets_path=dev_targets_path, fit_path=fit_path,
        train_freeze_path=train_freeze_path, expected_fit_sha256=expected_fit_sha256,
        expected_train_freeze_sha256=expected_train_freeze_sha256, source_pins=source_pins, scoring_inputs=scoring_inputs)
    freeze["selection_frozen_at"] = timestamp
    if raw != comparison_raw or _canonical(freeze) != freeze_raw:
        raise ValueError("Stored split-root DEV replay differs")
    captured[comparison_path], captured[freeze_path] = comparison_raw, freeze_raw
    _unchanged(captured)
    return {"comparison_raw": comparison_raw, "freeze_raw": freeze_raw, "freeze": freeze, "comparison": result}
