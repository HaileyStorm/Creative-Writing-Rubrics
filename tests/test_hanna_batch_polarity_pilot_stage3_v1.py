from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import sys
import tempfile
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1] / "evaluation-results" / "hbq-hanna-batch-polarity-pilot-v1"
_PRIVATE_DIRS: list[tempfile.TemporaryDirectory[str]] = []
PREDECESSOR_ARTIFACTS = {
    "attempt_start": {"path_sha256": "461bcb6a941ce239ed05a127b1d83b477183e08b8be9e78cda79a9560d8d3861", "bytes": 13721, "sha256": "5e940109e14e6355853d3179463f01563559576e58f265f44be9122a9c547358"},
    "disclosure": {"path_sha256": "a4c7299535bd5c34a130e2a96fe4ba38c8fedf96cecbafcc6d38d95c01cef666", "bytes": 28945, "sha256": "6d4295f411944f8af15996824f68e3f18be12fdff3a183a713480df85b5d8cce"},
    "execution_contract": {"path_sha256": "89e4a4ae231b436467da554f4e5445f6e87cd9364fdfe5b83a7464dd6711362a", "bytes": 4251, "sha256": "783fbbbaf60f9f2b25a80783c97f2ad51f0893da29c4d722ef8d39f1ba55e1e9"},
    "failed_terminal": {"path_sha256": "7abf8b75d655c8e2b682c38398cf9ea0ae7f311f6ef7405a2f2ca10baa666bee", "bytes": 468, "sha256": "704835df9c7fbb3f292f4bd726cfa90c2aabaa8432d52fb866aabc7cff497ddf"},
    "freeze": {"path_sha256": "da077e68673cd8d1256e68c13a1dde07f27ff79728900dee7e21edb38670f8a5", "bytes": 534, "sha256": "d48256f3b9276a4ae704bc4c477bfe11a70315264e0955fc8281832863e35999"},
}


@pytest.fixture(autouse=True)
def _cleanup_private_roots():
    yield
    while _PRIVATE_DIRS:
        _PRIVATE_DIRS.pop().cleanup()


def _private(prefix: str) -> Path:
    directory = tempfile.TemporaryDirectory(prefix=prefix); _PRIVATE_DIRS.append(directory)
    return Path(directory.name)


def _load(name: str, filename: str):
    specification = importlib.util.spec_from_file_location(name, ROOT / filename)
    assert specification and specification.loader
    module = importlib.util.module_from_spec(specification); sys.modules[specification.name] = module
    specification.loader.exec_module(module); return module


def _digest(value: str | bytes) -> str:
    return hashlib.sha256(value.encode("utf-8") if isinstance(value, str) else value).hexdigest()


def _parent(study, root: Path):
    root.mkdir(parents=True, exist_ok=True)
    source, prompt, verdicts = root / "source.md", root / "prompt.md", root / "parent-verdicts.jsonl"
    source.write_text("A private source story.", encoding="utf-8"); prompt.write_text("A private source prompt.", encoding="utf-8")
    verdicts.write_text("".join(json.dumps({"question_id": item, "verdict": "YES", "confidence": 0.8}) + "\n" for item in study._full_question_ids()), encoding="utf-8")
    binding = study.fingerprint(study.CONTRACT_PATH)
    return {"parent_runtime": {"root": "fixture", "files": {}, "sha256": _digest("fixture-runtime")}, "parent_work": binding, "parent_matrix": binding, "parent_gate": binding, "parent_run": binding, "parent_score": binding, "parent_verdicts": study.fingerprint(verdicts), "parent_cell": {"item_id": "hanna-225", "artifact": study.fingerprint(source), "contexts": [study.fingerprint(prompt)]}, "parent_verifier": {"sessions": [{"session_id_sha256": _digest(f"parent-{index}")} for index in range(6)]}}


def _response(prompt: str, flip_first: bool = False) -> str:
    request = json.loads(prompt); values = []
    for index, question in enumerate(request["questions"]):
        verdict = "NO" if question["polarity"] == "negative_failure_condition" else "YES"
        if flip_first and index == 0: verdict = "YES" if verdict == "NO" else "NO"
        values.append({"question_id": question["question_id"], "verdict": verdict, "confidence": 0.8})
    return json.dumps({"verdicts": values}, separators=(",", ":"))


