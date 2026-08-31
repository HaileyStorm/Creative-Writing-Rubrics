#!/usr/bin/env python3
"""One-shot, two-lane Sol execution over the frozen 38-cell confirmation schedule."""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import ModuleType
from typing import Any, Callable, Mapping


HERE = Path(__file__).resolve().parent
STUDY_ID = "hbq-human-alignment-optimizer-v5-f20-confirmation-sol-exec-v1"
FREEZE_ID = "hbq-human-alignment-optimizer-v5-f20-confirmation-freeze-v1"
FREEZE_COMMIT = "08fd8bd4442cf524bf631566cf539f2dc317d146"
FREEZE_SHA256 = "7b2d2a4b749656a9be9841919ea89346bb9a5ca615d339d9c03f27f9a3035ce4"
SCHEDULE_SHA256 = "cbdf783b7fa1306e89c9aee9b7f63d9eae2a8ea8c8ae4bcb3752ea14c18ceb6e"
V4_ID = "hbq-human-alignment-optimizer-v5-f20-nextwave-sol6-validation-exec-v4-threadsafe-route-load"
V4_COMMIT = "a95b9df6668da612af26a25c8abd8e8f5cb4027d"
V4_SHA256 = "ef2b44a5457292d71151a4ab48346a298956acb8126106d0cc186696efeb537c"
BASELINE = "candidate-102cc7f06c9a99a7"
SELECTED = "broader-nextwave-13-missing_evidence_not_no"
DIMENSIONS = ("Relevance", "Coherence", "Empathy", "Surprise", "Engagement", "Complexity")
MAX_CONCURRENCY = 2
WAIT_SECONDS = 120.0
_configuration_lock = threading.Lock()
_route_load_lock = threading.Lock()
_wave_lock = threading.Lock()


def canonical(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")


def sha256(value: bytes | Any) -> str:
    return hashlib.sha256(value if isinstance(value, bytes) else canonical(value)).hexdigest()


def _plain(path: Path, *, directory: bool | None = None) -> None:
    info = os.lstat(path)
    if stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)):
        raise ValueError("unsafe/reparsed path")
    if directory is not None and stat.S_ISDIR(info.st_mode) != directory:
        raise ValueError("unexpected path type")


def _safe(path: Path, *, directory: bool | None = None) -> Path:
    absolute = Path(os.path.abspath(path))
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current /= part
        if not current.exists():
            raise ValueError("required path is absent")
        _plain(current, directory=current != absolute or directory)
    return absolute


def stable(path: Path) -> bytes:
    path = _safe(path, directory=False)
    before = os.lstat(path)
    with path.open("rb") as handle:
        opened = os.fstat(handle.fileno())
        raw = handle.read()
        after = os.fstat(handle.fileno())
    identity = lambda item: (item.st_dev, item.st_ino, item.st_size)
    if identity(before) != identity(opened) or identity(opened) != identity(after):
        raise ValueError("stable read drift")
    return raw


def strict(raw: bytes, label: str) -> dict[str, Any]:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise ValueError(f"duplicate key in {label}")
            result[key] = value
        return result
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs, parse_constant=lambda token: (_ for _ in ()).throw(ValueError(token)))
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise ValueError(f"invalid {label}") from error
    if type(value) is not dict:
        raise ValueError(f"{label} must be an object")
    return value


def _git_blob(repo: Path, commit: str, relative: str) -> bytes:
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("dependency commit must be a full SHA-1")
    result = subprocess.run(["git", "-C", str(repo), "show", f"{commit}:{relative}"], capture_output=True, check=False)
    if result.returncode:
        raise ValueError("pinned Git blob is absent")
    return result.stdout


