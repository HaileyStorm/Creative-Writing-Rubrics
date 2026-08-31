#!/usr/bin/env python3
"""Two-lane, tool-free Sol execution over the public Fresh96 validation freeze."""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import math
import os
import re
import stat
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Mapping
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import ModuleType
from typing import Any

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
STUDY_ID = "hbq-human-alignment-hanna96-validation-sol-exec-v1"
FREEZE_ID = "hbq-human-alignment-hanna96-validation-freeze-v1"
FREEZE_SHA256 = "d8b99c651cfbc0c04207101a6ad15373168a5ffad3711f7d17fb589e8a13542e"
V4_ID = "hbq-human-alignment-optimizer-v5-f20-nextwave-sol6-validation-exec-v4-threadsafe-route-load"
V4_COMMIT = "a95b9df6668da612af26a25c8abd8e8f5cb4027d"
V4_SHA256 = "ef2b44a5457292d71151a4ab48346a298956acb8126106d0cc186696efeb537c"
BASELINE = "candidate-102cc7f06c9a99a7"
DESCENDANT = "broader-nextwave-13-missing_evidence_not_no"
DIMENSIONS = ("Relevance", "Coherence", "Empathy", "Surprise", "Engagement", "Complexity")
MAX_CONCURRENCY = 2
WAIT_SECONDS = 120.0
_configuration_lock = threading.Lock()
_route_lock = threading.Lock()
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


def _git_blob(commit: str, relative: str) -> bytes:
    result = subprocess.run(["git", "-C", str(REPO), "show", f"{commit}:{relative}"], capture_output=True, check=False)
    if result.returncode:
        raise ValueError("pinned Git blob is absent")
    return result.stdout


def _load_pinned(path: Path, digest: str, commit: str, relative: str, name: str) -> ModuleType:
    raw = stable(path)
    if not re.fullmatch(r"[0-9a-f]{64}", digest) or sha256(raw) != digest or _git_blob(commit, relative) != raw:
        raise ValueError("pinned Sol lifecycle dependency drifted")
    module = ModuleType(name)
    module.__file__ = str(path)
    sys.modules[name] = module
    try:
        exec(compile(raw, str(path), "exec"), module.__dict__)  # noqa: S102 -- exact pinned source is hash and Git-blob bound.
    finally:
        sys.modules.pop(name, None)
    if stable(path) != raw:
        raise ValueError("pinned Sol lifecycle dependency changed during load")
    return module


def _freeze_module() -> ModuleType:
    path = HERE.parent / FREEZE_ID / "study.py"
    raw = stable(path)
    if sha256(raw) != FREEZE_SHA256:
        raise ValueError("pinned Fresh96 freeze dependency drifted")
    module = ModuleType("_fresh96_validation_freeze")
    module.__file__ = str(path)
    sys.modules[module.__name__] = module
    try:
        exec(compile(raw, str(path), "exec"), module.__dict__)  # noqa: S102 -- freeze code validates the explicit schedule root.
    finally:
        sys.modules.pop(module.__name__, None)
    if stable(path) != raw or getattr(module, "STUDY_ID", None) != FREEZE_ID:
        raise ValueError("Fresh96 freeze module drifted")
    return module


def _sources() -> tuple[ModuleType, ModuleType]:
    freeze = _freeze_module()
    v4 = _load_pinned(HERE.parent / V4_ID / "executor.py", V4_SHA256, V4_COMMIT, f"evaluation-results/{V4_ID}/executor.py", "_fresh96_sol_v4")
    return freeze, v4


def _target(value: Any) -> dict[str, float]:
    if not isinstance(value, Mapping) or set(value) != set(DIMENSIONS):
        raise ValueError("Fresh96 target vector drifted")
    target = {dimension: float(value[dimension]) for dimension in DIMENSIONS}
    if any(not math.isfinite(score) or not 0.0 <= score <= 5.0 for score in target.values()):
        raise ValueError("Fresh96 target vector is invalid")
    return target


