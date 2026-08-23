from __future__ import annotations

import gzip
import importlib.util
import json
import sys
from pathlib import Path

import pytest

from hbqrs.paths import book_root


ROOT = book_root() / "evaluation-results" / "hbq-p1-discordance-audit-v1"


def study():
    spec = importlib.util.spec_from_file_location("p1_discordance_audit_v1", ROOT / "study.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")


def _source_root(s, root: Path) -> None:
    fixtures = []
    expected = {}
    slots = []
    for ordinal in range(1, 21):
        fixture = f"H{ordinal:02d}"
        leaf = "core.coherence_and_comprehensibility.referents"
        fixtures.append({"fixture_id": fixture, "leaf_id": leaf, "artifact_kind": "synthetic_diagnostic", "declared_scope": "excerpt", "completion_status": "complete", "text": f"fixture {fixture}"})
        expected[fixture] = "YES"
        for arm in s.ARMS:
            for repeat in range(1, 4):
                slot = {"slot_id": f"slot-{fixture}-{arm}-{repeat}", "fixture_id": fixture, "artifact_id": f"artifact-{fixture}", "leaf_id": leaf, "arm": arm, "repeat": repeat, "judge_id": f"judge-{fixture}-{arm}-{repeat}"}
                slots.append(slot)
                run = root / "runs" / slot["slot_id"]
                _write(run / "run.json", {"configuration": {"provider": "codex", "model": "gpt-5.6-sol", "reasoning": "high", "batch_size": 1, "retry_policy": {"batch_attempts": 3}, "attempt_lifecycle_policy": "terminal_sidecar_v1", "artifact_id": slot["artifact_id"], "judge_id": slot["judge_id"], "question_ids": [leaf]}})
                verdict = "NO" if (fixture, arm, repeat) == ("H01", "CURRENT", 1) else "YES"
                (run / "verdicts.jsonl").write_text(json.dumps({"question_id": leaf, "verdict": verdict, "evidence": [{"reference": "artifact", "exact_quote": f"fixture {fixture}"}]}), encoding="utf-8")
                _write(run / "responses" / "batch-0001.json", {"provider": {"reported": {"provider": "openai", "model": "gpt-5.6-sol", "reasoning_effort": "high", "session_id": f"session-{slot['slot_id']}"}}})
                prompt = "common prompt\n" + ("\ncandidate appendix\n" if arm == "TREATMENT" else "")
                (run / "responses").mkdir(parents=True, exist_ok=True)
                (run / "responses" / "batch-0001.prompt.txt.gz").write_bytes(gzip.compress(prompt.encode("utf-8")))
                _write(run / "responses" / "attempt-lifecycle" / "batch-0001" / "attempt-0001.start.json", {"attempt_number": 1})
                _write(run / "responses" / "attempt-lifecycle" / "batch-0001" / "attempt-0001.settled.json", {"attempt": 1, "outcome": "accepted", "policy": "terminal_sidecar_v1", "state": "settled"})
    _write(root / "private-corpus.json", {"format_version": 1, "study_id": s.SOURCE_STUDY_ID, "fixtures": fixtures})
    _write(root / "sealed-expected-ledger.json", {"format_version": 1, "study_id": s.SOURCE_STUDY_ID, "expected": expected})
    _write(root / "runtime-schedule.json", {"slots": slots})
    for name in ("study-manifest.json", "settlement.json", "arm-contract.json", "runtime-bundle.json", "remote-disclosure.json"):
        _write(root / name, {"name": name})
    base, delta = b"common prompt", b"\n\ncandidate appendix"
    binary = root / "runtime-book"
    (binary / "current" / "prompts" / "judge").mkdir(parents=True)
    (binary / "treatment" / "prompts" / "judge").mkdir(parents=True)
    (binary / "current" / "prompts" / "judge" / "BINARY_EVALUATION_PROMPT.md").write_bytes(base + b"\n")
    (binary / "treatment" / "prompts" / "judge" / "BINARY_EVALUATION_PROMPT.md").write_bytes(base + delta + b"\n")
    s.SOURCE_PRIVATE_CORPUS_SHA256 = s.sha(root / "private-corpus.json")
    s.SOURCE_LEDGER_SHA256 = s.sha(root / "sealed-expected-ledger.json")
    s.CANDIDATE_APPENDIX_SHA256 = s.digest(delta.lstrip(b"\n"))
    s.APPENDIX_PROMPT_DELTA_SHA256 = s.digest(delta)


def test_provider_free_contract_forbids_execution_and_dspy() -> None:
    s = study()
    assert s.validate_package()["provider_calls"] == 0
    value = s.contract()["review_plan"]
    assert value["provider_execution_enabled"] is False
    assert value["dspy_enabled"] is False
    assert value["maximum_provider_calls"] == 2 and value["retries"] == 0
    assert value["attempt_lifecycle_policy"] == "terminal_sidecar_v1"
    assert tuple(value["mechanism_classifications"]) == (
        "FIXTURE_OR_LEDGER_AMBIGUITY", "SAME_INPUT_VARIANCE", "EVIDENCE_OR_VALIDATOR_DEFECT", "APPENDIX_HARM", "SHARED_PROMPT_GAP",
    )


