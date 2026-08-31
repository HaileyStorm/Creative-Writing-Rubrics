from __future__ import annotations

import hashlib
import importlib.util
import json
import multiprocessing
import os
import sys
import threading
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation-results" / "hbq-human-alignment-optimizer-v5-f20-nextwave-sol6-validation-exec-v3-offset-timestamps"
ACK = "a" * 64
DIMENSIONS = ("Relevance", "Coherence", "Empathy", "Surprise", "Engagement", "Complexity")
GROK_RESULT = ROOT / "evaluation-results" / "hbq-human-alignment-optimizer-v5-f20-nextwave-grok-score-result-v1" / "result.json"
INPUT_ENV = {"normalized_root": "CWR_SOL6_NORMALIZED_ROOT", "materialization_root": "CWR_SOL6_MATERIALIZATION_ROOT", "frozen_successor_path": "CWR_SOL6_FROZEN_SUCCESSOR", "hanna_csv_path": "CWR_SOL6_HANNA_CSV", "grok_execution_root": "CWR_SOL6_GROK_EXECUTION_ROOT", "grok_collector_path": "CWR_SOL6_GROK_COLLECTOR"}


def module():
    spec = importlib.util.spec_from_file_location("_sol6_validation", PACKAGE / "executor.py")
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec); sys.modules[spec.name] = value; spec.loader.exec_module(value)
    return value


def route(value):
    def identity(count):
        return {"version": 1, "artifacts": [{"index": index, "path_hash": f"{index + 1:064x}", "sha256": f"{index + 2:064x}"} for index in range(count)]}
    base, _ = value._sources()
    codex = ["codex-fixture.exe"]
    return {"name": "codex-chatgpt-gpt-5.6-sol", "model": "gpt-5.6-sol", "adapter": "codex_exec", "provider": "openai_codex", "destination": "openai_codex_chatgpt_subscription", "account_class": "subscription", "zero_charge": True, "armed": True, "health": "healthy", "reasoning_effort": "high", "identity_evidence": "requested_only", "trusted": True, "allowed_payload_classes": ["public_repo", "public_synthetic"], "codex_command": codex, "codex_command_identity": identity(1), "cli_version_command": [codex[0], "--version"], "cli_version_identity": identity(1), "auth_status_command": [codex[0], "login", "status"], "auth_status_identity": identity(1), "codex_cli_version": "fixture", "command": ["python-fixture.exe", str(base._load_v3().CODEX_ADAPTER_PATH)], "command_identity": identity(2), "cost_evidence": {"allowance_state": "available", "checked_at": "2000-09-01T00:00:00.125-06:00", "evidence_hash": "e" * 64, "expires_at": "2099-09-01T01:00:00-06:00", "kind": "subscription_included", "version": 1}, "auth_receipt_hash": "1" * 64, "timeout_seconds": 60, "capabilities": ["public_repo", "public_synthetic", "json_object", "identity_requested_only"], "cwd_policy": "broker_root", "intelligence": 100, "output_schema": value._OUTPUT_SCHEMA, "priority": 0}


class Broker:
    def __init__(self, _root): self.route = route(module())
    def _load_registry_live(self): return {"version": 1, "routes": [self.route]}
    def _validate_route(self, candidate, *, verify_command_identity, validate_current_evidence): assert candidate == self.route and verify_command_identity and validate_current_evidence


def factory(root): return Broker(root)


def real_inputs():
    missing = [name for name in INPUT_ENV.values() if not os.environ.get(name)]
    if missing:
        pytest.skip("real Sol-6 provenance inputs require explicit environment paths: " + ", ".join(missing))
    return {key: Path(os.environ[value]) for key, value in INPUT_ENV.items()}


def args(tmp_path):
    inputs = real_inputs()
    (tmp_path / "queue").mkdir()
    return {"output_root": tmp_path / "roots", **inputs, "grok_result_path": GROK_RESULT, "queue_root": tmp_path / "queue", "authorization_acknowledgement_sha256": ACK, "broker_factory": factory}


def rows(value, common):
    return value._schedule(normalized_root=common["normalized_root"], materialization_root=common["materialization_root"], frozen_successor_path=common["frozen_successor_path"], hanna_csv_path=common["hanna_csv_path"], grok_execution_root=common["grok_execution_root"], grok_collector_path=common["grok_collector_path"], grok_result_path=common["grok_result_path"])[2]


