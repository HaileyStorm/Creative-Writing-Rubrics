"""Pure frozen-target rank arithmetic for Dryad TRAIN and DEV only.

This module neither loads targets nor admits native results.  Its outputs are
descriptive comparisons, not accuracy, promotion, or confirmation claims.
"""

from __future__ import annotations

from fractions import Fraction
import hashlib
import math
from pathlib import Path
import random
from typing import Any, Sequence


AXES = (
    "novel", "original", "rare", "appropriate", "feasible", "publishable",
    "well_written", "enjoyed", "boring", "funny", "twist", "future",
)
CO_PRIMARY = ("novelty", "usefulness")
DEV_COUNT = 60
BOOTSTRAP_REPLICATES = 2000
BOOTSTRAP_SEED = 20260905
PROTOCOL_PATH = Path(__file__).resolve().with_name("protocol.json")
PROTOCOL_SHA256 = "a0e2412be904a2fa89b200dbe734cdd42508c6ec40edf621a02f1c1cbd02272d"


def _protocol() -> bytes:
    raw = PROTOCOL_PATH.read_bytes()
    if hashlib.sha256(raw).hexdigest() != PROTOCOL_SHA256:
        raise ValueError("Analysis protocol hash drift")
    return raw


def _finish(result: dict[str, Any], protocol_raw: bytes) -> dict[str, Any]:
    if PROTOCOL_PATH.read_bytes() != protocol_raw:
        raise ValueError("Analysis protocol changed during calculation")
    return {**result, "protocol_sha256": PROTOCOL_SHA256}


class UndefinedCorrelation(ValueError):
    """A tie-only rank vector cannot yield a Spearman correlation."""


def _fraction(value: Any, label: str) -> Fraction:
    if not isinstance(value, dict) or set(value) != {"numerator", "denominator"}:
        raise ValueError(f"{label} must be an exact rational object")
    numerator, denominator = value["numerator"], value["denominator"]
    if type(numerator) is not int or type(denominator) is not int or denominator == 0:
        raise ValueError(f"{label} has an invalid exact rational value")
    return Fraction(numerator, denominator)


def _score(value: Any) -> Fraction:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or isinstance(value, float) and not math.isfinite(value):
        raise ValueError("score must be a finite non-boolean number")
    result = Fraction(str(value))
    if not 0 <= result <= 100:
        raise ValueError("score is outside the pinned 0..100 scale")
    return result


def _rank_number(value: Any, label: str) -> Fraction:
    if isinstance(value, bool) or not isinstance(value, (Fraction, int, float)):
        raise ValueError(f"{label} must be a finite non-boolean number")
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError(f"{label} must be a finite non-boolean number")
    return value if isinstance(value, Fraction) else Fraction(str(value))


def _coverage(value: Any) -> Fraction:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or isinstance(value, float) and not math.isfinite(value):
        raise ValueError("coverage must be a finite non-boolean number")
    result = Fraction(str(value))
    if not Fraction(22, 25) <= result <= 1:
        raise ValueError("coverage is outside the pinned 0.88..1 range")
    return result


def _render(value: Fraction) -> dict[str, int | float]:
    return {"numerator": value.numerator, "denominator": value.denominator, "float": float(value)}


def _ranks(values: Sequence[Fraction]) -> list[Fraction]:
    if not values:
        raise ValueError("rank input is empty")
    ranked = sorted(enumerate(values), key=lambda item: item[1])
    result = [Fraction()] * len(values)
    start = 0
    while start < len(ranked):
        end = start + 1
        while end < len(ranked) and ranked[end][1] == ranked[start][1]:
            end += 1
        rank = Fraction(start + 1 + end, 2)
        for index, _ in ranked[start:end]:
            result[index] = rank
        start = end
    return result


