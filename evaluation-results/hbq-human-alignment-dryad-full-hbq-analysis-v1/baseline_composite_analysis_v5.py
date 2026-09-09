"""TRAIN/DEV analysis over the successor's complete composite Dryad admission.

This adapter is provider-free.  It composes a fully revalidated v4/recovered/v5
admission before reading either target partition, then delegates unchanged
TRAIN fitting and DEV comparison to the pinned v1 scoring engines.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import uuid
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType
from typing import Any

ROOT = Path(__file__).resolve().parent
REPOSITORY = ROOT.parents[1]
COMPOSER_PATH = ROOT / "baseline_composite_admission_v5.py"
WORKFLOW_PATH = ROOT / "baseline_analysis_workflow.py"
OPTIMIZER_PATH = ROOT / "optimizer.py"
COMPARISON_PATH = ROOT / "dev_comparison.py"
RUNTIME_V1_PATH = ROOT / "baseline_native_runtime.py"
RUNTIME_V5_PATH = ROOT / "baseline_native_runtime_v5.py"
TRAIN_COUNT = 176
DEV_COUNT = 60
QUESTION_COUNT = 178
CANONICAL_VERDICTS = ("YES", "NO", "NOT_APPLICABLE", "CANNOT_ASSESS")


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canonical(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")


def _hash(value: Any, label: str) -> str:
    if type(value) is not str or len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError(f"{label} must be a lowercase SHA-256")
    return value


def _read_pinned(path: Path | str, expected: str, label: str) -> tuple[Path, bytes]:
    checked = Path(path).resolve()
    raw = checked.read_bytes()
    if _sha(raw) != _hash(expected, f"{label} expected hash"):
        raise ValueError(f"{label} hash drift")
    return checked, raw


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


def _load(path: Path, raw: bytes, label: str) -> ModuleType:
    name = f"_dryad_composite_analysis_{label}_{uuid.uuid4().hex}"
    spec = importlib.util.spec_from_loader(name, loader=None)
    if spec is None:
        raise ValueError(f"Cannot load {label}")
    module = importlib.util.module_from_spec(spec)
    module.__file__ = str(path)
    exec(compile(raw, str(path), "exec"), module.__dict__)  # noqa: S102 - exact hash-pinned local source.
    return module


def _unchanged(captured: Mapping[Path, bytes]) -> None:
    if any(path.read_bytes() != raw for path, raw in captured.items()):
        raise ValueError("Pinned composite analysis source changed during execution")


def _partitions(path: Path | str, expected: str) -> tuple[Path, bytes, dict[str, set[str]]]:
    checked, raw = _read_pinned(path, expected, "Public inputs")
    value = _strict_json(raw, "Public inputs")
    if not isinstance(value, dict) or set(value) != {"TRAIN", "DEV"}:
        raise ValueError("Public input partition schema differs")
    result: dict[str, set[str]] = {}
    for partition, count in (("TRAIN", TRAIN_COUNT), ("DEV", DEV_COUNT)):
        rows = value[partition]
        if not isinstance(rows, list) or len(rows) != count:
            raise ValueError("Public input partition count differs")
        ids = {row.get("opaque_story_id") for row in rows if isinstance(row, dict)}
        if len(ids) != count or any(type(item) is not str or not item for item in ids):
            raise ValueError("Public input partition identities differ")
        result[partition] = ids
    if result["TRAIN"] & result["DEV"]:
        raise ValueError("Public input partitions overlap")
    return checked, raw, result


def _output_preflight(path: Path | str, *protected: Path | str) -> Path:
    output = Path(os.path.abspath(path)).resolve()
    roots = [REPOSITORY]
    for item in protected:
        checked = Path(os.path.abspath(item)).resolve()
        roots.append(checked.parent if checked.is_file() else checked)
    if output.exists() or any(output.is_relative_to(root) or root.is_relative_to(output) for root in roots):
        raise ValueError("Stage output must be a fresh external directory")
    return output


def _write(output: Path, artifacts: Mapping[str, bytes]) -> dict[str, str]:
    staging = output.with_name(f".{output.name}.staging-{uuid.uuid4().hex}")
    try:
        staging.mkdir(parents=True, exist_ok=False)
        for name, raw in artifacts.items():
            with (staging / name).open("xb") as stream:
                stream.write(raw)
        reported = {name: _sha((staging / name).read_bytes()) for name in artifacts}
        if any((staging / name).read_bytes() != raw for name, raw in artifacts.items()):
            raise ValueError("Written stage artifact differs from its frozen bytes")
        staging.replace(output)
        return reported
    except Exception as error:
        raise RuntimeError(f"Stage retained at {staging}") from error


def _composite_admission(
    composer: ModuleType, *,
    plan_root: Path | str, public_inputs_path: Path | str, predecessor_path: Path | str,
    suffix_root: Path | str, expected_plan_sha256: str, expected_public_inputs_sha256: str,
    expected_predecessor_sha256: str, expected_suffix_epoch_sha256: str,
    expected_suffix_source_sha256: str, expected_composer_sha256: str,
    approved_v4_routes: Mapping[str, Any], approved_v5_routes: Mapping[str, Any],
) -> tuple[dict[str, Any], str]:
    result = composer.admit_composite_baseline(
        plan_root=plan_root, public_inputs_path=public_inputs_path, predecessor_path=predecessor_path,
        suffix_root=suffix_root, expected_plan_sha256=expected_plan_sha256,
        expected_public_inputs_sha256=expected_public_inputs_sha256,
        expected_predecessor_sha256=expected_predecessor_sha256,
        expected_suffix_epoch_sha256=expected_suffix_epoch_sha256,
        expected_suffix_source_sha256=expected_suffix_source_sha256,
        expected_composer_sha256=expected_composer_sha256, approved_v4_routes=dict(approved_v4_routes),
        approved_v5_routes=dict(approved_v5_routes),
    )
    if not isinstance(result, dict) or set(result) != {"composite_admission", "composite_admission_sha256", "provider_calls_made", "execution_authority"}:
        raise ValueError("Composite admission result schema differs")
    admission, admission_hash = result["composite_admission"], result["composite_admission_sha256"]
    if (not isinstance(admission, dict) or result["provider_calls_made"] != 0 or result["execution_authority"] is not False
            or admission.get("provider_calls_made") != 0 or admission.get("execution_authority") is not False
            or admission.get("promotion_authority") is not False or admission.get("confirmation_authority") is not False
            or admission.get("counts") != {"passes": 236, "logical": 5428, "native": 5427, "recovered": 1}
            or admission.get("recovered_ordinals") != [70]
            or admission.get("composer_source_sha256") != expected_composer_sha256
            or _sha(composer._canonical(admission)) != _hash(admission_hash, "Composite admission")):
        raise ValueError("Complete composite admission is required")
    return admission, admission_hash


def _source_map(runtime: Any, label: str) -> dict[str, str]:
    provenance = getattr(runtime, "provenance", None)
    sources = provenance.get("source_sha256") if isinstance(provenance, Mapping) else None
    if not isinstance(sources, dict) or not sources or any(type(path) is not str or type(value) is not str for path, value in sources.items()):
        raise ValueError(f"{label} scoring source provenance is missing")
    return dict(sources)


def _source_value(sources: Mapping[str, str], relative: str, label: str) -> str:
    matches = [value for path, value in sources.items() if path.replace("\\", "/").endswith(relative)]
    if len(matches) != 1:
        raise ValueError(f"{label} scoring dependency closure differs")
    return _hash(matches[0], f"{label} scoring dependency")


def _weight_schema(sources: Mapping[str, str]) -> tuple[Path, bytes]:
    matches = [Path(path) for path in sources if path.replace("\\", "/").endswith("registry/all_modules.json")]
    if len(matches) != 1:
        raise ValueError("Scoring dependency closure differs")
    path = matches[0].resolve().parents[1] / "schema" / "hbq_weight_profile.schema.json"
    raw = path.read_bytes()
    if not raw:
        raise ValueError("Scoring weight schema differs")
    return path, raw


def _questions(runtime: Any) -> list[str]:
    rows = getattr(runtime, "questions", None)
    if not isinstance(rows, list) or len(rows) != QUESTION_COUNT:
        raise ValueError("Scoring runtime question inventory differs")
    try:
        ids = [row["question"]["id"] for row in rows]
    except (KeyError, TypeError) as error:
        raise ValueError("Scoring runtime question inventory differs") from error
    if any(type(item) is not str or not item for item in ids) or len(set(ids)) != QUESTION_COUNT:
        raise ValueError("Scoring runtime question inventory differs")
    return ids


def _verdicts(question_ids: Sequence[str], values: Sequence[str]) -> list[dict[str, str]]:
    return [{"question_id": question, "verdict": values[index % len(values)]} for index, question in enumerate(question_ids)]


def _case_score(runtime: Any, verdicts: list[dict[str, str]], *, task_contract: Mapping[str, Any] | None = None,
                profile: Mapping[str, Any] | None = None) -> bytes:
    modules, bundle = runtime.modules, runtime.bundle
    if profile is not None:
        modules, bundle, _audit = runtime.weights.materialize_weight_profile(modules, bundle, profile)
    value = runtime.core.score_bundle(modules, bundle, verdicts, artifact_id="composite-parity", task_contract=task_contract)
    return _canonical(value)


def _scoring_parity(v1: Any, v5: Any) -> dict[str, Any]:
    """Bind scoring equivalence before and after bounded four-state probes."""
    v1.verify()
    v5.verify()
    v1_sources, v5_sources = _source_map(v1, "v1"), _source_map(v5, "v5")
    closure = ("src/hbqrs/core.py", "src/hbqrs/weights.py", "src/hbqrs/paths.py", "registry/all_modules.json", "bundles/all_bundles.json")
    closure_hashes = {item: _source_value(v1_sources, item, "v1") for item in closure}
    if closure_hashes != {item: _source_value(v5_sources, item, "v5") for item in closure}:
        raise ValueError("Scoring dependency closure differs")
    schema_path, schema_raw = _weight_schema(v1_sources)
    v5_schema_path, v5_schema_raw = _weight_schema(v5_sources)
    if schema_path != v5_schema_path or schema_raw != v5_schema_raw:
        raise ValueError("Scoring weight schema differs")
    closure_hashes["schema/hbq_weight_profile.schema.json"] = _sha(schema_raw)
    v1_questions, v5_questions = _questions(v1), _questions(v5)
    if v1_questions != v5_questions or _canonical(v1.modules) != _canonical(v5.modules) or _canonical(v1.bundle) != _canonical(v5.bundle) or _canonical(v1.compiled) != _canonical(v5.compiled):
        raise ValueError("Scoring compiled bundle, module, or question order differs")
    profile = {"profile_version": 1, "profile_id": "composite-parity", "bundle_id": v1.bundle["bundle_id"],
               "domain_weights": [{"domain_id": item["domain_id"], "weight": float(item["points"]) * (2.0 if index == 0 else 0.5)} for index, item in enumerate(v1.bundle["domains"])]}
    contract = {"contract_id": "composite-parity", "weighted_goals": [], "binding_requirements": [{
        "requirement_id": "bounded-hard-gate", "atomic_question": "Is the supplied parity case available?",
        "source": {"reference": "synthetic parity contract"}, "objective": True, "non_negotiable": True,
    }]}
    cases: dict[str, tuple[list[dict[str, str]], Mapping[str, Any] | None, Mapping[str, Any] | None]] = {
        "four_state": (_verdicts(v1_questions, CANONICAL_VERDICTS), None, None),
        "not_applicable": (_verdicts(v1_questions, ("NOT_APPLICABLE",)), None, None),
        "unknown": (_verdicts(v1_questions, ("CANNOT_ASSESS",)), None, None),
        "weighted": (_verdicts(v1_questions, ("YES",)), None, profile),
        "hard_gate_yes": (_verdicts(v1_questions, ("YES",)) + [{"question_id": "task.contract.composite-parity.bounded-hard-gate", "verdict": "YES"}], contract, None),
        "hard_gate_no": (_verdicts(v1_questions, ("YES",)) + [{"question_id": "task.contract.composite-parity.bounded-hard-gate", "verdict": "NO"}], contract, None),
        "hard_gate_unknown": (_verdicts(v1_questions, ("YES",)) + [{"question_id": "task.contract.composite-parity.bounded-hard-gate", "verdict": "CANNOT_ASSESS"}], contract, None),
    }
    hashes: dict[str, str] = {}
    for name, (verdicts, task_contract, case_profile) in cases.items():
        left = _case_score(v1, verdicts, task_contract=task_contract, profile=case_profile)
        right = _case_score(v5, verdicts, task_contract=task_contract, profile=case_profile)
        if left != right:
            raise ValueError(f"Scoring parity differs for {name}")
        hashes[name] = _sha(left)
    v1.verify()
    v5.verify()
    if schema_path.read_bytes() != schema_raw:
        raise ValueError("Scoring weight schema changed during parity")
    return {"schema_version": 1, "evidence_class": "v1_v5_source_bound_scoring_parity",
            "dependency_closure": closure_hashes, "modules_sha256": _sha(_canonical(v1.modules)),
            "bundle_sha256": _sha(_canonical(v1.bundle)), "compiled_bundle_sha256": _sha(_canonical(v1.compiled)),
            "question_order_sha256": _sha(_canonical(v1_questions)), "case_score_sha256": hashes,
            "before_after_verified": True}


def _capture(
    *, expected_analysis_sha256: str, expected_composer_sha256: str, expected_workflow_sha256: str,
    expected_engine_sha256: str, engine_label: str,
    expected_scoring_runtime_loader_sha256: str, expected_v5_runtime_loader_sha256: str,
) -> tuple[dict[Path, bytes], ModuleType, ModuleType, ModuleType, ModuleType, ModuleType]:
    paths = (
        (Path(__file__).resolve(), expected_analysis_sha256, "Composite analysis"),
        (COMPOSER_PATH, expected_composer_sha256, "Composite admission"),
        (WORKFLOW_PATH, expected_workflow_sha256, "Workflow pure helpers"),
        (OPTIMIZER_PATH if engine_label == "Optimizer" else COMPARISON_PATH, expected_engine_sha256, engine_label),
        (RUNTIME_V1_PATH, expected_scoring_runtime_loader_sha256, "v1 scoring runtime loader"),
        (RUNTIME_V5_PATH, expected_v5_runtime_loader_sha256, "v5 scoring runtime loader"),
    )
    captured: dict[Path, bytes] = {}
    loaded: dict[str, ModuleType] = {}
    for path, expected, label in paths:
        checked, raw = _read_pinned(path, expected, label)
        captured[checked] = raw
        loaded[label] = _load(checked, raw, label.replace(" ", "_"))
    return (captured, loaded["Composite admission"], loaded["Workflow pure helpers"], loaded[engine_label],
            loaded["v1 scoring runtime loader"], loaded["v5 scoring runtime loader"])


def _runtime_parity(
    v1_loader: ModuleType, v5_loader: ModuleType, *, scoring_manifest_path: Path | str,
    expected_scoring_manifest_sha256: str, v5_runtime_manifest_path: Path | str,
    expected_v5_runtime_manifest_sha256: str, v5_runtime_package_root: Path | str,
    expected_v5_runtime_package_manifest_sha256: str,
) -> tuple[dict[str, Any], dict[Path, bytes]]:
    v1_path, v1_raw = _read_pinned(scoring_manifest_path, expected_scoring_manifest_sha256, "v1 scoring manifest")
    v5_path, v5_raw = _read_pinned(v5_runtime_manifest_path, expected_v5_runtime_manifest_sha256, "v5 scoring manifest")
    package_path, package_raw = _read_pinned(Path(v5_runtime_package_root) / "candidate-manifest.json", expected_v5_runtime_package_manifest_sha256, "v5 scoring package manifest")
    v1 = v1_loader.load_runtime(v1_path, expected_manifest_sha256=expected_scoring_manifest_sha256)
    v5 = v5_loader.load_runtime(v5_path, expected_manifest_sha256=expected_v5_runtime_manifest_sha256,
                                runtime_package_root=Path(v5_runtime_package_root),
                                expected_package_manifest_sha256=expected_v5_runtime_package_manifest_sha256)
    parity = _scoring_parity(v1, v5)
    schema_path, schema_raw = _weight_schema(_source_map(v1, "v1"))
    return ({"v1_manifest": {"sha256": expected_scoring_manifest_sha256, "bytes": len(v1_raw)},
             "v5_manifest": {"sha256": expected_v5_runtime_manifest_sha256, "bytes": len(v5_raw)},
             "v5_package_manifest": {"sha256": expected_v5_runtime_package_manifest_sha256, "bytes": len(package_raw)},
             "parity": parity, "commitment_sha256": _sha(_canonical(parity))},
            {v1_path: v1_raw, v5_path: v5_raw, package_path: package_raw, schema_path: schema_raw})


def _admission_binding(admission: dict[str, Any], admission_sha256: str, projected: Mapping[str, list[dict[str, Any]],],
                       projected_binding: Mapping[str, Any]) -> dict[str, Any]:
    return {"canonical_composite_admission_sha256": admission_sha256,
            "endpoint_grok_rows_sha256": _sha(_canonical(admission["endpoint_grok_rows"])),
            "projected_rows_sha256": {name: _sha(_canonical(rows)) for name, rows in projected.items()},
            "pure_projection": dict(projected_binding)}


def _outer_freeze(
    stage: str, admission: dict[str, Any], admission_binding: dict[str, Any], *, partitions: Mapping[str, set[str]],
    target_raw: bytes, target_sha256: str, inner_raw: bytes, inner: Mapping[str, Any],
    source_hashes: Mapping[str, str], scoring: Mapping[str, Any],
) -> dict[str, Any]:
    return {"schema_version": 1, "evidence_class": f"composite_{stage.lower()}_outer_freeze_v5", "stage": stage,
            "provider_calls": 0, "execution_authority": False, "promotion_authority": False,
            "confirmation_authority": False, "sol_validation": False, "sources": dict(source_hashes),
            "scoring": dict(scoring), "public_partitions": {name: sorted(ids) for name, ids in partitions.items()},
            "target": {"partition": stage, "sha256": target_sha256, "bytes": len(target_raw)},
            "admission": admission, "admission_binding": admission_binding,
            "measurement_provenance": {"predecessor": admission.get("predecessor"), "suffix": admission.get("suffix")},
            "inner": {"sha256": _sha(inner_raw), "evidence_class": inner.get("evidence_class")}}


def _train_freeze(
    path: Path | str, expected: str, fit_raw: bytes, admission_binding: Mapping[str, Any],
    scoring_commitment_sha256: str,
) -> tuple[Path, bytes, dict[str, Any]]:
    checked, raw = _read_pinned(path, expected, "Composite TRAIN freeze")
    value = _strict_json(raw, "Composite TRAIN freeze")
    if (not isinstance(value, dict) or value.get("stage") != "TRAIN"
            or value.get("evidence_class") != "composite_train_outer_freeze_v5"
            or value.get("inner", {}).get("sha256") != _sha(fit_raw)
            or value.get("admission_binding") != admission_binding
            or value.get("scoring", {}).get("commitment_sha256") != scoring_commitment_sha256):
        raise ValueError("Composite TRAIN freeze binding differs")
    return checked, raw, value


def fit_composite_train(
    plan_root: Path | str, public_inputs_path: Path | str, predecessor_path: Path | str,
    suffix_root: Path | str, scoring_manifest_path: Path | str, v5_runtime_manifest_path: Path | str,
    v5_runtime_package_root: Path | str, train_targets_path: Path | str, output_root: Path | str, *,
    expected_plan_sha256: str, expected_public_inputs_sha256: str, expected_predecessor_sha256: str,
    expected_suffix_epoch_sha256: str, expected_suffix_source_sha256: str, expected_analysis_sha256: str,
    expected_composer_sha256: str, expected_workflow_sha256: str, expected_optimizer_sha256: str,
    expected_scoring_runtime_loader_sha256: str,
    expected_v5_runtime_loader_sha256: str, expected_scoring_manifest_sha256: str,
    expected_v5_runtime_manifest_sha256: str, expected_v5_runtime_package_manifest_sha256: str,
    approved_v4_routes: Mapping[str, Any], approved_v5_routes: Mapping[str, Any],
) -> dict[str, Any]:
    """Fit the fixed 128-trial TRAIN optimizer after full composite admission."""
    output = _output_preflight(output_root, plan_root, public_inputs_path, predecessor_path, suffix_root,
                                scoring_manifest_path, v5_runtime_manifest_path, v5_runtime_package_root,
                                train_targets_path)
    captured, composer, pure, optimizer, v1_loader, v5_loader = _capture(
        expected_analysis_sha256=expected_analysis_sha256, expected_composer_sha256=expected_composer_sha256,
        expected_workflow_sha256=expected_workflow_sha256, expected_engine_sha256=expected_optimizer_sha256,
        engine_label="Optimizer",
        expected_scoring_runtime_loader_sha256=expected_scoring_runtime_loader_sha256,
        expected_v5_runtime_loader_sha256=expected_v5_runtime_loader_sha256)
    admission, admission_sha256 = _composite_admission(
        composer, plan_root=plan_root, public_inputs_path=public_inputs_path,
        predecessor_path=predecessor_path, suffix_root=suffix_root, expected_plan_sha256=expected_plan_sha256,
        expected_public_inputs_sha256=expected_public_inputs_sha256, expected_predecessor_sha256=expected_predecessor_sha256,
        expected_suffix_epoch_sha256=expected_suffix_epoch_sha256, expected_suffix_source_sha256=expected_suffix_source_sha256,
        expected_composer_sha256=expected_composer_sha256, approved_v4_routes=approved_v4_routes,
        approved_v5_routes=approved_v5_routes)
    inputs_path, inputs_raw, partitions = _partitions(public_inputs_path, expected_public_inputs_sha256)
    captured[inputs_path] = inputs_raw
    projected, projected_binding = pure._project_rows(admission, partitions)
    admission_binding = _admission_binding(admission, admission_sha256, projected, projected_binding)
    scoring, scoring_captured = _runtime_parity(
        v1_loader, v5_loader, scoring_manifest_path=scoring_manifest_path,
        expected_scoring_manifest_sha256=expected_scoring_manifest_sha256,
        v5_runtime_manifest_path=v5_runtime_manifest_path,
        expected_v5_runtime_manifest_sha256=expected_v5_runtime_manifest_sha256,
        v5_runtime_package_root=v5_runtime_package_root,
        expected_v5_runtime_package_manifest_sha256=expected_v5_runtime_package_manifest_sha256)
    captured.update(scoring_captured)
    _unchanged(captured)
    targets_path, target_raw, targets = pure._targets(train_targets_path, pure.TRAIN_TARGETS_SHA256, "TRAIN", partitions["TRAIN"])
    captured[targets_path] = target_raw
    _unchanged(captured)
    fit = optimizer.fit_train(projected["TRAIN"], targets, expected_optimizer_sha256=expected_optimizer_sha256,
                              baseline_manifest_path=scoring_manifest_path,
                              baseline_manifest_sha256=expected_scoring_manifest_sha256)
    if not isinstance(fit, dict) or fit.get("evidence_class") != "baseline_source_verified_fit_unadmitted":
        raise ValueError("Inner TRAIN fit must retain its source-verified unadmitted class")
    pure._inner_commitments(fit, projected["TRAIN"], targets, pure.TRAIN_TARGETS_SHA256)
    fit_raw = _canonical(fit)
    _unchanged(captured)
    sources = {"analysis_sha256": expected_analysis_sha256, "composer_sha256": expected_composer_sha256,
               "workflow_sha256": expected_workflow_sha256, "optimizer_sha256": expected_optimizer_sha256,
               "suffix_sha256": expected_suffix_source_sha256,
               "v1_scoring_runtime_loader_sha256": expected_scoring_runtime_loader_sha256,
               "v5_scoring_runtime_loader_sha256": expected_v5_runtime_loader_sha256}
    freeze = _outer_freeze("TRAIN", admission, admission_binding, partitions=partitions, target_raw=target_raw,
                           target_sha256=pure.TRAIN_TARGETS_SHA256, inner_raw=fit_raw, inner=fit,
                           source_hashes=sources, scoring=scoring)
    freeze_raw = _canonical(freeze)
    return {"artifacts": _write(output, {"fit-unadmitted.json": fit_raw, "train-composite-freeze.json": freeze_raw}),
            "freeze": freeze}


def _compute_composite_dev(
    plan_root: Path | str, public_inputs_path: Path | str, predecessor_path: Path | str,
    suffix_root: Path | str, scoring_manifest_path: Path | str, v5_runtime_manifest_path: Path | str,
    v5_runtime_package_root: Path | str, dev_targets_path: Path | str, fit_path: Path | str,
    train_freeze_path: Path | str, *, expected_plan_sha256: str,
    expected_public_inputs_sha256: str, expected_predecessor_sha256: str,
    expected_suffix_epoch_sha256: str, expected_suffix_source_sha256: str,
    expected_analysis_sha256: str, expected_composer_sha256: str, expected_workflow_sha256: str,
    expected_comparison_sha256: str,
    expected_scoring_runtime_loader_sha256: str, expected_v5_runtime_loader_sha256: str,
    expected_scoring_manifest_sha256: str, expected_v5_runtime_manifest_sha256: str,
    expected_v5_runtime_package_manifest_sha256: str, expected_fit_sha256: str,
    expected_train_freeze_sha256: str, approved_v4_routes: Mapping[str, Any],
    approved_v5_routes: Mapping[str, Any],
) -> dict[str, Any]:
    """Compute the source-bound DEV result without writing a stage artifact."""
    captured, composer, pure, comparison, v1_loader, v5_loader = _capture(
        expected_analysis_sha256=expected_analysis_sha256, expected_composer_sha256=expected_composer_sha256,
        expected_workflow_sha256=expected_workflow_sha256, expected_engine_sha256=expected_comparison_sha256,
        engine_label="Comparison",
        expected_scoring_runtime_loader_sha256=expected_scoring_runtime_loader_sha256,
        expected_v5_runtime_loader_sha256=expected_v5_runtime_loader_sha256)
    admission, admission_sha256 = _composite_admission(
        composer, plan_root=plan_root, public_inputs_path=public_inputs_path,
        predecessor_path=predecessor_path, suffix_root=suffix_root, expected_plan_sha256=expected_plan_sha256,
        expected_public_inputs_sha256=expected_public_inputs_sha256, expected_predecessor_sha256=expected_predecessor_sha256,
        expected_suffix_epoch_sha256=expected_suffix_epoch_sha256, expected_suffix_source_sha256=expected_suffix_source_sha256,
        expected_composer_sha256=expected_composer_sha256, approved_v4_routes=approved_v4_routes,
        approved_v5_routes=approved_v5_routes)
    inputs_path, inputs_raw, partitions = _partitions(public_inputs_path, expected_public_inputs_sha256)
    captured[inputs_path] = inputs_raw
    projected, projected_binding = pure._project_rows(admission, partitions)
    admission_binding = _admission_binding(admission, admission_sha256, projected, projected_binding)
    scoring, scoring_captured = _runtime_parity(
        v1_loader, v5_loader, scoring_manifest_path=scoring_manifest_path,
        expected_scoring_manifest_sha256=expected_scoring_manifest_sha256,
        v5_runtime_manifest_path=v5_runtime_manifest_path,
        expected_v5_runtime_manifest_sha256=expected_v5_runtime_manifest_sha256,
        v5_runtime_package_root=v5_runtime_package_root,
        expected_v5_runtime_package_manifest_sha256=expected_v5_runtime_package_manifest_sha256)
    captured.update(scoring_captured)
    fit_checked, fit_raw = _read_pinned(fit_path, expected_fit_sha256, "Frozen composite TRAIN fit")
    captured[fit_checked] = fit_raw
    train_checked, train_raw, _train = _train_freeze(
        train_freeze_path, expected_train_freeze_sha256, fit_raw, admission_binding, scoring["commitment_sha256"])
    captured[train_checked] = train_raw
    _unchanged(captured)
    dev_path, dev_raw, targets = pure._targets(dev_targets_path, pure.DEV_TARGETS_SHA256, "DEV", partitions["DEV"])
    captured[dev_path] = dev_raw
    _unchanged(captured)
    result = comparison.evaluate_dev(projected["DEV"], targets, fit_raw, expected_fit_sha256=expected_fit_sha256,
                                     expected_comparison_sha256=expected_comparison_sha256,
                                     baseline_manifest_path=scoring_manifest_path,
                                     baseline_manifest_sha256=expected_scoring_manifest_sha256)
    if not isinstance(result, dict) or result.get("evidence_class") != "baseline_source_verified_dev_comparison_unadmitted":
        raise ValueError("Inner DEV comparison must retain its source-verified unadmitted class")
    pure._inner_commitments(result, projected["DEV"], targets, pure.DEV_TARGETS_SHA256)
    result_raw = _canonical(result)
    _unchanged(captured)
    sources = {"analysis_sha256": expected_analysis_sha256, "composer_sha256": expected_composer_sha256,
               "workflow_sha256": expected_workflow_sha256, "comparison_sha256": expected_comparison_sha256,
               "suffix_sha256": expected_suffix_source_sha256,
               "v1_scoring_runtime_loader_sha256": expected_scoring_runtime_loader_sha256,
               "v5_scoring_runtime_loader_sha256": expected_v5_runtime_loader_sha256}
    freeze = _outer_freeze("DEV", admission, admission_binding, partitions=partitions, target_raw=dev_raw,
                           target_sha256=pure.DEV_TARGETS_SHA256, inner_raw=result_raw, inner=result,
                           source_hashes=sources, scoring=scoring)
    freeze["train"] = {"fit_sha256": expected_fit_sha256, "freeze_sha256": expected_train_freeze_sha256}
    return {"comparison": result, "comparison_raw": result_raw, "freeze": freeze, "captured": captured}


def compare_composite_dev(
    plan_root: Path | str, public_inputs_path: Path | str, predecessor_path: Path | str,
    suffix_root: Path | str, scoring_manifest_path: Path | str, v5_runtime_manifest_path: Path | str,
    v5_runtime_package_root: Path | str, dev_targets_path: Path | str, fit_path: Path | str,
    train_freeze_path: Path | str, output_root: Path | str, *, expected_plan_sha256: str,
    expected_public_inputs_sha256: str, expected_predecessor_sha256: str,
    expected_suffix_epoch_sha256: str, expected_suffix_source_sha256: str,
    expected_analysis_sha256: str, expected_composer_sha256: str, expected_workflow_sha256: str,
    expected_comparison_sha256: str, expected_scoring_runtime_loader_sha256: str,
    expected_v5_runtime_loader_sha256: str, expected_scoring_manifest_sha256: str,
    expected_v5_runtime_manifest_sha256: str, expected_v5_runtime_package_manifest_sha256: str,
    expected_fit_sha256: str, expected_train_freeze_sha256: str, approved_v4_routes: Mapping[str, Any],
    approved_v5_routes: Mapping[str, Any],
) -> dict[str, Any]:
    """Produce the one DEV freeze after exact composite admission and TRAIN binding."""
    output = _output_preflight(output_root, plan_root, public_inputs_path, predecessor_path, suffix_root,
                                scoring_manifest_path, v5_runtime_manifest_path, v5_runtime_package_root,
                                dev_targets_path, fit_path, train_freeze_path)
    computed = _compute_composite_dev(
        plan_root, public_inputs_path, predecessor_path, suffix_root, scoring_manifest_path,
        v5_runtime_manifest_path, v5_runtime_package_root, dev_targets_path, fit_path, train_freeze_path,
        expected_plan_sha256=expected_plan_sha256, expected_public_inputs_sha256=expected_public_inputs_sha256,
        expected_predecessor_sha256=expected_predecessor_sha256, expected_suffix_epoch_sha256=expected_suffix_epoch_sha256,
        expected_suffix_source_sha256=expected_suffix_source_sha256, expected_analysis_sha256=expected_analysis_sha256,
        expected_composer_sha256=expected_composer_sha256, expected_workflow_sha256=expected_workflow_sha256,
        expected_comparison_sha256=expected_comparison_sha256,
        expected_scoring_runtime_loader_sha256=expected_scoring_runtime_loader_sha256,
        expected_v5_runtime_loader_sha256=expected_v5_runtime_loader_sha256,
        expected_scoring_manifest_sha256=expected_scoring_manifest_sha256,
        expected_v5_runtime_manifest_sha256=expected_v5_runtime_manifest_sha256,
        expected_v5_runtime_package_manifest_sha256=expected_v5_runtime_package_manifest_sha256,
        expected_fit_sha256=expected_fit_sha256, expected_train_freeze_sha256=expected_train_freeze_sha256,
        approved_v4_routes=approved_v4_routes, approved_v5_routes=approved_v5_routes)
    freeze = computed["freeze"]
    freeze["selection_frozen_at"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    freeze_raw = _canonical(freeze)
    return {"artifacts": _write(output, {"dev-comparison-unadmitted.json": computed["comparison_raw"],
                                           "dev-composite-freeze.json": freeze_raw}), "freeze": freeze}


def replay_composite_dev(
    plan_root: Path | str, public_inputs_path: Path | str, predecessor_path: Path | str,
    suffix_root: Path | str, scoring_manifest_path: Path | str, v5_runtime_manifest_path: Path | str,
    v5_runtime_package_root: Path | str, dev_targets_path: Path | str, fit_path: Path | str,
    train_freeze_path: Path | str, dev_comparison_path: Path | str, dev_freeze_path: Path | str, *,
    expected_plan_sha256: str, expected_public_inputs_sha256: str, expected_predecessor_sha256: str,
    expected_suffix_epoch_sha256: str, expected_suffix_source_sha256: str,
    expected_analysis_sha256: str, expected_composer_sha256: str, expected_workflow_sha256: str,
    expected_comparison_sha256: str, expected_scoring_runtime_loader_sha256: str,
    expected_v5_runtime_loader_sha256: str, expected_scoring_manifest_sha256: str,
    expected_v5_runtime_manifest_sha256: str, expected_v5_runtime_package_manifest_sha256: str,
    expected_fit_sha256: str, expected_train_freeze_sha256: str,
    expected_dev_comparison_sha256: str, expected_dev_freeze_sha256: str,
    approved_v4_routes: Mapping[str, Any], approved_v5_routes: Mapping[str, Any],
) -> dict[str, Any]:
    """Reconstruct externally supplied DEV artifacts byte-for-byte without writing or selecting."""
    comparison_path, comparison_raw = _read_pinned(dev_comparison_path, expected_dev_comparison_sha256, "Stored DEV comparison")
    freeze_path, freeze_raw = _read_pinned(dev_freeze_path, expected_dev_freeze_sha256, "Stored DEV freeze")
    stored_freeze = _strict_json(freeze_raw, "Stored DEV freeze")
    timestamp = stored_freeze.get("selection_frozen_at") if isinstance(stored_freeze, dict) else None
    if type(timestamp) is not str or not timestamp.endswith("Z"):
        raise ValueError("Stored DEV selection timestamp differs")
    try:
        parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("Stored DEV selection timestamp differs") from error
    if parsed.tzinfo != timezone.utc or parsed.isoformat().replace("+00:00", "Z") != timestamp:
        raise ValueError("Stored DEV selection timestamp differs")
    computed = _compute_composite_dev(
        plan_root, public_inputs_path, predecessor_path, suffix_root, scoring_manifest_path,
        v5_runtime_manifest_path, v5_runtime_package_root, dev_targets_path, fit_path, train_freeze_path,
        expected_plan_sha256=expected_plan_sha256, expected_public_inputs_sha256=expected_public_inputs_sha256,
        expected_predecessor_sha256=expected_predecessor_sha256, expected_suffix_epoch_sha256=expected_suffix_epoch_sha256,
        expected_suffix_source_sha256=expected_suffix_source_sha256, expected_analysis_sha256=expected_analysis_sha256,
        expected_composer_sha256=expected_composer_sha256, expected_workflow_sha256=expected_workflow_sha256,
        expected_comparison_sha256=expected_comparison_sha256,
        expected_scoring_runtime_loader_sha256=expected_scoring_runtime_loader_sha256,
        expected_v5_runtime_loader_sha256=expected_v5_runtime_loader_sha256,
        expected_scoring_manifest_sha256=expected_scoring_manifest_sha256,
        expected_v5_runtime_manifest_sha256=expected_v5_runtime_manifest_sha256,
        expected_v5_runtime_package_manifest_sha256=expected_v5_runtime_package_manifest_sha256,
        expected_fit_sha256=expected_fit_sha256, expected_train_freeze_sha256=expected_train_freeze_sha256,
        approved_v4_routes=approved_v4_routes, approved_v5_routes=approved_v5_routes)
    reconstructed_freeze = computed["freeze"]
    reconstructed_freeze["selection_frozen_at"] = timestamp
    reconstructed_freeze_raw = _canonical(reconstructed_freeze)
    if computed["comparison_raw"] != comparison_raw or reconstructed_freeze_raw != freeze_raw:
        raise ValueError("Stored DEV composite replay differs")
    computed["captured"][comparison_path] = comparison_raw
    computed["captured"][freeze_path] = freeze_raw
    _unchanged(computed["captured"])
    return {"comparison_raw": comparison_raw, "freeze_raw": freeze_raw, "freeze": reconstructed_freeze}
