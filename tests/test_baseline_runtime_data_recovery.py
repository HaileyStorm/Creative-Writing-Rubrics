"""No-contact recovery must preserve source evidence and native uniqueness."""
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

SOURCE = Path(__file__).resolve().parents[1] / "evaluation-results/hbq-human-alignment-dryad-full-hbq-analysis-v1/baseline_runtime_data_recovery.py"
spec = importlib.util.spec_from_file_location("data_recovery_test", SOURCE)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def canon(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def put(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canon(value))
    return m.sha(path.read_bytes())


@pytest.fixture
def fixture(tmp_path, monkeypatch):
    ids = [f"q{x}" for x in range(8)]
    verdicts = [{"question_id": item} for item in ids]
    identity = {"request_id_hash": "a" * 64, "session_id_hash": "b" * 64, "observed_turns": 1}
    envelope = b"retained original native envelope"
    result = {"output": {"verdicts": verdicts}, "native_envelope_artifact": {"sha256": m.sha(envelope), "byte_length": len(envelope)}}
    route = {"model": "grok-4.6", "reported_model": "grok-4.6-build"}
    manifest_raw = b"original manifest"
    manifest_sha = m.sha(manifest_raw)
    review_path = tmp_path / "review.json"
    review = {"candidate_manifest_sha256": "candidate", "controller_sha256": m.PARTIAL_SHA,
              "manifest_sha256": manifest_sha, "first_ordinal": 279, "operational_wave_cap": 1,
              "decision": "approved_dryad_grok_standing_v6_partial_successor_wave", "route": route,
              "route_sha256": m.sha(canon(route)), "gate_sha256": "gate"}
    review_sha = put(review_path, review)
    path = lambda root, ordinal, name: root / "attempts" / str(ordinal) / name
    start = {"ordinal": 279, "wave": {"ordinals": [279], "size": 1, "slot": 0, "start": 279},
             "candidate_manifest_sha256": "candidate", "route_sha256": review["route_sha256"], "gate_sha256": "gate",
             "prompt_sha256": "prompt", "schema_sha256": "schema", "question_ids": ids, "source_sha256": "story"}
    start_sha = put(path(tmp_path, 279, "attempt-start.json"), start)
    terminal = {"ordinal": 279, "state": "ambiguous", "error_type": "ValueError", "error_source": "dispatch_standing_v6_wave:cell",
                "candidate_result": result, "broker_outcome": {"state": "completed", "result": result},
                "attempt_start_sha256": start_sha, "native_identity": identity, "session_id": "session"}
    terminal_path = path(tmp_path, 279, "terminal.json")
    terminal_sha = put(terminal_path, terminal)
    put(tmp_path / "controller-authorizations/request-0279.json", {
        "candidate_manifest_sha256": "candidate", "gate_sha256": "gate", "manifest_sha256": manifest_sha,
        "operational_wave_cap": 1, "ordinal": 279, "review_sha256": review_sha, "route_sha256": review["route_sha256"]})
    schema_path = tmp_path / "schema.json"
    put(schema_path, {})
    calls = []
    runtime = SimpleNamespace(verify=lambda: calls.append("verify"), provenance={"data": "historical"}, runner=SimpleNamespace(
        EVIDENCE_NORMALIZATION_POLICY="original", _normalize_batch=lambda *args, **kwargs: verdicts))
    adapter = SimpleNamespace(_parse_grok_envelope=lambda *args, **kwargs: (result["output"], identity, {}))
    monkeypatch.setitem(sys.modules, "recovery_fixture.adapters.grok_exec", adapter)
    context = SimpleNamespace(
        runtime=runtime, root=tmp_path, partial=SimpleNamespace(_attempt_path=path, _identity_is_new=lambda value, old:
            all(value["request_id_hash"] != item["request_id_hash"] and value["session_id_hash"] != item["session_id_hash"] for item in old)),
        manifest={"candidate": {"manifest_sha256": "candidate"}}, manifest_raw=manifest_raw,
        requests={279: {"pass_id": "p", "question_ids": ids, "prompt_sha256": "prompt", "schema_sha256": "schema"}},
        passes={"p": {}}, plan_root=tmp_path,
        parent=SimpleNamespace(_source_for_pass=lambda *args: {"sha256": "story", "opaque_story_id": "story-id", "story_text": "text"},
                               _request_payload=lambda *args: ("prompt", schema_path, ids)),
        base=SimpleNamespace(_sha=m.sha, _canon=canon, _native_identity=lambda value, label: value),
        broker=SimpleNamespace(read_grok_native_envelope=lambda *args: envelope,
            _parse_grok_exec_envelope=lambda *args, **kwargs: SimpleNamespace(state="completed", result=result)),
        candidate=SimpleNamespace(__package__="recovery_fixture"),
        identities=[{"request_id_hash": f"{index:064x}", "session_id_hash": f"{index + 1000:064x}"} for index in range(276)],
        snapshot_manifest_sha256="snapshot", loader_sha256="loader", prefix_adapter_sha256="prefix")
    return context, terminal_path, terminal_sha, review_path, review_sha, calls


def recover(fixture):
    context, _, terminal_sha, review_path, review_sha, _ = fixture
    return m.recover_279(context=context, expected_terminal_sha256=terminal_sha,
                         review_path=review_path, expected_review_sha256=review_sha)


def test_retained_native_recovery_is_separate_and_zero_contact(fixture):
    raw = fixture[1].read_bytes()
    result = recover(fixture)
    assert len(result["verdicts"]) == 8
    assert result["state"] == "verified_pending_independent_adoption"
    assert result["original_terminal_state"] == "ambiguous"
    assert result["provider_calls_made"] == 0
    assert fixture[1].read_bytes() == raw
    assert fixture[-1] == ["verify", "verify"]


@pytest.mark.parametrize("field", ["request_id_hash", "session_id_hash"])
def test_duplicate_native_component_rejected(fixture, field):
    value = {"request_id_hash": "x" * 64, "session_id_hash": "y" * 64}
    value[field] = {"request_id_hash": "a" * 64, "session_id_hash": "b" * 64}[field]
    fixture[0].identities[0] = value
    with pytest.raises(ValueError, match="native result or identity"):
        recover(fixture)


def test_terminal_drift_rejected(fixture):
    fixture[1].write_bytes(fixture[1].read_bytes() + b" ")
    with pytest.raises(ValueError, match="evidence pin"):
        recover(fixture)


def test_provider_ambiguous_outcome_never_promoted(fixture):
    value = json.loads(fixture[1].read_bytes())
    value["broker_outcome"]["state"] = "ambiguous"
    digest = put(fixture[1], value)
    context, path, _, review_path, review_sha, calls = fixture
    with pytest.raises(ValueError, match="not recoverable"):
        recover((context, path, digest, review_path, review_sha, calls))
