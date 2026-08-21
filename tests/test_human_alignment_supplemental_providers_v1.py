from __future__ import annotations

import importlib.util
import json
import sys
import threading
import time
import types
from pathlib import Path

import pytest

from hbqrs.paths import book_root

ROOT = book_root() / "evaluation-results" / "hbq-human-alignment-supplemental-providers-v1"


def load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / filename)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


study = load("supplemental_hanna_study", "study.py")
sys.modules["study"] = study
runner = load("supplemental_hanna_runner", "run_study.py")
analysis = load("supplemental_hanna_analysis", "analyze_study.py")
sys.modules["analyze_study"] = analysis
gate = load("supplemental_hanna_gate", "promotion_gate.py")


def frozen() -> dict:
    rows = lambda prefix: [{"item_id": f"{prefix}-{number}", "model": "Human" if number % 11 == 0 else f"M{number % 11}", "quartile": number % 4 + 1, "prompt_group_id": f"p-{number % 48}"} for number in range(88)]
    return {"primary_work_dir": "C:/private/primary", "primary_frozen": {"sha256": "a" * 64}, "primary_protocol": {"study_contract_sha256": "b" * 64, "runtime_sha256": "c" * 64, "runner": {"bundle_id": "prose.short_story", "batch_size": 32, "batch_attempts": 3}}, "selection": {"selection": {"seed": 560820}, "partitions": {"development": rows("dev"), "confirmatory": rows("con")}, "repeatability": {"items": [{"item_id": f"dev-{number}", "model": f"M{number}"} for number in range(11)], "repetitions": 5}, "mapping_sets": {}}, "input_commitments": {"development": {}, "confirmatory": {}}}


def grok_record() -> dict:
    return {"provider": {"requested": {"model": "grok-4.6", "reasoning_effort": "high"}, "reported": {"provider": "grok", "model": "grok-4.6-build"}, "reasoning_attested": False, "reasoning_attestation": "not_reported", "cli_version": "x", "session_id_sha256": "1" * 64, "request_id_sha256": "2" * 64, "provider_artifacts": {"grok_envelope": {}}}}


def nous_record() -> dict:
    return {"provider": {"requested": {"model": "deepseek/deepseek-v4-flash-0731", "reasoning_effort": "max"}, "reported": {"provider": "nous", "model": "deepseek/deepseek-v4-flash-0731"}, "reasoning_attested": False, "reasoning_attestation": "not_reported", "provider_canonical_model": "deepseek/deepseek-v4-flash-20260731", "tool_free": True, "exact_gate_eligible": False, "transport_policy": analysis.NOUS_TRANSPORT_POLICY, "logical_provider_request_count": 1, "physical_http_attempt_count": 1, "recovered_request_count": 0, "evidence_sha256": "3" * 64, "serialization_proof_sha256": "4" * 64, "provider_artifacts": {key: {} for key in ("judge_request", "judge_result", "serialization_proof", "evidence_tree")}}}


def test_contract_and_full_primary_schedule_are_frozen():
    assert study.CONTRACT["gpt_primary"]["development_items"] == 88
    assert [item["provider_id"] for item in study.CONTRACT["providers"]] == ["grok_4_6_high", "nous_flash_max", "nous_pro_max"]
    value = frozen()
    assert len(study.phase_rows(value, "development")) == 88
    assert len(study.phase_rows(value, "repeatability")) == 55
    assert len(study.phase_rows(value, "confirmatory")) == 88


def test_provider_receipts_require_distinct_artifact_shapes(monkeypatch, tmp_path):
    monkeypatch.setattr(analysis, "_validate_provider_artifacts", lambda *_: None)
    assert analysis.receipt(tmp_path, grok_record(), study.provider("grok_4_6_high")).startswith("grok:")
    assert analysis.receipt(tmp_path, nous_record(), study.provider("nous_flash_max")).startswith("nous:")
    forged = nous_record()
    forged["provider"]["session_id_sha256"] = "5" * 64
    with pytest.raises(ValueError, match="Nous stateless"):
        analysis.receipt(tmp_path, forged, study.provider("nous_flash_max"))
    missing = grok_record()
    missing["provider"]["provider_artifacts"] = {}
    with pytest.raises(ValueError, match="Grok receipt"):
        analysis.receipt(tmp_path, missing, study.provider("grok_4_6_high"))


