import importlib.util
import json
from pathlib import Path
from threading import Event
from types import SimpleNamespace

import pytest


HERE = Path(__file__).resolve().parents[1] / "evaluation-results/hbq-matched-ttcw-20261004"
spec = importlib.util.spec_from_file_location("ttcw_suffix_v3_test", HERE / "collector_suffix_v3.py")
collector = importlib.util.module_from_spec(spec)
spec.loader.exec_module(collector)


def route_fixture(tmp_path, monkeypatch):
    route = {"name": "grok-build-grok-4.7", "model": "grok-4.7", "reported_model": "synthetic-reported",
        "reasoning_effort": "high", "timeout_seconds": 900, "nonvisual_max_turns": 1, "max_concurrency": 10,
        "nonvisual_transport_contract": "grok_nonvisual_history_v5", "armed": True, "trusted": True,
        "zero_charge": True, "allowed_payload_classes": ["public_repo"], "destination": "synthetic",
        "cost_evidence": {"expires_at": "2026-10-06T17:49:22+00:00"}, "subscription_receipt_hash": "receipt",
        "grok_command_identity": {"version": 1}, "grok_cli_version": "synthetic-cli"}
    monkeypatch.setattr(collector, "ROUTE_SHA", collector.sha(collector.canonical(route)))
    root = tmp_path / "route"
    root.mkdir()
    collector.record(root / "routes.json", {"routes": [route]})
    return root, route


def fixture(tmp_path, route):
    root, output = tmp_path / "frozen", tmp_path / "results"
    root.mkdir()
    output.mkdir()
    prompt, schema, text = b"Synthetic exact prompt.", b'{"type":"object"}', b"Synthetic source."
    for name, raw in (("prompt.txt", prompt), ("schema.json", schema), ("source.txt", text), ("context.txt", b"Synthetic context.")):
        (root / name).write_bytes(raw)
    row = {"endpoint": "grok", "endpoint_ordinal": 280, "logical_sample_id": "a" * 64, "arm": "synthetic",
        "prompt_path": "prompt.txt", "prompt_sha256": collector.sha(prompt),
        "schema_path": "schema.json", "schema_sha256": collector.sha(schema),
        "sources": [{"id": "source", "input_path": "source.txt", "sha256": collector.sha(text)}]}
    binding = {"manifest_sha256": "synthetic-manifest", "endpoint": "grok", "model": route["model"],
               "reasoning": route["reasoning_effort"], "route": route, "route_sha256": collector.ROUTE_SHA}
    collector.record(output / "job.json", binding)
    validator = SimpleNamespace(semantic_validate=lambda *args, **kwargs: {"accepted": True, "abstention": False})

    class Broker:
        contacts = 0
        envelope = None
        before_callback = lambda self: None

        def run_grok_native_request(self, name, request, *, output_schema, nonvisual_max_turns,
                                    session_id, before_contact, expected_route_sha256):
            self.before_callback()
            before_contact()
            self.contacts += 1
            answer = {"synthetic_rating": 3}
            self.envelope = collector.canonical({"sessionId": session_id, "structuredOutput": answer})
            runtime = {"session_id_hash": collector.sha(session_id.encode()), "requested_model": route["model"],
                "requested_reasoning_effort": route["reasoning_effort"], "reported_model": route["reported_model"],
                "execution_contract": {"output_schema_hash": collector.sha(collector.canonical(output_schema))},
                "subscription_receipt_hash": route["subscription_receipt_hash"],
                "command_identity": route["grok_command_identity"], "cli_version": route["grok_cli_version"]}
            return {"state": "completed", "result": {"output": answer, "runtime": runtime,
                "request_hash": collector.sha(collector.canonical(request)),
                "output_hash": collector.sha(collector.canonical(answer)),
                "native_envelope_artifact": {"sha256": collector.sha(self.envelope), "byte_length": len(self.envelope)}}}

        def read_grok_native_envelope(self, artifact):
            return self.envelope

    return root, output, row, binding, validator, Broker()


