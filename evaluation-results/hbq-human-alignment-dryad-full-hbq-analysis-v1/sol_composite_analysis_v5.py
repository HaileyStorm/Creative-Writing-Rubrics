"""Fail-closed Sol DEV replay after the successor composite Dryad freeze.

This is a provider-free adapter.  It never treats the retained early Sol prefix
as original-sequence evidence: the adopted amendment and the current provisional
snapshot are both explicit inputs, and the returned record remains unadmitted.
"""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType
from typing import Any

ROOT = Path(__file__).resolve().parent
REPOSITORY = ROOT.parents[1]
COMPOSITE_PATH = ROOT / "baseline_composite_analysis_v5.py"
LEGACY_SOL_PATH = ROOT / "sol_analysis_workflow.py"
SOL_ADMISSION_PATH = ROOT / "sol_pass_admission.py"
COMPARISON_PATH = ROOT / "dev_comparison.py"
WORKFLOW_PATH = ROOT / "baseline_analysis_workflow.py"
DEV_COUNT = 60


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canonical(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def _hash(value: Any, label: str) -> str:
    if (
        type(value) is not str
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
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
        return json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=pairs,
            parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)),
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise ValueError(f"{label} is not strict JSON") from error


def _read(path: Path | str, expected: str, label: str) -> tuple[Path, bytes]:
    checked = Path(path).resolve()
    raw = checked.read_bytes()
    if _sha(raw) != _hash(expected, f"{label} expected hash"):
        raise ValueError(f"{label} hash drift")
    return checked, raw


def _load(path: Path, raw: bytes, label: str) -> ModuleType:
    name = f"_dryad_sol_composite_{label}_{uuid.uuid4().hex}"
    spec = __import__("importlib.util").util.spec_from_loader(name, loader=None)
    if spec is None:
        raise ValueError(f"Cannot load {label}")
    module = __import__("importlib.util").util.module_from_spec(spec)
    module.__file__ = str(path)
    exec(compile(raw, str(path), "exec"), module.__dict__)  # noqa: S102 - exact hash-pinned local sources only.
    return module


def _unchanged(captured: Mapping[Path, bytes]) -> None:
    if any(path.read_bytes() != raw for path, raw in captured.items()):
        raise ValueError("Pinned successor Sol analysis input changed during execution")


def _output(path: Path | str, *protected: Path | str) -> Path:
    output = Path(os.path.abspath(path)).resolve()
    roots = [REPOSITORY]
    for item in protected:
        checked = Path(os.path.abspath(item)).resolve()
        roots.append(checked.parent if checked.is_file() else checked)
    if output.exists() or any(
        output.is_relative_to(root) or root.is_relative_to(output) for root in roots
    ):
        raise ValueError("Sol composite output must be a fresh external directory")
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
            raise ValueError("Written Sol composite artifact differs from frozen bytes")
        staging.replace(output)
        return reported
    except Exception as error:
        raise RuntimeError(f"Sol composite stage retained at {staging}") from error


def _progress(path: Path | str, expected: str) -> tuple[Path, bytes, dict[str, Any]]:
    checked, raw = _read(path, expected, "Sol partial progress snapshot")
    value = _json(raw, "Sol partial progress snapshot")
    sol = value.get("sol") if isinstance(value, Mapping) else None
    if (
        not isinstance(value, dict)
        or value.get("evidence_class") != "incomplete_collection_progress_snapshot"
        or value.get("full_study_admission") is not False
        or value.get("alignment_result") is not None
        or value.get("execution_authority") is not False
        or not isinstance(sol, Mapping)
        or sol.get("provisional_pass_number") != 19
        or sol.get("provisional_pass_remains_unadmitted") is not True
        or sol.get("recovered_transport_ordinal") != 221
    ):
        raise ValueError(
            "Sol partial progress snapshot does not retain the unresolved gate"
        )
    return checked, raw, dict(sol)


