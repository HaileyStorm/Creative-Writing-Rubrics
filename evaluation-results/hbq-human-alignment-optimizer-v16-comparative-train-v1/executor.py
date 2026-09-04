"""Endpoint-separated V16 receipt composition over the frozen comparative core."""
from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
import math
import re
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
STUDY_ID = "hbq-human-alignment-optimizer-v16-comparative-train-v1"
CORE = HERE / "study.py"
CORE_COMMIT = "bfdb0d2"
V15 = REPO / "evaluation-results/hbq-human-alignment-optimizer-v15-rank-discrimination-v1/study.py"
V15_SHA256 = "4afeaff679efaf37e702c08841eb30a3317693e677ecfc3ded4dbb4ae4710caf"
V15_COMMIT = "3b28c30"
V15_SOL = REPO / "evaluation-results/hbq-human-alignment-optimizer-v15-rank-discrimination-v1/sol.py"
V15_SOL_SHA256 = "0fa72115f578ca59d867b1cec85cb21ad04aa9baf9e850f219599441e62263c7"
V15_SOL_COMMIT = "60a2422"
DIMS = ("Relevance", "Coherence", "Empathy", "Surprise", "Engagement", "Complexity")
DIRECT, FORWARD, REVERSE = "direct_integer", "comparative_forward", "comparative_reverse"
ENDPOINTS = {"grok", "sol"}
MAX_CONCURRENCY = 10


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def sha256(value: bytes | Any) -> str:
    return hashlib.sha256(value if isinstance(value, bytes) else canonical(value)).hexdigest()


def _load_pinned(path: Path, digest: str, commit: str, name: str) -> ModuleType:
    raw = Path(path).read_bytes()
    blob = subprocess.run(["git", "-C", str(REPO), "show", f"{commit}:{Path(path).relative_to(REPO).as_posix()}"], capture_output=True, check=False)
    if blob.returncode or sha256(raw) != digest or blob.stdout != raw:
        raise ValueError("pinned dependency drifted")
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ValueError("pinned dependency cannot load")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(name, None)
    return module


def _core(expected_core_sha256: str) -> ModuleType:
    if re.fullmatch(r"[0-9a-f]{64}", expected_core_sha256) is None or sha256(CORE.read_bytes()) != expected_core_sha256:
        raise ValueError("explicit V16 core hash does not bind current source")
    blob = subprocess.run(["git", "-C", str(REPO), "show", f"{CORE_COMMIT}:{CORE.relative_to(REPO).as_posix()}"], capture_output=True, check=False)
    if blob.returncode or blob.stdout != CORE.read_bytes():
        raise ValueError("committed V16 core source drifted")
    spec = importlib.util.spec_from_file_location("_v16_core", CORE)
    if spec is None or spec.loader is None:
        raise ValueError("V16 core cannot load")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if sha256(CORE.read_bytes()) != expected_core_sha256:
        raise ValueError("V16 core changed during load")
    return module


def _resolution(*, split_manifest: Path, hanna_csv: Path, successor_contract: Path, expected_core_sha256: str) -> dict[str, Any]:
    core = _core(expected_core_sha256)
    paths = {"split_manifest": Path(split_manifest).resolve(), "hanna_csv": Path(hanna_csv).resolve(), "successor_contract": Path(successor_contract).resolve()}
    schedule = core.schedule(**paths)
    commitment = dict(schedule) if isinstance(schedule, Mapping) else {}
    schedule_sha256 = commitment.pop("schedule_sha256", None)
    if (not isinstance(schedule, Mapping) or schedule.get("study_id") != STUDY_ID or schedule.get("geometry", {}).get("logical_cells") != 39
            or schedule_sha256 != sha256(commitment) or schedule.get("authority", {}).get("endpoint_pooling") != "forbidden"):
        raise ValueError("V16 core schedule binding drifted")
    new = schedule.get("cells")
    reused = schedule.get("reused_direct_cells")
    if not isinstance(new, list) or not isinstance(reused, list) or len(new) != 39 or len(reused) != 21:
        raise ValueError("V16 executable/reused geometry drifted")
    payloads: dict[str, bytes] = {}
    for row in new:
        if not isinstance(row, Mapping) or row.get("condition") not in {DIRECT, FORWARD, REVERSE} or not isinstance(row.get("cell_id"), str):
            raise ValueError("V16 executable row drifted")
        raw = base64.b64decode(str(row.get("payload_base64", "")), validate=True)
        if row.get("payload_sha256") != sha256(raw) or row.get("endpoint_payload_sha256s") != {"grok_primary": sha256(raw), "sol_later": sha256(raw)}:
            raise ValueError("V16 endpoint payload parity drifted")
        payloads[row["cell_id"]] = raw
    if len(payloads) != 39 or sum(row["condition"] == DIRECT for row in new) != 29 or sum(row["condition"] in {FORWARD, REVERSE} for row in new) != 10:
        raise ValueError("V16 new-call geometry drifted")
    return {"core": core, "schedule": schedule, "schedule_sha256": schedule_sha256, "new": tuple(new), "reused": tuple(reused), "payloads": payloads, "source_paths": paths, "core_sha256": expected_core_sha256}


def _source_roots(resolution: Mapping[str, Any]) -> tuple[Path, ...]:
    return tuple(path.parent for path in resolution["source_paths"].values())


def _execution_schedule(resolution: Mapping[str, Any]) -> dict[str, Any]:
    """The lower lifecycle owns only fresh calls, but persists the full-core binding."""
    value: dict[str, Any] = {
        "format_version": 1,
        "study_id": STUDY_ID,
        "cells": list(resolution["new"]),
        "v16_core_sha256": resolution["core_sha256"],
        "v16_schedule_sha256": resolution["schedule_sha256"],
    }
    value["schedule_sha256"] = sha256(value)
    return value


