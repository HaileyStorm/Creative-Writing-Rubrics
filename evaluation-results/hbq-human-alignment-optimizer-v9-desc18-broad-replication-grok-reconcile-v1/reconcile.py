#!/usr/bin/env python3
"""Provider-free reconciliation of the immutable desc18 Grok response wave."""
from __future__ import annotations

import argparse
import base64
import hashlib
import importlib.util
import json
import math
import os
import re
import stat
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path
from types import ModuleType
from typing import Any

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
STUDY_ID = "hbq-human-alignment-optimizer-v9-desc18-broad-replication-grok-reconcile-v1"
SOURCE_STUDY_ID = "hbq-human-alignment-optimizer-v9-desc18-broad-replication-grok-exec-v1"
SOURCE_ROOT_NAME = "cwr-desc18-broad-grok-4d3b2ef-20260901a"
SOURCE_COMMIT = "4d3b2ef20f5fad4ea0974e888f37550d4b8480f2"
SOURCE = HERE.parent / "hbq-human-alignment-optimizer-v9-desc18-broad-replication-grok-exec-v1"
SOURCE_HASHES = {
    SOURCE / "executor.py": "d719d484fabc12110fe36f61c379edf8d15aa701f97f025d1ff2ac24f1d2f4a4",
    SOURCE / "README.md": "ebd7397922aa57e043f54f4facf85e0a513020b318c7b56f8aac49a3bc43b0b4",
    SOURCE / "study-contract.json": "43a41a10f2a56e8518bd34fb265a870d55e5d8c58a9227c11f05618b9b50ac77",
}
FREEZE_COMMIT = "83d7be718c99c1135302ccb4f8d339a4c68f292f"
FREEZE_SCHEDULE_SHA256 = "1e45510b99e328388ea663ef42523d202322011959ad7f0e62629c3ec8075dfa"
ACKNOWLEDGEMENT_SHA256 = "2fb371ff82b37fe22d238a223fc030ad7a7bb9a10b672719da081470d25dbe78"
DIMENSIONS = ("Relevance", "Coherence", "Empathy", "Surprise", "Engagement", "Complexity")
RESPONSE_FIELDS = {"modelUsage", "num_turns", "requestId", "sessionId", "stopReason", "structuredOutput", "text", "thought", "total_cost_usd", "total_cost_usd_ticks", "usage"}
PREPARED_FILES = {"authorization-acknowledgement.json", "disclosure.json", "outbound-payload.json", "prepared.json", "prompt-request.bin", "response-schema.json", "zero-charge-route-proof.json"}
CELL_FILES = PREPARED_FILES | {"launch-intent.json", "result.json", "responses"}
RESPONSE_FILES = {"batch-0001.attempt-0001.grok.envelope.json", "batch-0001.attempt-0001.prompt.txt"}


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def sha256(value: bytes | Any) -> str:
    return hashlib.sha256(value if isinstance(value, bytes) else canonical(value)).hexdigest()


def _plain(path: Path, *, directory: bool | None = None) -> None:
    info = os.lstat(path)
    if stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)):
        raise ValueError("unsafe/reparsed path")
    if directory is not None and stat.S_ISDIR(info.st_mode) != directory:
        raise ValueError("unexpected path type")


def safe(path: Path) -> Path:
    absolute = Path(os.path.abspath(path))
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current /= part
        if current.exists() or current.is_symlink():
            _plain(current, directory=True if current != absolute else None)
    return absolute


def stable(path: Path) -> bytes:
    path = safe(path)
    _plain(path, directory=False)
    before = os.lstat(path)
    with path.open("rb") as handle:
        opened, raw, after = os.fstat(handle.fileno()), handle.read(), os.fstat(handle.fileno())
    key = lambda item: (item.st_dev, item.st_ino, stat.S_IFMT(item.st_mode), item.st_size)
    if key(before) != key(opened) or key(opened) != key(after):
        raise ValueError("stable read drift")
    return raw


def strict(raw: bytes, label: str, *, canonical_required: bool = True) -> dict[str, Any]:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in items:
            if key in value:
                raise ValueError(f"duplicate key in {label}")
            value[key] = item
        return value

    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs, parse_constant=lambda token: (_ for _ in ()).throw(ValueError(token)))
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise ValueError(f"invalid {label}") from error
    if not isinstance(value, dict) or canonical_required and canonical(value) != raw:
        raise ValueError(f"noncanonical {label}")
    return value


def _blob(path: Path) -> bytes:
    relative = path.relative_to(REPO).as_posix()
    result = subprocess.run(["git", "-C", str(REPO), "show", f"{SOURCE_COMMIT}:{relative}"], capture_output=True, check=False)
    if result.returncode:
        raise ValueError("pinned source blob is absent")
    return result.stdout


