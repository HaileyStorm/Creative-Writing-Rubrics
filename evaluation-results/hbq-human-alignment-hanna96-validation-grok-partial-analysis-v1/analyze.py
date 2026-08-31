#!/usr/bin/env python3
"""Strict partial, endpoint-specific analysis of the closed Fresh96 Grok root."""
from __future__ import annotations

import argparse
import base64
import hashlib
import importlib.util
import json
import math
import os
import stat
import sys
from collections import defaultdict
from collections.abc import Mapping
from contextlib import contextmanager
from pathlib import Path
from types import ModuleType
from typing import Any

HERE = Path(__file__).resolve().parent
STUDY_ID = "hbq-human-alignment-hanna96-validation-grok-partial-analysis-v1"
EXECUTOR = HERE.parent / "hbq-human-alignment-hanna96-validation-grok-exec-v1" / "executor.py"
FREEZE = HERE.parent / "hbq-human-alignment-hanna96-validation-freeze-v1" / "study.py"
EXECUTOR_SHA256 = "91fa17d51b5f5449998884cda7fe7cf26992dc96931726153f8a308aa4c2ea5b"
FREEZE_SHA256 = "d8b99c651cfbc0c04207101a6ad15373168a5ffad3711f7d17fb589e8a13542e"
SCHEDULE_SHA256 = "639c34bb1d07266759280249b6b74a51c05d51f60ed27eb3aed0b2ea6c3bfee2"
SOURCE_COMMIT = "c280729bd2382fadd442b023845239b1056348e5"
AMBIGUOUS_CELL = "h96-cebcfbdcdf2ffcf72ffb"
DIMENSIONS = ("Relevance", "Coherence", "Empathy", "Surprise", "Engagement", "Complexity")
SUCCESS_FILES = {
    "authorization-acknowledgement.json", "disclosure.json", "effective-settings.json",
    "execution-receipt.json", "launch-intent.json", "native-request.bin", "native-response.bin",
    "outbound-payload.json", "prepared.json", "prompt-request.bin", "response-schema.json",
    "result.json", "runtime-identity.json", "zero-charge-route-proof.json", "responses",
}
AMBIGUOUS_FILES = {
    "authorization-acknowledgement.json", "disclosure.json", "launch-intent.json",
    "outbound-payload.json", "prepared.json", "prompt-request.bin", "response-schema.json",
    "result.json", "zero-charge-route-proof.json", "responses",
}


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def sha256(value: bytes | Any) -> str:
    return hashlib.sha256(value if isinstance(value, bytes) else canonical(value)).hexdigest()


def _plain(path: Path, directory: bool | None = None) -> None:
    info = os.lstat(path)
    if stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)):
        raise ValueError("reparsed filesystem artifact")
    if directory is not None and stat.S_ISDIR(info.st_mode) != directory:
        raise ValueError("unexpected filesystem artifact type")


def _safe(path: Path) -> Path:
    absolute = Path(os.path.abspath(path))
    current = Path(absolute.anchor)
    if current.exists():
        _plain(current, directory=True)
    for part in absolute.parts[1:]:
        current /= part
        if current.exists():
            _plain(current, directory=current != absolute or current.is_dir())
    return absolute


def stable(path: Path) -> bytes:
    path = _safe(Path(path))
    _plain(path, directory=False)
    before = os.lstat(path)
    with path.open("rb") as handle:
        opened, raw, after = os.fstat(handle.fileno()), handle.read(), os.fstat(handle.fileno())
    identity = lambda item: (item.st_dev, item.st_ino, item.st_size)
    if identity(before) != identity(opened) or identity(opened) != identity(after):
        raise ValueError("stable read drift")
    return raw


def strict(path: Path, label: str) -> dict[str, Any]:
    def no_duplicates(items: list[tuple[str, Any]]) -> dict[str, Any]:
        output: dict[str, Any] = {}
        for key, value in items:
            if key in output:
                raise ValueError("duplicate JSON key")
            output[key] = value
        return output

    raw = stable(path)
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=no_duplicates, parse_constant=lambda token: (_ for _ in ()).throw(ValueError(token)))
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise ValueError(f"invalid {label}") from error
    if not isinstance(value, dict) or canonical(value) != raw:
        raise ValueError(f"noncanonical {label}")
    return value


