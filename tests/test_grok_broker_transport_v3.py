from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from hbqrs import HBQError, book_root, run_judge, runner
from hbqrs import grok_broker_transport_v2 as bridge_v2
from hbqrs import grok_broker_transport_v3 as bridge

SOURCE = Path(bridge.__file__)
ROUTE = {
    "name": "public-synthetic-grok-v5",
    "adapter": "grok_exec",
    "model": "grok-4.6",
    "reasoning_effort": "high",
    "timeout_seconds": 300,
    "max_concurrency": 1,
    "nonvisual_max_turns": 1,
    "capabilities": ["public_synthetic", "grok_nonvisual_history_v5"],
    "nonvisual_transport_contract": "grok_nonvisual_history_v5",
}
LEGACY_ROUTE = {
    "name": "public-synthetic-grok-v2",
    "adapter": "grok_exec",
    "model": "grok-4.6",
    "reasoning_effort": "high",
    "timeout_seconds": 30,
}


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


class StubBroker:
    """Public-synthetic broker surface; it never starts a native process."""

    def __init__(self, *, mutate=None, binding_bridge=bridge, adapter_version=5, reasoning_attested=False):
        self.context = None
        self.calls = 0
        self.mutate = mutate or (lambda value: value)
        self.binding_bridge = binding_bridge
        self.adapter_version = adapter_version
        self.reasoning_attested = reasoning_attested
        self.envelope = b""
        self.expected_route_sha256 = None

    def run_grok_native_request(
        self, route_name, request, *, output_schema, nonvisual_max_turns, session_id,
        before_contact, expected_route_sha256,
    ):
        assert nonvisual_max_turns == 1 and len(expected_route_sha256) == 64
        self.expected_route_sha256 = expected_route_sha256
        before_contact()
        self.calls += 1
        questions = output_schema["properties"]["verdicts"]["items"]["properties"]["question_id"]["enum"]
        output = {
            "verdicts": [
                {
                    "question_id": question,
                    "verdict": "YES",
                    "confidence": 0.8,
                    "evidence": [{
                        "kind": "exact_quote", "reference": "line:1",
                        "exact_quote": "A short test scene.", "summary": None,
                    }],
                    "note": "Public synthetic attested transport fixture.",
                }
                for question in questions
            ]
        }
        execution = self.binding_bridge._context_bindings(self.context, ROUTE if self.binding_bridge is bridge else LEGACY_ROUTE)[-1]["execution_contract"]
        request_id = "public-synthetic-request"
        self.envelope = self.binding_bridge._canonical({
            "structuredOutput": output, "sessionId": session_id, "requestId": request_id,
        })
        runtime = {
            "session_id_hash": digest(session_id.encode("utf-8")),
            "request_id_hash": digest(request_id.encode("utf-8")),
            "envelope_hash": digest(self.envelope),
            "requested_model": "grok-4.6",
            "requested_reasoning_effort": "high",
            "execution_contract": execution,
            "adapter_version": self.adapter_version,
            "execution_policy": "bounded_nonvisual_deny_wins_attested",
            "tool_policy_attestation_hash": "a" * 64,
            "reasoning_attested": self.reasoning_attested,
        }
        if self.binding_bridge is bridge:
            runtime.update({
                "identity_evidence": "requested_only",
                "nonvisual_max_turns": 1,
                "observed_turns": 1,
            })
        result = {
            "schema_version": 2,
            "request_hash": digest(self.binding_bridge._canonical(request)),
            "output": output,
            "output_hash": digest(self.binding_bridge._canonical(output)),
            "runtime": runtime,
            "native_envelope_artifact": {
                "schema_version": 1,
                "sha256": digest(self.envelope),
                "byte_length": len(self.envelope),
            },
        }
        return {"state": "completed", "result": self.mutate(result), "failure": None}

    def read_grok_native_envelope(self, descriptor):
        return self.envelope


class PrecontactDenialBroker:
    def __init__(self):
        self.calls = 0
        self.outcome = {
            "state": "definitely_not_contacted",
            "result": None,
            "failure": {"code": "route_pin_denied"},
        }

    def run_grok_native_request(self, *args, **kwargs):
        self.calls += 1
        return self.outcome

    def read_grok_native_envelope(self, descriptor):
        raise AssertionError("precontact denial must not read an envelope")


