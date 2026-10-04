from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

import pytest

from hbqrs import codex_receipts as receipts

THREAD = "01a10869-52f9-7c23-bc33-ffdffe60b927"
TURN = "01a10869-559a-7be3-a156-375f7323ebab"
FOREIGN = "01a10860-7036-71b1-8036-d6556fe1dcd0"


def native_fixture(cwd: Path, prompt: str = "Judge this synthetic passage.",
                   final: str = '{"verdicts":[]}') -> tuple[list[dict], list[dict], bytes]:
    def message(role: str, text: str, kinds: list[str], phase: str | None = None) -> dict:
        payload = {"type": "message", "role": role,
                   "content": [{"type": "output_text" if role == "assistant" else "input_text", "text": text}],
                   "internal_chat_message_metadata_passthrough": {"turn_id": TURN, "content_item_kinds": kinds}}
        if phase:
            payload["phase"] = phase
        return {"type": "response_item", "payload": payload}
    rollout = [
        {"type": "session_meta", "payload": {"id": THREAD, "source": "exec", "model_provider": "openai", "cwd": str(cwd)}},
        {"type": "event_msg", "payload": {"type": "task_started", "turn_id": TURN}},
        message("developer", "Host instructions.", ["host_skills.instructions"]),
        message("user", "Environment description.", ["environments.environment_context"]),
        {"type": "world_state", "payload": {"full": True, "state": {}}},
        {"type": "turn_context", "payload": {"turn_id": TURN, "model": "gpt-6.1-sol", "effort": "high", "cwd": str(cwd)}},
        message("user", prompt, ["user.text"]),
        {"type": "event_msg", "payload": {"type": "item_completed", "thread_id": THREAD, "turn_id": TURN, "item": {"type": "UserMessage"}}},
        message("assistant", final, ["unknown"], "final_answer"),
        {"type": "token_usage_record", "payload": {"thread_id": THREAD, "turn_id": TURN, "response_id": "response-1", "usage": {}}},
        {"type": "event_msg", "payload": {"type": "token_count", "info": {}}},
        {"type": "event_msg", "payload": {"type": "task_complete", "turn_id": TURN, "last_agent_message": final}},
    ]
    events = [
        {"type": "thread.started", "thread_id": THREAD},
        {"type": "item.completed", "item": {"id": "item_0", "type": "error", "message": receipts.STARTUP_DIAGNOSTIC}},
        {"type": "turn.started"},
        {"type": "item.completed", "item": {"id": "item_1", "type": "agent_message", "text": final}},
        {"type": "turn.completed", "usage": {"input_tokens": 12, "output_tokens": 4}},
    ]
    return rollout, events, final.encode()


def raw(rows: list[dict]) -> bytes:
    return b"".join(json.dumps(row, separators=(",", ":")).encode() + b"\n" for row in rows)


def project(tmp_path: Path, rollout: list[dict], events: list[dict], final: bytes) -> dict:
    return receipts.project(raw(rollout), raw(events), final, prompt="Judge this synthetic passage.",
                            model="gpt-6.1-sol", reasoning="high", cwd=tmp_path)


def test_native_exec_receipt_accepts_004_shape_with_separate_environment(tmp_path: Path) -> None:
    value = project(tmp_path, *native_fixture(tmp_path))
    assert value["reported"] == {"model": "gpt-6.1-sol", "reasoning_effort": "high", "provider": "openai", "session_id": THREAD}
    assert value["startup_diagnostics"] == ["code_mode_host_disabled_startup_v1"]
    assert value["zero_tool_activity_observed"] is True
    assert value["physical_contact_cardinality_proven"] is False
    assert len(value["selected_line_sha256"]) == 6


@pytest.mark.parametrize("change", ["thread", "prompt", "model", "effort", "provider", "final", "completion",
                                    "foreign_turn", "tool", "unexpected_user", "missing_complete", "missing_context"])
