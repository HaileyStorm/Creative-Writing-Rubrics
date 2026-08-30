from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from _scoped_module_loader import load_module


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation-results" / "hbq-human-alignment-optimizer-v4-balanced-dspy-heldout-exec-v1"
executor = load_module(PACKAGE / "executor.py", name="hanna_heldout_exec_v1")
PINNED_SOL_V3 = executor._sol_v4()._v3()
ACK = "a" * 64
MANIFEST = Path(r"C:\Users\Haile\Documents\cwr-hanna-v4-balanced-dspy-grok-reconcile-v1-52dc2157-e0b5c104\reconciliation-manifest.json")
FROZEN = Path(r"C:\Users\Haile\Documents\cwr-hanna-successor-fresh88-freeze-v4\frozen-successor-contract.json")
CSV = Path(r"C:\Users\Haile\Documents\cwr-hanna-pinned-data-282f275\hanna_stories_annotations.csv")
PATHS = {"reconciliation_manifest_path": MANIFEST, "frozen_successor_path": FROZEN, "hanna_csv_path": CSV}


def _answer() -> dict:
    dimensions = ["Relevance", "Coherence", "Empathy", "Surprise", "Engagement", "Complexity"]
    return {"scores": {name: 3.0 for name in dimensions}, "evidence": {name: "fixture evidence" for name in dimensions}, "coverage": {name: True for name in dimensions}}


def _adapter_canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _lifecycle_events(final: bytes) -> bytes:
    stream = [{"type": "thread.started", "thread_id": "thread"}, {"type": "turn.started"}, {"type": "item.started", "item": {"id": "message", "type": "agent_message", "text": ""}}, {"type": "item.completed", "item": {"id": "message", "type": "agent_message", "text": final.decode("utf-8")}}, {"type": "turn.completed", "usage": {}}]
    return b"".join(json.dumps(item, separators=(",", ":")).encode("utf-8") + b"\n" for item in stream)


def _fake_sol() -> SimpleNamespace:
    class V3:
        CODEX_ADAPTER_PATH = PINNED_SOL_V3.CODEX_ADAPTER_PATH
        CODEX_ADAPTER_SHA256 = PINNED_SOL_V3.CODEX_ADAPTER_SHA256
        @staticmethod
        def _expected_codex_command(executable: str, root: Path) -> list[str]: return [executable]
        @staticmethod
        def _codex_event_projection(events: bytes, parser: object) -> dict: return {"completed_agent_message_text": events.decode("utf-8"), "thread_id": "fixture-thread", "usage": {}}
        @staticmethod
        def _load_parse_codex_events() -> object: return object()
        @staticmethod
        def _strict_stderr_labels(stderr: bytes) -> dict: return {"session_id": None}
    class Sol:
        @staticmethod
        def _v3() -> V3: return V3()
        @staticmethod
        def _artifact(root: Path, ref: object, label: str) -> bytes:
            assert isinstance(ref, dict); raw = (root / ref["path"]).read_bytes(); assert ref == {"path": ref["path"], "bytes": len(raw), "sha256": executor.sha256(raw)}; return raw
    return Sol()