def runner(counter=None, **kwargs):
    root, prompt = kwargs["output_dir"], kwargs["prompt"]
    if counter is not None:
        with counter["lock"]: counter["active"] += 1; counter["max"] = max(counter["max"], counter["active"])
        time.sleep(0.02)
    (root / "responses").mkdir(); kwargs["before_provider_attempt"]()
    token = hashlib.sha256(prompt.encode()).hexdigest()[:12]
    answer = json.dumps({"scores": {name: 2 for name in DIMENSIONS}, "evidence": {name: "fixture" for name in DIMENSIONS}, "coverage": {name: True for name in DIMENSIONS}}, separators=(",", ":"))
    message = root / "responses" / "batch-0001.attempt-0001.message.json"; message.write_text(answer, encoding="utf-8")
    stream = [{"type": "thread.started", "thread_id": "thread-" + token}, {"type": "turn.started"}, {"type": "item.started", "item": {"id": "m1", "type": "agent_message", "text": ""}}, {"type": "item.completed", "item": {"id": "m1", "type": "agent_message", "text": answer}}, {"type": "turn.completed", "usage": {"input_tokens": 10, "output_tokens": 5}}]
    events = b"".join(json.dumps(item, separators=(",", ":")).encode() + b"\n" for item in stream)
    event_path = root / "responses" / "batch-0001.attempt-0001.events.jsonl"; event_path.write_bytes(events)
    stderr = root / "raw-codex-stderr.bin"; stderr.write_bytes(b"")
    base, _ = module()._sources()
    if counter is not None:
        with counter["lock"]: counter["active"] -= 1
    return answer, {"command": base._load_v3()._expected_codex_command(kwargs["executable"], root), "provider_artifacts": {"codex_events": {"path": event_path.relative_to(root).as_posix(), "bytes": len(events), "sha256": hashlib.sha256(events).hexdigest()}, "codex_stderr": {"path": stderr.name, "bytes": 0, "sha256": hashlib.sha256(b"").hexdigest()}}}


def semaphore_worker(lock_dir, cell_id, counter, guard):
    value = module()
    slot = value._acquire_global_slot(Path(lock_dir), cell_id)
    try:
        with guard:
            counter["active"] += 1
            counter["maximum"] = max(counter["maximum"], counter["active"])
        time.sleep(0.12)
    finally:
        with guard:
            counter["active"] -= 1
            counter["completed"] += 1
        value._release_lock(slot)


def test_global_two_slot_semaphore_is_cross_process_and_cell_claims_collide(tmp_path):
    value = module()
    locks = tmp_path / "locks"; locks.mkdir()
    first = value._claim_cell(locks, "same-cell")
    try:
        with pytest.raises(FileExistsError):
            value._claim_cell(locks, "same-cell")
    finally:
        value._release_lock(first)
    context = multiprocessing.get_context("spawn")
    with context.Manager() as manager:
        counter, guard = manager.dict(active=0, maximum=0, completed=0), manager.Lock()
        workers = [context.Process(target=semaphore_worker, args=(str(locks), f"cell-{index}", counter, guard)) for index in range(4)]
        for worker in workers: worker.start()
        for worker in workers: worker.join(20)
        assert all(worker.exitcode == 0 for worker in workers)
        assert dict(counter) == {"active": 0, "maximum": 2, "completed": 4}
    assert not list(locks.iterdir())


