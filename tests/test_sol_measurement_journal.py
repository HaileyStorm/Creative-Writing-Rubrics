"""Synthetic journal tests; native Broker transport has separate contract tests."""

from dataclasses import replace

import pytest

from hbqrs import HBQError
from hbqrs import sol_broker_transport as transport
from hbqrs import sol_measurement_journal as journal


@pytest.fixture
def case(tmp_path, monkeypatch):
    prompt = "Exact public story payload: café\n".encode()
    schema = transport._canonical({"type": "array", "items": {"type": "object",
        "required": ["question_id", "verdict"], "properties": {
            "question_id": {"enum": ["q1", "q2"]}, "verdict": {"enum": ["YES", "NO"]}},
        "additionalProperties": False}, "minItems": 2, "maxItems": 2})
    final = transport._canonical([{"question_id": "q1", "verdict": "YES"},
                                  {"question_id": "q2", "verdict": "NO"}])
    events = b'synthetic retained event stream\n'
    projection = {"schema_version": 1, "thread_id": "synthetic-thread-1", "usage": {}}
    disclosure, route = {"payload_classification": "public"}, {"synthetic_route": True}
    digest = transport._sha256
    request = {"plan_sha256": "1" * 64, "ordinal": 1, "pass_id": "p1", "logical_sample_id": "s1",
               "question_ids": ["q1", "q2"], "prompt_sha256": digest(prompt), "prompt_bytes": len(prompt),
               "schema_sha256": digest(schema), "schema_bytes": len(schema),
               "execution_source_sha256": "2" * 64, "authorization_sha256": "3" * 64,
               "route_sha256": digest(transport._canonical(route))}
    receipt = replace(transport._receipt("completed", route_sha256=request["route_sha256"], prompt=prompt,
        planned_schema=schema, canonical_schema=schema, disclosure=transport._canonical(disclosure)),
        request_sha256=digest(transport._canonical({"prompt": prompt.decode()})),
        output_sha256=digest(final), raw_final_message_sha256=digest(final), raw_final_message_byte_length=len(final),
        events_sha256=digest(events), events_byte_length=len(events), final_message_bytes=final, events_bytes=events,
        parsed_output=transport._strict_json(final, "fixture"), requested_model="gpt-5.6-sol",
        requested_reasoning_effort="high", identity_evidence="requested_only",
        provider_contact_cardinality_evidence="unattested", one_provider_bearing_cli_invocation_observed=True,
        one_turn_observed=True, zero_tool_activity_observed=True,
        schema_artifact=transport.ArtifactDescriptor(digest(schema), len(schema)),
        disclosure_artifact=transport.ArtifactDescriptor(digest(transport._canonical(disclosure)), len(transport._canonical(disclosure))),
        events_artifact=transport.ArtifactDescriptor(digest(events), len(events)),
        final_message_artifact=transport.ArtifactDescriptor(digest(final), len(final)))
    calls = []
    def fake(broker, **kwargs):
        calls.append(kwargs)
        kwargs["precontact_hook"]()
        return receipt
    monkeypatch.setattr(transport, "run_sol_native_batch", fake)
    kwargs = {"request": request, "prompt_utf8": prompt, "planned_schema_utf8": schema, "disclosure": disclosure,
              "route_snapshot": route, "broker": object(), "event_replayer": lambda raw: projection if raw == events else {},
              "precontact_gate": lambda: None}
    return tmp_path / "request-0001", kwargs, calls, receipt


def test_roundtrip_retains_exact_payload_and_requested_identity(case):
    path, kwargs, calls, _ = case
    result = journal.run_request(path, **kwargs)
    replay = journal.replay_request(path, expected_terminal_sha256=result["terminal_sha256"],
        expected_request=kwargs["request"], event_replayer=kwargs["event_replayer"])
    assert len(calls) == 1
    assert (path / "prompt.txt").read_bytes() == kwargs["prompt_utf8"]
    assert replay["identity_evidence"] == "requested_only"
    assert replay["provider_contact_cardinality_evidence"] == "unattested"
    assert replay["full_pass_admitted"] is False
    assert [row["question_id"] for row in replay["admitted_rows"]] == ["q1", "q2"]


@pytest.mark.parametrize("state", ["completed", "ambiguous", "definitely_not_contacted"])
def test_every_terminal_blocks_resend(case, monkeypatch, state):
    path, kwargs, _, receipt = case
    monkeypatch.setattr(transport, "run_sol_native_batch", lambda *a, **k: replace(receipt, state=state))
    journal.run_request(path, **kwargs)
    with pytest.raises(FileExistsError):
        journal.run_request(path, **kwargs)


