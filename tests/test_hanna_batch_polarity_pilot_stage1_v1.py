from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
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


def _write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def _predecessor(executor, work: Path, private: Path, plan) -> None:
    schedule = executor._schedule(plan)
    first = schedule[0]
    disclosure = {
        "format_version": 1, "study_id": plan["study_id"], "stage": 1,
        "private_raw_root": {"path_sha256": executor._sha256(str(private.resolve()))},
        "outbound_requests": [{"sequence": 1, "condition_id": first["condition_id"], "prompt_sha256": first["prompt_sha256"]}],
    }
    _write_json(work / executor.DISCLOSURE_NAME, disclosure)
    contract = {
        "format_version": 1, "study_id": plan["study_id"], "stage": 1,
        "disclosure": executor._fingerprint(work / executor.DISCLOSURE_NAME),
        "private_raw_root_sha256": executor._sha256(str(private.resolve())),
        "response_schema": {"sha256": executor.PREDECESSOR_SCHEMA_SHA256},
        "executor": {"sha256": executor.PREDECESSOR_EXECUTOR_SHA256},
        "pushed_git": {"revision": executor.PREDECESSOR_REVISION, "complete_tracked_worktree_clean": True, "files": {"evaluation-results/hbq-hanna-batch-polarity-pilot-v1/run_stage1.py": {"sha256": executor.PREDECESSOR_EXECUTOR_SHA256}, "evaluation-results/hbq-hanna-batch-polarity-pilot-v1/stage1-response.schema.json": {"sha256": executor.PREDECESSOR_SCHEMA_SHA256}}},
    }
    _write_json(work / executor.EXECUTION_NAME, contract)
    _write_json(private / executor.ATTEMPTS / "0001" / "attempt-start.json", {"format_version": 1, "status": "started", "sequence": 1, "condition_id": "global_negative_batch32", "repetition": 1, "prompt_sha256": first["prompt_sha256"], "response_schema": {"sha256": executor.PREDECESSOR_SCHEMA_SHA256}})
    error_sha256 = _digest("fixture predecessor failure")
    _write_json(private / executor.ATTEMPTS / "0001" / "terminal.json", {"format_version": 1, "status": "failed", "sequence": 1, "prompt_sha256": first["prompt_sha256"], "response_sha256": None, "error_sha256": error_sha256, "provider_record": {"reported": {"session_id": "predecessor-private-session"}}})
    _write_json(work / executor.FREEZE_NAME, {"format_version": 1, "study_id": plan["study_id"], "stage": 1, "status": "frozen_failure", "reason": "provider_or_response_failure", "sequence": 1, "prompt_sha256": first["prompt_sha256"], "response_sha256": None, "detail_sha256": error_sha256, "private_raw_root_sha256": executor._sha256(str(private.resolve()))})


def _prepared(executor, tmp_path, monkeypatch, private_root):
    monkeypatch.setattr(executor.study, "_parent_binding", lambda *_: _parent_binding(executor.study, tmp_path))
    monkeypatch.setattr(executor.study, "_valid_parent_runtime", lambda _: True)
    work = tmp_path / "public-work"
    executor.study.prepare(tmp_path / "parent-work", tmp_path / "parent-artifacts", tmp_path / "authority", tmp_path / "runtime", work)
    predecessor_work, predecessor_private = tmp_path / "predecessor-work", private_root / "predecessor-private"
    _predecessor(executor, predecessor_work, predecessor_private, executor.study.load_plan(work))
    monkeypatch.setattr(executor, "PREDECESSOR_WORK_PATH_SHA256", executor._sha256(str(predecessor_work.resolve())))
    monkeypatch.setattr(executor, "PREDECESSOR_PRIVATE_PATH_SHA256", executor._sha256(str(predecessor_private.resolve())))
    executor._fixture_predecessor_work = predecessor_work
    executor._fixture_predecessor_private_root = predecessor_private
    monkeypatch.setattr(executor, "_pushed_git_binding", lambda *_: {"revision": "f" * 40, "remote_ref": "origin/main", "complete_tracked_worktree_clean": True, "files": {}, "sha256": _digest("pushed")})
    return work, private_root / "successor-private"