def _receipt(module, session: str):
    return {"command": ["codex", "exec", "<prompt-via-stdin>"], "reported": {"model": module.MODEL, "provider": "openai", "reasoning_effort": module.REASONING, "session_id": session}}


def _fake(module, seen, prefix: str, *, flip_at: int | None = None, duplicate: bool = False, fail_at: int | None = None):
    def call(**kwargs):
        assert (kwargs["output_dir"] / "attempt-start.json").is_file()
        seen.append(kwargs)
        if kwargs["batch_number"] == fail_at: raise RuntimeError("planned failure")
        session = f"{prefix}-same" if duplicate else f"{prefix}-{kwargs['batch_number']}"
        return _response(kwargs["prompt"], kwargs["batch_number"] == flip_at), _receipt(module, session)
    return call


def _fixture(tmp_path: Path, monkeypatch):
    stage1 = _load("hanna_stage3_fixture_stage1", "run_stage1.py")
    fast_questions = {question_id: f"Q:{question_id}" for question_id in stage1.study._full_question_ids()}
    monkeypatch.setattr(stage1.study, "_question_texts", lambda: fast_questions)
    monkeypatch.setattr(stage1.study, "_parent_binding", lambda *_: _parent(stage1.study, tmp_path / "parent")); monkeypatch.setattr(stage1.study, "_valid_parent_runtime", lambda _: True)
    stage1_work, stage1_private = tmp_path / "stage1-public", _private("hanna-stage3-stage1-")
    stage1.study.prepare(tmp_path / "parent-work", tmp_path / "parent-artifacts", tmp_path / "authority", tmp_path / "runtime", stage1_work)
    monkeypatch.setattr(stage1, "_predecessor_binding", lambda *_: {"revision": stage1.PREDECESSOR_REVISION, "work_root_path_sha256": stage1.PREDECESSOR_WORK_PATH_SHA256, "private_root_path_sha256": stage1.PREDECESSOR_PRIVATE_PATH_SHA256, "artifacts": PREDECESSOR_ARTIFACTS, "artifacts_sha256": stage1._sha256(stage1._canonical(PREDECESSOR_ARTIFACTS)), "failure": stage1.PREDECESSOR_FAILURE, "persisted_outcome": {"failed_terminal": True, "accepted_result": False, "retry": False}})
    first_calls = []; monkeypatch.setattr(stage1, "_call_codex", _fake(stage1, first_calls, "stage1"))
    assert stage1.execute_stage1(stage1_work, stage1_private, predecessor_work=tmp_path / "unused", predecessor_private_root=tmp_path / "unused-private")["calls"] == 60
    stage2 = _load("hanna_stage3_fixture_stage2", "run_stage2.py")
    monkeypatch.setattr(stage2.study, "_question_texts", lambda: fast_questions)
    monkeypatch.setattr(stage2.study, "_valid_parent_runtime", lambda _: True)
    stage2_work, stage2_private = tmp_path / "stage2-public", _private("hanna-stage3-stage2-"); stage2_work.mkdir(); shutil.copy2(stage1_work / "pilot-contract.json", stage2_work / "pilot-contract.json")
    second_calls = []; monkeypatch.setattr(stage2, "_call_codex", _fake(stage2, second_calls, "stage2", flip_at=1))
    assert stage2.execute_stage2(stage2_work, stage2_private, stage1_work=stage1_work, stage1_private_root=stage1_private)["status"] == "stage_3_required_signal"
    executor = _load("hanna_stage3_executor", "run_stage3.py")
    monkeypatch.setattr(executor.study, "_question_texts", lambda: fast_questions)
    monkeypatch.setattr(executor.study, "_valid_parent_runtime", lambda _: True)
    monkeypatch.setattr(executor.stage1, "_pushed_git_binding", lambda *_: {"revision": "f" * 40, "remote_ref": "origin/main", "complete_tracked_worktree_clean": True, "files": {}, "sha256": _digest("pushed-stage3")})
    work, private = tmp_path / "stage3-public", _private("hanna-stage3-private-"); work.mkdir(); shutil.copy2(stage2_work / "pilot-contract.json", work / "pilot-contract.json")
    return executor, work, private, stage2_work, stage2_private, stage1_work, stage1_private


