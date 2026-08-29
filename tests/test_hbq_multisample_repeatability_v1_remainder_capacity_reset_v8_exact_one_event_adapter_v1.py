from __future__ import annotations

import importlib.util
import json
import multiprocessing
import os
import shutil
import threading
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest


PATH = Path(__file__).parents[1] / "evaluation-results" / "hbq-multisample-repeatability-v1-remainder-capacity-reset-v8-exact-one-event-adapter-v1" / "adapter.py"
REPOSITORY = PATH.parents[2]
GUARD_PATH = REPOSITORY / "evaluation-results" / "hbq-multisample-repeatability-v1-remainder-capacity-reset-v8-resume-guard-v1" / "guard.py"
V8_PATH = REPOSITORY / "evaluation-results" / "hbq-multisample-repeatability-v1-remainder-capacity-reset-successor-v8" / "executor.py"


def _adapter() -> ModuleType:
    spec = importlib.util.spec_from_file_location("v8_exact_one_adapter_test", PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _module(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _RetryPause(Exception):
    pass


class _Guard:
    def __init__(self, event: dict[str, Any]) -> None:
        self.event, self.claimed, self.lock, self.dispatches = event, set(), threading.Lock(), 0

    def preflight(self, **_kwargs: Any) -> dict[str, Any]:
        return {"next_event": dict(self.event)}

    def _assert_no_unresolved_v8_state(self, _v8: Any, _work: Path) -> None:
        return None

    def dispatch_next(self, *, guard_root: Path, delegate: Any, **_kwargs: Any) -> Any:
        with self.lock:
            if str(guard_root) in self.claimed:
                raise ValueError("existing guard claim blocks resend")
            self.claimed.add(str(guard_root)); self.dispatches += 1
        return delegate(dict(self.event))


def _v8(events: list[dict[str, Any]]) -> tuple[Any, dict[str, Any]]:
    state: dict[str, Any] = {"accepted": [events[0]], "settle_calls": 0, "native_commands": 0, "attempt_rows": 99, "fail": None, "capacity_ok": True, "ack_ok": True, "clean": True}
    work = Path("C:/adapter-test/work")
    source = Path("C:/adapter-test/source")

    def external(path: Path) -> Path:
        return Path(path)

    def work_path(_work: Path, *parts: str, **_kwargs: Any) -> Path:
        return Path(_work).joinpath(*parts)

    def validate_capacity(_path: Path) -> dict[str, Any]:
        if not state["capacity_ok"]:
            raise ValueError("Capacity evidence is not current")
        return {"ready": True}

    def validate_ack(_work: Path, _ack: Path) -> None:
        if not state["ack_ok"]:
            raise ValueError("Disclosure acknowledgement does not match")

    def clean() -> None:
        if not state["clean"]:
            raise ValueError("Remote dispatch requires a clean checkout exactly at its upstream")

    def verify(*_args: Any) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
        return {"runtime": {"pinned": True}}, events, {"admission": True}

    def accepted(*_args: Any) -> list[dict[str, Any]]:
        return list(state["accepted"])

    def settle(_runner: Any, _frozen: Any, _source: Path, _work: Path, _schedule: Any, _admission: Any, accepted_before: list[dict[str, Any]], event: dict[str, Any], *_args: Any) -> list[dict[str, Any]]:
        state["settle_calls"] += 1; state["native_commands"] += 1
        if state["fail"] == "exception":
            raise RuntimeError("native timeout")
        if state["fail"] == "pause":
            raise _RetryPause("changed payload")
        if state["fail"] == "unsettled":
            return accepted_before
        state["accepted"] = [*accepted_before, event]
        return list(state["accepted"])

    v8 = SimpleNamespace(
        DISCLOSURE_ACK="disclosure-acknowledgement.json",
        _external=external,
        _work_path=work_path,
        validate_capacity_evidence=validate_capacity,
        _validate_disclosure_ack=validate_ack,
        _require_clean_pushed=clean,
        _verify_prepared=verify,
        _accepted=accepted,
        _validate_contact_sessions=lambda *_args: None,
        _require_no_orphan_output_cells=lambda *_args: None,
        _plain_path=lambda path: Path(path),
        read_json=lambda _path: {"frozen": True},
        _runtime_projection=lambda _frozen: {"pinned": True},
        _settle_one=settle,
        _load_hbq_runner=lambda: SimpleNamespace(RetryDisclosurePause=_RetryPause),
        _load_successor_runner=lambda: object(),
        SUCCESSOR_RUNNER=Path("C:/adapter-test/runtime/run_successor.py"),
        REPO=Path("C:/adapter-test/runtime"),
        _runtime_file=lambda *_args, **_kwargs: {"path": "run_successor.py", "bytes": 1, "sha256": "a" * 64},
    )
    return v8, state


def _call(adapter: ModuleType, *, state: dict[str, Any], guard: _Guard, v8: Any, root: str = "C:/adapter-test/guard") -> Any:
    adapter._load_pinned_modules = lambda _runtime: (guard, v8, Path("C:/adapter-test/runtime"), Path("C:/adapter-test/runtime/executor.py"))
    adapter._load_pinned_successor_runner = lambda _v8, _runtime: object()
    return adapter.dispatch_one(
        source_root=Path("C:/adapter-test/source"), closed_root=Path("C:/adapter-test/closed"), v7_root=Path("C:/adapter-test/v7"), work_root=Path("C:/adapter-test/work"), guard_root=Path(root), capacity_evidence=Path("C:/adapter-test/capacity.json"), disclosure_ack=Path("C:/adapter-test/work/disclosure-acknowledgement.json"), allow_remote=True,
    )


def _process_dispatch(adapter_path: str, guard_root: str, command_path: str, results: Any) -> None:
    spec = importlib.util.spec_from_file_location("v8_exact_one_adapter_process", adapter_path)
    assert spec and spec.loader
    adapter = importlib.util.module_from_spec(spec); spec.loader.exec_module(adapter)
    events = [{"sequence": 182}, {"sequence": 183}]
    v8, state = _v8(events)

    class FileClaimGuard(_Guard):
        def dispatch_next(self, *, guard_root: Path, delegate: Any, **_kwargs: Any) -> Any:
            claim = Path(guard_root) / "exclusive-guard-claim"
            try:
                descriptor = os.open(claim, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            except FileExistsError as exc:
                raise ValueError("existing guard claim blocks resend") from exc
            os.close(descriptor)
            return delegate(dict(self.event))

    def native_once(*args: Any) -> Any:
        descriptor = os.open(command_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        os.close(descriptor)
        return args[6] + [args[7]]

    v8._settle_one = native_once
    guard = FileClaimGuard(events[1])
    try:
        _call(adapter, state=state, guard=guard, v8=v8, root=guard_root)
    except BaseException as exc:
        results.put(type(exc).__name__)
    else:
        results.put("ok")


def test_one_native_settlement_accepts_only_the_guarded_next_event() -> None:
    adapter = _adapter(); events = [{"sequence": 182}, {"sequence": 183}, {"sequence": 184}]
    v8, state = _v8(events); guard = _Guard(events[1])
    settled = _call(adapter, state=state, guard=guard, v8=v8)
    assert settled == events[:2]
    assert state["settle_calls"] == state["native_commands"] == guard.dispatches == 1
    assert state["attempt_rows"] == 99 and state["accepted"] == events[:2] and events[2] not in state["accepted"]


@pytest.mark.parametrize("gate", ["capacity_ok", "ack_ok", "clean"])
def test_precontact_gates_fail_before_guard_or_native_command(gate: str) -> None:
    adapter = _adapter(); events = [{"sequence": 182}, {"sequence": 183}]
    v8, state = _v8(events); guard = _Guard(events[1]); state[gate] = False
    with pytest.raises(ValueError):
        _call(adapter, state=state, guard=guard, v8=v8)
    assert guard.dispatches == state["settle_calls"] == state["native_commands"] == 0


def test_public_dispatch_cannot_accept_a_runner_injection() -> None:
    adapter = _adapter(); events = [{"sequence": 182}, {"sequence": 183}]
    v8, state = _v8(events); guard = _Guard(events[1])
    adapter._load_pinned_modules = lambda _runtime: (guard, v8, Path("C:/adapter-test/runtime"), Path("C:/adapter-test/runtime/executor.py"))
    with pytest.raises(TypeError, match="runner"):
        adapter.dispatch_one(
            source_root=Path("C:/adapter-test/source"), closed_root=Path("C:/adapter-test/closed"), v7_root=Path("C:/adapter-test/v7"), work_root=Path("C:/adapter-test/work"), guard_root=Path("C:/adapter-test/guard"), capacity_evidence=Path("C:/adapter-test/capacity.json"), disclosure_ack=Path("C:/adapter-test/work/disclosure-acknowledgement.json"), allow_remote=True, runner=object(),
        )
    assert guard.dispatches == state["native_commands"] == 0


@pytest.mark.parametrize("failure, expected", [("exception", RuntimeError), ("unsettled", ValueError), ("pause", None)])
def test_terminal_outcomes_never_resend(failure: str, expected: type[Exception] | None) -> None:
    adapter = _adapter(); events = [{"sequence": 182}, {"sequence": 183}]
    v8, state = _v8(events); guard = _Guard(events[1]); state["fail"] = failure
    error = adapter.RetryPauseTerminal if expected is None else expected
    with pytest.raises(error):
        _call(adapter, state=state, guard=guard, v8=v8)
    with pytest.raises(ValueError, match="claim"):
        _call(adapter, state=state, guard=guard, v8=v8)
    assert state["settle_calls"] == state["native_commands"] == guard.dispatches == 1


def test_wrong_guard_event_is_rejected_without_v8_settlement() -> None:
    adapter = _adapter(); events = [{"sequence": 182}, {"sequence": 183}, {"sequence": 184}]
    v8, state = _v8(events); guard = _Guard(events[2])
    with pytest.raises(ValueError, match="exact next"):
        _call(adapter, state=state, guard=guard, v8=v8)
    assert state["settle_calls"] == state["native_commands"] == 0


def test_two_callers_share_one_guard_claim_and_make_one_native_command() -> None:
    adapter = _adapter(); events = [{"sequence": 182}, {"sequence": 183}]
    v8, state = _v8(events); guard = _Guard(events[1]); entered, release = threading.Event(), threading.Event()
    original = v8._settle_one

    def blocking(*args: Any) -> Any:
        entered.set(); release.wait(timeout=2)
        return original(*args)

    v8._settle_one = blocking
    outcomes: list[BaseException | Any] = []

    def invoke() -> None:
        try:
            outcomes.append(_call(adapter, state=state, guard=guard, v8=v8))
        except BaseException as exc:
            outcomes.append(exc)

    first = threading.Thread(target=invoke); second = threading.Thread(target=invoke)
    first.start(); assert entered.wait(timeout=2); second.start(); release.set(); first.join(5); second.join(5)
    assert state["native_commands"] == guard.dispatches == 1
    assert sum(isinstance(item, ValueError) for item in outcomes) == 1


def test_two_processes_share_one_guard_root_and_make_at_most_one_native_command(tmp_path: Path) -> None:
    root = tmp_path / "guard"; root.mkdir()
    command = tmp_path / "native-command"
    context = multiprocessing.get_context("spawn")
    results = context.Queue()
    workers = [context.Process(target=_process_dispatch, args=(str(PATH), str(root), str(command), results)) for _ in range(2)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(timeout=15)
        assert worker.exitcode == 0
    outcomes = sorted(results.get(timeout=2) for _ in workers)
    assert outcomes == ["ValueError", "ok"] and command.is_file()


def test_real_guard_separate_roots_race_at_frozen_v8_exclusive_claim(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = _adapter()
    runtime = tmp_path / "frozen-runtime" / "evaluation-results" / V8_PATH.parent.name
    runtime.mkdir(parents=True)
    shutil.copy2(V8_PATH, runtime / "executor.py")
    shutil.copy2(V8_PATH.with_name("study-contract.json"), runtime / "study-contract.json")
    v8 = _module(runtime / "executor.py", "v8_exact_one_integration")
    guard = _module(GUARD_PATH, "v8_exact_one_real_guard")
    source, closed, v7, work = (tmp_path / name for name in ("source", "closed", "v7", "work"))
    for root in (source, closed, v7, work):
        root.mkdir()
    (source / "frozen-run-contract.json").write_text(json.dumps({"frozen": True}), encoding="utf-8")
    schedule = [
        {"sequence": 182, "item_id": "item-182", "arm_id": "native", "repetition": 1},
        {"sequence": 183, "item_id": "item-183", "arm_id": "native", "repetition": 1},
        {"sequence": 184, "item_id": "item-184", "arm_id": "native", "repetition": 1},
    ]
    for name in (v8.BINDING, v8.ADMISSION, v8.DISCLOSURE):
        (work / name).write_text("{}\n", encoding="utf-8")
    (work / v8.SCHEDULE).write_text("\n".join(json.dumps(event) for event in schedule) + "\n", encoding="utf-8")
    (work / v8.JOURNAL).write_text("", encoding="utf-8")
    (work / v8.DISCLOSURE_ACK).write_text("{}\n", encoding="utf-8")
    capacity = tmp_path / "capacity.json"; capacity.write_text("{}\n", encoding="utf-8")
    binding, admission = {"runtime": {"pinned": "integration"}}, {"admission": True}
    native_commands: list[int] = []
    entered, release = threading.Event(), threading.Event()
    original_claim = v8._claim

    def accepted(current_work: Path, *_args: Any) -> list[dict[str, Any]]:
        rows = v8._read_journal(current_work)
        return schedule[:2] if any(row.get("event") == "completed" and row.get("sequence") == 183 for row in rows) else schedule[:1]

    def delayed_claim(*args: Any) -> Path:
        claim = original_claim(*args)
        entered.set(); release.wait(timeout=5)
        return claim

    def dispatch(_runner: Any, event: dict[str, Any], _frozen: Any, _source: Path, current_work: Path, _timeout: float, before_provider_attempt: Any = None) -> Path:
        assert before_provider_attempt is not None
        before_provider_attempt({"attempt": {"number": 1}})
        native_commands.append(int(event["sequence"]))
        target = v8._output_path(current_work, event)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("{}\n", encoding="utf-8")
        return target

    monkeypatch.setattr(v8, "_verify_prepared", lambda *_args: (binding, schedule, admission))
    monkeypatch.setattr(v8, "_runtime_projection", lambda _frozen: binding["runtime"])
    monkeypatch.setattr(v8, "validate_capacity_evidence", lambda _path: {"ready": True, "observed_at": "2026-08-29T00:00:00+00:00"})
    monkeypatch.setattr(v8, "_validate_disclosure_ack", lambda *_args: None)
    monkeypatch.setattr(v8, "_require_clean_pushed", lambda: None)
    monkeypatch.setattr(v8, "_require_no_orphan_output_cells", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(v8, "_validate_disclosed_payload", lambda *_args: None)
    monkeypatch.setattr(v8, "_validate_contact_sessions", lambda *_args: None)
    monkeypatch.setattr(v8, "_validate_base_attempt_context", lambda *_args: None)
    monkeypatch.setattr(v8, "_load_predecessor_runner", lambda: SimpleNamespace(_revalidate_predecessor_event=lambda *_args: None))
    monkeypatch.setattr(v8, "_proof", lambda *_args: (tmp_path / "proof", "a" * 64))
    monkeypatch.setattr(v8, "_recorded_provider_contacts", lambda *_args: 1)
    monkeypatch.setattr(v8, "_physical_output_sessions", lambda output, _event: ["native-183"] if output.exists() else [])
    monkeypatch.setattr(v8, "_load_hbq_runner", lambda: SimpleNamespace(RetryDisclosurePause=_RetryPause))
    monkeypatch.setattr(v8, "_claim", delayed_claim)
    monkeypatch.setattr(v8, "_dispatch_event", dispatch)
    monkeypatch.setattr(v8, "_accepted", accepted)
    v8._resume_guard_executor_path = str(runtime / "executor.py")
    v8._resume_guard_executor_sha256 = __import__("hashlib").sha256((runtime / "executor.py").read_bytes()).hexdigest()
    monkeypatch.setattr(guard, "_load_v8", lambda _executor: v8)
    for name in ("guard-one", "guard-two"):
        guard.prepare_guard(source_root=source, closed_root=closed, v7_root=v7, work_root=work, guard_root=tmp_path / name, v8_runtime_root=runtime)
    monkeypatch.setattr(adapter, "_load_pinned_modules", lambda _runtime: (guard, v8, runtime, runtime / "executor.py"))
    monkeypatch.setattr(adapter, "_load_pinned_successor_runner", lambda *_args: object())
    outcomes: list[Any] = []

    def invoke(root: Path) -> None:
        try:
            outcomes.append(adapter.dispatch_one(source_root=source, closed_root=closed, v7_root=v7, work_root=work, guard_root=root, capacity_evidence=capacity, disclosure_ack=work / v8.DISCLOSURE_ACK, allow_remote=True, v8_runtime_root=runtime))
        except BaseException as exc:
            outcomes.append(exc)

    first = threading.Thread(target=invoke, args=(tmp_path / "guard-one",)); first.start()
    assert entered.wait(timeout=5)
    second = threading.Thread(target=invoke, args=(tmp_path / "guard-two",)); second.start()
    second.join(timeout=5); release.set(); first.join(timeout=5)
    assert native_commands == [183], [repr(value) for value in outcomes]
    assert sum(isinstance(value, ValueError) and "Exclusive V8 claim" in str(value) for value in outcomes) == 1
    assert sum(isinstance(value, list) and value == schedule[:2] for value in outcomes) == 1
    assert v8._output_path(work, schedule[1]).is_file() and not v8._output_path(work, schedule[2]).exists()


def test_private_runner_loader_is_not_reached_before_a_guard_claim() -> None:
    adapter = _adapter(); events = [{"sequence": 182}, {"sequence": 183}]
    v8, state = _v8(events); guard = _Guard(events[1]); state["capacity_ok"] = False
    calls: list[object] = []
    adapter._load_pinned_modules = lambda _runtime: (guard, v8, Path("C:/adapter-test/runtime"), Path("C:/adapter-test/runtime/executor.py"))
    adapter._load_pinned_successor_runner = lambda *_args: calls.append(object())
    with pytest.raises(ValueError, match="Capacity"):
        adapter.dispatch_one(
            source_root=Path("C:/adapter-test/source"), closed_root=Path("C:/adapter-test/closed"), v7_root=Path("C:/adapter-test/v7"), work_root=Path("C:/adapter-test/work"), guard_root=Path("C:/adapter-test/guard"), capacity_evidence=Path("C:/adapter-test/capacity.json"), disclosure_ack=Path("C:/adapter-test/work/disclosure-acknowledgement.json"), allow_remote=True,
        )
    assert calls == [] and guard.dispatches == 0
