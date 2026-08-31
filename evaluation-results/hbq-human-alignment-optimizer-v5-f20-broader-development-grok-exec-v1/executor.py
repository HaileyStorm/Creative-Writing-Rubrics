#!/usr/bin/env python3
"""One-shot, bounded Grok execution for the frozen 35-cell broader HANNA development wave."""
from __future__ import annotations

import argparse
import asyncio
import base64
import hashlib
import importlib.util
import json
import os
import re
import secrets
import stat
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from types import ModuleType
from typing import Any, Callable, Mapping


HERE = Path(__file__).resolve().parent
STUDY_ID = "hbq-human-alignment-optimizer-v5-f20-broader-development-grok-exec-v1"
FREEZE_COMMIT = "436da1ef3f8cf239203ac6a80afe8f72708c0415"
FREEZE = HERE.parent / "hbq-human-alignment-optimizer-v5-f20-broader-development-freeze-v1" / "study.py"
FREEZE_HASHES = {
    FREEZE: "507e3c0bec1af6d0acef6e806cf6874a2633e892c9bbf567728f436af30f84bf",
    FREEZE.parent / "study-contract.json": "3b31c9b0d5ec4c71d6b562045dcd52b2646380cb318d72b83d2119e760543a77",
    FREEZE.parent / "README.md": "5f8956e96df28ddfe37533e631c163f1cdbf711e820e05e2607618975bf0e75f",
    HERE.parents[1] / "tests" / "test_hbq_human_alignment_optimizer_v5_f20_broader_development_freeze_v1.py": "5c58ac8eb15227703a090c4f2bd3aedd547b040fd4cb3ea66788018a78419656",
}
SCHEDULE_SHA256 = "bdb40b0f24f07ea938d57951768101a93ff62575919075abcd7bb9534e12c52c"
LIFECYCLE = HERE.parent / "hbq-human-alignment-optimizer-v5-f20-nextwave-grok-score-exec-v1" / "executor.py"
LIFECYCLE_SHA256 = "c1641089073c07d5906d31685101dedbd5cdc936568baeb039a612f85b0f7539"
MAX_CONCURRENCY = 10
LEASE_SECONDS = 900
SLOT_WAIT_SECONDS = 60
SLOT_RELEASE_ATTEMPTS = 40
SLOT_RETRY_SECONDS = 0.01
CLAIMS = ".claims"


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def sha256(value: bytes | Any) -> str:
    return hashlib.sha256(value if isinstance(value, bytes) else canonical(value)).hexdigest()


def _plain(path: Path, directory: bool | None = None) -> None:
    info = os.lstat(path)
    if stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)):
        raise ValueError("unsafe/reparsed path")
    if directory is not None and stat.S_ISDIR(info.st_mode) != directory:
        raise ValueError("unexpected path type")


def stable(path: Path) -> bytes:
    _plain(path, directory=False)
    before = os.lstat(path)
    with path.open("rb") as handle:
        opened = os.fstat(handle.fileno())
        raw = handle.read()
        after = os.fstat(handle.fileno())
    if (before.st_dev, before.st_ino, before.st_size) != (opened.st_dev, opened.st_ino, opened.st_size) or (opened.st_dev, opened.st_ino, opened.st_size) != (after.st_dev, after.st_ino, after.st_size):
        raise ValueError("stable read drift")
    return raw


def strict(raw: bytes, label: str) -> dict[str, Any]:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in items:
            if key in value:
                raise ValueError("duplicate JSON key")
            value[key] = item
        return value
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs, parse_constant=lambda token: (_ for _ in ()).throw(ValueError(token)))
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise ValueError(f"invalid {label}") from error
    if not isinstance(value, dict) or canonical(value) != raw:
        raise ValueError(f"noncanonical {label}")
    return value


def json_object(raw: bytes, label: str) -> dict[str, Any]:
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"invalid {label}") from error
    if not isinstance(value, dict):
        raise ValueError(f"invalid {label}")
    return value


def write_new(path: Path, raw: bytes) -> None:
    if path.exists() or path.is_symlink():
        raise ValueError("refuses overwrite")
    _plain(path.parent, directory=True)
    with path.open("xb") as handle:
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())


