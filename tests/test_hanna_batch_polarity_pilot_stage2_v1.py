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


def _private_root(prefix: str) -> Path:
    directory = tempfile.TemporaryDirectory(prefix=prefix)
    _PRIVATE_DIRS.append(directory)
    return Path(directory.name)


def _load(name: str, filename: str):
    specification = importlib.util.spec_from_file_location(name, ROOT / filename)
    assert specification and specification.loader
    module = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = module
    specification.loader.exec_module(module)
    return module


def _digest(value: str | bytes) -> str:
    return hashlib.sha256(value.encode("utf-8") if isinstance(value, str) else value).hexdigest()


def _parent_binding(study, root: Path):
    root.mkdir(parents=True, exist_ok=True)
    source, prompt, verdicts = root / "source.md", root / "prompt.md", root / "parent-verdicts.jsonl"
    source.write_text("A private source story.", encoding="utf-8")
    prompt.write_text("A private source prompt.", encoding="utf-8")
    verdicts.write_text("".join(json.dumps({"question_id": question_id, "verdict": "YES", "confidence": 0.8}) + "\n" for question_id in study._full_question_ids()), encoding="utf-8")
    binding = study.fingerprint(study.CONTRACT_PATH)
    return {"parent_runtime": {"root": "fixture", "files": {}, "sha256": _digest("fixture-runtime")}, "parent_work": binding, "parent_matrix": binding, "parent_gate": binding, "parent_run": binding, "parent_score": binding, "parent_verdicts": study.fingerprint(verdicts), "parent_cell": {"item_id": "hanna-225", "artifact": study.fingerprint(source), "contexts": [study.fingerprint(prompt)]}, "parent_verifier": {"sessions": [{"session_id_sha256": _digest(f"parent-{index}")} for index in range(6)]}}


def _response(prompt: str, *, flip_first: bool = False) -> str:
    request = json.loads(prompt)
    values = []
    for index, question in enumerate(request["questions"]):
        verdict = "NO" if question["polarity"] == "negative_failure_condition" else "YES"
        if flip_first and index == 0:
            verdict = "YES" if verdict == "NO" else "NO"
        values.append({"question_id": question["question_id"], "verdict": verdict, "confidence": 0.8})
    return json.dumps({"verdicts": values}, separators=(",", ":"))


def _receipt(module, session: str):
    return {"command": ["codex", "exec", "<prompt-via-stdin>"], "reported": {"model": module.MODEL, "provider": "openai", "reasoning_effort": module.REASONING, "session_id": session}}


def _fake(module, seen, *, prefix: str, flip_at: int | None = None, duplicate_session: bool = False):
    def call(**kwargs):
        assert (kwargs["output_dir"] / "attempt-start.json").is_file()
        assert kwargs["attempt_number"] == 1 and kwargs["timeout"] == module.TIMEOUT_SECONDS
        seen.append(kwargs)
        session = f"{prefix}-same" if duplicate_session else f"{prefix}-{kwargs['batch_number']}"
        return _response(kwargs["prompt"], flip_first=kwargs["batch_number"] == flip_at), _receipt(module, session)
    return call


def _fixture_stage1(tmp_path: Path, monkeypatch):
    stage1 = _load("hanna_batch_polarity_stage2_fixture_stage1", "run_stage1.py")
    monkeypatch.setattr(stage1.study, "_parent_binding", lambda *_: _parent_binding(stage1.study, tmp_path / "parent"))
    monkeypatch.setattr(stage1.study, "_valid_parent_runtime", lambda _: True)
    work = tmp_path / "stage1-public"; private = _private_root("hbq-hanna-stage2-fixture-stage1-private-")
    stage1.study.prepare(tmp_path / "parent-work", tmp_path / "parent-artifacts", tmp_path / "authority", tmp_path / "runtime", work)
    monkeypatch.setattr(stage1, "_predecessor_binding", lambda *_: {"revision": stage1.PREDECESSOR_REVISION, "work_root_path_sha256": stage1.PREDECESSOR_WORK_PATH_SHA256, "private_root_path_sha256": stage1.PREDECESSOR_PRIVATE_PATH_SHA256, "artifacts": PREDECESSOR_ARTIFACTS, "artifacts_sha256": stage1._sha256(stage1._canonical(PREDECESSOR_ARTIFACTS)), "failure": stage1.PREDECESSOR_FAILURE, "persisted_outcome": {"failed_terminal": True, "accepted_result": False, "retry": False}})
    calls = []; monkeypatch.setattr(stage1, "_call_codex", _fake(stage1, calls, prefix="stage1"))
    assert stage1.execute_stage1(work, private, predecessor_work=tmp_path / "unused-predecessor", predecessor_private_root=tmp_path / "unused-predecessor-private") == {"status": "stage_1_complete", "next_stage": 2, "calls": 60, "rows": 3}
    assert len(calls) == 60
    return stage1, work, private