def _run(executor, work: Path, private: Path, **kwargs):
    return executor.execute_stage1(work, private, predecessor_work=executor._fixture_predecessor_work, predecessor_private_root=executor._fixture_predecessor_private_root, **kwargs)


def _dry(executor, work: Path, private: Path):
    return executor.dry_run(work, private, predecessor_work=executor._fixture_predecessor_work, predecessor_private_root=executor._fixture_predecessor_private_root)


def _prepare_successor(executor, work: Path, private: Path):
    return executor.prepare(work, private, predecessor_work=executor._fixture_predecessor_work, predecessor_private_root=executor._fixture_predecessor_private_root)


def _response(prompt: str, *, confidence: float = 0.8) -> str:
    request = json.loads(prompt)
    values = []
    for question in request["questions"]:
        values.append({"question_id": question["question_id"], "verdict": "NO" if question["polarity"] == "negative_failure_condition" else "YES", "confidence": confidence})
    return json.dumps({"verdicts": values}, separators=(",", ":"))


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
    result = _run(executor, work, private, dry_run_only=True)
    assert result == {"study_id": "hbq-hanna-batch-polarity-pilot-v1", "stage": 1, "provider_calls": 0, "scheduled_calls": 60, "conditions": ["global_negative_batch32", "single_positive_batch1", "single_negative_batch1"]}
    assert not calls and not (work / executor.EXECUTION_NAME).exists() and not (private / executor.ATTEMPTS).exists()


def test_prepare_requires_predecessor_and_makes_zero_provider_calls(tmp_path, monkeypatch, private_root):
    executor = _executor(); work, private = _prepared(executor, tmp_path, monkeypatch, private_root)
    calls = []
    monkeypatch.setattr(executor, "_call_codex", _fake_factory(executor, calls))
    prepared = _prepare_successor(executor, work, private)
    assert prepared["provider_calls"] == 0 and prepared["scheduled_calls"] == 60
    assert prepared["predecessor_artifacts_sha256"]
    assert not calls and (work / executor.EXECUTION_NAME).is_file() and (work / executor.DISCLOSURE_NAME).is_file()


def test_object_envelope_schema_and_outbound_prompt_bytes_are_frozen(tmp_path, monkeypatch, private_root):
    executor = _executor(); work, private = _prepared(executor, tmp_path, monkeypatch, private_root)
    schema = json.loads(executor.SCHEMA_PATH.read_text(encoding="utf-8"))
    assert schema["type"] == "object" and schema["required"] == ["verdicts"] and schema["additionalProperties"] is False
    assert schema["properties"]["verdicts"]["type"] == "array"
    calls = []
    monkeypatch.setattr(executor, "_call_codex", _fake_factory(executor, calls))
    _run(executor, work, private)
    plan = executor.study.load_plan(work)
    first_cell = next(cell for cell in plan["cells"] if cell["condition_id"] == "global_negative_batch32" and cell["repetition"] == 1)
    first_ids = executor.study._chunks(first_cell["question_ids"], 32)[0]
    assert calls[0]["prompt"] == executor.study.rendered_prompt(plan, first_cell, first_ids)
    contract = json.loads((work / executor.EXECUTION_NAME).read_text(encoding="utf-8"))
    assert contract["transport"]["generation"] == "object-envelope-successor-v2"
    assert contract["transport"]["predecessor_failure"] == executor.PREDECESSOR_FAILURE
    assert contract["predecessor"]["revision"] == executor.PREDECESSOR_REVISION
    assert contract["predecessor"]["persisted_outcome"] == {"failed_terminal": True, "accepted_result": False, "retry": False}
    public_contract = (work / executor.EXECUTION_NAME).read_text(encoding="utf-8")
    assert str(executor._fixture_predecessor_work) not in public_contract
    assert str(executor._fixture_predecessor_private_root) not in public_contract
    assert "predecessor-private-session" not in public_contract


