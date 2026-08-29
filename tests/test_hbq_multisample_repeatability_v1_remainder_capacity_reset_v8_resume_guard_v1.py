from __future__ import annotations

import hashlib
import importlib.util
import json
import multiprocessing
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from queue import Empty
from types import ModuleType
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[1]
V8_PATH = ROOT / "evaluation-results" / "hbq-multisample-repeatability-v1-remainder-capacity-reset-successor-v8" / "executor.py"
GUARD_PATH = ROOT / "evaluation-results" / "hbq-multisample-repeatability-v1-remainder-capacity-reset-v8-resume-guard-v1" / "guard.py"


def _module(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def guard() -> ModuleType:
    return _module(GUARD_PATH, "v8_resume_guard_test")


@pytest.fixture()
def v8() -> ModuleType:
    return _module(V8_PATH, "v8_resume_guard_target_test")


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def _append_jsonl(path: Path, *rows: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write("".join(json.dumps(row) + "\n" for row in rows))


def _events() -> list[dict[str, Any]]:
    return [
        {"sequence": 182, "item_id": "adopted", "arm_id": "native", "repetition": 1},
        {"sequence": 183, "item_id": "hbq-one", "arm_id": "hbq_short_story_batch32", "repetition": 1},
        {"sequence": 184, "item_id": "next", "arm_id": "native", "repetition": 1},
    ]


def _configure_v8(monkeypatch: pytest.MonkeyPatch, v8: ModuleType, accepted: list[dict[str, Any]], schedule: list[dict[str, Any]]) -> None:
    binding = {"runtime": {"identity": "test-only"}}
    admission = {"settlement_sha256": "a" * 64}
    monkeypatch.setattr(v8, "_verify_prepared", lambda *_args: (binding, schedule, admission))
    monkeypatch.setattr(v8, "_accepted", lambda *_args: accepted)
    monkeypatch.setattr(v8, "_validate_contact_sessions", lambda *_args: None)


def _prepared_work(v8: ModuleType, tmp_path: Path) -> Path:
    work = tmp_path / "v8-work"
    work.mkdir()
    for name in (v8.BINDING, v8.ADMISSION, v8.SCHEDULE, v8.DISCLOSURE):
        _write_json(work / name, {"name": name})
    _append_jsonl(work / v8.JOURNAL, {"event": "admitted-prefix"})
    return work


def _write_hbq_output(v8: ModuleType, work: Path, event: dict[str, Any], *, first_attempt: int = 1, include_rejected: bool = True) -> None:
    output = v8._output_path(work, event).parent
    _write_json(output / "run.json", {"configuration": {"fixture": True}})
    for batch in range(1, 7):
        attempt = first_attempt if batch == 1 else 1
        _write_json(output / "responses" / f"batch-{batch:04d}.json", {"batch": batch, "accepted_attempt": attempt, "provider": {"reported": {"session_id": f"accepted-{batch}"}}})
        for ordinal in range(1, attempt + 1):
            _write_json(output / "responses" / f"batch-{batch:04d}.attempt-{ordinal:04d}.message.json", {"fixture": True})
        if attempt == 2 and include_rejected:
            _write_json(output / "responses" / "rejected" / "batch-0001" / "attempt-0001.json", {"response": {"provider": {"reported": {"session_id": "rejected-1"}}}})


def _prepare_guard(guard: ModuleType, v8: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, accepted: list[dict[str, Any]], schedule: list[dict[str, Any]], work: Path, runtime_root: Path = V8_PATH.parent) -> Path:
    _configure_v8(monkeypatch, v8, accepted, schedule)
    executor = runtime_root / "executor.py"
    v8._resume_guard_executor_path = str(executor)
    v8._resume_guard_executor_sha256 = hashlib.sha256(executor.read_bytes()).hexdigest()
    monkeypatch.setattr(guard, "_load_v8", lambda _executor: v8)
    root = tmp_path / "guard"
    guard.prepare_guard(source_root=tmp_path / "source", closed_root=tmp_path / "closed", v7_root=tmp_path / "v7", work_root=work, guard_root=root, v8_runtime_root=runtime_root)
    return root


def _separate_runtime(tmp_path: Path) -> Path:
    runtime = tmp_path / "separate-v8-runtime"
    runtime.mkdir()
    (runtime / "executor.py").write_bytes(V8_PATH.read_bytes())
    (runtime / "study-contract.json").write_bytes(V8_PATH.with_name("study-contract.json").read_bytes())
    return runtime


def _process_claim_worker(guard_path: str, v8_path: str, work_root: str, guard_root: str, source_root: str, closed_root: str, v7_root: str, schedule: list[dict[str, Any]], result_queue: Any, call_queue: Any) -> None:
    guard = _module(Path(guard_path), "v8_resume_guard_process")
    v8 = _module(Path(v8_path), "v8_resume_guard_target_process")
    binding = {"runtime": {"identity": "test-only"}}
    admission = {"settlement_sha256": "a" * 64}
    v8._verify_prepared = lambda *_args: (binding, schedule, admission)
    v8._accepted = lambda *_args: schedule[:1]
    v8._validate_contact_sessions = lambda *_args: None
    v8._resume_guard_executor_path = str(Path(v8_path))
    v8._resume_guard_executor_sha256 = hashlib.sha256(Path(v8_path).read_bytes()).hexdigest()
    guard._load_v8 = lambda _executor: v8
    try:
        guard.dispatch_next(source_root=Path(source_root), closed_root=Path(closed_root), v7_root=Path(v7_root), work_root=Path(work_root), guard_root=Path(guard_root), allow_remote=True, delegate=lambda event: call_queue.put(event["sequence"]), v8_runtime_root=Path(v8_path).parent)
    except Exception as exc:  # Each worker must report the fail-closed terminal state.
        result_queue.put(str(exc))
    else:
        result_queue.put("unexpected-success")


def test_incomplete_hbq_attempt_topology_fails_before_delegate(guard: ModuleType, v8: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    schedule = _events()
    work = _prepared_work(v8, tmp_path)
    _write_hbq_output(v8, work, schedule[1], first_attempt=2, include_rejected=False)
    _append_jsonl(work / v8.JOURNAL, {"event": "provider-contacts", "sequence": 183, "recorded_provider_contacts": 7})
    root = _prepare_guard(guard, v8, tmp_path, monkeypatch, accepted=schedule[:2], schedule=schedule, work=work)
    calls: list[dict[str, Any]] = []
    with pytest.raises(ValueError, match="exact physical attempt prefix"):
        guard.dispatch_next(source_root=tmp_path / "source", closed_root=tmp_path / "closed", v7_root=tmp_path / "v7", work_root=work, guard_root=root, allow_remote=True, delegate=calls.append, v8_runtime_root=V8_PATH.parent)
    assert calls == []


def test_valid_topology_delegates_exactly_once_and_journals(guard: ModuleType, v8: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    schedule = _events()
    work = _prepared_work(v8, tmp_path)
    _write_hbq_output(v8, work, schedule[1])
    _append_jsonl(work / v8.JOURNAL, {"event": "provider-contacts", "sequence": 183, "recorded_provider_contacts": 6})
    root = _prepare_guard(guard, v8, tmp_path, monkeypatch, accepted=schedule[:2], schedule=schedule, work=work)
    calls: list[dict[str, Any]] = []
    def settle(event: dict[str, Any]) -> None:
        calls.append(event)
        _append_jsonl(work / v8.JOURNAL, {"event": "provider-contacts", "sequence": 184, "recorded_provider_contacts": 1})
        output = v8._output_path(work, event).parent
        _write_json(v8._output_path(work, event), {"result": "accepted"})
        _write_json(output / "responses" / "batch-0001.attempt-0001.message.json", {"message": "native"})
        _write_json(output / "response.json", {"provider": {"reported": {"session_id": "native-184"}}})
        _append_jsonl(work / v8.JOURNAL, {"event": "completed", "sequence": 184})
        monkeypatch.setattr(v8, "_accepted", lambda *_args: schedule)
    assert guard.dispatch_next(source_root=tmp_path / "source", closed_root=tmp_path / "closed", v7_root=tmp_path / "v7", work_root=work, guard_root=root, allow_remote=True, delegate=settle, v8_runtime_root=V8_PATH.parent) is None
    assert calls == [schedule[2]]
    with pytest.raises(ValueError, match="no untouched sequence"):
        guard.dispatch_next(source_root=tmp_path / "source", closed_root=tmp_path / "closed", v7_root=tmp_path / "v7", work_root=work, guard_root=root, allow_remote=True, delegate=calls.append, v8_runtime_root=V8_PATH.parent)
    assert calls == [schedule[2]]
    rows = guard._guard_rows(root)
    assert [row["event"] for row in rows] == ["guard-prepared", "delegate-intent", "delegate-completed"]


def test_repeated_uncompleted_intent_refuses_resend(guard: ModuleType, v8: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    schedule = _events()
    work = _prepared_work(v8, tmp_path)
    root = _prepare_guard(guard, v8, tmp_path, monkeypatch, accepted=schedule[:1], schedule=schedule, work=work)
    commitment = hashlib.sha256(guard.canonical(schedule[1])).hexdigest()
    guard._create_claim(root, schedule[1])
    guard._append_guard(root, {"event": "delegate-intent", "sequence": 183, "event_sha256": commitment})
    with pytest.raises(ValueError, match="lacks completion"):
        guard.preflight(source_root=tmp_path / "source", closed_root=tmp_path / "closed", v7_root=tmp_path / "v7", work_root=work, guard_root=root, v8_runtime_root=V8_PATH.parent)


def test_tamper_reparse_and_orphan_fail(guard: ModuleType, v8: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    schedule = _events()
    work = _prepared_work(v8, tmp_path)
    root = _prepare_guard(guard, v8, tmp_path, monkeypatch, accepted=schedule[:1], schedule=schedule, work=work)
    (work / v8.BINDING).write_text('{"tampered":true}', encoding="utf-8")
    with pytest.raises(ValueError, match="identity drifted"):
        guard.preflight(source_root=tmp_path / "source", closed_root=tmp_path / "closed", v7_root=tmp_path / "v7", work_root=work, guard_root=root, v8_runtime_root=V8_PATH.parent)
    (work / v8.BINDING).write_text(json.dumps({"name": v8.BINDING}), encoding="utf-8")
    monkeypatch.setattr(guard, "_is_reparse", lambda path: path.name == guard.JOURNAL)
    with pytest.raises(ValueError, match="Reparse"):
        guard.preflight(source_root=tmp_path / "source", closed_root=tmp_path / "closed", v7_root=tmp_path / "v7", work_root=work, guard_root=root, v8_runtime_root=V8_PATH.parent)
    monkeypatch.setattr(guard, "_is_reparse", lambda path: False)
    v8._output_path(work, schedule[1]).parent.mkdir(parents=True)
    with pytest.raises(ValueError, match="future or unjournaled V8 cell"):
        guard.preflight(source_root=tmp_path / "source", closed_root=tmp_path / "closed", v7_root=tmp_path / "v7", work_root=work, guard_root=root, v8_runtime_root=V8_PATH.parent)


def test_physical_count_must_equal_journal_and_source_is_unchanged(guard: ModuleType, v8: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    source_before = hashlib.sha256(V8_PATH.read_bytes()).hexdigest()
    schedule = _events()
    work = _prepared_work(v8, tmp_path)
    _write_hbq_output(v8, work, schedule[1])
    _append_jsonl(work / v8.JOURNAL, {"event": "provider-contacts", "sequence": 183, "recorded_provider_contacts": 7})
    root = _prepare_guard(guard, v8, tmp_path, monkeypatch, accepted=schedule[:2], schedule=schedule, work=work)
    with pytest.raises(ValueError, match="Physical provider-contact topology"):
        guard.preflight(source_root=tmp_path / "source", closed_root=tmp_path / "closed", v7_root=tmp_path / "v7", work_root=work, guard_root=root, v8_runtime_root=V8_PATH.parent)
    assert hashlib.sha256(V8_PATH.read_bytes()).hexdigest() == source_before


def test_default_dispatch_is_provider_disabled_before_any_intent(guard: ModuleType, v8: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    schedule = _events()
    work = _prepared_work(v8, tmp_path)
    root = _prepare_guard(guard, v8, tmp_path, monkeypatch, accepted=schedule[:1], schedule=schedule, work=work)
    with pytest.raises(ValueError, match="disabled"):
        guard.dispatch_next(source_root=tmp_path / "source", closed_root=tmp_path / "closed", v7_root=tmp_path / "v7", work_root=work, guard_root=root, v8_runtime_root=V8_PATH.parent)
    assert [row["event"] for row in guard._guard_rows(root)] == ["guard-prepared"]


def test_unresolved_v8_state_is_rejected_before_mutating_accepted_path(guard: ModuleType, v8: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    schedule = _events()
    work = _prepared_work(v8, tmp_path)
    root = _prepare_guard(guard, v8, tmp_path, monkeypatch, accepted=schedule[:1], schedule=schedule, work=work)
    _append_jsonl(work / v8.JOURNAL, {"event": "attempt-intent", "sequence": 183})
    before = {path.relative_to(work).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest() for path in work.rglob("*") if path.is_file()}
    monkeypatch.setattr(v8, "_accepted", lambda *_args: pytest.fail("V8 _accepted must not run for unresolved state"))
    with pytest.raises(ValueError, match="unresolved intent or pause"):
        guard.preflight(source_root=tmp_path / "source", closed_root=tmp_path / "closed", v7_root=tmp_path / "v7", work_root=work, guard_root=root, v8_runtime_root=V8_PATH.parent)
    after = {path.relative_to(work).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest() for path in work.rglob("*") if path.is_file()}
    assert after == before


def test_guard_root_must_be_disjoint_and_loaded_module_identity_is_bound(guard: ModuleType, v8: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    schedule = _events()
    work = _prepared_work(v8, tmp_path)
    _configure_v8(monkeypatch, v8, schedule[:1], schedule)
    monkeypatch.setattr(guard, "_load_v8", lambda _executor: v8)
    with pytest.raises(ValueError, match="module bytes or path"):
        guard.prepare_guard(source_root=tmp_path / "source", closed_root=tmp_path / "closed", v7_root=tmp_path / "v7", work_root=work, guard_root=tmp_path / "guard", v8_runtime_root=V8_PATH.parent)
    v8._resume_guard_executor_path = str(V8_PATH)
    v8._resume_guard_executor_sha256 = hashlib.sha256(V8_PATH.read_bytes()).hexdigest()
    with pytest.raises(ValueError, match="disjoint"):
        guard.prepare_guard(source_root=tmp_path / "source", closed_root=tmp_path / "closed", v7_root=tmp_path / "v7", work_root=work, guard_root=work / "guard", v8_runtime_root=V8_PATH.parent)


def test_two_concurrent_callers_claim_at_most_one_delegate(guard: ModuleType, v8: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    schedule = _events()
    work = _prepared_work(v8, tmp_path)
    root = _prepare_guard(guard, v8, tmp_path, monkeypatch, accepted=schedule[:1], schedule=schedule, work=work)
    calls: list[int] = []
    calls_lock = threading.Lock()
    entered = threading.Event()
    release = threading.Event()

    def delegate(event: dict[str, Any]) -> None:
        with calls_lock:
            calls.append(int(event["sequence"]))
        entered.set()
        release.wait(timeout=2)

    def invoke() -> str:
        try:
            guard.dispatch_next(source_root=tmp_path / "source", closed_root=tmp_path / "closed", v7_root=tmp_path / "v7", work_root=work, guard_root=root, allow_remote=True, delegate=delegate, v8_runtime_root=V8_PATH.parent)
        except ValueError as exc:
            return str(exc)
        return "unexpected-success"

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(invoke)
        assert entered.wait(timeout=2)
        second = pool.submit(invoke)
        release.set()
        messages = [first.result(timeout=5), second.result(timeout=5)]
    assert calls == [183]
    assert all(message != "unexpected-success" for message in messages)


def test_two_processes_claim_at_most_one_delegate(guard: ModuleType, v8: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    schedule = _events()
    work = _prepared_work(v8, tmp_path)
    root = _prepare_guard(guard, v8, tmp_path, monkeypatch, accepted=schedule[:1], schedule=schedule, work=work)
    context = multiprocessing.get_context("spawn")
    results, calls = context.Queue(), context.Queue()
    args = (str(GUARD_PATH), str(V8_PATH), str(work), str(root), str(tmp_path / "source"), str(tmp_path / "closed"), str(tmp_path / "v7"), schedule, results, calls)
    workers = [context.Process(target=_process_claim_worker, args=args) for _ in range(2)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(timeout=15)
        assert worker.exitcode == 0
    messages = [results.get(timeout=2) for _ in workers]
    assert calls.get(timeout=2) == 183
    with pytest.raises(Empty):
        calls.get(timeout=1)
    assert all(message != "unexpected-success" for message in messages)


@pytest.mark.parametrize("delegate", [lambda _event: (_ for _ in ()).throw(RuntimeError("delegate failed")), lambda _event: None], ids=["exception", "return_without_settlement"])
def test_delegate_failure_or_unsettled_return_preserves_terminal_claim(guard: ModuleType, v8: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, delegate: Any):
    schedule = _events()
    work = _prepared_work(v8, tmp_path)
    root = _prepare_guard(guard, v8, tmp_path, monkeypatch, accepted=schedule[:1], schedule=schedule, work=work)
    with pytest.raises((RuntimeError, ValueError)):
        guard.dispatch_next(source_root=tmp_path / "source", closed_root=tmp_path / "closed", v7_root=tmp_path / "v7", work_root=work, guard_root=root, allow_remote=True, delegate=delegate, v8_runtime_root=V8_PATH.parent)
    assert [row["event"] for row in guard._guard_rows(root)] == ["guard-prepared", "delegate-intent"]
    assert (root / guard.CLAIMS / "sequence-0183.json").is_file()
    with pytest.raises(ValueError, match="claim|completion"):
        guard.dispatch_next(source_root=tmp_path / "source", closed_root=tmp_path / "closed", v7_root=tmp_path / "v7", work_root=work, guard_root=root, allow_remote=True, delegate=lambda _event: None, v8_runtime_root=V8_PATH.parent)


def test_fake_executor_and_stale_journal_path_are_rejected(guard: ModuleType, v8: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    schedule = _events()
    work = _prepared_work(v8, tmp_path)
    fake_root = tmp_path / "fake-runtime"
    fake_root.mkdir()
    fake = fake_root / "executor.py"
    fake.write_text("raise AssertionError('must not load')\n", encoding="utf-8")
    (fake_root / "study-contract.json").write_bytes(V8_PATH.with_name("study-contract.json").read_bytes())
    with pytest.raises(ValueError, match="SHA-256 drifted"):
        guard.prepare_guard(source_root=tmp_path / "source", closed_root=tmp_path / "closed", v7_root=tmp_path / "v7", work_root=work, guard_root=tmp_path / "fake-guard", v8_runtime_root=fake_root)
    root = _prepare_guard(guard, v8, tmp_path, monkeypatch, accepted=schedule[:1], schedule=schedule, work=work)
    before = (root / guard.JOURNAL).read_bytes()
    original_plain = guard._plain

    def stale_journal(path: Path, **kwargs: Any) -> Path:
        if Path(path).name == guard.JOURNAL:
            raise ValueError("Reparse points are forbidden: simulated post-lock swap")
        return original_plain(path, **kwargs)

    monkeypatch.setattr(guard, "_plain", stale_journal)
    with pytest.raises(ValueError, match="post-lock swap"):
        guard._append_guard(root, {"event": "delegate-intent", "sequence": 183, "event_sha256": "a" * 64})
    assert (root / guard.JOURNAL).read_bytes() == before


def test_postflight_requires_exactly_one_claimed_accepted_delta(guard: ModuleType, v8: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    schedule = _events()
    work = _prepared_work(v8, tmp_path)
    root = _prepare_guard(guard, v8, tmp_path, monkeypatch, accepted=schedule[:1], schedule=schedule, work=work)

    def settle_two(_event: dict[str, Any]) -> None:
        _write_hbq_output(v8, work, schedule[1])
        _append_jsonl(work / v8.JOURNAL, {"event": "provider-contacts", "sequence": 183, "recorded_provider_contacts": 6})
        output = v8._output_path(work, schedule[2]).parent
        _write_json(v8._output_path(work, schedule[2]), {"result": "accepted"})
        _write_json(output / "responses" / "batch-0001.attempt-0001.message.json", {"message": "native-184"})
        _write_json(output / "response.json", {"provider": {"reported": {"session_id": "native-184"}}})
        _append_jsonl(work / v8.JOURNAL, {"event": "provider-contacts", "sequence": 184, "recorded_provider_contacts": 1}, {"event": "completed", "sequence": 183}, {"event": "completed", "sequence": 184})
        monkeypatch.setattr(v8, "_accepted", lambda *_args: schedule)

    with pytest.raises(ValueError, match="exactly the claimed"):
        guard.dispatch_next(source_root=tmp_path / "source", closed_root=tmp_path / "closed", v7_root=tmp_path / "v7", work_root=work, guard_root=root, allow_remote=True, delegate=settle_two, v8_runtime_root=V8_PATH.parent)
    assert [row["event"] for row in guard._guard_rows(root)] == ["guard-prepared", "delegate-intent"]


def test_separate_runtime_root_is_bound_and_bad_layout_or_hash_rejects(guard: ModuleType, v8: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    schedule = _events()
    work = _prepared_work(v8, tmp_path)
    runtime = _separate_runtime(tmp_path)
    root = _prepare_guard(guard, v8, tmp_path, monkeypatch, accepted=schedule[:1], schedule=schedule, work=work, runtime_root=runtime)
    binding = guard._guard_binding(root)
    assert binding["v8_identity"]["canonical_runtime"]["root"] == str(runtime.absolute())
    assert guard.preflight(source_root=tmp_path / "source", closed_root=tmp_path / "closed", v7_root=tmp_path / "v7", work_root=work, guard_root=root, v8_runtime_root=runtime)["next_event"] == schedule[1]
    with pytest.raises(ValueError, match="Loaded V8 module bytes or path|identity.*drifted"):
        guard.preflight(source_root=tmp_path / "source", closed_root=tmp_path / "closed", v7_root=tmp_path / "v7", work_root=work, guard_root=root, v8_runtime_root=V8_PATH.parent)
    wrong_layout = tmp_path / "wrong-layout"
    wrong_layout.mkdir()
    with pytest.raises(ValueError, match="Required path is missing"):
        guard.preflight(source_root=tmp_path / "source", closed_root=tmp_path / "closed", v7_root=tmp_path / "v7", work_root=work, guard_root=root, v8_runtime_root=wrong_layout)
    (runtime / "executor.py").write_bytes(V8_PATH.read_bytes() + b"# drift\n")
    with pytest.raises(ValueError, match="SHA-256 drifted"):
        guard.preflight(source_root=tmp_path / "source", closed_root=tmp_path / "closed", v7_root=tmp_path / "v7", work_root=work, guard_root=root, v8_runtime_root=runtime)