def _load_pinned(path: Path, digest: str, commit: str, relative: str, name: str) -> ModuleType:
    raw = stable(path)
    if not re.fullmatch(r"[0-9a-f]{64}", digest) or sha256(raw) != digest or _git_blob(HERE.parents[1], commit, relative) != raw:
        raise ValueError("pinned dependency drifted or remains unbound")
    module = ModuleType(name)
    module.__file__ = str(path)
    sys.modules[name] = module
    try:
        exec(compile(raw, str(path), "exec"), module.__dict__)
    finally:
        sys.modules.pop(name, None)
    if stable(path) != raw:
        raise ValueError("pinned dependency changed during load")
    return module


def _sources() -> tuple[ModuleType, ModuleType]:
    freeze = _load_pinned(HERE.parent / FREEZE_ID / "study.py", FREEZE_SHA256, FREEZE_COMMIT, f"evaluation-results/{FREEZE_ID}/study.py", "_confirmation_freeze")
    v4 = _load_pinned(HERE.parent / V4_ID / "executor.py", V4_SHA256, V4_COMMIT, f"evaluation-results/{V4_ID}/executor.py", "_confirmation_sol_v4")
    return freeze, v4


def _target(value: Any) -> dict[str, float]:
    if not isinstance(value, Mapping) or set(value) != set(DIMENSIONS):
        raise ValueError("confirmation target vector drifted")
    result = {key: float(value[key]) for key in DIMENSIONS}
    if any(not (0.0 <= item <= 5.0) for item in result.values()):
        raise ValueError("confirmation target vector is out of range")
    return result


def _rows(schedule: Mapping[str, Any]) -> tuple[dict[str, Any], ...]:
    cells, geometry = schedule.get("cells"), schedule.get("geometry")
    if (schedule.get("study_id") != FREEZE_ID or not isinstance(cells, list) or not isinstance(geometry, Mapping)
            or geometry.get("candidates") != 2 or geometry.get("confirmation_items") != 19
            or geometry.get("confirmation_groups") != 8 or geometry.get("endpoint_neutral_logical_cells") != 38
            or schedule.get("schedule_sha256") != SCHEDULE_SHA256):
        raise ValueError("frozen confirmation schedule geometry drifted")
    selection = schedule.get("candidate_selection")
    if (not isinstance(selection, Mapping) or selection.get("control_candidate_id") != BASELINE
            or selection.get("selected_candidate_id") != SELECTED):
        raise ValueError("frozen confirmation candidate selection drifted")
    targets = schedule.get("targets")
    if targets is not None and not isinstance(targets, Mapping):
        raise ValueError("confirmation target map drifted")
    rows: list[dict[str, Any]] = []
    for cell in cells:
        if not isinstance(cell, Mapping):
            raise ValueError("confirmation cell drifted")
        source_id, candidate, group, item = (cell.get("cell_id"), cell.get("candidate_id"), cell.get("prompt_group_id"), cell.get("item_id"))
        encoded, payload_sha, schema_sha = cell.get("payload_base64"), cell.get("payload_sha256"), cell.get("response_schema_sha256")
        if (cell.get("partition") != "confirmation" or not all(isinstance(value, str) and value for value in (source_id, candidate, group, item, encoded))
                or candidate not in {BASELINE, SELECTED} or not re.fullmatch(r"[0-9a-f]{64}", str(payload_sha))
                or not re.fullmatch(r"[0-9a-f]{64}", str(schema_sha))):
            raise ValueError("confirmation cell identity or payload binding drifted")
        try:
            payload = base64.b64decode(encoded, validate=True)
            payload_value = strict(payload, "endpoint-neutral payload")
        except (ValueError, TypeError) as error:
            raise ValueError("confirmation payload encoding drifted") from error
        if ("route_name" in cell or sha256(payload) != payload_sha or sha256(canonical(payload_value.get("response_schema"))) != schema_sha
                or payload_value.get("study_id") != FREEZE_ID):
            raise ValueError("confirmation payload bytes drifted")
        source_target = cell.get("target", targets.get(item) if isinstance(targets, Mapping) else None)
        target = _target(source_target)
        rows.append({"cell_id": "confirmation-sol-" + source_id, "source_cell_id": source_id, "candidate_id": candidate,
                     "prompt_group_id": group, "item_id": item, "story_id": item, "payload_base64": encoded,
                     "payload_sha256": payload_sha, "target": target})
    if len(rows) != 38 or len({row["cell_id"] for row in rows}) != 38 or len({row["source_cell_id"] for row in rows}) != 38:
        raise ValueError("confirmation cell cardinality drifted")
    if any(sum(row["candidate_id"] == candidate for row in rows) != 19 for candidate in (BASELINE, SELECTED)):
        raise ValueError("confirmation candidate balance drifted")
    groups = {row["prompt_group_id"] for row in rows}
    if len(groups) != 8 or {row["item_id"] for row in rows}.__len__() != 19:
        raise ValueError("confirmation partition geometry drifted")
    by_item: dict[str, set[str]] = {}
    for row in rows:
        by_item.setdefault(row["item_id"], set()).add(row["candidate_id"])
    if any(value != {BASELINE, SELECTED} for value in by_item.values()):
        raise ValueError("confirmation endpoint-neutral pairing drifted")
    return tuple(sorted(rows, key=lambda row: row["cell_id"]))


