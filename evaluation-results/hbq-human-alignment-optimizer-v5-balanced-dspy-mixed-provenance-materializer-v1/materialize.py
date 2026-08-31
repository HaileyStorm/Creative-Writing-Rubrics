"""Provider-free materialization of one queue-derived HANNA descendant."""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import math
import os
import re
import sqlite3
import tempfile
from pathlib import Path
from typing import Any

STUDY_ID = "hbq-human-alignment-optimizer-v5-balanced-dspy-mixed-provenance-materializer-v1"
ITEM_ID = "2dcb7796bc76478f9cc3f930e9374186"
REQUESTER = "cwr-hanna-generalization-wave4-02"
IDEMPOTENCY_KEY = "cwr-hanna-generalization-wave4-20260830-02"
REQUEST_SHA256 = "ef4e551ffdf8557bf4676c4eec8e70aa20cd3e861cbb3eac74e6923738c5d6fa"
RESULT_SHA256 = "806fa0b3734252463da7db015be1e713ece6bc42945d8badccaa6b16d6539c0e"
TASK_METADATA_SHA256 = "b34cc20a5ec416d3c265604c6ca35262509111171da5d31b4eae2469f73e4dcf"
REGISTRY_SHA256 = "29a21d7efc6fe3c6ca8996cf378099f600a08dd3de4296758678896fb96718af"
DISCLOSURE_SHA256 = "0e74224a7032238ae07c190b168d01df4d16ea3aec0158dd9037027c644ed5bf"
OUTPUT_SHA256 = "0da5c22bd3a5d7a2c5cfdcd48718805c79b6bb2a0ae7f2a26530436fd1d6ecc3"
RECOMMENDATION_SHA256 = "de63e577fa16a4ba7065d592ccd2fc94d99d3aa71de985af91d30ecb85311920"
PREPARATION_SHA256 = "dd6dc97e7474d169eef384cafa14ab71237a6b45ea572b8bb9829ca6f8bb3e56"
PARTIAL_MANIFEST_FILE_SHA256 = "905594ab153deadc0c96fdaf23c1b97b124d1e1159adc50caeb7ebcd6558c99c"
PARTIAL_MANIFEST_SHA256 = "babebc8647de2e846945300d1fc87e29d0e7ba265c7fd585d3c56e500243f829"
PARENT_CANDIDATE_ID = "candidate-52d1be4bc34e0018"
PARENT_INSTRUCTION_SHA256 = "f318da394124d72dea4e9fb896d0345c6c5136d4839feae2cff1e389ea642de1"
PARENT_PROFILE_SHA256 = "3d90b5bdd1b1cd1673cc45b834485754eb0ee01f89e2c3c7ddf5d31e7d24c74f"
DESCENDANT_INSTRUCTION_SHA256 = "3db9a5c76e89212bd296ba50c90c601a2cd7acfcd9ba1e9e35c5df3ba976e3ac"
HERE = Path(__file__).resolve().parent
CONTRACT = HERE / "study-contract.json"
AUTHORITY = {
    "confirmation": {"cells": 0, "status": "unopened"},
    "endpoint_contact_evidence": {
        "materialization_provider_calls_made": 0,
        "native_contact_proven": False,
        "native_endpoint_contact_cardinality": "unknown_not_inferred_from_queue_attempt",
        "reasoning_attested": False,
        "source_provider_attempts": 1,
        "source_route": "grok-build-grok-4.6",
        "source_model": "grok-4.6",
    },
    "evaluation": False,
    "local_only": True,
    "promotion": False,
    "runtime": False,
    "selection": False,
}


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def canonical(value: Any, *, newline: bool = True) -> bytes:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return raw + (b"\n" if newline else b"")


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("mixed materializer JSON has a duplicate key")
        value[key] = item
    return value


def strict_json(raw: bytes, *, label: str) -> Any:
    def finite(token: str) -> float:
        value = float(token)
        if not math.isfinite(value):
            raise ValueError(token)
        return value
    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs,
                          parse_float=finite,
                          parse_constant=lambda token: (_ for _ in ()).throw(ValueError(token)))
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise ValueError(f"mixed materializer {label} is not strict UTF-8 JSON") from error


def _plain(path: Path, *, directory: bool | None = None) -> bool:
    try:
        stat = path.lstat()
    except OSError:
        return False
    if os.path.islink(path) or getattr(stat, "st_reparse_tag", 0):
        return False
    return path.is_dir() if directory else path.is_file() if directory is False else True


