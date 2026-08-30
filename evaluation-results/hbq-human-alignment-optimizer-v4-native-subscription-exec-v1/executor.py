#!/usr/bin/env python3
"""Pinned native subscription execution adapters for the HANNA v4 successor."""
from __future__ import annotations

import argparse
import hashlib
import importlib
import importlib.util
import json
import os
import re
import stat
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, Callable, Mapping


HERE = Path(__file__).resolve().parent
REPOSITORY = HERE.parents[1]
PREDECESSOR_DIR = HERE.parent / "hbq-human-alignment-optimizer-v4-native-subscription-v1"
PREDECESSOR_PATH = PREDECESSOR_DIR / "executor.py"
PREDECESSOR_CONTRACT_PATH = PREDECESSOR_DIR / "study-contract.json"
RUNNER_PATH = REPOSITORY / "src" / "hbqrs" / "runner.py"
BROKER_PATH = Path.home() / ".codex" / "tools" / "model_work_queue" / "broker.py"
CODEX_ADAPTER_PATH = Path.home() / ".codex" / "tools" / "model_work_queue" / "adapters" / "codex_exec.py"
STUDY_ID = "hbq-human-alignment-optimizer-v4-native-subscription-exec-v1"
PREDECESSOR_SHA256 = "6d93f69216d62bd0847aa6b338b6e2360587c82608669f78fbad245a34ba1c49"
PREDECESSOR_CONTRACT_SHA256 = "aac0c8952894a2501bd364fcf7fff392399633de8f310be1b97108061e78bbe9"
RUNNER_SHA256 = "de1dccd28c8ba544207b3b000d086948fa8c429a327b055762e8d7032e3fa938"
BROKER_SHA256 = "9f622edcdbf33bed47c737d1a4892a3fc7ab6350d960225316a6a59ecf957be5"
CODEX_ADAPTER_SHA256 = "89b906fe488c663d23cc1f5d0d8d3b5d0bf105fbdae96a848598bc2a1f6e3cee"
ROUTE_NAME = "grok-build-grok-4.6"
SOL_ROUTE_NAME = "codex-chatgpt-gpt-5.6-sol"
SYSTEM_PROMPT = "Act as an isolated structured-output evaluator. Do not use memory, tools, web, plans, or subagents."
TOOL_FREE_ARGV = [
    "--max-turns", "1", "--no-leader", "--no-subagents", "--disable-web-search", "--no-plan",
    "--tools", "", "--permission-mode", "dontAsk", "--sandbox", "read-only", "--verbatim",
]
PREPARED_FILES = frozenset({
    "predecessor-payload.json", "prompt-request.bin", "response-schema.json", "disclosure.json",
    "authorization-acknowledgement.json", "zero-charge-route-proof.json", "prepared.json",
})


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _stable_file_bytes(path: Path) -> bytes:
    absolute = Path(os.path.abspath(path))
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current /= part
        info = os.lstat(current)
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400):
            raise ValueError(f"HANNA native exec pinned path is reparsed: {current}")
    before = os.lstat(absolute)
    with absolute.open("rb") as handle:
        opened = os.fstat(handle.fileno())
        if (before.st_dev, before.st_ino, before.st_size) != (opened.st_dev, opened.st_ino, opened.st_size):
            raise ValueError(f"HANNA native exec pinned file identity drifted: {absolute}")
        raw = handle.read()
        after = os.fstat(handle.fileno())
        if (opened.st_dev, opened.st_ino, opened.st_size) != (after.st_dev, after.st_ino, after.st_size):
            raise ValueError(f"HANNA native exec pinned file changed during read: {absolute}")
    return raw


def _load_predecessor() -> ModuleType:
    raw = _stable_file_bytes(PREDECESSOR_PATH)
    contract_raw = _stable_file_bytes(PREDECESSOR_CONTRACT_PATH)
    if _sha(raw) != PREDECESSOR_SHA256 or _sha(contract_raw) != PREDECESSOR_CONTRACT_SHA256:
        raise ValueError("HANNA native exec predecessor bytes drifted")
    module = ModuleType("_hanna_v4_native_exec_parent")
    module.__file__ = str(PREDECESSOR_PATH)
    exec(compile(raw, str(PREDECESSOR_PATH), "exec"), module.__dict__)
    module.contract()
    return module


def _load_runner_function(name: str) -> Callable[..., tuple[str, dict[str, Any]]]:
    raw = _stable_file_bytes(RUNNER_PATH)
    if _sha(raw) != RUNNER_SHA256:
        raise ValueError("HANNA native exec pinned runner bytes drifted")
    source = str(REPOSITORY / "src")
    inserted = source not in sys.path
    if inserted:
        sys.path.insert(0, source)
    try:
        importlib.import_module("hbqrs")
        module = ModuleType("hbqrs._hanna_native_exec_pinned_runner")
        module.__file__ = str(RUNNER_PATH)
        module.__package__ = "hbqrs"
        exec(compile(raw, str(RUNNER_PATH), "exec"), module.__dict__)
    finally:
        if inserted:
            sys.path.remove(source)
    if _sha(_stable_file_bytes(RUNNER_PATH)) != RUNNER_SHA256:
        raise ValueError("HANNA native exec runner changed during exact-byte load")
    function = getattr(module, name, None)
    if not callable(function):
        raise ValueError("HANNA native exec pinned runner omitted its required call seam")
    return function


def _load_call_grok() -> Callable[..., tuple[str, dict[str, Any]]]:
    return _load_runner_function("_call_grok")


def _load_call_codex() -> Callable[..., tuple[str, dict[str, Any]]]:
    return _load_runner_function("_call_codex")


def _load_parse_codex_events() -> Callable[[bytes], dict[str, Any]]:
    raw = _stable_file_bytes(CODEX_ADAPTER_PATH)
    if _sha(raw) != CODEX_ADAPTER_SHA256:
        raise ValueError("HANNA native exec pinned Codex adapter bytes drifted")
    module = ModuleType("_hanna_pinned_codex_exec_adapter")
    module.__file__ = str(CODEX_ADAPTER_PATH)
    exec(compile(raw, str(CODEX_ADAPTER_PATH), "exec"), module.__dict__)
    if _sha(_stable_file_bytes(CODEX_ADAPTER_PATH)) != CODEX_ADAPTER_SHA256:
        raise ValueError("HANNA native exec Codex adapter changed during load")
    return module._parse_events


def _load_broker_class() -> type:
    raw = _stable_file_bytes(BROKER_PATH)
    if _sha(raw) != BROKER_SHA256:
        raise ValueError("HANNA native exec canonical Broker bytes drifted")
    tools_root = str(Path.home() / ".codex" / "tools")
    inserted = tools_root not in sys.path
    if inserted:
        sys.path.insert(0, tools_root)
    package_name = "_hanna_native_exec_pinned_model_work_queue"
    package = ModuleType(package_name)
    package.__path__ = [str(BROKER_PATH.parent)]
    package.__package__ = package_name
    module_name = f"{package_name}.broker"
    module = ModuleType(module_name)
    module.__file__ = str(BROKER_PATH)
    module.__package__ = package_name
    try:
        sys.modules[package_name] = package
        sys.modules[module_name] = module
        exec(compile(raw, str(BROKER_PATH), "exec"), module.__dict__)
    finally:
        for loaded_name in [name for name in sys.modules if name == package_name or name.startswith(f"{package_name}.")]:
            del sys.modules[loaded_name]
        if inserted:
            sys.path.remove(tools_root)
    if Path(module.__file__).resolve() != BROKER_PATH.resolve() or _sha(_stable_file_bytes(BROKER_PATH)) != BROKER_SHA256:
        raise ValueError("HANNA native exec loaded different or changed Broker bytes")
    broker = getattr(module, "Broker", None)
    if not isinstance(broker, type) or broker.__module__ != module_name:
        raise ValueError("HANNA native exec Broker class did not originate from pinned source bytes")
    return broker


