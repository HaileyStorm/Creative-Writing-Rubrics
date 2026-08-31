#!/usr/bin/env python3
"""One-shot Grok execution for the sealed 64-cell public Fresh96 validation schedule."""
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
import sys
from collections.abc import Callable, Mapping
from contextlib import contextmanager
from pathlib import Path
from types import ModuleType
from typing import Any

HERE = Path(__file__).resolve().parent
STUDY_ID = "hbq-human-alignment-hanna96-validation-grok-exec-v1"
PREDECESSOR = HERE.parent / "hbq-human-alignment-optimizer-v5-f20-confirmation-grok-exec-v1"
PREDECESSOR_HASHES = {
    PREDECESSOR / "executor.py": "5e5cf531a4f8a224164f032d5bb68e11c919d2f305cf7fdd5ba0c08f594b323a",
}
FREEZE = HERE.parent / "hbq-human-alignment-hanna96-validation-freeze-v1" / "study.py"
FREEZE_SHA256 = "d8b99c651cfbc0c04207101a6ad15373168a5ffad3711f7d17fb589e8a13542e"
SCHEDULE_SHA256 = "639c34bb1d07266759280249b6b74a51c05d51f60ed27eb3aed0b2ea6c3bfee2"
MAX_CONCURRENCY = 10
ENDPOINT = "grok-4.6"
ANALYSIS_STUDY_ID = "hbq-human-alignment-hanna96-validation-analysis-v1"
DIMENSIONS = ("Relevance", "Coherence", "Empathy", "Surprise", "Engagement", "Complexity")


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
        opened, raw, after = os.fstat(handle.fileno()), handle.read(), os.fstat(handle.fileno())
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


def _runtime() -> ModuleType:
    for path, digest in PREDECESSOR_HASHES.items():
        if sha256(stable(path)) != digest:
            raise ValueError("pinned confirmed Grok lifecycle drifted")
    return _load(PREDECESSOR / "executor.py", PREDECESSOR_HASHES[PREDECESSOR / "executor.py"], "_hanna96_validation_grok_predecessor")._runtime()


def freeze_module() -> ModuleType:
    return _load(FREEZE, FREEZE_SHA256, "_hanna96_validation_freeze")


def _payload_ok(row: Mapping[str, Any]) -> None:
    required = {"cell_id", "candidate_id", "item_id", "prompt_group_id", "payload_base64", "payload_sha256", "source_binding_sha256", "target_sha256", "target"}
    if not required <= set(row) or not all(isinstance(row[key], str) and row[key] for key in required - {"target"}):
        raise ValueError("Fresh96 cell shape drifted")
    try:
        payload = base64.b64decode(row["payload_base64"], validate=True)
    except (TypeError, ValueError) as error:
        raise ValueError("Fresh96 payload is not base64") from error
    if sha256(payload) != row["payload_sha256"] or sha256(row["target"]) != row["target_sha256"] or not isinstance(row["target"], Mapping):
        raise ValueError("Fresh96 cell payload/target drifted")


def _scores_from_response(response: bytes) -> dict[str, float]:
    envelope = strict(response, "native response")
    output = envelope.get("structuredOutput")
    if not isinstance(output, Mapping) or set(output) != {"scores", "evidence", "coverage"}:
        raise ValueError("native structured output drifted")
    scores = output.get("scores")
    if not isinstance(scores, Mapping) or set(scores) != set(DIMENSIONS):
        raise ValueError("native scores drifted")
    if any(type(scores[dimension]) not in (int, float) or not math.isfinite(scores[dimension]) or not 0 <= scores[dimension] <= 5 for dimension in DIMENSIONS):
        raise ValueError("native scores are outside the Fresh96 scale")
    return {dimension: float(scores[dimension]) for dimension in DIMENSIONS}