def _identity(stat: os.stat_result) -> tuple[int, int, int, int, int]:
    return (stat.st_dev, stat.st_ino, stat.st_mode, stat.st_size, stat.st_mtime_ns)


def _directory_identity(stat: os.stat_result) -> tuple[int, int, int]:
    return (stat.st_dev, stat.st_ino, stat.st_mode)


def _ancestry(path: Path) -> None:
    absolute = Path(os.path.abspath(path))
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current /= part
        if current.exists() and not _plain(current, directory=current.is_dir()):
            raise ValueError(f"mixed materializer unsafe path ancestry: {path}")


def _stable(path: Path, *, expected: str | None = None) -> bytes:
    _ancestry(path)
    if not _plain(path, directory=False):
        raise ValueError(f"mixed materializer unsafe or missing file: {path}")
    before = path.lstat()
    try:
        with path.open("rb") as handle:
            opened = os.fstat(handle.fileno())
            raw = handle.read()
    except OSError as error:
        raise ValueError(f"mixed materializer could not read source safely: {path}") from error
    try:
        after = path.lstat()
    except OSError as error:
        raise ValueError(f"mixed materializer source disappeared while reading: {path}") from error
    if _identity(before) != _identity(opened) or _identity(opened) != _identity(after):
        raise ValueError(f"mixed materializer source identity changed while reading: {path}")
    if expected is not None and sha256(raw) != expected:
        raise ValueError(f"mixed materializer source hash drifted: {path.name}")
    return raw


def _canonical_object(raw: bytes, *, label: str, newline: bool = True) -> dict[str, Any]:
    value = strict_json(raw, label=label)
    if not isinstance(value, dict) or canonical(value, newline=newline) != raw:
        raise ValueError(f"mixed materializer {label} must be a canonical object")
    return value


def _artifact(queue_root: Path, digest: str) -> Path:
    return queue_root / "artifacts" / digest[:2] / digest[2:]


def _queue_sources(queue_root: Path) -> tuple[dict[str, Any], dict[str, Any], bytes, bytes, bytes, bytes, bytes]:
    request_raw = _stable(_artifact(queue_root, REQUEST_SHA256), expected=REQUEST_SHA256)
    result_raw = _stable(_artifact(queue_root, RESULT_SHA256), expected=RESULT_SHA256)
    metadata_raw = _stable(_artifact(queue_root, TASK_METADATA_SHA256), expected=TASK_METADATA_SHA256)
    registry_raw = _stable(_artifact(queue_root, REGISTRY_SHA256), expected=REGISTRY_SHA256)
    disclosure_raw = _stable(_artifact(queue_root, DISCLOSURE_SHA256), expected=DISCLOSURE_SHA256)
    inbox_raw = _stable(queue_root / "inbox" / REQUESTER / f"{ITEM_ID}.json", expected=RESULT_SHA256)
    if inbox_raw != result_raw:
        raise ValueError("mixed materializer delivered inbox bytes differ from result artifact")
    request = _canonical_object(request_raw, label="queue request", newline=False)
    result = _canonical_object(result_raw, label="queue result", newline=False)
    metadata = _canonical_object(metadata_raw, label="queue task metadata", newline=False)
    registry = _canonical_object(registry_raw, label="queue registry", newline=False)
    disclosure = _canonical_object(disclosure_raw, label="queue disclosure", newline=False)
    if metadata != {"sample": 2, "wave": "generalization-wave4"}:
        raise ValueError("mixed materializer task metadata drifted")
    if set(request) != {"prompt"} or not isinstance(request["prompt"], str):
        raise ValueError("mixed materializer queue request shape drifted")
    expected_disclosure = {
        "authorizations": [{
            "destination": "xai_grok_build_subscription",
            "expires_at": "2026-08-30T21:43:24+00:00",
            "model": "grok-4.6",
            "not_before": "2026-08-30T21:33:24+00:00",
            "request_hash": REQUEST_SHA256,
            "route": "grok-build-grok-4.6",
        }],
        "authorized": True,
        "destination": "xai_grok_build_subscription",
        "payload_classification": "public_synthetic",
    }
    if disclosure != expected_disclosure:
        raise ValueError("mixed materializer queue disclosure drifted")
    _validate_result(result, registry)
    receipt = _queue_receipt(queue_root)
    if receipt["sqlite"]["work_item"]["disclosure_hash"] != DISCLOSURE_SHA256:
        raise ValueError("mixed materializer queue receipt disclosure binding drifted")
    return result, receipt, request_raw, result_raw, metadata_raw, registry_raw, disclosure_raw


