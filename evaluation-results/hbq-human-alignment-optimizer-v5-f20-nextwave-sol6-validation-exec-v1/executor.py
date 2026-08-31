#!/usr/bin/env python3
"""Six-cell, development-only Sol validation for the baseline and nextwave-08."""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType
from typing import Any, Callable, Mapping

HERE = Path(__file__).resolve().parent
STUDY_ID = "hbq-human-alignment-optimizer-v5-f20-nextwave-sol6-validation-exec-v1"
BASELINE = "candidate-102cc7f06c9a99a7"
CANDIDATE = "normalized-nextwave-08-conservative-hybrid"
DIMENSIONS = ("Relevance", "Coherence", "Empathy", "Surprise", "Engagement", "Complexity")
SOL_EXECUTOR = HERE.parent / "hbq-human-alignment-optimizer-v5-grok-descriptive-sol-validation-exec-v1" / "executor.py"
SOL_EXECUTOR_SHA256 = "7f8a9934bb8fea18ab4cba315f97ebe46e3b6e1bc04a1f4bfb6f2816f76daebd"
GROK_SCORER = HERE.parent / "hbq-human-alignment-optimizer-v5-f20-nextwave-grok-score-exec-v1" / "executor.py"
GROK_SCORER_SHA256 = "c1641089073c07d5906d31685101dedbd5cdc936568baeb039a612f85b0f7539"
GROK_SCORER_COMMIT = "6cfd64e8db03b06c70d39d79ca4aac24ba498232"
GROK_RESULT_COMMIT = "3b8202c20eed82f431e1a37024e547cfea1fe6f7"
MAX_CONCURRENCY = 2
_wave_lock = threading.Lock()
_ROUTE_KEYS = frozenset({"name", "model", "adapter", "provider", "destination", "account_class", "zero_charge", "armed", "health", "reasoning_effort", "identity_evidence", "trusted", "allowed_payload_classes", "codex_command", "codex_command_identity", "cli_version_identity", "auth_status_identity", "codex_cli_version", "command", "command_identity", "cost_evidence", "auth_receipt_hash", "timeout_seconds"})
_EVIDENCE_KEYS = frozenset({"route_name", "route_sha256", "registry_sha256", "cost_evidence_hash", "auth_receipt_hash", "cost_evidence_checked_at", "cost_evidence_expires_at", "wrapper_command_identity_sha256", "codex_command_identity_sha256", "cli_version_identity_sha256", "auth_status_identity_sha256", "codex_cli_version", "codex_adapter_sha256"})
_SLOT_WAIT_SECONDS = 120.0


def canonical(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")


def sha256(value: bytes | Any) -> str:
    return hashlib.sha256(value if isinstance(value, bytes) else canonical(value)).hexdigest()


def stable(path: Path) -> bytes:
    path = _safe_path(path, directory=False)
    before = os.lstat(path)
    with path.open("rb") as handle:
        opened = os.fstat(handle.fileno())
        raw = handle.read()
        after = os.fstat(handle.fileno())
    if (before.st_dev, before.st_ino, before.st_size) != (opened.st_dev, opened.st_ino, opened.st_size) or (opened.st_dev, opened.st_ino, opened.st_size) != (after.st_dev, after.st_ino, after.st_size):
        raise ValueError("stable read drift")
    return raw


def _plain(path: Path, directory: bool | None = None) -> None:
    info = os.lstat(path)
    if stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)):
        raise ValueError("unsafe/reparsed path")
    if directory is not None and stat.S_ISDIR(info.st_mode) != directory:
        raise ValueError("unexpected path type")


def _safe_path(path: Path, *, directory: bool | None = None) -> Path:
    absolute = Path(os.path.abspath(path))
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current /= part
        if not current.exists():
            raise ValueError("path does not exist")
        _plain(current, directory=current != absolute or directory)
    return absolute.resolve(strict=True)


def _load(path: Path, digest: str, name: str) -> ModuleType:
    raw = stable(path)
    if not re.fullmatch(r"[0-9a-f]{64}", digest) or sha256(raw) != digest:
        raise ValueError("pinned dependency drifted")
    module = ModuleType(name)
    module.__file__ = str(path)
    sys.modules[name] = module
    try:
        exec(compile(raw, str(path), "exec"), module.__dict__)
    finally:
        sys.modules.pop(name, None)
    if stable(path) != raw:
        raise ValueError("pinned dependency changed during load")
    return module


