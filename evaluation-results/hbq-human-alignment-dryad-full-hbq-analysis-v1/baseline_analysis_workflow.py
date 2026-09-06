"""Two-stage admitted TRAIN/DEV wrapper for the fixed Dryad analysis.

The optimizer and DEV comparison remain their original unadmitted records. This
module calls the complete native admission replay at each outer stage and binds
that replay to a fresh, external freeze without creating provider authority.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import uuid
from collections.abc import Mapping
from pathlib import Path
from types import ModuleType
from typing import Any

ROOT = Path(__file__).resolve().parent
REPOSITORY = ROOT.parents[1]
ADMISSION_PATH = ROOT / "baseline_measurement_admission.py"
OPTIMIZER_PATH = ROOT / "optimizer.py"
COMPARISON_PATH = ROOT / "dev_comparison.py"
SOURCE_PATH = ROOT / "source.py"
PUBLIC_INPUTS_SHA256 = "6254f58d3366667c9578e2661a1ca0d105a603a0f8affe2d925a767957937c42"
TARGET_FREEZE_SHA256 = "cf8d2306fd4977e0ed7d4572987b9665029c37a46107ba71d847a2b4de026988"
TRAIN_TARGETS_SHA256 = "029796e36051e791bd1990f7d09c668778bcf5a63ef43ae3dfff984da93156dd"
DEV_TARGETS_SHA256 = "d9071d48465faf7beb37b249b5120e33645a3bc0925aec7856402d75fc2d35b5"
TRAIN_COUNT = 176
DEV_COUNT = 60
ADMITTED_COUNT = TRAIN_COUNT + DEV_COUNT
REQUEST_COUNT = 5428


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canonical(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")


def _hash(value: Any, label: str) -> str:
    if type(value) is not str or len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError(f"{label} must be a lowercase SHA-256")
    return value


def _json(raw: bytes, label: str) -> Any:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in items:
            if key in value:
                raise ValueError(f"{label} has duplicate keys")
            value[key] = item
        return value

    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=pairs,
                          parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise ValueError(f"{label} is not strict JSON") from error


def _read_pinned(path: Path | str, expected: str, label: str) -> tuple[Path, bytes]:
    checked = Path(path).resolve()
    raw = checked.read_bytes()
    if _sha(raw) != _hash(expected, f"{label} expected hash"):
        raise ValueError(f"{label} hash drift")
    return checked, raw


def _load_module(path: Path, raw: bytes, label: str) -> ModuleType:
    name = f"_dryad_admitted_workflow_{label}_{uuid.uuid4().hex}"
    spec = importlib.util.spec_from_loader(name, loader=None)
    if spec is None:
        raise ValueError(f"Cannot load {label}")
    module = importlib.util.module_from_spec(spec)
    module.__file__ = str(path)
    exec(compile(raw, str(path), "exec"), module.__dict__)  # noqa: S102 - execute only hash-pinned local sources.
    return module


def _capture(expected_workflow_sha256: str, expected_admission_sha256: str,
             expected_engine_sha256: str, engine_path: Path, engine_label: str,
             runtime_manifest_path: Path | str, expected_runtime_manifest_sha256: str) -> tuple[dict[Path, bytes], ModuleType, ModuleType]:
    own_path, own_raw = _read_pinned(Path(__file__), expected_workflow_sha256, "Workflow")
    admission_path, admission_raw = _read_pinned(ADMISSION_PATH, expected_admission_sha256, "Admission")
    loaded_engine_path, engine_raw = _read_pinned(engine_path, expected_engine_sha256, engine_label)
    manifest_path, manifest_raw = _read_pinned(runtime_manifest_path, expected_runtime_manifest_sha256, "Runtime manifest")
    source_raw = SOURCE_PATH.read_bytes()
    return ({own_path: own_raw, admission_path: admission_raw, loaded_engine_path: engine_raw,
             manifest_path: manifest_raw, SOURCE_PATH: source_raw}, _load_module(admission_path, admission_raw, "admission"),
            _load_module(loaded_engine_path, engine_raw, engine_label))


def _unchanged(captured: Mapping[Path, bytes]) -> None:
    if any(path.read_bytes() != raw for path, raw in captured.items()):
        raise ValueError("Pinned admitted-workflow source changed during execution")


def _target_freeze(path: Path | str) -> tuple[Path, bytes, dict[str, Any]]:
    checked, raw = _read_pinned(path, TARGET_FREEZE_SHA256, "Target freeze")
    value = _json(raw, "Target freeze")
    expected = {
        "TRAIN": {"stories": TRAIN_COUNT, "ratings": 2116, "target_sha256": TRAIN_TARGETS_SHA256},
        "DEV": {"stories": DEV_COUNT, "ratings": 720, "target_sha256": DEV_TARGETS_SHA256},
    }
    if not isinstance(value, dict) or value.get("schema_version") != 1 or value.get("evidence_class") != "provider_free_human_target_preparation" or value.get("partitions") != expected:
        raise ValueError("Target freeze contract drift")
    return checked, raw, value


def _partition_ids(path: Path | str) -> tuple[Path, bytes, dict[str, set[str]]]:
    checked, raw = _read_pinned(path, PUBLIC_INPUTS_SHA256, "Public inputs")
    value = _json(raw, "Public inputs")
    if not isinstance(value, dict) or set(value) != {"TRAIN", "DEV"}:
        raise ValueError("Public input partition schema differs")
    result: dict[str, set[str]] = {}
    for partition, count in (("TRAIN", TRAIN_COUNT), ("DEV", DEV_COUNT)):
        rows = value[partition]
        if not isinstance(rows, list) or len(rows) != count:
            raise ValueError("Public input partition count differs")
        ids = {row.get("opaque_story_id") for row in rows if isinstance(row, dict)}
        if len(ids) != count or any(type(story) is not str or not story for story in ids):
            raise ValueError("Public input partition IDs differ")
        result[partition] = ids
    if result["TRAIN"].intersection(result["DEV"]) or len(result["TRAIN"] | result["DEV"]) != ADMITTED_COUNT:
        raise ValueError("Public input partitions are not disjoint and exhaustive")
    return checked, raw, result


def _admit(module: ModuleType, public_inputs_path: Path | str, plan_root: Path | str,
           execution_root: Path | str, runtime_manifest_path: Path | str, *,
           expected_plan_sha256: str, expected_final_settlement_sha256: str,
           expected_execution_source_sha256: str, expected_route_sha256: str,
           expected_runtime_manifest_sha256: str, expected_admission_sha256: str,
           expected_reviewer_task: str, expected_initialization_sha256: str) -> dict[str, Any]:
    result = module.admit_baseline(
        Path(public_inputs_path), Path(plan_root), Path(execution_root), Path(runtime_manifest_path),
        expected_plan_sha256=expected_plan_sha256,
        expected_final_settlement_sha256=expected_final_settlement_sha256,
        expected_execution_source_sha256=expected_execution_source_sha256,
        expected_route_sha256=expected_route_sha256,
        expected_runtime_manifest_sha256=expected_runtime_manifest_sha256,
        expected_admission_sha256=expected_admission_sha256,
        expected_reviewer_task=expected_reviewer_task,
        expected_initialization_sha256=expected_initialization_sha256,
    )
    if not isinstance(result, dict) or result.get("evidence_class") != "complete_native_baseline_measurement_admission" or result.get("execution_authority") is not False or result.get("provider_calls") != 0 or result.get("admitted_passes") != ADMITTED_COUNT or result.get("logical_requests") != REQUEST_COUNT:
        raise ValueError("Complete native baseline admission is required")
    # Admission uses integer cohort keys in memory; hash its persisted JSON shape.
    return _json(_canonical(result), "Admission result")


def _project_rows(admission: Mapping[str, Any], partitions: Mapping[str, set[str]]) -> tuple[dict[str, list[dict[str, Any]]], dict[str, Any]]:
    rows = admission.get("endpoint_grok_rows")
    if not isinstance(rows, list) or len(rows) != ADMITTED_COUNT:
        raise ValueError("Admission does not contain all 236 Grok rows")
    projected: dict[str, list[dict[str, Any]]] = {"TRAIN": [], "DEV": []}
    all_ids: set[str] = set()
    for row in rows:
        if not isinstance(row, dict) or type(row.get("opaque_story_id")) is not str or not row["opaque_story_id"] or "verdicts" not in row:
            raise ValueError("Admission row lacks its opaque identity or verdicts")
        story = row["opaque_story_id"]
        if story in all_ids:
            raise ValueError("Admission rows have duplicate opaque story IDs")
        all_ids.add(story)
        matching = [name for name, ids in partitions.items() if story in ids]
        if len(matching) != 1:
            raise ValueError("Admission row is outside the verified public partition")
        projected[matching[0]].append({"opaque_story_id": story, "verdicts": row["verdicts"]})
    all_expected = partitions["TRAIN"] | partitions["DEV"]
    if all_ids != all_expected or any({row["opaque_story_id"] for row in projected[name]} != partitions[name] for name in projected):
        raise ValueError("Admission rows are not globally partition-exhaustive")
    for rows_for_partition in projected.values():
        rows_for_partition.sort(key=lambda row: row["opaque_story_id"])
    return projected, {
        "admission_sha256": _sha(_canonical(admission)),
        "endpoint_grok_rows_sha256": _sha(_canonical(rows)),
        "projected_rows_sha256": {name: _sha(_canonical(rows_for_partition)) for name, rows_for_partition in projected.items()},
    }


def _targets(path: Path | str, expected: str, partition: str, ids: set[str]) -> tuple[Path, bytes, list[dict[str, Any]]]:
    checked, raw = _read_pinned(path, expected, f"{partition} targets")
    value = _json(raw, f"{partition} targets")
    if not isinstance(value, list) or len(value) != len(ids):
        raise ValueError(f"{partition} target count differs")
    found = {row.get("opaque_story_id") for row in value if isinstance(row, dict) and row.get("partition") == partition}
    if found != ids or len(found) != len(value):
        raise ValueError(f"{partition} target IDs differ from the public partition")
    return checked, raw, value


def _output_preflight(path: Path | str, *protected_paths: Path | str) -> Path:
    output = Path(os.path.abspath(path)).resolve()
    protected = [REPOSITORY]
    for protected_path in protected_paths:
        candidate = Path(os.path.abspath(protected_path)).resolve()
        protected.append(candidate.parent if candidate.is_file() else candidate)
    if output.exists() or any(output.is_relative_to(candidate) or candidate.is_relative_to(output) for candidate in protected):
        raise ValueError("Stage output must be a fresh external directory")
    return output


def _store(path: Path, raw: bytes) -> None:
    with path.open("xb") as stream:
        stream.write(raw)


def _write(output: Path, artifacts: Mapping[str, bytes]) -> dict[str, str]:
    staging = output.with_name(f".{output.name}.staging-{uuid.uuid4().hex}")
    try:
        staging.mkdir(parents=True, exist_ok=False)
        for name, raw in artifacts.items():
            _store(staging / name, raw)
        reported: dict[str, str] = {}
        for name, raw in artifacts.items():
            stored = (staging / name).read_bytes()
            if stored != raw:
                raise ValueError("Written stage artifact differs from its frozen bytes")
            reported[name] = _sha(stored)
        staging.replace(output)
        return reported
    except Exception as error:
        raise RuntimeError(f"Stage retained at {staging}") from error


def _inner_commitments(inner: Mapping[str, Any], projected_rows: list[dict[str, Any]],
                       targets: list[dict[str, Any]], target_sha256: str) -> None:
    target_canonical = _canonical(sorted(targets, key=lambda row: row["opaque_story_id"]))
    expected = {
        "verdict_rows_sha256": _sha(_canonical(projected_rows)),
        "target_rows_sha256": _sha(target_canonical),
    }
    if _sha(target_canonical) != target_sha256 or inner.get("input_commitments") != expected:
        raise ValueError("Inner input commitments differ from admitted rows or frozen targets")


def _source_metadata(raw: bytes) -> dict[str, Any]:
    return {
        "current_source_verifier": {"path": SOURCE_PATH.relative_to(REPOSITORY).as_posix(), "sha256": _sha(raw)},
        "current_source_verify_ran": False,
        "note": "target-freeze byte commitments control; its historical generator/protocol provenance is retained separately",
    }


def _outer_freeze(stage: str, admission: dict[str, Any], admission_binding: dict[str, Any],
                  partitions: Mapping[str, set[str]], target_freeze: dict[str, Any],
                  target_raw: bytes, target_hash: str, runtime_manifest_sha256: str,
                  workflow_sha256: str, admission_source_sha256: str, engine_source_sha256: str,
                  engine_label: str, inner_raw: bytes, inner: dict[str, Any], source_raw: bytes) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "evidence_class": f"admitted_{stage.lower()}_outer_freeze",
        "stage": stage,
        "provider_calls": 0,
        "execution_authority": False,
        "promotion_authority": False,
        "confirmation_authority": False,
        "sol_validation": False,
        "workflow": {"sha256": workflow_sha256},
        "runtime_manifest": {"sha256": runtime_manifest_sha256},
        "sources": {
            "admission_sha256": admission_source_sha256,
            f"{engine_label}_sha256": engine_source_sha256,
            "target_freeze_sha256": TARGET_FREEZE_SHA256,
        },
        "target_freeze": target_freeze,
        "target": {"partition": stage, "sha256": target_hash, "bytes": len(target_raw)},
        "public_partitions": {name: sorted(ids) for name, ids in partitions.items()},
        "admission": admission,
        "admission_binding": admission_binding,
        "inner": {"sha256": _sha(inner_raw), "evidence_class": inner.get("evidence_class")},
        "source_provenance": _source_metadata(source_raw),
    }


def fit_admitted_train(
    public_inputs_path: Path | str, plan_root: Path | str, execution_root: Path | str,
    runtime_manifest_path: Path | str, target_freeze_path: Path | str,
    train_targets_path: Path | str, output_root: Path | str, *,
    expected_plan_sha256: str, expected_final_settlement_sha256: str,
    expected_execution_source_sha256: str, expected_route_sha256: str,
    expected_runtime_manifest_sha256: str, expected_admission_sha256: str,
    expected_reviewer_task: str, expected_initialization_sha256: str,
    expected_workflow_sha256: str, expected_optimizer_sha256: str,
) -> dict[str, Any]:
    """Admit all native rows, fit the frozen TRAIN 176, then write a fresh freeze."""
    output = _output_preflight(output_root, public_inputs_path, plan_root, execution_root,
                                runtime_manifest_path, target_freeze_path, train_targets_path)
    captured, admission_module, optimizer = _capture(
        expected_workflow_sha256, expected_admission_sha256, expected_optimizer_sha256,
        OPTIMIZER_PATH, "Optimizer", runtime_manifest_path, expected_runtime_manifest_sha256,
    )
    freeze_path, freeze_raw, freeze = _target_freeze(target_freeze_path)
    captured[freeze_path] = freeze_raw
    admission = _admit(
        admission_module, public_inputs_path, plan_root, execution_root, runtime_manifest_path,
        expected_plan_sha256=expected_plan_sha256,
        expected_final_settlement_sha256=expected_final_settlement_sha256,
        expected_execution_source_sha256=expected_execution_source_sha256,
        expected_route_sha256=expected_route_sha256,
        expected_runtime_manifest_sha256=expected_runtime_manifest_sha256,
        expected_admission_sha256=expected_admission_sha256,
        expected_reviewer_task=expected_reviewer_task,
        expected_initialization_sha256=expected_initialization_sha256,
    )
    inputs_path, inputs_raw, partitions = _partition_ids(public_inputs_path)
    captured[inputs_path] = inputs_raw
    projected, admission_binding = _project_rows(admission, partitions)
    targets_path, target_raw, targets = _targets(train_targets_path, TRAIN_TARGETS_SHA256, "TRAIN", partitions["TRAIN"])
    captured[targets_path] = target_raw
    _unchanged(captured)
    fit = optimizer.fit_train(
        projected["TRAIN"], targets, expected_optimizer_sha256=expected_optimizer_sha256,
        baseline_manifest_path=runtime_manifest_path,
        baseline_manifest_sha256=expected_runtime_manifest_sha256,
    )
    if not isinstance(fit, dict) or fit.get("evidence_class") != "baseline_source_verified_fit_unadmitted":
        raise ValueError("Inner TRAIN fit must retain its source-verified unadmitted class")
    _inner_commitments(fit, projected["TRAIN"], targets, TRAIN_TARGETS_SHA256)
    fit_raw = _canonical(fit)
    _unchanged(captured)
    outer = _outer_freeze("TRAIN", admission, admission_binding, partitions, freeze, target_raw,
                          TRAIN_TARGETS_SHA256, expected_runtime_manifest_sha256,
                          expected_workflow_sha256, expected_admission_sha256,
                          expected_optimizer_sha256, "optimizer", fit_raw, fit, captured[SOURCE_PATH])
    freeze_raw = _canonical(outer)
    artifacts = {"fit-unadmitted.json": fit_raw, "train-freeze.json": freeze_raw}
    return {"artifacts": _write(output, artifacts), "freeze": outer}


def _train_freeze(path: Path | str, expected: str, fit_raw: bytes, admission_binding: dict[str, Any],
                  expected_runtime_manifest_sha256: str, expected_admission_sha256: str,
                  expected_workflow_sha256: str) -> tuple[Path, bytes, dict[str, Any]]:
    checked, raw = _read_pinned(path, expected, "TRAIN freeze")
    value = _json(raw, "TRAIN freeze")
    if not isinstance(value, dict) or value.get("stage") != "TRAIN" or value.get("evidence_class") != "admitted_train_outer_freeze":
        raise ValueError("TRAIN freeze stage differs")
    if value.get("inner", {}).get("sha256") != _sha(fit_raw) or value.get("workflow") != {"sha256": expected_workflow_sha256} or value.get("runtime_manifest") != {"sha256": expected_runtime_manifest_sha256}:
        raise ValueError("TRAIN freeze does not bind the supplied fit or runtime")
    sources = value.get("sources")
    if not isinstance(sources, dict) or sources.get("admission_sha256") != expected_admission_sha256 or sources.get("target_freeze_sha256") != TARGET_FREEZE_SHA256:
        raise ValueError("TRAIN freeze source binding differs")
    if value.get("admission_binding") != admission_binding:
        raise ValueError("TRAIN freeze admission binding differs from current admission")
    return checked, raw, value


def compare_admitted_dev(
    public_inputs_path: Path | str, plan_root: Path | str, execution_root: Path | str,
    runtime_manifest_path: Path | str, target_freeze_path: Path | str,
    dev_targets_path: Path | str, fit_path: Path | str, train_freeze_path: Path | str,
    output_root: Path | str, *, expected_plan_sha256: str,
    expected_final_settlement_sha256: str, expected_execution_source_sha256: str,
    expected_route_sha256: str, expected_runtime_manifest_sha256: str,
    expected_admission_sha256: str, expected_reviewer_task: str,
    expected_initialization_sha256: str, expected_workflow_sha256: str,
    expected_comparison_sha256: str, expected_fit_sha256: str,
    expected_train_freeze_sha256: str,
) -> dict[str, Any]:
    """Re-admit rows and compare DEV only after the exact TRAIN freeze binds."""
    output = _output_preflight(output_root, public_inputs_path, plan_root, execution_root,
                                runtime_manifest_path, target_freeze_path, dev_targets_path,
                                fit_path, train_freeze_path)
    captured, admission_module, comparison = _capture(
        expected_workflow_sha256, expected_admission_sha256, expected_comparison_sha256,
        COMPARISON_PATH, "Comparison", runtime_manifest_path, expected_runtime_manifest_sha256,
    )
    freeze_path, freeze_raw, freeze = _target_freeze(target_freeze_path)
    captured[freeze_path] = freeze_raw
    admission = _admit(
        admission_module, public_inputs_path, plan_root, execution_root, runtime_manifest_path,
        expected_plan_sha256=expected_plan_sha256,
        expected_final_settlement_sha256=expected_final_settlement_sha256,
        expected_execution_source_sha256=expected_execution_source_sha256,
        expected_route_sha256=expected_route_sha256,
        expected_runtime_manifest_sha256=expected_runtime_manifest_sha256,
        expected_admission_sha256=expected_admission_sha256,
        expected_reviewer_task=expected_reviewer_task,
        expected_initialization_sha256=expected_initialization_sha256,
    )
    inputs_path, inputs_raw, partitions = _partition_ids(public_inputs_path)
    captured[inputs_path] = inputs_raw
    projected, admission_binding = _project_rows(admission, partitions)
    fit_checked, fit_raw = _read_pinned(fit_path, expected_fit_sha256, "Frozen TRAIN fit")
    captured[fit_checked] = fit_raw
    train_freeze_checked, train_freeze_raw, _ = _train_freeze(
        train_freeze_path, expected_train_freeze_sha256, fit_raw, admission_binding,
        expected_runtime_manifest_sha256, expected_admission_sha256, expected_workflow_sha256,
    )
    captured[train_freeze_checked] = train_freeze_raw
    dev_path, dev_raw, targets = _targets(dev_targets_path, DEV_TARGETS_SHA256, "DEV", partitions["DEV"])
    captured[dev_path] = dev_raw
    _unchanged(captured)
    result = comparison.evaluate_dev(
        projected["DEV"], targets, fit_raw, expected_fit_sha256=expected_fit_sha256,
        expected_comparison_sha256=expected_comparison_sha256,
        baseline_manifest_path=runtime_manifest_path,
        baseline_manifest_sha256=expected_runtime_manifest_sha256,
    )
    if not isinstance(result, dict) or result.get("evidence_class") != "baseline_source_verified_dev_comparison_unadmitted":
        raise ValueError("Inner DEV comparison must retain its source-verified unadmitted class")
    _inner_commitments(result, projected["DEV"], targets, DEV_TARGETS_SHA256)
    result_raw = _canonical(result)
    _unchanged(captured)
    outer = _outer_freeze("DEV", admission, admission_binding, partitions, freeze, dev_raw,
                          DEV_TARGETS_SHA256, expected_runtime_manifest_sha256,
                          expected_workflow_sha256, expected_admission_sha256,
                          expected_comparison_sha256, "comparison", result_raw, result, captured[SOURCE_PATH])
    outer["train_freeze"] = {"sha256": expected_train_freeze_sha256, "fit_sha256": expected_fit_sha256}
    freeze_raw = _canonical(outer)
    artifacts = {"dev-comparison-unadmitted.json": result_raw, "dev-freeze.json": freeze_raw}
    return {"artifacts": _write(output, artifacts), "freeze": outer}