def test_dispatch_contact_guards_use_exact_current_route_margin_stop_and_shared_headroom(tmp_path, monkeypatch):
    route_root, route = route_fixture(tmp_path, monkeypatch)
    root, output, row, binding, validator, broker = fixture(tmp_path, route)
    expiry = collector.datetime.fromisoformat(route["cost_evidence"]["expires_at"])
    signal = Event()
    collector.guard(binding, output, signal, route_root, now=expiry - collector.MARGIN - collector.timedelta(microseconds=1))
    with pytest.raises(ValueError, match="margin"):
        collector.guard(binding, output, signal, route_root, now=expiry - collector.MARGIN)
    changed = dict(route, timeout_seconds=300)
    (route_root / "routes.json").write_text(json.dumps({"routes": [changed]}))
    with pytest.raises(ValueError, match="controls"):
        collector.guard(binding, output, signal, route_root, now=expiry - collector.timedelta(hours=1))
    (route_root / "routes.json").write_text(json.dumps({"routes": [route]}))
    manifest = {"collection_policy": {"name": "semantic_reject_continue_v2", "collector_sha256": collector.SOURCE_DRIVER_SHA},
        "continuation": {"source_manifest_sha256": "source", "prefix_jobs": [{"source_inventory_sha256": "inventory"}]},
        "implementation": {"semantic_validator_sha256": "validator", "schema_subset_sha256": "schema"},
        "artifacts": {}, "executor_contract": {"source_route_sha256": "historical-route"}}
    assert collector.job_binding(manifest, "grok", 10, 10, route)["collector_policy"] == collector.POLICY
    for endpoint in ("sol", "grok"):
        with pytest.raises(ValueError, match="headroom"):
            collector.job_binding(manifest, endpoint, 3, 2, route)
    now = expiry - collector.timedelta(hours=1)
    production_guard = collector.guard
    monkeypatch.setattr(collector, "guard", lambda *args, **kwargs: production_guard(*args, **kwargs, now=now))
    broker.before_callback = lambda: (output / "STOP").write_text("synthetic owner STOP")
    assert collector.collect_one(row, binding, root, output, None, validator, signal, route_root, broker) == "unadmitted_no_resend"
    assert broker.contacts == 0 and signal.is_set()
    assert not (collector.sample_path(output, row) / "attempt-started.json").exists()


def test_late_evidence_failure_reserves_slot_and_drains_started_tail_without_next_dispatch(tmp_path, monkeypatch):
    route_root, route = route_fixture(tmp_path, monkeypatch)
    root, output, row, binding, validator, broker = fixture(tmp_path, route)
    monkeypatch.setattr(collector, "guard", lambda *args, **kwargs: None)
    original = Path.read_bytes
    injected = False

    def late_failure(path):
        nonlocal injected
        if not injected and path.name == "acceptance.json" and path.parent == collector.sample_path(output, row):
            injected = True
            raise OSError("Synthetic private detail must not enter terminal")
        return original(path)

    monkeypatch.setattr(Path, "read_bytes", late_failure)
    signal = Event()
    assert collector.collect_one(row, binding, root, output, None, validator, signal, route_root, broker) == "unadmitted_no_resend"
    sample = collector.sample_path(output, row)
    terminal, answer = collector.replay(sample, row, binding, root, None, validator)
    assert injected and signal.is_set() and terminal["accepted"] is False and answer is None
    assert terminal["no_resend"] and "error" not in terminal
    with pytest.raises(FileExistsError):
        collector.collect_one(row, binding, root, output, None, validator, Event(), route_root, broker)
    incomplete = output / "incomplete"
    incomplete.mkdir()
    with pytest.raises(ValueError, match="Occupied unresolved"):
        collector.replay(incomplete, row, binding, root, None, validator)
    second_started, failure_settled = Event(), Event()
    started = []

    def worker(item, halt):
        started.append(item["endpoint_ordinal"])
        if item["endpoint_ordinal"] == 280:
            assert second_started.wait(5)
            halt.set()
            failure_settled.set()
            return "unadmitted_no_resend"
        second_started.set()
        assert failure_settled.wait(5)
        return "accepted"

    states, stopped = collector.dispatch([{"endpoint_ordinal": n} for n in (280, 281, 282)], output, 2, worker,
        lambda halt: None)
    assert stopped and set(started) == {280, 281}
    assert {(r["ordinal"], r["state"]) for r in states} == {(280, "unadmitted_no_resend"), (281, "accepted")}
