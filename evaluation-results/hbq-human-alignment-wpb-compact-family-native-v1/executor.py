"""Pinned V16 native transport composition for the WPB compact-family core."""
from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
import math
import subprocess
import sys
from collections.abc import Callable, Iterator, Mapping
from concurrent.futures import ThreadPoolExecutor
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
CONTRACT_SHA256 = "011e8fa91774c78ed63a786a677dc8d02cf0a5f9fd3c6c5125e519f534843c22"
ENDPOINTS = {"grok", "sol"}
MAX_CONCURRENCY = 10
TRANSPORT_TARGET = {"Relevance": 0.0, "Coherence": 0.0, "Empathy": 0.0, "Surprise": 0.0, "Engagement": 0.0, "Complexity": 0.0}
EXPECTED_CONTRACT = {"authority": {"confirmation": "closed", "endpoint_pooling": "forbidden", "promotion": "none", "runtime": "none", "selection": "development_only"}, "core": {"commit": CORE_COMMIT, "path": CORE.relative_to(REPO).as_posix(), "sha256": CORE_SHA256}, "execution": {"endpoints": ["grok", "sol"], "max_concurrency": 10, "payload_parity": "exact identical bytes per cell across endpoints", "precontact": "prepare_all makes zero provider calls or process launches", "transport": "pinned V16 native Grok/Sol lifecycle; endpoint adapters are test overrides only", "unit": "one rederived WPB pair per call"}, "format_version": 1, "kind": "wpb_compact_family_native_execution", "local_only": {"excluded_from_provider_payload": ["category", "source model", "preferred side", "chosen/rejected labels", "source scores", "local targets"], "sol_transport_target": "fixed all-zero V16 compatibility sentinel; never a WPB label or outbound payload"}, "native_runtime": {"commit": V16_COMMIT, "path": V16.relative_to(REPO).as_posix(), "sha256": V16_SHA256}, "study_id": STUDY_ID}


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


def _grok_prepare(resolution: Mapping[str, Any], *, output_root: Path, queue_root: Path, acknowledgement: str, route_provider: Callable[[Path], tuple[dict[str, Any], dict[str, Any]]] | None) -> dict[str, Any]:
    if Path(output_root).exists():
        raise ValueError("fresh Grok output root required")
    with _grok_bound(resolution) as (lifecycle, base, v9, _v11, _v13, _v15):
        lifecycle._disjoint(Path(output_root), REPO, Path(queue_root), Path(resolution["freeze_root"]))
        result = lifecycle.prepare_all(output_root=Path(output_root), queue_root=Path(queue_root), authorization_acknowledgement_sha256=acknowledgement, route_provider=v9._validated_route(v9.parent_stack(), base, Path(queue_root), route_provider), normalized_root=Path(output_root).parent / ".wpb-grok-normalized", materialization_root=Path(output_root).parent / ".wpb-grok-materialization", frozen_successor_path=Path(output_root).parent / ".wpb-grok-successor.json", hanna_csv_path=Path(resolution["freeze_root"]) / "execution-inputs.json")
    cells = result.get("prepared_cells", [])
    if set(cells) != {row["cell_id"] for row in resolution["rows"]}:
        raise ValueError("native Grok lifecycle did not prepare every WPB cell")
    return {"study_id": STUDY_ID, "endpoint": "grok", "prepared_cells": cells, "logical_cells": 129, "partitions": {"train": 105, "dev": 24}, "provider_calls_made": 0, "process_launches": 0, "native_contact_count": 0, "native_contact_count_semantics": "prepared_precontact_only"}