def _route_evidence(route: Mapping[str, Any], registry: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "route_name": route["name"],
        "route_sha256": _sha(_canonical(route)),
        "registry_sha256": _sha(_canonical(registry)),
        "cost_evidence_hash": route["cost_evidence"]["evidence_hash"],
        "subscription_receipt_hash": route["subscription_receipt_hash"],
        "grok_command_identity_sha256": _sha(_canonical(route["grok_command_identity"])),
        "cli_version_identity_sha256": _sha(_canonical(route["cli_version_identity"])),
        "grok_cli_version": route["grok_cli_version"],
    }


def _sol_route_evidence(route: Mapping[str, Any], registry: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "route_name": route["name"], "route_sha256": _sha(_canonical(route)),
        "registry_sha256": _sha(_canonical(registry)),
        "cost_evidence_hash": route["cost_evidence"]["evidence_hash"],
        "auth_receipt_hash": route["auth_receipt_hash"],
        "cost_evidence_checked_at": route["cost_evidence"]["checked_at"],
        "cost_evidence_expires_at": route["cost_evidence"]["expires_at"],
        "wrapper_command_identity_sha256": _sha(_canonical(route["command_identity"])),
        "codex_command_identity_sha256": _sha(_canonical(route["codex_command_identity"])),
        "cli_version_identity_sha256": _sha(_canonical(route["cli_version_identity"])),
        "auth_status_identity_sha256": _sha(_canonical(route["auth_status_identity"])),
        "codex_cli_version": route["codex_cli_version"],
        "codex_adapter_sha256": CODEX_ADAPTER_SHA256,
    }


