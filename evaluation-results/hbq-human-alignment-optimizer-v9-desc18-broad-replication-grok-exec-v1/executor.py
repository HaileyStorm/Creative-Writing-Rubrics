#!/usr/bin/env python3
"""Bounded Grok execution for the desc18 public/open Fresh96 replication."""
from __future__ import annotations

import argparse
import asyncio
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
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType
from typing import Any

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
STUDY_ID = "hbq-human-alignment-optimizer-v9-desc18-broad-replication-grok-exec-v1"
SOURCE_COMMIT = "83d7be718c99c1135302ccb4f8d339a4c68f292f"
FREEZE = HERE.parent / "hbq-human-alignment-optimizer-v9-desc18-broad-replication-candidates-v1"
FREEZE_HASHES = {
    FREEZE / "study.py": "99387d9626ae13f20ef58f0a7f6624ebe850d8477ba17934c4f35735ca9eda16",
    FREEZE / "study-contract.json": "5115e46f3f8c858e7954ceffa77d2d9dbff3e781f36a5aaf04fb2506c7c07dd2",
    FREEZE / "README.md": "3208c90b41ea52dcb81e3763d619ea1bcc7f75f3d0c10a9016d63be7dd239ebd",
}
FREEZE_SCHEDULE_SHA256 = "1e45510b99e328388ea663ef42523d202322011959ad7f0e62629c3ec8075dfa"
PARENT = HERE.parent / "hbq-human-alignment-optimizer-v8-desc17-generalization-grok-exec-v1"
PARENT_COMMIT = "7a768f09c34a226740fdd38f4efed0150d3580e0"
PARENT_HASHES = {
    PARENT / "executor.py": "bb332a22fda1f8c358fccaf5b9c852ddd915702b2f42fccf89c8af240f328901",
    PARENT / "study-contract.json": "c0d4da639fd3d228b8cca41cbf9b7daa63266dfe904b413e01464ac41452702a",
    PARENT / "README.md": "4d44633b4d90035226de0bb4ca7bcae44e1334a13f9aa87d3014ef54c8ac2fa7",
}
MAX_CONCURRENCY = 10
CONTACT_VALIDITY_MARGIN_SECONDS = 5.0
CLAIM_STUDY_ID = "hbq-human-alignment-optimizer-v5-f20-broader-development-grok-exec-v3-threadsafe-route-load"
DIMENSIONS = ("Relevance", "Coherence", "Empathy", "Surprise", "Engagement", "Complexity")


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


def _safe(path: Path) -> Path:
    absolute = Path(os.path.abspath(path))
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current /= part
        if current.exists():
            _plain(current, directory=True if current != absolute else None)
    return absolute


def stable(path: Path) -> bytes:
    path = _safe(Path(path))
    _plain(path, directory=False)
    before = os.lstat(path)
    with path.open("rb") as handle:
        opened = os.fstat(handle.fileno())
        raw = handle.read()
        after = os.fstat(handle.fileno())
    identity = (before.st_dev, before.st_ino, stat.S_IFMT(before.st_mode), before.st_size)
    if identity != (opened.st_dev, opened.st_ino, stat.S_IFMT(opened.st_mode), opened.st_size) or identity != (after.st_dev, after.st_ino, stat.S_IFMT(after.st_mode), after.st_size):
        raise ValueError("stable read drift")
    return raw


def strict(raw: bytes, label: str) -> dict[str, Any]:
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
    if not isinstance(value, dict) or canonical(value) != raw:
        raise ValueError(f"noncanonical {label}")
    return value


def _blob(path: Path, commit: str) -> bytes:
    relative = path.relative_to(REPO).as_posix()
    result = subprocess.run(["git", "-C", str(REPO), "show", f"{commit}:{relative}"], capture_output=True, check=False)
    if result.returncode:
        raise ValueError("pinned Git blob is absent")
    return result.stdout


