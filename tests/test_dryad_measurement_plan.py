from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation-results" / "hbq-human-alignment-dryad-full-hbq-analysis-v1"
SOURCE = PACKAGE / "measurement_plan.py"
PUBLIC_INPUTS = Path.home() / "Documents/cwr-dryad-pilot-source-freeze-20260905-r1/public-inputs.json"


def load():
    spec = importlib.util.spec_from_file_location("dryad_measurement_plan", SOURCE)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_builds_full_public_geometry_and_endpoint_identical_payloads() -> None:
    subject = load()
    campaign = subject._load(subject.CAMPAIGN_PLAN_PATH, subject.CAMPAIGN_PLAN_SHA256, "Campaign plan")
    runtime = campaign._load_runtime()
    raw = PUBLIC_INPUTS.read_bytes()
    generator = {"evidence_class": "synthetic_test_only", "git_commit": "0" * 40, "files": {}}
    for cap, batches in ((8, 23), (32, 6)):
        plan, artifacts = subject.build_plan(raw, runtime, {"cap": cap, "evidence_class": "complete_native_campaign_admission", "provider_calls": 0, "execution_authority": False}, generator=generator)
        assert plan["counts"] == {"train_stories": 176, "dev_stories": 60, "stories": 236, "questions_per_story": 178, "logical_requests": 236 * batches}
        assert len(plan["passes"]) == 236 and len(plan["requests"]) == 236 * batches
        assert all(item["batch_size"] == cap and item["batches"] == batches and item["purpose"] == "fresh_post_qualification_measurement" for item in plan["passes"])
        assert all(item["question_ids"] and item["endpoint_user_payloads"]["grok"] == item["endpoint_user_payloads"]["sol"] for item in plan["requests"])
        assert plan["namespace"]["measurement_pass_prefix"] == "measurement/"
        assert all(item["pass_id"].startswith("measurement/") and item["logical_sample_id"].startswith("measurement-") and not item["pass_id"].startswith("size-") for item in plan["passes"])
        assert hashlib.sha256(artifacts["plan.json"]).hexdigest() == hashlib.sha256(subject._canonical(plan)).hexdigest()


def test_public_input_hash_drift_rejects_before_plan_generation() -> None:
    subject = load()
    with pytest.raises(ValueError, match="Public inputs hash"):
        subject._inputs(b"{}")


