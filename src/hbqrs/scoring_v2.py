"""Versioned score-report v2 additions over the immutable v1 scorer."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping, Sequence

from jsonschema import Draft202012Validator

from . import core
from .paths import schema_dir


V2_SCHEMA = "../schema/hbq_score_report.v2.schema.json"


def _weighted_median(values: Sequence[tuple[float, float]]) -> float | None:
    """Return the lower weighted median; an exact-half tie selects the lower value."""

    positive = sorted((value, weight) for value, weight in values if weight > 0)
    total_weight = sum(weight for _, weight in positive)
    if total_weight <= 0:
        return None
    running_weight = 0.0
    for value, weight in positive:
        running_weight += weight
        if running_weight * 2 >= total_weight:
            return value
    return positive[-1][0]


def _role_aggregate(
    records: Sequence[Mapping[str, Any]],
    *,
    normalized_verdicts: Mapping[str, Mapping[str, Any]],
    effective_states: Mapping[str, str],
) -> dict[str, Any]:
    assessed: list[tuple[float, float]] = []
    applicable_count = 0
    applicable_weight = 0.0
    assessed_weight = 0.0
    confidence_mass = 0.0
    for record in records:
        question_id = str(record["question"]["id"])
        state = effective_states[question_id]
        weight = float(record["effective_weight"])
        if state == "NOT_APPLICABLE":
            continue
        applicable_count += 1
        applicable_weight += weight
        if state not in {"YES", "NO"}:
            continue
        confidence = float(normalized_verdicts[question_id]["confidence"])
        assessed.append((confidence, weight))
        assessed_weight += weight
        confidence_mass += confidence * weight
    weighted_mean = confidence_mass / assessed_weight if assessed_weight else None
    return {
        "question_count": len(records),
        "applicable_count": applicable_count,
        "assessed_count": len(assessed),
        "applicable_effective_weight": round(applicable_weight, 6),
        "assessed_effective_weight": round(assessed_weight, 6),
        "assessed_raw_confidence_weighted_mean": (
            None if weighted_mean is None else round(weighted_mean, 4)
        ),
        "assessed_raw_confidence_weighted_median": (
            None if (median := _weighted_median(assessed)) is None else round(median, 4)
        ),
        "assessed_effective_weight_threshold_shares": {
            f"gte_{threshold}": (
                round(
                    sum(weight for confidence, weight in assessed if confidence >= cutoff)
                    / assessed_weight,
                    4,
                )
                if assessed_weight
                else None
            )
            for threshold, cutoff in (("0_5", 0.5), ("0_75", 0.75), ("0_9", 0.9))
        },
        "effective_confidence_mass": {
            "value": (
                round(confidence_mass / applicable_weight, 4)
                if assessed_weight and applicable_weight
                else None
            ),
            "is_coverage": False,
        },
    }


def _confidence_diagnostics(
    modules: Sequence[dict[str, Any]],
    bundle: dict[str, Any],
    verdicts: Sequence[dict[str, Any]],
    *,
    task_contract: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Derive secondary diagnostics from the same normalized v1 verdict semantics."""

    compiled = core.compile_bundle(modules, bundle, task_contract=task_contract)
    verdict_by_id, issues = core._verdict_index(verdicts)
    selected: dict[str, Mapping[str, Any]] = {}
    for record in (
        list(compiled["domain_questions"])
        + list(compiled["hard_gates"])
        + list(compiled["supplemental_questions"])
    ):
        selected.setdefault(str(record["question"]["id"]), record)
    for group in compiled["penalty_groups"]:
        for record in group["questions"]:
            selected.setdefault(str(record["question"]["id"]), record)
    normalized = {
        question_id: core._get_verdict(record, verdict_by_id, issues)
        for question_id, record in selected.items()
    }
    effective_states = {
        question_id: str(verdict["verdict"])
        for question_id, verdict in normalized.items()
    }
    core._enforce_subjective_ladders(compiled, effective_states, issues)
    penalty_records = [
        record for group in compiled["penalty_groups"] for record in group["questions"]
    ]
    return {
        "diagnostic_version": 1,
        "status": "DESCRIPTIVE_UNCALIBRATED",
        "disclosure": (
            "Raw evaluator confidence descriptives only; they do not change canonical scores, "
            "coverage, bounds, gates, penalties, or status. Each role aggregate is "
            "effective-leaf-weighted: sum(confidence_i * effective_weight_i) / "
            "sum(effective_weight_i) across assessed leaves. Threshold shares use the same "
            "assessed effective-weight denominator. The weighted median selects the lower "
            "confidence at an exact-half tie. Legacy report.confidence is retained as a "
            "deprecated compatibility field: its domain-point-weighted formula is "
            "sum(domain_points * domain_confidence) / sum(domain_points) across assessed domains."
        ),
        "roles": {
            "domain": _role_aggregate(
                compiled["domain_questions"],
                normalized_verdicts=normalized,
                effective_states=effective_states,
            ),
            "hard_gate": _role_aggregate(
                compiled["hard_gates"],
                normalized_verdicts=normalized,
                effective_states=effective_states,
            ),
            "penalty": _role_aggregate(
                penalty_records,
                normalized_verdicts=normalized,
                effective_states=effective_states,
            ),
            "supplemental": _role_aggregate(
                compiled["supplemental_questions"],
                normalized_verdicts=normalized,
                effective_states=effective_states,
            ),
        },
        "calibration": {
            "status": "UNAVAILABLE",
            "exact_fingerprint": None,
            "reason": (
                "A single score has no polarity comparison, repeat judgments, or outcome history; "
                "no calibration inference is made."
            ),
        },
    }


def _validate_v2(report: Mapping[str, Any]) -> None:
    schema = core.load_data(schema_dir() / "hbq_score_report.v2.schema.json")
    errors = sorted(Draft202012Validator(schema).iter_errors(report), key=lambda error: list(error.path))
    if errors:
        path = ".".join(str(part) for part in errors[0].path) or "<root>"
        raise core.HBQError(f"Internal v2 score report violates its schema at {path}: {errors[0].message}")


def score_report_version(report: Mapping[str, Any]) -> int:
    """Identify a persisted score report without reinterpreting an old parent."""

    version = report.get("report_version")
    schema = report.get("$schema")
    if version is None:
        return 1
    if version == 2 and schema == V2_SCHEMA:
        _validate_v2(report)
        return 2
    raise core.HBQError(
        "Unsupported score report version/schema pair; expected an unversioned v1 report or "
        f"report_version 2 with {V2_SCHEMA!r}"
    )


def score_bundle(
    modules: Sequence[dict[str, Any]],
    bundle: dict[str, Any],
    verdicts: Sequence[dict[str, Any]],
    *,
    artifact_id: str | None = None,
    task_contract: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Produce a v2 descendant while leaving v1 scoring and evidence unchanged."""

    report = deepcopy(
        core.score_bundle(
            modules,
            bundle,
            verdicts,
            artifact_id=artifact_id,
            task_contract=task_contract,
        )
    )
    report["$schema"] = V2_SCHEMA
    report["report_version"] = 2
    report["confidence_diagnostics"] = _confidence_diagnostics(
        modules,
        bundle,
        verdicts,
        task_contract=task_contract,
    )
    _validate_v2(report)
    return report
