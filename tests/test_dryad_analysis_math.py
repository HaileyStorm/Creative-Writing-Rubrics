import importlib.util
import math
import random
from fractions import Fraction
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "evaluation-results/hbq-human-alignment-dryad-full-hbq-analysis-v1/analysis_math.py"
SPEC = importlib.util.spec_from_file_location("dryad_analysis_math_test_subject", SOURCE)
subject = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(subject)
AXES = ("novel", "original", "rare", "appropriate", "feasible", "publishable", "well_written", "enjoyed", "boring", "funny", "twist", "future")


def rational(value):
    value = Fraction(value)
    return {"numerator": value.numerator, "denominator": value.denominator}


def fixture_rows(binary=False):
    scores, targets = [], []
    for i in range(60):
        value = Fraction(2 + (i == 59)) if binary else Fraction(20 + i, 10)
        story = f"story-{i:02d}"
        scores.append({"opaque_story_id": story, "score": float(value * 10), "coverage": 1.0})
        targets.append({"opaque_story_id": story, "partition": "DEV", "rating_count": 10,
                        "axis_means": {axis: rational(9 - value if axis == "boring" else value) for axis in AXES},
                        "indices": {name: rational(value) for name in ("novelty", "usefulness")}})
    return scores, targets


def reference_rho(xs, ys):
    # Pairwise less/equal counts provide an independent quadratic average-rank oracle.
    def ranks(values):
        return [1 + sum(other < value for other in values) + (sum(other == value for other in values) - 1) / 2 for value in values]
    x, y = ranks(xs), ranks(ys)
    center = (len(x) + 1) / 2
    covariance = sum((a - center) * (b - center) for a, b in zip(x, y))
    denominator = math.sqrt(sum((a - center) ** 2 for a in x) * sum((b - center) ** 2 for b in y))
    return covariance / denominator if denominator else None


def test_exact_ties_against_independent_rank_oracle():
    rng = random.Random(19)
    for _ in range(40):
        xs = [Fraction(rng.randrange(7), 3) for _ in range(30)]
        ys = [Fraction(rng.randrange(5), 7) for _ in range(30)]
        assert subject.spearman(xs, ys) == pytest.approx(reference_rho(xs, ys), abs=1e-14)
    assert subject.spearman([1, 1], [1, 2]) is None
    assert subject.spearman([Fraction(10**20), Fraction(10**20 + 1)], [1, 2]) == 1


def test_raw_axes_preserve_boring_direction_and_id_alignment():
    scores, targets = fixture_rows()
    result = subject.analyze_scores(list(reversed(scores)), targets)
    assert result["co_primary"]["novelty"]["rho"] == 1
    assert result["co_primary"]["usefulness"]["rho"] == 1
    assert set(result["raw_axes"]) == set(AXES)
    assert result["raw_axes"]["boring"]["rho"] == -1
    assert result["protocol_sha256"] == subject.PROTOCOL_SHA256


def test_improvement_passes_both_primary_and_bootstrap_gates():
    candidate, targets = fixture_rows()
    baseline = [{**row, "score": 100 - row["score"]} for row in candidate]
    result = subject.compare_dev(baseline, candidate, targets)
    assert result["candidate_retained"] is True
    assert result["co_primary_deltas"] == {"novelty": 2, "usefulness": 2}
    assert result["bootstrap"]["replicates"] == 2000
    assert result["bootstrap"]["undefined_replicates"] == 0
    assert result["bootstrap"]["lower_bound_mean_co_primary_delta"] == 2


def test_undefined_bootstrap_replicates_are_counted_without_redraw():
    scores, targets = fixture_rows(binary=True)
    result = subject.compare_dev(scores, scores, targets)
    rng = random.Random(20260905)
    undefined = sum(len({rng.randrange(60) == 59 for _ in range(60)}) == 1 for _ in range(2000))
    assert result["bootstrap"]["undefined_replicates"] == undefined > 0
    assert result["bootstrap"]["lower_bound_mean_co_primary_delta"] is None
    assert result["candidate_retained"] is False


def test_positive_mean_cannot_hide_one_primary_regression():
    candidate, targets = fixture_rows()
    baseline = [{**row, "score": 100 - row["score"]} for row in candidate]
    for i, row in enumerate(targets):
        value = rational(Fraction(20 + (i + 30) % 60, 10))
        row["indices"]["usefulness"] = value
        for axis in ("appropriate", "feasible", "publishable"):
            row["axis_means"][axis] = value
    result = subject.compare_dev(baseline, candidate, targets)
    assert result["mean_co_primary_delta"] > 0
    assert result["co_primary_deltas"]["usefulness"] < 0
    assert result["bootstrap"]["gain_gate_passed"] is False
    assert result["candidate_retained"] is False


@pytest.mark.parametrize("kind", ["duplicate", "missing", "nonfinite", "coverage", "confirmation"])
def test_invalid_or_closed_inputs_fail(kind):
    scores, targets = fixture_rows()
    if kind == "duplicate":
        scores[-1] = dict(scores[0])
    elif kind == "missing":
        scores.pop()
    elif kind == "nonfinite":
        scores[0]["score"] = float("nan")
    elif kind == "coverage":
        scores[0]["coverage"] = 0.87
    else:
        targets[0]["partition"] = "CONFIRMATION"
    with pytest.raises(ValueError):
        subject.compare_dev(scores, scores, targets)


@pytest.mark.parametrize("partition,count", [("DEV", 59), ("TRAIN", 175)])
def test_descriptive_analysis_cannot_select_a_subset(partition, count):
    scores, targets = fixture_rows()
    selected_scores, selected_targets = [], []
    for i in range(count):
        story = f"subset-{i:03d}"
        selected_scores.append({**scores[i % 60], "opaque_story_id": story})
        selected_targets.append({**targets[i % 60], "opaque_story_id": story, "partition": partition})
    with pytest.raises(ValueError, match="partition count"):
        subject.analyze_scores(selected_scores, selected_targets)


@pytest.mark.parametrize("when", ["before", "during"])
def test_protocol_drift_is_rejected(monkeypatch, when):
    scores, targets = fixture_rows()
    original = Path.read_bytes
    reads = []
    def changed(path):
        raw = original(path)
        if path == subject.PROTOCOL_PATH:
            reads.append(True)
            if when == "before" or len(reads) > 1:
                return raw + b" "
        return raw
    monkeypatch.setattr(Path, "read_bytes", changed)
    with pytest.raises(ValueError, match="protocol"):
        subject.analyze_scores(scores, targets)
