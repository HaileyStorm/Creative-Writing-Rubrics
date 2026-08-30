from __future__ import annotations

import json
import inspect
import os
import shutil
import sys
from types import ModuleType
from pathlib import Path

import pytest

from _scoped_module_loader import load_module


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation-results" / "hbq-human-alignment-optimizer-v4-native-subscription-exec-v1"
executor = load_module(PACKAGE / "executor.py", name="hanna_v4_native_subscription_exec_v1")
DOCUMENTS = Path.home() / "Documents"
ROOTS = {
    "frozen_successor_path": DOCUMENTS / "cwr-hanna-successor-fresh88-freeze-v4" / "frozen-successor-contract.json",
    "hanna_csv_path": DOCUMENTS / "cwr-hanna-pinned-data-282f275" / "hanna_stories_annotations.csv",
}
AUTH = "d" * 64
LIVE = {**ROOTS, "authorization_acknowledgement_sha256": AUTH, "allow_remote": True}


def route(*, cost_hash: str = "a" * 64) -> dict:
    return {
        "name": executor.ROUTE_NAME,
        "model": "grok-4.6",
        "adapter": "grok_exec",
        "provider": "xai_grok_build",
        "destination": "xai_grok_build_subscription",
        "account_class": "subscription",
        "zero_charge": True,
        "armed": True,
        "health": "healthy",
        "reasoning_effort": "high",
        "reported_model": "grok-4.6-build",
        "identity_evidence": "requested_only",
        "allowed_payload_classes": ["public_repo"],
        "grok_command": ["grok-fixture.exe"],
        "grok_command_identity": {"version": 1, "artifacts": [{"path": "grok-fixture.exe", "sha256": "b" * 64}]},
        "cli_version_identity": {"version": 1, "artifacts": [{"path": "grok-fixture.exe", "sha256": "b" * 64}]},
        "grok_cli_version": "grok fixture 1.0",
        "cost_evidence": {"evidence_hash": cost_hash},
        "subscription_receipt_hash": "c" * 64,
        "timeout_seconds": 60,
    }


def sol_route(*, cost_hash: str = "e" * 64) -> dict:
    identity = {"version": 1, "artifacts": [{"path": "codex-fixture.exe", "sha256": "f" * 64}]}
    return {
        "name": executor.SOL_ROUTE_NAME, "model": "gpt-5.6-sol", "adapter": "codex_exec",
        "provider": "openai_codex", "destination": "openai_codex_chatgpt_subscription",
        "account_class": "subscription", "zero_charge": True, "armed": True, "health": "healthy",
        "reasoning_effort": "high", "identity_evidence": "requested_only", "trusted": True,
        "allowed_payload_classes": ["public_repo"], "codex_command": ["codex-fixture.exe"],
        "codex_command_identity": identity, "cli_version_identity": identity,
        "auth_status_identity": identity, "codex_cli_version": "codex-cli fixture 1.0",
        "command": ["python-fixture.exe", str(executor.CODEX_ADAPTER_PATH)], "command_identity": identity,
        "cost_evidence": {
            "evidence_hash": cost_hash, "checked_at": "2026-08-29T00:00:00Z",
            "expires_at": "2026-08-30T00:00:00Z",
        }, "auth_receipt_hash": "1" * 64,
        "timeout_seconds": 60,
    }


class FakeBroker:
    def __init__(self, _root: Path, *, candidate: dict | None = None, stale: bool = False):
        self.candidate = candidate or route()
        self.stale = stale
        self.validations = []

    def _load_registry_live(self):
        return {"version": 1, "routes": [self.candidate]}

    def _validate_route(self, candidate, *, verify_command_identity, validate_current_evidence):
        self.validations.append((candidate, verify_command_identity, validate_current_evidence))
        if self.stale:
            raise ValueError("stale auth receipt" if self.stale == "auth" else "stale route evidence")


@pytest.fixture(scope="module")
def parent_material():
    parent = executor._load_predecessor()
    schedule = parent.derive_schedule(**ROOTS)
    grok = next(row for row in schedule["mandatory_development"] if row["route_name"] == "grok_primary")
    sol = next(row for row in schedule["mandatory_development"] if row["route_name"] == "sol_validation")
    return parent, grok, sol


def parent_payload(parent, row: dict) -> bytes:
    return parent._payload(parent._load_v3(), row, **ROOTS)


def factory(candidate: dict | None = None, *, stale: bool = False):
    instances = []
    def build(path):
        broker = FakeBroker(path, candidate=candidate, stale=stale)
        instances.append(broker)
        return broker
    build.instances = instances
    return build


