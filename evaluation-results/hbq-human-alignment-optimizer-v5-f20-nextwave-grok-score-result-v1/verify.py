from __future__ import annotations

import argparse
import base64
import hashlib
import json
import math
import os
import re
import stat
import sys
from collections.abc import Mapping
from pathlib import Path
from types import ModuleType
from typing import Any


HERE = Path(__file__).resolve().parent
STUDY_ID = "hbq-human-alignment-optimizer-v5-f20-nextwave-grok-score-exec-v1"
LIVE_EXEC = HERE.parent / "hbq-human-alignment-optimizer-v5-balanced-dspy-mixed-provenance-live-exec-v1" / "executor.py"
PUBLIC_FILES = {"README.md", "result.json", "study-contract.json", "verify.py"}
DIMENSIONS = ("Relevance", "Coherence", "Empathy", "Surprise", "Engagement", "Complexity")
CELL_FILES = {
    "authorization-acknowledgement.json",
    "disclosure.json",
    "effective-settings.json",
    "execution-receipt.json",
    "launch-intent.json",
    "native-request.bin",
    "native-response.bin",
    "outbound-payload.json",
    "prepared.json",
    "prompt-request.bin",
    "response-schema.json",
    "responses",
    "result.json",
    "runtime-identity.json",
    "zero-charge-route-proof.json",
}
RESPONSE_FILES = {
    "batch-0001.attempt-0001.grok.envelope.json",
    "batch-0001.attempt-0001.prompt.txt",
}
SENSITIVE_KEYS = {
    "contact_id",
    "human_targets",
    "identity",
    "lifecycle_id",
    "local_path",
    "native_request",
    "native_response",
    "payload",
    "prompt_text",
    "raw_output",
    "request_id",
    "session_id",
    "story_text",
    "writing",
}
PATH_PATTERN = re.compile(r"(?:[A-Za-z]:[\\/]|\\\\[^\\]+\\[^\\]+|/(?:Users|home|private|tmp)/)")
SENSITIVE_TEXT_TOKENS = {
    "private_story_sentinel",
    "native_request_base64",
    "native_response_base64",
    "raw_output",
    "request_id",
    "session_id",
    "story_text",
}


def canonical(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
    ).encode()


