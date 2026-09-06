from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from hbqrs import HBQError, book_root, run_judge, runner
from hbqrs import grok_broker_transport_v2 as bridge

SOURCE = Path(bridge.__file__)


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


class StubBroker:
    """Public-synthetic broker surface; it never starts a native process."""

    def __init__(self, *, mutate=None):
        self.context = None
        self.calls = 0
        self.mutate = mutate or (lambda value: value)
        self.envelope = b""

    def run_grok_native_request(self, route_name, request, *, output_schema, nonvisual_max_turns, session_id, before_contact, expected_route_sha256):
        assert route_name == "public-synthetic-grok" and nonvisual_max_turns == 1 and len(expected_route_sha256) == 64
        before_contact()
        self.calls += 1
        questions = output_schema["properties"]["verdicts"]["items"]["properties"]["question_id"]["enum"]
        output = {"verdicts": [{"question_id": question, "verdict": "YES", "confidence": 0.8,
                                  "evidence": [{"kind": "exact_quote", "reference": "line:1", "exact_quote": "A short test scene.", "summary": None}],
                                  "note": "Public synthetic attested transport fixture."} for question in questions]}
        execution = bridge._context_bindings(self.context, ROUTE)[-1]["execution_contract"]
        request_raw = bridge._canonical(request)
        request_id = "public-synthetic-request"
        self.envelope = bridge._canonical({"structuredOutput": output, "sessionId": session_id, "requestId": request_id})
        result = {"schema_version": 2, "request_hash": digest(request_raw), "output": output,
                  "output_hash": digest(bridge._canonical(output)),
                  "runtime": {"session_id_hash": digest(session_id.encode()), "request_id_hash": digest(request_id.encode()),
                              "envelope_hash": digest(self.envelope), "requested_model": "grok-4.6", "requested_reasoning_effort": "high",
                              "execution_contract": execution, "adapter_version": 4,
                              "execution_policy": "bounded_nonvisual_deny_wins_attested", "tool_policy_attestation_hash": "a" * 64,
                              "reasoning_attested": True},
                  "native_envelope_artifact": {"schema_version": 1, "sha256": digest(self.envelope), "byte_length": len(self.envelope)}}
        return {"state": "completed", "result": self.mutate(result), "failure": None}

    def read_grok_native_envelope(self, descriptor):
        return self.envelope


ROUTE = {"name": "public-synthetic-grok", "adapter": "grok_exec", "model": "grok-4.6", "reasoning_effort": "high", "timeout_seconds": 30}


def execute(tmp_path: Path, broker: StubBroker, *, before_contact=lambda context: None, after_bind=lambda: None, resume: bool = False):
    def admission(context):
        broker.context = context
        before_contact(context)

    source_hash = digest(SOURCE.read_bytes())
    transport = bridge.bind_grok_broker_transport(broker=broker, route=ROUTE, before_contact=admission, runtime_check=lambda: None)
    after_bind()
    artifact = tmp_path / "artifact.txt"
    artifact.parent.mkdir(parents=True, exist_ok=True)
    if not artifact.exists():
        artifact.write_text("A short test scene.", encoding="utf-8")
    return run_judge(
        artifact_path=artifact, bundle_id="prose.short_story", provider="grok", model="grok-4.6", output_dir=tmp_path / "run",
        registry=book_root() / "registry/all_modules.json", bundles=book_root() / "bundles/all_bundles.json", batch_size=178,
        batch_attempts=1, reasoning="high", allow_remote=True, allow_unattested_reasoning=True, timeout=30,
        attempt_lifecycle_policy=runner.ATTEMPT_LIFECYCLE_POLICY, grok_transport=transport,
        grok_transport_sha256=source_hash, response_schema_mode="batch_question_ids_v1", resume=resume,
    )


def test_attested_public_synthetic_result_persists_runner_checkpoint_and_five_artifacts(tmp_path: Path) -> None:
    broker = StubBroker()
    result = execute(tmp_path, broker)
    assert result["verdicts"] == 178 and broker.calls == 1
    checkpoint = json.loads((tmp_path / "run/responses/batch-0001.json").read_bytes())
    metadata = checkpoint["provider"]
    assert metadata["tool_free"] is True and metadata["reasoning_attested"] is True
    assert set(metadata["provider_artifacts"]) == {"request", "context", "outcome", "envelope", "receipt"}
    context = json.loads((tmp_path / "run" / metadata["provider_artifacts"]["context"]["path"]).read_bytes())
    assert context["execution_contract"]["tools"] == "deny_wins_none_attested"
    execute(tmp_path, broker, resume=True)
    assert broker.calls == 1


@pytest.mark.parametrize("mutate", [
    lambda result: {**result, "schema_version": 1},
    lambda result: {**result, "runtime": {key: value for key, value in result["runtime"].items() if key != "tool_policy_attestation_hash"}},
    lambda result: {**result, "runtime": {**result["runtime"], "tool_policy_attestation_hash": "A" * 64}},
    lambda result: {**result, "runtime": {**result["runtime"], "adapter_version": 3}},
    lambda result: {**result, "runtime": {**result["runtime"], "execution_policy": "legacy"}},
    lambda result: {**result, "runtime": {**result["runtime"], "execution_contract": {**result["runtime"]["execution_contract"], "tools": "none"}}},
])
def test_legacy_or_malformed_attestation_is_rejected(tmp_path: Path, mutate) -> None:
    broker = StubBroker(mutate=mutate)
    with pytest.raises(HBQError, match="not retryable"):
        execute(tmp_path, broker)
    assert broker.calls == 1
    outcome = json.loads(next((tmp_path / "run").rglob("outcome.json")).read_bytes())
    assert outcome["state"] == "completed"


def test_before_contact_gate_blocks_stub_call_and_automatic_resend(tmp_path: Path) -> None:
    broker = StubBroker()
    with pytest.raises(HBQError, match="not retryable"):
        execute(tmp_path, broker, before_contact=lambda context: (_ for _ in ()).throw(RuntimeError("synthetic gate deny")))
    assert broker.calls == 0
    with pytest.raises(HBQError, match="terminal nonretryable"):
        execute(tmp_path, broker, resume=True)
    assert broker.calls == 0


def test_source_and_downstream_artifact_drift_fail_replay(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    broker = StubBroker()
    execute(tmp_path, broker)
    checkpoint = json.loads((tmp_path / "run/responses/batch-0001.json").read_bytes())
    receipt = tmp_path / "run" / checkpoint["provider"]["provider_artifacts"]["receipt"]["path"]
    receipt.write_bytes(receipt.read_bytes() + b" ")
    with pytest.raises(HBQError, match="artifact"):
        execute(tmp_path, broker, resume=True)
    original_read_bytes = Path.read_bytes
    def drift_source():
        monkeypatch.setattr(Path, "read_bytes", lambda path: original_read_bytes(path) + b" " if path.resolve() == SOURCE.resolve() else original_read_bytes(path))
    drifted_broker = StubBroker()
    with pytest.raises(HBQError, match="not retryable"):
        execute(tmp_path / "source-drift", drifted_broker, after_bind=drift_source)
    assert drifted_broker.calls == 0