def source_executor() -> ModuleType:
    for path, digest in SOURCE_HASHES.items():
        raw = stable(path)
        if sha256(raw) != digest or _blob(path) != raw:
            raise ValueError("pinned source executor package drifted")
    path = SOURCE / "executor.py"
    spec = importlib.util.spec_from_file_location("_desc18_reconcile_source", path)
    if spec is None or spec.loader is None:
        raise ValueError("cannot load source executor")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(spec.name, None)
    return module


def _inventory(root: Path, expected: set[str], *, directories: set[str] | None = None) -> None:
    root = safe(root)
    _plain(root, directory=True)
    children = list(root.iterdir())
    if {item.name for item in children} != expected:
        raise ValueError("inventory drifted")
    directory_names = directories or set()
    for item in children:
        _plain(item, directory=item.name in directory_names)


def _nonnegative_number(value: Any, label: str) -> float:
    if type(value) not in {int, float} or not math.isfinite(float(value)) or value < 0:
        raise ValueError(f"native response {label} telemetry drifted")
    return float(value)


def _response(raw: bytes, route: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    envelope = strict(raw, "native response", canonical_required=False)
    request_id, session_id = envelope.get("requestId"), envelope.get("sessionId")
    reported_model = route.get("reported_model")
    if (set(envelope) != RESPONSE_FIELDS or envelope.get("stopReason") != "end_turn"
            or not isinstance(request_id, str) or not request_id or not isinstance(session_id, str) or not session_id
            or envelope.get("num_turns") != 1 or not isinstance(reported_model, str)):
        raise ValueError("native response identity or terminal state drifted")
    structured = envelope.get("structuredOutput")
    if not isinstance(envelope.get("text"), str) or not isinstance(structured, Mapping):
        raise TypeError("native response output surface drifted")
    text = strict(envelope["text"].encode("utf-8"), "native response text", canonical_required=False)
    if text != structured or set(structured) != {"scores", "evidence", "coverage"}:
        raise ValueError("native response text/schema disagreement")
    scores, evidence, coverage = structured["scores"], structured["evidence"], structured["coverage"]
    if not all(isinstance(item, Mapping) and set(item) == set(DIMENSIONS) for item in (scores, evidence, coverage)):
        raise ValueError("native response dimension schema drifted")
    for dimension in DIMENSIONS:
        score, note, covered = scores[dimension], evidence[dimension], coverage[dimension]
        normalized = " ".join(note.split()).casefold() if isinstance(note, str) else ""
        if type(score) not in {int, float} or not math.isfinite(float(score)) or not 0 <= float(score) <= 5:
            raise ValueError("native response score drifted")
        if (not normalized or normalized in {"x", "n/a", "none", "missing", "redacted"} or "placeholder" in normalized
                or re.search(r"\b(?:search(?:ing)?|look(?:ing)?|inspect(?:ing)?) (?:the )?workspace\b", normalized)
                or re.search(r"\bworkspace (?:search|lookup)\b", normalized)):
            raise ValueError("native response evidence drifted")
        if type(covered) is not bool:
            raise ValueError("native response coverage drifted")
    if all(float(scores[dimension]) == 0 for dimension in DIMENSIONS):
        raise ValueError("native response all-zero score vector")
    usage = envelope.get("usage")
    usage_keys = {"input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens", "reasoning_tokens", "total_tokens"}
    if not isinstance(usage, Mapping) or set(usage) != usage_keys or any(type(usage[key]) is not int or usage[key] < 0 for key in usage_keys) or usage["input_tokens"] <= 0 or usage["output_tokens"] <= 0 or usage["total_tokens"] < max(usage["input_tokens"], usage["output_tokens"]):
        raise ValueError("native response usage telemetry drifted")
    model_usage = envelope.get("modelUsage")
    if not isinstance(model_usage, Mapping) or set(model_usage) != {reported_model} or not isinstance(model_usage[reported_model], Mapping):
        raise ValueError("native response model usage drifted")
    model = model_usage[reported_model]
    model_keys = {"inputTokens", "outputTokens", "cacheReadInputTokens", "cacheCreationInputTokens", "modelCalls", "costUSD"}
    if set(model) != model_keys or model.get("modelCalls") != 1 or any(type(model.get(key)) is not int or model[key] < 0 for key in model_keys - {"costUSD"}) or model["inputTokens"] <= 0 or model["outputTokens"] <= 0:
        raise ValueError("native response model call telemetry drifted")
    cost = _nonnegative_number(envelope.get("total_cost_usd"), "cost")
    ticks = envelope.get("total_cost_usd_ticks")
    if type(ticks) is not int or ticks < 0 or ticks != round(cost * 10_000_000_000) or not math.isclose(_nonnegative_number(model.get("costUSD"), "model cost"), cost, rel_tol=0, abs_tol=1e-12):
        raise ValueError("native response cost telemetry drifted")
    thought = envelope.get("thought")
    normalized_thought = " ".join(thought.split()).casefold() if isinstance(thought, str) else ""
    if not normalized_thought or normalized_thought in {"x", "n/a", "none", "placeholder"} or re.search(r"\b(?:search(?:ing)?|look(?:ing)?|inspect(?:ing)?) (?:the )?workspace\b", normalized_thought):
        raise ValueError("native response thought telemetry drifted")
    identity = {"provider": "xai", "requested_model": route.get("model"), "reported_model": reported_model, "request_id": request_id, "session_id": session_id, "native_endpoint_contact_cardinality": "unproven", "tools_enabled": False}
    return dict(envelope), identity


def _cell(lifecycle: ModuleType, native: ModuleType, root: Path, row: Mapping[str, Any], schedule: Mapping[str, Any]) -> tuple[dict[str, Any], Mapping[str, Any], Mapping[str, Any]]:
    _inventory(root, CELL_FILES, directories={"responses"})
    raw, prompt, schema = lifecycle.payload(row)
    prepared = strict(stable(root / "prepared.json"), "prepared")
    route, evidence = prepared.get("route"), prepared.get("route_evidence")
    if not isinstance(route, Mapping) or not isinstance(evidence, Mapping):
        raise TypeError("prepared route binding drifted")
    expected_prepared, files = lifecycle.artifacts(row, schedule, raw, prompt, schema, route, evidence, ACKNOWLEDGEMENT_SHA256)
    if prepared != expected_prepared or any(stable(root / name) != value for name, value in files.items()):
        raise ValueError("prepared artifact bytes drifted")
    acknowledgement = strict(stable(root / "authorization-acknowledgement.json"), "acknowledgement")
    if acknowledgement.get("acknowledgement_sha256") != ACKNOWLEDGEMENT_SHA256:
        raise ValueError("acknowledgement drifted")
    intent = {"format_version": 1, "study_id": SOURCE_STUDY_ID, "kind": "intent_before_native_grok_contact", "cell_id": row["cell_id"], "prepared_sha256": sha256(expected_prepared), "outbound_payload_sha256": sha256(raw), "native_contact_proven": False}
    if stable(root / "launch-intent.json") != canonical(intent):
        raise ValueError("launch intent drifted")
    result = strict(stable(root / "result.json"), "terminal result")
    expected_result = {"cell_id": row["cell_id"], "detail": "ValueError", "format_version": 1, "intent_sha256": sha256(intent), "kind": "reconcile_required_after_process_launch", "native_endpoint_contact_cardinality": "unknown", "process_launches": 1, "provider_calls_made": None, "retry_policy": "fresh_output_root_required_no_in_place_resend", "study_id": SOURCE_STUDY_ID}
    if result != expected_result:
        raise ValueError("terminal result drifted")
    responses = root / "responses"
    _inventory(responses, RESPONSE_FILES)
    prompt_artifact = stable(responses / "batch-0001.attempt-0001.prompt.txt")
    response = stable(responses / "batch-0001.attempt-0001.grok.envelope.json")
    if prompt_artifact != prompt:
        raise ValueError("runner prompt differs from frozen payload")
    _envelope, identity = _response(response, route)
    request = native.adapter_canonical({"prompt": prompt.decode("utf-8")})
    settings = {"route_name": route["name"], "adapter": "grok_exec", "requested_model": "grok-4.6", "reported_model": "grok-4.6-build", "requested_reasoning_effort": "high", "tools_enabled": False, "web_search_enabled": False, "subagents_enabled": False, "tool_free_argv": native.TOOL_FREE_ARGV, "system_prompt_override": "Act as an isolated structured-output evaluator. Do not use memory, tools, web, plans, or subagents.", "sampler": {"batch_number": 1, "attempt_number": 1, "timeout_seconds": float(route["timeout_seconds"]), "nonvisual_max_turns": 1}, "runner_prompt_artifact_sha256": sha256(prompt), "reasoning_attested": False}
    validated = native._validate_runner_result({"native_request_bytes": request, "native_response_bytes": response, "identity": identity, "effective_settings": settings}, route, prompt)
    if validated != (request, response, identity, settings):
        raise ValueError("pinned native runner validation drifted")
    cell = {"cell_id": row["cell_id"], "payload_base64": row["payload_base64"], "payload_sha256": row["payload_sha256"], "native_request_base64": base64.b64encode(request).decode("ascii"), "native_request_sha256": sha256(request), "native_response_base64": base64.b64encode(response).decode("ascii"), "native_response_sha256": sha256(response), "identity": identity, "effective_settings": settings, "effective_settings_sha256": sha256(settings)}
    return cell, route, evidence


def reconcile(*, output_root: Path, freeze_root: Path) -> dict[str, Any]:
    root = safe(output_root)
    if root.name != SOURCE_ROOT_NAME:
        raise ValueError("wrong immutable source root")
    source = source_executor()
    with source._bound_source(freeze_root=safe(freeze_root)) as (lifecycle, _source, schedule, parent, _runtime):
        if source.FREEZE_SCHEDULE_SHA256 != FREEZE_SCHEDULE_SHA256 or source.SOURCE_COMMIT != FREEZE_COMMIT:
            raise ValueError("pinned freeze identity drifted")
        expected_ids = {row["cell_id"] for row in schedule["cells"]}
        _inventory(root, {"schedule.json", ".claims", *expected_ids}, directories={".claims", *expected_ids})
        if stable(root / "schedule.json") != canonical(schedule):
            raise ValueError("persisted schedule drifted")
        source._validate_claims(root, expected_ids)
        native = lifecycle.live()
        cells, seen_pairs, seen_ids = [], set(), set()
        frozen_route = frozen_evidence = None
        for row in schedule["cells"]:
            cell, route, evidence = _cell(lifecycle, native, root / row["cell_id"], row, schedule)
            parent._validate_route_evidence(route, evidence)
            if frozen_route is None:
                frozen_route, frozen_evidence = route, evidence
            if route != frozen_route or evidence != frozen_evidence:
                raise ValueError("route/evidence differs across cells")
            pair = (cell["payload_sha256"], cell["native_response_sha256"])
            identity = (cell["identity"]["request_id"], cell["identity"]["session_id"])
            if pair in seen_pairs or identity in seen_ids:
                raise ValueError("duplicate prompt/response or native identity")
            seen_pairs.add(pair); seen_ids.add(identity); cells.append(cell)
    if len(cells) != 64 or frozen_route is None or frozen_evidence is None:
        raise ValueError("partial reconciliation")
    return {"format_version": 1, "study_id": STUDY_ID, "kind": "reconciled_64_desc18_open_validation_grok_receipts_cardinality_unproven", "source_lineage": {"source_study_id": SOURCE_STUDY_ID, "source_commit": SOURCE_COMMIT, "source_root_name": SOURCE_ROOT_NAME, "source_terminal_kind": "reconcile_required_after_process_launch", "reconciliation_reason": "native_json_formatting_only", "freeze_commit": FREEZE_COMMIT}, "schedule_sha256": schedule["schedule_sha256"], "authorization_acknowledgement_sha256": ACKNOWLEDGEMENT_SHA256, "route": frozen_route, "route_evidence": frozen_evidence, "cells": cells, "native_endpoint_contact_cardinality": "unproven", "provider_calls_made": 0, "process_launches": 0, "historical_process_launches": 64}


def replay_collector(*, output_root: Path, freeze_root: Path, collector_path: Path) -> dict[str, Any]:
    collector = strict(stable(collector_path), "collector")
    expected = reconcile(output_root=output_root, freeze_root=freeze_root)
    if collector != expected:
        raise ValueError("collector differs from reconciled immutable evidence")
    return {"format_version": 1, "study_id": STUDY_ID, "collector_sha256": sha256(collector), "cells": 64, "provider_calls_made": 0, "process_launches": 0, "historical_process_launches": 64, "native_endpoint_contact_cardinality": "unproven", "equal_group_projection_ready": True, "authority": {"selection": "none", "promotion": "none", "runtime": "none", "confirmation": {"status": "unopened", "cells": 0}}}


def write_collector(*, output_root: Path, freeze_root: Path, collector_output: Path) -> dict[str, Any]:
    collector = safe(collector_output)
    if collector.exists() or collector.is_symlink():
        raise ValueError("collector output must be fresh")
    source_root, freeze = safe(output_root), safe(freeze_root)
    if collector == source_root or source_root in collector.parents or collector == freeze or freeze in collector.parents or collector == REPO or REPO in collector.parents:
        raise ValueError("collector must be outside immutable inputs and repository")
    value = reconcile(output_root=source_root, freeze_root=freeze)
    _plain(collector.parent, directory=True)
    with collector.open("xb") as handle:
        handle.write(canonical(value)); handle.flush(); os.fsync(handle.fileno())
    return replay_collector(output_root=source_root, freeze_root=freeze, collector_path=collector)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--freeze-root", type=Path, required=True)
    parser.add_argument("--collector-output", type=Path)
    parser.add_argument("--collector-path", type=Path)
    args = parser.parse_args(argv)
    if bool(args.collector_output) == bool(args.collector_path):
        parser.error("choose exactly one of --collector-output or --collector-path")
    result = write_collector(output_root=args.output_root, freeze_root=args.freeze_root, collector_output=args.collector_output) if args.collector_output else replay_collector(output_root=args.output_root, freeze_root=args.freeze_root, collector_path=args.collector_path)
    print(canonical(result).decode("utf-8"), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
