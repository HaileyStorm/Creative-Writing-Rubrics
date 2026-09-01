from __future__ import annotations

import asyncio
import base64
import hashlib
import importlib.util
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation-results" / "hbq-human-alignment-optimizer-v9-desc18-broad-replication-grok-exec-v1"
CANDIDATES = ROOT / "evaluation-results" / "hbq-human-alignment-optimizer-v9-desc18-broad-replication-candidates-v1" / "study.py"
ACK = "2fb371ff82b37fe22d238a223fc030ad7a7bb9a10b672719da081470d25dbe78"


def load():
    spec = importlib.util.spec_from_file_location("desc18_exec", PACKAGE / "executor.py")
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = value
    try:
        spec.loader.exec_module(value)
    finally:
        sys.modules.pop(spec.name, None)
    return value


def freeze(root: Path):
    spec = importlib.util.spec_from_file_location("desc18_freeze_test", CANDIDATES)
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value.freeze(root)


def route_provider(*, expires_in: float = 600.0):
    now = datetime.now(timezone.utc)
    route = {"name": "grok-build-grok-4.6", "model": "grok-4.6", "reported_model": "grok-4.6-build", "adapter": "grok_exec", "provider": "xai_grok_build", "destination": "xai_grok_build_subscription", "account_class": "subscription", "identity_evidence": "requested_only", "zero_charge": True, "armed": True, "health": "healthy", "trusted": True, "reasoning_effort": "high", "grok_command": ["fixture"], "grok_command_identity": {"version": 1, "artifacts": []}, "cli_version_identity": {"version": 1, "artifacts": []}, "grok_cli_version": "grok fixture", "subscription_receipt_hash": "2" * 64, "cost_evidence": {"allowance_state": "available", "checked_at": (now - timedelta(seconds=1)).isoformat(), "evidence_hash": "1" * 64, "expires_at": (now + timedelta(seconds=expires_in)).isoformat(), "kind": "subscription_included", "version": 1}, "allowed_payload_classes": ["public_repo", "public_synthetic"], "timeout_seconds": 1.0}
    canonical = lambda value: json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode() + b"\n"
    evidence = {"route_name": route["name"], "route_sha256": hashlib.sha256(canonical(route)).hexdigest(), "cost_evidence_hash": route["cost_evidence"]["evidence_hash"], "subscription_receipt_hash": route["subscription_receipt_hash"], "grok_cli_version": route["grok_cli_version"], "cli_version_identity_sha256": hashlib.sha256(canonical(route["cli_version_identity"])).hexdigest(), "grok_command_identity_sha256": hashlib.sha256(canonical(route["grok_command_identity"])).hexdigest(), "registry_sha256": "3" * 64}
    return lambda _queue: (route, evidence)


