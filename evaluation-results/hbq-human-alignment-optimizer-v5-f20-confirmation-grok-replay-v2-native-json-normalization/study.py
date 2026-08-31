#!/usr/bin/env python3
"""Replay V1's completed confirmation collector with JSON-format normalization only."""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import math
import os
import stat
from pathlib import Path
from typing import Any, Mapping


HERE = Path(__file__).resolve().parent
STUDY_ID = "hbq-human-alignment-optimizer-v5-f20-confirmation-grok-replay-v2-native-json-normalization"
V1_COMMIT = "ab8cf7d6d53e353ccf8fc0c68091d1fb3372cec0"
V1 = HERE.parent / "hbq-human-alignment-optimizer-v5-f20-confirmation-grok-exec-v1"
V1_HASHES = {
    V1 / "executor.py": "5e5cf531a4f8a224164f032d5bb68e11c919d2f305cf7fdd5ba0c08f594b323a",
    V1 / "README.md": "4aa505cd952ef2416bb15662bb0ba842dc387df72fcd8174eff52770e971cabc",
    V1 / "study-contract.json": "4a8daee0ca5e72bb6b8c9de2b968e32f5946ee4c452cedfea482a63bd6592dee",
    HERE.parents[1] / "tests" / "test_hbq_human_alignment_optimizer_v5_f20_confirmation_grok_exec_v1.py": "33f4a8e51b64206b808b8da3c2355e9ebabca94b613df9a8767a9f22bfe71f5d",
}
COLLECTOR_SHA256 = "ea14fc2341d74e5c794f047ad10871d1157d774a6605d6a8265efb57b6dfbbf5"
SCHEDULE_SHA256 = "cbdf783b7fa1306e89c9aee9b7f63d9eae2a8ea8c8ae4bcb3752ea14c18ceb6e"
DIMENSIONS = ("Relevance", "Coherence", "Empathy", "Surprise", "Engagement", "Complexity")
RESPONSE_FIELDS = {"modelUsage", "num_turns", "requestId", "sessionId", "stopReason", "structuredOutput", "text", "thought", "total_cost_usd", "total_cost_usd_ticks", "usage"}


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def sha256(raw: bytes | Any) -> str:
    return hashlib.sha256(raw if isinstance(raw, bytes) else canonical(raw)).hexdigest()


def _plain(path: Path, directory: bool | None = None) -> None:
    info = os.lstat(path)
    if stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)):
        raise ValueError("unsafe/reparsed path")
    if directory is not None and stat.S_ISDIR(info.st_mode) != directory:
        raise ValueError("unexpected path type")


def stable(path: Path) -> bytes:
    _plain(path, directory=False)
    before = os.lstat(path)
    with path.open("rb") as handle:
        opened, raw, after = os.fstat(handle.fileno()), handle.read(), os.fstat(handle.fileno())
    if (before.st_dev, before.st_ino, before.st_size) != (opened.st_dev, opened.st_ino, opened.st_size) or (opened.st_dev, opened.st_ino, opened.st_size) != (after.st_dev, after.st_ino, after.st_size):
        raise ValueError("stable read drift")
    return raw


def strict(raw: bytes, label: str, *, canonical_required: bool = True) -> dict[str, Any]:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in items:
            if key in value:
                raise ValueError("duplicate JSON key")
            value[key] = item
        return value
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs, parse_constant=lambda token: (_ for _ in ()).throw(ValueError(token)))
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise ValueError(f"invalid {label}") from error
    if not isinstance(value, dict) or canonical_required and canonical(value) != raw:
        raise ValueError(f"noncanonical {label}")
    return value


def _pinned_v1() -> None:
    for path, digest in V1_HASHES.items():
        if sha256(stable(path)) != digest:
            raise ValueError("pinned V1 dependency drifted")


def _response(raw: bytes, identity: Mapping[str, Any]) -> dict[str, Any]:
    outer = strict(raw, "native response", canonical_required=False)
    if set(outer) != RESPONSE_FIELDS or outer.get("stopReason") != "end_turn" or outer.get("requestId") != identity.get("request_id") or outer.get("sessionId") != identity.get("session_id"):
        raise ValueError("native response identity or terminal state drifted")
    if not isinstance(outer["text"], str) or not isinstance(outer["structuredOutput"], Mapping):
        raise ValueError("native response output surface drifted")
    try:
        text = strict(outer["text"].encode("utf-8"), "native response text", canonical_required=False)
    except ValueError as error:
        raise ValueError("native response text is not JSON") from error
    output = dict(outer["structuredOutput"])
    if text != output or set(output) != {"scores", "evidence", "coverage"}:
        raise ValueError("native response text/schema disagreement")
    scores, evidence, coverage = output["scores"], output["evidence"], output["coverage"]
    if not isinstance(scores, Mapping) or not isinstance(evidence, Mapping) or not isinstance(coverage, Mapping) or set(scores) != set(DIMENSIONS) or set(evidence) != set(DIMENSIONS) or set(coverage) != set(DIMENSIONS):
        raise ValueError("native response dimension schema drifted")
    for dimension in DIMENSIONS:
        score = scores[dimension]
        if type(score) not in {int, float} or not math.isfinite(score) or not 0 <= score <= 5 or not isinstance(evidence[dimension], str) or not evidence[dimension] or type(coverage[dimension]) is not bool:
            raise ValueError("native response value schema drifted")
    return {"scores": {dimension: float(scores[dimension]) for dimension in DIMENSIONS}, "coverage_complete": all(coverage[dimension] for dimension in DIMENSIONS), "raw_sha256": sha256(raw)}