def codex_events(thread_id: str = "thread-1", *, extra: dict | None = None, error: bool = False,
                 agent_text: str | None = None) -> bytes:
    text = valid_final_response() if agent_text is None else agent_text
    events = [
        {"type": "thread.started", "thread_id": thread_id},
        {"type": "turn.started"},
        {"type": "item.started", "item": {"id": "m1", "type": "agent_message", "text": ""}},
        {"type": "item.completed", "item": {"id": "m1", "type": "agent_message", "text": text}},
        {"type": "turn.completed", "usage": {"input_tokens": 10, "output_tokens": 5}},
    ]
    if error:
        events.insert(-1, {"type": "error", "error": {"message": "fixture"}})
    if extra is not None:
        events.append(extra)
    return b"".join(json.dumps(event, separators=(",", ":")).encode() + b"\n" for event in events)


def valid_final_response() -> str:
    dimensions = ["Relevance", "Coherence", "Empathy", "Surprise", "Engagement", "Complexity"]
    return json.dumps({
        "scores": {name: 3 for name in dimensions},
        "evidence": {name: "fixture evidence" for name in dimensions},
        "coverage": {name: True for name in dimensions},
    }, separators=(",", ":"))


def sol_call(raw_events: bytes, *, session_id: str = "thread-1", prompts: list[bytes] | None = None):
    def invoke(**kwargs):
        assert kwargs["capture_jsonl_events"] is True
        assert kwargs["model"] == "gpt-5.6-sol" and kwargs["reasoning"] == "high"
        kwargs["before_provider_attempt"]()
        if prompts is not None:
            prompts.append(kwargs["prompt"].encode("utf-8"))
        root = kwargs["output_dir"]
        responses = root / "responses"
        responses.mkdir(exist_ok=True)
        final = valid_final_response()
        (responses / "batch-0001.attempt-0001.message.json").write_text(final, encoding="utf-8")
        events_path = responses / "batch-0001.attempt-0001.events.jsonl"
        events_path.write_bytes(raw_events)
        return final, {
            "command": executor._expected_codex_command(kwargs["executable"], root),
            "reported": {
                "model": "gpt-5.6-sol", "provider": "openai", "reasoning_effort": "high",
                "session_id": session_id,
            },
            "provider_artifacts": {"codex_events": {
                "path": events_path.relative_to(root).as_posix(), "bytes": len(raw_events),
                "sha256": executor._sha(raw_events),
            }},
        }
    return invoke


def test_current_route_validation_shape_uses_all_live_gates() -> None:
    build = factory()
    candidate, evidence = executor.validate_live_grok_route(Path("queue"), broker_factory=build)
    assert candidate["name"] == executor.ROUTE_NAME
    assert build.instances[0].validations == [(candidate, True, True)]
    assert evidence["cost_evidence_hash"] == "a" * 64
    assert evidence["subscription_receipt_hash"] == "c" * 64


def test_exact_final_runner_and_codex_parser_pins_load() -> None:
    assert executor._sha(executor._stable_file_bytes(executor.RUNNER_PATH)) == executor.RUNNER_SHA256 == (
        "de1dccd28c8ba544207b3b000d086948fa8c429a327b055762e8d7032e3fa938"
    )
    assert executor._load_call_grok().__name__ == "_call_grok"
    assert executor._load_call_codex().__name__ == "_call_codex"
    assert executor._load_parse_codex_events().__name__ == "_parse_events"


def test_prepare_only_preserves_bytes_and_makes_zero_calls(parent_material, tmp_path: Path, monkeypatch) -> None:
    parent, grok, _sol = parent_material
    calls = []
    monkeypatch.setattr(executor, "_load_call_grok", lambda: calls.append("subprocess"))
    prepared = executor.prepare_only(
        output_root=tmp_path / "exec", cell_id=grok["cell_id"], queue_root=tmp_path / "queue",
        broker_factory=factory(), authorization_acknowledgement_sha256=AUTH, **ROOTS,
    )
    source = json.loads(parent_payload(parent, grok).decode("utf-8"))["components"]
    root = tmp_path / "exec" / grok["cell_id"]
    assert (root / "prompt-request.bin").read_bytes() == source["task_payload"].encode("utf-8")
    assert (root / "response-schema.json").read_bytes() == source["response_schema"].encode("utf-8")
    assert prepared["provider_calls_made"] == 0 and prepared["process_launches"] == 0 and calls == []
    disclosure = json.loads((root / "disclosure.json").read_text(encoding="utf-8"))
    authorization = json.loads((root / "authorization-acknowledgement.json").read_text(encoding="utf-8"))
    proof = json.loads((root / "zero-charge-route-proof.json").read_text(encoding="utf-8"))
    assert disclosure["task_payload"]["text"] == source["task_payload"] and disclosure["tools_enabled"] is False
    assert disclosure["system_prompt_override"] == executor.SYSTEM_PROMPT
    assert disclosure["tool_free_argv"] == executor.TOOL_FREE_ARGV
    assert authorization["acknowledgement_sha256"] == AUTH
    assert proof["status"] == "CURRENT_BROKER_VALIDATED_ZERO_CHARGE_SUBSCRIPTION_ROUTE"
    assert "predecessor_output_root" not in inspect.signature(executor.prepare_only).parameters