def _sources() -> tuple[ModuleType, ModuleType]:
    return _load(SOL_EXECUTOR, SOL_EXECUTOR_SHA256, "_sol6_base"), _load(GROK_SCORER, GROK_SCORER_SHA256, "_sol6_grok")


def _schedule(*, normalized_root: Path, materialization_root: Path, frozen_successor_path: Path, hanna_csv_path: Path, grok_execution_root: Path, grok_collector_path: Path, grok_result_path: Path) -> tuple[ModuleType, dict[str, Any], tuple[dict[str, Any], ...], dict[str, str]]:
    base, grok = _sources()
    source, schedule = grok.schedule(normalized_root=normalized_root, materialization_root=materialization_root, frozen_successor_path=frozen_successor_path, hanna_csv_path=hanna_csv_path)
    execution_root = _safe_path(grok_execution_root, directory=True)
    collector_raw, result_raw = stable(grok_collector_path), stable(grok_result_path)
    persisted_schedule = stable(execution_root / "schedule.json")
    blob = subprocess.run(["git", "-C", str(HERE.parents[1]), "show", f"{GROK_RESULT_COMMIT}:evaluation-results/hbq-human-alignment-optimizer-v5-f20-nextwave-grok-score-result-v1/result.json"], capture_output=True, check=False)
    if blob.returncode != 0 or blob.stdout != result_raw:
        raise ValueError("published Grok result is not the exact pinned Git blob")
    result = json.loads(result_raw.decode("utf-8"))
    source_execution = result.get("source_execution", {})
    if (persisted_schedule != canonical(schedule) or sha256(persisted_schedule) != source_execution.get("schedule_file_sha256")
            or sha256(collector_raw) != source_execution.get("collector_sha256")
            or source_execution.get("executor_commit") != GROK_SCORER_COMMIT
            or source_execution.get("executor_sha256") != GROK_SCORER_SHA256
            or result.get("study_id") != "hbq-human-alignment-optimizer-v5-f20-nextwave-grok-score-exec-v1"
            or result.get("publication_geometry") != {"candidate_observations": 11, "cells": 33, "dimensions": 6, "prompt_groups": 3}):
        raise ValueError("completed Grok scorer/result binding drifted")
    collector = json.loads(collector_raw.decode("utf-8"))
    if collector.get("study_id") != result["study_id"] or len(collector.get("cells", [])) != 33:
        raise ValueError("completed Grok collector geometry drifted")
    projected = grok.descriptive_project(collector_path=grok_collector_path, output_root=execution_root, normalized_root=normalized_root, materialization_root=materialization_root, frozen_successor_path=frozen_successor_path, hanna_csv_path=hanna_csv_path)
    if projected.get("metrics") != result.get("metrics"):
        raise ValueError("completed Grok collector/result projection drifted")
    analyzer = source._analyze()
    token = analyzer._study().prepare_grok_schedule(materialization_root=materialization_root, frozen_successor_path=frozen_successor_path, hanna_csv_path=hanna_csv_path)
    targets = analyzer._targets(token)
    selected = [row for row in schedule["cells"] if row["candidate_id"] in {BASELINE, CANDIDATE}]
    if len(selected) != 6 or {row["candidate_id"] for row in selected} != {BASELINE, CANDIDATE}:
        raise ValueError("required two-candidate three-group geometry drifted")
    rows = []
    for row in selected:
        target = targets.get(row["item_id"])
        raw = base64.b64decode(row["payload_base64"], validate=True)
        cell_root = execution_root / row["cell_id"]
        if not isinstance(target, Mapping) or sha256(raw) != row["payload_sha256"] or stable(cell_root / "outbound-payload.json") != raw:
            raise ValueError("Grok scorer source binding drifted")
        rows.append({"cell_id": "sol6-" + row["cell_id"], "source_cell_id": row["cell_id"], "candidate_id": row["candidate_id"], "prompt_group_id": row["prompt_group_id"], "item_id": row["item_id"], "story_id": row["item_id"], "payload_sha256": row["payload_sha256"], "payload_base64": row["payload_base64"], "target": {key: float(target[key]) for key in DIMENSIONS}})
    rows.sort(key=lambda row: row["cell_id"])
    if len({row["cell_id"] for row in rows}) != 6 or len({row["payload_sha256"] for row in rows}) != 6:
        raise ValueError("six-cell byte identity geometry drifted")
    return base, schedule, tuple(rows), {"collector_sha256": sha256(collector_raw), "result_sha256": sha256(result_raw), "result_internal_sha256": str(result["result_internal_sha256"])}