def validate_live_grok_route(queue_root: Path, *, broker_factory: Callable[[Path], Any] | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    broker = (broker_factory or _load_broker_class())(Path(queue_root))
    registry = broker._load_registry_live()
    routes = [route for route in registry.get("routes", []) if route.get("name") == ROUTE_NAME]
    if len(routes) != 1:
        raise ValueError("HANNA native exec requires exactly one Grok Build route")
    route = routes[0]
    broker._validate_route(route, verify_command_identity=True, validate_current_evidence=True)
    required = {
        "name": ROUTE_NAME, "model": "grok-4.6", "adapter": "grok_exec", "provider": "xai_grok_build",
        "destination": "xai_grok_build_subscription", "account_class": "subscription", "zero_charge": True,
        "armed": True, "health": "healthy", "reasoning_effort": "high", "reported_model": "grok-4.6-build",
        "identity_evidence": "requested_only",
    }
    if any(route.get(key) != value for key, value in required.items()):
        raise ValueError("HANNA native exec Grok route policy drifted")
    if "public_repo" not in route.get("allowed_payload_classes", []) or len(route.get("grok_command", [])) != 1:
        raise ValueError("HANNA native exec Grok route cannot carry the frozen public prompt")
    return dict(route), _route_evidence(route, registry)


def validate_live_sol_route(queue_root: Path, *, broker_factory: Callable[[Path], Any] | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    if _sha(_stable_file_bytes(CODEX_ADAPTER_PATH)) != CODEX_ADAPTER_SHA256:
        raise ValueError("HANNA native exec pinned Codex adapter bytes drifted")
    broker = (broker_factory or _load_broker_class())(Path(queue_root))
    registry = broker._load_registry_live()
    routes = [route for route in registry.get("routes", []) if route.get("name") == SOL_ROUTE_NAME]
    if len(routes) != 1:
        raise ValueError("HANNA native exec requires exactly one Codex ChatGPT Sol route")
    route = routes[0]
    broker._validate_route(route, verify_command_identity=True, validate_current_evidence=True)
    required = {
        "name": SOL_ROUTE_NAME, "model": "gpt-5.6-sol", "adapter": "codex_exec",
        "provider": "openai_codex", "destination": "openai_codex_chatgpt_subscription",
        "account_class": "subscription", "zero_charge": True, "armed": True, "health": "healthy",
        "reasoning_effort": "high", "identity_evidence": "requested_only", "trusted": True,
    }
    if any(route.get(key) != value for key, value in required.items()):
        raise ValueError("HANNA native exec Sol route policy drifted")
    command = route.get("command", [])
    if ("public_repo" not in route.get("allowed_payload_classes", [])
            or len(route.get("codex_command", [])) != 1
            or not re.fullmatch(r"[0-9a-f]{64}", str(route.get("auth_receipt_hash", "")))
            or len(command) != 2 or Path(command[1]).resolve() != CODEX_ADAPTER_PATH.resolve()):
        raise ValueError("HANNA native exec Sol route cannot carry the frozen public prompt")
    return dict(route), _sol_route_evidence(route, registry)


def _extract_predecessor_payload(*, predecessor: ModuleType, cell_id: str,
                                 frozen_successor_path: Path, hanna_csv_path: Path) -> tuple[dict[str, Any], bytes, bytes, bytes]:
    schedule = predecessor.derive_schedule(
        frozen_successor_path=Path(frozen_successor_path), hanna_csv_path=Path(hanna_csv_path)
    )
    row = predecessor._cell(schedule, cell_id)
    raw = predecessor._payload(
        predecessor._load_v3(), row,
        frozen_successor_path=Path(frozen_successor_path), hanna_csv_path=Path(hanna_csv_path),
    )
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("HANNA native exec predecessor payload is invalid") from error
    if not isinstance(payload, dict) or predecessor.canonical(payload) != raw or payload.get("study_id") != predecessor.STUDY_ID:
        raise ValueError("HANNA native exec predecessor payload identity drifted")
    components = payload.get("components")
    if not isinstance(components, dict):
        raise ValueError("HANNA native exec predecessor payload components are absent")
    task = components.get("task_payload")
    schema = components.get("response_schema")
    if not isinstance(task, str) or not isinstance(schema, str):
        raise ValueError("HANNA native exec predecessor prompt/schema bytes are absent")
    task_bytes, schema_bytes = task.encode("utf-8"), schema.encode("utf-8")
    if _sha(task_bytes) != row["task_payload_sha256"] or _sha(schema_bytes) != row["response_schema_sha256"]:
        raise ValueError("HANNA native exec exact predecessor prompt/schema binding drifted")
    return row, raw, task_bytes, schema_bytes


def _write_new(predecessor: ModuleType, path: Path, value: bytes) -> None:
    predecessor._write_new(path, value)


def prepare_only(*, output_root: Path, cell_id: str, queue_root: Path,
                 frozen_successor_path: Path, hanna_csv_path: Path,
                 authorization_acknowledgement_sha256: str,
                 broker_factory: Callable[[Path], Any] | None = None) -> dict[str, Any]:
    if not re.fullmatch(r"[0-9a-f]{64}", authorization_acknowledgement_sha256):
        raise ValueError("HANNA native exec authorization acknowledgement must be lowercase SHA-256")
    predecessor = _load_predecessor()
    row, predecessor_payload, task, schema = _extract_predecessor_payload(
        predecessor=predecessor, cell_id=cell_id,
        frozen_successor_path=Path(frozen_successor_path), hanna_csv_path=Path(hanna_csv_path),
    )
    root = Path(output_root) / cell_id
    disclosure = {
        "format_version": 1, "study_id": STUDY_ID, "kind": "local_first_exact_outbound_disclosure",
        "cell_id": cell_id, "route_identity": row["route"], "destination": row["route"]["destination"],
        "task_payload": {"bytes": len(task), "sha256": _sha(task), "text": task.decode("utf-8")},
        "response_schema": {"bytes": len(schema), "sha256": _sha(schema), "text": schema.decode("utf-8")},
        "system_prompt_override": SYSTEM_PROMPT if row["route_name"] == "grok_primary" else None,
        "tool_free_argv": TOOL_FREE_ARGV if row["route_name"] == "grok_primary" else None,
        "tools_enabled": False, "web_search_enabled": False, "subagents_enabled": False,
        "provider_calls_made": 0, "process_launches": 0,
    }
    authorization = {
        "format_version": 1, "study_id": STUDY_ID, "kind": "caller_authorization_acknowledgement_reference",
        "cell_id": cell_id, "acknowledgement_sha256": authorization_acknowledgement_sha256,
        "disclosure_sha256": _sha(_canonical(disclosure)), "route_identity": row["route"],
        "destination": row["route"]["destination"],
    }
    if row["route_name"] == "sol_validation":
        route, evidence = validate_live_sol_route(Path(queue_root), broker_factory=broker_factory)
        route_status = "SOL_PREPARED_NO_CONTACT"
    elif row["route_name"] == "grok_primary":
        route, evidence = validate_live_grok_route(Path(queue_root), broker_factory=broker_factory)
        route_status = "GROK_PREPARED_NO_CONTACT"
    else:
        raise ValueError("HANNA native exec route is unsupported")
    proof = {
        "format_version": 1, "study_id": STUDY_ID, "kind": "route_proof", "cell_id": cell_id,
        "status": "CURRENT_BROKER_VALIDATED_ZERO_CHARGE_SUBSCRIPTION_ROUTE",
        "route_identity": row["route"], "destination": row["route"]["destination"],
        "route_evidence": evidence, "zero_charge_only": True, "paid_fallback_forbidden": True,
        "provider_calls_made": 0, "process_launches": 0,
    }
    prepared = {
        "format_version": 1, "study_id": STUDY_ID, "kind": "native_exec_preparation",
        "cell_id": cell_id, "route_status": route_status,
        "route_identity": row["route"], "destination": row["route"]["destination"],
        "fresh_row_sha256": _sha(_canonical(row)),
        "provider_calls_made": 0, "process_launches": 0,
        "predecessor_executor_sha256": PREDECESSOR_SHA256,
        "predecessor_contract_sha256": PREDECESSOR_CONTRACT_SHA256,
        "pinned_runner_sha256": RUNNER_SHA256,
        "predecessor_payload_sha256": _sha(predecessor_payload),
        "request_sha256": _sha(task), "response_schema_sha256": _sha(schema),
        "route_evidence": evidence,
        "disclosure_sha256": _sha(_canonical(disclosure)),
        "authorization_sha256": _sha(_canonical(authorization)), "route_proof_sha256": _sha(_canonical(proof)),
        "executable": route[("grok_command" if row["route_name"] == "grok_primary" else "codex_command")][0],
        "requested": {"model": route["model"], "reasoning_effort": route["reasoning_effort"]},
        "tool_free_argv": TOOL_FREE_ARGV if row["route_name"] == "grok_primary" else None,
        "system_prompt_override": SYSTEM_PROMPT if row["route_name"] == "grok_primary" else None,
        "capture_jsonl_events": row["route_name"] == "sol_validation",
        "pinned_codex_adapter_sha256": CODEX_ADAPTER_SHA256 if row["route_name"] == "sol_validation" else None,
    }
    root.mkdir(parents=True, exist_ok=False)
    _write_new(predecessor, root / "predecessor-payload.json", predecessor_payload)
    _write_new(predecessor, root / "prompt-request.bin", task)
    _write_new(predecessor, root / "response-schema.json", schema)
    _write_new(predecessor, root / "disclosure.json", _canonical(disclosure))
    _write_new(predecessor, root / "authorization-acknowledgement.json", _canonical(authorization))
    _write_new(predecessor, root / "zero-charge-route-proof.json", _canonical(proof))
    _write_new(predecessor, root / "prepared.json", _canonical(prepared))
    return prepared


def _read_prepared(predecessor: ModuleType, root: Path, *, cell_id: str,
                   frozen_successor_path: Path, hanna_csv_path: Path,
                   expected_authorization_sha256: str | None = None,
                   require_pristine: bool = True) -> tuple[dict[str, Any], bytes, bytes, bytes, dict[str, Any]]:
    if root.name != cell_id:
        raise ValueError("HANNA native exec prepared root/cell identity drifted")
    fresh_row, fresh_payload, fresh_task, fresh_schema = _extract_predecessor_payload(
        predecessor=predecessor, cell_id=cell_id,
        frozen_successor_path=Path(frozen_successor_path), hanna_csv_path=Path(hanna_csv_path),
    )
    children = frozenset(child.name for child in root.iterdir())
    invalid = any(child.is_symlink() for child in root.iterdir())
    if require_pristine:
        invalid = invalid or children != PREPARED_FILES or any(not child.is_file() for child in root.iterdir())
    else:
        invalid = invalid or not PREPARED_FILES <= children
    if invalid:
        raise ValueError("HANNA native exec prepared-root inventory drifted or contains orphan artifacts")
    prepared = predecessor._read_canonical(root / "prepared.json", label="native exec prepared manifest")
    predecessor_payload = predecessor._stable_read_bytes(root / "predecessor-payload.json")
    task = predecessor._stable_read_bytes(root / "prompt-request.bin")
    schema = predecessor._stable_read_bytes(root / "response-schema.json")
    disclosure = predecessor._read_canonical(root / "disclosure.json", label="native exec disclosure")
    authorization = predecessor._read_canonical(root / "authorization-acknowledgement.json", label="native exec authorization")
    proof = predecessor._read_canonical(root / "zero-charge-route-proof.json", label="native exec route proof")
    if (predecessor_payload != fresh_payload or task != fresh_task or schema != fresh_schema
            or prepared.get("study_id") != STUDY_ID or prepared.get("predecessor_executor_sha256") != PREDECESSOR_SHA256
            or prepared.get("predecessor_contract_sha256") != PREDECESSOR_CONTRACT_SHA256
            or prepared.get("pinned_runner_sha256") != RUNNER_SHA256
            or prepared.get("predecessor_payload_sha256") != _sha(predecessor_payload)
            or prepared.get("request_sha256") != _sha(task) or prepared.get("response_schema_sha256") != _sha(schema)
            or prepared.get("disclosure_sha256") != _sha(_canonical(disclosure))
            or prepared.get("authorization_sha256") != _sha(_canonical(authorization))
            or prepared.get("route_proof_sha256") != _sha(_canonical(proof))):
        raise ValueError("HANNA native exec prepared bytes drifted")
    semantic_records = (
        (prepared, "native_exec_preparation"),
        (disclosure, "local_first_exact_outbound_disclosure"),
        (authorization, "caller_authorization_acknowledgement_reference"),
        (proof, "route_proof"),
    )
    if any(
        record.get("format_version") != 1 or record.get("study_id") != STUDY_ID
        or record.get("kind") != kind or record.get("cell_id") != cell_id
        or record.get("route_identity") != fresh_row["route"]
        or record.get("destination") != fresh_row["route"]["destination"]
        for record, kind in semantic_records
    ):
        raise ValueError("HANNA native exec prepared artifact identity was copied or relabelled")
    if (prepared.get("fresh_row_sha256") != _sha(_canonical(fresh_row))
            or disclosure.get("route_identity") != fresh_row["route"]
            or authorization.get("route_identity") != fresh_row["route"]
            or proof.get("route_identity") != fresh_row["route"]
            or authorization.get("acknowledgement_sha256") is None
            or not re.fullmatch(r"[0-9a-f]{64}", str(authorization["acknowledgement_sha256"]))
            or (expected_authorization_sha256 is not None
                and authorization.get("acknowledgement_sha256") != expected_authorization_sha256)
            or authorization.get("disclosure_sha256") != _sha(_canonical(disclosure))
            or disclosure.get("provider_calls_made") != 0 or disclosure.get("process_launches") != 0
            or proof.get("provider_calls_made") != 0 or proof.get("process_launches") != 0):
        raise ValueError("HANNA native exec disclosure/authorization/route proof drifted")
    try:
        payload_components = json.loads(predecessor_payload.decode("utf-8"))["components"]
    except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError) as error:
        raise ValueError("HANNA native exec predecessor payload components drifted") from error
    if (payload_components.get("task_payload", "").encode("utf-8") != task
            or payload_components.get("response_schema", "").encode("utf-8") != schema
            or disclosure.get("task_payload") != {"bytes": len(task), "sha256": _sha(task), "text": task.decode("utf-8")}
            or disclosure.get("response_schema") != {"bytes": len(schema), "sha256": _sha(schema), "text": schema.decode("utf-8")}
            or any(disclosure.get(key) is not False for key in ("tools_enabled", "web_search_enabled", "subagents_enabled"))
            or proof.get("status") != "CURRENT_BROKER_VALIDATED_ZERO_CHARGE_SUBSCRIPTION_ROUTE"
            or proof.get("zero_charge_only") is not True or proof.get("paid_fallback_forbidden") is not True
            or proof.get("route_evidence") != prepared.get("route_evidence")):
        raise ValueError("HANNA native exec exact disclosure/route semantics drifted")
    if prepared.get("route_status") == "SOL_PREPARED_NO_CONTACT":
        if (fresh_row["route_name"] != "sol_validation"
                or disclosure.get("system_prompt_override") is not None or disclosure.get("tool_free_argv") is not None
                or prepared.get("capture_jsonl_events") is not True
                or prepared.get("pinned_codex_adapter_sha256") != CODEX_ADAPTER_SHA256
                or prepared.get("requested") != {"model": "gpt-5.6-sol", "reasoning_effort": "high"}
                or prepared.get("tool_free_argv") is not None or prepared.get("system_prompt_override") is not None):
            raise ValueError("HANNA native exec prepared Sol contract drifted")
    elif prepared.get("route_status") == "GROK_PREPARED_NO_CONTACT":
        if (fresh_row["route_name"] != "grok_primary"
                or disclosure.get("system_prompt_override") != SYSTEM_PROMPT
                or disclosure.get("tool_free_argv") != TOOL_FREE_ARGV
                or prepared.get("capture_jsonl_events") is not False
                or prepared.get("pinned_codex_adapter_sha256") is not None
                or prepared.get("requested") != {"model": "grok-4.6", "reasoning_effort": "high"}
                or prepared.get("tool_free_argv") != TOOL_FREE_ARGV
                or prepared.get("system_prompt_override") != SYSTEM_PROMPT):
            raise ValueError("HANNA native exec prepared Grok contract drifted")
    else:
        raise ValueError("HANNA native exec prepared route status is unsupported")
    return prepared, predecessor_payload, task, schema, fresh_row


def _envelope_identity(raw: bytes, record: Mapping[str, Any]) -> tuple[str, str]:
    try:
        envelope = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("HANNA native exec Grok envelope is invalid") from error
    usage = envelope.get("modelUsage") if isinstance(envelope, dict) else None
    request_id = envelope.get("requestId") if isinstance(envelope, dict) else None
    session_id = envelope.get("sessionId") if isinstance(envelope, dict) else None
    if (not isinstance(usage, dict) or list(usage) != ["grok-4.6-build"]
            or not isinstance(request_id, str) or not request_id
            or not isinstance(session_id, str) or not session_id
            or record.get("request_id_sha256") != _sha(request_id.encode("utf-8"))
            or record.get("session_id_sha256") != _sha(session_id.encode("utf-8"))):
        raise ValueError("HANNA native exec Grok envelope identity is misassociated")
    return request_id, session_id


def _persist_reconcile(predecessor: ModuleType, root: Path, cell_id: str, error: BaseException) -> dict[str, Any]:
    result = {
        "format_version": 1, "study_id": STUDY_ID, "kind": "native_exec_result",
        "cell_id": cell_id, "state": "reconcile_required_after_process_launch",
        "process_launches": 1, "native_contact_proven": False, "error_type": type(error).__name__,
    }
    _write_new(predecessor, root / "result.json", _canonical(result))
    return result


def _plain_entry(path: Path, *, directory: bool) -> bool:
    info = os.lstat(path)
    reparsed = stat.S_ISLNK(info.st_mode) or bool(
        getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    )
    return not reparsed and (stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode))