def _schedule(root: Path) -> dict[str, Any]:
    schedule = strict(stable(root / "schedule.json"), "persisted schedule")
    if schedule.get("schedule_sha256") != SCHEDULE_SHA256 or schedule.get("study_id") != "hbq-human-alignment-optimizer-v5-f20-confirmation-freeze-v1" or not isinstance(schedule.get("cells"), list) or len(schedule["cells"]) != 38:
        raise ValueError("confirmation schedule drifted")
    body = dict(schedule)
    declared = body.pop("schedule_sha256", None)
    if sha256(body) != declared:
        raise ValueError("confirmation schedule commitment drifted")
    cells = schedule["cells"]
    if len({row.get("cell_id") for row in cells if isinstance(row, Mapping)}) != 38:
        raise ValueError("confirmation cell geometry drifted")
    return schedule


def _receipt(root: Path, collector_cell: Mapping[str, Any], schedule_cell: Mapping[str, Any], acknowledgement: str, route: Mapping[str, Any], evidence: Mapping[str, Any]) -> tuple[bytes, bytes, dict[str, Any], dict[str, Any]]:
    required = {"cell_id", "payload_base64", "payload_sha256", "native_request_base64", "native_request_sha256", "native_response_base64", "native_response_sha256", "identity", "effective_settings", "effective_settings_sha256"}
    if set(collector_cell) != required or collector_cell.get("cell_id") != schedule_cell.get("cell_id") or collector_cell.get("payload_base64") != schedule_cell.get("payload_base64") or collector_cell.get("payload_sha256") != schedule_cell.get("payload_sha256"):
        raise ValueError("collector schedule binding drifted")
    try:
        request, response = base64.b64decode(collector_cell["native_request_base64"], validate=True), base64.b64decode(collector_cell["native_response_base64"], validate=True)
    except (TypeError, ValueError) as error:
        raise ValueError("collector native bytes are malformed") from error
    identity, settings = collector_cell.get("identity"), collector_cell.get("effective_settings")
    if not isinstance(identity, Mapping) or not isinstance(settings, Mapping) or collector_cell.get("native_request_sha256") != sha256(request) or collector_cell.get("native_response_sha256") != sha256(response) or collector_cell.get("effective_settings_sha256") != sha256(settings):
        raise ValueError("collector byte/settings hash drifted")
    if stable(root / "native-request.bin") != request or stable(root / "native-response.bin") != response or strict(stable(root / "runtime-identity.json"), "runtime identity") != identity or strict(stable(root / "effective-settings.json"), "effective settings") != settings:
        raise ValueError("collector differs from immutable V1 receipt bytes")
    prepared = strict(stable(root / "prepared.json"), "prepared")
    stored_ack = strict(stable(root / "authorization-acknowledgement.json"), "acknowledgement").get("acknowledgement_sha256")
    receipt = strict(stable(root / "execution-receipt.json"), "execution receipt")
    if stored_ack != acknowledgement or prepared.get("route") != route or prepared.get("route_evidence") != evidence or receipt.get("cell") != schedule_cell or receipt.get("native_request_sha256") != sha256(request) or receipt.get("native_response_sha256") != sha256(response) or receipt.get("identity") != identity or receipt.get("effective_settings_sha256") != sha256(settings):
        raise ValueError("V1 receipt binding drifted")
    payload = base64.b64decode(schedule_cell["payload_base64"], validate=True)
    if strict(request, "native request", canonical_required=False) != {"prompt": payload.decode("utf-8")}:
        raise ValueError("native request payload drifted")
    return request, response, dict(identity), dict(settings)


