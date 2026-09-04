from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

PATH = (
    Path(__file__).parents[1]
    / "evaluation-results"
    / "hbq-multisample-repeatability-v1-remainder-capacity-reset-v8-precontact-recovery-v2"
    / "adapter.py"
)


def _controller() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "v8_precontact_recovery_v2_test", PATH
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _event(sequence: int) -> dict[str, Any]:
    return {
        "sequence": sequence,
        "item_id": f"item-{sequence}",
        "arm_id": "native",
        "repetition": 1,
    }


def _tool_call(name: str, call_id: str, value: str) -> dict[str, Any]:
    return {
        "type": "response_item",
        "payload": {
            "type": "custom_tool_call",
            "name": name,
            "call_id": call_id,
            "input": value,
        },
    }


def _tool_output(call_id: str, value: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "response_item",
        "payload": {
            "type": "custom_tool_call_output",
            "call_id": call_id,
            "output": [
                {"type": "input_text", "text": ""},
                {"type": "input_text", "text": json.dumps(value)},
            ],
        },
    }


def _rollout(path: Path, module: ModuleType, *, stack: str | None = None) -> bytes:
    invocation = (
        "const anchored = { adapter: 'adapter.py', capacity: 'failed-capacity.json' };"
    )
    terminal_input = "const r = await tools.write_stdin({session_id:27739,chars:''});\ntext(JSON.stringify(r));\n"
    module.EXPECTED_INVOCATION_INPUT_SHA256 = hashlib.sha256(
        invocation.encode()
    ).hexdigest()
    module.EXPECTED_TERMINAL_POLL_INPUT_SHA256 = hashlib.sha256(
        terminal_input.encode()
    ).hexdigest()
    rows: list[dict[str, Any]] = [
        {"type": "session_meta", "payload": {"id": module.ROOT_TASK_ID}},
        _tool_call("exec", "exec-1", invocation),
        _tool_output("exec-1", {"session_id": module.UNIFIED_SESSION_ID}),
    ]
    for index in range(module.POLL_COUNT):
        call_id = f"poll-{index:02d}"
        rows.append(_tool_call("exec", call_id, terminal_input))
        if index + 1 == module.POLL_COUNT:
            rows.append(
                _tool_output(
                    call_id,
                    {
                        "exit_code": 1,
                        "output": stack
                        or "adapter.py\nin delegate\n_settle_one\nvalidate_capacity_evidence\nValueError: Capacity evidence is not current",
                    },
                )
            )
        else:
            rows.append(
                _tool_output(call_id, {"session_id": module.UNIFIED_SESSION_ID})
            )
    raw = b"".join(
        json.dumps(row, separators=(",", ":")).encode() + b"\n" for row in rows
    )
    module.REVIEWED_TERMINAL_LINE = len(rows)
    module.EXPECTED_PREFIX_BYTES = len(raw)
    module.EXPECTED_PREFIX_SHA256 = hashlib.sha256(raw).hexdigest()
    module.EXPECTED_TERMINAL_OUTPUT_SHA256 = hashlib.sha256(
        json.dumps(rows[-1]["payload"]["output"][1]["text"]).encode()
    ).hexdigest()
    path.write_bytes(raw)
    return raw


def test_actual_wrapper_shape_requires_all_linked_polls(tmp_path: Path) -> None:
    module = _controller()
    raw = _rollout(tmp_path / "rollout.jsonl", module)
    prefix, manifest = module.capture_rollout_prefix(tmp_path / "rollout.jsonl")
    assert prefix == raw
    assert manifest["poll_count"] == 17
    assert (
        manifest["failure_label"]
        == "pre_provider_pre_v8_intent_capacity_failure_at_settle_entry"
    )


@pytest.mark.parametrize(
    "mutation",
    ["wrong-session", "duplicate-terminal", "missing-output", "later-dispatch"],
)
def test_fixed_prefix_rejects_changed_transcript_bytes(
    tmp_path: Path, mutation: str
) -> None:
    module = _controller()
    path = tmp_path / "rollout.jsonl"
    _rollout(path, module)
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    if mutation == "wrong-session":
        rows[3]["payload"]["input"] = (
            "const r = await tools.write_stdin({session_id:1,chars:''});\ntext(JSON.stringify(r));\n"
        )
    elif mutation == "duplicate-terminal":
        rows.append(rows[-1])
    elif mutation == "missing-output":
        del rows[4]
    else:
        rows[-1]["payload"]["output"][1]["text"] = json.dumps(
            {
                "exit_code": 1,
                "output": "adapter.delegate\n_settle_one\nvalidate_capacity_evidence\nattempt-intent\nValueError: Capacity evidence is not current",
            }
        )
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
    with pytest.raises((TypeError, ValueError)):
        module.capture_rollout_prefix(path)


