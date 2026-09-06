from __future__ import annotations

import copy
import importlib.util
from fractions import Fraction
from pathlib import Path
from types import SimpleNamespace

import pytest

from hbqrs import materialize_weight_profile, resolve_bundle


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "evaluation-results/hbq-human-alignment-dryad-full-hbq-analysis-v1/optimizer.py"
SPEC = importlib.util.spec_from_file_location("dryad_optimizer", SOURCE)
subject = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(subject)
AXES = ("novel", "original", "rare", "appropriate", "feasible", "publishable", "well_written", "enjoyed", "boring", "funny", "twist", "future")


def _fraction(value: Fraction) -> dict[str, int]:
    return {"numerator": value.numerator, "denominator": value.denominator}


def _data() -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    targets: list[dict[str, object]] = []
    verdict_rows: list[dict[str, object]] = []
    states = ("YES", "NO", "NOT_APPLICABLE", "CANNOT_ASSESS")
    for story_number in range(subject.TRAIN_COUNT):
        means = {axis: Fraction((story_number * (1, 2, 4, 5, 7, 8)[axis_number % 6] + axis_number) % 9 + 1) for axis_number, axis in enumerate(AXES)}
        targets.append({
            "opaque_story_id": f"story-{story_number:03d}",
            "partition": "TRAIN",
            "rating_count": 1,
            "axis_means": {axis: _fraction(value) for axis, value in means.items()},
            "indices": {
                "novelty": _fraction(sum((means[axis] for axis in AXES[:3]), Fraction()) / 3),
                "usefulness": _fraction(sum((means[axis] for axis in AXES[3:6]), Fraction()) / 3),
            },
        })
        verdicts = []
        for question_number in range(subject.QUESTION_COUNT):
            domain = question_number % len(subject.DOMAIN_ORDER)
            signal = (story_number * (domain + 2) + question_number) % 11
            verdict = "YES" if signal < 4 else states[signal % len(states)]
            verdicts.append({"question_id": f"question-{question_number:03d}", "verdict": verdict})
        verdict_rows.append({"opaque_story_id": f"story-{story_number:03d}", "verdicts": verdicts})
    return verdict_rows, targets


class SyntheticWeights:
    def materialize_weight_profile(self, modules, bundle, profile):
        assert set(profile) == {"profile_version", "profile_id", "bundle_id", "domain_weights"}
        assert profile["bundle_id"] == "prose.short_story"
        requested = profile["domain_weights"]
        assert [row["domain_id"] for row in requested] == list(subject.DOMAIN_ORDER)
        total = sum(row["weight"] for row in requested)
        domains = [{"domain_id": row["domain_id"], "points": row["weight"] * 100 / total} for row in requested]
        audit = {
            "requested": copy.deepcopy(profile),
            "effective": {"domain_weights": [{"domain_id": row["domain_id"], "effective_points": row["points"]} for row in domains]},
        }
        return modules, {"bundle_id": "prose.short_story", "domains": domains}, audit


class SyntheticCore:
    VERDICTS = subject.CANONICAL_VERDICTS

    def __init__(self, fault_after: int | None = None) -> None:
        self.calls = 0
        self.fault_after = fault_after

    def score_bundle(self, _modules, bundle, verdicts, *, artifact_id, task_contract):
        assert task_contract is None
        self.calls += 1
        points = [domain["points"] for domain in bundle["domains"]]
        rates = [
            sum(record["verdict"] == "YES" for record in verdicts[index::len(points)]) / len(verdicts[index::len(points)])
            for index in range(len(points))
        ]
        observed = sum(point * rate for point, rate in zip(points, rates))
        result = {"final_score": {"observed": observed}, "coverage": 1.0, "artifact_id": artifact_id}
        if self.fault_after is not None and self.calls > self.fault_after:
            result["unexpected_replay_metadata"] = True
        return result


def _runtime(core: SyntheticCore) -> SimpleNamespace:
    return SimpleNamespace(
        questions=[{"question": {"id": f"question-{number:03d}"}} for number in range(subject.QUESTION_COUNT)],
        core=core,
        weights=SyntheticWeights(),
        modules=[],
        bundle={"bundle_id": "prose.short_story", "domains": [{"domain_id": domain, "points": float(point)} for domain, point in zip(subject.DOMAIN_ORDER, subject.CANONICAL_POINTS)]},
        verify=lambda: None,
    )


