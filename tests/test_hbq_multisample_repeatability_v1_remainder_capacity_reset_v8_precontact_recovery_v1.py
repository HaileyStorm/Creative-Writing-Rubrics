from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

PATH = Path(__file__).parents[1] / "evaluation-results" / "hbq-multisample-repeatability-v1-remainder-capacity-reset-v8-precontact-recovery-v1" / "adapter.py"


def _controller() -> ModuleType:
    spec = importlib.util.spec_from_file_location("v8_precontact_recovery_test", PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _event(sequence: int) -> dict[str, Any]:
    return {"sequence": sequence, "item_id": f"item-{sequence}", "arm_id": "native", "repetition": 1}


def _old_guard(root: Path, events: list[dict[str, Any]], module: ModuleType, *, bad_claim: bool = False) -> dict[str, Any]:
    root.mkdir(); (root / "claims").mkdir(); (root / "guard-journal.lock").write_bytes(b"\0")
    (root / "guard-binding.json").write_text(json.dumps({"study_id": "old"}) + "\n", encoding="utf-8")
    rows = [{"event": "guard-prepared", "binding_sha256": module.sha(root / "guard-binding.json")}]
    claims: list[dict[str, Any]] = []
    for event in events:
        claim = {"event": "delegate-intent", "sequence": event["sequence"], "event_sha256": hashlib.sha256(module.canonical(event)).hexdigest()}
        if bad_claim and event["sequence"] == 265: claim["event_sha256"] = "f" * 64
        claims.append(claim); rows.append(claim)
        if event["sequence"] != 265: rows.append({"event": "delegate-completed", "sequence": event["sequence"], "event_sha256": claim["event_sha256"]})
        (root / "claims" / f"sequence-{event['sequence']:04d}.json").write_text(json.dumps(claim) + "\n", encoding="utf-8")
    (root / "guard-journal.jsonl").write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
    return claims[-1]


def _rollout(path: Path, module: ModuleType, capacity: Path, event: dict[str, Any], *, bad: bool = False) -> None:
    arguments = {"adapter": str(module.EXACT_ONE_ADAPTER), "capacity": str(capacity.absolute()), "event_sha256": hashlib.sha256(module.canonical(event)).hexdigest()}
    terminal = {"call_id": "stdin-1", "output": {"exit_code": 1, "output": "delegate_precontact.validate_capacity_evidence\nValueError: Capacity evidence is not current"}}
    if bad: terminal["output"]["output"] = "forged"
    rows = [
        {"session_meta": {"payload": {"id": module.ROOT_TASK_ID}}},
        {"response_item": {"name": "functions.exec", "call_id": "exec-1", "arguments": arguments}},
        {"response_item": {"call_id": "exec-1", "output": {"session_id": 27739}}},
        {"response_item": {"name": "functions.write_stdin", "call_id": "stdin-1", "arguments": {"session_id": 27739}}},
        {"response_item": terminal},
    ]
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")


def _fake(module: ModuleType, tmp_path: Path) -> tuple[Any, dict[str, Any], dict[str, Path], list[dict[str, Any]]]:
    source, closed, v7, work, runtime = (tmp_path / name for name in ("source", "closed", "v7", "work", "runtime"))
    for root in (source, closed, v7, work, runtime): root.mkdir()
    (source / "frozen-run-contract.json").write_text("{}", encoding="utf-8")
    for name in ("journal.jsonl", "schedule.jsonl", "disclosure-acknowledgement.json"):
        (work / name).write_text("", encoding="utf-8")
    events = [_event(value) for value in range(182, 267)]
    state: dict[str, Any] = {"accepted": events[:83], "native": 0, "capacity": True}
    def accepted(*_args: Any) -> list[dict[str, Any]]: return list(state["accepted"])
    def settle(_runner: Any, _frozen: Any, _source: Path, _work: Path, _schedule: Any, _admission: Any, prior: list[dict[str, Any]], event: dict[str, Any], *_args: Any) -> list[dict[str, Any]]:
        state["native"] += 1
        state["accepted"] = [*prior, event]; return list(state["accepted"])
    v8 = SimpleNamespace(JOURNAL="journal.jsonl", SCHEDULE="schedule.jsonl", DISCLOSURE_ACK="disclosure-acknowledgement.json",
        _external=lambda value: Path(value), _verify_prepared=lambda *_args: ({"runtime": {"frozen": True}}, events, {"admission": True}),
        _accepted=accepted, _require_no_orphan_output_cells=lambda *_args: None, _output_path=lambda current, event: Path(current) / "outputs" / f"{event['sequence']}.json",
        _validate_contact_sessions=lambda *_args: None, _work_path=lambda current, *parts, **_kwargs: Path(current).joinpath(*parts), validate_capacity_evidence=lambda _path: ({"ok": True} if state["capacity"] else (_ for _ in ()).throw(ValueError("capacity stale"))),
        _validate_disclosure_ack=lambda *_args: None, _require_clean_pushed=lambda: None, _plain_path=lambda path: Path(path), read_json=lambda _path: {},
        _runtime_projection=lambda _frozen: {"frozen": True}, _settle_one=settle)
    guard = SimpleNamespace(_assert_no_unresolved_v8_state=lambda *_args: None)
    runner = SimpleNamespace(runtime_identity=lambda: {"helper_id": "runner", "path": "run_successor.py", "bytes": 1, "sha256": "c" * 64})
    adapter = SimpleNamespace(_load_pinned_successor_runner=lambda *_args: runner)
    module._load_modules = lambda _runtime: (adapter, guard, v8, runtime)
    module.sha = lambda _path: "d" * 64
    module._no_live_v8_process = lambda *_args: None
    return v8, state, {"source": source, "closed": closed, "v7": v7, "work": work, "runtime": runtime}, events


def _prepare(module: ModuleType, tmp_path: Path, *, bad_rollout: bool = False, bad_claim: bool = False) -> tuple[dict[str, Any], Any, dict[str, Any], dict[str, Path], list[dict[str, Any]]]:
    v8, state, roots, events = _fake(module, tmp_path); old = tmp_path / "old"; _old_guard(old, events[79:84], module, bad_claim=bad_claim)
    current_capacity = tmp_path / "current-capacity.json"; current_capacity.write_text("{}", encoding="utf-8")
    failed_capacity = tmp_path / "failed-capacity.json"; failed_capacity.write_text("{}", encoding="utf-8")
    rollout = tmp_path / "rollout.jsonl"; _rollout(rollout, module, failed_capacity, events[83], bad=bad_rollout)
    record = module.prepare_recovery(source_root=roots["source"], closed_root=roots["closed"], v7_root=roots["v7"], work_root=roots["work"], old_guard_root=old, rollout=rollout, failed_capacity_evidence=failed_capacity, current_capacity_evidence=current_capacity, recovery_root=tmp_path / "recovery", v8_runtime_root=roots["runtime"])
    roots["current_capacity"] = current_capacity
    roots["failed_capacity"] = failed_capacity
    roots["rollout"] = rollout
    return record, v8, state, roots, events


def test_provider_free_prepare_binds_exact_precontact_evidence_and_keeps_counter_zero(tmp_path: Path) -> None:
    module = _controller(); record, _v8, state, roots, _events = _prepare(module, tmp_path)
    assert record["target_sequence"] == 265 and record["status"] == module.STATUS
    assert state["native"] == 0
    result = module.preflight_recovery(recovery_root=tmp_path / "recovery", work_root=roots["work"], current_capacity_evidence=roots["current_capacity"], disclosure_ack=roots["work"] / "disclosure-acknowledgement.json", v8_runtime_root=roots["runtime"])
    assert result["provider_calls"] == 0 and state["native"] == 0


@pytest.mark.parametrize("bad_rollout,bad_claim", [(True, False), (False, True)])
def test_forged_rollout_or_old_claim_fails_closed(tmp_path: Path, bad_rollout: bool, bad_claim: bool) -> None:
    module = _controller()
    with pytest.raises(ValueError): _prepare(module, tmp_path, bad_rollout=bad_rollout, bad_claim=bad_claim)


def test_missing_or_modified_app_rollout_fails_closed(tmp_path: Path) -> None:
    module = _controller(); _record, _v8, _state, roots, _events = _prepare(module, tmp_path)
    roots["rollout"].unlink()
    with pytest.raises(ValueError, match="Missing required path"):
        module.preflight_recovery(recovery_root=tmp_path / "recovery", work_root=roots["work"], current_capacity_evidence=roots["current_capacity"], disclosure_ack=roots["work"] / "disclosure-acknowledgement.json", v8_runtime_root=roots["runtime"])


def test_old_claim_for_a_different_event_fails_closed(tmp_path: Path) -> None:
    module = _controller(); _v8, _state, roots, events = _fake(module, tmp_path)
    wrong = dict(events[83]); wrong["arm_id"] = "wrong"
    old = tmp_path / "old"; _old_guard(old, [*events[79:83], wrong], module)
    with pytest.raises(ValueError, match="guard journal"):
        module.prepare_recovery(source_root=roots["source"], closed_root=roots["closed"], v7_root=roots["v7"], work_root=roots["work"], old_guard_root=old, rollout=tmp_path / "rollout.jsonl", failed_capacity_evidence=tmp_path / "failed-capacity.json", current_capacity_evidence=tmp_path / "current-capacity.json", recovery_root=tmp_path / "recovery", v8_runtime_root=roots["runtime"])


def test_seq265_journal_or_output_artifact_blocks_recovery(tmp_path: Path) -> None:
    module = _controller(); v8, _state, roots, _events = _fake(module, tmp_path)
    (roots["work"] / v8.JOURNAL).write_text(json.dumps({"event": "provider-contacts", "sequence": 265}) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="journal"):
        module.prepare_recovery(source_root=roots["source"], closed_root=roots["closed"], v7_root=roots["v7"], work_root=roots["work"], old_guard_root=tmp_path / "old", rollout=tmp_path / "rollout.jsonl", failed_capacity_evidence=tmp_path / "failed-capacity.json", current_capacity_evidence=tmp_path / "current-capacity.json", recovery_root=tmp_path / "recovery", v8_runtime_root=roots["runtime"])


def test_live_settlement_is_explicitly_no_go_and_never_contacts(tmp_path: Path) -> None:
    module = _controller(); _record, _v8, state, roots, _events = _prepare(module, tmp_path)
    with pytest.raises(ValueError, match="NO-GO"):
        module.settle_one_after_review(source_root=roots["source"], closed_root=roots["closed"], v7_root=roots["v7"], work_root=roots["work"], recovery_root=tmp_path / "recovery", current_capacity_evidence=roots["current_capacity"], disclosure_ack=roots["work"] / "disclosure-acknowledgement.json", allow_remote=True, v8_runtime_root=roots["runtime"])
    assert state["native"] == 0 and not list((tmp_path / "recovery" / "claims").iterdir())


def test_fresh_capacity_gate_blocks_before_native_settlement(tmp_path: Path) -> None:
    module = _controller(); _record, _v8, state, roots, _events = _prepare(module, tmp_path); state["capacity"] = False
    with pytest.raises(ValueError, match="capacity"):
        module.preflight_recovery(recovery_root=tmp_path / "recovery", work_root=roots["work"], current_capacity_evidence=roots["current_capacity"], disclosure_ack=roots["work"] / "disclosure-acknowledgement.json", v8_runtime_root=roots["runtime"])
    assert state["native"] == 0
    assert not list((tmp_path / "recovery" / "claims").iterdir())
    state["capacity"] = True
    assert module.preflight_recovery(recovery_root=tmp_path / "recovery", work_root=roots["work"], current_capacity_evidence=roots["current_capacity"], disclosure_ack=roots["work"] / "disclosure-acknowledgement.json", v8_runtime_root=roots["runtime"])["provider_calls"] == 0