def _validate_result(value: dict[str, Any], registry: dict[str, Any]) -> None:
    if set(value) != {"finished_at", "item_id", "resolution", "resolution_hash", "result", "route", "started_at"} or value["item_id"] != ITEM_ID:
        raise ValueError("mixed materializer queue result envelope drifted")
    route, resolution, result = value["route"], value["resolution"], value["result"]
    if route != {"adapter": "grok_exec", "model": "grok-4.6", "name": "grok-build-grok-4.6"}:
        raise ValueError("mixed materializer queue route drifted")
    if not isinstance(resolution, dict) or value.get("resolution_hash") != sha256(canonical(resolution, newline=False)) or resolution.get("registry_hash") != REGISTRY_SHA256 or resolution.get("task_metadata") != {"sample": 2, "wave": "generalization-wave4"} or resolution.get("zero_charge_only") is not True or resolution.get("selector") != {"kind": "exact", "value": "grok-4.6"}:
        raise ValueError("mixed materializer queue resolution drifted")
    routes = registry.get("routes")
    selected = [item for item in routes if isinstance(item, dict) and item.get("name") == route["name"]] if isinstance(routes, list) else []
    if len(selected) != 1:
        raise ValueError("mixed materializer frozen registry route is missing or duplicated")
    frozen_route = selected[0]
    if resolution.get("route_hash") != sha256(canonical(frozen_route, newline=False)):
        raise ValueError("mixed materializer frozen registry route commitment drifted")
    if not isinstance(result, dict) or set(result) != {"output", "output_hash", "request_hash", "runtime", "schema_version"} or result["schema_version"] != 1 or result["request_hash"] != REQUEST_SHA256:
        raise ValueError("mixed materializer adapter result shape drifted")
    output = result["output"]
    if not isinstance(output, dict) or result["output_hash"] != OUTPUT_SHA256 or sha256(canonical(output, newline=False)) != OUTPUT_SHA256:
        raise ValueError("mixed materializer adapter output commitment drifted")
    recommendations = output.get("recommendations")
    if not isinstance(recommendations, list) or len(recommendations) != 1 or not isinstance(recommendations[0], str) or sha256(recommendations[0].encode("utf-8")) != RECOMMENDATION_SHA256:
        raise ValueError("mixed materializer exact recommendation drifted")
    runtime = result["runtime"]
    required = {"adapter_version", "cli_version", "command_identity", "command_identity_hash", "envelope_hash", "execution_policy", "identity_evidence", "nonvisual_max_turns", "observed_turns", "reasoning_attestation", "reasoning_attested", "reported_model", "request_id_hash", "requested_model", "requested_reasoning_effort", "session_id_hash", "subscription_receipt_hash", "usage_telemetry"}
    if not isinstance(runtime, dict) or set(runtime) != required:
        raise ValueError("mixed materializer runtime shape drifted")
    exact = {"adapter_version": 1, "execution_policy": "bounded_nonvisual_read_only", "identity_evidence": "requested_only", "nonvisual_max_turns": 1, "observed_turns": 1, "reasoning_attestation": "not_reported_by_grok_build_cli", "reasoning_attested": False, "reported_model": "grok-4.6-build", "requested_model": "grok-4.6", "requested_reasoning_effort": "high", "subscription_receipt_hash": "35c11416d9435e311fb1095052486523e570c8faf669b4c30ec3b3f2e58126b3"}
    if any(runtime.get(key) != item for key, item in exact.items()):
        raise ValueError("mixed materializer runtime identity drifted")
    hashes = ("command_identity_hash", "envelope_hash", "request_id_hash", "session_id_hash", "subscription_receipt_hash")
    if any(not isinstance(runtime[key], str) or not re.fullmatch(r"[0-9a-f]{64}", runtime[key]) for key in hashes) or runtime["request_id_hash"] == runtime["session_id_hash"]:
        raise ValueError("mixed materializer runtime commitments are invalid")
    command_domain = {"adapter_version": 1, "grok_command": frozen_route.get("grok_command"), "model": frozen_route.get("model"), "reported_model": frozen_route.get("reported_model"), "reasoning_effort": frozen_route.get("reasoning_effort")}
    if runtime["command_identity"] != frozen_route.get("grok_command_identity") or runtime["command_identity_hash"] != sha256(canonical(command_domain, newline=False)):
        raise ValueError("mixed materializer command identity commitment drifted")
    telemetry = runtime["usage_telemetry"]
    if not isinstance(telemetry, dict) or set(telemetry) != {"model_cost_usd", "status", "total_cost_usd", "total_cost_usd_ticks"} or telemetry["status"] != "reported":
        raise ValueError("mixed materializer usage telemetry shape drifted")
    for key in ("model_cost_usd", "total_cost_usd"):
        if not isinstance(telemetry[key], (int, float)) or isinstance(telemetry[key], bool) or not math.isfinite(telemetry[key]) or telemetry[key] < 0:
            raise ValueError("mixed materializer usage telemetry is invalid")
    if not isinstance(telemetry["total_cost_usd_ticks"], int) or isinstance(telemetry["total_cost_usd_ticks"], bool) or telemetry["total_cost_usd_ticks"] < 0:
        raise ValueError("mixed materializer usage telemetry ticks are invalid")