def adapter_canonical(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode()


def sha(value: bytes | Any) -> str:
    return hashlib.sha256(value if isinstance(value, bytes) else canonical(value)).hexdigest()


def _plain(path: Path, *, directory: bool | None = None) -> None:
    info = os.lstat(path)
    if stat.S_ISLNK(info.st_mode) or bool(
        getattr(info, "st_file_attributes", 0)
        & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    ):
        raise ValueError("unsafe or reparsed publication/source path")
    if directory is not None and stat.S_ISDIR(info.st_mode) != directory:
        raise ValueError("unexpected publication/source path type")


def _safe(path: Path) -> Path:
    absolute = Path(os.path.abspath(path))
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current /= part
        if current.exists():
            _plain(current)
    return absolute


def stable(path: Path) -> bytes:
    path = _safe(path)
    _plain(path, directory=False)
    before = os.lstat(path)
    with path.open("rb") as handle:
        opened = os.fstat(handle.fileno())
        raw = handle.read()
        after = os.fstat(handle.fileno())
    before_id = (before.st_dev, before.st_ino, before.st_size)
    opened_id = (opened.st_dev, opened.st_ino, opened.st_size)
    after_id = (after.st_dev, after.st_ino, after.st_size)
    if before_id != opened_id or opened_id != after_id:
        raise ValueError("publication/source file changed during read")
    return raw


def strict(raw: bytes, label: str) -> dict[str, Any]:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, child in items:
            if key in value:
                raise ValueError(f"duplicate key in {label}")
            value[key] = child
        return value

    try:
        value = json.loads(
            raw.decode(),
            object_pairs_hook=pairs,
            parse_constant=lambda token: (_ for _ in ()).throw(ValueError(token)),
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise ValueError(f"invalid {label}") from error
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return value


def _reject_sensitive(value: Any) -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            if not isinstance(key, str) or key.lower() in SENSITIVE_KEYS:
                raise ValueError("public surface contains sensitive material or a local path")
            _reject_sensitive(child)
    elif isinstance(value, list):
        for child in value:
            _reject_sensitive(child)
    elif isinstance(value, str) and PATH_PATTERN.search(value):
        raise ValueError("public surface contains sensitive material or a local path")


def _reject_sensitive_text(value: str) -> None:
    lowered = value.lower()
    if PATH_PATTERN.search(value) or any(token in lowered for token in SENSITIVE_TEXT_TOKENS):
        raise ValueError("public surface contains sensitive material or a local path")


def _exact_int(value: Any, expected: int) -> bool:
    return type(value) is int and value == expected


def _load(path: Path, digest: str, name: str) -> ModuleType:
    raw = stable(path)
    if sha(raw) != digest:
        raise ValueError("portable target reconstruction dependency drifted")
    module = ModuleType(name)
    module.__file__ = str(path)
    sys.modules[name] = module
    try:
        exec(compile(raw, str(path), "exec"), module.__dict__)
    finally:
        sys.modules.pop(name, None)
    if stable(path) != raw:
        raise ValueError("portable target reconstruction dependency changed")
    return module


def _derive_comparison(metrics: list[dict[str, Any]]) -> dict[str, Any]:
    if not isinstance(metrics, list) or len(metrics) != 11:
        raise ValueError("published metrics geometry drifted")
    baseline_rows = [row for row in metrics if str(row.get("candidate_id", "")).startswith("candidate-")]
    if len(baseline_rows) != 1:
        raise ValueError("baseline identity is not unique")
    for row in metrics:
        value = row.get("equal_group_mae")
        if type(value) not in (int, float) or not math.isfinite(value):
            raise ValueError("published metric is not finite numeric data")
    baseline = baseline_rows[0]
    lowest = min(metrics, key=lambda row: (row["equal_group_mae"], row["candidate_id"]))
    baseline_mae = baseline["equal_group_mae"]
    lowest_mae = lowest["equal_group_mae"]
    if baseline_mae <= 0:
        raise ValueError("baseline MAE must be positive")
    delta = lowest_mae - baseline_mae
    return {
        "absolute_delta": delta,
        "baseline_candidate_id": baseline["candidate_id"],
        "baseline_equal_group_mae": baseline_mae,
        "lowest_observed_candidate_id": lowest["candidate_id"],
        "lowest_observed_equal_group_mae": lowest_mae,
        "relative_reduction": -delta / baseline_mae,
    }


def validate_publication() -> dict[str, Any]:
    root = _safe(HERE)
    _plain(root, directory=True)
    if {path.name for path in root.iterdir()} != PUBLIC_FILES:
        raise ValueError("public package inventory drifted")
    for name in PUBLIC_FILES:
        _plain(root / name, directory=False)
    readme_raw = stable(root / "README.md")
    try:
        readme_text = readme_raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError("README is not UTF-8 text") from error
    _reject_sensitive_text(readme_text)
    contract_raw = stable(root / "study-contract.json")
    contract = strict(contract_raw, "study contract")
    result_raw = stable(root / "result.json")
    result = strict(result_raw, "public result")
    _reject_sensitive(contract)
    _reject_sensitive(result)
    if canonical(contract) != contract_raw:
        raise ValueError("study contract is not canonical")

    expected_contract_fields = {
        "authority",
        "comparison",
        "contract_internal_sha256",
        "evidence_ceiling",
        "format_version",
        "geometry",
        "kind",
        "publication_manifest",
        "result_internal_sha256",
        "source_execution",
        "study_id",
    }
    if set(contract) != expected_contract_fields:
        raise ValueError("study contract fields drifted")
    contract_internal = dict(contract)
    contract_internal.pop("contract_internal_sha256")
    if contract.get("contract_internal_sha256") != sha(contract_internal):
        raise ValueError("study contract internal commitment drifted")
    manifest = contract.get("publication_manifest")
    expected_manifest_fields = {"bound_files", "inventory", "strategy"}
    if not isinstance(manifest, dict) or set(manifest) != expected_manifest_fields:
        raise ValueError("publication manifest fields drifted")
    if manifest.get("inventory") != sorted(PUBLIC_FILES):
        raise ValueError("publication manifest inventory drifted")
    bound = manifest.get("bound_files")
    if not isinstance(bound, dict) or set(bound) != {"README.md", "result.json", "verify.py"}:
        raise ValueError("publication manifest bindings drifted")
    for name, digest in bound.items():
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ValueError("publication manifest digest drifted")
        if sha(stable(root / name)) != digest:
            raise ValueError(f"bound publication file drifted: {name}")

    expected_result_fields = {
        "authority",
        "claim",
        "comparison",
        "evidence_ceiling",
        "format_version",
        "kind",
        "metrics",
        "publication_geometry",
        "result_internal_sha256",
        "source_execution",
        "study_id",
    }
    expected_source_fields = {
        "collector_sha256",
        "executor_commit",
        "executor_sha256",
        "executor_study_contract_sha256",
        "normalized_source_manifest_sha256",
        "schedule_file_sha256",
        "target_reconstruction_contract_sha256",
        "target_reconstruction_executor_sha256",
    }
    if set(result) != expected_result_fields or set(result.get("source_execution", {})) != expected_source_fields:
        raise ValueError("public result fields drifted")
    if not _exact_int(result.get("format_version"), 1) or result.get("study_id") != STUDY_ID:
        raise ValueError("public result identity drifted")
    internal = dict(result)
    internal.pop("result_internal_sha256")
    if result.get("result_internal_sha256") != sha(internal):
        raise ValueError("public result internal commitment drifted")
    if contract.get("result_internal_sha256") != result["result_internal_sha256"]:
        raise ValueError("study contract internal result commitment drifted")
    if contract.get("source_execution") != result["source_execution"]:
        raise ValueError("source execution commitments drifted")
    if result.get("authority") != contract.get("authority"):
        raise ValueError("published authority drifted")
    if result.get("evidence_ceiling") != contract.get("evidence_ceiling"):
        raise ValueError("published evidence ceiling drifted")
    if result.get("publication_geometry") != {
        "candidate_observations": 11,
        "cells": 33,
        "dimensions": 6,
        "prompt_groups": 3,
    } or contract.get("geometry") != {
        "candidates": 11,
        "cells": 33,
        "development_groups": 3,
        "sol_cells": 0,
    }:
        raise ValueError("publication geometry drifted")

    metrics = result.get("metrics")
    if not isinstance(metrics, list) or len(metrics) != 11:
        raise ValueError("published metrics geometry drifted")
    candidates: set[str] = set()
    group_ids: set[str] | None = None
    for row in metrics:
        if not isinstance(row, dict) or set(row) != {"candidate_id", "cells", "equal_group_mae", "group_mae"}:
            raise ValueError("published metric fields drifted")
        candidate = row.get("candidate_id")
        groups = row.get("group_mae")
        if (
            not isinstance(candidate, str)
            or not candidate
            or candidate in candidates
            or not _exact_int(row.get("cells"), 3)
            or not isinstance(groups, dict)
            or len(groups) != 3
        ):
            raise ValueError("published metric geometry drifted")
        current_groups = set(groups)
        if group_ids is None:
            group_ids = current_groups
        if current_groups != group_ids:
            raise ValueError("published metric groups drifted")
        values = [row.get("equal_group_mae"), *groups.values()]
        if any(type(value) not in (int, float) or not math.isfinite(value) for value in values):
            raise ValueError("published metric is not finite numeric data")
        if row["equal_group_mae"] != sum(groups.values()) / 3:
            raise ValueError("published equal-group MAE drifted")
        candidates.add(candidate)
    ordered = sorted(metrics, key=lambda row: (row["equal_group_mae"], row["candidate_id"]))
    if metrics != ordered:
        raise ValueError("published metric ordering drifted")
    comparison = _derive_comparison(metrics)
    if result.get("comparison") != comparison or contract.get("comparison") != comparison:
        raise ValueError("published comparison is not derived from metrics")
    return result


def _canonical_file(path: Path, label: str) -> tuple[bytes, dict[str, Any]]:
    raw = stable(path)
    value = strict(raw, label)
    if canonical(value) != raw:
        raise ValueError(f"{label} is not canonical")
    return raw, value


def _decode(value: Any, label: str) -> bytes:
    if not isinstance(value, str):
        raise ValueError(f"{label} is not base64 text")
    try:
        return base64.b64decode(value, validate=True)
    except (ValueError, TypeError) as error:
        raise ValueError(f"invalid {label}") from error


def _validate_schedule(raw: bytes, source: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, dict[str, Any]], list[str]]:
    schedule = strict(raw, "persisted schedule")
    expected_fields = {
        "authority",
        "cells",
        "confirmation",
        "format_version",
        "groups",
        "kind",
        "normalized_source_manifest_sha256",
        "schedule_sha256",
        "study_id",
    }
    if canonical(schedule) != raw or set(schedule) != expected_fields:
        raise ValueError("persisted schedule fields drifted")
    internal = dict(schedule)
    internal.pop("schedule_sha256")
    if (
        not _exact_int(schedule.get("format_version"), 1)
        or schedule.get("study_id") != STUDY_ID
        or schedule.get("kind") != "frozen_33_cell_grok_development_schedule"
        or schedule.get("authority") != "development_only"
        or schedule.get("confirmation") != {"status": "unopened", "cells": 0}
        or schedule.get("schedule_sha256") != sha(internal)
        or schedule.get("normalized_source_manifest_sha256") != source["normalized_source_manifest_sha256"]
    ):
        raise ValueError("persisted schedule identity or authority drifted")
    groups = schedule.get("groups")
    if not isinstance(groups, list) or len(groups) != 3:
        raise ValueError("persisted schedule group geometry drifted")
    group_ids: list[str] = []
    for group in groups:
        if not isinstance(group, dict) or set(group) != {"item_id", "partition", "prompt_group_id"}:
            raise ValueError("persisted schedule group fields drifted")
        if group.get("partition") != "development" or not all(
            isinstance(group.get(key), str) and group[key] for key in ("item_id", "prompt_group_id")
        ):
            raise ValueError("persisted schedule group identity drifted")
        group_ids.append(group["prompt_group_id"])
    if len(set(group_ids)) != 3:
        raise ValueError("persisted schedule group identity is not unique")
    cells = schedule.get("cells")
    expected_cell_fields = {
        "candidate_id",
        "candidate_instruction_sha256",
        "candidate_profile_sha256",
        "cell_id",
        "item_id",
        "partition",
        "payload_base64",
        "payload_sha256",
        "prompt_group_id",
        "source_cell",
    }
    if not isinstance(cells, list) or len(cells) != 33:
        raise ValueError("persisted schedule cell geometry drifted")
    index: dict[str, dict[str, Any]] = {}
    candidate_groups: dict[str, set[str]] = {}
    for supplied in cells:
        if not isinstance(supplied, dict) or set(supplied) != expected_cell_fields:
            raise ValueError("persisted schedule cell fields drifted")
        row = dict(supplied)
        raw_payload = _decode(row.get("payload_base64"), "scheduled payload")
        cell_id = row.get("cell_id")
        candidate = row.get("candidate_id")
        if (
            not isinstance(cell_id, str)
            or not re.fullmatch(r"nextwave-score-[0-9a-f]{16}", cell_id)
            or cell_id in index
            or not isinstance(candidate, str)
            or not candidate
            or row.get("partition") != "development"
            or row.get("prompt_group_id") not in group_ids
            or row.get("payload_sha256") != sha(raw_payload)
            or not all(re.fullmatch(r"[0-9a-f]{64}", str(row.get(key, ""))) for key in ("candidate_instruction_sha256", "candidate_profile_sha256"))
        ):
            raise ValueError("persisted schedule cell binding drifted")
        index[cell_id] = row
        candidate_groups.setdefault(candidate, set()).add(row["prompt_group_id"])
    if len(candidate_groups) != 11 or any(value != set(group_ids) for value in candidate_groups.values()):
        raise ValueError("persisted schedule candidate geometry drifted")
    return schedule, index, group_ids


def _validate_collector(raw: bytes, schedule: Mapping[str, Any], index: Mapping[str, Any]) -> dict[str, Any]:
    collector = strict(raw, "persisted collector")
    expected_fields = {
        "authorization_acknowledgement_sha256",
        "cells",
        "format_version",
        "kind",
        "native_endpoint_contact_cardinality",
        "process_launches",
        "provider_calls_made",
        "route",
        "route_evidence",
        "schedule_sha256",
        "study_id",
    }
    route = collector.get("route")
    required_route = {
        "adapter": "grok_exec",
        "armed": True,
        "destination": "xai_grok_build_subscription",
        "health": "healthy",
        "model": "grok-4.6",
        "name": "grok-build-grok-4.6",
        "provider": "xai_grok_build",
        "reasoning_effort": "high",
        "reported_model": "grok-4.6-build",
        "zero_charge": True,
    }
    if (
        canonical(collector) != raw
        or set(collector) != expected_fields
        or not _exact_int(collector.get("format_version"), 1)
        or collector.get("study_id") != STUDY_ID
        or collector.get("kind") != "complete_33_normalized_nextwave_grok_receipts_cardinality_unproven"
        or collector.get("schedule_sha256") != schedule["schedule_sha256"]
        or collector.get("native_endpoint_contact_cardinality") != "unproven"
        or not _exact_int(collector.get("provider_calls_made"), 0)
        or not _exact_int(collector.get("process_launches"), 0)
        or not isinstance(route, dict)
        or any(route.get(key) != value for key, value in required_route.items())
        or not isinstance(collector.get("route_evidence"), dict)
        or not re.fullmatch(r"[0-9a-f]{64}", str(collector.get("authorization_acknowledgement_sha256", "")))
    ):
        raise ValueError("persisted collector identity, route, or authority drifted")
    cells = collector.get("cells")
    if not isinstance(cells, list) or len(cells) != 33:
        raise ValueError("persisted collector cell geometry drifted")
    if {row.get("cell_id") for row in cells if isinstance(row, dict)} != set(index):
        raise ValueError("persisted collector is partial or duplicated")
    return collector


def _validate_cell(
    *,
    root: Path,
    supplied: Mapping[str, Any],
    row: Mapping[str, Any],
    schedule: Mapping[str, Any],
    collector: Mapping[str, Any],
) -> tuple[bytes, tuple[str, str]]:
    expected_supplied = {
        "cell_id",
        "effective_settings",
        "effective_settings_sha256",
        "identity",
        "native_request_base64",
        "native_request_sha256",
        "native_response_base64",
        "native_response_sha256",
        "payload_base64",
        "payload_sha256",
    }
    if set(supplied) != expected_supplied:
        raise ValueError("collector cell fields drifted")
    _plain(root, directory=True)
    if {path.name for path in root.iterdir()} != CELL_FILES:
        raise ValueError("completed cell inventory drifted")
    responses = root / "responses"
    _plain(responses, directory=True)
    if {path.name for path in responses.iterdir()} != RESPONSE_FILES:
        raise ValueError("completed response inventory drifted")
    for path in root.iterdir():
        _plain(path, directory=path.name == "responses")
    for path in responses.iterdir():
        _plain(path, directory=False)

    payload = _decode(supplied.get("payload_base64"), "collector payload")
    request = _decode(supplied.get("native_request_base64"), "collector native request")
    response = _decode(supplied.get("native_response_base64"), "collector native response")
    identity = supplied.get("identity")
    settings = supplied.get("effective_settings")
    identity_fields = {
        "native_endpoint_contact_cardinality",
        "provider",
        "reported_model",
        "request_id",
        "requested_model",
        "session_id",
        "tools_enabled",
    }
    if (
        supplied.get("cell_id") != row["cell_id"]
        or supplied.get("payload_base64") != row["payload_base64"]
        or supplied.get("payload_sha256") != row["payload_sha256"]
        or sha(payload) != row["payload_sha256"]
        or supplied.get("native_request_sha256") != sha(request)
        or supplied.get("native_response_sha256") != sha(response)
        or supplied.get("effective_settings_sha256") != sha(settings)
        or not isinstance(identity, dict)
        or set(identity) != identity_fields
        or identity.get("provider") != "xai"
        or identity.get("requested_model") != "grok-4.6"
        or identity.get("reported_model") != "grok-4.6-build"
        or identity.get("native_endpoint_contact_cardinality") != "unproven"
        or identity.get("tools_enabled") is not False
        or not isinstance(settings, dict)
    ):
        raise ValueError("collector payload, response, identity, or settings drifted")
    contact = (identity.get("request_id"), identity.get("session_id"))
    if not all(isinstance(value, str) and value for value in contact):
        raise ValueError("collector native identity is absent")

    payload_value = strict(payload, "scheduled outbound payload")
    if canonical(payload_value) != payload:
        raise ValueError("scheduled outbound payload is not canonical")
    schema = payload_value.get("response_schema")
    if not isinstance(schema, dict):
        raise ValueError("scheduled response schema is absent")
    schema_raw = canonical(schema)
    if request != adapter_canonical({"prompt": payload.decode()}):
        raise ValueError("native request differs from frozen payload")
    if stable(root / "outbound-payload.json") != payload or stable(root / "prompt-request.bin") != payload:
        raise ValueError("prepared payload bytes drifted")
    if stable(root / "response-schema.json") != schema_raw:
        raise ValueError("prepared response schema drifted")
    if stable(root / "native-request.bin") != request or stable(root / "native-response.bin") != response:
        raise ValueError("persisted native bytes differ from collector")
    if stable(responses / "batch-0001.attempt-0001.prompt.txt") != payload:
        raise ValueError("runner prompt artifact differs from payload")
    if stable(responses / "batch-0001.attempt-0001.grok.envelope.json") != response:
        raise ValueError("runner envelope differs from native response")
    identity_raw, persisted_identity = _canonical_file(root / "runtime-identity.json", "runtime identity")
    settings_raw, persisted_settings = _canonical_file(root / "effective-settings.json", "effective settings")
    if persisted_identity != identity or persisted_settings != settings:
        raise ValueError("collector differs from persisted identity or settings")

    envelope = strict(response, "native Grok envelope")
    if envelope.get("requestId") != contact[0] or envelope.get("sessionId") != contact[1]:
        raise ValueError("native response identity is misassociated")
    _prepared_raw, prepared = _canonical_file(root / "prepared.json", "prepared evidence")
    disclosure_raw, disclosure = _canonical_file(root / "disclosure.json", "disclosure evidence")
    ack_raw, acknowledgement = _canonical_file(root / "authorization-acknowledgement.json", "acknowledgement evidence")
    proof_raw, proof = _canonical_file(root / "zero-charge-route-proof.json", "route proof evidence")
    intent_raw, intent = _canonical_file(root / "launch-intent.json", "launch intent evidence")
    receipt_raw, receipt = _canonical_file(root / "execution-receipt.json", "execution receipt evidence")
    _result_raw, terminal = _canonical_file(root / "result.json", "terminal result evidence")

    route = collector["route"]
    route_evidence = collector["route_evidence"]
    if (
        prepared.get("cell") != row
        or prepared.get("schedule_sha256") != schedule["schedule_sha256"]
        or prepared.get("outbound_payload_sha256") != sha(payload)
        or prepared.get("prompt_request_sha256") != sha(payload)
        or prepared.get("response_schema_sha256") != sha(schema_raw)
        or prepared.get("route") != route
        or prepared.get("route_evidence") != route_evidence
        or prepared.get("disclosure_sha256") != sha(disclosure)
        or prepared.get("authorization_sha256") != sha(acknowledgement)
        or prepared.get("route_proof_sha256") != sha(proof)
        or disclosure.get("cell_id") != row["cell_id"]
        or disclosure.get("route") != route
        or disclosure.get("route_evidence") != route_evidence
        or disclosure.get("payload") != {"bytes": len(payload), "sha256": sha(payload), "text": payload.decode()}
        or disclosure.get("response_schema") != {"bytes": len(schema_raw), "sha256": sha(schema_raw), "text": schema_raw.decode()}
        or acknowledgement.get("acknowledgement_sha256") != collector["authorization_acknowledgement_sha256"]
        or acknowledgement.get("disclosure_sha256") != sha(disclosure)
        or proof.get("route") != route
        or proof.get("route_evidence") != route_evidence
        or proof.get("zero_charge_only") is not True
        or proof.get("paid_fallback_forbidden") is not True
    ):
        raise ValueError("prepared disclosure, acknowledgement, or route proof drifted")
    if (
        intent.get("cell_id") != row["cell_id"]
        or intent.get("prepared_sha256") != sha(prepared)
        or intent.get("outbound_payload_sha256") != sha(payload)
        or intent.get("native_contact_proven") is not False
        or receipt.get("cell") != row
        or receipt.get("prepared_sha256") != sha(prepared)
        or receipt.get("launch_intent_sha256") != sha(intent)
        or receipt.get("payload_sha256") != sha(payload)
        or receipt.get("native_request_sha256") != sha(request)
        or receipt.get("native_response_sha256") != sha(response)
        or receipt.get("runner_prompt_artifact_sha256") != sha(payload)
        or receipt.get("effective_settings_sha256") != sha(settings)
        or receipt.get("identity") != identity
        or receipt.get("identity_sha256") != sha(identity)
        or receipt.get("native_endpoint_contact_cardinality") != "unproven"
        or terminal.get("cell_id") != row["cell_id"]
        or terminal.get("receipt_sha256") != sha(receipt)
        or terminal.get("native_endpoint_contact_cardinality") != "unproven"
    ):
        raise ValueError("launch, receipt, or terminal binding drifted")
    if identity_raw != canonical(identity) or settings_raw != canonical(settings):
        raise ValueError("persisted runtime evidence is not canonical")
    if any(raw != canonical(value) for raw, value in ((disclosure_raw, disclosure), (ack_raw, acknowledgement), (proof_raw, proof), (intent_raw, intent), (receipt_raw, receipt))):
        raise ValueError("persisted evidence canonicalization drifted")
    return response, contact


def replay(
    *,
    output_root: Path,
    collector: Path,
    materialization_root: Path,
    frozen_successor: Path,
    hanna_csv: Path,
) -> dict[str, Any]:
    public = validate_publication()
    source = public["source_execution"]
    output_root = _safe(output_root)
    collector = _safe(collector)
    _plain(output_root, directory=True)
    schedule_raw = stable(output_root / "schedule.json")
    collector_raw = stable(collector)
    if sha(schedule_raw) != source["schedule_file_sha256"]:
        raise ValueError("schedule file commitment drifted")
    if sha(collector_raw) != source["collector_sha256"]:
        raise ValueError("collector file commitment drifted")
    schedule, index, group_ids = _validate_schedule(schedule_raw, source)
    collector_value = _validate_collector(collector_raw, schedule, index)
    if {path.name for path in output_root.iterdir()} != {"schedule.json", *index}:
        raise ValueError("completed proof-root inventory drifted")
    for path in output_root.iterdir():
        _plain(path, directory=path.name != "schedule.json")

    historical_scorer = HERE.parent / "hbq-human-alignment-optimizer-v5-f20-nextwave-grok-score-exec-v1"
    if sha(stable(historical_scorer / "executor.py")) != source["executor_sha256"]:
        raise ValueError("historical scorer commitment drifted")
    if sha(stable(historical_scorer / "study-contract.json")) != source["executor_study_contract_sha256"]:
        raise ValueError("historical scorer contract commitment drifted")
    if sha(stable(LIVE_EXEC)) != source["target_reconstruction_executor_sha256"]:
        raise ValueError("portable target reconstruction executor drifted")
    live_contract = LIVE_EXEC.with_name("study-contract.json")
    if sha(stable(live_contract)) != source["target_reconstruction_contract_sha256"]:
        raise ValueError("portable target reconstruction contract drifted")
    live = _load(LIVE_EXEC, source["target_reconstruction_executor_sha256"], "_hanna_public_portable_live")
    live.contract()
    study = live._study()
    analyzer = live._analyze()
    token = study.prepare_grok_schedule(
        materialization_root=materialization_root,
        frozen_successor_path=frozen_successor,
        hanna_csv_path=hanna_csv,
    )
    targets = analyzer._targets(token)

    seen_contacts: set[tuple[str, str]] = set()
    observed: list[dict[str, Any]] = []
    collector_cells = {row["cell_id"]: row for row in collector_value["cells"]}
    for cell_id, row in index.items():
        response, contact = _validate_cell(
            root=output_root / cell_id,
            supplied=collector_cells[cell_id],
            row=row,
            schedule=schedule,
            collector=collector_value,
        )
        if contact in seen_contacts:
            raise ValueError("duplicate native identity")
        seen_contacts.add(contact)
        scores, _coverage, _reported = analyzer._v2()._extract_native(
            response,
            provider="xai",
            model="grok-4.6",
        )
        target = targets.get(row["item_id"])
        if not isinstance(target, dict) or set(target) != set(DIMENSIONS):
            raise ValueError("independently reconstructed human target drifted")
        values = [scores.get(dimension) for dimension in DIMENSIONS]
        if any(type(value) not in (int, float) or not math.isfinite(value) for value in values):
            raise ValueError("independently extracted model score drifted")
        observed.append(
            {
                "candidate_id": row["candidate_id"],
                "prompt_group_id": row["prompt_group_id"],
                "mae": sum(abs(scores[dimension] - target[dimension]) for dimension in DIMENSIONS) / 6,
            }
        )

    metrics: list[dict[str, Any]] = []
    for candidate in sorted({row["candidate_id"] for row in index.values()}):
        group_mae: dict[str, float] = {}
        for group_id in group_ids:
            values = [
                item["mae"]
                for item in observed
                if item["candidate_id"] == candidate and item["prompt_group_id"] == group_id
            ]
            if len(values) != 1:
                raise ValueError("replayed equal-group geometry drifted")
            group_mae[group_id] = values[0]
        metrics.append(
            {
                "candidate_id": candidate,
                "cells": 3,
                "equal_group_mae": sum(group_mae.values()) / 3,
                "group_mae": group_mae,
            }
        )
    metrics.sort(key=lambda row: (row["equal_group_mae"], row["candidate_id"]))
    if metrics != public["metrics"]:
        raise ValueError("portable replay metrics differ from publication")
    comparison = _derive_comparison(metrics)
    if comparison != public["comparison"]:
        raise ValueError("portable replay comparison differs from publication")
    return {
        **comparison,
        "cells": len(observed),
        "native_endpoint_contact_cardinality": "unproven",
        "provider_calls_made": 0,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Verify the portable public four-file binding, optionally replaying the private "
            "33-cell evidence from five explicitly supplied source paths."
        )
    )
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--collector", type=Path)
    parser.add_argument("--materialization-root", type=Path)
    parser.add_argument("--frozen-successor", type=Path)
    parser.add_argument("--hanna-csv", type=Path)
    args = parser.parse_args(argv)
    supplied = [
        args.output_root,
        args.collector,
        args.materialization_root,
        args.frozen_successor,
        args.hanna_csv,
    ]
    if any(value is not None for value in supplied) and not all(value is not None for value in supplied):
        parser.error("provide all five private replay paths or none")
    value = (
        replay(
            output_root=args.output_root,
            collector=args.collector,
            materialization_root=args.materialization_root,
            frozen_successor=args.frozen_successor,
            hanna_csv=args.hanna_csv,
        )
        if all(value is not None for value in supplied)
        else {
            "binding_scope": sorted(PUBLIC_FILES),
            "external_authenticity": "not_claimed",
            "provider_calls_made": 0,
            "publication_internal_binding": "verified",
        }
    )
    print(canonical(value).decode(), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
