"""Provider-free reconciliation of immutable V10 Fresh96 Grok receipts."""
from __future__ import annotations

import argparse
import base64
import hashlib
import importlib.util
import math
import os
import re
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path
from types import ModuleType
from typing import Any

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
STUDY_ID = "hbq-human-alignment-optimizer-v10-fresh96-confirmation-grok-reconcile-v1"
SOURCE_ID = "hbq-human-alignment-optimizer-v10-fresh96-confirmation-grok-exec-v1"
SOURCE_ROOT_NAME = "cwr-hanna-v10-fresh96-confirmation-grok-1c10bae-20260901-r1"
SOURCE = HERE.parent / "hbq-human-alignment-optimizer-v10-fresh96-confirmation-grok-exec-v1"
FREEZE = HERE.parent / "hbq-human-alignment-optimizer-v10-fresh96-confirmation-candidates-v1"
SOURCE_COMMIT = "1c10bae7e377bc47ac2b06babdab1c3db39ab5ea"
SOURCE_EXECUTOR_SHA256 = "f361d334a8ac6e1eb6900ff348ac98a933dbb5393862e693eaf77fe1d66cdfc3"
SOURCE_CONTRACT_SHA256 = "97e2a4df6b965894aac0bc58865c30b6b1bcba93ff211d3c76a4c4dbb4f379ee"
FREEZE_STUDY_SHA256 = "38ea9c9c0cf96dfc0ca32b64ee6639515600bc01b93e204cdd397bae393b2a6f"
FREEZE_CONTRACT_SHA256 = "acf8fbf0f3ef5937d963e53fecf286ae3a606eb62302b0e918468e74b17d9348"
ACK = "2fb371ff82b37fe22d238a223fc030ad7a7bb9a10b672719da081470d25dbe78"
V9 = HERE.parent / "hbq-human-alignment-optimizer-v9-desc18-broad-replication-grok-reconcile-v1" / "reconcile.py"
V9_SHA256 = "6274f1afb1b81a351c91a87d5fa17dddc51821c2b393ea118d87f797fdbb3552"
PREPARED = {"authorization-acknowledgement.json", "disclosure.json", "outbound-payload.json", "prepared.json", "prompt-request.bin", "response-schema.json", "zero-charge-route-proof.json"}
RESPONSE_FILES = {"batch-0001.attempt-0001.grok.envelope.json", "batch-0001.attempt-0001.prompt.txt"}
DIMENSIONS = ("Relevance", "Coherence", "Empathy", "Surprise", "Engagement", "Complexity")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _blob(path: Path) -> bytes:
    result = subprocess.run(["git", "-C", str(REPO), "show", f"{SOURCE_COMMIT}:{path.relative_to(REPO).as_posix()}"], capture_output=True, check=False)
    if result.returncode:
        raise ValueError("pinned source Git blob is absent")
    return result.stdout


def helper() -> ModuleType:
    if _sha(V9) != V9_SHA256:
        raise ValueError("pinned V9 reconciler drifted")
    spec = importlib.util.spec_from_file_location("_v10_reconcile_helpers", V9)
    if spec is None or spec.loader is None:
        raise ValueError("cannot load pinned reconciler helpers")
    module = importlib.util.module_from_spec(spec); sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(spec.name, None)
    return module


def contract() -> dict[str, Any]:
    h = helper(); value = h.strict(h.stable(HERE / "study-contract.json"), "study contract")
    expected = {"authority": {"confirmation": "measurement_only", "endpoint_pooling": "forbidden", "promotion": "none", "runtime": "none", "selection": "none"}, "format_version": 1, "geometry": {"historical_process_launches": 64, "provider_calls_during_reconciliation": 0, "reconciled_cells": 64}, "kind": "provider_free_fresh96_future_confirmation_grok_reconciliation", "native_endpoint_contact_cardinality": "unproven", "output_kind": "reconciled_64_fresh96_future_confirmation_grok_receipts_cardinality_unproven", "pins": {"source_commit": SOURCE_COMMIT, "source_executor_sha256": SOURCE_EXECUTOR_SHA256, "source_freeze_sha256": FREEZE_STUDY_SHA256}, "prohibitions": ["no provider calls or process launches", "no retry fallback or resend", "no source-root writes", "no endpoint pooling"], "study_id": STUDY_ID}
    if value != expected:
        raise ValueError("reconciliation contract drifted")
    return value


