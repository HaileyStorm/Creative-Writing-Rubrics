"""Pinned V16 native transport composition for the WPB compact-family core."""
from __future__ import annotations

import base64
import hashlib
import importlib.util
import inspect
import json
import math
import subprocess
import sys
import threading
import uuid
from datetime import datetime, timedelta, timezone
from collections.abc import Callable, Iterator, Mapping
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from contextlib import contextmanager
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
STUDY_ID = "hbq-human-alignment-wpb-compact-family-v1"
CORE = HERE.parent / "hbq-human-alignment-wpb-compact-family-v1" / "study.py"
CORE_COMMIT = "b43f68381f3767b590ef68b19ddb8206c8818cda"
CORE_SHA256 = "ef1f8d5e45da1700283ef351ab943ec39abedb103ad1ef979d731d4934d32caf"
CORE_CONTRACT = CORE.parent / "experiment-contract.json"
CORE_CONTRACT_SHA256 = "dd1638d917b32c5de2423ab58aba9d952fbca906722807b8079c1fbb72967e96"
V16 = HERE.parent / "hbq-human-alignment-optimizer-v16-comparative-train-v1" / "executor.py"
V16_COMMIT = "3c1bec6"
V16_SHA256 = "554c6ab1e70a74a89c9b7cefab7c15ea66146a44aea7a8d38293ae6c2d4956db"
CONTRACT = HERE / "study-contract.json"
CONTRACT_SHA256 = "71047d987bf5b15039afa737cfc8e398e0b1c96de74376a9e577d9f4c8f6c4d7"
QUEUE_TOOLS_ROOT = Path(r"C:\Users\Haile\.codex\tools")
BROKER_PATH = QUEUE_TOOLS_ROOT / "model_work_queue" / "broker.py"
BROKER_SHA256 = "1e906ce2d2128c8097b46c980328bd45a6dd45ec3edee53f0c5f32cff4adfc4a"
IMAGE_CANARY_PATH = QUEUE_TOOLS_ROOT / "model_work_queue" / "image_canary.py"
IMAGE_CANARY_SHA256 = "6fa00f59bd0c84d0d752f67ad502b4e3dd5e39850bdc5c75855926fff1454da8"
USAGE_EVIDENCE_PATH = QUEUE_TOOLS_ROOT / "model_work_queue" / "grok_usage_evidence.py"
USAGE_EVIDENCE_SHA256 = "dc5e00849699858445d966783bfa2b2afc5255b896f41544196ac023c82be99f"
GROK_ADAPTER_PATH = QUEUE_TOOLS_ROOT / "model_work_queue" / "adapters" / "grok_exec.py"
GROK_ADAPTER_SHA256 = "8067348efa7024d6d266d9a6f30b11380d2c54adce768cfc6e774f642c3c06aa"
SCHEMA_SUBSET_PATH = GROK_ADAPTER_PATH.parent / "json_schema_subset.py"
SCHEMA_SUBSET_SHA256 = "0efa225bbd16746ffb22dd053036c37da18642b19c1399cb2b181970158ee67e"
ENDPOINTS = {"grok", "sol"}
MAX_CONCURRENCY = 10
GROK_BATCH_SIZE = 10
GROK_ROUTE_FRESHNESS_SECONDS = 900
GROK_DISPATCH_MARGIN_SECONDS = 15
SUCCESS_STATES = {"Grok": "provisional_scoring_received", "Sol": "local_codex_lifecycle_received_native_contact_unproven"}
TRANSPORT_TARGET = {"Relevance": 0.0, "Coherence": 0.0, "Empathy": 0.0, "Surprise": 0.0, "Engagement": 0.0, "Complexity": 0.0}
EXPECTED_CONTRACT = {
    "authority": {"confirmation": "closed", "endpoint_pooling": "forbidden", "promotion": "none", "runtime": "none", "selection": "development_only"},
    "core": {"commit": CORE_COMMIT, "path": CORE.relative_to(REPO).as_posix(), "sha256": CORE_SHA256},
    "execution": {
        "endpoints": ["grok", "sol"],
        "grok_batches": {"active_marker": "create-exclusive execution-active.json; crash remains fail-closed for manual recovery", "api": ["create_campaign", "prepare_next_batch", "execute_batch", "settle_batch", "report"], "batch_size": GROK_BATCH_SIZE, "dispatch_margin_seconds": GROK_DISPATCH_MARGIN_SECONDS, "fresh_route_window_seconds": GROK_ROUTE_FRESHNESS_SECONDS, "global_manifest": "ordered 129 cell IDs, payload hashes, partitions, core, executor, contract, and global acknowledgement", "settlement": "exact per-batch claims and all artifact hashes are rederived; completed receipts require a canonical shared-native result, and only claim-free prepared cells are eligible"},
        "grok_native_contact_guard": {"adapter_path": "C:/Users/Haile/.codex/tools/model_work_queue/adapters/grok_exec.py", "adapter_sha256": GROK_ADAPTER_SHA256, "api": "Broker.run_grok_native_request", "expected_route_pin": "required_before_contact", "image_canary_path": "C:/Users/Haile/.codex/tools/model_work_queue/image_canary.py", "image_canary_sha256": IMAGE_CANARY_SHA256, "path": "C:/Users/Haile/.codex/tools/model_work_queue/broker.py", "raw_reader": "Broker.read_grok_native_envelope", "schema_subset_path": SCHEMA_SUBSET_PATH.as_posix(), "schema_subset_sha256": SCHEMA_SUBSET_SHA256, "sha256": BROKER_SHA256, "usage_evidence_path": "C:/Users/Haile/.codex/tools/model_work_queue/grok_usage_evidence.py", "usage_evidence_sha256": USAGE_EVIDENCE_SHA256},
        "max_concurrency": MAX_CONCURRENCY, "payload_parity": "exact identical bytes per cell across endpoints", "precontact": "create_campaign and prepare_next_batch make zero provider calls or process launches", "transport": "unchanged pinned V16 Sol lifecycle plus raw-preserving shared Grok requests in bounded batches; custom runners are test-only", "unit": "one rederived WPB pair per call"},
    "format_version": 2, "kind": "wpb_compact_family_native_execution",
    "local_only": {"excluded_from_provider_payload": ["category", "source model", "preferred side", "chosen/rejected labels", "source scores", "local targets"], "sol_transport_target": "fixed all-zero V16 compatibility sentinel; never a WPB label or outbound payload"},
    "native_runtime": {"commit": V16_COMMIT, "path": V16.relative_to(REPO).as_posix(), "sha256": V16_SHA256}, "study_id": STUDY_ID,
}


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def sha256(value: bytes | Any) -> str:
    return hashlib.sha256(value if isinstance(value, bytes) else canonical(value)).hexdigest()


def _load_exact(path: Path, digest: str, commit: str, name: str) -> ModuleType:
    raw = Path(path).read_bytes()
    relative = Path(path).relative_to(REPO).as_posix()
    blob = subprocess.run(["git", "-C", str(REPO), "show", f"{commit}:{relative}"], capture_output=True, check=False)
    if blob.returncode or sha256(raw) != digest or blob.stdout != raw:
        raise ValueError("pinned native dependency drifted")
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ValueError("pinned native dependency cannot load")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        exec(compile(raw, str(path), "exec"), module.__dict__)
    finally:
        sys.modules.pop(name, None)
    if Path(path).read_bytes() != raw:
        raise ValueError("pinned native dependency changed during load")
    return module


def _core() -> ModuleType:
    return _load_exact(CORE, CORE_SHA256, CORE_COMMIT, "_wpb_native_core")


def _pinned_core_contract() -> None:
    raw = CORE_CONTRACT.read_bytes()
    relative = CORE_CONTRACT.relative_to(REPO).as_posix()
    blob = subprocess.run(["git", "-C", str(REPO), "show", f"{CORE_COMMIT}:{relative}"], capture_output=True, check=False)
    if sha256(raw) != CORE_CONTRACT_SHA256 or blob.returncode or blob.stdout != raw:
        raise ValueError("pinned compact core contract drifted")


def _contract() -> dict[str, Any]:
    raw = CONTRACT.read_bytes()
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("invalid native executor contract") from error
    if sha256(raw) != CONTRACT_SHA256 or raw != canonical(value) or value != EXPECTED_CONTRACT:
        raise ValueError("native executor contract drifted")
    return value


def _valid_response(core: ModuleType, response: Any) -> dict[str, Any]:
    if not isinstance(response, Mapping):
        raise ValueError("WPB native response is not an object")
    core._outcome(response, {"core": 1.0, "craft": 1.0, "form": 1.0}, core.compact_profile()["base_family_mass"])
    return dict(response)


def _resolution(*, freeze_root: Path | str) -> dict[str, Any]:
    core = _core()
    _pinned_core_contract()
    _contract()
    schedule = core.build_tasks(Path(freeze_root))
    tasks = schedule.get("tasks") if isinstance(schedule, Mapping) else None
    if not isinstance(tasks, list) or len(tasks) != 129 or schedule.get("study_id") != STUDY_ID:
        raise ValueError("WPB native schedule geometry drifted")
    rows: list[dict[str, Any]] = []
    payloads: dict[str, bytes] = {}
    for task in tasks:
        if not isinstance(task, Mapping) or set(task) != {"cell_id", "partition", "payload_utf8_base64", "payload_sha256", "grok_payload_sha256", "sol_payload_sha256"}:
            raise ValueError("WPB provider task shape drifted")
        cell_id = str(task["cell_id"])
        payload = base64.b64decode(str(task["payload_utf8_base64"]), validate=True)
        if sha256(payload) != task["payload_sha256"] or task["grok_payload_sha256"] != task["payload_sha256"] or task["sol_payload_sha256"] != task["payload_sha256"]:
            raise ValueError("WPB endpoint payload parity drifted")
        rows.append({"cell_id": cell_id, "source_cell_id": cell_id, "candidate_id": "wpb_compact_family", "condition": "wpb_pair", "item_id": cell_id, "story_id": cell_id, "prompt_group_id": cell_id, "partition": task["partition"], "payload_base64": task["payload_utf8_base64"], "payload_sha256": task["payload_sha256"], "endpoint_payload_sha256s": {"grok_primary": task["payload_sha256"], "sol_later": task["payload_sha256"]}, "payload_parity": "wpb_compact_core_exact_endpoint_payload", "target": dict(TRANSPORT_TARGET)})
        payloads[cell_id] = payload
    if len({row["cell_id"] for row in rows}) != 129 or sum(row["partition"] == "train" for row in rows) != 105 or sum(row["partition"] == "dev" for row in rows) != 24:
        raise ValueError("WPB native partition geometry drifted")
    value = {"format_version": 1, "study_id": STUDY_ID, "cells": rows, "wpb_core_commit": CORE_COMMIT, "wpb_core_sha256": CORE_SHA256, "authority": {"endpoint_pooling": "forbidden", "selection": "development_only", "promotion": "none", "runtime": "none", "confirmation": "closed"}}
    value["schedule_sha256"] = sha256(value)
    return {"core": core, "schedule": value, "schedule_sha256": value["schedule_sha256"], "rows": tuple(sorted(rows, key=lambda row: str(row["cell_id"]))), "payloads": payloads, "freeze_root": Path(freeze_root).resolve()}