def _require_hash(path: Path, expected: str, label: str) -> None:
    if sha256(stable(path)) != expected:
        raise ValueError(f"pinned {label} drifted")


def _load_executor() -> ModuleType:
    raw = stable(EXECUTOR)
    if sha256(raw) != EXECUTOR_SHA256:
        raise ValueError("pinned Grok execution wrapper drifted")
    spec = importlib.util.spec_from_file_location("_hanna96_partial_pinned_executor", EXECUTOR)
    if spec is None or spec.loader is None:
        raise ValueError("cannot load pinned Grok execution wrapper")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(spec.name, None)
    if stable(EXECUTOR) != raw:
        raise ValueError("pinned Grok execution wrapper changed during load")
    return module


@contextmanager
def _pinned_admission(schedule: Mapping[str, Any]):
    executor = _load_executor()
    runtime = executor._runtime()
    source = runtime.lifecycle()
    live = source.live()
    original_schedule, original_study_id = source.schedule, source.STUDY_ID
    source.schedule = lambda **_ignored: (live, dict(schedule))
    source.STUDY_ID = executor.STUDY_ID
    try:
        yield source, live
    finally:
        source.schedule, source.STUDY_ID = original_schedule, original_study_id


def _inventory(root: Path, expected: set[str], label: str) -> None:
    _plain(root, directory=True)
    if {entry.name for entry in root.iterdir()} != expected:
        raise ValueError(f"{label} inventory drifted")


def _fields(value: Mapping[str, Any], required: set[str], label: str) -> None:
    if set(value) != required:
        raise ValueError(f"{label} fields drifted")


def _scores(response: bytes) -> dict[str, float]:
    try:
        value = json.loads(response.decode("utf-8"), parse_constant=lambda token: (_ for _ in ()).throw(ValueError(token)))
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise ValueError("native response is invalid JSON") from error
    if not isinstance(value, Mapping) or not isinstance(value.get("structuredOutput"), Mapping):
        raise TypeError("native response lacks structured output")
    output = value["structuredOutput"]
    if set(output) != {"scores", "evidence", "coverage"}:
        raise ValueError("native structured output drifted")
    scores, evidence, coverage = output["scores"], output["evidence"], output["coverage"]
    if not isinstance(scores, Mapping) or not isinstance(evidence, Mapping) or not isinstance(coverage, Mapping) or set(scores) != set(DIMENSIONS) or set(evidence) != set(DIMENSIONS) or set(coverage) != set(DIMENSIONS):
        raise ValueError("native six-dimension output drifted")
    if any(type(scores[key]) not in (int, float) or not math.isfinite(scores[key]) or not 0 <= scores[key] <= 5 or not isinstance(evidence[key], str) or not evidence[key] or type(coverage[key]) is not bool for key in DIMENSIONS):
        raise ValueError("native response values drifted")
    return {key: float(scores[key]) for key in DIMENSIONS}


def _schedule(root: Path) -> dict[str, Any]:
    value = strict(root / "schedule.json", "schedule")
    if value.get("format_version") != 1 or value.get("study_id") != "hbq-human-alignment-hanna96-validation-freeze-v1" or value.get("kind") != "endpoint_neutral_fresh96_validation_schedule" or value.get("schedule_sha256") != SCHEDULE_SHA256 or sha256({key: item for key, item in value.items() if key != "schedule_sha256"}) != SCHEDULE_SHA256:
        raise ValueError("pinned Fresh96 schedule drifted")
    if value.get("geometry") != {"candidates": 2, "endpoint_neutral_logical_cells": 64, "groups": 16, "items": 32} or not isinstance(value.get("cells"), list) or len(value["cells"]) != 64:
        raise ValueError("Fresh96 schedule geometry drifted")
    cells = value["cells"]
    if len({row.get("cell_id") for row in cells if isinstance(row, Mapping)}) != 64 or any(not isinstance(row, Mapping) for row in cells):
        raise ValueError("Fresh96 cell identity drifted")
    return value


