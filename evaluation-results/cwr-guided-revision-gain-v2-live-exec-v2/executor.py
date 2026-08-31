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
STUDY_ID = "cwr-guided-revision-gain-v2-live-exec-v2"
PILOT_STUDY_ID = "cwr-guided-revision-gain-v2-lean-pilot"
PILOT_PATH = ROOT / "evaluation-results" / "cwr-guided-revision-gain-v2-lean-pilot" / "study.py"
V1_EXECUTOR_PATH = ROOT / "evaluation-results" / "cwr-guided-revision-gain-v2-live-exec-v1" / "executor.py"
QUEUE_TOOLS_ROOT = Path(r"C:\Users\Haile\.codex\tools")
DEFAULT_QUEUE_ROOT = Path(r"C:\Users\Haile\.codex\state\model-work-queue")
V1_TERMINAL_RUN_ROOT = Path(r"C:\Users\Haile\Documents\cwr-revision-gain-v2-live-run-9bb20be-20260830a")
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


def _write_bytes_once(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle:
        handle.write(raw)


def _adapter_envelope(raw: bytes) -> Mapping[str, Any]:
    if raw.startswith(b"\xef\xbb\xbf") or not raw.endswith((b"\n", b"\r\n")):
        raise ValueError("Revision-gain live adapter stdout is not exact shared-adapter serialization")
    newline = b"\r\n" if raw.endswith(b"\r\n") else b"\n"
    body = raw[:-len(newline)]
    try:
        envelope = json.loads(body.decode("ascii"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("Revision-gain live adapter stdout envelope is invalid") from error
    if not isinstance(envelope, Mapping) or json.dumps(envelope, sort_keys=True).encode("ascii") + newline != raw:
        raise ValueError("Revision-gain live adapter stdout is not exact shared-adapter serialization")
    return envelope


def _persist_raw_stream(root: Path, *, stream: str, raw: bytes) -> dict[str, Any]:
    if stream not in {"stdout", "stderr"} or not isinstance(raw, bytes):
        raise ValueError("Revision-gain live adapter raw subprocess stream is invalid")
    path = root / f"adapter-{stream}.raw"
    _write_bytes_once(path, raw)
    run_root = root.parent.parent.parent
    binding = _commitment(run_root, path)
    _write_once(root / f"adapter-{stream}-binding.json", {"format_version": 1, "study_id": STUDY_ID, "kind": f"exact_raw_adapter_{stream}", f"raw_{stream}": binding})
    return binding


def _persist_raw_stdout(root: Path, raw: bytes) -> dict[str, Any]:
    return _persist_raw_stream(root, stream="stdout", raw=raw)


def _persist_timeout_streams(root: Path, error: subprocess.TimeoutExpired) -> list[dict[str, Any]]:
    observed: list[dict[str, Any]] = []
    stdout = error.stdout if error.stdout is not None else error.output
    for stream, raw in (("stdout", stdout), ("stderr", error.stderr)):
        if raw is not None:
            observed.append({"stream": stream, "raw": _persist_raw_stream(root, stream=stream, raw=raw)})
    return observed


def _write_control_once(path: Path, raw: bytes) -> None:
    _write_once(path, _adapter_envelope(raw))


def _commitment(root: Path, path: Path) -> dict[str, Any]:
    raw = _stable_bytes(path, label="artifact")
    return {"path": path.relative_to(root).as_posix(), "bytes": len(raw), "sha256": _sha256(raw)}


PREDECESSOR_TERMINAL_CELLS = [
    {"event_id": "feedback-v2-revision-v2-c1-hanna-1035-grok-4.6-cwr_guided", "path": "live-cells/cwr_feedback/feedback-v2-revision-v2-c1-hanna-1035-grok-4.6-cwr_guided", "artifacts": {"governed-route-proof.json": {"bytes": 1239, "sha256": "3a0ff49172d5a431dca4aae527f64affec921413f9b608a6a22a17d7cf0f48cb"}, "launch-intent.json": {"bytes": 230, "sha256": "b800e8600310f4df3dc1557486936eac06a7e7faa4e4ed2a93fe0bd71e458c73"}, "live-admission.json": {"bytes": 1666, "sha256": "62f326057530098b403d233d2c7befbe0e9109594b9f878ac7a6572a140e79d5"}, "payload.json": {"bytes": 97499, "sha256": "9754aa28c3c64a38876b42220ce46502e590742d13dcf347aff083d62419a56a"}, "prepared-cell.json": {"bytes": 859, "sha256": "6499e71b7c8749e504d2dd6523dc2fcc02db93cf00411083c177028c118b62cc"}, "terminal-outcome.json": {"bytes": 103, "sha256": "23e631ec1c248f259b009b447bb300d7cc22eabc8c6c479904c7e6ae931b07a5"}}},
    {"event_id": "feedback-v2-revision-v2-c1-hanna-178-grok-4.6-cwr_guided", "path": "live-cells/cwr_feedback/feedback-v2-revision-v2-c1-hanna-178-grok-4.6-cwr_guided", "artifacts": {"governed-route-proof.json": {"bytes": 1239, "sha256": "874cfda080ce1df45f94e19475e7c63e08eb0803a2a0f45840be359b07a1e8ee"}, "launch-intent.json": {"bytes": 230, "sha256": "01a661e2faece6b812869528631824e0de528e76c8f321b6d0121ab4da1b1e9b"}, "live-admission.json": {"bytes": 1662, "sha256": "db5cbb752e52ef74406fb539afd6e63f1577d78bf30c5696e4c1bfe79186f88b"}, "payload.json": {"bytes": 97390, "sha256": "b6adaba6ec6f7b893b359ff5132ca576787ee103b2375c5329dfe7caeec556fd"}, "prepared-cell.json": {"bytes": 858, "sha256": "017a4ee4455d34d839fb258bc3f784a735167978bbff5b8d772de9e0c238d2ea"}, "terminal-outcome.json": {"bytes": 103, "sha256": "23e631ec1c248f259b009b447bb300d7cc22eabc8c6c479904c7e6ae931b07a5"}}},
]
PREDECESSOR_ABSENT_ARTIFACTS = ["adapter-control.json", "adapter-stdout.raw", "adapter-stdout-binding.json", "verified-receipt.json", "reconciled-verified-receipt.json", "execution-result.json"]


def _predecessor_contract() -> dict[str, Any]:
    return {"study_id": "cwr-guided-revision-gain-v2-live-exec-v1", "executor_sha256": "a210b45dc534c815e0a946e7d2db7f1b08ba200ff07aade2a2aa1b6c10262b6e", "terminal_run_root": str(V1_TERMINAL_RUN_ROOT), "terminal_cells": PREDECESSOR_TERMINAL_CELLS, "absent_artifacts": PREDECESSOR_ABSENT_ARTIFACTS, "state": "terminal_no_vote_unknown_contact", "reconcile_or_resend": False}


def _validate_predecessor_lineage(predecessor: Mapping[str, Any]) -> None:
    if predecessor != _predecessor_contract():
        raise ValueError("Revision-gain live v2 predecessor contract drifted")
    for cell in PREDECESSOR_TERMINAL_CELLS:
        root = V1_TERMINAL_RUN_ROOT / cell["path"]
        if not root.is_dir():
            raise ValueError("Revision-gain live v2 predecessor terminal root is missing")
        for name, expected in cell["artifacts"].items():
            raw = _stable_bytes(root / name, label="pinned v1 terminal artifact")
            if {"bytes": len(raw), "sha256": _sha256(raw)} != expected:
                raise ValueError("Revision-gain live v2 predecessor terminal artifact drifted")
        if any((root / name).exists() for name in PREDECESSOR_ABSENT_ARTIFACTS):
            raise ValueError("Revision-gain live v2 predecessor terminal cell acquired receipt evidence")


def contract() -> dict[str, Any]:
    raw = _stable_bytes(CONTRACT_PATH, label="contract")
    value = json.loads(raw.decode("utf-8"))
    expected = {"format_version": 1, "study_id": STUDY_ID, "pilot": {"commit": "37ba2cb0fb72fe9c1abcb05efc3d6f641c380cab", "path": "evaluation-results/cwr-guided-revision-gain-v2-lean-pilot/study.py", "bytes": 54847, "sha256": "727db4cee210f5930eecdde1654b0c89cc1756006393601eaa33e70cfd5a72cf"}, "predecessor": _predecessor_contract(), "authorized_acknowledgement_sha256": "2fb371ff82b37fe22d238a223fc030ad7a7bb9a10b672719da081470d25dbe78", "geometry": {"feedback": 4, "revisions": 8, "endpoints": 40, "contacts": 52}, "phases": ["cwr_feedback", "revision_generation", "blind_endpoint_judgment"], "provider_calls_made_by_prepare": 0, "dispatch": "explicit_allow_remote_one_launch_no_resend_fresh_successor_root"}
    if value != expected:
        raise ValueError("Revision-gain live adapter contract drifted")
    if _sha256(_stable_bytes(V1_EXECUTOR_PATH, label="pinned v1 executor")) != expected["predecessor"]["executor_sha256"]:
        raise ValueError("Revision-gain live adapter v1 predecessor pin drifted")
    _validate_predecessor_lineage(expected["predecessor"])
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


def _successor_event_id(run_root: Path, phase: str, event_id: str) -> str:
    token = canonical({"study_id": STUDY_ID, "run_root": str(Path(run_root).resolve()), "phase": phase, "pilot_event_id": event_id})
    return f"exec-v2-{_sha256(token)[:24]}"


def _prepare_outbound_payload(root: Path, *, run_root: Path, phase: str, event_id: str) -> dict[str, Any]:
    pilot_raw = _stable_bytes(root / "payload.json", label="pinned pilot payload")
    pilot_payload = json.loads(pilot_raw.decode("utf-8"))
    identity = {"study_id": STUDY_ID, "successor_event_id": _successor_event_id(run_root, phase, event_id), "logical_sample_id": _sha256(canonical({"study_id": STUDY_ID, "phase": phase, "event_id": event_id, "run_root": str(Path(run_root).resolve())}))}
    outbound = {"format_version": 1, "kind": "versioned_successor_outbound_payload", "identity": identity, "pilot_payload": pilot_payload}
    _write_once(root / "outbound-payload.json", outbound)
    return {"identity": identity, "payload": _commitment(run_root, root / "outbound-payload.json")}


def _read_outbound_payload(root: Path, *, run_root: Path, phase: str, event_id: str) -> tuple[dict[str, Any], bytes]:
    raw = _stable_bytes(root / "outbound-payload.json", label="versioned successor outbound payload")
    value = json.loads(raw.decode("utf-8"))
    pilot_payload = json.loads(_stable_bytes(root / "payload.json", label="pinned pilot payload").decode("utf-8"))
    identity = {"study_id": STUDY_ID, "successor_event_id": _successor_event_id(run_root, phase, event_id), "logical_sample_id": _sha256(canonical({"study_id": STUDY_ID, "phase": phase, "event_id": event_id, "run_root": str(Path(run_root).resolve())}))}
    expected = {"format_version": 1, "kind": "versioned_successor_outbound_payload", "identity": identity, "pilot_payload": pilot_payload}
    if canonical(value) + b"\n" != raw or value != expected:
        raise ValueError("Revision-gain live v2 outbound successor identity or payload drifted")
    return identity, raw


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
    if run_root.resolve() == V1_TERMINAL_RUN_ROOT.resolve():
        raise ValueError("Revision-gain live v2 refuses the immutable v1 terminal run root")
    if acknowledgement_sha256 != contract()["authorized_acknowledgement_sha256"]:
        raise ValueError("Revision-gain live adapter acknowledgement is not the frozen authorized hash")
    _phase_dependencies(pilot, phase=phase, event_id=event_id, lineage_records=lineage_records, feedback_receipt_path=feedback_receipt_path, completed_feedback_receipt_paths=completed_feedback_receipt_paths, target_root=target_root, target_manifest_path=target_manifest_path)
    _broker_instance, _route, proof = _governed_route(pilot, queue_root=Path(queue_root), phase=phase, event_id=event_id)
    root = _cell_root(run_root, phase, event_id)
    prepared = pilot.prepare_cell(work_root=run_root, prepared_root=root, phase=phase, event_id=event_id, acknowledgement_sha256=acknowledgement_sha256, source_root=Path(source_root) if phase != "blind_endpoint_judgment" else None, revision_records=lineage_records, feedback_receipt_path=feedback_receipt_path, target_root=target_root, target_manifest_path=target_manifest_path)
    if prepared["provider_calls_made"] != 0 or prepared["process_launches"] != 0:
        raise ValueError("Revision-gain live adapter preparation contacted a provider")
    route_binding = _persist_route_proof(run_root=run_root, root=root, proof=proof)
    outbound = _prepare_outbound_payload(root, run_root=run_root, phase=phase, event_id=event_id)
    admission = {"format_version": 1, "study_id": STUDY_ID, "kind": "provider_free_prepared_cell", "pilot_commit": contract()["pilot"]["commit"], "phase": phase, "event_id": event_id, "successor_event_id": outbound["identity"]["successor_event_id"], "logical_sample_id": outbound["identity"]["logical_sample_id"], "outbound_payload": outbound["payload"], "predecessor_terminal_lineage": contract()["predecessor"], "authorized_acknowledgement_sha256": acknowledgement_sha256, "route_evidence": route_binding, "prepared_root": str(root.resolve()), "prepared": prepared, "provider_calls_made": 0}
    _write_once(root / "live-admission.json", admission)
    return admission


def _read_admission(*, root: Path, phase: str, event_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    raw = _stable_bytes(root / "live-admission.json", label="live admission")
    value = json.loads(raw.decode("utf-8"))
    prepared_raw = _stable_bytes(root / "prepared-cell.json", label="prepared cell")
    prepared = json.loads(prepared_raw.decode("utf-8"))
    if not isinstance(value, Mapping):
        raise ValueError("Revision-gain live adapter admission is invalid")
    identity, _ = _read_outbound_payload(root, run_root=Path(prepared["work_root"]), phase=phase, event_id=event_id)
    expected = {"format_version": 1, "study_id": STUDY_ID, "kind": "provider_free_prepared_cell", "pilot_commit": contract()["pilot"]["commit"], "phase": phase, "event_id": event_id, "successor_event_id": identity["successor_event_id"], "logical_sample_id": identity["logical_sample_id"], "outbound_payload": _commitment(Path(prepared["work_root"]), root / "outbound-payload.json"), "predecessor_terminal_lineage": contract()["predecessor"], "authorized_acknowledgement_sha256": contract()["authorized_acknowledgement_sha256"], "route_evidence": value.get("route_evidence"), "prepared_root": str(root.resolve()), "prepared": prepared, "provider_calls_made": 0}
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
    payload = _read_outbound_payload(root, run_root=Path(prepared["work_root"]), phase=prepared["phase"], event_id=prepared["event_id"])[1]
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
    envelope = _adapter_envelope(control_raw)
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


def _stored_adapter_stdout(root: Path) -> bytes:
    raw = _stable_bytes(root / "adapter-stdout.raw", label="persisted raw adapter stdout")
    binding_raw = _stable_bytes(root / "adapter-stdout-binding.json", label="raw adapter stdout binding")
    binding = json.loads(binding_raw.decode("utf-8"))
    expected_binding = {"format_version": 1, "study_id": STUDY_ID, "kind": "exact_raw_adapter_stdout", "raw_stdout": _commitment(root.parent.parent.parent, root / "adapter-stdout.raw")}
    if canonical(binding) + b"\n" != binding_raw or binding != expected_binding:
        raise ValueError("Revision-gain live adapter raw stdout binding drifted")
    envelope = _adapter_envelope(raw)
    projection_raw = _stable_bytes(root / "adapter-control.json", label="canonical adapter control projection")
    try:
        projection = json.loads(projection_raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("Revision-gain live adapter control projection is invalid") from error
    if canonical(projection) + b"\n" != projection_raw or projection != envelope:
        raise ValueError("Revision-gain live adapter control projection drifted from raw stdout")
    return raw


def _receipt_from_control(*, pilot: ModuleType, root: Path, prepared: Mapping[str, Any], control_raw: bytes) -> dict[str, Any]:
    state, result = _control_from_adapter(control_raw)
    if state != "completed" or result is None:
        raise ValueError("Revision-gain live adapter completed control is required for receipt ingestion")
    payload = _read_outbound_payload(root, run_root=Path(prepared["work_root"]), phase=prepared["phase"], event_id=prepared["event_id"])[1]
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
    return {"prepared_record_sha256": _sha256(prepared_raw), "launch_intent_sha256": _sha256(intent_raw), "frozen_manifest_sha256": prepared["frozen_manifest_sha256"], "provider_request_id": request_id, "session_id": session_id, "status": 200, "provider_model": prepared["provider_model"], "reasoning": prepared["reasoning"], "tools_enabled": False, "transmitted_payload_sha256": _sha256(payload), "returned_response_sha256": _sha256(pilot.canonical(response)), "response": dict(response)}


def _write_grok_native_binding(*, root: Path, run_root: Path, native: Mapping[str, Any]) -> None:
    outbound = _commitment(run_root, root / "outbound-payload.json")
    value = {"format_version": 1, "study_id": STUDY_ID, "kind": "raw_rederived_grok_native_receipt", "outbound_payload": outbound, "native_receipt": dict(native)}
    path = root / "adapter-native-binding.json"
    if path.exists():
        raw = _stable_bytes(path, label="existing raw-rederived Grok receipt binding")
        if canonical(value) + b"\n" != raw:
            raise ValueError("Revision-gain live v2 existing Grok raw receipt binding drifted")
        return
    _write_once(path, value)


def _verify_grok_native_binding(*, pilot: ModuleType, root: Path, prepared: Mapping[str, Any], verified: Mapping[str, Any]) -> None:
    raw = _stable_bytes(root / "adapter-native-binding.json", label="raw-rederived Grok receipt binding")
    value = json.loads(raw.decode("utf-8"))
    actual = _receipt_from_control(pilot=pilot, root=root, prepared=prepared, control_raw=_stored_adapter_stdout(root))
    expected = {"format_version": 1, "study_id": STUDY_ID, "kind": "raw_rederived_grok_native_receipt", "outbound_payload": _commitment(Path(prepared["work_root"]), root / "outbound-payload.json"), "native_receipt": actual}
    normalized = dict(actual); normalized["transmitted_payload_sha256"] = prepared["payload"]["sha256"]
    if canonical(value) + b"\n" != raw or value != expected or verified.get("native_receipt") != normalized:
        raise ValueError("Revision-gain live v2 Grok receipt authority is not bound to raw stdout and successor payload")


def _sol_lifecycle_verified(*, pilot: ModuleType, root: Path, prepared: Mapping[str, Any], control_raw: bytes) -> dict[str, Any]:
    state, result = _control_from_adapter(control_raw)
    if state != "completed" or result is None:
        raise ValueError("Revision-gain live adapter completed Sol lifecycle is required")
    payload = _read_outbound_payload(root, run_root=Path(prepared["work_root"]), phase=prepared["phase"], event_id=prepared["event_id"])[1]
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
        "reasoning": prepared["reasoning"], "tools_enabled": False, "payload_sha256": _sha256(payload),
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
    control_raw = _stored_adapter_stdout(root)
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
        prepared = json.loads(_stable_bytes(root / "prepared-cell.json", label="prepared cell").decode("utf-8"))
        _verify_grok_native_binding(pilot=pilot, root=root, prepared=prepared, verified=verified)
        native = verified.get("native_receipt", {})
        if not str(native.get("provider_request_id", "")).startswith("grok-request-sha256:") or not str(native.get("session_id", "")).startswith("grok-session-sha256:"):
            raise ValueError("Revision-gain live adapter Grok receipt lacks native request/session authority")
        if native["provider_request_id"].split(":", 1)[1] == native["session_id"].split(":", 1)[1]:
            raise ValueError("Revision-gain live adapter Grok request and session identities are not distinct")
        return path, verified
    if value.get("kind") != "verified_local_codex_lifecycle_receipt" or value.get("evidence_class") != "sol_local_codex_lifecycle_native_endpoint_cardinality_unproven_v1":
        raise ValueError("Revision-gain live adapter receipt evidence class is unsupported")
    prepared = json.loads(_stable_bytes(root / "prepared-cell.json", label="prepared cell").decode("utf-8"))
    expected = _sol_lifecycle_verified(pilot=pilot, root=root, prepared=prepared, control_raw=_stored_adapter_stdout(root))
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
        raw_stdout = _persist_raw_stdout(root, completed.stdout)
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
            _write_grok_native_binding(root=root, run_root=run_root, native=native)
            normalized = dict(native); normalized["transmitted_payload_sha256"] = prepared["payload"]["sha256"]
            pilot.validate_receipt(prepared_root=root, receipt=normalized, output_path=receipt_path)
            evidence_class, native_contacts = "grok_native_request_session_exact_one_contact_v1", 1
        else:
            _write_once(receipt_path, _sol_lifecycle_verified(pilot=pilot, root=root, prepared=prepared, control_raw=completed.stdout))
            evidence_class, native_contacts = "sol_local_codex_lifecycle_native_endpoint_cardinality_unproven_v1", "unproven"
    except subprocess.TimeoutExpired as error:
        partial_streams = _persist_timeout_streams(root, error)
        outcome = pilot.record_terminal_outcome(prepared_root=root, process_launches=1, settled=False)
        return {"study_id": STUDY_ID, "phase": phase, "event_id": event_id, "state": outcome["state"], "provider_calls_made": "unproven", "process_launches": 1, "native_contact_state": "unproven", "native_contacts": "unproven", "partial_adapter_streams": partial_streams, "error_type": type(error).__name__, "error": str(error)}
    except Exception as error:
        outcome = pilot.record_terminal_outcome(prepared_root=root, process_launches=1, settled=False)
        return {"study_id": STUDY_ID, "phase": phase, "event_id": event_id, "state": outcome["state"], "provider_calls_made": "unproven", "process_launches": 1, "native_contact_state": "unproven", "native_contacts": "unproven", "error_type": type(error).__name__, "error": str(error)}
    result = {"format_version": 1, "study_id": STUDY_ID, "kind": "one_endpoint_attempt_result", "phase": phase, "event_id": event_id, "state": "settled", "evidence_class": evidence_class, "provider_calls_made": native_contacts, "process_launches": 1, "native_contacts": native_contacts, "admission_sha256": _sha256(_stable_bytes(root / "live-admission.json", label="live admission")), "route_evidence_sha256": admission["route_evidence"]["sha256"], "raw_adapter_stdout": raw_stdout, "adapter_control_projection": _commitment(run_root, root / "adapter-control.json"), "verified_receipt": _commitment(run_root, receipt_path)}
    _write_once(root / "execution-result.json", result)
    return result


def reconcile_existing_receipt(*, run_root: Path, phase: str, event_id: str, reconciliation_acknowledgement_sha256: str) -> dict[str, Any]:
    """Validate an already-returned native receipt after explicit reconciliation; never launches or dispatches."""
    pilot = _pilot()
    root = _cell_root(Path(run_root), phase, event_id)
    _read_admission(root=root, phase=phase, event_id=event_id)
    prepared = json.loads(_stable_bytes(root / "prepared-cell.json", label="prepared cell").decode("utf-8"))
    control_raw = _stored_adapter_stdout(root)
    output = root / "reconciled-verified-receipt.json"
    if (root / "verified-receipt.json").exists() or output.exists():
        raise ValueError("Revision-gain live adapter reconciliation cannot duplicate or remint receipt authority")
    pilot.reconcile_postlaunch(prepared_root=root, acknowledgement_sha256=reconciliation_acknowledgement_sha256)
    if prepared["provider_model"] == "grok-4.6":
        native_receipt = _receipt_from_control(pilot=pilot, root=root, prepared=prepared, control_raw=control_raw)
        _write_grok_native_binding(root=root, run_root=Path(run_root), native=native_receipt)
        normalized = dict(native_receipt); normalized["transmitted_payload_sha256"] = prepared["payload"]["sha256"]
        verified = pilot.validate_receipt(prepared_root=root, receipt=normalized, output_path=output)
        authority = verified["provider_request_id"]
    else:
        verified = _sol_lifecycle_verified(pilot=pilot, root=root, prepared=prepared, control_raw=control_raw)
        _write_once(output, verified)
        authority = verified["local_lifecycle"]["thread_id_sha256"]
    return {"study_id": STUDY_ID, "kind": "reconciliation_only_receipt_ingest", "phase": phase, "event_id": event_id, "provider_calls_made": 0, "process_launches": 0, "raw_adapter_stdout": _commitment(Path(run_root), root / "adapter-stdout.raw"), "adapter_control_projection": _commitment(Path(run_root), root / "adapter-control.json"), "verified_receipt": _commitment(Path(run_root), output), "receipt_authority": authority}


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


def _projection_boundary(*, root: Path, prepared: Mapping[str, Any], event_id: str) -> dict[str, Any]:
    run_root = Path(str(prepared.get("work_root", ""))).resolve()
    if root.resolve() != _cell_root(run_root, "blind_endpoint_judgment", event_id).resolve():
        raise ValueError("Revision-gain live v2 endpoint receipt is outside its prepared run root")
    frozen_sha256 = prepared.get("frozen_manifest_sha256")
    if not isinstance(frozen_sha256, str) or _sha256(_stable_bytes(run_root / "frozen-inputs.json", label="projection frozen inputs")) != frozen_sha256:
        raise ValueError("Revision-gain live v2 endpoint frozen-input boundary drifted")
    endpoint_target = prepared.get("endpoint_target")
    if not isinstance(endpoint_target, Mapping) or set(endpoint_target) != {"target_root", "target_manifest", "blind_target_id", "target"}:
        raise ValueError("Revision-gain live v2 endpoint target boundary is invalid")
    target_root = Path(str(endpoint_target["target_root"])).resolve()
    manifest = endpoint_target["target_manifest"]
    if not isinstance(manifest, Mapping) or set(manifest) != {"path", "bytes", "sha256"}:
        raise ValueError("Revision-gain live v2 endpoint target manifest commitment is invalid")
    relative = manifest["path"]
    if not isinstance(relative, str) or not relative or Path(relative).is_absolute() or any(part in {"", ".", ".."} for part in Path(relative).parts):
        raise ValueError("Revision-gain live v2 endpoint target manifest path is unsafe")
    actual_manifest = _commitment(target_root, target_root / relative)
    if actual_manifest != dict(manifest):
        raise ValueError("Revision-gain live v2 endpoint target manifest commitment drifted")
    manifest_value = json.loads(_stable_bytes(target_root / relative, label="projection target manifest").decode("utf-8"))
    if manifest_value.get("work_root") != str(run_root) or manifest_value.get("frozen_manifest_sha256") != frozen_sha256:
        raise ValueError("Revision-gain live v2 endpoint target manifest crosses a run or frozen-input boundary")
    return {"run_root": str(run_root), "frozen_inputs_sha256": frozen_sha256, "target_root": str(target_root), "target_manifest": actual_manifest}


def _require_single_projection_boundary(boundaries: list[Mapping[str, Any]]) -> dict[str, Any]:
    if not boundaries:
        raise ValueError("Revision-gain live v2 endpoint projection has no boundary")
    first = dict(boundaries[0])
    required = {"run_root", "frozen_inputs_sha256", "target_root", "target_manifest"}
    if set(first) != required or any(dict(boundary) != first for boundary in boundaries[1:]):
        raise ValueError("Revision-gain live v2 endpoint projection splices multiple runs or target freezes")
    return first


def project(*, endpoint_receipt_paths: list[Path]) -> dict[str, Any]:
    pilot = _pilot()
    value = pilot.contract()
    schedule = {row["endpoint_event_id"]: row for row in pilot.endpoint_schedule(value)}
    if len(endpoint_receipt_paths) != len(schedule):
        raise ValueError("Revision-gain live adapter mixed endpoint evidence is incomplete")
    observed: dict[str, int] = {}
    evidence_by_judge: dict[str, dict[str, Any]] = {}
    boundaries: list[dict[str, Any]] = []
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
        prepared = json.loads(_stable_bytes(supplied.parent / "prepared-cell.json", label="projection prepared endpoint cell").decode("utf-8"))
        boundaries.append(_projection_boundary(root=supplied.parent, prepared=prepared, event_id=event_id))
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

    projection_boundary = _require_single_projection_boundary(boundaries)

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
    return {"study_id": STUDY_ID, "kind": "independently_recomputed_mixed_endpoint_projection", "projection_boundary": projection_boundary,
            "endpoint_results_are_not_pooled": True, "paired_payloads": "unchanged_blind_target_and_measure_within_each_judge_route",
            "endpoint_evidence": evidence_summary, "primary_guided_minus_control": primary,
            "arm_minus_baseline": versus_baseline, "summaries": summaries}