def _validate_queue_rows(work_rows: list[dict[str, Any]], attempt_rows: list[dict[str, Any]], delivery_rows: list[dict[str, Any]]) -> None:
    """Bind every queue lifecycle field rather than inferring a native contact."""
    expected_work = [{
        "id": ITEM_ID, "requester": REQUESTER, "idempotency_key": IDEMPOTENCY_KEY,
        "idempotency_hash": "8f958208a25d45663aa5617abbddb755f3fb585ae3891f6e223cc569929b51fc",
        "request_hash": REQUEST_SHA256, "registry_hash": REGISTRY_SHA256,
        "disclosure_hash": DISCLOSURE_SHA256, "selector_kind": "exact", "selector_value": "grok-4.6",
        "zero_charge_only": 1, "conversation_key": None, "affinity_model": None, "affinity_route": None,
        "minimum_intelligence": None, "allowed_models_json": None, "profile_name": None, "profile_hash": None,
        "hierarchy_version": 1, "profile_version": None, "status": "completed", "backoff_count": 0,
        "next_attempt_at": "2026-08-30T21:33:24+00:00", "lease_token": None, "lease_until": None,
        "claimed_route": "grok-build-grok-4.6", "resolved_route": "grok-build-grok-4.6",
        "resolved_model": "grok-4.6", "created_at": "2026-08-30T21:33:24+00:00",
        "updated_at": "2026-08-30T21:35:07+00:00", "completed_at": "2026-08-30T21:35:07+00:00",
        "error": None, "task_metadata_hash": TASK_METADATA_SHA256,
    }]
    expected_attempts = [{
        "id": 78, "item_id": ITEM_ID, "lease_token": "b7b8fac091d34befac8d932acd5e96cd",
        "route_name": "grok-build-grok-4.6", "route_model": "grok-4.6",
        "started_at": "2026-08-30T21:33:44+00:00", "finished_at": "2026-08-30T21:35:07+00:00",
        "outcome": "completed", "detail": None, "result_hash": RESULT_SHA256,
        "late_result_hash": None, "late_detail": None,
    }]
    expected_deliveries = [{
        "item_id": ITEM_ID, "requester": REQUESTER, "result_hash": RESULT_SHA256,
        "status": "delivered", "attempts": 1, "last_error": None,
        "updated_at": "2026-08-30T21:35:07+00:00",
    }]
    if work_rows != expected_work or attempt_rows != expected_attempts or delivery_rows != expected_deliveries:
        raise ValueError("mixed materializer queue completion receipt drifted")