def test_freeze_then_fake_sequential_execution_binds_state_before_mechanism_and_settles_aggregate_only(tmp_path: Path) -> None:
    s = study()
    source, packet = tmp_path / "source", tmp_path / "packet"
    _source_root(s, source)
    result = s.freeze(source, packet)
    assert result == {"status": "INCOMPLETE", "provider_calls": 0, "selected_fixture_count": 1, "frozen_reviews": 2}
    manifest = json.loads((packet / "audit-manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "INCOMPLETE" and manifest["maximum_provider_calls"] == 2
    assert all(len(row["source_slot_commitments"]) == 6 for row in manifest["candidates"])
    state = json.loads(next((packet / "review-plans").glob("*-state.json")).read_text(encoding="utf-8"))
    assert state["visibility"]["hidden"] == ["label", "verdicts", "arm", "appendix", "session"]
    assert "source_judgment" not in json.dumps(state["material"])
    mechanism = json.loads(next((packet / "review-plans").glob("*-mechanism.json")).read_text(encoding="utf-8"))
    assert len(mechanism["material"]["anonymized_receipts"]) == 6
    assert {row["variant"] for row in mechanism["material"]["anonymized_receipts"]} == {"variant-a", "variant-b"}
    assert tuple(mechanism["response_contract"]["classification"]) == s.MECHANISM_CLASSIFICATIONS
    public = (packet / "public-aggregate.json").read_text(encoding="utf-8")
    assert "H01" not in public and "H02" not in public and json.loads(public)["bound_receipts"] == 6
    disclosure = json.loads((packet / "remote-disclosure.json").read_text(encoding="utf-8"))
    assert disclosure["endpoint_profile"]["destination"] == "Codex CLI -> authenticated OpenAI service"
    assert disclosure["expected_ledger_sent"] is False and "sealed expected ledger" in disclosure["excluded_materials"]
    assert len(disclosure["candidate_transmissions"][0]["mechanism_review_transmission"]["anonymized_six_receipts"]) == 6
    assert s.dry_run(source, packet) == {"status": "INCOMPLETE", "provider_calls": 0, "drift": [], "mode": "dry_run"}
    calls = []

    def fake_runner(request):
        calls.append(request)
        result = {"reported": {"provider": "openai", "model": "gpt-5.6-sol", "reasoning_effort": "high", "session_id": "fake-" + request["review_id"]}}
        if request["review_type"] == "state_review":
            result["output"] = {"judgment_state": "YES", "evidence": "fixture evidence"}
        else:
            assert request["material"]["blinded_state_judgment"]["output"]["judgment_state"] == "YES"
            result["output"] = {"classification": "SAME_INPUT_VARIANCE", "evidence": "receipt evidence"}
        return result

    with pytest.raises(ValueError, match="arming"):
        s.execute(source, packet, allow_remote=True, acknowledged_zero_incremental_charge=True, runner_call=fake_runner)
    armed = s.arm(source, packet, confirm_pre_execution_contract=True)
    assert armed["status"] == "ARMED" and armed["provider_calls"] == 0
    executed = s.execute(source, packet, allow_remote=True, acknowledged_zero_incremental_charge=True, runner_call=fake_runner)
    assert executed["physical_provider_calls"] == 2
    assert [call["review_type"] for call in calls] == ["state_review", "mechanism_review"]
    assert all(call["model"]["enabled"] is True for call in calls)
    settled = s.settle(source, packet)
    assert settled["status"] == "SETTLED_AGGREGATE_ONLY" and settled["review_count"] == 2
    assert settled["mechanism_classifications"]["SAME_INPUT_VARIANCE"] == 1
    assert "H01" not in json.dumps(settled) and "H02" not in json.dumps(settled)
    successor = json.loads((packet / "public-aggregate.settled.v1.json").read_text(encoding="utf-8"))
    assert successor["status"] == "SETTLED_AGGREGATE_ONLY" and json.loads(public)["status"] == "INCOMPLETE"
    extra = packet / "review-runs" / executed["review_ids"][0] / "attempt-lifecycle" / "batch-0001" / "attempt-0002.settled.json"
    extra.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="run tree"):
        s._validate_review_receipt(packet, executed["review_ids"][0])
    assert s.settle(source, packet)["status"] == "INCOMPLETE"


def test_state_output_cannot_carry_provider_metadata_into_mechanism() -> None:
    s = study()
    request = {"review_type": "state_review"}
    with pytest.raises(ValueError, match="state review output"):
        s._validate_provider_result({"reported": {"provider": "openai", "model": "gpt-5.6-sol", "reasoning_effort": "high", "session_id": "provider-session"}, "output": {"judgment_state": "YES", "evidence": "quote", "session_id": "leak"}}, request)
    with pytest.raises(ValueError, match="prohibited provider metadata"):
        s._validate_provider_result({"reported": {"provider": "openai", "model": "gpt-5.6-sol", "reasoning_effort": "high", "session_id": "provider-session"}, "output": {"judgment_state": "YES", "evidence": "session_id: leak"}}, request)


def test_review_namespace_rejects_an_unexpected_global_run_id(tmp_path: Path) -> None:
    s = study()
    source, packet = tmp_path / "source", tmp_path / "packet"
    _source_root(s, source)
    s.freeze(source, packet)
    (packet / "review-runs" / "unexpected-review").mkdir(parents=True)
    manifest = json.loads((packet / "audit-manifest.json").read_text(encoding="utf-8"))
    with pytest.raises(ValueError, match="unexpected review-run"):
        s._validate_review_namespace(packet, manifest, require_all=False)


def test_any_source_or_packet_drift_is_incomplete(tmp_path: Path) -> None:
    s = study()
    source, packet = tmp_path / "source", tmp_path / "packet"
    _source_root(s, source)
    s.freeze(source, packet)
    response = next((source / "runs").glob("*/responses/batch-0001.json"))
    response.write_text("{}", encoding="utf-8")
    result = s.verify(source, packet)
    assert result["status"] == "INCOMPLETE" and result["drift"]