def test_tool_free_execution_callback_and_receipt(parent_material, tmp_path: Path) -> None:
    parent, grok, _sol = parent_material
    build = factory()
    executor.prepare_only(
        output_root=tmp_path / "exec", cell_id=grok["cell_id"], queue_root=tmp_path / "queue",
        broker_factory=build, authorization_acknowledgement_sha256=AUTH, **ROOTS,
    )
    launches = []
    def call_grok(**kwargs):
        assert kwargs["system_prompt_override"] == executor.SYSTEM_PROMPT
        assert executor.TOOL_FREE_ARGV[executor.TOOL_FREE_ARGV.index("--tools") + 1] == ""
        launches.append("launch")
        kwargs["before_provider_attempt"]()
        root = kwargs["output_dir"]
        responses = root / "responses"
        responses.mkdir(exist_ok=True)
        (responses / "batch-0001.attempt-0001.prompt.txt").write_text(kwargs["prompt"], encoding="utf-8")
        envelope = executor._canonical({
            "modelUsage": {"grok-4.6-build": {}}, "stopReason": "end_turn", "num_turns": 1,
            "sessionId": "session-1", "requestId": "request-1", "structuredOutput": {"ok": True},
        })
        path = responses / "batch-0001.attempt-0001.grok.envelope.json"
        path.write_bytes(envelope)
        record = {
            "cli_version": "grok fixture 1.0", "requested": {"model": "grok-4.6", "reasoning_effort": "high"},
            "reported": {"provider": "grok", "model": "grok-4.6-build"},
            "session_id_sha256": executor._sha(b"session-1"), "request_id_sha256": executor._sha(b"request-1"),
            "reasoning_attested": False, "reasoning_attestation": "not_reported_by_grok_build_cli",
            "provider_artifacts": {"grok_envelope": {"path": path.relative_to(root).as_posix(), "bytes": len(envelope), "sha256": executor._sha(envelope)}},
        }
        return "{}", record
    result = executor.execute_grok(
        output_root=tmp_path / "exec", cell_id=grok["cell_id"], queue_root=tmp_path / "queue",
        broker_factory=build, call_grok=call_grok, **LIVE,
    )
    assert launches == ["launch"] and result["native_contact_proven"] is True
    assert result["identity"]["contact_id"] == "request-1" and result["identity"]["session_id"] == "session-1"
    predecessor_payload = parent_payload(parent, grok)
    event = {
        "cell": grok,
        "identity": result["identity"],
        "native_request_bytes": result["request_bytes"],
        "outbound_payload": predecessor_payload,
        "effective_settings": {
            "route_name": grok["route"]["route_name"],
            "effective_model": grok["route"]["effective_model"],
            "requested_reasoning_effort": grok["route"]["requested_reasoning_effort"],
            "tools_enabled": False,
            "web_search_enabled": False,
            "subagents_enabled": False,
            "output_schema_sha256": grok["response_schema_sha256"],
            "provider_attested": False,
            "source": "grok_cli_invocation_and_envelope_v1",
        },
    }
    assert executor.verify_predecessor_receipt(
        event, execution_root=tmp_path / "exec", queue_root=tmp_path / "queue", broker_factory=build, **ROOTS,
    ) == {"accepted": True}
    with pytest.raises(ValueError, match="stale route evidence"):
        executor.verify_predecessor_receipt(
            event, execution_root=tmp_path / "exec", queue_root=tmp_path / "queue",
            broker_factory=factory(stale=True), **ROOTS,
        )