def runner(value, *, quality: str = "valid", contacts: dict[str, int] | None = None):
    def run(*, prompt: bytes, schema_path: Path, output_dir: Path, route, before_contact):
        assert json.loads(schema_path.read_bytes())["required"] == ["scores", "evidence", "coverage"]
        responses = output_dir / "responses"
        responses.mkdir()
        (responses / "batch-0001.attempt-0001.prompt.txt").write_bytes(prompt)
        before_contact()
        if contacts is not None:
            contacts["count"] = contacts.get("count", 0) + 1
        token = hashlib.sha256(prompt + str(output_dir).encode()).hexdigest()
        scores = {key: 3.0 for key in value.DIMENSIONS}
        evidence = {key: "fixture evidence" for key in value.DIMENSIONS}
        if quality == "zero":
            scores = {key: 0.0 for key in value.DIMENSIONS}
        elif quality == "x":
            evidence["Coherence"] = "x"
        elif quality == "placeholder":
            evidence["Empathy"] = "[placeholder]"
        elif quality == "workspace":
            evidence["Surprise"] = "Searching workspace"
        coverage = {key: True for key in value.DIMENSIONS}
        if quality == "blank":
            evidence["Complexity"] = " \t "
        elif quality == "nonfinite":
            scores["Engagement"] = float("nan")
        elif quality == "out_of_range":
            scores["Relevance"] = 5.1
        elif quality == "bad_coverage":
            coverage["Empathy"] = "true"
        elif quality == "missing_coverage":
            coverage.pop("Empathy")
        elif quality == "extra_structured_field":
            coverage["Extra"] = True
        structured = {"scores": scores, "evidence": evidence, "coverage": coverage}
        if quality == "extra_structured_field":
            structured["unexpected"] = True
        elif quality == "missing_structured_field":
            structured.pop("coverage")
        response = value.canonical({"requestId": "request-" + token, "sessionId": "session-" + token, "modelUsage": {"grok-4.6-build": {}}, "stopReason": "end_turn", "num_turns": 1, "structuredOutput": structured})
        (responses / "batch-0001.attempt-0001.grok.envelope.json").write_bytes(response)
        return {"native_request_bytes": json.dumps({"prompt": prompt.decode()}, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(), "native_response_bytes": response, "identity": {"provider": "xai", "requested_model": "grok-4.6", "reported_model": "grok-4.6-build", "request_id": "request-" + token, "session_id": "session-" + token, "native_endpoint_contact_cardinality": "unproven", "tools_enabled": False}, "effective_settings": {"route_name": route["name"], "adapter": "grok_exec", "requested_model": "grok-4.6", "reported_model": "grok-4.6-build", "requested_reasoning_effort": "high", "tools_enabled": False, "web_search_enabled": False, "subagents_enabled": False, "tool_free_argv": ["--max-turns", "1", "--no-leader", "--no-subagents", "--disable-web-search", "--no-plan", "--tools", "", "--permission-mode", "dontAsk", "--sandbox", "read-only", "--verbatim"], "system_prompt_override": "Act as an isolated structured-output evaluator. Do not use memory, tools, web, plans, or subagents.", "sampler": {"batch_number": 1, "attempt_number": 1, "timeout_seconds": 1.0, "nonvisual_max_turns": 1}, "runner_prompt_artifact_sha256": value.sha256(prompt), "reasoning_attested": False}}

    return run


def common(tmp_path: Path):
    return {"output_root": tmp_path / "output", "freeze_root": tmp_path / "freeze", "queue_root": tmp_path / "queue", "authorization_acknowledgement_sha256": ACK, "route_provider": route_provider()}


def test_prepare_binds_64_open_validation_cells_without_contact(tmp_path: Path):
    value, args = load(), common(tmp_path)
    freeze(args["freeze_root"])
    schedule = value.frozen_schedule(args["freeze_root"])
    prepared = value.prepare_all(**args)
    assert schedule["geometry"] == {"candidates": 2, "confirmation_cells": 0, "grok_cells": 64, "open_validation_groups": 16, "open_validation_items": 32, "sol_cells": 0}
    assert prepared["logical_cells"] == len(prepared["prepared_cells"]) == 64
    assert prepared["provider_calls_made"] == prepared["process_launches"] == 0
    assert all((args["output_root"] / row["cell_id"] / "outbound-payload.json").read_bytes() == base64.b64decode(row["payload_base64"], validate=True) for row in schedule["cells"])


@pytest.mark.parametrize("prompt", ("file:C:/x.txt", "C:\\\\archive\\story.txt", "/tmp/story.txt", "../story.md", "source://freeze/123", "cell-0001", "0123456789abcdef"))
def test_precontact_rejects_pointer_like_prompt_with_full_story(prompt: str):
    value = load()
    payload = value.canonical({"writing": {"prompt": prompt, "story": "A complete synthetic story remains long enough to be accepted as actual writing rather than an identifier. " * 3}})
    with pytest.raises(ValueError, match="pointer"):
        value._validate_precontact_payload(payload)


@pytest.mark.parametrize("payload", [b'{"writing":{"prompt":"file:C:/x.txt","story":"a"}}\n', b'{"writing":{"prompt":"Hitchhiker","story":"short"}}\n', b'{"writing":{"prompt":"Hitchhiker"}}\n'])
def test_precontact_rejects_pointer_missing_or_nonfull_text(payload: bytes):
    value = load()
    with pytest.raises(ValueError, match="pointer|full|contain"):
        value._validate_precontact_payload(payload)


def test_precontact_rejection_prevents_fixture_contact(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    value, args, contacts = load(), common(tmp_path), {"count": 0}
    freeze(args["freeze_root"])
    prepared = value.prepare_all(**args)
    monkeypatch.setattr(value, "_validate_precontact_payload", lambda _payload: (_ for _ in ()).throw(ValueError("pointer-like fixture")))
    result = value.execute_one(**args, cell_id=prepared["prepared_cells"][0], allow_remote=True, runner=runner(value, contacts=contacts))
    assert result["kind"] == "definitely_not_contacted"
    assert contacts["count"] == 0 and result["provider_calls_made"] == result["process_launches"] == 0


def test_expired_cost_evidence_is_rejected_before_fixture_contact(tmp_path: Path):
    value, args, contacts = load(), common(tmp_path), {"count": 0}
    freeze(args["freeze_root"])
    prepared = value.prepare_all(**args)
    args["route_provider"] = route_provider(expires_in=-1.0)
    with pytest.raises(ValueError, match="not currently valid"):
        value.execute_one(**args, cell_id=prepared["prepared_cells"][0], allow_remote=True, runner=runner(value, contacts=contacts))
    assert contacts["count"] == 0


@pytest.mark.parametrize("quality", ("zero", "x", "placeholder", "workspace", "blank", "nonfinite", "out_of_range", "bad_coverage", "missing_coverage", "extra_structured_field", "missing_structured_field"))
def test_postresponse_rejections_are_terminal_and_never_collector_admitted(tmp_path: Path, quality: str):
    value, args, contacts = load(), common(tmp_path), {"count": 0}
    freeze(args["freeze_root"])
    prepared = value.prepare_all(**args)
    cell = prepared["prepared_cells"][0]
    first = value.execute_one(**args, cell_id=cell, allow_remote=True, runner=runner(value, quality=quality, contacts=contacts))
    second = value.execute_one(**args, cell_id=cell, allow_remote=True, runner=runner(value, contacts=contacts))
    assert first["kind"] == "reconcile_required_after_process_launch"
    assert second["state"] == "terminal"
    assert contacts["count"] == 1
    with pytest.raises(ValueError, match="output schedule inventory|execution claim inventory|collector"):
        value.finalize_collector(output_root=args["output_root"], freeze_root=args["freeze_root"], collector_output=tmp_path / "collector.json", authorization_acknowledgement_sha256=ACK)


def test_ten_lane_wave_replays_exact_request_response_identity_and_tool_free_settings(tmp_path: Path):
    value, args = load(), common(tmp_path)
    freeze(args["freeze_root"])
    value.prepare_all(**args)
    rows = asyncio.run(value.execute_wave(**args, allow_remote=True, runner=runner(value)))
    assert len(rows) == 64 and value.MAX_CONCURRENCY == 10
    collector = tmp_path / "collector.json"
    finalized = value.finalize_collector(output_root=args["output_root"], freeze_root=args["freeze_root"], collector_output=collector, authorization_acknowledgement_sha256=ACK)
    replay = value.replay_collector(output_root=args["output_root"], freeze_root=args["freeze_root"], collector_path=collector)
    assert finalized["cells"] == replay["cells"] == 64
    assert replay["equal_group_projection_ready"] is True


def test_contact_rechecks_expiry_immediately_before_fixture_contact(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    value, args, contacts = load(), common(tmp_path), {"count": 0}
    freeze(args["freeze_root"])
    prepared = value.prepare_all(**args)
    now = datetime.now(timezone.utc)
    clock = {"now": now}

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return clock["now"] if tz else clock["now"].replace(tzinfo=None)

    def delayed_runner(**kwargs):
        clock["now"] = now + timedelta(seconds=601)
        return runner(value, contacts=contacts)(**kwargs)

    monkeypatch.setattr(value, "datetime", Clock)
    result = value.execute_one(**args, cell_id=prepared["prepared_cells"][0], allow_remote=True, runner=delayed_runner)
    assert result["kind"] == "definitely_not_contacted"
    assert contacts["count"] == result["provider_calls_made"] == result["process_launches"] == 0