def _fixture_stage2(tmp_path: Path, monkeypatch):
    _, stage1_work, stage1_private = _fixture_stage1(tmp_path, monkeypatch)
    executor = _load("hanna_batch_polarity_stage2_executor", "run_stage2.py")
    monkeypatch.setattr(executor.study, "_valid_parent_runtime", lambda _: True)
    work, private = tmp_path / "stage2-public", _private_root("hbq-hanna-stage2-fixture-private-")
    work.mkdir(); shutil.copy2(stage1_work / "pilot-contract.json", work / "pilot-contract.json")
    monkeypatch.setattr(executor.stage1, "_pushed_git_binding", lambda *_: {"revision": "f" * 40, "remote_ref": "origin/main", "complete_tracked_worktree_clean": True, "files": {}, "sha256": _digest("pushed")})
    return executor, work, private, stage1_work, stage1_private


def _run(executor, work, private, stage1_work, stage1_private, **kwargs):
    return executor.execute_stage2(work, private, stage1_work=stage1_work, stage1_private_root=stage1_private, **kwargs)


def test_stage2_dry_run_and_prepare_replay_stage1_without_provider_contact(tmp_path, monkeypatch):
    executor, work, private, stage1_work, stage1_private = _fixture_stage2(tmp_path, monkeypatch)
    calls = []; monkeypatch.setattr(executor, "_call_codex", _fake(executor, calls, prefix="stage2"))
    assert executor.dry_run(work, private, stage1_work=stage1_work, stage1_private_root=stage1_private) == {"study_id": "hbq-hanna-batch-polarity-pilot-v1", "stage": 2, "provider_calls": 0, "scheduled_calls": 66, "conditions": ["global_negative_batch32", "single_positive_batch1", "single_negative_batch1", "global_positive_batch32"]}
    result = executor.prepare(work, private, stage1_work=stage1_work, stage1_private_root=stage1_private)
    assert result["provider_calls"] == 0 and result["scheduled_calls"] == 66 and result["stage1_artifacts_sha256"]
    assert not calls and (work / executor.EXECUTION_NAME).is_file() and (work / executor.DISCLOSURE_NAME).is_file()


def test_stage2_exact_66_call_order_remainders_and_merged_prefix(tmp_path, monkeypatch):
    executor, work, private, stage1_work, stage1_private = _fixture_stage2(tmp_path, monkeypatch)
    calls = []; monkeypatch.setattr(executor, "_call_codex", _fake(executor, calls, prefix="stage2"))
    result = _run(executor, work, private, stage1_work, stage1_private)
    assert result == {"status": "stage_2_stop_no_reproduced_signal", "next_stage": None, "calls": 66, "rows": 7}
    assert len(calls) == 66 and [json.loads(call["prompt"])["condition_id"] for call in calls] == ["global_negative_batch32"] * 6 + ["single_positive_batch1"] * 27 + ["single_negative_batch1"] * 27 + ["global_positive_batch32"] * 6
    sizes = [len(json.loads(call["prompt"])["questions"]) for call in calls]
    assert all(size == 1 for size in sizes[6:60]) and all(size == 32 for size in sizes[:5] + sizes[60:65])
    assert 0 < sizes[5] < 32 and 0 < sizes[65] < 32
    raw = json.loads((private / executor.RAW_EVIDENCE_NAME).read_text(encoding="utf-8"))
    assert raw["row_count"] == 7 and len(raw["rows"]) == 7
    executor.study.verify_evidence(executor.study.load_plan(work), raw["rows"])
    assert not (work / "stage3-evidence.json").exists()