def test_native_receipt_rejects_unbound_or_foreign_evidence(tmp_path: Path, change: str) -> None:
    rollout, events, final = native_fixture(tmp_path)
    if change == "thread": rollout[0]["payload"]["id"] = FOREIGN
    elif change == "prompt": rollout[6]["payload"]["content"][0]["text"] = "Different prompt."
    elif change == "model": rollout[5]["payload"]["model"] = "another-model"
    elif change == "effort": rollout[5]["payload"]["effort"] = "low"
    elif change == "provider": rollout[0]["payload"]["model_provider"] = "another-provider"
    elif change == "final": rollout[8]["payload"]["content"][0]["text"] = "different"
    elif change == "completion": rollout[-1]["payload"]["last_agent_message"] = "different"
    elif change == "foreign_turn": rollout[6]["payload"]["internal_chat_message_metadata_passthrough"]["turn_id"] = FOREIGN
    elif change == "tool": rollout[7]["payload"]["item"]["type"] = "CommandExecution"
    elif change == "unexpected_user": rollout[3]["payload"]["internal_chat_message_metadata_passthrough"]["content_item_kinds"] = ["user.text"]
    elif change == "missing_complete": rollout.pop()
    elif change == "missing_context": rollout.pop(5)
    with pytest.raises(ValueError):
        project(tmp_path, rollout, events, final)


@pytest.mark.parametrize("change", ["tool", "foreign_thread", "error", "late_diagnostic", "missing_complete", "final"])
def test_json_events_reject_tools_errors_and_incomplete_or_foreign_turns(tmp_path: Path, change: str) -> None:
    rollout, events, final = native_fixture(tmp_path)
    if change == "tool": events[3]["item"]["type"] = "command_execution"
    elif change == "foreign_thread": events[3]["thread_id"] = FOREIGN
    elif change == "error": events[1]["item"]["message"] = "Some other error."
    elif change == "late_diagnostic": events[1], events[2] = events[2], events[1]
    elif change == "missing_complete": events.pop()
    elif change == "final": events[3]["item"]["text"] = "different"
    with pytest.raises(ValueError):
        project(tmp_path, rollout, events, final)


def test_truncated_receipt_and_missing_exact_rollout_fail(tmp_path: Path) -> None:
    rollout, events, final = native_fixture(tmp_path)
    with pytest.raises(ValueError, match="truncated"):
        receipts.project(raw(rollout)[:-1], raw(events), final, prompt="Judge this synthetic passage.",
                         model="gpt-6.1-sol", reasoning="high", cwd=tmp_path)
    with pytest.raises(ValueError, match="missing"):
        receipts.locate(tmp_path, THREAD, started_at=datetime.now(timezone.utc))


def test_private_receipt_replays_without_home_logs_and_detects_missing_artifact(tmp_path: Path) -> None:
    rollout, events, final = native_fixture(tmp_path)
    responses = tmp_path / "responses"
    responses.mkdir()
    original = tmp_path / "own-rollout.jsonl"
    original.write_bytes(raw(rollout))
    event_path, message_path = responses / "events.jsonl", responses / "message.json"
    event_path.write_bytes(raw(events)); message_path.write_bytes(final)
    receipt, artifacts = receipts.capture(tmp_path, "batch-0001.attempt-0001", events_path=event_path,
        message_path=message_path, prompt="Judge this synthetic passage.", model="gpt-6.1-sol", reasoning="high",
        codex_home=tmp_path / "unavailable-home", started_at=datetime.now(timezone.utc), rollout_path=original)
    provider = {"receipt_policy": receipts.POLICY, "reported": receipt["reported"], "provider_artifacts": artifacts}
    original.unlink()
    receipts.verify(tmp_path, provider, prompt="Judge this synthetic passage.", model="gpt-6.1-sol", reasoning="high")
    (tmp_path / artifacts["codex_rollout"]["path"]).unlink()
    with pytest.raises(FileNotFoundError):
        receipts.verify(tmp_path, provider, prompt="Judge this synthetic passage.", model="gpt-6.1-sol", reasoning="high")
