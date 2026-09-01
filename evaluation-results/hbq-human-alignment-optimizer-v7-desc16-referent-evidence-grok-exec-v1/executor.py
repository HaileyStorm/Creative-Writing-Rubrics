#!/usr/bin/env python3
"""Bounded Grok execution for the frozen desc16 referent-evidence development schedule."""
from __future__ import annotations

import argparse
import asyncio
import base64
import importlib.util
import json
import os
import stat
import sys
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path
from types import ModuleType
from typing import Any

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
STUDY_ID = "hbq-human-alignment-optimizer-v7-desc16-referent-evidence-grok-exec-v1"
SOURCE_COMMIT = "2fb8b1e1dd9acc0d0869c3ebf51c384653ac3ee5"
FREEZE_PACKAGE = HERE.parent / "hbq-human-alignment-optimizer-v7-desc16-referent-evidence-candidates-v1"
DESC13_STACK = HERE.parent / "hbq-human-alignment-optimizer-v6-desc13-lower-step-grok-exec-v1"
FREEZE_HASHES = {
    FREEZE_PACKAGE / "study.py": "31735918ae0d9a1e2871e0b40ac00b3c587388531f9c721a73e7334900f2f29a",
    FREEZE_PACKAGE / "study-contract.json": "ffd560d68e5ddf6d73d9534342121c5e56519b6058446b5f34a99d1acb7acd9f",
    FREEZE_PACKAGE / "README.md": "f2ccfdd81c4a5bf02e1da9384c95f1a9a96eaf2eedc666dd46024542624dc0c0",
}
DESC13_HASHES = {
    DESC13_STACK / "executor.py": "ad86eb68ccd2bad67473e3f54f6191fb8654b2bfd33a937efbb cda94e3a49ec6".replace(" ", ""),
    DESC13_STACK / "study-contract.json": "66017a72f570d388d5f5cb84ac66b9cfd05bb42e711ac0d1770b6156c2fbcddd",
    DESC13_STACK / "README.md": "ea0378ae7a25cf5dd78ecbec4e8cf837fb10d4b52a29ce8a20cd84f81354abc5",
}
FREEZE_SCHEDULE_SHA256 = "bffed26aec631bda163909fcdc66d5a91eef35ce9082d75bb05cce5c58fb6d45"
FREEZE_SCHEDULE_FILE_SHA256 = "00cf5cd9d95767cec44fb296197eec1760aab18327d753b816d84462aca712f3"
FREEZE_MANIFEST_SHA256 = "5aa8f797d833e387432d956b7d7e326ab71fa3a5642a368967842b26aa82909f"
MAX_CONCURRENCY = 10
CLAIM_STUDY_ID = "hbq-human-alignment-optimizer-v5-f20-broader-development-grok-exec-v3-threadsafe-route-load"


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def sha256(value: bytes | Any) -> str:
    import hashlib
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


def _blob(relative: Path, *, commit: str) -> bytes:
    import subprocess
    result = subprocess.run(["git", "-C", str(REPO), "show", f"{commit}:{relative.as_posix()}"], capture_output=True, check=False)
    if result.returncode:
        raise ValueError("pinned source Git blob is absent")
    return result.stdout


def _load_pinned(path: Path, hashes: Mapping[Path, str], name: str, *, commit: str) -> ModuleType:
    for candidate, digest in hashes.items():
        raw = stable(candidate)
        if sha256(raw) != digest or _blob(candidate.relative_to(REPO), commit=commit) != raw:
            raise ValueError("pinned execution dependency drifted")
    raw = stable(path)
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ValueError("cannot load pinned execution dependency")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(name, None)
    if stable(path) != raw:
        raise ValueError("pinned execution dependency changed during load")
    return module


def desc13_stack() -> ModuleType:
    return _load_pinned(DESC13_STACK / "executor.py", DESC13_HASHES, "_desc16_referent_evidence_desc13_stack", commit="cd67452ceb018e18f5d2d3315c544af0d47f23ef")


def _verify_freeze_package() -> None:
    for candidate, digest in FREEZE_HASHES.items():
        raw = stable(candidate)
        if sha256(raw) != digest or _blob(candidate.relative_to(REPO), commit=SOURCE_COMMIT) != raw:
            raise ValueError("pinned freeze package drifted")


def contract() -> dict[str, Any]:
    return strict(stable(HERE / "study-contract.json"), "study contract")