def test_precontact_zero_and_stale_route(parent_material, tmp_path: Path) -> None:
    parent, grok, sol = parent_material
    executor.prepare_only(
        output_root=tmp_path / "exec", cell_id=grok["cell_id"], queue_root=tmp_path / "queue",
        broker_factory=factory(), authorization_acknowledgement_sha256=AUTH, **ROOTS,
    )
    pending = executor.execute_grok(
        output_root=tmp_path / "exec", cell_id=grok["cell_id"], queue_root=tmp_path / "queue",
        broker_factory=factory(), call_grok=lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("before callback")),
        **LIVE,
    )
    assert pending == {"cell_id": grok["cell_id"], "state": "pending_precontact", "process_launches": 0, "native_contact_proven": False}
    prepared = executor.prepare_only(
        output_root=tmp_path / "sol-exec", cell_id=sol["cell_id"], queue_root=tmp_path / "queue",
        broker_factory=factory(sol_route()), authorization_acknowledgement_sha256=AUTH, **ROOTS,
    )
    assert prepared["route_status"] == "SOL_PREPARED_NO_CONTACT" and prepared["capture_jsonl_events"] is True
    with pytest.raises(ValueError, match="stale route evidence"):
        executor.validate_live_grok_route(tmp_path / "queue", broker_factory=factory(stale=True))
    with pytest.raises(ValueError, match="stale route evidence"):
        executor.validate_live_sol_route(tmp_path / "queue", broker_factory=factory(sol_route(), stale=True))


def test_swapped_grok_ids_are_rejected() -> None:
    raw = executor._canonical({
        "modelUsage": {"grok-4.6-build": {}}, "requestId": "request-b", "sessionId": "session-b",
    })
    record = {"request_id_sha256": executor._sha(b"request-a"), "session_id_sha256": executor._sha(b"session-a")}
    with pytest.raises(ValueError, match="misassociated"):
        executor._envelope_identity(raw, record)


def test_orphan_prepared_artifact_and_postlaunch_malformed_envelope_reconcile(parent_material, tmp_path: Path) -> None:
    _parent, grok, _sol = parent_material
    executor.prepare_only(
        output_root=tmp_path / "orphan", cell_id=grok["cell_id"], queue_root=tmp_path / "queue",
        broker_factory=factory(), authorization_acknowledgement_sha256=AUTH, **ROOTS,
    )
    root = tmp_path / "orphan" / grok["cell_id"]
    (root / "orphan.bin").write_bytes(b"orphan")
    launches = []
    with pytest.raises(ValueError, match="prepared-root inventory drifted"):
        executor.execute_grok(
            output_root=tmp_path / "orphan", cell_id=grok["cell_id"], queue_root=tmp_path / "queue",
            broker_factory=factory(), call_grok=lambda **_kwargs: launches.append("launch"), **LIVE,
        )
    assert launches == []

    executor.prepare_only(
        output_root=tmp_path / "malformed", cell_id=grok["cell_id"], queue_root=tmp_path / "queue",
        broker_factory=factory(), authorization_acknowledgement_sha256=AUTH, **ROOTS,
    )
    def malformed(**kwargs):
        kwargs["before_provider_attempt"]()
        responses = kwargs["output_dir"] / "responses"
        responses.mkdir(exist_ok=True)
        (responses / "batch-0001.attempt-0001.prompt.txt").write_text(kwargs["prompt"], encoding="utf-8")
        path = responses / "batch-0001.attempt-0001.grok.envelope.json"
        path.write_bytes(b"{}")
        return "{}", {"provider_artifacts": {"grok_envelope": {"path": path.relative_to(kwargs["output_dir"]).as_posix(), "bytes": 2, "sha256": executor._sha(b"{}")}}}
    result = executor.execute_grok(
        output_root=tmp_path / "malformed", cell_id=grok["cell_id"], queue_root=tmp_path / "queue",
        broker_factory=factory(), call_grok=malformed, **LIVE,
    )
    assert result["state"] == "reconcile_required_after_process_launch" and result["native_contact_proven"] is False
    with pytest.raises(ValueError, match="refuses to resend"):
        executor.execute_grok(
            output_root=tmp_path / "malformed", cell_id=grok["cell_id"], queue_root=tmp_path / "queue",
            broker_factory=factory(), call_grok=malformed, **LIVE,
        )


