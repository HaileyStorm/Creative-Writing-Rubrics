#!/usr/bin/env python3
"""Validate frozen Flash-Next planning identity without adapter execution."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
from typing import Any

HERE = Path(os.path.abspath(__file__)).parent
ROOT = HERE.parents[1]


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _assert_no_reparse_path(path: Path, label: str) -> None:
    absolute = Path(os.path.abspath(path))
    cursor = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        cursor = cursor / part
        if os.path.lexists(cursor):
            metadata = os.lstat(cursor)
            if stat.S_ISLNK(metadata.st_mode) or bool(getattr(metadata, "st_file_attributes", 0) & 0x400):
                raise ValueError(f"Flash-Next {label} contains a symlink or reparse point")


def _read_safe_bytes(path: Path, label: str) -> bytes:
    _assert_no_reparse_path(path, label)
    value = path.read_bytes()
    _assert_no_reparse_path(path, label)
    return value


def contract() -> dict[str, Any]:
    try:
        value = json.loads(_read_safe_bytes(HERE / "study-contract.json", "study contract").decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("Study contract bytes are malformed") from error
    if not isinstance(value, dict):
        raise ValueError("Study contract must be an object")
    unsigned = dict(value)
    digest = unsigned.pop("semantic_contract_sha256", None)
    if not isinstance(digest, str) or canonical_sha256(unsigned) != digest:
        raise ValueError("Canonical semantic-contract digest drifted")
    return value


def _asset_path(record: dict[str, Any]) -> Path:
    raw_path = record.get("path")
    if not isinstance(raw_path, str) or not raw_path or "\\" in raw_path:
        raise ValueError("Asset record shape drifted")
    candidate = ROOT / raw_path
    _assert_no_reparse_path(ROOT, "repository root")
    _assert_no_reparse_path(candidate, "repository asset")
    resolved_root = ROOT.resolve()
    resolved = candidate.resolve()
    try:
        resolved.relative_to(resolved_root)
    except ValueError as error:
        raise ValueError("Asset path escapes repository containment") from error
    return resolved


def _validate_asset(record: dict[str, Any]) -> None:
    if not {"path", "sha256", "bytes"}.issubset(record):
        raise ValueError("Asset record shape drifted")
    path = _asset_path(record)
    content = _read_safe_bytes(path, "repository asset")
    if not path.is_file() or len(content) != record["bytes"] or hashlib.sha256(content).hexdigest() != record["sha256"]:
        raise ValueError(f"Frozen asset binding drifted: {record['path']}")


def _expected_requests() -> list[dict[str, Any]]:
    identity = contract()["planning_identity"]
    requests: list[dict[str, Any]] = []
    for repetition, block in enumerate(identity["five_block_rotated_near_latin_schedule"], start=1):
        for method_id in block:
            for batch in range(1, identity["requests_per_repetition"][method_id] + 1):
                requests.append({"request_id": f"r{repetition}-{method_id}-{batch}", "repetition": repetition, "method_id": method_id, "batch_ordinal": batch})
    return requests


def _validate_rows(rows: list[Any]) -> None:
    spec = contract()
    identity = spec["planning_identity"]
    manifest = spec["method_input_manifest"]
    expected = _expected_requests()
    if len(rows) != manifest["artifact"]["rows"] or len(expected) != 45:
        raise ValueError("Method-input row count drifted")
    required = set(manifest["row_required_fields"])
    per_repetition: dict[int, list[str]] = {}
    geometry = identity["hbq_question_geometry"]
    for expected_request, row in zip(expected, rows, strict=True):
        if not isinstance(row, dict) or set(row) != required or row.get("format_version") != 1 or row.get("request") != expected_request:
            raise ValueError("Method-input row schema or order drifted")
        if row.get("source_artifact") != identity["source_artifact"] or row.get("condition_labels") != identity["condition_labels"]:
            raise ValueError("Method-input planning identity drifted")
        ids = row.get("question_ids")
        if not isinstance(ids, list) or len(set(ids)) != len(ids) or not all(isinstance(item, str) and item for item in ids):
            raise ValueError("Method-input question IDs are malformed")
        if expected_request["method_id"] != "hbq":
            if ids:
                raise ValueError("Native method row unexpectedly carries HBQ question IDs")
            continue
        expected_count = min(geometry["batch_size"], geometry["question_count"] - (expected_request["batch_ordinal"] - 1) * geometry["batch_size"])
        if len(ids) != expected_count:
            raise ValueError("Method-input HBQ question coverage drifted")
        per_repetition.setdefault(expected_request["repetition"], []).extend(ids)
    if set(per_repetition) != {1, 2, 3, 4, 5} or any(len(ids) != geometry["question_count"] or len(set(ids)) != len(ids) for ids in per_repetition.values()):
        raise ValueError("Method-input HBQ repetition coverage drifted")
    if len({tuple(ids) for ids in per_repetition.values()}) != 1:
        raise ValueError("Method-input HBQ repetition identity drifted")


def _read_method_inputs() -> list[Any]:
    spec = contract()
    artifact = spec["method_input_manifest"]["artifact"]
    path = _asset_path(artifact)
    content = _read_safe_bytes(path, "method-input artifact")
    if len(content) != artifact["bytes"] or hashlib.sha256(content).hexdigest() != artifact["sha256"]:
        raise ValueError("Method-input artifact binding drifted")
    try:
        rows = [json.loads(line) for line in content.decode("utf-8").splitlines()]
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("Method-input artifact bytes are malformed") from error
    if not rows or b"\n\n" in content or not content.endswith(b"\n"):
        raise ValueError("Method-input artifact line framing drifted")
    _validate_rows(rows)
    return rows


def _validate_adapter_assets(spec: dict[str, Any]) -> None:
    manifest_record = spec.get("adapter_asset_manifest")
    if not isinstance(manifest_record, dict) or set(manifest_record) != {"path", "sha256", "bytes"}:
        raise ValueError("Adapter asset-manifest binding drifted")
    manifest_path = _asset_path(manifest_record)
    content = _read_safe_bytes(manifest_path, "adapter asset manifest")
    if len(content) != manifest_record["bytes"] or hashlib.sha256(content).hexdigest() != manifest_record["sha256"]:
        raise ValueError("Adapter asset-manifest bytes drifted")
    try:
        manifest = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("Adapter asset manifest is malformed") from error
    if not isinstance(manifest, dict) or set(manifest) != {"format_version", "adapter", "geometry", "parser", "runtime_policy", "study", "tests"} or manifest.get("format_version") != 2:
        raise ValueError("Adapter asset manifest shape drifted")
    for key in ("adapter", "study", "runtime_policy"):
        value = manifest[key]
        if not isinstance(value, dict) or set(value) != {"path", "sha256", "bytes"}:
            raise ValueError("Adapter asset binding shape drifted")
        _validate_asset(value)
    geometry = manifest["geometry"]
    if not isinstance(geometry, list) or len(geometry) != 2:
        raise ValueError("Adapter geometry asset binding drifted")
    for value in geometry:
        if not isinstance(value, dict) or set(value) != {"path", "sha256", "bytes"}:
            raise ValueError("Adapter geometry asset shape drifted")
        _validate_asset(value)
    tests = manifest["tests"]
    if not isinstance(tests, list) or len(tests) != 2:
        raise ValueError("Adapter test asset binding drifted")
    for value in tests:
        if not isinstance(value, dict) or set(value) != {"path", "sha256", "bytes"}:
            raise ValueError("Adapter test asset shape drifted")
        _validate_asset(value)
    if manifest["parser"] != {"module": "adapter.py canonical JSON/URL parser", "asset_sha256": manifest["adapter"]["sha256"]}:
        raise ValueError("Adapter parser asset binding drifted")
    runtime_policy = json.loads(_read_safe_bytes(_asset_path(manifest["runtime_policy"]), "runtime policy").decode("utf-8"))
    if runtime_policy != {"format_version": 1, "execution_state": "offline_only", "python": {"implementation": "CPython", "minimum_version": "3.12"}, "platform": "Linux", "network": {"dispatch": "disabled", "provider_calls": 0}, "response_classification": "untrusted_raw_only", "pairing": "disabled_pending_independent_linux_evidence"}:
        raise ValueError("Adapter runtime policy drifted")


def nonpromotion_status() -> dict[str, Any]:
    return {"state": "OFFLINE_ADAPTER_ONLY", "execution_ready": False, "pairable": False, "reason": "the offline package has no network dispatch or native-provenance authority; owner assertions and raw bytes are nonpromotable pending a separately evidenced Linux execution path"}


def validate() -> dict[str, Any]:
    spec = contract()
    if spec.get("status") != "provider_free_scaffold" or spec.get("frozen_before_execution") is not True:
        raise ValueError("Flash-Next study must remain provider-free")
    root = spec.get("canonical_root")
    if root != {"format_version": 1, "identity": "207b2e43f13821ea85298913614ebd42ccac320d65c5dc17b3d8a89df323b06d", "role": "per-explicitly-bound-offline-root-v1"}:
        raise ValueError("Canonical external-root identity drifted")
    _validate_asset(spec["planning_identity"]["source_artifact"])
    _validate_adapter_assets(spec)
    if len(_read_method_inputs()) != 45:
        raise ValueError("Frozen method-input geometry drifted")
    return {"study_id": spec["study_id"], "conditions": len(spec["planning_identity"]["condition_labels"]), "repetitions": spec["planning_identity"]["repetitions"], "provider_calls": 0, **nonpromotion_status()}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("validate",))
    parser.parse_args()
    print(json.dumps(validate(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
