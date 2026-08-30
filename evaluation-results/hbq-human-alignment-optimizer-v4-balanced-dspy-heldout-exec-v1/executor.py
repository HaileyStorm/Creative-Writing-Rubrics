#!/usr/bin/env python3
"""Thin native transport composition for the frozen 66-cell HANNA heldout schedule."""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import importlib.util
import json
import math
import os
import re
import stat
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any, Awaitable, Callable, Mapping


HERE = Path(__file__).resolve().parent
STUDY_ID = "hbq-human-alignment-optimizer-v4-balanced-dspy-heldout-exec-v1"
SCHEDULE_SHA256 = "de7fce6600b03181fd429a3018c89468b1d08cf74841905bd341329be4aa437e"
CONTRACT_PATH = HERE / "study-contract.json"
CONTRACT_SHA256 = "0c15377c5d092b5b9a153e1692877f124725a0c1e09f73f3ed90092f2e605e40"
HELDOUT_STUDY_PATH = HERE.parent / "hbq-human-alignment-optimizer-v4-balanced-dspy-heldout-eval-v1" / "study.py"
HELDOUT_STUDY_SHA256 = "770b8c496df3c86dbc6ae3c7673d462428f81bcbddf84e493ea7c6710bd1b346"
GROK_EXEC_PATH = HERE.parent / "hbq-human-alignment-optimizer-v4-balanced-dspy-grok-exec-v2" / "executor.py"
GROK_EXEC_SHA256 = "475f5d2fb02cdddcf5b14810d25ef63bd166c85f129dc64106b443f33895fbc4"
NATIVE_PATH = HERE.parent / "hbq-human-alignment-optimizer-v4-native-subscription-exec-v1" / "executor.py"
NATIVE_SHA256 = "6d93f69216d62bd0847aa6b338b6e2360587c82608669f78fbad245a34ba1c49"
SOL_V4_PATH = HERE.parent / "hbq-human-alignment-optimizer-v4-native-subscription-exec-v4" / "executor.py"
SOL_V4_SHA256 = "4c961721b08dca237f1c4bd5f743438e3d54ef66af650e7c07bfc775b209f426"
PREPARED = frozenset({"payload.bin", "response-schema.json", "disclosure.json", "authorization-acknowledgement.json", "zero-charge-route-proof.json", "prepared.json"})


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def _adapter_canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _plain(path: Path, *, directory: bool | None = None) -> bool:
    info = os.lstat(path)
    if stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)):
        return False
    return directory is None or (stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode))


def stable_bytes(path: Path) -> bytes:
    absolute = Path(os.path.abspath(path)); current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current /= part
        if not _plain(current): raise ValueError(f"heldout exec v1 unsafe path: {current}")
    before = os.lstat(absolute)
    with absolute.open("rb") as handle:
        opened = os.fstat(handle.fileno())
        if (before.st_dev, before.st_ino, before.st_size) != (opened.st_dev, opened.st_ino, opened.st_size): raise ValueError("heldout exec v1 file identity drifted")
        raw = handle.read(); after = os.fstat(handle.fileno())
    if (opened.st_dev, opened.st_ino, opened.st_size) != (after.st_dev, after.st_ino, after.st_size): raise ValueError("heldout exec v1 file changed during read")
    return raw


def _load(path: Path, digest: str, name: str) -> ModuleType:
    raw = stable_bytes(path)
    if sha256(raw) != digest: raise ValueError(f"heldout exec v1 pinned dependency drifted: {path.name}")
    module = ModuleType(name); module.__file__ = str(path); exec(compile(raw, str(path), "exec"), module.__dict__)
    if stable_bytes(path) != raw: raise ValueError(f"heldout exec v1 dependency changed during load: {path.name}")
    return module


def _contract() -> dict[str, Any]:
    raw = stable_bytes(CONTRACT_PATH)
    if not CONTRACT_SHA256 or sha256(raw) != CONTRACT_SHA256: raise ValueError("heldout exec v1 contract drifted")
    value = json.loads(raw.decode("utf-8"))
    if not isinstance(value, dict) or canonical(value) != raw or value != {"authority": {"confirmation": {"cells": 0, "status": "unopened"}, "evaluation": False, "optimizer_runtime": False}, "execution": {"grok_max_concurrency": 10, "grok_native_contact": "proven_exactly_one_on_completed_adapter_control", "sol_max_concurrency": 1, "sol_native_contact": "unproven_local_codex_lifecycle_only"}, "format_version": 1, "schedule": {"schedule_sha256": SCHEDULE_SHA256, "total_cells": 66}, "study_id": STUDY_ID}:
        raise ValueError("heldout exec v1 contract semantics drifted")
    return value


def _study() -> ModuleType: return _load(HELDOUT_STUDY_PATH, HELDOUT_STUDY_SHA256, "_heldout_exec_study")
def _grok() -> ModuleType: return _load(GROK_EXEC_PATH, GROK_EXEC_SHA256, "_heldout_exec_grok")
def _native() -> ModuleType: return _load(NATIVE_PATH, NATIVE_SHA256, "_heldout_exec_native")
def _sol_v4() -> ModuleType: return _load(SOL_V4_PATH, SOL_V4_SHA256, "_heldout_exec_sol_v4")


def _write_new(path: Path, raw: bytes) -> None:
    with path.open("xb") as handle: handle.write(raw); handle.flush(); os.fsync(handle.fileno())


def _write_or_match(path: Path, raw: bytes) -> None:
    if path.exists():
        if stable_bytes(path) != raw: raise ValueError("heldout exec v1 runner-owned artifact differs from verified bytes")
        return
    _write_new(path, raw)


def _safe_output_ancestry(path: Path) -> None:
    absolute = Path(os.path.abspath(path)); current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current /= part
        if current.exists() and not _plain(current, directory=True): raise ValueError("heldout exec v1 output ancestry is unsafe")


