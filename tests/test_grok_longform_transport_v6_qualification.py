"""Synthetic qualification boundaries; no subprocess, account, or provider calls."""
import copy
from datetime import datetime, timedelta, timezone
import importlib.util
import json
from pathlib import Path
import sys
import uuid
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
TOOLS = Path.home() / ".codex/tools"
spec = importlib.util.spec_from_file_location("test_v6_native_qualification", ROOT / "evaluation-results/hbq-grok-longform-transport-v6/qualify.py")
q = importlib.util.module_from_spec(spec); spec.loader.exec_module(q)


def route():
    d, _ = q.w.profile(TOOLS)
    return {"name": "grok-build-grok-4.7", "adapter": "grok_exec", "provider": "xai_grok_build",
        "account_class": "subscription", "model": "grok-4.7", "reported_model": "grok-4.7-build",
        "reasoning_effort": "high", "armed": True, "trusted": True, "health": "healthy", "zero_charge": True,
        "timeout_seconds": 900, "nonvisual_max_turns": 1, "nonvisual_transport_contract": d.CONTRACT_NAME,
        "capabilities": [d.CONTRACT_NAME, "bounded_nonvisual_read_only"], "allowed_payload_classes": ["public_synthetic"],
        "command": [str(Path(sys.executable).resolve()), str(q.HERE / "adapters/grok_exec.py"), "--tools-root", str(TOOLS.resolve())],
        "grok_command": ["synthetic-never-executed"], "grok_command_identity": {"synthetic": True},
        "subscription_receipt_hash": "1" * 64, "grok_cli_version": "synthetic",
        "cost_evidence": {"expires_at": "2026-10-16T05:40:00Z"}}


@pytest.fixture
def case(tmp_path):
    d, commitment = q.w.profile(TOOLS)
    row = {"endpoint": "grok", "endpoint_ordinal": 88, "prompt_bytes": 248426,
        "prompt_sha256": q.PROMPT_SHA, "schema_sha256": q.SCHEMA_SHA, "arm": "hbq",
        "logical_sample_id": "2" * 64, "request_sha256": "3" * 64,
        "prompt_policy": "human_authored_source_override_v1", "sources": [{"sha256": "4" * 64}],
        "task_context": {"sha256": "5" * 64}}
    manifest = {"requests": [row], "artifacts": {"synthetic.txt": {"sha256": "6" * 64}}}
    root = tmp_path / "frozen"; root.mkdir(); (root / "manifest.json").write_bytes(q.canonical(manifest))
    prompt = b"Synthetic public full-source fixture.\r\nNo normalization."
    schema = q.canonical({"$schema_version": 1, "type": "object"})
    source_inputs = (prompt, schema, {"synthetic": "Synthetic source"}, "Synthetic context")
    with patch.object(q.c, "load_manifest", return_value=(manifest, root, None, None, None)), \
            patch.object(q.c, "inputs", return_value=source_inputs):
        plan, *_ = q.build_plan(root / "manifest.json", TOOLS, tmp_path / "plan", tmp_path / "result")
    return tmp_path, d, commitment, row, manifest, root, source_inputs, plan


def test_preparation_distinct_identity_preserves_exact_condition_and_pins(case):
    tmp, _, _, row, manifest, root, inputs, plan = case
    assert plan["source_condition"] == row and plan["source_artifacts"] == manifest["artifacts"]
    assert plan["qualification_id"] != row["logical_sample_id"]
    assert plan["study_vote"] is False and plan["execution_authority"] is False
    assert plan["outbound_receipt"]["prompt"]["sha256"] == q.digest(inputs[0])
    assert plan["outbound_receipt"]["additional_prompt_text"] is False
    assert not (tmp / "plan").exists() and not (tmp / "result").exists()
    row["endpoint_ordinal"] = 89
    with patch.object(q.c, "load_manifest", return_value=(manifest, root, None, None, None)):
        with pytest.raises(ValueError, match="maximum P4"):
            q.build_plan(root / "manifest.json", TOOLS, tmp / "plan", tmp / "result")


def test_route_refuses_tools_paid_fallback_wrong_pin_runtime_and_command(case):
    _, _, _, _, _, _, _, plan = case
    good = route()
    q.validate_route(plan, good, q.digest(q.canonical(good).rstrip(b"\n")), TOOLS)
    for change in ("tools", "paid", "version", "interpreter"):
        r = copy.deepcopy(good)
        if change == "tools": r["capabilities"].append("web_search")
        elif change == "paid": r["zero_charge"] = False
        elif change == "version": r["nonvisual_transport_contract"] = "grok_nonvisual_history_v5"
        else: r["command"][0] = "C:/Python314/python.exe"
        with pytest.raises(ValueError): q.validate_route(plan, r, q.digest(q.canonical(r).rstrip(b"\n")), TOOLS)
    with pytest.raises(ValueError, match="route pin"):
        q.validate_route(plan, good, "0" * 64, TOOLS)
    bad = copy.deepcopy(plan); bad["python_runtime"]["version"] = "wrong"
    with pytest.raises(ValueError, match="runtime/profile"):
        q.validate_route(bad, good, q.digest(q.canonical(good).rstrip(b"\n")), TOOLS)


