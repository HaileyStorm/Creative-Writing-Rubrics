"""Provider-free composed replay and independent pre-label lifecycle boundaries."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
import uuid

import pytest

HERE = Path(__file__).resolve().parents[1] / "evaluation-results/hbq-matched-ttcw-20261004"
spec = importlib.util.spec_from_file_location("ttcw_chain_v3_test", HERE / "analysis_chain_v3.py")
a = importlib.util.module_from_spec(spec)
spec.loader.exec_module(a)


def write(path, value):
    path.write_bytes(json.dumps(value, sort_keys=True, separators=(",", ":")).encode())
    return a.sha(path.read_bytes())


def test_composed_v3_strict_replay_missing_failure_and_no_duplicate_vote(tmp_path, monkeypatch):
    chain, loaded = a.runtime()
    v3, prepare = loaded["suffix_v3"], loaded["prepare"]
    root, results = tmp_path / "frozen", tmp_path / "results"
    root.mkdir(); results.mkdir()
    prompt, schema, text = b"Exact synthetic prompt", b'{"type":"object"}', b"Exact synthetic source"
    for name, raw in (("prompt.txt", prompt), ("schema.json", schema), ("source.txt", text), ("context.txt", b"Exact context")):
        (root / name).write_bytes(raw)
    pins = {p.name: {"sha256": a.sha(p.read_bytes()), "bytes": p.stat().st_size} for p in root.iterdir()}
    rows = [{"endpoint": "grok", "endpoint_ordinal": n, "logical_sample_id": f"{n:064x}", "arm": "synthetic",
             "prompt_path": "prompt.txt", "prompt_sha256": a.sha(prompt), "schema_path": "schema.json",
             "schema_sha256": a.sha(schema), "sources": [{"id": "source", "input_path": "source.txt", "sha256": a.sha(text)}]}
            for n in range(1, 282)]
    for row in rows:
        row["request_sha256"] = a.sha(prepare.canonical(row))
    base = {"requests": rows, "artifacts": pins}
    source = {"requests": rows[279:], "artifacts": pins,
        "collection_policy": {"name": "semantic_reject_continue_v2", "collector_sha256": v3.SOURCE_DRIVER_SHA},
        "continuation": {"reserved_through_endpoint_ordinal": 279, "source_manifest_sha256": "prior",
            "prefix_jobs": [{"source_inventory_sha256": "inventory"}]},
        "implementation": {"semantic_validator_sha256": "semantic", "schema_subset_sha256": "schema"},
        "executor_contract": {"source_route_sha256": "prior-route"}}
    base["implementation"] = source["implementation"]
    base_raw = prepare.canonical(base)
    source["manifest_content_sha256"] = a.sha(prepare.canonical(source))
    manifest_path = root / "manifest.json"
    manifest_path.write_bytes(prepare.canonical(source))
    monkeypatch.setattr(v3, "MANIFEST_SHA", a.sha(manifest_path.read_bytes()))
    route = {"model": "grok-4.7", "reasoning_effort": "high", "reported_model": "synthetic-native",
             "destination": "synthetic", "subscription_receipt_hash": "subscription",
             "grok_command_identity": {"version": 1}, "grok_cli_version": "synthetic"}
    monkeypatch.setattr(v3, "ROUTE_SHA", a.sha(v3.canonical(route)))
    job = v3.job_binding(source, "grok", 2, 2, route)
    v3.record(results / "job.json", job)
    validator = SimpleNamespace(semantic_validate=lambda *args, **kwargs: {"accepted": True, "abstention": False})
    monkeypatch.setattr(v3, "load_manifest", lambda *args: (source, root, rows[279:], None, validator))
    session = str(uuid.uuid4())
    accepted = v3.sample_path(results, rows[279]); accepted.mkdir()
    answer = {"value": 3}
    envelope_raw = v3.canonical({"sessionId": session, "structuredOutput": answer})
    (accepted / "native-envelope.json").write_bytes(envelope_raw)
    runtime = {"session_id_hash": a.sha(session.encode()), "requested_model": job["model"],
        "requested_reasoning_effort": "high", "reported_model": route["reported_model"], "request_id_hash": "request-one",
        "execution_contract": {"output_schema_hash": a.sha(v3.canonical(json.loads(schema)))},
        "subscription_receipt_hash": route["subscription_receipt_hash"], "command_identity": route["grok_command_identity"],
        "cli_version": route["grok_cli_version"]}
    native = {"state": "completed", "result": {"output": answer, "runtime": runtime,
        "request_hash": a.sha(v3.canonical({"prompt": prompt.decode()})), "output_hash": a.sha(v3.canonical(answer)),
        "native_envelope_artifact": {"sha256": a.sha(envelope_raw), "byte_length": len(envelope_raw)}}}
    started = {"no_resend": True, "logical_sample_id": rows[279]["logical_sample_id"], "session_id": session,
        "job_sha256": a.sha((results / "job.json").read_bytes()), "attempt": 1, "prompt_sha256": a.sha(prompt),
        "schema_sha256": a.sha(schema), "time": "2026-10-05T00:01:00+00:00", "state": "before_contact",
        "manifest_sha256": job["manifest_sha256"]}
    for name, value in (("condition.json", rows[279]), ("native-identity.json", {"session_id": session,
        "logical_sample_id": rows[279]["logical_sample_id"]}), ("attempt-started.json", started),
        ("native-result.json", native), ("response.json", answer), ("acceptance.json", {"accepted": True, "abstention": False})):
        v3.record(accepted / name, value)
    (accepted / "prompt.txt").write_bytes(prompt); (accepted / "schema.json").write_bytes(schema)

    def terminal(sample, row, state):
        v3.record(sample / "terminal.json", {"state": state, "accepted": state == "accepted", "no_resend": True,
            "logical_sample_id": row["logical_sample_id"], "manifest_sha256": job["manifest_sha256"],
            "job_sha256": started["job_sha256"], "retention_errors": [],
            "retained_artifacts": {p.name: {"sha256": a.sha(p.read_bytes()), "bytes": p.stat().st_size} for p in sample.iterdir()}})
    terminal(accepted, rows[279], "accepted")
    failed = v3.sample_path(results, rows[280]); failed.mkdir()
    v3.record(failed / "condition.json", rows[280])
    terminal(failed, rows[280], "unadmitted_no_resend")
    source_spec = {"endpoint": "grok", "collector_policy": a.V3_POLICY, "manifest_path": str(manifest_path),
        "manifest_sha256": a.sha(manifest_path.read_bytes()), "results_root": str(results), "job_sha256": started["job_sha256"]}
    _, records, identities, public = chain.replay_source(source_spec, base, base_raw, {}, None, loaded, None, 0)
    assert public["states"] == {"accepted": 1, "unadmitted_no_resend": 1}
    assert records[("grok", rows[279]["logical_sample_id"])]["accepted"]["response"] == answer
    assert records[("grok", rows[280]["logical_sample_id"])]["native_evidence_verified"] is False
    assert not (failed / "native-result.json").exists() and len(identities) == 2
    originals = {("grok", r["logical_sample_id"]): r for r in rows}
    joined = chain.merge([records], originals)
    assert len(joined) == 281 and sum(r["state"] == "not_collected" for r in joined.values()) == 279
    with pytest.raises(ValueError, match="Duplicate attempted"):
        chain.merge([records, records], originals)
    # A late-demoted completion retains its native request identity without an admitted answer.
    v3.record(failed / "native-result.json", {"state": "completed", "result": {
        "runtime": {"request_id_hash": "request-one"}, "output": {"excluded_response": "not projected"}}})
    (failed / "terminal.json").unlink(); terminal(failed, rows[280], "unadmitted_no_resend")
    with pytest.raises(ValueError, match="Duplicate native"):
        chain.replay_source(source_spec, base, base_raw, {}, None, loaded, None, 0)
    (failed / "native-result.json").unlink()
    v3.record(failed / "native-result.json", {"state": "completed", "result": {
        "runtime": {"request_id_hash": "request-two"}, "output": {"excluded_response": "not projected"}}})
    (failed / "terminal.json").unlink(); terminal(failed, rows[280], "unadmitted_no_resend")
    _, demoted, identities, _ = chain.replay_source(source_spec, base, base_raw, {}, None, loaded, None, 0)
    assert ("grok_request", "request-two") in identities
    assert demoted[("grok", rows[280]["logical_sample_id"])]["accepted"] is None
    v3.record(failed / "native-identity.json", {"session_id": session, "logical_sample_id": rows[280]["logical_sample_id"]})
    (failed / "terminal.json").unlink(); terminal(failed, rows[280], "unadmitted_no_resend")
    with pytest.raises(ValueError, match="Duplicate native"):
        chain.replay_source(source_spec, base, base_raw, {}, None, loaded, None, 0)
    (accepted / "native-envelope.json").write_bytes(b"changed")
    with pytest.raises(ValueError):
        chain.replay_source(source_spec, base, base_raw, {}, None, loaded, None, 0)


def test_true_outer_invocation_and_native_gap_block_before_label_decode(tmp_path, monkeypatch):
    chain, loaded = a.runtime()
    loaded["analysis"].load_labels = Mock(side_effect=AssertionError("Human targets must remain closed"))
    joined = {str(n): {"state": "accepted", "source_index": 0, "accepted": None} for n in range(a.DENOMINATOR)}
    life = tmp_path / "life"; life.mkdir()
    names = ("invocation", "outer_terminal", "run_started", "native_handle", "handle", "launcher")
    pins = {name: {"path": str(life / (name + ".json")), "sha256": "0" * 64} for name in names}
    config = {"sources": [{"endpoint": "grok", "lifecycle": pins}]}
    with pytest.raises(ValueError, match="Explicit"):
        a.release_labels(config, {}, joined, {}, {}, loaded, chain, tmp_path / "sealed")
    with pytest.raises(FileNotFoundError):
        a.release_labels(config, {}, joined, {}, {}, loaded, chain, tmp_path / "sealed", explicit_release=True)
    pins["outer_terminal"]["sha256"] = write(Path(pins["outer_terminal"]["path"]),
        {"exit_code": 3, "no_resend": True, "invocation_sha256": "0" * 64})
    with pytest.raises(FileNotFoundError):
        a.release_labels(config, {}, joined, {}, {}, loaded, chain, tmp_path / "sealed", explicit_release=True)
    joined["0"]["native_evidence_verified"] = False
    with pytest.raises(ValueError, match="Unverified completed native"):
        a.release_labels(config, {}, joined, {}, {}, loaded, chain, tmp_path / "sealed", explicit_release=True)
    joined["0"]["state"] = "not_collected"
    with pytest.raises(ValueError, match="every original planned"):
        a.release_labels(config, {}, joined, {}, {}, loaded, chain, tmp_path / "sealed", explicit_release=True)
    # Returned failures can contribute missing predictions; no successful native vote is invented.
    joined = {str(n): {"state": "definitely_not_contacted", "accepted": None, "native_evidence_verified": False,
        "terminal_evidence_verified": True, "source_index": n // 1554, "request": {
            "endpoint_ordinal": n % 1554 + 1, "logical_sample_id": f"{n:064x}"}} for n in range(a.DENOMINATOR)}
    config = {"sources": [{"endpoint": endpoint, "results_root": str(tmp_path / endpoint)} for endpoint in ("sol", "grok")]}
    beginning = a.timestamp("2026-10-05T00:00:00+00:00")
    ending = a.timestamp("2026-10-05T01:00:00+00:00")
    monkeypatch.setattr(a, "verify_lifecycle", lambda source: ({"endpoint": source["endpoint"]}, beginning, ending))
    release = Mock(return_value={"labels_opened": True})
    monkeypatch.setattr(chain, "release_labels", release)
    result = a.release_labels(config, {}, joined, {}, {}, loaded, chain, tmp_path / "sealed", explicit_release=True)
    assert result["own_lifecycles_verified"] is True and len(result["own_lifecycles"]) == 2
    release.assert_called_once()
    joined["0"]["terminal_evidence_verified"] = False
    with pytest.raises(ValueError, match="retained terminal"):
        a.release_labels(config, {}, joined, {}, {}, loaded, chain, tmp_path / "sealed", explicit_release=True)
    assert release.call_count == 1
    loaded["analysis"].load_labels.assert_not_called()