@pytest.mark.skipif(
    not os.environ.get("CWR_V2_NATIVE_ROLLOUT"),
    reason="explicit local read-only rollout path required",
)
def test_native_rollout_prefix_is_opt_in_and_read_only() -> None:
    module = _controller()
    source = Path(os.environ["CWR_V2_NATIVE_ROLLOUT"])
    prefix, manifest = module.capture_rollout_prefix(source)
    assert source.read_bytes().startswith(prefix)
    assert manifest["root_task_id"] == module.ROOT_TASK_ID


def _old_guard(
    root: Path,
    events: list[dict[str, Any]],
    module: ModuleType,
    *,
    malformed: bool = False,
) -> None:
    root.mkdir()
    (root / "claims").mkdir()
    (root / "guard-journal.lock").write_bytes(b"\0")
    (root / "guard-binding.json").write_text(
        json.dumps({"study_id": "old"}) + "\n", encoding="utf-8"
    )
    rows = [
        {
            "event": "guard-prepared",
            "binding_sha256": module.sha(root / "guard-binding.json"),
        }
    ]
    for event in events:
        claim = {
            "event": "delegate-intent",
            "sequence": event["sequence"],
            "event_sha256": hashlib.sha256(module.canonical(event)).hexdigest(),
        }
        if malformed and event["sequence"] == 265:
            claim["event_sha256"] = "f" * 64
        rows.append(claim)
        if event["sequence"] != 265:
            rows.append(
                {
                    "event": "delegate-completed",
                    "sequence": event["sequence"],
                    "event_sha256": claim["event_sha256"],
                }
            )
        (root / "claims" / f"sequence-{event['sequence']:04d}.json").write_text(
            json.dumps(claim), encoding="utf-8"
        )
    (root / "guard-journal.jsonl").write_text(
        "\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8"
    )
    module.EXPECTED_OLD_GUARD_HASHES = {
        name: module.sha(root / name) for name in module.EXPECTED_OLD_GUARD_HASHES
    }