def _run(executor, work, private, stage2_work, stage2_private, stage1_work, stage1_private, **kwargs):
    return executor.execute_stage3(work, private, stage2_work=stage2_work, stage2_private_root=stage2_private, stage1_work=stage1_work, stage1_private_root=stage1_private, **kwargs)


def test_stage3_prepare_and_dry_run_replay_full_prefix_without_contact(tmp_path, monkeypatch):
    executor, work, private, *roots = _fixture(tmp_path, monkeypatch); calls = []; monkeypatch.setattr(executor, "_call_codex", _fake(executor, calls, "stage3"))
    assert executor.dry_run(work, private, stage2_work=roots[0], stage2_private_root=roots[1], stage1_work=roots[2], stage1_private_root=roots[3])["scheduled_calls"] == 66
    result = executor.prepare(work, private, stage2_work=roots[0], stage2_private_root=roots[1], stage1_work=roots[2], stage1_private_root=roots[3])
    assert result["provider_calls"] == 0 and result["stage2_artifacts_sha256"] and not calls


def test_stage3_exact_order_chunks_and_terminal_gate(tmp_path, monkeypatch):
    executor, work, private, *roots = _fixture(tmp_path, monkeypatch); calls = []; monkeypatch.setattr(executor, "_call_codex", _fake(executor, calls, "stage3"))
    result = _run(executor, work, private, *roots)
    assert result == {"status": "stage_3_complete_development_only", "next_stage": None, "calls": 66, "rows": 11}
    assert [json.loads(call["prompt"])["condition_id"] for call in calls] == ["single_positive_batch1"] * 27 + ["single_negative_batch1"] * 27 + ["global_positive_batch32"] * 6 + ["global_negative_batch32"] * 6
    sizes = [len(json.loads(call["prompt"])["questions"]) for call in calls]
    assert all(size == 1 for size in sizes[:54]) and all(size == 32 for size in sizes[54:59] + sizes[60:65]) and 0 < sizes[59] < 32 and 0 < sizes[65] < 32
    raw = json.loads((private / executor.RAW_EVIDENCE_NAME).read_text(encoding="utf-8")); assert raw["row_count"] == 11 and len(raw["rows"]) == 11
    assert not (work / "stage4-evidence.json").exists()


@pytest.mark.parametrize("mutation, message", [("missing", "incomplete"), ("tamper", "terminal replay"), ("partial", "incomplete")])
def test_stage3_rejects_full_predecessor_damage_before_contact(tmp_path, monkeypatch, mutation, message):
    executor, work, private, stage2_work, stage2_private, stage1_work, stage1_private = _fixture(tmp_path, monkeypatch); calls = []; monkeypatch.setattr(executor, "_call_codex", _fake(executor, calls, "stage3"))
    if mutation == "missing": (stage2_work / executor.stage2.GATE_NAME).unlink()
    elif mutation == "tamper":
        path = stage2_private / executor.stage2.ATTEMPTS / "0001" / "terminal.json"; value = json.loads(path.read_text(encoding="utf-8")); value["transport_projection"] = "[]"; path.write_text(json.dumps(value), encoding="utf-8")
    else: (stage1_private / executor.stage1.ATTEMPTS / "0001" / "terminal.json").unlink()
    with pytest.raises(RuntimeError, match=message): _run(executor, work, private, stage2_work, stage2_private, stage1_work, stage1_private)
    assert not calls


