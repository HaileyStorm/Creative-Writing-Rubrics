import importlib.util
from pathlib import Path

import pytest
from hbqrs.core import VERDICTS


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "evaluation-results/hbq-human-alignment-dryad-full-hbq-analysis-v1/qualification_math.py"
SPEC = importlib.util.spec_from_file_location("dryad_qualification_math", SOURCE)
subject = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(subject)
QUESTION_IDS = [f"q-{number:03d}" for number in range(178)]


@pytest.mark.parametrize("when", ["before", "during"])
def test_qualification_protocol_drift_is_rejected(monkeypatch, when):
    original = Path.read_bytes
    raw = subject.QUALIFICATION_PATH.read_bytes()
    calls = []
    def changing(path):
        if path == subject.QUALIFICATION_PATH:
            calls.append(True)
            return raw + b" " if when == "before" or len(calls) > 1 else raw
        return original(path)
    monkeypatch.setattr(Path, "read_bytes", changing)
    with pytest.raises(ValueError, match="hash drift|changed during"):
        subject.evaluate_comparability(rows(), QUESTION_IDS)


def rows():
    return [
        {
            "opaque_story_id": story,
            "batch_size": size,
            "repetition": repetition,
            "verdicts": [{"question_id": question_id, "verdict": "YES"} for question_id in QUESTION_IDS],
            "score": 50,
            "coverage": 0.88,
        }
        for story in subject.COHORT
        for size in subject.SIZES
        for repetition in subject.REPETITIONS
    ]


def cell(value, story, size, repetition):
    return next(row for row in value if (row["opaque_story_id"], row["batch_size"], row["repetition"]) == (story, size, repetition))


def set_state(row, state):
    for verdict in row["verdicts"]:
        verdict["verdict"] = state


def test_literal_states_match_the_hbq_core_contract():
    assert subject.CANONICAL_VERDICTS == VERDICTS


def test_returns_all_frozen_pair_aggregates_as_exact_rationals():
    value = rows()
    story = subject.COHORT[0]
    set_state(cell(value, story, 8, 1), "YES")
    set_state(cell(value, story, 8, 2), "YES")
    set_state(cell(value, story, 8, 3), "NO")
    set_state(cell(value, story, 32, 1), "YES")
    set_state(cell(value, story, 32, 2), "NO")
    set_state(cell(value, story, 32, 3), "NO")
    result = subject.evaluate_comparability(value, QUESTION_IDS)
    first = result["stories"][0]
    assert result["evidence_class"] == "arithmetic_only"
    assert first["reference_within_disagreement"] == {"numerator": 2, "denominator": 3, "float": pytest.approx(2 / 3)}
    assert first["candidate_within_disagreement"] == {"numerator": 2, "denominator": 3, "float": pytest.approx(2 / 3)}
    assert first["cross_size_disagreement"] == {"numerator": 5, "denominator": 9, "float": pytest.approx(5 / 9)}
    assert first["cross_size_disagreement"]["float"] != pytest.approx(1 / 3)  # A favorable one-to-one pairing is forbidden.
    assert first["reference_scores"] == [{"numerator": 50, "denominator": 1, "float": 50.0}] * 3
    assert first["candidate_comparable"] is True
    assert result["overall_candidate_comparable"] is True
    assert set(result) == {"evidence_class", "qualification_sha256", "stories", "overall_candidate_comparable"}
    assert result["qualification_sha256"] == subject.QUALIFICATION_SHA256


@pytest.mark.parametrize("mutation", ["missing", "duplicate"])
def test_rejects_missing_or_duplicate_frozen_passes(mutation):
    value = rows()
    if mutation == "missing":
        value.pop()
    else:
        value[-1]["repetition"] = 2
    with pytest.raises(ValueError, match="18 passes|identity|Cartesian"):
        subject.evaluate_comparability(value, QUESTION_IDS)


@pytest.mark.parametrize("mutation", ["omission", "reorder"])
def test_rejects_question_omission_or_order_drift(mutation):
    value = rows()
    verdicts = value[0]["verdicts"]
    if mutation == "omission":
        verdicts.pop()
    else:
        verdicts[0], verdicts[1] = verdicts[1], verdicts[0]
    with pytest.raises(ValueError, match="178 verdicts|frozen order"):
        subject.evaluate_comparability(value, QUESTION_IDS)


@pytest.mark.parametrize("field, bad", [("verdict", "MAYBE"), ("score", float("nan")), ("score", True), ("coverage", 0.87)])
def test_rejects_noncanonical_or_invalid_numeric_inputs(field, bad):
    value = rows()
    if field == "verdict":
        value[0]["verdicts"][0]["verdict"] = bad
    else:
        value[0][field] = bad
    with pytest.raises(ValueError):
        subject.evaluate_comparability(value, QUESTION_IDS)


def test_candidate_instability_fails_even_when_scores_match():
    value = rows()
    story = subject.COHORT[0]
    set_state(cell(value, story, 32, 2), "NO")
    result = subject.evaluate_comparability(value, QUESTION_IDS)
    first = result["stories"][0]
    assert first["reference_within_disagreement"]["numerator"] == 0
    assert first["candidate_within_disagreement"] == {"numerator": 2, "denominator": 3, "float": pytest.approx(2 / 3)}
    assert first["candidate_comparable"] is False
    assert result["overall_candidate_comparable"] is False


@pytest.mark.parametrize("candidate_score, expected", [(55, True), (55.1, False)])
def test_score_shift_threshold_is_inclusive(candidate_score, expected):
    value = rows()
    for row in value:
        if row["batch_size"] == 32:
            row["score"] = candidate_score
    result = subject.evaluate_comparability(value, QUESTION_IDS)
    assert all(story["candidate_comparable"] is expected for story in result["stories"])
    assert result["overall_candidate_comparable"] is expected