def _cleanup_known_precontact(predecessor: ModuleType, root: Path, *, route_name: str, task: bytes) -> None:
    responses = root / "responses"
    try:
        os.lstat(responses)
    except FileNotFoundError:
        return
    if not _plain_entry(responses, directory=True):
        raise ValueError("HANNA native exec precontact responses path is unsafe")
    expected = (
        {"batch-0001.attempt-0001.prompt.txt": task}
        if route_name == "grok_primary"
        else {"batch-0001.attempt-0001.events.jsonl": b""}
    )
    children = {child.name: child for child in responses.iterdir()}
    if set(children) - set(expected):
        raise ValueError("HANNA native exec unknown precontact artifacts require manual reconciliation")
    for name, child in children.items():
        if not _plain_entry(child, directory=False) or predecessor._stable_read_bytes(child) != expected[name]:
            raise ValueError("HANNA native exec precontact artifact bytes are not safely retryable")
        child.unlink()
    responses.rmdir()


def _validate_completed_inventory(root: Path, *, is_sol: bool) -> None:
    route_files = (
        {"raw-codex-events.bin", "raw-codex-final-response.bin", "codex-record.json"}
        if is_sol else {"raw-grok-envelope.bin", "grok-record.json"}
    )
    expected_root = set(PREPARED_FILES) | route_files | {
        "launch-intent.json", "effective-settings.json", "execution-receipt.json", "responses",
    }
    children = {child.name: child for child in root.iterdir()}
    if set(children) != expected_root:
        raise ValueError("HANNA native exec completed-root inventory contains missing or extra artifacts")
    for name, child in children.items():
        if not _plain_entry(child, directory=name == "responses"):
            raise ValueError("HANNA native exec completed-root inventory contains unsafe entries")
    expected_responses = (
        {"batch-0001.attempt-0001.events.jsonl", "batch-0001.attempt-0001.message.json"}
        if is_sol else {"batch-0001.attempt-0001.prompt.txt", "batch-0001.attempt-0001.grok.envelope.json"}
    )
    responses = children["responses"]
    response_children = {child.name: child for child in responses.iterdir()}
    if set(response_children) != expected_responses or any(
        not _plain_entry(child, directory=False) for child in response_children.values()
    ):
        raise ValueError("HANNA native exec completed response inventory contains missing, extra, or unsafe artifacts")