def _load(path: Path, hashes: Mapping[Path, str], commit: str, name: str) -> ModuleType:
    for candidate, expected in hashes.items():
        raw = stable(candidate)
        if sha256(raw) != expected or _blob(candidate, commit) != raw:
            raise ValueError("pinned execution dependency drifted")
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ValueError("cannot load pinned execution dependency")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(name, None)
    return module


def parent_stack() -> ModuleType:
    return _load(PARENT / "executor.py", PARENT_HASHES, PARENT_COMMIT, "_desc18_desc17_stack")


def freeze_module() -> ModuleType:
    return _load(FREEZE / "study.py", FREEZE_HASHES, SOURCE_COMMIT, "_desc18_freeze")


def contract() -> dict[str, Any]:
    return strict(stable(HERE / "study-contract.json"), "study contract")


def _validate_contract() -> None:
    expected = {
        "authority": {"confirmation": {"cells": 0, "status": "unopened"}, "promotion": "none", "runtime": "none", "selection": "none", "sol": "veto_only_after_grok_qualification"},
        "format_version": 1,
        "geometry": {"candidates": 2, "confirmation_cells": 0, "grok_cells": 64, "open_validation_groups": 16, "open_validation_items": 32, "sol_cells": 0},
        "kind": "desc18_open_fresh96_replication_grok_execution",
        "pinned_desc17_stack": {"commit": PARENT_COMMIT, "executor_sha256": PARENT_HASHES[PARENT / "executor.py"]},
        "pinned_freeze": {"commit": SOURCE_COMMIT, "schedule_sha256": FREEZE_SCHEDULE_SHA256, "study_contract_sha256": FREEZE_HASHES[FREEZE / "study-contract.json"], "study_sha256": FREEZE_HASHES[FREEZE / "study.py"]},
        "prohibitions": ["tools disabled", "no fallback or resend", "no confirmation, reserve, selection, promotion, runtime, or general claim"],
        "study_id": STUDY_ID,
    }
    if contract() != expected:
        raise ValueError("execution contract drifted")


def frozen_schedule(freeze_root: Path) -> dict[str, Any]:
    module = freeze_module()
    schedule = module.validate_frozen_root(Path(freeze_root))
    if schedule.get("schedule_sha256") != FREEZE_SCHEDULE_SHA256 or schedule.get("geometry") != {"candidates": 2, "grok_cells": 64, "open_validation_groups": 16, "open_validation_items": 32, "sol_cells": 0}:
        raise ValueError("desc18 freeze identity drifted")
    cells = schedule.get("cells")
    if not isinstance(cells, list) or len(cells) != 64 or len({row.get("item_id") for row in cells}) != 32 or len({row.get("prompt_group_id") for row in cells}) != 16:
        raise ValueError("desc18 freeze geometry drifted")
    value = dict(schedule)
    value["study_id"] = STUDY_ID
    value["kind"] = "frozen_desc18_open_fresh96_replication_grok_execution_schedule"
    value["geometry"] = {"candidates": 2, "confirmation_cells": 0, "grok_cells": 64, "open_validation_groups": 16, "open_validation_items": 32, "sol_cells": 0}
    value["authority"] = {"provider_calls_made": 0, "process_launches": 0, "selection": "none", "promotion": "none", "runtime": "none", "sol": "veto_only_after_grok_qualification", "confirmation": {"status": "unopened", "cells": 0}}
    value["frozen_schedule_sha256"] = FREEZE_SCHEDULE_SHA256
    value.pop("schedule_sha256", None)
    value["schedule_sha256"] = sha256(value)
    _validate_contract()
    return value