def _rows(schedule: Mapping[str, Any]) -> tuple[dict[str, Any], ...]:
    geometry, cells = schedule.get("geometry"), schedule.get("cells")
    if (schedule.get("study_id") != FREEZE_ID or not isinstance(geometry, Mapping) or geometry != {"groups": 16, "items": 32, "candidates": 2, "endpoint_neutral_logical_cells": 64}
            or not isinstance(cells, list) or len(cells) != 64):
        raise ValueError("Fresh96 validation schedule geometry drifted")
    rows: list[dict[str, Any]] = []
    for cell in cells:
        if not isinstance(cell, Mapping):
            raise TypeError("Fresh96 validation cell drifted")
        cell_id, candidate, group, item = (cell.get("cell_id"), cell.get("candidate_id"), cell.get("prompt_group_id"), cell.get("item_id"))
        encoded, payload_sha = cell.get("payload_base64"), cell.get("payload_sha256")
        if (not all(isinstance(value, str) and value for value in (cell_id, candidate, group, item, encoded)) or candidate not in {BASELINE, DESCENDANT}
                or not isinstance(payload_sha, str) or not re.fullmatch(r"[0-9a-f]{64}", payload_sha)):
            raise ValueError("Fresh96 validation cell identity drifted")
        try:
            payload = base64.b64decode(encoded, validate=True)
            payload_value = strict(payload, "endpoint-neutral payload")
        except (ValueError, TypeError) as error:
            raise ValueError("Fresh96 validation payload encoding drifted") from error
        if (sha256(payload) != payload_sha or payload_value.get("study_id") != FREEZE_ID
                or sha256(cell.get("target")) != cell.get("target_sha256")
                or not isinstance(cell.get("source_binding_sha256"), str) or not re.fullmatch(r"[0-9a-f]{64}", cell["source_binding_sha256"])):
            raise ValueError("Fresh96 validation payload/source binding drifted")
        rows.append({"cell_id": "h96-sol-" + cell_id, "source_cell_id": cell_id, "candidate_id": candidate, "prompt_group_id": group, "item_id": item,
                     "story_id": item, "payload_base64": encoded, "payload_sha256": payload_sha, "source_binding_sha256": cell["source_binding_sha256"],
                     "target_sha256": cell["target_sha256"], "target": _target(cell.get("target"))})
    if (len({row["cell_id"] for row in rows}) != 64 or len({row["source_cell_id"] for row in rows}) != 64
            or len({row["item_id"] for row in rows}) != 32 or len({row["prompt_group_id"] for row in rows}) != 16
            or any(sum(row["candidate_id"] == candidate for row in rows) != 32 for candidate in (BASELINE, DESCENDANT))):
        raise ValueError("Fresh96 validation pairing geometry drifted")
    paired: dict[str, set[str]] = {}
    for row in rows:
        paired.setdefault(row["item_id"], set()).add(row["candidate_id"])
    if any(candidates != {BASELINE, DESCENDANT} for candidates in paired.values()):
        raise ValueError("Fresh96 endpoint-neutral pairing drifted")
    return tuple(sorted(rows, key=lambda row: row["cell_id"]))


def _resolve(*, frozen_root: Path) -> dict[str, Any]:
    freeze, _v4 = _sources()
    schedule = freeze.validate_frozen_root(Path(frozen_root))
    raw = stable(Path(frozen_root) / "schedule.json")
    if raw != canonical(schedule):
        raise ValueError("persisted Fresh96 schedule commitment drifted")
    return {"schedule": schedule, "schedule_file_sha256": sha256(raw), "schedule_sha256": schedule["schedule_sha256"], "rows": _rows(schedule)}


def _configured_base(resolution: Mapping[str, Any]) -> ModuleType:
    _freeze, v4 = _sources()
    base, _unused = v4._sources()
    with _configuration_lock:
        base.STUDY_ID = STUDY_ID
        base.ROWS = resolution["rows"]
        base.BASELINE = BASELINE
        base.CANDIDATE = DESCENDANT
        base.PUBLIC_RESULT_COMMIT = V4_COMMIT
        base.SOURCE_RESULT_FILE_SHA256 = resolution["schedule_file_sha256"]
        base.SOURCE_EXECUTOR_COMMIT = V4_COMMIT
        base.SOURCE_EXECUTOR_SHA256 = V4_SHA256
        base.SCHEDULE_SHA256 = resolution["schedule"]["schedule_sha256"]
        base.COLLECTOR_SHA256 = resolution["schedule_file_sha256"]
        base.ALIAS_MANIFEST_SHA256 = "0" * 64
        base.RESULT_INTERNAL_SHA256 = resolution["schedule_file_sha256"]
        base.TARGET_CSV_SHA256 = resolution["schedule"]["source"]["fresh96_manifest_sha256"]
        base._validate_target = lambda row, _path: dict(row["target"])
        original_route = base._route
        def route(*args: Any, **kwargs: Any) -> Any:
            with _route_lock:
                value, evidence, v3 = original_route(*args, **kwargs)
                return (*v4._frozen_route(value, evidence, v3, require_unexpired=True), v3)
        base._route = route
        original_prepared = base._prepared
        def prepared(row: Mapping[str, Any], payload: bytes, schema: bytes, target: Mapping[str, float], route_value: Mapping[str, Any], evidence: Mapping[str, Any], acknowledgement: str) -> dict[str, bytes]:
            files = original_prepared(row, payload, schema, target, route_value, evidence, acknowledgement)
            target_file = strict(files["target-vector.json"], "target vector")
            target_file.pop("hanna_csv_sha256", None)
            target_file["fresh96_manifest_sha256"] = resolution["schedule"]["source"]["fresh96_manifest_sha256"]
            target_file["source_binding_sha256"] = row["source_binding_sha256"]
            files["target-vector.json"] = base.canonical(target_file)
            value = strict(files["prepared.json"], "prepared")
            source = dict(value["source"])
            source["fresh96_validation_schedule_sha256"] = resolution["schedule_sha256"]
            source["fresh96_validation_study_id"] = FREEZE_ID
            value["source"] = source
            value["target_vector_sha256"] = sha256(files["target-vector.json"])
            files["prepared.json"] = base.canonical(value)
            return files
        base._prepared = prepared
    return base