def _spearman(scores: Sequence[Fraction], targets: Sequence[Fraction]) -> dict[str, Any]:
    if len(scores) != len(targets) or len(scores) < 2:
        raise ValueError("Spearman inputs must have the same length of at least two")
    score_ranks, target_ranks = _ranks(scores), _ranks(targets)
    center = Fraction(len(scores) + 1, 2)
    numerator = sum((score - center) * (target - center) for score, target in zip(score_ranks, target_ranks))
    score_squares = sum((score - center) ** 2 for score in score_ranks)
    target_squares = sum((target - center) ** 2 for target in target_ranks)
    if not score_squares or not target_squares:
        raise UndefinedCorrelation("Spearman correlation is undefined for a constant rank vector")
    return {
        "rho": float(numerator) / math.sqrt(float(score_squares) * float(target_squares)),
        "rank_covariance_numerator": _render(numerator),
        "score_rank_sum_squares": _render(score_squares),
        "target_rank_sum_squares": _render(target_squares),
    }


def spearman(values: Sequence[Fraction | int | float], targets: Sequence[Fraction | int | float]) -> float | None:
    """Return average-tie Spearman rho, or ``None`` for a constant rank vector."""
    if not isinstance(values, (list, tuple)) or not isinstance(targets, (list, tuple)):
        raise ValueError("Spearman inputs must be lists or tuples")
    try:
        return _spearman([_rank_number(value, "value") for value in values], [_rank_number(target, "target") for target in targets])["rho"]
    except UndefinedCorrelation:
        return None


def _targets(target_rows: Sequence[dict[str, Any]]) -> tuple[str, list[tuple[str, dict[str, Fraction]]]]:
    if not isinstance(target_rows, list) or not target_rows:
        raise ValueError("target_rows must be a non-empty list")
    result: list[tuple[str, dict[str, Fraction]]] = []
    seen: set[str] = set()
    partition: str | None = None
    for row in target_rows:
        if not isinstance(row, dict) or set(row) != {"opaque_story_id", "partition", "rating_count", "axis_means", "indices"}:
            raise ValueError("target row does not match the frozen target format")
        story, current_partition, rating_count = row["opaque_story_id"], row["partition"], row["rating_count"]
        if type(story) is not str or not story or story in seen or current_partition not in {"TRAIN", "DEV"} or type(rating_count) is not int or rating_count < 1:
            raise ValueError("target identity or partition is invalid")
        if partition is None:
            partition = current_partition
        elif partition != current_partition:
            raise ValueError("target rows must belong to one partition")
        axis_means, indices = row["axis_means"], row["indices"]
        if not isinstance(axis_means, dict) or set(axis_means) != set(AXES) or not isinstance(indices, dict) or set(indices) != set(CO_PRIMARY):
            raise ValueError("target dimensions do not match the frozen protocol")
        values = {name: _fraction(axis_means[name], f"axis_means.{name}") for name in AXES}
        values.update({name: _fraction(indices[name], f"indices.{name}") for name in CO_PRIMARY})
        if any(not 1 <= value <= 9 for value in values.values()):
            raise ValueError("target value is outside the source rating scale")
        seen.add(story)
        result.append((story, values))
    if len(result) != {"TRAIN": 176, "DEV": 60}[partition]:
        raise ValueError("Target partition count differs from frozen protocol")
    return partition or "", sorted(result)


def _scores(score_rows: Sequence[dict[str, Any]]) -> dict[str, Fraction]:
    if not isinstance(score_rows, list) or not score_rows:
        raise ValueError("score_rows must be a non-empty list")
    result: dict[str, Fraction] = {}
    for row in score_rows:
        if not isinstance(row, dict) or set(row) != {"opaque_story_id", "score", "coverage"}:
            raise ValueError("score row must contain only opaque_story_id, score, and coverage")
        story = row["opaque_story_id"]
        if type(story) is not str or not story or story in result:
            raise ValueError("score identity is invalid or duplicated")
        result[story] = _score(row["score"])
        _coverage(row["coverage"])
    return result


def _aligned(score_rows: Sequence[dict[str, Any]], target_rows: Sequence[dict[str, Any]]) -> tuple[str, list[tuple[str, Fraction, dict[str, Fraction]]]]:
    partition, targets = _targets(target_rows)
    scores = _scores(score_rows)
    target_ids = {story for story, _ in targets}
    if set(scores) != target_ids:
        raise ValueError("score and target identities must match exactly")
    return partition, [(story, scores[story], values) for story, values in targets]


