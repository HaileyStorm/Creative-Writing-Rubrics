"""Synthetic selected100 coverage for the amended 70/30 math adapter."""

from __future__ import annotations

import copy
import importlib.util
import json
from fractions import Fraction
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "evaluation-results/hbq-human-alignment-dryad-full-hbq-analysis-v1/baseline_selected_analysis_runtime.py"
AXES = ("novel", "original", "rare", "appropriate", "feasible", "publishable", "well_written", "enjoyed", "boring", "funny", "twist", "future")


def _load():
    spec = importlib.util.spec_from_file_location("dryad_selected100_runtime_test", SOURCE)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _fraction(value: Fraction) -> dict[str, int]:
    return {"numerator": value.numerator, "denominator": value.denominator}


def _selection(subject):
    return {
        "schema_version": 1,
        "selected_schedule_sha256": "a" * 64,
        "selected_schedule_source_sha256": "b" * 64,
        "TRAIN": [f"train-{number:03d}" for number in range(subject.TRAIN_COUNT)],
        "DEV": [f"dev-{number:03d}" for number in range(subject.DEV_COUNT)],
    }


def _rows(subject, partition: str, count: int):
    verdict_rows = []
    target_rows = []
    states = ("YES", "NO", "NOT_APPLICABLE", "CANNOT_ASSESS")
    for story_number in range(count):
        story = f"{partition.lower()}-{story_number:03d}"
        means = {
            axis: Fraction((story_number * (1, 2, 4, 5, 7, 8)[axis_number % 6] + axis_number) % 9 + 1)
            for axis_number, axis in enumerate(AXES)
        }
        target_rows.append({
            "opaque_story_id": story,
            "partition": partition,
            "rating_count": 1,
            "axis_means": {axis: _fraction(value) for axis, value in means.items()},
            "indices": {
                "novelty": _fraction(sum((means[axis] for axis in AXES[:3]), Fraction()) / 3),
                "usefulness": _fraction(sum((means[axis] for axis in AXES[3:6]), Fraction()) / 3),
            },
        })
        verdicts = []
        for question_number in range(subject.QUESTION_COUNT):
            domain = question_number % 9
            signal = (story_number * (domain + 2) + question_number) % 11
            verdicts.append({"question_id": f"question-{question_number:03d}",
                             "verdict": "YES" if signal < 4 else states[signal % len(states)]})
        verdict_rows.append({"opaque_story_id": story, "verdicts": verdicts})
    return verdict_rows, target_rows


class _Weights:
    def __init__(self, profiles):
        self.profiles = profiles

    def materialize_weight_profile(self, modules, bundle, profile):
        self.profiles.append(copy.deepcopy(profile))
        if profile is None:
            return copy.deepcopy(modules), copy.deepcopy(bundle), {"identity": True, "requested": None}
        requested = profile["domain_weights"]
        total = sum(row["weight"] for row in requested)
        domains = [{"domain_id": row["domain_id"], "points": row["weight"] * 100 / total} for row in requested]
        return modules, {"bundle_id": "prose.short_story", "domains": domains}, {"requested": copy.deepcopy(profile)}


class _Core:
    VERDICTS = frozenset({"YES", "NO", "NOT_APPLICABLE", "CANNOT_ASSESS"})

    def __init__(self, coverage=1.0, fault_after=None):
        self.calls = 0
        self.coverage = coverage
        self.fault_after = fault_after

    def score_bundle(self, _modules, bundle, verdicts, *, artifact_id, task_contract):
        assert task_contract is None
        self.calls += 1
        if self.fault_after is not None and self.calls > self.fault_after:
            raise RuntimeError("synthetic scoring fault")
        points = [domain["points"] for domain in bundle["domains"]]
        rates = [sum(row["verdict"] == "YES" for row in verdicts[index::len(points)]) / len(verdicts[index::len(points)])
                 for index in range(len(points))]
        return {"final_score": {"observed": sum(point * rate for point, rate in zip(points, rates))},
                "coverage": self.coverage, "artifact_id": artifact_id}