def test_precise_900_second_campaign_and_expiry_boundaries():
    r = route(); boundary = datetime(2026, 10, 16, 5, 25, tzinfo=timezone.utc)
    assert q.c.grok_contact_allowed(r, boundary - timedelta(microseconds=1))
    assert not q.c.grok_contact_allowed(r, boundary)
    r["cost_evidence"]["expires_at"] = "2026-10-15T00:00:00Z"
    boundary = datetime(2026, 10, 14, 23, 45, tzinfo=timezone.utc)
    assert q.c.grok_contact_allowed(r, boundary - timedelta(microseconds=1))
    assert not q.c.grok_contact_allowed(r, boundary)


class MockNative:
    """Constructed receipt exercises the real parser; never launches a CLI."""
    def __init__(self, derived, route, output, *, ambiguous=False, stop=False):
        self.d, self.route, self.output = derived, route, output
        self.ambiguous, self.stop, self.contacts = ambiguous, stop, 0

    def run_grok_native_request(self, name, request, *, output_schema, nonvisual_max_turns, session_id,
                                before_contact, expected_route_sha256):
        if self.stop: (self.output / "STOP").write_bytes(b"stop before contact")
        try: before_contact()
        except ValueError:
            return {"state": "definitely_not_contacted", "result": None, "failure": {"code": "before_contact_failed"}}
        self.contacts += 1
        if self.ambiguous: return {"state": "ambiguous", "result": None, "failure": {"code": "unclassified_after_launch"}}
        m = self.d.load_broker(); r = self.route; answer = {"answer": "synthetic"}
        self.envelope = m._canonical({"sessionId": session_id, "requestId": "synthetic-request", "structuredOutput": answer})
        runtime = {"adapter_version": 6, "requested_model": r["model"], "reported_model": r["reported_model"],
            "requested_reasoning_effort": "high", "reasoning_attested": False,
            "reasoning_attestation": "not_reported_by_grok_build_cli", "identity_evidence": "requested_only",
            "cli_version": r["grok_cli_version"], "session_id_hash": q.digest(session_id.encode()),
            "request_id_hash": q.digest(b"synthetic-request"), "envelope_hash": q.digest(self.envelope),
            "command_identity": r["grok_command_identity"], "command_identity_hash": q.digest(m._canonical({
                "adapter_version": 6, "grok_command": r["grok_command"], "model": r["model"],
                "reported_model": r["reported_model"], "reasoning_effort": "high"})),
            "subscription_receipt_hash": r["subscription_receipt_hash"], "execution_policy": "bounded_nonvisual_deny_wins_attested",
            "usage_telemetry": {"status": "not_reported"}, "nonvisual_max_turns": 1, "observed_turns": 1,
            "tool_policy_attestation_hash": "7" * 64,
            "execution_contract": {"schema_version": 1, "output_schema_hash": q.digest(m._canonical(output_schema)),
                "max_turns": 1, "tools": "deny_wins_none_attested", "staged_prompt_sha256": q.digest(request["prompt"].encode()),
                "staged_prompt_byte_length": len(request["prompt"].encode()), "nonvisual_transport_contract": self.d.CONTRACT,
                "nonvisual_transport_contract_sha256": q.digest(m._canonical(self.d.CONTRACT))},
            "transport": {"schema_version": 1, "exit_code": 0, "stdout_byte_length": len(self.envelope), "stderr_byte_length": 0}}
        result = {"schema_version": 2, "request_hash": q.digest(m._canonical(request)), "output": answer,
            "output_hash": q.digest(m._canonical(answer)), "runtime": runtime,
            "native_envelope_artifact": {"schema_version": 1, "sha256": q.digest(self.envelope), "byte_length": len(self.envelope)}}
        return {"state": "completed", "result": result, "failure": None}

    def read_grok_native_envelope(self, descriptor): return self.envelope