def _launch_intent_sha256(predecessor: ModuleType, root: Path, *, cell_id: str,
                          prepared_sha256: str) -> str:
    intent = predecessor._read_canonical(root / "launch-intent.json", label="native exec launch intent")
    expected = {
        "format_version": 1, "study_id": STUDY_ID, "kind": "process_launch_intent_not_native_contact",
        "cell_id": cell_id, "prepared_sha256": prepared_sha256, "native_contact_proven": False,
    }
    if intent != expected:
        raise ValueError("HANNA native exec launch-intent provenance drifted")
    return _sha(_canonical(intent))


def _finalize_grok(*, predecessor: ModuleType, root: Path, cell_id: str, task: bytes, schema: bytes,
                   route: Mapping[str, Any], evidence: Mapping[str, Any], launches: int,
                   record: Mapping[str, Any], prepared_sha256: str) -> dict[str, Any]:
    if launches != 1 or not isinstance(record, Mapping):
        raise ValueError("HANNA native exec runner did not bind exactly one process launch")
    artifact = record.get("provider_artifacts", {}).get("grok_envelope")
    if not isinstance(artifact, Mapping) or set(artifact) != {"path", "bytes", "sha256"}:
        raise ValueError("HANNA native exec runner omitted the pinned Grok envelope artifact")
    artifact_path = root / str(artifact["path"])
    try:
        artifact_path.resolve().relative_to(root.resolve())
    except ValueError as error:
        raise ValueError("HANNA native exec envelope artifact escapes its root") from error
    raw_envelope = predecessor._stable_read_bytes(artifact_path)
    if artifact["bytes"] != len(raw_envelope) or artifact["sha256"] != _sha(raw_envelope):
        raise ValueError("HANNA native exec Grok envelope artifact binding drifted")
    request_id, session_id = _envelope_identity(raw_envelope, record)
    if (record.get("cli_version") != route["grok_cli_version"]
            or record.get("requested") != {"model": "grok-4.6", "reasoning_effort": "high"}
            or record.get("reported") != {"provider": "grok", "model": "grok-4.6-build"}
            or record.get("reasoning_attested") is not False):
        raise ValueError("HANNA native exec Grok effective settings drifted")
    if predecessor._stable_read_bytes(root / "responses" / "batch-0001.attempt-0001.prompt.txt") != task:
        raise ValueError("HANNA native exec runner prompt bytes drifted")
    effective = {
        "requested_model": "grok-4.6", "reported_model": "grok-4.6-build",
        "requested_reasoning_effort": "high", "reasoning_attested": False,
        "grok_cli_version": route["grok_cli_version"], "grok_command_identity": route["grok_command_identity"],
        "tool_free_argv": TOOL_FREE_ARGV, "system_prompt_override": SYSTEM_PROMPT,
    }
    identity = {
        "provider": "xai_grok_build", "route_name": ROUTE_NAME, "requested_model": "grok-4.6",
        "requested_reasoning_effort": "high", "effective_model": "grok-4.6-build",
        "provider_reported_model": "grok-4.6-build",
        "identity_evidence": "requested_and_cli_envelope_reported_model_reasoning_unattested",
        "reasoning_attested": False, "transport_identity": "grok_build_saved_session_subscription_tool_free_v1",
        "contact_id": request_id, "session_id": session_id,
    }
    launch_intent_sha256 = _launch_intent_sha256(
        predecessor, root, cell_id=cell_id, prepared_sha256=prepared_sha256,
    )
    receipt = {
        "format_version": 1, "study_id": STUDY_ID, "kind": "grok_native_envelope_receipt",
        "cell_id": cell_id, "native_contact_proven": True, "process_launches": 1,
        "request_sha256": _sha(task), "response_schema_sha256": _sha(schema),
        "raw_envelope_sha256": _sha(raw_envelope), "route_evidence": evidence,
        "effective_settings_sha256": _sha(_canonical(effective)),
        "launch_intent_sha256": launch_intent_sha256, "identity": identity,
    }
    _write_new(predecessor, root / "raw-grok-envelope.bin", raw_envelope)
    _write_new(predecessor, root / "grok-record.json", _canonical(dict(record)))
    _write_new(predecessor, root / "effective-settings.json", _canonical(effective))
    _write_new(predecessor, root / "execution-receipt.json", _canonical(receipt))
    return {"cell_id": cell_id, "state": "native_envelope_received", "process_launches": 1,
            "native_contact_proven": True, "request_bytes": task, "raw_envelope_bytes": raw_envelope,
             "effective_settings": effective, "identity": identity}


_CODEX_DISABLED = [
    "shell_tool", "unified_exec", "code_mode_host", "hooks", "auth_elicitation", "memories",
    "plugins", "multi_agent", "apps", "browser_use", "browser_use_external", "computer_use",
    "image_generation", "view_image", "workspace_dependencies", "skill_search", "tool_suggest",
    "tool_call_mcp_elicitation",
]


def _expected_codex_command(executable: str, root: Path) -> list[str]:
    disabled = [part for name in _CODEX_DISABLED for part in ("--disable", name)]
    return [
        executable, "exec", "--json", "--ephemeral", "--ignore-user-config", "--ignore-rules",
        "--strict-config", *disabled, "-c", 'web_search="disabled"', "-c", "mcp_servers={}",
        "--disable", "unbounded_connection_retries", "-c", 'approval_policy="never"',
        "--skip-git-repo-check", "--sandbox", "read-only", "--color", "never", "--model",
        "gpt-5.6-sol", "-c", 'model_reasoning_effort="high"', "--output-schema",
        str(root / "response-schema.json"), "--output-last-message",
        str(root / "responses" / "batch-0001.attempt-0001.message.json"), "--cd", str(root),
        "<prompt-via-stdin>",
    ]


def _artifact_bytes(predecessor: ModuleType, root: Path, artifact: Any, label: str) -> bytes:
    if not isinstance(artifact, Mapping) or set(artifact) != {"path", "bytes", "sha256"}:
        raise ValueError(f"HANNA native exec runner omitted the pinned {label} artifact")
    path = root / str(artifact["path"])
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError as error:
        raise ValueError(f"HANNA native exec {label} artifact escapes its root") from error
    raw = predecessor._stable_read_bytes(path)
    if artifact["bytes"] != len(raw) or artifact["sha256"] != _sha(raw):
        raise ValueError(f"HANNA native exec {label} artifact binding drifted")
    return raw