def test_sol_json_capture_coherent_receipt_and_identical_prompt_bytes(parent_material, tmp_path: Path) -> None:
    parent, grok, sol = parent_material
    assert grok["task_payload_sha256"] == sol["task_payload_sha256"]
    executor.prepare_only(
        output_root=tmp_path / "grok", cell_id=grok["cell_id"], queue_root=tmp_path / "queue",
        broker_factory=factory(), authorization_acknowledgement_sha256=AUTH, **ROOTS,
    )
    executor.prepare_only(
        output_root=tmp_path / "sol", cell_id=sol["cell_id"], queue_root=tmp_path / "queue",
        broker_factory=factory(sol_route()), authorization_acknowledgement_sha256=AUTH, **ROOTS,
    )
    grok_prompt = (tmp_path / "grok" / grok["cell_id"] / "prompt-request.bin").read_bytes()
    sol_prompt = (tmp_path / "sol" / sol["cell_id"] / "prompt-request.bin").read_bytes()
    assert grok_prompt == sol_prompt
    prompts = []
    result = executor.execute_sol(
        output_root=tmp_path / "sol", cell_id=sol["cell_id"], queue_root=tmp_path / "queue",
        broker_factory=factory(sol_route()), call_codex=sol_call(codex_events(), prompts=prompts), **LIVE,
    )
    assert prompts == [sol_prompt] and result["native_contact_proven"] is False
    assert result["native_endpoint_contact_cardinality"] == "unproven"
    assert result["identity"] == {
        "provider": "openai_codex", "route_name": executor.SOL_ROUTE_NAME,
        "requested_model": "gpt-5.6-sol", "requested_reasoning_effort": "high",
        "effective_model": "gpt-5.6-sol", "provider_reported_model": None,
        "identity_evidence": "requested_and_local_effective_settings_only_not_provider_attested",
        "reasoning_attested": False, "transport_identity": "codex_chatgpt_subscription_exec_tool_free_v1",
        "contact_id": "unproven-native-endpoint-contact-for-local-thread:thread-1",
        "session_id": "local-codex-thread-session:thread-1",
    }
    event = {
        "cell": sol, "identity": result["identity"], "native_request_bytes": result["request_bytes"],
        "outbound_payload": parent_payload(parent, sol),
        "effective_settings": {
            "route_name": sol["route"]["route_name"], "effective_model": sol["route"]["effective_model"],
            "requested_reasoning_effort": sol["route"]["requested_reasoning_effort"],
            "tools_enabled": False, "web_search_enabled": False, "subagents_enabled": False,
            "output_schema_sha256": sol["response_schema_sha256"], "provider_attested": False,
            "source": "codex_cli_local_events_and_invocation_v1",
        },
    }
    assert executor.verify_predecessor_receipt(
        event, execution_root=tmp_path / "sol", queue_root=tmp_path / "queue",
        broker_factory=factory(sol_route()), **ROOTS,
    ) == {
        "accepted": False, "local_lifecycle_verified": True,
        "native_endpoint_contact_cardinality": "unproven",
        "reason": "local_codex_thread_events_do_not_attest_native_endpoint_contact_cardinality",
    }
    completed = tmp_path / "sol" / sol["cell_id"]
    extra = completed / "arbitrary-extra.bin"
    extra.write_bytes(b"extra")
    with pytest.raises(ValueError, match="completed-root inventory"):
        executor.verify_predecessor_receipt(
            event, execution_root=tmp_path / "sol", queue_root=tmp_path / "queue",
            broker_factory=factory(sol_route()), **ROOTS,
        )
    extra.unlink()
    extra.mkdir()
    with pytest.raises(ValueError, match="completed-root inventory"):
        executor.verify_predecessor_receipt(
            event, execution_root=tmp_path / "sol", queue_root=tmp_path / "queue",
            broker_factory=factory(sol_route()), **ROOTS,
        )
    extra.rmdir()
    relabelled_event = {**event, "cell": {**sol, "partition": "train"}}
    with pytest.raises(ValueError, match="caller cell row was copied or relabelled"):
        executor.verify_predecessor_receipt(
            relabelled_event, execution_root=tmp_path / "sol", queue_root=tmp_path / "queue",
            broker_factory=factory(sol_route()), **ROOTS,
        )
    intent_path = completed / "launch-intent.json"
    intent = json.loads(intent_path.read_text(encoding="utf-8"))
    intent["kind"] = "mutated_launch_intent"
    intent_path.write_bytes(executor._canonical(intent))
    receipt_path = completed / "execution-receipt.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["launch_intent_sha256"] = executor._sha(intent_path.read_bytes())
    receipt_path.write_bytes(executor._canonical(receipt))
    with pytest.raises(ValueError, match="launch-intent provenance drifted"):
        executor.verify_predecessor_receipt(
            event, execution_root=tmp_path / "sol", queue_root=tmp_path / "queue",
            broker_factory=factory(sol_route()), **ROOTS,
        )