def _grok_execute(resolution: Mapping[str, Any], *, output_root: Path, queue_root: Path, acknowledgement: str, cell_id: str, route_provider: Callable[[Path], tuple[dict[str, Any], dict[str, Any]]] | None, runner: Callable[..., Mapping[str, Any]] | None) -> dict[str, Any]:
    with _grok_bound(resolution) as (lifecycle, base, v9, v11, v13, _v15):
        rows = {str(row["cell_id"]): row for row in resolution["rows"]}
        if cell_id not in rows:
            raise ValueError("unknown WPB Grok cell")
        lifecycle._disjoint(Path(output_root), REPO, Path(queue_root), Path(resolution["freeze_root"]))
        helper = v13.load(v13.RECONCILE, v13.RECONCILE_COMMIT, v13.RECONCILE_SHA256, "_wpb_grok_response_helper").helper()
        parent = v9.parent_stack()
        route, evidence = v9._validated_route(parent, base, Path(queue_root), route_provider)(Path(queue_root))
        selected = parent._guard_runner(runner or lifecycle.live()._default_runner, lifecycle, _execution_schedule(resolution))

        def parse(_helper: Any, raw: bytes, receipt_route: Mapping[str, Any]) -> Any:
            return _grok_answer(resolution["core"], helper, raw, receipt_route)

        return v11._execute_bound(value=_execution_schedule(resolution), lifecycle=lifecycle, runtime=base, v9=v9, reconciler=SimpleNamespace(_response=parse), response_helper=helper, selected=selected, output_root=Path(output_root), queue_root=Path(queue_root), authorization_acknowledgement_sha256=acknowledgement, cell_id=cell_id, route_provider=lambda _ignored: (route, evidence))


def _grok_wave(resolution: Mapping[str, Any], *, output_root: Path, queue_root: Path, acknowledgement: str, route_provider: Callable[[Path], tuple[dict[str, Any], dict[str, Any]]] | None, runner: Callable[..., Mapping[str, Any]] | None) -> list[dict[str, Any]]:
    rows = tuple(resolution["rows"])
    with _grok_bound(resolution) as (lifecycle, base, v9, v11, v13, _v15):
        lifecycle._disjoint(Path(output_root), REPO, Path(queue_root), Path(resolution["freeze_root"]))
        helper = v13.load(v13.RECONCILE, v13.RECONCILE_COMMIT, v13.RECONCILE_SHA256, "_wpb_grok_wave_response_helper").helper()
        parent = v9.parent_stack()
        route, evidence = v9._validated_route(parent, base, Path(queue_root), route_provider)(Path(queue_root))
        execution = _execution_schedule(resolution)
        selected = parent._guard_runner(runner or lifecycle.live()._default_runner, lifecycle, execution)

        def run(row: Mapping[str, Any]) -> dict[str, Any]:
            def parse(_helper: Any, raw: bytes, receipt_route: Mapping[str, Any]) -> Any:
                return _grok_answer(resolution["core"], helper, raw, receipt_route)
            return v11._execute_bound(value=execution, lifecycle=lifecycle, runtime=base, v9=v9, reconciler=SimpleNamespace(_response=parse), response_helper=helper, selected=selected, output_root=Path(output_root), queue_root=Path(queue_root), authorization_acknowledgement_sha256=acknowledgement, cell_id=str(row["cell_id"]), route_provider=lambda _ignored: (route, evidence))

        with ThreadPoolExecutor(max_workers=MAX_CONCURRENCY) as pool:
            outcomes = list(pool.map(run, rows))
    expected = {str(row["cell_id"]) for row in rows}
    observed = {str(value.get("cell_id")) for value in outcomes if isinstance(value, Mapping)}
    if observed != expected or len(outcomes) != 129 or any(not (Path(output_root) / cell_id / "execution-receipt.json").is_file() for cell_id in expected):
        raise ValueError("incomplete WPB Grok native terminal receipt wave")
    return outcomes


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
        with ThreadPoolExecutor(max_workers=MAX_CONCURRENCY) as pool:
            outcomes = list(pool.map(run, rows))
        expected = {str(row["cell_id"]) for row in rows}
        observed = {str(value.get("cell_id")) for value in outcomes if isinstance(value, Mapping)}
        if observed != expected or len(outcomes) != 129 or any(not (Path(output_root) / cell_id / "execution-receipt.json").is_file() for cell_id in expected):
            raise ValueError("incomplete WPB Sol native terminal receipt wave")
        return outcomes
    finally:
        if locks.exists() and not any(locks.iterdir()):
            locks.rmdir()


