#!/usr/bin/env python3
"""Provider-free replay of the full lean HANNA collector artifact chain."""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from pathlib import Path
from types import ModuleType
from typing import Any, Mapping


HERE = Path(__file__).resolve().parent
STUDY_ID = "hbq-human-alignment-optimizer-v4-lean-training-verifier-v1"
CONTRACT_PATH = HERE / "study-contract.json"
CONTRACT_SHA256 = "20ea7d2e7a9bc59ca01227f34fd9c441b6ccb902c2d02aa41256df69f1bae27b"
COLLECTOR_PATH = HERE.parent / "hbq-human-alignment-optimizer-v4-lean-training-exec-v1" / "executor.py"
COLLECTOR_SHA256 = "c90fb4b40d85e70d3a5ae68ce509533bb2cee214e58bf89b88ffd22f0b2cf4fc"
COLLECTOR_CONTRACT_PATH = COLLECTOR_PATH.with_name("study-contract.json")
COLLECTOR_CONTRACT_SHA256 = "b608ae2313bca80289f7edc629ea3656f0394f7c76ec559adb35c73ecef7c27b"
OPTIMIZER_PATH = HERE.parent / "hbq-human-alignment-optimizer-v4-lean-development-v1" / "optimizer.py"
OPTIMIZER_SHA256 = "cbbf3b51a875ff4c0c1b72379e089cbd8f0a76cb2a0da5da74f31a13b4de377f"
NATIVE_PATH = HERE.parent / "hbq-human-alignment-optimizer-v4-native-subscription-v1" / "executor.py"
NATIVE_SHA256 = "6d93f69216d62bd0847aa6b338b6e2360587c82608669f78fbad245a34ba1c49"
EXEC_V1_PATH = HERE.parent / "hbq-human-alignment-optimizer-v4-native-subscription-exec-v1" / "executor.py"
EXEC_V1_SHA256 = "5d2bd6871fe2013b8af5e166d89eeb020ff98889ce30494dd8889f7bee2d942f"
EXEC_V3_PATH = HERE.parent / "hbq-human-alignment-optimizer-v4-native-subscription-exec-v3" / "executor.py"
EXEC_V3_SHA256 = "cea177b5185a84b682bd5271ae7384cd7742add872d31b45227433d72c7f7e90"

REFERENCE_KEYS = frozenset({"cell_id", "execution_root"})
MANIFEST_KEYS = frozenset({"format_version", "study_id", "kind", "collector_executor_sha256", "collector_contract_sha256", "optimizer_sha256", "native_executor_sha256", "schedule_sha256", "stage", "cells"})
LAUNCH_KEYS = frozenset({"format_version", "study_id", "kind", "cell_id", "prepared_sha256", "request_sha256", "response_schema_sha256", "outbound_payload_sha256", "collector_executor_sha256", "native_contact_proven"})
RECEIPT_KEYS = frozenset({"format_version", "study_id", "kind", "cell", "schedule_sha256", "outbound_payload_sha256", "request_sha256", "response_schema_sha256", "prepared_sha256", "launch_intent_sha256", "route_evidence", "provider_calls_made", "process_launches", "identity", "collector_executor_sha256", "native_response_sha256", "result_sha256", "native_contact_proven", "native_endpoint_contact_cardinality"})
RESULT_KEYS = frozenset({"format_version", "study_id", "kind", "cell_id", "identity", "identity_sha256", "native_response_sha256", "effective_settings_sha256", "provider_calls_made", "process_launches"})
PREPARED_FILES = frozenset({"outbound-payload.json", "prompt-request.bin", "response-schema.json", "disclosure.json", "authorization-acknowledgement.json", "zero-charge-route-proof.json", "prepared.json"})
GROK_FILES = PREPARED_FILES | frozenset({"launch-intent.json", "raw-grok-envelope.bin", "grok-record.json", "effective-settings.json", "execution-receipt.json", "result.json", "responses"})
SOL_FILES = PREPARED_FILES | frozenset({"launch-intent.json", "raw-codex-events.bin", "raw-codex-final-response.bin", "raw-codex-stderr.bin", "codex-record.json", "effective-settings.json", "execution-receipt.json", "result.json", "responses"})
GROK_RESPONSE_FILES = frozenset({"batch-0001.attempt-0001.prompt.txt", "batch-0001.attempt-0001.grok.envelope.json"})
SOL_RESPONSE_FILES = frozenset({"batch-0001.attempt-0001.events.jsonl", "batch-0001.attempt-0001.message.json"})


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _plain(path: Path, *, directory: bool | None = None) -> None:
    info = os.lstat(path)
    if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400):
        raise ValueError(f"HANNA lean verifier path is reparsed: {path}")
    if directory is True and not stat.S_ISDIR(info.st_mode):
        raise ValueError(f"HANNA lean verifier expected directory: {path}")
    if directory is False and not stat.S_ISREG(info.st_mode):
        raise ValueError(f"HANNA lean verifier expected plain file: {path}")