def _execution_schedule(resolution: Mapping[str, Any]) -> dict[str, Any]:
    value = {"format_version": 1, "study_id": STUDY_ID, "cells": list(resolution["rows"]), "wpb_core_sha256": CORE_SHA256, "wpb_schedule_sha256": resolution["schedule_sha256"], "wpb_native_contract_sha256": CONTRACT_SHA256}
    value["schedule_sha256"] = sha256(value)
    return value


@contextmanager
def _grok_bound(resolution: Mapping[str, Any]) -> Iterator[tuple[ModuleType, ModuleType, ModuleType, ModuleType, ModuleType, ModuleType]]:
    runtime = _load_exact(V16, V16_SHA256, V16_COMMIT, "_wpb_v16_grok")
    runtime.STUDY_ID = STUDY_ID
    runtime._execution_schedule = _execution_schedule
    mapped = {"core": resolution["core"], "new": resolution["rows"], "rows": resolution["rows"], "payloads": resolution["payloads"], "schedule": resolution["schedule"], "schedule_sha256": resolution["schedule_sha256"], "core_sha256": CORE_SHA256}
    with runtime._grok_bound(mapped) as value:
        lifecycle, base, v9, v11, v13, v15 = value
        original_study = lifecycle.STUDY_ID
        lifecycle.STUDY_ID = STUDY_ID
        try:
            yield lifecycle, base, v9, v11, v13, v15
        finally:
            lifecycle.STUDY_ID = original_study


def _grok_answer(core: ModuleType, helper: Any, raw: bytes, route: Mapping[str, Any]) -> dict[str, Any]:
    envelope = helper.strict(raw, "WPB native response", canonical_required=False)
    reported, structured = route.get("reported_model"), envelope.get("structuredOutput")
    if (set(envelope) != helper.RESPONSE_FIELDS or envelope.get("stopReason") != "end_turn" or envelope.get("num_turns") != 1 or not isinstance(envelope.get("requestId"), str) or not envelope["requestId"] or not isinstance(envelope.get("sessionId"), str) or not envelope["sessionId"] or not isinstance(reported, str) or not reported or not isinstance(envelope.get("text"), str) or not isinstance(structured, Mapping) or helper.strict(envelope["text"].encode("utf-8"), "WPB structured response", canonical_required=False) != structured):
        raise ValueError("WPB Grok native envelope drifted")
    usage = envelope.get("usage")
    usage_keys = {"input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens", "reasoning_tokens", "total_tokens"}
    model_usage = envelope.get("modelUsage")
    model_keys = {"inputTokens", "outputTokens", "cacheReadInputTokens", "cacheCreationInputTokens", "modelCalls", "costUSD"}
    if (not isinstance(usage, Mapping) or set(usage) != usage_keys or any(type(usage[key]) is not int or usage[key] < 0 for key in usage_keys) or usage["input_tokens"] <= 0 or usage["output_tokens"] <= 0 or usage["total_tokens"] < max(usage["input_tokens"], usage["output_tokens"]) or not isinstance(model_usage, Mapping) or set(model_usage) != {reported} or not isinstance(model_usage[reported], Mapping) or set(model_usage[reported]) != model_keys or model_usage[reported].get("modelCalls") != 1):
        raise ValueError("WPB Grok native usage telemetry drifted")
    model = model_usage[reported]
    if any(type(model[key]) is not int or model[key] < 0 for key in model_keys - {"costUSD"}) or model["inputTokens"] <= 0 or model["outputTokens"] <= 0:
        raise ValueError("WPB Grok native model-call telemetry drifted")
    cost, ticks = helper._nonnegative_number(envelope.get("total_cost_usd"), "cost"), envelope.get("total_cost_usd_ticks")
    if type(ticks) is not int or ticks < 0 or ticks != round(cost * 10_000_000_000) or not math.isclose(helper._nonnegative_number(model["costUSD"], "model cost"), cost, rel_tol=0, abs_tol=1e-12) or not isinstance(envelope.get("thought"), str):
        raise ValueError("WPB Grok native cost or thought telemetry drifted")
    return {"envelope": dict(envelope), "answer": _valid_response(core, structured)}


def _write_new(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle:
        handle.write(canonical(value))


def _read_exact(path: Path, label: str) -> dict[str, Any]:
    try:
        raw = path.read_bytes()
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"invalid {label}") from error
    if not isinstance(value, dict) or raw != canonical(value):
        raise ValueError(f"non-canonical {label}")
    return value


def _campaign_file(root: Path) -> Path:
    return Path(root) / "campaign.json"


def _campaign(root: Path, resolution: Mapping[str, Any], acknowledgement: str) -> tuple[dict[str, Any], str]:
    path = _campaign_file(root)
    value = _read_exact(path, "WPB Grok campaign")
    digest = sha256(path.read_bytes())
    expected = [{"cell_id": str(row["cell_id"]), "partition": row["partition"], "payload_sha256": row["payload_sha256"]} for row in resolution["rows"]]
    if (value.get("format_version") != 2 or value.get("kind") != "wpb_grok_bounded_campaign" or value.get("study_id") != STUDY_ID
            or value.get("cells") != expected or value.get("global_task_manifest_sha256") != sha256(expected)
            or value.get("wpb_core_sha256") != CORE_SHA256 or value.get("wpb_schedule_sha256") != resolution["schedule_sha256"]
            or value.get("executor_sha256") != sha256(Path(__file__).read_bytes()) or value.get("contract_sha256") != CONTRACT_SHA256
            or value.get("authorization_acknowledgement_sha256") != acknowledgement):
        raise ValueError("WPB Grok campaign binding drifted")
    ack = _read_exact(Path(root) / "campaign-acknowledgement.json", "WPB Grok campaign acknowledgement")
    expected_ack = {"format_version": 1, "kind": "wpb_grok_global_acknowledgement", "study_id": STUDY_ID, "campaign_sha256": digest, "global_task_manifest_sha256": sha256(expected), "authorization_acknowledgement_sha256": acknowledgement}
    if ack != expected_ack:
        raise ValueError("WPB Grok global acknowledgement drifted")
    return value, digest


def _batch_root(campaign_root: Path, number: int) -> Path:
    if type(number) is not int or number < 1:
        raise ValueError("batch number must be a positive integer")
    return Path(campaign_root) / "batches" / f"{number:04d}"


def _batch_numbers(campaign_root: Path) -> tuple[int, ...]:
    root = Path(campaign_root) / "batches"
    if not root.exists():
        return ()
    numbers: list[int] = []
    for entry in root.iterdir():
        if not entry.is_dir() or len(entry.name) != 4 or not entry.name.isdecimal():
            raise ValueError("WPB Grok batch directory is malformed")
        numbers.append(int(entry.name))
    numbers.sort()
    if numbers != list(range(1, len(numbers) + 1)):
        raise ValueError("WPB Grok batch sequence is discontinuous")
    return tuple(numbers)


def _active_batch(campaign_root: Path) -> int | None:
    for number in _batch_numbers(campaign_root):
        if (_batch_root(campaign_root, number) / "execution-active.json").exists():
            return number
    return None


def _batch_plan(campaign_root: Path, number: int, campaign_sha256: str) -> tuple[dict[str, Any], str]:
    root = _batch_root(campaign_root, number)
    plan_path = root / "plan.json"
    plan = _read_exact(plan_path, "WPB Grok batch plan")
    digest = sha256(plan_path.read_bytes())
    acknowledgement = _read_exact(root / "batch-acknowledgement.json", "WPB Grok batch acknowledgement")
    campaign_acknowledgement = _read_exact(Path(campaign_root) / "campaign-acknowledgement.json", "WPB Grok campaign acknowledgement")
    cell_ids = plan.get("cell_ids")
    expected_ack = {"format_version": 1, "kind": "wpb_grok_batch_acknowledgement", "study_id": STUDY_ID, "campaign_sha256": campaign_sha256, "batch_number": number, "cell_ids": cell_ids, "authorization_acknowledgement_sha256": plan.get("authorization_acknowledgement_sha256")}
    expected_keys = {"format_version", "kind", "study_id", "campaign_sha256", "campaign_acknowledgement_sha256", "batch_number", "predecessor_settlement_sha256", "cell_ids", "route", "route_evidence", "route_sha256", "route_evidence_sha256", "route_expiry_utc", "freshness_seconds", "authorization_acknowledgement_sha256", "batch_acknowledgement_sha256"}
    predecessor = plan.get("predecessor_settlement_sha256")
    if (set(plan) != expected_keys or plan.get("format_version") != 1 or plan.get("kind") != "wpb_grok_bounded_batch_plan" or plan.get("study_id") != STUDY_ID
            or plan.get("batch_number") != number or plan.get("campaign_sha256") != campaign_sha256
            or not isinstance(cell_ids, list) or not cell_ids or len(cell_ids) > GROK_BATCH_SIZE or len(set(cell_ids)) != len(cell_ids)
            or not isinstance(plan.get("route"), Mapping) or not isinstance(plan.get("route_evidence"), Mapping)
            or plan.get("route_sha256") != sha256(plan["route"]) or plan.get("route_evidence_sha256") != sha256(plan["route_evidence"])
            or not isinstance(plan.get("route_expiry_utc"), str) or plan.get("freshness_seconds") != GROK_ROUTE_FRESHNESS_SECONDS
            or predecessor is not None and (not isinstance(predecessor, str) or len(predecessor) != 64)
            or plan.get("campaign_acknowledgement_sha256") != sha256((Path(campaign_root) / "campaign-acknowledgement.json").read_bytes())
            or campaign_acknowledgement.get("campaign_sha256") != campaign_sha256
            or plan.get("authorization_acknowledgement_sha256") != campaign_acknowledgement.get("authorization_acknowledgement_sha256")
            or acknowledgement != expected_ack or plan.get("batch_acknowledgement_sha256") != sha256((root / "batch-acknowledgement.json").read_bytes())):
        raise ValueError("WPB Grok batch plan binding drifted")
    return plan, digest


