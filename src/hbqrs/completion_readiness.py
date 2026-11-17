"""Opt-in bank-based completion diagnostics; historical semantics unchanged.

Always recompute the historical report and finite completion envelope from raw
verdict banks. Caller-supplied reports or numeric intervals are not accepted.
This is fixed-verdict scorer sensitivity, not evidence admission for synthetic
replacements, confidence, human alignment, promotion or execution authority.
"""
from __future__ import annotations

import json
import math
from typing import Any, Mapping, Sequence

from jsonschema import Draft202012Validator

from . import core, decision_readiness, scoring_completion_envelope
from .paths import schema_dir

POLICY = "finite_completion_decision_readiness_v1"
MAX_CASES = scoring_completion_envelope.MAX_CASES


def _threshold(value: float | None) -> None:
    if value is not None and (type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 100):
        raise ValueError("threshold must be a finite number from 0 through 100")


def _compute(modules, bundle, verdicts, *, artifact_id, task_contract, admission_policy, max_cases):
    if task_contract is not None and admission_policy in ("strict_import_v1", "strict_import_v2", "strict_import_v3"):
        schema = json.loads((schema_dir() / "hbq_task_contract.schema.json").read_bytes())
        error = next(Draft202012Validator(schema).iter_errors(task_contract), None)
        if error is not None:
            location = ".".join(map(str, error.absolute_path)) or "contract"
            raise core.HBQError(f"Task contract violates its strict schema at {location}: {error.message}")
    envelope = scoring_completion_envelope.completion_envelope(
        modules, bundle, verdicts, artifact_id=artifact_id, task_contract=task_contract,
        admission_policy=admission_policy, max_cases=max_cases)
    historical = core.score_bundle(modules, bundle, verdicts, artifact_id=artifact_id,
                                          task_contract=task_contract)
    reason = None
    if historical["hard_gate_status"] != "VALID":
        reason = "historical_hard_gate_invalid_or_unresolved"
    elif historical["status"] != "SCORED":
        reason = "historical_status_not_scored"
    elif envelope["status"] != "ENUMERATED_FIXED_VERDICT_COMPLETIONS":
        reason = envelope["status"]
    elif envelope.get("non_scored_completions") != 0:
        reason = "non_scored_completion"
    bounds = envelope["numeric_completion_bounds"]
    if reason is None and (type(bounds) is not dict or set(bounds) != {"lower", "upper"}
                          or any(type(bounds[k]) not in (int, float) or not math.isfinite(bounds[k])
                                 or not 0 <= bounds[k] <= 100 for k in ("lower", "upper"))
                          or bounds["lower"] > bounds["upper"]):
        reason = "completion_bounds_unavailable_or_malformed"
    return historical, envelope, None if reason else bounds, reason


def readiness(
    modules: Sequence[dict[str, Any]], bundle: dict[str, Any], verdicts: list[dict[str, Any]], *,
    artifact_id: str, threshold: float | None = None,
    task_contract: Mapping[str, Any] | None = None,
    admission_policy: str = "strict_import_v1", max_cases: int = MAX_CASES,
) -> dict[str, Any]:
    """Recompute an inclusive threshold relation from original verdict records.

    The existing exact enumerator strictly admits the bank and permits at most
    MAX_CASES (19683) finite replacements per bank; callers may lower this cap.
    Unsupported inputs raise rather than emit a usable relation. Historical
    invalid/unresolved gates, non-SCORED reports, exceeded caps, and non-SCORED
    completions withhold numeric decision bounds. No report or interval input is
    accepted. Returned historical report/readiness retain their old semantics.
    """
    _threshold(threshold)
    report, envelope, bounds, reason = _compute(
        modules, bundle, verdicts, artifact_id=artifact_id, task_contract=task_contract,
        admission_policy=admission_policy, max_cases=max_cases)
    relation = None if threshold is None else (
        "UNAVAILABLE" if reason else "ROBUSTLY_MEETS" if bounds["lower"] >= threshold
        else "ROBUSTLY_BELOW" if bounds["upper"] < threshold else "UNRESOLVED")
    return {"policy": POLICY, "historical_report": report,
            "historical_readiness": decision_readiness.decision_readiness(report, threshold=threshold),
            "completion_envelope": envelope,
            "completion_readiness": {"status": "UNAVAILABLE" if reason else "AVAILABLE",
                                     "reason": reason, "bounds": bounds,
                                     "threshold": threshold, "relation": relation,
                                     "convention": "score >= threshold"}}


def comparison(
    modules: Sequence[dict[str, Any]], bundle: dict[str, Any],
    left_verdicts: list[dict[str, Any]], right_verdicts: list[dict[str, Any]], *,
    left_artifact_id: str, right_artifact_id: str,
    task_contract: Mapping[str, Any] | None = None,
    admission_policy: str = "strict_import_v1", max_cases: int = MAX_CASES,
) -> dict[str, Any]:
    """Strictly separate recomputed ranges under shared supplied scorer inputs.

    Keep historical report-visible compatibility requirements. Dynamic task
    contexts are withheld because historical comparison needs a further context
    attestation; this API does not accept that attestation as proof.
    The cap applies separately to each bank (at most 2 * MAX_CASES combined).
    Independent bank completions cover a Cartesian product, not shared latent
    evidence or a model/human preference claim. Touching endpoints do not rank.
    """
    args = dict(task_contract=task_contract, admission_policy=admission_policy, max_cases=max_cases)
    left = readiness(modules, bundle, left_verdicts, artifact_id=left_artifact_id, **args)
    right = readiness(modules, bundle, right_verdicts, artifact_id=right_artifact_id, **args)
    legacy = decision_readiness.interval_comparison(left["historical_report"], right["historical_report"])
    relation, reason = "INCONCLUSIVE", "completion_ranges_overlap_or_touch"
    a, b = left["completion_readiness"], right["completion_readiness"]
    if legacy["relation"] in ("INELIGIBLE", "INCOMPARABLE"):
        relation, reason = legacy["relation"], legacy["reason"]
    elif a["status"] != "AVAILABLE" or b["status"] != "AVAILABLE":
        relation, reason = "UNAVAILABLE", "one_or_both_completion_readiness_unavailable"
    elif a["bounds"]["lower"] > b["bounds"]["upper"]:
        relation, reason = "LEFT_ABOVE", "strictly_separated_completion_ranges"
    elif b["bounds"]["lower"] > a["bounds"]["upper"]:
        relation, reason = "RIGHT_ABOVE", "strictly_separated_completion_ranges"
    return {"policy": POLICY, "left": left, "right": right, "historical_comparison": legacy,
            "completion_comparison": {"relation": relation, "reason": reason,
                                      "full_context_provenance_established": False}}