def _queue_receipt(queue_root: Path) -> dict[str, Any]:
    db = queue_root / "queue.sqlite3"
    db_raw = _stable(db)
    wal = Path(f"{db}-wal")
    wal_raw = _stable(wal) if wal.exists() else None
    with tempfile.TemporaryDirectory(prefix="cwr-hanna-queue-snapshot-") as temporary:
        snapshot_root = Path(temporary)
        _ancestry(snapshot_root)
        if not _plain(snapshot_root, directory=True):
            raise ValueError("mixed materializer SQLite snapshot root is unsafe")
        root_identity = _directory_identity(snapshot_root.lstat())
        parent_identity = _directory_identity(snapshot_root.parent.lstat())
        snapshot = snapshot_root / "queue.sqlite3"
        _write_artifact(snapshot_root, root_identity, parent_identity, snapshot.name, db_raw)
        snapshot_wal = Path(f"{snapshot}-wal")
        if wal_raw is not None:
            _write_artifact(snapshot_root, root_identity, parent_identity, snapshot_wal.name, wal_raw)
        if _stable(snapshot) != db_raw or (wal_raw is not None and _stable(snapshot_wal) != wal_raw):
            raise ValueError("mixed materializer SQLite snapshot hash drifted")
        uri = snapshot.resolve().as_uri() + "?mode=ro"
        connection = sqlite3.connect(uri, uri=True)
        connection.row_factory = sqlite3.Row
        try:
            opened = connection.execute("PRAGMA database_list").fetchall()
            if len(opened) != 1 or Path(opened[0][2]).resolve() != snapshot.resolve():
                raise ValueError("mixed materializer SQLite snapshot was redirected")
            connection.execute("PRAGMA query_only=ON")
            connection.execute("BEGIN")
            work = connection.execute("SELECT * FROM work_items WHERE id=?", (ITEM_ID,)).fetchall()
            attempts = connection.execute("SELECT * FROM attempts WHERE item_id=? ORDER BY id", (ITEM_ID,)).fetchall()
            deliveries = connection.execute("SELECT * FROM deliveries WHERE item_id=?", (ITEM_ID,)).fetchall()
            connection.execute("COMMIT")
        except sqlite3.Error as error:
            raise ValueError("mixed materializer SQLite snapshot could not be queried") from error
        finally:
            connection.close()
        if _directory_identity(snapshot_root.parent.lstat()) != parent_identity or _directory_identity(snapshot_root.lstat()) != root_identity or _stable(snapshot) != db_raw or (wal_raw is not None and _stable(snapshot_wal) != wal_raw):
            raise ValueError("mixed materializer SQLite snapshot changed while reading")
    if _stable(db) != db_raw or (wal_raw is not None and _stable(wal) != wal_raw):
        raise ValueError("mixed materializer queue database changed while snapshotting")
    work_rows = [dict(row) for row in work]
    attempt_rows = [dict(row) for row in attempts]
    delivery_rows = [dict(row) for row in deliveries]
    _validate_queue_rows(work_rows, attempt_rows, delivery_rows)
    return {
        "format_version": 2,
        "item_id": ITEM_ID,
        "evidence_class": "completed_queue_adapter_result_with_one_completed_attempt",
        "sqlite_database_sha256": sha256(db_raw),
        "sqlite_wal_sha256": sha256(wal_raw) if wal_raw is not None else None,
        "sqlite": {"work_item": work_rows[0], "attempts": attempt_rows, "deliveries": delivery_rows},
        "endpoint_contact_evidence": {
            "source_provider_attempts": 1,
            "native_contact_proven": False,
            "native_endpoint_contact_cardinality": "unknown_not_inferred_from_queue_attempt",
            "reasoning_attested": False,
            "source_route": "grok-build-grok-4.6",
            "source_model": "grok-4.6",
        },
    }


def _preparation(path: Path) -> tuple[bytes, dict[str, Any], bytes, bytes]:
    raw = _stable(path, expected=PREPARATION_SHA256); value = _canonical_object(raw, label="DSPy input preparation")
    inputs = value.get("inputs")
    if not isinstance(inputs, dict) or value.get("inputs_sha256") != sha256(canonical(inputs)) or inputs.get("parent_candidate_id") != PARENT_CANDIDATE_ID:
        raise ValueError("mixed materializer DSPy preparation binding drifted")
    instruction = _b64(inputs.get("parent_instruction_base64"), label="parent instruction")
    profile = _b64(inputs.get("parent_profile_base64"), label="parent profile")
    if sha256(instruction) != PARENT_INSTRUCTION_SHA256 or sha256(profile) != PARENT_PROFILE_SHA256:
        raise ValueError("mixed materializer frozen parent bytes drifted")
    profile_value = strict_json(profile, label="parent profile")
    if not isinstance(profile_value, dict) or profile_value.get("instruction_sha256") != PARENT_INSTRUCTION_SHA256:
        raise ValueError("mixed materializer parent profile binding drifted")
    return raw, value, instruction, profile


def _b64(value: Any, *, label: str) -> bytes:
    if not isinstance(value, str) or not value or not value.isascii() or re.search(r"\s", value):
        raise ValueError(f"mixed materializer {label} base64 is invalid")
    try:
        raw = base64.b64decode(value.encode("ascii"), validate=True)
    except ValueError as error:
        raise ValueError(f"mixed materializer {label} base64 is invalid") from error
    if base64.b64encode(raw).decode("ascii") != value:
        raise ValueError(f"mixed materializer {label} base64 is noncanonical")
    return raw