def test_successor_requires_exact_cross_bound_predecessor_and_rejects_tampering(tmp_path, monkeypatch, private_root):
    executor = _executor(); work, private = _prepared(executor, tmp_path, monkeypatch, private_root)
    binding = executor._predecessor_binding(executor._fixture_predecessor_work, executor._fixture_predecessor_private_root)
    assert set(binding["artifacts"]) == {"execution_contract", "disclosure", "freeze", "attempt_start", "failed_terminal"}
    assert all("path" not in artifact for artifact in binding["artifacts"].values())
    with pytest.raises(RuntimeError, match="exact frozen predecessor"):
        executor.dry_run(work, private, predecessor_work=tmp_path / "wrong", predecessor_private_root=executor._fixture_predecessor_private_root)
    freeze_path = executor._fixture_predecessor_work / executor.FREEZE_NAME
    freeze = json.loads(freeze_path.read_text(encoding="utf-8"))
    freeze["prompt_sha256"] = "0" * 64
    freeze_path.write_text(json.dumps(freeze), encoding="utf-8")
    with pytest.raises(RuntimeError, match="freeze cross-binding"):
        _dry(executor, work, private)


def test_predecessor_error_commitments_and_path_privacy_are_strict(tmp_path, monkeypatch, private_root):
    executor = _executor(); work, private = _prepared(executor, tmp_path, monkeypatch, private_root)
    path_hashes = [executor.PREDECESSOR_WORK_PATH_SHA256, executor.PREDECESSOR_PRIVATE_PATH_SHA256]
    assert all(isinstance(value, str) and len(value) == 64 and value == value.lower() and all(character in "0123456789abcdef" for character in value) for value in path_hashes)
    _prepare_successor(executor, work, private)
    for path in work.rglob("*"):
        if path.is_file():
            public = path.read_text(encoding="utf-8")
            assert str(executor._fixture_predecessor_work) not in public
            assert str(executor._fixture_predecessor_private_root) not in public
    terminal_path = executor._fixture_predecessor_private_root / executor.ATTEMPTS / "0001" / "terminal.json"
    terminal = json.loads(terminal_path.read_text(encoding="utf-8"))
    terminal["error_sha256"] = "0" * 64
    terminal_path.write_text(json.dumps(terminal), encoding="utf-8")
    with pytest.raises(RuntimeError, match="freeze cross-binding"):
        _dry(executor, work, private)
    repository = ROOT.parents[1]
    tracked = subprocess.run(["git", "-C", str(repository), "ls-files"], text=True, encoding="utf-8", capture_output=True, check=True).stdout.splitlines()
    absolute_markers = [chr(67) + ":" + "\\" + "Users" + "\\", chr(67) + ":" + "/" + "Users" + "/"]
    for relative in tracked:
        path = repository / relative
        if path.suffix in {".py", ".json"}:
            text = path.read_text(encoding="utf-8")
            assert all(marker not in text for marker in absolute_markers)


def test_stage1_makes_exactly_sixty_one_attempt_calls_with_reviewed_polarity_and_response_derived_rows(tmp_path, monkeypatch, private_root):
    executor = _executor(); work, private = _prepared(executor, tmp_path, monkeypatch, private_root)
    calls = []
    monkeypatch.setattr(executor, "_call_codex", _fake_factory(executor, calls))
    result = _run(executor, work, private)
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
    terminal = json.loads((private / "attempts" / "0001" / "terminal.json").read_text(encoding="utf-8"))
    assert json.loads(terminal["raw_object_response"]) == {"verdicts": raw_evidence["rows"][0]["calls"][0]["verdicts"]}
    assert json.loads(terminal["transport_projection"]) == raw_evidence["rows"][0]["calls"][0]["verdicts"]
    assert terminal["transport_projection_rule_sha256"] == executor._sha256(executor._canonical(executor.TRANSPORT_PROJECTION_RULE))
    gate = json.loads((work / executor.GATE_NAME).read_text(encoding="utf-8"))
    assert gate["status"] == "stage_1_complete" and gate["next_stage"] == 2 and gate["recommendation"] is None and gate["promotion"] == "forbidden"
    raw_response = terminal["raw_object_response"]
    for path in work.rglob("*"):
        if path.is_file():
            public = path.read_text(encoding="utf-8")
            assert "A private source story." not in public
            assert "A private source prompt." not in public
            assert raw_response not in public
            assert "provider_record" not in public
            assert "predecessor-private-session" not in public
    assert raw_evidence["rows"][0]["calls"][0]["response"] == terminal["transport_projection"]