@pytest.mark.parametrize("raw", [
    b"not-json\n",
    codex_events(extra={"type": "turn.started"}),
    codex_events(error=True),
])
def test_sol_malformed_extra_or_error_events_reconcile_no_resend(parent_material, tmp_path: Path, raw: bytes) -> None:
    _parent, _grok, sol = parent_material
    root = tmp_path / executor._sha(raw)[:8]
    executor.prepare_only(
        output_root=root, cell_id=sol["cell_id"], queue_root=tmp_path / "queue",
        broker_factory=factory(sol_route()), authorization_acknowledgement_sha256=AUTH, **ROOTS,
    )
    result = executor.execute_sol(
        output_root=root, cell_id=sol["cell_id"], queue_root=tmp_path / "queue",
        broker_factory=factory(sol_route()), call_codex=sol_call(raw), **LIVE,
    )
    assert result["state"] == "reconcile_required_after_process_launch"
    with pytest.raises(ValueError, match="refuses to resend"):
        executor.execute_sol(
            output_root=root, cell_id=sol["cell_id"], queue_root=tmp_path / "queue",
            broker_factory=factory(sol_route()), call_codex=sol_call(raw), **LIVE,
        )


def test_sol_swapped_thread_session_and_stale_auth_are_denied(parent_material, tmp_path: Path) -> None:
    _parent, _grok, sol = parent_material
    executor.prepare_only(
        output_root=tmp_path / "swapped", cell_id=sol["cell_id"], queue_root=tmp_path / "queue",
        broker_factory=factory(sol_route()), authorization_acknowledgement_sha256=AUTH, **ROOTS,
    )
    result = executor.execute_sol(
        output_root=tmp_path / "swapped", cell_id=sol["cell_id"], queue_root=tmp_path / "queue",
        broker_factory=factory(sol_route()), call_codex=sol_call(codex_events("thread-a"), session_id="thread-b"), **LIVE,
    )
    assert result["state"] == "reconcile_required_after_process_launch"
    with pytest.raises(ValueError, match="stale auth receipt"):
        executor.prepare_only(
            output_root=tmp_path / "stale", cell_id=sol["cell_id"], queue_root=tmp_path / "queue",
            broker_factory=factory(sol_route(), stale="auth"), authorization_acknowledgement_sha256=AUTH, **ROOTS,
        )


def test_sol_agent_message_final_response_mismatch_reconciles(parent_material, tmp_path: Path) -> None:
    _parent, _grok, sol = parent_material
    executor.prepare_only(
        output_root=tmp_path / "mismatch", cell_id=sol["cell_id"], queue_root=tmp_path / "queue",
        broker_factory=factory(sol_route()), authorization_acknowledgement_sha256=AUTH, **ROOTS,
    )
    result = executor.execute_sol(
        output_root=tmp_path / "mismatch", cell_id=sol["cell_id"], queue_root=tmp_path / "queue",
        broker_factory=factory(sol_route()), call_codex=sol_call(codex_events(agent_text='{"different":true}')),
        **LIVE,
    )
    assert result["state"] == "reconcile_required_after_process_launch"


@pytest.mark.parametrize(("artifact", "field", "value"), [
    ("prepared.json", "cell_id", "v4-cell-relabeled"),
    ("disclosure.json", "destination", "wrong_destination"),
    ("authorization-acknowledgement.json", "kind", "wrong_kind"),
    ("zero-charge-route-proof.json", "study_id", "wrong_study"),
])
def test_self_consistent_relabel_destination_kind_or_study_mutation_is_rejected(
    parent_material, tmp_path: Path, artifact: str, field: str, value: str,
) -> None:
    _parent, grok, _sol = parent_material
    output = tmp_path / f"mut-{artifact[:4]}-{field}"
    executor.prepare_only(
        output_root=output, cell_id=grok["cell_id"], queue_root=tmp_path / "queue",
        broker_factory=factory(), authorization_acknowledgement_sha256=AUTH, **ROOTS,
    )
    root = output / grok["cell_id"]
    target = root / artifact
    value_record = json.loads(target.read_text(encoding="utf-8"))
    value_record[field] = value
    target.write_bytes(executor._canonical(value_record))
    if artifact != "prepared.json":
        hash_field = {
            "disclosure.json": "disclosure_sha256",
            "authorization-acknowledgement.json": "authorization_sha256",
            "zero-charge-route-proof.json": "route_proof_sha256",
        }[artifact]
        prepared = json.loads((root / "prepared.json").read_text(encoding="utf-8"))
        prepared[hash_field] = executor._sha(target.read_bytes())
        (root / "prepared.json").write_bytes(executor._canonical(prepared))
    launches = []
    with pytest.raises(ValueError, match="copied or relabelled"):
        executor.execute_grok(
            output_root=output, cell_id=grok["cell_id"], queue_root=tmp_path / "queue",
            broker_factory=factory(), call_grok=lambda **_kwargs: launches.append("launch"), **LIVE,
        )
    assert launches == []