def _schedule(*, reconciliation_manifest_path: Path, frozen_successor_path: Path, hanna_csv_path: Path) -> dict[str, Any]:
    schedule = _study().build_schedule(reconciliation_manifest_path=Path(reconciliation_manifest_path), frozen_successor_path=Path(frozen_successor_path), hanna_csv_path=Path(hanna_csv_path))
    if not isinstance(schedule, Mapping) or schedule.get("schedule_sha256") != SCHEDULE_SHA256 or schedule.get("confirmation") != {"status": "unopened", "cells": 0} or schedule.get("geometry") != {"candidates": 11, "grok_cells": 44, "sol_cells": 22, "total_cells": 66}:
        raise ValueError("heldout exec v1 frozen schedule drifted")
    cells = schedule.get("cells")
    if not isinstance(cells, list) or len(cells) != 66 or len({row.get("cell_id") for row in cells if isinstance(row, Mapping)}) != 66: raise ValueError("heldout exec v1 requires exactly 66 unique cells")
    grok = [row for row in cells if row.get("route_name") == "grok_primary"]; sol = [row for row in cells if row.get("route_name") == "sol_validation"]
    if len(grok) != 44 or len(sol) != 22 or len({row.get("candidate_id") for row in cells}) != 11:
        raise ValueError("heldout exec v1 route geometry drifted")
    for row in cells:
        if not isinstance(row.get("payload_base64"), str) or not isinstance(row.get("payload_sha256"), str) or not re.fullmatch(r"[0-9a-f]{64}", row["payload_sha256"]): raise ValueError("heldout exec v1 cell payload binding is invalid")
    for row in sol:
        matches = [peer for peer in grok if peer.get("item_id") == row.get("item_id") and peer.get("candidate_id") == row.get("candidate_id")]
        if len(matches) != 1 or matches[0].get("payload_base64") != row.get("payload_base64") or matches[0].get("payload_sha256") != row.get("payload_sha256"):
            raise ValueError("heldout exec v1 paired payload bytes drifted")
    return dict(schedule)


def _cell(schedule: Mapping[str, Any], cell_id: str) -> dict[str, Any]:
    rows = [dict(row) for row in schedule["cells"] if row.get("cell_id") == cell_id]
    if len(rows) != 1 or rows[0].get("route_name") not in {"grok_primary", "sol_validation"}: raise ValueError("heldout exec v1 cell is absent or unsafe")
    return rows[0]


def _schema(payload: bytes) -> bytes:
    value = json.loads(payload.decode("utf-8")); schema = value.get("response_schema") if isinstance(value, Mapping) else None
    if not isinstance(schema, Mapping) or set(schema) != {"format_version", "type", "additionalProperties", "required", "properties"} or schema.get("format_version") != 1 or schema.get("type") != "object" or schema.get("additionalProperties") is not False or schema.get("required") != ["scores", "evidence", "coverage"]:
        raise ValueError("heldout exec v1 embedded response schema drifted")
    return canonical(dict(schema))


def _validate_response(raw: bytes, schema: Mapping[str, Any]) -> dict[str, Any]:
    try: value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error: raise ValueError("heldout exec v1 response is not strict JSON") from error
    dimensions = ["Relevance", "Coherence", "Empathy", "Surprise", "Engagement", "Complexity"]
    if not isinstance(value, dict) or set(value) != {"scores", "evidence", "coverage"} or any(not isinstance(value.get(key), dict) or set(value[key]) != set(dimensions) for key in value): raise ValueError("heldout exec v1 response schema drifted")
    for dimension in dimensions:
        score = value["scores"][dimension]
        if not isinstance(score, (int, float)) or isinstance(score, bool) or score < 0 or score > 5 or score != score or score in {float("inf"), float("-inf")} or not isinstance(value["evidence"][dimension], str) or not value["evidence"][dimension].strip() or not isinstance(value["coverage"][dimension], bool): raise ValueError("heldout exec v1 response dimensions are invalid")
    if canonical(schema) != canonical(json.loads(canonical(schema).decode("utf-8"))): raise ValueError("heldout exec v1 response schema is invalid")
    return value


def _admit_grok_identity(request: Any, session: Any, requests: set[str], sessions: set[str]) -> None:
    if not all(isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) for value in (request, session)) or request == session or request in requests or session in sessions:
        raise ValueError("heldout exec v1 Grok request/session identity is duplicated or invalid")
    requests.add(request); sessions.add(session)


def _read_canonical(path: Path, label: str) -> dict[str, Any]:
    raw = stable_bytes(path)
    try: value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error: raise ValueError(f"heldout exec v1 {label} is invalid JSON") from error
    if not isinstance(value, dict) or canonical(value) != raw: raise ValueError(f"heldout exec v1 {label} is not canonical")
    return value