def test_disclosure_is_committed_before_contact_and_private_prompt_is_not_projected_publicly(tmp_path, monkeypatch, private_root):
    executor = _executor(); work, private = _prepared(executor, tmp_path, monkeypatch, private_root)
    calls = []
    monkeypatch.setattr(executor, "_call_codex", _fake_factory(executor, calls, fail_at=1))
    with pytest.raises(RuntimeError, match="frozen"):
        _run(executor, work, private)
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
        _dry(executor, work, executor.REPOSITORY / "private-stage1")


def test_duplicate_session_or_malformed_response_freezes_without_retry(tmp_path, monkeypatch, private_root):
    executor = _executor(); work, private = _prepared(executor, tmp_path, monkeypatch, private_root)
    calls = []
    monkeypatch.setattr(executor, "_call_codex", _fake_factory(executor, calls, duplicate=True))
    with pytest.raises(RuntimeError, match="frozen"):
        _run(executor, work, private)
    assert len(calls) == 2
    freeze = json.loads((work / executor.FREEZE_NAME).read_text(encoding="utf-8"))
    assert freeze["status"] == "frozen_failure" and freeze["reason"] == "provider_or_response_failure"
    with pytest.raises(RuntimeError, match="frozen"):
        _run(executor, work, private)
    executor = _executor(); work, private = _prepared(executor, tmp_path / "malformed", monkeypatch, private_root / "malformed")
    calls = []
    monkeypatch.setattr(executor, "_call_codex", _fake_factory(executor, calls, malformed_at=1))
    with pytest.raises(RuntimeError, match="frozen"):
        _run(executor, work, private)
    assert len(calls) == 1
    executor = _executor(); work, private = _prepared(executor, tmp_path / "root-array", monkeypatch, private_root / "root-array")
    calls = []
    def old_root_array(**kwargs):
        calls.append(kwargs)
        return json.dumps(json.loads(_response(kwargs["prompt"]))["verdicts"]), {"command": ["codex", "exec", "<prompt-via-stdin>"], "reported": {"model": executor.MODEL, "provider": "openai", "reasoning_effort": executor.REASONING, "session_id": "old-schema-session"}}
    monkeypatch.setattr(executor, "_call_codex", old_root_array)
    with pytest.raises(RuntimeError, match="frozen"):
        _run(executor, work, private)
    assert len(calls) == 1
    executor = _executor(); work, private = _prepared(executor, tmp_path / "receipt", monkeypatch, private_root / "receipt")
    calls = []
    def bad_receipt(**kwargs):
        calls.append(kwargs)
        return _response(kwargs["prompt"]), {"reported": {"model": executor.MODEL, "provider": "openai", "reasoning_effort": executor.REASONING, "session_id": "receipt-session"}}
    monkeypatch.setattr(executor, "_call_codex", bad_receipt)
    with pytest.raises(RuntimeError, match="frozen"):
        _run(executor, work, private)
    assert len(calls) == 1


def test_restart_preserves_completed_artifacts_and_never_recalls_provider(tmp_path, monkeypatch, private_root):
    executor = _executor(); work, private = _prepared(executor, tmp_path, monkeypatch, private_root)
    calls = []
    monkeypatch.setattr(executor, "_call_codex", _fake_factory(executor, calls))
    _run(executor, work, private)
    tracked = [work / executor.DISCLOSURE_NAME, work / executor.EXECUTION_NAME, work / executor.EVIDENCE_NAME, work / executor.GATE_NAME, private / "attempts" / "0001" / "attempt-start.json", private / "attempts" / "0001" / "terminal.json"]
    before = [(path.read_bytes(), path.stat().st_mtime_ns) for path in tracked]
    monkeypatch.setattr(executor, "_call_codex", lambda **_: pytest.fail("completed restart called provider"))
    assert _run(executor, work, private) == {"status": "stage_1_complete", "next_stage": 2, "calls": 60, "rows": 3}
    assert [(path.read_bytes(), path.stat().st_mtime_ns) for path in tracked] == before