def _write_complete_collection(root: Path) -> dict:
    schedule = executor._schedule(**PATHS)
    command_identity = {"version": 1, "artifacts": [{"path": "grok-fixture.exe", "sha256": "b" * 64}]}
    grok_route = {"name": "grok-build-grok-4.6", "model": "grok-4.6", "adapter": "grok_exec", "provider": "xai_grok_build", "destination": "xai_grok_build_subscription", "account_class": "subscription", "zero_charge": True, "armed": True, "health": "healthy", "reasoning_effort": "high", "reported_model": "grok-4.6-build", "identity_evidence": "requested_only", "allowed_payload_classes": ["public_repo"], "grok_command": ["grok-fixture.exe"], "grok_command_identity": command_identity, "cli_version_identity": command_identity, "grok_cli_version": "grok fixture 1.0", "cost_evidence": {"evidence_hash": "a" * 64}, "subscription_receipt_hash": "c" * 64, "timeout_seconds": 60}
    grok_evidence = {"route_name": grok_route["name"], "route_sha256": executor.sha256(executor.canonical(grok_route)), "registry_sha256": "d" * 64, "cost_evidence_hash": "a" * 64, "subscription_receipt_hash": "c" * 64, "grok_command_identity_sha256": executor.sha256(executor.canonical(command_identity)), "cli_version_identity_sha256": executor.sha256(executor.canonical(command_identity)), "grok_cli_version": "grok fixture 1.0"}
    sol_identity = {"version": 1, "artifacts": [{"path": "codex-fixture.exe", "sha256": "e" * 64}]}
    sol_route = {"name": "codex-chatgpt-gpt-5.6-sol", "model": "gpt-5.6-sol", "adapter": "codex_exec", "provider": "openai_codex", "destination": "openai_codex_chatgpt_subscription", "account_class": "subscription", "zero_charge": True, "armed": True, "health": "healthy", "reasoning_effort": "high", "identity_evidence": "requested_only", "trusted": True, "allowed_payload_classes": ["public_repo"], "codex_command": ["codex-fixture.exe"], "codex_command_identity": sol_identity, "cli_version_identity": sol_identity, "auth_status_identity": sol_identity, "codex_cli_version": "codex fixture 1.0", "command": ["python-fixture.exe", str(PINNED_SOL_V3.CODEX_ADAPTER_PATH)], "command_identity": sol_identity, "cost_evidence": {"evidence_hash": "f" * 64, "checked_at": "2026-08-30T00:00:00Z", "expires_at": "2026-08-30T01:00:00Z"}, "auth_receipt_hash": "1" * 64, "timeout_seconds": 60}
    sol_evidence = {"route_name": sol_route["name"], "route_sha256": executor.sha256(executor.canonical(sol_route)), "registry_sha256": "2" * 64, "cost_evidence_hash": sol_route["cost_evidence"]["evidence_hash"], "auth_receipt_hash": sol_route["auth_receipt_hash"], "cost_evidence_checked_at": sol_route["cost_evidence"]["checked_at"], "cost_evidence_expires_at": sol_route["cost_evidence"]["expires_at"], "wrapper_command_identity_sha256": executor.sha256(executor.canonical(sol_identity)), "codex_command_identity_sha256": executor.sha256(executor.canonical(sol_identity)), "cli_version_identity_sha256": executor.sha256(executor.canonical(sol_identity)), "auth_status_identity_sha256": executor.sha256(executor.canonical(sol_identity)), "codex_cli_version": sol_route["codex_cli_version"], "codex_adapter_sha256": PINNED_SOL_V3.CODEX_ADAPTER_SHA256}
    for ordinal, cell in enumerate(schedule["cells"]):
        cell_root = root / cell["cell_id"]; cell_root.mkdir(parents=True)
        route, evidence = (grok_route, grok_evidence) if cell["route_name"] == "grok_primary" else (sol_route, sol_evidence)
        payload = executor._payload(executor._study(), cell); files = executor._files(cell, schedule, payload, route, evidence, ACK)
        for name, raw in files.items(): (cell_root / name).write_bytes(raw)
        prepared = json.loads(files["prepared.json"]); intent = {"format_version": 1, "study_id": executor.STUDY_ID, "kind": "process_launch_intent_not_native_contact", "cell_id": cell["cell_id"], "prepared_sha256": executor.sha256(executor.canonical(prepared)), "native_contact_proven": False}; (cell_root / "launch-intent.json").write_bytes(executor.canonical(intent))
        if cell["route_name"] == "grok_primary":
            output = _answer(); command_hash = executor.sha256(_adapter_canonical({"adapter_version": 1, "grok_command": grok_route["grok_command"], "model": "grok-4.6", "reported_model": "grok-4.6-build", "reasoning_effort": "high"})); runtime = {"adapter_version": 1, "requested_model": "grok-4.6", "reported_model": "grok-4.6-build", "requested_reasoning_effort": "high", "reasoning_attested": False, "reasoning_attestation": "not_reported_by_grok_build_cli", "identity_evidence": "requested_only", "cli_version": grok_route["grok_cli_version"], "nonvisual_max_turns": 1, "observed_turns": 1, "command_identity": command_identity, "command_identity_hash": command_hash, "subscription_receipt_hash": grok_route["subscription_receipt_hash"], "request_id_hash": f"{ordinal + 1:064x}", "session_id_hash": f"{ordinal + 101:064x}", "envelope_hash": f"{ordinal + 201:064x}", "execution_policy": "bounded_nonvisual_read_only", "usage_telemetry": {"status": "not_reported"}}; control = {"control": {"version": 1, "state": "completed"}, "result": {"schema_version": 1, "request_hash": executor.sha256(_adapter_canonical({"prompt": payload.decode("utf-8")})), "output_hash": executor.sha256(_adapter_canonical(output)), "output": output, "runtime": runtime}}
            raw = _adapter_canonical(control); (cell_root / "adapter-stdout.bin").write_bytes(raw); (cell_root / "adapter-control-envelope.json").write_bytes(executor.canonical(control)); (cell_root / "runtime-identity.json").write_bytes(executor.canonical(runtime))
            receipt = {"format_version": 1, "study_id": executor.STUDY_ID, "kind": "grok_completed_adapter_receipt", "cell_id": cell["cell_id"], "prepared_sha256": executor.sha256(executor.canonical(prepared)), "payload_sha256": executor.sha256(payload), "response_schema_sha256": executor.sha256(files["response-schema.json"]), "adapter_stdout_sha256": executor.sha256(raw), "adapter_control_sha256": executor.sha256(executor.canonical(control)), "runtime_sha256": executor.sha256(executor.canonical(runtime)), "output_sha256": control["result"]["output_hash"], "request_id_hash": runtime["request_id_hash"], "session_id_hash": runtime["session_id_hash"], "native_contact_proven": True, "native_endpoint_contact_cardinality": "proven_exactly_one", "route_evidence": evidence}
            result = {"format_version": 1, "study_id": executor.STUDY_ID, "kind": "grok_completed", "cell_id": cell["cell_id"], "provider_calls_made": 1, "process_launches": 1, "receipt_sha256": executor.sha256(executor.canonical(receipt)), "adapter_stdout_sha256": executor.sha256(raw), "output_sha256": control["result"]["output_hash"]}
        else:
            responses = cell_root / "responses"; responses.mkdir(); final = executor.canonical(_answer()); events, stderr = final, b""; (responses / "batch-0001.attempt-0001.message.json").write_bytes(final); (responses / "batch-0001.attempt-0001.events.jsonl").write_bytes(events); (cell_root / "raw-codex-events.bin").write_bytes(events); (cell_root / "raw-codex-stderr.bin").write_bytes(stderr); (cell_root / "raw-codex-final-response.bin").write_bytes(final)
            artifacts = {"codex_events": {"path": "raw-codex-events.bin", "bytes": len(events), "sha256": executor.sha256(events)}, "codex_stderr": {"path": "raw-codex-stderr.bin", "bytes": len(stderr), "sha256": executor.sha256(stderr)}}; record = {"command": ["codex-fixture.exe"], "provider_artifacts": artifacts}; effective = {"requested_model": "gpt-5.6-sol", "local_effective_model": "gpt-5.6-sol", "requested_reasoning_effort": "high", "local_effective_reasoning_effort": "high", "provider_attested": False, "codex_cli_version": sol_route["codex_cli_version"], "codex_command_identity": sol_route["codex_command_identity"], "capture_jsonl_events": True, "tools_enabled": False, "web_search_enabled": False, "plans_enabled": False, "subagents_enabled": False, "event_projection": {"completed_agent_message_text": final.decode("utf-8"), "thread_id": "fixture-thread", "usage": {}}, "stderr_label_evidence": {"session_id": None}}; (cell_root / "codex-record.json").write_bytes(executor.canonical(record)); (cell_root / "effective-settings.json").write_bytes(executor.canonical(effective))
            receipt = {"format_version": 1, "study_id": executor.STUDY_ID, "kind": "sol_local_lifecycle_receipt", "cell_id": cell["cell_id"], "prepared_sha256": executor.sha256(executor.canonical(prepared)), "payload_sha256": executor.sha256(payload), "response_schema_sha256": executor.sha256(files["response-schema.json"]), "native_contact_proven": False, "native_endpoint_contact_cardinality": "unproven", "process_launches": 1, "route_evidence": evidence, "raw_events_sha256": executor.sha256(events), "raw_stderr_sha256": executor.sha256(stderr), "final_response_sha256": executor.sha256(final), "codex_record_sha256": executor.sha256(executor.canonical(record)), "effective_settings_sha256": executor.sha256(executor.canonical(effective)), "usage": {}}
            result = {"format_version": 1, "study_id": executor.STUDY_ID, "kind": "sol_local_lifecycle_completed", "cell_id": cell["cell_id"], "provider_calls_made": None, "process_launches": 1, "receipt_sha256": executor.sha256(executor.canonical(receipt)), "final_response_sha256": executor.sha256(final)}
        (cell_root / "execution-receipt.json").write_bytes(executor.canonical(receipt)); (cell_root / "result.json").write_bytes(executor.canonical(result))
    return schedule