def _partial(path: Path) -> tuple[bytes, dict[str, Any]]:
    raw = _stable(path, expected=PARTIAL_MANIFEST_FILE_SHA256); value = _canonical_object(raw, label="partial-nine manifest")
    body = dict(value); digest = body.pop("manifest_sha256", None)
    if digest != PARTIAL_MANIFEST_SHA256 or sha256(canonical(body)) != digest:
        raise ValueError("mixed materializer partial manifest commitment drifted")
    authority = {"confirmation": {"cells": 0, "status": "unopened"}, "evaluation": False, "local_only": True, "promotion": False, "runtime": False, "selection": False}
    samples = value.get("samples")
    if value.get("authority") != authority or value.get("completion", {}).get("status") != "partial" or not isinstance(samples, list) or len(samples) != 9:
        raise ValueError("mixed materializer partial manifest authority or geometry drifted")
    return raw, value


def _derive(parent_instruction: bytes, parent_profile: bytes, recommendation: bytes) -> tuple[bytes, bytes, str, str]:
    instruction = parent_instruction + b"\n" + recommendation + b"\n"
    if sha256(instruction) != DESCENDANT_INSTRUCTION_SHA256:
        raise ValueError("mixed materializer derived instruction commitment drifted")
    profile = strict_json(parent_profile, label="parent profile")
    derived = dict(profile)
    derived.update({"format_version": 2, "study_id": STUDY_ID, "instruction_sha256": sha256(instruction), "parent_candidate_id": PARENT_CANDIDATE_ID, "version": "queue-materialized-v1", "wave_id": "generalization-wave4", "descendant_version": "v5", "feedback_kind": "completed_queue_public_feedback_recommendation", "lineage": {"derivation": "parent_instruction_lf_recommendation_lf", "parent_instruction_sha256": PARENT_INSTRUCTION_SHA256, "parent_profile_sha256": PARENT_PROFILE_SHA256, "queue_item_id": ITEM_ID, "queue_result_sha256": RESULT_SHA256, "queue_output_sha256": OUTPUT_SHA256, "recommendation_sha256": RECOMMENDATION_SHA256, "provider_output_unchanged": False}})
    profile_raw = canonical(derived)
    identity = {"study_id": STUDY_ID, "queue_item_id": ITEM_ID, "queue_result_sha256": RESULT_SHA256, "queue_output_sha256": OUTPUT_SHA256, "recommendation_sha256": RECOMMENDATION_SHA256, "parent_candidate_id": PARENT_CANDIDATE_ID, "parent_instruction_sha256": PARENT_INSTRUCTION_SHA256, "parent_profile_sha256": PARENT_PROFILE_SHA256, "descendant_instruction_sha256": sha256(instruction), "descendant_profile_sha256": sha256(profile_raw)}
    candidate_sha = sha256(canonical(identity)); candidate_id = "candidate-" + candidate_sha[:16]
    if candidate_id == PARENT_CANDIDATE_ID:
        raise ValueError("mixed materializer did not derive a distinct candidate identity")
    return instruction, profile_raw, candidate_id, candidate_sha