def _validate_precontact_payload(payload: bytes) -> None:
    value = strict(payload, "outbound payload")
    writing = value.get("writing")
    if not isinstance(writing, Mapping) or set(writing) != {"prompt", "story"}:
        raise ValueError("outbound writing must contain full prompt and story text")
    for name in ("prompt", "story"):
        text = writing.get(name)
        if not isinstance(text, str) or not text.strip() or _pointer_like(text):
            raise ValueError(f"outbound {name} is missing or pointer-like")
        if not re.search(r"[A-Za-z0-9]", text):
            raise ValueError(f"outbound {name} is not substantive text")
    story = str(writing["story"]).strip()
    if len(story) < 120 or len(re.findall(r"[A-Za-z0-9]+", story)) < 20:
        raise ValueError("outbound story is not full text")


def _pointer_like(text: str) -> bool:
    raw = text.strip()
    value = raw.casefold()
    return (
        value in {"x", "n/a", "none", "placeholder", "[placeholder]", "missing", "redacted"}
        or value.startswith(("file:", "source:", "http:", "https:", "\\\\", "/", "./", "../", "see attached", "see workspace", "workspace:", "path:"))
        or bool(re.match(r"^[a-z]:[\\/]", value))
        or bool(re.match(r"^[a-z][a-z0-9+.-]*://", value))
        or bool(re.fullmatch(r"(?:@|\.?\.?[\\/])?[\w.-]+\.(?:txt|json|jsonl|csv|md)", value))
        or bool(re.fullmatch(r"[0-9a-f]{16,}", value))
        or bool(re.fullmatch(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", value))
        or bool(re.fullmatch(r"(?:cell|item|prompt|story|source|record|sample)[_-]?[0-9a-f]+", value))
    )


def _validate_response_quality(response: bytes) -> None:
    envelope = strict(response, "native response")
    structured = envelope.get("structuredOutput")
    if not isinstance(structured, Mapping):
        raise TypeError("native response lacks structured output")
    if set(structured) != {"scores", "evidence", "coverage"}:
        raise ValueError("native response structured output shape drifted")
    scores, evidence, coverage = structured["scores"], structured["evidence"], structured["coverage"]
    if (not isinstance(scores, Mapping) or not isinstance(evidence, Mapping) or not isinstance(coverage, Mapping)
            or set(scores) != set(DIMENSIONS) or set(evidence) != set(DIMENSIONS) or set(coverage) != set(DIMENSIONS)):
        raise ValueError("native response dimension shape drifted")
    values = list(scores.values())
    if (any(type(item) not in (int, float) or not math.isfinite(float(item)) or not 0 <= float(item) <= 5 for item in values)
            or all(float(item) == 0 for item in values)):
        raise ValueError("all-zero or invalid score vector")
    if any(type(item) is not bool for item in coverage.values()):
        raise TypeError("native response coverage is invalid")
    for item in evidence.values():
        if not isinstance(item, str):
            raise TypeError("native response evidence is invalid")
        normalized = " ".join(item.split()).casefold()
        if (not normalized or normalized in {"x", "n/a", "none", "missing", "redacted"}
                or "placeholder" in normalized
                or re.search(r"\b(?:search(?:ing)?|look(?:ing)?|inspect(?:ing)?) (?:the )?workspace\b", normalized)
                or re.search(r"\bworkspace (?:search|lookup)\b", normalized)):
            raise ValueError("native response contains placeholder evidence")


def _surrogates(freeze_root: Path) -> dict[str, Path]:
    parent = _safe(Path(freeze_root)).parent
    return {
        "normalized_root": parent / ".desc18-exec-surrogate-normalized",
        "materialization_root": parent / ".desc18-exec-surrogate-materialization",
        "frozen_successor_path": parent / ".desc18-exec-surrogate-successor.json",
        "hanna_csv_path": parent / ".desc18-exec-surrogate-hanna.csv",
    }


@contextmanager
def _bound_source(*, freeze_root: Path) -> Iterator[tuple[ModuleType, ModuleType, dict[str, Any], ModuleType, ModuleType]]:
    schedule = frozen_schedule(freeze_root)
    parent = parent_stack()
    base = parent.desc13_stack()
    v3 = base.v3_runtime()
    runtime = v3._runtime()
    lifecycle = runtime.lifecycle()
    source = lifecycle.live()
    original_schedule, original_study_id = lifecycle.schedule, lifecycle.STUDY_ID
    lifecycle.schedule = lambda **_kwargs: (source, schedule)
    lifecycle.STUDY_ID = STUDY_ID
    try:
        yield lifecycle, source, schedule, parent, runtime
    finally:
        lifecycle.schedule, lifecycle.STUDY_ID = original_schedule, original_study_id


def _validated_route(parent: ModuleType, runtime: ModuleType, queue_root: Path, route_provider: Callable[[Path], tuple[dict[str, Any], dict[str, Any]]] | None) -> Callable[[Path], tuple[dict[str, Any], dict[str, Any]]]:
    base = parent.desc13_stack()
    inherited = parent._validated_route(base, runtime, Path(queue_root), route_provider)

    def validated(root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
        route, evidence = inherited(root)
        _live_route_expiry(route)
        return route, evidence

    return validated


def _live_route_expiry(route: Mapping[str, Any]) -> datetime:
    cost = route.get("cost_evidence")
    if not isinstance(cost, Mapping):
        raise TypeError("route cost evidence is invalid")
    try:
        checked_at = datetime.fromisoformat(str(cost.get("checked_at", "")).replace("Z", "+00:00"))
        expires_at = datetime.fromisoformat(str(cost.get("expires_at", "")).replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("route cost timestamp is invalid") from error
    if checked_at.tzinfo is None or expires_at.tzinfo is None:
        raise ValueError("route cost timestamp lacks timezone")
    checked_at, expires_at = checked_at.astimezone(timezone.utc), expires_at.astimezone(timezone.utc)
    now = datetime.now(timezone.utc)
    if checked_at >= expires_at or not checked_at <= now < expires_at:
        raise ValueError("route cost evidence is not currently valid")
    return expires_at


def _require_contact_validity(route: Mapping[str, Any]) -> None:
    timeout = route.get("timeout_seconds")
    if type(timeout) not in (int, float) or not math.isfinite(float(timeout)) or timeout <= 0:
        raise ValueError("route timeout is invalid")
    required = float(timeout) + CONTACT_VALIDITY_MARGIN_SECONDS
    if (_live_route_expiry(route) - datetime.now(timezone.utc)).total_seconds() < required:
        raise ValueError("route cost evidence cannot cover this provider contact")


def _guard_runner(parent: ModuleType, runner: Callable[..., Mapping[str, Any]], lifecycle: ModuleType, schedule: Mapping[str, Any]) -> Callable[..., Mapping[str, Any]]:
    guarded = parent._guard_runner(runner, lifecycle, schedule)

    def checked(**kwargs: Any) -> Mapping[str, Any]:
        before_contact = kwargs["before_contact"]

        def precontact() -> None:
            _validate_precontact_payload(kwargs["prompt"])
            _require_contact_validity(kwargs["route"])
            before_contact()

        result = guarded(**{**kwargs, "before_contact": precontact})
        response = result.get("native_response_bytes") if isinstance(result, Mapping) else None
        if not isinstance(response, bytes):
            raise TypeError("runner response bytes are absent")
        _validate_response_quality(response)
        return result

    return checked


def prepare_all(*, output_root: Path, freeze_root: Path, queue_root: Path, authorization_acknowledgement_sha256: str, route_provider: Callable[[Path], tuple[dict[str, Any], dict[str, Any]]] | None = None) -> dict[str, Any]:
    with _bound_source(freeze_root=Path(freeze_root)) as (lifecycle, _source, schedule, parent, runtime):
        result = lifecycle.prepare_all(output_root=Path(output_root), queue_root=Path(queue_root), authorization_acknowledgement_sha256=authorization_acknowledgement_sha256, route_provider=_validated_route(parent, runtime, queue_root, route_provider), **_surrogates(Path(freeze_root)))
    if result.get("provider_calls_made") != 0 or result.get("process_launches") != 0 or len(result.get("prepared_cells", [])) != 64:
        raise ValueError("desc18 preparation lifecycle drifted")
    if stable(Path(output_root) / "schedule.json") != canonical(schedule):
        raise ValueError("persisted schedule differs from prepared schedule")
    return {"format_version": 1, "study_id": STUDY_ID, "kind": "prepared_64_desc18_open_validation_grok_cells", "prepared_cells": result["prepared_cells"], "logical_cells": 64, "effective_candidates": 2, "provider_calls_made": 0, "process_launches": 0}


def _execute_bound(*, lifecycle: ModuleType, parent: ModuleType, runtime: ModuleType, schedule: Mapping[str, Any], output_root: Path, freeze_root: Path, queue_root: Path, authorization_acknowledgement_sha256: str, cell_id: str, route_provider: Callable[[Path], tuple[dict[str, Any], dict[str, Any]]], runner: Callable[..., Mapping[str, Any]] | None) -> dict[str, Any]:
    if cell_id not in {row["cell_id"] for row in schedule["cells"]}:
        raise ValueError("unknown cell")
    slot: Path | None = None
    record: dict[str, Any] | None = None
    try:
        slot, record = runtime._acquire_global_slot(Path(output_root), cell_id)
        state = runtime._claim(Path(output_root), cell_id)
        if state != "claimed_now":
            return {"format_version": 1, "study_id": STUDY_ID, "cell_id": cell_id, "state": "reconcile_required" if state == "expired" else state, "provider_calls_made": 0, "process_launches": 0}
        selected = runner or lifecycle.live()._default_runner
        return lifecycle.execute_one(output_root=Path(output_root), queue_root=Path(queue_root), authorization_acknowledgement_sha256=authorization_acknowledgement_sha256, cell_id=cell_id, allow_remote=True, route_provider=route_provider, runner=_guard_runner(parent, selected, lifecycle, schedule), **_surrogates(Path(freeze_root)))
    finally:
        runtime._release_global_slot(slot, record)


def execute_one(*, output_root: Path, freeze_root: Path, queue_root: Path, authorization_acknowledgement_sha256: str, cell_id: str, allow_remote: bool, route_provider: Callable[[Path], tuple[dict[str, Any], dict[str, Any]]] | None = None, runner: Callable[..., Mapping[str, Any]] | None = None) -> dict[str, Any]:
    if allow_remote is not True:
        raise ValueError("explicit allow_remote required")
    with _bound_source(freeze_root=Path(freeze_root)) as (lifecycle, _source, schedule, parent, runtime):
        return _execute_bound(lifecycle=lifecycle, parent=parent, runtime=runtime, schedule=schedule, output_root=Path(output_root), freeze_root=Path(freeze_root), queue_root=Path(queue_root), authorization_acknowledgement_sha256=authorization_acknowledgement_sha256, cell_id=cell_id, route_provider=_validated_route(parent, runtime, queue_root, route_provider), runner=runner)


async def execute_wave(*, output_root: Path, freeze_root: Path, queue_root: Path, authorization_acknowledgement_sha256: str, allow_remote: bool, route_provider: Callable[[Path], tuple[dict[str, Any], dict[str, Any]]] | None = None, runner: Callable[..., Mapping[str, Any]] | None = None) -> list[dict[str, Any]]:
    if allow_remote is not True:
        raise ValueError("explicit allow_remote required")
    with _bound_source(freeze_root=Path(freeze_root)) as (lifecycle, _source, schedule, parent, runtime):
        route = _validated_route(parent, runtime, queue_root, route_provider)
        frozen_route, evidence = route(Path(queue_root))
        semaphore = asyncio.Semaphore(MAX_CONCURRENCY)

        async def run(cell_id: str) -> dict[str, Any]:
            async with semaphore:
                return await asyncio.to_thread(_execute_bound, lifecycle=lifecycle, parent=parent, runtime=runtime, schedule=schedule, output_root=Path(output_root), freeze_root=Path(freeze_root), queue_root=Path(queue_root), authorization_acknowledgement_sha256=authorization_acknowledgement_sha256, cell_id=cell_id, route_provider=lambda _ignored: (frozen_route, evidence), runner=runner)

        completed = await asyncio.gather(*(run(row["cell_id"]) for row in schedule["cells"]), return_exceptions=True)
        failure = next((item for item in completed if isinstance(item, BaseException)), None)
        if failure is not None:
            raise failure
    if len(completed) != 64:
        raise ValueError("desc18 execution wave cardinality drifted")
    return completed


def _admit_cell(lifecycle: ModuleType, source: ModuleType, output_root: Path, row: Mapping[str, Any], schedule: Mapping[str, Any], acknowledgement: str) -> tuple[bytes, bytes, Mapping[str, Any], Mapping[str, Any], Mapping[str, Any]]:
    root = Path(output_root) / str(row["cell_id"])
    stored = strict(stable(root / "prepared.json"), "prepared")
    if not isinstance(stored.get("route"), Mapping) or not isinstance(stored.get("route_evidence"), Mapping):
        raise TypeError("collector route binding drifted")
    if strict(stable(root / "authorization-acknowledgement.json"), "acknowledgement").get("acknowledgement_sha256") != acknowledgement:
        raise ValueError("collector acknowledgement drifted")
    raw, prompt, schema = lifecycle.payload(row)
    request, response, identity, settings = lifecycle.admit(root, row, schedule, raw, prompt, schema, stored["route"], stored["route_evidence"], acknowledgement, source)
    _validate_response_quality(response)
    return request, response, identity, settings, stored


def _validate_claims(output_root: Path, expected_cells: set[str]) -> None:
    claims = Path(output_root) / ".claims"
    _plain(claims, directory=True)
    if {path.name for path in claims.iterdir()} != expected_cells:
        raise ValueError("execution claim inventory drifted")
    for cell_id in expected_cells:
        claim = claims / cell_id
        _plain(claim, directory=True)
        if {path.name for path in claim.iterdir()} != {"claim.json"}:
            raise ValueError("execution claim artifact inventory drifted")
        record = strict(stable(claim / "claim.json"), "claim")
        if (set(record) != {"format_version", "study_id", "kind", "cell_id", "acquired_at", "lease_seconds"}
                or record.get("format_version") != 1
                or record.get("study_id") != CLAIM_STUDY_ID
                or record.get("kind") != "exclusive_execution_claim"
                or record.get("cell_id") != cell_id
                or type(record.get("acquired_at")) not in {int, float}
                or type(record.get("lease_seconds")) not in {int, float}
                or record["lease_seconds"] <= 0):
            raise ValueError("execution claim binding drifted")


def finalize_collector(*, output_root: Path, freeze_root: Path, collector_output: Path, authorization_acknowledgement_sha256: str) -> dict[str, Any]:
    with _bound_source(freeze_root=Path(freeze_root)) as (lifecycle, source, schedule, parent, _runtime):
        collector = _safe(Path(collector_output))
        if collector.exists():
            raise ValueError("collector output must be fresh")
        expected_cells = {row["cell_id"] for row in schedule["cells"]}
        if {path.name for path in Path(output_root).iterdir()} != {"schedule.json", ".claims", *expected_cells} or stable(Path(output_root) / "schedule.json") != canonical(schedule):
            raise ValueError("output schedule inventory drifted")
        _validate_claims(Path(output_root), expected_cells)
        cells: list[dict[str, Any]] = []
        frozen_route: Mapping[str, Any] | None = None
        frozen_evidence: Mapping[str, Any] | None = None
        for row in schedule["cells"]:
            request, response, identity, settings, stored = _admit_cell(lifecycle, source, Path(output_root), row, schedule, authorization_acknowledgement_sha256)
            if frozen_route is None:
                frozen_route, frozen_evidence = stored["route"], stored["route_evidence"]
            if stored["route"] != frozen_route or stored["route_evidence"] != frozen_evidence:
                raise ValueError("collector route/evidence differs across cells")
            cells.append({"cell_id": row["cell_id"], "payload_base64": row["payload_base64"], "payload_sha256": row["payload_sha256"], "native_request_base64": base64.b64encode(request).decode("ascii"), "native_request_sha256": sha256(request), "native_response_base64": base64.b64encode(response).decode("ascii"), "native_response_sha256": sha256(response), "identity": identity, "effective_settings": settings, "effective_settings_sha256": sha256(settings)})
        if frozen_route is None or frozen_evidence is None:
            raise ValueError("collector has no cells")
        parent._validate_route_evidence(frozen_route, frozen_evidence)
        value = {"format_version": 1, "study_id": STUDY_ID, "kind": "complete_64_desc18_open_validation_grok_receipts_cardinality_unproven", "schedule_sha256": schedule["schedule_sha256"], "authorization_acknowledgement_sha256": authorization_acknowledgement_sha256, "route": frozen_route, "route_evidence": frozen_evidence, "cells": cells, "native_endpoint_contact_cardinality": "unproven", "provider_calls_made": None, "process_launches": 64}
        lifecycle.write_new(collector, canonical(value))
        return {"format_version": 1, "study_id": STUDY_ID, "kind": value["kind"], "collector_sha256": sha256(value), "cells": 64, "native_endpoint_contact_cardinality": "unproven", "provider_calls_made": None, "process_launches": 64}


def replay_collector(*, output_root: Path, freeze_root: Path, collector_path: Path) -> dict[str, Any]:
    with _bound_source(freeze_root=Path(freeze_root)) as (lifecycle, source, schedule, parent, _runtime):
        collector = strict(stable(Path(collector_path)), "collector")
        expected_fields = {"format_version", "study_id", "kind", "schedule_sha256", "authorization_acknowledgement_sha256", "route", "route_evidence", "cells", "native_endpoint_contact_cardinality", "provider_calls_made", "process_launches"}
        if (set(collector) != expected_fields or collector.get("format_version") != 1 or collector.get("study_id") != STUDY_ID or collector.get("kind") != "complete_64_desc18_open_validation_grok_receipts_cardinality_unproven" or collector.get("schedule_sha256") != schedule["schedule_sha256"] or collector.get("native_endpoint_contact_cardinality") != "unproven" or collector.get("provider_calls_made") is not None or collector.get("process_launches") != 64 or not isinstance(collector.get("route"), Mapping) or not isinstance(collector.get("route_evidence"), Mapping) or not isinstance(collector.get("cells"), list) or len(collector["cells"]) != 64):
            raise ValueError("collector drifted")
        parent._validate_route_evidence(collector.get("route", {}), collector.get("route_evidence", {}))
        index = {row["cell_id"]: row for row in schedule["cells"]}
        _validate_claims(Path(output_root), set(index))
        seen: set[tuple[str, str]] = set()
        for supplied in collector["cells"]:
            expected_cell = {"cell_id", "payload_base64", "payload_sha256", "native_request_base64", "native_request_sha256", "native_response_base64", "native_response_sha256", "identity", "effective_settings", "effective_settings_sha256"}
            if not isinstance(supplied, Mapping) or set(supplied) != expected_cell or supplied.get("cell_id") not in index:
                raise ValueError("collector cell drifted")
            row = index[supplied["cell_id"]]
            request, response, identity, settings, stored = _admit_cell(lifecycle, source, Path(output_root), row, schedule, str(collector.get("authorization_acknowledgement_sha256", "")))
            supplied_request = base64.b64decode(supplied.get("native_request_base64", ""), validate=True)
            supplied_response = base64.b64decode(supplied.get("native_response_base64", ""), validate=True)
            if (stored.get("route") != collector["route"] or stored.get("route_evidence") != collector["route_evidence"]
                    or supplied.get("payload_base64") != row["payload_base64"] or supplied.get("payload_sha256") != row["payload_sha256"]
                    or supplied_request != request or supplied_response != response
                    or supplied.get("native_request_sha256") != sha256(request) or supplied.get("native_response_sha256") != sha256(response)
                    or supplied.get("identity") != identity or supplied.get("effective_settings") != settings
                    or supplied.get("effective_settings_sha256") != sha256(settings)):
                raise ValueError("collector native receipt differs from persisted execution")
            key = (identity.get("request_id"), identity.get("session_id")) if isinstance(identity, Mapping) else ("", "")
            if not all(key) or key in seen:
                raise ValueError("duplicate or invalid native identity")
            seen.add(key)
        if set(index) != {row.get("cell_id") for row in collector["cells"]}:
            raise ValueError("partial collector")
        return {"format_version": 1, "study_id": STUDY_ID, "collector_sha256": sha256(collector), "cells": 64, "provider_calls_made": None, "process_launches": 64, "equal_group_projection_ready": True, "native_endpoint_contact_cardinality": "unproven", "authority": {"selection": "none", "promotion": "none", "runtime": "none", "confirmation": {"status": "unopened", "cells": 0}}}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    for name in ("prepare-all", "execute-one", "execute-wave", "finalize-collector", "replay-collector"):
        modes.add_argument("--" + name, action="store_true")
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--freeze-root", type=Path, required=True)
    parser.add_argument("--queue-root", type=Path)
    parser.add_argument("--collector-output", type=Path)
    parser.add_argument("--collector-path", type=Path)
    parser.add_argument("--authorization-acknowledgement-sha256")
    parser.add_argument("--cell-id")
    parser.add_argument("--allow-remote", action="store_true")
    args = parser.parse_args(argv)
    shared = {"output_root": args.output_root, "freeze_root": args.freeze_root}
    if args.prepare_all:
        if args.allow_remote or not args.queue_root or not args.authorization_acknowledgement_sha256:
            parser.error("prepare requires queue/acknowledgement and forbids remote execution")
        result = prepare_all(**shared, queue_root=args.queue_root, authorization_acknowledgement_sha256=args.authorization_acknowledgement_sha256)
    elif args.execute_one:
        if not args.allow_remote or not args.queue_root or not args.authorization_acknowledgement_sha256 or not args.cell_id:
            parser.error("execute-one requires queue/acknowledgement/cell and explicit remote execution")
        result = execute_one(**shared, queue_root=args.queue_root, authorization_acknowledgement_sha256=args.authorization_acknowledgement_sha256, cell_id=args.cell_id, allow_remote=True)
    elif args.execute_wave:
        if not args.allow_remote or not args.queue_root or not args.authorization_acknowledgement_sha256:
            parser.error("execute-wave requires queue/acknowledgement and explicit remote execution")
        result = asyncio.run(execute_wave(**shared, queue_root=args.queue_root, authorization_acknowledgement_sha256=args.authorization_acknowledgement_sha256, allow_remote=True))
    elif args.finalize_collector:
        if args.allow_remote or not args.collector_output or not args.authorization_acknowledgement_sha256:
            parser.error("finalize requires collector output/acknowledgement and forbids remote execution")
        result = finalize_collector(**shared, collector_output=args.collector_output, authorization_acknowledgement_sha256=args.authorization_acknowledgement_sha256)
    else:
        if args.allow_remote or not args.collector_path:
            parser.error("replay requires collector path and forbids remote execution")
        result = replay_collector(**shared, collector_path=args.collector_path)
    print(canonical(result).decode("utf-8"), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