def _expected_contract() -> dict[str, Any]:
    return {
        "authority": {"confirmation": {"cells": 0, "status": "unopened"}, "promotion": "none", "runtime": "none", "selection": "none", "sol": "out_of_scope"},
        "format_version": 1,
        "geometry": {"candidates": 4, "confirmation_cells": 0, "development_groups": 7, "development_items": 13, "grok_cells": 52, "sol_cells": 0},
        "kind": "desc16_referent_evidence_grok_development_execution",
        "pinned_desc13_callback_stack": {"commit": "cd67452ceb018e18f5d2d3315c544af0d47f23ef", "executor_sha256": "ad86eb68ccd2bad67473e3f54f6191fb8654b2bfd33a937efbbcda94e3a49ec6"},
        "pinned_freeze": {"commit": SOURCE_COMMIT, "manifest_file_sha256": FREEZE_MANIFEST_SHA256, "schedule_file_sha256": FREEZE_SCHEDULE_FILE_SHA256, "schedule_sha256": FREEZE_SCHEDULE_SHA256, "study_contract_sha256": FREEZE_HASHES[FREEZE_PACKAGE / "study-contract.json"], "study_sha256": FREEZE_HASHES[FREEZE_PACKAGE / "study.py"]},
        "prohibitions": ["no runtime optimizer dependency", "no fallback or resend", "no confirmation, private path, target, selection, promotion, runtime, or general claim"],
        "study_id": STUDY_ID,
    }


def _validate_contract() -> None:
    expected = _expected_contract()
    if contract() != expected:
        raise ValueError("execution contract drifted")


def frozen_schedule(freeze_root: Path) -> dict[str, Any]:
    _verify_freeze_package()
    root = _safe(Path(freeze_root))
    _plain(root, directory=True)
    if {path.name for path in root.iterdir()} != {"manifest.json", "schedule.json"}:
        raise ValueError("frozen root inventory drifted")
    manifest_raw, schedule_raw = stable(root / "manifest.json"), stable(root / "schedule.json")
    if sha256(manifest_raw) != FREEZE_MANIFEST_SHA256 or sha256(schedule_raw) != FREEZE_SCHEDULE_FILE_SHA256:
        raise ValueError("frozen root file binding drifted")
    manifest, schedule = strict(manifest_raw, "freeze manifest"), strict(schedule_raw, "freeze schedule")
    if (manifest.get("study_id") != "hbq-human-alignment-optimizer-v7-desc16-referent-evidence-candidates-v1"
            or manifest.get("schedule_sha256") != FREEZE_SCHEDULE_SHA256
            or schedule.get("study_id") != manifest.get("study_id")
            or schedule.get("schedule_sha256") != FREEZE_SCHEDULE_SHA256):
        raise ValueError("frozen schedule identity drifted")
    geometry = {"candidates": 4, "development_groups": 7, "development_items": 13, "grok_cells": 52, "sol_cells": 0}
    cells, candidates = schedule.get("cells"), schedule.get("candidates")
    if (schedule.get("geometry") != geometry or not isinstance(cells, list) or not isinstance(candidates, list)
            or len(cells) != 52 or len(candidates) != 4
            or len({row.get("prompt_group_id") for row in cells if isinstance(row, Mapping)}) != 7
            or len({row.get("item_id") for row in cells if isinstance(row, Mapping)}) != 13):
        raise ValueError("52-cell frozen geometry drifted")
    if schedule.get("authority", {}).get("confirmation") != "unopened" or schedule.get("authority", {}).get("dspy_optuna_runtime") != "forbidden":
        raise ValueError("frozen authority drifted")
    ids = {row.get("cell_id") for row in cells if isinstance(row, Mapping)}
    payloads = {row.get("payload_sha256") for row in cells if isinstance(row, Mapping)}
    if len(ids) != 52 or None in ids or len(payloads) != 52 or None in payloads:
        raise ValueError("frozen cell identity drifted")
    source_payload_study_ids: set[str] = set()
    for row in cells:
        if not isinstance(row, Mapping):
            raise TypeError("frozen cell type drifted")
        try:
            payload = base64.b64decode(row["payload_base64"], validate=True)
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError("frozen payload encoding drifted") from error
        payload_value = strict(payload, "frozen payload")
        if sha256(payload) != row.get("payload_sha256") or not isinstance(payload_value.get("study_id"), str):
            raise ValueError("frozen payload binding drifted")
        source_payload_study_ids.add(payload_value["study_id"])
    if source_payload_study_ids != {"hbq-human-alignment-optimizer-v5-f20-broader-development-freeze-v1"}:
        raise ValueError("frozen payload source lineage drifted")
    value = dict(schedule)
    value["study_id"] = STUDY_ID
    value["kind"] = "frozen_desc16_referent_evidence_grok_development_execution_schedule"
    value["geometry"] = {**geometry, "confirmation_cells": 0}
    value["authority"] = {"provider_calls_made": 0, "process_launches": 0, "selection": "none", "promotion": "none", "runtime": "none", "sol": "out_of_scope", "confirmation": {"status": "unopened", "cells": 0}}
    value["frozen_schedule_sha256"] = FREEZE_SCHEDULE_SHA256
    value.pop("schedule_sha256", None)
    value["schedule_sha256"] = sha256(value)
    _validate_contract()
    return value


