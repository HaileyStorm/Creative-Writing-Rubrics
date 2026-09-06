"""Pure arithmetic for the frozen Dryad batch-size qualification only.

This module validates a complete 3-story × 2-size × 3-repeat result matrix.
It deliberately makes no native-admission, metric-eligibility, or cap claim.
"""

from __future__ import annotations

from fractions import Fraction
import hashlib
import math
from pathlib import Path
from typing import Any, Sequence


COHORT = (
    "dryad-cec700bfc2d75abb112b3e05",
    "dryad-44cae24e55019e2cbf491660",
    "dryad-1fdece08b78477bd30f527f0",
)
SIZES = (8, 32)
REPETITIONS = (1, 2, 3)
QUESTION_COUNT = 178
QUALIFICATION_PATH = Path(__file__).with_name("qualification.json")
QUALIFICATION_SHA256 = "18e2b199bafdf49328402d78a7f9f7b83d408c6140acccb2e35993c046a11989"
CANONICAL_VERDICTS = {"YES", "NO", "NOT_APPLICABLE", "CANNOT_ASSESS"}
_ROW_KEYS = {"opaque_story_id", "batch_size", "repetition", "verdicts", "score", "coverage"}


def _number(value: Any, label: str) -> Fraction:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or isinstance(value, float) and not math.isfinite(value):
        raise ValueError(f"{label} must be a finite non-boolean number")
    return Fraction(str(value))


def _render(value: Fraction) -> dict[str, int | float]:
    return {"numerator": value.numerator, "denominator": value.denominator, "float": float(value)}


def _validate_question_ids(question_ids: Sequence[str]) -> tuple[str, ...]:
    if not isinstance(question_ids, (list, tuple)) or len(question_ids) != QUESTION_COUNT:
        raise ValueError("question_ids must contain exactly 178 IDs")
    ids = tuple(question_ids)
    if any(type(question_id) is not str or not question_id for question_id in ids) or len(set(ids)) != QUESTION_COUNT:
        raise ValueError("question_ids must contain 178 unique non-empty strings")
    return ids


def _validate_rows(rows: Sequence[dict[str, Any]], question_ids: tuple[str, ...]) -> dict[tuple[str, int, int], tuple[tuple[str, ...], Fraction]]:
    if not isinstance(rows, list) or len(rows) != len(COHORT) * len(SIZES) * len(REPETITIONS):
        raise ValueError("rows must contain exactly 18 passes")
    expected = {(story, size, repetition) for story in COHORT for size in SIZES for repetition in REPETITIONS}
    checked: dict[tuple[str, int, int], tuple[tuple[str, ...], Fraction]] = {}
    for row in rows:
        if not isinstance(row, dict) or set(row) != _ROW_KEYS:
            raise ValueError("each row must contain only the frozen qualification fields")
        story, size, repetition = row["opaque_story_id"], row["batch_size"], row["repetition"]
        identity = (story, size, repetition)
        if type(story) is not str or type(size) is not int or type(repetition) is not int or identity not in expected or identity in checked:
            raise ValueError("row identity is not one frozen story/size/repetition cell")
        score = _number(row["score"], "score")
        coverage = _number(row["coverage"], "coverage")
        if not Fraction(0) <= score <= 100 or not Fraction(22, 25) <= coverage <= 1:
            raise ValueError("score or coverage is outside the frozen qualification bounds")
        verdicts = row["verdicts"]
        if not isinstance(verdicts, list) or len(verdicts) != QUESTION_COUNT:
            raise ValueError("every pass must contain exactly 178 verdicts")
        actual_ids: list[str] = []
        states: list[str] = []
        for verdict in verdicts:
            if not isinstance(verdict, dict) or set(verdict) != {"question_id", "verdict"}:
                raise ValueError("each verdict must be a question_id/verdict pair")
            question_id, state = verdict["question_id"], verdict["verdict"]
            if type(question_id) is not str or type(state) is not str or state not in CANONICAL_VERDICTS:
                raise ValueError("verdict has an invalid question ID or canonical state")
            actual_ids.append(question_id)
            states.append(state)
        if tuple(actual_ids) != question_ids:
            raise ValueError("verdict question IDs must exactly match the frozen order")
        checked[identity] = (tuple(states), score)
    if set(checked) != expected:
        raise ValueError("pass inventory is not the complete frozen Cartesian matrix")
    return checked


def _disagreement(left: tuple[str, ...], right: tuple[str, ...]) -> Fraction:
    return Fraction(sum(a != b for a, b in zip(left, right)), QUESTION_COUNT)


def _mean(values: Sequence[Fraction]) -> Fraction:
    return sum(values, Fraction()) / len(values)


def evaluate_comparability(rows: list[dict[str, Any]], question_ids: Sequence[str]) -> dict[str, Any]:
    """Evaluate only the preregistered arithmetic comparability tolerances.

    The return value contains exact rational components and float renderings.
    It does not establish native admission, metric eligibility, or any cap.
    """
    qualification_raw = QUALIFICATION_PATH.read_bytes()
    if hashlib.sha256(qualification_raw).hexdigest() != QUALIFICATION_SHA256:
        raise ValueError("Frozen qualification protocol hash drift")
    ids = _validate_question_ids(question_ids)
    cells = _validate_rows(rows, ids)
    stories: list[dict[str, Any]] = []
    all_comparable = True
    for story in COHORT:
        reference = [cells[(story, 8, repetition)] for repetition in REPETITIONS]
        candidate = [cells[(story, 32, repetition)] for repetition in REPETITIONS]
        reference_within = _mean([_disagreement(reference[0][0], reference[1][0]), _disagreement(reference[0][0], reference[2][0]), _disagreement(reference[1][0], reference[2][0])])
        candidate_within = _mean([_disagreement(candidate[0][0], candidate[1][0]), _disagreement(candidate[0][0], candidate[2][0]), _disagreement(candidate[1][0], candidate[2][0])])
        cross = _mean([_disagreement(left[0], right[0]) for left in reference for right in candidate])
        reference_scores = [value[1] for value in reference]
        candidate_scores = [value[1] for value in candidate]
        shift = abs(_mean(reference_scores) - _mean(candidate_scores))
        comparable = cross <= reference_within + Fraction(1, 20) and candidate_within <= reference_within + Fraction(1, 20) and shift <= 5
        all_comparable = all_comparable and comparable
        stories.append({
            "opaque_story_id": story,
            "reference_within_disagreement": _render(reference_within),
            "candidate_within_disagreement": _render(candidate_within),
            "cross_size_disagreement": _render(cross),
            "score_shift": _render(shift),
            "reference_scores": [_render(value) for value in reference_scores],
            "candidate_scores": [_render(value) for value in candidate_scores],
            "candidate_comparable": comparable,
        })
    if QUALIFICATION_PATH.read_bytes() != qualification_raw:
        raise ValueError("Qualification protocol changed during arithmetic")
    return {"evidence_class": "arithmetic_only", "qualification_sha256": QUALIFICATION_SHA256,
            "stories": stories, "overall_candidate_comparable": all_comparable}