def admit_frozen_root(frozen_root: Path) -> dict[str, Any]:
    schedule = freeze_module().validate_frozen_root(Path(frozen_root))
    if not isinstance(schedule, dict) or schedule.get("schedule_sha256") != SCHEDULE_SHA256 or schedule.get("study_id") != "hbq-human-alignment-hanna96-validation-freeze-v1":
        raise ValueError("frozen Fresh96 schedule drifted")
    if schedule.get("geometry") != {"groups": 16, "items": 32, "candidates": 2, "endpoint_neutral_logical_cells": 64}:
        raise ValueError("Fresh96 geometry drifted")
    cells = schedule.get("cells")
    if not isinstance(cells, list) or len(cells) != 64 or len({row.get("cell_id") for row in cells if isinstance(row, Mapping)}) != 64:
        raise ValueError("Fresh96 cell identity geometry drifted")
    for row in cells:
        if not isinstance(row, Mapping):
            raise TypeError("Fresh96 cell is invalid")
        _payload_ok(row)
    candidates, items, groups = {row["candidate_id"] for row in cells}, {row["item_id"] for row in cells}, {row["prompt_group_id"] for row in cells}
    if len(candidates) != 2 or len(items) != 32 or len(groups) != 16 or {(row["candidate_id"], row["item_id"]) for row in cells} != {(candidate, item) for candidate in candidates for item in items}:
        raise ValueError("Fresh96 candidate/item/group bindings drifted")
    if any(len({row["prompt_group_id"] for row in cells if row["item_id"] == item}) != 1 or len({canonical(row["target"]) for row in cells if row["item_id"] == item}) != 1 for item in items):
        raise ValueError("Fresh96 item pair bindings drifted")
    if schedule.get("authority") != {"endpoint_pooling": "forbidden", "generalization": "none", "process_launches": 0, "promotion": "none", "provider_calls_made": 0, "runtime": "none", "selection": "none"}:
        raise ValueError("Fresh96 authority drifted")
    return schedule


@contextmanager
def bound_lifecycle(frozen_root: Path):
    schedule, runtime = admit_frozen_root(frozen_root), _runtime()
    source = runtime.lifecycle()
    original_schedule, original_study_id = source.schedule, source.STUDY_ID
    source.schedule = lambda **_ignored: (source.live(), schedule)
    source.STUDY_ID = STUDY_ID
    try:
        yield source, source.live(), schedule, runtime
    finally:
        source.schedule, source.STUDY_ID = original_schedule, original_study_id


def _surrogates(frozen_root: Path) -> dict[str, Path]:
    parent = Path(frozen_root).resolve().parent
    return {"normalized_root": Path(frozen_root), "materialization_root": parent / "_hanna96-validation-grok-surrogate-materialization", "frozen_successor_path": parent / "_hanna96-validation-grok-surrogate-successor.json", "hanna_csv_path": parent / "_hanna96-validation-grok-surrogate-data.csv"}


def _frozen_route(source: ModuleType, queue_root: Path, route_provider: Callable[[Path], tuple[dict[str, Any], dict[str, Any]]] | None) -> Callable[[Path], tuple[dict[str, Any], dict[str, Any]]]:
    route, evidence = source._route(Path(queue_root), route_provider)
    route_raw, evidence_raw = canonical(route), canonical(evidence)
    return lambda _queue_root: (json.loads(route_raw), json.loads(evidence_raw))


def prepare_all(*, output_root: Path, frozen_root: Path, queue_root: Path, authorization_acknowledgement_sha256: str, route_provider: Callable[[Path], tuple[dict[str, Any], dict[str, Any]]] | None = None) -> dict[str, Any]:
    with bound_lifecycle(frozen_root) as (source, live, schedule, _runtime_value):
        result = source.prepare_all(output_root=Path(output_root), queue_root=Path(queue_root), authorization_acknowledgement_sha256=authorization_acknowledgement_sha256, route_provider=_frozen_route(live, queue_root, route_provider), **_surrogates(frozen_root))
    if result.get("provider_calls_made") != 0 or result.get("process_launches") != 0 or len(result.get("prepared_cells", [])) != len(schedule["cells"]):
        raise ValueError("Fresh96 preparation lifecycle drifted")
    return {"format_version": 1, "study_id": STUDY_ID, "kind": "prepared_64_fresh96_validation_grok_cells", "prepared_cells": result["prepared_cells"], "logical_cells": 64, "provider_calls_made": 0, "process_launches": 0}


