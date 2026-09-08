"""Governed native continuation after the non-native WPB 0843 projection.

``recovery.py`` remains the admission authority for native suffix results.  Its
frozen dispatcher predates the explicitly adopted 0843 local projection and
therefore requires an admission the projection must never receive.  This
versioned bridge only recognizes the separately verified marker, then delegates
ordinary-result admission back to the frozen helper.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import uuid
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import ModuleType
from typing import Any

HERE = Path(__file__).resolve().parent
RECOVERY_PATH = HERE / "recovery.py"
SCHEMA_PATH = HERE / "schema_recovery.py"
RECOVERY_SHA256 = "3bd13df9f27f71563e3a0bf444b22e5bdc3741ca5b3ef278a2254227a155f5ec"
SCHEMA_CELL = "wpb-pair-wpb-en-0843"
FIRST_NATIVE_CELL = "wpb-pair-wpb-en-0834"
_HEX = set("0123456789abcdef")


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _hash(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _hex(value: Any, label: str) -> str:
    _require(isinstance(value, str) and len(value) == 64 and set(value) <= _HEX, f"{label} must be a lowercase SHA-256")
    return value


def _load(path: Path, expected_sha256: str, name: str) -> ModuleType:
    raw = path.read_bytes()
    _require(_hash(raw) == _hex(expected_sha256, f"{name} source hash"), f"{name} source drifted")
    spec = importlib.util.spec_from_file_location(name, path)
    _require(spec is not None and spec.loader is not None, f"cannot load {name}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    _require(path.read_bytes() == raw, f"{name} changed during load")
    return module


def _timestamp(value: Any, label: str) -> datetime:
    _require(isinstance(value, str), f"{label} must be an ISO UTC timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"{label} is not an ISO UTC timestamp") from error
    _require(parsed.tzinfo is not None, f"{label} must include UTC offset")
    return parsed.astimezone(UTC)


def _json(path: Path, label: str) -> tuple[dict[str, Any], bytes]:
    raw = path.read_bytes()
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{label} is not UTF-8 JSON") from error
    _require(isinstance(value, dict), f"{label} must be an object")
    return value, raw


def _descriptor(path: Path, sha256: str, *, adapter_version: int | None = None) -> dict[str, Any]:
    value: dict[str, Any] = {"path": str(path.resolve()), "sha256": _hex(sha256, "source hash")}
    if adapter_version is not None:
        value["adapter_version"] = adapter_version
    return value


def _sources(*, broker_path: Path, runtime_source_path: Path, helper_source_path: Path,
             expected_schema_helper_sha256: str) -> dict[str, dict[str, Any]]:
    for path, label in ((broker_path, "broker"), (runtime_source_path, "runtime"), (helper_source_path, "helper"), (SCHEMA_PATH, "schema helper")):
        _require(path.is_file(), f"canonical {label} source is unavailable")
    return {
        "broker": _descriptor(broker_path, _hash(broker_path.read_bytes())),
        "runtime": _descriptor(runtime_source_path, _hash(runtime_source_path.read_bytes()), adapter_version=4),
        "helper": _descriptor(helper_source_path, _hash(helper_source_path.read_bytes())),
        "schema_helper": _descriptor(SCHEMA_PATH, expected_schema_helper_sha256),
        "execution_helper": _descriptor(HERE / "schema_recovery_execution.py", _hash((HERE / "schema_recovery_execution.py").read_bytes())),
    }


def _sources_still_pinned(sources: Mapping[str, Any]) -> None:
    for name, descriptor in sources.items():
        _require(isinstance(descriptor, Mapping), f"{name} source descriptor is malformed")
        path, expected = descriptor.get("path"), descriptor.get("sha256")
        _require(isinstance(path, str) and isinstance(expected, str) and _hash(Path(path).read_bytes()) == expected,
                 f"{name} source drifted")


def _plan(recovery: ModuleType, root: Path, expected_plan_sha256: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    plan = recovery._read_plan(root, _hex(expected_plan_sha256, "expected recovery plan hash"))
    recovery._verify_origin(plan)
    cells = plan.get("cells")
    _require(isinstance(cells, list) and len(cells) == 40, "recovery plan must retain exactly 40 cells")
    values = [dict(value) for value in cells if isinstance(value, Mapping)]
    _require(len(values) == 40 and values[0].get("cell_id") == FIRST_NATIVE_CELL and values[1].get("cell_id") == SCHEMA_CELL, "recovery plan terminal prefix drifted")
    _require(len({value.get("cell_id") for value in values}) == 40, "recovery plan has duplicate cells")
    return plan, values


def _remaining(plan_cells: list[dict[str, Any]]) -> list[dict[str, Any]]:
    values = plan_cells[2:]
    _require(len(values) == 38 and all(value.get("kind") == "unstarted" for value in values), "continuation must contain the exact 38 ordinary unstarted cells")
    return values


def _review(*, review_path: Path, expected_review_sha256: str, expected_plan_sha256: str,
            remaining: list[dict[str, Any]], route: Mapping[str, Any], adoption_path: Path,
            expected_adoption_sha256: str, marker_path: Path, expected_marker_sha256: str,
            sources: Mapping[str, Any], now: datetime) -> dict[str, Any]:
    review, raw = _json(review_path, "independent continuation review")
    _require(_hash(raw) == _hex(expected_review_sha256, "expected independent continuation review hash"), "independent continuation review hash drifted")
    _require(review.get("format_version") == 1 and review.get("kind") == "wpb0843_schema_recovery_continuation_review"
             and review.get("decision") == "approved_wpb_remaining_native_dispatch"
             and review.get("recovery_plan_sha256") == expected_plan_sha256
             and review.get("remaining_cell_ids") == [value["cell_id"] for value in remaining]
             and review.get("route_sha256") == _hash(json.dumps(dict(route), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")),
             "independent continuation review binding drifted")
    _require(review.get("adoption") == _descriptor(adoption_path, expected_adoption_sha256)
             and review.get("marker") == _descriptor(marker_path, expected_marker_sha256)
             and review.get("sources") == dict(sources), "independent continuation review source binding drifted")
    _require(isinstance(review.get("reviewer_task"), str) and review["reviewer_task"], "independent continuation review lacks reviewer identity")
    reviewed, expires = _timestamp(review.get("reviewed_at"), "independent continuation review reviewed_at"), _timestamp(review.get("expires_at"), "independent continuation review expires_at")
    timeout = route.get("timeout_seconds")
    _require(isinstance(timeout, int) and not isinstance(timeout, bool) and timeout > 0, "continuation route has no positive timeout")
    _require(reviewed <= now < expires, "independent continuation review is expired or not yet active")
    _require(expires - now >= timedelta(seconds=timeout), "independent continuation review does not cover the route timeout")
    return review


def _schema_marker(*, recovery: ModuleType, plan: Mapping[str, Any], schema: ModuleType, root: Path, plan_cells: list[dict[str, Any]],
                   adoption_path: Path, expected_adoption_sha256: str, marker_path: Path,
                   expected_marker_sha256: str, proposal_root: Path, source_cell_root: Path) -> None:
    first, adopted = plan_cells[:2]
    recovery._verify_admission(plan, root, first)
    materialized = schema.verify_adopted_projection_marker(
        marker_path=marker_path, expected_marker_sha256=expected_marker_sha256,
        adoption_path=adoption_path, expected_adoption_sha256=expected_adoption_sha256,
        proposal_root=proposal_root, source_cell_root=source_cell_root,
        expected_payload_sha256=adopted["payload_sha256"],
    )
    _require(isinstance(materialized, Mapping) and materialized.get("marker", {}).get("native_admission_permitted") is False,
             "0843 marker attempts a native admission")


def remaining_candidates(*, recovery_root: Path | str, expected_plan_sha256: str,
                         adoption_path: Path | str, expected_adoption_sha256: str,
                         marker_path: Path | str, expected_marker_sha256: str,
                         proposal_root: Path | str, source_cell_root: Path | str,
                         expected_schema_helper_sha256: str) -> list[str]:
    """Return the immutable native suffix only after replaying both predecessors."""
    root = Path(recovery_root).resolve()
    recovery = _load(RECOVERY_PATH, RECOVERY_SHA256, "frozen WPB recovery")
    plan, cells = _plan(recovery, root, expected_plan_sha256)
    schema = _load(SCHEMA_PATH, expected_schema_helper_sha256, "0843 schema recovery")
    _schema_marker(recovery=recovery, plan=plan, schema=schema, root=root, plan_cells=cells, adoption_path=Path(adoption_path).resolve(),
                   expected_adoption_sha256=_hex(expected_adoption_sha256, "0843 adoption hash"), marker_path=Path(marker_path).resolve(),
                   expected_marker_sha256=_hex(expected_marker_sha256, "0843 marker hash"), proposal_root=Path(proposal_root).resolve(),
                   source_cell_root=Path(source_cell_root).resolve())
    return [value["cell_id"] for value in _remaining(cells)]


def _guard(*, recovery_root: Path, expected_plan_sha256: str, cell_id: str, route: Mapping[str, Any],
           review_path: Path, expected_review_sha256: str, adoption_path: Path, expected_adoption_sha256: str,
           marker_path: Path, expected_marker_sha256: str, proposal_root: Path, source_cell_root: Path,
           expected_schema_helper_sha256: str, sources: Mapping[str, Any], queue_root: Path,
           inflight: bool = False) -> tuple[ModuleType, dict[str, Any], dict[str, Any]]:
    _sources_still_pinned(sources)
    recovery = _load(RECOVERY_PATH, RECOVERY_SHA256, "frozen WPB recovery")
    _require(queue_root == recovery.QUEUE_ROOT.resolve() and queue_root.is_dir(), "continuation requires the governed queue root")
    plan, cells = _plan(recovery, recovery_root, expected_plan_sha256)
    schema = _load(SCHEMA_PATH, expected_schema_helper_sha256, "0843 schema recovery")
    _schema_marker(recovery=recovery, plan=plan, schema=schema, root=recovery_root, plan_cells=cells, adoption_path=adoption_path,
                   expected_adoption_sha256=expected_adoption_sha256, marker_path=marker_path,
                   expected_marker_sha256=expected_marker_sha256, proposal_root=proposal_root, source_cell_root=source_cell_root)
    remaining = _remaining(cells)
    entries = {value["cell_id"]: value for value in remaining}
    item = entries.get(cell_id)
    _require(item is not None, "continuation never dispatches a terminal or already-adopted cell")
    for prior in remaining[:remaining.index(item)]:
        recovery._verify_admission(plan, recovery_root, prior)
    cell_root = recovery_root / "cells" / cell_id
    _require((cell_root / "prepared.json").is_file(), "continuation prepared-cell evidence is unavailable")
    if inflight:
        attempt, _raw = _json(cell_root / "attempt.json", "in-flight continuation attempt")
        _require(not (cell_root / "outcome.json").exists() and attempt.get("cell_id") == cell_id
                 and attempt.get("plan_sha256") == expected_plan_sha256 and attempt.get("review_sha256") == expected_review_sha256
                 and attempt.get("adoption_sha256") == expected_adoption_sha256 and attempt.get("marker_sha256") == expected_marker_sha256
                 and attempt.get("route_sha256") == _hash(json.dumps(dict(route), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8"))
                 and attempt.get("broker_sha256") == sources["broker"]["sha256"] and attempt.get("runtime_source_sha256") == sources["runtime"]["sha256"]
                 and attempt.get("helper_source_sha256") == sources["helper"]["sha256"] and attempt.get("schema_helper_sha256") == expected_schema_helper_sha256
                 and attempt.get("execution_helper_sha256") == sources["execution_helper"]["sha256"]
                 and attempt.get("broker_path") == sources["broker"]["path"] and attempt.get("runtime_source_path") == sources["runtime"]["path"]
                 and attempt.get("helper_source_path") == sources["helper"]["path"] and attempt.get("queue_root") == str(queue_root),
                 "in-flight continuation attempt binding drifted")
    else:
        _require(not (cell_root / "attempt.json").exists(), "continuation cell is already consumed; no resend")
    _sources_still_pinned(sources)
    _review(review_path=review_path, expected_review_sha256=expected_review_sha256, expected_plan_sha256=expected_plan_sha256,
            remaining=remaining, route=route, adoption_path=adoption_path, expected_adoption_sha256=expected_adoption_sha256,
            marker_path=marker_path, expected_marker_sha256=expected_marker_sha256, sources=sources, now=datetime.now(UTC))
    return recovery, plan, item


def dispatch_one(*, recovery_root: Path | str, expected_plan_sha256: str, cell_id: str, route: Mapping[str, Any],
                 reviewed_continuation_path: Path | str, expected_review_sha256: str,
                 adoption_path: Path | str, expected_adoption_sha256: str,
                 marker_path: Path | str, expected_marker_sha256: str,
                 proposal_root: Path | str, source_cell_root: Path | str,
                 expected_schema_helper_sha256: str, broker_path: Path | str,
                 runtime_source_path: Path | str, helper_source_path: Path | str,
                 queue_root: Path | str) -> dict[str, Any]:
    """Make one native suffix request after replaying every mutable permission gate."""
    root = Path(recovery_root).resolve()
    adoption, marker = Path(adoption_path).resolve(), Path(marker_path).resolve()
    proposal, source = Path(proposal_root).resolve(), Path(source_cell_root).resolve()
    review = Path(reviewed_continuation_path).resolve()
    broker_path, runtime_source_path, helper_source_path = Path(broker_path).resolve(), Path(runtime_source_path).resolve(), Path(helper_source_path).resolve()
    queue = Path(queue_root).resolve()
    sources = _sources(broker_path=broker_path, runtime_source_path=runtime_source_path,
                       helper_source_path=helper_source_path, expected_schema_helper_sha256=expected_schema_helper_sha256)
    recovery, plan, item = _guard(
        recovery_root=root, expected_plan_sha256=_hex(expected_plan_sha256, "expected recovery plan hash"), cell_id=cell_id, route=route,
        review_path=review, expected_review_sha256=_hex(expected_review_sha256, "expected continuation review hash"),
        adoption_path=adoption, expected_adoption_sha256=_hex(expected_adoption_sha256, "0843 adoption hash"),
        marker_path=marker, expected_marker_sha256=_hex(expected_marker_sha256, "0843 marker hash"), proposal_root=proposal,
        source_cell_root=source, expected_schema_helper_sha256=_hex(expected_schema_helper_sha256, "0843 schema helper hash"),
        sources=sources, queue_root=queue,
    )
    legacy = recovery._load_legacy()
    resolution, rows = recovery._rows(legacy, Path(plan["freeze_root"]))
    row = rows.get(cell_id)
    _require(isinstance(row, Mapping) and row.get("payload_sha256") == item["payload_sha256"]
             and resolution.get("schedule_sha256") == plan.get("schedule_sha256"), "continuation payload or schedule drifted")
    payload = resolution["payloads"][cell_id]
    _require(recovery.sha256(payload) == item["payload_sha256"], "continuation payload bytes drifted")
    schema = recovery._frozen_schema(plan)
    _module, broker_type = recovery._load_broker(broker_path)
    _require(isinstance(route.get("name"), str) and route["name"], "continuation route has no name")
    session_id = str(uuid.uuid4())
    cell_root = root / "cells" / cell_id
    attempt = {
        "format_version": 1, "cell_id": cell_id, "plan_sha256": expected_plan_sha256, "review_sha256": expected_review_sha256,
        "adoption_sha256": expected_adoption_sha256, "marker_sha256": expected_marker_sha256,
        "payload_sha256": recovery.sha256(payload), "schema_sha256": recovery.sha256(schema), "route_sha256": recovery.sha256(route),
        "broker_sha256": sources["broker"]["sha256"], "runtime_source_sha256": sources["runtime"]["sha256"],
        "helper_source_sha256": sources["helper"]["sha256"], "schema_helper_sha256": expected_schema_helper_sha256,
        "execution_helper_sha256": sources["execution_helper"]["sha256"], "broker_path": str(broker_path),
        "runtime_source_path": str(runtime_source_path), "helper_source_path": str(helper_source_path), "queue_root": str(queue), "session_id": session_id,
        "session_id_hash": recovery.sha256(session_id.encode("utf-8")), "route_name": route["name"],
        "requested_model": route.get("model"), "requested_reasoning_effort": route.get("reasoning_effort"),
    }
    recovery._write_new(cell_root / "attempt.json", attempt)
    recovery._write_new(cell_root / "route.json", dict(route))
    recovery._write_new(cell_root / "request.json", {"prompt": payload.decode("utf-8")})
    recovery._write_new(cell_root / "response-schema.json", schema)

    def before_contact() -> None:
        _guard(
            recovery_root=root, expected_plan_sha256=expected_plan_sha256, cell_id=cell_id, route=route, review_path=review,
            expected_review_sha256=expected_review_sha256, adoption_path=adoption, expected_adoption_sha256=expected_adoption_sha256,
            marker_path=marker, expected_marker_sha256=expected_marker_sha256, proposal_root=proposal, source_cell_root=source,
            expected_schema_helper_sha256=expected_schema_helper_sha256, sources=sources, queue_root=queue, inflight=True,
        )

    broker = broker_type(queue)
    outcome = broker.run_grok_native_request(str(route["name"]), {"prompt": payload.decode("utf-8")}, output_schema=schema,
                                              nonvisual_max_turns=1, session_id=session_id, before_contact=before_contact,
                                              expected_route_sha256=recovery.sha256(route))
    _require(isinstance(outcome, Mapping) and set(outcome) == {"state", "result", "failure"}, "canonical broker outcome is malformed")
    recovery._write_new(cell_root / "outcome.json", dict(outcome))
    if outcome["state"] != "completed" or outcome["failure"] is not None or not isinstance(outcome["result"], Mapping):
        return {"cell_id": cell_id, "status": "terminal_no_resend", "outcome_sha256": recovery.sha256(dict(outcome)), "provider_calls_made": 1}
    result = dict(outcome["result"])
    descriptor = result.get("native_envelope_artifact")
    _require(isinstance(descriptor, Mapping), "completed broker result lacks envelope descriptor")
    envelope = broker.read_grok_native_envelope(dict(descriptor))
    _require(isinstance(envelope, bytes), "canonical broker returned a non-byte envelope")
    recovery._write_new(cell_root / "result.json", result)
    with (cell_root / "native-envelope.json").open("xb") as handle:
        handle.write(envelope)
    return {"cell_id": cell_id, "status": "completed_pending_native_admission", "result_sha256": recovery.sha256(result),
            "envelope_sha256": recovery.sha256(envelope), "provider_calls_made": 1}


def admit_native_suffix(*, recovery_root: Path | str, expected_plan_sha256: str, cell_id: str, **marker_arguments: Any) -> dict[str, Any]:
    """Delegate ordinary suffix admission to the frozen native-evidence validator."""
    candidates = remaining_candidates(recovery_root=recovery_root, expected_plan_sha256=expected_plan_sha256, **marker_arguments)
    _require(cell_id in candidates, "continuation never admits a terminal or adopted local-session cell")
    recovery = _load(RECOVERY_PATH, RECOVERY_SHA256, "frozen WPB recovery")
    return recovery.admit(recovery_root=Path(recovery_root), expected_plan_sha256=expected_plan_sha256, cell_id=cell_id)