def _runtime(subject, core=None, profiles=None):
    profiles = [] if profiles is None else profiles
    return SimpleNamespace(
        questions=[{"question": {"id": f"question-{number:03d}"}} for number in range(subject.QUESTION_COUNT)],
        core=core or _Core(), weights=_Weights(profiles), modules=[],
        bundle={"bundle_id": "prose.short_story", "domains": [
            {"domain_id": domain, "points": float(point)}
            for domain, point in zip(("task", "character", "movement", "language", "setting", "effect", "fresh", "mechanics", "holistic"),
                                     (8, 15, 19, 16, 9, 10, 10, 5, 8))]},
        verify=lambda: None,
    )


@pytest.fixture(scope="module")
def selected_fit():
    subject = _load()
    selection = _selection(subject)
    verdicts, targets = _rows(subject, "TRAIN", subject.TRAIN_COUNT)
    runtime = _runtime(subject)
    fit = subject.fit_train(verdicts, targets, selection_binding=selection,
                            expected_successor_sha256=subject._sha(SOURCE.read_bytes()), runtime=runtime)
    return subject, selection, verdicts, targets, fit


def _fit_raw(fit):
    return json.dumps(fit, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def test_selected70_fit_replays_all_trials_and_binds_exact_id_schedule(selected_fit):
    subject, selection, verdicts, targets, fit = selected_fit
    assert fit["evidence_class"] == "selected100_synthetic_fit_no_authority"
    assert fit["identity"]["selection_binding"] == selection
    assert [item["global"] for item in fit["identity"]["overrides"]] == ["DEV_COUNT", "TRAIN_COUNT", "DEV_COUNT"]
    assert fit["trial_count"] == 128
    assert fit["trial_records"][0]["multipliers"] == [1.0] * 9
    assert all(record["independent_recompute_match"] for record in fit["trial_records"])
    assert all(set(record["score_hashes"]) == set(selection["TRAIN"]) for record in fit["trial_records"])
    assert all(record["analysis"]["item_count"] == 70 for record in fit["trial_records"])
    assert "protocol_sha256" not in fit["identity"]
    assert fit["identity"]["protocol_predecessor"]["sha256"] == subject.PROTOCOL_SHA256
    assert all("protocol_sha256" not in record["analysis"]
               and record["analysis"]["protocol_predecessor_sha256"] == subject.PROTOCOL_SHA256
               for record in fit["trial_records"])
    assert fit["input_commitments"] == {
        "verdict_rows_sha256": subject._sha(subject._canonical(verdicts)),
        "target_rows_sha256": subject._sha(subject._canonical(targets)),
    }


def test_selected30_dev_uses_paired_2000_bootstrap_and_frozen_fit(selected_fit):
    subject, selection, _train_rows, _train_targets, fit = selected_fit
    verdicts, targets = _rows(subject, "DEV", subject.DEV_COUNT)
    raw = _fit_raw(fit)
    profiles = []
    runtime = _runtime(subject, profiles=profiles)
    result = subject.evaluate_dev(verdicts, targets, raw, expected_fit_sha256=subject._sha(raw),
                                  selection_binding=selection, expected_successor_sha256=subject._sha(SOURCE.read_bytes()),
                                  runtime=runtime)
    bootstrap = result["comparison"]["bootstrap"]
    assert result["evidence_class"] == "selected100_synthetic_dev_comparison_no_authority"
    assert result["identity"]["selection_binding"] == selection
    assert bootstrap["replicates"] == 2000 and bootstrap["seed"] == 20260905 and bootstrap["sample_size"] == 30
    assert len(result["baseline_scores"]) == len(result["candidate_scores"]) == 30
    assert profiles[0] is None and profiles[1] == fit["winner"]["profile"]
    assert "protocol_sha256" not in result["comparison"]
    assert result["comparison"]["protocol_predecessor_sha256"] == subject.PROTOCOL_SHA256


def test_fit_requires_exact_selected_ids_and_source_hash_before_optimization():
    subject = _load()
    selection = _selection(subject)
    verdicts, targets = _rows(subject, "TRAIN", subject.TRAIN_COUNT)
    verdicts[0]["opaque_story_id"] = "outside-selected"
    with pytest.raises(ValueError, match="Selected TRAIN verdict IDs"):
        subject.fit_train(verdicts, targets, selection_binding=selection,
                          expected_successor_sha256=subject._sha(SOURCE.read_bytes()), runtime=_runtime(subject))
    with pytest.raises(ValueError, match="Selected adapter hash"):
        subject.fit_train([], [], selection_binding=selection, expected_successor_sha256="0" * 64,
                          runtime=_runtime(subject))


def test_coverage_failure_is_trial_fail_stop_without_replacement():
    subject = _load()
    selection = _selection(subject)
    verdicts, targets = _rows(subject, "TRAIN", subject.TRAIN_COUNT)
    with pytest.raises(Exception) as raised:
        subject.fit_train(verdicts, targets, selection_binding=selection,
                          expected_successor_sha256=subject._sha(SOURCE.read_bytes()),
                          runtime=_runtime(subject, core=_Core(coverage=0.87)))
    assert len(raised.value.attempted_trials) == 1
    assert raised.value.attempted_trials[0]["state"] == "failed"


def test_dev_rejects_legacy_or_unreplayed_fit_before_scoring(selected_fit):
    subject, selection, _train_rows, _train_targets, fit = selected_fit
    verdicts, targets = _rows(subject, "DEV", subject.DEV_COUNT)
    legacy = copy.deepcopy(fit)
    legacy["evidence_class"] = "baseline_source_verified_fit_unadmitted"
    raw = _fit_raw(legacy)
    runtime = _runtime(subject)
    with pytest.raises(ValueError, match="identity or authority"):
        subject.evaluate_dev(verdicts, targets, raw, expected_fit_sha256=subject._sha(raw),
                             selection_binding=selection, expected_successor_sha256=subject._sha(SOURCE.read_bytes()),
                             runtime=runtime)
    assert runtime.core.calls == 0
    unreplayed = copy.deepcopy(fit)
    unreplayed["trial_records"][0]["independent_recompute_match"] = False
    raw = _fit_raw(unreplayed)
    with pytest.raises(ValueError, match="trial replay"):
        subject.evaluate_dev(verdicts, targets, raw, expected_fit_sha256=subject._sha(raw),
                             selection_binding=selection, expected_successor_sha256=subject._sha(SOURCE.read_bytes()),
                             runtime=_runtime(subject))


def test_public_fit_binds_real_source_verified_runtime_before_inputs(monkeypatch):
    subject = _load()
    baseline = SOURCE.parent / "baseline-runtime-v1.json"
    baseline_sha = subject._sha(baseline.read_bytes())
    original = subject._runtime
    observed = {}

    class RuntimeBound(RuntimeError):
        pass

    def select_and_stop(optimizer, native, runtime, **kwargs):
        loaded, source, binding, captures = original(optimizer, native, runtime, **kwargs)
        loaded.verify()
        observed.update(source=source, binding=binding, captures=captures, arguments=kwargs)
        raise RuntimeBound

    monkeypatch.setattr(subject, "_runtime", select_and_stop)
    with pytest.raises(RuntimeBound):
        subject.fit_train([], [], selection_binding=_selection(subject),
                          expected_successor_sha256=subject._sha(SOURCE.read_bytes()),
                          baseline_manifest_path=baseline, baseline_manifest_sha256=baseline_sha)
    assert observed["source"] == subject.BASELINE_RUNTIME_SOURCE
    assert observed["binding"]["baseline_manifest"]["sha256"] == baseline_sha
    assert observed["arguments"] == {"baseline_manifest_path": baseline, "baseline_manifest_sha256": baseline_sha}
    assert observed["captures"]


def test_fit_preflight_validates_all_records_without_scoring_or_dev_targets(selected_fit):
    subject, selection, _rows, _targets, fit = selected_fit
    runtime = _runtime(subject)
    raw = _fit_raw(fit)
    subject.validate_frozen_fit(raw, expected_fit_sha256=subject._sha(raw), selection_binding=selection,
                                expected_successor_sha256=subject._sha(SOURCE.read_bytes()), runtime=runtime)
    assert runtime.core.calls == 0
    changed = copy.deepcopy(fit)
    changed["trial_records"][-1]["independent_recompute_match"] = False
    changed_raw = _fit_raw(changed)
    with pytest.raises(ValueError, match="trial replay"):
        subject.validate_frozen_fit(changed_raw, expected_fit_sha256=subject._sha(changed_raw), selection_binding=selection,
                                    expected_successor_sha256=subject._sha(SOURCE.read_bytes()), runtime=runtime)
    assert runtime.core.calls == 0
