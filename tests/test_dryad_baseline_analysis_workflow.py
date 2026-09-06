"""Synthetic composition checks for the admitted outer TRAIN/DEV workflow."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "evaluation-results/hbq-human-alignment-dryad-full-hbq-analysis-v1/baseline_analysis_workflow.py"


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _json(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode()


def _module():
    spec = importlib.util.spec_from_file_location("dryad_admitted_workflow_test", SOURCE)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def workflow(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    subject = _module()
    source_root = tmp_path / "source"
    target_root = tmp_path / "targets"
    runtime_root = tmp_path / "runtime"
    source_root.mkdir()
    target_root.mkdir()
    runtime_root.mkdir()
    train_ids = {f"train-{number:03d}" for number in range(176)}
    dev_ids = {f"dev-{number:03d}" for number in range(60)}
    public_inputs = source_root / "public-inputs.json"
    public_raw = _json({
        "TRAIN": [{"opaque_story_id": story, "story_text": "train"} for story in sorted(train_ids)],
        "DEV": [{"opaque_story_id": story, "story_text": "dev"} for story in sorted(dev_ids)],
    })
    public_inputs.write_bytes(public_raw)
    train_targets = target_root / "train-targets.json"
    train_raw = _json([{"opaque_story_id": story, "partition": "TRAIN"} for story in sorted(train_ids)])
    train_targets.write_bytes(train_raw)
    dev_targets = target_root / "dev-targets.json"
    dev_raw = _json([{"opaque_story_id": story, "partition": "DEV"} for story in sorted(dev_ids)])
    dev_targets.write_bytes(dev_raw)
    target_freeze = target_root / "target-freeze.json"
    freeze_raw = _json({
        "schema_version": 1,
        "evidence_class": "provider_free_human_target_preparation",
        "partitions": {
            "TRAIN": {"stories": 176, "ratings": 2116, "target_sha256": _sha(train_raw)},
            "DEV": {"stories": 60, "ratings": 720, "target_sha256": _sha(dev_raw)},
        },
    })
    target_freeze.write_bytes(freeze_raw)
    runtime = runtime_root / "runtime.json"
    runtime.write_bytes(b"synthetic runtime")
    admission_path = subject.ADMISSION_PATH
    optimizer_path = subject.OPTIMIZER_PATH
    comparison_path = subject.COMPARISON_PATH
    calls: list[str] = []
    admission_kwargs: list[dict[str, object]] = []
    state = {"fit_commitment_mismatch": False, "fit_error": None}
    rows = [
        {"opaque_story_id": story, "verdicts": [{"question_id": "q", "verdict": "YES"}],
         "coverage": 1.0, "source_sha256": _sha(story.encode())}
        for story in sorted(train_ids | dev_ids)
    ]

    def admission(**_kwargs):
        calls.append("admit")
        admission_kwargs.append(_kwargs)
        return {
            "schema_version": 2,
            "evidence_class": "complete_native_baseline_measurement_admission",
            "execution_authority": False,
            "provider_calls": 0,
            "admitted_passes": 236,
            "logical_requests": 5428,
            "original_initialization": {"execution_source_sha256": "a" * 64, "route_sha256": "b" * 64},
            "cohort_epochs": {number: {"route_sha256": "b" * 64} for number in range(1, 13)},
            "endpoint_grok_rows": rows,
        }

    def fit(verdicts, targets, **kwargs):
        calls.append("fit")
        assert {row["opaque_story_id"] for row in verdicts} == train_ids
        assert {row["opaque_story_id"] for row in targets} == train_ids
        assert kwargs["baseline_manifest_path"] == runtime
        if state["fit_error"] is not None:
            raise state["fit_error"]
        commitments = {
            "verdict_rows_sha256": _sha(subject._canonical(verdicts)),
            "target_rows_sha256": _sha(subject._canonical(sorted(targets, key=lambda row: row["opaque_story_id"]))),
        }
        if state["fit_commitment_mismatch"]:
            commitments["verdict_rows_sha256"] = "0" * 64
        return {
            "evidence_class": "baseline_source_verified_fit_unadmitted",
            "identity": {"kind": "synthetic"},
            "input_commitments": commitments,
        }

    def compare(verdicts, targets, fit_raw, **kwargs):
        calls.append("compare")
        assert {row["opaque_story_id"] for row in verdicts} == dev_ids
        assert {row["opaque_story_id"] for row in targets} == dev_ids
        assert json.loads(fit_raw)["evidence_class"] == "baseline_source_verified_fit_unadmitted"
        return {
            "evidence_class": "baseline_source_verified_dev_comparison_unadmitted",
            "identity": {"kind": "synthetic"},
            "input_commitments": {
                "verdict_rows_sha256": _sha(subject._canonical(verdicts)),
                "target_rows_sha256": _sha(subject._canonical(sorted(targets, key=lambda row: row["opaque_story_id"]))),
            },
        }

    def load(path, raw, _label):
        if path == admission_path:
            return SimpleNamespace(admit_baseline=lambda *args, **kwargs: admission(**kwargs))
        if path == optimizer_path:
            return SimpleNamespace(fit_train=fit)
        if path == comparison_path:
            return SimpleNamespace(evaluate_dev=compare)
        raise AssertionError(path)

    monkeypatch.setattr(subject, "PUBLIC_INPUTS_SHA256", _sha(public_raw))
    monkeypatch.setattr(subject, "TARGET_FREEZE_SHA256", _sha(freeze_raw))
    monkeypatch.setattr(subject, "TRAIN_TARGETS_SHA256", _sha(train_raw))
    monkeypatch.setattr(subject, "DEV_TARGETS_SHA256", _sha(dev_raw))
    monkeypatch.setattr(subject, "_load_module", load)
    return SimpleNamespace(
        subject=subject, calls=calls, rows=rows, admission_kwargs=admission_kwargs, state=state, train_ids=train_ids, dev_ids=dev_ids,
        public_inputs=public_inputs, target_freeze=target_freeze, train_targets=train_targets,
        dev_targets=dev_targets, runtime=runtime, tmp_path=tmp_path,
    )


def _anchors(case) -> dict[str, str]:
    subject = case.subject
    return {
        "expected_plan_sha256": "1" * 64,
        "expected_final_settlement_sha256": "2" * 64,
        "expected_execution_source_sha256": "3" * 64,
        "expected_route_sha256": "4" * 64,
        "expected_runtime_manifest_sha256": _sha(case.runtime.read_bytes()),
        "expected_admission_sha256": _sha(subject.ADMISSION_PATH.read_bytes()),
        "expected_reviewer_task": "synthetic-reviewer",
        "expected_initialization_sha256": "5" * 64,
        "expected_workflow_sha256": _sha(SOURCE.read_bytes()),
        "expected_optimizer_sha256": _sha(subject.OPTIMIZER_PATH.read_bytes()),
        "expected_comparison_sha256": _sha(subject.COMPARISON_PATH.read_bytes()),
    }


def _fit(case, output: Path | None = None, **override):
    output = output or case.tmp_path / "train-output"
    anchors = _anchors(case)
    anchors.update(override)
    return case.subject.fit_admitted_train(
        case.public_inputs, case.tmp_path / "plan", case.tmp_path / "execution", case.runtime,
        case.target_freeze, case.train_targets, output,
        **{key: value for key, value in anchors.items() if key != "expected_comparison_sha256"},
    )


def _compare(case, train_output: Path, output: Path | None = None, **override):
    output = output or case.tmp_path / "dev-output"
    anchors = _anchors(case)
    anchors.update(override)
    fit_path = train_output / "fit-unadmitted.json"
    freeze_path = train_output / "train-freeze.json"
    expected_fit = anchors.pop("expected_fit_sha256", _sha(fit_path.read_bytes()))
    expected_train_freeze = anchors.pop("expected_train_freeze_sha256", _sha(freeze_path.read_bytes()))
    anchors.pop("expected_optimizer_sha256")
    return case.subject.compare_admitted_dev(
        case.public_inputs, case.tmp_path / "plan", case.tmp_path / "execution", case.runtime,
        case.target_freeze, case.dev_targets, fit_path, freeze_path, output,
        **anchors,
        expected_fit_sha256=expected_fit,
        expected_train_freeze_sha256=expected_train_freeze,
    )


def test_train_admits_before_reading_targets_and_retains_v2_evidence(workflow, monkeypatch):
    observed: list[str] = []
    original = workflow.subject._targets

    def target_probe(*args, **kwargs):
        observed.append(workflow.calls[-1])
        return original(*args, **kwargs)

    monkeypatch.setattr(workflow.subject, "_targets", target_probe)
    result = _fit(workflow)
    assert observed == ["admit"]
    assert workflow.calls == ["admit", "fit"]
    assert result["freeze"]["admission"]["schema_version"] == 2
    assert result["freeze"]["admission"]["cohort_epochs"] == {
        str(number): {"route_sha256": "b" * 64} for number in range(1, 13)
    }
    assert result["freeze"]["inner"]["evidence_class"] == "baseline_source_verified_fit_unadmitted"
    assert result["freeze"]["source_provenance"]["current_source_verify_ran"] is False


def test_stored_admission_commitment_recomputes_after_json_reload(workflow):
    output = workflow.tmp_path / "train-output"
    _fit(workflow, output)
    stored = json.loads((output / "train-freeze.json").read_bytes())
    assert stored["admission_binding"]["admission_sha256"] == _sha(
        workflow.subject._canonical(stored["admission"])
    )


def test_failed_admission_creates_no_output_or_target_read(workflow, monkeypatch):
    def failed(*_args, **_kwargs):
        raise ValueError("synthetic admission failure")

    monkeypatch.setattr(workflow.subject, "_admit", failed)
    monkeypatch.setattr(workflow.subject, "_targets", lambda *_args, **_kwargs: pytest.fail("targets read before admission"))
    output = workflow.tmp_path / "missing-output"
    with pytest.raises(ValueError, match="synthetic admission failure"):
        _fit(workflow, output)
    assert not output.exists()


def test_output_inside_execution_evidence_is_rejected_before_admission(workflow):
    output = workflow.tmp_path / "execution" / "not-a-new-stage"
    with pytest.raises(ValueError, match="fresh external"):
        _fit(workflow, output)
    assert workflow.calls == []
    assert not output.exists()


def test_forwards_the_existing_original_initialization_anchors(workflow):
    _fit(workflow, expected_execution_source_sha256="a" * 64, expected_route_sha256="b" * 64)
    assert workflow.admission_kwargs == [{
        "expected_plan_sha256": "1" * 64,
        "expected_final_settlement_sha256": "2" * 64,
        "expected_execution_source_sha256": "a" * 64,
        "expected_route_sha256": "b" * 64,
        "expected_runtime_manifest_sha256": _sha(workflow.runtime.read_bytes()),
        "expected_admission_sha256": _sha(workflow.subject.ADMISSION_PATH.read_bytes()),
        "expected_reviewer_task": "synthetic-reviewer",
        "expected_initialization_sha256": "5" * 64,
    }]


def test_train_rejects_mismatched_inner_input_commitments(workflow):
    workflow.state["fit_commitment_mismatch"] = True
    output = workflow.tmp_path / "mismatched-output"
    with pytest.raises(ValueError, match="Inner input commitments"):
        _fit(workflow, output)
    assert workflow.calls == ["admit", "fit"]
    assert not output.exists()


def test_aborted_inner_fit_propagates_without_output(workflow):
    class SyntheticOptimizationAborted(RuntimeError):
        pass

    error = SyntheticOptimizationAborted("attempted records retained by inner optimizer")
    workflow.state["fit_error"] = error
    output = workflow.tmp_path / "aborted-output"
    with pytest.raises(SyntheticOptimizationAborted) as caught:
        _fit(workflow, output)
    assert caught.value is error
    assert not output.exists()


def test_failed_stage_retains_first_artifact_without_a_partial_final(workflow, monkeypatch):
    output = workflow.tmp_path / "published"
    calls = 0
    original = workflow.subject._store

    def fail_second(path, raw):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("synthetic second write failure")
        original(path, raw)

    monkeypatch.setattr(workflow.subject, "_store", fail_second)
    with pytest.raises(RuntimeError, match="Stage retained at"):
        workflow.subject._write(output, {"fit-unadmitted.json": b"fit", "train-freeze.json": b"freeze"})
    stages = list(workflow.tmp_path.glob(".published.staging-*"))
    assert not output.exists()
    assert len(stages) == 1
    assert (stages[0] / "fit-unadmitted.json").read_bytes() == b"fit"


def test_train_rejects_target_drift_before_fit(workflow):
    workflow.train_targets.write_bytes(b"[]")
    with pytest.raises(ValueError, match="TRAIN targets hash drift"):
        _fit(workflow)
    assert workflow.calls == ["admit"]


def test_train_rejects_nonexhaustive_admission_ids(workflow):
    workflow.rows.pop()
    with pytest.raises(ValueError, match="all 236"):
        _fit(workflow)
    assert workflow.calls == ["admit"]


def test_train_rejects_workflow_source_anchor_drift(workflow):
    anchors = _anchors(workflow)
    with pytest.raises(ValueError, match="Workflow hash drift"):
        workflow.subject.fit_admitted_train(
            workflow.public_inputs, workflow.tmp_path / "plan", workflow.tmp_path / "execution", workflow.runtime,
            workflow.target_freeze, workflow.train_targets, workflow.tmp_path / "bad-output",
            **{key: value for key, value in anchors.items() if key not in {"expected_comparison_sha256", "expected_workflow_sha256"}},
            expected_workflow_sha256="0" * 64,
        )
    assert workflow.calls == []


def test_dev_binds_exact_train_freeze_before_reading_dev_targets(workflow, monkeypatch):
    train_output = workflow.tmp_path / "train-output"
    _fit(workflow, train_output)
    train_freeze = train_output / "train-freeze.json"
    original_raw = train_freeze.read_bytes()
    train_freeze.write_bytes(original_raw + b" ")
    monkeypatch.setattr(workflow.subject, "_targets", lambda *_args, **_kwargs: pytest.fail("DEV targets read before TRAIN freeze"))
    with pytest.raises(ValueError, match="TRAIN freeze hash drift"):
        _compare(workflow, train_output, expected_train_freeze_sha256=_sha(original_raw))
    assert workflow.calls == ["admit", "fit", "admit"]


def test_dev_rejects_altered_fit_and_runs_only_after_train(workflow):
    train_output = workflow.tmp_path / "train-output"
    _fit(workflow, train_output)
    fit_path = train_output / "fit-unadmitted.json"
    original_raw = fit_path.read_bytes()
    fit_path.write_bytes(b"{}")
    with pytest.raises(ValueError, match="Frozen TRAIN fit hash drift"):
        _compare(workflow, train_output, expected_fit_sha256=_sha(original_raw))
    assert workflow.calls == ["admit", "fit", "admit"]


def test_dev_rejects_target_drift_after_train_freeze_binding(workflow):
    train_output = workflow.tmp_path / "train-output"
    _fit(workflow, train_output)
    workflow.dev_targets.write_bytes(b"[]")
    with pytest.raises(ValueError, match="DEV targets hash drift"):
        _compare(workflow, train_output)
    assert workflow.calls == ["admit", "fit", "admit"]


def test_dev_comparison_uses_dev_only_after_train_freeze(workflow):
    train_output = workflow.tmp_path / "train-output"
    _fit(workflow, train_output)
    result = _compare(workflow, train_output)
    assert workflow.calls == ["admit", "fit", "admit", "compare"]
    assert result["freeze"]["stage"] == "DEV"
    assert result["freeze"]["inner"]["evidence_class"] == "baseline_source_verified_dev_comparison_unadmitted"
    assert (workflow.tmp_path / "dev-output" / "dev-comparison-unadmitted.json").is_file()


def test_partial_kwargs_are_rejected_by_the_public_api(workflow):
    with pytest.raises(TypeError):
        workflow.subject.fit_admitted_train(workflow.public_inputs, workflow.tmp_path / "plan", workflow.tmp_path / "execution")