def _resolve(*, frozen_root: Path) -> dict[str, Any]:
    freeze, _v4 = _sources()
    schedule = freeze.validate_frozen_root(Path(frozen_root))
    schedule_raw = stable(Path(frozen_root) / "schedule.json")
    if schedule_raw != canonical(schedule):
        raise ValueError("persisted confirmation schedule commitment drifted")
    return {"schedule": schedule, "schedule_sha256": sha256(schedule_raw), "rows": _rows(schedule)}


def _configured_base(resolution: Mapping[str, Any]) -> ModuleType:
    _freeze, v4 = _sources()
    base, _unused = v4._sources()
    rows = resolution["rows"]
    with _configuration_lock:
        base.STUDY_ID = STUDY_ID
        base.ROWS = rows
        base.PUBLIC_RESULT_COMMIT = FREEZE_COMMIT
        base.SOURCE_RESULT_FILE_SHA256 = FREEZE_SHA256
        base.SOURCE_EXECUTOR_COMMIT = FREEZE_COMMIT
        base.SOURCE_EXECUTOR_SHA256 = FREEZE_SHA256
        base.SCHEDULE_SHA256 = resolution["schedule"]["schedule_sha256"]
        base.COLLECTOR_SHA256 = resolution["schedule_sha256"]
        base.ALIAS_MANIFEST_SHA256 = "0" * 64
        base.RESULT_INTERNAL_SHA256 = resolution["schedule_sha256"]
        base.TARGET_CSV_SHA256 = resolution["schedule_sha256"]
        base._validate_target = lambda row, _path: dict(row["target"])
        original_route = base._route
        base._route = lambda *args, **kwargs: _locked_route(original_route, *args, **kwargs)
        original_prepared = base._prepared
        def prepared(row: Mapping[str, Any], payload: bytes, schema: bytes, target: Mapping[str, float], route: Mapping[str, Any], evidence: Mapping[str, Any], acknowledgement: str) -> dict[str, bytes]:
            files = original_prepared(row, payload, schema, target, route, evidence, acknowledgement)
            value = strict(files["prepared.json"], "prepared")
            source = dict(value["source"])
            source.pop("alias_manifest_sha256", None)
            source["confirmation_freeze_commit"] = FREEZE_COMMIT
            source["confirmation_freeze_study_sha256"] = FREEZE_SHA256
            source["confirmation_schedule_file_sha256"] = resolution["schedule_sha256"]
            value["source"] = source
            files["prepared.json"] = base.canonical(value)
            return files
        base._prepared = prepared
    return base


