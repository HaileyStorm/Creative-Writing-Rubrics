from __future__ import annotations

import asyncio
import base64
import hashlib
import importlib.util
import json
import shutil
import sys
import threading
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation-results" / "hbq-human-alignment-optimizer-v7-desc16-referent-evidence-grok-exec-v1"
FREEZE = Path(r"C:\Users\Haile\Documents\cwr-hanna-desc16-referent-evidence-freeze-commit-pending-20260901a")
ACK = "2fb371ff82b37fe22d238a223fc030ad7a7bb9a10b672719da081470d25dbe78"


def load():
    spec = importlib.util.spec_from_file_location("_desc16_referent_evidence_grok_exec_test", PACKAGE / "executor.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(spec.name, None)
    return module


def route_provider(counter: dict[str, int] | None = None):
    route = {"name": "grok-build-grok-4.6", "model": "grok-4.6", "reported_model": "grok-4.6-build", "adapter": "grok_exec", "provider": "xai_grok_build", "destination": "xai_grok_build_subscription", "account_class": "subscription", "identity_evidence": "requested_only", "zero_charge": True, "armed": True, "health": "healthy", "trusted": True, "reasoning_effort": "high", "grok_command": ["fixture"], "grok_command_identity": {"version": 1, "artifacts": []}, "cli_version_identity": {"version": 1, "artifacts": []}, "grok_cli_version": "grok fixture", "subscription_receipt_hash": "2" * 64, "cost_evidence": {"allowance_state": "available", "checked_at": "2026-09-01T00:00:00+00:00", "evidence_hash": "1" * 64, "expires_at": "2026-09-01T01:00:00+00:00", "kind": "subscription_included", "version": 1}, "allowed_payload_classes": ["public_repo", "public_synthetic"], "timeout_seconds": 1.0}
    evidence = {"route_name": route["name"], "route_sha256": hashlib.sha256(json.dumps(route, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode() + b"\n").hexdigest(), "cost_evidence_hash": route["cost_evidence"]["evidence_hash"], "subscription_receipt_hash": route["subscription_receipt_hash"], "grok_cli_version": route["grok_cli_version"], "cli_version_identity_sha256": hashlib.sha256(json.dumps(route["cli_version_identity"], ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode() + b"\n").hexdigest(), "grok_command_identity_sha256": hashlib.sha256(json.dumps(route["grok_command_identity"], ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode() + b"\n").hexdigest(), "registry_sha256": "3" * 64}
    lock = threading.Lock()
    def provider(_queue: Path):
        if counter is not None:
            with lock:
                counter["active"] = counter.get("active", 0) + 1
                counter["maximum"] = max(counter.get("maximum", 0), counter["active"])
            time.sleep(0.003)
            with lock:
                counter["active"] -= 1
                counter["calls"] = counter.get("calls", 0) + 1
        return route, evidence
    return provider


def runner(value, *, postlaunch_failure: bool = False, concurrency: dict[str, int] | None = None):
    calls = {"count": 0}
    lock = threading.Lock()
    def run(*, prompt: bytes, schema_path: Path, output_dir: Path, route, before_contact):
        with lock:
            calls["count"] += 1
        if concurrency is not None:
            with lock:
                concurrency["active"] = concurrency.get("active", 0) + 1
                concurrency["maximum"] = max(concurrency.get("maximum", 0), concurrency["active"])
        try:
            schema = json.loads(schema_path.read_bytes())
            assert schema["required"] == ["scores", "evidence", "coverage"]
            responses = output_dir / "responses"
            responses.mkdir()
            (responses / "batch-0001.attempt-0001.prompt.txt").write_bytes(prompt)
            before_contact()
            if postlaunch_failure:
                raise RuntimeError("postlaunch")
            token = hashlib.sha256(prompt + str(output_dir).encode()).hexdigest()
            scores = {key: 3.0 for key in ("Relevance", "Coherence", "Empathy", "Surprise", "Engagement", "Complexity")}
            response = value.canonical({"requestId": "request-" + token, "sessionId": "session-" + token, "modelUsage": {"grok-4.6-build": {}}, "stopReason": "end_turn", "num_turns": 1, "structuredOutput": {"scores": scores, "evidence": {key: "fixture" for key in scores}, "coverage": {key: True for key in scores}}})
            (responses / "batch-0001.attempt-0001.grok.envelope.json").write_bytes(response)
            return {"native_request_bytes": json.dumps({"prompt": prompt.decode()}, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(), "native_response_bytes": response, "identity": {"provider": "xai", "requested_model": "grok-4.6", "reported_model": "grok-4.6-build", "request_id": "request-" + token, "session_id": "session-" + token, "native_endpoint_contact_cardinality": "unproven", "tools_enabled": False}, "effective_settings": {"route_name": route["name"], "adapter": "grok_exec", "requested_model": "grok-4.6", "reported_model": "grok-4.6-build", "requested_reasoning_effort": "high", "tools_enabled": False, "web_search_enabled": False, "subagents_enabled": False, "tool_free_argv": ["--max-turns", "1", "--no-leader", "--no-subagents", "--disable-web-search", "--no-plan", "--tools", "", "--permission-mode", "dontAsk", "--sandbox", "read-only", "--verbatim"], "system_prompt_override": "Act as an isolated structured-output evaluator. Do not use memory, tools, web, plans, or subagents.", "sampler": {"batch_number": 1, "attempt_number": 1, "timeout_seconds": 1.0, "nonvisual_max_turns": 1}, "runner_prompt_artifact_sha256": value.sha256(prompt), "reasoning_attested": False}}
        finally:
            if concurrency is not None:
                with lock:
                    concurrency["active"] -= 1
    return run, calls


def common(tmp_path: Path):
    return {"output_root": tmp_path / "output", "freeze_root": FREEZE, "queue_root": tmp_path / "queue", "authorization_acknowledgement_sha256": ACK, "route_provider": route_provider()}


def test_freeze_is_exact_and_contract_is_fully_bound(monkeypatch: pytest.MonkeyPatch):
    value = load()
    schedule = value.frozen_schedule(FREEZE)
    assert schedule["geometry"] == {"candidates": 4, "development_groups": 7, "development_items": 13, "grok_cells": 52, "sol_cells": 0, "confirmation_cells": 0}
    assert len(schedule["cells"]) == 52
    assert all(base64.b64decode(row["payload_base64"], validate=True) for row in schedule["cells"])
    original_stable = value.stable
    monkeypatch.setattr(value, "stable", lambda path: b"drift" if Path(path) == value.FREEZE_PACKAGE / "study.py" else original_stable(path))
    with pytest.raises(ValueError, match="pinned freeze package"):
        value.frozen_schedule(FREEZE)
    monkeypatch.setattr(value, "stable", original_stable)
    tampered = value.contract()
    tampered["study_id"] += "-tampered"
    monkeypatch.setattr(value, "contract", lambda: tampered)
    with pytest.raises(ValueError, match="contract"):
        value.frozen_schedule(FREEZE)


def test_prepare_writes_exact_fifty_two_payloads_without_contact(tmp_path: Path):
    value, args = load(), common(tmp_path)
    prepared = value.prepare_all(**args)
    assert prepared["logical_cells"] == len(prepared["prepared_cells"]) == 52
    assert prepared["effective_candidates"] == 4
    assert prepared["provider_calls_made"] == prepared["process_launches"] == 0
    schedule = value.frozen_schedule(FREEZE)
    persisted = json.loads((args["output_root"] / "schedule.json").read_bytes())
    assert persisted == schedule
    assert all((args["output_root"] / row["cell_id"] / "outbound-payload.json").read_bytes() == base64.b64decode(row["payload_base64"], validate=True) for row in schedule["cells"])
    source = (PACKAGE / "executor.py").read_text(encoding="utf-8").lower()
    assert "import dspy" not in source and "import optuna" not in source


def test_self_consistent_paid_route_evidence_is_rejected():
    value = load()
    route, evidence = route_provider()(Path("."))
    forged_route = dict(route)
    forged_route["account_class"] = "paid"
    forged_route["cost_evidence"] = {**route["cost_evidence"], "kind": "paid", "evidence_hash": "4" * 64}
    forged_evidence = dict(evidence)
    forged_evidence["route_sha256"] = value.sha256(forged_route)
    forged_evidence["cost_evidence_hash"] = forged_route["cost_evidence"]["evidence_hash"]
    with pytest.raises(ValueError, match="route evidence"):
        value._validate_route_evidence(forged_route, forged_evidence)
    malformed_route = dict(route)
    malformed_route["zero_charge"] = 1
    malformed_evidence = dict(evidence)
    malformed_evidence["route_sha256"] = value.sha256(malformed_route)
    with pytest.raises(ValueError, match="route evidence"):
        value._validate_route_evidence(malformed_route, malformed_evidence)


def test_wave_is_one_route_load_at_most_ten_lanes_and_collector_replays(tmp_path: Path):
    value, args = load(), common(tmp_path)
    value.prepare_all(**args)
    route_counter: dict[str, int] = {}
    concurrency: dict[str, int] = {}
    fake, calls = runner(value, concurrency=concurrency)
    rows = asyncio.run(value.execute_wave(**{**args, "route_provider": route_provider(route_counter)}, allow_remote=True, runner=fake))
    assert len(rows) == calls["count"] == 52
    assert 1 <= concurrency["maximum"] <= 10
    assert route_counter["maximum"] == route_counter["calls"] == 1
    collector = tmp_path / "collector.json"
    claim_path = args["output_root"] / ".claims" / rows[0]["cell_id"] / "claim.json"
    claim_bytes = claim_path.read_bytes()
    forged_claim = json.loads(claim_bytes)
    forged_claim["study_id"] = "forged"
    claim_path.write_bytes(value.canonical(forged_claim))
    with pytest.raises(ValueError, match="claim binding"):
        value.finalize_collector(output_root=args["output_root"], freeze_root=FREEZE, collector_output=collector, authorization_acknowledgement_sha256=ACK)
    claim_path.write_bytes(claim_bytes)
    claim_path.write_bytes(b"{")
    with pytest.raises(ValueError, match="invalid claim"):
        value.finalize_collector(output_root=args["output_root"], freeze_root=FREEZE, collector_output=collector, authorization_acknowledgement_sha256=ACK)
    claim_path.write_bytes(claim_bytes)
    missing_claim_key = json.loads(claim_bytes)
    del missing_claim_key["kind"]
    claim_path.write_bytes(value.canonical(missing_claim_key))
    with pytest.raises(ValueError, match="claim binding"):
        value.finalize_collector(output_root=args["output_root"], freeze_root=FREEZE, collector_output=collector, authorization_acknowledgement_sha256=ACK)
    claim_path.write_bytes(claim_bytes)
    extra_claim_key = json.loads(claim_bytes)
    extra_claim_key["extra"] = True
    claim_path.write_bytes(value.canonical(extra_claim_key))
    with pytest.raises(ValueError, match="claim binding"):
        value.finalize_collector(output_root=args["output_root"], freeze_root=FREEZE, collector_output=collector, authorization_acknowledgement_sha256=ACK)
    claim_path.write_bytes(claim_bytes)
    extra_claim = args["output_root"] / ".claims" / rows[0]["cell_id"] / "unexpected.json"
    extra_claim.write_bytes(value.canonical({"unexpected": True}))
    with pytest.raises(ValueError, match="claim artifact"):
        value.finalize_collector(output_root=args["output_root"], freeze_root=FREEZE, collector_output=collector, authorization_acknowledgement_sha256=ACK)
    extra_claim.unlink()
    finalized = value.finalize_collector(output_root=args["output_root"], freeze_root=FREEZE, collector_output=collector, authorization_acknowledgement_sha256=ACK)
    assert finalized["cells"] == finalized["process_launches"] == 52
    assert finalized["provider_calls_made"] is None
    assert finalized["native_endpoint_contact_cardinality"] == "unproven"
    replay = value.replay_collector(output_root=args["output_root"], freeze_root=FREEZE, collector_path=collector)
    assert replay["equal_group_projection_ready"] is True
    assert replay["authority"]["selection"] == "none"
    assert replay["process_launches"] == 52 and replay["provider_calls_made"] is None
    assert replay["native_endpoint_contact_cardinality"] == "unproven"
    forged_evidence = json.loads(collector.read_bytes())
    forged_evidence["route_evidence"] = {"kind": "forged"}
    forged_evidence_path = tmp_path / "forged-evidence-collector.json"
    forged_evidence_path.write_bytes(value.canonical(forged_evidence))
    with pytest.raises(ValueError, match="route"):
        value.replay_collector(output_root=args["output_root"], freeze_root=FREEZE, collector_path=forged_evidence_path)
    forged_counter = json.loads(collector.read_bytes())
    forged_counter["provider_calls_made"] = 999
    forged_counter_path = tmp_path / "forged-counter-collector.json"
    forged_counter_path.write_bytes(value.canonical(forged_counter))
    with pytest.raises(ValueError, match="collector drifted"):
        value.replay_collector(output_root=args["output_root"], freeze_root=FREEZE, collector_path=forged_counter_path)
    forged_ack = json.loads(collector.read_bytes())
    forged_ack["authorization_acknowledgement_sha256"] = "0" * 64
    forged_ack_path = tmp_path / "forged-acknowledgement-collector.json"
    forged_ack_path.write_bytes(value.canonical(forged_ack))
    with pytest.raises(ValueError, match="acknowledgement"):
        value.replay_collector(output_root=args["output_root"], freeze_root=FREEZE, collector_path=forged_ack_path)
    forged_cell = json.loads(collector.read_bytes())
    forged_cell["cells"][0]["extra"] = True
    forged_cell_path = tmp_path / "forged-cell-collector.json"
    forged_cell_path.write_bytes(value.canonical(forged_cell))
    with pytest.raises(ValueError, match="collector cell"):
        value.replay_collector(output_root=args["output_root"], freeze_root=FREEZE, collector_path=forged_cell_path)
    forged_receipt = json.loads(collector.read_bytes())
    receipt_cell = forged_receipt["cells"][0]
    forged_identity = dict(receipt_cell["identity"])
    forged_identity["request_id"] = "forged-request"
    forged_identity["session_id"] = "forged-session"
    forged_response = json.loads(base64.b64decode(receipt_cell["native_response_base64"], validate=True))
    forged_response["requestId"] = forged_identity["request_id"]
    forged_response["sessionId"] = forged_identity["session_id"]
    forged_response_bytes = value.canonical(forged_response)
    receipt_cell["identity"] = forged_identity
    receipt_cell["native_response_base64"] = base64.b64encode(forged_response_bytes).decode("ascii")
    receipt_cell["native_response_sha256"] = value.sha256(forged_response_bytes)
    forged_receipt_path = tmp_path / "forged-receipt-collector.json"
    forged_receipt_path.write_bytes(value.canonical(forged_receipt))
    with pytest.raises(ValueError, match="native receipt differs"):
        value.replay_collector(output_root=args["output_root"], freeze_root=FREEZE, collector_path=forged_receipt_path)


def test_wave_waits_for_all_threads_before_unbinding_runtime(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    value, args = load(), common(tmp_path)
    value.prepare_all(**args)
    entered, release, completed = threading.Event(), threading.Event(), threading.Event()
    cells = value.frozen_schedule(FREEZE)["cells"]
    first, second = cells[0]["cell_id"], cells[1]["cell_id"]

    def failing_bound(*, cell_id: str, **_kwargs):
        if cell_id == first:
            entered.set()
            assert release.wait(1)
            time.sleep(0.05)
            completed.set()
            return {"cell_id": cell_id, "state": "done"}
        if cell_id == second:
            assert entered.wait(1)
            release.set()
            raise RuntimeError("fixture concurrent failure")
        return {"cell_id": cell_id, "state": "done"}

    monkeypatch.setattr(value, "_execute_bound", failing_bound)
    with pytest.raises(RuntimeError, match="fixture concurrent failure"):
        asyncio.run(value.execute_wave(**args, allow_remote=True))
    assert completed.is_set()


def test_postlaunch_ambiguity_is_terminal_and_staged_prompt_must_match(tmp_path: Path):
    value, args = load(), common(tmp_path)
    prepared = value.prepare_all(**args)
    fake, calls = runner(value, postlaunch_failure=True)
    cell = prepared["prepared_cells"][0]
    first = value.execute_one(**args, cell_id=cell, allow_remote=True, runner=fake)
    assert first["kind"] == "reconcile_required_after_process_launch" and calls["count"] == 1
    second = value.execute_one(**args, cell_id=cell, allow_remote=True, runner=fake)
    assert second["state"] == "terminal" and calls["count"] == 1

    clean = common(tmp_path / "mismatch")
    prepared = value.prepare_all(**clean)
    def mismatch(*, output_dir: Path, before_contact, **_kwargs):
        responses = output_dir / "responses"
        responses.mkdir()
        (responses / "batch-0001.attempt-0001.prompt.txt").write_bytes(b"mismatch")
        before_contact()
    result = value.execute_one(**clean, cell_id=prepared["prepared_cells"][0], allow_remote=True, runner=mismatch)
    assert result["kind"] == "definitely_not_contacted"
    assert result["provider_calls_made"] == result["process_launches"] == 0


def test_unexpected_response_artifact_is_rejected_before_contact(tmp_path: Path):
    value, args = load(), common(tmp_path)
    prepared = value.prepare_all(**args)

    def unexpected(*, output_dir: Path, before_contact, **_kwargs):
        responses = output_dir / "responses"
        responses.mkdir()
        (responses / "unexpected.json").write_bytes(value.canonical({"unexpected": True}))
        before_contact()

    result = value.execute_one(
        **args,
        cell_id=prepared["prepared_cells"][0],
        allow_remote=True,
        runner=unexpected,
    )
    assert result["kind"] == "definitely_not_contacted"
    assert result["provider_calls_made"] == result["process_launches"] == 0


def test_freeze_mutation_is_rejected_before_prepare(tmp_path: Path):
    value = load()
    copied = tmp_path / "freeze"
    shutil.copytree(FREEZE, copied)
    schedule = json.loads((copied / "schedule.json").read_bytes())
    schedule["cells"][0]["candidate_id"] += "-tampered"
    (copied / "schedule.json").write_bytes(value.canonical(schedule))
    with pytest.raises(ValueError, match="file binding"):
        value.frozen_schedule(copied)