def test_execution_preserves_primary_runner_shape_and_blocks_pro_development(monkeypatch, tmp_path):
    value = frozen()
    (tmp_path / "frozen-provider-contract.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(runner, "load_frozen", lambda _: value)
    monkeypatch.setattr(runner, "phase_rows", lambda *_: [{"item_id": "dev-0", "repetition": 1}])
    folder = tmp_path / "inputs"; folder.mkdir()
    monkeypatch.setattr(runner, "primary_input", lambda *_: (folder, {"item_id": "dev-0"}))
    calls = []
    monkeypatch.setattr(runner, "run_judge", lambda **kwargs: calls.append(kwargs) or {"status": "ok"})
    runner.execute(tmp_path, "grok_4_6_high", "development", 1, 1)
    assert calls[0]["provider"] == "grok" and calls[0]["model"] == "grok-4.6" and calls[0]["strict_ai"] is False and calls[0]["batch_size"] == 32 and calls[0]["allow_unattested_reasoning"] is True
    with pytest.raises(ValueError, match="Nous Pro"):
        runner.execute(tmp_path, "nous_pro_max", "development", 1, 600)
    with pytest.raises(ValueError, match="maximum"):
        runner.execute(tmp_path, "grok_4_6_high", "development", 5, 1)


@pytest.mark.parametrize("workers, timeout, message", [(2, 600, "exactly one"), (4, 600, "exactly one"), (1, 419, "at least 420")])
def test_nous_preflight_rejects_before_input_paths_or_provider_calls(monkeypatch, tmp_path, workers, timeout, message):
    monkeypatch.setattr(runner, "load_frozen", lambda _: frozen())
    monkeypatch.setattr(runner, "primary_input", lambda *_: pytest.fail("invalid Nous execution must not inspect run paths"))
    monkeypatch.setattr(runner, "run_judge", lambda **_: pytest.fail("invalid Nous execution must not call provider"))
    with pytest.raises(ValueError, match=message):
        runner.execute(tmp_path, "nous_flash_max", "development", workers, timeout)
    assert not (tmp_path / "invocations").exists()


def test_nous_invocation_record_exact_repeat_tamper_and_resume(monkeypatch, tmp_path):
    value = frozen()
    (tmp_path / "frozen-provider-contract.json").write_text("{}", encoding="utf-8")
    rows = [{"item_id": "dev-0", "repetition": 1}]
    folder = tmp_path / "inputs"; folder.mkdir()
    monkeypatch.setattr(runner, "load_frozen", lambda _: value)
    monkeypatch.setattr(runner, "phase_rows", lambda *_: rows)
    monkeypatch.setattr(runner, "primary_input", lambda *_: (folder, {"item_id": "dev-0"}))
    calls = []
    def provider_boundary(**kwargs):
        calls.append(kwargs)
        output = Path(kwargs["output_dir"]); output.mkdir(parents=True, exist_ok=True); (output / "run.json").write_text("{}", encoding="utf-8")
        return {"status": "ok"}
    monkeypatch.setattr(runner, "run_judge", provider_boundary)
    runner.execute(tmp_path, "nous_flash_max", "development", 1, 600)
    record_path = tmp_path / "invocations" / "nous_flash_max" / "development.json"
    record = json.loads(record_path.read_text(encoding="utf-8"))
    assert record["provider_id"] == "nous_flash_max" and record["workers"] == 1 and record["timeout"] == 600.0
    assert "nous_transport" in record
    runner.execute(tmp_path, "nous_flash_max", "development", 1, 600)
    assert calls[1]["resume"] is True
    record_path.write_text("forged", encoding="utf-8")
    with pytest.raises(ValueError, match="Immutable invocation"):
        runner.execute(tmp_path, "nous_flash_max", "development", 1, 600)
    assert len(calls) == 2


def test_provider_failure_cancels_queued_waits_started_and_never_resumes(monkeypatch, tmp_path):
    value = frozen()
    (tmp_path / "frozen-provider-contract.json").write_text("{}", encoding="utf-8")
    rows = [{"item_id": f"dev-{number}", "repetition": 1} for number in range(100)]
    folder = tmp_path / "inputs"; folder.mkdir()
    second_started = threading.Event()
    second_finished = threading.Event()
    calls: list[str] = []
    monkeypatch.setattr(runner, "load_frozen", lambda _: value)
    monkeypatch.setattr(runner, "phase_rows", lambda *_: rows)
    monkeypatch.setattr(runner, "primary_input", lambda *_: (folder, {"item_id": "ignored"}))
    def provider_boundary(**kwargs):
        item_id = kwargs["artifact_id"]; calls.append(item_id)
        if item_id == "dev-0":
            assert second_started.wait(2)
            raise RuntimeError("provider failed")
        if item_id == "dev-1":
            second_started.set(); time.sleep(0.5); second_finished.set()
        return {"status": "ok"}
    monkeypatch.setattr(runner, "run_judge", provider_boundary)
    with pytest.raises(RuntimeError, match="provider failed"):
        runner.execute(tmp_path, "grok_4_6_high", "development", 2, 600)
    assert second_finished.is_set() and set(calls) <= {"dev-0", "dev-1"}


def test_invocations_are_provider_phase_scoped_and_refuse_backfill_or_partial_records(monkeypatch, tmp_path):
    value = frozen()
    (tmp_path / "frozen-provider-contract.json").write_text("{}", encoding="utf-8")
    rows = [{"item_id": "dev-0", "repetition": 1}]
    folder = tmp_path / "inputs"; folder.mkdir()
    monkeypatch.setattr(runner, "load_frozen", lambda _: value)
    monkeypatch.setattr(runner, "phase_rows", lambda *_: rows)
    monkeypatch.setattr(runner, "primary_input", lambda *_: (folder, {"item_id": "dev-0"}))
    monkeypatch.setattr(runner, "run_judge", lambda **_: {"status": "ok"})
    runner.execute(tmp_path, "grok_4_6_high", "development", 1, 600)
    monkeypatch.setattr(runner, "_can_run", lambda *_: None)
    runner.execute(tmp_path, "grok_4_6_high", "repeatability", 1, 600)
    grok_development = tmp_path / "invocations" / "grok_4_6_high" / "development.json"
    grok_repeatability = tmp_path / "invocations" / "grok_4_6_high" / "repeatability.json"
    assert grok_development.is_file() and grok_repeatability.is_file()
    assert "nous_transport" not in json.loads(grok_development.read_text(encoding="utf-8"))
    output = tmp_path / "runs" / "nous_flash_max" / "development" / "historical"; output.mkdir(parents=True)
    with pytest.raises(ValueError, match="backfill"):
        runner.execute(tmp_path, "nous_flash_max", "development", 1, 600)
    partial = tmp_path / "invocations" / "nous_flash_max" / "repeatability.json"
    partial.parent.mkdir(parents=True, exist_ok=True); partial.write_text("{", encoding="utf-8")
    with pytest.raises(ValueError, match="Immutable invocation"):
        runner.execute(tmp_path, "nous_flash_max", "repeatability", 1, 600)


def test_synchronized_invocation_race_never_clobbers(monkeypatch, tmp_path):
    value = frozen()
    (tmp_path / "frozen-provider-contract.json").write_text("{}", encoding="utf-8")
    folder = tmp_path / "inputs"; folder.mkdir()
    monkeypatch.setattr(runner, "load_frozen", lambda _: value)
    monkeypatch.setattr(runner, "phase_rows", lambda *_: [{"item_id": "dev-0", "repetition": 1}])
    monkeypatch.setattr(runner, "primary_input", lambda *_: (folder, {"item_id": "dev-0"}))
    monkeypatch.setattr(runner, "run_judge", lambda **_: {"status": "ok"})
    barrier = threading.Barrier(2)
    monkeypatch.setattr(runner, "_INVOCATION_TEMP_WRITTEN", lambda: barrier.wait(2))
    failures: list[BaseException] = []
    def invoke():
        try:
            runner.execute(tmp_path, "grok_4_6_high", "development", 1, 600)
        except BaseException as error:
            failures.append(error)
    first, second = threading.Thread(target=invoke), threading.Thread(target=invoke)
    first.start(); second.start(); first.join(); second.join()
    path = tmp_path / "invocations" / "grok_4_6_high" / "development.json"
    assert path.is_file() and json.loads(path.read_text(encoding="utf-8"))["provider_id"] == "grok_4_6_high"
    assert not failures


def test_runner_binds_its_sibling_analyzer_after_v3_load_order(monkeypatch):
    v3_root = book_root() / "evaluation-results" / "the-part-that-arrives-first-repeatability" / "supplemental-providers-v3"
    v3_runner_spec = importlib.util.spec_from_file_location("supplemental_v3_runner_for_order", v3_root / "run_study.py")
    assert v3_runner_spec and v3_runner_spec.loader
    v3_runner = importlib.util.module_from_spec(v3_runner_spec); v3_runner_spec.loader.exec_module(v3_runner)
    monkeypatch.setitem(sys.modules, "run_study", v3_runner)
    v3_analysis_spec = importlib.util.spec_from_file_location("supplemental_v3_analysis_for_order", v3_root / "analyze_study.py")
    assert v3_analysis_spec and v3_analysis_spec.loader
    v3_analysis = importlib.util.module_from_spec(v3_analysis_spec); v3_analysis_spec.loader.exec_module(v3_analysis)
    monkeypatch.setitem(sys.modules, "study", types.ModuleType("poisoned_study"))
    monkeypatch.setitem(sys.modules, "analyze_study", v3_analysis)
    mixed = load("supplemental_hanna_runner_mixed", "run_study.py")
    assert Path(mixed._ANALYSIS.__file__).resolve() == (ROOT / "analyze_study.py").resolve()


def test_later_phases_require_both_complete_development_conditions(monkeypatch, tmp_path):
    value = frozen()
    calls = []
    monkeypatch.setattr(runner, "load_frozen", lambda _: value)
    monkeypatch.setattr(runner, "_promotion", lambda *_: {"eligible_provider_ids": ["grok_4_6_high", "nous_flash_max"]})
    monkeypatch.setattr(runner._ANALYSIS, "verify_phase", lambda _work, _frozen, provider_id, phase: calls.append((provider_id, phase)) or [])
    monkeypatch.setattr(runner._ANALYSIS, "verify_study_receipts", lambda _work, _frozen, provider_id: calls.append((provider_id, "study-wide")))
    runner._can_run("nous_flash_max", "repeatability", tmp_path, tmp_path)
    assert calls == [("grok_4_6_high", "development"), ("grok_4_6_high", "study-wide"), ("nous_flash_max", "development"), ("nous_flash_max", "study-wide")]


def test_confirmatory_waits_for_every_eligible_repeatability_phase(monkeypatch, tmp_path):
    value = frozen(); calls = []
    monkeypatch.setattr(runner, "load_frozen", lambda _: value)
    monkeypatch.setattr(runner, "_promotion", lambda *_: {"eligible_provider_ids": ["grok_4_6_high", "nous_flash_max"]})
    monkeypatch.setattr(runner._ANALYSIS, "verify_phase", lambda _work, _frozen, provider_id, phase: calls.append((provider_id, phase)) or [])
    monkeypatch.setattr(runner._ANALYSIS, "verify_study_receipts", lambda _work, _frozen, provider_id: calls.append((provider_id, "study-wide")))
    runner._can_run("grok_4_6_high", "confirmatory", tmp_path, tmp_path)
    assert ("grok_4_6_high", "repeatability") in calls and ("nous_flash_max", "repeatability") in calls


def test_promotion_gate_rejects_unearned_pro(monkeypatch, tmp_path):
    value = frozen()
    monkeypatch.setattr(gate, "load_frozen", lambda _: value)
    monkeypatch.setattr(gate, "_replay", lambda *_: ({"primary_generated_only": {"macro_spearman": {"estimate": .6}}}, {}, {"primary_generated_only": {"macro_spearman": {"estimate": .4}}}))
    path = tmp_path / "promotion-decision.json"
    path.write_text(json.dumps({"format_version": 1, "study_id": study.CONTRACT["study_id"], "supplemental_contract_sha256": study.sha(ROOT / "study-contract.json"), "primary_frozen_sha256": "a" * 64, "eligible_provider_ids": ["grok_4_6_high", "nous_flash_max"], "promotion_reason": "not_triggered", "gpt_macro_estimate": .6, "flash_macro_estimate": .4, "flash_macro_delta_vs_gpt": "0.2"}), encoding="utf-8")
    with pytest.raises(ValueError, match="exactly satisfy"):
        gate.validate_gate(tmp_path, tmp_path)


def test_promotion_gate_recomputes_bidirectional_threshold(monkeypatch, tmp_path):
    value = frozen()
    monkeypatch.setattr(gate, "load_frozen", lambda _: value)
    monkeypatch.setattr(gate, "_replay", lambda *_: ({"primary_generated_only": {"macro_spearman": {"estimate": .6}}}, {}, {"primary_generated_only": {"macro_spearman": {"estimate": .4}}}))
    payload = {"format_version": 1, "study_id": study.CONTRACT["study_id"], "supplemental_contract_sha256": study.sha(ROOT / "study-contract.json"), "primary_frozen_sha256": "a" * 64, "gpt_macro_estimate": .6, "flash_macro_estimate": .4, "flash_macro_delta_vs_gpt": "0.2", "promotion_reason": "flash_generated_only_macro_delta", "eligible_provider_ids": ["grok_4_6_high", "nous_flash_max", "nous_pro_max"]}
    (tmp_path / "promotion-decision.json").write_text(json.dumps(payload), encoding="utf-8")
    assert gate.validate_gate(tmp_path, tmp_path)["promotion_reason"] == "flash_generated_only_macro_delta"
    payload["promotion_reason"] = "not_triggered"; payload["eligible_provider_ids"] = ["grok_4_6_high", "nous_flash_max"]
    (tmp_path / "promotion-decision.json").write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="exactly satisfy"):
        gate.validate_gate(tmp_path, tmp_path)