def test_precontact_failure_is_consumed_and_has_safe_terminal(case):
    path, kwargs, calls, _ = case
    checks = []
    def gate():
        checks.append(1)
        if len(checks) == 2:
            raise RuntimeError("sensitive diagnostic")
    kwargs["precontact_gate"] = gate
    result = journal.run_request(path, **kwargs)
    assert result["state"] == "ambiguous" and len(calls) == 1
    assert b"sensitive" not in (path / "terminal.json").read_bytes()
    with pytest.raises(FileExistsError):
        journal.run_request(path, **kwargs)


def test_initial_gate_failure_does_not_reserve_or_call(case):
    path, kwargs, calls, _ = case
    def gate():
        raise RuntimeError("unapproved")
    kwargs["precontact_gate"] = gate
    with pytest.raises(RuntimeError):
        journal.run_request(path, **kwargs)
    assert not path.exists() and not calls


def test_terminal_write_failure_leaves_unresolved_attempt(case, monkeypatch):
    path, kwargs, calls, _ = case
    original = journal._write
    def fail_terminal(p, raw):
        if p.name == "terminal.json":
            raise OSError("write interrupted")
        original(p, raw)
    monkeypatch.setattr(journal, "_write", fail_terminal)
    with pytest.raises(OSError):
        journal.run_request(path, **kwargs)
    assert (path / "start.json").is_file() and len(calls) == 1
    with pytest.raises(FileExistsError):
        journal.run_request(path, **kwargs)


@pytest.mark.parametrize("name", ["prompt.txt", "schema.json", "final.json", "events.jsonl", "route.json", "disclosure.json"])
def test_retained_artifact_drift_rejected(case, name):
    path, kwargs, _, _ = case
    result = journal.run_request(path, **kwargs)
    with (path / name).open("ab") as output:
        output.write(b" ")
    with pytest.raises(HBQError):
        journal.replay_request(path, expected_terminal_sha256=result["terminal_sha256"],
            expected_request=kwargs["request"], event_replayer=kwargs["event_replayer"])


def test_wrong_question_order_is_terminal_ambiguous(case):
    path, kwargs, _, _ = case
    kwargs["request"]["question_ids"] = ["q2", "q1"]
    assert journal.run_request(path, **kwargs)["state"] == "ambiguous"


def test_native_replay_mismatch_rejected(case):
    path, kwargs, _, _ = case
    result = journal.run_request(path, **kwargs)
    with pytest.raises(HBQError):
        journal.replay_request(path, expected_terminal_sha256=result["terminal_sha256"],
            expected_request=kwargs["request"], event_replayer=lambda raw: {})


@pytest.mark.parametrize("name", ["events.jsonl", "final.json"])
def test_ambiguous_completed_artifacts_remain_checked(case, name):
    path, kwargs, _, _ = case
    kwargs["request"]["question_ids"] = ["q2", "q1"]
    result = journal.run_request(path, **kwargs)
    assert result["state"] == "ambiguous"
    assert journal.replay_request(path, expected_terminal_sha256=result["terminal_sha256"],
        expected_request=kwargs["request"], event_replayer=kwargs["event_replayer"])["state"] == "ambiguous"
    with (path / name).open("ab") as output:
        output.write(b" ")
    with pytest.raises(HBQError):
        journal.replay_request(path, expected_terminal_sha256=result["terminal_sha256"],
            expected_request=kwargs["request"], event_replayer=kwargs["event_replayer"])


@pytest.mark.parametrize("field", ["schema_artifact", "disclosure_artifact", "events_artifact",
                                    "final_message_artifact", "canonical_schema_byte_length", "disclosure_byte_length"])
def test_replay_recomputes_receipt_descriptors_and_sizes(case, field):
    path, kwargs, _, _ = case
    journal.run_request(path, **kwargs)
    terminal = transport._strict_json((path / "terminal.json").read_bytes(), "fixture")
    if field.endswith("artifact"):
        terminal["receipt"][field]["byte_length"] += 1
    else:
        terminal["receipt"][field] += 1
    raw = transport._canonical(terminal)
    (path / "terminal.json").write_bytes(raw)
    with pytest.raises(HBQError):
        journal.replay_request(path, expected_terminal_sha256=transport._sha256(raw),
            expected_request=kwargs["request"], event_replayer=kwargs["event_replayer"])