def _composition(partial: dict[str, Any], instruction: bytes, profile: bytes, candidate_id: str, candidate_sha: str) -> dict[str, Any]:
    candidates: list[dict[str, Any]] = []
    for source in partial["samples"]:
        normalized = source.get("canonical_descendant")
        if not isinstance(normalized, dict) or set(normalized) != {"descendant_instruction_base64", "descendant_profile_base64"}:
            raise ValueError("mixed materializer reconciled candidate shape drifted")
        source_instruction = _b64(normalized["descendant_instruction_base64"], label="reconciled instruction")
        source_profile = _b64(normalized["descendant_profile_base64"], label="reconciled profile")
        source_terminal = source.get("source_terminal")
        if not isinstance(source_terminal, dict) or source_terminal.get("kind") != "reconcile_required_after_process_launch" or source_terminal.get("native_contact_proven") is not False or source_terminal.get("native_endpoint_contact_cardinality") != "unknown" or source_terminal.get("provider_calls_made") is not None:
            raise ValueError("mixed materializer reconciled terminal ceiling drifted")
        if not isinstance(source.get("source_native_contact_status"), str):
            raise ValueError("mixed materializer reconciled native-contact status drifted")
        descriptor = {"instruction_sha256": sha256(source_instruction), "profile_sha256": sha256(source_profile)}
        source_candidate_sha = sha256(canonical(descriptor))
        if source.get("canonical_descendant_sha256") != sha256(canonical(normalized)) or source.get("canonical_profile_sha256") != sha256(source_profile):
            raise ValueError("mixed materializer reconciled candidate commitment drifted")
        candidates.append({"sample_id": source["sample_id"], "candidate_id": "candidate-" + source_candidate_sha[:16], "candidate_sha256": source_candidate_sha, "instruction_base64": normalized["descendant_instruction_base64"], "instruction_sha256": descriptor["instruction_sha256"], "profile_base64": normalized["descendant_profile_base64"], "profile_sha256": descriptor["profile_sha256"], "provenance": {"kind": "reconciled_v3_terminal_descendant_under_unknown_native_contact", "source_manifest_sha256": PARTIAL_MANIFEST_SHA256, "source_canonical_descendant_sha256": source["canonical_descendant_sha256"], "source_native_contact_status": source["source_native_contact_status"], "source_terminal": source_terminal}})
    candidates.append({"sample_id": "generalization-wave4-sample-02-queue-materialized-v5", "candidate_id": candidate_id, "candidate_sha256": candidate_sha, "instruction_base64": base64.b64encode(instruction).decode("ascii"), "instruction_sha256": sha256(instruction), "profile_base64": base64.b64encode(profile).decode("ascii"), "profile_sha256": sha256(profile), "provenance": {"kind": "EXPLORATORY_POST_HOC_MATERIALIZATION", "queue_item_id": ITEM_ID, "queue_result_sha256": RESULT_SHA256, "queue_output_sha256": OUTPUT_SHA256, "recommendation_sha256": RECOMMENDATION_SHA256, "source_provider_attempts": 1, "reasoning_attested": False, "native_contact_proven": False, "native_endpoint_contact_cardinality": "unknown_not_inferred_from_queue_attempt", "provider_output_unchanged": False, "not_a_recovered_replacement_or_native_descendant": True}})
    if len(candidates) != 10 or len({row["candidate_id"] for row in candidates}) != 10:
        raise ValueError("mixed materializer composition candidates are not ten distinct identities")
    value = {"format_version": 2, "study_id": STUDY_ID, "kind": "mixed_generation_provenance_ten_candidate_composition", "sources": {"partial_nine_manifest_file_sha256": PARTIAL_MANIFEST_FILE_SHA256, "partial_nine_manifest_sha256": PARTIAL_MANIFEST_SHA256, "queue_item_id": ITEM_ID, "queue_result_sha256": RESULT_SHA256}, "composition": {"candidate_count": 10, "reconciled_v3_terminal_descendants": 9, "exploratory_post_hoc_materializations": 1}, "candidates": candidates, "authority": AUTHORITY, "materialization_provider_calls_made": 0, "materialization_process_launches": 0, "claim": "exploratory generation material only; independent evaluation required; not a homogeneous, recovered, replacement, or native-descendant set"}
    value["manifest_sha256"] = sha256(canonical(value))
    return value


def _create_output_root(path: Path) -> tuple[tuple[int, int, int], tuple[int, int, int]]:
    _ancestry(path.parent)
    if not _plain(path.parent, directory=True) or path.exists():
        raise ValueError("mixed materializer requires a safe existing parent and fresh output path")
    parent_identity = _directory_identity(path.parent.lstat())
    try:
        path.mkdir(mode=0o700)
    except FileExistsError as error:
        raise ValueError("mixed materializer requires a fresh output path") from error
    if _directory_identity(path.parent.lstat()) != parent_identity or not _plain(path, directory=True):
        raise ValueError("mixed materializer output root is unsafe")
    return _directory_identity(path.lstat()), parent_identity