def _disjoint(output_root: Path, *sources: Path) -> None:
    output = Path(os.path.abspath(output_root))
    _safe(output.parent, directory=True)
    for source in sources:
        source = _safe(source)
        if output == source or output in source.parents or source in output.parents:
            raise ValueError("output root must be disjoint from source, queue, and repository paths")


def _release(path: Path | None) -> None:
    if path is not None and path.exists():
        _plain(path, directory=False)
        path.unlink()


def _sharing_conflict(error: PermissionError) -> bool:
    return getattr(error, "winerror", None) in {32, 33} or (os.name == "nt" and error.errno == 13)


def _terminal(root: Path) -> bool:
    return any((root / name).exists() for name in ("launch-intent.json", "execution-receipt.json", "result.json", "precontact-failure.json"))


def _locks(output_root: Path) -> Path:
    locks = output_root.parent / ("." + output_root.name + ".fresh96-sol-locks")
    locks.mkdir(exist_ok=True)
    _plain(locks, directory=True)
    return locks


def _claim(locks: Path, root: Path, cell_id: str) -> Path:
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


def _slot(locks: Path, cell_id: str) -> Path:
    deadline = time.monotonic() + WAIT_SECONDS
    while time.monotonic() < deadline:
        for index in range(MAX_CONCURRENCY):
            path = locks / f"slot-{index}.lock"
            try:
                with path.open("x", encoding="ascii") as handle:
                    handle.write(cell_id)
                return path
            except FileExistsError:
                pass
            except PermissionError as error:
                if not _sharing_conflict(error):
                    raise
        time.sleep(0.01)
    raise TimeoutError("global Sol two-slot semaphore did not become available")


def prepare_all(*, output_root: Path, frozen_root: Path, queue_root: Path, authorization_acknowledgement_sha256: str, broker_factory: Callable[[Path], Any] | None = None) -> dict[str, Any]:
    if Path(output_root).exists():
        raise ValueError("fresh output root required")
    _disjoint(Path(output_root), Path(frozen_root), Path(queue_root), REPO)
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
    return {"study_id": STUDY_ID, "cells": 64, "items": 32, "groups": 16, "state": "prepared_no_contact", "provider_calls_made": 0, "process_launches": 0, "max_concurrency": MAX_CONCURRENCY, "authority": "endpoint_specific_measurement_only"}


def execute_wave(*, output_root: Path, frozen_root: Path, queue_root: Path, authorization_acknowledgement_sha256: str, allow_remote: bool, broker_factory: Callable[[Path], Any] | None = None, call_codex: Callable[..., Any] | None = None) -> list[dict[str, Any]]:
    if allow_remote is not True:
        raise ValueError("execution requires explicit allow_remote=True")
    _disjoint(Path(output_root), Path(frozen_root), Path(queue_root), REPO)
    resolution = _resolve(frozen_root=Path(frozen_root))
    base = _configured_base(resolution)
    rows = resolution["rows"]
    if {path.name for path in Path(output_root).iterdir()} != {row["cell_id"] for row in rows}:
        raise ValueError("prepared output inventory drifted")
    locks = _locks(Path(output_root))
    def run(row: Mapping[str, Any]) -> dict[str, Any]:
        claim = slot = None
        try:
            root = Path(output_root) / row["cell_id"]
            claim = _claim(locks, root, row["cell_id"])
            slot = _slot(locks, row["cell_id"])
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


