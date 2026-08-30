#!/usr/bin/env python3
"""Thin governed one-cell execution adapter for the frozen revision-gain v2 pilot."""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import subprocess
import sys
from datetime import UTC, datetime
from collections.abc import Mapping
from pathlib import Path
from types import ModuleType
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
CONTRACT_PATH = HERE / "study-contract.json"
STUDY_ID = "cwr-guided-revision-gain-v2-live-exec-v1"
PILOT_STUDY_ID = "cwr-guided-revision-gain-v2-lean-pilot"
PILOT_PATH = ROOT / "evaluation-results" / "cwr-guided-revision-gain-v2-lean-pilot" / "study.py"
QUEUE_TOOLS_ROOT = Path(r"C:\Users\Haile\.codex\tools")
DEFAULT_QUEUE_ROOT = Path(r"C:\Users\Haile\.codex\state\model-work-queue")
EXPECTED_ROUTES = {
    "grok-4.6": {"adapter": "grok_exec", "provider": "xai_grok_build", "destination": "xai_grok_build_subscription"},
    "gpt-5.6-sol": {"adapter": "codex_exec", "provider": "openai_codex", "destination": "openai_codex_chatgpt_subscription"},
}
GROK_REPORTED_MODEL = "grok-4.6-build"
_SUBPROCESS_RUN = subprocess.run


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _stable_bytes(path: Path, *, label: str) -> bytes:
    path = Path(os.path.abspath(path))
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current /= part
        try:
            info = os.lstat(current)
        except FileNotFoundError as error:
            raise ValueError(f"Revision-gain live adapter {label} is missing") from error
        if stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & 0x400):
            raise ValueError(f"Revision-gain live adapter {label} is reparsed")
    before = os.lstat(path)
    with path.open("rb") as handle:
        opened = os.fstat(handle.fileno())
        if (before.st_dev, before.st_ino, before.st_size) != (opened.st_dev, opened.st_ino, opened.st_size):
            raise ValueError(f"Revision-gain live adapter {label} identity drifted")
        raw = handle.read()
        after = os.fstat(handle.fileno())
    if (opened.st_dev, opened.st_ino, opened.st_size) != (after.st_dev, after.st_ino, after.st_size):
        raise ValueError(f"Revision-gain live adapter {label} changed during read")
    return raw


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _write_once(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle:
        handle.write(canonical(value) + b"\n")


def _write_control_once(path: Path, raw: bytes) -> None:
    value = json.loads(raw.decode("utf-8"))
    if canonical(value) + b"\n" != raw.rstrip(b"\r\n") + b"\n":
        raise ValueError("Revision-gain live adapter control envelope is not canonical")
    _write_once(path, value)


def _commitment(root: Path, path: Path) -> dict[str, Any]:
    raw = _stable_bytes(path, label="artifact")
    return {"path": path.relative_to(root).as_posix(), "bytes": len(raw), "sha256": _sha256(raw)}


def contract() -> dict[str, Any]:
    raw = _stable_bytes(CONTRACT_PATH, label="contract")
    value = json.loads(raw.decode("utf-8"))
    expected = {"format_version": 1, "study_id": STUDY_ID, "pilot": {"commit": "37ba2cb0fb72fe9c1abcb05efc3d6f641c380cab", "path": "evaluation-results/cwr-guided-revision-gain-v2-lean-pilot/study.py", "bytes": 54847, "sha256": "727db4cee210f5930eecdde1654b0c89cc1756006393601eaa33e70cfd5a72cf"}, "authorized_acknowledgement_sha256": "2fb371ff82b37fe22d238a223fc030ad7a7bb9a10b672719da081470d25dbe78", "geometry": {"feedback": 4, "revisions": 8, "endpoints": 40, "contacts": 52}, "phases": ["cwr_feedback", "revision_generation", "blind_endpoint_judgment"], "provider_calls_made_by_prepare": 0, "dispatch": "explicit_allow_remote_one_launch_no_resend"}
    if value != expected:
        raise ValueError("Revision-gain live adapter contract drifted")
    return value


def _pilot() -> ModuleType:
    expected = contract()["pilot"]
    raw = _stable_bytes(PILOT_PATH, label="pinned v2 pilot")
    if len(raw) != expected["bytes"] or _sha256(raw) != expected["sha256"]:
        raise ValueError("Revision-gain live adapter pilot pin drifted")
    module = ModuleType("_revision_gain_v2_pilot")
    module.__file__ = str(PILOT_PATH)
    exec(compile(raw, str(PILOT_PATH), "exec"), module.__dict__)
    module._native_read_verified_receipt = module._read_verified_receipt
    def read_authority(path: Path, *, expected_event_id: str, expected_phase: str) -> dict[str, Any]:
        _, verified = _read_receipt_authority(module, root=Path(path).parent, event_id=expected_event_id, phase=expected_phase)
        return verified
    module._read_verified_receipt = read_authority
    if _stable_bytes(PILOT_PATH, label="pinned v2 pilot") != raw:
        raise ValueError("Revision-gain live adapter pilot changed during load")
    return module


def _broker(queue_root: Path):
    tools = str(QUEUE_TOOLS_ROOT)
    if tools not in sys.path:
        sys.path.insert(0, tools)
    from model_work_queue.broker import Broker  # type: ignore[import-not-found]
    import model_work_queue.broker as broker_module  # type: ignore[import-not-found]

    if Path(broker_module.__file__).resolve().parent != (QUEUE_TOOLS_ROOT / "model_work_queue").resolve():
        raise ValueError("Revision-gain live adapter queue validator resolved outside the governed tools root")
    return Broker(Path(queue_root))


def _governed_route(pilot: ModuleType, *, queue_root: Path, phase: str, event_id: str) -> tuple[Any, dict[str, Any], dict[str, Any]]:
    if Path(queue_root).resolve() != DEFAULT_QUEUE_ROOT.resolve():
        raise ValueError("Revision-gain live adapter requires the canonical governed queue root")
    generic = pilot._prepared_payload(pilot.contract(), phase=phase, event_id=event_id)
    expected = EXPECTED_ROUTES[generic["provider_model"]]
    broker = _broker(queue_root)
    registry = broker._load_registry_live()
    candidates = [route for route in registry["routes"] if route.get("model") == generic["provider_model"]]
    if len(candidates) != 1:
        raise ValueError("Revision-gain live adapter current governed exact route is missing or ambiguous")
    route = candidates[0]
    broker._validate_route(route, verify_command_identity=True, validate_current_evidence=True)
    required = {
        "adapter": expected["adapter"], "provider": expected["provider"], "destination": expected["destination"],
        "model": generic["provider_model"], "reasoning_effort": generic["reasoning"], "account_class": "subscription",
        "zero_charge": True, "armed": True, "health": "healthy", "identity_evidence": "requested_only",
    }
    if any(route.get(key) != value for key, value in required.items()) or "public_repo" not in route.get("allowed_payload_classes", []):
        raise ValueError("Revision-gain live adapter governed route identity or disclosure class drifted")
    if route.get("timeout_seconds") != 900:
        raise ValueError("Revision-gain live adapter governed route timeout drifted")
    registry_raw = _stable_bytes(broker.routes_path, label="governed route registry")
    if json.loads(registry_raw.decode("utf-8")) != registry:
        raise ValueError("Revision-gain live adapter governed registry changed during validation")
    evidence_hash = route["cost_evidence"]["evidence_hash"]
    evidence_raw = broker._load_artifact_bytes(evidence_hash)
    receipt_key = "subscription_receipt_hash" if route["adapter"] == "grok_exec" else "auth_receipt_hash"
    receipt_raw = broker._load_artifact_bytes(route[receipt_key])
    runtime_identity = ({"adapter_version": 1, "grok_command": route["grok_command"], "model": route["model"],
                         "reported_model": route["reported_model"], "reasoning_effort": route["reasoning_effort"],
                         "nonvisual_max_turns": route["nonvisual_max_turns"]}
                        if route["adapter"] == "grok_exec" else
                        {"adapter_version": 1, "codex_command": route["codex_command"], "model": route["model"],
                         "reasoning_effort": route["reasoning_effort"]})
    proof = {
        "format_version": 1, "kind": "governed_model_work_queue_route_proof", "queue_root": str(Path(queue_root).resolve()),
        "registry_sha256": _sha256(registry_raw), "route_name": route["name"], "route_semantic_sha256": broker._route_semantic_identity_hash(route),
        "model": route["model"], "adapter": route["adapter"], "provider": route["provider"], "destination": route["destination"],
        "reasoning": route["reasoning_effort"], "tools_enabled": False, "payload_classification": "public_repo",
        "zero_charge": True, "account_class": "subscription", "cost_evidence": dict(route["cost_evidence"]),
        "cost_evidence_sha256": _sha256(evidence_raw), "route_receipt_field": receipt_key,
        "route_receipt_sha256": _sha256(receipt_raw),
        "expected_adapter_runtime_identity_sha256": _sha256(canonical(runtime_identity)),
        "validated_at": datetime.now(UTC).isoformat(),
    }
    return broker, dict(route), proof


def _persist_route_proof(*, run_root: Path, root: Path, proof: Mapping[str, Any]) -> dict[str, Any]:
    path = root / "governed-route-proof.json"
    _write_once(path, proof)
    return _commitment(run_root, path)


def _reauth_route(*, pilot: ModuleType, run_root: Path, phase: str, event_id: str, binding: Mapping[str, Any]) -> tuple[Any, dict[str, Any]]:
    proof_path = Path(run_root) / str(binding.get("path", ""))
    if _commitment(Path(run_root), proof_path) != dict(binding):
        raise ValueError("Revision-gain live adapter governed route proof binding drifted")
    proof = json.loads(_stable_bytes(proof_path, label="governed route proof").decode("utf-8"))
    broker, route, current = _governed_route(pilot, queue_root=Path(proof["queue_root"]), phase=phase, event_id=event_id)
    stable_fields = set(proof) - {"validated_at"}
    if any(proof.get(key) != current.get(key) for key in stable_fields):
        raise ValueError("Revision-gain live adapter live governed route changed after preparation")
    return broker, route


def _cell_root(run_root: Path, phase: str, event_id: str) -> Path:
    return Path(run_root) / "live-cells" / phase / event_id


def _phase_dependencies(pilot: ModuleType, *, phase: str, event_id: str, lineage_records: list[Mapping[str, Any]] | None, feedback_receipt_path: Path | None, completed_feedback_receipt_paths: list[Path] | None, target_root: Path | None, target_manifest_path: Path | None) -> None:
    value = pilot.contract()
    if phase == "cwr_feedback":
        allowed = {event["cwr_feedback_event_id"] for event in pilot.revision_schedule(value) if event["cwr_feedback_event_id"]}
        if event_id not in allowed:
            raise ValueError("Revision-gain live adapter feedback event is not scheduled")
        return
    if phase == "revision_generation":
        event = next((row for row in pilot.revision_schedule(value) if row["event_id"] == event_id), None)
        if event is None:
            raise ValueError("Revision-gain live adapter revision event is not scheduled")
        if event["guidance_arm"] == "cwr_guided":
            if feedback_receipt_path is None:
                raise ValueError("Revision-gain live adapter guided revision requires ingested Sol feedback")
            receipt = pilot._read_verified_receipt(Path(feedback_receipt_path), expected_event_id=event["cwr_feedback_event_id"], expected_phase="cwr_feedback")
            if receipt["event_id"] != event["cwr_feedback_event_id"]:
                raise ValueError("Revision-gain live adapter feedback receipt binding drifted")
        if event["cycle"] == 2 and not lineage_records:
            raise ValueError("Revision-gain live adapter cycle two requires ingested cycle-one lineage")
        return
    if phase == "blind_endpoint_judgment":
        if event_id not in {event["endpoint_event_id"] for event in pilot.endpoint_schedule(value)}:
            raise ValueError("Revision-gain live adapter endpoint event is not scheduled")
        if target_root is None or target_manifest_path is None:
            raise ValueError("Revision-gain live adapter endpoints require the frozen ten-target manifest")
        return
    raise ValueError("Revision-gain live adapter phase is unsupported")


def prepare_one(*, run_root: Path, source_root: Path, phase: str, event_id: str, acknowledgement_sha256: str, queue_root: Path = DEFAULT_QUEUE_ROOT, lineage_records: list[Mapping[str, Any]] | None = None, feedback_receipt_path: Path | None = None, completed_feedback_receipt_paths: list[Path] | None = None, target_root: Path | None = None, target_manifest_path: Path | None = None) -> dict[str, Any]:
    pilot = _pilot()
    run_root = Path(run_root)
    if acknowledgement_sha256 != contract()["authorized_acknowledgement_sha256"]:
        raise ValueError("Revision-gain live adapter acknowledgement is not the frozen authorized hash")
    _phase_dependencies(pilot, phase=phase, event_id=event_id, lineage_records=lineage_records, feedback_receipt_path=feedback_receipt_path, completed_feedback_receipt_paths=completed_feedback_receipt_paths, target_root=target_root, target_manifest_path=target_manifest_path)
    _broker_instance, _route, proof = _governed_route(pilot, queue_root=Path(queue_root), phase=phase, event_id=event_id)
    root = _cell_root(run_root, phase, event_id)
    prepared = pilot.prepare_cell(work_root=run_root, prepared_root=root, phase=phase, event_id=event_id, acknowledgement_sha256=acknowledgement_sha256, source_root=Path(source_root) if phase != "blind_endpoint_judgment" else None, revision_records=lineage_records, feedback_receipt_path=feedback_receipt_path, target_root=target_root, target_manifest_path=target_manifest_path)
    if prepared["provider_calls_made"] != 0 or prepared["process_launches"] != 0:
        raise ValueError("Revision-gain live adapter preparation contacted a provider")
    route_binding = _persist_route_proof(run_root=run_root, root=root, proof=proof)
    admission = {"format_version": 1, "study_id": STUDY_ID, "kind": "provider_free_prepared_cell", "pilot_commit": contract()["pilot"]["commit"], "phase": phase, "event_id": event_id, "authorized_acknowledgement_sha256": acknowledgement_sha256, "route_evidence": route_binding, "prepared_root": str(root.resolve()), "prepared": prepared, "provider_calls_made": 0}
    _write_once(root / "live-admission.json", admission)
    return admission


def _read_admission(*, root: Path, phase: str, event_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    raw = _stable_bytes(root / "live-admission.json", label="live admission")
    value = json.loads(raw.decode("utf-8"))
    prepared_raw = _stable_bytes(root / "prepared-cell.json", label="prepared cell")
    prepared = json.loads(prepared_raw.decode("utf-8"))
    if not isinstance(value, Mapping):
        raise ValueError("Revision-gain live adapter admission is invalid")
    expected = {"format_version": 1, "study_id": STUDY_ID, "kind": "provider_free_prepared_cell", "pilot_commit": contract()["pilot"]["commit"], "phase": phase, "event_id": event_id, "authorized_acknowledgement_sha256": contract()["authorized_acknowledgement_sha256"], "route_evidence": value.get("route_evidence"), "prepared_root": str(root.resolve()), "prepared": prepared, "provider_calls_made": 0}
    if canonical(value) + b"\n" != raw or value != expected or prepared.get("acknowledgement_sha256") != value["authorized_acknowledgement_sha256"]:
        raise ValueError("Revision-gain live adapter admission or acknowledgement drifted")
    return dict(value), prepared


def _reauth_admission(*, pilot: ModuleType, run_root: Path, root: Path, phase: str, event_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    admission, prepared = _read_admission(root=root, phase=phase, event_id=event_id)
    binding = admission["route_evidence"]
    if not isinstance(binding, Mapping) or set(binding) != {"path", "bytes", "sha256"}:
        raise ValueError("Revision-gain live adapter route evidence binding is invalid")
    _reauth_route(pilot=pilot, run_root=run_root, phase=phase, event_id=event_id, binding=binding)
    return admission, prepared


def _build_invocation(*, broker: Any, root: Path, prepared: Mapping[str, Any], route: Mapping[str, Any]) -> tuple[list[str], bytes, int]:
    payload = _stable_bytes(root / prepared["payload"]["path"], label="outbound payload")
    try:
        decoded = payload.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError("Revision-gain live adapter payload is not UTF-8") from error
    pilot = _pilot()
    if prepared["phase"] == "cwr_feedback":
        response_schema = json.loads(pilot._asset("cwr-feedback.schema.json", pilot.contract()["assets"]["cwr-feedback.schema.json"]).decode("utf-8"))
    elif prepared["phase"] == "blind_endpoint_judgment":
        response_schema = json.loads(pilot._asset("score.schema.json", pilot.contract()["assets"]["score.schema.json"]).decode("utf-8"))
    else:
        response_schema = {"$schema_version": 1, "type": "object", "additionalProperties": False,
                           "properties": {"story": {"type": "string"}}, "required": ["story"]}
    if route["adapter"] == "codex_exec":
        argv = ["--codex-command-json", canonical(route["codex_command"]).decode(), "--model", route["model"], "--reasoning-effort", route["reasoning_effort"], "--output-schema-json", canonical(response_schema).decode(), "--expected-command-identity-json", canonical(route["codex_command_identity"]).decode(), "--cli-version-command-json", canonical(route["cli_version_command"]).decode(), "--expected-cli-version-identity-json", canonical(route["cli_version_identity"]).decode(), "--expected-cli-version", route["codex_cli_version"], "--auth-status-command-json", canonical(route["auth_status_command"]).decode(), "--expected-auth-status-identity-json", canonical(route["auth_status_identity"]).decode(), "--auth-receipt-json", canonical(broker._load_json_artifact(route["auth_receipt_hash"])).decode(), "--broker-root", str(broker.root), "--timeout-seconds", str(route["timeout_seconds"])]
    else:
        argv = ["--grok-command-json", canonical(route["grok_command"]).decode(), "--model", route["model"], "--reported-model", route["reported_model"], "--reasoning-effort", route["reasoning_effort"], "--output-schema-json", canonical(response_schema).decode(), "--expected-command-identity-json", canonical(route["grok_command_identity"]).decode(), "--cli-version-command-json", canonical(route["cli_version_command"]).decode(), "--expected-cli-version-identity-json", canonical(route["cli_version_identity"]).decode(), "--expected-cli-version", route["grok_cli_version"], "--subscription-receipt-json", canonical(broker._load_json_artifact(route["subscription_receipt_hash"])).decode(), "--broker-root", str(broker.root), "--timeout-seconds", str(route["timeout_seconds"]), "--nonvisual-max-turns", str(route["nonvisual_max_turns"])]
    return [*route["command"], *argv], canonical({"prompt": decoded}), int(route["timeout_seconds"])


def _control_from_adapter(control_raw: bytes) -> tuple[str, Mapping[str, Any] | None]:
    try:
        envelope = json.loads(control_raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("Revision-gain live adapter adapter control envelope is invalid") from error
    if canonical(envelope) + b"\n" != control_raw.rstrip(b"\r\n") + b"\n" or not isinstance(envelope, Mapping):
        raise ValueError("Revision-gain live adapter adapter control envelope is not canonical")
    control = envelope.get("control")
    if not isinstance(control, Mapping) or control.get("version") != 1 or control.get("state") not in {"completed", "definitely_not_contacted", "ambiguous"}:
        raise ValueError("Revision-gain live adapter adapter control completion drifted")
    state = control["state"]
    if state != "completed":
        if set(envelope) != {"control"} or set(control) != {"version", "state", "detail"} or not isinstance(control["detail"], str):
            raise ValueError("Revision-gain live adapter adapter failure control drifted")
        return state, None
    result = envelope.get("result")
    if set(envelope) != {"control", "result"} or control != {"version": 1, "state": "completed"} or not isinstance(result, Mapping) or set(result) != {"schema_version", "request_hash", "output", "output_hash", "runtime"}:
        raise ValueError("Revision-gain live adapter adapter completion result drifted")
    return state, result


def _receipt_from_control(*, pilot: ModuleType, root: Path, prepared: Mapping[str, Any], control_raw: bytes) -> dict[str, Any]:
    state, result = _control_from_adapter(control_raw)
    if state != "completed" or result is None:
        raise ValueError("Revision-gain live adapter completed control is required for receipt ingestion")
    payload = _stable_bytes(root / prepared["payload"]["path"], label="outbound payload")
    request = {"prompt": payload.decode("utf-8")}
    runtime, response = result["runtime"], result["output"]
    route_proof = json.loads(_stable_bytes(root / "governed-route-proof.json", label="governed route proof").decode("utf-8"))
    if result["schema_version"] != 1 or result["request_hash"] != _sha256(canonical(request)) or not isinstance(response, Mapping) or result["output_hash"] != _sha256(canonical(response)) or not isinstance(runtime, Mapping):
        raise ValueError("Revision-gain live adapter adapter result binding drifted")
    if prepared["provider_model"] == "grok-4.6":
        required = {"adapter_version", "requested_model", "reported_model", "requested_reasoning_effort", "reasoning_attested", "reasoning_attestation", "identity_evidence", "cli_version", "session_id_hash", "request_id_hash", "observed_turns", "envelope_hash", "command_identity", "command_identity_hash", "subscription_receipt_hash", "execution_policy", "usage_telemetry", "nonvisual_max_turns"}
        if set(runtime) != required or runtime["adapter_version"] != 1 or runtime["requested_model"] != prepared["provider_model"] or runtime["reported_model"] != GROK_REPORTED_MODEL or runtime["requested_reasoning_effort"] != prepared["reasoning"] or runtime["reasoning_attested"] is not False or runtime["identity_evidence"] != "requested_only" or runtime["observed_turns"] != 1 or runtime["nonvisual_max_turns"] != 1 or any(not isinstance(runtime[key], str) or not re.fullmatch(r"[0-9a-f]{64}", runtime[key]) for key in ("session_id_hash", "request_id_hash", "envelope_hash", "command_identity_hash", "subscription_receipt_hash")) or runtime["request_id_hash"] == runtime["session_id_hash"] or runtime["subscription_receipt_hash"] != route_proof.get("route_receipt_sha256") or runtime["command_identity_hash"] != route_proof.get("expected_adapter_runtime_identity_sha256"):
            raise ValueError("Revision-gain live adapter Grok completion identity drifted")
        request_id, session_id = f"grok-request-sha256:{runtime['request_id_hash']}", f"grok-session-sha256:{runtime['session_id_hash']}"
    else:
        raise ValueError("Revision-gain live adapter Codex completion lacks independent native request/session identity")
    prepared_raw = _stable_bytes(root / "prepared-cell.json", label="prepared cell")
    intent_raw = _stable_bytes(root / "launch-intent.json", label="launch intent")
    return {"prepared_record_sha256": _sha256(prepared_raw), "launch_intent_sha256": _sha256(intent_raw), "frozen_manifest_sha256": prepared["frozen_manifest_sha256"], "provider_request_id": request_id, "session_id": session_id, "status": 200, "provider_model": prepared["provider_model"], "reasoning": prepared["reasoning"], "tools_enabled": False, "transmitted_payload_sha256": prepared["payload"]["sha256"], "returned_response_sha256": _sha256(pilot.canonical(response)), "response": dict(response)}


def _sol_lifecycle_verified(*, pilot: ModuleType, root: Path, prepared: Mapping[str, Any], control_raw: bytes) -> dict[str, Any]:
    state, result = _control_from_adapter(control_raw)
    if state != "completed" or result is None:
        raise ValueError("Revision-gain live adapter completed Sol lifecycle is required")
    payload = _stable_bytes(root / prepared["payload"]["path"], label="outbound payload")
    request = {"prompt": payload.decode("utf-8")}
    runtime, response = result["runtime"], result["output"]
    route_proof = json.loads(_stable_bytes(root / "governed-route-proof.json", label="governed route proof").decode("utf-8"))
    required = {"adapter_version", "requested_model", "requested_reasoning_effort", "identity_evidence", "cli_version", "events_hash", "event_projection", "raw_output_hash", "command_identity", "auth_receipt_hash", "command_identity_hash"}
    if (result["schema_version"] != 1 or result["request_hash"] != _sha256(canonical(request))
            or not isinstance(response, Mapping) or result["output_hash"] != _sha256(canonical(response))
            or not isinstance(runtime, Mapping) or set(runtime) != required
            or runtime["adapter_version"] != 1 or runtime["requested_model"] != "gpt-5.6-sol"
            or runtime["requested_reasoning_effort"] != prepared["reasoning"] or runtime["identity_evidence"] != "requested_only"
            or any(not isinstance(runtime[key], str) or not re.fullmatch(r"[0-9a-f]{64}", runtime[key]) for key in ("events_hash", "raw_output_hash", "auth_receipt_hash", "command_identity_hash"))
            or not isinstance(runtime["event_projection"], Mapping) or not isinstance(runtime["event_projection"].get("thread_id"), str)
            or runtime["auth_receipt_hash"] != route_proof.get("route_receipt_sha256")
            or runtime["command_identity_hash"] != route_proof.get("expected_adapter_runtime_identity_sha256")):
        raise ValueError("Revision-gain live adapter Sol local lifecycle identity drifted")
    pilot._validate_current_prepared(prepared_root=root, prepared=prepared)
    pilot._validate_response_schema(prepared, response)
    prepared_raw = _stable_bytes(root / "prepared-cell.json", label="prepared cell")
    intent_raw = _stable_bytes(root / "launch-intent.json", label="launch intent")
    return {
        "format_version": 1, "study_id": STUDY_ID, "kind": "verified_local_codex_lifecycle_receipt",
        "evidence_class": "sol_local_codex_lifecycle_native_endpoint_cardinality_unproven_v1",
        "prepared_root": str(root.resolve()), "event_id": prepared["event_id"], "phase": prepared["phase"],
        "prepared_record_sha256": _sha256(prepared_raw), "launch_intent_sha256": _sha256(intent_raw),
        "frozen_manifest_sha256": prepared["frozen_manifest_sha256"], "provider_model": prepared["provider_model"],
        "reasoning": prepared["reasoning"], "tools_enabled": False, "payload_sha256": prepared["payload"]["sha256"],
        "response_sha256": _sha256(canonical(response)), "response": dict(response),
        "local_lifecycle": {"events_hash": runtime["events_hash"], "raw_output_hash": runtime["raw_output_hash"],
                            "thread_id_sha256": _sha256(runtime["event_projection"]["thread_id"].encode("utf-8")),
                            "command_identity_hash": runtime["command_identity_hash"], "auth_receipt_hash": runtime["auth_receipt_hash"],
                            "native_endpoint_contact_cardinality": "unproven"},
    }


def _receipt_authority_path(root: Path) -> Path:
    candidates = [root / "verified-receipt.json", root / "reconciled-verified-receipt.json"]
    present = [path for path in candidates if path.exists()]
    if len(present) != 1:
        raise ValueError("Revision-gain live adapter requires exactly one verified receipt authority")
    return present[0]


def _validate_receipt_authority_state(*, root: Path, authority_path: Path) -> None:
    prepared_raw = _stable_bytes(root / "prepared-cell.json", label="prepared cell")
    intent_raw = _stable_bytes(root / "launch-intent.json", label="launch intent")
    prepared = json.loads(prepared_raw.decode("utf-8"))
    intent = json.loads(intent_raw.decode("utf-8"))
    expected_intent = {"format_version": 1, "study_id": PILOT_STUDY_ID, "kind": "one_launch_intent",
                       "prepared_record_sha256": _sha256(prepared_raw), "process_launches": 1, "no_resend": True}
    if canonical(prepared) + b"\n" != prepared_raw or canonical(intent) + b"\n" != intent_raw or intent != expected_intent:
        raise ValueError("Revision-gain live adapter receipt authority launch lineage drifted")
    terminal_path = root / "terminal-outcome.json"
    reconciliation_path = root / "reconciliation.json"
    if authority_path.name == "verified-receipt.json":
        if terminal_path.exists() or reconciliation_path.exists():
            raise ValueError("Revision-gain live adapter original receipt cannot carry reconciliation state")
        return
    terminal_raw = _stable_bytes(terminal_path, label="terminal outcome")
    reconciliation_raw = _stable_bytes(reconciliation_path, label="postlaunch reconciliation")
    terminal = json.loads(terminal_raw.decode("utf-8"))
    reconciliation = json.loads(reconciliation_raw.decode("utf-8"))
    expected_terminal = {"state": "terminal_postlaunch_reconcile_required", "fresh_output_root_required": False, "no_resend": True}
    expected_reconciliation = {"format_version": 1, "study_id": PILOT_STUDY_ID,
                               "kind": "postlaunch_receipt_reconciliation",
                               "prepared_record_sha256": _sha256(prepared_raw),
                               "launch_intent_sha256": _sha256(intent_raw),
                               "terminal_outcome_sha256": _sha256(terminal_raw),
                               "acknowledgement_sha256": reconciliation.get("acknowledgement_sha256"),
                               "action": "accept_settled_native_receipt_without_resend"}
    acknowledgement = reconciliation.get("acknowledgement_sha256")
    if (canonical(terminal) + b"\n" != terminal_raw or terminal != expected_terminal
            or canonical(reconciliation) + b"\n" != reconciliation_raw or reconciliation != expected_reconciliation
            or not isinstance(acknowledgement, str) or not re.fullmatch(r"[0-9a-f]{64}", acknowledgement)):
        raise ValueError("Revision-gain live adapter reconciled receipt authority is unauthenticated")
    control_raw = _stable_bytes(root / "adapter-control.json", label="adapter control")
    state, _ = _control_from_adapter(control_raw)
    if state != "completed":
        raise ValueError("Revision-gain live adapter reconciled receipt lacks a completed persisted control")
def _read_receipt_authority(pilot: ModuleType, *, root: Path, event_id: str, phase: str) -> tuple[Path, dict[str, Any]]:
    path = _receipt_authority_path(root)
    _validate_receipt_authority_state(root=root, authority_path=path)
    raw = _stable_bytes(path, label="verified receipt authority")
    value = json.loads(raw.decode("utf-8"))
    if canonical(value) + b"\n" != raw or value.get("event_id") != event_id or value.get("phase") != phase:
        raise ValueError("Revision-gain live adapter receipt authority binding drifted")
    if value.get("kind") == "verified_native_receipt":
        verified = pilot._native_read_verified_receipt(path, expected_event_id=event_id, expected_phase=phase)
        native = verified.get("native_receipt", {})
        if not str(native.get("provider_request_id", "")).startswith("grok-request-sha256:") or not str(native.get("session_id", "")).startswith("grok-session-sha256:"):
            raise ValueError("Revision-gain live adapter Grok receipt lacks native request/session authority")
        if native["provider_request_id"].split(":", 1)[1] == native["session_id"].split(":", 1)[1]:
            raise ValueError("Revision-gain live adapter Grok request and session identities are not distinct")
        return path, verified
    if value.get("kind") != "verified_local_codex_lifecycle_receipt" or value.get("evidence_class") != "sol_local_codex_lifecycle_native_endpoint_cardinality_unproven_v1":
        raise ValueError("Revision-gain live adapter receipt evidence class is unsupported")
    prepared = json.loads(_stable_bytes(root / "prepared-cell.json", label="prepared cell").decode("utf-8"))
    expected = _sol_lifecycle_verified(pilot=pilot, root=root, prepared=prepared, control_raw=_stable_bytes(root / "adapter-control.json", label="adapter control"))
    if expected != value:
        raise ValueError("Revision-gain live adapter Sol local lifecycle replay authentication failed")
    return path, value


def _precontact_terminal(*, pilot: ModuleType, root: Path, phase: str, event_id: str, error: Exception) -> dict[str, Any]:
    outcome = pilot.record_terminal_outcome(prepared_root=root, process_launches=0, settled=False)
    return {"study_id": STUDY_ID, "phase": phase, "event_id": event_id, "state": outcome["state"], "provider_calls_made": 0, "process_launches": 0, "native_contacts": 0, "error_type": type(error).__name__, "error": str(error)}


def execute_one(*, run_root: Path, phase: str, event_id: str, allow_remote: bool) -> dict[str, Any]:
    if allow_remote is not True:
        raise ValueError("Revision-gain live adapter requires explicit allow_remote=True")
    pilot = _pilot()
    run_root = Path(run_root)
    root = _cell_root(run_root, phase, event_id)
    try:
        admission, prepared = _reauth_admission(pilot=pilot, run_root=run_root, root=root, phase=phase, event_id=event_id)
        route_binding = admission["route_evidence"]
        broker, route = _reauth_route(pilot=pilot, run_root=run_root, phase=phase, event_id=event_id, binding=route_binding)
        command, stdin, timeout_seconds = _build_invocation(broker=broker, root=root, prepared=prepared, route=route)
        pilot.begin_one_launch(prepared_root=root)
    except Exception as error:
        if (root / "launch-intent.json").exists():
            raise
        return _precontact_terminal(pilot=pilot, root=root, phase=phase, event_id=event_id, error=error)
    try:
        completed = _SUBPROCESS_RUN(command, input=stdin, capture_output=True, check=False, timeout=timeout_seconds)
        if completed.returncode != 0:
            raise ValueError("Revision-gain live adapter subprocess did not settle")
        control_state, _ = _control_from_adapter(completed.stdout)
        _write_control_once(root / "adapter-control.json", completed.stdout)
        if control_state != "completed":
            outcome = pilot.record_terminal_outcome(prepared_root=root, process_launches=1, settled=False)
            return {"study_id": STUDY_ID, "phase": phase, "event_id": event_id, "state": outcome["state"], "provider_calls_made": 0 if control_state == "definitely_not_contacted" else "unproven", "process_launches": 1, "native_contact_state": control_state, "native_contacts": 0 if control_state == "definitely_not_contacted" else "unproven"}
        receipt_path = root / "verified-receipt.json"
        if prepared["provider_model"] == "grok-4.6":
            native = _receipt_from_control(pilot=pilot, root=root, prepared=prepared, control_raw=completed.stdout)
            pilot.validate_receipt(prepared_root=root, receipt=native, output_path=receipt_path)
            evidence_class, native_contacts = "grok_native_request_session_exact_one_contact_v1", 1
        else:
            _write_once(receipt_path, _sol_lifecycle_verified(pilot=pilot, root=root, prepared=prepared, control_raw=completed.stdout))
            evidence_class, native_contacts = "sol_local_codex_lifecycle_native_endpoint_cardinality_unproven_v1", "unproven"
    except Exception as error:
        outcome = pilot.record_terminal_outcome(prepared_root=root, process_launches=1, settled=False)
        return {"study_id": STUDY_ID, "phase": phase, "event_id": event_id, "state": outcome["state"], "provider_calls_made": "unproven", "process_launches": 1, "native_contact_state": "unproven", "native_contacts": "unproven", "error_type": type(error).__name__, "error": str(error)}
    result = {"format_version": 1, "study_id": STUDY_ID, "kind": "one_endpoint_attempt_result", "phase": phase, "event_id": event_id, "state": "settled", "evidence_class": evidence_class, "provider_calls_made": native_contacts, "process_launches": 1, "native_contacts": native_contacts, "admission_sha256": _sha256(_stable_bytes(root / "live-admission.json", label="live admission")), "route_evidence_sha256": admission["route_evidence"]["sha256"], "adapter_control": _commitment(run_root, root / "adapter-control.json"), "verified_receipt": _commitment(run_root, receipt_path)}
    _write_once(root / "execution-result.json", result)
    return result


def reconcile_existing_receipt(*, run_root: Path, phase: str, event_id: str, reconciliation_acknowledgement_sha256: str) -> dict[str, Any]:
    """Validate an already-returned native receipt after explicit reconciliation; never launches or dispatches."""
    pilot = _pilot()
    root = _cell_root(Path(run_root), phase, event_id)
    _read_admission(root=root, phase=phase, event_id=event_id)
    prepared = json.loads(_stable_bytes(root / "prepared-cell.json", label="prepared cell").decode("utf-8"))
    control_raw = _stable_bytes(root / "adapter-control.json", label="persisted adapter control")
    output = root / "reconciled-verified-receipt.json"
    if (root / "verified-receipt.json").exists() or output.exists():
        raise ValueError("Revision-gain live adapter reconciliation cannot duplicate or remint receipt authority")
    pilot.reconcile_postlaunch(prepared_root=root, acknowledgement_sha256=reconciliation_acknowledgement_sha256)
    if prepared["provider_model"] == "grok-4.6":
        native_receipt = _receipt_from_control(pilot=pilot, root=root, prepared=prepared, control_raw=control_raw)
        verified = pilot.validate_receipt(prepared_root=root, receipt=native_receipt, output_path=output)
        authority = verified["provider_request_id"]
    else:
        verified = _sol_lifecycle_verified(pilot=pilot, root=root, prepared=prepared, control_raw=control_raw)
        _write_once(output, verified)
        authority = verified["local_lifecycle"]["thread_id_sha256"]
    return {"study_id": STUDY_ID, "kind": "reconciliation_only_receipt_ingest", "phase": phase, "event_id": event_id, "provider_calls_made": 0, "process_launches": 0, "adapter_control": _commitment(Path(run_root), root / "adapter-control.json"), "verified_receipt": _commitment(Path(run_root), output), "receipt_authority": authority}


def ingest_revision(*, run_root: Path, event_id: str, lineage_records: list[Mapping[str, Any]], feedback_receipt_path: Path | None = None) -> dict[str, Any]:
    pilot = _pilot()
    root = _cell_root(Path(run_root), "revision_generation", event_id)
    verified_path, verified = _read_receipt_authority(pilot, root=root, event_id=event_id, phase="revision_generation")
    event = next(row for row in pilot.revision_schedule() if row["event_id"] == event_id)
    descendant = Path(run_root) / "descendants" / f"{event_id}.md"
    descendant.parent.mkdir(parents=True, exist_ok=True)
    with descendant.open("xb") as handle:
        handle.write(verified["response"]["story"].encode("utf-8"))
    source = pilot.contract()["sources"]["items"][event["source_item_id"]]
    prior = {row["event_id"]: row for row in lineage_records}
    parent = None if event["parent_event_id"] is None else {"event_id": event["parent_event_id"], "descendant": prior[event["parent_event_id"]]["descendant"]}
    if event["guidance_arm"] == "generic_no_feedback":
        feedback = None
    else:
        feedback_root = _cell_root(Path(run_root), "cwr_feedback", event["cwr_feedback_event_id"])
        authority_path, _ = _read_receipt_authority(pilot, root=feedback_root, event_id=event["cwr_feedback_event_id"], phase="cwr_feedback")
        if Path(feedback_receipt_path).resolve() != authority_path.resolve():
            raise ValueError("Revision-gain live adapter feedback must use the sole receipt authority")
        feedback = {"event_id": event["cwr_feedback_event_id"], "verified_receipt": _commitment(Path(run_root), authority_path)}
    record = {"event_id": event_id, "source": {"item_id": event["source_item_id"], "source.md": source["source.md"], "prompt.md": source["prompt.md"]}, "parent": parent, "descendant": _commitment(Path(run_root), descendant), "generator": {"model": "grok-4.6", "reasoning": "high", "tools_enabled": False}, "generator_receipt": _commitment(Path(run_root), verified_path), "cwr_feedback": feedback}
    _write_once(root / "revision-record.json", record)
    return record


def ingest_feedback(*, run_root: Path, event_id: str) -> dict[str, Any]:
    pilot = _pilot()
    root = _cell_root(Path(run_root), "cwr_feedback", event_id)
    authority_path, verified = _read_receipt_authority(pilot, root=root, event_id=event_id, phase="cwr_feedback")
    record = {"format_version": 1, "study_id": STUDY_ID, "kind": "ingested_sol_feedback", "event_id": event_id, "verified_receipt": _commitment(Path(run_root), authority_path), "provider_model": verified["provider_model"], "reasoning": verified["reasoning"], "tools_enabled": False, "evidence_class": verified.get("evidence_class", "grok_native_request_session_exact_one_contact_v1"), "native_endpoint_contact_cardinality": verified.get("local_lifecycle", {}).get("native_endpoint_contact_cardinality", 1)}
    _write_once(root / "feedback-ingest.json", record)
    return record


def ingest_endpoint(*, run_root: Path, event_id: str) -> dict[str, Any]:
    pilot = _pilot()
    root = _cell_root(Path(run_root), "blind_endpoint_judgment", event_id)
    authority_path, verified = _read_receipt_authority(pilot, root=root, event_id=event_id, phase="blind_endpoint_judgment")
    record = {"format_version": 1, "study_id": STUDY_ID, "kind": "ingested_blind_endpoint", "event_id": event_id, "verified_receipt": _commitment(Path(run_root), authority_path), "provider_model": verified["provider_model"], "reasoning": verified["reasoning"], "tools_enabled": False, "evidence_class": verified.get("evidence_class", "grok_native_request_session_exact_one_contact_v1"), "native_endpoint_contact_cardinality": verified.get("local_lifecycle", {}).get("native_endpoint_contact_cardinality", 1)}
    _write_once(root / "endpoint-ingest.json", record)
    return record


def freeze_targets(*, run_root: Path, source_root: Path, lineage_records: list[Mapping[str, Any]], target_root: Path) -> dict[str, Any]:
    return _pilot().prepare_targets(work_root=Path(run_root), target_root=Path(target_root), source_root=Path(source_root), revision_records=lineage_records)


def project(*, endpoint_receipt_paths: list[Path]) -> dict[str, Any]:
    pilot = _pilot()
    value = pilot.contract()
    schedule = {row["endpoint_event_id"]: row for row in pilot.endpoint_schedule(value)}
    if len(endpoint_receipt_paths) != len(schedule):
        raise ValueError("Revision-gain live adapter mixed endpoint evidence is incomplete")
    observed: dict[str, int] = {}
    evidence_by_judge: dict[str, dict[str, Any]] = {}
    for supplied in endpoint_receipt_paths:
        supplied = Path(supplied)
        raw = _stable_bytes(supplied, label="persisted mixed endpoint receipt")
        receipt = json.loads(raw.decode("utf-8"))
        event_id = receipt.get("event_id") if isinstance(receipt, Mapping) else None
        event = schedule.get(event_id)
        if event is None or event_id in observed:
            raise ValueError("Revision-gain live adapter endpoint evidence is unscheduled or duplicated")
        authority_path, verified = _read_receipt_authority(
            pilot, root=supplied.parent, event_id=event_id, phase="blind_endpoint_judgment"
        )
        if authority_path.resolve() != supplied.resolve():
            raise ValueError("Revision-gain live adapter projection must use the sole endpoint receipt authority")
        expected = value["routes"]["judges"][event["judge_route_id"]]
        response = verified.get("response")
        score = response.get("overall") if isinstance(response, Mapping) else None
        limits = (1, 7) if event["measure_id"] == "holistic" else (1, 5)
        if (verified.get("provider_model") != expected["model"] or verified.get("reasoning") != expected["reasoning"]
                or verified.get("tools_enabled") is not False or not isinstance(score, int) or isinstance(score, bool)
                or not limits[0] <= score <= limits[1]):
            raise ValueError("Revision-gain live adapter endpoint identity or score drifted")
        if expected["model"] == "grok-4.6":
            evidence = {"evidence_class": "grok_native_request_session_exact_one_contact_v1",
                        "native_endpoint_contact_cardinality": 1}
        else:
            if verified.get("evidence_class") != "sol_local_codex_lifecycle_native_endpoint_cardinality_unproven_v1":
                raise ValueError("Revision-gain live adapter Sol endpoint evidence ceiling drifted")
            evidence = {"evidence_class": verified["evidence_class"],
                        "native_endpoint_contact_cardinality": "unproven"}
        previous = evidence_by_judge.setdefault(event["judge_route_id"], evidence)
        if previous != evidence:
            raise ValueError("Revision-gain live adapter endpoint evidence class changed within a judge")
        observed[event_id] = score

    target_by_event = {row["target_event_id"]: row["blind_target_id"] for row in pilot.targets(value) if row["target_event_id"]}
    primary: list[dict[str, Any]] = []
    for revision in pilot.revision_schedule(value):
        if revision["guidance_arm"] != "cwr_guided":
            continue
        control = pilot._revision_id(revision["cycle"], revision["source_item_id"], "generic_no_feedback")
        for judge in value["routes"]["judges"]:
            for measure in ("holistic", "compact"):
                guided_id = f"endpoint-v2-{target_by_event[revision['event_id']]}-{measure}-{judge}"
                control_id = f"endpoint-v2-{target_by_event[control]}-{measure}-{judge}"
                primary.append({"source_item_id": revision["source_item_id"], "cycle": revision["cycle"],
                                "generator_id": "grok-4.6", "judge_route_id": judge, "measure_id": measure,
                                "guided_event_id": revision["event_id"], "control_event_id": control,
                                "guided_minus_control": observed[guided_id] - observed[control_id],
                                **evidence_by_judge[judge]})
    summaries = []
    for judge in value["routes"]["judges"]:
        for measure in ("holistic", "compact"):
            scores = [row["guided_minus_control"] for row in primary if row["judge_route_id"] == judge and row["measure_id"] == measure]
            summaries.append({"judge_route_id": judge, "measure_id": measure, "sample_count": len(scores),
                              "mean_guided_minus_control": sum(scores) / len(scores),
                              "positive": sum(score > 0 for score in scores), "zero": sum(score == 0 for score in scores),
                              "negative": sum(score < 0 for score in scores), **evidence_by_judge[judge]})
    baselines = {row["source_item_id"]: row["blind_target_id"] for row in pilot.targets(value) if row["kind"] == "source_baseline"}
    versus_baseline = []
    for revision in pilot.revision_schedule(value):
        target = target_by_event[revision["event_id"]]
        for judge in value["routes"]["judges"]:
            for measure in ("holistic", "compact"):
                endpoint_id = f"endpoint-v2-{target}-{measure}-{judge}"
                baseline_id = f"endpoint-v2-{baselines[revision['source_item_id']]}-{measure}-{judge}"
                versus_baseline.append({"source_item_id": revision["source_item_id"], "cycle": revision["cycle"],
                                        "guidance_arm": revision["guidance_arm"], "judge_route_id": judge,
                                        "measure_id": measure, "event_id": revision["event_id"],
                                        "baseline_target_id": baselines[revision["source_item_id"]],
                                        "arm_minus_baseline": observed[endpoint_id] - observed[baseline_id],
                                        **evidence_by_judge[judge]})
    evidence_summary = [{"judge_route_id": judge, "endpoint_count": sum(row["judge_route_id"] == judge for row in schedule.values()),
                         **evidence_by_judge[judge]} for judge in value["routes"]["judges"]]
    return {"study_id": STUDY_ID, "kind": "independently_recomputed_mixed_endpoint_projection",
            "endpoint_results_are_not_pooled": True, "paired_payloads": "unchanged_blind_target_and_measure_within_each_judge_route",
            "endpoint_evidence": evidence_summary, "primary_guided_minus_control": primary,
            "arm_minus_baseline": versus_baseline, "summaries": summaries}