def execute_one(*, output_root: Path, frozen_root: Path, queue_root: Path, authorization_acknowledgement_sha256: str, cell_id: str, allow_remote: bool, route_provider: Callable[[Path], tuple[dict[str, Any], dict[str, Any]]] | None = None, runner: Callable[..., Mapping[str, Any]] | None = None) -> dict[str, Any]:
    if allow_remote is not True:
        raise ValueError("explicit allow_remote required")
    schedule = admit_frozen_root(frozen_root)
    if cell_id not in {row["cell_id"] for row in schedule["cells"]}:
        raise ValueError("unknown Fresh96 cell")
    runtime = _runtime()
    slot = record = None
    try:
        slot, record = runtime._acquire_global_slot(Path(output_root), cell_id)
        state = runtime._claim(Path(output_root), cell_id)
        if state != "claimed_now":
            return {"format_version": 1, "study_id": STUDY_ID, "cell_id": cell_id, "state": "reconcile_required" if state == "expired" else state, "provider_calls_made": 0, "process_launches": 0}
        with bound_lifecycle(frozen_root) as (source, live, _schedule, _runtime_value):
            result = source.execute_one(output_root=Path(output_root), queue_root=Path(queue_root), authorization_acknowledgement_sha256=authorization_acknowledgement_sha256, cell_id=cell_id, allow_remote=True, route_provider=_frozen_route(live, queue_root, route_provider), runner=runner, **_surrogates(frozen_root))
        return {"format_version": 1, "study_id": STUDY_ID, **result}
    finally:
        if slot is not None and record is not None:
            runtime._release_global_slot(slot, record)


async def execute_wave(*, output_root: Path, frozen_root: Path, queue_root: Path, authorization_acknowledgement_sha256: str, allow_remote: bool, route_provider: Callable[[Path], tuple[dict[str, Any], dict[str, Any]]] | None = None, runner: Callable[..., Mapping[str, Any]] | None = None) -> list[dict[str, Any]]:
    if allow_remote is not True:
        raise ValueError("explicit allow_remote required")
    schedule = admit_frozen_root(frozen_root)
    with bound_lifecycle(frozen_root) as (_source, live, _schedule, _runtime_value):
        frozen = _frozen_route(live, queue_root, route_provider)
    semaphore = asyncio.Semaphore(MAX_CONCURRENCY)
    async def run(row: Mapping[str, Any]) -> dict[str, Any]:
        async with semaphore:
            return await asyncio.to_thread(execute_one, output_root=output_root, frozen_root=frozen_root, queue_root=queue_root, authorization_acknowledgement_sha256=authorization_acknowledgement_sha256, cell_id=row["cell_id"], allow_remote=True, route_provider=frozen, runner=runner)
    return await asyncio.gather(*(run(row) for row in schedule["cells"]))


def _output_schedule(output_root: Path, frozen_root: Path) -> dict[str, Any]:
    schedule, root = admit_frozen_root(frozen_root), Path(output_root)
    _plain(root, directory=True)
    expected = {"schedule.json", ".claims", *(row["cell_id"] for row in schedule["cells"])}
    if {path.name for path in root.iterdir()} != expected or stable(root / "schedule.json") != canonical(schedule):
        raise ValueError("proof-root inventory or persisted schedule drifted")
    claims = root / ".claims"
    _plain(claims, directory=True)
    if {path.name for path in claims.iterdir()} != {row["cell_id"] for row in schedule["cells"]}:
        raise ValueError("claim inventory drifted")
    for row in schedule["cells"]:
        claim = claims / row["cell_id"]
        _plain(claim, directory=True)
        if {path.name for path in claim.iterdir()} != {"claim.json"}:
            raise ValueError("claim artifact drifted")
        strict(stable(claim / "claim.json"), "claim")
    return schedule