def test_phase_rejects_unmanifested_run_and_studywide_receipt_reuse(monkeypatch, tmp_path):
    value = frozen()
    one = {"item_id": "dev-0", "model": "M0"}
    monkeypatch.setattr(analysis, "_validate_invocation", lambda *_: {})
    monkeypatch.setattr(analysis, "_selection", lambda *_: [one])
    monkeypatch.setattr(analysis, "verify_run", lambda *_: ([], {}, ["receipt-x"]))
    expected = tmp_path / "runs" / "grok_4_6_high" / "development" / "dev-0" / "run-01" / "run.json"
    expected.parent.mkdir(parents=True); expected.write_text("{}", encoding="utf-8")
    extra = tmp_path / "runs" / "grok_4_6_high" / "development" / "extra" / "run-01" / "run.json"
    extra.parent.mkdir(parents=True); extra.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="unmanifested"):
        analysis.verify_phase(tmp_path, value, "grok_4_6_high", "development")
    extra.unlink()
    assert analysis.verify_phase(tmp_path, value, "grok_4_6_high", "development") == ["receipt-x"]
    confirm = tmp_path / "runs" / "grok_4_6_high" / "confirmatory" / "dev-0" / "run-01" / "run.json"
    confirm.parent.mkdir(parents=True); confirm.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(analysis, "PHASES", ("development", "confirmatory"))
    with pytest.raises(ValueError, match="across supplemental phases"):
        analysis.verify_study_receipts(tmp_path, value, "grok_4_6_high")