def _load(path: Path, digest: str, name: str) -> ModuleType:
    raw = stable(path)
    if sha256(raw) != digest:
        raise ValueError("pinned dependency drifted")
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ValueError("cannot load pinned dependency")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(name, None)
    if stable(path) != raw:
        raise ValueError("pinned dependency changed during load")
    return module


def freeze_module() -> ModuleType:
    for path, digest in FREEZE_HASHES.items():
        if sha256(stable(path)) != digest:
            raise ValueError("pinned freeze dependency drifted")
    return _load(FREEZE, FREEZE_HASHES[FREEZE], "_broader_grok_freeze")


def lifecycle() -> ModuleType:
    return _load(LIFECYCLE, LIFECYCLE_SHA256, "_broader_grok_lifecycle")


def admit_frozen_root(frozen_root: Path) -> dict[str, Any]:
    module = freeze_module()
    root = Path(frozen_root)
    schedule = module.validate_frozen_root(root)
    if schedule.get("schedule_sha256") != SCHEDULE_SHA256 or schedule.get("geometry") != {"candidates": 5, "development_groups": 7, "grok_cells": 35, "sol_cells": 0, "confirmation_cells": 0}:
        raise ValueError("frozen broader schedule drifted")
    if schedule.get("authority", {}).get("confirmation") != {"status": "unopened", "cells": 0}:
        raise ValueError("confirmation surface is forbidden")
    return schedule


@contextmanager
def bound_lifecycle(frozen_root: Path):
    schedule = admit_frozen_root(frozen_root)
    module = lifecycle()
    source = module.live()
    original_schedule, original_study_id = module.schedule, module.STUDY_ID
    module.schedule = lambda **_ignored: (source, schedule)
    module.STUDY_ID = STUDY_ID
    try:
        yield module, source, schedule
    finally:
        module.schedule, module.STUDY_ID = original_schedule, original_study_id


def _surrogate_paths(frozen_root: Path) -> dict[str, Path]:
    parent = Path(frozen_root).resolve().parent
    return {
        "normalized_root": Path(frozen_root),
        "materialization_root": parent / "_broader-exec-surrogate-materialization",
        "frozen_successor_path": parent / "_broader-exec-surrogate-successor.json",
        "hanna_csv_path": parent / "_broader-exec-surrogate-data.csv",
    }


def _claims_root(output_root: Path) -> Path:
    root = Path(output_root)
    _plain(root, directory=True)
    claims = root / CLAIMS
    if not claims.exists():
        try:
            claims.mkdir()
        except FileExistsError:
            pass
    _plain(claims, directory=True)
    return claims


def _safe_existing(path: Path, directory: bool) -> Path:
    absolute = Path(os.path.abspath(path))
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current /= part
        if current.exists():
            _plain(current, directory=directory if current == absolute else True)
    if not absolute.exists():
        raise ValueError("required safe path is absent")
    return absolute


def _slot_root(output_root: Path) -> tuple[Path, str]:
    root = _safe_existing(Path(output_root), directory=True)
    parent = _safe_existing(root.parent, directory=True)
    locks = parent / ("." + root.name + ".broader-grok-slots")
    try:
        locks.mkdir()
    except FileExistsError:
        pass
    _safe_existing(locks, directory=True)
    return locks, sha256(str(root).encode("utf-8"))


def _slot_record(*, cell_id: str, slot: int, output_root_sha256: str) -> dict[str, Any]:
    return {"format_version": 1, "study_id": STUDY_ID, "kind": "global_broader_grok_execution_slot", "cell_id": cell_id, "slot": slot, "output_root_sha256": output_root_sha256, "token": secrets.token_hex(16)}


def _validate_slot(raw: bytes, *, slot: int, output_root_sha256: str) -> dict[str, Any]:
    value = strict(raw, "global execution slot")
    if set(value) != {"format_version", "study_id", "kind", "cell_id", "slot", "output_root_sha256", "token"} or value.get("format_version") != 1 or value.get("study_id") != STUDY_ID or value.get("kind") != "global_broader_grok_execution_slot" or value.get("slot") != slot or value.get("output_root_sha256") != output_root_sha256 or not isinstance(value.get("cell_id"), str) or not value["cell_id"] or not re.fullmatch(r"[0-9a-f]{32}", value.get("token", "")):
        raise ValueError("foreign or malformed global execution slot")
    return value