def finalize_collector(*, output_root: Path, frozen_root: Path, collector_output: Path, authorization_acknowledgement_sha256: str) -> dict[str, Any]:
    collector = Path(collector_output)
    if collector.exists() or collector.is_symlink():
        raise ValueError("collector output must be fresh")
    schedule = _output_schedule(output_root, frozen_root)
    cells: list[dict[str, Any]] = []
    route = evidence = None
    with bound_lifecycle(frozen_root) as (source, live, _schedule, _runtime_value):
        for row in schedule["cells"]:
            root = Path(output_root) / row["cell_id"]
            prepared = strict(stable(root / "prepared.json"), "prepared")
            acknowledgement = strict(stable(root / "authorization-acknowledgement.json"), "acknowledgement").get("acknowledgement_sha256")
            if acknowledgement != authorization_acknowledgement_sha256 or not isinstance(prepared.get("route"), Mapping) or not isinstance(prepared.get("route_evidence"), Mapping):
                raise ValueError("collector acknowledgement or route binding drifted")
            if route is None:
                route, evidence = prepared["route"], prepared["route_evidence"]
            if prepared["route"] != route or prepared["route_evidence"] != evidence:
                raise ValueError("collector route/evidence differs across cells")
            raw, prompt, schema = source.payload(row)
            request, response, identity, settings = source.admit(root, row, schedule, raw, prompt, schema, route, evidence, acknowledgement, live)
            cells.append({"cell_id": row["cell_id"], "candidate_id": row["candidate_id"], "item_id": row["item_id"], "prompt_group_id": row["prompt_group_id"], "source_binding_sha256": row["source_binding_sha256"], "target_sha256": row["target_sha256"], "payload_base64": row["payload_base64"], "payload_sha256": row["payload_sha256"], "native_request_base64": base64.b64encode(request).decode("ascii"), "native_request_sha256": sha256(request), "native_response_base64": base64.b64encode(response).decode("ascii"), "native_response_sha256": sha256(response), "identity": identity, "effective_settings": settings, "effective_settings_sha256": sha256(settings)})
        source.validate_frozen_route(route, evidence)
    value = {"format_version": 1, "study_id": STUDY_ID, "kind": "complete_64_fresh96_validation_grok_receipts_cardinality_unproven", "schedule_sha256": schedule["schedule_sha256"], "authorization_acknowledgement_sha256": authorization_acknowledgement_sha256, "route": route, "route_evidence": evidence, "cells": cells, "native_endpoint_contact_cardinality": "unproven", "provider_calls_made": 0, "process_launches": 0}
    write_new(collector, canonical(value))
    return {"format_version": 1, "study_id": STUDY_ID, "kind": value["kind"], "collector_sha256": sha256(value), "cells": 64, "provider_calls_made": 0, "process_launches": 0}