def _projection_set(*, output_root: Path, frozen_root: Path, authorization_acknowledgement_sha256: str) -> dict[str, Any]:
    _disjoint(Path(output_root), Path(frozen_root), REPO)
    resolution = _resolve(frozen_root=Path(frozen_root))
    base = _configured_base(resolution)
    root = _safe(Path(output_root), directory=True)
    rows = resolution["rows"]
    if {path.name for path in root.iterdir()} != {row["cell_id"] for row in rows}:
        raise ValueError("output-root inventory drifted")
    projections: list[dict[str, Any]] = []
    identities: set[tuple[str, str, str]] = set()
    for row in rows:
        cell = root / row["cell_id"]
        base._inventory(cell, completed=True)
        prepared = base._canonical_json(cell / "prepared.json", "prepared")
        proof = base._canonical_json(cell / "zero-charge-route-proof.json", "route proof")
        route, evidence = proof.get("route"), prepared.get("route_evidence")
        if not isinstance(route, Mapping) or not isinstance(evidence, Mapping):
            raise TypeError("prepared route binding drifted")
        payload, schema = base.stable(cell / "outbound-payload.json"), base.stable(cell / "response-schema.json")
        expected = base._prepared(row, payload, schema, row["target"], route, evidence, authorization_acknowledgement_sha256)
        if any(base.stable(cell / name) != raw for name, raw in expected.items()) or sha256(payload) != row["payload_sha256"]:
            raise ValueError("prepared payload binding drifted")
        final = base._json(cell / "raw-codex-final-response.bin", "final response")
        answer = base._validate_answer(final)
        receipt = base._canonical_json(cell / "execution-receipt.json", "receipt")
        identity = receipt.get("identity", {})
        key = (identity.get("thread_id"), identity.get("session_id"), identity.get("contact_id"))
        if (receipt.get("cell") != row or receipt.get("study_id") != STUDY_ID or receipt.get("process_launches") != 1
                or receipt.get("provider_calls_made") is not None or receipt.get("native_endpoint_contact_cardinality") != "unproven"
                or receipt.get("request_sha256") != sha256(payload) or receipt.get("response_schema_sha256") != sha256(schema)
                or receipt.get("human_score_projection") != answer or identity.get("effective_model") != "gpt-5.6-sol"
                or identity.get("requested_model") != "gpt-5.6-sol" or identity.get("requested_reasoning_effort") != "high"
                or not all(isinstance(value, str) and value for value in key) or key in identities):
            raise ValueError("Sol lifecycle receipt/identity drifted")
        identities.add(key)
        projections.append({"endpoint": "gpt-5.6-sol", "cell_id": row["source_cell_id"], "candidate_id": row["candidate_id"], "payload_sha256": row["payload_sha256"], "source_binding_sha256": row["source_binding_sha256"], "target_sha256": row["target_sha256"], "scores": {dimension: float(answer["scores"][dimension]) for dimension in DIMENSIONS}})
    if len(projections) != 64 or len({row["cell_id"] for row in projections}) != 64:
        raise ValueError("Fresh96 projection cardinality drifted")
    value = {"format_version": 1, "study_id": "hbq-human-alignment-hanna96-validation-analysis-v1", "kind": "persisted_endpoint_cell_projection_set", "endpoint": "gpt-5.6-sol", "executor_binding": {"executor_id": STUDY_ID, "executor_sha256": sha256(stable(HERE / "executor.py"))}, "schedule_sha256": resolution["schedule_sha256"], "projections": sorted(projections, key=lambda row: row["cell_id"])}
    value["projection_set_sha256"] = sha256(value)
    return value


def write_projection_set(*, projection_output: Path, output_root: Path, frozen_root: Path, authorization_acknowledgement_sha256: str) -> dict[str, Any]:
    projection_output = Path(projection_output)
    if projection_output.name != "sol.json" or projection_output.exists():
        raise ValueError("projection output must be a fresh sol.json")
    _disjoint(projection_output, Path(output_root), Path(frozen_root), REPO)
    _safe(projection_output.parent, directory=True)
    value = _projection_set(output_root=output_root, frozen_root=frozen_root, authorization_acknowledgement_sha256=authorization_acknowledgement_sha256)
    with projection_output.open("xb") as handle:
        handle.write(canonical(value))
        handle.flush()
        os.fsync(handle.fileno())
    return value