def _settlement(campaign_root: Path, number: int, plan_sha256: str, campaign_sha256: str) -> tuple[dict[str, Any], str]:
    path = _batch_root(campaign_root, number) / "settlement.json"
    value = _read_exact(path, "WPB Grok batch settlement")
    digest = sha256(path.read_bytes())
    plan, actual_plan_sha256 = _batch_plan(campaign_root, number, campaign_sha256)
    cells = value.get("cells")
    if (set(value) != {"format_version", "kind", "study_id", "campaign_sha256", "batch_number", "plan_sha256", "predecessor_settlement_sha256", "cells"}
            or value.get("format_version") != 1 or value.get("kind") != "wpb_grok_bounded_batch_settlement" or value.get("study_id") != STUDY_ID
            or value.get("campaign_sha256") != campaign_sha256 or value.get("batch_number") != number or value.get("plan_sha256") != plan_sha256 or actual_plan_sha256 != plan_sha256
            or not isinstance(cells, list) or len(cells) != len(plan["cell_ids"]) or {entry.get("cell_id") for entry in cells if isinstance(entry, Mapping)} != set(plan["cell_ids"])):
        raise ValueError("WPB Grok settlement binding drifted")
    for entry in cells:
        if not isinstance(entry, Mapping) or not isinstance(entry.get("artifacts"), Mapping):
            raise ValueError("WPB Grok settlement cell artifact binding drifted")
        state = entry.get("state")
        expected_keys = {"cell_id", "state", "artifacts", "claim_sha256", "execution_receipt_sha256", "identity_sha256"} if state == "completed" else ({"cell_id", "state", "artifacts", "prepared_sha256"} if state == "prepared_unlaunched" else None)
        if expected_keys is None:
            expected_keys = {"cell_id", "state", "reason", "artifacts", "claim_sha256"} if state == "consumed_terminal" and entry.get("reason") == "claimed_without_terminal_receipt" else ({"cell_id", "state", "reason", "artifacts", "artifact_sha256", "claim_sha256"} if state == "consumed_terminal" and entry.get("reason") == "malformed_terminal_receipt" else ({"cell_id", "state", "reason", "artifacts"} if state == "consumed_terminal" else set()))
        if set(entry) != expected_keys:
            raise ValueError("WPB Grok settlement cell shape drifted")
    return value, digest


def _fresh_route(v9: ModuleType, route: Mapping[str, Any]) -> str:
    expiry = v9._live_route_expiry(route)
    cost = route.get("cost_evidence")
    if not isinstance(cost, Mapping):
        raise ValueError("WPB Grok route has no cost evidence")
    try:
        observed = datetime.fromisoformat(str(cost["checked_at"]).replace("Z", "+00:00"))
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("WPB Grok route observation is invalid") from error
    if observed.tzinfo is None:
        raise ValueError("WPB Grok route observation lacks timezone")
    observed = observed.astimezone(timezone.utc)
    if expiry - observed > timedelta(seconds=GROK_ROUTE_FRESHNESS_SECONDS):
        raise ValueError("WPB Grok route proof exceeds its 900-second source lifetime")
    if expiry < datetime.now(timezone.utc) + timedelta(seconds=GROK_DISPATCH_MARGIN_SECONDS):
        raise ValueError("WPB Grok route proof cannot cover the next dispatch")
    return expiry.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _settlement_chain(campaign_root: Path, campaign_sha256: str) -> list[dict[str, Any]]:
    predecessor: str | None = None
    chain: list[dict[str, Any]] = []
    for number in _batch_numbers(campaign_root):
        plan, plan_sha256 = _batch_plan(campaign_root, number, campaign_sha256)
        settlement, settlement_sha256 = _settlement(campaign_root, number, plan_sha256, campaign_sha256)
        if plan.get("predecessor_settlement_sha256") != predecessor or settlement.get("predecessor_settlement_sha256") != predecessor:
            raise ValueError("WPB Grok settlement chain drifted")
        chain.append({"batch_number": number, "plan_sha256": plan_sha256, "settlement_sha256": settlement_sha256, "predecessor_settlement_sha256": predecessor})
        predecessor = settlement_sha256
    return chain


def _grok_plan_rows(resolution: Mapping[str, Any], plan: Mapping[str, Any]) -> tuple[dict[str, Any], ...]:
    index = {str(row["cell_id"]): row for row in resolution["rows"]}
    ids = plan.get("cell_ids")
    if not isinstance(ids, list) or any(not isinstance(cell_id, str) or cell_id not in index for cell_id in ids):
        raise ValueError("WPB Grok plan references an unknown cell")
    rows = tuple(index[cell_id] for cell_id in ids)
    if [str(row["cell_id"]) for row in rows] != ids:
        raise ValueError("WPB Grok plan cell order drifted")
    return rows


def _terminal_artifacts(root: Path) -> bool:
    return _shared_result_path(root).exists() or any((Path(root) / name).exists() for name in ("launch-intent.json", "broker-contact-outcome.json", "result.json", "native-response.bin", "execution-receipt.json"))


def _claim_hashes(v9: ModuleType, execution: Path, allowed_cells: set[str], expected_schedule: bytes) -> dict[str, str]:
    inventory = {entry.name for entry in Path(execution).iterdir()}
    if inventory - (allowed_cells | {".claims", "schedule.json"}) or (allowed_cells | {"schedule.json"}) - inventory:
        raise ValueError("WPB Grok execution inventory drifted")
    if v9.stable(Path(execution) / "schedule.json") != expected_schedule:
        raise ValueError("WPB Grok execution schedule drifted")
    shared = Path(execution).parent / "shared-native-results"
    if shared.exists():
        v9._plain(shared, directory=True)
        if {path.name for path in shared.iterdir()} - {cell + ".json" for cell in allowed_cells}:
            raise ValueError("WPB shared native evidence inventory drifted")
        for path in shared.iterdir():
            v9._plain(path, directory=False)
    claims = Path(execution) / ".claims"
    if not claims.exists():
        return {}
    observed = {entry.name for entry in claims.iterdir()}
    if not observed <= allowed_cells:
        raise ValueError("WPB Grok claim inventory includes an unplanned cell")
    v9._validate_claims(Path(execution), observed)
    return {cell_id: sha256((claims / cell_id / "claim.json").read_bytes()) for cell_id in observed}


def _historical_cell_states(campaign_root: Path, campaign_sha256: str, resolution: Mapping[str, Any], acknowledgement: str, lifecycle: ModuleType, v9: ModuleType) -> tuple[set[str], str | None]:
    consumed: set[str] = set()
    predecessor: str | None = None
    for number in _batch_numbers(campaign_root):
        plan, plan_sha256 = _batch_plan(campaign_root, number, campaign_sha256)
        settlement, settlement_sha256 = _settlement(campaign_root, number, plan_sha256, campaign_sha256)
        if plan.get("predecessor_settlement_sha256") != predecessor:
            raise ValueError("WPB Grok plan predecessor chain drifted")
        if settlement.get("predecessor_settlement_sha256") != predecessor:
            raise ValueError("WPB Grok settlement predecessor chain drifted")
        entries = _settlement_cells(resolution, _batch_root(campaign_root, number) / "execution", plan, acknowledgement, lifecycle=lifecycle, v9=v9, admitted=None)
        if settlement["cells"] != entries:
            raise ValueError("WPB Grok settlement no longer matches its artifacts")
        for entry in entries:
            if not isinstance(entry, Mapping) or entry.get("state") not in {"completed", "consumed_terminal", "prepared_unlaunched"}:
                raise ValueError("WPB Grok settlement state is invalid")
            cell_id = str(entry["cell_id"])
            if entry["state"] != "prepared_unlaunched":
                if cell_id in consumed:
                    raise ValueError("WPB Grok duplicate terminal cell")
                consumed.add(cell_id)
        predecessor = settlement_sha256
    return consumed, predecessor


def create_campaign(*, campaign_root: Path, freeze_root: Path | str, authorization_acknowledgement_sha256: str) -> dict[str, Any]:
    """Create the immutable, provider-free global manifest for all 129 Grok cells."""
    root = Path(campaign_root)
    if root.exists():
        raise ValueError("fresh WPB Grok campaign root required")
    resolution = _resolution(freeze_root=freeze_root)
    cells = [{"cell_id": str(row["cell_id"]), "partition": row["partition"], "payload_sha256": row["payload_sha256"]} for row in resolution["rows"]]
    campaign = {"format_version": 2, "kind": "wpb_grok_bounded_campaign", "study_id": STUDY_ID, "cells": cells, "global_task_manifest_sha256": sha256(cells), "wpb_core_sha256": CORE_SHA256, "wpb_schedule_sha256": resolution["schedule_sha256"], "executor_sha256": sha256(Path(__file__).read_bytes()), "contract_sha256": CONTRACT_SHA256, "authorization_acknowledgement_sha256": authorization_acknowledgement_sha256}
    root.mkdir(parents=True)
    _write_new(_campaign_file(root), campaign)
    campaign_sha256 = sha256(_campaign_file(root).read_bytes())
    _write_new(root / "campaign-acknowledgement.json", {"format_version": 1, "kind": "wpb_grok_global_acknowledgement", "study_id": STUDY_ID, "campaign_sha256": campaign_sha256, "global_task_manifest_sha256": sha256(cells), "authorization_acknowledgement_sha256": authorization_acknowledgement_sha256})
    return {"study_id": STUDY_ID, "endpoint": "grok", "campaign_sha256": campaign_sha256, "logical_cells": 129, "partitions": {"train": 105, "dev": 24}, "provider_calls_made": 0, "process_launches": 0, "native_contact_count": 0}