def replay_collector(*, output_root: Path, frozen_root: Path, collector_path: Path) -> dict[str, Any]:
    schedule = _output_schedule(output_root, frozen_root)
    raw, value = stable(Path(collector_path)), strict(stable(Path(collector_path)), "collector")
    expected = {"format_version", "study_id", "kind", "schedule_sha256", "authorization_acknowledgement_sha256", "route", "route_evidence", "cells", "native_endpoint_contact_cardinality", "provider_calls_made", "process_launches"}
    if set(value) != expected or value.get("study_id") != STUDY_ID or value.get("kind") != "complete_64_fresh96_validation_grok_receipts_cardinality_unproven" or value.get("schedule_sha256") != schedule["schedule_sha256"] or not re.fullmatch(r"[0-9a-f]{64}", value.get("authorization_acknowledgement_sha256", "")) or value.get("native_endpoint_contact_cardinality") != "unproven" or value.get("provider_calls_made") != 0 or value.get("process_launches") != 0 or not isinstance(value.get("cells"), list) or len(value["cells"]) != 64:
        raise ValueError("collector drifted")
    index, identities = {row["cell_id"]: row for row in schedule["cells"]}, set()
    with bound_lifecycle(frozen_root) as (source, live, _schedule, _runtime_value):
        source.validate_frozen_route(value["route"], value["route_evidence"])
        for supplied in value["cells"]:
            keys = {"cell_id", "candidate_id", "item_id", "prompt_group_id", "source_binding_sha256", "target_sha256", "payload_base64", "payload_sha256", "native_request_base64", "native_request_sha256", "native_response_base64", "native_response_sha256", "identity", "effective_settings", "effective_settings_sha256"}
            if not isinstance(supplied, Mapping) or set(supplied) != keys:
                raise ValueError("collector cell fields drifted")
            row = index.get(supplied.get("cell_id"))
            try:
                request = base64.b64decode(supplied.get("native_request_base64", ""), validate=True)
                response = base64.b64decode(supplied.get("native_response_base64", ""), validate=True)
            except (TypeError, ValueError) as error:
                raise ValueError("collector native bytes are invalid") from error
            if row is None or any(supplied.get(key) != row[key] for key in ("candidate_id", "item_id", "prompt_group_id", "source_binding_sha256", "target_sha256", "payload_base64", "payload_sha256")) or supplied.get("native_request_sha256") != sha256(request) or supplied.get("native_response_sha256") != sha256(response) or supplied.get("effective_settings_sha256") != sha256(supplied.get("effective_settings")):
                raise ValueError("collector payload/response/settings drifted")
            identity = supplied.get("identity")
            if not isinstance(identity, Mapping):
                raise TypeError("invalid native identity")
            contact = (identity.get("request_id"), identity.get("session_id"))
            if not all(isinstance(item, str) and item for item in contact) or contact in identities:
                raise ValueError("duplicate native identity")
            root = Path(output_root) / row["cell_id"]
            prepared = strict(stable(root / "prepared.json"), "prepared")
            acknowledgement = strict(stable(root / "authorization-acknowledgement.json"), "acknowledgement").get("acknowledgement_sha256")
            if acknowledgement != value["authorization_acknowledgement_sha256"] or prepared.get("route") != value["route"] or prepared.get("route_evidence") != value["route_evidence"]:
                raise ValueError("collector route/evidence differs from persisted execution proof")
            payload, prompt, schema = source.payload(row)
            persisted = source.admit(root, row, schedule, payload, prompt, schema, prepared["route"], prepared["route_evidence"], acknowledgement, live)
            if (request, response, dict(identity), supplied["effective_settings"]) != persisted:
                raise ValueError("collector differs from persisted execution receipt")
            verified = live._validate_runner_result({"native_request_bytes": request, "native_response_bytes": response, "identity": identity, "effective_settings": supplied["effective_settings"]}, value["route"], payload)
            envelope = strict(response, "native response")
            if verified != persisted or envelope.get("requestId") != contact[0] or envelope.get("sessionId") != contact[1]:
                raise ValueError("independently reconstructed receipt drifted")
            identities.add(contact)
    if set(index) != {row["cell_id"] for row in value["cells"]}:
        raise ValueError("partial collector")
    return {"format_version": 1, "study_id": STUDY_ID, "kind": "durable_64_fresh96_validation_grok_cell_receipt_replay", "collector_sha256": sha256(raw), "cells": 64, "native_endpoint_contact_cardinality": "unproven", "authority": {"measurement": "endpoint_specific_only", "selection": "none", "promotion": "none", "runtime": "none", "sol": "out_of_scope"}}