def test_prepare_fails_closed_without_authenticated_admission(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    subject = load()
    output = tmp_path / "measurement"
    qualification_plan = tmp_path / "qualification-plan"
    qualification_execution = tmp_path / "qualification-execution"
    qualification_plan.mkdir()
    qualification_execution.mkdir()
    def reject(*args, **kwargs):
        raise ValueError("synthetic admission is not authenticated")
    monkeypatch.setattr(subject, "_sources", lambda: ({Path(subject.__file__).resolve(): Path(subject.__file__).read_bytes()}, (SimpleNamespace(_load_runtime=lambda: pytest.fail("runtime must not load")), SimpleNamespace(admit_campaign=reject))))
    with pytest.raises(ValueError, match="synthetic admission"):
        subject.prepare(PUBLIC_INPUTS, output, qualification_plan, qualification_execution, expected_qualification_plan_sha256="0" * 64, expected_settlement_sha256="1" * 64, expected_admission_sha256="2" * 64, expected_execution_sha256="3" * 64)
    assert not output.exists()


def _synthetic_prepare_fixture(subject, monkeypatch: pytest.MonkeyPatch):
    state = {"cap": 8}
    def admit_campaign(*args, **kwargs):
        cap = state["cap"]
        return {"evidence_class": "complete_native_campaign_admission", "execution_authority": False, "provider_calls": 0,
                "cap": cap, "plan_sha256": kwargs["expected_plan_sha256"], "admission_sha256": kwargs["expected_admission_sha256"],
                "execution_source_sha256": kwargs["expected_execution_sha256"], "ledger_head": {"settlement_sha256": kwargs["expected_final_settlement_sha256"]}}
    campaign = SimpleNamespace(_load_runtime=lambda: SimpleNamespace(verify=lambda: None))
    monkeypatch.setattr(subject, "_sources", lambda: ({Path(subject.__file__).resolve(): Path(subject.__file__).read_bytes()}, (campaign, SimpleNamespace(admit_campaign=admit_campaign))))
    monkeypatch.setattr(subject, "_identity", lambda commit=None: {"evidence_class": "synthetic_test_only", "git_commit": commit or "a" * 40, "files": {}})
    def build(raw, runtime, admission, *, generator):
        plan = {"generator": generator, "qualification_admission": admission, "cap": admission["cap"]}
        return plan, {"plan.json": subject._canonical(plan), "inputs/synthetic.txt": b"synthetic public fixture"}
    monkeypatch.setattr(subject, "build_plan", build)
    return state


def _prepare_synthetic(subject, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    state = _synthetic_prepare_fixture(subject, monkeypatch)
    qualification_plan, qualification_execution = tmp_path / "qualification-plan", tmp_path / "qualification-execution"
    qualification_plan.mkdir()
    qualification_execution.mkdir()
    output = tmp_path / "measurement"
    anchors = {"expected_qualification_plan_sha256": "0" * 64, "expected_settlement_sha256": "1" * 64,
               "expected_admission_sha256": "2" * 64, "expected_execution_sha256": "3" * 64}
    prepared = subject.prepare(PUBLIC_INPUTS, output, qualification_plan, qualification_execution, **anchors)
    return state, output, qualification_plan, qualification_execution, anchors, prepared


def test_synthetic_prepare_verify_round_trip_and_closed_inventory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    subject = load()
    _, output, qualification_plan, qualification_execution, anchors, prepared = _prepare_synthetic(subject, tmp_path, monkeypatch)
    assert set(prepared) == {"inputs/synthetic.txt", "plan.json"}
    assert subject.verify(PUBLIC_INPUTS, output, qualification_plan, qualification_execution, **anchors) == prepared
    (output / "extra.txt").write_text("extra", encoding="utf-8")
    with pytest.raises(ValueError, match="inventory"):
        subject.verify(PUBLIC_INPUTS, output, qualification_plan, qualification_execution, **anchors)


def test_verify_rejects_tampered_artifact_and_extra_directory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    subject = load()
    _, output, qualification_plan, qualification_execution, anchors, _ = _prepare_synthetic(subject, tmp_path, monkeypatch)
    (output / "inputs/synthetic.txt").write_bytes(b"tampered")
    with pytest.raises(ValueError, match="byte drift"):
        subject.verify(PUBLIC_INPUTS, output, qualification_plan, qualification_execution, **anchors)
    (output / "inputs/synthetic.txt").write_bytes(b"synthetic public fixture")
    (output / "orphan").mkdir()
    with pytest.raises(ValueError, match="directory inventory"):
        subject.verify(PUBLIC_INPUTS, output, qualification_plan, qualification_execution, **anchors)


def test_verify_rejects_admission_drift_and_dependency_pin_drift(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    subject = load()
    state, output, qualification_plan, qualification_execution, anchors, _ = _prepare_synthetic(subject, tmp_path, monkeypatch)
    state["cap"] = 32
    with pytest.raises(ValueError, match="byte drift"):
        subject.verify(PUBLIC_INPUTS, output, qualification_plan, qualification_execution, **anchors)
    fresh = load()
    monkeypatch.setattr(fresh, "CAMPAIGN_PLAN_SHA256", "0" * 64)
    with pytest.raises(ValueError, match="source pin"):
        fresh._sources()


def test_output_rejects_qualification_and_public_source_overlap(tmp_path: Path) -> None:
    subject = load()
    qualification_plan, qualification_execution = tmp_path / "qualification-plan", tmp_path / "qualification-execution"
    qualification_plan.mkdir()
    qualification_execution.mkdir()
    with pytest.raises(ValueError, match="overlaps"):
        subject._output(PUBLIC_INPUTS, qualification_plan / "measurement", qualification_plan, qualification_execution, fresh=True)
    with pytest.raises(ValueError, match="overlaps"):
        subject._output(PUBLIC_INPUTS, PUBLIC_INPUTS.parent / "measurement-plan", qualification_plan, qualification_execution, fresh=True)


def test_prepare_rejects_admission_drift_before_writing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    subject = load()
    _synthetic_prepare_fixture(subject, monkeypatch)
    qualification_plan, qualification_execution = tmp_path / "qualification-plan", tmp_path / "qualification-execution"
    qualification_plan.mkdir()
    qualification_execution.mkdir()
    calls = {"count": 0}
    def admission(*args, **kwargs):
        calls["count"] += 1
        cap = 8 if calls["count"] == 1 else 32
        return {"evidence_class": "complete_native_campaign_admission", "execution_authority": False, "provider_calls": 0, "cap": cap,
                "plan_sha256": kwargs["plan_sha256"], "admission_sha256": kwargs["admission_sha256"], "execution_source_sha256": kwargs["execution_sha256"], "ledger_head": {"settlement_sha256": kwargs["settlement_sha256"]}}
    monkeypatch.setattr(subject, "_admission", admission)
    anchors = {"expected_qualification_plan_sha256": "0" * 64, "expected_settlement_sha256": "1" * 64, "expected_admission_sha256": "2" * 64, "expected_execution_sha256": "3" * 64}
    output = tmp_path / "measurement"
    with pytest.raises(ValueError, match="admission changed"):
        subject.prepare(PUBLIC_INPUTS, output, qualification_plan, qualification_execution, **anchors)
    assert calls["count"] == 2 and not output.exists()