def test_full_frozen_train_fit_replays_all_trials_without_dev():
    verdicts, targets = _data()
    result = subject.fit_train(verdicts, targets, runtime=_runtime(SyntheticCore()), expected_optimizer_sha256=subject._sha(SOURCE.read_bytes()))
    assert result["evidence_class"] == "synthetic_fit_no_authority"
    assert result["identity"]["optimizer_sha256"] == subject._sha(SOURCE.read_bytes())
    assert set(result["input_commitments"]) == {"verdict_rows_sha256", "target_rows_sha256"}
    assert result["identity"]["runtime_source"] == "caller_supplied_test_runtime_no_authority"
    assert result["trial_count"] == 128
    assert result["trial_records"][0]["trial_number"] == 0
    assert result["trial_records"][0]["multipliers"] == [1.0] * len(subject.DOMAIN_ORDER)
    assert result["trial_records"][0]["canonical_points_reproduced"] is True
    assert all(record["independent_recompute_match"] for record in result["trial_records"])
    assert all(record["analysis"]["partition"] == "TRAIN" for record in result["trial_records"])
    for record in result["trial_records"]:
        assert set(record["profile"]) == {"profile_version", "profile_id", "bundle_id", "domain_weights"}
        assert [row["weight"] for row in record["profile"]["domain_weights"]] == [point * multiplier for point, multiplier in zip(subject.CANONICAL_POINTS, record["multipliers"])]
        assert len(record["score_hashes"]) == subject.TRAIN_COUNT
        assert set(record["analysis"]["co_primary"]) == {"novelty", "usefulness"}
        assert set(record["analysis"]["raw_axes"]) == set(AXES)


def test_sampling_failure_preserves_attempt_when_postcheck_also_fails(monkeypatch):
    verdicts, targets = _data()
    runtime = _runtime(SyntheticCore())
    calls = []
    def verify():
        calls.append(True)
        if len(calls) > 1:
            raise ValueError("postcheck fixture")
    runtime.verify = verify
    def fail(*args, **kwargs):
        raise RuntimeError("sampling fixture")
    monkeypatch.setattr(subject.optuna.Trial, "suggest_categorical", fail)
    with pytest.raises(subject.OptimizationAborted) as caught:
        subject.fit_train(verdicts, targets, runtime=runtime, expected_optimizer_sha256=subject._sha(SOURCE.read_bytes()))
    assert len(caught.value.attempted_trials) == 1
    assert caught.value.attempted_trials[0]["state"] == "failed"
    assert caught.value.attempted_trials[0]["multipliers"] == []
    assert caught.value.postcheck_failure == "ValueError"


def test_unreviewed_optimizer_identity_rejected():
    verdicts, targets = _data()
    with pytest.raises(ValueError, match="Reviewed optimizer"):
        subject.fit_train(verdicts, targets, runtime=_runtime(SyntheticCore()), expected_optimizer_sha256="0" * 64)


def test_winner_tie_order_prefers_simplest_then_vector_then_trial_number():
    records = [
        {"trial_number": 8, "multipliers": [2.0] * 9, "objective": 0.5},
        {"trial_number": 7, "multipliers": [1.0] * 9, "objective": 0.5},
        {"trial_number": 3, "multipliers": [1.0] * 9, "objective": 0.5},
        {"trial_number": 2, "multipliers": [0.5] + [1.0] * 8, "objective": 0.5},
    ]
    assert subject._winner(records)["trial_number"] == 3


def test_actual_materializer_receives_only_nine_domain_point_overrides(modules, bundles):
    profile = subject._profile((0.5, 1.0, 2.0, 0.5, 1.0, 2.0, 0.5, 1.0, 2.0))
    bundle = resolve_bundle(bundles, "prose.short_story")
    _, materialized, audit = materialize_weight_profile(modules, bundle, profile)
    assert set(profile) == {"profile_version", "profile_id", "bundle_id", "domain_weights"}
    assert [record["domain_id"] for record in profile["domain_weights"]] == list(subject.DOMAIN_ORDER)
    assert [record["weight"] for record in profile["domain_weights"]] == [point * multiplier for point, multiplier in zip(subject.CANONICAL_POINTS, (0.5, 1.0, 2.0, 0.5, 1.0, 2.0, 0.5, 1.0, 2.0))]
    assert len(audit["effective"]["domain_weights"]) == 9
    assert all(not audit["effective"][name] for name in ("component_weights", "group_weights", "question_weights", "penalty_caps"))
    assert sum(domain["points"] for domain in materialized["domains"]) == pytest.approx(100)


@pytest.mark.parametrize("mutation", ["175", "dev", "missing", "unknown"])
def test_fit_rejects_malformed_or_non_train_inputs_before_optimization(mutation):
    verdicts, targets = _data()
    if mutation == "175":
        verdicts.pop()
    elif mutation == "dev":
        for target in targets:
            target["partition"] = "DEV"
    elif mutation == "missing":
        verdicts[0]["verdicts"].pop()
    else:
        verdicts[0]["verdicts"][0]["verdict"] = "MAYBE"
    with pytest.raises(ValueError):
        subject.fit_train(verdicts, targets, runtime=_runtime(SyntheticCore()), expected_optimizer_sha256=subject._sha(SOURCE.read_bytes()))


def test_replay_fault_aborts_with_all_attempted_trial_records():
    verdicts, targets = _data()
    core = SyntheticCore(fault_after=128 * subject.TRAIN_COUNT)
    with pytest.raises(subject.OptimizationAborted, match="recomputation") as raised:
        subject.fit_train(verdicts, targets, runtime=_runtime(core), expected_optimizer_sha256=subject._sha(SOURCE.read_bytes()))
    attempted = raised.value.attempted_trials
    assert len(attempted) == 128
    assert all("state" not in record for record in attempted)
    assert core.calls > 128 * subject.TRAIN_COUNT