def _configure(base: ModuleType, rows: tuple[dict[str, Any], ...], source_schedule: Mapping[str, Any], bindings: Mapping[str, str]) -> None:
    base.STUDY_ID = STUDY_ID
    base.ROWS = rows
    base.PUBLIC_RESULT_COMMIT = GROK_RESULT_COMMIT
    base.SOURCE_RESULT_FILE_SHA256 = bindings["result_sha256"]
    base.SOURCE_EXECUTOR_COMMIT = GROK_SCORER_COMMIT
    base.SOURCE_EXECUTOR_SHA256 = GROK_SCORER_SHA256
    base.SCHEDULE_SHA256 = source_schedule["schedule_sha256"]
    base.COLLECTOR_SHA256 = bindings["collector_sha256"]
    base.ALIAS_MANIFEST_SHA256 = "0" * 64
    base.RESULT_INTERNAL_SHA256 = bindings["result_internal_sha256"]
    base._validate_target = lambda row, _path: dict(row["target"])
    original_prepared = base._prepared
    def prepared(row, payload, schema, target, route, evidence, acknowledgement):
        files = original_prepared(row, payload, schema, target, route, evidence, acknowledgement)
        value = json.loads(files["prepared.json"].decode("utf-8"))
        source = dict(value["source"])
        source.pop("alias_manifest_sha256", None)
        source["completed_grok_result_sha256"] = bindings["result_sha256"]
        source["completed_grok_result_internal_sha256"] = bindings["result_internal_sha256"]
        value["source"] = source
        files["prepared.json"] = base.canonical(value)
        return files
    base._prepared = prepared


def _hex(value: Any) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _timestamp(value: Any) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError("route cost-evidence timestamp is invalid")
    try:
        return datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as error:
        raise ValueError("route cost-evidence timestamp is invalid") from error


def _identity(value: Any) -> bool:
    if not isinstance(value, Mapping) or set(value) != {"version", "artifacts"} or type(value["version"]) is not int or value["version"] != 1:
        return False
    artifacts = value["artifacts"]
    return (isinstance(artifacts, list) and bool(artifacts) and all(isinstance(item, Mapping) and set(item) == {"path", "sha256"}
            and isinstance(item["path"], str) and item["path"] and _hex(item["sha256"]) for item in artifacts))