def test_restart_resumes_only_the_first_unsent_call_without_rewriting_prior_terminal(tmp_path, monkeypatch, private_root):
    executor = _executor(); work, private = _prepared(executor, tmp_path, monkeypatch, private_root)
    plan, schedule, _ = executor._bootstrap(work, private, executor._fixture_predecessor_work, executor._fixture_predecessor_private_root, executor.REPOSITORY, dry_run=False)
    first = schedule[0]
    root, started, terminal = executor._attempt_paths(private, 1)
    executor._immutable_json(started, {"format_version": 1, "status": "started", "sequence": 1, "condition_id": first["condition_id"], "repetition": 1, "call_in_cell": 1, "question_ids": first["question_ids"], "prompt": first["prompt"], "prompt_sha256": first["prompt_sha256"], "response_schema": executor._fingerprint(executor.SCHEMA_PATH), "provider": {"provider": "codex", "model": executor.MODEL, "reasoning": executor.REASONING, "ephemeral": True, "attempt_number": 1}})
    executor._immutable_json(terminal, executor._terminal_success(first, _response(first["prompt"]), {"command": ["codex", "exec", "<prompt-via-stdin>"], "reported": {"model": executor.MODEL, "provider": "openai", "reasoning_effort": executor.REASONING, "session_id": "session-1"}}))
    prior = (terminal.read_bytes(), terminal.stat().st_mtime_ns)
    calls = []
    monkeypatch.setattr(executor, "_call_codex", _fake_factory(executor, calls))
    assert _run(executor, work, private) == {"status": "stage_1_complete", "next_stage": 2, "calls": 60, "rows": 3}
    assert [call["batch_number"] for call in calls] == list(range(2, 61))
    assert (terminal.read_bytes(), terminal.stat().st_mtime_ns) == prior


def test_restart_rederives_transport_projection_and_freezes_tampering(tmp_path, monkeypatch, private_root):
    executor = _executor(); work, private = _prepared(executor, tmp_path, monkeypatch, private_root)
    calls = []
    monkeypatch.setattr(executor, "_call_codex", _fake_factory(executor, calls))
    _run(executor, work, private)
    terminal_path = private / "attempts" / "0001" / "terminal.json"
    terminal = json.loads(terminal_path.read_text(encoding="utf-8"))
    terminal["transport_projection"] = "[]"
    terminal["transport_projection_sha256"] = executor._sha256("[]")
    terminal_path.write_text(json.dumps(terminal), encoding="utf-8")
    monkeypatch.setattr(executor, "_call_codex", lambda **_: pytest.fail("tampered restart called provider"))
    with pytest.raises(RuntimeError, match="invalid_existing_terminal"):
        _run(executor, work, private)
    assert json.loads((work / executor.FREEZE_NAME).read_text(encoding="utf-8"))["reason"] == "invalid_existing_terminal"


def test_started_without_terminal_and_explicit_provider_failure_are_terminal_freezes(tmp_path, monkeypatch, private_root):
    executor = _executor(); work, private = _prepared(executor, tmp_path, monkeypatch, private_root)
    plan = executor.study.load_plan(work); first = executor._schedule(plan)[0]
    root, started, _ = executor._attempt_paths(private, 1)
    executor._immutable_json(started, {"format_version": 1, "status": "started", "sequence": 1})
    with pytest.raises(RuntimeError, match="started_without_terminal"):
        _run(executor, work, private)
    assert json.loads((work / executor.FREEZE_NAME).read_text(encoding="utf-8"))["reason"] == "started_without_terminal"
    executor = _executor(); work, private = _prepared(executor, tmp_path / "provider", monkeypatch, private_root / "provider")
    calls = []
    monkeypatch.setattr(executor, "_call_codex", _fake_factory(executor, calls, fail_at=1))
    with pytest.raises(RuntimeError, match="frozen"):
        _run(executor, work, private)
    assert len(calls) == 1
    assert json.loads((private / "attempts" / "0001" / "terminal.json").read_text(encoding="utf-8"))["status"] == "failed"