def execute(
    tmp_path: Path,
    broker: StubBroker,
    *,
    before_contact=lambda context: None,
    after_bind=lambda: None,
    resume: bool = False,
    transport_module=bridge,
    route=ROUTE,
):
    def admission(context):
        broker.context = context
        before_contact(context)

    source_hash = digest(Path(transport_module.__file__).read_bytes())
    transport = transport_module.bind_grok_broker_transport(
        broker=broker, route=route, before_contact=admission, runtime_check=lambda: None,
    )
    after_bind()
    artifact = tmp_path / "artifact.txt"
    if not artifact.exists():
        artifact.write_text("A short test scene.", encoding="utf-8")
    return run_judge(
        artifact_path=artifact,
        bundle_id="prose.short_story",
        provider="grok",
        model="grok-4.6",
        output_dir=tmp_path / "run",
        registry=book_root() / "registry/all_modules.json",
        bundles=book_root() / "bundles/all_bundles.json",
        batch_size=178,
        batch_attempts=1,
        reasoning="high",
        allow_remote=True,
        allow_unattested_reasoning=True,
        timeout=300 if transport_module is bridge else 30,
        attempt_lifecycle_policy=runner.ATTEMPT_LIFECYCLE_POLICY,
        grok_transport=transport,
        grok_transport_sha256=source_hash,
        response_schema_mode="batch_question_ids_v1",
        resume=resume,
    )


def test_v5_result_persists_five_artifacts_and_exact_contract_without_resend(tmp_path: Path) -> None:
    broker = StubBroker()
    result = execute(tmp_path, broker)
    assert result["verdicts"] == 178 and broker.calls == 1
    assert broker.expected_route_sha256 == bridge._sha256(bridge._canonical(ROUTE))
    checkpoint = json.loads((tmp_path / "run/responses/batch-0001.json").read_bytes())
    metadata = checkpoint["provider"]
    assert metadata["tool_free"] is True and metadata["reasoning_attested"] is False
    assert set(metadata["provider_artifacts"]) == {"request", "context", "outcome", "envelope", "receipt"}
    context = json.loads((tmp_path / "run" / metadata["provider_artifacts"]["context"]["path"]).read_bytes())
    execution = context["execution_contract"]
    assert execution["nonvisual_transport_contract"] == bridge._V5_NONVISUAL_TRANSPORT_CONTRACT
    assert execution["nonvisual_transport_contract_sha256"] == bridge._V5_TRANSPORT_CONTRACT_SHA256
    receipt = json.loads((tmp_path / "run" / metadata["provider_artifacts"]["receipt"]["path"]).read_bytes())
    assert set(receipt) == {
        "schema_version", "source_sha256", "route_sha256", "request_sha256", "context_sha256",
        "schema_sha256", "result_sha256", "outcome_sha256", "envelope_sha256",
        "session_id_hash", "request_id_hash",
    }
    execute(tmp_path, broker, resume=True)
    assert broker.calls == 1


def test_v5_route_accepts_truthful_ten_way_concurrency(tmp_path: Path) -> None:
    route = {**ROUTE, "max_concurrency": 10}
    broker = StubBroker()
    result = execute(tmp_path, broker, route=route)
    assert result["verdicts"] == 178 and broker.calls == 1
    assert broker.expected_route_sha256 == bridge._sha256(bridge._canonical(route))
    frozen, route_sha256 = bridge._route_freeze(route)
    assert frozen["max_concurrency"] == 10 and route_sha256 == broker.expected_route_sha256


@pytest.mark.parametrize("field,value", [
    ("timeout_seconds", 30),
    ("max_concurrency", 2),
    ("nonvisual_max_turns", 2),
    ("capabilities", ["public_synthetic"]),
    ("nonvisual_transport_contract", "other"),
])
def test_v5_route_rejects_before_broker_or_output(field: str, value, tmp_path: Path) -> None:
    class BrokerMustNotBeRead:
        def __getattr__(self, name):
            raise AssertionError(f"broker read before route rejection: {name}")

    route = {**ROUTE, field: value}
    with pytest.raises(HBQError, match="exact v5 nonvisual contract"):
        bridge.bind_grok_broker_transport(
            broker=BrokerMustNotBeRead(), route=route, before_contact=lambda _: None, runtime_check=lambda: None,
        )
    assert not any(tmp_path.iterdir())