def _write_slot(path: Path, record: Mapping[str, Any]) -> None:
    _plain(path.parent, directory=True)
    with path.open("xb") as handle:
        handle.write(canonical(dict(record)))
        handle.flush()
        os.fsync(handle.fileno())


def _sharing_or_lock(error: OSError) -> bool:
    return getattr(error, "winerror", None) in {32, 33}


def _slot_fingerprint(path: Path) -> tuple[int, int, int, int]:
    info = os.stat(path)
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns


def _acquire_global_slot(output_root: Path, cell_id: str) -> tuple[Path, dict[str, Any]]:
    locks, root_hash = _slot_root(output_root)
    deadline = time.monotonic() + SLOT_WAIT_SECONDS
    observed: dict[Path, tuple[int, int, int, int]] = {}
    while time.monotonic() < deadline:
        for slot in range(MAX_CONCURRENCY):
            path = locks / f"slot-{slot}.lock"
            record = _slot_record(cell_id=cell_id, slot=slot, output_root_sha256=root_hash)
            try:
                _write_slot(path, record)
                return path, record
            except FileExistsError:
                try:
                    _plain(path, directory=False)
                    fingerprint = _slot_fingerprint(path)
                    if observed.get(path) != fingerprint:
                        _validate_slot(stable(path), slot=slot, output_root_sha256=root_hash)
                        observed[path] = fingerprint
                except FileNotFoundError:
                    observed.pop(path, None)
                except OSError as error:
                    if not _sharing_or_lock(error):
                        raise
        time.sleep(0.01)
    raise TimeoutError("global Grok ten-slot semaphore did not become available")


def _release_global_slot(path: Path | None, record: Mapping[str, Any] | None) -> None:
    if path is None or record is None:
        return
    expected = canonical(dict(record))
    for attempt in range(SLOT_RELEASE_ATTEMPTS):
        try:
            if not path.exists():
                raise ValueError("global execution slot disappeared")
            _plain(path, directory=False)
            if stable(path) != expected:
                raise ValueError("global execution slot changed before release")
            path.unlink()
            return
        except OSError as error:
            if not _sharing_or_lock(error) or attempt + 1 == SLOT_RELEASE_ATTEMPTS:
                raise
            time.sleep(SLOT_RETRY_SECONDS)
    raise AssertionError("unreachable slot-release retry exhaustion")


def _claim(output_root: Path, cell_id: str) -> str:
    root = Path(output_root) / cell_id
    _plain(root, directory=True)
    terminal = root / "result.json"
    if terminal.exists():
        _plain(terminal, directory=False)
        return "terminal"
    claims = _claims_root(output_root)
    claim = claims / cell_id
    try:
        os.mkdir(claim)
    except FileExistsError:
        _plain(claim, directory=True)
        claim_file = claim / "claim.json"
        record = strict(stable(claim_file), "claim")
        acquired = record.get("acquired_at")
        if not isinstance(acquired, (int, float)):
            raise ValueError("claim timestamp drifted")
        if time.time() - acquired <= LEASE_SECONDS:
            return "claimed"
        result = {"format_version": 1, "study_id": STUDY_ID, "kind": "reconcile_required_after_expired_lease", "cell_id": cell_id, "provider_calls_made": 0, "process_launches": 0, "retry_policy": "fresh_output_root_required_no_in_place_resend"}
        write_new(terminal, canonical(result))
        return "expired"
    record = {"format_version": 1, "study_id": STUDY_ID, "kind": "exclusive_execution_claim", "cell_id": cell_id, "acquired_at": time.time(), "lease_seconds": LEASE_SECONDS}
    write_new(claim / "claim.json", canonical(record))
    return "claimed_now"


def prepare_all(*, output_root: Path, frozen_root: Path, queue_root: Path, authorization_acknowledgement_sha256: str, route_provider: Callable[[Path], tuple[dict[str, Any], dict[str, Any]]] | None = None) -> dict[str, Any]:
    with bound_lifecycle(frozen_root) as (module, _source, schedule):
        result = module.prepare_all(output_root=Path(output_root), queue_root=Path(queue_root), authorization_acknowledgement_sha256=authorization_acknowledgement_sha256, route_provider=route_provider, **_surrogate_paths(frozen_root))
    if result.get("provider_calls_made") != 0 or result.get("process_launches") != 0 or len(result.get("prepared_cells", [])) != 35:
        raise ValueError("preparation lifecycle drifted")
    return {"format_version": 1, "study_id": STUDY_ID, "kind": "prepared_35_broader_grok_development_cells", "prepared_cells": result["prepared_cells"], "logical_cells": 35, "effective_candidates": 5, "provider_calls_made": 0, "process_launches": 0}