def _projection_value(*, output_root: Path, frozen_root: Path, collector_path: Path) -> dict[str, Any]:
    replay = replay_collector(output_root=output_root, frozen_root=frozen_root, collector_path=collector_path)
    raw = stable(Path(collector_path))
    if replay["collector_sha256"] != sha256(raw):
        raise ValueError("collector changed after receipt replay")
    collector = strict(raw, "collector")
    schedule = admit_frozen_root(frozen_root)
    cells = {row["cell_id"]: row for row in schedule["cells"]}
    projections: list[dict[str, Any]] = []
    for supplied in collector["cells"]:
        cell = cells.get(supplied.get("cell_id"))
        if cell is None:
            raise ValueError("collector cell is outside Fresh96 schedule")
        try:
            response = base64.b64decode(supplied.get("native_response_base64", ""), validate=True)
        except (TypeError, ValueError) as error:
            raise ValueError("collector response is not base64") from error
        if supplied.get("native_response_sha256") != sha256(response):
            raise ValueError("collector response binding drifted")
        projections.append({"endpoint": ENDPOINT, "cell_id": cell["cell_id"], "candidate_id": cell["candidate_id"], "payload_sha256": cell["payload_sha256"], "source_binding_sha256": cell["source_binding_sha256"], "target_sha256": cell["target_sha256"], "scores": _scores_from_response(response)})
    if {row["cell_id"] for row in projections} != set(cells) or len(projections) != 64:
        raise ValueError("projection set is partial or duplicate")
    executor_hash = sha256(stable(Path(__file__).resolve()))
    value = {"format_version": 1, "study_id": ANALYSIS_STUDY_ID, "kind": "persisted_endpoint_cell_projection_set", "endpoint": ENDPOINT, "executor_binding": {"executor_id": STUDY_ID, "executor_sha256": executor_hash}, "schedule_sha256": schedule["schedule_sha256"], "projections": projections}
    value["projection_set_sha256"] = sha256(value)
    return value


def write_projection(*, output_root: Path, frozen_root: Path, collector_path: Path, projection_output: Path) -> dict[str, Any]:
    output = Path(projection_output)
    if output.exists() or output.is_symlink():
        raise ValueError("projection output must be fresh")
    _plain(output.parent, directory=True)
    value = _projection_value(output_root=output_root, frozen_root=frozen_root, collector_path=collector_path)
    write_new(output, canonical(value))
    return {"format_version": 1, "study_id": STUDY_ID, "kind": "persisted_64_fresh96_grok_cell_projections", "projection_output_sha256": sha256(value), "cells": 64, "endpoint": ENDPOINT, "provider_calls_made": 0, "process_launches": 0}


def replay_projection(*, output_root: Path, frozen_root: Path, collector_path: Path, projection_path: Path) -> dict[str, Any]:
    expected = _projection_value(output_root=output_root, frozen_root=frozen_root, collector_path=collector_path)
    raw = stable(Path(projection_path))
    supplied = strict(raw, "endpoint projection set")
    if supplied != expected:
        raise ValueError("endpoint projection set drifted")
    return {"format_version": 1, "study_id": STUDY_ID, "kind": "durable_64_fresh96_grok_projection_replay", "projection_set_sha256": sha256(raw), "cells": 64, "endpoint": ENDPOINT, "provider_calls_made": 0, "process_launches": 0}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    for name in ("prepare-all", "execute-one", "execute-wave", "finalize-collector", "replay-collector", "write-projection", "replay-projection"):
        modes.add_argument("--" + name, action="store_true")
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--frozen-root", type=Path, required=True)
    parser.add_argument("--queue-root", type=Path)
    parser.add_argument("--collector-output", type=Path)
    parser.add_argument("--collector-path", type=Path)
    parser.add_argument("--projection-output", type=Path)
    parser.add_argument("--projection-path", type=Path)
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
    elif args.replay_collector:
        if args.allow_remote or not args.collector_path:
            parser.error("replay requires collector and forbids remote")
        result = replay_collector(output_root=args.output_root, frozen_root=args.frozen_root, collector_path=args.collector_path)
    elif args.write_projection:
        if args.allow_remote or not args.collector_path or not args.projection_output:
            parser.error("projection requires collector/output and forbids remote")
        result = write_projection(output_root=args.output_root, frozen_root=args.frozen_root, collector_path=args.collector_path, projection_output=args.projection_output)
    else:
        if args.allow_remote or not args.collector_path or not args.projection_path:
            parser.error("projection replay requires collector/path and forbids remote")
        result = replay_projection(output_root=args.output_root, frozen_root=args.frozen_root, collector_path=args.collector_path, projection_path=args.projection_path)
    print(canonical(result).decode("utf-8"), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