def _analysis(partition: str, rows: Sequence[tuple[str, Fraction, dict[str, Fraction]]]) -> dict[str, Any]:
    scores = [row[1] for row in rows]
    def correlation(name: str) -> dict[str, Any]:
        return _spearman(scores, [row[2][name] for row in rows])
    return {
        "partition": partition,
        "item_count": len(rows),
        "rank_method": "average_ties_one_based",
        "co_primary": {name: correlation(name) for name in CO_PRIMARY},
        "raw_axes": {name: correlation(name) for name in AXES},
    }


def analyze_scores(score_rows: list[dict[str, Any]], target_rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Calculate exact-rank Spearman summaries for one frozen open partition."""
    protocol_raw = _protocol()
    partition, rows = _aligned(score_rows, target_rows)
    return _finish(_analysis(partition, rows), protocol_raw)


def _bootstrap(baseline: Sequence[tuple[str, Fraction, dict[str, Fraction]]], candidate: Sequence[tuple[str, Fraction, dict[str, Fraction]]]) -> dict[str, Any]:
    generator = random.Random(BOOTSTRAP_SEED)
    deltas: list[float] = []
    undefined = 0
    for _ in range(BOOTSTRAP_REPLICATES):
        indices = [generator.randrange(DEV_COUNT) for _ in range(DEV_COUNT)]
        try:
            differences = [
                _spearman([candidate[index][1] for index in indices], [candidate[index][2][name] for index in indices])["rho"]
                - _spearman([baseline[index][1] for index in indices], [baseline[index][2][name] for index in indices])["rho"]
                for name in CO_PRIMARY
            ]
        except UndefinedCorrelation:
            undefined += 1
        else:
            deltas.append(sum(differences) / len(differences))
    lower_bound: float | None = None
    if not undefined:
        ordered = sorted(deltas)
        position = Fraction((len(ordered) - 1), 40)
        lower, remainder = divmod(position.numerator, position.denominator)
        upper = lower if not remainder else lower + 1
        weight = Fraction(remainder, position.denominator)
        lower_bound = ordered[lower] + float(weight) * (ordered[upper] - ordered[lower])
    return {
        "replicates": BOOTSTRAP_REPLICATES,
        "seed": BOOTSTRAP_SEED,
        "sample_size": DEV_COUNT,
        "lower_bound_percentile": 2.5,
        "quantile_method": "linear_interpolation_at_(n-1)*0.025",
        "undefined_replicates": undefined,
        "lower_bound_mean_co_primary_delta": lower_bound,
        "gain_gate_passed": undefined == 0 and lower_bound is not None and lower_bound > 0,
    }


def compare_dev(baseline_scores: list[dict[str, Any]], candidate_scores: list[dict[str, Any]], targets: list[dict[str, Any]]) -> dict[str, Any]:
    """Apply the frozen 60-story DEV comparison and paired bootstrap gate."""
    protocol_raw = _protocol()
    partition, baseline = _aligned(baseline_scores, targets)
    candidate_partition, candidate = _aligned(candidate_scores, targets)
    if partition != "DEV" or candidate_partition != "DEV" or len(baseline) != DEV_COUNT or [row[0] for row in baseline] != [row[0] for row in candidate]:
        raise ValueError("DEV comparison requires exactly 60 matching unique DEV stories")
    baseline_analysis, candidate_analysis = _analysis(partition, baseline), _analysis(candidate_partition, candidate)
    deltas = {name: candidate_analysis["co_primary"][name]["rho"] - baseline_analysis["co_primary"][name]["rho"] for name in CO_PRIMARY}
    mean_delta = sum(deltas.values()) / len(deltas)
    dev_rule = all(value >= 0 for value in deltas.values()) and mean_delta > 0
    bootstrap = _bootstrap(baseline, candidate)
    bootstrap["gain_gate_passed"] = dev_rule and bootstrap["gain_gate_passed"]
    return _finish({
        "baseline": baseline_analysis,
        "candidate": candidate_analysis,
        "co_primary_deltas": deltas,
        "mean_co_primary_delta": mean_delta,
        "dev_rule_passed": dev_rule,
        "bootstrap": bootstrap,
        "candidate_retained": dev_rule and bootstrap["gain_gate_passed"],
    }, protocol_raw)