def _full_identity(path: Path, *, directory: bool) -> tuple[tuple[str, int, int, int, int | None], ...]:
    absolute = _safe(path)
    values: list[tuple[str, int, int, int, int | None]] = []
    for index, current in enumerate((absolute, *absolute.parents)):
        info = os.lstat(current)
        expected_directory = directory if index == 0 else True
        if stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)):
            raise ValueError("unsafe/reparsed prepared artifact ancestry")
        if stat.S_ISDIR(info.st_mode) != expected_directory:
            raise ValueError("prepared artifact type drifted")
        values.append((str(current), info.st_dev, info.st_ino, stat.S_IFMT(info.st_mode), None if expected_directory else info.st_size))
    return tuple(values)


def _capture_prepared(lifecycle: ModuleType, schedule: Mapping[str, Any], root: Path) -> dict[str, tuple[bytes, tuple[tuple[str, int, int, int, int | None], ...]]]:
    root = _safe(root)
    if lifecycle.inventory(root) != set(lifecycle.PREPARED):
        raise ValueError("prepared root is not pristine at runner entry")
    schedule_path = root.parent / "schedule.json"
    if stable(schedule_path) != canonical(schedule):
        raise ValueError("persisted schedule drifted before runner entry")
    captured = {name: (stable(root / name), _full_identity(root / name, directory=False)) for name in lifecycle.PREPARED}
    captured["schedule.json"] = (stable(schedule_path), _full_identity(schedule_path, directory=False))
    return captured


def _verify_callback_prepared(lifecycle: ModuleType, root: Path, captured: Mapping[str, tuple[bytes, tuple[tuple[str, int, int, int, int | None], ...]]]) -> None:
    root = _safe(root)
    allowed = set(lifecycle.PREPARED) | {"responses"}
    if {path.name for path in root.iterdir()} != allowed:
        raise ValueError("prepared root inventory drifted before launch")
    responses = root / "responses"
    _full_identity(responses, directory=True)
    staged = {path.name for path in responses.iterdir()}
    if staged not in (set(), {"batch-0001.attempt-0001.prompt.txt"}):
        raise ValueError("responses contain an ungoverned prelaunch artifact")
    if staged and stable(responses / "batch-0001.attempt-0001.prompt.txt") != captured["outbound-payload.json"][0]:
        raise ValueError("staged prompt differs from admitted payload")
    for name in lifecycle.PREPARED:
        raw, identity = captured[name]
        if stable(root / name) != raw or _full_identity(root / name, directory=False) != identity:
            raise ValueError("prepared artifact drifted before launch")
    schedule_raw, schedule_identity = captured["schedule.json"]
    schedule_path = root.parent / "schedule.json"
    if stable(schedule_path) != schedule_raw or _full_identity(schedule_path, directory=False) != schedule_identity:
        raise ValueError("persisted schedule drifted before launch")


def _guard_runner(runner: Callable[..., Mapping[str, Any]], lifecycle: ModuleType, schedule: Mapping[str, Any]) -> Callable[..., Mapping[str, Any]]:
    def guarded(**kwargs: Any) -> Mapping[str, Any]:
        root = Path(kwargs["output_dir"])
        captured = _capture_prepared(lifecycle, schedule, root)
        before_contact = kwargs["before_contact"]
        def guarded_before_contact() -> None:
            _verify_callback_prepared(lifecycle, root, captured)
            before_contact()
        copied = dict(kwargs)
        copied["before_contact"] = guarded_before_contact
        return runner(**copied)
    return guarded


