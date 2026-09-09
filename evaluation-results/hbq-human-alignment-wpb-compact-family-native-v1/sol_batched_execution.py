"""Bounded WPB Sol composition with one independently reviewed route epoch per batch."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import uuid
from collections.abc import Callable, Mapping
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import ModuleType
from typing import Any

HERE = Path(__file__).resolve().parent
REPOSITORY = HERE.parents[1]
FROZEN = HERE / "executor.py"
FROZEN_SHA256 = "b41ef08b9f93e0f6cb8646e96746240a058ce6d13392a80484caa61272421c10"
CURRENT_RUNTIME = REPOSITORY / "evaluation-results/hbq-human-alignment-optimizer-v4-native-subscription-exec-v3/executor.py"
CURRENT_RUNTIME_SHA256 = "cea177b5185a84b682bd5271ae7384cd7742add872d31b45227433d72c7f7e90"
CURRENT_RUNNER = REPOSITORY / "src/hbqrs/runner.py"
CURRENT_RUNNER_SHA256 = "3af6dd86088fddb91c2979ed6ddef00efb3da767e959972f8ee1ee0c1ab034f6"
PROCESS_CAPTURE = REPOSITORY / "src/hbqrs/sol_process_capture.py"
PROCESS_CAPTURE_SHA256 = "d93a24580b1b492ea116514ba768bb7f7dc5a8e386c925720b434ce94c4d9cb7"
FREEZE = HERE / "grok_selection_freeze.py"
MIXED_V5_SELECTION_CONTEXT = "mixed_v5_selection_context"
MAX_BATCH_SIZE = 10
ROUTE_MARGIN_SECONDS = 900
STUDY_ID = "hbq-human-alignment-wpb-compact-family-v1"


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def sha256(value: bytes | Any) -> str:
    return hashlib.sha256(value if isinstance(value, bytes) else canonical(value)).hexdigest()


def _require(value: bool, message: str) -> None:
    if not value:
        raise ValueError(message)


def _time(value: Any, label: str) -> datetime:
    _require(type(value) is str and value.endswith("Z"), f"{label} must be UTC Z")
    try:
        result = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as error:
        raise ValueError(f"{label} is invalid") from error
    return result.astimezone(timezone.utc)


def _instant(value: Any, label: str) -> datetime:
    _require(type(value) is str, f"{label} is invalid")
    try:
        result = datetime.fromisoformat(value[:-1] + "+00:00" if value.endswith("Z") else value)
    except ValueError as error:
        raise ValueError(f"{label} is invalid") from error
    _require(result.tzinfo is not None, f"{label} is invalid")
    return result.astimezone(timezone.utc)


def _read(path: Path, label: str) -> tuple[dict[str, Any], bytes]:
    try:
        raw = path.read_bytes()
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"invalid {label}") from error
    _require(isinstance(value, dict) and raw == canonical(value), f"noncanonical {label}")
    return value, raw


def _write_new(path: Path, value: Mapping[str, Any]) -> bytes:
    raw = canonical(dict(value))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle:
        handle.write(raw)
    return raw


def _load_exact(path: Path, expected: str, name: str) -> ModuleType:
    raw = path.read_bytes()
    _require(sha256(raw) == expected, f"{path.name} source drifted")
    spec = importlib.util.spec_from_file_location(f"{name}_{uuid.uuid4().hex}", path)
    _require(spec is not None and spec.loader is not None, f"cannot load {path.name}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module.__name__] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(module.__name__, None)
    _require(path.read_bytes() == raw, f"{path.name} changed during load")
    return module


def _frozen() -> ModuleType:
    return _load_exact(FROZEN, FROZEN_SHA256, "_wpb_frozen_sol")


def _verifier_path(path: Path | None) -> Path:
    return FREEZE.resolve() if path is None else Path(path).resolve()


def _freeze_module(path: Path, expected_sha256: str) -> ModuleType:
    return _load_exact(path, expected_sha256, "_wpb_grok_selection_freeze")


def _mixed_v5_context(value: Any) -> dict[str, Any]:
    _require(isinstance(value, Mapping), "mixed v5 selection context is malformed")
    required = {"legacy_measurement_count", "v4_native_measurement_count", "v5_native_measurement_count",
                "local_session_schema_recovered_measurement_count", "native_measurement_count", "measurement_count",
                "v4_cell_ids", "v5_cell_ids", "recovered_cell_id", "authority", "release_or_promotion_authority"}
    _require(set(value) == required and value["legacy_measurement_count"] == 89
             and value["v4_native_measurement_count"] == 12 and value["v5_native_measurement_count"] == 27
             and value["local_session_schema_recovered_measurement_count"] == 1
             and value["native_measurement_count"] == 128 and value["measurement_count"] == 129
             and value["recovered_cell_id"] == "wpb-pair-wpb-en-0843"
             and value["authority"] == "development_only_no_runtime_or_confirmation_authority"
             and value["release_or_promotion_authority"] == "none", "mixed v5 selection geometry differs")
    v4, v5 = value["v4_cell_ids"], value["v5_cell_ids"]
    _require(isinstance(v4, list) and isinstance(v5, list) and len(v4) == 12 and len(v5) == 27
             and all(isinstance(cell_id, str) for cell_id in v4 + v5)
             and len(set(v4)) == 12 and len(set(v5)) == 27 and not (set(v4) & set(v5))
             and value["recovered_cell_id"] not in set(v4) | set(v5), "mixed v5 cell inventory differs")
    return dict(value)


def _freeze_contract(context: Mapping[str, Any], *, verifier_path: Path, mixed_v5_freeze: bool) -> dict[str, Any]:
    if not mixed_v5_freeze:
        return {}
    return {"freeze_verifier_path": str(verifier_path), "freeze_context_kind": "mixed_v5",
            "mixed_v5_selection_context_sha256": sha256(context[MIXED_V5_SELECTION_CONTEXT])}


def _campaign_freeze_binding(context: Mapping[str, Any], *, mixed_v5_freeze: bool) -> dict[str, Any]:
    return {"freeze_source_bindings_sha256": sha256(context["source_bindings"])} if mixed_v5_freeze else {}


def _full_freeze(freeze_path: Path, expected_sha256: str, expected_verifier_sha256: str, *, verifier_path: Path,
                 mixed_v5_freeze: bool, replay_native: bool) -> dict[str, Any]:
    _require(type(mixed_v5_freeze) is bool, "mixed_v5_freeze must be boolean")
    module = _freeze_module(verifier_path, expected_verifier_sha256)
    method = "verify_freeze_context" if mixed_v5_freeze else "verify_freeze"
    verify = getattr(module, method, None)
    _require(callable(verify), "WPB Grok freeze verifier is unavailable")
    value = verify(Path(freeze_path), expected_sha256, replay_native=replay_native)
    _require(isinstance(value, Mapping), "WPB Grok freeze context is malformed")
    required = {"freeze_sha256", "selection_frozen_at", "selected_profile", "schedule_sha256", "source_bindings"}
    if mixed_v5_freeze:
        required.add(MIXED_V5_SELECTION_CONTEXT)
    else:
        required.update({"evidence_files", "native_measurement_count"})
    _require(set(value) == required and value["freeze_sha256"] == expected_sha256
             and isinstance(value["selected_profile"], Mapping) and isinstance(value["source_bindings"], Mapping),
             "WPB Grok selection freeze differs")
    if mixed_v5_freeze:
        _mixed_v5_context(value[MIXED_V5_SELECTION_CONTEXT])
    else:
        _require(value["native_measurement_count"] == 129 and isinstance(value["evidence_files"], Mapping),
                 "WPB Grok selection freeze differs")
    _time(value["selection_frozen_at"], "selection_frozen_at")
    return dict(value)


def _outside(path: Path, *sources: Path) -> Path:
    result = path.resolve()
    for source in sources:
        checked = source.resolve()
        _require(result != checked and result not in checked.parents and checked not in result.parents, "batch root must be external and disjoint")
    return result


def _resolution(frozen: ModuleType, freeze_root: Path) -> dict[str, Any]:
    resolution = frozen._resolution(freeze_root=freeze_root)
    _require(resolution.get("schedule_sha256") and len(resolution.get("rows", ())) == 129, "WPB frozen schedule differs")
    return resolution


def _campaign_path(root: Path) -> Path:
    return root / "campaign.json"


def _campaign(root: Path, resolution: Mapping[str, Any], freeze: Mapping[str, Any], expected_freeze_sha256: str,
              expected_freeze_verifier_sha256: str, freeze_contract: Mapping[str, Any]) -> tuple[dict[str, Any], str]:
    value, raw = _read(_campaign_path(root), "WPB Sol batch campaign")
    expected_cells = [{"cell_id": str(row["cell_id"]), "payload_sha256": row["payload_sha256"], "partition": row["partition"]} for row in resolution["rows"]]
    expected = {"format_version": 1, "kind": "wpb_sol_batched_campaign", "study_id": STUDY_ID,
                "frozen_executor_sha256": FROZEN_SHA256, "current_runtime_sha256": CURRENT_RUNTIME_SHA256,
                "process_capture_sha256": PROCESS_CAPTURE_SHA256,
                "current_runner_sha256": CURRENT_RUNNER_SHA256, "freeze_sha256": expected_freeze_sha256,
                "freeze_verifier_sha256": expected_freeze_verifier_sha256,
                "independent_freeze_review_sha256": value.get("independent_freeze_review_sha256"),
                "selection_frozen_at": freeze["selection_frozen_at"], "schedule_sha256": resolution["schedule_sha256"],
                "cells": expected_cells, "max_batch_size": MAX_BATCH_SIZE, "route_margin_seconds": ROUTE_MARGIN_SECONDS,
                **freeze_contract, **_campaign_freeze_binding(freeze, mixed_v5_freeze=bool(freeze_contract))}
    _require(value == expected, "WPB Sol campaign binding drifted")
    return value, sha256(raw)


def _freeze_review(path: Path, expected_sha256: str, freeze_sha256: str, freeze_verifier_sha256: str,
                   freeze_contract: Mapping[str, Any] | None = None) -> str:
    value, raw = _read(path, "WPB Grok selection independent review")
    expected = {"format_version": 1, "kind": "wpb_grok_selection_freeze_independent_review",
                "decision": "approved_wpb_grok_selection_freeze", "freeze_sha256": freeze_sha256,
                "freeze_verifier_sha256": freeze_verifier_sha256, "reviewed_at": value.get("reviewed_at"),
                **dict(freeze_contract or {})}
    _require(sha256(raw) == expected_sha256 and value == expected
             and _time(value.get("reviewed_at"), "freeze review timestamp") <= datetime.now(timezone.utc),
             "WPB Grok selection independent review differs")
    return sha256(raw)


def create_campaign(*, campaign_root: Path, queue_root: Path, freeze_root: Path, freeze_path: Path,
                    expected_freeze_sha256: str, expected_freeze_verifier_sha256: str,
                    independent_review_path: Path, expected_independent_review_sha256: str,
                    freeze_verifier_path: Path | None = None, mixed_v5_freeze: bool = False) -> dict[str, Any]:
    """Anchor the full native Grok replay before any Sol route is read."""
    root = _outside(Path(campaign_root), REPOSITORY, Path(queue_root), Path(freeze_root), Path(freeze_path))
    _require(not root.exists(), "fresh external WPB Sol campaign root required")
    frozen = _frozen(); resolution = _resolution(frozen, Path(freeze_root))
    verifier_path = _verifier_path(freeze_verifier_path)
    context = _full_freeze(Path(freeze_path), expected_freeze_sha256, expected_freeze_verifier_sha256,
                            verifier_path=verifier_path, mixed_v5_freeze=mixed_v5_freeze, replay_native=True)
    freeze_contract = _freeze_contract(context, verifier_path=verifier_path, mixed_v5_freeze=mixed_v5_freeze)
    freeze_review_contract = freeze_contract | _campaign_freeze_binding(context, mixed_v5_freeze=mixed_v5_freeze)
    _require(context["schedule_sha256"] == resolution["schedule_sha256"], "Grok freeze schedule differs")
    review_sha256 = _freeze_review(Path(independent_review_path), expected_independent_review_sha256,
                                   expected_freeze_sha256, expected_freeze_verifier_sha256, freeze_review_contract)
    root.mkdir(parents=True)
    cells = [{"cell_id": str(row["cell_id"]), "payload_sha256": row["payload_sha256"], "partition": row["partition"]} for row in resolution["rows"]]
    record = {"format_version": 1, "kind": "wpb_sol_batched_campaign", "study_id": STUDY_ID,
              "frozen_executor_sha256": FROZEN_SHA256, "current_runtime_sha256": CURRENT_RUNTIME_SHA256,
              "process_capture_sha256": PROCESS_CAPTURE_SHA256,
              "current_runner_sha256": CURRENT_RUNNER_SHA256, "freeze_sha256": expected_freeze_sha256,
              "freeze_verifier_sha256": expected_freeze_verifier_sha256,
              "independent_freeze_review_sha256": review_sha256,
              "selection_frozen_at": context["selection_frozen_at"], "schedule_sha256": resolution["schedule_sha256"],
              "cells": cells, "max_batch_size": MAX_BATCH_SIZE, "route_margin_seconds": ROUTE_MARGIN_SECONDS,
              **freeze_contract, **_campaign_freeze_binding(context, mixed_v5_freeze=mixed_v5_freeze)}
    raw = _write_new(_campaign_path(root), record)
    return {"campaign_sha256": sha256(raw), "prepared_batches": 0, "logical_cells": 129, "provider_calls_made": 0, "process_launches": 0}


def _batch_root(root: Path, number: int) -> Path:
    _require(type(number) is int and number > 0, "batch number is invalid")
    return root / "batches" / f"{number:04d}"


def _batch_numbers(root: Path) -> tuple[int, ...]:
    batches = root / "batches"
    if not batches.exists():
        return ()
    values = []
    for entry in batches.iterdir():
        _require(entry.is_dir() and entry.name.isdecimal() and len(entry.name) == 4, "batch directory is malformed")
        values.append(int(entry.name))
    values.sort()
    _require(values == list(range(1, len(values) + 1)), "batch sequence is discontinuous")
    return tuple(values)


def _review(path: Path, expected_sha256: str, *, campaign_sha256: str, batch_number: int,
            cell_ids: list[str], freeze_sha256: str, route_sha256: str,
            freeze_contract: Mapping[str, Any] | None = None) -> tuple[dict[str, Any], str]:
    value, raw = _read(path, "WPB Sol independent review")
    _require(sha256(raw) == expected_sha256, "WPB Sol independent review anchor drifted")
    contract = dict(freeze_contract or {})
    required = {"format_version", "kind", "decision", "campaign_sha256", "batch_number", "cell_ids", "freeze_sha256", "route_sha256", "reviewed_at", "expires_at"} | set(contract)
    _require(set(value) == required and value.get("format_version") == 1 and value.get("kind") == "approved_wpb_sol_batched_dispatch"
             and value.get("decision") == "approved_wpb_sol_batched_dispatch"
             and value.get("campaign_sha256") == campaign_sha256 and value.get("batch_number") == batch_number
             and value.get("cell_ids") == cell_ids and value.get("freeze_sha256") == freeze_sha256
             and value.get("route_sha256") == route_sha256 and _time(value.get("reviewed_at"), "reviewed_at") < _time(value.get("expires_at"), "expires_at"),
             "WPB Sol independent review differs")
    _require(all(value.get(key) == expected for key, expected in contract.items()), "WPB Sol independent review differs")
    _require(datetime.now(timezone.utc) < _time(value["expires_at"], "expires_at"), "WPB Sol independent review has expired")
    return value, sha256(raw)


def _route(lifecycle: ModuleType, runtime: ModuleType, queue_root: Path, broker_factory: Callable[[Path], Any] | None) -> tuple[dict[str, Any], dict[str, Any]]:
    route, evidence, _v3 = runtime._route(queue_root, broker_factory)
    v4 = runtime._load_v3()
    frozen_route, frozen_evidence = lifecycle.sol_v4()._frozen_route(route, evidence, v4, require_unexpired=True)
    expiry = _instant(frozen_evidence.get("cost_evidence_expires_at"), "route expiry")
    _require(expiry - datetime.now(timezone.utc) >= timedelta(seconds=ROUTE_MARGIN_SECONDS), "WPB Sol route lacks the 900-second dispatch margin")
    return dict(frozen_route), dict(frozen_evidence)


def _process_receipts(batch: Path, cell_ids: list[str]) -> dict[str, str]:
    receipts = batch / "sol-process-receipts"
    return {cell_id: sha256(path.read_bytes()) for cell_id in cell_ids
            if (path := receipts / f"{cell_id}.json").is_file()}


def _settlement(root: Path, number: int, campaign_sha256: str) -> tuple[dict[str, Any], str]:
    path = _batch_root(root, number) / "settlement.json"
    value, raw = _read(path, "WPB Sol batch settlement")
    _require(value.get("campaign_sha256") == campaign_sha256 and value.get("batch_number") == number, "WPB Sol settlement binding drifted")
    _require(value.get("process_completion_receipts") == _process_receipts(
        _batch_root(root, number), [str(cell["cell_id"]) for cell in value["cells"]]),
        "WPB Sol process completion receipts drifted")
    return value, sha256(raw)


def _completed_ids(root: Path, campaign_sha256: str) -> set[str]:
    completed: set[str] = set()
    for number in _batch_numbers(root):
        settlement, _digest = _settlement(root, number, campaign_sha256)
        _require(settlement.get("status") == "completed", "only settled complete batches may renew")
        for cell in settlement.get("cells", []):
            _require(isinstance(cell, Mapping) and cell.get("state") == "completed", "terminal or ambiguous batch cannot renew")
            cell_id = cell.get("cell_id")
            _require(isinstance(cell_id, str) and cell_id not in completed, "duplicate batch cell")
            completed.add(cell_id)
    return completed


def _plan_freeze_contract(plan: Mapping[str, Any]) -> dict[str, Any]:
    keys = {"freeze_verifier_path", "freeze_context_kind", "mixed_v5_selection_context_sha256"}
    present = keys & set(plan)
    if not present:
        return {}
    _require(present == keys and plan.get("freeze_context_kind") == "mixed_v5"
             and isinstance(plan.get("freeze_verifier_path"), str)
             and isinstance(plan.get("mixed_v5_selection_context_sha256"), str)
             and len(plan["mixed_v5_selection_context_sha256"]) == 64,
             "WPB Sol mixed freeze plan differs")
    _require(isinstance(plan.get("freeze_source_bindings_sha256"), str)
             and len(plan["freeze_source_bindings_sha256"]) == 64, "WPB Sol mixed freeze source binding differs")
    return {key: plan[key] for key in keys | {"freeze_source_bindings_sha256"}}


def _plan_review_contract(plan: Mapping[str, Any]) -> dict[str, Any]:
    contract = _plan_freeze_contract(plan)
    if not contract:
        return {}
    return {"freeze_verifier_sha256": plan["freeze_verifier_sha256"], **contract}


def _prepared_bindings(batch_root: Path, rows: tuple[Mapping[str, Any], ...], *, campaign_sha256: str,
                       freeze_sha256: str, freeze_verifier_sha256: str, route: Mapping[str, Any],
                       evidence: Mapping[str, Any], freeze_contract: Mapping[str, Any] | None = None) -> str:
    files = {str(row["cell_id"]): sha256((batch_root / "execution" / str(row["cell_id"]) / "prepared.json").read_bytes()) for row in rows}
    value = {"format_version": 1, "kind": "wpb_sol_batched_prepared_source_bindings", "campaign_sha256": campaign_sha256,
             "freeze_sha256": freeze_sha256, "freeze_verifier_sha256": freeze_verifier_sha256,
             "frozen_executor_sha256": FROZEN_SHA256,
             "current_runtime_sha256": CURRENT_RUNTIME_SHA256, "current_runner_sha256": CURRENT_RUNNER_SHA256,
             "process_capture_sha256": PROCESS_CAPTURE_SHA256,
             "route_sha256": sha256(route), "route_evidence_sha256": sha256(evidence), "prepared_sha256s": files,
             **dict(freeze_contract or {})}
    return sha256(_write_new(batch_root / "prepared-source-bindings.json", value))


def _verify_prepared_bindings(batch_root: Path, rows: tuple[Mapping[str, Any], ...], plan: Mapping[str, Any]) -> None:
    value, raw = _read(batch_root / "prepared-source-bindings.json", "WPB Sol prepared source bindings")
    expected = {"format_version": 1, "kind": "wpb_sol_batched_prepared_source_bindings", "campaign_sha256": plan["campaign_sha256"],
                "freeze_sha256": plan["freeze_sha256"], "freeze_verifier_sha256": plan["freeze_verifier_sha256"],
                "frozen_executor_sha256": FROZEN_SHA256,
                "current_runtime_sha256": CURRENT_RUNTIME_SHA256, "current_runner_sha256": CURRENT_RUNNER_SHA256,
                "process_capture_sha256": PROCESS_CAPTURE_SHA256,
                "route_sha256": plan["route_sha256"], "route_evidence_sha256": plan["route_evidence_sha256"],
                "prepared_sha256s": {str(row["cell_id"]): sha256((batch_root / "execution" / str(row["cell_id"]) / "prepared.json").read_bytes()) for row in rows},
                **_plan_freeze_contract(plan)}
    _require(value == expected and sha256(raw) == plan["prepared_source_bindings_sha256"], "WPB Sol prepared source bindings drifted")


def _review_companion(batch_root: Path, plan: Mapping[str, Any], *, require_unexpired: bool) -> None:
    value, raw = _read(batch_root / "independent-review.json", "persisted WPB Sol independent review")
    expected = {"format_version", "kind", "decision", "campaign_sha256", "batch_number", "cell_ids",
                "freeze_sha256", "route_sha256", "reviewed_at", "expires_at"} | set(_plan_review_contract(plan))
    _require(set(value) == expected and sha256(raw) == plan["review_sha256"]
             and value["campaign_sha256"] == plan["campaign_sha256"] and value["batch_number"] == plan["batch_number"]
             and value["cell_ids"] == plan["cell_ids"] and value["freeze_sha256"] == plan["freeze_sha256"]
             and value["route_sha256"] == plan["route_sha256"] and value["format_version"] == 1
             and value["kind"] == "approved_wpb_sol_batched_dispatch"
             and value["decision"] == "approved_wpb_sol_batched_dispatch"
             and all(value.get(key) == expected for key, expected in _plan_review_contract(plan).items())
             and _time(value["reviewed_at"], "reviewed_at") < _time(value["expires_at"], "expires_at"),
             "persisted WPB Sol independent review differs")
    if require_unexpired:
        _require(datetime.now(timezone.utc) < _time(value["expires_at"], "expires_at"),
                 "persisted WPB Sol independent review has expired")


def prepare_next_batch(*, campaign_root: Path, queue_root: Path, freeze_root: Path, freeze_path: Path,
                       expected_freeze_sha256: str, expected_freeze_verifier_sha256: str,
                       review_path: Path, expected_review_sha256: str,
                       authorization_acknowledgement_sha256: str, broker_factory: Callable[[Path], Any] | None = None,
                       freeze_verifier_path: Path | None = None, mixed_v5_freeze: bool = False) -> dict[str, Any]:
    """Prepare one fresh, reviewed route epoch; it has no dispatch capability by itself."""
    root = Path(campaign_root).resolve(); frozen = _frozen(); resolution = _resolution(frozen, Path(freeze_root))
    verifier_path = _verifier_path(freeze_verifier_path)
    context = _full_freeze(Path(freeze_path), expected_freeze_sha256, expected_freeze_verifier_sha256,
                            verifier_path=verifier_path, mixed_v5_freeze=mixed_v5_freeze, replay_native=False)
    freeze_contract = _freeze_contract(context, verifier_path=verifier_path, mixed_v5_freeze=mixed_v5_freeze)
    review_contract = {"freeze_verifier_sha256": expected_freeze_verifier_sha256,
                       **freeze_contract, **_campaign_freeze_binding(context, mixed_v5_freeze=mixed_v5_freeze)} if mixed_v5_freeze else {}
    _require(context["schedule_sha256"] == resolution["schedule_sha256"], "Grok freeze schedule differs")
    _campaign_value, campaign_sha256 = _campaign(root, resolution, context, expected_freeze_sha256,
                                                  expected_freeze_verifier_sha256, freeze_contract)
    _require(not (root / "stopped.json").exists(), "WPB Sol campaign is stopped")
    completed = _completed_ids(root, campaign_sha256)
    all_rows = tuple(resolution["rows"])
    expected_ids = [str(row["cell_id"]) for row in all_rows]
    _require(completed <= set(expected_ids), "settlement has unknown cell")
    pending = tuple(row for row in all_rows if str(row["cell_id"]) not in completed)
    _require(pending, "WPB Sol campaign is already complete")
    number = len(_batch_numbers(root)) + 1; batch = _batch_root(root, number)
    _require(not batch.exists(), "fresh WPB Sol batch root required")
    lifecycle, runtime, _rows = frozen._sol_runtime(resolution)
    route, evidence = _route(lifecycle, runtime, Path(queue_root), broker_factory)
    selected = pending[:MAX_BATCH_SIZE]; cell_ids = [str(row["cell_id"]) for row in selected]
    _review_value, review_sha256 = _review(Path(review_path), expected_review_sha256, campaign_sha256=campaign_sha256,
                                    batch_number=number, cell_ids=cell_ids, freeze_sha256=expected_freeze_sha256,
                                    route_sha256=sha256(route), freeze_contract=review_contract)
    _require(_time(context["selection_frozen_at"], "selection_frozen_at") <= datetime.now(timezone.utc), "Sol cannot predate Grok selection freeze")
    batch.parent.mkdir(exist_ok=True)
    lifecycle._disjoint(batch, REPOSITORY, Path(queue_root), Path(freeze_root))
    execution = batch / "execution"; execution.mkdir(parents=True)
    for row in selected:
        cell = execution / str(row["cell_id"]); cell.mkdir()
        payload = resolution["payloads"][str(row["cell_id"])]
        schema = runtime.canonical(json.loads(payload.decode("utf-8"))["response_schema"])
        for name, raw in runtime._prepared(row, payload, schema, row["target"], route, evidence, authorization_acknowledgement_sha256).items():
            runtime._write_new(cell / name, raw)
    lifecycle._prepared_inventory(runtime, execution, selected)
    binding_sha256 = _prepared_bindings(batch, selected, campaign_sha256=campaign_sha256,
                                         freeze_sha256=expected_freeze_sha256,
                                         freeze_verifier_sha256=expected_freeze_verifier_sha256,
                                         route=route, evidence=evidence, freeze_contract=review_contract)
    plan = {"format_version": 1, "kind": "wpb_sol_batched_plan", "study_id": STUDY_ID, "campaign_sha256": campaign_sha256,
            "batch_number": number, "cell_ids": cell_ids, "freeze_sha256": expected_freeze_sha256,
             "freeze_verifier_sha256": expected_freeze_verifier_sha256,
             "selection_frozen_at": context["selection_frozen_at"], "schedule_sha256": resolution["schedule_sha256"],
             "freeze_source_bindings_sha256": sha256(context["source_bindings"]),
             **({} if mixed_v5_freeze else {"freeze_evidence_files_sha256": sha256(context["evidence_files"])}),
             "route": route, "route_evidence": evidence, "route_sha256": sha256(route), "route_evidence_sha256": sha256(evidence),
             "review_sha256": review_sha256, "prepared_source_bindings_sha256": binding_sha256,
             "authorization_acknowledgement_sha256": authorization_acknowledgement_sha256,
             **freeze_contract}
    raw = _write_new(batch / "plan.json", plan)
    _write_new(batch / "independent-review.json", _review_value)
    return {"batch_number": number, "plan_sha256": sha256(raw), "prepared_cells": cell_ids,
            "provider_calls_made": 0, "process_launches": 0, "native_contact_count": 0}


def _plan(root: Path, number: int, campaign_sha256: str, *, verifier_path: Path,
          mixed_v5_freeze: bool) -> tuple[dict[str, Any], str]:
    value, raw = _read(_batch_root(root, number) / "plan.json", "WPB Sol batch plan")
    required = {"format_version", "kind", "study_id", "campaign_sha256", "batch_number", "cell_ids", "freeze_sha256", "freeze_verifier_sha256",
                "selection_frozen_at", "schedule_sha256", "freeze_source_bindings_sha256",
                "route", "route_evidence", "route_sha256", "route_evidence_sha256", "review_sha256",
                "prepared_source_bindings_sha256", "authorization_acknowledgement_sha256"}
    if mixed_v5_freeze:
        required.update({"freeze_verifier_path", "freeze_context_kind", "mixed_v5_selection_context_sha256"})
    else:
        required.add("freeze_evidence_files_sha256")
    _require(set(value) == required and value.get("format_version") == 1 and value.get("kind") == "wpb_sol_batched_plan"
             and value.get("study_id") == STUDY_ID and value.get("campaign_sha256") == campaign_sha256
              and value.get("batch_number") == number and isinstance(value.get("cell_ids"), list)
              and 1 <= len(value["cell_ids"]) <= MAX_BATCH_SIZE and len(set(value["cell_ids"])) == len(value["cell_ids"])
              and (not mixed_v5_freeze or value.get("freeze_verifier_path") == str(verifier_path))
              and value.get("route_sha256") == sha256(value.get("route")) and value.get("route_evidence_sha256") == sha256(value.get("route_evidence")),
              "WPB Sol batch plan differs")
    return value, sha256(raw)


def _cheap_freeze(plan: Mapping[str, Any], freeze_path: Path, expected_freeze_sha256: str,
                  expected_freeze_verifier_sha256: str, *, verifier_path: Path,
                  mixed_v5_freeze: bool) -> dict[str, Any]:
    context = _full_freeze(freeze_path, expected_freeze_sha256, expected_freeze_verifier_sha256,
                            verifier_path=verifier_path, mixed_v5_freeze=mixed_v5_freeze, replay_native=False)
    freeze_contract = _freeze_contract(context, verifier_path=verifier_path, mixed_v5_freeze=mixed_v5_freeze)
    _require(plan.get("freeze_sha256") == context["freeze_sha256"] and plan.get("selection_frozen_at") == context["selection_frozen_at"]
              and plan.get("freeze_verifier_sha256") == expected_freeze_verifier_sha256
              and plan.get("schedule_sha256") == context["schedule_sha256"]
              and plan.get("freeze_source_bindings_sha256") == sha256(context["source_bindings"])
              and all(plan.get(key) == expected for key, expected in freeze_contract.items()), "WPB Sol frozen Grok binding drifted")
    if not mixed_v5_freeze:
        _require(plan.get("freeze_evidence_files_sha256") == sha256(context["evidence_files"]),
                 "WPB Sol frozen Grok binding drifted")
    _require(_time(context["selection_frozen_at"], "selection_frozen_at") <= datetime.now(timezone.utc), "Sol contact predates Grok selection freeze")
    _require(sha256(FROZEN.read_bytes()) == FROZEN_SHA256 and sha256(CURRENT_RUNNER.read_bytes()) == CURRENT_RUNNER_SHA256
             and sha256(CURRENT_RUNTIME.read_bytes()) == CURRENT_RUNTIME_SHA256 and sha256(PROCESS_CAPTURE.read_bytes()) == PROCESS_CAPTURE_SHA256, "WPB Sol source binding drifted")
    return context


def _current_call_codex(runtime: ModuleType, *, receipt_root: Path) -> Callable[..., tuple[str, dict[str, Any]]]:
    """Patch the exact V3 command builder shared by WPB launch and validation."""
    _require(sha256(CURRENT_RUNTIME.read_bytes()) == CURRENT_RUNTIME_SHA256
             and sha256(CURRENT_RUNNER.read_bytes()) == CURRENT_RUNNER_SHA256
             and sha256(PROCESS_CAPTURE.read_bytes()) == PROCESS_CAPTURE_SHA256, "current WPB Sol runtime drifted")
    original_loader = runtime._load_v3

    def configured_v3() -> ModuleType:
        v3 = original_loader()
        if getattr(v3, "_wpb_code_mode_disabled", False):
            return v3
        _require(Path(v3.__file__).resolve() == CURRENT_RUNTIME.resolve(), "WPB Sol current V3 runtime differs")
        v3.RUNNER_SHA256 = CURRENT_RUNNER_SHA256
        original_command = v3._expected_codex_command

        def command(executable: str, output_root: Path) -> list[str]:
            value = original_command(executable, output_root)
            message = output_root / "responses" / "batch-0001.attempt-0001.message.json"
            _require(value[value.index("--output-last-message") + 1] == str(message), "WPB V3 message path drifted")
            _require(value[-1] == "<prompt-via-stdin>" and value.count("code_mode") == 1
                     and value[value.index("code_mode") - 1] == "--disable", "WPB V3 code-mode control drifted")
            return value

        v3._expected_codex_command = command
        v3.subprocess = _load_exact(PROCESS_CAPTURE, PROCESS_CAPTURE_SHA256, "sol_process_capture").facade(
            v3.subprocess, receipt_root=receipt_root)
        v3._wpb_code_mode_disabled = True
        return v3

    runtime._load_v3 = configured_v3
    return configured_v3()._load_call_codex()


def _batch_rows(resolution: Mapping[str, Any], plan: Mapping[str, Any]) -> tuple[dict[str, Any], ...]:
    by_id = {str(row["cell_id"]): row for row in resolution["rows"]}
    result = tuple(by_id.get(str(cell_id)) for cell_id in plan["cell_ids"])
    _require(all(row is not None for row in result), "batch cell is absent from frozen schedule")
    return tuple(row for row in result if row is not None)


def dispatch_batch(*, campaign_root: Path, queue_root: Path, freeze_root: Path, freeze_path: Path,
                    expected_freeze_sha256: str, expected_freeze_verifier_sha256: str, batch_number: int, allow_remote: bool,
                    broker_factory: Callable[[Path], Any] | None = None,
                    call_codex: Callable[..., tuple[str, dict[str, Any]]] | None = None,
                    freeze_verifier_path: Path | None = None, mixed_v5_freeze: bool = False) -> list[dict[str, Any]]:
    """Run exactly one prepared route epoch through the frozen per-cell lifecycle."""
    _require(allow_remote is True, "WPB Sol dispatch requires explicit allow_remote=True")
    root = Path(campaign_root).resolve(); frozen = _frozen(); resolution = _resolution(frozen, Path(freeze_root))
    verifier_path = _verifier_path(freeze_verifier_path)
    context = _full_freeze(Path(freeze_path), expected_freeze_sha256, expected_freeze_verifier_sha256,
                            verifier_path=verifier_path, mixed_v5_freeze=mixed_v5_freeze, replay_native=False)
    freeze_contract = _freeze_contract(context, verifier_path=verifier_path, mixed_v5_freeze=mixed_v5_freeze)
    _campaign_value, campaign_sha256 = _campaign(root, resolution, context, expected_freeze_sha256,
                                                  expected_freeze_verifier_sha256, freeze_contract)
    _require(not (root / "stopped.json").exists(), "WPB Sol campaign is stopped")
    plan, _plan_sha256 = _plan(root, batch_number, campaign_sha256, verifier_path=verifier_path,
                               mixed_v5_freeze=mixed_v5_freeze)
    _cheap_freeze(plan, Path(freeze_path), expected_freeze_sha256, expected_freeze_verifier_sha256,
                  verifier_path=verifier_path, mixed_v5_freeze=mixed_v5_freeze)
    rows = _batch_rows(resolution, plan); batch = _batch_root(root, batch_number); execution = batch / "execution"
    lifecycle, runtime, _ignored = frozen._sol_runtime(resolution)
    lifecycle._disjoint(batch, REPOSITORY, Path(queue_root), Path(freeze_root))
    _verify_prepared_bindings(batch, rows, plan)
    _review_companion(batch, plan, require_unexpired=True)
    lifecycle._prepared_inventory(runtime, execution, rows)
    if (batch / "settlement.json").exists():
        raise ValueError("settled WPB Sol batch cannot dispatch again")
    locks = lifecycle._locks(execution)
    original = call_codex or _current_call_codex(runtime, receipt_root=batch / "sol-process-receipts")

    def invoke(**kwargs: Any) -> tuple[str, dict[str, Any]]:
        before = kwargs.get("before_provider_attempt")
        _require(callable(before), "frozen Sol runtime omitted precontact gate")
        def guarded() -> None:
            _cheap_freeze(plan, Path(freeze_path), expected_freeze_sha256, expected_freeze_verifier_sha256,
                          verifier_path=verifier_path, mixed_v5_freeze=mixed_v5_freeze)
            _review_companion(batch, plan, require_unexpired=True)
            route, evidence = _route(lifecycle, runtime, Path(queue_root), broker_factory)
            _require(route == plan["route"] and evidence == plan["route_evidence"], "Sol route changed after independent review")
            before()
        return original(**(kwargs | {"before_provider_attempt": guarded}))

    def run(row: Mapping[str, Any]) -> dict[str, Any]:
        return lifecycle._execute_prepared(base=runtime, row=row, output_root=execution, queue_root=Path(queue_root),
                                           authorization_acknowledgement_sha256=plan["authorization_acknowledgement_sha256"],
                                           allow_remote=True, locks=locks, broker_factory=broker_factory, call_codex=invoke)
    try:
        return frozen._fail_fast_wave(rows=rows, output_root=execution, endpoint="Sol", run=run)
    finally:
        if locks.exists() and not any(locks.iterdir()):
            locks.rmdir()


def settle_batch(*, campaign_root: Path, freeze_root: Path, freeze_path: Path, expected_freeze_sha256: str,
                  expected_freeze_verifier_sha256: str, batch_number: int, freeze_verifier_path: Path | None = None,
                  mixed_v5_freeze: bool = False) -> dict[str, Any]:
    """Re-admit one route epoch before it can authorize any receipt-only renewal."""
    root = Path(campaign_root).resolve(); frozen = _frozen(); resolution = _resolution(frozen, Path(freeze_root))
    verifier_path = _verifier_path(freeze_verifier_path)
    context = _full_freeze(Path(freeze_path), expected_freeze_sha256, expected_freeze_verifier_sha256,
                            verifier_path=verifier_path, mixed_v5_freeze=mixed_v5_freeze, replay_native=False)
    freeze_contract = _freeze_contract(context, verifier_path=verifier_path, mixed_v5_freeze=mixed_v5_freeze)
    _campaign(root, resolution, context, expected_freeze_sha256, expected_freeze_verifier_sha256, freeze_contract)
    campaign_sha256 = sha256(_campaign_path(root).read_bytes()); plan, plan_sha256 = _plan(root, batch_number, campaign_sha256,
                                                                                              verifier_path=verifier_path, mixed_v5_freeze=mixed_v5_freeze)
    _cheap_freeze(plan, Path(freeze_path), expected_freeze_sha256, expected_freeze_verifier_sha256,
                  verifier_path=verifier_path, mixed_v5_freeze=mixed_v5_freeze)
    batch = _batch_root(root, batch_number); _require(not (batch / "settlement.json").exists(), "batch already settled")
    lifecycle, runtime, _ignored = frozen._sol_runtime(resolution); rows = _batch_rows(resolution, plan)
    _verify_prepared_bindings(batch, rows, plan)
    _review_companion(batch, plan, require_unexpired=False)
    entries = lifecycle._output_inventory(batch / "execution", rows); v4 = lifecycle.sol_v4()
    cells: list[dict[str, Any]] = []; identities: set[tuple[str, str]] = set(); complete = True
    for row in rows:
        cell_id = str(row["cell_id"])
        try:
            admitted = lifecycle._admit_completed_cell(runtime, v4, row, entries[cell_id], plan["authorization_acknowledgement_sha256"])
            _require(admitted["route"] == plan["route"] and admitted["route_evidence"] == plan["route_evidence"], "admitted route differs from batch review")
            identity = admitted["identity"]; key = (str(identity.get("thread_id")), str(identity.get("session_id"))) if isinstance(identity, Mapping) else ("", "")
            _require(all(key) and key not in identities, "duplicate or missing Sol native identity")
            identities.add(key)
            cells.append({"cell_id": cell_id, "state": "completed", "execution_receipt_sha256": sha256(admitted["receipt"]),
                          "raw_response_sha256": sha256(admitted["final"]), "identity_sha256": sha256(identity)})
        except (OSError, TypeError, ValueError) as error:
            complete = False; cells.append({"cell_id": cell_id, "state": "terminal_or_ambiguous", "error_type": type(error).__name__})
    settlement = {"format_version": 1, "kind": "wpb_sol_batched_settlement", "study_id": STUDY_ID,
                  "campaign_sha256": campaign_sha256, "batch_number": batch_number, "plan_sha256": plan_sha256,
                  "freeze_sha256": expected_freeze_sha256, "cells": cells,
                  "process_completion_receipts": _process_receipts(batch, [str(row["cell_id"]) for row in rows]),
                  "status": "completed" if complete else "terminal_or_ambiguous"}
    raw = _write_new(batch / "settlement.json", settlement)
    if not complete:
        _write_new(root / "stopped.json", {"format_version": 1, "kind": "wpb_sol_batched_campaign_stopped", "campaign_sha256": campaign_sha256,
                                              "batch_number": batch_number, "settlement_sha256": sha256(raw), "reason": "terminal_or_ambiguous_no_resend"})
    return {"batch_number": batch_number, "settlement_sha256": sha256(raw), "status": settlement["status"],
            "completed_cells": [cell["cell_id"] for cell in cells if cell["state"] == "completed"]}


def report(*, campaign_root: Path, freeze_root: Path, freeze_path: Path, expected_freeze_sha256: str,
            expected_freeze_verifier_sha256: str, freeze_verifier_path: Path | None = None,
            mixed_v5_freeze: bool = False) -> dict[str, Any]:
    """Replay every completed batch with the canonical frozen native parser and core analyzer."""
    root = Path(campaign_root).resolve(); frozen = _frozen(); resolution = _resolution(frozen, Path(freeze_root))
    verifier_path = _verifier_path(freeze_verifier_path)
    context = _full_freeze(Path(freeze_path), expected_freeze_sha256, expected_freeze_verifier_sha256,
                            verifier_path=verifier_path, mixed_v5_freeze=mixed_v5_freeze, replay_native=True)
    freeze_contract = _freeze_contract(context, verifier_path=verifier_path, mixed_v5_freeze=mixed_v5_freeze)
    _campaign_value, campaign_sha256 = _campaign(root, resolution, context, expected_freeze_sha256,
                                                  expected_freeze_verifier_sha256, freeze_contract)
    if (root / "stopped.json").exists():
        return {"status": "closed_terminal_or_ambiguous", "authority": "development_screening_only", "metrics": None}
    numbers = _batch_numbers(root)
    if len(numbers) != 13:
        return {"status": "closed_incomplete", "authority": "development_screening_only", "completed_batches": len(numbers), "metrics": None}
    lifecycle, runtime, _ignored = frozen._sol_runtime(resolution); v4 = lifecycle.sol_v4()
    measurements: list[dict[str, Any]] = []; bindings: dict[str, dict[str, Any]] = {}; identities: set[tuple[str, str]] = set()
    epochs: list[dict[str, Any]] = []
    for number in numbers:
        plan, plan_sha256 = _plan(root, number, campaign_sha256, verifier_path=verifier_path,
                                  mixed_v5_freeze=mixed_v5_freeze)
        _cheap_freeze(plan, Path(freeze_path), expected_freeze_sha256, expected_freeze_verifier_sha256,
                      verifier_path=verifier_path, mixed_v5_freeze=mixed_v5_freeze)
        settlement, settlement_sha256 = _settlement(root, number, campaign_sha256)
        _require(settlement.get("plan_sha256") == plan_sha256 and settlement.get("freeze_sha256") == expected_freeze_sha256
                 and settlement.get("status") == "completed" and len(settlement.get("cells", [])) == len(plan["cell_ids"]),
                 "WPB Sol batch settlement is incomplete")
        rows = _batch_rows(resolution, plan); batch = _batch_root(root, number)
        _verify_prepared_bindings(batch, rows, plan)
        _review_companion(batch, plan, require_unexpired=False)
        entries = lifecycle._output_inventory(batch / "execution", rows)
        epoch = {"batch_number": number, "route_sha256": plan["route_sha256"], "route_evidence_sha256": plan["route_evidence_sha256"],
                 "review_sha256": plan["review_sha256"], "settlement_sha256": settlement_sha256}
        epochs.append(epoch)
        settlement_cells = {str(cell.get("cell_id")): cell for cell in settlement["cells"] if isinstance(cell, Mapping)}
        for row in rows:
            cell_id = str(row["cell_id"]); settled = settlement_cells.get(cell_id)
            _require(isinstance(settled, Mapping) and settled.get("state") == "completed", "unsettled Sol cell cannot be reported")
            admitted = lifecycle._admit_completed_cell(runtime, v4, row, entries[cell_id], plan["authorization_acknowledgement_sha256"])
            _require(admitted["route"] == plan["route"] and admitted["route_evidence"] == plan["route_evidence"], "reported Sol route differs from batch epoch")
            answer = frozen._valid_response(resolution["core"], admitted["answer"])
            identity = admitted["identity"]; key = (str(identity.get("thread_id")), str(identity.get("session_id"))) if isinstance(identity, Mapping) else ("", "")
            _require(all(key) and key not in identities, "duplicate or missing Sol native identity across epochs")
            identities.add(key)
            _require(settled.get("execution_receipt_sha256") == sha256(admitted["receipt"])
                     and settled.get("raw_response_sha256") == sha256(admitted["final"])
                     and settled.get("identity_sha256") == sha256(identity), "Sol settlement receipt binding drifted")
            measurements.append({"endpoint": "sol", "cell_id": cell_id, "payload_sha256": row["payload_sha256"],
                                 "measurement_provenance": {"endpoint": "sol", "cell_id": cell_id,
                                                            "payload_sha256": row["payload_sha256"],
                                                            "parsed_response_sha256": frozen.sha256(answer)}, "response": answer})
            bindings[cell_id] = {"batch_number": number, "route_sha256": plan["route_sha256"],
                                 "route_evidence_sha256": plan["route_evidence_sha256"], "review_sha256": plan["review_sha256"],
                                 "execution_receipt_sha256": sha256(admitted["receipt"]), "identity_sha256": sha256(identity),
                                 "effective_settings_sha256": frozen.sha256(admitted["settings"]),
                                 "prepared_source_bindings_sha256": plan["prepared_source_bindings_sha256"]}
    expected_ids = {str(row["cell_id"]) for row in resolution["rows"]}
    _require(len(measurements) == 129 and {item["cell_id"] for item in measurements} == expected_ids and len(identities) == 129,
             "WPB Sol batched receipt inventory is incomplete")
    analysis = resolution["core"].analyze(Path(freeze_root), measurements, context["selected_profile"])
    return {"format_version": 1, "kind": "wpb_sol_batched_native_receipt_replayed_report", "study_id": STUDY_ID,
            "status": "complete_batched_sol_campaign", "authority": "development_screening_only", "confirmation": "closed",
            "native_endpoint_contact_cardinality": "unproven", "measurement_count": 129, "wpb_schedule_sha256": resolution["schedule_sha256"],
            "freeze_sha256": expected_freeze_sha256, "selection_frozen_at": context["selection_frozen_at"],
            "route_epochs": epochs, "native_receipt_bindings": bindings, "analysis": analysis}