def test_stage2_freezes_missing_partial_or_tampered_stage1_before_contact(tmp_path, monkeypatch):
    executor, work, private, stage1_work, stage1_private = _fixture_stage2(tmp_path, monkeypatch)
    calls = []; monkeypatch.setattr(executor, "_call_codex", _fake(executor, calls, prefix="stage2"))
    (stage1_work / executor.stage1.GATE_NAME).unlink()
    with pytest.raises(RuntimeError, match="incomplete"):
        _run(executor, work, private, stage1_work, stage1_private)
    assert not calls
    executor, work, private, stage1_work, stage1_private = _fixture_stage2(tmp_path / "tampered", monkeypatch)
    terminal = stage1_private / executor.stage1.ATTEMPTS / "0001" / "terminal.json"
    value = json.loads(terminal.read_text(encoding="utf-8")); value["transport_projection"] = "[]"; terminal.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(RuntimeError, match="terminal replay"):
        _run(executor, work, private, stage1_work, stage1_private)
    assert not (private / executor.ATTEMPTS).exists()
    executor, work, private, stage1_work, stage1_private = _fixture_stage2(tmp_path / "partial", monkeypatch)
    (stage1_private / executor.stage1.ATTEMPTS / "0002" / "terminal.json").unlink()
    with pytest.raises(RuntimeError, match="incomplete"):
        _run(executor, work, private, stage1_work, stage1_private)


def test_stage2_replays_every_stage1_contract_and_attempt_commitment(tmp_path, monkeypatch):
    executor, work, private, stage1_work, stage1_private = _fixture_stage2(tmp_path, monkeypatch)
    contract = stage1_work / executor.stage1.EXECUTION_NAME
    value = json.loads(contract.read_text(encoding="utf-8")); value["outcome_policy"]["automatic_stage_2"] = "allowed"; contract.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(RuntimeError, match="execution contract"):
        _run(executor, work, private, stage1_work, stage1_private)
    executor, work, private, stage1_work, stage1_private = _fixture_stage2(tmp_path / "predecessor", monkeypatch)
    contract = stage1_work / executor.stage1.EXECUTION_NAME
    value = json.loads(contract.read_text(encoding="utf-8")); value["predecessor"]["artifacts"]["freeze"]["sha256"] = "0" * 64; value["predecessor"]["artifacts_sha256"] = executor._sha256(executor._canonical(value["predecessor"]["artifacts"])); contract.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(RuntimeError, match="predecessor binding"):
        _run(executor, work, private, stage1_work, stage1_private)
    executor, work, private, stage1_work, stage1_private = _fixture_stage2(tmp_path / "start", monkeypatch)
    started = stage1_private / executor.stage1.ATTEMPTS / "0001" / "attempt-start.json"
    value = json.loads(started.read_text(encoding="utf-8")); value["call_in_cell"] = 99; started.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(RuntimeError, match="attempt-start"):
        _run(executor, work, private, stage1_work, stage1_private)
    executor, work, private, stage1_work, stage1_private = _fixture_stage2(tmp_path / "parent-collision", monkeypatch)
    terminal = stage1_private / executor.stage1.ATTEMPTS / "0001" / "terminal.json"
    value = json.loads(terminal.read_text(encoding="utf-8")); value["provider_record"]["reported"]["session_id"] = "parent-0"; value["session_id_sha256"] = _digest("parent-0"); terminal.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(RuntimeError, match="terminal replay"):
        _run(executor, work, private, stage1_work, stage1_private)


def test_stage2_gate_is_stop_or_stage3_required_but_never_launches_stage3(tmp_path, monkeypatch):
    executor, work, private, stage1_work, stage1_private = _fixture_stage2(tmp_path, monkeypatch)
    calls = []; monkeypatch.setattr(executor, "_call_codex", _fake(executor, calls, prefix="stage2", flip_at=1))
    result = _run(executor, work, private, stage1_work, stage1_private)
    assert result["status"] == "stage_3_required_signal" and result["next_stage"] == 3
    assert len(calls) == 66 and not (private / "stage3-attempts").exists()
    gate = json.loads((work / executor.GATE_NAME).read_text(encoding="utf-8"))
    assert gate["recommendation"] is None and gate["promotion"] == "forbidden"