def _surrogates(freeze_root: Path) -> dict[str, Path]:
    parent = _safe(Path(freeze_root)).parent
    return {
        "normalized_root": parent / ".desc16-exec-surrogate-normalized",
        "materialization_root": parent / ".desc16-exec-surrogate-materialization",
        "frozen_successor_path": parent / ".desc16-exec-surrogate-successor.json",
        "hanna_csv_path": parent / ".desc16-exec-surrogate-hanna.csv",
    }


@contextmanager
def _bound_source(*, freeze_root: Path) -> Iterator[tuple[ModuleType, ModuleType, dict[str, Any], ModuleType, ModuleType]]:
    schedule = frozen_schedule(Path(freeze_root))
    base = desc13_stack()
    v3 = base.v3_runtime()
    runtime = v3._runtime()
    lifecycle = runtime.lifecycle()
    source = lifecycle.live()
    original_schedule, original_study_id = lifecycle.schedule, lifecycle.STUDY_ID
    lifecycle.schedule = lambda **_kwargs: (source, schedule)
    lifecycle.STUDY_ID = STUDY_ID
    try:
        yield lifecycle, source, schedule, base, runtime
    finally:
        lifecycle.schedule, lifecycle.STUDY_ID = original_schedule, original_study_id


def _validated_route(base: ModuleType, runtime: ModuleType, queue_root: Path, route_provider: Callable[[Path], tuple[dict[str, Any], dict[str, Any]]] | None) -> Callable[[Path], tuple[dict[str, Any], dict[str, Any]]]:
    provider = base._validated_route(base.v3_runtime(), runtime, Path(queue_root), route_provider)
    def validated(root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
        route, evidence = provider(root)
        _validate_route_evidence(route, evidence)
        return route, evidence
    return validated


def _validate_route_evidence(route: Mapping[str, Any], evidence: Mapping[str, Any]) -> None:
    evidence_keys = {
        "cli_version_identity_sha256",
        "cost_evidence_hash",
        "grok_cli_version",
        "grok_command_identity_sha256",
        "registry_sha256",
        "route_name",
        "route_sha256",
        "subscription_receipt_hash",
    }
    hash_keys = evidence_keys - {"grok_cli_version", "route_name"}
    critical_route = {
        "adapter": "grok_exec",
        "provider": "xai_grok_build",
        "destination": "xai_grok_build_subscription",
        "model": "grok-4.6",
        "reported_model": "grok-4.6-build",
        "reasoning_effort": "high",
        "account_class": "subscription",
        "identity_evidence": "requested_only",
        "zero_charge": True,
        "armed": True,
        "health": "healthy",
        "trusted": True,
    }
    cost = route.get("cost_evidence")
    if (set(evidence) != evidence_keys
            or any(route.get(key) != expected for key, expected in critical_route.items())
            or any(type(route.get(key)) is not bool for key in ("zero_charge", "armed", "trusted"))
            or not isinstance(cost, Mapping)
            or set(cost) != {"allowance_state", "checked_at", "evidence_hash", "expires_at", "kind", "version"}
            or cost.get("allowance_state") != "available"
            or cost.get("kind") != "subscription_included"
            or type(cost.get("version")) is not int or cost["version"] != 1
            or not isinstance(cost.get("checked_at"), str) or not cost["checked_at"]
            or not isinstance(cost.get("expires_at"), str) or not cost["expires_at"]
            or not isinstance(route.get("cli_version_identity"), Mapping)
            or not isinstance(route.get("grok_command_identity"), Mapping)
            or evidence.get("route_name") != route.get("name")
            or evidence.get("route_sha256") != sha256(route)
            or evidence.get("cost_evidence_hash") != cost.get("evidence_hash")
            or evidence.get("subscription_receipt_hash") != route.get("subscription_receipt_hash")
            or evidence.get("grok_cli_version") != route.get("grok_cli_version")
            or evidence.get("cli_version_identity_sha256") != sha256(route.get("cli_version_identity"))
            or evidence.get("grok_command_identity_sha256") != sha256(route.get("grok_command_identity"))
            or any(not isinstance(evidence.get(key), str) or len(evidence[key]) != 64
                   or any(character not in "0123456789abcdef" for character in evidence[key])
                   for key in hash_keys)):
        raise ValueError("frozen route evidence drifted")


def prepare_all(*, output_root: Path, freeze_root: Path, queue_root: Path, authorization_acknowledgement_sha256: str, route_provider: Callable[[Path], tuple[dict[str, Any], dict[str, Any]]] | None = None) -> dict[str, Any]:
    with _bound_source(freeze_root=Path(freeze_root)) as (lifecycle, _source, schedule, base, runtime):
        result = lifecycle.prepare_all(output_root=Path(output_root), queue_root=Path(queue_root), authorization_acknowledgement_sha256=authorization_acknowledgement_sha256, route_provider=_validated_route(base, runtime, queue_root, route_provider), **_surrogates(Path(freeze_root)))
    if result.get("provider_calls_made") != 0 or result.get("process_launches") != 0 or len(result.get("prepared_cells", [])) != 52:
        raise ValueError("desc16 preparation lifecycle drifted")
    if stable(Path(output_root) / "schedule.json") != canonical(schedule):
        raise ValueError("persisted schedule differs from prepared schedule")
    return {"format_version": 1, "study_id": STUDY_ID, "kind": "prepared_52_desc16_referent_evidence_grok_cells", "prepared_cells": result["prepared_cells"], "logical_cells": 52, "effective_candidates": 4, "provider_calls_made": 0, "process_launches": 0}


def _execute_bound(*, lifecycle: ModuleType, runtime: ModuleType, schedule: Mapping[str, Any], output_root: Path, freeze_root: Path, queue_root: Path, authorization_acknowledgement_sha256: str, cell_id: str, route_provider: Callable[[Path], tuple[dict[str, Any], dict[str, Any]]], runner: Callable[..., Mapping[str, Any]] | None) -> dict[str, Any]:
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
        return lifecycle.execute_one(output_root=Path(output_root), queue_root=Path(queue_root), authorization_acknowledgement_sha256=authorization_acknowledgement_sha256, cell_id=cell_id, allow_remote=True, route_provider=route_provider, runner=_guard_runner(selected, lifecycle, schedule), **_surrogates(Path(freeze_root)))
    finally:
        runtime._release_global_slot(slot, record)


def execute_one(*, output_root: Path, freeze_root: Path, queue_root: Path, authorization_acknowledgement_sha256: str, cell_id: str, allow_remote: bool, route_provider: Callable[[Path], tuple[dict[str, Any], dict[str, Any]]] | None = None, runner: Callable[..., Mapping[str, Any]] | None = None) -> dict[str, Any]:
    if allow_remote is not True:
        raise ValueError("explicit allow_remote required")
    with _bound_source(freeze_root=Path(freeze_root)) as (lifecycle, _source, schedule, base, runtime):
        return _execute_bound(lifecycle=lifecycle, runtime=runtime, schedule=schedule, output_root=Path(output_root), freeze_root=Path(freeze_root), queue_root=Path(queue_root), authorization_acknowledgement_sha256=authorization_acknowledgement_sha256, cell_id=cell_id, route_provider=_validated_route(base, runtime, queue_root, route_provider), runner=runner)


async def execute_wave(*, output_root: Path, freeze_root: Path, queue_root: Path, authorization_acknowledgement_sha256: str, allow_remote: bool, route_provider: Callable[[Path], tuple[dict[str, Any], dict[str, Any]]] | None = None, runner: Callable[..., Mapping[str, Any]] | None = None) -> list[dict[str, Any]]:
    if allow_remote is not True:
        raise ValueError("explicit allow_remote required")
    with _bound_source(freeze_root=Path(freeze_root)) as (lifecycle, _source, schedule, base, runtime):
        frozen_route = _validated_route(base, runtime, queue_root, route_provider)
        route, evidence = frozen_route(Path(queue_root))
        route_once = lambda _ignored: (route, evidence)
        semaphore = asyncio.Semaphore(MAX_CONCURRENCY)
        async def run(cell_id: str) -> dict[str, Any]:
            async with semaphore:
                return await asyncio.to_thread(_execute_bound, lifecycle=lifecycle, runtime=runtime, schedule=schedule, output_root=Path(output_root), freeze_root=Path(freeze_root), queue_root=Path(queue_root), authorization_acknowledgement_sha256=authorization_acknowledgement_sha256, cell_id=cell_id, route_provider=route_once, runner=runner)
        completed = await asyncio.gather(*(run(row["cell_id"]) for row in schedule["cells"]), return_exceptions=True)
        failure = next((item for item in completed if isinstance(item, BaseException)), None)
        if failure is not None:
            raise failure
        result = completed
    if len(result) != 52:
        raise ValueError("desc16 execution wave cardinality drifted")
    return result


def finalize_collector(*, output_root: Path, freeze_root: Path, collector_output: Path, authorization_acknowledgement_sha256: str) -> dict[str, Any]:
    with _bound_source(freeze_root=Path(freeze_root)) as (lifecycle, source, schedule, _base, _runtime):
        collector = _safe(Path(collector_output))
        if collector.exists():
            raise ValueError("collector output must be fresh")
        expected_cells = {row["cell_id"] for row in schedule["cells"]}
        if {path.name for path in Path(output_root).iterdir()} != {"schedule.json", ".claims", *expected_cells} or stable(Path(output_root) / "schedule.json") != canonical(schedule):
            raise ValueError("output schedule inventory drifted")
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
                    or record.get("format_version") != 1 or record.get("kind") != "exclusive_execution_claim"
                    or record.get("cell_id") != cell_id
                    or record.get("study_id") != CLAIM_STUDY_ID
                    or type(record.get("acquired_at")) not in {int, float} or type(record.get("lease_seconds")) not in {int, float}
                    or record["lease_seconds"] <= 0):
                raise ValueError("execution claim binding drifted")
        cells: list[dict[str, Any]] = []
        frozen_route: Mapping[str, Any] | None = None
        frozen_evidence: Mapping[str, Any] | None = None
        for row in schedule["cells"]:
            root = Path(output_root) / row["cell_id"]
            stored = strict(stable(root / "prepared.json"), "prepared")
            acknowledgement = strict(stable(root / "authorization-acknowledgement.json"), "acknowledgement").get("acknowledgement_sha256")
            if acknowledgement != authorization_acknowledgement_sha256 or not isinstance(stored.get("route"), Mapping) or not isinstance(stored.get("route_evidence"), Mapping):
                raise ValueError("collector acknowledgement or route binding drifted")
            if frozen_route is None:
                frozen_route, frozen_evidence = stored["route"], stored["route_evidence"]
            if stored["route"] != frozen_route or stored["route_evidence"] != frozen_evidence:
                raise ValueError("collector route/evidence differs across cells")
            raw, prompt, schema = lifecycle.payload(row)
            request, response, identity, settings = lifecycle.admit(root, row, schedule, raw, prompt, schema, stored["route"], stored["route_evidence"], acknowledgement, source)
            cells.append({"cell_id": row["cell_id"], "payload_base64": row["payload_base64"], "payload_sha256": row["payload_sha256"], "native_request_base64": base64.b64encode(request).decode("ascii"), "native_request_sha256": sha256(request), "native_response_base64": base64.b64encode(response).decode("ascii"), "native_response_sha256": sha256(response), "identity": identity, "effective_settings": settings, "effective_settings_sha256": sha256(settings)})
        if frozen_route is None or frozen_evidence is None:
            raise ValueError("collector has no cells")
        lifecycle.validate_frozen_route(frozen_route, frozen_evidence)
        _validate_route_evidence(frozen_route, frozen_evidence)
        value = {"format_version": 1, "study_id": STUDY_ID, "kind": "complete_52_desc16_referent_evidence_grok_receipts_cardinality_unproven", "schedule_sha256": schedule["schedule_sha256"], "authorization_acknowledgement_sha256": authorization_acknowledgement_sha256, "route": frozen_route, "route_evidence": frozen_evidence, "cells": cells, "native_endpoint_contact_cardinality": "unproven", "provider_calls_made": None, "process_launches": 52}
        lifecycle.write_new(collector, canonical(value))
        return {"format_version": 1, "study_id": STUDY_ID, "kind": value["kind"], "collector_sha256": sha256(value), "cells": 52, "native_endpoint_contact_cardinality": "unproven", "provider_calls_made": None, "process_launches": 52}