def _common(root: Path, row: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    prepared = strict(root / "prepared.json", "prepared cell")
    if prepared.get("study_id") != "hbq-human-alignment-hanna96-validation-grok-exec-v1" or prepared.get("schedule_sha256") != SCHEDULE_SHA256 or prepared.get("cell") != dict(row) or prepared.get("outbound_payload_sha256") != row.get("payload_sha256") or prepared.get("prompt_request_sha256") != row.get("payload_sha256"):
        raise ValueError("prepared cell binding drifted")
    try:
        payload = base64.b64decode(str(row.get("payload_base64")), validate=True)
    except (ValueError, TypeError) as error:
        raise ValueError("scheduled payload is invalid") from error
    if sha256(payload) != row.get("payload_sha256") or stable(root / "outbound-payload.json") != payload or stable(root / "prompt-request.bin") != payload:
        raise ValueError("outbound payload binding drifted")
    disclosure = strict(root / "disclosure.json", "disclosure")
    acknowledgement = strict(root / "authorization-acknowledgement.json", "acknowledgement")
    route_proof = strict(root / "zero-charge-route-proof.json", "route proof")
    if acknowledgement.get("cell_id") != row["cell_id"] or acknowledgement.get("disclosure_sha256") != sha256(stable(root / "disclosure.json")) or acknowledgement.get("acknowledgement_sha256") != "2fb371ff82b37fe22d238a223fc030ad7a7bb9a10b672719da081470d25dbe78" or disclosure.get("cell_id") != row["cell_id"] or disclosure.get("payload", {}).get("sha256") != row["payload_sha256"] or route_proof.get("cell_id") != row["cell_id"] or route_proof.get("route") != prepared.get("route"):
        raise ValueError("disclosure or route binding drifted")
    intent = strict(root / "launch-intent.json", "launch intent")
    if intent.get("cell_id") != row["cell_id"] or intent.get("study_id") != prepared["study_id"] or intent.get("prepared_sha256") != sha256(stable(root / "prepared.json")) or intent.get("outbound_payload_sha256") != row["payload_sha256"]:
        raise ValueError("launch intent binding drifted")
    return prepared, intent


def _success(root: Path, row: Mapping[str, Any], schedule: Mapping[str, Any], source: ModuleType, live: ModuleType, identities: set[tuple[str, str]]) -> float:
    _inventory(root, SUCCESS_FILES, "successful cell")
    prepared, _intent = _common(root, row)
    _inventory(root / "responses", {"batch-0001.attempt-0001.grok.envelope.json", "batch-0001.attempt-0001.prompt.txt"}, "successful response")
    response = stable(root / "native-response.bin")
    if response != stable(root / "responses" / "batch-0001.attempt-0001.grok.envelope.json"):
        raise ValueError("native envelope association drifted")
    receipt = strict(root / "execution-receipt.json", "execution receipt")
    identity = strict(root / "runtime-identity.json", "runtime identity")
    settings = strict(root / "effective-settings.json", "effective settings")
    if receipt.get("cell") != dict(row) or receipt.get("prepared_sha256") != sha256(stable(root / "prepared.json")) or receipt.get("launch_intent_sha256") != sha256(stable(root / "launch-intent.json")) or receipt.get("native_request_sha256") != sha256(stable(root / "native-request.bin")) or receipt.get("native_response_sha256") != sha256(response) or receipt.get("identity") != identity or receipt.get("identity_sha256") != sha256(identity) or receipt.get("effective_settings_sha256") != sha256(settings) or receipt.get("payload_sha256") != row["payload_sha256"]:
        raise ValueError("receipt/native association drifted")
    acknowledgement = strict(root / "authorization-acknowledgement.json", "acknowledgement")["acknowledgement_sha256"]
    source.validate_frozen_route(prepared["route"], prepared["route_evidence"])
    raw, prompt, schema = source.payload(row)
    request, admitted_response, admitted_identity, admitted_settings = source.admit(root, row, schedule, raw, prompt, schema, prepared["route"], prepared["route_evidence"], acknowledgement, live)
    if raw != stable(root / "outbound-payload.json") or prompt != stable(root / "prompt-request.bin") or schema != stable(root / "response-schema.json") or request != stable(root / "native-request.bin") or admitted_response != response or admitted_identity != identity or admitted_settings != settings:
        raise ValueError("pinned admission replay drifted")
    verified = live._validate_runner_result({"native_request_bytes": request, "native_response_bytes": admitted_response, "identity": admitted_identity, "effective_settings": admitted_settings}, prepared["route"], raw)
    if verified != (request, admitted_response, admitted_identity, admitted_settings):
        raise ValueError("runner receipt replay drifted")
    contact = (identity.get("request_id"), identity.get("session_id"))
    if not all(isinstance(value, str) and value for value in contact) or contact in identities or identity.get("provider") != "xai" or identity.get("requested_model") != "grok-4.6" or identity.get("reported_model") != "grok-4.6-build" or identity.get("tools_enabled") is not False:
        raise ValueError("native identity drifted")
    response_identity = json.loads(response.decode("utf-8"))
    if response_identity.get("requestId") != contact[0] or response_identity.get("sessionId") != contact[1]:
        raise ValueError("native receipt/envelope identity association drifted")
    identities.add(contact)
    result = strict(root / "result.json", "successful result")
    if result != {"cell_id": row["cell_id"], "format_version": 1, "kind": "provisional_normalized_nextwave_grok_scoring_received", "native_endpoint_contact_cardinality": "unproven", "process_launches": 1, "provider_calls_made": None, "receipt_sha256": sha256(stable(root / "execution-receipt.json")), "study_id": "hbq-human-alignment-hanna96-validation-grok-exec-v1"}:
        raise ValueError("successful result binding drifted")
    scores = _scores(response)
    return sum(abs(scores[key] - float(row["target"][key])) for key in DIMENSIONS) / len(DIMENSIONS)


def _ambiguous(root: Path, row: Mapping[str, Any]) -> None:
    _inventory(root, AMBIGUOUS_FILES, "ambiguous cell")
    _common(root, row)
    _inventory(root / "responses", {"batch-0001.attempt-0001.prompt.txt"}, "ambiguous response")
    result = strict(root / "result.json", "ambiguous result")
    expected = {"cell_id": row["cell_id"], "detail": "_ProviderAttemptFailure", "format_version": 1, "intent_sha256": sha256(stable(root / "launch-intent.json")), "kind": "reconcile_required_after_process_launch", "native_endpoint_contact_cardinality": "unknown", "process_launches": 1, "provider_calls_made": None, "retry_policy": "fresh_output_root_required_no_in_place_resend", "study_id": "hbq-human-alignment-hanna96-validation-grok-exec-v1"}
    if result != expected:
        raise ValueError("ambiguous result binding drifted")


def _metric(rows: list[tuple[str, str, str, float]], groups: set[str], label: str, baseline: str, descendant: str) -> dict[str, Any]:
    per_candidate: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for candidate, _item, group, mae in rows:
        per_candidate[candidate][group].append(mae)
    if set(per_candidate) != {baseline, descendant} or any(set(values) != groups for values in per_candidate.values()):
        raise ValueError("paired group coverage drifted")
    summary: dict[str, float] = {}
    for candidate, values in per_candidate.items():
        if any(not values[group] for group in groups):
            raise ValueError("paired group observation is missing")
        summary[candidate] = sum(sum(values[group]) / len(values[group]) for group in groups) / len(groups)
    return {"subset": label, "groups": len(groups), "paired_items": len({item for _candidate, item, group, _mae in rows if group in groups}), "baseline_equal_group_mae": summary[baseline], "descendant13_equal_group_mae": summary[descendant], "percent_reduction": (summary[baseline] - summary[descendant]) * 100 / summary[baseline]}


def analyze(source_root: Path) -> dict[str, Any]:
    """Parse one exact closed 64-cell root and emit its non-imputed 63-cell analysis."""
    _require_hash(EXECUTOR, EXECUTOR_SHA256, "Grok execution wrapper")
    _require_hash(FREEZE, FREEZE_SHA256, "Fresh96 freeze")
    root = _safe(Path(source_root))
    _plain(root, directory=True)
    schedule = _schedule(root)
    cells = {row["cell_id"]: dict(row) for row in schedule["cells"]}
    descendant = cells[AMBIGUOUS_CELL]["candidate_id"]
    baseline_candidates = {row["candidate_id"] for row in cells.values()} - {descendant}
    if len(baseline_candidates) != 1:
        raise ValueError("baseline/descendant identity drifted")
    baseline = next(iter(baseline_candidates))
    _inventory(root, {"schedule.json", ".claims", *cells}, "source root")
    claims = root / ".claims"
    _inventory(claims, set(cells), "claim root")
    observations: list[tuple[str, str, str, float]] = []
    identities: set[tuple[str, str]] = set()
    with _pinned_admission(schedule) as (source, live):
        for cell_id, row in cells.items():
            claim = claims / cell_id
            _inventory(claim, {"claim.json"}, "claim")
            if strict(claim / "claim.json", "claim").get("cell_id") != cell_id:
                raise ValueError("claim binding drifted")
            cell_root = root / cell_id
            if cell_id == AMBIGUOUS_CELL:
                _ambiguous(cell_root, row)
            else:
                observations.append((row["candidate_id"], row["item_id"], row["prompt_group_id"], _success(cell_root, row, schedule, source, live, identities)))
    if len(observations) != 63 or len(identities) != 63:
        raise ValueError("successful receipt coverage is not exactly 63")
    by_item: dict[str, list[tuple[str, str, str, float]]] = defaultdict(list)
    for row in observations:
        by_item[row[1]].append(row)
    paired = [row for values in by_item.values() if len(values) == 2 for row in values]
    if len(paired) != 62 or len(by_item) != 32 or any(len(values) not in {1, 2} for values in by_item.values()):
        raise ValueError("partial item pairing drifted")
    all_groups = {row[2] for row in paired}
    complete_groups = {group for group in all_groups if sum(1 for row in paired if row[2] == group) == 4}
    if len(all_groups) != 16 or len(complete_groups) != 15:
        raise ValueError("partial group geometry drifted")
    metrics = [_metric(paired, all_groups, "all_31_paired_items", baseline, descendant), _metric([row for row in paired if row[2] in complete_groups], complete_groups, "15_fully_complete_groups", baseline, descendant)]
    value = {"format_version": 1, "study_id": STUDY_ID, "kind": "strict_grok_fresh96_partial_validation_analysis", "source": {"source_commit": SOURCE_COMMIT, "schedule_sha256": SCHEDULE_SHA256, "execution_wrapper_sha256": EXECUTOR_SHA256, "freeze_sha256": FREEZE_SHA256}, "coverage": {"scheduled_cells": 64, "baseline_scheduled_cells": 32, "descendant13_scheduled_cells": 32, "receipt_backed_cells": 63, "baseline_receipt_backed_cells": 32, "descendant13_receipt_backed_cells": 31, "terminal_ambiguous_cells": 1, "paired_items": 31, "unpaired_items": 1, "paired_groups": 16, "fully_complete_groups": 15, "native_endpoint_contact_cardinality": "unproven"}, "metrics": metrics, "authority": {"endpoint": "grok-4.6", "imputation": "forbidden", "pooling": "forbidden", "selection": "none", "confirmation": "none", "generalization": "none", "runtime": "none"}, "interpretation": "Partial endpoint-specific analysis only: one descendant cell is terminally ambiguous and is excluded rather than imputed."}
    value["result_sha256"] = sha256(value)
    return value


def write_result(source_root: Path, output: Path) -> dict[str, Any]:
    if output.exists() or output.is_symlink():
        raise ValueError("result output must be fresh")
    _plain(output.parent, directory=True)
    value = analyze(source_root)
    with output.open("xb") as handle:
        handle.write(canonical(value))
        handle.flush()
        os.fsync(handle.fileno())
    return value


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--result-output", type=Path, required=True)
    args = parser.parse_args()
    write_result(args.source_root, args.result_output)