def execute_one(*, output_root: Path, frozen_root: Path, queue_root: Path, authorization_acknowledgement_sha256: str, cell_id: str, allow_remote: bool, route_provider: Callable[[Path], tuple[dict[str, Any], dict[str, Any]]] | None = None, runner: Callable[..., Mapping[str, Any]] | None = None) -> dict[str, Any]:
    if allow_remote is not True:
        raise ValueError("explicit allow_remote required")
    schedule = admit_frozen_root(frozen_root)
    if "confirmation" in cell_id:
        raise ValueError("confirmation cells are forbidden")
    if cell_id not in {row["cell_id"] for row in schedule["cells"]}:
        raise ValueError("unknown cell")
    slot: Path | None = None
    record: dict[str, Any] | None = None
    try:
        slot, record = _acquire_global_slot(Path(output_root), cell_id)
        state = _claim(Path(output_root), cell_id)
        if state != "claimed_now":
            return {"format_version": 1, "study_id": STUDY_ID, "cell_id": cell_id, "state": "reconcile_required" if state == "expired" else state, "provider_calls_made": 0, "process_launches": 0}
        with bound_lifecycle(frozen_root) as (module, _source, _schedule):
            result = module.execute_one(output_root=Path(output_root), queue_root=Path(queue_root), authorization_acknowledgement_sha256=authorization_acknowledgement_sha256, cell_id=cell_id, allow_remote=True, route_provider=route_provider, runner=runner, **_surrogate_paths(frozen_root))
        return {"format_version": 1, "study_id": STUDY_ID, **result}
    finally:
        _release_global_slot(slot, record)


async def execute_wave(*, output_root: Path, frozen_root: Path, queue_root: Path, authorization_acknowledgement_sha256: str, allow_remote: bool, route_provider: Callable[[Path], tuple[dict[str, Any], dict[str, Any]]] | None = None, runner: Callable[..., Mapping[str, Any]] | None = None) -> list[dict[str, Any]]:
    if allow_remote is not True:
        raise ValueError("explicit allow_remote required")
    schedule = admit_frozen_root(frozen_root)
    semaphore = asyncio.Semaphore(MAX_CONCURRENCY)
    async def run(row: Mapping[str, Any]) -> dict[str, Any]:
        async with semaphore:
            return await asyncio.to_thread(execute_one, output_root=output_root, frozen_root=frozen_root, queue_root=queue_root, authorization_acknowledgement_sha256=authorization_acknowledgement_sha256, cell_id=row["cell_id"], allow_remote=True, route_provider=route_provider, runner=runner)
    return await asyncio.gather(*(run(row) for row in schedule["cells"]))


def _output_schedule(output_root: Path, frozen_root: Path) -> dict[str, Any]:
    schedule = admit_frozen_root(frozen_root)
    root = Path(output_root)
    _plain(root, directory=True)
    expected = {"schedule.json", CLAIMS, *(row["cell_id"] for row in schedule["cells"])}
    if {path.name for path in root.iterdir()} != expected or stable(root / "schedule.json") != canonical(schedule):
        raise ValueError("proof-root inventory or persisted schedule drifted")
    claims = root / CLAIMS
    if {path.name for path in claims.iterdir()} != {row["cell_id"] for row in schedule["cells"]}:
        raise ValueError("claim inventory drifted")
    for row in schedule["cells"]:
        claim = claims / row["cell_id"]
        _plain(claim, directory=True)
        if set(path.name for path in claim.iterdir()) != {"claim.json"}:
            raise ValueError("claim artifact drifted")
        strict(stable(claim / "claim.json"), "claim")
    return schedule


