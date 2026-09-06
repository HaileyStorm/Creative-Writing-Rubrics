"""Synthetic unit tests for the future native Sol Broker transport primitive."""

from __future__ import annotations

import hashlib
import json
from typing import Any

import pytest

from hbqrs import HBQError
from hbqrs.sol_broker_transport import run_sol_native_batch


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def descriptor(value: bytes) -> dict[str, Any]:
    return {"schema_version": 1, "sha256": digest(value), "byte_length": len(value)}


ROUTE_SNAPSHOT = {
    "name": "codex-chatgpt-gpt-5.6-sol",
    "model": "gpt-5.6-sol",
    "reasoning_effort": "high",
    "codex_cli_version": "0.1",
    "codex_command": ["codex", "exec"],
    "codex_command_identity": {"command": ["codex", "exec"]},
    "auth_receipt_hash": "b" * 64,
}
ROUTE_SHA256 = digest(canonical(ROUTE_SNAPSHOT))
EVENTS = b"\n".join((
    canonical({"type": "thread.started", "thread_id": "thread-1"}),
    canonical({"type": "turn.started"}),
    canonical({"type": "item.started", "item": {"id": "item-1", "type": "agent_message", "text": ""}}),
    canonical({"type": "item.completed", "item": {"id": "item-1", "type": "agent_message", "text": '{"answer":"yes"}'}}),
    canonical({"type": "turn.completed", "usage": {"input_tokens": 1, "output_tokens": 2}}),
)) + b"\n"
EVENT_PROJECTION = {
    "schema_version": 1,
    "thread_id": "thread-1",
    "usage": {"input_tokens": 1, "output_tokens": 2},
}