@contextmanager
def _grok_bound(resolution: Mapping[str, Any]) -> Iterator[tuple[ModuleType, ModuleType, ModuleType, ModuleType, ModuleType, ModuleType]]:
    v15 = _load_pinned(V15, V15_SHA256, V15_COMMIT, "_v16_v15_grok")
    v13 = v15.load(v15.V13, v15.V13_COMMIT, v15.V13_SHA256, "_v16_v13")
    v11 = v13.load(v13.V11, v13.V11_COMMIT, v13.V11_SHA256, "_v16_v11")
    payloads = set(resolution["payloads"].values())
    schedule = _execution_schedule(resolution)
    with v11.bound(schedule_value=schedule) as (lifecycle, runtime, v9):
        prior_study, prior_precontact = lifecycle.STUDY_ID, v9._validate_precontact_payload

        def exact_precontact(payload: bytes) -> None:
            if type(payload) is not bytes or payload not in payloads:
                raise ValueError("outbound payload is not an exact V16 frozen payload")

        lifecycle.STUDY_ID, v9._validate_precontact_payload = STUDY_ID, exact_precontact
        try:
            yield lifecycle, runtime, v9, v11, v13, v15
        finally:
            lifecycle.STUDY_ID, v9._validate_precontact_payload = prior_study, prior_precontact


def _grok_answer(core: ModuleType, v15: ModuleType, helper: Any, raw: bytes, route: Mapping[str, Any], row: Mapping[str, Any]) -> dict[str, Any]:
    envelope = helper.strict(raw, "native response", canonical_required=False)
    reported = route.get("reported_model")
    structured = envelope.get("structuredOutput")
    if (set(envelope) != helper.RESPONSE_FIELDS or envelope.get("stopReason") != "end_turn" or envelope.get("num_turns") != 1
            or not isinstance(envelope.get("requestId"), str) or not envelope["requestId"] or not isinstance(envelope.get("sessionId"), str)
            or not envelope["sessionId"] or not isinstance(reported, str) or not isinstance(envelope.get("text"), str)
            or not isinstance(structured, Mapping) or helper.strict(envelope["text"].encode("utf-8"), "native response text", canonical_required=False) != structured):
        raise ValueError("native response identity or structured output drifted")
    usage = envelope.get("usage")
    usage_keys = {"input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens", "reasoning_tokens", "total_tokens"}
    model_usage = envelope.get("modelUsage")
    model_keys = {"inputTokens", "outputTokens", "cacheReadInputTokens", "cacheCreationInputTokens", "modelCalls", "costUSD"}
    if (not isinstance(usage, Mapping) or set(usage) != usage_keys or any(type(usage[key]) is not int or usage[key] < 0 for key in usage_keys)
            or usage["input_tokens"] <= 0 or usage["output_tokens"] <= 0 or usage["total_tokens"] < max(usage["input_tokens"], usage["output_tokens"])
            or not isinstance(model_usage, Mapping) or set(model_usage) != {reported} or not isinstance(model_usage[reported], Mapping)
            or set(model_usage[reported]) != model_keys or model_usage[reported].get("modelCalls") != 1):
        raise ValueError("native response usage telemetry drifted")
    model = model_usage[reported]
    if any(type(model[key]) is not int or model[key] < 0 for key in model_keys - {"costUSD"}) or model["inputTokens"] <= 0 or model["outputTokens"] <= 0:
        raise ValueError("native response model call telemetry drifted")
    cost, ticks = helper._nonnegative_number(envelope.get("total_cost_usd"), "cost"), envelope.get("total_cost_usd_ticks")
    if (type(ticks) is not int or ticks < 0 or ticks != round(cost * 10_000_000_000)
            or not math.isclose(helper._nonnegative_number(model["costUSD"], "model cost"), cost, rel_tol=0, abs_tol=1e-12)
            or not isinstance(envelope.get("thought"), str)):
        raise ValueError("native response cost or thought telemetry drifted")
    answer = core.validate_answer(str(row["condition"]), structured, expected_item_ids=row.get("item_ids"))
    return {"envelope": dict(envelope), "answer": answer}


def _grok_prepare(resolution: Mapping[str, Any], *, output_root: Path, queue_root: Path, acknowledgement: str, route_provider: Callable[[Path], tuple[dict[str, Any], dict[str, Any]]] | None) -> dict[str, Any]:
    if Path(output_root).exists():
        raise ValueError("fresh Grok output root required")
    with _grok_bound(resolution) as (lifecycle, runtime, v9, _v11, _v13, _v15):
        lifecycle._disjoint(Path(output_root), REPO, Path(queue_root), *_source_roots(resolution))
        result = lifecycle.prepare_all(output_root=Path(output_root), queue_root=Path(queue_root), authorization_acknowledgement_sha256=acknowledgement, route_provider=v9._validated_route(v9.parent_stack(), runtime, Path(queue_root), route_provider), normalized_root=Path(output_root).parent / ".v16-grok-normalized", materialization_root=Path(output_root).parent / ".v16-grok-materialization", frozen_successor_path=Path(output_root).parent / ".v16-grok-successor.json", hanna_csv_path=Path(output_root).parent / ".v16-grok-source.csv")
    prepared = result.get("prepared_cells", [])
    if set(prepared) != {row["cell_id"] for row in resolution["new"]} or len(prepared) != 39:
        raise ValueError("lower lifecycle did not prepare exact V16 Grok cells")
    return {"study_id": STUDY_ID, "endpoint": "grok", "prepared_cells": prepared, "logical_cells": 39, "provider_calls_made": 0, "process_launches": 0}


