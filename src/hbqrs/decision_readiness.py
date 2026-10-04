"""Opt-in descriptive diagnostics over existing scores; never rescore or promote.

Bounds describe rubric sensitivity to unassessed verdicts, not statistical
confidence intervals or calibrated model confidence. The historical scorer and
its positive-only coverage retain their existing meaning.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import re
from typing import Any, Mapping, Sequence

from .core import HBQError


POLICY = "descriptive_decision_readiness_v1"
COMPARISON_POLICY = "strict_interval_comparison_v1"
_STATES = {"YES", "NO", "CANNOT_ASSESS", "NOT_APPLICABLE"}


def _number(value: Any, name: str, low: float = 0, high: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise HBQError(f"{name} must be a finite number")
    if value < low or (high is not None and value > high):
        raise HBQError(f"{name} is outside its allowed range")
    return float(value)


def _rows(value: Any, name: str) -> list[Mapping[str, Any]]:
    if not isinstance(value, list) or not all(isinstance(row, Mapping) for row in value):
        raise HBQError(f"{name} must be a list of objects")
    return value


def _assessment(groups: Sequence[Mapping[str, Any]], name: str) -> dict[str, Any]:
    applicable = assessed = 0.0
    unassessed_count = 0
    for group in groups:
        for question in _rows(group.get("questions"), f"{name}.questions"):
            weight = _number(question.get("weight"), f"{name}.question.weight")
            state = question.get("verdict")
            if state not in _STATES:
                raise HBQError(f"{name}.question.verdict is unsupported")
            if state == "NOT_APPLICABLE":
                continue
            applicable += weight
            if state == "CANNOT_ASSESS":
                unassessed_count += 1
            else:
                assessed += weight
    return {
        "applicable_weight": applicable,
        "assessed_weight": assessed,
        "unassessed_questions": unassessed_count,
        "complete": unassessed_count == 0,
    }


def decision_readiness(report: Mapping[str, Any], *, threshold: float | None = None) -> dict[str, Any]:
    """Describe completeness and an inclusive ``score >= threshold`` relation.

    Inputs are trusted local v1/v2 score reports. This checks only fields needed
    for diagnostics, and does not establish evidence validity or literary truth.
    """
    if not isinstance(report, Mapping):
        raise HBQError("score report must be an object")
    for name in ("bundle_id", "artifact_id", "status"):
        if not isinstance(report.get(name), str) or not report[name]:
            raise HBQError(f"score report requires {name}")
    gate = report.get("hard_gate_status")
    if gate not in {"VALID", "INVALID", "UNRESOLVED"}:
        raise HBQError("score report requires a supported hard_gate_status")
    coverage = _number(report.get("coverage"), "coverage", high=1)
    domains = _rows(report.get("domains"), "domains")
    penalties = _rows(report.get("penalties"), "penalties")
    positive = _assessment(domains, "domains")
    positive["weighted_coverage"] = coverage
    positive["complete"] = positive["complete"] and positive["applicable_weight"] > 0
    penalty = _assessment(penalties, "penalties")
    penalty["assessed_coverage"] = (
        penalty["assessed_weight"] / penalty["applicable_weight"]
        if penalty["applicable_weight"] else 1.0
    )
    penalty["coverage_basis"] = "pooled_applicable_effective_leaf_weight"
    score = report.get("final_score")
    if not isinstance(score, Mapping) or not {"observed", "lower", "upper"} <= score.keys():
        raise HBQError("score report requires final_score observed/lower/upper")
    observed = score["observed"]
    if observed is not None:
        _number(observed, "final_score.observed", high=100)
    lower, upper = score["lower"], score["upper"]
    if (lower is None) != (upper is None):
        raise HBQError("final_score bounds must both be numbers or both be null")
    if lower is not None:
        _number(lower, "final_score.lower", high=100)
        _number(upper, "final_score.upper", high=100)
        if lower > upper:
            raise HBQError("final_score lower exceeds upper")
    eligible = gate == "VALID"
    fully_assessed = eligible and positive["complete"] and penalty["complete"]
    usable = observed is not None and lower is not None
    relation = None
    if threshold is not None:
        threshold = _number(threshold, "threshold", high=100)
        relation = (
            "UNAVAILABLE" if lower is None else
            "ROBUSTLY_MEETS" if lower >= threshold else
            "ROBUSTLY_BELOW" if upper < threshold else "UNRESOLVED"
        )
    return {
        "policy": POLICY,
        "artifact_id": report["artifact_id"],
        "bundle_id": report["bundle_id"],
        "reported_status": report["status"],
        "hard_gate_status": gate,
        "eligible": eligible,
        "positive": positive,
        "penalties": penalty,
        "fully_assessed": fully_assessed,
        "fully_assessed_point_score": (
            fully_assessed and usable and report["status"] == "SCORED" and lower == upper
        ),
        "scalar_interval": {
            "observed": observed, "lower": lower, "upper": upper,
            "width": None if lower is None else upper - lower,
            "meaning": "rubric_sensitivity_bounds_not_statistical_confidence",
        },
        "threshold": None if threshold is None else {
            "value": threshold, "convention": "score >= threshold",
            "relation": relation, "basis": "scalar_bounds_only_hard_gate_eligibility_is_separate",
        },
    }


def _structure(report: Mapping[str, Any]) -> dict[str, Any]:
    def questions(group: Mapping[str, Any], weighted: bool = True) -> list[tuple[Any, ...]]:
        result = []
        for question in _rows(group.get("questions"), "comparison questions"):
            qid = question.get("question_id")
            if not isinstance(qid, str) or not qid:
                raise HBQError("comparison requires question_id")
            result.append((qid, question.get("module_id"),
                           question.get("weight") if weighted else None,
                           question.get("verdict") != "NOT_APPLICABLE"))
        return sorted(result, key=lambda row: row[0])

    gates = _rows(report.get("hard_gates"), "hard_gates")
    return {
        "standard": report.get("standard"),
        "bundle_id": report["bundle_id"],
        "bundle_version": report.get("bundle_version"),
        "minimum_coverage": report.get("minimum_coverage"),
        "task_contract": report.get("task_contract"),
        "domains": sorted([
            (group.get("domain_id"), group.get("nominal_points"), questions(group))
            for group in report["domains"]
        ], key=lambda row: str(row[0])),
        "penalties": sorted([
            (group.get("module_id"), group.get("cap_points"), questions(group))
            for group in report["penalties"]
        ], key=lambda row: str(row[0])),
        "hard_gates": questions({"questions": gates}, weighted=False),
    }


def interval_comparison(
    left: Mapping[str, Any], right: Mapping[str, Any], *,
    comparison_context_sha256: str | None = None,
) -> dict[str, Any]:
    """Compare compatible eligible report bounds with strict separation.

    A shared context digest is the caller's attestation that both reports use
    the same frozen conditions; this module cannot verify that external binding.
    Bare dynamic-contract metadata omits question/source content and is
    insufficient. Null-contract comparisons establish report structure only,
    not model, prompt, source-revision, or full frozen-context equivalence.
    """
    a, b = decision_readiness(left), decision_readiness(right)
    if comparison_context_sha256 is not None and not re.fullmatch(r"[0-9a-fA-F]{64}", comparison_context_sha256):
        raise HBQError("comparison_context_sha256 must be a SHA-256 hex digest")
    result: dict[str, Any] = {
        "policy": COMPARISON_POLICY,
        "left_artifact_id": left["artifact_id"], "right_artifact_id": right["artifact_id"],
        "relation": "INCONCLUSIVE", "reason": "intervals_overlap_or_touch",
        "compatibility_basis": "report_visible_bundle_question_role_weight_and_applicability",
        "full_context_attestation": (
            "caller_supplied_shared_digest" if comparison_context_sha256 else "not_established"
        ),
        "comparison_context_sha256": comparison_context_sha256,
        "interval_meaning": "rubric_sensitivity_bounds_not_statistical_confidence",
    }
    if not a["eligible"] or not b["eligible"]:
        result.update(relation="INELIGIBLE", reason="hard_gate_invalid_or_unresolved")
    elif any(not report.get("standard") or not report.get("bundle_version") for report in (left, right)):
        result.update(relation="INCOMPARABLE", reason="report_scoring_context_incomplete")
    elif left.get("scoring_policy") != right.get("scoring_policy"):
        result.update(relation="INCOMPARABLE", reason="scoring_policy_differs")
    elif left.get("scoring_policy") is not None and any(not report.get("scoring_context") for report in (left, right)):
        result.update(relation="INCOMPARABLE", reason="declared_scoring_policy_context_incomplete")
    elif left.get("scoring_context") != right.get("scoring_context"):
        result.update(relation="INCOMPARABLE", reason="scoring_context_commitments_differ")
    elif _structure(left) != _structure(right):
        result.update(relation="INCOMPARABLE", reason="report_scoring_context_differs")
    elif (left.get("task_contract") is not None or right.get("task_contract") is not None) and not comparison_context_sha256:
        result.update(relation="INCOMPARABLE", reason="dynamic_task_contract_requires_frozen_context_attestation")
    elif any(report["status"] != "SCORED" for report in (left, right)):
        result.update(reason="report_status_not_scored")
    elif any(item["scalar_interval"]["observed"] is None for item in (a, b)):
        result.update(reason="observed_scalar_unavailable")
    elif any(item["scalar_interval"]["lower"] is None for item in (a, b)):
        result.update(reason="scalar_bounds_unavailable")
    else:
        ai, bi = a["scalar_interval"], b["scalar_interval"]
        if ai["lower"] > bi["upper"]:
            result.update(relation="LEFT_ABOVE", reason="strictly_separated_bounds")
        elif bi["lower"] > ai["upper"]:
            result.update(relation="RIGHT_ABOVE", reason="strictly_separated_bounds")
    return result


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    parser.add_argument("--compare", type=Path)
    parser.add_argument("--threshold", type=float)
    parser.add_argument("--comparison-context-sha256", help="Caller attests both reports share this frozen context")
    args = parser.parse_args(argv)
    try:
        report_bytes = args.report.read_bytes()
        report = json.loads(report_bytes)
        output = {
            "report_sha256": hashlib.sha256(report_bytes).hexdigest(),
            "readiness": decision_readiness(report, threshold=args.threshold),
        }
        if args.compare:
            other_bytes = args.compare.read_bytes()
            other = json.loads(other_bytes)
            output["comparison_report_sha256"] = hashlib.sha256(other_bytes).hexdigest()
            output["comparison_readiness"] = decision_readiness(other, threshold=args.threshold)
            output["comparison"] = interval_comparison(
                report, other, comparison_context_sha256=args.comparison_context_sha256,
            )
        elif args.comparison_context_sha256:
            raise HBQError("--comparison-context-sha256 requires --compare")
    except (OSError, ValueError, HBQError) as error:
        parser.exit(2, f"decision readiness: {error}\n")
    print(json.dumps(output, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
