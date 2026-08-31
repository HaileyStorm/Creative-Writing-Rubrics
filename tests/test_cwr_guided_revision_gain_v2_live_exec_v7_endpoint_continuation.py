from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from hbqrs.paths import book_root

ROOT = book_root() / "evaluation-results" / "cwr-guided-revision-gain-v2-live-exec-v7-endpoint-continuation"
_MODULE = None
_IMMUTABLE_CONTEXT = None
_VALIDATED_INPUTS = None

def mod():
    global _MODULE
    if _MODULE is not None:
        return _MODULE
    spec = importlib.util.spec_from_file_location("v7_endpoint", ROOT / "executor.py")
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec); spec.loader.exec_module(value); value._test_real_inputs = value._inputs; value._test_real_validated_inputs = value._validated_endpoint_inputs; _MODULE = value; return value

def _context(adapter):
    global _IMMUTABLE_CONTEXT
    if _IMMUTABLE_CONTEXT is None:
        _IMMUTABLE_CONTEXT = adapter._test_real_inputs()
    return _IMMUTABLE_CONTEXT

def _validated(adapter):
    global _VALIDATED_INPUTS
    if _VALIDATED_INPUTS is None:
        _VALIDATED_INPUTS = adapter._test_real_validated_inputs(_context(adapter)[1])
    return _VALIDATED_INPUTS

def _route_proof(adapter, pilot, queue_root, event_id):
    event = next(row for row in adapter.endpoint_schedule() if row["endpoint_event_id"] == event_id)
    model = adapter._event_model(event)
    route = {"adapter": "grok_exec" if model == "grok-4.6" else "codex_exec", "command": ["fixture"], "model": model, "reasoning_effort": "high", "timeout_seconds": 1,
        "grok_command": ["fixture"], "reported_model": "grok-4.6-build", "grok_command_identity": {"fixture": True}, "grok_cli_version": "fixture", "subscription_receipt_hash": "receipt",
        "codex_command": ["fixture"], "codex_command_identity": {"fixture": True}, "codex_cli_version": "fixture", "auth_status_command": ["fixture"], "auth_status_identity": {"fixture": True}, "auth_receipt_hash": "receipt",
        "cli_version_command": ["fixture"], "cli_version_identity": {"fixture": True}, "nonvisual_max_turns": 1}
    proof = {"format_version": 1, "route_receipt_sha256": "a" * 64, "expected_adapter_runtime_identity_sha256": "b" * 64, "route_name": "fixture", "queue_root": str(queue_root), "model": model, "adapter": route["adapter"], "provider": "fixture", "destination": "fixture", "reasoning": "high", "tools_enabled": False, "payload_classification": "public_repo", "zero_charge": True, "account_class": "subscription", "validated_at": "fixture", "study_id": adapter.STUDY_ID, "phase": "blind_endpoint_judgment", "event_id": event_id}
    return SimpleNamespace(root=Path(queue_root), _load_json_artifact=lambda _key: {}), route, proof

def _output(adapter, args, kwargs):
    model = args[0][args[0].index("--model") + 1]
    prompt = json.loads(kwargs["input"])["prompt"]
    identity = adapter.sha(prompt.encode())
    response = {"overall": 4, "rationale": "fixture endpoint rationale"}
    if model == "grok-4.6":
        runtime = {"adapter_version": 1, "requested_model": "grok-4.6", "reported_model": "grok-4.6-build", "requested_reasoning_effort": "high", "reasoning_attested": False, "reasoning_attestation": "requested_only", "identity_evidence": "requested_only", "cli_version": "fixture", "session_id_hash": identity, "request_id_hash": adapter.sha((identity + "request").encode()), "observed_turns": 1, "envelope_hash": "3" * 64, "command_identity": {"fixture": True}, "command_identity_hash": "4" * 64, "subscription_receipt_hash": "a" * 64, "execution_policy": {}, "usage_telemetry": {}, "nonvisual_max_turns": 1}
    else:
        runtime = {"adapter_version": 1, "requested_model": "gpt-5.6-sol", "requested_reasoning_effort": "high", "identity_evidence": "requested_only", "cli_version": "fixture", "events_hash": "1" * 64, "event_projection": {"thread_id": "fixture-thread-" + identity}, "raw_output_hash": "2" * 64, "command_identity": {"fixture": True}, "auth_receipt_hash": "a" * 64, "command_identity_hash": "b" * 64}
    envelope = {"control": {"version": 1, "state": "completed"}, "result": {"schema_version": 1, "request_hash": adapter.sha(adapter.canonical({"prompt": prompt})), "output": response, "output_hash": adapter.sha(adapter.canonical(response)), "runtime": runtime}}
    return SimpleNamespace(returncode=0, stdout=json.dumps(envelope, sort_keys=True).encode("ascii") + b"\n")