def test_frozen_route_requires_complete_bound_semantics(tmp_path):
    value = module(); base, _ = value._sources()
    good_route, good_evidence, v3 = base._route(tmp_path, factory)
    value._frozen_route(good_route, good_evidence, v3, require_unexpired=True)
    bad_route = dict(good_route); bad_route.pop("trusted")
    with pytest.raises(ValueError): value._frozen_route(bad_route, good_evidence, v3, require_unexpired=False)
    bad_route = dict(good_route); bad_route["allowed_payload_classes"] = ["private_repo"]
    with pytest.raises(ValueError): value._frozen_route(bad_route, good_evidence, v3, require_unexpired=False)
    bad_evidence = dict(good_evidence); bad_evidence["route_sha256"] = "0" * 64
    with pytest.raises(ValueError): value._frozen_route(good_route, bad_evidence, v3, require_unexpired=False)
    equal_route = dict(good_route); equal_cost = dict(equal_route["cost_evidence"])
    equal_cost["expires_at"] = equal_cost["checked_at"]; equal_route["cost_evidence"] = equal_cost
    equal_evidence = dict(good_evidence); equal_evidence["route_sha256"] = value.sha256(equal_route); equal_evidence["cost_evidence_expires_at"] = equal_cost["expires_at"]
    with pytest.raises(ValueError): value._frozen_route(equal_route, equal_evidence, v3, require_unexpired=False)
    unknown_route = dict(good_route); unknown_route["unknown"] = "forbidden"
    with pytest.raises(ValueError): value._frozen_route(unknown_route, good_evidence, v3, require_unexpired=False)
    bad_route = dict(good_route); bad_route["auth_status_command"] = [good_route["codex_command"][0], "logout"]
    bad_evidence = dict(good_evidence); bad_evidence["route_sha256"] = value.sha256(bad_route)
    with pytest.raises(ValueError): value._frozen_route(bad_route, bad_evidence, v3, require_unexpired=False)
    bad_route = dict(good_route); bad_route["capabilities"] = ["private_repo"]
    bad_evidence = dict(good_evidence); bad_evidence["route_sha256"] = value.sha256(bad_route)
    with pytest.raises(ValueError): value._frozen_route(bad_route, bad_evidence, v3, require_unexpired=False)
    bad_route = dict(good_route); bad_identity = dict(bad_route["command_identity"])
    bad_identity["artifacts"] = [{"index": 0, "path_hash": "a" * 64, "sha256": "b" * 64}]
    bad_route["command_identity"] = bad_identity
    bad_evidence = dict(good_evidence); bad_evidence["route_sha256"] = value.sha256(bad_route)
    bad_evidence["wrapper_command_identity_sha256"] = value.sha256(bad_identity)
    with pytest.raises(ValueError): value._frozen_route(bad_route, bad_evidence, v3, require_unexpired=False)
    bad_route = dict(good_route); bad_cost = dict(bad_route["cost_evidence"]); bad_cost["version"] = True; bad_route["cost_evidence"] = bad_cost
    bad_evidence = dict(good_evidence); bad_evidence["route_sha256"] = value.sha256(bad_route)
    with pytest.raises(ValueError): value._frozen_route(bad_route, bad_evidence, v3, require_unexpired=False)
    for field, replacement in (("zero_charge", 1), ("armed", 1), ("trusted", 1), ("intelligence", True), ("priority", False)):
        bad_route = dict(good_route); bad_route[field] = replacement
        bad_evidence = dict(good_evidence); bad_evidence["route_sha256"] = value.sha256(bad_route)
        with pytest.raises(ValueError): value._frozen_route(bad_route, bad_evidence, v3, require_unexpired=False)
    bad_route = dict(good_route); bad_schema = dict(good_route["output_schema"]); bad_schema["$schema_version"] = True
    bad_route["output_schema"] = bad_schema
    bad_evidence = dict(good_evidence); bad_evidence["route_sha256"] = value.sha256(bad_route)
    with pytest.raises(ValueError): value._frozen_route(bad_route, bad_evidence, v3, require_unexpired=False)


@pytest.mark.parametrize("timestamp", (
    "2026-09-01T00:00:00",
    "2026-09-01 00:00:00Z",
    "2026-09-01T00:00:00+0000",
    "2026-09-01T00:00:00+24:00",
    "2026-09-01T24:00:00Z",
    "2026-09-01T24:00:00+00:00",
    "2026-09-01T00:60:00Z",
    "2026-09-01T00:00:60Z",
    "2026-09-01T00:00:00. Z",
    True,
    1,
))
def test_timestamp_rejects_noncanonical_or_naive_forms(timestamp):
    with pytest.raises(ValueError):
        module()._timestamp(timestamp)


def test_timestamp_accepts_z_and_offset_forms_without_rewriting_evidence(tmp_path):
    value = module()
    assert value._timestamp("2026-09-01T00:00:00Z") == value._timestamp("2026-08-31T18:00:00-06:00")
    assert value._timestamp("2026-09-01T00:00:00.125+00:00").microsecond == 125000
    base, _ = value._sources()
    route_value, evidence, v3 = base._route(tmp_path, factory)
    route_value, evidence = value._frozen_route(route_value, evidence, v3, require_unexpired=False)
    assert route_value["cost_evidence"]["checked_at"] == "2000-09-01T00:00:00.125-06:00"
    assert evidence["cost_evidence_checked_at"] == route_value["cost_evidence"]["checked_at"]


def test_safe_path_rejects_reparse_component_when_supported(tmp_path):
    value = module(); target, link = tmp_path / "target", tmp_path / "link"
    target.mkdir()
    try:
        link.symlink_to(target, target_is_directory=True)
    except OSError:
        pytest.skip("symlink privilege unavailable")
    with pytest.raises(ValueError): value._safe_path(link, directory=True)