def _stable_bytes(path: Path) -> bytes:
    absolute, current = Path(os.path.abspath(path)), Path(Path(os.path.abspath(path)).anchor)
    for part in absolute.parts[1:]:
        current /= part
        _plain(current)
    _plain(absolute, directory=False)
    before = os.lstat(absolute)
    with absolute.open("rb") as handle:
        opened = os.fstat(handle.fileno())
        if (before.st_dev, before.st_ino, before.st_size) != (opened.st_dev, opened.st_ino, opened.st_size):
            raise ValueError("HANNA lean verifier file identity drifted")
        raw = handle.read()
        after = os.fstat(handle.fileno())
        if (opened.st_dev, opened.st_ino, opened.st_size) != (after.st_dev, after.st_ino, after.st_size):
            raise ValueError("HANNA lean verifier file changed during read")
    return raw


def _object(path: Path, label: str) -> dict[str, Any]:
    try:
        raw, value = _stable_bytes(path), None
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"HANNA lean verifier {label} is unavailable or invalid") from error
    if not isinstance(value, dict) or canonical(value) != raw:
        raise ValueError(f"HANNA lean verifier {label} is noncanonical")
    return value


def _load(path: Path, expected: str, name: str) -> ModuleType:
    raw = _stable_bytes(path)
    if sha256_bytes(raw) != expected:
        raise ValueError(f"HANNA lean verifier pinned {path.name} bytes drifted")
    module = ModuleType(name); module.__file__ = str(path)
    exec(compile(raw, str(path), "exec"), module.__dict__)
    if sha256_bytes(_stable_bytes(path)) != expected:
        raise ValueError(f"HANNA lean verifier pinned {path.name} changed during load")
    return module


def contract() -> dict[str, Any]:
    value = _object(CONTRACT_PATH, "study contract")
    if sha256_bytes(_stable_bytes(CONTRACT_PATH)) != CONTRACT_SHA256 or value.get("study_id") != STUDY_ID:
        raise ValueError("HANNA lean verifier study contract identity drifted")
    return value


def _dependencies() -> tuple[ModuleType, ModuleType, ModuleType, ModuleType, ModuleType]:
    contract()
    collector = _load(COLLECTOR_PATH, COLLECTOR_SHA256, "_hanna_lean_collector")
    if sha256_bytes(_stable_bytes(COLLECTOR_CONTRACT_PATH)) != COLLECTOR_CONTRACT_SHA256:
        raise ValueError("HANNA lean verifier collector contract drifted")
    collector.contract()
    optimizer = _load(OPTIMIZER_PATH, OPTIMIZER_SHA256, "_hanna_lean_optimizer")
    native = _load(NATIVE_PATH, NATIVE_SHA256, "_hanna_lean_native")
    exec_v1 = _load(EXEC_V1_PATH, EXEC_V1_SHA256, "_hanna_lean_exec_v1")
    exec_v3 = _load(EXEC_V3_PATH, EXEC_V3_SHA256, "_hanna_lean_exec_v3")
    return collector, optimizer, native, exec_v1, exec_v3