def _write_artifact(output_root: Path, root_identity: tuple[int, int, int], parent_identity: tuple[int, int, int], name: str, raw: bytes) -> None:
    try:
        parent_current = _directory_identity(output_root.parent.lstat())
        root_current = _directory_identity(output_root.lstat())
    except OSError as error:
        raise ValueError("mixed materializer output root identity changed") from error
    if parent_current != parent_identity or root_current != root_identity or not _plain(output_root, directory=True):
        raise ValueError("mixed materializer output root identity changed")
    path = output_root / name
    if path.parent != output_root or path.name != name or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", name):
        raise ValueError("mixed materializer output artifact name is unsafe")
    try:
        with path.open("xb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
            opened = os.fstat(handle.fileno())
    except OSError as error:
        raise ValueError(f"mixed materializer could not create artifact: {name}") from error
    try:
        parent_current = _directory_identity(output_root.parent.lstat())
    except OSError as error:
        raise ValueError(f"mixed materializer output artifact identity changed: {name}") from error
    if parent_current != parent_identity or not _plain(path, directory=False) or _identity(path.lstat()) != _identity(opened) or _stable(path) != raw:
        raise ValueError(f"mixed materializer output artifact identity changed: {name}")


def materialize(*, queue_root: Path, dspy_input_preparation: Path, partial_nine_manifest: Path, output_root: Path) -> dict[str, Any]:
    contract_raw = _stable(CONTRACT); contract = _canonical_object(contract_raw, label="study contract")
    expected_contract = {"format_version": 2, "study_id": STUDY_ID, "kind": "provider_free_mixed_provenance_tenth_descendant_materialization", "sources": {"dspy_input_preparation_sha256": PREPARATION_SHA256, "partial_nine_manifest_file_sha256": PARTIAL_MANIFEST_FILE_SHA256, "queue": {"disclosure_sha256": DISCLOSURE_SHA256, "item_id": ITEM_ID, "registry_sha256": REGISTRY_SHA256, "request_sha256": REQUEST_SHA256, "result_sha256": RESULT_SHA256, "task_metadata_sha256": TASK_METADATA_SHA256}}, "authority": AUTHORITY}
    if contract != expected_contract:
        raise ValueError("mixed materializer study contract drifted")
    queue_root = Path(queue_root); output_root = Path(output_root)
    _ancestry(queue_root)
    if not _plain(queue_root, directory=True):
        raise ValueError("mixed materializer requires a safe existing queue root and fresh output path")
    result, receipt, request_raw, result_raw, metadata_raw, registry_raw, disclosure_raw = _queue_sources(queue_root)
    preparation_raw, _preparation_value, parent_instruction, parent_profile = _preparation(Path(dspy_input_preparation))
    partial_raw, partial = _partial(Path(partial_nine_manifest))
    recommendation = result["result"]["output"]["recommendations"][0].encode("utf-8")
    instruction, profile, candidate_id, candidate_sha = _derive(parent_instruction, parent_profile, recommendation)
    composition = _composition(partial, instruction, profile, candidate_id, candidate_sha)
    descriptor = {"format_version": 2, "study_id": STUDY_ID, "kind": "EXPLORATORY_POST_HOC_MATERIALIZATION", "candidate_id": candidate_id, "candidate_sha256": candidate_sha, "instruction_sha256": sha256(instruction), "profile_sha256": sha256(profile), "parent_candidate_id": PARENT_CANDIDATE_ID, "source_provider_attempts": 1, "reasoning_attested": False, "native_contact_proven": False, "native_endpoint_contact_cardinality": "unknown_not_inferred_from_queue_attempt", "provider_output_unchanged": False, "not_a_recovered_replacement_or_native_descendant": True, "authority": AUTHORITY}
    artifacts = {"queue-request.json": request_raw, "queue-result.json": result_raw, "queue-task-metadata.json": metadata_raw, "queue-registry.json": registry_raw, "queue-disclosure.json": disclosure_raw, "queue-receipt.json": canonical(receipt), "dspy-input-preparation.json": preparation_raw, "partial-nine-manifest.json": partial_raw, "recommendation.bin": recommendation, "parent-instruction.bin": parent_instruction, "parent-profile.bin": parent_profile, "descendant-instruction.bin": instruction, "descendant-profile.json": profile, "descendant.json": canonical(descriptor), "mixed-composition.json": canonical(composition)}
    materialization = {"format_version": 2, "study_id": STUDY_ID, "kind": "completed_provider_free_materialization", "candidate_id": candidate_id, "candidate_sha256": candidate_sha, "artifacts": {name: sha256(raw) for name, raw in sorted(artifacts.items())}, "provider_calls_made": 0, "process_launches": 0, "authority": AUTHORITY}
    artifacts["materialization.json"] = canonical(materialization)
    output_identity, parent_identity = _create_output_root(output_root)
    for name, raw in artifacts.items():
        _write_artifact(output_root, output_identity, parent_identity, name, raw)
    return materialization


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--queue-root", type=Path, required=True)
    parser.add_argument("--dspy-input-preparation", type=Path, required=True)
    parser.add_argument("--partial-nine-manifest", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    result = materialize(queue_root=args.queue_root, dspy_input_preparation=args.dspy_input_preparation, partial_nine_manifest=args.partial_nine_manifest, output_root=args.output_root)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