@pytest.mark.parametrize("mutate", [
    lambda result: {**result, "runtime": {**result["runtime"], "adapter_version": 4}},
    lambda result: {**result, "runtime": {**result["runtime"], "identity_evidence": "reported"}},
    lambda result: {**result, "runtime": {**result["runtime"], "reasoning_attested": True}},
    lambda result: {**result, "runtime": {**result["runtime"], "observed_turns": 2}},
])
def test_v3_rejects_non_v5_runtime(mutate, tmp_path: Path) -> None:
    broker = StubBroker(mutate=mutate)
    with pytest.raises(HBQError, match="not retryable"):
        execute(tmp_path, broker)
    assert broker.calls == 1


def test_unchanged_v2_rejects_adapter_five(tmp_path: Path) -> None:
    broker = StubBroker(
        binding_bridge=bridge_v2, adapter_version=5, reasoning_attested=True,
    )
    with pytest.raises(HBQError, match="not retryable"):
        execute(tmp_path, broker, transport_module=bridge_v2, route=LEGACY_ROUTE)
    assert broker.calls == 1


@pytest.mark.parametrize("mutation", [
    lambda result: {**result, "runtime": {**result["runtime"], "execution_contract": {
        **result["runtime"]["execution_contract"], "nonvisual_transport_contract_sha256": "b" * 64,
    }}},
    lambda result: {**result, "runtime": {**result["runtime"], "execution_contract": {
        **result["runtime"]["execution_contract"], "output_schema_hash": "b" * 64,
    }}},
    lambda result: {**result, "runtime": {**result["runtime"], "execution_contract": {
        **result["runtime"]["execution_contract"], "staged_prompt_sha256": "b" * 64,
    }}},
    lambda result: {**result, "runtime": {**result["runtime"], "execution_contract": {
        **result["runtime"]["execution_contract"], "staged_prompt_byte_length": 0,
    }}},
])
def test_v5_contract_schema_and_prompt_drift_are_rejected(mutation, tmp_path: Path) -> None:
    broker = StubBroker(mutate=mutation)
    with pytest.raises(HBQError, match="not retryable"):
        execute(tmp_path, broker)
    assert broker.calls == 1


@pytest.mark.parametrize("mutation", [
    lambda result: {**result, "request_hash": "b" * 64},
    lambda result: {**result, "runtime": {**result["runtime"], "session_id_hash": "b" * 64}},
    lambda result: {**result, "runtime": {**result["runtime"], "request_id_hash": "b" * 64}},
    lambda result: {**result, "runtime": {**result["runtime"], "envelope_hash": "b" * 64}},
    lambda result: {**result, "runtime": {**result["runtime"], "requested_model": "other"}},
])
def test_request_envelope_session_and_model_bindings_are_rejected(mutation, tmp_path: Path) -> None:
    broker = StubBroker(mutate=mutation)
    with pytest.raises(HBQError, match="not retryable"):
        execute(tmp_path, broker)
    assert broker.calls == 1


def test_before_contact_gate_blocks_call_and_automatic_resend(tmp_path: Path) -> None:
    broker = StubBroker()
    with pytest.raises(HBQError, match="not retryable"):
        execute(
            tmp_path,
            broker,
            before_contact=lambda _: (_ for _ in ()).throw(RuntimeError("synthetic gate deny")),
        )
    assert broker.calls == 0
    with pytest.raises(HBQError, match="terminal nonretryable"):
        execute(tmp_path, broker, resume=True)
    assert broker.calls == 0


def test_precontact_terminal_denial_is_retained_without_admission_or_resend(tmp_path: Path) -> None:
    broker = PrecontactDenialBroker()
    admitted = []
    with pytest.raises(HBQError, match="not retryable"):
        execute(tmp_path, broker, before_contact=admitted.append)
    assert broker.calls == 1 and admitted == []
    outcome = json.loads(next((tmp_path / "run").rglob("outcome.json")).read_bytes())
    assert outcome == broker.outcome
    with pytest.raises(HBQError, match="terminal nonretryable"):
        execute(tmp_path, broker, resume=True)
    assert broker.calls == 1


@pytest.mark.parametrize("target", [
    SOURCE,
    Path(bridge_v2.__file__),
    Path(bridge_v2._legacy.__file__),
])
def test_all_source_chain_drift_blocks_contact(target: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    original_read_bytes = Path.read_bytes

    def drift(path: Path) -> bytes:
        raw = original_read_bytes(path)
        return raw + b" " if path.resolve() == target.resolve() else raw

    broker = StubBroker()
    with pytest.raises(HBQError, match="not retryable"):
        execute(tmp_path, broker, after_bind=lambda: monkeypatch.setattr(Path, "read_bytes", drift))
    assert broker.calls == 0