def prepare_next_batch(*, campaign_root: Path, queue_root: Path, freeze_root: Path | str, authorization_acknowledgement_sha256: str, grok_route_provider: Callable[[Path], tuple[dict[str, Any], dict[str, Any]]] | None = None) -> dict[str, Any]:
    """Prepare the next deterministic <=10-cell Grok batch without provider contact."""
    root = Path(campaign_root)
    resolution = _resolution(freeze_root=freeze_root)
    campaign, campaign_sha256 = _campaign(root, resolution, authorization_acknowledgement_sha256)
    if _active_batch(root) is not None:
        raise ValueError("WPB Grok campaign has an active batch")
    numbers = _batch_numbers(root)
    if numbers and not (_batch_root(root, numbers[-1]) / "settlement.json").is_file():
        raise ValueError("WPB Grok predecessor batch is not settled")
    with _grok_bound(resolution) as (lifecycle, base, v9, _v11, _v13, _v15):
        consumed, predecessor = _historical_cell_states(root, campaign_sha256, resolution, authorization_acknowledgement_sha256, lifecycle, v9)
        selected = [str(cell["cell_id"]) for cell in campaign["cells"] if str(cell["cell_id"]) not in consumed][:GROK_BATCH_SIZE]
        if not selected:
            raise ValueError("WPB Grok campaign has no eligible cells")
        number, batch = len(numbers) + 1, _batch_root(root, len(numbers) + 1)
        acknowledgement = {"format_version": 1, "kind": "wpb_grok_batch_acknowledgement", "study_id": STUDY_ID, "campaign_sha256": campaign_sha256, "batch_number": number, "cell_ids": selected, "authorization_acknowledgement_sha256": authorization_acknowledgement_sha256}
        lifecycle._disjoint(batch / "execution", REPO, Path(queue_root), Path(resolution["freeze_root"]))
        route, evidence = v9._validated_route(v9.parent_stack(), base, Path(queue_root), grok_route_provider)(Path(queue_root))
        expiry = _fresh_route(v9, route)
        batch.mkdir(parents=True)
        _write_new(batch / "batch-acknowledgement.json", acknowledgement)
        plan = {"format_version": 1, "kind": "wpb_grok_bounded_batch_plan", "study_id": STUDY_ID, "campaign_sha256": campaign_sha256, "campaign_acknowledgement_sha256": sha256((root / "campaign-acknowledgement.json").read_bytes()), "batch_number": number, "predecessor_settlement_sha256": predecessor, "cell_ids": selected, "route": route, "route_evidence": evidence, "route_sha256": sha256(route), "route_evidence_sha256": sha256(evidence), "route_expiry_utc": expiry, "freshness_seconds": GROK_ROUTE_FRESHNESS_SECONDS, "authorization_acknowledgement_sha256": authorization_acknowledgement_sha256, "batch_acknowledgement_sha256": sha256((batch / "batch-acknowledgement.json").read_bytes())}
        _write_new(batch / "plan.json", plan)
        execution = batch / "execution"
        execution.mkdir()
        schedule = _execution_schedule(resolution)
        lifecycle.write_new(execution / "schedule.json", lifecycle.canonical(schedule))
        for row in _grok_plan_rows(resolution, plan):
            cell_root = execution / str(row["cell_id"])
            cell_root.mkdir()
            raw, prompt, schema = lifecycle.payload(row)
            if prompt != resolution["payloads"][str(row["cell_id"])] or sha256(prompt) != row["payload_sha256"]:
                raise ValueError("WPB Grok prepared payload drifted")
            _prepared, files = lifecycle.artifacts(row, schedule, raw, prompt, schema, route, evidence, authorization_acknowledgement_sha256)
            for name, value in files.items():
                lifecycle.write_new(cell_root / name, value)
            lifecycle.verify_prepared(cell_root, row, schedule, raw, prompt, schema, route, evidence, authorization_acknowledgement_sha256)
    plan_sha256 = sha256((batch / "plan.json").read_bytes())
    return {"study_id": STUDY_ID, "endpoint": "grok", "campaign_sha256": campaign_sha256, "batch_number": number, "plan_sha256": plan_sha256, "prepared_cells": selected, "provider_calls_made": 0, "process_launches": 0, "native_contact_count": 0, "route_expiry_utc": expiry}


class GrokNativeContactOutcome(RuntimeError):
    def __init__(self, state: str, failure_sha256: str):
        self.state = state
        self.failure_sha256 = failure_sha256
        super().__init__("Grok native contact did not complete")


def _grok_broker_module() -> ModuleType:
    schema_source = SCHEMA_SUBSET_PATH.read_bytes()
    if sha256(schema_source) != SCHEMA_SUBSET_SHA256:
        raise ValueError("installed Grok schema dependency drifted")
    units = (("image_canary", IMAGE_CANARY_PATH, IMAGE_CANARY_SHA256), ("grok_usage_evidence", USAGE_EVIDENCE_PATH, USAGE_EVIDENCE_SHA256), ("broker", BROKER_PATH, BROKER_SHA256))
    sources = {name: path.read_bytes() for name, path, _digest in units}
    if any(sha256(sources[name]) != digest for name, _path, digest in units):
        raise ValueError("installed Grok contact broker dependency drifted")
    package_name = "_wpb_pinned_model_work_queue"
    if any(name == package_name or name.startswith(package_name + ".") for name in sys.modules):
        raise ValueError("Grok contact broker module cache is not accepted")
    package = ModuleType(package_name)
    package.__path__ = [str(BROKER_PATH.parent)]  # type: ignore[attr-defined]
    package.__package__ = package_name
    sys.modules[package_name] = package
    modules: dict[str, ModuleType] = {}
    try:
        for name, path, _digest in units:
            module_name = package_name + "." + name
            spec = importlib.util.spec_from_file_location(module_name, path)
            if spec is None:
                raise ValueError("Grok contact broker dependency cannot load")
            modules[name] = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = modules[name]
            exec(compile(sources[name], str(path), "exec"), modules[name].__dict__)
    finally:
        for name in list(sys.modules):
            if name == package_name or name.startswith(package_name + "."):
                sys.modules.pop(name)
    broker_module = modules["broker"]
    if SCHEMA_SUBSET_PATH.read_bytes() != schema_source or any(path.read_bytes() != sources[name] for name, path, _digest in units) or not isinstance(getattr(broker_module, "Broker", None), type) or not isinstance(getattr(broker_module, "GrokNativeProviderError", None), type):
        raise ValueError("Grok contact broker import drifted")
    return broker_module


def _grok_broker(queue_root: Path, factory: Callable[[Path, type[Any], type[Exception]], Any] | None) -> tuple[Any, type[Exception]]:
    if factory is not None:
        module = _grok_broker_module()
        broker = factory(Path(queue_root), module.Broker, module.GrokNativeProviderError)
        if type(broker) is not module.Broker:
            raise ValueError("Grok broker factory must return the exact verified Broker type")
        return broker, module.GrokNativeProviderError
    module = _grok_broker_module()
    return module.Broker(Path(queue_root)), module.GrokNativeProviderError


def _broker_contact_outcome(root: Path, *, route_name: str, outcome: Mapping[str, Any], prompt: bytes) -> None:
    state, failure = outcome.get("state"), outcome.get("failure")
    if state not in {"definitely_not_contacted", "unavailable", "ambiguous"} or not isinstance(failure, Mapping):
        raise ValueError("Grok broker contact outcome is malformed")
    bindings = {"cell_id": Path(root).name, "outbound_payload_sha256": sha256(prompt)}
    for name, key in (("prepared.json", "prepared_sha256"), ("authorization-acknowledgement.json", "acknowledgement_record_sha256"), ("launch-intent.json", "launch_intent_sha256")):
        path = Path(root) / name
        if path.is_file():
            bindings[key] = sha256(path.read_bytes())
    record = {"format_version": 1, "study_id": STUDY_ID, "kind": "grok_native_broker_contact_outcome", "state": state, "route_name": route_name, "broker_sha256": BROKER_SHA256, "bindings": bindings, "failure": dict(failure), "failure_sha256": sha256(failure)}
    path = Path(root) / "broker-contact-outcome.json"
    with path.open("xb") as handle:
        handle.write(canonical(record))


def _brokered_grok_runner(*, broker: Any, route_name: str, runner: Callable[..., Mapping[str, Any]]) -> Callable[..., Mapping[str, Any]]:
    def guarded(**kwargs: Any) -> Mapping[str, Any]:
        outcome = broker.run_grok_native_contact(route_name, lambda: runner(**kwargs))
        if not isinstance(outcome, Mapping) or set(outcome) != {"state", "result", "failure"}:
            raise ValueError("Grok broker returned an invalid contact envelope")
        if outcome["state"] == "completed" and outcome["failure"] is None and isinstance(outcome["result"], Mapping):
            return outcome["result"]
        prompt = kwargs.get("prompt")
        if not isinstance(prompt, bytes):
            raise ValueError("Grok runner omitted its outbound payload bytes")
        _broker_contact_outcome(Path(kwargs["output_dir"]), route_name=route_name, outcome=outcome, prompt=prompt)
        raise GrokNativeContactOutcome(str(outcome["state"]), sha256(outcome["failure"]))
    return guarded


def _shared_grok_runner(*, broker: Any, lifecycle: ModuleType, response_schema: Mapping[str, Any]) -> Callable[..., Mapping[str, Any]]:
    method = broker.run_grok_native_request
    if "expected_route_sha256" not in inspect.signature(method).parameters:
        raise ValueError("shared native request lacks the prepared-route pin")
    frozen_schema, _schema_bytes = broker._freeze_grok_output_schema(dict(response_schema))
    if frozen_schema != response_schema:
        raise ValueError("shared native request changed the frozen response schema")
    source = lifecycle.live()
    system_prompt = "Act as an isolated structured-output evaluator. Do not use memory, tools, web, plans, or subagents."

    def run(*, prompt: bytes, schema_path: Path, output_dir: Path, route: Mapping[str, Any], before_contact: Callable[[], None]) -> Mapping[str, Any]:
        if sha256(GROK_ADAPTER_PATH.read_bytes()) != GROK_ADAPTER_SHA256 or sha256(SCHEMA_SUBSET_PATH.read_bytes()) != SCHEMA_SUBSET_SHA256:
            raise ValueError("shared Grok adapter drifted")
        request = {"prompt": prompt.decode("utf-8")}
        schema = json.loads(schema_path.read_bytes())
        session_id = str(uuid.uuid4())
        # The pinned lifecycle checks this copy at its before-contact checkpoint;
        # the shared adapter separately records its own staged bytes below.
        responses = output_dir / "responses"
        responses.mkdir()
        lifecycle.write_new(responses / "batch-0001.attempt-0001.prompt.txt", prompt)
        outcome = method(str(route["name"]), request, output_schema=schema, nonvisual_max_turns=1,
                         session_id=session_id, before_contact=before_contact,
                         expected_route_sha256=sha256(source.adapter_canonical(dict(route))))
        if not isinstance(outcome, Mapping) or set(outcome) != {"state", "result", "failure"}:
            raise ValueError("invalid shared Grok contact envelope")
        if outcome["state"] != "completed" or outcome["failure"] is not None:
            _broker_contact_outcome(output_dir, route_name=str(route["name"]), outcome=outcome, prompt=prompt)
            raise GrokNativeContactOutcome(str(outcome["state"]), sha256(outcome["failure"]))
        result = outcome["result"]
        if not isinstance(result, Mapping) or not isinstance(result.get("runtime"), Mapping):
            raise ValueError("missing shared Grok success evidence")
        response = broker.read_grok_native_envelope(result["native_envelope_artifact"])
        lifecycle.write_new(responses / "batch-0001.attempt-0001.grok.envelope.json", response)
        proof_path = _shared_result_path(output_dir)
        proof_path.parent.mkdir(exist_ok=True)
        lifecycle.write_new(proof_path, canonical(result))
        envelope = json.loads(response)
        request_id = envelope.get("requestId")
        if envelope.get("sessionId") != session_id or not isinstance(request_id, str) or not request_id:
            raise ValueError("shared Grok native identity drifted")
        identity = {"provider": "xai", "requested_model": "grok-4.6", "reported_model": "grok-4.6-build", "request_id": request_id,
                    "session_id": session_id, "native_endpoint_contact_cardinality": "unproven", "tools_enabled": False}
        settings = {"route_name": route["name"], "adapter": "grok_exec", "requested_model": "grok-4.6", "reported_model": "grok-4.6-build",
                    "requested_reasoning_effort": "high", "tools_enabled": False, "web_search_enabled": False, "subagents_enabled": False,
                    "tool_free_argv": source.TOOL_FREE_ARGV, "system_prompt_override": system_prompt,
                    "sampler": {"batch_number": 1, "attempt_number": 1, "timeout_seconds": float(route["timeout_seconds"]), "nonvisual_max_turns": 1},
                    "runner_prompt_artifact_sha256": sha256(prompt), "reasoning_attested": False}
        _validate_shared_grok_result(proof=canonical(result), native_request=source.adapter_canonical(request),
                                    prompt=prompt, schema=schema_path.read_bytes(), response=response,
                                    route=route, identity=identity, settings=settings)
        return {"native_request_bytes": source.adapter_canonical(request), "native_response_bytes": response, "identity": identity, "effective_settings": settings}

    return run