def replay(*, output_root: Path, collector_path: Path) -> dict[str, Any]:
    _pinned_v1()
    root = Path(output_root)
    schedule = _schedule(root)
    raw_collector = stable(Path(collector_path))
    if sha256(raw_collector) != COLLECTOR_SHA256:
        raise ValueError("collector hash is not the pinned V1 evidence")
    collector = strict(raw_collector, "collector")
    expected = {"format_version", "study_id", "kind", "schedule_sha256", "authorization_acknowledgement_sha256", "route", "route_evidence", "cells", "native_endpoint_contact_cardinality", "provider_calls_made", "process_launches"}
    if set(collector) != expected or collector.get("study_id") != "hbq-human-alignment-optimizer-v5-f20-confirmation-grok-exec-v1" or collector.get("kind") != "complete_38_confirmation_grok_receipts_cardinality_unproven" or collector.get("schedule_sha256") != SCHEDULE_SHA256 or collector.get("native_endpoint_contact_cardinality") != "unproven" or collector.get("provider_calls_made") != 0 or collector.get("process_launches") != 0 or not isinstance(collector.get("authorization_acknowledgement_sha256"), str) or not isinstance(collector.get("route"), Mapping) or not isinstance(collector.get("route_evidence"), Mapping) or not isinstance(collector.get("cells"), list) or len(collector["cells"]) != 38:
        raise ValueError("collector contract drifted")
    index = {row["cell_id"]: row for row in schedule["cells"]}
    observations: list[dict[str, Any]] = []
    identities: set[tuple[str, str]] = set()
    for supplied in collector["cells"]:
        if not isinstance(supplied, Mapping):
            raise ValueError("collector cell is invalid")
        cell_id = supplied.get("cell_id")
        schedule_cell = index.get(cell_id)
        if schedule_cell is None:
            raise ValueError("collector cell is outside frozen schedule")
        _request, response, identity, _settings = _receipt(root / cell_id, supplied, schedule_cell, collector["authorization_acknowledgement_sha256"], collector["route"], collector["route_evidence"])
        contact = identity.get("request_id"), identity.get("session_id")
        if not all(isinstance(value, str) and value for value in contact) or contact in identities:
            raise ValueError("native identity drifted or duplicated")
        identities.add(contact)
        normalized = _response(response, identity)
        mae = sum(abs(normalized["scores"][dimension] - float(schedule_cell["target"][dimension])) for dimension in DIMENSIONS) / len(DIMENSIONS)
        observations.append({"candidate_id": schedule_cell["candidate_id"], "item_id": schedule_cell["item_id"], "prompt_group_id": schedule_cell["prompt_group_id"], "mae": mae, "coverage_complete": normalized["coverage_complete"], "native_response_sha256": normalized["raw_sha256"]})
    if {row["cell_id"] for row in collector["cells"]} != set(index):
        raise ValueError("collector is partial or has duplicate cells")
    metrics = []
    for candidate in sorted({row["candidate_id"] for row in observations}):
        groups = {group: [row["mae"] for row in observations if row["candidate_id"] == candidate and row["prompt_group_id"] == group] for group in sorted({row["prompt_group_id"] for row in observations})}
        if len(groups) != 8 or any(not values for values in groups.values()):
            raise ValueError("confirmation group geometry drifted")
        group_mae = {group: sum(values) / len(values) for group, values in groups.items()}
        metrics.append({"candidate_id": candidate, "confirmation_group_weighted_mae": sum(group_mae.values()) / len(group_mae), "group_mae": group_mae, "items": 19, "cells": 19, "coverage_incomplete_cells": sum(not row["coverage_complete"] for row in observations if row["candidate_id"] == candidate)})
    metrics.sort(key=lambda value: value["candidate_id"])
    if len(metrics) != 2:
        raise ValueError("confirmation candidate geometry drifted")
    baseline = next((row for row in metrics if row["candidate_id"] == "candidate-102cc7f06c9a99a7"), None)
    descendant = next((row for row in metrics if row["candidate_id"] == "broader-nextwave-13-missing_evidence_not_no"), None)
    if baseline is None or descendant is None:
        raise ValueError("frozen baseline/descendant binding drifted")
    delta = descendant["confirmation_group_weighted_mae"] - baseline["confirmation_group_weighted_mae"]
    value = {"format_version": 1, "study_id": STUDY_ID, "kind": "independently_replayed_confirmation_grok_group_weighted_mae_native_json_normalization", "pinned_v1_commit": V1_COMMIT, "collector_sha256": sha256(raw_collector), "schedule_sha256": SCHEDULE_SHA256, "metrics": metrics, "comparison": {"baseline_candidate_id": baseline["candidate_id"], "descendant_candidate_id": descendant["candidate_id"], "descendant_minus_baseline_mae": delta, "relative_mae_reduction": -delta / baseline["confirmation_group_weighted_mae"]}, "native_endpoint_contact_cardinality": "unproven", "authority": {"confirmation": "measurement_only", "selection": "none", "promotion": "none", "runtime": "none", "sol": "out_of_scope"}, "claim": "CONFIRMATION_MEASUREMENT_ONLY; Grok endpoint evidence is not pooled with Sol and does not establish generalization."}
    value["result_internal_sha256"] = sha256(value)
    return value


def write_result(*, output_root: Path, collector_path: Path, result_path: Path) -> dict[str, Any]:
    if result_path.exists() or result_path.is_symlink():
        raise ValueError("result path must be fresh")
    value = replay(output_root=output_root, collector_path=collector_path)
    _plain(result_path.parent, directory=True)
    with result_path.open("xb") as handle:
        handle.write(canonical(value))
        handle.flush()
        os.fsync(handle.fileno())
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--collector", type=Path, required=True)
    parser.add_argument("--result", type=Path)
    args = parser.parse_args(argv)
    value = write_result(output_root=args.output_root, collector_path=args.collector, result_path=args.result) if args.result else replay(output_root=args.output_root, collector_path=args.collector)
    print(canonical(value).decode("utf-8"), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