def test_copied_cell_root_and_missing_remote_gate_cannot_launch(parent_material, tmp_path: Path) -> None:
    parent, grok, _sol = parent_material
    schedule = parent.derive_schedule(**ROOTS)
    other = next(row for row in schedule["mandatory_development"] if row["route_name"] == "grok_primary" and row["cell_id"] != grok["cell_id"])
    source_output = tmp_path / "source"
    copied_output = tmp_path / "copied"
    executor.prepare_only(
        output_root=source_output, cell_id=grok["cell_id"], queue_root=tmp_path / "queue",
        broker_factory=factory(), authorization_acknowledgement_sha256=AUTH, **ROOTS,
    )
    copied_output.mkdir()
    shutil.copytree(source_output / grok["cell_id"], copied_output / other["cell_id"])
    launches = []
    with pytest.raises(ValueError, match="prepared bytes drifted"):
        executor.execute_grok(
            output_root=copied_output, cell_id=other["cell_id"], queue_root=tmp_path / "queue",
            broker_factory=factory(), call_grok=lambda **_kwargs: launches.append("launch"), **LIVE,
        )
    with pytest.raises(ValueError, match="allow_remote=True"):
        executor.execute_grok(
            output_root=source_output, cell_id=grok["cell_id"], queue_root=tmp_path / "queue",
            broker_factory=factory(), call_grok=lambda **_kwargs: launches.append("launch"),
            authorization_acknowledgement_sha256=AUTH, allow_remote=False, **ROOTS,
        )
    assert launches == []


def test_cli_live_modes_require_explicit_remote_bind_authorization_and_summarize_bytes(
    tmp_path: Path, monkeypatch, capsys,
) -> None:
    base = [
        "--output-root", str(tmp_path / "out"), "--cell-id", "cell-fixture",
        "--queue-root", str(tmp_path / "queue"), "--frozen-successor", str(ROOTS["frozen_successor_path"]),
        "--hanna-csv", str(ROOTS["hanna_csv_path"]), "--authorization-acknowledgement-sha256", AUTH,
    ]
    with pytest.raises(SystemExit):
        executor.main(["--execute-one-sol", *base])
    capsys.readouterr()
    captured = []
    sol_bytes = b"\x00sol-final\xff"
    monkeypatch.setattr(executor, "execute_sol", lambda **kwargs: captured.append(("sol", kwargs)) or {
        "state": "fixture-sol", "raw_response_bytes": sol_bytes, "raw_events_bytes": b"events",
    })
    assert executor.main(["--execute-one-sol", "--allow-remote", *base]) == 0
    sol_summary = json.loads(capsys.readouterr().out)
    assert sol_summary["kind"] == "native_exec_cli_summary"
    assert sol_summary["persisted_evidence_authoritative"] is True
    assert sol_summary["result"]["raw_response_bytes"] == {
        "raw_bytes_omitted": True, "byte_count": len(sol_bytes), "sha256": executor._sha(sol_bytes),
    }
    assert captured[0][1]["allow_remote"] is True
    assert captured[0][1]["authorization_acknowledgement_sha256"] == AUTH

    grok_bytes = b"grok-envelope\x00"
    monkeypatch.setattr(executor, "execute_grok", lambda **kwargs: captured.append(("grok", kwargs)) or {
        "state": "fixture-grok", "request_bytes": b"request", "raw_envelope_bytes": grok_bytes,
    })
    assert executor.main(["--execute-one-grok", "--allow-remote", *base]) == 0
    grok_summary = json.loads(capsys.readouterr().out)
    assert grok_summary["result"]["raw_envelope_bytes"] == {
        "raw_bytes_omitted": True, "byte_count": len(grok_bytes), "sha256": executor._sha(grok_bytes),
    }
    assert [kind for kind, _kwargs in captured] == ["sol", "grok"]
    with pytest.raises(SystemExit):
        executor.main(["--prepare-only", "--execute-one-grok", *base])