def prepare_all(*, endpoint: str, output_root: Path, queue_root: Path, freeze_root: Path | str, authorization_acknowledgement_sha256: str, grok_route_provider: Callable[[Path], tuple[dict[str, Any], dict[str, Any]]] | None = None, sol_broker_factory: Callable[[Path], Any] | None = None) -> dict[str, Any]:
    """Materialize the native V16-derived lifecycle only; no contact is made."""
    if endpoint not in ENDPOINTS:
        raise ValueError("endpoint must be grok or sol")
    resolution = _resolution(freeze_root=freeze_root)
    if endpoint == "grok":
        return _grok_prepare(resolution, output_root=Path(output_root), queue_root=Path(queue_root), acknowledgement=authorization_acknowledgement_sha256, route_provider=grok_route_provider)
    return _sol_prepare(resolution, output_root=Path(output_root), queue_root=Path(queue_root), acknowledgement=authorization_acknowledgement_sha256, broker_factory=sol_broker_factory)


def execute_one(*, endpoint: str, output_root: Path, queue_root: Path, freeze_root: Path | str, authorization_acknowledgement_sha256: str, cell_id: str, allow_remote: bool, grok_route_provider: Callable[[Path], tuple[dict[str, Any], dict[str, Any]]] | None = None, sol_broker_factory: Callable[[Path], Any] | None = None, grok_runner: Callable[..., Mapping[str, Any]] | None = None, call_codex: Callable[..., Any] | None = None) -> dict[str, Any]:
    if endpoint not in ENDPOINTS or allow_remote is not True:
        raise ValueError("execution requires endpoint and explicit allow_remote=True")
    resolution = _resolution(freeze_root=freeze_root)
    if endpoint == "grok":
        outcome = _grok_execute(resolution, output_root=Path(output_root), queue_root=Path(queue_root), acknowledgement=authorization_acknowledgement_sha256, cell_id=cell_id, route_provider=grok_route_provider, runner=grok_runner)
    else:
        outcome = _sol_execute(resolution, output_root=Path(output_root), queue_root=Path(queue_root), acknowledgement=authorization_acknowledgement_sha256, cell_id=cell_id, broker_factory=sol_broker_factory, call_codex=call_codex)
    if not isinstance(outcome, Mapping) or outcome.get("cell_id") != cell_id or not (Path(output_root) / cell_id / "execution-receipt.json").is_file():
        raise ValueError("WPB native execution did not produce an exact terminal receipt")
    return dict(outcome)


def execute_wave(*, endpoint: str, output_root: Path, queue_root: Path, freeze_root: Path | str, authorization_acknowledgement_sha256: str, allow_remote: bool, grok_route_provider: Callable[[Path], tuple[dict[str, Any], dict[str, Any]]] | None = None, sol_broker_factory: Callable[[Path], Any] | None = None, grok_runner: Callable[..., Mapping[str, Any]] | None = None, call_codex: Callable[..., Any] | None = None) -> list[dict[str, Any]]:
    if endpoint not in ENDPOINTS or allow_remote is not True:
        raise ValueError("execution requires endpoint and explicit allow_remote=True")
    resolution = _resolution(freeze_root=freeze_root)
    if endpoint == "grok":
        return _grok_wave(resolution, output_root=Path(output_root), queue_root=Path(queue_root), acknowledgement=authorization_acknowledgement_sha256, route_provider=grok_route_provider, runner=grok_runner)
    return _sol_wave(resolution, output_root=Path(output_root), queue_root=Path(queue_root), acknowledgement=authorization_acknowledgement_sha256, broker_factory=sol_broker_factory, call_codex=call_codex)