def finalize_collector(*, output_root: Path, frozen_root: Path, collector_output: Path, authorization_acknowledgement_sha256: str) -> dict[str, Any]:
    collector = Path(collector_output)
    if collector.exists() or collector.is_symlink():
        raise ValueError("collector output must be fresh")
    schedule = _output_schedule(output_root, frozen_root)
    cells: list[dict[str, Any]] = []
    frozen_route = frozen_evidence = None
    with bound_lifecycle(frozen_root) as (module, source, _schedule):
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
            raw, prompt, schema = module.payload(row)
            request, response, identity, settings = module.admit(root, row, schedule, raw, prompt, schema, stored["route"], stored["route_evidence"], acknowledgement, source)
            cells.append({"cell_id": row["cell_id"], "payload_base64": row["payload_base64"], "payload_sha256": row["payload_sha256"], "native_request_base64": base64.b64encode(request).decode("ascii"), "native_request_sha256": sha256(request), "native_response_base64": base64.b64encode(response).decode("ascii"), "native_response_sha256": sha256(response), "identity": identity, "effective_settings": settings, "effective_settings_sha256": sha256(settings)})
        module.validate_frozen_route(frozen_route, frozen_evidence)
    value = {"format_version": 1, "study_id": STUDY_ID, "kind": "complete_35_broader_grok_receipts_cardinality_unproven", "schedule_sha256": schedule["schedule_sha256"], "authorization_acknowledgement_sha256": authorization_acknowledgement_sha256, "route": frozen_route, "route_evidence": frozen_evidence, "cells": cells, "native_endpoint_contact_cardinality": "unproven", "provider_calls_made": 0, "process_launches": 0}
    write_new(collector, canonical(value))
    return {"format_version": 1, "study_id": STUDY_ID, "kind": value["kind"], "collector_sha256": sha256(value), "cells": 35, "provider_calls_made": 0, "process_launches": 0}


