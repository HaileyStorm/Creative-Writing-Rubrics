from __future__ import annotations

import copy
import importlib.util
import json
import sys
from pathlib import Path

import pytest
from tests import _historical_runtime_compat as historical_runtime
from hbqrs.paths import book_root
from hbqrs.runner import _provider_artifact, _provider_tree_digest


ROOT = book_root() / "evaluation-results" / "the-part-that-arrives-first-repeatability" / "supplemental-providers-pro-successor-v1"


def load(name: str, path: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


runner = load("pro_successor_runner", "run_study.py")
compatible_v3 = runner._v3()
historical_runtime.allow_supplemental_v3_runner_drift(compatible_v3)
runner._v3 = lambda: compatible_v3
sys.modules["run_study"] = runner
analyzer = load("pro_successor_analyzer", "analyze_study.py")


def test_contract_records_the_exact_flash_failure_and_five_run_schedule():
    trigger = runner.CONTRACT["flash_execution_trigger"]
    assert trigger["journal_sha256"] == "dd0ba1c0f3d2a5e972591aebdde0ff06eadbed92d8cffe03437a1cbb465f86f6"
    assert trigger["completed_event_count"] == 1 and len(trigger["semantic_rejections"]) == 3
    assert trigger["completed_hbq_manifest"]["path"] == "providers/nous_flash_max/hbq/run-01/run.json"
    assert all(item["reason"] == "naplan_narrative_2022 exact quote is not grounded in the frozen source" for item in trigger["semantic_rejections"])
    assert len(runner.schedule_events()) == 20
    assert [item["method_id"] for item in runner.schedule_events()[:4]] == ["hbq", "naplan", "cambridge", "oregon"]


def test_preflight_binds_flash_trigger_and_pro_provider(tmp_path, monkeypatch):
    raw = load("pro_successor_runner_refusal", "run_study.py")
    with pytest.raises(ValueError, match="Frozen asset changed: runner"):
        raw.preflight(tmp_path / "raw-flash")
    root, _ = _fake_trigger_root(tmp_path, monkeypatch)
    contract, source = runner.preflight(root)
    assert source.name == "source.md"
    assert contract["provider"]["model"] == "deepseek/deepseek-v4-pro-0813"
    assert contract["provider"]["no_purchase"] is True and contract["provider"]["stop_on_http_402"] is True
def test_preflight_rejects_schedule_provider_and_parity_drift(tmp_path, monkeypatch):
    root, _ = _fake_trigger_root(tmp_path, monkeypatch)
    monkeypatch.setitem(runner.CONTRACT["provider"], "model", "other")
    with pytest.raises(ValueError, match="successor protocol"):
        runner.preflight(root)
    monkeypatch.undo()
    monkeypatch.setitem(runner.CONTRACT["schedule"], "execution", "parallel")
    with pytest.raises(ValueError, match="successor protocol"):
        runner.preflight(root)
    monkeypatch.undo()
    monkeypatch.setitem(runner.CONTRACT["parity"]["hbq"], "batch_size", 31)
    with pytest.raises(ValueError, match="parity"):
        runner.preflight(root)


@pytest.mark.parametrize(("field", "value"), [("reported_models", ["forged"]), ("provider_canonical_model", "forged"), ("provisional_reasoning", False)])
def test_preflight_rejects_exact_provider_receipt_freeze_drift(tmp_path, monkeypatch, field, value):
    root, _ = _fake_trigger_root(tmp_path, monkeypatch)
    monkeypatch.setitem(runner.CONTRACT["provider"], field, value)
    with pytest.raises(ValueError, match="successor protocol"):
        runner.preflight(root)


def _fake_trigger_root(tmp_path: Path, monkeypatch) -> tuple[Path, Path]:
    root = tmp_path / "flash"
    journal = root / "providers/nous_flash_max/schedule-journal.jsonl"
    planned = [{"event": "planned", "sequence": index} for index in range(1, 21)]
    completed = {"event": "completed", "provider_id": "nous_flash_max", "method_id": "hbq", "run_id": "run-01", "run_binding_sha256": "b" * 64}
    journal.parent.mkdir(parents=True)
    journal.write_text("\n".join(json.dumps(row) for row in [*planned, completed]) + "\n")
    hbq_manifest = root / "providers/nous_flash_max/hbq/run-01/run.json"
    hbq_manifest.parent.mkdir(parents=True)
    hbq_manifest.write_text("hbq manifest")
    rejected = root / "providers/nous_flash_max/naplan/run-01/attempts/rejected-0001.json"
    rejected.parent.mkdir(parents=True)
    rejected.write_text(json.dumps({"reason": "ungrounded"}))
    manifest = root / "providers/nous_flash_max/naplan/run-01/pass.json"
    manifest.write_text("manifest")
    artifact = {"path": rejected.relative_to(root).as_posix(), "bytes": rejected.stat().st_size, "sha256": runner.sha(rejected), "reason": "ungrounded"}
    trigger = {"provider_id": "nous_flash_max", "journal_path": journal.relative_to(root).as_posix(), "journal_sha256": runner.sha(journal), "planned_event_count": 20, "completed_event_count": 1, "completed_hbq_run_binding_sha256": runner.sha(hbq_manifest), "completed_hbq_manifest": {"path": hbq_manifest.relative_to(root).as_posix(), "bytes": hbq_manifest.stat().st_size, "sha256": runner.sha(hbq_manifest)}, "naplan_pass_manifest": {"path": manifest.relative_to(root).as_posix(), "bytes": manifest.stat().st_size, "sha256": runner.sha(manifest)}, "required_absent_paths": ["providers/nous_flash_max/naplan/run-01/response.json"], "semantic_rejections": [artifact]}
    completed["run_binding_sha256"] = trigger["completed_hbq_run_binding_sha256"]
    journal.write_text("\n".join(json.dumps(row) for row in [*planned, completed]) + "\n")
    trigger["journal_sha256"] = runner.sha(journal)
    monkeypatch.setitem(runner.CONTRACT, "flash_execution_trigger", trigger)
    return root, rejected


def test_trigger_rejects_semantic_artifact_or_receipt_tamper(tmp_path, monkeypatch):
    root, rejected = _fake_trigger_root(tmp_path, monkeypatch)
    runner.validate_flash_trigger(root)
    rejected.write_text(json.dumps({"reason": "changed"}))
    with pytest.raises(ValueError, match="artifact"):
        runner.validate_flash_trigger(root)


def test_trigger_rejects_missing_or_tampered_completed_hbq_manifest(tmp_path, monkeypatch):
    root, _ = _fake_trigger_root(tmp_path, monkeypatch)
    hbq = root / "providers/nous_flash_max/hbq/run-01/run.json"
    hbq.unlink()
    with pytest.raises(ValueError, match="HBQ manifest"):
        runner.validate_flash_trigger(root)
    hbq.write_text("tampered")
    with pytest.raises(ValueError, match="HBQ manifest"):
        runner.validate_flash_trigger(root)


def test_resume_journal_accepts_only_the_exact_planned_prefix(tmp_path):
    journal, completed = runner._prepare_journal(tmp_path)
    assert completed == 0 and len(runner._journal(journal)) == 20
    plans = runner.schedule_events()
    for event in plans[:2]:
        binding = runner._binding(tmp_path, event["method_id"], event["run_id"])
        binding.parent.mkdir(parents=True, exist_ok=True)
        binding.write_text(event["method_id"])
        runner._append(journal, {**event, "event": "completed", "run_binding_sha256": runner.sha(binding)})
    assert runner._prepare_journal(tmp_path)[1] == 2
    binding = runner._binding(tmp_path, plans[0]["method_id"], plans[0]["run_id"])
    binding.write_text("tampered")
    with pytest.raises(ValueError, match="completion"):
        runner._prepare_journal(tmp_path)


def test_execute_stops_on_402_without_retry_or_purchase(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "preflight", lambda _: (runner.CONTRACT, Path("source.md")))
    class V3:
        @staticmethod
        def _run(*args, **kwargs):
            raise RuntimeError("HTTP 402")
    monkeypatch.setattr(runner, "_v3", lambda: V3())
    with pytest.raises(RuntimeError, match="without purchase or retry"):
        runner.execute(tmp_path, tmp_path / "flash", 1)
    assert len(runner._journal(tmp_path / "providers/nous_pro_max/schedule-journal.jsonl")) == 20


def test_nous_pro_receipt_shape_is_strict(tmp_path):
    inherited = analyzer._v3_analyzer()
    fixture = json.loads((ROOT.parent / "supplemental-providers-v3/fixtures/provider-receipts.json").read_text())["nous"]
    fixture = copy.deepcopy(fixture)
    provider = runner.CONTRACT["provider"]
    fixture["requested"] = {"model": provider["model"], "reasoning_effort": provider["reasoning"]}
    fixture["reported"]["model"] = provider["model"]
    fixture["provider_canonical_model"] = provider["provider_canonical_model"]
    artifacts = {}
    for name in ("judge_request", "judge_result", "serialization_proof"):
        path = tmp_path / f"{name}.json"
        path.write_text(name)
        artifacts[name] = _provider_artifact(tmp_path, path)
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    (evidence / "proof.json").write_text("proof")
    artifacts["evidence_tree"] = _provider_tree_digest(tmp_path, evidence)
    fixture["provider_artifacts"] = artifacts
    assert inherited.receipt(tmp_path, {"provider": fixture}, provider).startswith("nous:")
    fixture["provider_canonical_model"] = "forged"
    with pytest.raises(ValueError, match="Nous"):
        inherited.receipt(tmp_path, {"provider": fixture}, provider)


def test_analyzer_refuses_incomplete_pro_journal_before_reading_v3_outputs(tmp_path, monkeypatch):
    root, _ = _fake_trigger_root(tmp_path, monkeypatch)
    monkeypatch.setattr(analyzer, "_v3_analyzer", lambda: (_ for _ in ()).throw(AssertionError("should not inspect v3 outputs")))
    with pytest.raises(ValueError, match="journal is incomplete"):
        analyzer.analyze(tmp_path, root, tmp_path / "output")