def replay_projection_set(*, projection_path: Path, output_root: Path, frozen_root: Path, authorization_acknowledgement_sha256: str) -> dict[str, Any]:
    expected = _projection_set(output_root=output_root, frozen_root=frozen_root, authorization_acknowledgement_sha256=authorization_acknowledgement_sha256)
    actual = strict(stable(Path(projection_path)), "persisted Sol projection set")
    if actual != expected:
        raise ValueError("persisted Sol projection set differs from exact lifecycle replay")
    return actual


def reconcile_all(*, output_root: Path, frozen_root: Path, authorization_acknowledgement_sha256: str) -> dict[str, Any]:
    resolution = _resolve(frozen_root=Path(frozen_root))
    root = _safe(Path(output_root), directory=True)
    ambiguous = []
    for row in resolution["rows"]:
        terminal = root / row["cell_id"] / "result.json"
        if terminal.exists():
            value = strict(stable(terminal), "terminal result")
            if value.get("kind") != "reconcile_required_after_process_launch":
                raise ValueError("unexpected terminal result")
            ambiguous.append(row["cell_id"])
    if ambiguous:
        return {"study_id": STUDY_ID, "state": "reconcile_required", "cells": ambiguous, "provider_calls_made": 0, "action": "no_requeue_or_resend"}
    _projection_set(output_root=output_root, frozen_root=frozen_root, authorization_acknowledgement_sha256=authorization_acknowledgement_sha256)
    return {"study_id": STUDY_ID, "state": "ready_for_provider_free_projection_replay", "cells": 64, "provider_calls_made": 0}


def validate_package() -> dict[str, Any]:
    expected = {"README.md", "study-contract.json", "executor.py"}
    if {path.name for path in HERE.iterdir() if path.name != "__pycache__"} != expected:
        raise ValueError("package inventory drifted")
    contract = strict(stable(HERE / "study-contract.json"), "study contract")
    expected_contract = {"authority": {"endpoint_pooling": "forbidden", "generalization": "none", "promotion": "none", "runtime": "none", "selection": "none"}, "format_version": 1, "geometry": {"cells": 64, "groups": 16, "items_per_candidate": 32, "max_concurrency": 2}, "kind": "fresh96_sol_validation_execution", "pinned_dependencies": {"fresh96_freeze_study_sha256": FREEZE_SHA256, "sol_lifecycle": {"commit": V4_COMMIT, "executor_sha256": V4_SHA256}}, "prohibitions": ["no runtime DSPy or Optuna", "no fallback or resend", "no selection, promotion, runtime, pooled-endpoint, or generalization claim"], "study_id": STUDY_ID}
    if contract != expected_contract:
        raise ValueError("package contract drifted")
    return contract


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--prepare", action="store_true")
    mode.add_argument("--execute-wave", action="store_true")
    mode.add_argument("--write-projection-set", action="store_true")
    mode.add_argument("--replay-projection-set", action="store_true")
    mode.add_argument("--reconcile", action="store_true")
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--frozen-root", type=Path, required=True)
    parser.add_argument("--queue-root", type=Path)
    parser.add_argument("--projection-path", type=Path)
    parser.add_argument("--authorization-acknowledgement-sha256", required=True)
    parser.add_argument("--allow-remote", action="store_true")
    args = parser.parse_args(argv)
    validate_package()
    common = {"output_root": args.output_root, "frozen_root": args.frozen_root, "authorization_acknowledgement_sha256": args.authorization_acknowledgement_sha256}
    if args.prepare:
        if args.allow_remote or args.queue_root is None:
            parser.error("prepare requires queue root and forbids remote execution")
        result = prepare_all(**common, queue_root=args.queue_root)
    elif args.execute_wave:
        if not args.allow_remote or args.queue_root is None:
            parser.error("execute-wave requires queue root and explicit remote authorization")
        result = execute_wave(**common, queue_root=args.queue_root, allow_remote=True)
    elif args.write_projection_set:
        if args.allow_remote or args.queue_root is not None or args.projection_path is None:
            parser.error("write-projection-set is provider-free and requires only a fresh projection path")
        result = write_projection_set(**common, projection_output=args.projection_path)
    elif args.replay_projection_set:
        if args.allow_remote or args.queue_root is not None or args.projection_path is None:
            parser.error("replay-projection-set is provider-free and requires a projection path")
        result = replay_projection_set(**common, projection_path=args.projection_path)
    else:
        if args.allow_remote or args.queue_root is not None:
            parser.error("reconcile is provider-free and takes no queue root")
        result = reconcile_all(**common)
    print(canonical(result).decode("utf-8"), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