def _rows(optimizer: ModuleType, frozen_successor_path: Path, hanna_csv_path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    schedule = optimizer.freeze_lean_schedule(frozen_successor_path=Path(frozen_successor_path), hanna_csv_path=Path(hanna_csv_path))
    rows = [*schedule["partitions"]["training"]["grok"], *schedule["partitions"]["training"]["sol_sprinkled"]]
    if len(rows) != 35 or sum(row.get("route_name") == "grok_primary" for row in rows) != 25 or sum(row.get("route_name") == "sol_validation" for row in rows) != 10:
        raise ValueError("HANNA lean verifier frozen training geometry drifted")
    return dict(schedule), [dict(row) for row in rows]


def _inventory(root: Path, expected: frozenset[str], response_files: frozenset[str]) -> None:
    _plain(root, directory=True)
    entries = {entry.name: entry for entry in root.iterdir()}
    if set(entries) != expected:
        raise ValueError("HANNA lean verifier collector inventory is incomplete, extra, or unsafe")
    for name, entry in entries.items():
        _plain(entry, directory=name == "responses")
    responses = {entry.name: entry for entry in entries["responses"].iterdir()}
    if set(responses) != response_files:
        raise ValueError("HANNA lean verifier collector response inventory drifted")
    for entry in responses.values():
        _plain(entry, directory=False)


def _prepared(collector: ModuleType, native: ModuleType, root: Path, row: Mapping[str, Any], schedule: Mapping[str, Any], *, frozen_successor_path: Path, hanna_csv_path: Path) -> tuple[bytes, bytes, bytes, dict[str, Any]]:
    payload, request, schema = collector._payload(native, row, frozen_successor_path=Path(frozen_successor_path), hanna_csv_path=Path(hanna_csv_path))
    authorization = _object(root / "authorization-acknowledgement.json", "authorization acknowledgement")
    acknowledgement = authorization.get("acknowledgement_sha256")
    if not isinstance(acknowledgement, str) or not re.fullmatch(r"[0-9a-f]{64}", acknowledgement):
        raise ValueError("HANNA lean verifier authorization acknowledgement is invalid")
    prepared, expected = collector._expected_prepared_artifacts(row, schedule, payload, request, schema, _object(root / "prepared.json", "prepared record").get("route_evidence"), acknowledgement)
    for name, raw in expected.items():
        if _stable_bytes(root / name) != raw:
            raise ValueError(f"HANNA lean verifier prepared artifact binding drifted: {name}")
    return payload, request, schema, prepared


def _launch(root: Path, collector: ModuleType, row: Mapping[str, Any], payload: bytes, request: bytes, schema: bytes, prepared: Mapping[str, Any]) -> dict[str, Any]:
    launch = _object(root / "launch-intent.json", "launch intent")
    expected = {
        "format_version": 1, "study_id": collector.STUDY_ID, "kind": "lean_training_contact_intent", "cell_id": row["cell_id"],
        "prepared_sha256": sha256_bytes(canonical(prepared)), "request_sha256": sha256_bytes(request),
        "response_schema_sha256": sha256_bytes(schema), "outbound_payload_sha256": sha256_bytes(payload),
        "collector_executor_sha256": COLLECTOR_SHA256, "native_contact_proven": False,
    }
    if set(launch) != LAUNCH_KEYS or launch != expected:
        raise ValueError("HANNA lean verifier launch intent is misbound")
    return launch


def _artifact(record: Mapping[str, Any], name: str, root: Path) -> bytes:
    artifact = record.get("provider_artifacts", {}).get(name) if isinstance(record.get("provider_artifacts"), Mapping) else None
    if not isinstance(artifact, Mapping) or set(artifact) != {"path", "bytes", "sha256"}:
        raise ValueError(f"HANNA lean verifier record lacks {name} artifact")
    path = root / str(artifact["path"])
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError as error:
        raise ValueError("HANNA lean verifier record artifact escapes root") from error
    raw = _stable_bytes(path)
    if artifact["bytes"] != len(raw) or artifact["sha256"] != sha256_bytes(raw):
        raise ValueError("HANNA lean verifier record artifact hash drifted")
    return raw


def _result(root: Path, collector: ModuleType, row: Mapping[str, Any], identity: Mapping[str, Any], response: bytes, effective: Mapping[str, Any]) -> dict[str, Any]:
    result = _object(root / "result.json", "collector result")
    expected = {
        "format_version": 1, "study_id": collector.STUDY_ID, "kind": "training_collector_result", "cell_id": row["cell_id"],
        "identity": dict(identity), "identity_sha256": sha256_bytes(canonical(identity)), "native_response_sha256": sha256_bytes(response),
        "effective_settings_sha256": sha256_bytes(canonical(effective)), "provider_calls_made": 1, "process_launches": 1,
    }
    if set(result) != RESULT_KEYS or result != expected:
        raise ValueError("HANNA lean verifier collector result binding drifted")
    return result


def _grok_final(collector: ModuleType, native: ModuleType, exec_v1: ModuleType, root: Path, row: Mapping[str, Any], request: bytes) -> tuple[bytes, dict[str, Any], dict[str, float], dict[str, bool]]:
    record, effective = _object(root / "grok-record.json", "Grok record"), _object(root / "effective-settings.json", "Grok effective settings")
    if not record or not isinstance(record.get("provider_artifacts"), Mapping):
        raise ValueError("HANNA lean verifier Grok record is empty or malformed")
    raw = _stable_bytes(root / "raw-grok-envelope.bin")
    if raw != _stable_bytes(root / "responses" / "batch-0001.attempt-0001.grok.envelope.json") or request != _stable_bytes(root / "responses" / "batch-0001.attempt-0001.prompt.txt"):
        raise ValueError("HANNA lean verifier Grok raw artifact copies drifted")
    if _artifact(record, "grok_envelope", root) != raw:
        raise ValueError("HANNA lean verifier Grok envelope record binding drifted")
    request_id, session_id = exec_v1._envelope_identity(raw, record)
    if (record.get("requested") != {"model": "grok-4.6", "reasoning_effort": "high"}
            or record.get("reported") != {"provider": "grok", "model": "grok-4.6-build"}
            or record.get("reasoning_attested") is not False or not isinstance(record.get("cli_version"), str)):
        raise ValueError("HANNA lean verifier Grok model or reasoning record drifted")
    route_evidence = _object(root / "zero-charge-route-proof.json", "route proof")["route_evidence"]
    command_identity = effective.get("grok_command_identity")
    expected_effective = {
        "requested_model": "grok-4.6", "reported_model": "grok-4.6-build", "requested_reasoning_effort": "high",
        "reasoning_attested": False, "grok_cli_version": record["cli_version"], "grok_command_identity": command_identity,
        "tool_free_argv": collector.GROK_TOOL_FREE_ARGV, "system_prompt_override": collector.GROK_SYSTEM_PROMPT,
    }
    if (not isinstance(command_identity, Mapping) or effective != expected_effective
            or route_evidence.get("grok_cli_version") != record["cli_version"]
            or route_evidence.get("grok_command_identity_sha256") != sha256_bytes(canonical(command_identity))):
        raise ValueError("HANNA lean verifier Grok effective settings drifted")
    identity = {
        "provider": "xai_grok_build", "route_name": row["route"]["route_name"], "requested_model": "grok-4.6",
        "requested_reasoning_effort": "high", "effective_model": "grok-4.6-build", "provider_reported_model": "grok-4.6-build",
        "identity_evidence": "requested_and_cli_envelope_reported_model_reasoning_unattested", "reasoning_attested": False,
        "transport_identity": "grok_build_saved_session_subscription_tool_free_v1", "contact_id": request_id, "session_id": session_id,
    }
    identity = native._validate_identity(identity, row)
    scores, coverage = native._extract_native(raw, row=row, identity=identity)
    return raw, identity, scores, coverage


def _sol_final(collector: ModuleType, optimizer: ModuleType, native: ModuleType, exec_v3: ModuleType, root: Path, row: Mapping[str, Any], request: bytes) -> tuple[bytes, dict[str, Any], dict[str, float], dict[str, bool]]:
    record, effective = _object(root / "codex-record.json", "Codex record"), _object(root / "effective-settings.json", "Codex effective settings")
    if not record or not isinstance(record.get("command"), list) or not record["command"]:
        raise ValueError("HANNA lean verifier Codex record is empty or malformed")
    events, response, stderr = _stable_bytes(root / "raw-codex-events.bin"), _stable_bytes(root / "raw-codex-final-response.bin"), _stable_bytes(root / "raw-codex-stderr.bin")
    if (events != _stable_bytes(root / "responses" / "batch-0001.attempt-0001.events.jsonl")
            or response != _stable_bytes(root / "responses" / "batch-0001.attempt-0001.message.json")
            or request != _stable_bytes(root / "prompt-request.bin")):
        raise ValueError("HANNA lean verifier Codex raw artifact copies drifted")
    if _artifact(record, "codex_events", root) != events or _artifact(record, "codex_stderr", root) != stderr:
        raise ValueError("HANNA lean verifier Codex record artifact binding drifted")
    labels = exec_v3._strict_stderr_labels(stderr)
    projection = exec_v3._codex_event_projection(events, exec_v3._load_parse_codex_events())
    thread_id = projection.get("thread_id")
    if (not isinstance(thread_id, str) or not thread_id or not isinstance(projection.get("usage"), dict)
            or projection.get("completed_agent_message_text", "").encode("utf-8") != response
            or record.get("reported") != labels or record.get("command") != exec_v3._expected_codex_command(record["command"][0], root)):
        raise ValueError("HANNA lean verifier Codex lifecycle record drifted")
    route_evidence = _object(root / "zero-charge-route-proof.json", "route proof")["route_evidence"]
    command_identity = effective.get("codex_command_identity")
    expected_effective = {
        "requested_model": "gpt-5.6-sol", "local_effective_model": "gpt-5.6-sol", "requested_reasoning_effort": "high",
        "local_effective_reasoning_effort": "high", "provider_attested": False, "codex_cli_version": effective.get("codex_cli_version"),
        "codex_command_identity": command_identity, "capture_jsonl_events": True, "tools_enabled": False,
        "web_search_enabled": False, "subagents_enabled": False, "event_projection": projection,
    }
    if (not isinstance(command_identity, Mapping) or effective != expected_effective
            or route_evidence.get("codex_cli_version") != effective["codex_cli_version"]
            or route_evidence.get("codex_command_identity_sha256") != sha256_bytes(canonical(command_identity))):
        raise ValueError("HANNA lean verifier Codex effective settings drifted")
    identity = {
        "provider": "openai_codex", "route_name": row["route"]["route_name"], "requested_model": "gpt-5.6-sol",
        "requested_reasoning_effort": "high", "effective_model": "gpt-5.6-sol", "provider_reported_model": None,
        "identity_evidence": "requested_and_local_effective_settings_only_stderr_labels_may_be_absent_not_provider_attested",
        "reasoning_attested": False, "transport_identity": "codex_chatgpt_subscription_exec_tool_free_v3",
        "contact_id": f"unproven-native-endpoint-contact-for-local-thread:{thread_id}",
        "session_id": f"local-codex-thread-session:{labels['session_id'] or thread_id}",
    }
    identity = optimizer._validate_sol_v3_identity(identity, row)
    scores, coverage = optimizer._extract_sol_v3(native, response)
    return response, identity, scores, coverage


def _receipt(root: Path, collector: ModuleType, row: Mapping[str, Any], schedule: Mapping[str, Any], payload: bytes, request: bytes, schema: bytes, prepared: Mapping[str, Any], launch: Mapping[str, Any], response: bytes, identity: Mapping[str, Any], result: Mapping[str, Any], *, grok: bool) -> None:
    receipt = _object(root / "execution-receipt.json", "collector receipt")
    expected = {
        "format_version": 1, "study_id": collector.STUDY_ID,
        "kind": "lean_training_grok_native_receipt" if grok else "lean_training_sol_local_lifecycle_receipt",
        "cell": dict(row), "schedule_sha256": schedule["schedule_sha256"], "outbound_payload_sha256": sha256_bytes(payload),
        "request_sha256": sha256_bytes(request), "response_schema_sha256": sha256_bytes(schema),
        "prepared_sha256": sha256_bytes(canonical(prepared)), "launch_intent_sha256": sha256_bytes(canonical(launch)),
        "route_evidence": prepared["route_evidence"], "provider_calls_made": 1, "process_launches": 1,
        "identity": dict(identity), "collector_executor_sha256": COLLECTOR_SHA256, "native_response_sha256": sha256_bytes(response),
        "result_sha256": sha256_bytes(canonical(result)), "native_contact_proven": grok,
        "native_endpoint_contact_cardinality": "proven_exactly_one" if grok else "unproven",
    }
    if set(receipt) != RECEIPT_KEYS or receipt != expected:
        raise ValueError("HANNA lean verifier collector receipt binding drifted")


def _cell(collector: ModuleType, optimizer: ModuleType, native: ModuleType, exec_v1: ModuleType, exec_v3: ModuleType, root: Path, row: Mapping[str, Any], schedule: Mapping[str, Any], *, frozen_successor_path: Path, hanna_csv_path: Path) -> dict[str, Any]:
    grok = row["route_name"] == "grok_primary"
    _inventory(root, GROK_FILES if grok else SOL_FILES, GROK_RESPONSE_FILES if grok else SOL_RESPONSE_FILES)
    payload, request, schema, prepared = _prepared(collector, native, root, row, schedule, frozen_successor_path=frozen_successor_path, hanna_csv_path=hanna_csv_path)
    launch = _launch(root, collector, row, payload, request, schema, prepared)
    response, identity, scores, coverage = (_grok_final(collector, native, exec_v1, root, row, request) if grok else _sol_final(collector, optimizer, native, exec_v3, root, row, request))
    effective = _object(root / "effective-settings.json", "effective settings")
    result = _result(root, collector, row, identity, response, effective)
    _receipt(root, collector, row, schedule, payload, request, schema, prepared, launch, response, identity, result, grok=grok)
    return {**dict(row), "scores": scores, "coverage": coverage, "request_bytes": len(request), "identity": identity}


def verify_training_receipts(*, collection_evidence_path: Path, frozen_successor_path: Path, hanna_csv_path: Path) -> dict[str, Any]:
    collector, optimizer, native, exec_v1, exec_v3 = _dependencies()
    schedule, rows = _rows(optimizer, Path(frozen_successor_path), Path(hanna_csv_path))
    manifest = _object(Path(collection_evidence_path), "collector manifest")
    expected_manifest = {
        "format_version": 1, "study_id": STUDY_ID, "kind": "lean_training_collector_receipts",
        "collector_executor_sha256": COLLECTOR_SHA256, "collector_contract_sha256": COLLECTOR_CONTRACT_SHA256,
        "optimizer_sha256": OPTIMIZER_SHA256, "native_executor_sha256": NATIVE_SHA256,
        "schedule_sha256": schedule["schedule_sha256"], "stage": "training",
    }
    if set(manifest) != MANIFEST_KEYS or any(manifest.get(key) != value for key, value in expected_manifest.items()):
        raise ValueError("HANNA lean verifier collection evidence identity drifted")
    references = manifest.get("cells")
    if (not isinstance(references, list) or len(references) != len(rows)
            or any(not isinstance(reference, Mapping) or set(reference) != REFERENCE_KEYS for reference in references)
            or [reference["cell_id"] for reference in references] != [row["cell_id"] for row in rows]):
        raise ValueError("HANNA lean verifier refuses partial, aggregate, confirmation, or synthetic collection evidence")
    observations, contacts = [], set()
    for reference, row in zip(references, rows, strict=True):
        if not isinstance(reference["execution_root"], str):
            raise ValueError("HANNA lean verifier execution root is invalid")
        observation = _cell(collector, optimizer, native, exec_v1, exec_v3, Path(reference["execution_root"]), row, schedule, frozen_successor_path=Path(frozen_successor_path), hanna_csv_path=Path(hanna_csv_path))
        identity = observation["identity"]
        contact = (identity["provider"], identity["contact_id"], identity["session_id"])
        if contact in contacts:
            raise ValueError("HANNA lean verifier duplicate collector contact identity")
        contacts.add(contact); observations.append(observation)
    targets = optimizer._targets(native, rows, frozen_successor_path=Path(frozen_successor_path), hanna_csv_path=Path(hanna_csv_path))
    source_sha = sha256_bytes(_stable_bytes(Path(__file__)))
    projection = {
        "format_version": 1, "study_id": STUDY_ID, "kind": "lean_training_optimizer_observation_projection",
        "collector_evidence_sha256": sha256_bytes(_stable_bytes(Path(collection_evidence_path))),
        "dependencies": {"verifier_source_sha256": source_sha, "verifier_contract_sha256": CONTRACT_SHA256, "collector_executor_sha256": COLLECTOR_SHA256, "collector_contract_sha256": COLLECTOR_CONTRACT_SHA256, "optimizer_sha256": OPTIMIZER_SHA256, "native_executor_sha256": NATIVE_SHA256, "exec_v1_sha256": EXEC_V1_SHA256, "exec_v3_sha256": EXEC_V3_SHA256},
        "schedule_sha256": schedule["schedule_sha256"], "stage": "training", "observations": observations, "human_targets": targets,
        "geometry": {"grok_cells": 25, "sol_cells": 10, "total_cells": 35}, "sol_evidence_class": "local_codex_lifecycle_received_native_contact_unproven",
        "confirmation": {"status": "unopened", "cells": 0}, "runtime_authority": "none",
    }
    projection["projection_sha256"] = sha256_bytes(canonical(projection))
    return projection