def _replayed_composite_freeze(
    result: Mapping[str, Any],
    comparison_path: Path | str,
    freeze_path: Path | str,
    expected_comparison_sha256: str,
    expected_freeze_sha256: str,
    expected_fit_sha256: str,
    expected_train_freeze_sha256: str,
) -> tuple[dict[str, Any], bytes, bytes]:
    if not isinstance(result, Mapping) or set(result) != {
        "comparison_raw",
        "freeze_raw",
        "freeze",
    }:
        raise ValueError("Composite DEV replay result schema differs")
    freeze = result["freeze"]
    if (
        not isinstance(freeze, dict)
        or type(result["comparison_raw"]) is not bytes
        or type(result["freeze_raw"]) is not bytes
    ):
        raise ValueError("Composite DEV replay artifacts differ")
    _comparison_path, comparison_raw = _read(
        comparison_path, expected_comparison_sha256, "Frozen composite DEV comparison"
    )
    _freeze_path, freeze_raw = _read(
        freeze_path, expected_freeze_sha256, "Frozen composite DEV freeze"
    )
    comparison = _json(comparison_raw, "Reconstructed composite DEV comparison")
    if (
        result["comparison_raw"] != comparison_raw
        or result["freeze_raw"] != freeze_raw
        or freeze_raw != _canonical(freeze)
    ):
        raise ValueError("Composite DEV replay bytes differ")
    admission = freeze.get("admission")
    binding = freeze.get("admission_binding")
    scoring = freeze.get("scoring")
    train = freeze.get("train")
    inner = freeze.get("inner")
    if (
        freeze.get("schema_version") != 1
        or freeze.get("evidence_class") != "composite_dev_outer_freeze_v5"
        or freeze.get("stage") != "DEV"
        or freeze.get("provider_calls") != 0
        or freeze.get("execution_authority") is not False
        or freeze.get("promotion_authority") is not False
        or freeze.get("confirmation_authority") is not False
        or freeze.get("sol_validation") is not False
        or not isinstance(admission, Mapping)
        or not isinstance(binding, Mapping)
        or not isinstance(scoring, Mapping)
        or not isinstance(train, Mapping)
        or not isinstance(inner, Mapping)
        or train
        != {
            "fit_sha256": expected_fit_sha256,
            "freeze_sha256": expected_train_freeze_sha256,
        }
        or inner
        != {
            "sha256": _sha(comparison_raw),
            "evidence_class": comparison.get("evidence_class"),
        }
        or comparison.get("evidence_class")
        != "baseline_source_verified_dev_comparison_unadmitted"
        or type(binding.get("canonical_composite_admission_sha256")) is not str
        or admission.get("counts")
        != {"passes": 236, "logical": 5428, "native": 5427, "recovered": 1}
        or admission.get("recovered_ordinals") != [70]
        or scoring.get("parity", {}).get("evidence_class")
        != "v1_v5_source_bound_scoring_parity"
        or _hash(scoring.get("commitment_sha256"), "v1 scoring parity commitment")
        != _sha(_canonical(scoring["parity"]))
        or type(freeze.get("selection_frozen_at")) is not str
    ):
        raise ValueError("Composite DEV freeze does not bind the full successor study")
    _hash(
        binding["canonical_composite_admission_sha256"], "Composite admission binding"
    )
    return freeze, comparison_raw, freeze_raw


def _amendment(
    legacy: ModuleType,
    *,
    amendment_manifest_path: Path | str,
    cohort_bindings_root: Path | str,
    approval_path: Path | str,
    cutoff_path: Path | str,
    native_root: Path | str,
) -> tuple[dict[str, Any], dict[Path, bytes]]:
    return legacy._amendment_context(
        amendment_manifest_path,
        cohort_bindings_root,
        approval_path=approval_path,
        cutoff_path=cutoff_path,
        native_root=native_root,
    )


def _sol_campaign(
    legacy: ModuleType,
    sol: ModuleType,
    *,
    plan_root: Path | str,
    execution_root: Path | str,
    expected_source_bindings: Mapping[str, str],
    expected_reviews: set[str],
    transport: Mapping[str, Any] | None,
    transport_adoption_path: Path | str | None,
    expected_transport_adoption_sha256: str | None,
    transport_incident_path: Path | str | None,
) -> Mapping[str, Any]:
    if transport is None:
        return sol.admit_campaign(
            Path(plan_root),
            Path(execution_root),
            expected_plan_sha256=sol.PLAN_SHA256,
            expected_source_bindings=expected_source_bindings,
            expected_reviews=expected_reviews,
        )
    campaign = transport["helper"].admit_campaign(
        Path(plan_root),
        Path(execution_root),
        expected_plan_sha256=sol.PLAN_SHA256,
        expected_source_bindings=expected_source_bindings,
        expected_reviews=expected_reviews,
        adoption_path=transport_adoption_path,
        expected_adoption_sha256=expected_transport_adoption_sha256,
        incident_path=transport_incident_path,
    )
    if not isinstance(campaign, Mapping) or legacy._canonical(
        campaign.get("transport_recovery")
    ) != legacy._canonical(transport["provenance"]):
        raise ValueError("Recovered Sol transport campaign provenance differs")
    return campaign