def _locked_route(route: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    with _route_load_lock:
        return route(*args, **kwargs)


def _disjoint(output_root: Path, *sources: Path) -> None:
    output = Path(os.path.abspath(output_root))
    _safe(output.parent, directory=True)
    for source in sources:
        source = _safe(source)
        if output == source or output in source.parents or source in output.parents:
            raise ValueError("output root must be disjoint from every source and queue root")


def _locks(output_root: Path) -> Path:
    locks = output_root.parent / ("." + output_root.name + ".confirmation-sol-locks")
    locks.mkdir(exist_ok=True)
    _plain(locks, directory=True)
    return locks


def _release(path: Path | None) -> None:
    if path is not None and path.exists():
        _plain(path, directory=False)
        path.unlink()


def _terminal(root: Path) -> bool:
    return any((root / name).exists() for name in ("launch-intent.json", "execution-receipt.json", "result.json", "precontact-failure.json"))


def _sharing_conflict(error: PermissionError) -> bool:
    # Python 3.14's Windows Path.open can surface a sharing violation as errno 13
    # without preserving winerror while a sibling lane removes a slot file.
    return getattr(error, "winerror", None) in {32, 33} or (os.name == "nt" and error.errno == 13)


def _claim_cell(locks: Path, root: Path, cell_id: str) -> Path:
    deadline, path = time.monotonic() + WAIT_SECONDS, locks / (cell_id + ".lock")
    while time.monotonic() < deadline:
        if _terminal(root):
            raise ValueError("no resend: cell already has terminal launch evidence")
        try:
            with path.open("x", encoding="ascii") as handle:
                handle.write(cell_id)
            if _terminal(root):
                _release(path)
                raise ValueError("no resend: cell already has terminal launch evidence")
            return path
        except FileExistsError:
            time.sleep(0.01)
        except PermissionError as error:
            if not _sharing_conflict(error):
                raise
            time.sleep(0.01)
    raise TimeoutError("same-cell execution claim did not become available")


def _acquire_slot(locks: Path, cell_id: str) -> Path:
    deadline = time.monotonic() + WAIT_SECONDS
    while time.monotonic() < deadline:
        for index in range(MAX_CONCURRENCY):
            path = locks / f"slot-{index}.lock"
            try:
                with path.open("x", encoding="ascii") as handle:
                    handle.write(cell_id)
                return path
            except FileExistsError:
                continue
            except PermissionError as error:
                if not _sharing_conflict(error):
                    raise
                continue
        time.sleep(0.01)
    raise TimeoutError("global Sol two-slot semaphore did not become available")


def prepare_all(*, output_root: Path, frozen_root: Path, queue_root: Path, authorization_acknowledgement_sha256: str, broker_factory: Callable[[Path], Any] | None = None) -> dict[str, Any]:
    if Path(output_root).exists():
        raise ValueError("fresh output root required")
    _disjoint(Path(output_root), Path(frozen_root), Path(queue_root), HERE.parents[1])
    resolution = _resolve(frozen_root=Path(frozen_root))
    base = _configured_base(resolution)
    route, evidence, _v3 = base._route(Path(queue_root), broker_factory)
    Path(output_root).mkdir(parents=True)
    for row in resolution["rows"]:
        root = Path(output_root) / row["cell_id"]
        root.mkdir()
        payload = base64.b64decode(row["payload_base64"], validate=True)
        schema = base.canonical(strict(payload, "endpoint-neutral payload")["response_schema"])
        for name, raw in base._prepared(row, payload, schema, row["target"], route, evidence, authorization_acknowledgement_sha256).items():
            base._write_new(root / name, raw)
    return {"study_id": STUDY_ID, "cells": 38, "confirmation_items": 19, "confirmation_groups": 8, "state": "prepared_no_contact", "provider_calls_made": 0, "process_launches": 0, "max_concurrency": MAX_CONCURRENCY, "authority": "confirmation_measurement_only"}


def execute_wave(*, output_root: Path, frozen_root: Path, queue_root: Path, authorization_acknowledgement_sha256: str, allow_remote: bool, broker_factory: Callable[[Path], Any] | None = None, call_codex: Callable[..., Any] | None = None) -> list[dict[str, Any]]:
    if allow_remote is not True:
        raise ValueError("execution requires explicit allow_remote=True")
    _disjoint(Path(output_root), Path(frozen_root), Path(queue_root), HERE.parents[1])
    resolution = _resolve(frozen_root=Path(frozen_root))
    base = _configured_base(resolution)
    rows = resolution["rows"]
    if {path.name for path in Path(output_root).iterdir()} != {row["cell_id"] for row in rows}:
        raise ValueError("prepared output inventory drifted")
    locks = _locks(Path(output_root))
    def run(row: Mapping[str, Any]) -> dict[str, Any]:
        root = Path(output_root) / row["cell_id"]
        claim = slot = None
        try:
            claim = _claim_cell(locks, root, row["cell_id"])
            slot = _acquire_slot(locks, row["cell_id"])
            return base.execute_one(output_root=Path(output_root), cell_id=row["cell_id"], queue_root=Path(queue_root), authorization_acknowledgement_sha256=authorization_acknowledgement_sha256, allow_remote=True, hanna_csv_path=Path(frozen_root) / "schedule.json", broker_factory=broker_factory, call_codex=call_codex)
        finally:
            _release(slot)
            _release(claim)
    try:
        with _wave_lock, ThreadPoolExecutor(max_workers=MAX_CONCURRENCY) as pool:
            return list(pool.map(run, rows))
    finally:
        if locks.exists() and not any(locks.iterdir()):
            locks.rmdir()


def validate_package() -> dict[str, Any]:
    expected = {"README.md", "study-contract.json", "executor.py"}
    if {path.name for path in HERE.iterdir() if path.name != "__pycache__"} != expected:
        raise ValueError("package inventory drifted")
    contract = strict(stable(HERE / "study-contract.json"), "study contract")
    expected_contract = {"format_version": 1, "study_id": STUDY_ID, "kind": "one_shot_confirmation_sol_execution", "geometry": {"candidates": 2, "confirmation_items": 19, "confirmation_groups": 8, "sol_cells": 38}, "authority": {"selection": "frozen_before_confirmation", "endpoint_pooling": "forbidden", "generalization": "none", "promotion": "none", "runtime": "none", "outcome": "measurement_only"}, "pinned_dependencies": {"confirmation_freeze": {"commit": FREEZE_COMMIT, "schedule_sha256": SCHEDULE_SHA256, "study_sha256": FREEZE_SHA256}, "sol_lifecycle": {"commit": V4_COMMIT, "executor_sha256": V4_SHA256}}, "prohibitions": ["no runtime DSPy or Optuna", "no fallback or resend", "no selection, promotion, runtime, pooled-endpoint, or generalization claim"]}
    if contract != expected_contract:
        raise ValueError("package contract drifted or overclaims authority")
    return contract


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--prepare", action="store_true")
    mode.add_argument("--execute-wave", action="store_true")
    for name in ("output-root", "frozen-root", "queue-root"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--authorization-acknowledgement-sha256", required=True)
    parser.add_argument("--allow-remote", action="store_true")
    args = parser.parse_args(argv)
    validate_package()
    common = {"output_root": args.output_root, "frozen_root": args.frozen_root, "queue_root": args.queue_root, "authorization_acknowledgement_sha256": args.authorization_acknowledgement_sha256}
    if args.prepare:
        if args.allow_remote:
            parser.error("prepare forbids remote execution")
        result = prepare_all(**common)
    else:
        if not args.allow_remote:
            parser.error("execute-wave requires explicit remote authorization")
        result = execute_wave(**common, allow_remote=True)
    print(canonical(result).decode("utf-8"), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
