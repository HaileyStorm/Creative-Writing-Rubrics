from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import tempfile
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1] / "evaluation-results" / "hbq-hanna-batch-polarity-pilot-v1"


def _executor():
    specification = importlib.util.spec_from_file_location("hanna_batch_polarity_stage1_executor", ROOT / "run_stage1.py")
    assert specification and specification.loader
    module = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = module
    specification.loader.exec_module(module)
    return module


def _digest(value: str | bytes) -> str:
    return hashlib.sha256(value.encode("utf-8") if isinstance(value, str) else value).hexdigest()


def _parent_binding(study, tmp_path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    binding = study.fingerprint(study.CONTRACT_PATH)
    source = tmp_path / "source.md"; source.write_text("A private source story.", encoding="utf-8")
    prompt = tmp_path / "prompt.md"; prompt.write_text("A private source prompt.", encoding="utf-8")
    verdicts = tmp_path / "parent-verdicts.jsonl"
    verdicts.write_text("".join(json.dumps({"question_id": question_id, "verdict": "YES", "confidence": 0.8}) + "\n" for question_id in study._full_question_ids()), encoding="utf-8")
    return {
        "parent_runtime": {"root": "fixture", "files": {}, "sha256": _digest("fixture-runtime")},
        "parent_work": binding, "parent_matrix": binding, "parent_gate": binding, "parent_run": binding, "parent_score": binding,
        "parent_verdicts": study.fingerprint(verdicts),
        "parent_cell": {"item_id": "hanna-225", "artifact": study.fingerprint(source), "contexts": [study.fingerprint(prompt)]},
        "parent_verifier": {"sessions": [{"session_id_sha256": _digest(f"parent-{index}")} for index in range(6)]},
    }


@pytest.fixture
def private_root():
    with tempfile.TemporaryDirectory(prefix="hbq-hanna-stage1-private-") as directory:
        yield Path(directory)


def _prepared(executor, tmp_path, monkeypatch, private_root):
    monkeypatch.setattr(executor.study, "_parent_binding", lambda *_: _parent_binding(executor.study, tmp_path))
    monkeypatch.setattr(executor.study, "_valid_parent_runtime", lambda _: True)
    work = tmp_path / "public-work"
    executor.study.prepare(tmp_path / "parent-work", tmp_path / "parent-artifacts", tmp_path / "authority", tmp_path / "runtime", work)
    monkeypatch.setattr(executor, "_pushed_git_binding", lambda *_: {"revision": "f" * 40, "remote_ref": "origin/main", "complete_tracked_worktree_clean": True, "files": {}, "sha256": _digest("pushed")})
    return work, private_root


def _response(prompt: str, *, confidence: float = 0.8) -> str:
    request = json.loads(prompt)
    values = []
    for question in request["questions"]:
        values.append({"question_id": question["question_id"], "verdict": "NO" if question["polarity"] == "negative_failure_condition" else "YES", "confidence": confidence})
    return json.dumps(values, separators=(",", ":"))


def _fake_factory(executor, seen, *, duplicate=False, malformed_at=None, fail_at=None):
    def fake(**kwargs):
        sequence = kwargs["batch_number"]
        root = kwargs["output_dir"]
        assert (root / "attempt-start.json").is_file(), "attempt start must precede provider contact"
        assert kwargs["attempt_number"] == 1
        assert kwargs["timeout"] == executor.TIMEOUT_SECONDS
        seen.append(kwargs)
        if fail_at == sequence:
            raise RuntimeError("simulated transport failure")
        content = "{}" if malformed_at == sequence else _response(kwargs["prompt"])
        session = "same-session" if duplicate else f"session-{sequence}"
        return content, {"command": ["codex", "exec", "<prompt-via-stdin>"], "reported": {"model": executor.MODEL, "provider": "openai", "reasoning_effort": executor.REASONING, "session_id": session}}
    return fake


def test_dry_run_has_exact_schedule_and_zero_provider_calls(tmp_path, monkeypatch, private_root):
    executor = _executor(); work, private = _prepared(executor, tmp_path, monkeypatch, private_root)
    calls = []
    monkeypatch.setattr(executor, "_call_codex", _fake_factory(executor, calls))
    result = executor.execute_stage1(work, private, dry_run_only=True)
    assert result == {"study_id": "hbq-hanna-batch-polarity-pilot-v1", "stage": 1, "provider_calls": 0, "scheduled_calls": 60, "conditions": ["global_negative_batch32", "single_positive_batch1", "single_negative_batch1"]}
    assert not calls and not (work / executor.EXECUTION_NAME).exists() and not (private / executor.ATTEMPTS).exists()


def test_stage1_makes_exactly_sixty_one_attempt_calls_with_reviewed_polarity_and_response_derived_rows(tmp_path, monkeypatch, private_root):
    executor = _executor(); work, private = _prepared(executor, tmp_path, monkeypatch, private_root)
    calls = []
    monkeypatch.setattr(executor, "_call_codex", _fake_factory(executor, calls))
    result = executor.execute_stage1(work, private)
    assert result == {"status": "stage_1_complete", "next_stage": 2, "calls": 60, "rows": 3}
    assert len(calls) == 60 and {call["batch_number"] for call in calls} == set(range(1, 61))
    assert all(json.loads(call["prompt"])["condition_id"] != "global_positive_batch32" for call in calls)
    global_negative = json.loads(calls[0]["prompt"])
    focal = set(executor.study.focal_question_ids())
    assert any(question["question_id"] not in focal and question["polarity"] == "positive" for question in global_negative["questions"])
    assert all(question["asked_question"] != question["canonical_question"] for question in global_negative["questions"] if question["question_id"] in focal)
    evidence = json.loads((work / executor.EVIDENCE_NAME).read_text(encoding="utf-8"))
    raw_evidence = json.loads((private / executor.RAW_EVIDENCE_NAME).read_text(encoding="utf-8"))
    assert evidence["row_count"] == 3 and evidence["call_count"] == 60 and len(evidence["rows"]) == 3
    assert evidence["private_raw_evidence"]["sha256"] == _digest((private / executor.RAW_EVIDENCE_NAME).read_bytes())
    assert {"prompt", "response", "verdicts", "provider_record"}.isdisjoint(evidence["rows"][0]["calls"][0])
    executor.study.verify_evidence(executor.study.load_plan(work), raw_evidence["rows"])
    assert json.loads(raw_evidence["rows"][0]["calls"][0]["response"]) == raw_evidence["rows"][0]["calls"][0]["verdicts"]
    gate = json.loads((work / executor.GATE_NAME).read_text(encoding="utf-8"))
    assert gate["status"] == "stage_1_complete" and gate["next_stage"] == 2 and gate["recommendation"] is None and gate["promotion"] == "forbidden"
    raw_response = raw_evidence["rows"][0]["calls"][0]["response"]
    for path in work.rglob("*"):
        if path.is_file():
            public = path.read_text(encoding="utf-8")
            assert "A private source story." not in public
            assert "A private source prompt." not in public
            assert raw_response not in public
            assert "provider_record" not in public
    assert raw_evidence["rows"][0]["calls"][0]["response"] == raw_response


def test_disclosure_is_committed_before_contact_and_private_prompt_is_not_projected_publicly(tmp_path, monkeypatch, private_root):
    executor = _executor(); work, private = _prepared(executor, tmp_path, monkeypatch, private_root)
    calls = []
    monkeypatch.setattr(executor, "_call_codex", _fake_factory(executor, calls, fail_at=1))
    with pytest.raises(RuntimeError, match="frozen"):
        executor.execute_stage1(work, private)
    disclosure = json.loads((work / executor.DISCLOSURE_NAME).read_text(encoding="utf-8"))
    contract = json.loads((work / executor.EXECUTION_NAME).read_text(encoding="utf-8"))
    assert len(disclosure["outbound_requests"]) == 60
    assert disclosure["outbound_requests"][0]["sequence"] == 1
    assert "A private source story." not in (work / executor.DISCLOSURE_NAME).read_text(encoding="utf-8")
    assert disclosure["outbound_artifacts"]["source"]["sha256"]
    assert "path" not in disclosure["outbound_artifacts"]["source"]
    assert contract["disclosure"]["sha256"] == _digest((work / executor.DISCLOSURE_NAME).read_bytes())
    assert contract["pushed_git"]["complete_tracked_worktree_clean"] is True
    started = json.loads((private / "attempts" / "0001" / "attempt-start.json").read_text(encoding="utf-8"))
    assert started["prompt"] == calls[0]["prompt"]


def test_private_raw_root_inside_the_repository_is_rejected_even_for_dry_run(tmp_path, monkeypatch, private_root):
    executor = _executor(); work, _ = _prepared(executor, tmp_path, monkeypatch, private_root)
    with pytest.raises(RuntimeError, match="must not be inside the repository"):
        executor.dry_run(work, executor.REPOSITORY / "private-stage1")


def test_duplicate_session_or_malformed_response_freezes_without_retry(tmp_path, monkeypatch, private_root):
    executor = _executor(); work, private = _prepared(executor, tmp_path, monkeypatch, private_root)
    calls = []
    monkeypatch.setattr(executor, "_call_codex", _fake_factory(executor, calls, duplicate=True))
    with pytest.raises(RuntimeError, match="frozen"):
        executor.execute_stage1(work, private)
    assert len(calls) == 2
    freeze = json.loads((work / executor.FREEZE_NAME).read_text(encoding="utf-8"))
    assert freeze["status"] == "frozen_failure" and freeze["reason"] == "provider_or_response_failure"
    with pytest.raises(RuntimeError, match="frozen"):
        executor.execute_stage1(work, private)
    executor = _executor(); work, private = _prepared(executor, tmp_path / "malformed", monkeypatch, private_root / "malformed")
    calls = []
    monkeypatch.setattr(executor, "_call_codex", _fake_factory(executor, calls, malformed_at=1))
    with pytest.raises(RuntimeError, match="frozen"):
        executor.execute_stage1(work, private)
    assert len(calls) == 1
    executor = _executor(); work, private = _prepared(executor, tmp_path / "receipt", monkeypatch, private_root / "receipt")
    calls = []
    def bad_receipt(**kwargs):
        calls.append(kwargs)
        return _response(kwargs["prompt"]), {"reported": {"model": executor.MODEL, "provider": "openai", "reasoning_effort": executor.REASONING, "session_id": "receipt-session"}}
    monkeypatch.setattr(executor, "_call_codex", bad_receipt)
    with pytest.raises(RuntimeError, match="frozen"):
        executor.execute_stage1(work, private)
    assert len(calls) == 1


def test_restart_preserves_completed_artifacts_and_never_recalls_provider(tmp_path, monkeypatch, private_root):
    executor = _executor(); work, private = _prepared(executor, tmp_path, monkeypatch, private_root)
    calls = []
    monkeypatch.setattr(executor, "_call_codex", _fake_factory(executor, calls))
    executor.execute_stage1(work, private)
    tracked = [work / executor.DISCLOSURE_NAME, work / executor.EXECUTION_NAME, work / executor.EVIDENCE_NAME, work / executor.GATE_NAME, private / "attempts" / "0001" / "attempt-start.json", private / "attempts" / "0001" / "terminal.json"]
    before = [(path.read_bytes(), path.stat().st_mtime_ns) for path in tracked]
    monkeypatch.setattr(executor, "_call_codex", lambda **_: pytest.fail("completed restart called provider"))
    assert executor.execute_stage1(work, private) == {"status": "stage_1_complete", "next_stage": 2, "calls": 60, "rows": 3}
    assert [(path.read_bytes(), path.stat().st_mtime_ns) for path in tracked] == before


def test_restart_resumes_only_the_first_unsent_call_without_rewriting_prior_terminal(tmp_path, monkeypatch, private_root):
    executor = _executor(); work, private = _prepared(executor, tmp_path, monkeypatch, private_root)
    plan, schedule, _ = executor._bootstrap(work, private, executor.REPOSITORY, dry_run=False)
    first = schedule[0]
    root, started, terminal = executor._attempt_paths(private, 1)
    executor._immutable_json(started, {"format_version": 1, "status": "started", "sequence": 1, "condition_id": first["condition_id"], "repetition": 1, "call_in_cell": 1, "question_ids": first["question_ids"], "prompt": first["prompt"], "prompt_sha256": first["prompt_sha256"], "response_schema": executor._fingerprint(executor.SCHEMA_PATH), "provider": {"provider": "codex", "model": executor.MODEL, "reasoning": executor.REASONING, "ephemeral": True, "attempt_number": 1}})
    executor._immutable_json(terminal, executor._terminal_success(first, _response(first["prompt"]), {"command": ["codex", "exec", "<prompt-via-stdin>"], "reported": {"model": executor.MODEL, "provider": "openai", "reasoning_effort": executor.REASONING, "session_id": "session-1"}}))
    prior = (terminal.read_bytes(), terminal.stat().st_mtime_ns)
    calls = []
    monkeypatch.setattr(executor, "_call_codex", _fake_factory(executor, calls))
    assert executor.execute_stage1(work, private) == {"status": "stage_1_complete", "next_stage": 2, "calls": 60, "rows": 3}
    assert [call["batch_number"] for call in calls] == list(range(2, 61))
    assert (terminal.read_bytes(), terminal.stat().st_mtime_ns) == prior


def test_started_without_terminal_and_explicit_provider_failure_are_terminal_freezes(tmp_path, monkeypatch, private_root):
    executor = _executor(); work, private = _prepared(executor, tmp_path, monkeypatch, private_root)
    plan = executor.study.load_plan(work); first = executor._schedule(plan)[0]
    root, started, _ = executor._attempt_paths(private, 1)
    executor._immutable_json(started, {"format_version": 1, "status": "started", "sequence": 1})
    with pytest.raises(RuntimeError, match="started_without_terminal"):
        executor.execute_stage1(work, private)
    assert json.loads((work / executor.FREEZE_NAME).read_text(encoding="utf-8"))["reason"] == "started_without_terminal"
    executor = _executor(); work, private = _prepared(executor, tmp_path / "provider", monkeypatch, private_root / "provider")
    calls = []
    monkeypatch.setattr(executor, "_call_codex", _fake_factory(executor, calls, fail_at=1))
    with pytest.raises(RuntimeError, match="frozen"):
        executor.execute_stage1(work, private)
    assert len(calls) == 1
    assert json.loads((private / "attempts" / "0001" / "terminal.json").read_text(encoding="utf-8"))["status"] == "failed"
