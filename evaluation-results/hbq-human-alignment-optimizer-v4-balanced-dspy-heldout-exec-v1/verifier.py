#!/usr/bin/env python3
"""Independent replay of the frozen held-out adapter-control and Codex evidence."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import math
import os
import re
import stat
import sys
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any, Mapping, Sequence


HERE = Path(__file__).resolve().parent
STUDY_ID = "hbq-human-alignment-optimizer-v4-balanced-dspy-heldout-exec-v1"
SCHEDULE_SHA256 = "de7fce6600b03181fd429a3018c89468b1d08cf74841905bd341329be4aa437e"
EXECUTOR_PATH = HERE / "executor.py"
EXECUTOR_SHA256 = "c8798475ae335b3a24f6deddbee627090718359a1e3b283396d892a15cb0720c"
EXECUTOR_CONTRACT_PATH = HERE / "study-contract.json"
EXECUTOR_CONTRACT_SHA256 = "0c15377c5d092b5b9a153e1692877f124725a0c1e09f73f3ed90092f2e605e40"
HELDOUT_STUDY_PATH = HERE.parent / "hbq-human-alignment-optimizer-v4-balanced-dspy-heldout-eval-v1" / "study.py"
HELDOUT_STUDY_SHA256 = "770b8c496df3c86dbc6ae3c7673d462428f81bcbddf84e493ea7c6710bd1b346"
NATIVE_PATH = HERE.parent / "hbq-human-alignment-optimizer-v4-native-subscription-v1" / "executor.py"
NATIVE_SHA256 = "6d93f69216d62bd0847aa6b338b6e2360587c82608669f78fbad245a34ba1c49"
EXEC_V3_PATH = HERE.parent / "hbq-human-alignment-optimizer-v4-native-subscription-exec-v3" / "executor.py"
EXEC_V3_SHA256 = "cea177b5185a84b682bd5271ae7384cd7742add872d31b45227433d72c7f7e90"
METRICS_PATH = HERE.parent / "hbq-human-alignment-optimizer-v2" / "analyze.py"
METRICS_SHA256 = "dc8479a962e4a0e2d0082a4619e0e52922d9d82663bd97bc6e17694781aef822"
R4_ADOPTION_SHA256 = "369c42f544ff316a53bf541ac18d712f31ed3d566d41444a815a3fd43bcdd73b"
R4_COLLECTION_MANIFEST_SHA256 = "97820229e2364ec601624e270d9dcda95aa46bb8697008a6768a63535bd4cda8"
PREPARED = frozenset({"payload.bin", "response-schema.json", "disclosure.json", "authorization-acknowledgement.json", "zero-charge-route-proof.json", "prepared.json"})
GROK_FILES = PREPARED | frozenset({"launch-intent.json", "adapter-stdout.bin", "adapter-control-envelope.json", "runtime-identity.json", "execution-receipt.json", "result.json"})
SOL_FILES = PREPARED | frozenset({"launch-intent.json", "raw-codex-events.bin", "raw-codex-stderr.bin", "raw-codex-final-response.bin", "codex-record.json", "effective-settings.json", "execution-receipt.json", "result.json", "responses"})
SOL_RESPONSES = frozenset({"batch-0001.attempt-0001.events.jsonl", "batch-0001.attempt-0001.message.json"})
MANIFEST_KEYS = frozenset({"format_version", "study_id", "kind", "schedule_sha256", "cells", "grok_completed_native_identities", "sol_native_endpoint_cardinality", "provider_calls_made", "process_launches", "confirmation", "manifest_sha256"})
REFERENCE_KEYS = frozenset({"cell_id", "route_name", "payload_sha256", "receipt_sha256", "result_sha256"})
BASELINE_ID = "candidate-52d1be4bc34e0018"
_PHASE_TOKEN = object()


@dataclass(frozen=True)
class GrokPhase:
    projection: Mapping[str, Any]
    collection_root: Path
    collection_evidence_path: Path
    adoption_path: Path
    adoption: Mapping[str, Any]
    r3_grok_digests: Mapping[str, str]
    r4_grok_digests: Mapping[str, str]
    _token: object


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def adapter_canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _plain(path: Path, *, directory: bool | None = None) -> None:
    info = os.lstat(path)
    if stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)):
        raise ValueError("HANNA heldout verifier rejects reparsed evidence")
    if directory is not None and (stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)) is False:
        raise ValueError("HANNA heldout verifier evidence type is unsafe")


def stable_bytes(path: Path) -> bytes:
    absolute, current = Path(os.path.abspath(path)), Path(Path(os.path.abspath(path)).anchor)
    for part in absolute.parts[1:]:
        current /= part
        _plain(current)
    _plain(absolute, directory=False)
    before = os.lstat(absolute)
    with absolute.open("rb") as handle:
        opened = os.fstat(handle.fileno())
        if (before.st_dev, before.st_ino, before.st_size) != (opened.st_dev, opened.st_ino, opened.st_size):
            raise ValueError("HANNA heldout verifier evidence changed before read")
        raw = handle.read()
        after = os.fstat(handle.fileno())
    if (opened.st_dev, opened.st_ino, opened.st_size) != (after.st_dev, after.st_ino, after.st_size):
        raise ValueError("HANNA heldout verifier evidence changed during read")
    return raw


def object_at(path: Path, label: str) -> dict[str, Any]:
    try:
        raw = stable_bytes(path)
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"HANNA heldout verifier {label} is invalid") from error
    if not isinstance(value, dict) or canonical(value) != raw:
        raise ValueError(f"HANNA heldout verifier {label} must be canonical JSON")
    return value


def load(path: Path, digest: str, name: str) -> ModuleType:
    raw = stable_bytes(path)
    if sha256(raw) != digest:
        raise ValueError(f"HANNA heldout verifier pinned {path.name} drifted")
    module = ModuleType(name); module.__file__ = str(path); sys.modules[name] = module
    exec(compile(raw, str(path), "exec"), module.__dict__)
    if sha256(stable_bytes(path)) != digest:
        raise ValueError(f"HANNA heldout verifier pinned {path.name} changed during load")
    return module


def dependencies() -> tuple[ModuleType, ModuleType]:
    executor = load(EXECUTOR_PATH, EXECUTOR_SHA256, "_heldout_executor")
    if sha256(stable_bytes(EXECUTOR_CONTRACT_PATH)) != EXECUTOR_CONTRACT_SHA256:
        raise ValueError("HANNA heldout verifier executor contract drifted")
    executor._contract()
    return executor, load(HELDOUT_STUDY_PATH, HELDOUT_STUDY_SHA256, "_heldout_study")


def _metrics() -> ModuleType:
    return load(METRICS_PATH, METRICS_SHA256, "_heldout_metrics")


def select_grok(projection: Mapping[str, Any]) -> dict[str, Any]:
    body = dict(projection)
    digest = body.pop("projection_sha256", None)
    if (
        digest != sha256(canonical(body))
        or projection.get("study_id") != STUDY_ID
        or projection.get("kind") != "heldout_independently_replayed_grok_observations"
        or projection.get("schedule_sha256") != SCHEDULE_SHA256
        or projection.get("geometry") != {"grok_cells": 44, "total_cells": 66}
        or projection.get("confirmation") != {"status": "unopened", "cells": 0}
        or projection.get("runtime_authority") != "none"
    ):
        raise ValueError("HANNA heldout Grok projection authority drifted")
    rows, targets = projection.get("observations"), projection.get("human_targets")
    if (
        not isinstance(rows, list)
        or not isinstance(targets, Mapping)
        or len(rows) != 44
        or any(not isinstance(row, Mapping) for row in rows)
        or len({row.get("cell_id") for row in rows}) != 44
    ):
        raise ValueError("HANNA heldout Grok projection is incomplete")
    grok = [dict(row) for row in rows]
    if any(
        row.get("route_name") != "grok_primary"
        or row.get("identity", {}).get("evidence_class") != "derived_from_pinned_completed_adapter_control"
        for row in grok
    ):
        raise ValueError("HANNA heldout Grok evidence ceiling/geometry drifted")
    candidates = sorted({row.get("candidate_id") for row in grok})
    if len(candidates) != 11 or BASELINE_ID not in candidates:
        raise ValueError("HANNA heldout fresh baseline is absent")
    metrics = _metrics()
    endpoints = []
    for candidate_id in candidates:
        candidate_rows = [row for row in grok if row.get("candidate_id") == candidate_id]
        if len(candidate_rows) != 4:
            raise ValueError("HANNA heldout Grok candidate is incomplete")
        bindings = {(row.get("item_id"), row.get("prompt_group_id")) for row in candidate_rows}
        if len(bindings) != 4:
            raise ValueError("HANNA heldout Grok item/group pairing drifted")
        endpoints.append(
            {
                "candidate_id": candidate_id,
                "endpoint": metrics._candidate_endpoint(candidate_rows, targets, expected_items=4, expected_groups=4),
                "item_ids": sorted(item for item, _group in bindings),
                "prompt_group_ids": sorted(group for _item, group in bindings),
            }
        )
    winner = min(endpoints, key=lambda item: (float(item["endpoint"]["mean_absolute_error"]), item["candidate_id"]))
    baseline = next(item for item in endpoints if item["candidate_id"] == BASELINE_ID)
    return {
        "format_version": 1,
        "kind": "heldout_grok_selection_frozen_before_sol",
        "grok_projection_sha256": projection["projection_sha256"],
        "baseline_candidate_id": BASELINE_ID,
        "grok_endpoints": endpoints,
        "selected_candidate_id": winner["candidate_id"],
        "selected_grok_mean_absolute_error": winner["endpoint"]["mean_absolute_error"],
        "baseline_grok_mean_absolute_error": baseline["endpoint"]["mean_absolute_error"],
        "strict_grok_improvement": float(winner["endpoint"]["mean_absolute_error"])
        < float(baseline["endpoint"]["mean_absolute_error"]),
        "tie_break": ["grok_mean_absolute_error:ascending", "candidate_id:lexicographic"],
    }


def schedule(*, reconciliation_manifest_path: Path, frozen_successor_path: Path, hanna_csv_path: Path) -> dict[str, Any]:
    _executor, study = dependencies()
    value = study.build_schedule(reconciliation_manifest_path=Path(reconciliation_manifest_path), frozen_successor_path=Path(frozen_successor_path), hanna_csv_path=Path(hanna_csv_path))
    if value.get("schedule_sha256") != SCHEDULE_SHA256:
        raise ValueError("HANNA heldout verifier schedule reconstruction drifted")
    return value


def _inventory(root: Path, expected: frozenset[str]) -> None:
    _plain(root, directory=True)
    entries = {entry.name: entry for entry in root.iterdir()}
    if set(entries) != expected:
        raise ValueError("HANNA heldout verifier root inventory is incomplete, terminal, or extra")
    for name, entry in entries.items():
        _plain(entry, directory=name == "responses")
    if "responses" in expected:
        responses = {entry.name: entry for entry in entries["responses"].iterdir()}
        if set(responses) != SOL_RESPONSES or any(_plain(entry, directory=False) is not None for entry in responses.values()):
            raise ValueError("HANNA heldout verifier Sol response inventory drifted")


def _inventory_digest(root: Path) -> str:
    _plain(root, directory=True)
    directories: list[str] = []
    files: list[dict[str, Any]] = []
    stack = [root]
    while stack:
        current = stack.pop()
        for entry in current.iterdir():
            _plain(entry)
            relative = entry.relative_to(root).as_posix()
            if entry.is_dir():
                directories.append(relative); stack.append(entry)
            else:
                raw = stable_bytes(entry)
                files.append({"name": relative, "bytes": len(raw), "sha256": sha256(raw)})
    return sha256(canonical({"directories": sorted(directories), "files": sorted(files, key=lambda item: item["name"])}))


def _collection_digest(root: Path, expected_cells: set[str]) -> tuple[str, dict[str, str]]:
    _plain(root, directory=True)
    entries = {entry.name: entry for entry in root.iterdir()}
    if set(entries) != expected_cells or any(_plain(entry, directory=True) is not None for entry in entries.values()):
        raise ValueError("HANNA heldout verifier adoption collection inventory drifted")
    digests = {cell_id: _inventory_digest(entries[cell_id]) for cell_id in sorted(entries)}
    return sha256(canonical([{"cell_id": cell_id, "inventory_sha256": digests[cell_id]} for cell_id in sorted(digests)])), digests


def _collection_digest_after_grok(root: Path, expected_cells: set[str], grok_digests: Mapping[str, str]) -> tuple[str, dict[str, str]]:
    _plain(root, directory=True)
    entries = {entry.name: entry for entry in root.iterdir()}
    if set(entries) != expected_cells or any(_plain(entry, directory=True) is not None for entry in entries.values()):
        raise ValueError("HANNA heldout verifier adoption collection inventory drifted")
    digests = {cell_id: grok_digests[cell_id] if cell_id in grok_digests else _inventory_digest(entries[cell_id]) for cell_id in sorted(entries)}
    return sha256(canonical([{"cell_id": cell_id, "inventory_sha256": digests[cell_id]} for cell_id in sorted(digests)])), digests


def _adoption_grok(path: Path, root: Path, frozen: Mapping[str, Any]) -> dict[str, Any]:
    raw = stable_bytes(path)
    if sha256(raw) != R4_ADOPTION_SHA256:
        raise ValueError("HANNA heldout r4 adoption manifest hash drifted")
    adoption = object_at(path, "r4 adoption manifest")
    expected_keys = {"copied_grok_cells", "format_version", "geometry", "kind", "operation", "prior_r2_adoption", "r4_native_zero_contact_preparations", "schedule_sha256", "source_roots", "study_id"}
    if set(adoption) != expected_keys or adoption.get("format_version") != 1 or adoption.get("study_id") != STUDY_ID or adoption.get("kind") != "provider_free_exact_r3_to_r4_heldout_adoption" or adoption.get("schedule_sha256") != SCHEDULE_SHA256 or adoption.get("geometry") != {"confirmation": {"cells": 0, "status": "unopened"}, "copied_grok_cells": 44, "r4_native_sol_preparations": 22, "total_scheduled_cells": 66} or adoption.get("operation") != {"no_resend": True, "process_launches": 0, "provider_calls_made": 0, "source_roots_mutated": False}:
        raise ValueError("HANNA heldout r4 adoption authority drifted")
    source = adoption.get("source_roots")
    if not isinstance(source, Mapping) or set(source) != {"r3", "r3_collection_inventory_sha256", "r4", "r4_collection_inventory_sha256"} or Path(source["r4"]) != root or not all(isinstance(source[key], str) and re.fullmatch(r"[0-9a-f]{64}", source[key]) for key in ("r3_collection_inventory_sha256", "r4_collection_inventory_sha256")):
        raise ValueError("HANNA heldout r4 adoption source roots drifted")
    r3 = Path(source["r3"]); _plain(r3, directory=True)
    grok_rows = [row for row in frozen["cells"] if row["route_name"] == "grok_primary"]
    copied = adoption.get("copied_grok_cells")
    if not isinstance(copied, list) or len(copied) != 44 or {row.get("cell_id") for row in copied if isinstance(row, Mapping)} != {row["cell_id"] for row in grok_rows}:
        raise ValueError("HANNA heldout r4 adoption Grok geometry drifted")
    for item in copied:
        row = next(row for row in grok_rows if row["cell_id"] == item["cell_id"])
        if any(item.get(key) != row.get(key) for key in ("cell_id", "ordinal", "sample_id", "candidate_id", "item_id", "prompt_group_id", "payload_sha256")):
            raise ValueError("HANNA heldout r4 adoption cell binding drifted")
        r3_digest, r4_digest = _inventory_digest(r3 / row["cell_id"]), _inventory_digest(root / row["cell_id"])
        if item.get("r3_inventory_sha256") != r3_digest or item.get("r4_inventory_sha256") != r4_digest or r3_digest != r4_digest:
            raise ValueError("HANNA heldout r4 adoption copied root inventory drifted")
    return adoption


def _finish_adoption(adoption: Mapping[str, Any], root: Path, frozen: Mapping[str, Any], *, r3_grok_digests: Mapping[str, str] | None = None, r4_grok_digests: Mapping[str, str] | None = None) -> None:
    source = adoption["source_roots"]; r3 = Path(source["r3"])
    sol = adoption.get("r4_native_zero_contact_preparations")
    if not isinstance(sol, list) or len(sol) != 22 or {item.get("cell_id") for item in sol if isinstance(item, Mapping)} != {row["cell_id"] for row in frozen["cells"] if row["route_name"] == "sol_validation"}:
        raise ValueError("HANNA heldout r4 adoption Sol preparation geometry drifted")
    expected_cells = {row["cell_id"] for row in frozen["cells"]}
    r3_collection, r3_digests = (_collection_digest(r3, expected_cells) if r3_grok_digests is None else _collection_digest_after_grok(r3, expected_cells, r3_grok_digests))
    r4_collection, r4_digests = (_collection_digest(root, expected_cells) if r4_grok_digests is None else _collection_digest_after_grok(root, expected_cells, r4_grok_digests))
    if r3_collection != source["r3_collection_inventory_sha256"] or r4_collection != source["r4_collection_inventory_sha256"]:
        raise ValueError("HANNA heldout r4 adoption aggregate inventory drifted")
    for item in sol:
        row = next(row for row in frozen["cells"] if row["cell_id"] == item["cell_id"])
        expected = {"cell_id": row["cell_id"], "ordinal": row["ordinal"], "sample_id": row["sample_id"], "candidate_id": row["candidate_id"], "item_id": row["item_id"], "prompt_group_id": row["prompt_group_id"], "payload_sha256": row["payload_sha256"], "inventory_sha256": r4_digests[row["cell_id"]], "prepared_sha256": sha256(stable_bytes(root / row["cell_id"] / "prepared.json")), "prepared_provider_calls_made": 0, "prepared_process_launches": 0}
        if item != expected:
            raise ValueError("HANNA heldout r4 adoption Sol inventory binding drifted")


def _adoption(path: Path, root: Path, frozen: Mapping[str, Any]) -> dict[str, Any]:
    adoption = _adoption_grok(path, root, frozen)
    _finish_adoption(adoption, root, frozen)
    return adoption


def _grok_route(route: Mapping[str, Any], evidence: Mapping[str, Any]) -> None:
    required = {"name", "model", "adapter", "provider", "destination", "reasoning_effort", "reported_model", "grok_command", "grok_command_identity", "cli_version_identity", "grok_cli_version", "cost_evidence", "subscription_receipt_hash"}
    policy = {"name": "grok-build-grok-4.6", "model": "grok-4.6", "adapter": "grok_exec", "provider": "xai_grok_build", "destination": "xai_grok_build_subscription", "account_class": "subscription", "zero_charge": True, "armed": True, "health": "healthy", "reasoning_effort": "high", "reported_model": "grok-4.6-build", "identity_evidence": "requested_only"}
    if not isinstance(route, Mapping) or not required <= set(route) or any(route.get(key) != value for key, value in policy.items()) or "public_repo" not in route.get("allowed_payload_classes", []) or not isinstance(route.get("grok_command"), list) or len(route["grok_command"]) != 1 or any(not isinstance(value, str) or not value for value in route["grok_command"]) or not isinstance(route.get("grok_command_identity"), dict) or not isinstance(route.get("cli_version_identity"), dict) or not isinstance(route.get("grok_cli_version"), str) or not route["grok_cli_version"] or not isinstance(route.get("cost_evidence"), Mapping):
        raise ValueError("HANNA heldout verifier Grok route policy drifted")
    cost_hash, subscription = route["cost_evidence"].get("evidence_hash"), route.get("subscription_receipt_hash")
    expected = {"route_name": route["name"], "route_sha256": sha256(canonical(dict(route))), "registry_sha256": evidence.get("registry_sha256"), "cost_evidence_hash": cost_hash, "subscription_receipt_hash": subscription, "grok_command_identity_sha256": sha256(canonical(route["grok_command_identity"])), "cli_version_identity_sha256": sha256(canonical(route["cli_version_identity"])), "grok_cli_version": route["grok_cli_version"]}
    if not all(isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) for value in (cost_hash, subscription, evidence.get("registry_sha256"))) or not isinstance(evidence, Mapping) or evidence != expected:
        raise ValueError("HANNA heldout verifier Grok route proof drifted")


def _sol_route(route: Mapping[str, Any], evidence: Mapping[str, Any], exec_v3: ModuleType) -> None:
    required = {"name", "model", "adapter", "provider", "destination", "account_class", "zero_charge", "armed", "health", "reasoning_effort", "identity_evidence", "trusted", "allowed_payload_classes", "codex_command", "command", "command_identity", "codex_command_identity", "cli_version_identity", "auth_status_identity", "codex_cli_version", "auth_receipt_hash", "cost_evidence"}
    policy = {"name": "codex-chatgpt-gpt-5.6-sol", "model": "gpt-5.6-sol", "adapter": "codex_exec", "provider": "openai_codex", "destination": "openai_codex_chatgpt_subscription", "account_class": "subscription", "zero_charge": True, "armed": True, "health": "healthy", "reasoning_effort": "high", "identity_evidence": "requested_only", "trusted": True}
    if not isinstance(route, Mapping) or not required <= set(route) or any(route.get(key) != value for key, value in policy.items()) or "public_repo" not in route.get("allowed_payload_classes", []) or not isinstance(route.get("codex_command"), list) or len(route["codex_command"]) != 1 or any(not isinstance(value, str) or not value for value in route["codex_command"]) or not isinstance(route.get("command"), list) or len(route["command"]) != 2 or Path(route["command"][1]).resolve() != exec_v3.CODEX_ADAPTER_PATH.resolve() or any(not isinstance(route.get(key), dict) for key in ("command_identity", "codex_command_identity", "cli_version_identity", "auth_status_identity")) or not isinstance(route.get("codex_cli_version"), str) or not route["codex_cli_version"] or not isinstance(route.get("auth_receipt_hash"), str) or not re.fullmatch(r"[0-9a-f]{64}", route["auth_receipt_hash"]) or not isinstance(route.get("cost_evidence"), Mapping):
        raise ValueError("HANNA heldout verifier Sol route policy drifted")
    cost = route["cost_evidence"]
    expected = {"route_name": route["name"], "route_sha256": sha256(canonical(dict(route))), "registry_sha256": evidence.get("registry_sha256"), "cost_evidence_hash": cost.get("evidence_hash"), "auth_receipt_hash": route["auth_receipt_hash"], "cost_evidence_checked_at": cost.get("checked_at"), "cost_evidence_expires_at": cost.get("expires_at"), "wrapper_command_identity_sha256": sha256(canonical(route["command_identity"])), "codex_command_identity_sha256": sha256(canonical(route["codex_command_identity"])), "cli_version_identity_sha256": sha256(canonical(route["cli_version_identity"])), "auth_status_identity_sha256": sha256(canonical(route["auth_status_identity"])), "codex_cli_version": route["codex_cli_version"], "codex_adapter_sha256": exec_v3.CODEX_ADAPTER_SHA256}
    hex_keys = {"route_sha256", "registry_sha256", "cost_evidence_hash", "auth_receipt_hash", "wrapper_command_identity_sha256", "codex_command_identity_sha256", "cli_version_identity_sha256", "auth_status_identity_sha256", "codex_adapter_sha256"}
    if not all(isinstance(cost.get(key), str) and cost[key] for key in ("evidence_hash", "checked_at", "expires_at")) or not isinstance(evidence, Mapping) or evidence != expected or any(not isinstance(evidence.get(key), str) or not re.fullmatch(r"[0-9a-f]{64}", evidence[key]) for key in hex_keys):
        raise ValueError("HANNA heldout verifier Sol route proof drifted")


def _prepared(executor: ModuleType, study: ModuleType, root: Path, row: Mapping[str, Any], frozen: Mapping[str, Any]) -> tuple[bytes, bytes, dict[str, Any], dict[str, Any]]:
    payload, schema = study.payload_bytes(row), executor._schema(study.payload_bytes(row))
    if stable_bytes(root / "payload.bin") != payload or stable_bytes(root / "response-schema.json") != schema:
        raise ValueError("HANNA heldout verifier payload or schema replay drifted")
    disclosure, acknowledgement = object_at(root / "disclosure.json", "disclosure"), object_at(root / "authorization-acknowledgement.json", "acknowledgement")
    proof, prepared = object_at(root / "zero-charge-route-proof.json", "route proof"), object_at(root / "prepared.json", "prepared record")
    destination, evidence, route = disclosure.get("destination"), proof.get("route_evidence"), prepared.get("route")
    acknowledgement_hash = acknowledgement.get("acknowledgement_sha256")
    if not isinstance(destination, str) or not destination or not isinstance(evidence, Mapping) or not isinstance(route, Mapping) or not isinstance(acknowledgement_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", acknowledgement_hash):
        raise ValueError("HANNA heldout verifier preparation route/acknowledgement is invalid")
    expected_disclosure = {"format_version": 1, "study_id": STUDY_ID, "kind": "local_first_exact_outbound_disclosure", "cell_id": row["cell_id"], "schedule_sha256": frozen["schedule_sha256"], "route_name": row["route_name"], "destination": destination, "payload": {"bytes": len(payload), "sha256": sha256(payload), "text": payload.decode("utf-8")}, "response_schema_sha256": sha256(schema), "tools_enabled": False, "web_search_enabled": False, "plans_enabled": False, "subagents_enabled": False, "provider_calls_made": 0, "process_launches": 0}
    expected_acknowledgement = {"format_version": 1, "study_id": STUDY_ID, "kind": "caller_authorization_acknowledgement_reference", "cell_id": row["cell_id"], "acknowledgement_sha256": acknowledgement_hash, "disclosure_sha256": sha256(canonical(disclosure)), "destination": destination}
    expected_proof = {"format_version": 1, "study_id": STUDY_ID, "kind": "current_zero_charge_route_proof", "cell_id": row["cell_id"], "route_evidence": dict(evidence), "zero_charge_only": True, "paid_fallback_forbidden": True, "provider_calls_made": 0, "process_launches": 0}
    exec_v3 = load(EXEC_V3_PATH, EXEC_V3_SHA256, "_prepared_exec_v3")
    if row["route_name"] == "grok_primary": _grok_route(route, evidence)
    else: _sol_route(route, evidence, exec_v3)
    if destination != route.get("destination"):
        raise ValueError("HANNA heldout verifier disclosure destination drifted")
    sol_executable = prepared.get("sol_executable")
    if row["route_name"] == "sol_validation" and (not isinstance(sol_executable, str) or not sol_executable): raise ValueError("HANNA heldout verifier Sol executable binding is invalid")
    if row["route_name"] == "grok_primary" and sol_executable is not None: raise ValueError("HANNA heldout verifier Grok has a Sol executable binding")
    expected_prepared = {"format_version": 1, "study_id": STUDY_ID, "kind": "heldout_native_preparation", "cell": dict(row), "schedule_sha256": frozen["schedule_sha256"], "payload_sha256": sha256(payload), "response_schema_sha256": sha256(schema), "route": dict(route), "route_evidence": dict(evidence), "disclosure_sha256": sha256(canonical(disclosure)), "acknowledgement_sha256": sha256(canonical(acknowledgement)), "route_proof_sha256": sha256(canonical(proof)), "sol_executable": sol_executable, "provider_calls_made": 0, "process_launches": 0, "confirmation": {"status": "unopened", "cells": 0}, "runtime_authority": "none"}
    if disclosure != expected_disclosure or acknowledgement != expected_acknowledgement or proof != expected_proof or prepared != expected_prepared:
        raise ValueError("HANNA heldout verifier prepared artifact replay drifted")
    return payload, schema, prepared, dict(evidence)


def _intent(root: Path, row: Mapping[str, Any], prepared: Mapping[str, Any]) -> dict[str, Any]:
    intent = object_at(root / "launch-intent.json", "launch intent")
    expected = {"format_version": 1, "study_id": STUDY_ID, "kind": "process_launch_intent_not_native_contact", "cell_id": row["cell_id"], "prepared_sha256": sha256(canonical(prepared)), "native_contact_proven": False}
    if intent != expected:
        raise ValueError("HANNA heldout verifier launch intent drifted")
    return intent


def _control(raw: bytes, *, payload: bytes, route: Mapping[str, Any], evidence: Mapping[str, Any], native: ModuleType) -> tuple[dict[str, Any], dict[str, float], dict[str, bool], dict[str, Any]]:
    try: control = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error: raise ValueError("HANNA heldout verifier Grok adapter control is invalid") from error
    if not isinstance(control, dict) or set(control) != {"control", "result"} or control.get("control") != {"version": 1, "state": "completed"}:
        raise ValueError("HANNA heldout verifier Grok control is not completed")
    result = control.get("result")
    if not isinstance(result, dict) or set(result) != {"schema_version", "request_hash", "output", "output_hash", "runtime"} or result.get("schema_version") != 1 or result.get("request_hash") != sha256(adapter_canonical({"prompt": payload.decode("utf-8")})):
        raise ValueError("HANNA heldout verifier Grok request binding drifted")
    output, runtime = result.get("output"), result.get("runtime")
    v2 = native._load_v3().v2_module()
    if not isinstance(output, dict) or result.get("output_hash") != sha256(adapter_canonical(output)):
        raise ValueError("HANNA heldout verifier Grok output hash drifted")
    scores = v2._validate_scores(output); coverage = {dimension: bool(output["coverage"][dimension]) for dimension in v2.DIMENSIONS}
    required = {"adapter_version", "requested_model", "reported_model", "requested_reasoning_effort", "reasoning_attested", "reasoning_attestation", "identity_evidence", "cli_version", "session_id_hash", "request_id_hash", "envelope_hash", "command_identity", "command_identity_hash", "subscription_receipt_hash", "execution_policy", "usage_telemetry", "nonvisual_max_turns", "observed_turns"}
    command_hash = sha256(adapter_canonical({"adapter_version": 1, "grok_command": route["grok_command"], "model": route["model"], "reported_model": route["reported_model"], "reasoning_effort": route["reasoning_effort"]}))
    if not isinstance(runtime, dict) or set(runtime) != required or runtime.get("adapter_version") != 1 or runtime.get("requested_model") != route["model"] or runtime.get("reported_model") != route["reported_model"] or runtime.get("requested_reasoning_effort") != route["reasoning_effort"] or runtime.get("reasoning_attested") is not False or runtime.get("reasoning_attestation") != "not_reported_by_grok_build_cli" or runtime.get("identity_evidence") != "requested_only" or runtime.get("execution_policy") != "bounded_nonvisual_read_only" or runtime.get("nonvisual_max_turns") != 1 or runtime.get("observed_turns") != 1 or runtime.get("cli_version") != route["grok_cli_version"] or runtime.get("subscription_receipt_hash") != route["subscription_receipt_hash"] or runtime.get("command_identity") != route["grok_command_identity"] or runtime.get("command_identity_hash") != command_hash:
        raise ValueError("HANNA heldout verifier Grok runtime semantics drifted")
    telemetry = runtime.get("usage_telemetry")
    if not isinstance(telemetry, dict) or set(telemetry) - {"status", "total_cost_usd", "total_cost_usd_ticks", "model_cost_usd"} or telemetry.get("status") not in {"reported", "not_reported"} or (telemetry.get("status") == "not_reported" and set(telemetry) != {"status"}) or (telemetry.get("status") == "reported" and set(telemetry) == {"status"}):
        raise ValueError("HANNA heldout verifier Grok telemetry drifted")
    for key in ("total_cost_usd", "model_cost_usd"):
        if key in telemetry and (not isinstance(telemetry[key], (int, float)) or isinstance(telemetry[key], bool) or not math.isfinite(telemetry[key]) or telemetry[key] < 0):
            raise ValueError("HANNA heldout verifier Grok telemetry is invalid")
    if "total_cost_usd_ticks" in telemetry and (type(telemetry["total_cost_usd_ticks"]) is not int or telemetry["total_cost_usd_ticks"] < 0):
        raise ValueError("HANNA heldout verifier Grok telemetry is invalid")
    if any(not isinstance(runtime.get(key), str) or not re.fullmatch(r"[0-9a-f]{64}", runtime[key]) for key in ("request_id_hash", "session_id_hash", "envelope_hash", "command_identity_hash")):
        raise ValueError("HANNA heldout verifier Grok runtime identity drifted")
    return control, scores, coverage, runtime


def _grok(root: Path, row: Mapping[str, Any], payload: bytes, schema: bytes, prepared: Mapping[str, Any], evidence: Mapping[str, Any], native: ModuleType) -> dict[str, Any]:
    raw, control_file, runtime_file = stable_bytes(root / "adapter-stdout.bin"), object_at(root / "adapter-control-envelope.json", "Grok control copy"), object_at(root / "runtime-identity.json", "Grok runtime copy")
    route = prepared["route"]
    control, scores, coverage, runtime = _control(raw, payload=payload, route=route, evidence=evidence, native=native)
    if control_file != control or runtime_file != runtime:
        raise ValueError("HANNA heldout verifier Grok persisted control copies drifted")
    receipt, result = object_at(root / "execution-receipt.json", "Grok receipt"), object_at(root / "result.json", "Grok result")
    expected_receipt = {"format_version": 1, "study_id": STUDY_ID, "kind": "grok_completed_adapter_receipt", "cell_id": row["cell_id"], "prepared_sha256": sha256(canonical(prepared)), "payload_sha256": sha256(payload), "response_schema_sha256": sha256(schema), "adapter_stdout_sha256": sha256(raw), "adapter_control_sha256": sha256(canonical(control)), "runtime_sha256": sha256(canonical(runtime)), "output_sha256": control["result"]["output_hash"], "request_id_hash": runtime["request_id_hash"], "session_id_hash": runtime["session_id_hash"], "native_contact_proven": True, "native_endpoint_contact_cardinality": "proven_exactly_one", "route_evidence": dict(evidence)}
    expected_result = {"format_version": 1, "study_id": STUDY_ID, "kind": "grok_completed", "cell_id": row["cell_id"], "provider_calls_made": 1, "process_launches": 1, "receipt_sha256": sha256(canonical(receipt)), "adapter_stdout_sha256": sha256(raw), "output_sha256": control["result"]["output_hash"]}
    if receipt != expected_receipt or result != expected_result:
        raise ValueError("HANNA heldout verifier Grok receipt/result binding drifted")
    identity = {"provider": "xai_grok_build", "contact_id": runtime["request_id_hash"], "session_id": runtime["session_id_hash"], "evidence_class": "derived_from_pinned_completed_adapter_control", "reasoning_attested": False}
    return {**dict(row), "scores": scores, "coverage": coverage, "request_bytes": len(payload), "identity": identity}


def _sol(root: Path, row: Mapping[str, Any], payload: bytes, schema: bytes, prepared: Mapping[str, Any], evidence: Mapping[str, Any], native: ModuleType, exec_v3: ModuleType) -> dict[str, Any]:
    events, stderr, response = stable_bytes(root / "raw-codex-events.bin"), stable_bytes(root / "raw-codex-stderr.bin"), stable_bytes(root / "raw-codex-final-response.bin")
    if events != stable_bytes(root / "responses" / "batch-0001.attempt-0001.events.jsonl") or response != stable_bytes(root / "responses" / "batch-0001.attempt-0001.message.json"):
        raise ValueError("HANNA heldout verifier Sol raw response copies drifted")
    record, effective = object_at(root / "codex-record.json", "Codex record"), object_at(root / "effective-settings.json", "Sol effective settings")
    artifacts = record.get("provider_artifacts")
    if not isinstance(artifacts, Mapping): raise ValueError("HANNA heldout verifier Sol artifacts are absent")
    def artifact(name: str, raw: bytes) -> None:
        value = artifacts.get(name)
        if not isinstance(value, Mapping) or set(value) != {"path", "bytes", "sha256"} or value.get("bytes") != len(raw) or value.get("sha256") != sha256(raw): raise ValueError("HANNA heldout verifier Sol artifact binding drifted")
    artifact("codex_events", events); artifact("codex_stderr", stderr)
    labels, projection = exec_v3._strict_stderr_labels(stderr), exec_v3._codex_event_projection(events, exec_v3._load_parse_codex_events())
    thread_id = projection.get("thread_id")
    if not isinstance(thread_id, str) or not thread_id or projection.get("completed_agent_message_text", "").encode("utf-8") != response or record.get("reported") != labels or not isinstance(record.get("command"), list) or record["command"] != exec_v3._expected_codex_command(prepared["sol_executable"], root):
        raise ValueError("HANNA heldout verifier Sol lifecycle binding drifted")
    expected_effective = {"requested_model": "gpt-5.6-sol", "local_effective_model": "gpt-5.6-sol", "requested_reasoning_effort": "high", "local_effective_reasoning_effort": "high", "provider_attested": False, "codex_cli_version": effective.get("codex_cli_version"), "codex_command_identity": effective.get("codex_command_identity"), "capture_jsonl_events": True, "tools_enabled": False, "web_search_enabled": False, "plans_enabled": False, "subagents_enabled": False, "stderr_label_evidence": labels, "event_projection": projection}
    route = prepared["route"]
    if effective != expected_effective or effective["codex_command_identity"] != route["codex_command_identity"] or evidence.get("codex_cli_version") != effective["codex_cli_version"] or evidence.get("codex_command_identity_sha256") != sha256(canonical(effective["codex_command_identity"])):
        raise ValueError("HANNA heldout verifier Sol effective settings drifted")
    identity = {"provider": "openai_codex", "route_name": "codex-chatgpt-gpt-5.6-sol", "requested_model": "gpt-5.6-sol", "requested_reasoning_effort": "high", "effective_model": "gpt-5.6-sol", "provider_reported_model": None, "identity_evidence": "requested_and_local_effective_settings_only_not_provider_attested", "reasoning_attested": False, "transport_identity": "codex_chatgpt_subscription_exec_tool_free_v1", "contact_id": f"unproven-native-endpoint-contact-for-local-thread:{thread_id}", "session_id": f"local-codex-thread-session:{labels['session_id'] or thread_id}", "evidence_class": "local_lifecycle_verified_native_endpoint_contact_cardinality_unproven"}
    scores, coverage = native._extract_native(response, row=row, identity=identity)
    receipt, result = object_at(root / "execution-receipt.json", "Sol receipt"), object_at(root / "result.json", "Sol result")
    expected_receipt = {"format_version": 1, "study_id": STUDY_ID, "kind": "sol_local_lifecycle_receipt", "cell_id": row["cell_id"], "prepared_sha256": sha256(canonical(prepared)), "payload_sha256": sha256(payload), "response_schema_sha256": sha256(schema), "native_contact_proven": False, "native_endpoint_contact_cardinality": "unproven", "process_launches": 1, "route_evidence": dict(evidence), "raw_events_sha256": sha256(events), "raw_stderr_sha256": sha256(stderr), "final_response_sha256": sha256(response), "codex_record_sha256": sha256(canonical(record)), "effective_settings_sha256": sha256(canonical(effective)), "usage": projection["usage"]}
    expected_result = {"format_version": 1, "study_id": STUDY_ID, "kind": "sol_local_lifecycle_completed", "cell_id": row["cell_id"], "provider_calls_made": None, "process_launches": 1, "receipt_sha256": sha256(canonical(receipt)), "final_response_sha256": sha256(response)}
    if receipt != expected_receipt or result != expected_result:
        raise ValueError("HANNA heldout verifier Sol receipt/result binding drifted")
    return {**dict(row), "scores": scores, "coverage": coverage, "request_bytes": len(payload), "identity": identity}


def _context(*, collection_evidence_path: Path, collection_root: Path, r4_adoption_path: Path | None, reconciliation_manifest_path: Path, frozen_successor_path: Path, hanna_csv_path: Path) -> tuple[ModuleType, ModuleType, ModuleType, ModuleType, dict[str, Any], dict[str, Any], list[Mapping[str, Any]], Path]:
    executor, study = dependencies()
    native = load(NATIVE_PATH, NATIVE_SHA256, "_heldout_native"); exec_v3 = load(EXEC_V3_PATH, EXEC_V3_SHA256, "_heldout_exec_v3")
    frozen = schedule(reconciliation_manifest_path=Path(reconciliation_manifest_path), frozen_successor_path=Path(frozen_successor_path), hanna_csv_path=Path(hanna_csv_path))
    root_base = Path(collection_root); _plain(root_base, directory=True)
    if r4_adoption_path is not None: _adoption_grok(Path(r4_adoption_path), root_base, frozen)
    manifest = object_at(Path(collection_evidence_path), "collection manifest")
    body = dict(manifest); manifest_sha = body.pop("manifest_sha256", None)
    expected = {"format_version": 1, "study_id": STUDY_ID, "kind": "heldout_execution_collection", "schedule_sha256": SCHEDULE_SHA256, "grok_completed_native_identities": 44, "sol_native_endpoint_cardinality": "unproven", "provider_calls_made": None, "process_launches": 66, "confirmation": {"status": "unopened", "cells": 0}}
    if set(manifest) != MANIFEST_KEYS or manifest_sha != R4_COLLECTION_MANIFEST_SHA256 or manifest_sha != sha256(canonical(body)) or any(manifest.get(key) != value for key, value in expected.items()): raise ValueError("HANNA heldout verifier manifest identity drifted")
    references, rows = manifest.get("cells"), frozen["cells"]
    if not isinstance(references, list) or len(references) != 66 or any(not isinstance(item, Mapping) or set(item) != REFERENCE_KEYS for item in references) or [item["cell_id"] for item in references] != [row["cell_id"] for row in rows]: raise ValueError("HANNA heldout verifier rejects partial, aggregate, swapped, or confirmation evidence")
    if {entry.name for entry in root_base.iterdir()} != {row["cell_id"] for row in rows}: raise ValueError("HANNA heldout verifier collection root inventory drifted")
    return executor, study, native, exec_v3, frozen, manifest, list(references), root_base


def _verify_endpoint(*, route_name: str, executor: ModuleType, study: ModuleType, native: ModuleType, exec_v3: ModuleType, frozen: Mapping[str, Any], references: Sequence[Mapping[str, Any]], root_base: Path) -> list[dict[str, Any]]:
    rows = [row for row in frozen["cells"] if row["route_name"] == route_name]
    index = {reference["cell_id"]: reference for reference in references}
    observations, identities = [], set()
    for row in rows:
        reference = index[row["cell_id"]]
        if reference.get("route_name") != row["route_name"] or reference.get("payload_sha256") != row["payload_sha256"]: raise ValueError("HANNA heldout verifier collection row binding drifted")
        root, grok = root_base / row["cell_id"], route_name == "grok_primary"
        _inventory(root, GROK_FILES if grok else SOL_FILES); payload, schema, prepared, evidence = _prepared(executor, study, root, row, frozen); _intent(root, row, prepared)
        observation = _grok(root, row, payload, schema, prepared, evidence, native) if grok else _sol(root, row, payload, schema, prepared, evidence, native, exec_v3)
        if reference.get("receipt_sha256") != sha256(stable_bytes(root / "execution-receipt.json")) or reference.get("result_sha256") != sha256(stable_bytes(root / "result.json")): raise ValueError("HANNA heldout verifier collection hashes drifted")
        identity = observation["identity"]; key = (identity["provider"], identity["contact_id"], identity["session_id"])
        if key in identities: raise ValueError("HANNA heldout verifier duplicate endpoint identity")
        identities.add(key); observations.append(observation)
    expected_count = 44 if route_name == "grok_primary" else 22
    if len(observations) != expected_count: raise ValueError("HANNA heldout verifier endpoint geometry drifted")
    for candidate_id in {row["candidate_id"] for row in rows}:
        expected = {(row["item_id"], row["prompt_group_id"]) for row in rows if row["candidate_id"] == candidate_id}
        observed = {(row["item_id"], row["prompt_group_id"]) for row in observations if row["candidate_id"] == candidate_id}
        if observed != expected or len(observed) != (4 if route_name == "grok_primary" else 2):
            raise ValueError("HANNA heldout verifier endpoint item/group pairing drifted")
    return observations


def verify_grok_phase(*, collection_evidence_path: Path, collection_root: Path, r4_adoption_path: Path, reconciliation_manifest_path: Path, frozen_successor_path: Path, hanna_csv_path: Path) -> GrokPhase:
    executor, study, native, exec_v3, frozen, manifest, references, root_base = _context(collection_evidence_path=collection_evidence_path, collection_root=collection_root, r4_adoption_path=None, reconciliation_manifest_path=reconciliation_manifest_path, frozen_successor_path=frozen_successor_path, hanna_csv_path=hanna_csv_path)
    adoption = _adoption_grok(Path(r4_adoption_path), root_base, frozen)
    observations = _verify_endpoint(route_name="grok_primary", executor=executor, study=study, native=native, exec_v3=exec_v3, frozen=frozen, references=references, root_base=root_base)
    targets = native._load_v3().v2_module()._human_targets(study=native._load_v3().v2_module().parent_modules()[0], frozen_successor_path=Path(frozen_successor_path), hanna_csv_path=Path(hanna_csv_path))
    projection = {"format_version": 1, "study_id": STUDY_ID, "kind": "heldout_independently_replayed_grok_observations", "collection_evidence_sha256": sha256(stable_bytes(Path(collection_evidence_path))), "r4_adoption_sha256": sha256(stable_bytes(Path(r4_adoption_path))), "dependencies": {"verifier_source_sha256": sha256(stable_bytes(Path(__file__))), "executor_sha256": EXECUTOR_SHA256, "executor_contract_sha256": EXECUTOR_CONTRACT_SHA256, "heldout_study_sha256": HELDOUT_STUDY_SHA256, "native_extractor_sha256": NATIVE_SHA256, "equal_group_metrics_sha256": METRICS_SHA256}, "schedule_sha256": SCHEDULE_SHA256, "observations": observations, "human_targets": targets, "geometry": {"grok_cells": 44, "total_cells": 66}, "grok_evidence_class": "derived_from_pinned_completed_adapter_control", "confirmation": {"status": "unopened", "cells": 0}, "runtime_authority": "none"}
    projection["projection_sha256"] = sha256(canonical(projection))
    r3_grok_digests = {item["cell_id"]: item["r3_inventory_sha256"] for item in adoption["copied_grok_cells"]}
    r4_grok_digests = {item["cell_id"]: item["r4_inventory_sha256"] for item in adoption["copied_grok_cells"]}
    return GrokPhase(projection=projection, collection_root=root_base.resolve(), collection_evidence_path=Path(collection_evidence_path).resolve(), adoption_path=Path(r4_adoption_path).resolve(), adoption=adoption, r3_grok_digests=r3_grok_digests, r4_grok_digests=r4_grok_digests, _token=_PHASE_TOKEN)


def verify_sol_phase(*, grok_phase: GrokPhase, frozen_selection: Mapping[str, Any], collection_evidence_path: Path, collection_root: Path, reconciliation_manifest_path: Path, frozen_successor_path: Path, hanna_csv_path: Path) -> dict[str, Any]:
    if not isinstance(grok_phase, GrokPhase) or grok_phase._token is not _PHASE_TOKEN or grok_phase.collection_root != Path(collection_root).resolve() or grok_phase.collection_evidence_path != Path(collection_evidence_path).resolve():
        raise ValueError("HANNA heldout verifier Sol phase requires an in-memory Grok evidence phase")
    projection = grok_phase.projection
    expected_selection = select_grok(projection)
    if canonical(dict(frozen_selection)) != canonical(expected_selection):
        raise ValueError("HANNA heldout verifier Sol phase requires the frozen Grok selection")
    executor, study, native, exec_v3, frozen, manifest, references, root_base = _context(collection_evidence_path=collection_evidence_path, collection_root=collection_root, r4_adoption_path=None, reconciliation_manifest_path=reconciliation_manifest_path, frozen_successor_path=frozen_successor_path, hanna_csv_path=hanna_csv_path)
    _finish_adoption(grok_phase.adoption, root_base, frozen, r3_grok_digests=grok_phase.r3_grok_digests, r4_grok_digests=grok_phase.r4_grok_digests)
    observations = _verify_endpoint(route_name="sol_validation", executor=executor, study=study, native=native, exec_v3=exec_v3, frozen=frozen, references=references, root_base=root_base)
    if projection.get("schedule_sha256") != frozen["schedule_sha256"] or projection.get("human_targets") != native._load_v3().v2_module()._human_targets(study=native._load_v3().v2_module().parent_modules()[0], frozen_successor_path=Path(frozen_successor_path), hanna_csv_path=Path(hanna_csv_path)):
        raise ValueError("HANNA heldout verifier Sol lineage drifted")
    return {"format_version": 1, "study_id": STUDY_ID, "kind": "heldout_independently_replayed_sol_observations", "grok_projection_sha256": projection["projection_sha256"], "frozen_selection_sha256": sha256(canonical(dict(frozen_selection))), "collection_evidence_sha256": sha256(stable_bytes(Path(collection_evidence_path))), "schedule_sha256": SCHEDULE_SHA256, "observations": observations, "human_targets": projection["human_targets"], "geometry": {"sol_cells": 22, "total_cells": 66}, "sol_evidence_class": "local_lifecycle_verified_native_endpoint_contact_cardinality_unproven", "confirmation": {"status": "unopened", "cells": 0}, "runtime_authority": "none"}