def replay_collector(*, output_root: Path, frozen_root: Path, collector_path: Path) -> dict[str, Any]:
    schedule = _output_schedule(output_root, frozen_root)
    raw = stable(Path(collector_path))
    value = strict(raw, "collector")
    expected = {"format_version", "study_id", "kind", "schedule_sha256", "authorization_acknowledgement_sha256", "route", "route_evidence", "cells", "native_endpoint_contact_cardinality", "provider_calls_made", "process_launches"}
    if set(value) != expected or value.get("study_id") != STUDY_ID or value.get("kind") != "complete_35_broader_grok_receipts_cardinality_unproven" or value.get("schedule_sha256") != schedule["schedule_sha256"] or not re.fullmatch(r"[0-9a-f]{64}", value.get("authorization_acknowledgement_sha256", "")) or value.get("native_endpoint_contact_cardinality") != "unproven" or value.get("provider_calls_made") != 0 or value.get("process_launches") != 0 or not isinstance(value.get("cells"), list) or len(value["cells"]) != 35:
        raise ValueError("collector drifted")
    index = {row["cell_id"]: row for row in schedule["cells"]}
    seen: set[tuple[str, str]] = set()
    with bound_lifecycle(frozen_root) as (module, source, _schedule):
        module.validate_frozen_route(value["route"], value["route_evidence"])
        for supplied in value["cells"]:
            keys = {"cell_id", "payload_base64", "payload_sha256", "native_request_base64", "native_request_sha256", "native_response_base64", "native_response_sha256", "identity", "effective_settings", "effective_settings_sha256"}
            if not isinstance(supplied, Mapping) or set(supplied) != keys:
                raise ValueError("collector cell fields drifted")
            row = index.get(supplied.get("cell_id"))
            request = base64.b64decode(supplied.get("native_request_base64", ""), validate=True)
            response = base64.b64decode(supplied.get("native_response_base64", ""), validate=True)
            if row is None or supplied.get("payload_base64") != row["payload_base64"] or supplied.get("payload_sha256") != row["payload_sha256"] or supplied.get("native_request_sha256") != sha256(request) or supplied.get("native_response_sha256") != sha256(response) or supplied.get("effective_settings_sha256") != sha256(supplied.get("effective_settings")):
                raise ValueError("collector payload/response/settings drifted")
            identity = supplied.get("identity")
            if not isinstance(identity, Mapping):
                raise ValueError("invalid native identity")
            contact = (identity.get("request_id"), identity.get("session_id"))
            if not all(isinstance(item, str) and item for item in contact) or contact in seen:
                raise ValueError("duplicate native identity")
            root = Path(output_root) / row["cell_id"]
            stored = strict(stable(root / "prepared.json"), "prepared")
            acknowledgement = strict(stable(root / "authorization-acknowledgement.json"), "acknowledgement").get("acknowledgement_sha256")
            if acknowledgement != value["authorization_acknowledgement_sha256"] or stored.get("route") != value["route"] or stored.get("route_evidence") != value["route_evidence"]:
                raise ValueError("collector route/evidence differs from persisted execution proof")
            payload, prompt, schema = module.payload(row)
            persisted = module.admit(root, row, schedule, payload, prompt, schema, stored["route"], stored["route_evidence"], acknowledgement, source)
            if (request, response, dict(identity), supplied["effective_settings"]) != persisted:
                raise ValueError("collector differs from persisted execution receipt")
            verified = source._validate_runner_result({"native_request_bytes": request, "native_response_bytes": response, "identity": identity, "effective_settings": supplied["effective_settings"]}, value["route"], payload)
            response_object = json_object(response, "native response")
            if verified != persisted or response_object.get("requestId") != contact[0] or response_object.get("sessionId") != contact[1]:
                raise ValueError("independently reconstructed receipt drifted")
            seen.add(contact)
    if set(index) != {item["cell_id"] for item in value["cells"]}:
        raise ValueError("partial collector")
    return {"format_version": 1, "study_id": STUDY_ID, "kind": "durable_35_cell_receipt_replay", "collector_sha256": sha256(raw), "cells": 35, "equal_group_projection_ready": True, "authority": {"selection": "none", "promotion": "none", "runtime": "none", "sol": "out_of_scope", "confirmation": {"status": "unopened", "cells": 0}}}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    for name in ("prepare-all", "execute-one", "execute-wave", "finalize-collector", "replay-collector"):
        modes.add_argument("--" + name, action="store_true")
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--frozen-root", type=Path, required=True)
    parser.add_argument("--queue-root", type=Path)
    parser.add_argument("--collector-output", type=Path)
    parser.add_argument("--collector-path", type=Path)
    parser.add_argument("--authorization-acknowledgement-sha256")
    parser.add_argument("--cell-id")
    parser.add_argument("--allow-remote", action="store_true")
    args = parser.parse_args(argv)
    if args.prepare_all:
        if args.allow_remote or not args.queue_root or not args.authorization_acknowledgement_sha256:
            parser.error("prepare requires queue/ack and forbids remote")
        result = prepare_all(output_root=args.output_root, frozen_root=args.frozen_root, queue_root=args.queue_root, authorization_acknowledgement_sha256=args.authorization_acknowledgement_sha256)
    elif args.execute_one:
        if not args.allow_remote or not args.queue_root or not args.authorization_acknowledgement_sha256 or not args.cell_id:
            parser.error("execute requires queue/ack/cell and explicit remote")
        result = execute_one(output_root=args.output_root, frozen_root=args.frozen_root, queue_root=args.queue_root, authorization_acknowledgement_sha256=args.authorization_acknowledgement_sha256, cell_id=args.cell_id, allow_remote=True)
    elif args.execute_wave:
        if not args.allow_remote or not args.queue_root or not args.authorization_acknowledgement_sha256:
            parser.error("wave requires queue/ack and explicit remote")
        result = asyncio.run(execute_wave(output_root=args.output_root, frozen_root=args.frozen_root, queue_root=args.queue_root, authorization_acknowledgement_sha256=args.authorization_acknowledgement_sha256, allow_remote=True))
    elif args.finalize_collector:
        if args.allow_remote or not args.collector_output or not args.authorization_acknowledgement_sha256:
            parser.error("finalize requires collector/ack and forbids remote")
        result = finalize_collector(output_root=args.output_root, frozen_root=args.frozen_root, collector_output=args.collector_output, authorization_acknowledgement_sha256=args.authorization_acknowledgement_sha256)
    else:
        if args.allow_remote or not args.collector_path:
            parser.error("replay requires collector and forbids remote")
        result = replay_collector(output_root=args.output_root, frozen_root=args.frozen_root, collector_path=args.collector_path)
    print(canonical(result).decode("utf-8"), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