def _grok_execute_wave(resolution: Mapping[str, Any], *, output_root: Path, queue_root: Path, acknowledgement: str, route_provider: Callable[[Path], tuple[dict[str, Any], dict[str, Any]]] | None, runner: Callable[..., Mapping[str, Any]] | None) -> list[dict[str, Any]]:
    with _grok_bound(resolution) as (lifecycle, runtime, v9, v11, v13, v15):
        core, parent = resolution["core"], v9.parent_stack()
        helper = v13.load(v13.RECONCILE, v13.RECONCILE_COMMIT, v13.RECONCILE_SHA256, "_v16_grok_helper").helper()
        route, evidence = v9._validated_route(parent, runtime, Path(queue_root), route_provider)(Path(queue_root))
        execution = _execution_schedule(resolution)
        selected = parent._guard_runner(runner or lifecycle.live()._default_runner, lifecycle, execution)

        def run(row: Mapping[str, Any]) -> dict[str, Any]:
            def parse(_helper: Any, raw: bytes, receipt_route: Mapping[str, Any]) -> Any:
                return _grok_answer(core, v15, helper, raw, receipt_route, row)
            return v11._execute_bound(value=execution, lifecycle=lifecycle, runtime=runtime, v9=v9, reconciler=SimpleNamespace(_response=parse), response_helper=helper, selected=selected, output_root=Path(output_root), queue_root=Path(queue_root), authorization_acknowledgement_sha256=acknowledgement, cell_id=str(row["cell_id"]), route_provider=lambda _ignored: (route, evidence))

        pilot = next(row for row in resolution["new"] if row["condition"] in {FORWARD, REVERSE})
        direct = [row for row in resolution["new"] if row["condition"] == DIRECT]
        remaining = [row for row in resolution["new"] if row is not pilot and row["condition"] in {FORWARD, REVERSE}]
        with ThreadPoolExecutor(max_workers=MAX_CONCURRENCY) as pool:
            initial = list(pool.map(run, [pilot, *direct]))
        if not any(value.get("cell_id") == pilot["cell_id"] for value in initial if isinstance(value, Mapping)):
            raise ValueError("V16 first comparative batch did not return a terminal receipt")
        _grok_admit(resolution, lifecycle=lifecycle, v9=v9, v15=v15, helper=helper, output_root=Path(output_root), acknowledgement=acknowledgement, row=pilot)
        with ThreadPoolExecutor(max_workers=MAX_CONCURRENCY) as pool:
            return [*initial, *pool.map(run, remaining)]


def _grok_admit(resolution: Mapping[str, Any], *, lifecycle: ModuleType, v9: ModuleType, v15: ModuleType, helper: Any, output_root: Path, acknowledgement: str, row: Mapping[str, Any]) -> dict[str, Any]:
    root = Path(output_root) / str(row["cell_id"])
    stored = v9.strict(v9.stable(root / "prepared.json"), "prepared")
    route, evidence = stored.get("route"), stored.get("route_evidence")
    if not isinstance(route, Mapping) or not isinstance(evidence, Mapping):
        raise TypeError("Grok prepared route evidence is invalid")
    source = lifecycle.live(); raw, prompt, schema = lifecycle.payload(row)
    _request, response, identity, settings = lifecycle.admit(root, row, _execution_schedule(resolution), raw, prompt, schema, route, evidence, acknowledgement, source)
    parsed = _grok_answer(resolution["core"], v15, helper, response, route, row)
    return {"identity": identity, "settings": settings, "route": route, "route_evidence": evidence, "response": response, **parsed}


def _panel_targets(resolution: Mapping[str, Any]) -> dict[str, dict[str, float]]:
    panel = resolution["schedule"].get("panel")
    if not isinstance(panel, list):
        raise TypeError("V16 panel is unavailable")
    targets: dict[str, dict[str, float]] = {}
    for item in panel:
        if not isinstance(item, Mapping) or not isinstance(item.get("item_id"), str) or not isinstance(item.get("target"), Mapping):
            raise TypeError("V16 panel target is malformed")
        target = {dimension: float(item["target"][dimension]) for dimension in DIMS}
        if set(item["target"]) != set(DIMS) or any(not math.isfinite(value) for value in target.values()):
            raise ValueError("V16 panel target is invalid")
        targets[item["item_id"]] = target
    if len(targets) != 50:
        raise ValueError("V16 panel target count drifted")
    return targets


def _sol_rows(resolution: Mapping[str, Any]) -> tuple[dict[str, Any], ...]:
    targets = _panel_targets(resolution)
    rows: list[dict[str, Any]] = []
    for source in resolution["new"]:
        row = dict(source)
        row["source_cell_id"] = str(source["cell_id"])
        row["candidate_id"] = str(source["condition"])
        row["payload_parity"] = "v16_core_endpoint_payload_exact"
        if source["condition"] == DIRECT:
            item_id = source.get("item_id")
            if not isinstance(item_id, str) or item_id not in targets:
                raise ValueError("V16 direct target binding drifted")
            row["story_id"] = item_id
            row["target"] = targets[item_id]
        else:
            item_ids = source.get("item_ids")
            if not isinstance(item_ids, list) or len(item_ids) != 10 or len(set(item_ids)) != 10 or any(item_id not in targets for item_id in item_ids):
                raise ValueError("V16 batch target binding drifted")
            # The inherited lifecycle requires item_id/story_id fields for a
            # target-vector artifact.  These are batch identities, explicitly
            # labeled below; the target itself remains all ten true item vectors.
            row["item_id"] = "batch:" + str(source["cell_id"])
            row["story_id"] = row["item_id"]
            row["target"] = {item_id: targets[item_id] for item_id in item_ids}
        rows.append(row)
    if len(rows) != 39 or len({row["cell_id"] for row in rows}) != 39:
        raise ValueError("V16 Sol executable row geometry drifted")
    return tuple(sorted(rows, key=lambda row: str(row["cell_id"])))