def _fake(
    module: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[dict[str, Path], dict[str, Any]]:
    roots = {
        name: tmp_path / name for name in ("source", "closed", "v7", "work", "runtime")
    }
    for root in roots.values():
        root.mkdir()
    (roots["runtime"] / "executor.py").write_text("# pinned fake\n", encoding="utf-8")
    (roots["source"] / "frozen-run-contract.json").write_text("{}", encoding="utf-8")
    for name in ("journal.jsonl", "schedule.jsonl", "disclosure-acknowledgement.json"):
        (roots["work"] / name).write_text("", encoding="utf-8")
    roots["failed"] = tmp_path / "failed-capacity.json"
    roots["failed"].write_text("immutable", encoding="utf-8")
    roots["current"] = tmp_path / "current-capacity.json"
    roots["current"].write_text("fresh", encoding="utf-8")
    events = [_event(value) for value in range(182, 267)]
    state: dict[str, Any] = {
        "accepted": events[:83],
        "capacity": True,
        "capacity_checks": 0,
        "native": 0,
        "journal_seq265": False,
        "output": False,
    }

    def accepted(*_args: Any) -> list[dict[str, Any]]:
        return list(state["accepted"])

    def capacity(_path: Path) -> dict[str, bool]:
        state["capacity_checks"] += 1
        if not state["capacity"]:
            raise ValueError("Capacity evidence is not current")
        return {"ready": True}

    def settle(
        _runner: Any,
        _frozen: Any,
        _source: Path,
        _work: Path,
        _schedule: Any,
        _admission: Any,
        prior: list[dict[str, Any]],
        event: dict[str, Any],
        *_args: Any,
    ) -> list[dict[str, Any]]:
        state["native"] += 1
        state["accepted"] = [*prior, event]
        return list(state["accepted"])

    v8 = SimpleNamespace(
        JOURNAL="journal.jsonl",
        SCHEDULE="schedule.jsonl",
        DISCLOSURE_ACK="disclosure-acknowledgement.json",
        _external=lambda value: Path(value),
        _verify_prepared=lambda *_args: (
            {"runtime": {"frozen": True}},
            events,
            {"admission": True},
        ),
        _accepted=accepted,
        _require_no_orphan_output_cells=lambda *_args: None,
        _output_path=lambda current, event: (
            Path(current) / "outputs" / f"{event['sequence']}.json"
        ),
        _validate_contact_sessions=lambda *_args: None,
        _work_path=lambda current, *parts, **_kwargs: Path(current).joinpath(*parts),
        validate_capacity_evidence=capacity,
        _validate_disclosure_ack=lambda *_args: None,
        _require_clean_pushed=lambda: None,
        _plain_path=lambda path: Path(path),
        read_json=lambda _path: {},
        _runtime_projection=lambda _frozen: {"frozen": True},
        _settle_one=settle,
    )
    guard = SimpleNamespace(_assert_no_unresolved_v8_state=lambda *_args: None)
    runner = SimpleNamespace(
        runtime_identity=lambda: {
            "helper_id": "runner",
            "path": "runner.py",
            "bytes": 1,
            "sha256": "c" * 64,
        }
    )
    adapter = SimpleNamespace(_load_pinned_successor_runner=lambda *_args: runner)
    monkeypatch.setattr(
        module, "_load_modules", lambda _runtime: (adapter, guard, v8, roots["runtime"])
    )
    monkeypatch.setattr(module, "_no_live_v8_process", lambda *_args: None)
    module.EXPECTED_PATHS = {
        "source": roots["source"],
        "closed": roots["closed"],
        "v7": roots["v7"],
        "work": roots["work"],
        "old_guard": tmp_path / "old-guard",
        "failed_capacity": roots["failed"],
        "rollout": tmp_path / "rollout.jsonl",
    }
    module.EXPECTED_FAILED_CAPACITY_SHA256 = module.sha(roots["failed"])
    module.EXPECTED_EVENT_SHA256 = hashlib.sha256(
        module.canonical(_event(265))
    ).hexdigest()
    return roots, state


def _prepared(
    module: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[dict[str, Path], dict[str, Any]]:
    roots, state = _fake(module, tmp_path, monkeypatch)
    rollout = tmp_path / "rollout.jsonl"
    _rollout(rollout, module)
    old = tmp_path / "old-guard"
    _old_guard(old, [_event(value) for value in range(261, 266)], module)
    module.prepare_recovery(
        source_root=roots["source"],
        closed_root=roots["closed"],
        v7_root=roots["v7"],
        work_root=roots["work"],
        old_guard_root=old,
        rollout=rollout,
        failed_capacity_evidence=roots["failed"],
        recovery_root=tmp_path / "recovery",
        v8_runtime_root=roots["runtime"],
    )
    roots["rollout"] = rollout
    roots["old"] = old
    roots["recovery"] = tmp_path / "recovery"
    return roots, state


def _preflight(module: ModuleType, roots: dict[str, Path]) -> dict[str, Any]:
    return module.preflight_recovery(
        recovery_root=roots["recovery"],
        work_root=roots["work"],
        current_capacity_evidence=roots["current"],
        disclosure_ack=roots["work"] / "disclosure-acknowledgement.json",
        v8_runtime_root=roots["runtime"],
    )


def test_prepare_is_provider_free_and_prefix_allows_only_suffix_append(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _controller()
    roots, state = _prepared(module, tmp_path, monkeypatch)
    assert state["capacity_checks"] == 0
    roots["rollout"].write_bytes(
        roots["rollout"].read_bytes() + b'{"suffix":"allowed"}\n'
    )
    assert _preflight(module, roots)["provider_calls"] == 0
    payload = roots["rollout"].read_bytes()
    roots["rollout"].write_bytes(b"x" + payload[1:])
    with pytest.raises(ValueError, match="prefix"):
        _preflight(module, roots)


def test_prepare_rejects_nonhistorical_root_association(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _controller()
    roots, _state = _fake(module, tmp_path, monkeypatch)
    rollout = tmp_path / "rollout.jsonl"
    _rollout(rollout, module)
    old = tmp_path / "old-guard"
    _old_guard(old, [_event(value) for value in range(261, 266)], module)
    wrong = tmp_path / "wrong-source"
    wrong.mkdir()
    with pytest.raises(ValueError, match="historical"):
        module.prepare_recovery(
            source_root=wrong,
            closed_root=roots["closed"],
            v7_root=roots["v7"],
            work_root=roots["work"],
            old_guard_root=old,
            rollout=rollout,
            failed_capacity_evidence=roots["failed"],
            recovery_root=tmp_path / "recovery",
            v8_runtime_root=roots["runtime"],
        )


@pytest.mark.parametrize(
    "change", ["old-claim", "failed-capacity", "runtime", "journal", "output"]
)
def test_preflight_rejects_bound_evidence_or_seq265_artifacts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, change: str
) -> None:
    module = _controller()
    roots, _state = _prepared(module, tmp_path, monkeypatch)
    if change == "old-claim":
        claim = roots["old"] / "claims" / "sequence-0265.json"
        claim.write_text("{}", encoding="utf-8")
    elif change == "failed-capacity":
        roots["failed"].write_text("changed", encoding="utf-8")
    elif change == "runtime":
        # The fake identity hashes the requested runtime executor just as the real adapter does.
        (roots["runtime"] / "executor.py").write_text("changed", encoding="utf-8")
    elif change == "journal":
        (roots["work"] / "journal.jsonl").write_text(
            '{"sequence":265}\n', encoding="utf-8"
        )
    else:
        output = roots["work"] / "outputs" / "265.json"
        output.parent.mkdir()
        output.write_text("exists", encoding="utf-8")
    with pytest.raises((TypeError, ValueError)):
        _preflight(module, roots)


def test_stale_capacity_blocks_before_claim_or_native_settlement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _controller()
    roots, state = _prepared(module, tmp_path, monkeypatch)
    state["capacity"] = False
    with pytest.raises(ValueError, match="Capacity"):
        module.settle_one_after_review(
            source_root=roots["source"],
            closed_root=roots["closed"],
            v7_root=roots["v7"],
            work_root=roots["work"],
            recovery_root=roots["recovery"],
            current_capacity_evidence=roots["current"],
            disclosure_ack=roots["work"] / "disclosure-acknowledgement.json",
            allow_remote=True,
            v8_runtime_root=roots["runtime"],
        )
    assert state["native"] == 0 and not list((roots["recovery"] / "claims").iterdir())


def test_default_off_then_exact_one_terminal_no_resend(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _controller()
    roots, state = _prepared(module, tmp_path, monkeypatch)
    kwargs = {
        "source_root": roots["source"],
        "closed_root": roots["closed"],
        "v7_root": roots["v7"],
        "work_root": roots["work"],
        "recovery_root": roots["recovery"],
        "current_capacity_evidence": roots["current"],
        "disclosure_ack": roots["work"] / "disclosure-acknowledgement.json",
        "v8_runtime_root": roots["runtime"],
    }
    with pytest.raises(ValueError, match="explicit remote"):
        module.settle_one_after_review(**kwargs)
    assert state["native"] == 0
    settled = module.settle_one_after_review(**kwargs, allow_remote=True)
    assert [row["sequence"] for row in settled][-1] == 265 and state["native"] == 1
    with pytest.raises(ValueError, match="pristine|resend"):
        module.settle_one_after_review(**kwargs, allow_remote=True)
    assert state["native"] == 1


@pytest.mark.parametrize(
    "inventory", ["", "[]", "[{}]", '[{"ProcessId":1,"ParentProcessId":0}]']
)
def test_process_inventory_cannot_silently_prove_absence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, inventory: str
) -> None:
    module = _controller()
    monkeypatch.setattr(module.os, "getpid", lambda: 42)
    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(stdout=inventory),
    )
    with pytest.raises(ValueError, match="inventory|process identities"):
        module._no_live_v8_process(tmp_path / "work", tmp_path / "runtime")


def test_process_inventory_excludes_ancestry_but_rejects_competitor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _controller()
    work, runtime = tmp_path / "work", tmp_path / "runtime"
    records = [
        {"ProcessId": 0, "ParentProcessId": 0, "CommandLine": None},
        {"ProcessId": 42, "ParentProcessId": 41, "CommandLine": str(work)},
        {"ProcessId": 41, "ParentProcessId": 0, "CommandLine": str(runtime)},
    ]
    monkeypatch.setattr(module.os, "getpid", lambda: 42)
    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(stdout=json.dumps(records)),
    )
    module._no_live_v8_process(work, runtime)
    records.append({"ProcessId": 43, "ParentProcessId": 41, "CommandLine": str(work)})
    with pytest.raises(ValueError, match="Another V8 process"):
        module._no_live_v8_process(work, runtime)


def test_runtime_copy_is_not_historical_path(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="exact historical"):
        _controller()._load_modules(tmp_path)


def test_old_guard_reminted_binding_is_not_historical(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _controller()
    roots, _state = _prepared(module, tmp_path, monkeypatch)
    binding = roots["old"] / "guard-binding.json"
    journal = roots["old"] / "guard-journal.jsonl"
    binding.write_text('{"study_id":"replacement"}\n', encoding="utf-8")
    rows = [
        json.loads(line) for line in journal.read_text(encoding="utf-8").splitlines()
    ]
    rows[0]["binding_sha256"] = module.sha(binding)
    journal.write_text(
        "\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8"
    )
    with pytest.raises(ValueError, match="historical bytes"):
        module._old_evidence(
            roots["old"], [_event(i) for i in range(182, 265)], _event(265)
        )
