"""Provider-free Sol DEV comparison after the frozen original Grok selection."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import uuid
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType
from typing import Any

ROOT = Path(__file__).resolve().parent
REPOSITORY = ROOT.parents[1]
BASELINE_WORKFLOW_PATH = ROOT / "baseline_analysis_workflow.py"
SOL_ADMISSION_PATH = ROOT / "sol_pass_admission.py"
DEV_COUNT = 60
ADMITTED_COUNT = 236
REQUEST_COUNT = 5428


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canonical(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                       allow_nan=False) + "\n").encode("utf-8")


def _hash(value: Any, label: str) -> str:
    if type(value) is not str or len(value) != 64 or any(item not in "0123456789abcdef" for item in value):
        raise ValueError(f"{label} must be a lowercase SHA-256")
    return value


def _json(raw: bytes, label: str) -> Any:
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


def _read_pinned(path: Path | str, expected: str, label: str) -> tuple[Path, bytes]:
    checked = Path(path).resolve()
    raw = checked.read_bytes()
    if _sha(raw) != _hash(expected, f"{label} expected hash"):
        raise ValueError(f"{label} hash drift")
    return checked, raw


def _load(path: Path, raw: bytes, label: str) -> ModuleType:
    name = f"_dryad_original_sequence_{label}_{uuid.uuid4().hex}"
    spec = importlib.util.spec_from_loader(name, loader=None)
    if spec is None:
        raise ValueError(f"Cannot load {label}")
    module = importlib.util.module_from_spec(spec)
    module.__file__ = str(path)
    exec(compile(raw, str(path), "exec"), module.__dict__)  # noqa: S102 - execute only hash-pinned local sources.
    return module


def _unchanged(captured: Mapping[Path, bytes]) -> None:
    if any(path.read_bytes() != raw for path, raw in captured.items()):
        raise ValueError("Pinned original-sequence input changed during analysis")


def _dev_freeze(raw: bytes, sol: ModuleType) -> tuple[dict[str, Any], datetime]:
    value = _json(raw, "Grok DEV freeze")
    if not isinstance(value, dict) or value.get("schema_version") != 1 or value.get("stage") != "DEV" or value.get("evidence_class") != "admitted_dev_outer_freeze":
        raise ValueError("Grok DEV freeze differs")
    frozen_at = sol._time(value.get("selection_frozen_at"), "Grok selection freeze")
    if frozen_at > datetime.now(timezone.utc):
        raise ValueError("Grok selection freeze is in the future")
    workflow = value.get("workflow")
    runtime = value.get("runtime_manifest")
    sources = value.get("sources")
    target = value.get("target")
    inner = value.get("inner")
    train_freeze = value.get("train_freeze")
    admission = value.get("admission")
    if (workflow is None or runtime is None or not isinstance(sources, Mapping) or not isinstance(target, Mapping)
            or not isinstance(inner, Mapping) or not isinstance(train_freeze, Mapping) or not isinstance(admission, Mapping)
            or set(workflow) != {"sha256"} or set(runtime) != {"sha256"}
            or target != {"partition": "DEV", "sha256": value.get("target", {}).get("sha256"), "bytes": value.get("target", {}).get("bytes")}
            or inner.get("evidence_class") != "baseline_source_verified_dev_comparison_unadmitted"):
        raise ValueError("Grok DEV freeze lineage differs")
    for item, label in ((workflow["sha256"], "Grok workflow"), (runtime["sha256"], "Grok runtime"),
                        (sources.get("admission_sha256"), "Grok admission"),
                        (sources.get("comparison_sha256"), "Grok comparison"),
                        (inner.get("sha256"), "Grok DEV comparison"),
                        (train_freeze.get("sha256"), "Grok TRAIN freeze"),
                        (train_freeze.get("fit_sha256"), "Grok frozen fit"),
                        (admission.get("plan_sha256"), "Grok plan"),
                        (admission.get("initialization_sha256"), "Grok initialization"),
                        (admission.get("admission_sha256"), "Grok admission record")):
        _hash(item, label)
    original = admission.get("original_initialization")
    provenance = admission.get("immutable_provenance")
    if (not isinstance(original, Mapping) or not isinstance(provenance, Mapping)
            or not isinstance(provenance.get("ledger_head"), Mapping)):
        raise ValueError("Grok DEV freeze native lineage differs")  # noqa: TRY004 - persisted-evidence validation uses ValueError.
    for item, label in ((original.get("route_sha256"), "Grok original route"),
                        (original.get("execution_source_sha256"), "Grok execution source"),
                        (provenance["ledger_head"].get("settlement_sha256"), "Grok final settlement")):
        _hash(item, label)
    reviewer = admission.get("reviewer_task")
    if type(reviewer) is not str or not reviewer:
        raise ValueError("Grok reviewer task differs")
    return value, frozen_at


def _recovery(baseline: ModuleType, freeze: Mapping[str, Any], grok_execution_root: Path | str) -> dict[str, Any] | None:
    provenance = freeze["admission"].get("recovery_provenance")
    if provenance is None:
        return None
    if not isinstance(provenance, Mapping):
        raise ValueError("Grok recovery provenance differs")  # noqa: TRY004 - persisted-evidence validation uses ValueError.
    manifest_sha = _hash(provenance.get("manifest_sha256"), "Grok recovery manifest")
    finalizer_sha = _hash(provenance.get("finalizer_sha256"), "Grok recovery finalizer")
    marker = Path(grok_execution_root).resolve().parent / baseline.RECOVERY_MANIFEST
    return baseline._recovery_context(
        grok_execution_root,
        recovery_manifest_path=marker,
        expected_recovery_manifest_sha256=manifest_sha,
        expected_recovery_execution_sha256=finalizer_sha,
    )


def _grok_admission(baseline: ModuleType, admission_module: ModuleType, finalizer: ModuleType | None,
                    recovery: Mapping[str, Any] | None, public_inputs_path: Path | str,
                    plan_root: Path | str, execution_root: Path | str,
                    runtime_manifest_path: Path | str, freeze: Mapping[str, Any]) -> dict[str, Any]:
    admission = freeze["admission"]
    original = admission["original_initialization"]
    settlement = admission["immutable_provenance"]["ledger_head"]["settlement_sha256"]
    return baseline._admit(
        admission_module, finalizer, recovery, public_inputs_path, plan_root, execution_root, runtime_manifest_path,
        expected_plan_sha256=admission["plan_sha256"],
        expected_final_settlement_sha256=settlement,
        expected_execution_source_sha256=original["execution_source_sha256"],
        expected_route_sha256=original["route_sha256"],
        expected_runtime_manifest_sha256=freeze["runtime_manifest"]["sha256"],
        expected_admission_sha256=freeze["sources"]["admission_sha256"],
        expected_reviewer_task=admission["reviewer_task"],
        expected_initialization_sha256=admission["initialization_sha256"],
    )


def _chronology(sol: ModuleType, plan_root: Path | str, execution_root: Path | str,
                selection_frozen_at: datetime) -> dict[str, Any]:
    plan_raw = (Path(plan_root).resolve() / "plan.json").read_bytes()
    if _sha(plan_raw) != sol.PLAN_SHA256:
        raise ValueError("Frozen Sol campaign plan differs")
    plan = sol._json(plan_raw, "Sol plan")
    passes, requests = plan.get("passes"), plan.get("requests")
    if not isinstance(passes, list) or not isinstance(requests, list) or len(passes) != ADMITTED_COUNT or len(requests) != REQUEST_COUNT:
        raise ValueError("Sol chronology plan geometry differs")
    by_id: dict[str, Mapping[str, Any]] = {}
    for record in passes:
        if not isinstance(record, Mapping) or type(record.get("pass_id")) is not str or type(record.get("run_path")) is not str or record["pass_id"] in by_id:
            raise ValueError("Sol chronology pass map differs")
        by_id[record["pass_id"]] = record
    if len(by_id) != ADMITTED_COUNT:
        raise ValueError("Sol chronology pass cardinality differs")
    ordered: list[dict[str, Any]] = []
    times: list[datetime] = []
    for ordinal, request in enumerate(requests, start=1):
        if (not isinstance(request, Mapping) or request.get("ordinal") != ordinal
                or request.get("pass_id") not in by_id or type(request.get("batch_number")) is not int):
            raise ValueError("Sol chronology request order differs")
        record = by_id[request["pass_id"]]
        checkpoint = Path(execution_root).resolve() / record["run_path"] / "responses" / f"batch-{request['batch_number']:04d}.json"
        raw = checkpoint.read_bytes()
        value = sol._json(raw, "Sol chronology checkpoint")
        provider = value.get("provider") if isinstance(value, Mapping) else None
        metadata = provider.get("dryad_sol") if isinstance(provider, Mapping) else None
        if not isinstance(metadata, Mapping) or metadata.get("ordinal") != ordinal:
            raise ValueError("Sol chronology checkpoint ordinal differs")
        authorized = sol._time(metadata.get("authorized_at"), "Sol authorization")
        if authorized < selection_frozen_at:
            raise ValueError("Sol authorization precedes frozen Grok selection")
        times.append(authorized)
        ordered.append({"ordinal": ordinal, "checkpoint_sha256": _sha(raw),
                        "authorized_at": metadata["authorized_at"]})
    if len(times) != REQUEST_COUNT:
        raise ValueError("Sol chronology is incomplete")
    return {
        "checkpoint_count": REQUEST_COUNT,
        "first_authorized_at": min(times).isoformat().replace("+00:00", "Z"),
        "last_authorized_at": max(times).isoformat().replace("+00:00", "Z"),
        "ordered_checkpoint_commitment": _sha(_canonical(ordered)),
    }


def _capture_sol_sources(sol: ModuleType, expected: Mapping[str, str]) -> dict[Path, bytes]:
    required = {
        "driver": ROOT / "sol_measurement_execution.py",
        "adapter": ROOT / "sol_existing_runtime.py",
        "runner": REPOSITORY / "src/hbqrs/runner.py",
        "v3": ROOT.parent / "hbq-human-alignment-optimizer-v4-native-subscription-exec-v3/executor.py",
        "core": REPOSITORY / "src/hbqrs/core.py",
    }
    if set(expected) != set(required):
        raise ValueError("Sol source bindings differ")
    captured = {
        path: _read_pinned(path, expected[key], f"Sol {key} source")[1]
        for key, path in required.items()
    }
    protocol_path, protocol_raw = _read_pinned(sol.PROTOCOL, sol.PROTOCOL_SHA256, "Sol protocol")
    protocol = _json(protocol_raw, "Sol protocol")
    runtime_bindings = protocol.get("runtime_bindings") if isinstance(protocol, Mapping) else None
    if not isinstance(runtime_bindings, Mapping):
        raise ValueError("Sol protocol runtime bindings differ")  # noqa: TRY004 - persisted-evidence validation uses ValueError.
    captured[protocol_path] = protocol_raw
    for relative, source_sha in runtime_bindings.items():
        if type(relative) is not str:
            raise ValueError("Sol protocol runtime path differs")
        path, raw = _read_pinned(REPOSITORY / relative, source_sha, "Sol inherited runtime source")
        captured[path] = raw
    return captured


def _sol_rows(baseline: ModuleType, campaign: Mapping[str, Any], partitions: Mapping[str, set[str]]) -> tuple[dict[str, list[dict[str, Any]]], dict[str, Any]]:
    if (campaign.get("evidence_class") != "complete_sol_local_lifecycle_campaign_admission"
            or campaign.get("execution_authority") is not False or campaign.get("provider_calls") != 0
            or campaign.get("admitted_passes") != ADMITTED_COUNT or campaign.get("logical_requests") != REQUEST_COUNT):
        raise ValueError("Complete Sol admission is required")
    rows = campaign.get("endpoint_sol_rows")
    if not isinstance(rows, list) or len(rows) != ADMITTED_COUNT:
        raise ValueError("Sol admission does not contain all 236 rows")
    projected, shared_binding = baseline._project_rows({"endpoint_grok_rows": rows}, partitions)
    if len(projected["DEV"]) != DEV_COUNT:
        raise ValueError("Sol DEV projection differs")
    return projected, {
        "endpoint_sol_rows_sha256": _sha(_canonical(rows)),
        "projected_rows_sha256": shared_binding["projected_rows_sha256"],
    }


def compare_original_sequence_sol(
    public_inputs_path: Path | str, shared_plan_root: Path | str, grok_execution_root: Path | str,
    sol_execution_root: Path | str, runtime_manifest_path: Path | str, target_freeze_path: Path | str,
    train_targets_path: Path | str, dev_targets_path: Path | str, frozen_fit_path: Path | str,
    train_freeze_path: Path | str, grok_dev_comparison_path: Path | str,
    grok_dev_freeze_path: Path | str, output_root: Path | str, *,
    expected_grok_dev_freeze_sha256: str, expected_wrapper_sha256: str,
    expected_sol_admission_sha256: str, expected_sol_source_bindings: Mapping[str, str],
    expected_sol_reviews: set[str],
) -> dict[str, Any]:
    """Rescore full Sol DEV leaves after, and only after, the frozen Grok selection."""
    own_path, own_raw = _read_pinned(Path(__file__), expected_wrapper_sha256, "Sol analysis workflow")
    freeze_path, freeze_raw = _read_pinned(grok_dev_freeze_path, expected_grok_dev_freeze_sha256, "Grok DEV freeze")
    sol_path, sol_raw = _read_pinned(SOL_ADMISSION_PATH, expected_sol_admission_sha256, "Sol admission")
    sol = _load(sol_path, sol_raw, "sol_admission")
    freeze, selection_frozen_at = _dev_freeze(freeze_raw, sol)
    baseline_path, baseline_raw = _read_pinned(BASELINE_WORKFLOW_PATH, freeze["workflow"]["sha256"], "Grok workflow")
    baseline = _load(baseline_path, baseline_raw, "baseline_workflow")
    recovery = _recovery(baseline, freeze, grok_execution_root)
    output = baseline._output_preflight(
        output_root, public_inputs_path, shared_plan_root, grok_execution_root, sol_execution_root,
        runtime_manifest_path, target_freeze_path, train_targets_path, dev_targets_path, frozen_fit_path,
        train_freeze_path, grok_dev_comparison_path, grok_dev_freeze_path,
        *((recovery["manifest_path"],) if recovery is not None else ()),
    )
    captured, admission_module, comparison, finalizer = baseline._capture(
        freeze["workflow"]["sha256"], freeze["sources"]["admission_sha256"],
        freeze["sources"]["comparison_sha256"], baseline.COMPARISON_PATH, "Comparison",
        runtime_manifest_path, freeze["runtime_manifest"]["sha256"], recovery,
    )
    captured.update({own_path: own_raw, sol_path: sol_raw, freeze_path: freeze_raw})
    target_freeze_checked, target_freeze_raw, target_freeze = baseline._target_freeze(target_freeze_path)
    captured[target_freeze_checked] = target_freeze_raw
    admission = _grok_admission(
        baseline, admission_module, finalizer, recovery, public_inputs_path, shared_plan_root,
        grok_execution_root, runtime_manifest_path, freeze,
    )
    inputs_path, inputs_raw, partitions = baseline._partition_ids(public_inputs_path)
    captured[inputs_path] = inputs_raw
    projected_grok, grok_binding = baseline._project_rows(admission, partitions)
    fit_path, fit_raw = _read_pinned(frozen_fit_path, freeze["train_freeze"]["fit_sha256"], "Frozen Grok TRAIN fit")
    captured[fit_path] = fit_raw
    train_targets_checked, train_targets_raw, train_targets = baseline._targets(
        train_targets_path, baseline.TRAIN_TARGETS_SHA256, "TRAIN", partitions["TRAIN"],
    )
    captured[train_targets_checked] = train_targets_raw
    frozen_fit = baseline._json(fit_raw, "Frozen Grok TRAIN fit")
    if (not isinstance(frozen_fit, dict)
            or frozen_fit.get("evidence_class") != "baseline_source_verified_fit_unadmitted"):
        raise ValueError("Frozen Grok TRAIN fit is not source-verified and unadmitted")
    baseline._inner_commitments(frozen_fit, projected_grok["TRAIN"], train_targets, baseline.TRAIN_TARGETS_SHA256)
    train_path, train_raw, _ = baseline._train_freeze(
        train_freeze_path, freeze["train_freeze"]["sha256"], fit_raw, grok_binding,
        freeze["runtime_manifest"]["sha256"], freeze["sources"]["admission_sha256"],
        freeze["workflow"]["sha256"],
    )
    captured[train_path] = train_raw
    dev_path, dev_raw, dev_targets = baseline._targets(
        dev_targets_path, baseline.DEV_TARGETS_SHA256, "DEV", partitions["DEV"],
    )
    captured[dev_path] = dev_raw
    grok_comparison_path, grok_comparison_raw = _read_pinned(
        grok_dev_comparison_path, freeze["inner"]["sha256"], "Frozen Grok DEV comparison",
    )
    captured[grok_comparison_path] = grok_comparison_raw
    baseline._unchanged(captured)
    recomputed_grok = comparison.evaluate_dev(
        projected_grok["DEV"], dev_targets, fit_raw,
        expected_fit_sha256=freeze["train_freeze"]["fit_sha256"],
        expected_comparison_sha256=freeze["sources"]["comparison_sha256"],
        baseline_manifest_path=runtime_manifest_path,
        baseline_manifest_sha256=freeze["runtime_manifest"]["sha256"],
    )
    if (not isinstance(recomputed_grok, dict)
            or recomputed_grok.get("evidence_class") != "baseline_source_verified_dev_comparison_unadmitted"):
        raise ValueError("Recomputed Grok DEV comparison is not source-verified and unadmitted")
    baseline._inner_commitments(recomputed_grok, projected_grok["DEV"], dev_targets, baseline.DEV_TARGETS_SHA256)
    recomputed_grok_raw = baseline._canonical(recomputed_grok)
    if recomputed_grok_raw != grok_comparison_raw:
        raise ValueError("Frozen Grok DEV comparison bytes differ from native replay")
    reconstructed_freeze = baseline._outer_freeze(
        "DEV", admission, grok_binding, partitions, target_freeze, dev_raw, baseline.DEV_TARGETS_SHA256,
        freeze["runtime_manifest"]["sha256"], freeze["workflow"]["sha256"],
        freeze["sources"]["admission_sha256"], freeze["sources"]["comparison_sha256"], "comparison",
        recomputed_grok_raw, recomputed_grok, captured[baseline.SOURCE_PATH],
    )
    reconstructed_freeze["train_freeze"] = dict(freeze["train_freeze"])
    reconstructed_freeze["selection_frozen_at"] = freeze["selection_frozen_at"]
    if baseline._canonical(reconstructed_freeze) != freeze_raw:
        raise ValueError("Grok DEV freeze bytes differ from native replay")
    plan_path = Path(shared_plan_root).resolve() / "plan.json"
    plan_raw = plan_path.read_bytes()
    if _sha(plan_raw) != sol.PLAN_SHA256:
        raise ValueError("Frozen Sol campaign plan differs")
    captured[plan_path] = plan_raw
    captured.update(_capture_sol_sources(sol, expected_sol_source_bindings))
    campaign = sol.admit_campaign(
        Path(shared_plan_root), Path(sol_execution_root), expected_plan_sha256=sol.PLAN_SHA256,
        expected_source_bindings=expected_sol_source_bindings, expected_reviews=expected_sol_reviews,
    )
    chronology = _chronology(sol, shared_plan_root, sol_execution_root, selection_frozen_at)
    projected_sol, sol_binding = _sol_rows(baseline, campaign, partitions)
    baseline._unchanged(captured)
    sol_result = comparison.evaluate_dev(
        projected_sol["DEV"], dev_targets, fit_raw,
        expected_fit_sha256=freeze["train_freeze"]["fit_sha256"],
        expected_comparison_sha256=freeze["sources"]["comparison_sha256"],
        baseline_manifest_path=runtime_manifest_path,
        baseline_manifest_sha256=freeze["runtime_manifest"]["sha256"],
    )
    if not isinstance(sol_result, dict) or sol_result.get("evidence_class") != "baseline_source_verified_dev_comparison_unadmitted":
        raise ValueError("Inner Sol DEV comparison must retain its source-verified unadmitted class")
    baseline._inner_commitments(sol_result, projected_sol["DEV"], dev_targets, baseline.DEV_TARGETS_SHA256)
    sol_result_raw = baseline._canonical(sol_result)
    if _chronology(sol, shared_plan_root, sol_execution_root, selection_frozen_at) != chronology:
        raise ValueError("Sol checkpoint chronology changed during analysis")
    baseline._unchanged(captured)
    outer = {
        "schema_version": 1,
        "evidence_class": "original_sequence_sol_dev_outer_freeze",
        "workflow": {"sha256": expected_wrapper_sha256},
        "stage": "DEV",
        "provider_calls": 0,
        "execution_authority": False,
        "promotion_authority": False,
        "confirmation_authority": False,
        "sol_comparison_completed": True,
        "no_pooling": True,
        "grok_selection": {
            "dev_freeze_sha256": expected_grok_dev_freeze_sha256,
            "selection_frozen_at": freeze["selection_frozen_at"],
            "workflow_sha256": freeze["workflow"]["sha256"],
            "runtime_manifest_sha256": freeze["runtime_manifest"]["sha256"],
            "admission_sha256": freeze["sources"]["admission_sha256"],
            "comparison_sha256": freeze["sources"]["comparison_sha256"],
            "plan_sha256": freeze["admission"]["plan_sha256"],
            "initialization_sha256": freeze["admission"]["initialization_sha256"],
            "final_settlement_sha256": freeze["admission"]["immutable_provenance"]["ledger_head"]["settlement_sha256"],
            "original_route_sha256": freeze["admission"]["original_initialization"]["route_sha256"],
            "execution_source_sha256": freeze["admission"]["original_initialization"]["execution_source_sha256"],
            "reviewer_task": freeze["admission"]["reviewer_task"],
            "fit_sha256": freeze["train_freeze"]["fit_sha256"],
            "train_freeze_sha256": freeze["train_freeze"]["sha256"],
            "inner_comparison_sha256": freeze["inner"]["sha256"],
            "source_provenance": freeze["source_provenance"],
            "recovery_provenance": freeze["admission"].get("recovery_provenance"),
        },
        "sol_admission": {
            "source_sha256": expected_sol_admission_sha256,
            "plan_sha256": sol.PLAN_SHA256,
            "source_bindings": dict(expected_sol_source_bindings),
            "review_set_sha256": _sha(_canonical(sorted(expected_sol_reviews))),
            "review_count": len(expected_sol_reviews),
            "campaign_sha256": _sha(_canonical(campaign)),
            "row_binding": sol_binding,
            "chronology": chronology,
            "requested_identity": campaign.get("identity_ceiling"),
        },
        "inner": {"sha256": _sha(sol_result_raw), "evidence_class": sol_result["evidence_class"]},
        "limitations": {
            "local_clock_chronology": "selection and authorization ordering relies on trusted local UTC clocks, not external timestamp proof",
            "requested_model_and_effort": "gpt-5.6-sol high requested only",
            "native_endpoint_contact_cardinality": "unproven",
        },
    }
    artifacts = {"sol-dev-comparison-unadmitted.json": sol_result_raw, "sol-dev-freeze.json": _canonical(outer)}
    return {"artifacts": baseline._write(output, artifacts), "freeze": outer}