def _sol_runtime(resolution: Mapping[str, Any]) -> tuple[ModuleType, ModuleType, tuple[dict[str, Any], ...]]:
    composition = _load_pinned(V15_SOL, V15_SOL_SHA256, V15_SOL_COMMIT, "_v16_v15_sol")
    base = composition._base()
    v9 = base._load(base.V9, base.V9_SHA256, base.V9_COMMIT, "_v16_sol_lifecycle")
    rows = _sol_rows(resolution)
    bindings = {
        "v16_core_sha256": resolution["core_sha256"],
        "v16_schedule_sha256": resolution["schedule_sha256"],
        "hanna_csv_sha256": sha256(Path(resolution["source_paths"]["hanna_csv"]).read_bytes()),
    }
    compatibility = {
        "rows": rows,
        "schedule": {"schedule_sha256": resolution["schedule_sha256"]},
        "bindings": {
            **bindings,
            "result_analyzer_commit": "not_applicable_exact_v16_frozen_schedule",
            "result_analyzer_sha256": resolution["schedule_sha256"],
            "result_analyzer_contract_sha256": resolution["schedule_sha256"],
            "grok_result_sha256": resolution["schedule_sha256"],
            "grok_result_internal_sha256": None,
            "grok_execution_commit": "not_applicable_exact_v16_frozen_schedule",
            "grok_executor_sha256": resolution["core_sha256"],
            "grok_collector_sha256": resolution["schedule_sha256"],
            "parent_sol_reference": {"candidate_id": DIRECT, "comparison": "same_v16_comparative_train_frozen_schedule_matched_sol_only", "source": "v16_frozen_schedule"},
            "replay_input_commitments": {"v16_schedule": resolution["schedule_sha256"], "v16_core": resolution["core_sha256"]},
        },
    }
    lifecycle = v9.desc16_lifecycle()
    lifecycle.STUDY_ID = v9.STUDY_ID
    lifecycle.QUALIFIED_CHILDREN = (v9.CHILD,)
    lifecycle.PARENT_CANDIDATE_ID = v9.PARENT
    lifecycle.RESULT_FILE_SHA256 = v9.RESULT_FILE_SHA256
    lifecycle.RESULT_INTERNAL_SHA256 = v9.RESULT_INTERNAL_SHA256
    runtime = lifecycle._configured_base(compatibility)
    lifecycle.STUDY_ID = STUDY_ID
    lifecycle.QUALIFIED_CHILDREN = (DIRECT, FORWARD, REVERSE)
    lifecycle.PARENT_CANDIDATE_ID = DIRECT
    runtime.STUDY_ID = STUDY_ID
    runtime.SOURCE_RESULT_FILE_SHA256 = resolution["schedule_sha256"]
    runtime.RESULT_INTERNAL_SHA256 = None

    def validate_answer(value: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(value, Mapping):
            raise TypeError("V16 Sol final response is not an object")
        try:
            return resolution["core"].validate_answer(DIRECT, value)
        except (TypeError, ValueError):
            pass
        # The lower callback has no row parameter.  It can nevertheless accept
        # a comparative response only if it exactly matches one frozen ten-item
        # ordering; _sol_admit then binds that answer to the particular row.
        for row in rows:
            if row["condition"] not in {FORWARD, REVERSE}:
                continue
            try:
                return resolution["core"].validate_answer(str(row["condition"]), value, expected_item_ids=row["item_ids"])
            except (TypeError, ValueError):
                continue
        raise ValueError("V16 Sol final response does not match a frozen response schema")

    runtime._validate_answer = validate_answer
    inherited = runtime._prepared

    def prepared(row: Mapping[str, Any], payload: bytes, schema: bytes, target: Mapping[str, Any], route: Mapping[str, Any], evidence: Mapping[str, Any], acknowledgement: str) -> dict[str, bytes]:
        files = inherited(row, payload, schema, target, route, evidence, acknowledgement)
        target_file = json.loads(files["target-vector.json"])
        prepared_value = json.loads(files["prepared.json"])
        if row["condition"] in {FORWARD, REVERSE}:
            target_file.update({"kind": "v16_comparative_panel_target_map", "item_ids": list(row["item_ids"]), "target_scope": "ten_true_panel_item_vectors_not_an_aggregate"})
            files["target-vector.json"] = runtime.canonical(target_file)
            prepared_value["target_vector_sha256"] = sha256(files["target-vector.json"])
        source = dict(prepared_value["source"])
        for key in ("frozen_grok_qualifiers", "parent_sol_reference", "sol_role", "independently_replayed_grok_result_sha256", "independently_replayed_grok_result_internal_sha256", "result_analyzer_commit", "result_analyzer_sha256", "result_analyzer_contract_sha256"):
            source.pop(key, None)
        source.update({"v16_core_sha256": bindings["v16_core_sha256"], "v16_schedule_sha256": bindings["v16_schedule_sha256"], "sol_role": "matched_train_measurement_on_v16_comparative_frozen_schedule", "endpoint_pooling": "forbidden", "selection": "none", "promotion": "none", "generalization": "none"})
        prepared_value["source"] = source
        files["prepared.json"] = runtime.canonical(prepared_value)
        return files

    runtime._prepared = prepared
    return lifecycle, runtime, rows


def _sol_prepare(resolution: Mapping[str, Any], *, output_root: Path, queue_root: Path, acknowledgement: str, broker_factory: Callable[[Path], Any] | None) -> dict[str, Any]:
    if Path(output_root).exists():
        raise ValueError("fresh Sol output root required")
    lifecycle, runtime, rows = _sol_runtime(resolution)
    lifecycle._disjoint(Path(output_root), REPO, Path(queue_root), *_source_roots(resolution))
    route, evidence, _v3 = runtime._route(Path(queue_root), broker_factory)
    Path(output_root).mkdir(parents=True)
    for row in rows:
        root = Path(output_root) / str(row["cell_id"])
        root.mkdir()
        payload = resolution["payloads"][row["cell_id"]]
        schema = runtime.canonical(json.loads(payload.decode("utf-8"))["response_schema"])
        for name, raw in runtime._prepared(row, payload, schema, row["target"], route, evidence, acknowledgement).items():
            runtime._write_new(root / name, raw)
    return {"study_id": STUDY_ID, "endpoint": "sol", "prepared_cells": [row["cell_id"] for row in rows], "logical_cells": 39, "provider_calls_made": 0, "process_launches": 0}


def _sol_execute(resolution: Mapping[str, Any], *, output_root: Path, queue_root: Path, acknowledgement: str, cell_id: str, broker_factory: Callable[[Path], Any] | None, call_codex: Callable[..., Any] | None) -> dict[str, Any]:
    lifecycle, runtime, rows = _sol_runtime(resolution)
    index = {row["cell_id"]: row for row in rows}
    if cell_id not in index:
        raise ValueError("unknown V16 Sol cell")
    lifecycle._disjoint(Path(output_root), REPO, Path(queue_root), *_source_roots(resolution))
    lifecycle._prepared_inventory(runtime, Path(output_root), rows)
    locks = lifecycle._locks(Path(output_root))
    try:
        return lifecycle._execute_prepared(base=runtime, row=index[cell_id], output_root=Path(output_root), queue_root=Path(queue_root), authorization_acknowledgement_sha256=acknowledgement, allow_remote=True, locks=locks, broker_factory=broker_factory, call_codex=call_codex)
    finally:
        if locks.exists() and not any(locks.iterdir()):
            locks.rmdir()


def _sol_execute_wave(resolution: Mapping[str, Any], *, output_root: Path, queue_root: Path, acknowledgement: str, broker_factory: Callable[[Path], Any] | None, call_codex: Callable[..., Any] | None) -> list[dict[str, Any]]:
    lifecycle, runtime, rows = _sol_runtime(resolution)
    lifecycle._disjoint(Path(output_root), REPO, Path(queue_root), *_source_roots(resolution))
    lifecycle._prepared_inventory(runtime, Path(output_root), rows)
    locks = lifecycle._locks(Path(output_root))
    index = {row["cell_id"]: row for row in rows}
    pilot = next(row for row in rows if row["condition"] in {FORWARD, REVERSE})
    direct = [row for row in rows if row["condition"] == DIRECT]
    remaining = [row for row in rows if row["condition"] in {FORWARD, REVERSE} and row["cell_id"] != pilot["cell_id"]]

    def run(row: Mapping[str, Any]) -> dict[str, Any]:
        return lifecycle._execute_prepared(base=runtime, row=index[row["cell_id"]], output_root=Path(output_root), queue_root=Path(queue_root), authorization_acknowledgement_sha256=acknowledgement, allow_remote=True, locks=locks, broker_factory=broker_factory, call_codex=call_codex)

    try:
        with ThreadPoolExecutor(max_workers=MAX_CONCURRENCY) as pool:
            initial = list(pool.map(run, [pilot, *direct]))
        _sol_admit(resolution, lifecycle=lifecycle, runtime=runtime, row=pilot, output_root=Path(output_root), acknowledgement=acknowledgement)
        with ThreadPoolExecutor(max_workers=MAX_CONCURRENCY) as pool:
            return [*initial, *pool.map(run, remaining)]
    finally:
        if locks.exists() and not any(locks.iterdir()):
            locks.rmdir()


def _sol_admit(resolution: Mapping[str, Any], *, lifecycle: ModuleType, runtime: ModuleType, row: Mapping[str, Any], output_root: Path, acknowledgement: str) -> dict[str, Any]:
    v4 = lifecycle.sol_v4()
    admitted = lifecycle._admit_completed_cell(runtime, v4, row, Path(output_root) / str(row["cell_id"]), acknowledgement)
    answer = resolution["core"].validate_answer(str(row["condition"]), admitted["answer"], expected_item_ids=row.get("item_ids"))
    return {**admitted, "answer": answer}


def _v15_grok_reuse(resolution: Mapping[str, Any], *, v15_root: Path, acknowledgement: str) -> dict[str, dict[str, Any]]:
    v15 = _load_pinned(V15, V15_SHA256, V15_COMMIT, "_v16_v15_grok_replay")
    paths = resolution["source_paths"]
    complete = v15.report(output_root=Path(v15_root), authorization_acknowledgement_sha256=acknowledgement, **paths)
    if complete.get("status") != "complete_matched_96_cells" or complete.get("endpoint") != "grok_primary":
        raise ValueError("V15 Grok reuse root is not a complete admitted endpoint report")
    value = v15.schedule(**paths)
    expected = {str(row["source_cell_id"]): row for row in resolution["reused"]}
    measurements: dict[str, dict[str, Any]] = {}
    with v15.bound(schedule_value=value) as (lifecycle, _runtime, v9, _v11, v13):
        helper = v13.load(v13.RECONCILE, v13.RECONCILE_COMMIT, v13.RECONCILE_SHA256, "_v16_v15_reuse_helper").helper()
        source = lifecycle.live()
        for source_row in value["cells"]:
            reused = expected.get(str(source_row["cell_id"]))
            if reused is None:
                continue
            if source_row.get("condition") != DIRECT or source_row.get("payload_sha256") != reused.get("payload_sha256"):
                raise ValueError("V15 reused direct payload binding drifted")
            root = Path(v15_root) / str(source_row["cell_id"])
            stored = v9.strict(v9.stable(root / "prepared.json"), "V15 prepared")
            route, evidence = stored.get("route"), stored.get("route_evidence")
            if not isinstance(route, Mapping) or not isinstance(evidence, Mapping):
                raise TypeError("V15 reused route evidence is invalid")
            raw, prompt, schema = lifecycle.payload(source_row)
            _request, response, _identity, _settings = lifecycle.admit(root, source_row, value, raw, prompt, schema, route, evidence, acknowledgement, source)
            envelope = helper.strict(response, "V15 native response", canonical_required=False)
            answer = resolution["core"].validate_answer(DIRECT, envelope.get("structuredOutput"))
            measurements[str(reused["cell_id"])] = {"condition": DIRECT, "answer": answer, "provenance": {"receipt_sha256": sha256(v9.stable(root / "execution-receipt.json")), "raw_response_sha256": sha256(response), "endpoint": "grok_primary"}}
    if set(measurements) != {str(row["cell_id"]) for row in resolution["reused"]}:
        raise ValueError("V15 Grok reuse replay is incomplete")
    return measurements


def _v15_sol_reuse(resolution: Mapping[str, Any], *, v15_root: Path, acknowledgement: str) -> dict[str, dict[str, Any]]:
    composition = _load_pinned(V15_SOL, V15_SOL_SHA256, V15_SOL_COMMIT, "_v16_v15_sol_replay")
    paths = resolution["source_paths"]
    complete = composition.report(output_root=Path(v15_root), authorization_acknowledgement_sha256=acknowledgement, **paths)
    if complete.get("status") != "complete_matched_96_cells" or complete.get("endpoint") != "sol_later":
        raise ValueError("V15 Sol reuse root is not a complete admitted endpoint report")
    v15_resolution = composition._resolution(**paths)
    lifecycle, runtime = composition._runtime(v15_resolution)
    index = {str(row["source_cell_id"]): row for row in v15_resolution["rows"]}
    expected = {str(row["source_cell_id"]): row for row in resolution["reused"]}
    v4 = lifecycle.sol_v4()
    measurements: dict[str, dict[str, Any]] = {}
    for source_cell_id, reused in expected.items():
        source_row = index.get(source_cell_id)
        if source_row is None or source_row.get("condition") != DIRECT or source_row.get("payload_sha256") != reused.get("payload_sha256"):
            raise ValueError("V15 Sol reused direct payload binding drifted")
        root = Path(v15_root) / str(source_row["cell_id"])
        admitted = lifecycle._admit_completed_cell(runtime, v4, source_row, root, acknowledgement)
        try:
            raw_answer = json.loads(admitted["final"].decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError("V15 Sol final response is not JSON") from error
        answer = resolution["core"].validate_answer(DIRECT, raw_answer)
        measurements[str(reused["cell_id"])] = {"condition": DIRECT, "answer": answer, "provenance": {"receipt_sha256": sha256(admitted["receipt"]), "raw_response_sha256": sha256(admitted["final"]), "endpoint": "sol_later"}}
    if set(measurements) != {str(row["cell_id"]) for row in resolution["reused"]}:
        raise ValueError("V15 Sol reuse replay is incomplete")
    return measurements


def _grok_fresh_measurements(resolution: Mapping[str, Any], *, output_root: Path, acknowledgement: str) -> dict[str, dict[str, Any]]:
    measurements: dict[str, dict[str, Any]] = {}
    with _grok_bound(resolution) as (lifecycle, _runtime, v9, _v11, v13, v15):
        helper = v13.load(v13.RECONCILE, v13.RECONCILE_COMMIT, v13.RECONCILE_SHA256, "_v16_grok_report_helper").helper()
        expected = {str(row["cell_id"]) for row in resolution["new"]}
        v9._validate_claims(Path(output_root), expected)
        route = evidence = None
        identities: set[tuple[str, str]] = set()
        for row in resolution["new"]:
            admitted = _grok_admit(resolution, lifecycle=lifecycle, v9=v9, v15=v15, helper=helper, output_root=Path(output_root), acknowledgement=acknowledgement, row=row)
            identity = admitted["identity"]
            key = (str(identity.get("request_id")), str(identity.get("session_id")))
            if not all(key) or key in identities:
                raise ValueError("duplicate or missing V16 Grok identity")
            identities.add(key)
            if route is None:
                route, evidence = admitted["route"], admitted["route_evidence"]
            elif route != admitted["route"] or evidence != admitted["route_evidence"]:
                raise ValueError("mixed V16 Grok route or evidence")
            root = Path(output_root) / str(row["cell_id"])
            measurements[str(row["cell_id"])] = {"condition": row["condition"], "answer": admitted["answer"], "provenance": {"receipt_sha256": sha256(v9.stable(root / "execution-receipt.json")), "raw_response_sha256": sha256(admitted["response"]), "endpoint": "grok_primary"}}
        if len(measurements) != 39 or len(identities) != 39 or route is None or evidence is None:
            raise ValueError("V16 Grok fresh receipt geometry is incomplete")
        lifecycle.validate_frozen_route(route, evidence)
        v9.parent_stack()._validate_route_evidence(route, evidence)
    return measurements


def _sol_fresh_measurements(resolution: Mapping[str, Any], *, output_root: Path, acknowledgement: str) -> dict[str, dict[str, Any]]:
    lifecycle, runtime, rows = _sol_runtime(resolution)
    entries = lifecycle._output_inventory(Path(output_root), rows)
    v4 = lifecycle.sol_v4()
    route = evidence = None
    identities: set[tuple[str, str]] = set()
    measurements: dict[str, dict[str, Any]] = {}
    for row in rows:
        admitted = _sol_admit(resolution, lifecycle=lifecycle, runtime=runtime, row=row, output_root=Path(output_root), acknowledgement=acknowledgement)
        identity = admitted["identity"]
        key = (str(identity.get("thread_id")), str(identity.get("session_id")))
        if not all(key) or key in identities:
            raise ValueError("duplicate or missing V16 Sol identity")
        identities.add(key)
        if route is None:
            route, evidence = admitted["route"], admitted["route_evidence"]
        elif route != admitted["route"] or evidence != admitted["route_evidence"]:
            raise ValueError("mixed V16 Sol route or evidence")
        measurements[str(row["cell_id"])] = {"condition": row["condition"], "answer": admitted["answer"], "provenance": {"receipt_sha256": sha256(admitted["receipt"]), "raw_response_sha256": sha256(admitted["final"]), "endpoint": "sol_later"}}
    if set(entries) != {str(row["cell_id"]) for row in rows} or len(measurements) != 39 or len(identities) != 39 or route is None or evidence is None:
        raise ValueError("V16 Sol fresh receipt geometry is incomplete")
    v4._frozen_route(route, evidence, runtime._load_v3(), require_unexpired=False)
    return measurements


def _resolve_inputs(*, split_manifest: Path, hanna_csv: Path, successor_contract: Path, expected_core_sha256: str) -> dict[str, Any]:
    return _resolution(split_manifest=Path(split_manifest), hanna_csv=Path(hanna_csv), successor_contract=Path(successor_contract), expected_core_sha256=expected_core_sha256)


def prepare_all(
    *,
    endpoint: str,
    output_root: Path,
    expected_core_sha256: str,
    authorization_acknowledgement_sha256: str,
    split_manifest: Path,
    hanna_csv: Path,
    successor_contract: Path,
    queue_root: Path,
    grok_route_provider: Callable[[Path], tuple[dict[str, Any], dict[str, Any]]] | None = None,
    sol_broker_factory: Callable[[Path], Any] | None = None,
) -> dict[str, Any]:
    """Prepare exactly the 39 fresh calls for one endpoint; no remote contact."""
    if endpoint not in ENDPOINTS:
        raise ValueError("endpoint must be grok or sol")
    resolution = _resolve_inputs(split_manifest=split_manifest, hanna_csv=hanna_csv, successor_contract=successor_contract, expected_core_sha256=expected_core_sha256)
    if endpoint == "grok":
        return _grok_prepare(resolution, output_root=Path(output_root), queue_root=Path(queue_root), acknowledgement=authorization_acknowledgement_sha256, route_provider=grok_route_provider)
    return _sol_prepare(resolution, output_root=Path(output_root), queue_root=Path(queue_root), acknowledgement=authorization_acknowledgement_sha256, broker_factory=sol_broker_factory)


def execute_one(
    *,
    endpoint: str,
    output_root: Path,
    expected_core_sha256: str,
    authorization_acknowledgement_sha256: str,
    split_manifest: Path,
    hanna_csv: Path,
    successor_contract: Path,
    queue_root: Path,
    cell_id: str,
    allow_remote: bool,
    grok_route_provider: Callable[[Path], tuple[dict[str, Any], dict[str, Any]]] | None = None,
    sol_broker_factory: Callable[[Path], Any] | None = None,
    grok_runner: Callable[..., Mapping[str, Any]] | None = None,
    call_codex: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    if endpoint not in ENDPOINTS or allow_remote is not True:
        raise ValueError("execution requires endpoint and explicit allow_remote=True")
    resolution = _resolve_inputs(split_manifest=split_manifest, hanna_csv=hanna_csv, successor_contract=successor_contract, expected_core_sha256=expected_core_sha256)
    row = next((row for row in resolution["new"] if str(row["cell_id"]) == cell_id), None)
    if row is None:
        raise ValueError("unknown V16 executable cell")
    if endpoint == "grok":
        pilot = next(row for row in resolution["new"] if row["condition"] in {FORWARD, REVERSE})
        if row["condition"] in {FORWARD, REVERSE} and row["cell_id"] != pilot["cell_id"]:
            with _grok_bound(resolution) as (lifecycle, _runtime, v9, _v11, v13, v15):
                helper = v13.load(v13.RECONCILE, v13.RECONCILE_COMMIT, v13.RECONCILE_SHA256, "_v16_grok_one_pilot_helper").helper()
                _grok_admit(resolution, lifecycle=lifecycle, v9=v9, v15=v15, helper=helper, output_root=Path(output_root), acknowledgement=authorization_acknowledgement_sha256, row=pilot)
        # Direct calls are independent; a later comparative batch is gated above.
        return _grok_execute_one(resolution, output_root=Path(output_root), queue_root=Path(queue_root), acknowledgement=authorization_acknowledgement_sha256, cell_id=cell_id, route_provider=grok_route_provider, runner=grok_runner)
    pilot = next(item for item in _sol_rows(resolution) if item["condition"] in {FORWARD, REVERSE})
    if row["condition"] in {FORWARD, REVERSE} and row["cell_id"] != pilot["cell_id"]:
        lifecycle, runtime, _rows = _sol_runtime(resolution)
        _sol_admit(resolution, lifecycle=lifecycle, runtime=runtime, row=pilot, output_root=Path(output_root), acknowledgement=authorization_acknowledgement_sha256)
    return _sol_execute(resolution, output_root=Path(output_root), queue_root=Path(queue_root), acknowledgement=authorization_acknowledgement_sha256, cell_id=cell_id, broker_factory=sol_broker_factory, call_codex=call_codex)


def _grok_execute_one(resolution: Mapping[str, Any], *, output_root: Path, queue_root: Path, acknowledgement: str, cell_id: str, route_provider: Callable[[Path], tuple[dict[str, Any], dict[str, Any]]] | None, runner: Callable[..., Mapping[str, Any]] | None) -> dict[str, Any]:
    row = next(row for row in resolution["new"] if row["cell_id"] == cell_id)
    with _grok_bound(resolution) as (lifecycle, runtime, v9, v11, v13, v15):
        helper = v13.load(v13.RECONCILE, v13.RECONCILE_COMMIT, v13.RECONCILE_SHA256, "_v16_grok_one_helper").helper()
        parent = v9.parent_stack()
        execution = _execution_schedule(resolution)
        selected = parent._guard_runner(runner or lifecycle.live()._default_runner, lifecycle, execution)
        def parse(_helper: Any, raw: bytes, receipt_route: Mapping[str, Any]) -> Any:
            return _grok_answer(resolution["core"], v15, helper, raw, receipt_route, row)
        return v11._execute_bound(value=execution, lifecycle=lifecycle, runtime=runtime, v9=v9, reconciler=SimpleNamespace(_response=parse), response_helper=helper, selected=selected, output_root=Path(output_root), queue_root=Path(queue_root), authorization_acknowledgement_sha256=acknowledgement, cell_id=cell_id, route_provider=v9._validated_route(parent, runtime, Path(queue_root), route_provider))


def execute_wave(
    *,
    endpoint: str,
    output_root: Path,
    expected_core_sha256: str,
    authorization_acknowledgement_sha256: str,
    split_manifest: Path,
    hanna_csv: Path,
    successor_contract: Path,
    queue_root: Path,
    allow_remote: bool,
    grok_route_provider: Callable[[Path], tuple[dict[str, Any], dict[str, Any]]] | None = None,
    sol_broker_factory: Callable[[Path], Any] | None = None,
    grok_runner: Callable[..., Mapping[str, Any]] | None = None,
    call_codex: Callable[..., Any] | None = None,
) -> list[dict[str, Any]]:
    if endpoint not in ENDPOINTS or allow_remote is not True:
        raise ValueError("execution requires endpoint and explicit allow_remote=True")
    resolution = _resolve_inputs(split_manifest=split_manifest, hanna_csv=hanna_csv, successor_contract=successor_contract, expected_core_sha256=expected_core_sha256)
    if endpoint == "grok":
        return _grok_execute_wave(resolution, output_root=Path(output_root), queue_root=Path(queue_root), acknowledgement=authorization_acknowledgement_sha256, route_provider=grok_route_provider, runner=grok_runner)
    return _sol_execute_wave(resolution, output_root=Path(output_root), queue_root=Path(queue_root), acknowledgement=authorization_acknowledgement_sha256, broker_factory=sol_broker_factory, call_codex=call_codex)


def report(
    *,
    endpoint: str,
    output_root: Path,
    expected_core_sha256: str,
    authorization_acknowledgement_sha256: str,
    split_manifest: Path,
    hanna_csv: Path,
    successor_contract: Path,
    v15_root: Path,
    v15_acknowledgement_sha256: str,
) -> dict[str, Any]:
    """Replay all 39 fresh and 21 historical receipts before core-only arithmetic."""
    if endpoint not in ENDPOINTS:
        raise ValueError("endpoint must be grok or sol")
    resolution = _resolve_inputs(split_manifest=split_manifest, hanna_csv=hanna_csv, successor_contract=successor_contract, expected_core_sha256=expected_core_sha256)
    if endpoint == "grok":
        fresh = _grok_fresh_measurements(resolution, output_root=Path(output_root), acknowledgement=authorization_acknowledgement_sha256)
        reused = _v15_grok_reuse(resolution, v15_root=Path(v15_root), acknowledgement=v15_acknowledgement_sha256)
        endpoint_label = "grok_primary"
    else:
        fresh = _sol_fresh_measurements(resolution, output_root=Path(output_root), acknowledgement=authorization_acknowledgement_sha256)
        reused = _v15_sol_reuse(resolution, v15_root=Path(v15_root), acknowledgement=v15_acknowledgement_sha256)
        endpoint_label = "sol_later"
    measurements = {**reused, **fresh}
    if len(measurements) != 60 or set(reused) & set(fresh):
        raise ValueError("V16 endpoint receipt measurement inventory drifted")
    analysis = resolution["core"].analyze(resolution["schedule"], measurements)
    return {"format_version": 1, "study_id": STUDY_ID, "kind": "receipt_replayed_v16_comparative_train_endpoint_report", "endpoint": endpoint_label, "native_endpoint_contact_cardinality": "unproven", "core_commit": CORE_COMMIT, "core_sha256": resolution["core_sha256"], "schedule_sha256": resolution["schedule_sha256"], "fresh_native_cell_count": 39, "historical_v15_direct_reuse_count": 21, "measurement_provenance": {"fresh_endpoint": endpoint_label, "v15_acknowledgement_sha256": v15_acknowledgement_sha256}, "analysis": analysis, "authority": resolution["schedule"]["authority"]}


if __name__ == "__main__":
    raise SystemExit("Use the callable endpoint API; execution needs an explicit reviewed invocation.")