@pytest.fixture(scope="module")
def complete_collection(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, dict]:
    root = tmp_path_factory.mktemp("heldout-complete") / "roots"; return root, _write_complete_collection(root)


@pytest.fixture()
def collection_copy(complete_collection: tuple[Path, dict], tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    source, schedule = complete_collection; target = tmp_path / "roots"; shutil.copytree(source, target); monkeypatch.setattr(executor, "_sol_v4", _fake_sol); monkeypatch.setattr(executor, "_schedule", lambda **_: schedule); return target


def test_freeze_accepts_full_44_grok_22_sol_protocol_roots(collection_copy: Path, tmp_path: Path):
    manifest = executor.freeze_collection(**PATHS, output_root=collection_copy, manifest_path=tmp_path / "collection.json")
    assert len(manifest["cells"]) == 66 and manifest["grok_completed_native_identities"] == 44


@pytest.mark.parametrize("kind", ["adapter", "intent", "route_command", "subscription", "sol_association", "grok_result", "sol_effective", "responses_extra", "runtime_route_binding", "grok_route_policy", "sol_route_policy", "reparse"])
def test_freeze_rejects_protocol_tamper_across_full_collection(collection_copy: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kind: str):
    grok = next(path for path in collection_copy.iterdir() if (path / "adapter-stdout.bin").exists()); sol = next(path for path in collection_copy.iterdir() if (path / "codex-record.json").exists())
    if kind == "adapter": (grok / "adapter-stdout.bin").write_bytes(b"{}")
    elif kind == "intent": (grok / "launch-intent.json").write_bytes(executor.canonical({"forged": True}))
    elif kind == "route_command":
        record = json.loads((sol / "codex-record.json").read_bytes()); record["command"] = ["forged"]; (sol / "codex-record.json").write_bytes(executor.canonical(record))
    elif kind == "subscription":
        control = json.loads((grok / "adapter-control-envelope.json").read_bytes()); control["result"]["runtime"]["subscription_receipt_hash"] = "b" * 64; (grok / "adapter-control-envelope.json").write_bytes(executor.canonical(control))
    elif kind == "sol_association": (sol / "raw-codex-final-response.bin").write_bytes(b"{}")
    elif kind == "grok_result":
        result = json.loads((grok / "result.json").read_bytes()); result.update({"provider_calls_made": 0, "process_launches": 0}); (grok / "result.json").write_bytes(executor.canonical(result))
    elif kind == "sol_effective":
        effective = json.loads((sol / "effective-settings.json").read_bytes()); effective["requested_model"] = "wrong"; (sol / "effective-settings.json").write_bytes(executor.canonical(effective))
        receipt = json.loads((sol / "execution-receipt.json").read_bytes()); receipt["effective_settings_sha256"] = executor.sha256(executor.canonical(effective)); (sol / "execution-receipt.json").write_bytes(executor.canonical(receipt))
        result = json.loads((sol / "result.json").read_bytes()); result["receipt_sha256"] = executor.sha256(executor.canonical(receipt)); (sol / "result.json").write_bytes(executor.canonical(result))
    elif kind == "responses_extra": (sol / "responses" / "orphan.bin").write_bytes(b"orphan")
    elif kind == "runtime_route_binding":
        control = json.loads((grok / "adapter-stdout.bin").read_bytes()); runtime = control["result"]["runtime"]; runtime.update({"command_identity_hash": "f" * 64, "cli_version": "forged", "envelope_hash": "e" * 64})
        raw = _adapter_canonical(control); (grok / "adapter-stdout.bin").write_bytes(raw); (grok / "adapter-control-envelope.json").write_bytes(executor.canonical(control)); (grok / "runtime-identity.json").write_bytes(executor.canonical(runtime))
        receipt = json.loads((grok / "execution-receipt.json").read_bytes()); receipt.update({"adapter_stdout_sha256": executor.sha256(raw), "adapter_control_sha256": executor.sha256(executor.canonical(control)), "runtime_sha256": executor.sha256(executor.canonical(runtime))}); (grok / "execution-receipt.json").write_bytes(executor.canonical(receipt))
        result = json.loads((grok / "result.json").read_bytes()); result.update({"receipt_sha256": executor.sha256(executor.canonical(receipt)), "adapter_stdout_sha256": executor.sha256(raw)}); (grok / "result.json").write_bytes(executor.canonical(result))
    elif kind in {"grok_route_policy", "sol_route_policy"}:
        target = grok if kind == "grok_route_policy" else sol; prepared = json.loads((target / "prepared.json").read_bytes()); route = dict(prepared["route"]); route.update({"zero_charge": False, "armed": False}); proof = json.loads((target / "zero-charge-route-proof.json").read_bytes()); evidence = dict(proof["route_evidence"]); evidence["route_sha256"] = executor.sha256(executor.canonical(route))
        schedule = executor._schedule(); cell = next(row for row in schedule["cells"] if row["cell_id"] == target.name); payload = executor._payload(executor._study(), cell); acknowledgement = json.loads((target / "authorization-acknowledgement.json").read_bytes())["acknowledgement_sha256"]
        for name, raw in executor._files(cell, schedule, payload, route, evidence, acknowledgement).items(): (target / name).write_bytes(raw)
        prepared = json.loads((target / "prepared.json").read_bytes()); intent = {"format_version": 1, "study_id": executor.STUDY_ID, "kind": "process_launch_intent_not_native_contact", "cell_id": target.name, "prepared_sha256": executor.sha256(executor.canonical(prepared)), "native_contact_proven": False}; (target / "launch-intent.json").write_bytes(executor.canonical(intent))
        receipt = json.loads((target / "execution-receipt.json").read_bytes()); receipt.update({"prepared_sha256": executor.sha256(executor.canonical(prepared)), "route_evidence": evidence}); (target / "execution-receipt.json").write_bytes(executor.canonical(receipt))
        result = json.loads((target / "result.json").read_bytes()); result["receipt_sha256"] = executor.sha256(executor.canonical(receipt)); (target / "result.json").write_bytes(executor.canonical(result))
    else:
        original = executor._plain; monkeypatch.setattr(executor, "_plain", lambda path, directory=None: False if Path(path).name == "adapter-stdout.bin" else original(path, directory=directory))
    with pytest.raises(ValueError): executor.freeze_collection(**PATHS, output_root=collection_copy, manifest_path=tmp_path / f"{kind}.json")


def _schedule() -> dict:
    cells = []
    for index in range(66):
        route = "grok_primary" if index < 44 else "sol_validation"
        cells.append({"cell_id": f"cell-{index:02d}", "route_name": route, "payload_base64": "e30=", "payload_sha256": executor.sha256(b"{}"), "item_id": f"item-{index % 4}", "candidate_id": f"candidate-{index % 11}"})
    return {"schedule_sha256": executor.SCHEDULE_SHA256, "confirmation": {"status": "unopened", "cells": 0}, "geometry": {"candidates": 11, "grok_cells": 44, "sol_cells": 22, "total_cells": 66}, "cells": cells}


def _route(route_name: str, _queue: Path):
    route = {"destination": "grok-subscription" if route_name == "grok_primary" else "sol-subscription", "timeout_seconds": 1, "codex_command": ["codex"]}
    return SimpleNamespace(), SimpleNamespace(), route, {"route": route_name, "proof": "x"}


@pytest.fixture()
def prepared(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setattr(executor, "_study", lambda: SimpleNamespace(payload_bytes=lambda row: b"{}"))
    monkeypatch.setattr(executor, "_schedule", lambda **_: _schedule())
    monkeypatch.setattr(executor, "_schema", lambda _: executor.canonical({"format_version": 1, "type": "object", "additionalProperties": False, "required": ["scores", "evidence", "coverage"], "properties": {"scores": {}, "evidence": {}, "coverage": {}}}))
    monkeypatch.setattr(executor, "_route", _route)
    return _schedule(), tmp_path / "roots", tmp_path / "queue"


def test_real_pinned_schedule_reconstruction_and_embedded_schema():
    schedule = executor._schedule(**PATHS)
    assert schedule["schedule_sha256"] == executor.SCHEDULE_SHA256 and len(schedule["cells"]) == 66
    schema = json.loads(executor._schema(executor._payload(executor._study(), schedule["cells"][0])))
    assert schema["required"] == ["scores", "evidence", "coverage"] and set(schema["properties"]["scores"]["properties"]) == {"Relevance", "Coherence", "Empathy", "Surprise", "Engagement", "Complexity"}


def test_pinned_native_route_module_exposes_both_prepare_validators():
    native = executor._native()
    assert callable(native.validate_live_grok_route) and callable(native.validate_live_sol_route)


def test_freeze_identity_rejects_same_request_and_session_per_cell():
    request = "1" * 64; requests: set[str] = set(); sessions: set[str] = set()
    with pytest.raises(ValueError, match="request/session"):
        executor._admit_grok_identity(request, request, requests, sessions)
    assert not requests and not sessions


def test_prepare_all_66_has_zero_calls_and_cross_route_payload_parity(prepared):
    schedule, roots, queue = prepared
    rows = executor.prepare_all(**PATHS, output_root=roots, queue_root=queue, authorization_acknowledgement_sha256=ACK)
    assert len(rows) == 66 and all(row["provider_calls_made"] == row["process_launches"] == 0 for row in rows)
    assert (roots / "cell-00" / "payload.bin").read_bytes() == (roots / "cell-44" / "payload.bin").read_bytes() == b"{}"
    assert json.loads((roots / "cell-00" / "prepared.json").read_bytes())["confirmation"] == {"status": "unopened", "cells": 0}


def test_cli_main_guard_prepares_all_66_provider_free_roots(tmp_path: Path):
    direct = subprocess.run([sys.executable, str(PACKAGE / "executor.py"), "--help"], capture_output=True, text=True)
    assert direct.returncode == 0 and "--prepare-all" in direct.stdout
    output = tmp_path / "roots"; source = (PACKAGE / "executor.py").as_posix()
    script = f'''import hashlib, importlib.util, json, sys
from pathlib import Path
from types import SimpleNamespace
path = Path({source!r})
spec = importlib.util.spec_from_file_location("heldout_cli", path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
cells = []
for index in range(66):
    route = "grok_primary" if index < 44 else "sol_validation"
    cells.append({{"cell_id": f"cell-{{index:02d}}", "route_name": route, "payload_base64": "e30=", "payload_sha256": hashlib.sha256(b"{{}}").hexdigest(), "item_id": f"item-{{index % 4}}", "candidate_id": f"candidate-{{index % 11}}"}})
schedule = {{"schedule_sha256": module.SCHEDULE_SHA256, "confirmation": {{"status": "unopened", "cells": 0}}, "geometry": {{"candidates": 11, "grok_cells": 44, "sol_cells": 22, "total_cells": 66}}, "cells": cells}}
schema = {{"format_version": 1, "type": "object", "additionalProperties": False, "required": ["scores", "evidence", "coverage"], "properties": {{"scores": {{}}, "evidence": {{}}, "coverage": {{}}}}}}
module._schedule = lambda **_: schedule
module._study = lambda: SimpleNamespace(payload_bytes=lambda row: b"{{}}")
module._schema = lambda _: module.canonical(schema)
module._route = lambda route_name, queue_root: (SimpleNamespace(), SimpleNamespace(), {{"destination": "grok-subscription" if route_name == "grok_primary" else "sol-subscription", "codex_command": ["codex"]}}, {{"fixture": route_name}})
sys.argv = [str(path), "--reconciliation-manifest", "unused", "--frozen-successor", "unused", "--hanna-csv", "unused", "--output-root", {str(output)!r}, "--queue-root", "unused", "--acknowledgement-sha256", "a" * 64, "--prepare-all"]
raise SystemExit(module.main())
'''
    prepared = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True)
    assert prepared.returncode == 0, prepared.stderr
    result = json.loads(prepared.stdout)
    assert len(result) == 66 and all(row["provider_calls_made"] == row["process_launches"] == 0 for row in result)
    assert {entry.name for entry in output.iterdir()} == {f"cell-{index:02d}" for index in range(66)}
    assert all({entry.name for entry in (output / f"cell-{index:02d}").iterdir()} == executor.PREPARED for index in range(66))
    missing = subprocess.run([sys.executable, str(PACKAGE / "executor.py")], capture_output=True, text=True)
    assert missing.returncode != 0 and "required" in missing.stderr


def test_confirmation_and_existing_or_extra_roots_fail_before_contact(prepared, monkeypatch: pytest.MonkeyPatch):
    schedule, roots, queue = prepared
    executor.prepare_cell(**PATHS, cell_id="cell-00", output_root=roots, queue_root=queue, authorization_acknowledgement_sha256=ACK)
    (roots / "cell-00" / "extra.bin").write_bytes(b"x")
    with pytest.raises(ValueError):
        executor.execute_cell(**PATHS, cell_id="cell-00", output_root=roots, queue_root=queue, authorization_acknowledgement_sha256=ACK, allow_remote=True)


def test_sol_callback_ordering_postlaunch_terminal_and_no_resend(prepared, monkeypatch: pytest.MonkeyPatch):
    schedule, roots, queue = prepared; executor.prepare_cell(**PATHS, cell_id="cell-44", output_root=roots, queue_root=queue, authorization_acknowledgement_sha256=ACK)
    def invoke(**kwargs):
        (kwargs["output_dir"] / "responses").mkdir(); kwargs["before_provider_attempt"](); raise RuntimeError("after launch")
    v3 = SimpleNamespace(_load_call_codex=lambda: invoke, _expected_codex_command=lambda executable, root: [])
    def sol_route(route_name: str, queue_root: Path):
        route = _route(route_name, queue_root)[2]; evidence = _route(route_name, queue_root)[3]
        return SimpleNamespace(), v3, route, evidence
    monkeypatch.setattr(executor, "_route", sol_route)
    result = executor.execute_cell(**PATHS, cell_id="cell-44", output_root=roots, queue_root=queue, authorization_acknowledgement_sha256=ACK, allow_remote=True)
    assert result["kind"] == "reconcile_required_after_process_launch" and result["process_launches"] == 1
    with pytest.raises(ValueError, match="cannot resend"):
        executor.execute_cell(**PATHS, cell_id="cell-44", output_root=roots, queue_root=queue, authorization_acknowledgement_sha256=ACK, allow_remote=True)


def test_sol_execute_success_preserves_runner_owned_stderr(prepared, monkeypatch: pytest.MonkeyPatch):
    schedule, roots, queue = prepared
    final = executor.canonical(_answer())
    v3 = executor._sol_v4()._v3()
    root = roots / "cell-44"
    def run(*_args, **_kwargs):
        (root / "responses" / "batch-0001.attempt-0001.message.json").write_bytes(final)
        return SimpleNamespace(stdout=_lifecycle_events(final), stderr=b"", returncode=0)
    monkeypatch.setattr(v3.subprocess, "run", run)
    def route(route_name: str, queue_root: Path):
        base = _route(route_name, queue_root)[2]; base.update({"codex_cli_version": "fixture", "codex_command_identity": {}}); return _fake_sol(), v3, base, _route(route_name, queue_root)[3]
    monkeypatch.setattr(executor, "_route", route)
    executor.prepare_cell(**PATHS, cell_id="cell-44", output_root=roots, queue_root=queue, authorization_acknowledgement_sha256=ACK)
    result = executor.execute_cell(**PATHS, cell_id="cell-44", output_root=roots, queue_root=queue, authorization_acknowledgement_sha256=ACK, allow_remote=True)
    assert result.get("state") == "sol_local_lifecycle_completed", result
    assert (roots / "cell-44" / "raw-codex-stderr.bin").read_bytes() == b""


def test_grok_identity_mismatch_is_terminal(prepared, monkeypatch: pytest.MonkeyPatch):
    schedule, roots, queue = prepared; executor.prepare_cell(**PATHS, cell_id="cell-00", output_root=roots, queue_root=queue, authorization_acknowledgement_sha256=ACK)
    native = SimpleNamespace(_load_broker_class=lambda: lambda _: object(), validate_live_grok_route=lambda _: (_route("grok_primary", queue)[2], _route("grok_primary", queue)[3]))
    monkeypatch.setattr(executor, "_native", lambda: native); monkeypatch.setattr(executor, "_grok", lambda: SimpleNamespace())
    raw = json.dumps({"control": {"version": 1, "state": "completed"}, "result": {"runtime": {"requested_model": "wrong"}}}).encode()
    monkeypatch.setattr(executor, "_grok_invoke", lambda *args: (SimpleNamespace(state="completed"), raw))
    result = executor.execute_cell(**PATHS, cell_id="cell-00", output_root=roots, queue_root=queue, authorization_acknowledgement_sha256=ACK, allow_remote=True)
    assert result["kind"] == "reconcile_required_after_process_launch" and result["process_launches"] == 1


def test_wave_enforces_ten_grok_and_one_sol(prepared, monkeypatch: pytest.MonkeyPatch):
    schedule, roots, queue = prepared; active = {"grok": 0, "sol": 0, "grok_max": 0, "sol_max": 0}
    def fake(**kwargs):
        key = "grok" if kwargs["cell_id"] in {row["cell_id"] for row in schedule["cells"][:44]} else "sol"; active[key] += 1; active[f"{key}_max"] = max(active[f"{key}_max"], active[key]); time.sleep(0.01); active[key] -= 1; return {"cell_id": kwargs["cell_id"]}
    monkeypatch.setattr(executor, "execute_cell", fake)
    asyncio.run(executor.execute_wave(**PATHS, cell_ids=[row["cell_id"] for row in schedule["cells"]], output_root=roots, queue_root=queue, authorization_acknowledgement_sha256=ACK, allow_remote=True))
    assert active["grok_max"] <= 10 and active["sol_max"] == 1
