"""Conditional DEV integration with synthetic scores, never provider evidence."""

import copy
import importlib.util
import json
from pathlib import Path

import pytest
import test_dryad_optimizer as fitting

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "evaluation-results/hbq-human-alignment-dryad-full-hbq-analysis-v1/dev_comparison.py"
BASELINE_MANIFEST = SOURCE.parent / "baseline-runtime-v1.json"


def test_public_dev_forwards_verified_baseline_binding_before_reading_inputs(monkeypatch):
    class SelectionReached(RuntimeError):
        pass

    spec = importlib.util.spec_from_file_location("dryad_dev_public_forwarding", SOURCE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    capture = module._capture
    observed = {}
    manifest_sha = fitting.subject._sha(BASELINE_MANIFEST.read_bytes())

    def capture_with_selection_probe(expected):
        values = capture(expected)
        captures, protocol, optimizer, _, _ = values
        select = optimizer._runtime

        def select_and_stop(runtime, native, **kwargs):
            loaded, source, binding, _ = select(runtime, native, **kwargs)
            observed.update(arguments=kwargs, identity=optimizer._identity(protocol, captures, source, binding))
            loaded.verify()
            raise SelectionReached

        monkeypatch.setattr(optimizer, "_runtime", select_and_stop)
        return values

    monkeypatch.setattr(module, "_capture", capture_with_selection_probe)
    with pytest.raises(SelectionReached):
        module.evaluate_dev([], [], b"{}", expected_fit_sha256=fitting.subject._sha(b"{}"),
                            expected_comparison_sha256=fitting.subject._sha(SOURCE.read_bytes()),
                            baseline_manifest_path=BASELINE_MANIFEST, baseline_manifest_sha256=manifest_sha)
    assert observed["arguments"] == {
        "baseline_manifest_path": BASELINE_MANIFEST, "baseline_manifest_sha256": manifest_sha,
    }
    assert observed["identity"]["evidence_class"] == "baseline_source_verified_fit_unadmitted"
    assert observed["identity"]["runtime_pins"]["baseline_manifest"]["sha256"] == manifest_sha


@pytest.fixture(scope="module")
def frozen_fit():
    verdicts, targets = fitting._data()
    fit = fitting.subject.fit_train(verdicts, targets,
        expected_optimizer_sha256=fitting.subject._sha(fitting.SOURCE.read_bytes()),
        runtime=fitting._runtime(fitting.SyntheticCore()))
    return fit, verdicts, targets


@pytest.fixture
def example(frozen_fit):
    spec = importlib.util.spec_from_file_location("dryad_dev_comparison_test_subject", SOURCE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    fit, train_verdicts, train_targets = copy.deepcopy(frozen_fit)
    verdicts, targets = train_verdicts[:60], train_targets[:60]
    for index, (row, target) in enumerate(zip(verdicts, targets)):
        story = f"dev-story-{index:03d}"
        row["opaque_story_id"] = target["opaque_story_id"] = story
        target["partition"] = "DEV"
    profiles = []
    class Weights(fitting.SyntheticWeights):
        def materialize_weight_profile(self, modules, bundle, profile):
            profiles.append(copy.deepcopy(profile))
            if profile is None:
                return copy.deepcopy(modules), copy.deepcopy(bundle), {"identity": True, "requested": None}
            return super().materialize_weight_profile(modules, bundle, profile)
    runtime = fitting._runtime(fitting.SyntheticCore())
    runtime.weights = Weights()
    return module, fit, verdicts, targets, runtime, profiles


def evaluate(example):
    module, fit, verdicts, targets, runtime, _ = example
    raw = json.dumps(fit, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return module.evaluate_dev(verdicts, targets, raw,
        expected_fit_sha256=fitting.subject._sha(raw),
        expected_comparison_sha256=fitting.subject._sha(SOURCE.read_bytes()), runtime=runtime)


def test_frozen_winner_and_canonical_baseline_are_scored_once(example):
    _module, fit, verdicts, targets, runtime, profiles = example
    before = copy.deepcopy((fit, verdicts, targets))
    result = evaluate(example)
    assert result["evidence_class"] == "synthetic_dev_comparison_no_authority"
    assert result["native_admission_verified"] is False
    assert result["target_freeze_verified"] is False
    assert profiles == [None, fitting.subject._profile(tuple(fit["winner"]["multipliers"]))]
    assert runtime.core.calls == 120
    assert len(result["baseline_scores"]) == len(result["candidate_scores"]) == 60
    assert result["comparison"]["bootstrap"]["replicates"] == 2000
    assert before == (fit, verdicts, targets)


@pytest.mark.parametrize("fault", ["winner", "unreplayed", "trial_inventory", "train_overlap", "missing_dev", "synthetic_class", "nonwinner_vector", "objective"])
def test_unqualified_fit_or_dev_inputs_are_rejected(example, fault):
    _, fit, verdicts, targets, runtime, _ = example
    if fault == "winner":
        fit["winner"]["multipliers"][0] = 3.0
    elif fault == "unreplayed":
        fit["trial_records"][17]["independent_recompute_match"] = False
    elif fault == "trial_inventory":
        fit["trial_records"].pop()
    elif fault == "train_overlap":
        story = next(iter(fit["trial_records"][0]["score_hashes"]))
        verdicts[0]["opaque_story_id"] = targets[0]["opaque_story_id"] = story
    elif fault == "missing_dev":
        verdicts.pop()
        targets.pop()
    elif fault == "synthetic_class":
        fit["evidence_class"] = fit["identity"]["evidence_class"] = "development_fit_only"
    elif fault == "nonwinner_vector":
        record = fit["trial_records"][5]
        record["multipliers"][0] = 3.0
        record["profile"] = fitting.subject._profile(tuple(record["multipliers"]))
        fit["winner"] = fitting.subject._winner(fit["trial_records"])
    else:
        fit["trial_records"][5]["objective"] += 0.01
    with pytest.raises(ValueError):
        evaluate(example)
    assert runtime.core.calls == 0


def test_default_scoring_path_cannot_promote_raw_inputs(example, monkeypatch):
    module, fit, verdicts, targets, runtime, _ = example
    fit["evidence_class"] = fit["identity"]["evidence_class"] = "development_fit_only"
    fit["identity"]["runtime_source"] = "pinned_native_load_runtime"
    capture = module._capture

    def capture_with_test_native(expected):
        result = capture(expected)
        monkeypatch.setattr(result[-1], "load_runtime", lambda: runtime)
        return result

    monkeypatch.setattr(module, "_capture", capture_with_test_native)
    raw = json.dumps(fit, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    result = module.evaluate_dev(verdicts, targets, raw,
        expected_fit_sha256=fitting.subject._sha(raw), expected_comparison_sha256=fitting.subject._sha(SOURCE.read_bytes()))
    assert result["evidence_class"] == "unadmitted_dev_comparison_only"
    assert result["native_admission_verified"] is False
    assert result["target_freeze_verified"] is False


def test_source_and_fit_anchors_are_required(example):
    module, fit, verdicts, targets, runtime, _ = example
    raw = json.dumps(fit).encode()
    for fit_hash, source_hash in (("0" * 64, fitting.subject._sha(SOURCE.read_bytes())), (fitting.subject._sha(raw), "0" * 64)):
        with pytest.raises(ValueError, match="hash"):
            module.evaluate_dev(verdicts, targets, raw, expected_fit_sha256=fit_hash, expected_comparison_sha256=source_hash, runtime=runtime)
    assert runtime.core.calls == 0


def test_source_verified_baseline_fit_binding_must_match_dev_runtime(example):
    module, fit, _, _, _, _ = example
    captures, protocol, optimizer, analysis, _ = module._capture(fitting.subject._sha(SOURCE.read_bytes()))
    source = optimizer.BASELINE_RUNTIME_SOURCE
    fit_binding = {
        "baseline_runtime_loader": {"path": "loader.py", "sha256": "1" * 64},
        "baseline_manifest": {"path": "manifest.json", "sha256": "2" * 64},
        "baseline_runtime_provenance": {"evidence_class": "prospective_baseline_runtime_source_binding", "manifest_sha256": "2" * 64, "source_sha256": {"runtime.py": "3" * 64}, "provider_calls": 0, "native_admission": False, "execution_authority": False},
    }
    dev_binding = copy.deepcopy(fit_binding)
    dev_binding["baseline_manifest"]["sha256"] = "4" * 64
    fit["evidence_class"] = optimizer._evidence_class(source)
    fit["identity"] = optimizer._identity(protocol, captures, source, fit_binding)
    raw = json.dumps(fit, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    with pytest.raises(ValueError, match="Frozen fit identity"):
        module._fit(raw, fitting.subject._sha(raw), optimizer, analysis, source, dev_binding, protocol, captures)


def test_injected_dev_runtime_cannot_select_source_verified_baseline_path(example):
    module, fit, verdicts, targets, runtime, _ = example
    raw = json.dumps(fit, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    with pytest.raises(ValueError, match="Injected runtime"):
        module.evaluate_dev(
            verdicts,
            targets,
            raw,
            expected_fit_sha256=fitting.subject._sha(raw),
            expected_comparison_sha256=fitting.subject._sha(SOURCE.read_bytes()),
            runtime=runtime,
            baseline_manifest_path=BASELINE_MANIFEST,
            baseline_manifest_sha256="3b1f70a40a6dac8028d11c52f747400ab88dff3a193f828e3940c53813f3273d",
        )