def _grok_measurements(resolution: Mapping[str, Any], *, output_root: Path, acknowledgement: str) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    rows = tuple(resolution["rows"])
    with _grok_bound(resolution) as (lifecycle, _base, v9, _v11, v13, _v15):
        helper = v13.load(v13.RECONCILE, v13.RECONCILE_COMMIT, v13.RECONCILE_SHA256, "_wpb_grok_report_helper").helper()
        v9._validate_claims(Path(output_root), {str(row["cell_id"]) for row in rows})
        source = lifecycle.live()
        measurements = []
        bindings: dict[str, dict[str, Any]] = {}
        frozen_route = frozen_evidence = None
        identities: set[tuple[str, str]] = set()
        for row in rows:
            root = Path(output_root) / str(row["cell_id"])
            stored = v9.strict(v9.stable(root / "prepared.json"), "WPB prepared")
            route, evidence = stored.get("route"), stored.get("route_evidence")
            if not isinstance(route, Mapping) or not isinstance(evidence, Mapping):
                raise ValueError("WPB native route proof is malformed")
            if frozen_route is None:
                frozen_route, frozen_evidence = route, evidence
            elif route != frozen_route or evidence != frozen_evidence:
                raise ValueError("mixed WPB Grok route or evidence")
            raw, prompt, schema = lifecycle.payload(row)
            request, response, identity, settings = lifecycle.admit(root, row, _execution_schedule(resolution), raw, prompt, schema, route, evidence, acknowledgement, source)
            answer = _grok_answer(resolution["core"], helper, response, route)["answer"]
            key = (str(identity.get("request_id")), str(identity.get("session_id"))) if isinstance(identity, Mapping) else ("", "")
            if not all(key) or key in identities:
                raise ValueError("duplicate or missing WPB Grok native identity")
            identities.add(key)
            measurements.append({"endpoint": "grok", "cell_id": row["cell_id"], "payload_sha256": row["payload_sha256"], "measurement_provenance": {"endpoint": "grok", "cell_id": row["cell_id"], "payload_sha256": row["payload_sha256"], "parsed_response_sha256": sha256(answer)}, "response": answer})
            bindings[str(row["cell_id"])] = {"native_request_sha256": sha256(request), "raw_response_sha256": sha256(response), "execution_receipt_sha256": sha256(v9.stable(root / "execution-receipt.json")), "identity_sha256": sha256(identity), "effective_settings_sha256": sha256(settings), "route_sha256": sha256(route), "route_evidence_sha256": sha256(evidence), "acknowledgement_sha256": acknowledgement, "wpb_schedule_sha256": resolution["schedule_sha256"], "wpb_core_sha256": CORE_SHA256, "wpb_native_contract_sha256": CONTRACT_SHA256}
        if frozen_route is None or frozen_evidence is None:
            raise ValueError("missing WPB Grok frozen route evidence")
        lifecycle.validate_frozen_route(frozen_route, frozen_evidence)
        v9.parent_stack()._validate_route_evidence(frozen_route, frozen_evidence)
    if len(measurements) != 129:
        raise ValueError("incomplete WPB Grok receipt inventory")
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
    measurements, receipt_bindings = _grok_measurements(resolution, output_root=Path(output_root), acknowledgement=authorization_acknowledgement_sha256) if endpoint == "grok" else _sol_measurements(resolution, output_root=Path(output_root), acknowledgement=authorization_acknowledgement_sha256)
    analysis = resolution["core"].analyze(Path(freeze_root), measurements, profile)
    return {"format_version": 1, "study_id": STUDY_ID, "kind": "native_receipt_replayed_wpb_compact_family_endpoint_report", "endpoint": endpoint, "native_endpoint_contact_cardinality": "unproven", "local_terminal_receipt_count": len(measurements), "core_commit": CORE_COMMIT, "core_sha256": CORE_SHA256, "core_contract_sha256": CORE_CONTRACT_SHA256, "native_contract_sha256": CONTRACT_SHA256, "wpb_schedule_sha256": resolution["schedule_sha256"], "v16_native_runtime": {"commit": V16_COMMIT, "sha256": V16_SHA256}, "measurement_count": len(measurements), "native_receipt_bindings": receipt_bindings, "authority": "development_screening_only", "confirmation": "closed", "analysis": analysis}


if __name__ == "__main__":
    raise SystemExit("Use the callable API; execution requires an explicit reviewed invocation.")