def test_callback_zero_known_runner_artifacts_are_cleaned_for_retry(parent_material, tmp_path: Path) -> None:
    _parent, grok, sol = parent_material
    executor.prepare_only(
        output_root=tmp_path / "grok-zero", cell_id=grok["cell_id"], queue_root=tmp_path / "queue",
        broker_factory=factory(), authorization_acknowledgement_sha256=AUTH, **ROOTS,
    )
    def grok_precontact(**kwargs):
        responses = kwargs["output_dir"] / "responses"
        responses.mkdir()
        (responses / "batch-0001.attempt-0001.prompt.txt").write_text(kwargs["prompt"], encoding="utf-8")
        raise RuntimeError("CLI version failed before callback")
    result = executor.execute_grok(
        output_root=tmp_path / "grok-zero", cell_id=grok["cell_id"], queue_root=tmp_path / "queue",
        broker_factory=factory(), call_grok=grok_precontact, **LIVE,
    )
    assert result["state"] == "pending_precontact"
    assert not (tmp_path / "grok-zero" / grok["cell_id"] / "responses").exists()

    executor.prepare_only(
        output_root=tmp_path / "sol-zero", cell_id=sol["cell_id"], queue_root=tmp_path / "queue",
        broker_factory=factory(sol_route()), authorization_acknowledgement_sha256=AUTH, **ROOTS,
    )
    def sol_precontact(**kwargs):
        responses = kwargs["output_dir"] / "responses"
        responses.mkdir()
        (responses / "batch-0001.attempt-0001.events.jsonl").write_bytes(b"")
        raise RuntimeError("command construction failed before callback")
    result = executor.execute_sol(
        output_root=tmp_path / "sol-zero", cell_id=sol["cell_id"], queue_root=tmp_path / "queue",
        broker_factory=factory(sol_route()), call_codex=sol_precontact, **LIVE,
    )
    assert result["state"] == "pending_precontact"
    assert not (tmp_path / "sol-zero" / sol["cell_id"] / "responses").exists()


def test_route_is_revalidated_adjacent_to_callback_before_intent(parent_material, tmp_path: Path) -> None:
    _parent, grok, _sol = parent_material
    validations = []
    candidate = route()
    class DriftingBroker(FakeBroker):
        def _validate_route(self, candidate, *, verify_command_identity, validate_current_evidence):
            validations.append((verify_command_identity, validate_current_evidence))
            if len(validations) == 3:
                raise ValueError("route drift at callback")
    def drifting(path):
        return DriftingBroker(path, candidate=candidate)
    executor.prepare_only(
        output_root=tmp_path / "drift", cell_id=grok["cell_id"], queue_root=tmp_path / "queue",
        broker_factory=drifting, authorization_acknowledgement_sha256=AUTH, **ROOTS,
    )
    def invoke(**kwargs):
        responses = kwargs["output_dir"] / "responses"
        responses.mkdir()
        (responses / "batch-0001.attempt-0001.prompt.txt").write_text(kwargs["prompt"], encoding="utf-8")
        kwargs["before_provider_attempt"]()
        raise AssertionError("callback drift must abort before launch")
    result = executor.execute_grok(
        output_root=tmp_path / "drift", cell_id=grok["cell_id"], queue_root=tmp_path / "queue",
        broker_factory=drifting, call_grok=invoke, **LIVE,
    )
    root = tmp_path / "drift" / grok["cell_id"]
    assert result["state"] == "pending_precontact" and len(validations) == 3
    assert not (root / "launch-intent.json").exists() and not (root / "responses").exists()


def test_broker_loader_ignores_cached_module_and_binds_exact_source(monkeypatch) -> None:
    cached = ModuleType("model_work_queue.broker")
    cached.Broker = type("CachedBroker", (), {})
    monkeypatch.setitem(sys.modules, "model_work_queue.broker", cached)
    loaded = executor._load_broker_class()
    assert loaded is not cached.Broker
    assert loaded.__module__ == "_hanna_native_exec_pinned_model_work_queue.broker"


def test_completed_inventory_rejects_required_file_reparse(tmp_path: Path) -> None:
    root = tmp_path / "inventory"
    responses = root / "responses"
    responses.mkdir(parents=True)
    root_names = set(executor.PREPARED_FILES) | {
        "raw-codex-events.bin", "raw-codex-final-response.bin", "codex-record.json",
        "launch-intent.json", "effective-settings.json", "execution-receipt.json",
    }
    for name in root_names:
        (root / name).write_bytes(b"")
    (responses / "batch-0001.attempt-0001.events.jsonl").write_bytes(b"")
    outside = tmp_path / "outside.json"
    outside.write_bytes(b"{}")
    link = responses / "batch-0001.attempt-0001.message.json"
    try:
        os.symlink(outside, link)
    except OSError as error:
        pytest.skip(f"symlink creation unavailable: {error}")
    with pytest.raises(ValueError, match="unsafe"):
        executor._validate_completed_inventory(root, is_sol=True)