def _invalid_output(adapter, args, kwargs, field, value):
    completed = _output(adapter, args, kwargs); envelope = json.loads(completed.stdout)
    if field == "thread_id":
        envelope["result"]["runtime"]["event_projection"]["thread_id"] = value
    else:
        envelope["result"]["runtime"][field] = value
    return SimpleNamespace(returncode=0, stdout=json.dumps(envelope, sort_keys=True).encode("ascii") + b"\n")

def _prepared(adapter, tmp_path, monkeypatch):
    monkeypatch.setattr(adapter, "_inputs", lambda: _context(adapter))
    monkeypatch.setattr(adapter, "_validated_endpoint_inputs", lambda _pilot: _validated(adapter))
    monkeypatch.setattr(adapter, "_route_proof", lambda **kwargs: _route_proof(adapter, **kwargs))
    run = tmp_path / "run"; prepared = adapter.prepare_all(run_root=run, acknowledgement_sha256=adapter.ACK, queue_root=tmp_path / "queue")
    assert len(prepared) == 40 and all(row["provider_calls_made"] == 0 for row in prepared)
    return run, prepared

def test_contract_geometry_and_provider_free_prepare(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = mod(); assert adapter.contract()["geometry"] == {"endpoints": 40, "grok": 20, "sol": 20, "grok_max_concurrency": 10, "sol_max_concurrency": 2}
    run, _rows = _prepared(adapter, tmp_path, monkeypatch)
    assert (run / "prepared-index.json").is_file()

def test_one_shot_fake_native_execution_and_route_expiry_replay(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = mod(); run, rows = _prepared(adapter, tmp_path, monkeypatch)
    monkeypatch.setattr(adapter, "_SUBPROCESS_RUN", lambda *args, **kwargs: _output(adapter, args, kwargs))
    selected = [next(row["event_id"] for row in rows if row["provider_model"] == model) for model in ("grok-4.6", "gpt-5.6-sol")]
    results = [adapter.execute_one(run_root=run, event_id=event_id, allow_remote=True, queue_root=tmp_path / "queue") for event_id in selected]
    assert [row["state"] for row in results] == ["settled", "settled"]
    monkeypatch.setattr(adapter, "_route_proof", lambda **kwargs: (_ for _ in ()).throw(RuntimeError("route expired")))
    for event_id in selected:
        with pytest.raises(ValueError, match="one-shot"):
            adapter.execute_one(run_root=run, event_id=event_id, allow_remote=True, queue_root=tmp_path / "queue")
    for event_id in selected:
        root = adapter._cell_root(run, event_id)
        receipt, event = adapter._replay_receipt(run, root / "verified-receipt.json")
        assert receipt["event_id"] == event["endpoint_event_id"]

def test_full_fake_wave_projects_separate_endpoint_identities_and_rejects_tamper(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = mod(); run, rows = _prepared(adapter, tmp_path, monkeypatch)
    monkeypatch.setattr(adapter, "_SUBPROCESS_RUN", lambda *args, **kwargs: _output(adapter, args, kwargs))
    results = adapter.execute_endpoint_wave(run_root=run, event_ids=[row["event_id"] for row in rows], allow_remote=True, queue_root=tmp_path / "queue")
    assert len(results) == 40 and all(row["state"] == "settled" for row in results)
    receipts = [adapter._cell_root(run, row["event_id"]) / "verified-receipt.json" for row in rows]
    projection = adapter.project_independent_metrics(receipt_paths=receipts)
    assert projection["endpoint_results_are_not_pooled"] is True
    assert {row["judge_route_id"]: row["endpoint_count"] for row in projection["endpoint_evidence"]} == {"grok-4.6-high": 20, "gpt-5.6-sol-high": 20}
    assert len(projection["primary_guided_minus_control"]) == 16 and len(projection["arm_minus_baseline"]) == 32
    raw = receipts[0].read_bytes(); forged = json.loads(raw); forged["response"]["overall"] = 99; receipts[0].write_bytes(adapter.canonical(forged) + b"\n")
    with pytest.raises(ValueError): adapter.project_independent_metrics(receipt_paths=receipts)
    receipts[0].write_bytes(raw)
    root = receipts[0].parent; proof = root / "governed-route-proof.json"; proof_raw = proof.read_bytes(); forged_proof = json.loads(proof_raw); forged_proof["route_name"] = "forged"; proof.write_bytes(adapter.canonical(forged_proof) + b"\n")
    with pytest.raises(ValueError, match="replay admission"):
        adapter.project_independent_metrics(receipt_paths=receipts)
    proof.write_bytes(proof_raw)
    binding = root / "adapter-stdout-binding.json"; binding_raw = binding.read_bytes(); forged_binding = json.loads(binding_raw); forged_binding["study_id"] = "forged"; binding.write_bytes(adapter.canonical(forged_binding) + b"\n")
    with pytest.raises(ValueError, match="raw adapter"):
        adapter.project_independent_metrics(receipt_paths=receipts)
    binding.write_bytes(binding_raw)
    with pytest.raises(ValueError, match="forty"): adapter.project_independent_metrics(receipt_paths=receipts[:-1])

def test_rejects_prelaunch_tamper_before_process(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = mod(); run, rows = _prepared(adapter, tmp_path, monkeypatch); event_id = rows[0]["event_id"]; root = adapter._cell_root(run, event_id)
    (root / "extra.txt").write_text("no", encoding="utf-8"); launches=[]; monkeypatch.setattr(adapter, "_SUBPROCESS_RUN", lambda *args, **kwargs: launches.append((args, kwargs)))
    with pytest.raises(ValueError, match="inventory"):
        adapter.execute_one(run_root=run, event_id=event_id, allow_remote=True, queue_root=tmp_path / "queue")
    assert launches == []

def test_rejects_prelaunch_schema_tamper_and_overlapping_queue(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = mod(); run, rows = _prepared(adapter, tmp_path, monkeypatch); event_id = rows[0]["event_id"]; root = adapter._cell_root(run, event_id)
    raw = (root / "adapter-schema-binding.json").read_bytes(); forged = json.loads(raw); forged["adapter_output_schema"]["type"] = "array"; (root / "adapter-schema-binding.json").write_bytes(adapter.canonical(forged) + b"\n")
    with pytest.raises(ValueError, match="immutable input"):
        adapter.execute_one(run_root=run, event_id=event_id, allow_remote=True, queue_root=tmp_path / "queue")
    (root / "adapter-schema-binding.json").write_bytes(raw)
    with pytest.raises(ValueError, match="overlap"):
        adapter.prepare_all(run_root=tmp_path / "other", acknowledgement_sha256=adapter.ACK, queue_root=tmp_path / "other")
    with pytest.raises(ValueError, match="source"):
        adapter._safe_run_root(adapter.ROOT / "v7-unsafe-output", fresh=True)

def test_exact_admission_and_prepared_index_reject_tamper(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = mod(); run, rows = _prepared(adapter, tmp_path, monkeypatch); event_id = rows[0]["event_id"]; root = adapter._cell_root(run, event_id)
    admission_path = root / "admission.json"; original = admission_path.read_bytes(); forged = json.loads(original); forged["tools_enabled"] = True; forged["provider_calls_made"] = 9; forged["no_resend"] = False; admission_path.write_bytes(adapter.canonical(forged) + b"\n")
    with pytest.raises(ValueError):
        adapter.execute_one(run_root=run, event_id=event_id, allow_remote=True, queue_root=tmp_path / "queue")
    admission_path.write_bytes(original)
    index_path = run / "prepared-index.json"; index_original = index_path.read_bytes(); index = json.loads(index_original); index["study_id"] = "forged"; index_path.write_bytes(adapter.canonical(index) + b"\n")
    with pytest.raises(ValueError, match="prepared-index"):
        adapter.execute_one(run_root=run, event_id=event_id, allow_remote=True, queue_root=tmp_path / "queue")
    index_path.write_bytes(index_original)
    monkeypatch.setattr(adapter, "_SUBPROCESS_RUN", lambda *args, **kwargs: _output(adapter, args, kwargs))
    assert adapter.execute_one(run_root=run, event_id=event_id, allow_remote=True, queue_root=tmp_path / "queue")["state"] == "settled"
    forged = json.loads(original); forged["tools_enabled"] = True; forged["provider_calls_made"] = 9; forged["no_resend"] = False; admission_path.write_bytes(adapter.canonical(forged) + b"\n")
    with pytest.raises(ValueError):
        adapter._replay_receipt(run, root / "verified-receipt.json")

@pytest.mark.parametrize(("model", "field", "value"), [
    ("grok-4.6", "adapter_version", 99),
    ("grok-4.6", "reasoning_attested", True),
    ("grok-4.6", "identity_evidence", "fabricated"),
    ("gpt-5.6-sol", "adapter_version", 99),
    ("gpt-5.6-sol", "events_hash", "not-a-hash"),
    ("gpt-5.6-sol", "thread_id", ""),
])
def test_rejects_invalid_native_runtime_metadata(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, model: str, field: str, value: object) -> None:
    adapter = mod(); run, rows = _prepared(adapter, tmp_path, monkeypatch); event_id = next(row["event_id"] for row in rows if row["provider_model"] == model)
    monkeypatch.setattr(adapter, "_SUBPROCESS_RUN", lambda *args, **kwargs: _invalid_output(adapter, args, kwargs, field, value))
    result = adapter.execute_one(run_root=run, event_id=event_id, allow_remote=True, queue_root=tmp_path / "queue")
    assert result["state"] == "terminal_postlaunch_reconcile_required"
    root = adapter._cell_root(run, event_id)
    assert not (root / "verified-receipt.json").exists()