def _frozen_route(route: Any, evidence: Any, v3: ModuleType, *, require_unexpired: bool) -> tuple[dict[str, Any], dict[str, Any]]:
    """Validate persisted route proof without treating later expiry as historical drift."""
    if not isinstance(route, Mapping) or not isinstance(evidence, Mapping) or set(route) != _ROUTE_KEYS or set(evidence) != _EVIDENCE_KEYS:
        raise ValueError("frozen route proof format drifted")
    route, evidence = dict(route), dict(evidence)
    required = {"name": "codex-chatgpt-gpt-5.6-sol", "model": "gpt-5.6-sol", "adapter": "codex_exec", "provider": "openai_codex", "destination": "openai_codex_chatgpt_subscription", "account_class": "subscription", "zero_charge": True, "armed": True, "health": "healthy", "reasoning_effort": "high", "identity_evidence": "requested_only", "trusted": True, "allowed_payload_classes": ["public_repo"]}
    if any(route.get(key) != expected for key, expected in required.items()):
        raise ValueError("frozen route semantics drifted")
    if (not isinstance(route["codex_command"], list) or len(route["codex_command"]) != 1 or not isinstance(route["codex_command"][0], str) or not route["codex_command"][0]
            or not isinstance(route["command"], list) or len(route["command"]) != 2 or not all(isinstance(item, str) and item for item in route["command"])
            or route["command"][1] != str(v3.CODEX_ADAPTER_PATH) or type(route["timeout_seconds"]) is not int or route["timeout_seconds"] <= 0
            or not isinstance(route["codex_cli_version"], str) or not route["codex_cli_version"] or not _hex(route["auth_receipt_hash"])
            or not all(_identity(route[key]) for key in ("command_identity", "codex_command_identity", "cli_version_identity", "auth_status_identity"))):
        raise ValueError("frozen route command identity drifted")
    cost = route["cost_evidence"]
    if not isinstance(cost, Mapping) or set(cost) != {"evidence_hash", "checked_at", "expires_at"} or not _hex(cost["evidence_hash"]):
        raise ValueError("frozen route cost evidence drifted")
    checked_at, expires_at = _timestamp(cost["checked_at"]), _timestamp(cost["expires_at"])
    if checked_at >= expires_at or (require_unexpired and not (checked_at <= datetime.now(timezone.utc) < expires_at)):
        raise ValueError("frozen route cost evidence is not currently valid")
    identity_hashes = {"wrapper_command_identity_sha256": sha256(route["command_identity"]), "codex_command_identity_sha256": sha256(route["codex_command_identity"]), "cli_version_identity_sha256": sha256(route["cli_version_identity"]), "auth_status_identity_sha256": sha256(route["auth_status_identity"])}
    if (evidence["route_name"] != route["name"] or evidence["route_sha256"] != sha256(route) or evidence["cost_evidence_hash"] != cost["evidence_hash"]
            or evidence["auth_receipt_hash"] != route["auth_receipt_hash"] or evidence["cost_evidence_checked_at"] != cost["checked_at"] or evidence["cost_evidence_expires_at"] != cost["expires_at"]
            or evidence["codex_cli_version"] != route["codex_cli_version"] or evidence["codex_adapter_sha256"] != v3.CODEX_ADAPTER_SHA256
            or any(evidence[key] != expected for key, expected in identity_hashes.items()) or not _hex(evidence["registry_sha256"])):
        raise ValueError("frozen route evidence binding drifted")
    return route, evidence


def _disjoint(output_root: Path, *sources: Path) -> None:
    output_candidate = Path(os.path.abspath(output_root))
    output_parent = _safe_path(output_candidate.parent, directory=True)
    output = output_parent / output_candidate.name
    for source in sources:
        source = _safe_path(source)
        if output == source or output in source.parents or source in output.parents:
            raise ValueError("output root must be disjoint from every source and queue root")


def _acquire_global_slot(locks: Path, cell_id: str) -> Path:
    deadline = time.monotonic() + _SLOT_WAIT_SECONDS
    while time.monotonic() < deadline:
        for slot in range(MAX_CONCURRENCY):
            path = locks / f"slot-{slot}.lock"
            try:
                with path.open("x", encoding="ascii") as handle:
                    handle.write(cell_id)
                return path
            except FileExistsError:
                continue
        time.sleep(0.01)
    raise TimeoutError("global Sol two-slot semaphore did not become available")


def _claim_cell(locks: Path, cell_id: str) -> Path:
    path = locks / (cell_id + ".lock")
    with path.open("x", encoding="ascii") as handle:
        handle.write(cell_id)
    return path


def _release_lock(path: Path | None) -> None:
    if path is not None and path.exists():
        _plain(path, directory=False)
        path.unlink()


def prepare_all(*, output_root: Path, normalized_root: Path, materialization_root: Path, frozen_successor_path: Path, hanna_csv_path: Path, grok_execution_root: Path, grok_collector_path: Path, grok_result_path: Path, queue_root: Path, authorization_acknowledgement_sha256: str, broker_factory: Callable[[Path], Any] | None = None) -> dict[str, Any]:
    _disjoint(output_root, normalized_root, materialization_root, frozen_successor_path, hanna_csv_path, grok_execution_root, grok_collector_path, grok_result_path, queue_root, HERE.parents[1])
    if Path(output_root).exists():
        raise ValueError("fresh output root required")
    base, schedule, rows, bindings = _schedule(normalized_root=normalized_root, materialization_root=materialization_root, frozen_successor_path=frozen_successor_path, hanna_csv_path=hanna_csv_path, grok_execution_root=grok_execution_root, grok_collector_path=grok_collector_path, grok_result_path=grok_result_path)
    _configure(base, rows, schedule, bindings)
    route, evidence, v3 = base._route(queue_root, broker_factory)
    route, evidence = _frozen_route(route, evidence, v3, require_unexpired=True)
    Path(output_root).mkdir(parents=True)
    for row in rows:
        root = Path(output_root) / row["cell_id"]
        root.mkdir()
        payload = base64.b64decode(row["payload_base64"], validate=True)
        schema = base.canonical(json.loads(payload.decode("utf-8"))["response_schema"])
        for name, raw in base._prepared(row, payload, schema, row["target"], route, evidence, authorization_acknowledgement_sha256).items():
            base._write_new(root / name, raw)
    return {"study_id": STUDY_ID, "cells": 6, "groups": 3, "state": "prepared_no_contact", "provider_calls_made": 0, "process_launches": 0, "max_concurrency": 2, "authority": "Sol_validation_only"}