def replay_collector(*, output_root: Path, freeze_root: Path, collector_path: Path) -> dict[str, Any]:
    with _bound_source(freeze_root=Path(freeze_root)) as (lifecycle, source, schedule, _base, _runtime):
        collector = strict(stable(Path(collector_path)), "collector")
        expected = {"format_version", "study_id", "kind", "schedule_sha256", "authorization_acknowledgement_sha256", "route", "route_evidence", "cells", "native_endpoint_contact_cardinality", "provider_calls_made", "process_launches"}
        if (set(collector) != expected or collector.get("study_id") != STUDY_ID or collector.get("kind") != "complete_52_desc16_referent_evidence_grok_receipts_cardinality_unproven"
                or collector.get("schedule_sha256") != schedule["schedule_sha256"] or collector.get("native_endpoint_contact_cardinality") != "unproven"
                or collector.get("provider_calls_made") is not None
                or type(collector.get("process_launches")) is not int or collector["process_launches"] != 52
                or not isinstance(collector.get("route"), Mapping) or not isinstance(collector.get("route_evidence"), Mapping)
                or not isinstance(collector.get("cells"), list) or len(collector["cells"]) != 52):
            raise ValueError("collector drifted")
        lifecycle.validate_frozen_route(collector["route"], collector["route_evidence"])
        _validate_route_evidence(collector["route"], collector["route_evidence"])
        index = {row["cell_id"]: row for row in schedule["cells"]}
        seen: set[tuple[str, str]] = set()
        for supplied in collector["cells"]:
            expected_cell = {"cell_id", "payload_base64", "payload_sha256", "native_request_base64", "native_request_sha256", "native_response_base64", "native_response_sha256", "identity", "effective_settings", "effective_settings_sha256"}
            if not isinstance(supplied, Mapping) or set(supplied) != expected_cell or supplied.get("cell_id") not in index:
                raise ValueError("collector cell drifted")
            row = index[supplied["cell_id"]]
            prepared = strict(stable(Path(output_root) / row["cell_id"] / "prepared.json"), "prepared")
            if prepared.get("route") != collector["route"] or prepared.get("route_evidence") != collector["route_evidence"]:
                raise ValueError("collector route provenance differs from persisted preparation")
            acknowledgement = strict(stable(Path(output_root) / row["cell_id"] / "authorization-acknowledgement.json"), "acknowledgement").get("acknowledgement_sha256")
            if acknowledgement != collector["authorization_acknowledgement_sha256"]:
                raise ValueError("collector acknowledgement differs from persisted preparation")
            request = base64.b64decode(supplied.get("native_request_base64", ""), validate=True)
            response = base64.b64decode(supplied.get("native_response_base64", ""), validate=True)
            if supplied.get("payload_base64") != row["payload_base64"] or supplied.get("payload_sha256") != row["payload_sha256"] or supplied.get("native_request_sha256") != sha256(request) or supplied.get("native_response_sha256") != sha256(response):
                raise ValueError("collector payload binding drifted")
            identity = supplied.get("identity")
            settings = supplied.get("effective_settings")
            raw, prompt, schema = lifecycle.payload(row)
            persisted = lifecycle.admit(Path(output_root) / row["cell_id"], row, schedule, raw, prompt, schema, prepared["route"], prepared["route_evidence"], acknowledgement, source)
            if (request, response, identity, settings) != persisted:
                raise ValueError("collector native receipt differs from persisted execution")
            checked = source._validate_runner_result({"native_request_bytes": request, "native_response_bytes": response, "identity": identity, "effective_settings": settings}, collector["route"], base64.b64decode(row["payload_base64"], validate=True))
            if checked[0] != source.adapter_canonical({"prompt": base64.b64decode(row["payload_base64"], validate=True).decode("utf-8")}) or supplied.get("effective_settings_sha256") != sha256(settings):
                raise ValueError("collector native binding drifted")
            key = (identity.get("request_id"), identity.get("session_id")) if isinstance(identity, Mapping) else ("", "")
            if not all(key) or key in seen:
                raise ValueError("duplicate or invalid native identity")
            seen.add(key)
        if set(index) != {row["cell_id"] for row in collector["cells"]}:
            raise ValueError("partial collector")
        return {"format_version": 1, "study_id": STUDY_ID, "collector_sha256": sha256(collector), "cells": 52, "provider_calls_made": None, "process_launches": 52, "equal_group_projection_ready": True, "native_endpoint_contact_cardinality": "unproven", "authority": {"selection": "none", "promotion": "none", "runtime": "none", "confirmation": {"status": "unopened", "cells": 0}}}


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