def _codex_event_projection(raw: bytes, parse_events: Callable[[bytes], dict[str, Any]]) -> dict[str, Any]:
    projection = parse_events(raw)
    completed_messages: list[str] = []
    for line in raw.splitlines():
        if not line.strip():
            continue
        event = json.loads(line.decode("utf-8"))
        item = event.get("item") if isinstance(event, dict) and event.get("type") == "item.completed" else None
        if isinstance(item, dict) and item.get("type") == "agent_message":
            completed_messages.append(item["text"])
    if len(completed_messages) != 1:
        raise ValueError("HANNA native exec Codex JSONL must complete exactly one agent message")
    return {**projection, "completed_agent_message_text": completed_messages[0]}


def _finalize_sol(*, predecessor: ModuleType, root: Path, cell_id: str, task: bytes, schema: bytes,
                  route: Mapping[str, Any], evidence: Mapping[str, Any], launches: int,
                  content: str, record: Mapping[str, Any], parse_events: Callable[[bytes], dict[str, Any]],
                  prepared_sha256: str) -> dict[str, Any]:
    if launches != 1 or not isinstance(content, str) or not isinstance(record, Mapping):
        raise ValueError("HANNA native exec Codex runner did not bind exactly one process launch")
    events = _artifact_bytes(
        predecessor, root, record.get("provider_artifacts", {}).get("codex_events"), "Codex JSONL events"
    )
    projection = _codex_event_projection(events, parse_events)
    thread_id = projection.get("thread_id")
    usage = projection.get("usage")
    if not isinstance(thread_id, str) or not thread_id or not isinstance(usage, dict):
        raise ValueError("HANNA native exec Codex event projection is incomplete")
    final_response = predecessor._stable_read_bytes(root / "responses" / "batch-0001.attempt-0001.message.json")
    if content.encode("utf-8") != final_response:
        raise ValueError("HANNA native exec Codex returned final response bytes drifted")
    if projection["completed_agent_message_text"].encode("utf-8") != final_response:
        raise ValueError("HANNA native exec Codex completed agent message/final response bytes drifted")
    try:
        final_value = json.loads(final_response.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("HANNA native exec Codex final response is not strict JSON") from error
    if not isinstance(final_value, dict):
        raise ValueError("HANNA native exec Codex final response must be one JSON object")
    reported = record.get("reported")
    if not isinstance(reported, Mapping) or any(
        reported.get(key) != value for key, value in {
            "model": "gpt-5.6-sol", "provider": "openai", "reasoning_effort": "high",
        }.items()
    ):
        raise ValueError("HANNA native exec Codex local effective settings drifted")
    reported_session = reported.get("session_id")
    if reported_session is not None and reported_session != thread_id:
        raise ValueError("HANNA native exec Codex thread/session identity is misassociated")
    if list(record.get("command", [])) != _expected_codex_command(route["codex_command"][0], root):
        raise ValueError("HANNA native exec Codex tool-disabled command drifted")
    effective = {
        "requested_model": "gpt-5.6-sol", "local_effective_model": reported["model"],
        "requested_reasoning_effort": "high", "local_effective_reasoning_effort": reported["reasoning_effort"],
        "provider_attested": False, "codex_cli_version": route["codex_cli_version"],
        "codex_command_identity": route["codex_command_identity"],
        "codex_adapter_sha256": CODEX_ADAPTER_SHA256, "capture_jsonl_events": True,
        "tools_enabled": False, "web_search_enabled": False, "subagents_enabled": False,
        "event_projection": projection,
    }
    identity = {
        "provider": "openai_codex", "route_name": SOL_ROUTE_NAME, "requested_model": "gpt-5.6-sol",
        "requested_reasoning_effort": "high", "effective_model": "gpt-5.6-sol",
        "provider_reported_model": None,
        "identity_evidence": "requested_and_local_effective_settings_only_not_provider_attested",
        "reasoning_attested": False, "transport_identity": "codex_chatgpt_subscription_exec_tool_free_v1",
        "contact_id": f"unproven-native-endpoint-contact-for-local-thread:{thread_id}",
        "session_id": f"local-codex-thread-session:{reported_session or thread_id}",
    }
    launch_intent_sha256 = _launch_intent_sha256(
        predecessor, root, cell_id=cell_id, prepared_sha256=prepared_sha256,
    )
    receipt = {
        "format_version": 1, "study_id": STUDY_ID, "kind": "codex_local_lifecycle_receipt",
        "cell_id": cell_id, "native_contact_proven": False, "process_launches": 1,
        "local_codex_thread_lifecycle_proven": True,
        "native_endpoint_contact_cardinality": "unproven",
        "internal_retry_cardinality": "unproven",
        "request_sha256": _sha(task), "response_schema_sha256": _sha(schema),
        "raw_events_sha256": _sha(events), "final_response_sha256": _sha(final_response),
        "route_evidence": evidence, "effective_settings_sha256": _sha(_canonical(effective)),
        "launch_intent_sha256": launch_intent_sha256, "identity": identity, "usage": usage,
    }
    _write_new(predecessor, root / "raw-codex-events.bin", events)
    _write_new(predecessor, root / "raw-codex-final-response.bin", final_response)
    _write_new(predecessor, root / "codex-record.json", _canonical(dict(record)))
    _write_new(predecessor, root / "effective-settings.json", _canonical(effective))
    _write_new(predecessor, root / "execution-receipt.json", _canonical(receipt))
    return {"cell_id": cell_id, "state": "local_codex_lifecycle_received_native_contact_unproven", "process_launches": 1,
            "native_contact_proven": False, "native_endpoint_contact_cardinality": "unproven",
            "request_bytes": task, "raw_response_bytes": final_response,
            "raw_events_bytes": events, "effective_settings": effective, "identity": identity}


def execute_grok(*, output_root: Path, cell_id: str, queue_root: Path,
                 frozen_successor_path: Path, hanna_csv_path: Path,
                 authorization_acknowledgement_sha256: str, allow_remote: bool,
                 broker_factory: Callable[[Path], Any] | None = None,
                 call_grok: Callable[..., tuple[str, dict[str, Any]]] | None = None) -> dict[str, Any]:
    if allow_remote is not True:
        raise ValueError("HANNA native exec requires explicit allow_remote=True for one Grok cell")
    predecessor = _load_predecessor()
    root = Path(output_root) / cell_id
    if any((root / name).exists() for name in ("launch-intent.json", "execution-receipt.json", "result.json")):
        raise ValueError("HANNA native exec refuses to resend or overwrite prior launch state")
    prepared, _parent_payload, task, schema, _fresh_row = _read_prepared(
        predecessor, root, cell_id=cell_id, frozen_successor_path=Path(frozen_successor_path),
        hanna_csv_path=Path(hanna_csv_path), expected_authorization_sha256=authorization_acknowledgement_sha256,
    )
    if prepared.get("route_status") != "GROK_PREPARED_NO_CONTACT":
        raise ValueError("HANNA native exec cell is not a prepared Grok primary cell")
    route, evidence = validate_live_grok_route(Path(queue_root), broker_factory=broker_factory)
    if evidence != prepared.get("route_evidence"):
        raise ValueError("HANNA native exec live Grok route evidence became stale")
    launches = 0
    intent = {
        "format_version": 1, "study_id": STUDY_ID, "kind": "process_launch_intent_not_native_contact",
        "cell_id": cell_id, "prepared_sha256": _sha(_canonical(prepared)), "native_contact_proven": False,
    }

    def before_provider_attempt() -> None:
        nonlocal launches
        if launches:
            raise ValueError("HANNA native exec provider launch callback repeated")
        fresh_route, fresh_evidence = validate_live_grok_route(Path(queue_root), broker_factory=broker_factory)
        if fresh_route != route or fresh_evidence != evidence or fresh_evidence != prepared.get("route_evidence"):
            raise ValueError("HANNA native exec Grok route drifted adjacent to process launch")
        _write_new(predecessor, root / "launch-intent.json", _canonical(intent))
        launches += 1

    invoke = call_grok or _load_call_grok()
    try:
        _content, record = invoke(
            executable=route["grok_command"][0], model="grok-4.6", reasoning="high",
            prompt=task.decode("utf-8"), output_dir=root, response_schema=root / "response-schema.json",
            batch_number=1, timeout=float(route["timeout_seconds"]), attempt_number=1,
            allow_unattested_reasoning=True, system_prompt_override=SYSTEM_PROMPT,
            before_provider_attempt=before_provider_attempt,
        )
    except BaseException as error:
        if launches == 0:
            _cleanup_known_precontact(predecessor, root, route_name="grok_primary", task=task)
            return {"cell_id": cell_id, "state": "pending_precontact", "process_launches": 0, "native_contact_proven": False}
        result = {
            "format_version": 1, "study_id": STUDY_ID, "kind": "native_exec_result",
            "cell_id": cell_id, "state": "reconcile_required_after_process_launch",
            "process_launches": 1, "native_contact_proven": False, "error_type": type(error).__name__,
        }
        _write_new(predecessor, root / "result.json", _canonical(result))
        return result
    try:
        return _finalize_grok(
            predecessor=predecessor, root=root, cell_id=cell_id, task=task, schema=schema,
            route=route, evidence=evidence, launches=launches, record=record,
            prepared_sha256=_sha(_canonical(prepared)),
        )
    except BaseException as error:
        return _persist_reconcile(predecessor, root, cell_id, error)


def execute_sol(*, output_root: Path, cell_id: str, queue_root: Path,
                frozen_successor_path: Path, hanna_csv_path: Path,
                authorization_acknowledgement_sha256: str, allow_remote: bool,
                broker_factory: Callable[[Path], Any] | None = None,
                call_codex: Callable[..., tuple[str, dict[str, Any]]] | None = None,
                parse_events: Callable[[bytes], dict[str, Any]] | None = None) -> dict[str, Any]:
    if allow_remote is not True:
        raise ValueError("HANNA native exec requires explicit allow_remote=True for one Sol cell")
    predecessor = _load_predecessor()
    root = Path(output_root) / cell_id
    if any((root / name).exists() for name in ("launch-intent.json", "execution-receipt.json", "result.json")):
        raise ValueError("HANNA native exec refuses to resend or overwrite prior launch state")
    prepared, _parent_payload, task, schema, _fresh_row = _read_prepared(
        predecessor, root, cell_id=cell_id, frozen_successor_path=Path(frozen_successor_path),
        hanna_csv_path=Path(hanna_csv_path), expected_authorization_sha256=authorization_acknowledgement_sha256,
    )
    if prepared.get("route_status") != "SOL_PREPARED_NO_CONTACT":
        raise ValueError("HANNA native exec cell is not a prepared Sol validation cell")
    route, evidence = validate_live_sol_route(Path(queue_root), broker_factory=broker_factory)
    if evidence != prepared.get("route_evidence"):
        raise ValueError("HANNA native exec live Sol route evidence became stale")
    launches = 0
    intent = {
        "format_version": 1, "study_id": STUDY_ID, "kind": "process_launch_intent_not_native_contact",
        "cell_id": cell_id, "prepared_sha256": _sha(_canonical(prepared)), "native_contact_proven": False,
    }

    def before_provider_attempt() -> None:
        nonlocal launches
        if launches:
            raise ValueError("HANNA native exec provider launch callback repeated")
        fresh_route, fresh_evidence = validate_live_sol_route(Path(queue_root), broker_factory=broker_factory)
        if fresh_route != route or fresh_evidence != evidence or fresh_evidence != prepared.get("route_evidence"):
            raise ValueError("HANNA native exec Sol route drifted adjacent to process launch")
        _write_new(predecessor, root / "launch-intent.json", _canonical(intent))
        launches += 1

    invoke = call_codex or _load_call_codex()
    strict_parser = parse_events or _load_parse_codex_events()
    try:
        content, record = invoke(
            executable=route["codex_command"][0], model="gpt-5.6-sol", reasoning="high",
            prompt=task.decode("utf-8"), output_dir=root, response_schema=root / "response-schema.json",
            batch_number=1, timeout=float(route["timeout_seconds"]), attempt_number=1,
            before_provider_attempt=before_provider_attempt, capture_jsonl_events=True,
        )
    except BaseException as error:
        if launches == 0:
            _cleanup_known_precontact(predecessor, root, route_name="sol_validation", task=task)
            return {"cell_id": cell_id, "state": "pending_precontact", "process_launches": 0, "native_contact_proven": False}
        return _persist_reconcile(predecessor, root, cell_id, error)
    try:
        return _finalize_sol(
            predecessor=predecessor, root=root, cell_id=cell_id, task=task, schema=schema,
            route=route, evidence=evidence, launches=launches, content=content, record=record,
            parse_events=strict_parser, prepared_sha256=_sha(_canonical(prepared)),
        )
    except BaseException as error:
        return _persist_reconcile(predecessor, root, cell_id, error)


def verify_predecessor_receipt(event: Mapping[str, Any], *, execution_root: Path, queue_root: Path,
                               frozen_successor_path: Path, hanna_csv_path: Path,
                               broker_factory: Callable[[Path], Any] | None = None) -> dict[str, Any]:
    """Independent predecessor verifier; it attests bytes/contact IDs, never reasoning."""
    predecessor = _load_predecessor()
    cell = event.get("cell")
    identity = event.get("identity")
    if (not isinstance(cell, Mapping) or cell.get("route_name") not in {"grok_primary", "sol_validation"}
            or not isinstance(identity, Mapping)):
        raise ValueError("HANNA native exec receipt verifier requires one supported predecessor cell")
    root = Path(execution_root) / str(cell["cell_id"])
    prepared, predecessor_payload, task, schema, fresh_row = _read_prepared(
        predecessor, root, cell_id=str(cell["cell_id"]), frozen_successor_path=Path(frozen_successor_path),
        hanna_csv_path=Path(hanna_csv_path), require_pristine=False,
    )
    if dict(cell) != fresh_row:
        raise ValueError("HANNA native exec caller cell row was copied or relabelled")
    is_sol = cell["route_name"] == "sol_validation"
    _validate_completed_inventory(root, is_sol=is_sol)
    expected_status = "SOL_PREPARED_NO_CONTACT" if is_sol else "GROK_PREPARED_NO_CONTACT"
    if prepared.get("route_status") != expected_status:
        raise ValueError("HANNA native exec receipt route preparation drifted")
    label = "Codex" if is_sol else "Grok"
    receipt = predecessor._read_canonical(root / "execution-receipt.json", label=f"{label} execution receipt")
    launch_intent_sha256 = _launch_intent_sha256(
        predecessor, root, cell_id=str(cell["cell_id"]), prepared_sha256=_sha(_canonical(prepared)),
    )
    record = predecessor._read_canonical(
        root / ("codex-record.json" if is_sol else "grok-record.json"), label=f"{label} provider record"
    )
    effective = predecessor._read_canonical(root / "effective-settings.json", label=f"{label} effective settings")
    route, evidence = (
        validate_live_sol_route(Path(queue_root), broker_factory=broker_factory)
        if is_sol else validate_live_grok_route(Path(queue_root), broker_factory=broker_factory)
    )
    if evidence != prepared.get("route_evidence") or evidence != receipt.get("route_evidence"):
        raise ValueError("HANNA native exec receipt route evidence is stale")
    expected_kind = "codex_local_lifecycle_receipt" if is_sol else "grok_native_envelope_receipt"
    expected_native_contact = not is_sol
    if (receipt.get("study_id") != STUDY_ID or receipt.get("kind") != expected_kind
            or receipt.get("cell_id") != cell["cell_id"] or receipt.get("native_contact_proven") is not expected_native_contact
            or receipt.get("process_launches") != 1 or receipt.get("request_sha256") != _sha(task)
            or receipt.get("response_schema_sha256") != _sha(schema)
            or receipt.get("launch_intent_sha256") != launch_intent_sha256
            or receipt.get("effective_settings_sha256") != _sha(_canonical(effective))):
        raise ValueError("HANNA native exec receipt bindings drifted")
    expected_identity = receipt.get("identity")
    if not isinstance(expected_identity, Mapping) or dict(identity) != dict(expected_identity):
        raise ValueError("HANNA native exec receipt identity is misassociated")
    if is_sol:
        raw_events = predecessor._stable_read_bytes(root / "raw-codex-events.bin")
        final_response = predecessor._stable_read_bytes(root / "raw-codex-final-response.bin")
        projection = _codex_event_projection(raw_events, _load_parse_codex_events())
        thread_id = projection["thread_id"]
        reported_session = record.get("reported", {}).get("session_id")
        if (receipt.get("raw_events_sha256") != _sha(raw_events)
                or receipt.get("final_response_sha256") != _sha(final_response)
                or final_response != predecessor._stable_read_bytes(root / "responses" / "batch-0001.attempt-0001.message.json")
                or projection["completed_agent_message_text"].encode("utf-8") != final_response
                or receipt.get("usage") != projection["usage"]
                or identity.get("contact_id") != f"unproven-native-endpoint-contact-for-local-thread:{thread_id}"
                or identity.get("session_id") != f"local-codex-thread-session:{reported_session or thread_id}"
                or (reported_session is not None and reported_session != thread_id)
                or receipt.get("local_codex_thread_lifecycle_proven") is not True
                or receipt.get("native_endpoint_contact_cardinality") != "unproven"
                or receipt.get("internal_retry_cardinality") != "unproven"
                or record.get("command") != _expected_codex_command(route["codex_command"][0], root)
                or effective.get("codex_cli_version") != route["codex_cli_version"]
                or effective.get("codex_command_identity") != route["codex_command_identity"]
                or effective.get("codex_adapter_sha256") != CODEX_ADAPTER_SHA256
                or effective.get("capture_jsonl_events") is not True
                or any(effective.get(key) is not False for key in ("tools_enabled", "web_search_enabled", "subagents_enabled"))
                or identity.get("provider") != "openai_codex"
                or identity.get("provider_reported_model") is not None
                or identity.get("identity_evidence") != "requested_and_local_effective_settings_only_not_provider_attested"):
            raise ValueError("HANNA native exec Codex receipt/session/command identity drifted")
    else:
        raw = predecessor._stable_read_bytes(root / "raw-grok-envelope.bin")
        request_id, session_id = _envelope_identity(raw, record)
        if (receipt.get("raw_envelope_sha256") != _sha(raw)
                or identity.get("contact_id") != request_id or identity.get("session_id") != session_id):
            raise ValueError("HANNA native exec receipt identity is misassociated")
        if (record.get("cli_version") != route["grok_cli_version"]
                or effective.get("grok_cli_version") != route["grok_cli_version"]
                or effective.get("grok_command_identity") != route["grok_command_identity"]
                or effective.get("tool_free_argv") != TOOL_FREE_ARGV
                or effective.get("system_prompt_override") != SYSTEM_PROMPT):
            raise ValueError("HANNA native exec receipt CLI/command identity drifted")
    native_request = event.get("native_request_bytes")
    if not isinstance(native_request, bytes) or native_request != task:
        raise ValueError("HANNA native exec predecessor native request bytes drifted")
    outbound = event.get("outbound_payload")
    try:
        outbound_value = json.loads(outbound.decode("utf-8")) if isinstance(outbound, bytes) else None
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("HANNA native exec predecessor outbound payload is invalid") from error
    if (not isinstance(outbound_value, dict) or predecessor.canonical(outbound_value) != predecessor_payload
            or outbound_value.get("components", {}).get("task_payload", "").encode("utf-8") != task
            or outbound_value.get("components", {}).get("response_schema", "").encode("utf-8") != schema):
        raise ValueError("HANNA native exec predecessor exact prompt/schema association drifted")
    predecessor._validate_effective_settings(event.get("effective_settings"), cell)
    if is_sol:
        return {
            "accepted": False, "local_lifecycle_verified": True,
            "native_endpoint_contact_cardinality": "unproven",
            "reason": "local_codex_thread_events_do_not_attest_native_endpoint_contact_cardinality",
        }
    return {"accepted": True}


def _cli_json_safe(value: Any) -> Any:
    if isinstance(value, bytes):
        return {"raw_bytes_omitted": True, "byte_count": len(value), "sha256": _sha(value)}
    if isinstance(value, Mapping):
        return {str(key): _cli_json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_cli_json_safe(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise TypeError(f"HANNA native exec CLI result contains unsupported value type: {type(value).__name__}")


def _cli_summary(result: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "format_version": 1, "study_id": STUDY_ID, "kind": "native_exec_cli_summary",
        "persisted_evidence_authoritative": True, "result": _cli_json_safe(result),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--prepare-only", action="store_true")
    mode.add_argument("--execute-one-grok", action="store_true")
    mode.add_argument("--execute-one-sol", action="store_true")
    parser.add_argument("--allow-remote", action="store_true")
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--cell-id", required=True)
    parser.add_argument("--queue-root", required=True, type=Path)
    parser.add_argument("--frozen-successor", required=True, type=Path)
    parser.add_argument("--hanna-csv", required=True, type=Path)
    parser.add_argument("--authorization-acknowledgement-sha256", required=True)
    args = parser.parse_args(argv)
    common = {
        "output_root": args.output_root, "cell_id": args.cell_id, "queue_root": args.queue_root,
        "frozen_successor_path": args.frozen_successor, "hanna_csv_path": args.hanna_csv,
        "authorization_acknowledgement_sha256": args.authorization_acknowledgement_sha256,
    }
    if args.prepare_only:
        if args.allow_remote:
            parser.error("--prepare-only forbids --allow-remote")
        result = prepare_only(**common)
    else:
        if not args.allow_remote:
            parser.error("live one-cell execution requires --allow-remote")
        result = (execute_grok if args.execute_one_grok else execute_sol)(**common, allow_remote=True)
    print(_canonical(_cli_summary(result)).decode("utf-8"), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