def _execute_one(*, output_root: Path, cell_id: str, normalized_root: Path, materialization_root: Path, frozen_successor_path: Path, hanna_csv_path: Path, grok_execution_root: Path, grok_collector_path: Path, grok_result_path: Path, queue_root: Path, authorization_acknowledgement_sha256: str, allow_remote: bool, broker_factory: Callable[[Path], Any] | None = None, call_codex=None, _frozen=None) -> dict[str, Any]:
    base, schedule, rows, bindings = _frozen or _schedule(normalized_root=normalized_root, materialization_root=materialization_root, frozen_successor_path=frozen_successor_path, hanna_csv_path=hanna_csv_path, grok_execution_root=grok_execution_root, grok_collector_path=grok_collector_path, grok_result_path=grok_result_path)
    _configure(base, rows, schedule, bindings)
    return base.execute_one(output_root=output_root, cell_id=cell_id, queue_root=queue_root, authorization_acknowledgement_sha256=authorization_acknowledgement_sha256, allow_remote=allow_remote, hanna_csv_path=hanna_csv_path, broker_factory=broker_factory, call_codex=call_codex)


def execute_wave(*, cell_ids: list[str], **kwargs: Any) -> list[dict[str, Any]]:
    if not isinstance(cell_ids, list) or len(cell_ids) != 6 or len(set(cell_ids)) != 6:
        raise ValueError("execute-wave requires exactly six distinct cells")
    frozen = _schedule(normalized_root=kwargs["normalized_root"], materialization_root=kwargs["materialization_root"], frozen_successor_path=kwargs["frozen_successor_path"], hanna_csv_path=kwargs["hanna_csv_path"], grok_execution_root=kwargs["grok_execution_root"], grok_collector_path=kwargs["grok_collector_path"], grok_result_path=kwargs["grok_result_path"])
    _base, _schedule_value, rows, _bindings = frozen
    if set(cell_ids) != {row["cell_id"] for row in rows}:
        raise ValueError("execute-wave cell IDs do not exactly equal the frozen six-cell schedule")
    output_root = Path(kwargs["output_root"])
    _disjoint(output_root, kwargs["normalized_root"], kwargs["materialization_root"], kwargs["frozen_successor_path"], kwargs["hanna_csv_path"], kwargs["grok_execution_root"], kwargs["grok_collector_path"], kwargs["grok_result_path"], kwargs["queue_root"], HERE.parents[1])
    _safe_path(output_root, directory=True)
    locks = output_root.parent / ("." + output_root.name + ".sol6-cell-locks")
    locks.mkdir(exist_ok=True)
    _plain(locks, directory=True)

    def run(cell_id: str) -> dict[str, Any]:
        lock: Path | None = None
        slot: Path | None = None
        try:
            lock = _claim_cell(locks, cell_id)
            slot = _acquire_global_slot(locks, cell_id)
            return _execute_one(cell_id=cell_id, _frozen=frozen, **kwargs)
        finally:
            _release_lock(slot)
            _release_lock(lock)
    try:
        with _wave_lock, ThreadPoolExecutor(max_workers=MAX_CONCURRENCY) as pool:
            return list(pool.map(run, cell_ids))
    finally:
        if locks.exists() and not any(locks.iterdir()):
            locks.rmdir()