def _grok_route_evidence(route: Mapping[str, Any], evidence: Mapping[str, Any]) -> None:
    required = {"name", "model", "adapter", "provider", "destination", "reasoning_effort", "reported_model", "grok_command", "grok_command_identity", "cli_version_identity", "grok_cli_version", "cost_evidence", "subscription_receipt_hash"}
    policy = {"name": "grok-build-grok-4.6", "model": "grok-4.6", "adapter": "grok_exec", "provider": "xai_grok_build", "destination": "xai_grok_build_subscription", "account_class": "subscription", "zero_charge": True, "armed": True, "health": "healthy", "reasoning_effort": "high", "reported_model": "grok-4.6-build", "identity_evidence": "requested_only"}
    if not isinstance(route, Mapping) or not required <= set(route) or any(route.get(key) != value for key, value in policy.items()) or "public_repo" not in route.get("allowed_payload_classes", []) or not isinstance(route.get("grok_command"), list) or len(route["grok_command"]) != 1 or any(not isinstance(value, str) or not value for value in route["grok_command"]) or not isinstance(route.get("grok_command_identity"), dict) or not isinstance(route.get("cli_version_identity"), dict) or not isinstance(route.get("grok_cli_version"), str) or not route["grok_cli_version"] or not isinstance(route.get("cost_evidence"), Mapping):
        raise ValueError("heldout exec v1 persisted Grok route is invalid")
    cost_hash, subscription = route["cost_evidence"].get("evidence_hash"), route.get("subscription_receipt_hash")
    if not all(isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) for value in (cost_hash, subscription)):
        raise ValueError("heldout exec v1 persisted Grok route identities are invalid")
    expected = {"route_name": route["name"], "route_sha256": sha256(canonical(dict(route))), "registry_sha256": evidence.get("registry_sha256"), "cost_evidence_hash": cost_hash, "subscription_receipt_hash": subscription, "grok_command_identity_sha256": sha256(canonical(route["grok_command_identity"])), "cli_version_identity_sha256": sha256(canonical(route["cli_version_identity"])), "grok_cli_version": route["grok_cli_version"]}
    if not isinstance(evidence, Mapping) or set(evidence) != set(expected) or evidence != expected or not isinstance(evidence["registry_sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", evidence["registry_sha256"]):
        raise ValueError("heldout exec v1 persisted Grok route proof drifted")


def _sol_route_evidence(route: Mapping[str, Any], evidence: Mapping[str, Any]) -> None:
    v3 = _sol_v4()._v3(); required = {"name", "model", "adapter", "provider", "destination", "account_class", "zero_charge", "armed", "health", "reasoning_effort", "identity_evidence", "trusted", "allowed_payload_classes", "codex_command", "command", "command_identity", "codex_command_identity", "cli_version_identity", "auth_status_identity", "codex_cli_version", "auth_receipt_hash", "cost_evidence"}
    policy = {"name": "codex-chatgpt-gpt-5.6-sol", "model": "gpt-5.6-sol", "adapter": "codex_exec", "provider": "openai_codex", "destination": "openai_codex_chatgpt_subscription", "account_class": "subscription", "zero_charge": True, "armed": True, "health": "healthy", "reasoning_effort": "high", "identity_evidence": "requested_only", "trusted": True}
    if not isinstance(route, Mapping) or not required <= set(route) or any(route.get(key) != value for key, value in policy.items()) or "public_repo" not in route.get("allowed_payload_classes", []) or not isinstance(route.get("codex_command"), list) or len(route["codex_command"]) != 1 or any(not isinstance(value, str) or not value for value in route["codex_command"]) or not isinstance(route.get("command"), list) or len(route["command"]) != 2 or Path(route["command"][1]).resolve() != v3.CODEX_ADAPTER_PATH.resolve() or any(not isinstance(route.get(key), dict) for key in ("command_identity", "codex_command_identity", "cli_version_identity", "auth_status_identity")) or not isinstance(route.get("codex_cli_version"), str) or not route["codex_cli_version"] or not isinstance(route.get("auth_receipt_hash"), str) or not re.fullmatch(r"[0-9a-f]{64}", route["auth_receipt_hash"]) or not isinstance(route.get("cost_evidence"), Mapping):
        raise ValueError("heldout exec v1 persisted Sol route is invalid")
    cost = route["cost_evidence"]
    if not all(isinstance(cost.get(key), str) and cost[key] for key in ("evidence_hash", "checked_at", "expires_at")) or not re.fullmatch(r"[0-9a-f]{64}", cost["evidence_hash"]):
        raise ValueError("heldout exec v1 persisted Sol cost evidence is invalid")
    expected = {"route_name": route["name"], "route_sha256": sha256(canonical(dict(route))), "registry_sha256": evidence.get("registry_sha256"), "cost_evidence_hash": cost["evidence_hash"], "auth_receipt_hash": route["auth_receipt_hash"], "cost_evidence_checked_at": cost["checked_at"], "cost_evidence_expires_at": cost["expires_at"], "wrapper_command_identity_sha256": sha256(canonical(route["command_identity"])), "codex_command_identity_sha256": sha256(canonical(route["codex_command_identity"])), "cli_version_identity_sha256": sha256(canonical(route["cli_version_identity"])), "auth_status_identity_sha256": sha256(canonical(route["auth_status_identity"])), "codex_cli_version": route["codex_cli_version"], "codex_adapter_sha256": v3.CODEX_ADAPTER_SHA256}
    hex_keys = {"route_sha256", "registry_sha256", "cost_evidence_hash", "auth_receipt_hash", "wrapper_command_identity_sha256", "codex_command_identity_sha256", "cli_version_identity_sha256", "auth_status_identity_sha256", "codex_adapter_sha256"}
    if not isinstance(evidence, Mapping) or set(evidence) != set(expected) or evidence != expected or any(not isinstance(evidence[key], str) or not re.fullmatch(r"[0-9a-f]{64}", evidence[key]) for key in hex_keys):
        raise ValueError("heldout exec v1 persisted Sol route proof drifted")


def _validate_grok_runtime(runtime: Mapping[str, Any], route: Mapping[str, Any], evidence: Mapping[str, Any]) -> None:
    required = {"adapter_version", "requested_model", "reported_model", "requested_reasoning_effort", "reasoning_attested", "reasoning_attestation", "identity_evidence", "cli_version", "session_id_hash", "request_id_hash", "envelope_hash", "command_identity", "command_identity_hash", "subscription_receipt_hash", "execution_policy", "usage_telemetry", "nonvisual_max_turns", "observed_turns"}
    command_hash = sha256(_adapter_canonical({"adapter_version": 1, "grok_command": route["grok_command"], "model": route["model"], "reported_model": route["reported_model"], "reasoning_effort": route["reasoning_effort"]}))
    if set(runtime) != required or runtime.get("adapter_version") != 1 or runtime.get("requested_model") != route["model"] or runtime.get("reported_model") != route["reported_model"] or runtime.get("requested_reasoning_effort") != route["reasoning_effort"] or runtime.get("reasoning_attested") is not False or runtime.get("reasoning_attestation") != "not_reported_by_grok_build_cli" or runtime.get("identity_evidence") != "requested_only" or runtime.get("cli_version") != route["grok_cli_version"] or runtime.get("command_identity") != route["grok_command_identity"] or runtime.get("command_identity_hash") != command_hash or runtime.get("subscription_receipt_hash") != route["subscription_receipt_hash"] or runtime.get("execution_policy") != "bounded_nonvisual_read_only" or runtime.get("nonvisual_max_turns") != 1 or runtime.get("observed_turns") != 1 or any(not isinstance(runtime.get(key), str) or not re.fullmatch(r"[0-9a-f]{64}", runtime[key]) for key in ("request_id_hash", "session_id_hash", "envelope_hash")):
        raise ValueError("heldout exec v1 Grok runtime identity drifted")
    telemetry = runtime.get("usage_telemetry")
    if not isinstance(telemetry, dict) or set(telemetry) - {"status", "total_cost_usd", "total_cost_usd_ticks", "model_cost_usd"} or telemetry.get("status") not in {"reported", "not_reported"} or (telemetry.get("status") == "not_reported" and set(telemetry) != {"status"}) or (telemetry.get("status") == "reported" and set(telemetry) == {"status"}):
        raise ValueError("heldout exec v1 Grok telemetry drifted")
    for key in ("total_cost_usd", "model_cost_usd"):
        if key in telemetry and (not isinstance(telemetry[key], (int, float)) or isinstance(telemetry[key], bool) or not math.isfinite(telemetry[key]) or telemetry[key] < 0):
            raise ValueError("heldout exec v1 Grok telemetry is invalid")
    if "total_cost_usd_ticks" in telemetry and (type(telemetry["total_cost_usd_ticks"]) is not int or telemetry["total_cost_usd_ticks"] < 0):
        raise ValueError("heldout exec v1 Grok telemetry is invalid")


def _route(route_name: str, queue_root: Path) -> tuple[Any, Any, dict[str, Any], dict[str, Any]]:
    native = _native()
    if route_name == "grok_primary":
        route, evidence = native.validate_live_grok_route(Path(queue_root)); broker = native._load_broker_class()(Path(queue_root)); return native, broker, route, evidence
    sol = _sol_v4(); v3 = sol._v3(); route, evidence = v3.validate_live_sol_route(Path(queue_root)); return sol, v3, route, evidence


def _payload(study: ModuleType, row: Mapping[str, Any]) -> bytes:
    raw = study.payload_bytes(row)
    if sha256(raw) != row.get("payload_sha256"): raise ValueError("heldout exec v1 payload binding drifted")
    return raw


def _files(row: Mapping[str, Any], schedule: Mapping[str, Any], payload: bytes, route: Mapping[str, Any], evidence: Mapping[str, Any], acknowledgement: str) -> dict[str, bytes]:
    if not re.fullmatch(r"[0-9a-f]{64}", acknowledgement): raise ValueError("heldout exec v1 acknowledgement must be SHA-256")
    schema = _schema(payload); destination = route["destination"]
    disclosure = {"format_version": 1, "study_id": STUDY_ID, "kind": "local_first_exact_outbound_disclosure", "cell_id": row["cell_id"], "schedule_sha256": schedule["schedule_sha256"], "route_name": row["route_name"], "destination": destination, "payload": {"bytes": len(payload), "sha256": sha256(payload), "text": payload.decode("utf-8")}, "response_schema_sha256": sha256(schema), "tools_enabled": False, "web_search_enabled": False, "plans_enabled": False, "subagents_enabled": False, "provider_calls_made": 0, "process_launches": 0}
    ack = {"format_version": 1, "study_id": STUDY_ID, "kind": "caller_authorization_acknowledgement_reference", "cell_id": row["cell_id"], "acknowledgement_sha256": acknowledgement, "disclosure_sha256": sha256(canonical(disclosure)), "destination": destination}
    proof = {"format_version": 1, "study_id": STUDY_ID, "kind": "current_zero_charge_route_proof", "cell_id": row["cell_id"], "route_evidence": dict(evidence), "zero_charge_only": True, "paid_fallback_forbidden": True, "provider_calls_made": 0, "process_launches": 0}
    prepared = {"format_version": 1, "study_id": STUDY_ID, "kind": "heldout_native_preparation", "cell": dict(row), "schedule_sha256": schedule["schedule_sha256"], "payload_sha256": sha256(payload), "response_schema_sha256": sha256(schema), "route": dict(route), "route_evidence": dict(evidence), "disclosure_sha256": sha256(canonical(disclosure)), "acknowledgement_sha256": sha256(canonical(ack)), "route_proof_sha256": sha256(canonical(proof)), "sol_executable": (route.get("codex_command") or [None])[0], "provider_calls_made": 0, "process_launches": 0, "confirmation": {"status": "unopened", "cells": 0}, "runtime_authority": "none"}
    return {"payload.bin": payload, "response-schema.json": schema, "disclosure.json": canonical(disclosure), "authorization-acknowledgement.json": canonical(ack), "zero-charge-route-proof.json": canonical(proof), "prepared.json": canonical(prepared)}


def _validate_root(root: Path, files: Mapping[str, bytes], *, allow_responses: bool = False) -> None:
    if not root.is_dir() or not _plain(root, directory=True): raise ValueError("heldout exec v1 root is unsafe")
    entries = {entry.name: entry for entry in root.iterdir()}; expected = set(files) | ({"responses"} if allow_responses else set())
    if set(entries) != expected or any(not _plain(path, directory=name == "responses") for name, path in entries.items()): raise ValueError("heldout exec v1 root inventory is incomplete or unsafe")
    if allow_responses and any((root / "responses").iterdir()): raise ValueError("heldout exec v1 callback responses inventory is unsafe")
    for name, raw in files.items():
        if stable_bytes(root / name) != raw: raise ValueError("heldout exec v1 prepared artifact drifted")


def prepare_cell(*, reconciliation_manifest_path: Path, frozen_successor_path: Path, hanna_csv_path: Path, cell_id: str, output_root: Path, queue_root: Path, authorization_acknowledgement_sha256: str) -> dict[str, Any]:
    _contract(); frozen = _schedule(reconciliation_manifest_path=reconciliation_manifest_path, frozen_successor_path=frozen_successor_path, hanna_csv_path=hanna_csv_path); row = _cell(frozen, cell_id); study = _study(); payload = _payload(study, row); _owner, _runner, route, evidence = _route(row["route_name"], Path(queue_root)); root = Path(output_root) / cell_id
    if root.exists(): raise ValueError("heldout exec v1 refuses an existing or orphan root")
    _safe_output_ancestry(root.parent); files = _files(row, frozen, payload, route, evidence, authorization_acknowledgement_sha256); root.mkdir(parents=True, exist_ok=False)
    for name, raw in files.items(): _write_new(root / name, raw)
    return {"cell_id": cell_id, "state": "prepared_no_contact", "provider_calls_made": 0, "process_launches": 0}


def prepare_all(*, reconciliation_manifest_path: Path, frozen_successor_path: Path, hanna_csv_path: Path, output_root: Path, queue_root: Path, authorization_acknowledgement_sha256: str) -> list[dict[str, Any]]:
    frozen = _schedule(reconciliation_manifest_path=reconciliation_manifest_path, frozen_successor_path=frozen_successor_path, hanna_csv_path=hanna_csv_path)
    if Path(output_root).exists(): raise ValueError("heldout exec v1 all-cell output root must be fresh")
    return [prepare_cell(reconciliation_manifest_path=reconciliation_manifest_path, frozen_successor_path=frozen_successor_path, hanna_csv_path=hanna_csv_path, cell_id=row["cell_id"], output_root=output_root, queue_root=queue_root, authorization_acknowledgement_sha256=authorization_acknowledgement_sha256) for row in frozen["cells"]]


def _terminal(root: Path, row: Mapping[str, Any], prepared: Mapping[str, Any], *, state: str, launches: int, detail: str | None = None) -> dict[str, Any]:
    result = {"format_version": 1, "study_id": STUDY_ID, "kind": state, "cell_id": row["cell_id"], "prepared_sha256": sha256(canonical(prepared)), "process_launches": launches, "provider_calls_made": 0 if launches == 0 else None, "native_contact_proven": False, "native_endpoint_contact_cardinality": "zero" if launches == 0 else "unknown", "detail": detail}
    _write_new(root / ("precontact-failure.json" if launches == 0 else "result.json"), canonical(result)); return result


def _prepared(root: Path, row: Mapping[str, Any], schedule: Mapping[str, Any], queue_root: Path, acknowledgement: str, *, callback: bool = False) -> tuple[dict[str, Any], dict[str, Any], bytes, dict[str, Any], dict[str, Any]]:
    study = _study(); payload = _payload(study, row); _owner, _runner, route, evidence = _route(row["route_name"], queue_root); files = _files(row, schedule, payload, route, evidence, acknowledgement); _validate_root(root, files, allow_responses=callback)
    return json.loads(files["prepared.json"]), route, payload, evidence, files


def _intent(root: Path, row: Mapping[str, Any], prepared: Mapping[str, Any]) -> None:
    value = {"format_version": 1, "study_id": STUDY_ID, "kind": "process_launch_intent_not_native_contact", "cell_id": row["cell_id"], "prepared_sha256": sha256(canonical(prepared)), "native_contact_proven": False}
    _write_new(root / "launch-intent.json", canonical(value))


def _grok_invoke(grok: ModuleType, broker: Any, route: Mapping[str, Any], payload: bytes, schema: Mapping[str, Any], capture: Path) -> tuple[Any, bytes]:
    adapter_route = grok._adapter_command(broker, route, schema)
    wrapper = {**adapter_route, "command": [sys.executable, str(grok.CAPTURE_WRAPPER_PATH), "--capture-path", str(capture.resolve()), "--", *adapter_route["command"]]}
    seen: list[bytes] = []
    def parse(raw: bytes) -> Any:
        seen.append(raw); return broker._parse_grok_exec_envelope(raw, adapter_route, {"prompt": payload.decode("utf-8")})
    outcome = broker._run_subprocess(wrapper, {"prompt": payload.decode("utf-8")}, parse)
    raw = stable_bytes(capture) if capture.exists() else b""
    if seen and raw != seen[0]: return SimpleNamespace(state="ambiguous", detail="capture differs from broker stdout", result=None), raw
    return outcome, raw


def execute_cell(*, reconciliation_manifest_path: Path, frozen_successor_path: Path, hanna_csv_path: Path, cell_id: str, output_root: Path, queue_root: Path, authorization_acknowledgement_sha256: str, allow_remote: bool) -> dict[str, Any]:
    if allow_remote is not True: raise ValueError("heldout exec v1 requires explicit allow_remote=True")
    _contract(); frozen = _schedule(reconciliation_manifest_path=reconciliation_manifest_path, frozen_successor_path=frozen_successor_path, hanna_csv_path=hanna_csv_path); row = _cell(frozen, cell_id); root = Path(output_root) / cell_id
    if any((root / name).exists() for name in ("precontact-failure.json", "launch-intent.json", "result.json", "execution-receipt.json")):
        raise ValueError("heldout exec v1 terminal or launched root cannot resend")
    try:
        prepared, route, payload, evidence, files = _prepared(root, row, frozen, Path(queue_root), authorization_acknowledgement_sha256)
    except BaseException as error:
        if root.is_dir() and not (root / "precontact-failure.json").exists():
            try:
                _terminal(root, row, {"unvalidated": True}, state="definitely_not_contacted", launches=0, detail=type(error).__name__)
            except BaseException: pass
        raise
    if row["route_name"] == "grok_primary":
        grok = _grok(); native = _native(); broker = native._load_broker_class()(Path(queue_root))
        try:
            fresh_route, fresh_evidence = native.validate_live_grok_route(Path(queue_root))
            if fresh_route != route or fresh_evidence != evidence: raise ValueError("heldout exec v1 Grok route drifted adjacent to launch")
        except BaseException as error:
            return _terminal(root, row, prepared, state="definitely_not_contacted", launches=0, detail=type(error).__name__)
        _validate_root(root, files); _intent(root, row, prepared)
        try:
            schema = json.loads(files["response-schema.json"].decode("utf-8")); outcome, raw = _grok_invoke(grok, broker, fresh_route, payload, schema, root / "adapter-stdout.bin")
            if outcome.state != "completed": raise ValueError(getattr(outcome, "detail", "Grok adapter ambiguity"))
            control = json.loads(raw.decode("utf-8")); runtime = control["result"]["runtime"]
            if runtime.get("requested_model") != "grok-4.6" or runtime.get("reported_model") != "grok-4.6-build" or runtime.get("requested_reasoning_effort") != "high" or runtime.get("nonvisual_max_turns") != 1 or runtime.get("observed_turns") != 1: raise ValueError("heldout exec v1 Grok runtime identity drifted")
            _validate_response(canonical(control["result"]["output"]), schema)
            _write_new(root / "adapter-control-envelope.json", canonical(control)); _write_new(root / "runtime-identity.json", canonical(runtime))
            receipt = {"format_version": 1, "study_id": STUDY_ID, "kind": "grok_completed_adapter_receipt", "cell_id": cell_id, "prepared_sha256": sha256(canonical(prepared)), "payload_sha256": sha256(payload), "response_schema_sha256": sha256(files["response-schema.json"]), "adapter_stdout_sha256": sha256(raw), "adapter_control_sha256": sha256(canonical(control)), "runtime_sha256": sha256(canonical(runtime)), "output_sha256": control["result"]["output_hash"], "request_id_hash": runtime["request_id_hash"], "session_id_hash": runtime["session_id_hash"], "native_contact_proven": True, "native_endpoint_contact_cardinality": "proven_exactly_one", "route_evidence": evidence}
            _write_new(root / "execution-receipt.json", canonical(receipt)); _write_new(root / "result.json", canonical({"format_version": 1, "study_id": STUDY_ID, "kind": "grok_completed", "cell_id": cell_id, "provider_calls_made": 1, "process_launches": 1, "receipt_sha256": sha256(canonical(receipt)), "adapter_stdout_sha256": sha256(raw), "output_sha256": control["result"]["output_hash"]}))
            return {"cell_id": cell_id, "state": "grok_completed", "provider_calls_made": 1, "process_launches": 1, "native_endpoint_contact_cardinality": "proven_exactly_one"}
        except BaseException as error:
            return _terminal(root, row, prepared, state="reconcile_required_after_process_launch", launches=1, detail=type(error).__name__)
    sol, v3, _unused, _unused_evidence = _route("sol_validation", Path(queue_root)); launched = False
    def before_provider_attempt() -> None:
        nonlocal launched
        if launched: raise ValueError("heldout exec v1 Sol callback repeated")
        fresh_prepared, fresh_route, _fresh_payload, fresh_evidence, fresh_files = _prepared(root, row, frozen, Path(queue_root), authorization_acknowledgement_sha256, callback=True)
        if fresh_prepared != prepared or fresh_route != route or fresh_evidence != evidence: raise ValueError("heldout exec v1 Sol callback-time route/prepared drifted")
        _validate_root(root, fresh_files, allow_responses=True); _intent(root, row, prepared); launched = True
    try:
        invoke = v3._load_call_codex(); content, record = invoke(executable=route["codex_command"][0], model="gpt-5.6-sol", reasoning="high", prompt=payload.decode("utf-8"), output_dir=root, response_schema=root / "response-schema.json", batch_number=1, timeout=float(route["timeout_seconds"]), attempt_number=1, before_provider_attempt=before_provider_attempt, capture_jsonl_events=True)
        if not launched or not isinstance(content, str) or not isinstance(record, Mapping): raise ValueError("heldout exec v1 Sol lifecycle is incomplete")
        artifacts = record.get("provider_artifacts")
        if not isinstance(artifacts, Mapping) or list(record.get("command", [])) != v3._expected_codex_command(route["codex_command"][0], root): raise ValueError("heldout exec v1 Sol command/artifact binding drifted")
        events = sol._artifact(root, artifacts.get("codex_events"), "Codex events"); stderr = sol._artifact(root, artifacts.get("codex_stderr"), "Codex stderr")
        final = stable_bytes(root / "responses" / "batch-0001.attempt-0001.message.json")
        if content.encode("utf-8") != final: raise ValueError("heldout exec v1 Sol final response association drifted")
        projection = v3._codex_event_projection(events, v3._load_parse_codex_events())
        if projection.get("completed_agent_message_text", "").encode("utf-8") != final: raise ValueError("heldout exec v1 Sol event/final association drifted")
        labels = v3._strict_stderr_labels(stderr); thread_id = projection.get("thread_id")
        if not isinstance(thread_id, str) or not thread_id or labels.get("session_id") not in {None, thread_id}: raise ValueError("heldout exec v1 Sol thread/session association drifted")
        _validate_response(final, json.loads(files["response-schema.json"].decode("utf-8")))
        effective = {"requested_model": "gpt-5.6-sol", "local_effective_model": "gpt-5.6-sol", "requested_reasoning_effort": "high", "local_effective_reasoning_effort": "high", "provider_attested": False, "codex_cli_version": route["codex_cli_version"], "codex_command_identity": route["codex_command_identity"], "capture_jsonl_events": True, "tools_enabled": False, "web_search_enabled": False, "plans_enabled": False, "subagents_enabled": False, "stderr_label_evidence": labels, "event_projection": projection}
        _write_or_match(root / "raw-codex-events.bin", events); _write_or_match(root / "raw-codex-stderr.bin", stderr); _write_or_match(root / "raw-codex-final-response.bin", final); _write_or_match(root / "codex-record.json", canonical(dict(record))); _write_or_match(root / "effective-settings.json", canonical(effective))
        receipt = {"format_version": 1, "study_id": STUDY_ID, "kind": "sol_local_lifecycle_receipt", "cell_id": cell_id, "prepared_sha256": sha256(canonical(prepared)), "payload_sha256": sha256(payload), "response_schema_sha256": sha256(files["response-schema.json"]), "native_contact_proven": False, "native_endpoint_contact_cardinality": "unproven", "process_launches": 1, "route_evidence": evidence, "raw_events_sha256": sha256(events), "raw_stderr_sha256": sha256(stderr), "final_response_sha256": sha256(final), "codex_record_sha256": sha256(canonical(dict(record))), "effective_settings_sha256": sha256(canonical(effective)), "usage": projection["usage"]}
        _write_new(root / "execution-receipt.json", canonical(receipt)); _write_new(root / "result.json", canonical({"format_version": 1, "study_id": STUDY_ID, "kind": "sol_local_lifecycle_completed", "cell_id": cell_id, "provider_calls_made": None, "process_launches": 1, "receipt_sha256": sha256(canonical(receipt)), "final_response_sha256": sha256(final)}))
        return {"cell_id": cell_id, "state": "sol_local_lifecycle_completed", "provider_calls_made": None, "process_launches": 1, "native_endpoint_contact_cardinality": "unproven"}
    except BaseException as error:
        if launched: return _terminal(root, row, prepared, state="reconcile_required_after_process_launch", launches=1, detail=type(error).__name__)
        return _terminal(root, row, prepared, state="definitely_not_contacted", launches=0, detail=type(error).__name__)


async def execute_wave(*, reconciliation_manifest_path: Path, frozen_successor_path: Path, hanna_csv_path: Path, cell_ids: list[str], output_root: Path, queue_root: Path, authorization_acknowledgement_sha256: str, allow_remote: bool) -> list[dict[str, Any]]:
    frozen = _schedule(reconciliation_manifest_path=reconciliation_manifest_path, frozen_successor_path=frozen_successor_path, hanna_csv_path=hanna_csv_path); rows = [_cell(frozen, cell_id) for cell_id in cell_ids]
    if len(set(cell_ids)) != len(cell_ids): raise ValueError("heldout exec v1 wave has duplicate cells")
    grok_limit, sol_limit = asyncio.Semaphore(10), asyncio.Semaphore(1)
    async def one(row: Mapping[str, Any]) -> dict[str, Any]:
        limit = grok_limit if row["route_name"] == "grok_primary" else sol_limit
        async with limit: return await asyncio.to_thread(execute_cell, reconciliation_manifest_path=reconciliation_manifest_path, frozen_successor_path=frozen_successor_path, hanna_csv_path=hanna_csv_path, cell_id=row["cell_id"], output_root=output_root, queue_root=queue_root, authorization_acknowledgement_sha256=authorization_acknowledgement_sha256, allow_remote=allow_remote)
    return await asyncio.gather(*(one(row) for row in rows))


def freeze_collection(*, reconciliation_manifest_path: Path, frozen_successor_path: Path, hanna_csv_path: Path, output_root: Path, manifest_path: Path) -> dict[str, Any]:
    frozen = _schedule(reconciliation_manifest_path=reconciliation_manifest_path, frozen_successor_path=frozen_successor_path, hanna_csv_path=hanna_csv_path); root = Path(output_root)
    entries = {entry.name: entry for entry in root.iterdir()} if root.is_dir() and _plain(root, directory=True) else {}
    if set(entries) != {row["cell_id"] for row in frozen["cells"]} or any(not _plain(path, directory=True) for path in entries.values()): raise ValueError("heldout exec v1 collection inventory is incomplete or unsafe")
    rows: list[dict[str, Any]] = []; requests: set[str] = set(); sessions: set[str] = set(); study = _study(); sol_module = _sol_v4()
    for cell in frozen["cells"]:
        cell_root = root / cell["cell_id"]
        children = {entry.name: entry for entry in cell_root.iterdir()} if cell_root.is_dir() and _plain(cell_root, directory=True) else {}
        for path in children.values():
            if not _plain(path, directory=path.name == "responses"): raise ValueError("heldout exec v1 completed root is unsafe")
        disclosure = _read_canonical(cell_root / "disclosure.json", "disclosure"); proof = _read_canonical(cell_root / "zero-charge-route-proof.json", "route proof"); ack = _read_canonical(cell_root / "authorization-acknowledgement.json", "acknowledgement"); persisted_prepared = _read_canonical(cell_root / "prepared.json", "prepared record")
        if not isinstance(disclosure, dict) or not isinstance(proof, dict) or not isinstance(ack, dict) or not re.fullmatch(r"[0-9a-f]{64}", str(ack.get("acknowledgement_sha256"))): raise ValueError("heldout exec v1 completed disclosure/proof/ack is invalid")
        if not isinstance(persisted_prepared, dict) or not isinstance(persisted_prepared.get("sol_executable"), (str, type(None))) or not isinstance(persisted_prepared.get("route"), dict) or not isinstance(proof.get("route_evidence"), dict): raise ValueError("heldout exec v1 persisted prepared/proof is invalid")
        payload = _payload(study, cell); route = persisted_prepared["route"]; expected = _files(cell, frozen, payload, route, proof["route_evidence"], ack["acknowledgement_sha256"])
        if any(stable_bytes(cell_root / name) != raw for name, raw in expected.items()): raise ValueError("heldout exec v1 completed prepared bytes drifted")
        prepared = json.loads(expected["prepared.json"]); receipt = _read_canonical(cell_root / "execution-receipt.json", "execution receipt"); result = _read_canonical(cell_root / "result.json", "result")
        if persisted_prepared != prepared: raise ValueError("heldout exec v1 persisted prepared reconstruction drifted")
        intent = _read_canonical(cell_root / "launch-intent.json", "launch intent")
        if intent != {"format_version": 1, "study_id": STUDY_ID, "kind": "process_launch_intent_not_native_contact", "cell_id": cell["cell_id"], "prepared_sha256": sha256(canonical(prepared)), "native_contact_proven": False}: raise ValueError("heldout exec v1 launch intent binding drifted")
        if cell["route_name"] == "grok_primary":
            required = PREPARED | {"launch-intent.json", "adapter-stdout.bin", "adapter-control-envelope.json", "runtime-identity.json", "execution-receipt.json", "result.json"}
            children = {entry.name for entry in cell_root.iterdir()}
            if set(children) != required or receipt.get("kind") != "grok_completed_adapter_receipt" or result.get("kind") != "grok_completed": raise ValueError("heldout exec v1 Grok completion inventory drifted")
            raw = stable_bytes(cell_root / "adapter-stdout.bin"); control = json.loads(raw.decode("utf-8")); stored = _read_canonical(cell_root / "adapter-control-envelope.json", "adapter control"); runtime = _read_canonical(cell_root / "runtime-identity.json", "runtime identity")
            if control != stored or control.get("control") != {"version": 1, "state": "completed"} or not isinstance(control.get("result"), dict) or set(control["result"]) != {"schema_version", "request_hash", "output", "output_hash", "runtime"} or control["result"].get("schema_version") != 1 or control["result"].get("runtime") != runtime: raise ValueError("heldout exec v1 Grok control/runtime binding drifted")
            _grok_route_evidence(route, proof["route_evidence"])
            if control["result"].get("request_hash") != sha256(_adapter_canonical({"prompt": payload.decode("utf-8")})) or control["result"].get("output_hash") != sha256(_adapter_canonical(control["result"].get("output"))): raise ValueError("heldout exec v1 Grok control hash replay drifted")
            _validate_grok_runtime(runtime, route, proof["route_evidence"])
            _validate_response(canonical(control["result"]["output"]), json.loads(expected["response-schema.json"].decode("utf-8")))
            if receipt != {"format_version": 1, "study_id": STUDY_ID, "kind": "grok_completed_adapter_receipt", "cell_id": cell["cell_id"], "prepared_sha256": sha256(canonical(prepared)), "payload_sha256": sha256(payload), "response_schema_sha256": sha256(expected["response-schema.json"]), "adapter_stdout_sha256": sha256(raw), "adapter_control_sha256": sha256(canonical(control)), "runtime_sha256": sha256(canonical(runtime)), "output_sha256": control["result"]["output_hash"], "request_id_hash": runtime.get("request_id_hash"), "session_id_hash": runtime.get("session_id_hash"), "native_contact_proven": True, "native_endpoint_contact_cardinality": "proven_exactly_one", "route_evidence": proof["route_evidence"]}: raise ValueError("heldout exec v1 Grok receipt binding drifted")
            request, session = receipt.get("request_id_hash"), receipt.get("session_id_hash")
            _admit_grok_identity(request, session, requests, sessions)
            expected_result = {"format_version": 1, "study_id": STUDY_ID, "kind": "grok_completed", "cell_id": cell["cell_id"], "provider_calls_made": 1, "process_launches": 1, "receipt_sha256": sha256(canonical(receipt)), "adapter_stdout_sha256": sha256(raw), "output_sha256": control["result"]["output_hash"]}
            if result != expected_result: raise ValueError("heldout exec v1 Grok result binding drifted")
        else:
            required = PREPARED | {"responses", "launch-intent.json", "raw-codex-events.bin", "raw-codex-stderr.bin", "raw-codex-final-response.bin", "codex-record.json", "effective-settings.json", "execution-receipt.json", "result.json"}
            if set(children) != required or receipt.get("kind") != "sol_local_lifecycle_receipt" or receipt.get("native_endpoint_contact_cardinality") != "unproven" or result.get("kind") != "sol_local_lifecycle_completed": raise ValueError("heldout exec v1 Sol completion ceiling drifted")
            _sol_route_evidence(route, proof["route_evidence"])
            response_children = {entry.name: entry for entry in (cell_root / "responses").iterdir()}
            if set(response_children) != {"batch-0001.attempt-0001.events.jsonl", "batch-0001.attempt-0001.message.json"} or any(not _plain(entry, directory=False) for entry in response_children.values()): raise ValueError("heldout exec v1 Sol responses inventory drifted")
            final = stable_bytes(cell_root / "raw-codex-final-response.bin"); events = stable_bytes(cell_root / "raw-codex-events.bin"); stderr = stable_bytes(cell_root / "raw-codex-stderr.bin"); record = _read_canonical(cell_root / "codex-record.json", "Codex record"); effective = _read_canonical(cell_root / "effective-settings.json", "effective settings")
            v3 = sol_module._v3()
            if not isinstance(prepared.get("sol_executable"), str) or list(record.get("command", [])) != v3._expected_codex_command(prepared["sol_executable"], cell_root): raise ValueError("heldout exec v1 Sol record command drifted")
            sol = sol_module; artifacts = record.get("provider_artifacts")
            if not isinstance(artifacts, Mapping) or sol._artifact(cell_root, artifacts.get("codex_events"), "Codex events") != events or sol._artifact(cell_root, artifacts.get("codex_stderr"), "Codex stderr") != stderr or stable_bytes(cell_root / "responses" / "batch-0001.attempt-0001.message.json") != final: raise ValueError("heldout exec v1 Sol artifact association drifted")
            projection = v3._codex_event_projection(events, v3._load_parse_codex_events())
            labels = v3._strict_stderr_labels(stderr)
            expected_effective = {"requested_model": "gpt-5.6-sol", "local_effective_model": "gpt-5.6-sol", "requested_reasoning_effort": "high", "local_effective_reasoning_effort": "high", "provider_attested": False, "codex_cli_version": route["codex_cli_version"], "codex_command_identity": route["codex_command_identity"], "capture_jsonl_events": True, "tools_enabled": False, "web_search_enabled": False, "plans_enabled": False, "subagents_enabled": False, "stderr_label_evidence": labels, "event_projection": projection}
            if projection.get("completed_agent_message_text", "").encode("utf-8") != final or effective != expected_effective: raise ValueError("heldout exec v1 Sol lifecycle projection drifted")
            if stable_bytes(cell_root / "responses" / "batch-0001.attempt-0001.events.jsonl") != events: raise ValueError("heldout exec v1 Sol events copy drifted")
            expected_receipt = {"format_version": 1, "study_id": STUDY_ID, "kind": "sol_local_lifecycle_receipt", "cell_id": cell["cell_id"], "prepared_sha256": sha256(canonical(prepared)), "payload_sha256": sha256(payload), "response_schema_sha256": sha256(expected["response-schema.json"]), "native_contact_proven": False, "native_endpoint_contact_cardinality": "unproven", "process_launches": 1, "route_evidence": proof["route_evidence"], "raw_events_sha256": sha256(events), "raw_stderr_sha256": sha256(stderr), "final_response_sha256": sha256(final), "codex_record_sha256": sha256(canonical(record)), "effective_settings_sha256": sha256(canonical(effective)), "usage": projection["usage"]}
            if receipt != expected_receipt: raise ValueError("heldout exec v1 Sol receipt binding drifted")
            _validate_response(final, json.loads(expected["response-schema.json"].decode("utf-8")))
            expected_result = {"format_version": 1, "study_id": STUDY_ID, "kind": "sol_local_lifecycle_completed", "cell_id": cell["cell_id"], "provider_calls_made": None, "process_launches": 1, "receipt_sha256": sha256(canonical(receipt)), "final_response_sha256": sha256(final)}
            if result != expected_result: raise ValueError("heldout exec v1 Sol result binding drifted")
        rows.append({"cell_id": cell["cell_id"], "route_name": cell["route_name"], "payload_sha256": cell["payload_sha256"], "receipt_sha256": sha256(canonical(receipt)), "result_sha256": sha256(canonical(result))})
    if len(requests) != 44 or len(sessions) != 44: raise ValueError("heldout exec v1 Grok collection cardinality drifted")
    manifest = {"format_version": 1, "study_id": STUDY_ID, "kind": "heldout_execution_collection", "schedule_sha256": SCHEDULE_SHA256, "cells": rows, "grok_completed_native_identities": 44, "sol_native_endpoint_cardinality": "unproven", "provider_calls_made": None, "process_launches": 66, "confirmation": {"status": "unopened", "cells": 0}}
    manifest["manifest_sha256"] = sha256(canonical(manifest)); target = Path(manifest_path)
    if target.exists(): raise ValueError("heldout exec v1 refuses to overwrite collection manifest")
    _safe_output_ancestry(target.parent); _write_new(target, canonical(manifest)); return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument("--reconciliation-manifest", type=Path, required=True); parser.add_argument("--frozen-successor", type=Path, required=True); parser.add_argument("--hanna-csv", type=Path, required=True); parser.add_argument("--output-root", type=Path, required=True); parser.add_argument("--queue-root", type=Path, required=True); parser.add_argument("--acknowledgement-sha256", required=True); parser.add_argument("--prepare-all", action="store_true"); parser.add_argument("--cell-id"); parser.add_argument("--allow-remote", action="store_true")
    args = parser.parse_args(argv); common = {"reconciliation_manifest_path": args.reconciliation_manifest, "frozen_successor_path": args.frozen_successor, "hanna_csv_path": args.hanna_csv, "output_root": args.output_root, "queue_root": args.queue_root, "authorization_acknowledgement_sha256": args.acknowledgement_sha256}
    if args.prepare_all: result = prepare_all(**common)
    else:
        if not args.cell_id: parser.error("--cell-id is required for execution")
        result = execute_cell(**common, cell_id=args.cell_id, allow_remote=args.allow_remote)
    print(canonical(result).decode("utf-8"), end=""); return 0