def _fail_fast_wave(*, rows: tuple[Mapping[str, Any], ...], output_root: Path, endpoint: str, run: Callable[[Mapping[str, Any]], dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep at most ten native calls in flight and stop queuing after a failure."""
    stop = threading.Event()
    outcomes: list[dict[str, Any]] = []
    queued = iter(rows)

    def guarded(row: Mapping[str, Any]) -> dict[str, Any]:
        try:
            if stop.is_set():
                raise ValueError(f"WPB {endpoint} wave already stopped before native dispatch")
            outcome = run(row)
            cell_id = str(row["cell_id"])
            if not isinstance(outcome, Mapping) or outcome.get("cell_id") != cell_id or outcome.get("state") != SUCCESS_STATES[endpoint] or not (Path(output_root) / cell_id / "execution-receipt.json").is_file():
                raise ValueError(f"WPB {endpoint} native call has no exact terminal receipt")
            return dict(outcome)
        except BaseException:
            stop.set()
            raise

    with ThreadPoolExecutor(max_workers=MAX_CONCURRENCY) as pool:
        pending = {}
        while len(pending) < MAX_CONCURRENCY and not stop.is_set():
            try:
                row = next(queued)
            except StopIteration:
                break
            pending[pool.submit(guarded, row)] = row
        failure: BaseException | None = None
        while pending:
            completed, _ = wait(tuple(pending), return_when=FIRST_COMPLETED)
            for future in completed:
                pending.pop(future)
                try:
                    outcomes.append(future.result())
                except BaseException as error:
                    failure = failure or error
            if failure is None and not stop.is_set():
                while len(pending) < MAX_CONCURRENCY:
                    try:
                        row = next(queued)
                    except StopIteration:
                        break
                    if stop.is_set():
                        break
                    pending[pool.submit(guarded, row)] = row
        if failure is not None:
            raise ValueError(f"WPB {endpoint} native wave stopped after a terminal failure; queued cells were not started") from failure
    expected = {str(row["cell_id"]) for row in rows}
    observed = {str(value.get("cell_id")) for value in outcomes}
    if observed != expected or len(outcomes) != len(rows):
        raise ValueError(f"incomplete WPB {endpoint} native terminal receipt wave")
    return outcomes


def execute_batch(*, campaign_root: Path, batch_number: int, queue_root: Path, freeze_root: Path | str, authorization_acknowledgement_sha256: str, allow_remote: bool, grok_broker_factory: Callable[[Path, type[Any], type[Exception]], Any] | None = None, grok_runner_factory: Callable[[type[Exception]], Callable[..., Mapping[str, Any]]] | None = None) -> list[dict[str, Any]]:
    """Execute one prepared batch through the pinned shared native request path."""
    if allow_remote is not True or (grok_runner_factory is not None and not callable(grok_runner_factory)):
        raise ValueError("WPB Grok batch execution requires allow_remote=True and a callable test override when supplied")
    root = Path(campaign_root)
    resolution = _resolution(freeze_root=freeze_root)
    _campaign_value, campaign_sha256 = _campaign(root, resolution, authorization_acknowledgement_sha256)
    active = _active_batch(root)
    if active is not None:
        raise ValueError("WPB Grok campaign has an active batch")
    plan, plan_sha256 = _batch_plan(root, batch_number, campaign_sha256)
    batch = _batch_root(root, batch_number)
    if (batch / "settlement.json").exists():
        raise ValueError("WPB Grok batch is already settled")
    numbers = _batch_numbers(root)
    if batch_number not in numbers or any(not (_batch_root(root, number) / "settlement.json").is_file() for number in numbers if number < batch_number):
        raise ValueError("WPB Grok batch predecessor is not settled")
    if batch_number > 1:
        _previous_plan, previous_plan_sha256 = _batch_plan(root, batch_number - 1, campaign_sha256)
        _previous, previous_settlement_sha256 = _settlement(root, batch_number - 1, previous_plan_sha256, campaign_sha256)
        if plan.get("predecessor_settlement_sha256") != previous_settlement_sha256:
            raise ValueError("WPB Grok batch predecessor binding drifted")
    elif plan.get("predecessor_settlement_sha256") is not None:
        raise ValueError("WPB Grok initial batch has a predecessor")
    execution = batch / "execution"
    rows = _grok_plan_rows(resolution, plan)
    marker = batch / "execution-active.json"
    marker_value = {"format_version": 1, "kind": "wpb_grok_batch_execution_active", "study_id": STUDY_ID, "batch_number": batch_number, "plan_sha256": plan_sha256, "created_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")}
    marker_raw = canonical(marker_value)
    with _grok_bound(resolution) as (lifecycle, base, v9, v11, v13, _v15):
        lifecycle._disjoint(execution, REPO, Path(queue_root), Path(resolution["freeze_root"]))
        route, evidence = plan.get("route"), plan.get("route_evidence")
        if (not isinstance(route, Mapping) or not isinstance(evidence, Mapping) or plan.get("route_sha256") != sha256(route)
                or plan.get("route_evidence_sha256") != sha256(evidence) or plan.get("freshness_seconds") != GROK_ROUTE_FRESHNESS_SECONDS):
            raise ValueError("WPB Grok batch route binding drifted")
        if plan.get("route_expiry_utc") != _fresh_route(v9, route):
            raise ValueError("WPB Grok batch route freshness drifted")
        schedule = _execution_schedule(resolution)
        if _claim_hashes(v9, execution, {str(row["cell_id"]) for row in rows}, lifecycle.canonical(schedule)):
            raise ValueError("WPB Grok batch cells were already claimed")
        for row in rows:
            if _terminal_artifacts(execution / str(row["cell_id"])):
                raise ValueError("WPB Grok batch contains terminal evidence; no resend")
            raw, prompt, schema = lifecycle.payload(row)
            lifecycle.verify_prepared(execution / str(row["cell_id"]), row, schedule, raw, prompt, schema, route, evidence, authorization_acknowledgement_sha256)
        helper = v13.load(v13.RECONCILE, v13.RECONCILE_COMMIT, v13.RECONCILE_SHA256, "_wpb_grok_batch_response_helper").helper()
        parent = v9.parent_stack()
        broker, error_type = _grok_broker(Path(queue_root), grok_broker_factory)
        route_name = route.get("name")
        if not isinstance(route_name, str) or not route_name:
            raise ValueError("WPB Grok route lacks a governed route name")
        if grok_runner_factory is None:
            selected = parent._guard_runner(_shared_grok_runner(broker=broker, lifecycle=lifecycle, response_schema=resolution["core"].RESPONSE_SCHEMA), lifecycle, schedule)
        else:
            selected = parent._guard_runner(grok_runner_factory(error_type), lifecycle, schedule)
            selected = _brokered_grok_runner(broker=broker, route_name=route_name, runner=selected)
        slot_runtime = _batch_slot_runtime(base, execution, rows)
        try:
            with marker.open("xb") as handle:
                handle.write(marker_raw)
        except FileExistsError as error:
            raise ValueError("WPB Grok batch execution is already active") from error

        def run(row: Mapping[str, Any]) -> dict[str, Any]:
            def parse(_helper: Any, raw: bytes, receipt_route: Mapping[str, Any]) -> Any:
                return _grok_answer(resolution["core"], helper, raw, receipt_route)
            return v11._execute_bound(value=schedule, lifecycle=lifecycle, runtime=slot_runtime, v9=v9, reconciler=SimpleNamespace(_response=parse), response_helper=helper, selected=selected, output_root=execution, queue_root=Path(queue_root), authorization_acknowledgement_sha256=authorization_acknowledgement_sha256, cell_id=str(row["cell_id"]), route_provider=lambda _ignored: (route, evidence))

        try:
            return _fail_fast_wave(rows=rows, output_root=execution, endpoint="Grok", run=run)
        finally:
            # A crash intentionally leaves the marker for manual recovery.  This owner
            # clears only the exact marker it created after all futures have settled.
            if marker.is_file() and marker.read_bytes() == marker_raw:
                marker.unlink()


def _batch_slot_runtime(base: ModuleType, execution: Path, rows: tuple[Mapping[str, Any], ...]) -> SimpleNamespace:
    slots = {str(row["cell_id"]): index for index, row in enumerate(rows)}
    if len(slots) != len(rows) or not 1 <= len(slots) <= MAX_CONCURRENCY:
        raise ValueError("invalid bounded batch slot assignment")

    def acquire(output_root: Path, cell_id: str) -> tuple[Path, dict[str, Any]]:
        if Path(output_root) != execution or cell_id not in slots:
            raise ValueError("slot outside the owned batch")
        locks, root_hash = base._slot_root(output_root)
        slot = slots[cell_id]
        path = locks / f"slot-{slot}.lock"
        record = base._slot_record(cell_id=cell_id, slot=slot, output_root_sha256=root_hash)
        # The exclusive batch owner assigns each worker a distinct slot, so no
        # worker inspects another worker's partially published lock file.
        base._write_slot(path, record)
        return path, record

    return SimpleNamespace(_acquire_global_slot=acquire, _release_global_slot=base._release_global_slot, _claim=base._claim)


def _validate_shared_grok_result(*, proof: bytes, native_request: bytes, prompt: bytes, schema: bytes, response: bytes, route: Mapping[str, Any], identity: Mapping[str, Any], settings: Mapping[str, Any]) -> dict[str, Any]:
    """Validate the canonical shared-native result against the admitted receipt bytes."""
    compact = lambda value: canonical(value)[:-1]
    try:
        result = json.loads(proof.decode("utf-8"))
        schema_value = json.loads(schema.decode("utf-8"))
        envelope = json.loads(response.decode("utf-8"))
        request = json.loads(native_request.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("shared Grok native evidence is not JSON") from error
    if (not isinstance(result, dict) or proof != canonical(result) or set(result) != {"schema_version", "request_hash", "output", "output_hash", "runtime", "native_envelope_artifact"}
            or result.get("schema_version") != 2 or native_request != compact(request) or request != {"prompt": prompt.decode("utf-8")}
            or not isinstance(schema_value, Mapping) or schema != canonical(schema_value) or not isinstance(envelope, Mapping)
            or result.get("request_hash") != sha256(native_request) or result.get("output") != envelope.get("structuredOutput")
            or result.get("output_hash") != sha256(compact(result["output"]))):
        raise ValueError("shared Grok result request or output binding drifted")
    native = result["native_envelope_artifact"]
    if (not isinstance(native, Mapping) or set(native) != {"schema_version", "sha256", "byte_length"}
            or native.get("schema_version") != 1 or native.get("sha256") != sha256(response) or native.get("byte_length") != len(response)):
        raise ValueError("shared Grok native envelope descriptor drifted")
    runtime = result["runtime"]
    required_runtime = {"adapter_version", "requested_model", "reported_model", "requested_reasoning_effort", "reasoning_attested", "reasoning_attestation", "identity_evidence", "cli_version", "session_id_hash", "request_id_hash", "envelope_hash", "command_identity", "command_identity_hash", "subscription_receipt_hash", "execution_policy", "usage_telemetry", "execution_contract", "transport", "nonvisual_max_turns", "observed_turns"}
    expected_contract = {"schema_version": 1, "output_schema_hash": sha256(compact(schema_value)), "max_turns": 1, "tools": "none", "staged_prompt_sha256": sha256(prompt), "staged_prompt_byte_length": len(prompt)}
    expected_command = {"adapter_version": 2, "grok_command": route.get("grok_command"), "model": "grok-4.6", "reported_model": "grok-4.6-build", "reasoning_effort": "high"}
    request_id, session_id = envelope.get("requestId"), envelope.get("sessionId")
    if (not isinstance(runtime, Mapping) or set(runtime) != required_runtime or not isinstance(request_id, str) or not request_id or not isinstance(session_id, str) or not session_id
            or runtime.get("adapter_version") != 2 or runtime.get("requested_model") != "grok-4.6" or runtime.get("reported_model") != "grok-4.6-build"
            or runtime.get("requested_reasoning_effort") != "high" or runtime.get("reasoning_attested") is not False or runtime.get("reasoning_attestation") != "not_reported_by_grok_build_cli"
            or runtime.get("identity_evidence") != "requested_only" or runtime.get("cli_version") != route.get("grok_cli_version")
            or runtime.get("command_identity") != route.get("grok_command_identity") or runtime.get("command_identity_hash") != sha256(compact(expected_command))
            or runtime.get("subscription_receipt_hash") != route.get("subscription_receipt_hash") or runtime.get("execution_policy") != "bounded_nonvisual_read_only"
            or runtime.get("execution_contract") != expected_contract or runtime.get("envelope_hash") != sha256(response)
            or runtime.get("session_id_hash") != sha256(session_id.encode("utf-8")) or runtime.get("request_id_hash") != sha256(request_id.encode("utf-8"))
            or runtime.get("nonvisual_max_turns") != 1 or runtime.get("observed_turns") != 1):
        raise ValueError("shared Grok native runtime binding drifted")
    transport = runtime["transport"]
    if (not isinstance(transport, Mapping) or set(transport) != {"schema_version", "exit_code", "stdout_byte_length", "stderr_byte_length"}
            or transport.get("schema_version") != 1 or transport.get("exit_code") != 0 or transport.get("stdout_byte_length") != len(response)
            or type(transport.get("stderr_byte_length")) is not int or transport["stderr_byte_length"] < 0):
        raise ValueError("shared Grok native transport binding drifted")
    expected_usage = {"status": "reported", "total_cost_usd": envelope["total_cost_usd"],
                      "total_cost_usd_ticks": envelope["total_cost_usd_ticks"],
                      "model_cost_usd": envelope["modelUsage"]["grok-4.6-build"]["costUSD"]}
    if runtime["usage_telemetry"] != expected_usage:
        raise ValueError("shared Grok native usage binding drifted")
    expected_identity = {"provider": "xai", "requested_model": "grok-4.6", "reported_model": "grok-4.6-build", "request_id": request_id, "session_id": session_id, "native_endpoint_contact_cardinality": "unproven", "tools_enabled": False}
    if dict(identity) != expected_identity:
        raise ValueError("shared Grok admitted identity drifted")
    sampler = settings.get("sampler") if isinstance(settings, Mapping) else None
    if (set(settings) != {"route_name", "adapter", "requested_model", "reported_model", "requested_reasoning_effort", "tools_enabled", "web_search_enabled", "subagents_enabled", "tool_free_argv", "system_prompt_override", "sampler", "runner_prompt_artifact_sha256", "reasoning_attested"}
            or settings.get("route_name") != route.get("name") or settings.get("adapter") != "grok_exec" or settings.get("requested_model") != "grok-4.6" or settings.get("reported_model") != "grok-4.6-build"
            or settings.get("requested_reasoning_effort") != "high" or settings.get("tools_enabled") is not False or settings.get("web_search_enabled") is not False or settings.get("subagents_enabled") is not False
            or settings.get("tool_free_argv") != ["--max-turns", "1", "--no-leader", "--no-subagents", "--disable-web-search", "--no-plan", "--tools", "", "--permission-mode", "dontAsk", "--sandbox", "read-only", "--verbatim"] or settings.get("system_prompt_override") != "Act as an isolated structured-output evaluator. Do not use memory, tools, web, plans, or subagents."
            or sampler != {"batch_number": 1, "attempt_number": 1, "timeout_seconds": float(route["timeout_seconds"]), "nonvisual_max_turns": 1}
            or settings.get("runner_prompt_artifact_sha256") != sha256(prompt) or settings.get("reasoning_attested") is not False):
        raise ValueError("shared Grok admitted settings drifted")
    return result


def _grok_admit_rows(resolution: Mapping[str, Any], *, lifecycle: ModuleType, v13: ModuleType, execution: Path, rows: tuple[Mapping[str, Any], ...], plan: Mapping[str, Any], acknowledgement: str) -> dict[str, dict[str, Any]]:
    route, evidence = plan["route"], plan["route_evidence"]
    helper = v13.load(v13.RECONCILE, v13.RECONCILE_COMMIT, v13.RECONCILE_SHA256, "_wpb_grok_batch_admit_helper").helper()
    admitted: dict[str, dict[str, Any]] = {}
    schedule = _execution_schedule(resolution)
    for row in rows:
        cell_id = str(row["cell_id"])
        raw, prompt, schema = lifecycle.payload(row)
        request, response, identity, settings = lifecycle.admit(Path(execution) / cell_id, row, schedule, raw, prompt, schema, route, evidence, acknowledgement, lifecycle.live())
        proof = _shared_result_path(Path(execution) / cell_id)
        result = _validate_shared_grok_result(proof=proof.read_bytes(), native_request=request, prompt=prompt, schema=schema, response=response, route=route, identity=identity, settings=settings)
        parsed = _grok_answer(resolution["core"], helper, response, route)
        if result["output"] != parsed["envelope"]["structuredOutput"]:
            raise ValueError("shared Grok result structured output drifted")
        admitted[cell_id] = {"request": request, "response": response, "identity": identity, "settings": settings, "answer": parsed["answer"], "shared_result": result}
    return admitted


def _verify_grok_prepared_cell(resolution: Mapping[str, Any], *, lifecycle: ModuleType, execution: Path, row: Mapping[str, Any], plan: Mapping[str, Any], acknowledgement: str) -> str:
    raw, prompt, schema = lifecycle.payload(row)
    root = Path(execution) / str(row["cell_id"])
    lifecycle.verify_prepared(root, row, _execution_schedule(resolution), raw, prompt, schema, plan["route"], plan["route_evidence"], acknowledgement)
    return sha256((root / "prepared.json").read_bytes())


def _cell_artifact_hashes(root: Path) -> dict[str, str]:
    if not Path(root).is_dir():
        return {}
    artifacts = {path.relative_to(root).as_posix(): sha256(path.read_bytes()) for path in sorted(Path(root).rglob("*")) if path.is_file()}
    proof = _shared_result_path(root)
    if proof.is_file():
        artifacts["@shared-native-result"] = sha256(proof.read_bytes())
    return artifacts


def _shared_result_path(cell_root: Path) -> Path:
    # Shared transport evidence sits outside the inherited strict cell inventory.
    return Path(cell_root).parent.parent / "shared-native-results" / (Path(cell_root).name + ".json")


def _settlement_cells(resolution: Mapping[str, Any], execution: Path, plan: Mapping[str, Any], acknowledgement: str, *, lifecycle: ModuleType, v9: ModuleType, admitted: Mapping[str, Mapping[str, Any]] | None) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    rows = _grok_plan_rows(resolution, plan)
    claim_hashes = _claim_hashes(v9, Path(execution), {str(row["cell_id"]) for row in rows}, lifecycle.canonical(_execution_schedule(resolution)))
    for row in rows:
        cell_id, cell_root = str(row["cell_id"]), Path(execution) / str(row["cell_id"])
        receipt = cell_root / "execution-receipt.json"
        artifacts = _cell_artifact_hashes(cell_root)
        if receipt.is_file():
            identity_path = cell_root / "runtime-identity.json"
            identity_sha256 = sha256(identity_path.read_bytes()) if identity_path.is_file() else None
            if admitted is not None and cell_id in admitted and cell_id in claim_hashes and identity_sha256 is not None:
                identity = admitted[cell_id]["identity"]
                if isinstance(identity, Mapping) and identity.get("request_id") and identity.get("session_id") and sha256(identity) == identity_sha256:
                    entries.append({"cell_id": cell_id, "state": "completed", "artifacts": artifacts, "claim_sha256": claim_hashes[cell_id], "execution_receipt_sha256": sha256(receipt.read_bytes()), "identity_sha256": identity_sha256})
                    continue
            if admitted is None and cell_id in claim_hashes and identity_sha256 is not None:
                entries.append({"cell_id": cell_id, "state": "completed", "artifacts": artifacts, "claim_sha256": claim_hashes[cell_id], "execution_receipt_sha256": sha256(receipt.read_bytes()), "identity_sha256": identity_sha256})
            else:
                entries.append({"cell_id": cell_id, "state": "consumed_terminal", "reason": "malformed_terminal_receipt", "artifacts": artifacts, "artifact_sha256": sha256(receipt.read_bytes()), "claim_sha256": claim_hashes.get(cell_id)})
        elif cell_id in claim_hashes:
            entries.append({"cell_id": cell_id, "state": "consumed_terminal", "reason": "claimed_without_terminal_receipt", "artifacts": artifacts, "claim_sha256": claim_hashes[cell_id]})
        elif _terminal_artifacts(cell_root):
            entries.append({"cell_id": cell_id, "state": "consumed_terminal", "reason": "launch_or_ambiguous_terminal", "artifacts": artifacts})
        else:
            try:
                entries.append({"cell_id": cell_id, "state": "prepared_unlaunched", "artifacts": artifacts, "prepared_sha256": _verify_grok_prepared_cell(resolution, lifecycle=lifecycle, execution=Path(execution), row=row, plan=plan, acknowledgement=acknowledgement)})
            except (TypeError, ValueError, OSError):
                entries.append({"cell_id": cell_id, "state": "consumed_terminal", "reason": "malformed_or_missing_preparation", "artifacts": artifacts})
    return entries


def settle_batch(*, campaign_root: Path, batch_number: int, freeze_root: Path | str, authorization_acknowledgement_sha256: str) -> dict[str, Any]:
    """Write an immutable artifact-based settlement after every owned future is done."""
    root = Path(campaign_root)
    resolution = _resolution(freeze_root=freeze_root)
    _campaign_value, campaign_sha256 = _campaign(root, resolution, authorization_acknowledgement_sha256)
    if _active_batch(root) is not None:
        raise ValueError("WPB Grok campaign has an active batch")
    plan, plan_sha256 = _batch_plan(root, batch_number, campaign_sha256)
    batch = _batch_root(root, batch_number)
    if (batch / "settlement.json").exists():
        raise ValueError("WPB Grok batch is already settled")
    predecessor = plan.get("predecessor_settlement_sha256")
    if batch_number > 1:
        previous_plan, previous_plan_sha256 = _batch_plan(root, batch_number - 1, campaign_sha256)
        _previous, actual_predecessor = _settlement(root, batch_number - 1, previous_plan_sha256, campaign_sha256)
        if predecessor != actual_predecessor:
            raise ValueError("WPB Grok batch predecessor binding drifted")
    elif predecessor is not None:
        raise ValueError("WPB Grok initial batch has a predecessor")
    execution = batch / "execution"
    rows = _grok_plan_rows(resolution, plan)
    admitted: dict[str, dict[str, Any]] = {}
    with _grok_bound(resolution) as (lifecycle, _base, v9, _v11, v13, _v15):
        for row in rows:
            if not (execution / str(row["cell_id"]) / "execution-receipt.json").is_file():
                continue
            try:
                admitted.update(_grok_admit_rows(resolution, lifecycle=lifecycle, v13=v13, execution=execution, rows=(row,), plan=plan, acknowledgement=authorization_acknowledgement_sha256))
            except (TypeError, ValueError, OSError):
                pass
        entries = _settlement_cells(resolution, execution, plan, authorization_acknowledgement_sha256, lifecycle=lifecycle, v9=v9, admitted=admitted)
    settlement = {"format_version": 1, "kind": "wpb_grok_bounded_batch_settlement", "study_id": STUDY_ID, "campaign_sha256": campaign_sha256, "batch_number": batch_number, "plan_sha256": plan_sha256, "predecessor_settlement_sha256": predecessor, "cells": entries}
    _write_new(batch / "settlement.json", settlement)
    return {"study_id": STUDY_ID, "endpoint": "grok", "batch_number": batch_number, "settlement_sha256": sha256((batch / "settlement.json").read_bytes()), "completed_cells": [entry["cell_id"] for entry in entries if entry["state"] == "completed"], "consumed_cells": [entry["cell_id"] for entry in entries if entry["state"] == "consumed_terminal"], "eligible_successors": [entry["cell_id"] for entry in entries if entry["state"] == "prepared_unlaunched"]}


def _sol_runtime(resolution: Mapping[str, Any]) -> tuple[ModuleType, ModuleType, tuple[dict[str, Any], ...]]:
    native = _load_exact(V16, V16_SHA256, V16_COMMIT, "_wpb_v16_sol")
    composition = native._load_pinned(native.V15_SOL, native.V15_SOL_SHA256, native.V15_SOL_COMMIT, "_wpb_v15_sol")
    base = composition._base()
    v9 = base._load(base.V9, base.V9_SHA256, base.V9_COMMIT, "_wpb_sol_lifecycle")
    rows = tuple(resolution["rows"])
    sentinel_sha256 = sha256(TRANSPORT_TARGET)
    compatibility = {"rows": rows, "schedule": {"schedule_sha256": resolution["schedule_sha256"]}, "bindings": {"wpb_core_sha256": CORE_SHA256, "wpb_core_contract_sha256": CORE_CONTRACT_SHA256, "wpb_schedule_sha256": resolution["schedule_sha256"], "wpb_native_contract_sha256": CONTRACT_SHA256, "hanna_csv_sha256": sentinel_sha256, "transport_target_sha256": sentinel_sha256, "result_analyzer_commit": CORE_COMMIT, "result_analyzer_sha256": CORE_SHA256, "result_analyzer_contract_sha256": CORE_CONTRACT_SHA256, "grok_result_sha256": "not_applicable_endpoint_separated_wpb", "grok_result_internal_sha256": None, "grok_execution_commit": CORE_COMMIT, "grok_executor_sha256": CORE_SHA256, "grok_collector_sha256": resolution["schedule_sha256"], "parent_sol_reference": {"candidate_id": "wpb_compact_family", "comparison": "same_wpb_frozen_payloads", "source": "wpb_compact_core"}, "replay_input_commitments": {"wpb_schedule": resolution["schedule_sha256"], "wpb_core": CORE_SHA256, "core_contract": CORE_CONTRACT_SHA256, "native_contract": CONTRACT_SHA256, "transport_target": sentinel_sha256}}}
    lifecycle = v9.desc16_lifecycle()
    lifecycle.STUDY_ID = STUDY_ID
    lifecycle.QUALIFIED_CHILDREN = ("wpb_compact_family",)
    lifecycle.PARENT_CANDIDATE_ID = "wpb_compact_family"
    runtime = lifecycle._configured_base(compatibility)
    lifecycle.STUDY_ID = STUDY_ID
    runtime.STUDY_ID = STUDY_ID
    runtime.SOURCE_RESULT_FILE_SHA256 = resolution["schedule_sha256"]
    runtime.RESULT_INTERNAL_SHA256 = None
    inherited = runtime._prepared

    def validate_answer(value: Mapping[str, Any]) -> dict[str, Any]:
        return _valid_response(resolution["core"], value)

    def prepared(row: Mapping[str, Any], payload: bytes, schema: bytes, target: Mapping[str, Any], route: Mapping[str, Any], evidence: Mapping[str, Any], acknowledgement: str) -> dict[str, bytes]:
        files = inherited(row, payload, schema, target, route, evidence, acknowledgement)
        value = json.loads(files["prepared.json"])
        source = dict(value["source"])
        for key in ("frozen_grok_qualifiers", "parent_sol_reference", "sol_role", "independently_replayed_grok_result_sha256", "independently_replayed_grok_result_internal_sha256", "result_analyzer_commit", "result_analyzer_sha256", "result_analyzer_contract_sha256", "grok_result_sha256", "grok_result_internal_sha256", "grok_execution_commit", "grok_executor_sha256", "grok_collector_sha256", "public_result_commit", "source_result_file_sha256", "source_executor_commit", "source_executor_sha256", "schedule_sha256", "collector_sha256", "result_internal_sha256", "hanna_csv_sha256"):
            source.pop(key, None)
        source.update({"wpb_core_commit": CORE_COMMIT, "wpb_core_sha256": CORE_SHA256, "wpb_core_contract_sha256": CORE_CONTRACT_SHA256, "wpb_schedule_sha256": resolution["schedule_sha256"], "wpb_native_contract_sha256": CONTRACT_SHA256, "transport_target_sha256": sentinel_sha256, "target_vector_semantics": "fixed transport sentinel only; WPB local targets are absent", "sol_role": "unchanged_byte_endpoint_separated_wpb_measurement", "endpoint_pooling": "forbidden", "selection": "development_only", "promotion": "none", "runtime": "none", "confirmation": "closed"})
        value["source"] = source
        files["prepared.json"] = runtime.canonical(value)
        return files

    runtime._validate_answer = validate_answer
    runtime._prepared = prepared
    return lifecycle, runtime, rows


def _sol_prepare(resolution: Mapping[str, Any], *, output_root: Path, queue_root: Path, acknowledgement: str, broker_factory: Callable[[Path], Any] | None) -> dict[str, Any]:
    if Path(output_root).exists():
        raise ValueError("fresh Sol output root required")
    lifecycle, runtime, rows = _sol_runtime(resolution)
    lifecycle._disjoint(Path(output_root), REPO, Path(queue_root), Path(resolution["freeze_root"]))
    route, evidence, _v3 = runtime._route(Path(queue_root), broker_factory)
    Path(output_root).mkdir(parents=True)
    for row in rows:
        root = Path(output_root) / str(row["cell_id"])
        root.mkdir()
        payload = resolution["payloads"][str(row["cell_id"])]
        schema = runtime.canonical(json.loads(payload.decode("utf-8"))["response_schema"])
        for name, raw in runtime._prepared(row, payload, schema, row["target"], route, evidence, acknowledgement).items():
            runtime._write_new(root / name, raw)
    return {"study_id": STUDY_ID, "endpoint": "sol", "prepared_cells": [row["cell_id"] for row in rows], "logical_cells": 129, "partitions": {"train": 105, "dev": 24}, "provider_calls_made": 0, "process_launches": 0, "native_contact_count": 0, "native_contact_count_semantics": "prepared_precontact_only"}


def _sol_execute(resolution: Mapping[str, Any], *, output_root: Path, queue_root: Path, acknowledgement: str, cell_id: str, broker_factory: Callable[[Path], Any] | None, call_codex: Callable[..., Any] | None) -> dict[str, Any]:
    lifecycle, runtime, rows = _sol_runtime(resolution)
    index = {str(row["cell_id"]): row for row in rows}
    if cell_id not in index:
        raise ValueError("unknown WPB Sol cell")
    lifecycle._disjoint(Path(output_root), REPO, Path(queue_root), Path(resolution["freeze_root"]))
    lifecycle._prepared_inventory(runtime, Path(output_root), rows)
    locks = lifecycle._locks(Path(output_root))
    try:
        return lifecycle._execute_prepared(base=runtime, row=index[cell_id], output_root=Path(output_root), queue_root=Path(queue_root), authorization_acknowledgement_sha256=acknowledgement, allow_remote=True, locks=locks, broker_factory=broker_factory, call_codex=call_codex)
    finally:
        if locks.exists() and not any(locks.iterdir()):
            locks.rmdir()


def _sol_wave(resolution: Mapping[str, Any], *, output_root: Path, queue_root: Path, acknowledgement: str, broker_factory: Callable[[Path], Any] | None, call_codex: Callable[..., Any] | None) -> list[dict[str, Any]]:
    lifecycle, runtime, rows = _sol_runtime(resolution)
    lifecycle._disjoint(Path(output_root), REPO, Path(queue_root), Path(resolution["freeze_root"]))
    lifecycle._prepared_inventory(runtime, Path(output_root), rows)
    locks = lifecycle._locks(Path(output_root))
    try:
        def run(row: Mapping[str, Any]) -> dict[str, Any]:
            return lifecycle._execute_prepared(base=runtime, row=row, output_root=Path(output_root), queue_root=Path(queue_root), authorization_acknowledgement_sha256=acknowledgement, allow_remote=True, locks=locks, broker_factory=broker_factory, call_codex=call_codex)
        return _fail_fast_wave(rows=rows, output_root=Path(output_root), endpoint="Sol", run=run)
    finally:
        if locks.exists() and not any(locks.iterdir()):
            locks.rmdir()


def prepare_all(*, endpoint: str, output_root: Path, queue_root: Path, freeze_root: Path | str, authorization_acknowledgement_sha256: str, sol_broker_factory: Callable[[Path], Any] | None = None) -> dict[str, Any]:
    """Materialize the native V16-derived lifecycle only; no contact is made."""
    if endpoint != "sol":
        raise ValueError("single-root Grok preparation is retired; use create_campaign and prepare_next_batch")
    resolution = _resolution(freeze_root=freeze_root)
    return _sol_prepare(resolution, output_root=Path(output_root), queue_root=Path(queue_root), acknowledgement=authorization_acknowledgement_sha256, broker_factory=sol_broker_factory)


def execute_one(*, endpoint: str, output_root: Path, queue_root: Path, freeze_root: Path | str, authorization_acknowledgement_sha256: str, cell_id: str, allow_remote: bool, sol_broker_factory: Callable[[Path], Any] | None = None, call_codex: Callable[..., Any] | None = None) -> dict[str, Any]:
    if endpoint != "sol" or allow_remote is not True:
        raise ValueError("single-root Grok execution is retired; Sol requires explicit allow_remote=True")
    resolution = _resolution(freeze_root=freeze_root)
    outcome = _sol_execute(resolution, output_root=Path(output_root), queue_root=Path(queue_root), acknowledgement=authorization_acknowledgement_sha256, cell_id=cell_id, broker_factory=sol_broker_factory, call_codex=call_codex)
    state = SUCCESS_STATES["Sol"]
    if not isinstance(outcome, Mapping) or outcome.get("cell_id") != cell_id or outcome.get("state") != state or not (Path(output_root) / cell_id / "execution-receipt.json").is_file():
        raise ValueError("WPB native execution did not produce an exact terminal receipt")
    return dict(outcome)


def execute_wave(*, endpoint: str, output_root: Path, queue_root: Path, freeze_root: Path | str, authorization_acknowledgement_sha256: str, allow_remote: bool, sol_broker_factory: Callable[[Path], Any] | None = None, call_codex: Callable[..., Any] | None = None) -> list[dict[str, Any]]:
    if endpoint != "sol" or allow_remote is not True:
        raise ValueError("single-root Grok execution is retired; Sol requires explicit allow_remote=True")
    resolution = _resolution(freeze_root=freeze_root)
    return _sol_wave(resolution, output_root=Path(output_root), queue_root=Path(queue_root), acknowledgement=authorization_acknowledgement_sha256, broker_factory=sol_broker_factory, call_codex=call_codex)


def _grok_measurements(resolution: Mapping[str, Any], *, output_root: Path, acknowledgement: str) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    campaign_root = Path(output_root)
    _campaign_value, campaign_sha256 = _campaign(campaign_root, resolution, acknowledgement)
    if _active_batch(campaign_root) is not None:
        raise ValueError("WPB Grok campaign has an active batch")
    completed: dict[str, tuple[dict[str, Any], dict[str, Any], Path, int, str, str]] = {}
    with _grok_bound(resolution) as (lifecycle, _base, v9, _v11, v13, _v15):
        _historical_cell_states(campaign_root, campaign_sha256, resolution, acknowledgement, lifecycle, v9)
        predecessor: str | None = None
        for number in _batch_numbers(campaign_root):
            plan, plan_sha256 = _batch_plan(campaign_root, number, campaign_sha256)
            settlement, settlement_sha256 = _settlement(campaign_root, number, plan_sha256, campaign_sha256)
            if plan.get("predecessor_settlement_sha256") != predecessor or settlement.get("predecessor_settlement_sha256") != predecessor:
                raise ValueError("WPB Grok report predecessor chain drifted")
            rows = {str(row["cell_id"]): row for row in _grok_plan_rows(resolution, plan)}
            for entry in settlement["cells"]:
                if not isinstance(entry, Mapping) or entry.get("state") != "completed":
                    continue
                cell_id = str(entry["cell_id"])
                if cell_id in completed:
                    raise ValueError("duplicate WPB Grok completed cell")
                completed[cell_id] = (rows[cell_id], plan, _batch_root(campaign_root, number) / "execution", number, plan_sha256, settlement_sha256)
            predecessor = settlement_sha256
        expected = [str(row["cell_id"]) for row in resolution["rows"]]
        if set(completed) != set(expected) or len(completed) != 129:
            raise ValueError("partial WPB Grok campaign cannot produce metrics")
        admitted_by_cell: dict[str, dict[str, Any]] = {}
        for number in _batch_numbers(campaign_root):
            rows = tuple(value[0] for value in completed.values() if value[3] == number)
            if rows:
                row, plan, execution, _number, _plan_sha256, _settlement_sha256 = completed[str(rows[0]["cell_id"])]
                admitted_by_cell.update(_grok_admit_rows(resolution, lifecycle=lifecycle, v13=v13, execution=execution, rows=rows, plan=plan, acknowledgement=acknowledgement))
        measurements: list[dict[str, Any]] = []
        bindings: dict[str, dict[str, Any]] = {}
        identities: set[tuple[str, str]] = set()
        for cell_id in expected:
            row, plan, execution, number, plan_sha256, settlement_sha256 = completed[cell_id]
            admitted = admitted_by_cell[cell_id]
            identity = admitted["identity"]
            key = (str(identity.get("request_id")), str(identity.get("session_id"))) if isinstance(identity, Mapping) else ("", "")
            if not all(key) or key in identities:
                raise ValueError("duplicate or missing WPB Grok native identity")
            identities.add(key)
            answer = admitted["answer"]
            receipt = execution / cell_id / "execution-receipt.json"
            measurements.append({"endpoint": "grok", "cell_id": cell_id, "payload_sha256": row["payload_sha256"], "measurement_provenance": {"endpoint": "grok", "cell_id": cell_id, "payload_sha256": row["payload_sha256"], "parsed_response_sha256": sha256(answer)}, "response": answer})
            bindings[cell_id] = {"native_request_sha256": sha256(admitted["request"]), "raw_response_sha256": sha256(admitted["response"]), "execution_receipt_sha256": sha256(receipt.read_bytes()), "identity_sha256": sha256(identity), "effective_settings_sha256": sha256(admitted["settings"]), "route_sha256": plan["route_sha256"], "route_evidence_sha256": plan["route_evidence_sha256"], "campaign_sha256": campaign_sha256, "batch_number": number, "plan_sha256": plan_sha256, "settlement_sha256": settlement_sha256, "authorization_acknowledgement_sha256": acknowledgement, "wpb_schedule_sha256": resolution["schedule_sha256"], "wpb_core_sha256": CORE_SHA256, "wpb_native_contract_sha256": CONTRACT_SHA256}
    return measurements, bindings


def _sol_measurements(resolution: Mapping[str, Any], *, output_root: Path, acknowledgement: str) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    lifecycle, runtime, rows = _sol_runtime(resolution)
    entries = lifecycle._output_inventory(Path(output_root), rows)
    v4 = lifecycle.sol_v4()
    measurements = []
    bindings: dict[str, dict[str, Any]] = {}
    frozen_route = frozen_evidence = None
    identities: set[tuple[str, str]] = set()
    for row in rows:
        admitted = lifecycle._admit_completed_cell(runtime, v4, row, entries[str(row["cell_id"])], acknowledgement)
        answer = _valid_response(resolution["core"], admitted["answer"])
        identity = admitted["identity"]
        route, evidence = admitted["route"], admitted["route_evidence"]
        if not isinstance(route, Mapping) or not isinstance(evidence, Mapping):
            raise ValueError("WPB Sol native route proof is malformed")
        if frozen_route is None:
            frozen_route, frozen_evidence = route, evidence
        elif route != frozen_route or evidence != frozen_evidence:
            raise ValueError("mixed WPB Sol route or evidence")
        key = (str(identity.get("thread_id")), str(identity.get("session_id"))) if isinstance(identity, Mapping) else ("", "")
        if not all(key) or key in identities:
            raise ValueError("duplicate or missing WPB Sol native identity")
        identities.add(key)
        measurements.append({"endpoint": "sol", "cell_id": row["cell_id"], "payload_sha256": row["payload_sha256"], "measurement_provenance": {"endpoint": "sol", "cell_id": row["cell_id"], "payload_sha256": row["payload_sha256"], "parsed_response_sha256": sha256(answer)}, "response": answer})
        bindings[str(row["cell_id"])] = {"raw_response_sha256": sha256(admitted["final"]), "execution_receipt_sha256": sha256(admitted["receipt"]), "identity_sha256": sha256(identity), "effective_settings_sha256": sha256(admitted["settings"]), "route_sha256": sha256(admitted["route"]), "route_evidence_sha256": sha256(admitted["route_evidence"]), "acknowledgement_sha256": acknowledgement, "wpb_schedule_sha256": resolution["schedule_sha256"], "wpb_core_sha256": CORE_SHA256, "wpb_native_contract_sha256": CONTRACT_SHA256}
    if frozen_route is None or frozen_evidence is None:
        raise ValueError("missing WPB Sol frozen route evidence")
    v4._frozen_route(frozen_route, frozen_evidence, runtime._load_v3(), require_unexpired=False)
    if len(measurements) != 129:
        raise ValueError("incomplete WPB Sol receipt inventory")
    return measurements, bindings


def report(*, endpoint: str, output_root: Path, freeze_root: Path | str, authorization_acknowledgement_sha256: str, profile: Mapping[str, Any]) -> dict[str, Any]:
    """Re-admit native receipts through the unchanged compact analyzer."""
    if endpoint not in ENDPOINTS:
        raise ValueError("endpoint must be grok or sol")
    resolution = _resolution(freeze_root=freeze_root)
    if endpoint == "grok":
        measurements, receipt_bindings = _grok_measurements(resolution, output_root=Path(output_root), acknowledgement=authorization_acknowledgement_sha256)
        _campaign_value, campaign_sha256 = _campaign(Path(output_root), resolution, authorization_acknowledgement_sha256)
        settlement_chain: list[dict[str, Any]] | None = _settlement_chain(Path(output_root), campaign_sha256)
    else:
        measurements, receipt_bindings = _sol_measurements(resolution, output_root=Path(output_root), acknowledgement=authorization_acknowledgement_sha256)
        settlement_chain = None
    analysis = resolution["core"].analyze(Path(freeze_root), measurements, profile)
    return {"format_version": 1, "study_id": STUDY_ID, "kind": "native_receipt_replayed_wpb_compact_family_endpoint_report", "endpoint": endpoint, "native_endpoint_contact_cardinality": "unproven", "local_terminal_receipt_count": len(measurements), "core_commit": CORE_COMMIT, "core_sha256": CORE_SHA256, "core_contract_sha256": CORE_CONTRACT_SHA256, "native_contract_sha256": CONTRACT_SHA256, "wpb_schedule_sha256": resolution["schedule_sha256"], "v16_native_runtime": {"commit": V16_COMMIT, "sha256": V16_SHA256}, "measurement_count": len(measurements), "native_receipt_bindings": receipt_bindings, "batch_settlement_chain": settlement_chain, "authority": "development_screening_only", "confirmation": "closed", "analysis": analysis}


if __name__ == "__main__":
    raise SystemExit("Use the callable API; execution requires an explicit reviewed invocation.")