def test_dataset_metadata_reopens_the_pinned_primary_binding(monkeypatch, tmp_path):
    (tmp_path / "frozen-run-contract.json").write_text("{}", encoding="utf-8")
    value = {"primary_work_dir": str(tmp_path), "rating_metadata": {"one": {"model": "M"}}}
    calls = []
    class Primary:
        def validate_dataset_binding(self, data, frozen_contract): calls.append((data, frozen_contract))
    monkeypatch.setattr(study, "_load_primary_study", lambda: Primary())
    monkeypatch.setattr(study, "_rating_metadata", lambda data, frozen_contract: {"one": {"model": "M"}})
    study.validate_dataset_and_metadata(tmp_path, value)
    monkeypatch.setattr(study, "_rating_metadata", lambda data, frozen_contract: {"one": {"model": "forged"}})
    with pytest.raises(ValueError, match="rating/model metadata"):
        study.validate_dataset_and_metadata(tmp_path, value)
    assert calls


def test_paired_gpt_baseline_rejects_manifest_mutation(monkeypatch, tmp_path):
    value = frozen()
    value["primary_protocol"].update({"study_contract_sha256": "b" * 64})
    selected = value["selection"]["partitions"]["confirmatory"]
    records = [{"item_id": row["item_id"], "prompt_group_id": row["prompt_group_id"], "hbq_full_observed_score": 50.0} for row in selected]
    output = tmp_path / "gpt-confirmatory"; output.mkdir()
    items = output / "items.jsonl"; items.write_text("".join(json.dumps(row) + "\n" for row in records), encoding="utf-8")
    summary = {"format_version": 3, "study_id": "hbq-human-alignment-v3", "phase": "confirmatory", "study_contract_sha256": "b" * 64, "runtime_sha256": "c" * 64, "item_count": 88}
    (output / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
    manifest = {"format_version": 3, "study_id": "hbq-human-alignment-v3", "phase": "confirmatory", "study_contract_sha256": "b" * 64, "runtime_sha256": "c" * 64, "files": {"items.jsonl": {"bytes": items.stat().st_size, "sha256": study.sha(items)}}}
    (output / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    monkeypatch.setattr(analysis, "verify_primary_phase", lambda *_: records)
    assert analysis._paired_gpt_delta(records, items, "confirmatory", value, tmp_path)["item_count"] == 88
    manifest["files"]["items.jsonl"]["sha256"] = "0" * 64
    (output / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="manifest"):
        analysis._paired_gpt_delta(records, items, "confirmatory", value, tmp_path)


def test_primary_baseline_rejects_semantic_resign_mutation(monkeypatch, tmp_path):
    primary = tmp_path / "primary"; primary.mkdir()
    rows = [{"item_id": f"item-{number}", "model": "M", "story_sha256": f"s{number}", "prompt_sha256": f"p{number}", "prompt_group_id": f"group-{number % 48}"} for number in range(88)]
    frozen_primary = {"study_id": "hbq-human-alignment-v3", "runtime_sha256": "c" * 64, "study_contract_sha256": "b" * 64, "package_commit": "commit", "selection": {"seed": 7}, "partitions": {"development": rows}, "mapping_sets": {}}
    (primary / "frozen-run-contract.json").write_text(json.dumps(frozen_primary), encoding="utf-8")
    class Item:
        def __init__(self, row): self.item_id=row["item_id"]; self.model=row["model"]; self.story_sha256=row["story_sha256"]; self.prompt_sha256=row["prompt_sha256"]
    class FakeStudy:
        validate_dataset_binding = staticmethod(lambda *_: None)
        load_hanna_items = staticmethod(lambda _: [Item(row) for row in rows])
    class FakeAnalysis:
        verify_phase_runs = staticmethod(lambda *_: None)
        verify_run = staticmethod(lambda *_: ([], {}))
        record_for = staticmethod(lambda item, selection, *_: {"item_id": item.item_id, "source_model": item.model, "prompt_group_id": selection["prompt_group_id"], "hbq_full_observed_score": 50.0})
        macro_cluster_bootstrap = staticmethod(lambda *_: {"estimate": .6})
    monkeypatch.setattr(analysis, "PRIMARY_STUDY", FakeStudy)
    monkeypatch.setattr(analysis, "PRIMARY_ANALYSIS", FakeAnalysis)
    for row in rows:
        folder = primary / "inputs" / "development" / row["item_id"]; folder.mkdir(parents=True); (folder / "source.md").write_text("s"); (folder / "prompt.md").write_text("p")
    output = tmp_path / "output"; output.mkdir()
    records = [{"item_id": row["item_id"], "source_model": "M", "prompt_group_id": row["prompt_group_id"], "hbq_full_observed_score": 50.0} for row in rows]
    items = output / "items.jsonl"; items.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in records), encoding="utf-8")
    summary = {"format_version": 3, "study_id": "hbq-human-alignment-v3", "phase": "development", "study_contract_sha256": "b" * 64, "runtime_sha256": "c" * 64, "item_count": 88, "primary_generated_only": {"macro_spearman": {"estimate": .6}}}
    (output / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
    manifest = {"format_version": 3, "study_id": "hbq-human-alignment-v3", "phase": "development", "study_contract_sha256": "b" * 64, "runtime_sha256": "c" * 64, "package_commit": "commit", "files": {path.name: {"bytes": path.stat().st_size, "sha256": study.sha(path)} for path in output.iterdir()}}
    (output / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    supplemental = {"primary_work_dir": str(primary), "primary_protocol": {"runtime_sha256": "c" * 64}}
    assert len(analysis.verify_primary_phase(tmp_path, supplemental, "development", output)) == 88
    summary["primary_generated_only"]["macro_spearman"] = {"estimate": -.9}
    (output / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
    manifest["files"]["summary.json"] = {"bytes": (output / "summary.json").stat().st_size, "sha256": study.sha(output / "summary.json")}
    (output / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="summary"):
        analysis.verify_primary_phase(tmp_path, supplemental, "development", output)


def test_contract_is_prose_free():
    text = (ROOT / "study-contract.json").read_text(encoding="utf-8")
    assert "HANNA" in text and "raw_prose" not in text