def test_stage2_restart_and_public_projection_do_not_retry_or_leak_private_content(tmp_path, monkeypatch):
    executor, work, private, stage1_work, stage1_private = _fixture_stage2(tmp_path, monkeypatch)
    calls = []; monkeypatch.setattr(executor, "_call_codex", _fake(executor, calls, prefix="stage2"))
    _run(executor, work, private, stage1_work, stage1_private)
    first = private / executor.ATTEMPTS / "0001" / "terminal.json"; before = (first.read_bytes(), first.stat().st_mtime_ns)
    monkeypatch.setattr(executor, "_call_codex", lambda **_: pytest.fail("completed restart contacted provider"))
    assert _run(executor, work, private, stage1_work, stage1_private)["calls"] == 66
    assert (first.read_bytes(), first.stat().st_mtime_ns) == before
    for path in work.rglob("*"):
        if path.is_file():
            text = path.read_text(encoding="utf-8")
            assert "A private source story." not in text and "A private source prompt." not in text
            assert str(stage1_work) not in text and str(stage1_private) not in text
    for name in (executor.EXECUTION_NAME, executor.DISCLOSURE_NAME, executor.EVIDENCE_NAME, executor.GATE_NAME):
        text = (work / name).read_text(encoding="utf-8")
        assert str(work) not in text and str(executor.REPOSITORY) not in text and str(Path.home()) not in text
    contract = json.loads((work / executor.EXECUTION_NAME).read_text(encoding="utf-8"))
    assert len(contract["stage1_parent"]["artifacts"]["attempts"]) == 60
    assert all(set(item["attempt_start"]) == {"path_sha256", "bytes", "sha256"} and set(item["terminal"]) == {"path_sha256", "bytes", "sha256"} and all(set(file) == {"relative_path", "fingerprint"} and set(file["fingerprint"]) == {"path_sha256", "bytes", "sha256"} for file in item["files"]) for item in contract["stage1_parent"]["artifacts"]["attempts"])


def test_stage2_duplicate_session_freezes_without_retry(tmp_path, monkeypatch):
    executor, work, private, stage1_work, stage1_private = _fixture_stage2(tmp_path, monkeypatch)
    calls = []; monkeypatch.setattr(executor, "_call_codex", _fake(executor, calls, prefix="stage2", duplicate_session=True))
    with pytest.raises(RuntimeError, match="frozen"):
        _run(executor, work, private, stage1_work, stage1_private)
    assert len(calls) == 2
    assert json.loads((work / executor.FREEZE_NAME).read_text(encoding="utf-8"))["reason"] == "provider_or_response_failure"


def test_stage2_requires_pushed_runtime_binding(tmp_path, monkeypatch):
    executor, work, private, stage1_work, stage1_private = _fixture_stage2(tmp_path, monkeypatch)
    monkeypatch.setattr(executor.stage1, "_pushed_git_binding", lambda *_: (_ for _ in ()).throw(RuntimeError("not pushed")))
    with pytest.raises(RuntimeError, match="not pushed"):
        executor.prepare(work, private, stage1_work=stage1_work, stage1_private_root=stage1_private)


def test_stage2_completion_validation_failure_freezes_after_all_calls(tmp_path, monkeypatch):
    executor, work, private, stage1_work, stage1_private = _fixture_stage2(tmp_path, monkeypatch)
    calls = []; monkeypatch.setattr(executor, "_call_codex", _fake(executor, calls, prefix="stage2"))
    monkeypatch.setattr(executor.study, "stage_gate", lambda *_: {"unexpected": True})
    with pytest.raises(RuntimeError, match="completion_validation_failure"):
        _run(executor, work, private, stage1_work, stage1_private)
    assert len(calls) == 66
    assert json.loads((work / executor.FREEZE_NAME).read_text(encoding="utf-8"))["reason"] == "completion_validation_failure"