class FakeBroker:
    def __init__(self, scenario: str = "completed") -> None:
        self.scenario = scenario
        self.calls = 0
        self.arguments: dict[str, Any] | None = None
        self.blobs: dict[str, bytes] = {}

    def run_codex_native_request(self, route_name: str, request: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        self.calls += 1
        self.arguments = {"route_name": route_name, "request": request, **kwargs}
        if self.scenario in {"definitely_not_contacted", "ambiguous"}:
            return {"state": self.scenario, "result": None, "failure": {"code": self.scenario}}
        if self.scenario != "without_hook":
            kwargs["before_contact"]()
        schema_bytes = canonical(kwargs["output_schema"])
        disclosure_bytes = canonical(kwargs["disclosure"])
        output = {"answer": "yes"}
        final_message = b'{\n  "answer": "yes"\n}'
        events = EVENTS
        if self.scenario == "final_mismatch":
            final_message = b'{"answer":"no"}'
        if self.scenario == "duplicate_final_key":
            final_message = b'{"answer":"yes","answer":"no"}'
        if self.scenario == "schema_readback_mismatch":
            schema_bytes = canonical({"type": "object", "properties": {}})
        schema_descriptor = descriptor(schema_bytes)
        disclosure_descriptor = descriptor(disclosure_bytes)
        events_descriptor = descriptor(events)
        final_descriptor = descriptor(final_message)
        self.blobs = {
            schema_descriptor["sha256"]: schema_bytes,
            disclosure_descriptor["sha256"]: disclosure_bytes,
            events_descriptor["sha256"]: events,
            final_descriptor["sha256"]: final_message,
        }
        command_identity = ROUTE_SNAPSHOT["codex_command_identity"]
        runtime = {
            "adapter_version": 2,
            "requested_model": "gpt-5.6-sol",
            "requested_reasoning_effort": "high",
            "identity_evidence": "requested_only",
            "provider_contact_cardinality_evidence": "unattested",
            "one_provider_bearing_cli_invocation_observed": True,
            "one_turn_observed": True,
            "cli_version": ROUTE_SNAPSHOT["codex_cli_version"],
            "events_hash": digest(events),
            "event_projection": EVENT_PROJECTION,
            "raw_output_hash": digest(final_message),
            "command_identity": command_identity,
            "command_identity_hash": digest(canonical({
                "adapter_version": 2,
                "codex_command": ROUTE_SNAPSHOT["codex_command"],
                "model": "gpt-5.6-sol",
                "reasoning_effort": "high",
            })),
            "auth_receipt_hash": ROUTE_SNAPSHOT["auth_receipt_hash"],
            "execution_contract": {
                "schema_version": 1,
                "prompt_sha256": digest(request["prompt"].encode("utf-8")),
                "prompt_byte_length": len(request["prompt"].encode("utf-8")),
                "output_schema_artifact": schema_descriptor,
                "disclosure_artifact": disclosure_descriptor,
                "max_turns": 1,
                "zero_tool_activity_observed": True,
                "payload_classification": kwargs["disclosure"]["payload_classification"],
            },
        }
        if self.scenario == "identity_mismatch":
            runtime["identity_evidence"] = "accepted_model"
        route_sha256 = ROUTE_SHA256 if self.scenario != "route_mismatch" else "c" * 64
        result = {
            "schema_version": 2,
            "request_hash": digest(canonical(request)),
            "output": output,
            "output_hash": digest(canonical(output)),
            "runtime": runtime,
            "native_events_artifact": events_descriptor,
            "native_final_message_artifact": final_descriptor,
            "route_sha256": route_sha256,
        }
        return {"state": "completed", "result": result, "failure": None}

    def read_codex_native_artifact(self, value: dict[str, Any]) -> bytes:
        if self.scenario == "reader_raises":
            raise OSError("synthetic reader fault")
        raw = self.blobs[value["sha256"]]
        return raw + b"!" if self.scenario == "returned_byte_mismatch" else raw

    def read_codex_native_events(self, value: dict[str, Any]) -> bytes:
        return self.blobs[value["sha256"]]

    def read_codex_native_final_message(self, value: dict[str, Any]) -> bytes:
        return self.blobs[value["sha256"]]


def invoke(broker: FakeBroker, **kwargs: Any):
    options = {
        "prompt_utf8": "Line one\nRésumé ☃".encode(),
        "planned_schema_utf8": b'{\n  "properties": {"answer": {"type": "string"}},\n  "type": "object"\n}',
        "disclosure": {"payload_classification": "public_synthetic", "authorized": True},
        "expected_route_sha256": ROUTE_SHA256,
        "route_snapshot": ROUTE_SNAPSHOT,
        "event_replayer": lambda raw: EVENT_PROJECTION,
    }
    options.update(kwargs)
    return run_sol_native_batch(broker, **options)


def test_completed_receipt_preserves_raw_bytes_and_canonical_schema_distinction() -> None:
    broker = FakeBroker()
    hooks: list[str] = []
    receipt = invoke(broker, precontact_hook=lambda: hooks.append("called"))

    assert receipt.state == "completed"
    assert hooks == ["called"]
    assert broker.calls == 1
    assert broker.arguments is not None
    assert broker.arguments["route_name"] == "codex-chatgpt-gpt-5.6-sol"
    assert broker.arguments["max_turns"] == 1
    assert broker.arguments["request"]["prompt"].encode("utf-8") == "Line one\nRésumé ☃".encode()
    assert digest(canonical(ROUTE_SNAPSHOT["codex_command_identity"])) != digest(canonical({
        "adapter_version": 2,
        "codex_command": ROUTE_SNAPSHOT["codex_command"],
        "model": "gpt-5.6-sol",
        "reasoning_effort": "high",
    }))
    assert receipt.planned_schema_sha256 != receipt.canonical_schema_sha256
    assert receipt.final_message_bytes == b'{\n  "answer": "yes"\n}'
    assert receipt.events_bytes == EVENTS
    assert receipt.raw_final_message_sha256 == digest(receipt.final_message_bytes)
    assert receipt.output_sha256 == digest(canonical(receipt.parsed_output))
    assert receipt.parsed_output == {"answer": "yes"}
    assert receipt.identity_evidence == "requested_only"
    assert receipt.provider_contact_cardinality_evidence == "unattested"
    assert receipt.zero_tool_activity_observed is True


@pytest.mark.parametrize("scenario", ["definitely_not_contacted", "ambiguous"])
def test_terminal_noncompleted_outcomes_are_preserved_without_retry(scenario: str) -> None:
    broker = FakeBroker(scenario)
    receipt = invoke(broker)

    assert receipt.state == scenario
    assert receipt.failure_code is None
    assert broker.calls == 1


@pytest.mark.parametrize(
    "scenario",
    [
        "without_hook", "route_mismatch", "identity_mismatch", "final_mismatch",
        "duplicate_final_key", "schema_readback_mismatch", "returned_byte_mismatch", "reader_raises",
    ],
)
def test_completed_binding_mismatches_fail_closed_without_retry(scenario: str) -> None:
    broker = FakeBroker(scenario)
    receipt = invoke(broker)

    assert receipt.state == "ambiguous"
    assert receipt.failure_code in {
        "precontact_hook_count_invalid", "completed_result_binding_invalid",
        "retained_artifact_or_event_replay_invalid",
    }
    assert broker.calls == 1


def test_missing_public_reader_fails_before_request() -> None:
    broker = FakeBroker()
    broker.read_codex_native_events = None  # type: ignore[method-assign]

    with pytest.raises(HBQError, match="artifact readers"):
        invoke(broker)
    assert broker.calls == 0


def test_route_snapshot_mismatch_fails_before_request() -> None:
    broker = FakeBroker()

    with pytest.raises(HBQError, match="does not match"):
        invoke(broker, route_snapshot={**ROUTE_SNAPSHOT, "codex_cli_version": "drift"})
    assert broker.calls == 0


def test_missing_event_replayer_fails_before_request() -> None:
    broker = FakeBroker()

    with pytest.raises(HBQError, match="event replayer"):
        invoke(broker, event_replayer=None)
    assert broker.calls == 0


def test_event_replayer_is_invoked_and_projection_mismatch_fails_closed() -> None:
    broker = FakeBroker()
    replayed: list[bytes] = []
    receipt = invoke(broker, event_replayer=lambda raw: (replayed.append(raw) or {**EVENT_PROJECTION, "thread_id": "wrong"}))

    assert replayed == [EVENTS]
    assert receipt.state == "ambiguous"
    assert receipt.failure_code == "retained_artifact_or_event_replay_invalid"
    assert broker.calls == 1


@pytest.mark.parametrize(
    "planned_schema",
    [b'{"type":"object","type":"string"}', b'{"type":NaN}'],
)
def test_invalid_raw_schema_is_rejected_before_request(planned_schema: bytes) -> None:
    broker = FakeBroker()

    with pytest.raises(HBQError, match="strict UTF-8 JSON"):
        invoke(broker, planned_schema_utf8=planned_schema)
    assert broker.calls == 0