def test_stage3_new_or_predecessor_session_collision_freezes_without_retry(tmp_path, monkeypatch):
    executor, work, private, *roots = _fixture(tmp_path, monkeypatch); calls = []; monkeypatch.setattr(executor, "_call_codex", _fake(executor, calls, "stage3", duplicate=True))
    with pytest.raises(RuntimeError, match="frozen"): _run(executor, work, private, *roots)
    assert len(calls) == 2 and json.loads((work / executor.FREEZE_NAME).read_text(encoding="utf-8"))["reason"] == "provider_or_response_failure"
    executor, work, private, stage2_work, stage2_private, stage1_work, stage1_private = _fixture(tmp_path / "predecessor", monkeypatch)
    terminal = stage2_private / executor.stage2.ATTEMPTS / "0001" / "terminal.json"; value = json.loads(terminal.read_text(encoding="utf-8")); value["provider_record"]["reported"]["session_id"] = "parent-0"; value["session_id_sha256"] = _digest("parent-0"); terminal.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(RuntimeError, match="terminal replay"): _run(executor, work, private, stage2_work, stage2_private, stage1_work, stage1_private)


def test_stage3_restart_provider_failure_completion_failure_and_public_privacy(tmp_path, monkeypatch):
    executor, work, private, *roots = _fixture(tmp_path, monkeypatch); calls = []; monkeypatch.setattr(executor, "_call_codex", _fake(executor, calls, "stage3")); _run(executor, work, private, *roots)
    first = private / executor.ATTEMPTS / "0001" / "terminal.json"; before = first.read_bytes(); monkeypatch.setattr(executor, "_call_codex", lambda **_: pytest.fail("restart contacted provider")); assert _run(executor, work, private, *roots)["calls"] == 66 and first.read_bytes() == before
    for path in work.rglob("*"):
        if path.is_file(): assert "A private source story." not in path.read_text(encoding="utf-8") and str(roots[0]) not in path.read_text(encoding="utf-8")
    executor, work, private, *roots = _fixture(tmp_path / "provider", monkeypatch); calls = []; monkeypatch.setattr(executor, "_call_codex", _fake(executor, calls, "stage3", fail_at=1))
    with pytest.raises(RuntimeError, match="provider_or_response_failure"): _run(executor, work, private, *roots)
    assert len(calls) == 1
    executor, work, private, *roots = _fixture(tmp_path / "completion", monkeypatch); calls = []; monkeypatch.setattr(executor, "_call_codex", _fake(executor, calls, "stage3")); monkeypatch.setattr(executor.study, "stage_gate", lambda *_: {"unexpected": True})
    with pytest.raises(RuntimeError, match="completion_validation_failure"): _run(executor, work, private, *roots)
    assert len(calls) == 66


@pytest.mark.parametrize("mutation", ("missing", "tampered"))
def test_stage3_restart_freezes_when_existing_terminal_lacks_its_bound_start(tmp_path, monkeypatch, mutation):
    executor, work, private, *roots = _fixture(tmp_path, monkeypatch)
    calls = []; monkeypatch.setattr(executor, "_call_codex", _fake(executor, calls, "stage3")); _run(executor, work, private, *roots)
    started = private / executor.ATTEMPTS / "0001" / "attempt-start.json"
    if mutation == "missing":
        started.unlink()
    else:
        value = json.loads(started.read_text(encoding="utf-8")); value["call_in_cell"] = 99; started.write_text(json.dumps(value), encoding="utf-8")
    monkeypatch.setattr(executor, "_call_codex", lambda **_: pytest.fail("restart contacted provider"))
    with pytest.raises(RuntimeError, match="invalid_existing_attempt"):
        _run(executor, work, private, *roots)
    assert json.loads((work / executor.FREEZE_NAME).read_text(encoding="utf-8"))["reason"] == "invalid_existing_attempt"


def test_stage3_requires_a_pushed_runtime_before_contact(tmp_path, monkeypatch):
    executor, work, private, *roots = _fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(executor.stage1, "_pushed_git_binding", lambda *_: (_ for _ in ()).throw(RuntimeError("not pushed")))
    with pytest.raises(RuntimeError, match="not pushed"):
        executor.prepare(work, private, stage2_work=roots[0], stage2_private_root=roots[1], stage1_work=roots[2], stage1_private_root=roots[3])