def run(case, *, ambiguous=False, stop=False, admitted=False):
    tmp, d, _, _, manifest, root, inputs, plan = case
    output = tmp / "result"; r = route(); broker = MockNative(d, r, output, ambiguous=ambiguous, stop=stop)
    class Validator:
        def semantic_validate(self, *args, **kwargs): return {"accepted": admitted, "mock_only": True}
    with patch.object(q.c, "inputs", return_value=inputs):
        terminal = q.execute(output, plan, q.digest(q.canonical(plan)), r,
            q.digest(q.canonical(r).rstrip(b"\n")), root, manifest, None, Validator(), broker, d)
    return terminal, broker, output


def test_completed_receipt_qualifies_transport_despite_semantic_missing_and_replays(case):
    terminal, broker, output = run(case)
    assert terminal["transport_qualified"] and terminal["semantic_admission"] == "rejected_unscored"
    assert terminal["study_vote"] is False and broker.contacts == 1
    _, d, _, _, _, _, inputs, _ = case
    sample = output / "attempt-0001"; job = json.loads((output / "job.json").read_bytes())
    assert q.verify_native(sample, job, inputs[0], inputs[1], d) == {"answer": "synthetic"}
    assert broker.contacts == 1


def test_full_parser_refuses_foreign_session_tool_policy_prompt_and_contract(case):
    _, _, output = run(case)
    _, d, _, _, _, _, inputs, _ = case
    sample = output / "attempt-0001"; job = json.loads((output / "job.json").read_bytes())
    raw = (sample / "native-result.json").read_bytes()
    for change in ("tool", "prompt", "contract", "version"):
        value = json.loads(raw); runtime = value["result"]["runtime"]
        if change == "tool": runtime["tool_policy_attestation_hash"] = ""
        elif change == "prompt": runtime["execution_contract"]["staged_prompt_sha256"] = "0" * 64
        elif change == "contract": runtime["execution_contract"]["nonvisual_transport_contract"]["prompt_utf8_bytes"] += 1
        else: runtime["adapter_version"] = 5
        (sample / "native-result.json").write_bytes(q.canonical(value))
        with pytest.raises(ValueError): q.verify_native(sample, job, inputs[0], inputs[1], d)
    (sample / "native-result.json").write_bytes(raw)
    started = json.loads((sample / "attempt-started.json").read_bytes()); started["session_id"] = str(uuid.uuid4())
    (sample / "attempt-started.json").write_bytes(q.canonical(started))
    with pytest.raises(ValueError, match="started/session"):
        q.verify_native(sample, job, inputs[0], inputs[1], d)


def test_ambiguity_and_incomplete_handle_permanently_reserve_qualification(case):
    terminal, broker, output = run(case, ambiguous=True)
    assert terminal["state"] == "ambiguous" and not terminal["transport_qualified"] and broker.contacts == 1
    with pytest.raises(ValueError, match="already reserved"):
        run(case)
    (output / "attempt-0001/terminal.json").unlink()
    with pytest.raises(ValueError, match="already reserved"):
        run(case)


def test_stop_before_contact_and_stop_during_call_settles_once(case):
    terminal, broker, output = run(case, stop=True)
    assert broker.contacts == 0 and terminal["state"] == "definitely_not_contacted"
    assert terminal["stop_observed_after_settlement"] and not (output / "attempt-0001/attempt-started.json").exists()


def test_stop_created_after_contact_does_not_discard_current_completion(case):
    original = MockNative.read_grok_native_envelope
    def settle(self, descriptor):
        (self.output / "STOP").write_bytes(b"stop during call")
        return original(self, descriptor)
    with patch.object(MockNative, "read_grok_native_envelope", settle):
        terminal, broker, _ = run(case, admitted=True)
    assert terminal["transport_qualified"] and terminal["semantic_admission"] == "accepted_unscored"
    assert terminal["stop_observed_after_settlement"] and broker.contacts == 1


def test_deadline_rechecked_at_contact_and_frozen_source_start_binding(case):
    with patch.object(q.c, "grok_contact_allowed", side_effect=[True, False]):
        terminal, broker, output = run(case)
    assert broker.contacts == 0 and terminal["state"] == "definitely_not_contacted"
    assert not (output / "attempt-0001/attempt-started.json").exists()


def test_wrong_source_request_cannot_replay_as_qualification(case):
    _, _, output = run(case)
    _, d, _, _, _, _, inputs, _ = case
    sample = output / "attempt-0001"; job = json.loads((output / "job.json").read_bytes())
    started = json.loads((sample / "attempt-started.json").read_bytes())
    started["source_request_sha256"] = "0" * 64
    (sample / "attempt-started.json").write_bytes(q.canonical(started))
    with pytest.raises(ValueError, match="started/session"):
        q.verify_native(sample, job, inputs[0], inputs[1], d)