def compare_composite_sol(
    plan_root: Path | str,
    public_inputs_path: Path | str,
    predecessor_path: Path | str,
    suffix_root: Path | str,
    scoring_manifest_path: Path | str,
    v5_runtime_manifest_path: Path | str,
    v5_runtime_package_root: Path | str,
    dev_targets_path: Path | str,
    fit_path: Path | str,
    train_freeze_path: Path | str,
    grok_dev_comparison_path: Path | str,
    grok_dev_freeze_path: Path | str,
    sol_execution_root: Path | str,
    progress_snapshot_path: Path | str,
    output_root: Path | str,
    *,
    expected_plan_sha256: str,
    expected_public_inputs_sha256: str,
    expected_predecessor_sha256: str,
    expected_suffix_epoch_sha256: str,
    expected_suffix_source_sha256: str,
    expected_composite_analysis_sha256: str,
    expected_composer_sha256: str,
    expected_workflow_sha256: str,
    expected_comparison_sha256: str,
    expected_scoring_runtime_loader_sha256: str,
    expected_v5_runtime_loader_sha256: str,
    expected_scoring_manifest_sha256: str,
    expected_v5_runtime_manifest_sha256: str,
    expected_v5_runtime_package_manifest_sha256: str,
    expected_fit_sha256: str,
    expected_train_freeze_sha256: str,
    expected_grok_dev_comparison_sha256: str,
    expected_grok_dev_freeze_sha256: str,
    approved_v4_routes: Mapping[str, Any],
    approved_v5_routes: Mapping[str, Any],
    expected_sol_analysis_sha256: str,
    expected_legacy_sol_workflow_sha256: str,
    expected_sol_admission_sha256: str,
    expected_sol_source_bindings: Mapping[str, str],
    expected_sol_reviews: set[str],
    expected_progress_snapshot_sha256: str,
    amendment_manifest_path: Path | str,
    cohort_bindings_root: Path | str,
    approval_path: Path | str,
    cutoff_path: Path | str,
    native_root: Path | str,
    transport_adoption_path: Path | str | None = None,
    expected_transport_adoption_sha256: str | None = None,
    transport_incident_path: Path | str | None = None,
    expected_recovered_interpreter_sha256: str | None = None,
) -> dict[str, Any]:
    """Replay successor Grok first, then score separately admitted Sol DEV rows only."""
    output = _output(
        output_root,
        plan_root,
        public_inputs_path,
        predecessor_path,
        suffix_root,
        scoring_manifest_path,
        v5_runtime_manifest_path,
        v5_runtime_package_root,
        dev_targets_path,
        fit_path,
        train_freeze_path,
        grok_dev_comparison_path,
        grok_dev_freeze_path,
        sol_execution_root,
        progress_snapshot_path,
        amendment_manifest_path,
        approval_path,
        cutoff_path,
        native_root,
    )
    own_path, own_raw = _read(
        Path(__file__), expected_sol_analysis_sha256, "Successor Sol analysis"
    )
    composite_path, composite_raw = _read(
        COMPOSITE_PATH, expected_composite_analysis_sha256, "Composite analysis"
    )
    legacy_path, legacy_raw = _read(
        LEGACY_SOL_PATH,
        expected_legacy_sol_workflow_sha256,
        "Pinned legacy Sol workflow",
    )
    sol_path, sol_raw = _read(
        SOL_ADMISSION_PATH, expected_sol_admission_sha256, "Sol admission"
    )
    comparison_path, comparison_raw = _read(
        COMPARISON_PATH, expected_comparison_sha256, "DEV comparison"
    )
    workflow_path, workflow_raw = _read(
        WORKFLOW_PATH, expected_workflow_sha256, "Workflow pure helpers"
    )
    captured = {
        own_path: own_raw,
        composite_path: composite_raw,
        legacy_path: legacy_raw,
        sol_path: sol_raw,
        comparison_path: comparison_raw,
        workflow_path: workflow_raw,
    }
    composite = _load(composite_path, composite_raw, "analysis")
    legacy = _load(legacy_path, legacy_raw, "workflow")
    sol = legacy._load(sol_path, sol_raw, "sol_admission")
    comparison = _load(comparison_path, comparison_raw, "comparison")
    workflow = _load(workflow_path, workflow_raw, "workflow_helpers")
    progress_path, progress_raw, progress = _progress(
        progress_snapshot_path, expected_progress_snapshot_sha256
    )
    captured[progress_path] = progress_raw
    amendment, amendment_captured = _amendment(
        legacy,
        amendment_manifest_path=amendment_manifest_path,
        cohort_bindings_root=cohort_bindings_root,
        approval_path=approval_path,
        cutoff_path=cutoff_path,
        native_root=native_root,
    )
    captured.update(amendment_captured)
    transport = legacy._transport_adoption_context(
        transport_adoption_path=transport_adoption_path,
        expected_transport_adoption_sha256=expected_transport_adoption_sha256,
        transport_incident_path=transport_incident_path,
        expected_recovered_interpreter_sha256=expected_recovered_interpreter_sha256,
        expected_sol_admission_sha256=expected_sol_admission_sha256,
    )
    if transport is None:
        raise ValueError(
            "Successor Sol replay requires the adopted ordinal-221 transport interpretation"
        )
    captured.update(transport["captured"])
    _unchanged(captured)
    grok = composite.replay_composite_dev(
        plan_root,
        public_inputs_path,
        predecessor_path,
        suffix_root,
        scoring_manifest_path,
        v5_runtime_manifest_path,
        v5_runtime_package_root,
        dev_targets_path,
        fit_path,
        train_freeze_path,
        grok_dev_comparison_path,
        grok_dev_freeze_path,
        expected_plan_sha256=expected_plan_sha256,
        expected_public_inputs_sha256=expected_public_inputs_sha256,
        expected_predecessor_sha256=expected_predecessor_sha256,
        expected_suffix_epoch_sha256=expected_suffix_epoch_sha256,
        expected_suffix_source_sha256=expected_suffix_source_sha256,
        expected_analysis_sha256=expected_composite_analysis_sha256,
        expected_composer_sha256=expected_composer_sha256,
        expected_workflow_sha256=expected_workflow_sha256,
        expected_comparison_sha256=expected_comparison_sha256,
        expected_scoring_runtime_loader_sha256=expected_scoring_runtime_loader_sha256,
        expected_v5_runtime_loader_sha256=expected_v5_runtime_loader_sha256,
        expected_scoring_manifest_sha256=expected_scoring_manifest_sha256,
        expected_v5_runtime_manifest_sha256=expected_v5_runtime_manifest_sha256,
        expected_v5_runtime_package_manifest_sha256=expected_v5_runtime_package_manifest_sha256,
        expected_fit_sha256=expected_fit_sha256,
        expected_train_freeze_sha256=expected_train_freeze_sha256,
        expected_dev_comparison_sha256=expected_grok_dev_comparison_sha256,
        expected_dev_freeze_sha256=expected_grok_dev_freeze_sha256,
        approved_v4_routes=approved_v4_routes,
        approved_v5_routes=approved_v5_routes,
    )
    freeze, grok_raw, grok_freeze_raw = _replayed_composite_freeze(
        grok,
        grok_dev_comparison_path,
        grok_dev_freeze_path,
        expected_grok_dev_comparison_sha256,
        expected_grok_dev_freeze_sha256,
        expected_fit_sha256,
        expected_train_freeze_sha256,
    )
    frozen_comparison_path, frozen_comparison_raw = _read(
        grok_dev_comparison_path,
        expected_grok_dev_comparison_sha256,
        "Frozen composite DEV comparison",
    )
    frozen_freeze_path, frozen_freeze_raw = _read(
        grok_dev_freeze_path,
        expected_grok_dev_freeze_sha256,
        "Frozen composite DEV freeze",
    )
    if frozen_comparison_raw != grok_raw or frozen_freeze_raw != grok_freeze_raw:
        raise ValueError("Composite DEV replay bytes changed after reconstruction")
    captured[frozen_comparison_path] = frozen_comparison_raw
    captured[frozen_freeze_path] = frozen_freeze_raw
    selection = sol._time(
        freeze["selection_frozen_at"], "Composite Grok selection freeze"
    )
    if selection > datetime.now(timezone.utc):
        raise ValueError("Composite Grok selection freeze is in the future")
    campaign = _sol_campaign(
        legacy,
        sol,
        plan_root=plan_root,
        execution_root=sol_execution_root,
        expected_source_bindings=expected_sol_source_bindings,
        expected_reviews=expected_sol_reviews,
        transport=transport,
        transport_adoption_path=transport_adoption_path,
        expected_transport_adoption_sha256=expected_transport_adoption_sha256,
        transport_incident_path=transport_incident_path,
    )
    chronology = legacy._chronology(
        sol, plan_root, sol_execution_root, selection, amendment
    )
    inputs_path, inputs_raw, partitions = workflow._partition_ids(public_inputs_path)
    captured[inputs_path] = inputs_raw
    projected, row_binding = legacy._sol_rows(workflow, campaign, partitions)
    if len(projected["DEV"]) != DEV_COUNT:
        raise ValueError("Sol DEV projection differs")
    fit_checked, fit_raw = _read(
        fit_path, expected_fit_sha256, "Frozen composite TRAIN fit"
    )
    captured[fit_checked] = fit_raw
    dev_path, dev_raw, targets = workflow._targets(
        dev_targets_path, workflow.DEV_TARGETS_SHA256, "DEV", partitions["DEV"]
    )
    captured[dev_path] = dev_raw
    _unchanged(captured)
    result = comparison.evaluate_dev(
        projected["DEV"],
        targets,
        fit_raw,
        expected_fit_sha256=expected_fit_sha256,
        expected_comparison_sha256=expected_comparison_sha256,
        baseline_manifest_path=scoring_manifest_path,
        baseline_manifest_sha256=expected_scoring_manifest_sha256,
    )
    if (
        not isinstance(result, dict)
        or result.get("evidence_class")
        != "baseline_source_verified_dev_comparison_unadmitted"
    ):
        raise ValueError(
            "Inner Sol DEV comparison must remain source-verified and unadmitted"
        )
    workflow._inner_commitments(
        result, projected["DEV"], targets, workflow.DEV_TARGETS_SHA256
    )
    result_raw = _canonical(result)
    replayed_chronology = legacy._chronology(
        sol, plan_root, sol_execution_root, selection, amendment
    )
    if replayed_chronology != chronology:
        raise ValueError("Sol checkpoint chronology changed during analysis")
    _unchanged(captured)
    outer = {
        "schema_version": 1,
        "evidence_class": "sequencing_amended_composite_sol_dev_outer_freeze_v5",
        "stage": "DEV",
        "provider_calls": 0,
        "execution_authority": False,
        "promotion_authority": False,
        "confirmation_authority": False,
        "full_study_admission": False,
        "alignment_result": None,
        "sol_comparison_completed": True,
        "no_pooling": True,
        "grok_selection": {
            "composite_dev_freeze_sha256": _sha(grok_freeze_raw),
            "composite_dev_comparison_sha256": _sha(grok_raw),
            "selection_frozen_at": freeze["selection_frozen_at"],
            "train": freeze["train"],
            "admission_binding": freeze["admission_binding"],
            "scoring_commitment_sha256": freeze["scoring"]["commitment_sha256"],
        },
        "sol_admission": {
            "source_sha256": expected_sol_admission_sha256,
            "campaign_sha256": _sha(legacy._canonical(campaign)),
            "row_binding": row_binding,
            "chronology": chronology,
            "transport_recovery": transport["provenance"],
        },
        "sequencing_amendment": {
            "manifest_sha256": amendment["manifest_sha256"],
            "proposal_sha256": amendment["manifest"]["proposal_sha256"],
            "approval_sha256": amendment["manifest"]["approval_sha256"],
            "approval_recorded_at": amendment["manifest"]["approval_recorded_at"],
            "deviation_label": "sequencing_amended_after_partial_sol_observation",
        },
        "current_sol_prefix": {
            "snapshot_sha256": expected_progress_snapshot_sha256,
            "provisional_pass_number": progress["provisional_pass_number"],
            "provisional_pass_remains_unadmitted": progress[
                "provisional_pass_remains_unadmitted"
            ],
            "recovered_transport_ordinal": progress["recovered_transport_ordinal"],
        },
        "inner": {
            "sha256": _sha(result_raw),
            "evidence_class": result["evidence_class"],
        },
        "limitations": {
            "original_sequence": "ineligible: Sol observation preceded composite Grok selection",
            "adopted_sequence": "sequencing-amended after partial Sol observation",
            "native_endpoint_contact_cardinality": "unproven",
            "requested_model_and_effort": "gpt-5.6-sol high requested only",
        },
    }
    return {
        "artifacts": _write(
            output,
            {
                "sol-composite-dev-comparison-unadmitted.json": result_raw,
                "sol-composite-dev-freeze.json": _canonical(outer),
            },
        ),
        "freeze": outer,
    }