def project(*, output_root: Path, normalized_root: Path, materialization_root: Path, frozen_successor_path: Path, hanna_csv_path: Path, grok_execution_root: Path, grok_collector_path: Path, grok_result_path: Path, authorization_acknowledgement_sha256: str) -> dict[str, Any]:
    _disjoint(output_root, normalized_root, materialization_root, frozen_successor_path, hanna_csv_path, grok_execution_root, grok_collector_path, grok_result_path, HERE.parents[1])
    root = _safe_path(output_root, directory=True)
    base, schedule, rows, bindings = _schedule(normalized_root=normalized_root, materialization_root=materialization_root, frozen_successor_path=frozen_successor_path, hanna_csv_path=hanna_csv_path, grok_execution_root=grok_execution_root, grok_collector_path=grok_collector_path, grok_result_path=grok_result_path)
    _configure(base, rows, schedule, bindings)
    if {path.name for path in root.iterdir()} != {row["cell_id"] for row in rows}:
        raise ValueError("output-root inventory drifted")
    groups = {row["prompt_group_id"] for row in rows}
    values = {BASELINE: {}, CANDIDATE: {}}
    identities: set[tuple[str, str, str]] = set()
    persisted_route = persisted_evidence = None
    for row in rows:
        cell = root / row["cell_id"]
        base._inventory(cell, completed=True)
        prepared = base._canonical_json(cell / "prepared.json", "prepared")
        disclosure = base._canonical_json(cell / "disclosure.json", "disclosure")
        acknowledgement = base._canonical_json(cell / "authorization-acknowledgement.json", "acknowledgement")
        proof = base._canonical_json(cell / "zero-charge-route-proof.json", "route proof")
        target_file = base._canonical_json(cell / "target-vector.json", "target vector")
        intent = base._canonical_json(cell / "launch-intent.json", "launch intent")
        receipt = base._canonical_json(cell / "execution-receipt.json", "receipt")
        payload = base.stable(cell / "outbound-payload.json")
        schema = base.stable(cell / "response-schema.json")
        final = base.stable(cell / "raw-codex-final-response.bin")
        events = base.stable(cell / "raw-codex-events.bin")
        response_events = base.stable(cell / "responses" / "batch-0001.attempt-0001.events.jsonl")
        stderr = base.stable(cell / "raw-codex-stderr.bin")
        record = base._canonical_json(cell / "codex-record.json", "Codex record")
        settings = base._canonical_json(cell / "effective-settings.json", "effective settings")
        v3 = base._load_v3()
        projection = v3._codex_event_projection(events, v3._load_parse_codex_events())
        answer = base._validate_answer(base._json(cell / "raw-codex-final-response.bin", "final response"))
        identity = receipt.get("identity", {})
        key = (identity.get("thread_id"), identity.get("session_id"), identity.get("contact_id"))
        route, evidence = proof.get("route"), prepared.get("route_evidence")
        route, evidence = _frozen_route(route, evidence, v3, require_unexpired=False)
        expected = base._prepared(row, payload, schema, row["target"], route, evidence, authorization_acknowledgement_sha256)
        expected_settings = {"requested_model": "gpt-5.6-sol", "local_effective_model": "gpt-5.6-sol", "requested_reasoning_effort": "high", "local_effective_reasoning_effort": "high", "tools_enabled": False, "web_search_enabled": False, "subagents_enabled": False, "provider_attested": False, "event_projection": projection, "route_name": route["name"], "codex_command_identity": route["codex_command_identity"]}
        expected_record = {"command": v3._expected_codex_command(route["codex_command"][0], cell), "provider_artifacts": {"codex_events": {"path": "responses/batch-0001.attempt-0001.events.jsonl", "bytes": len(events), "sha256": sha256(events)}, "codex_stderr": {"path": "raw-codex-stderr.bin", "bytes": len(stderr), "sha256": sha256(stderr)}}}
        expected_identity = {"provider": "openai_codex", "route_name": route["name"], "requested_model": "gpt-5.6-sol", "requested_reasoning_effort": "high", "effective_model": "gpt-5.6-sol", "provider_reported_model": None, "reasoning_attested": False, "transport_identity": "codex_chatgpt_subscription_exec_tool_free_v3", "native_endpoint_contact_cardinality": "unproven", "thread_id": projection.get("thread_id"), "session_id": f"local-codex-thread-session:{projection.get('thread_id')}", "contact_id": f"unproven-native-endpoint-contact-for-local-thread:{projection.get('thread_id')}"}
        expected_intent = {"format_version": 1, "study_id": STUDY_ID, "kind": "process_launch_intent_not_native_contact", "cell_id": row["cell_id"], "prepared_sha256": sha256(prepared)}
        expected_receipt = {"format_version": 1, "study_id": STUDY_ID, "kind": "local_codex_lifecycle_receipt", "cell": dict(row), "process_launches": 1, "provider_calls_made": None, "native_endpoint_contact_cardinality": "unproven", "internal_retry_cardinality": "unproven", "request_sha256": sha256(payload), "response_schema_sha256": sha256(schema), "raw_events_sha256": sha256(events), "raw_stderr_sha256": sha256(stderr), "final_response_sha256": sha256(final), "route_evidence": evidence, "effective_settings_sha256": sha256(settings), "launch_intent_sha256": sha256(base.stable(cell / "launch-intent.json")), "identity": expected_identity, "human_score_projection": answer}
        if persisted_route is None:
            persisted_route, persisted_evidence = route, evidence
        if (route != persisted_route or evidence != persisted_evidence
                or any(base.stable(cell / name) != raw for name, raw in expected.items())
                or proof.get("route") != route or proof.get("route_evidence") != evidence
                or acknowledgement.get("acknowledgement_sha256") != authorization_acknowledgement_sha256 or target_file.get("target") != row["target"]
                or intent != expected_intent or sha256(payload) != row["payload_sha256"] or prepared.get("cell") != row
                or settings != expected_settings or record != expected_record or receipt != expected_receipt
                or final != base.stable(cell / "responses" / "batch-0001.attempt-0001.message.json") or response_events != events
                or projection.get("completed_agent_message_text", "").encode() != final or not all(isinstance(value, str) and value for value in key) or key in identities):
            raise ValueError("receipt/source/identity binding drifted")
        identities.add(key)
        values[row["candidate_id"]][row["prompt_group_id"]] = sum(abs(answer["scores"][dimension] - row["target"][dimension]) for dimension in DIMENSIONS) / len(DIMENSIONS)
    if set(values) != {BASELINE, CANDIDATE} or any(set(item) != groups or len(item) != 3 for item in values.values()):
        raise ValueError("equal-group six-cell geometry is incomplete")
    metrics = {candidate: sum(group_values.values()) / 3 for candidate, group_values in values.items()}
    return {"format_version": 1, "study_id": STUDY_ID, "kind": "three_group_equal_group_sol_mae_descriptive_only", "metrics": metrics, "group_mae": values, "native_endpoint_contact_cardinality": "unproven", "authority": {"selection": "none", "confirmation": "unopened", "generalization": "none", "promotion": "none", "runtime": "none", "endpoint_pooling": "forbidden"}, "claim": "DESCRIPTIVE_SOL_VALIDATION_ONLY; no Grok/Sol pooling, selection, generalization, promotion, or runtime claim"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--prepare", action="store_true"); mode.add_argument("--execute-wave", action="store_true"); mode.add_argument("--project", action="store_true")
    for name in ("output-root", "normalized-root", "materialization-root", "frozen-successor", "hanna-csv", "grok-execution-root", "grok-collector", "grok-result", "queue-root"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--authorization-acknowledgement-sha256", required=True); parser.add_argument("--allow-remote", action="store_true")
    args = parser.parse_args(argv)
    common = {"output_root": args.output_root, "normalized_root": args.normalized_root, "materialization_root": args.materialization_root, "frozen_successor_path": args.frozen_successor, "hanna_csv_path": args.hanna_csv, "grok_execution_root": args.grok_execution_root, "grok_collector_path": args.grok_collector, "grok_result_path": args.grok_result, "queue_root": args.queue_root, "authorization_acknowledgement_sha256": args.authorization_acknowledgement_sha256}
    if args.prepare:
        if args.allow_remote: parser.error("prepare forbids remote execution")
        result = prepare_all(**common)
    elif args.execute_wave:
        if not args.allow_remote: parser.error("execute-wave requires explicit remote authorization")
        _base, _schedule_value, rows, _bindings = _schedule(normalized_root=args.normalized_root, materialization_root=args.materialization_root, frozen_successor_path=args.frozen_successor, hanna_csv_path=args.hanna_csv, grok_execution_root=args.grok_execution_root, grok_collector_path=args.grok_collector, grok_result_path=args.grok_result)
        result = execute_wave(**common, cell_ids=[row["cell_id"] for row in rows], allow_remote=True)
    else:
        if args.allow_remote: parser.error("project forbids remote execution")
        project_common = dict(common); project_common.pop("queue_root")
        result = project(**project_common)
    print(canonical(result).decode(), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
