from __future__ import annotations

import base64
import copy
import hashlib
import importlib.util
import json
import threading
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation-results" / "hbq-human-alignment-optimizer-v12-development-sol-exec-v1"
V12 = ROOT / "evaluation-results" / "hbq-human-alignment-optimizer-v12-development-panel-v1" / "study.py"
V9_SOL_ROOT = Path(r"C:\Users\Haile\Documents\cwr-desc18-broad-sol-veto-926f8f1-20260901a")
SPLIT = Path(r"C:\Users\Haile\Documents\cwr-hanna-optimizer-grok-primary-dev-20260829-d189d71\split-manifest.json")
CSV = Path(r"C:\Users\Haile\Documents\cwr-hanna-pinned-data-282f275\hanna_stories_annotations.csv")
CONTRACT = Path(r"C:\Users\Haile\Documents\cwr-hanna-successor-fresh88-freeze-v4\frozen-successor-contract.json")
ACK = "a" * 64


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def module():
    return load(PACKAGE / "executor.py", "v12_development_sol_exec")


def _sha(value: bytes | Any) -> str:
    raw = value if isinstance(value, bytes) else (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()
    return hashlib.sha256(raw).hexdigest()


def grok_route_provider():
    now = datetime.now(timezone.utc)
    route = {
        "name": "grok-build-grok-4.6",
        "model": "grok-4.6",
        "reported_model": "grok-4.6-build",
        "adapter": "grok_exec",
        "provider": "xai_grok_build",
        "destination": "xai_grok_build_subscription",
        "account_class": "subscription",
        "identity_evidence": "requested_only",
        "zero_charge": True,
        "armed": True,
        "health": "healthy",
        "trusted": True,
        "reasoning_effort": "high",
        "grok_command": ["fixture"],
        "grok_command_identity": {"version": 1, "artifacts": []},
        "cli_version_identity": {"version": 1, "artifacts": []},
        "grok_cli_version": "fixture",
        "subscription_receipt_hash": "2" * 64,
        "cost_evidence": {"allowance_state": "available", "checked_at": (now - timedelta(seconds=1)).isoformat(), "evidence_hash": "1" * 64, "expires_at": (now + timedelta(minutes=10)).isoformat(), "kind": "subscription_included", "version": 1},
        "allowed_payload_classes": ["public_repo"],
        "timeout_seconds": 1.0,
    }
    canonical = lambda value: json.dumps(value, sort_keys=True, separators=(",", ":")).encode() + b"\n"
    evidence = {"route_name": route["name"], "route_sha256": hashlib.sha256(canonical(route)).hexdigest(), "cost_evidence_hash": route["cost_evidence"]["evidence_hash"], "subscription_receipt_hash": route["subscription_receipt_hash"], "grok_cli_version": route["grok_cli_version"], "cli_version_identity_sha256": hashlib.sha256(canonical(route["cli_version_identity"])).hexdigest(), "grok_command_identity_sha256": hashlib.sha256(canonical(route["grok_command_identity"])).hexdigest(), "registry_sha256": "3" * 64}
    return lambda _queue: (route, evidence)


def grok_runner(value, cells: list[dict], contacts: list[str]):
    targets = {cell["cell_id"]: cell["target"] for cell in cells}

    def run(*, prompt: bytes, schema_path: Path, output_dir: Path, route, before_contact):
        assert json.loads(schema_path.read_bytes())["required"] == ["scores", "evidence", "coverage"]
        cell_id = output_dir.name
        target = targets[cell_id]
        structured = {"scores": {name: float(target[name]) for name in value.DIMS}, "evidence": {name: "Fixture evidence is present." for name in value.DIMS}, "coverage": {name: False for name in value.DIMS}}
        response = json.dumps({"modelUsage": {"grok-4.6-build": {"inputTokens": 2, "outputTokens": 2, "cacheReadInputTokens": 0, "cacheCreationInputTokens": 0, "modelCalls": 1, "costUSD": 0.0}}, "num_turns": 1, "requestId": f"request-{cell_id}", "sessionId": f"session-{cell_id}", "stopReason": "end_turn", "structuredOutput": structured, "text": json.dumps(structured, sort_keys=True, separators=(",", ":")), "thought": "I evaluated every requested criterion.", "total_cost_usd": 0.0, "total_cost_usd_ticks": 0, "usage": {"input_tokens": 2, "output_tokens": 2, "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0, "reasoning_tokens": 0, "total_tokens": 4}}, ensure_ascii=False, indent=2).encode()
        responses = output_dir / "responses"
        responses.mkdir()
        (responses / "batch-0001.attempt-0001.prompt.txt").write_bytes(prompt)
        before_contact()
        contacts.append(cell_id)
        (responses / "batch-0001.attempt-0001.grok.envelope.json").write_bytes(response)
        return {"native_request_bytes": json.dumps({"prompt": prompt.decode()}, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(), "native_response_bytes": response, "identity": {"provider": "xai", "requested_model": "grok-4.6", "reported_model": "grok-4.6-build", "request_id": f"request-{cell_id}", "session_id": f"session-{cell_id}", "native_endpoint_contact_cardinality": "unproven", "tools_enabled": False}, "effective_settings": {"route_name": route["name"], "adapter": "grok_exec", "requested_model": "grok-4.6", "reported_model": "grok-4.6-build", "requested_reasoning_effort": "high", "tools_enabled": False, "web_search_enabled": False, "subagents_enabled": False, "tool_free_argv": ["--max-turns", "1", "--no-leader", "--no-subagents", "--disable-web-search", "--no-plan", "--tools", "", "--permission-mode", "dontAsk", "--sandbox", "read-only", "--verbatim"], "system_prompt_override": "Act as an isolated structured-output evaluator. Do not use memory, tools, web, plans, or subagents.", "sampler": {"batch_number": 1, "attempt_number": 1, "timeout_seconds": 1.0, "nonvisual_max_turns": 1}, "runner_prompt_artifact_sha256": value.sha256(prompt), "reasoning_attested": False}}

    return run


@pytest.fixture(scope="module")
def grok_material(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    value = load(V12, "v12_development_fixture")
    root = tmp_path_factory.mktemp("v12-sol-grok")
    output_root, queue_root = root / "grok-output", root / "grok-queue"
    common = {"output_root": output_root, "queue_root": queue_root, "authorization_acknowledgement_sha256": ACK, "split_manifest": SPLIT, "hanna_csv": CSV, "successor_contract": CONTRACT, "route_provider": grok_route_provider()}
    schedule = value.schedule(split_manifest=SPLIT, hanna_csv=CSV, successor_contract=CONTRACT)
    value.prepare_all(**common)
    contacts: list[str] = []
    assert len(value.execute_wave(**common, allow_remote=True, runner=grok_runner(value, schedule["cells"], contacts))) == len(contacts) == 26
    report = value.report(**{key: common[key] for key in common if key not in {"queue_root", "route_provider"}})
    result_path = root / "grok-result.json"
    result_path.write_bytes(value.canonical(report))
    return {"root": output_root, "result_path": result_path, "result_sha256": value.sha256(report), "schedule": schedule, "report": report}


def sol_route() -> tuple[dict[str, Any], dict[str, Any]]:
    proofs = list(V9_SOL_ROOT.rglob("zero-charge-route-proof.json"))
    if not proofs:
        pytest.skip("pinned V9 Sol route fixture is not available")
    proof = json.loads(proofs[0].read_text(encoding="utf-8"))
    route, evidence = copy.deepcopy(proof["route"]), copy.deepcopy(proof["route_evidence"])
    now = datetime.now(timezone.utc)
    route["cost_evidence"]["checked_at"] = (now - timedelta(minutes=1)).isoformat()
    route["cost_evidence"]["expires_at"] = (now + timedelta(minutes=10)).isoformat()
    evidence["cost_evidence_checked_at"] = route["cost_evidence"]["checked_at"]
    evidence["cost_evidence_expires_at"] = route["cost_evidence"]["expires_at"]
    evidence["route_sha256"] = _sha(route)
    return route, evidence


class Broker:
    def __init__(self, route: dict[str, Any]) -> None:
        self.route = route

    def _load_registry_live(self) -> dict[str, Any]:
        return {"version": 1, "routes": [self.route]}

    def _validate_route(self, candidate: dict[str, Any], *, verify_command_identity: bool, validate_current_evidence: bool) -> None:
        assert candidate == self.route
        assert verify_command_identity and validate_current_evidence


def call_args(tmp_path: Path, material: dict[str, Any], route: dict[str, Any] | None = None) -> dict[str, Any]:
    route = route or sol_route()[0]
    queue_root = tmp_path / "sol-queue"
    queue_root.mkdir()
    return {"grok_root": material["root"], "grok_acknowledgement": ACK, "grok_result_path": material["result_path"], "expected_grok_result_sha256": material["result_sha256"], "split_manifest": SPLIT, "hanna_csv": CSV, "successor_contract": CONTRACT, "output_root": tmp_path / "sol-output", "queue_root": queue_root, "authorization_acknowledgement_sha256": ACK, "broker_factory": lambda _root: Broker(route)}


def fake_codex(value, rows: tuple[dict, ...], contacts: list[str], concurrency: dict[str, int]):
    targets = {row["cell_id"]: row["target"] for row in rows}
    zero_cell = min(row["cell_id"] for row in rows if row["candidate_id"] == value.BASELINE)
    memberships: dict[tuple[str, str], list[str]] = defaultdict(list)
    for row in rows:
        memberships[(row["candidate_id"], row["prompt_group_id"])].append(row["cell_id"])
    signs = {cell_id: 0.25 if index % 2 == 0 else -0.25 for members in memberships.values() for index, cell_id in enumerate(sorted(members))}
    lock = threading.Lock()

    def invoke(**kwargs: Any):
        root = Path(kwargs["output_dir"])
        cell_id = root.name
        target = targets[cell_id]
        with lock:
            concurrency["active"] += 1
            concurrency["maximum"] = max(concurrency["maximum"], concurrency["active"])
        try:
            time.sleep(0.015)
            scores = {name: 2.0 if name == "Coherence" else float(target[name]) + signs[cell_id] for name in value.DIMS}
            if cell_id == zero_cell:
                scores = {name: 0.0 for name in value.DIMS}
            answer = {"scores": scores, "evidence": {name: "Fixture evidence is present." for name in value.DIMS}, "coverage": {name: False for name in value.DIMS}}
            final = json.dumps(answer, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            responses = root / "responses"
            responses.mkdir(exist_ok=True)
            kwargs["before_provider_attempt"]()
            events = b"".join(json.dumps(event, ensure_ascii=False, separators=(",", ":")).encode() + b"\n" for event in ({"type": "thread.started", "thread_id": f"fixture-thread-{cell_id}"}, {"type": "turn.started"}, {"type": "item.started", "item": {"id": "message-1", "type": "agent_message", "text": ""}}, {"type": "item.completed", "item": {"id": "message-1", "type": "agent_message", "text": final}}, {"type": "turn.completed", "usage": {"input_tokens": 4, "output_tokens": 4}}))
            events_path, message_path, stderr_path = responses / "batch-0001.attempt-0001.events.jsonl", responses / "batch-0001.attempt-0001.message.json", root / "raw-codex-stderr.bin"
            events_path.write_bytes(events)
            message_path.write_text(final, encoding="utf-8")
            stderr_path.write_bytes(b"")
            contacts.append(cell_id)
            native = load(ROOT / "evaluation-results" / "hbq-human-alignment-optimizer-v4-native-subscription-exec-v3" / "executor.py", "v12_sol_native_fixture")
            return final, {"command": native._expected_codex_command(kwargs["executable"], root), "reported": {"model": None, "provider": None, "reasoning_effort": None, "session_id": f"fixture-thread-{cell_id}"}, "provider_artifacts": {"codex_events": {"path": events_path.relative_to(root).as_posix(), "bytes": len(events), "sha256": value.sha256(events)}, "codex_stderr": {"path": stderr_path.relative_to(root).as_posix(), "bytes": 0, "sha256": value.sha256(b"")}}}
        finally:
            with lock:
                concurrency["active"] -= 1

    return invoke


def report_args(common: dict[str, Any]) -> dict[str, Any]:
    return {key: common[key] for key in ("grok_root", "grok_acknowledgement", "grok_result_path", "expected_grok_result_sha256", "split_manifest", "hanna_csv", "successor_contract", "output_root", "authorization_acknowledgement_sha256")}


def test_complete_v12_grok_replay_has_exact_26_row_payload_parity(grok_material: dict[str, Any]) -> None:
    value = module()
    resolution = value._resolution(grok_root=grok_material["root"], grok_acknowledgement=ACK, grok_result_path=grok_material["result_path"], expected_grok_result_sha256=grok_material["result_sha256"], split_manifest=SPLIT, hanna_csv=CSV, successor_contract=CONTRACT)
    source = {cell["cell_id"]: cell for cell in grok_material["schedule"]["cells"]}
    assert len(resolution["rows"]) == len(source) == 26
    for row in resolution["rows"]:
        original = source[row["source_cell_id"]]
        assert row["payload_base64"] == original["payload_base64"] and row["payload_sha256"] == original["payload_sha256"]
        assert "target" not in json.loads(base64.b64decode(row["payload_base64"], validate=True))


def test_prepare_is_provider_free_and_binds_complete_grok_replay(tmp_path: Path, grok_material: dict[str, Any]) -> None:
    value, common = module(), call_args(tmp_path, grok_material)
    result = value.prepare_all(**common)
    assert result == {"study_id": value.STUDY_ID, "state": "prepared_exact_26_matched_sol_development_cells", "cells": 26, "groups": 7, "provider_calls_made": 0, "process_launches": 0, "max_concurrency": 10}


def test_sol_wave_is_bounded_one_shot_and_uses_non_cancelling_group_mae(tmp_path: Path, grok_material: dict[str, Any]) -> None:
    value, common = module(), call_args(tmp_path, grok_material)
    value.prepare_all(**common)
    rows = value._resolution(**{key: common[key] for key in ("grok_root", "grok_acknowledgement", "grok_result_path", "expected_grok_result_sha256", "split_manifest", "hanna_csv", "successor_contract")})["rows"]
    contacts: list[str] = []
    concurrency = {"active": 0, "maximum": 0}
    results = value.execute_wave(**common, allow_remote=True, call_codex=fake_codex(value, rows, contacts, concurrency))
    assert len(results) == len(contacts) == 26 and 1 <= concurrency["maximum"] <= 10
    report = value.report(**report_args(common))
    assert (report["endpoint"], report["partition"]) == ("sol_later", "development")
    assert len(report["cells"]) == report["unique_thread_ids"] == report["unique_session_ids"] == 26
    assert all(not all(cell["coverage"].values()) and all(type(cell["scores"][name]) is float for name in value.DIMS) for cell in report["cells"])
    assert any(not any(cell["scores"].values()) and not any(cell["coverage"].values()) for cell in report["cells"])
    expected = {}
    for candidate in (value.BASELINE, value.CHILD20):
        groups: dict[str, list[float]] = defaultdict(list)
        for cell in report["cells"]:
            if cell["candidate_id"] == candidate:
                groups[cell["prompt_group_id"]].append(sum(abs(cell["scores"][name] - cell["target"][name]) for name in value.DIMS) / len(value.DIMS))
        expected[candidate] = sum(sum(errors) / len(errors) for errors in groups.values()) / len(groups)
    assert {row["candidate_id"]: row["equal_group_mean_item_mae"] for row in report["metrics"]} == pytest.approx(expected)
    assert all(row["item_count"] == 13 and row["group_count"] == 7 and len(row["per_group_mean_item_mae"]) == 7 for row in report["metrics"])
    assert report["rank_correlations"][value.CHILD20]["item_13"]["Coherence"] is None
    assert report["rank_correlations"][value.CHILD20]["group_mean_7"]["Coherence"] is None
    before = {path.relative_to(common["output_root"]).as_posix(): _sha(path.read_bytes()) for path in common["output_root"].rglob("*") if path.is_file()}
    with pytest.raises(ValueError, match="resend|terminal|inventory"):
        value.execute_wave(**common, allow_remote=True, call_codex=lambda **_kwargs: pytest.fail("replay contacted Codex"))
    assert {path.relative_to(common["output_root"]).as_posix(): _sha(path.read_bytes()) for path in common["output_root"].rglob("*") if path.is_file()} == before
    prepared_path = common["output_root"] / results[1]["cell_id"] / "prepared.json"
    original_prepared = prepared_path.read_bytes()
    prepared = json.loads(original_prepared)
    prepared["route_evidence"]["route_name"] = "mixed-route"
    prepared_path.write_bytes(value.canonical(prepared))
    with pytest.raises(ValueError):
        value.report(**report_args(common))
    prepared_path.write_bytes(original_prepared)


def test_tampered_grok_report_is_rejected_before_any_route(tmp_path: Path, grok_material: dict[str, Any]) -> None:
    value = module()
    forged = tmp_path / "forged-grok-result.json"
    raw = json.loads(grok_material["result_path"].read_text(encoding="utf-8"))
    raw["endpoint"] = "sol_later"
    forged.write_bytes(value.canonical(raw))
    route_calls: list[str] = []
    args = call_args(tmp_path, grok_material)
    args.update({"grok_result_path": forged, "expected_grok_result_sha256": value.sha256(raw), "broker_factory": lambda _root: route_calls.append("route")})
    with pytest.raises(ValueError, match="Grok receipt replay differs|expected V12 Grok result"):
        value.prepare_all(**args)
    assert route_calls == [] and not args["output_root"].exists()


def test_precontact_tamper_prevents_sol_contact_and_report(tmp_path: Path, grok_material: dict[str, Any]) -> None:
    value, common = module(), call_args(tmp_path, grok_material)
    value.prepare_all(**common)
    rows = value._resolution(**{key: common[key] for key in ("grok_root", "grok_acknowledgement", "grok_result_path", "expected_grok_result_sha256", "split_manifest", "hanna_csv", "successor_contract")})["rows"]
    contacts: list[str] = []
    concurrency = {"active": 0, "maximum": 0}
    clean = fake_codex(value, rows, contacts, concurrency)

    def mutate_then_call(**kwargs: Any):
        (Path(kwargs["output_dir"]) / "prepared.json").write_bytes(b"{}\n")
        return clean(**kwargs)

    with pytest.raises((TypeError, ValueError)):
        value.execute_wave(**common, allow_remote=True, call_codex=mutate_then_call)
    assert contacts == []
    with pytest.raises((TypeError, ValueError)):
        value.report(**report_args(common))
