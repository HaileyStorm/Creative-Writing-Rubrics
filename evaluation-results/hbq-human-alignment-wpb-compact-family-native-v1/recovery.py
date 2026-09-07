"""Append-only recovery for the incomplete WPB Grok campaign.

The original campaign remains the authority for its 89 completed receipts and
its ambiguous terminal attempt.  This module creates a separate recovery root;
it never edits, retries, or reuses evidence from that campaign.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import uuid
from collections.abc import Mapping
from pathlib import Path
from types import ModuleType
from typing import Any

HERE = Path(__file__).resolve().parent
QUEUE_ROOT = Path(r"C:\Users\Haile\.codex\state\model-work-queue")
LEGACY_EXECUTOR = HERE / "executor.py"
LEGACY_EXECUTOR_SHA256 = "b41ef08b9f93e0f6cb8646e96746240a058ce6d13392a80484caa61272421c10"
STUDY_ID = "hbq-human-alignment-wpb-compact-family-v1"
ORIGINAL_TERMINAL_CELL = "wpb-pair-wpb-en-0834"
ORIGINAL_CLAIM_SHA256 = "f0f61cd20baed8d8f2dfb5369c020cfde793a5973f5582d55652d59aab26be51"
LAST_SETTLEMENT_SHA256 = "c3b4d522f60639fe80061a57bb1282ed202f3ad9516a9b3eb41e7edeb60877f3"
ORIGINAL_SUCCESS_COUNT = 89
RECOVERY_COUNT = 40
AUTHORIZATION_RECORD_SHA256 = "699fbb473ee3b781607a12af388b57538f2ca973c60abb775ed56adfeed08cfd"
PLAN_NAME = "recovery-plan.json"
_HEX = set("0123456789abcdef")


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def sha256(value: bytes | Any) -> str:
    return hashlib.sha256(value if isinstance(value, bytes) else canonical(value)).hexdigest()


def _require(value: bool, message: str) -> None:
    if not value:
        raise ValueError(message)


def _hex(value: Any, label: str) -> str:
    _require(isinstance(value, str) and len(value) == 64 and set(value) <= _HEX, f"{label} must be a lowercase SHA-256")
    return value


def _json(path: Path, label: str) -> tuple[dict[str, Any], bytes]:
    raw = path.read_bytes()
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{label} is not UTF-8 JSON") from error
    _require(isinstance(value, dict), f"{label} must be an object")
    return value, raw


def _write_new(path: Path, value: Any) -> bytes:
    raw = canonical(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle:
        handle.write(raw)
    return raw


def _inventory(root: Path) -> dict[str, str]:
    return {path.relative_to(root).as_posix(): sha256(path.read_bytes()) for path in sorted(root.rglob("*")) if path.is_file()}


def _verify_origin(plan: Mapping[str, Any]) -> None:
    origin = plan.get("origin")
    _require(isinstance(origin, Mapping), "recovery origin binding is malformed")
    root = Path(str(origin.get("root", "")))
    expected = origin.get("inventory")
    if isinstance(expected, Mapping):
        _require(root.is_dir() and _inventory(root) == dict(expected), "original WPB evidence changed")
    status_path = origin.get("incomplete_status_path")
    if isinstance(status_path, str) and isinstance(origin.get("incomplete_sha256"), str):
        _require(sha256(Path(status_path).read_bytes()) == origin["incomplete_sha256"], "original incomplete status changed")


def _load_legacy() -> ModuleType:
    raw = LEGACY_EXECUTOR.read_bytes()
    _require(sha256(raw) == LEGACY_EXECUTOR_SHA256, "legacy WPB executor source drifted")
    name = "_wpb_recovery_legacy_executor"
    _require(name not in sys.modules, "legacy WPB executor module cache is not accepted")
    spec = importlib.util.spec_from_file_location(name, LEGACY_EXECUTOR)
    _require(spec is not None and spec.loader is not None, "legacy WPB executor cannot load")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        exec(compile(raw, str(LEGACY_EXECUTOR), "exec"), module.__dict__)  # noqa: S102 - hash-pinned legacy bytes
    finally:
        sys.modules.pop(name, None)
    _require(LEGACY_EXECUTOR.read_bytes() == raw, "legacy WPB executor changed during load")
    return module


def _plan_path(root: Path) -> Path:
    return root / PLAN_NAME


def _read_plan(root: Path, expected_sha256: str) -> dict[str, Any]:
    value, raw = _json(_plan_path(root), "recovery plan")
    _require(sha256(raw) == _hex(expected_sha256, "expected recovery plan hash"), "recovery plan hash drifted")
    _require(value.get("kind") == "wpb_native_recovery_plan" and value.get("study_id") == STUDY_ID, "recovery plan identity drifted")
    return value


def _origin_completed(origin: Path) -> tuple[set[str], set[str]]:
    completed: set[str] = set()
    terminal: set[str] = set()
    for settlement_path in sorted((origin / "batches").glob("*/settlement.json")):
        settlement, _raw = _json(settlement_path, "origin settlement")
        cells = settlement.get("cells")
        _require(isinstance(cells, list), "origin settlement cells are malformed")
        for entry in cells:
            _require(isinstance(entry, Mapping) and isinstance(entry.get("cell_id"), str), "origin settlement entry is malformed")
            cell_id = str(entry["cell_id"])
            if entry.get("state") == "completed":
                _require(cell_id not in completed, "origin has duplicate completed logical cells")
                completed.add(cell_id)
            elif entry.get("state") == "consumed_terminal":
                _require(cell_id not in terminal, "origin has duplicate terminal logical cells")
                terminal.add(cell_id)
    return completed, terminal


def _origin_identity_keys(origin: Path, completed: set[str]) -> set[str]:
    keys: set[str] = set()
    for identity_path in origin.glob("batches/*/execution/*/runtime-identity.json"):
        cell_id = identity_path.parent.name
        if cell_id not in completed:
            continue
        value, _raw = _json(identity_path, "origin runtime identity")
        request_id, session_id = value.get("request_id"), value.get("session_id")
        _require(isinstance(request_id, str) and request_id and isinstance(session_id, str) and session_id, "origin identity is incomplete")
        key = sha256({"request_id": request_id, "session_id": session_id})
        _require(key not in keys, "origin has duplicate request/session identity")
        keys.add(key)
    _require(len(keys) == len(completed), "origin completed identity inventory differs")
    return keys


def _origin_ambiguous_identity_keys(origin: Path) -> set[str]:
    path = origin / "batches" / "0009" / "execution" / ORIGINAL_TERMINAL_CELL / "runtime-identity.json"
    if not path.is_file():
        return set()
    value, _raw = _json(path, "origin ambiguous runtime identity")
    request_id, session_id = value.get("request_id"), value.get("session_id")
    if not isinstance(request_id, str) or not request_id or not isinstance(session_id, str) or not session_id:
        return set()
    return {sha256({"request_id": request_id, "session_id": session_id})}


def _origin_identity_components(origin: Path, completed: set[str]) -> tuple[set[str], set[str]]:
    requests: set[str] = set()
    sessions: set[str] = set()
    for identity_path in origin.glob("batches/*/execution/*/runtime-identity.json"):
        if identity_path.parent.name not in completed:
            continue
        value, _raw = _json(identity_path, "origin runtime identity")
        request_id, session_id = value.get("request_id"), value.get("session_id")
        _require(isinstance(request_id, str) and request_id and isinstance(session_id, str) and session_id, "origin identity is incomplete")
        requests.add(sha256(request_id.encode("utf-8")))
        sessions.add(sha256(session_id.encode("utf-8")))
    _require(len(requests) == len(completed) and len(sessions) == len(completed), "origin identity component inventory differs")
    return requests, sessions


def _rows(legacy: ModuleType, freeze_root: Path) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    resolution = legacy._resolution(freeze_root=freeze_root)
    values = resolution.get("rows")
    _require(isinstance(values, tuple) and len(values) == 129, "legacy WPB schedule geometry drifted")
    rows = {str(row["cell_id"]): dict(row) for row in values}
    _require(len(rows) == 129, "legacy WPB schedule has duplicate cells")
    return resolution, rows


def _frozen_schema(plan: Mapping[str, Any]) -> dict[str, Any]:
    binding = plan.get("response_schema")
    _require(isinstance(binding, Mapping), "recovery response schema binding is absent")
    path = Path(str(binding.get("path", "")))
    raw = path.read_bytes()
    _require(sha256(raw) == binding.get("sha256"), "recovery response schema changed")
    try:
        schema = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("recovery response schema is invalid") from error
    _require(isinstance(schema, dict) and canonical(schema) == raw, "recovery response schema is not canonical")
    return schema


def prepare(*, origin_root: Path, recovery_root: Path, freeze_root: Path, authorization_path: Path,
            incomplete_status_path: Path = HERE / "grok-incomplete.json",
            expected_authorization_metadata_sha256: str | None = None) -> dict[str, Any]:
    """Create the immutable recovery plan.  This performs no provider contact."""
    origin, recovery, authorization = Path(origin_root).resolve(), Path(recovery_root).resolve(), Path(authorization_path).resolve()
    incomplete_path = Path(incomplete_status_path).resolve()
    _require(origin.is_dir() and authorization.is_file() and incomplete_path.is_file(), "recovery origin, status, or authorization is unavailable")
    _require(not recovery.exists(), "recovery root must be new")
    _require(recovery != origin and origin not in recovery.parents and recovery not in origin.parents, "recovery root overlaps origin")
    authorization_value, authorization_raw = _json(authorization, "recovery authorization")
    if expected_authorization_metadata_sha256 is not None:
        _require(sha256(authorization_raw) == _hex(expected_authorization_metadata_sha256, "expected authorization metadata hash"), "recovery authorization metadata hash drifted")
    _require(authorization_value.get("decision") == "owner_authorized_wpb_recovery" and authorization_value.get("original_successful_cells") == ORIGINAL_SUCCESS_COUNT
             and authorization_value.get("original_terminal_cell") == ORIGINAL_TERMINAL_CELL and authorization_value.get("original_unstarted_cells") == 39
             and authorization_value.get("authorization_record_sha256") == AUTHORIZATION_RECORD_SHA256
             and authorization_value.get("automatic_retry_or_resend") is False and authorization_value.get("duplicate_logical_votes") is False,
             "recovery authorization does not bind the approved WPB scope")
    incomplete, incomplete_raw = _json(incomplete_path, "origin incomplete status")
    _require(incomplete.get("successful_cells") == ORIGINAL_SUCCESS_COUNT and incomplete.get("ambiguous_terminal_cells") == 1
             and incomplete.get("unstarted_cells") == 39 and incomplete.get("last_settlement_sha256") == LAST_SETTLEMENT_SHA256,
             "origin incomplete status drifted")
    completed, terminal = _origin_completed(origin)
    _require(len(completed) == ORIGINAL_SUCCESS_COUNT and terminal == {ORIGINAL_TERMINAL_CELL}, "origin terminal geometry drifted")
    settlement, settlement_raw = _json(origin / "batches" / "0009" / "settlement.json", "origin terminal settlement")
    _require(sha256(settlement_raw) == LAST_SETTLEMENT_SHA256, "origin last settlement hash drifted")
    terminal_entry = next((item for item in settlement.get("cells", []) if isinstance(item, Mapping) and item.get("cell_id") == ORIGINAL_TERMINAL_CELL), None)
    _require(isinstance(terminal_entry, Mapping) and terminal_entry.get("state") == "consumed_terminal" and terminal_entry.get("claim_sha256") == ORIGINAL_CLAIM_SHA256,
             "origin ambiguous terminal claim drifted")
    legacy = _load_legacy()
    resolution, rows = _rows(legacy, Path(freeze_root).resolve())
    unstarted = sorted(set(rows) - completed - terminal)
    _require(len(unstarted) == 39, "origin unstarted geometry drifted")
    reserved = _origin_identity_keys(origin, completed) | _origin_ambiguous_identity_keys(origin)
    reserved_requests, reserved_sessions = _origin_identity_components(origin, completed)
    schema_path = origin / "batches" / "0009" / "execution" / ORIGINAL_TERMINAL_CELL / "response-schema.json"
    _require(schema_path.is_file(), "original response schema is absent")
    schema_raw = schema_path.read_bytes()
    cells = [{"cell_id": ORIGINAL_TERMINAL_CELL, "kind": "single_replacement", "payload_sha256": rows[ORIGINAL_TERMINAL_CELL]["payload_sha256"]}]
    cells.extend({"cell_id": cell_id, "kind": "unstarted", "payload_sha256": rows[cell_id]["payload_sha256"]} for cell_id in unstarted)
    value = {
        "format_version": 1, "kind": "wpb_native_recovery_plan", "study_id": STUDY_ID,
        "authority": "development_screening_only", "metrics": "closed_until_complete_native_recovery",
        "origin": {"root": str(origin), "inventory": _inventory(origin), "incomplete_status_path": str(incomplete_path), "incomplete_sha256": sha256(incomplete_raw), "last_settlement_sha256": LAST_SETTLEMENT_SHA256,
                   "ambiguous_terminal_cell": ORIGINAL_TERMINAL_CELL, "ambiguous_claim_sha256": ORIGINAL_CLAIM_SHA256,
                   "successful_cells": ORIGINAL_SUCCESS_COUNT, "reserved_identity_hashes": sorted(reserved),
                   "reserved_request_id_hashes": sorted(reserved_requests), "reserved_session_id_hashes": sorted(reserved_sessions)},
        "authorization": {"path": str(authorization), "metadata_sha256": sha256(authorization_raw), "record_sha256": AUTHORIZATION_RECORD_SHA256},
        "legacy_executor": {"path": str(LEGACY_EXECUTOR), "sha256": LEGACY_EXECUTOR_SHA256},
        "response_schema": {"path": str(schema_path), "sha256": sha256(schema_raw)},
        "freeze_root": str(Path(freeze_root).resolve()), "schedule_sha256": resolution["schedule_sha256"], "cells": cells,
        "dispatch_policy": {"maximum_new_attempts": RECOVERY_COUNT, "automatic_retry_or_resend": False, "stop_on_ambiguity": True,
                            "required_runtime": {"adapter_version": 4, "execution_policy": "bounded_nonvisual_deny_wins_attested", "tools": "deny_wins_none_attested"}},
    }
    recovery.mkdir(parents=True)
    raw = _write_new(_plan_path(recovery), value)
    for item in cells:
        _write_new(recovery / "cells" / item["cell_id"] / "prepared.json", item)
    return {"recovery_root": str(recovery), "recovery_plan_sha256": sha256(raw), "planned_cells": RECOVERY_COUNT,
            "original_successful_cells": ORIGINAL_SUCCESS_COUNT, "provider_calls_made": 0}


def _read_review(path: Path, expected_sha256: str, plan_hash: str, plan: Mapping[str, Any], route: Mapping[str, Any], broker_path: Path,
                 runtime_path: Path, helper_path: Path) -> dict[str, Any]:
    value, raw = _json(path, "independent recovery review")
    _require(sha256(raw) == _hex(expected_sha256, "expected independent review hash"), "independent recovery review hash drifted")
    _require(value.get("decision") == "approved_wpb_native_recovery_dispatch" and value.get("recovery_plan_sha256") == plan_hash
             and value.get("authorization_record_sha256") == plan["authorization"]["record_sha256"], "independent recovery review binding drifted")
    _require(value.get("broker") == {"path": str(broker_path), "sha256": sha256(broker_path.read_bytes())}
             and value.get("runtime") == {"path": str(runtime_path), "sha256": sha256(runtime_path.read_bytes()), "adapter_version": 4}
             and value.get("helper") == {"path": str(helper_path), "sha256": sha256(helper_path.read_bytes())}
             and value.get("route_sha256") == sha256(route), "independent recovery review source or route pin drifted")
    return value


def _dispatchable(plan: Mapping[str, Any], root: Path, cell_id: str) -> None:
    cells = plan.get("cells")
    _require(isinstance(cells, list) and len(cells) == RECOVERY_COUNT, "recovery schedule is malformed")
    order = [str(item.get("cell_id")) for item in cells if isinstance(item, Mapping)]
    _require(len(order) == RECOVERY_COUNT and len(set(order)) == RECOVERY_COUNT and cell_id in order, "recovery schedule identity drifted")
    selected = order.index(cell_id)
    for previous in order[:selected]:
        previous_root = root / "cells" / previous
        _require((previous_root / "admission.json").is_file(), "recovery campaign stopped before this cell; no skip or retry")
    for candidate in order:
        candidate_root = root / "cells" / candidate
        if (candidate_root / "attempt.json").is_file() and not (candidate_root / "admission.json").is_file():
            _require(candidate == cell_id and not (candidate_root / "outcome.json").is_file(), "recovery campaign stopped by an unresolved or terminal attempt")


def _load_broker(path: Path) -> tuple[ModuleType, type[Any]]:
    raw = path.read_bytes()
    package_name = "_wpb_recovery_model_work_queue"
    _require(not any(name == package_name or name.startswith(package_name + ".") for name in sys.modules), "broker module cache is not accepted")
    package = ModuleType(package_name)
    package.__path__ = [str(path.parent)]  # type: ignore[attr-defined]
    package.__package__ = package_name
    sys.modules[package_name] = package
    try:
        spec = importlib.util.spec_from_file_location(package_name + ".broker", path)
        _require(spec is not None and spec.loader is not None, "canonical broker cannot load")
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        exec(compile(raw, str(path), "exec"), module.__dict__)  # noqa: S102 - independently reviewed current broker bytes
    finally:
        for name in list(sys.modules):
            if name == package_name or name.startswith(package_name + "."):
                sys.modules.pop(name, None)
    broker_type = getattr(module, "Broker", None)
    _require(isinstance(broker_type, type) and callable(getattr(broker_type, "run_grok_native_request", None))
             and callable(getattr(broker_type, "read_grok_native_envelope", None)), "canonical broker surface drifted")
    _require(path.read_bytes() == raw, "canonical broker changed during load")
    return module, broker_type


def dispatch(*, recovery_root: Path, expected_plan_sha256: str, cell_id: str, route: Mapping[str, Any],
             reviewed_authorization_path: Path, broker_path: Path, runtime_source_path: Path, helper_source_path: Path,
             expected_review_sha256: str, queue_root: Path = QUEUE_ROOT) -> dict[str, Any]:
    """Make one governed native request; every outcome permanently consumes its recovery cell."""
    root = Path(recovery_root).resolve()
    plan = _read_plan(root, expected_plan_sha256)
    _verify_origin(plan)
    expected_plan_sha256 = _hex(expected_plan_sha256, "expected recovery plan hash")
    entries = {str(item.get("cell_id")): item for item in plan.get("cells", []) if isinstance(item, Mapping)}
    item = entries.get(cell_id)
    _require(item is not None and len(entries) == RECOVERY_COUNT, "recovery cell is not planned")
    cell_root = root / "cells" / cell_id
    _require((cell_root / "prepared.json").is_file() and not (cell_root / "attempt.json").exists(), "recovery cell is already consumed; no resend")
    _dispatchable(plan, root, cell_id)
    broker_path, runtime_source_path, helper_source_path = Path(broker_path).resolve(), Path(runtime_source_path).resolve(), Path(helper_source_path).resolve()
    queue_root = Path(queue_root).resolve()
    _require(broker_path.is_file() and runtime_source_path.is_file() and helper_source_path.is_file(), "canonical broker, runtime, or helper source is unavailable")
    _require(queue_root == QUEUE_ROOT.resolve() and queue_root.is_dir(), "dispatch requires the existing governed queue root")
    _read_review(Path(reviewed_authorization_path).resolve(), expected_review_sha256, expected_plan_sha256, plan, route, broker_path, runtime_source_path, helper_source_path)
    legacy = _load_legacy()
    resolution, rows = _rows(legacy, Path(plan["freeze_root"]))
    row = rows.get(cell_id)
    _require(row is not None and row["payload_sha256"] == item["payload_sha256"] and resolution["schedule_sha256"] == plan["schedule_sha256"], "recovery payload or schedule drifted")
    payload = resolution["payloads"][cell_id]
    _require(sha256(payload) == item["payload_sha256"], "recovery payload bytes drifted")
    schema = _frozen_schema(plan)
    _broker_module, broker_type = _load_broker(broker_path)
    broker = broker_type(queue_root)
    _require(isinstance(route.get("name"), str) and route["name"], "recovery route has no name")
    session_id = str(uuid.uuid4())
    attempt = {"format_version": 1, "cell_id": cell_id, "plan_sha256": expected_plan_sha256, "review_sha256": expected_review_sha256,
               "payload_sha256": sha256(payload), "schema_sha256": sha256(schema), "route_sha256": sha256(route),
               "broker_sha256": sha256(broker_path.read_bytes()), "runtime_source_sha256": sha256(runtime_source_path.read_bytes()),
               "helper_source_sha256": sha256(helper_source_path.read_bytes()), "broker_path": str(broker_path),
               "runtime_source_path": str(runtime_source_path), "helper_source_path": str(helper_source_path), "queue_root": str(queue_root),
               "session_id": session_id, "session_id_hash": sha256(session_id.encode("utf-8")), "route_name": route["name"],
               "requested_model": route.get("model"), "requested_reasoning_effort": route.get("reasoning_effort")}
    _write_new(cell_root / "attempt.json", attempt)
    _write_new(cell_root / "route.json", dict(route))
    _write_new(cell_root / "request.json", {"prompt": payload.decode("utf-8")})
    _write_new(cell_root / "response-schema.json", schema)
    outcome = broker.run_grok_native_request(str(route["name"]), {"prompt": payload.decode("utf-8")}, output_schema=schema,
                                              nonvisual_max_turns=1, session_id=session_id,
                                              before_contact=lambda: (_verify_origin(plan), _read_review(Path(reviewed_authorization_path).resolve(), expected_review_sha256, expected_plan_sha256, plan, route, broker_path, runtime_source_path, helper_source_path)),
                                              expected_route_sha256=sha256(route))
    _require(isinstance(outcome, Mapping) and set(outcome) == {"state", "result", "failure"}, "canonical broker outcome is malformed")
    _write_new(cell_root / "outcome.json", dict(outcome))
    if outcome["state"] != "completed" or outcome["failure"] is not None or not isinstance(outcome["result"], Mapping):
        return {"cell_id": cell_id, "status": "terminal_no_resend", "outcome_sha256": sha256(canonical(dict(outcome))), "provider_calls_made": 1}
    result = dict(outcome["result"])
    descriptor = result.get("native_envelope_artifact")
    _require(isinstance(descriptor, Mapping), "completed broker result lacks envelope descriptor")
    envelope = broker.read_grok_native_envelope(dict(descriptor))
    _require(isinstance(envelope, bytes), "canonical broker returned a non-byte envelope")
    _write_new(cell_root / "result.json", result)
    with (cell_root / "native-envelope.json").open("xb") as handle:
        handle.write(envelope)
    return {"cell_id": cell_id, "status": "completed_pending_admission", "result_sha256": sha256(result),
            "envelope_sha256": sha256(envelope), "provider_calls_made": 1}


def _validate_provider_evidence(plan: Mapping[str, Any], cell_root: Path, attempt: Mapping[str, Any], result: Mapping[str, Any], envelope_raw: bytes) -> tuple[str, str]:
    route, request = _json(cell_root / "route.json", "recovery route"), _json(cell_root / "request.json", "recovery request")
    schema, schema_raw = _json(cell_root / "response-schema.json", "recovery response schema")
    route_value, request_value = route[0], request[0]
    _require(schema_raw == canonical(schema) and sha256(schema_raw) == attempt.get("schema_sha256"), "recovery response schema commitment drifted")
    _require(schema == _frozen_schema(plan), "recovery response schema no longer matches the frozen plan")
    _require(request_value == {"prompt": _payload_for(plan, cell_root.name).decode("utf-8")}, "recovery request payload drifted")
    _require(attempt.get("route_sha256") == sha256(route_value) and attempt.get("broker_sha256") == sha256(Path(str(attempt.get("broker_path", ""))).read_bytes())
             and attempt.get("runtime_source_sha256") == sha256(Path(str(attempt.get("runtime_source_path", ""))).read_bytes())
             and attempt.get("helper_source_sha256") == sha256(Path(str(attempt.get("helper_source_path", ""))).read_bytes()), "recovery route, broker, runtime, or helper commitment drifted")
    queue_root = Path(str(attempt.get("queue_root", ""))).resolve()
    _require(queue_root == QUEUE_ROOT.resolve() and queue_root.is_dir(), "recovery evidence queue root drifted")
    _module, broker_type = _load_broker(Path(str(attempt["broker_path"])))
    broker = broker_type(queue_root)
    effective_route = {**route_value, "output_schema": schema, "output_schema_artifact_hash": sha256(schema_raw), "nonvisual_max_turns": 1}
    descriptor = result.get("native_envelope_artifact")
    _require(isinstance(descriptor, Mapping) and broker.read_grok_native_envelope(dict(descriptor)) == envelope_raw, "retained native envelope bytes differ from the canonical artifact")
    projection = canonical({"control": {"version": 1, "state": "completed"}, "result": dict(result)})
    parsed = broker._parse_grok_exec_envelope(projection, effective_route, request_value, expected_session_id=str(attempt["session_id"]))
    _require(getattr(parsed, "state", None) == "completed" and getattr(parsed, "result", None) == result, "canonical Grok envelope validation failed")
    request_id = json.loads(envelope_raw.decode("utf-8")).get("requestId")
    session_id = str(attempt["session_id"])
    _require(isinstance(request_id, str) and request_id, "canonical Grok envelope lacks request identity")
    return request_id, session_id


def admit(*, recovery_root: Path, expected_plan_sha256: str, cell_id: str) -> dict[str, Any]:
    """Admit one completed adapter-v4 result from immutable recovery evidence."""
    root = Path(recovery_root).resolve()
    plan = _read_plan(root, expected_plan_sha256)
    _verify_origin(plan)
    entries = {str(item.get("cell_id")): item for item in plan.get("cells", []) if isinstance(item, Mapping)}
    item = entries.get(cell_id)
    _require(item is not None, "recovery cell is not planned")
    cell_root = root / "cells" / cell_id
    _require(not (cell_root / "admission.json").exists(), "recovery cell already admitted")
    attempt, _ = _json(cell_root / "attempt.json", "recovery attempt")
    outcome, _ = _json(cell_root / "outcome.json", "recovery outcome")
    _require(outcome.get("state") == "completed" and outcome.get("failure") is None, "recovery cell has no completed native result")
    result, result_raw = _json(cell_root / "result.json", "recovery native result")
    envelope_raw = (cell_root / "native-envelope.json").read_bytes()
    try:
        envelope = json.loads(envelope_raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("recovery native envelope is not JSON") from error
    canonical_request_id, canonical_session_id = _validate_provider_evidence(plan, cell_root, attempt, result, envelope_raw)
    _require(outcome.get("result") == result and isinstance(envelope, Mapping) and set(result) == {"schema_version", "request_hash", "output", "output_hash", "runtime", "native_envelope_artifact"}
             and result.get("schema_version") == 2 and envelope.get("structuredOutput") == result.get("output")
             and result.get("request_hash") == sha256(canonical({"prompt": _payload_for(plan, cell_id).decode("utf-8")}))
             and result.get("output_hash") == sha256(result["output"]), "recovery result payload binding drifted")
    descriptor, runtime = result.get("native_envelope_artifact"), result.get("runtime")
    _require(isinstance(descriptor, Mapping) and descriptor == {"schema_version": 1, "sha256": sha256(envelope_raw), "byte_length": len(envelope_raw)}
             and isinstance(runtime, Mapping), "recovery envelope descriptor or runtime is malformed")
    execution = runtime.get("execution_contract")
    _require(runtime.get("adapter_version") == 4 and runtime.get("execution_policy") == "bounded_nonvisual_deny_wins_attested"
             and isinstance(runtime.get("tool_policy_attestation_hash"), str) and len(runtime["tool_policy_attestation_hash"]) == 64
             and isinstance(execution, Mapping) and execution.get("tools") == "deny_wins_none_attested" and execution.get("max_turns") == 1
             and execution.get("output_schema_hash") == attempt["schema_sha256"] and runtime.get("reasoning_attested") is False
             and execution.get("staged_prompt_sha256") == item["payload_sha256"] and execution.get("staged_prompt_byte_length") == len(_payload_for(plan, cell_id))
             and runtime.get("session_id_hash") == attempt["session_id_hash"] and runtime.get("envelope_hash") == sha256(envelope_raw),
             "recovery result lacks adapter-v4 deny-wins attestation")
    if isinstance(attempt.get("requested_model"), str):
        _require(runtime.get("requested_model") == attempt["requested_model"], "recovery result model drifted")
    if isinstance(attempt.get("requested_reasoning_effort"), str):
        _require(runtime.get("requested_reasoning_effort") == attempt["requested_reasoning_effort"], "recovery result reasoning drifted")
    request_id, session_id = envelope.get("requestId"), envelope.get("sessionId")
    _require(isinstance(request_id, str) and request_id and isinstance(session_id, str) and session_id
             and request_id == canonical_request_id and session_id == canonical_session_id
             and runtime.get("request_id_hash") == sha256(request_id.encode("utf-8")) and runtime.get("session_id_hash") == sha256(session_id.encode("utf-8")),
             "recovery result identity binding drifted")
    identity_key, request_hash, session_hash = sha256({"request_id": request_id, "session_id": session_id}), sha256(request_id.encode("utf-8")), sha256(session_id.encode("utf-8"))
    _require(identity_key not in set(plan["origin"]["reserved_identity_hashes"])
             and request_hash not in set(plan["origin"].get("reserved_request_id_hashes", []))
             and session_hash not in set(plan["origin"].get("reserved_session_id_hashes", [])), "recovery identity overlaps original evidence")
    for path in (root / "cells").glob("*/admission.json"):
        prior, _ = _json(path, "prior recovery admission")
        _require(prior.get("identity_sha256") != identity_key and prior.get("request_id_sha256") != request_hash and prior.get("session_id_sha256") != session_hash, "recovery identity overlaps another recovery cell")
    legacy = _load_legacy()
    resolution, _rows_value = _rows(legacy, Path(plan["freeze_root"]))
    answer = legacy._valid_response(resolution["core"], result["output"])
    admission = {"format_version": 1, "cell_id": cell_id, "plan_sha256": expected_plan_sha256, "result_sha256": sha256(result_raw),
                 "envelope_sha256": sha256(envelope_raw), "identity_sha256": identity_key, "request_id_sha256": request_hash, "session_id_sha256": session_hash, "payload_sha256": item["payload_sha256"],
                 "adapter_version": 4, "tool_policy_attestation_hash": runtime["tool_policy_attestation_hash"], "response": answer}
    raw = _write_new(cell_root / "admission.json", admission)
    return {"cell_id": cell_id, "admission_sha256": sha256(raw), "status": "admitted", "provider_calls_made": 0}


def _payload_for(plan: Mapping[str, Any], cell_id: str) -> bytes:
    legacy = _load_legacy()
    resolution, rows = _rows(legacy, Path(plan["freeze_root"]))
    _require(cell_id in rows and resolution["schedule_sha256"] == plan["schedule_sha256"], "recovery schedule drifted")
    payload = resolution["payloads"][cell_id]
    _require(sha256(payload) == rows[cell_id]["payload_sha256"], "recovery payload bytes drifted")
    return payload


def _verify_admission(plan: Mapping[str, Any], root: Path, item: Mapping[str, Any]) -> dict[str, Any]:
    cell_id = str(item["cell_id"])
    cell_root = root / "cells" / cell_id
    _require(all((cell_root / name).is_file() for name in ("attempt.json", "outcome.json", "result.json", "native-envelope.json", "route.json", "request.json", "response-schema.json", "admission.json")), "recovery raw evidence is missing")
    admission, _admission_raw = _json(cell_root / "admission.json", "recovery admission")
    attempt, _ = _json(cell_root / "attempt.json", "recovery attempt")
    outcome, _ = _json(cell_root / "outcome.json", "recovery outcome")
    result, result_raw = _json(cell_root / "result.json", "recovery native result")
    envelope_raw = (cell_root / "native-envelope.json").read_bytes()
    _require(outcome.get("state") == "completed" and outcome.get("failure") is None and outcome.get("result") == result
             and admission.get("cell_id") == cell_id and admission.get("plan_sha256") == sha256(_plan_path(root).read_bytes())
             and admission.get("payload_sha256") == item["payload_sha256"] and admission.get("result_sha256") == sha256(result_raw)
             and admission.get("envelope_sha256") == sha256(envelope_raw),
             "recovery admission commitment drifted")
    request_id, session_id = _validate_provider_evidence(plan, cell_root, attempt, result, envelope_raw)
    _require(admission.get("request_id_sha256") == sha256(request_id.encode("utf-8"))
             and admission.get("session_id_sha256") == sha256(session_id.encode("utf-8"))
             and admission.get("identity_sha256") == sha256({"request_id": request_id, "session_id": session_id}), "recovery admission identity drifted")
    legacy = _load_legacy()
    resolution, _rows_value = _rows(legacy, Path(plan["freeze_root"]))
    _require(admission.get("response") == legacy._valid_response(resolution["core"], result.get("output")), "recovery admitted response differs from the canonical result")
    return admission


def _legacy_prefix(*, plan: Mapping[str, Any]) -> tuple[list[dict[str, Any]], set[str]]:
    """Re-admit the historical prefix through the exact legacy receipt validators."""
    legacy = _load_legacy()
    resolution, _rows_value = _rows(legacy, Path(plan["freeze_root"]))
    origin = Path(plan["origin"]["root"])
    campaign, _raw = legacy._campaign(origin, resolution, "222647de0beecb6f860ade8d63bf6b212562cfc400602aac8184c5af59ddf322")
    completed: dict[str, tuple[dict[str, Any], dict[str, Any], Path]] = {}
    with legacy._grok_bound(resolution) as (lifecycle, _base, v9, _v11, v13, _v15):
        legacy._historical_cell_states(origin, sha256(campaign), resolution, "222647de0beecb6f860ade8d63bf6b212562cfc400602aac8184c5af59ddf322", lifecycle, v9)
        for number in legacy._batch_numbers(origin):
            batch_plan, batch_hash = legacy._batch_plan(origin, number, sha256(campaign))
            settlement, _settlement_hash = legacy._settlement(origin, number, batch_hash, sha256(campaign))
            rows = {str(row["cell_id"]): row for row in legacy._grok_plan_rows(resolution, batch_plan)}
            for entry in settlement["cells"]:
                if entry.get("state") == "completed":
                    cell_id = str(entry["cell_id"])
                    _require(cell_id not in completed, "legacy prefix has duplicate completed cell")
                    completed[cell_id] = (rows[cell_id], batch_plan, origin / "batches" / f"{number:04d}" / "execution")
        _require(len(completed) == ORIGINAL_SUCCESS_COUNT, "legacy prefix is not exactly 89 completed cells")
        admitted: dict[str, dict[str, Any]] = {}
        for number in legacy._batch_numbers(origin):
            subset = tuple(row for row, batch, _execution in completed.values() if batch.get("batch_number") == number)
            if subset:
                first = completed[str(subset[0]["cell_id"])]
                admitted.update(legacy._grok_admit_rows(resolution, lifecycle=lifecycle, v13=v13, execution=first[2], rows=subset, plan=first[1], acknowledgement="222647de0beecb6f860ade8d63bf6b212562cfc400602aac8184c5af59ddf322"))
    measurements = [{"endpoint": "grok", "cell_id": cell_id, "payload_sha256": completed[cell_id][0]["payload_sha256"],
                     "measurement_provenance": {"endpoint": "grok", "cell_id": cell_id, "payload_sha256": completed[cell_id][0]["payload_sha256"], "parsed_response_sha256": sha256(admitted[cell_id]["answer"])},
                     "response": admitted[cell_id]["answer"]} for cell_id in sorted(completed)]
    return measurements, {str(item["cell_id"]) for item in measurements}


def report(*, recovery_root: Path, expected_plan_sha256: str, profile: Mapping[str, Any]) -> dict[str, Any]:
    """Produce development-only amended metrics only after all 129 receipts admit."""
    root = Path(recovery_root).resolve()
    plan = _read_plan(root, expected_plan_sha256)
    _verify_origin(plan)
    recoveries = []
    for item in plan["cells"]:
        path = root / "cells" / str(item["cell_id"]) / "admission.json"
        if not path.is_file():
            return {"status": "closed_incomplete", "authority": "development_screening_only", "original_successful_cells": ORIGINAL_SUCCESS_COUNT,
                    "recovered_native_cells": len(recoveries), "required_recovered_native_cells": RECOVERY_COUNT, "metrics": None}
        recoveries.append(_verify_admission(plan, root, item))
    legacy_measurements, legacy_ids = _legacy_prefix(plan=plan)
    _require(len(legacy_measurements) == ORIGINAL_SUCCESS_COUNT and ORIGINAL_TERMINAL_CELL not in legacy_ids, "legacy prefix replay drifted")
    recovery_ids = {str(item["cell_id"]) for item in recoveries}
    _require(len(recovery_ids) == RECOVERY_COUNT and not (legacy_ids & recovery_ids), "recovery logical vote overlap")
    _require(len({item["request_id_sha256"] for item in recoveries}) == RECOVERY_COUNT and len({item["session_id_sha256"] for item in recoveries}) == RECOVERY_COUNT, "recovery report identity overlap")
    legacy = _load_legacy()
    resolution, rows = _rows(legacy, Path(plan["freeze_root"]))
    recovered_measurements = [{"endpoint": "grok", "cell_id": item["cell_id"], "payload_sha256": item["payload_sha256"],
                               "measurement_provenance": {"endpoint": "grok", "cell_id": item["cell_id"], "payload_sha256": item["payload_sha256"], "parsed_response_sha256": sha256(item["response"])}, "response": item["response"]}
                              for item in recoveries]
    all_measurements = legacy_measurements + recovered_measurements
    _require(set(rows) == {str(item["cell_id"]) for item in all_measurements} and len(all_measurements) == 129, "recovery report remains incomplete")
    analysis = resolution["core"].analyze(Path(plan["freeze_root"]), all_measurements, profile)
    return {"format_version": 1, "kind": "wpb_recovery_amended_native_report", "study_id": STUDY_ID,
            "status": "complete_recovered_native_campaign", "authority": "development_screening_only", "confirmation": "closed",
            "metrics_label": "recovery_amended", "original_successful_cells": ORIGINAL_SUCCESS_COUNT, "recovered_native_cells": RECOVERY_COUNT,
            "native_endpoint_contact_cardinality": "unproven", "analysis": analysis}