def test_prepare_binds_six_cross_model_payloads_without_contact(tmp_path):
    value = module(); common = args(tmp_path)
    result = value.prepare_all(**common)
    assert result["cells"] == 6 and result["groups"] == 3 and result["provider_calls_made"] == 0 and result["max_concurrency"] == 2
    selected = rows(value, common)
    assert all((tmp_path / "roots" / row["cell_id"] / "outbound-payload.json").read_bytes() == __import__("base64").b64decode(row["payload_base64"]) for row in selected)


def test_wave_enforces_two_lanes_and_project_replays_without_live_route(tmp_path):
    value = module(); common = args(tmp_path); value.prepare_all(**common)
    selected = rows(value, common)
    counter = {"active": 0, "max": 0, "lock": threading.Lock()}
    result = value.execute_wave(**common, cell_ids=[row["cell_id"] for row in selected], allow_remote=True, call_codex=lambda **kwargs: runner(counter=counter, **kwargs))
    assert len(result) == 6 and len({item["cell_id"] for item in result}) == 6 and counter["max"] == 2
    project_args = dict(common); project_args.pop("queue_root"); project_args.pop("broker_factory")
    projected = value.project(**project_args)
    assert set(projected["metrics"]) == {value.BASELINE, value.CANDIDATE}


def test_replay_rejects_payload_tampering(tmp_path):
    value = module(); common = args(tmp_path); value.prepare_all(**common)
    selected = rows(value, common)
    value.execute_wave(**common, cell_ids=[row["cell_id"] for row in selected], allow_remote=True, call_codex=runner)
    project_args = dict(common); project_args.pop("queue_root"); project_args.pop("broker_factory")
    (tmp_path / "roots" / selected[0]["cell_id"] / "outbound-payload.json").write_bytes(b"{}")
    with pytest.raises(ValueError): value.project(**project_args)
    source = (PACKAGE / "executor.py").read_text(encoding="utf-8").lower()
    assert "import dspy" not in source and "import optuna" not in source and "c:\\users" not in source


def test_project_rejects_response_event_copy_tampering(tmp_path):
    value = module(); common = args(tmp_path); value.prepare_all(**common)
    selected = rows(value, common)
    value.execute_wave(**common, cell_ids=[row["cell_id"] for row in selected], allow_remote=True, call_codex=runner)
    event_copy = tmp_path / "roots" / selected[0]["cell_id"] / "responses" / "batch-0001.attempt-0001.events.jsonl"
    event_copy.write_bytes(b'{"tampered":true}\n')
    project_args = dict(common); project_args.pop("queue_root"); project_args.pop("broker_factory")
    with pytest.raises(ValueError): value.project(**project_args)


@pytest.mark.parametrize("artifact", ("effective-settings.json", "codex-record.json", "execution-receipt.json", "zero-charge-route-proof.json"))
def test_project_rejects_coherent_lifecycle_and_route_rewrites(tmp_path, artifact):
    value = module(); common = args(tmp_path); value.prepare_all(**common)
    selected = rows(value, common)
    value.execute_wave(**common, cell_ids=[row["cell_id"] for row in selected], allow_remote=True, call_codex=runner)
    cell = tmp_path / "roots" / selected[0]["cell_id"]
    path = cell / artifact
    document = json.loads(path.read_text(encoding="utf-8"))
    if artifact == "effective-settings.json":
        document["provider_attested"] = True
        receipt = cell / "execution-receipt.json"; receipt_value = json.loads(receipt.read_text(encoding="utf-8"))
        receipt_value["effective_settings_sha256"] = value.sha256(value.canonical(document))
        receipt.write_bytes(value.canonical(receipt_value))
    elif artifact == "codex-record.json":
        document["command"] = ["wrong-command"]
    elif artifact == "execution-receipt.json":
        document["identity"]["session_id"] = "coherently-wrong-session"
    else:
        document["route"]["trusted"] = False
        document["route_evidence"]["route_sha256"] = value.sha256(document["route"])
        prepared = cell / "prepared.json"; prepared_value = json.loads(prepared.read_text(encoding="utf-8"))
        prepared_value["route_evidence"] = document["route_evidence"]
        prepared.write_bytes(value.canonical(prepared_value))
    path.write_bytes(value.canonical(document))
    project_args = dict(common); project_args.pop("queue_root"); project_args.pop("broker_factory")
    with pytest.raises(ValueError): value.project(**project_args)