def source_executor() -> ModuleType:
    paths = {SOURCE / "executor.py": SOURCE_EXECUTOR_SHA256, SOURCE / "study-contract.json": SOURCE_CONTRACT_SHA256, FREEZE / "study.py": FREEZE_STUDY_SHA256, FREEZE / "study-contract.json": FREEZE_CONTRACT_SHA256}
    for path, digest in paths.items():
        if _sha(path) != digest or _blob(path) != path.read_bytes():
            raise ValueError("pinned V10 source package drifted")
    spec = importlib.util.spec_from_file_location("_v10_reconcile_source", SOURCE / "executor.py")
    if spec is None or spec.loader is None:
        raise ValueError("cannot load V10 source executor")
    module = importlib.util.module_from_spec(spec); sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(spec.name, None)
    return module


def _response(h: ModuleType, raw: bytes, route: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    envelope = h.strict(raw, "native response", canonical_required=False)
    reported = route.get("reported_model")
    if (set(envelope) != h.RESPONSE_FIELDS or envelope.get("stopReason") != "end_turn" or envelope.get("num_turns") != 1
            or not isinstance(envelope.get("requestId"), str) or not envelope["requestId"]
            or not isinstance(envelope.get("sessionId"), str) or not envelope["sessionId"] or not isinstance(reported, str)):
        raise ValueError("native response identity or terminal state drifted")
    structured = envelope.get("structuredOutput")
    if not isinstance(envelope.get("text"), str) or not isinstance(structured, Mapping) or h.strict(envelope["text"].encode("utf-8"), "native response text", canonical_required=False) != structured:
        raise ValueError("native response text/schema disagreement")
    scores, evidence, coverage = structured.get("scores"), structured.get("evidence"), structured.get("coverage")
    if set(structured) != {"scores", "evidence", "coverage"} or not all(isinstance(value, Mapping) and set(value) == set(DIMENSIONS) for value in (scores, evidence, coverage)):
        raise ValueError("native response dimension schema drifted")
    for dimension in DIMENSIONS:
        score, note, covered = scores[dimension], evidence[dimension], coverage[dimension]
        normalized = " ".join(note.split()).casefold() if isinstance(note, str) else ""
        if type(score) not in {int, float} or not math.isfinite(float(score)) or not 0 <= float(score) <= 5:
            raise ValueError("native response score drifted")
        if (not normalized or normalized in {"x", "n/a", "none", "missing", "redacted", "placeholder"}
                or re.search(r"\b(?:search(?:ing)?|look(?:ing)?|inspect(?:ing)?) (?:the )?workspace\b", normalized)
                or re.search(r"\bworkspace (?:search|lookup)\b", normalized)):
            raise ValueError("native response evidence drifted")
        if type(covered) is not bool:
            raise ValueError("native response coverage drifted")
    if all(float(scores[name]) == 0 for name in DIMENSIONS):
        raise ValueError("native response all-zero score vector")
    usage = envelope.get("usage")
    usage_keys = {"input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens", "reasoning_tokens", "total_tokens"}
    if not isinstance(usage, Mapping) or set(usage) != usage_keys or any(type(usage[key]) is not int or usage[key] < 0 for key in usage_keys) or usage["input_tokens"] <= 0 or usage["output_tokens"] <= 0 or usage["total_tokens"] < max(usage["input_tokens"], usage["output_tokens"]):
        raise ValueError("native response usage telemetry drifted")
    model_usage = envelope.get("modelUsage")
    model_keys = {"inputTokens", "outputTokens", "cacheReadInputTokens", "cacheCreationInputTokens", "modelCalls", "costUSD"}
    if not isinstance(model_usage, Mapping) or set(model_usage) != {reported} or not isinstance(model_usage[reported], Mapping) or set(model_usage[reported]) != model_keys or model_usage[reported].get("modelCalls") != 1:
        raise ValueError("native response model usage drifted")
    model = model_usage[reported]
    if any(type(model[key]) is not int or model[key] < 0 for key in model_keys - {"costUSD"}) or model["inputTokens"] <= 0 or model["outputTokens"] <= 0:
        raise ValueError("native response model call telemetry drifted")
    cost, ticks = h._nonnegative_number(envelope.get("total_cost_usd"), "cost"), envelope.get("total_cost_usd_ticks")
    if type(ticks) is not int or ticks < 0 or ticks != round(cost * 10_000_000_000) or not math.isclose(h._nonnegative_number(model["costUSD"], "model cost"), cost, rel_tol=0, abs_tol=1e-12):
        raise ValueError("native response cost telemetry drifted")
    thought = " ".join(envelope.get("thought", "").split()).casefold() if isinstance(envelope.get("thought"), str) else ""
    if (not thought or thought in {"x", "n/a", "none", "placeholder"}
            or re.search(r"\b(?:search(?:ing)?|look(?:ing)?|inspect(?:ing)?) (?:the )?workspace\b", thought)):
        raise ValueError("native response thought telemetry drifted")
    return dict(envelope), {"provider": "xai", "requested_model": route.get("model"), "reported_model": reported, "request_id": envelope["requestId"], "session_id": envelope["sessionId"], "native_endpoint_contact_cardinality": "unproven", "tools_enabled": False}


def _cell(h: ModuleType, lifecycle: ModuleType, native: ModuleType, root: Path, row: Mapping[str, Any], schedule: Mapping[str, Any]) -> tuple[dict[str, Any], Mapping[str, Any], Mapping[str, Any]]:
    h._inventory(root, PREPARED | {"launch-intent.json", "result.json", "responses"}, directories={"responses"})
    raw, prompt, schema = lifecycle.payload(row)
    prepared = h.strict(h.stable(root / "prepared.json"), "prepared")
    route, evidence = prepared.get("route"), prepared.get("route_evidence")
    if not isinstance(route, Mapping) or not isinstance(evidence, Mapping):
        raise TypeError("prepared route binding drifted")
    expected_prepared, files = lifecycle.artifacts(row, schedule, raw, prompt, schema, route, evidence, ACK)
    if prepared != expected_prepared or any(h.stable(root / name) != value for name, value in files.items()):
        raise ValueError("prepared artifact bytes drifted")
    acknowledgement = h.strict(h.stable(root / "authorization-acknowledgement.json"), "acknowledgement")
    if acknowledgement.get("acknowledgement_sha256") != ACK:
        raise ValueError("acknowledgement drifted")
    intent = {"format_version": 1, "study_id": SOURCE_ID, "kind": "intent_before_native_grok_contact", "cell_id": row["cell_id"], "prepared_sha256": h.sha256(expected_prepared), "outbound_payload_sha256": h.sha256(raw), "native_contact_proven": False}
    if h.stable(root / "launch-intent.json") != h.canonical(intent):
        raise ValueError("launch intent drifted")
    result = h.strict(h.stable(root / "result.json"), "terminal result")
    expected_result = {"cell_id": row["cell_id"], "detail": "ValueError", "format_version": 1, "intent_sha256": h.sha256(intent), "kind": "reconcile_required_after_process_launch", "native_endpoint_contact_cardinality": "unknown", "process_launches": 1, "provider_calls_made": None, "retry_policy": "fresh_output_root_required_no_in_place_resend", "study_id": SOURCE_ID}
    if result != expected_result:
        raise ValueError("terminal result drifted")
    responses = root / "responses"; h._inventory(responses, RESPONSE_FILES)
    prompt_artifact, response = h.stable(responses / "batch-0001.attempt-0001.prompt.txt"), h.stable(responses / "batch-0001.attempt-0001.grok.envelope.json")
    if prompt_artifact != prompt:
        raise ValueError("runner prompt differs from frozen payload")
    _envelope, identity = _response(h, response, route)
    request = native.adapter_canonical({"prompt": prompt.decode("utf-8")})
    settings = {"route_name": route["name"], "adapter": "grok_exec", "requested_model": "grok-4.6", "reported_model": "grok-4.6-build", "requested_reasoning_effort": "high", "tools_enabled": False, "web_search_enabled": False, "subagents_enabled": False, "tool_free_argv": native.TOOL_FREE_ARGV, "system_prompt_override": "Act as an isolated structured-output evaluator. Do not use memory, tools, web, plans, or subagents.", "sampler": {"batch_number": 1, "attempt_number": 1, "timeout_seconds": float(route["timeout_seconds"]), "nonvisual_max_turns": 1}, "runner_prompt_artifact_sha256": h.sha256(prompt), "reasoning_attested": False}
    if settings["tools_enabled"] is not False:
        raise ValueError("tools must be disabled")
    if native._validate_runner_result({"native_request_bytes": request, "native_response_bytes": response, "identity": identity, "effective_settings": settings}, route, prompt) != (request, response, identity, settings):
        raise ValueError("pinned native validator drifted")
    return {"cell_id": row["cell_id"], "payload_base64": row["payload_base64"], "payload_sha256": row["payload_sha256"], "native_request_base64": base64.b64encode(request).decode("ascii"), "native_request_sha256": h.sha256(request), "native_response_base64": base64.b64encode(response).decode("ascii"), "native_response_sha256": h.sha256(response), "identity": identity, "effective_settings": settings, "effective_settings_sha256": h.sha256(settings)}, route, evidence


def reconcile(*, output_root: Path, freeze_root: Path) -> dict[str, Any]:
    h = helper(); root = h.safe(Path(output_root)); contract()
    if root.name != SOURCE_ROOT_NAME:
        raise ValueError("wrong immutable source root")
    source = source_executor()._configured_base()
    with source._bound_source(freeze_root=h.safe(Path(freeze_root))) as (lifecycle, _source, schedule, parent, _runtime):
        expected_ids = {row["cell_id"] for row in schedule["cells"]}
        h._inventory(root, {"schedule.json", ".claims", *expected_ids}, directories={".claims", *expected_ids})
        if h.stable(root / "schedule.json") != h.canonical(schedule):
            raise ValueError("persisted schedule drifted")
        source._validate_claims(root, expected_ids)
        cells, identities, routes = [], set(), []
        for row in schedule["cells"]:
            cell, route, evidence = _cell(h, lifecycle, lifecycle.live(), root / row["cell_id"], row, schedule)
            parent._validate_route_evidence(route, evidence); identity = (cell["identity"]["request_id"], cell["identity"]["session_id"])
            if identity in identities:
                raise ValueError("duplicate native identity")
            identities.add(identity); cells.append(cell); routes.append((route, evidence))
    if len(cells) != 64 or len(routes) != 64 or any(route != routes[0] for route in routes[1:]):
        raise ValueError("partial reconciliation or route drift")
    route, evidence = routes[0]
    return {"format_version": 1, "study_id": STUDY_ID, "kind": "reconciled_64_fresh96_future_confirmation_grok_receipts_cardinality_unproven", "source_lineage": {"source_study_id": SOURCE_ID, "source_commit": SOURCE_COMMIT, "source_root_name": SOURCE_ROOT_NAME, "source_terminal_kind": "reconcile_required_after_process_launch", "reconciliation_reason": "native_json_formatting_and_false_positive_placeholder_text"}, "schedule_sha256": schedule["schedule_sha256"], "authorization_acknowledgement_sha256": ACK, "route": route, "route_evidence": evidence, "cells": cells, "native_endpoint_contact_cardinality": "unproven", "provider_calls_made": 0, "process_launches": 0, "historical_process_launches": 64, "authority": {"selection": "none", "promotion": "none", "runtime": "none", "endpoint_pooling": "forbidden", "confirmation": {"status": "measurement_only", "cells": 64}}}


def replay_collector(*, output_root: Path, freeze_root: Path, collector_path: Path) -> dict[str, Any]:
    h = helper(); collector = h.strict(h.stable(Path(collector_path)), "collector")
    if collector != reconcile(output_root=output_root, freeze_root=freeze_root):
        raise ValueError("collector differs from reconciled immutable evidence")
    return {"format_version": 1, "study_id": STUDY_ID, "collector_sha256": h.sha256(collector), "cells": 64, "provider_calls_made": 0, "process_launches": 0, "historical_process_launches": 64, "native_endpoint_contact_cardinality": "unproven", "equal_group_projection_ready": True, "authority": collector["authority"]}


def write_collector(*, output_root: Path, freeze_root: Path, collector_output: Path) -> dict[str, Any]:
    h = helper(); collector, source_root, freeze = h.safe(Path(collector_output)), h.safe(Path(output_root)), h.safe(Path(freeze_root))
    if collector.exists() or collector.is_symlink():
        raise ValueError("collector output must be fresh")
    if collector == source_root or source_root in collector.parents or collector == freeze or freeze in collector.parents or collector == REPO or REPO in collector.parents:
        raise ValueError("collector must be outside immutable inputs and repository")
    value = reconcile(output_root=source_root, freeze_root=freeze)
    with collector.open("xb") as handle:
        handle.write(h.canonical(value)); handle.flush(); os.fsync(handle.fileno())
    return replay_collector(output_root=source_root, freeze_root=freeze, collector_path=collector)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(); parser.add_argument("--output-root", type=Path, required=True); parser.add_argument("--freeze-root", type=Path, required=True); parser.add_argument("--collector-path", type=Path, required=True)
    print(helper().canonical(replay_collector(output_root=parser.parse_args().output_root, freeze_root=parser.parse_args().freeze_root, collector_path=parser.parse_args().collector_path)).decode(), end="")
