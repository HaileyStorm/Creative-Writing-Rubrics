#!/usr/bin/env python3
"""Provider-free preparation and two-lane Sol validation after a Grok-only development choice."""
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
STUDY_ID = "hbq-human-alignment-optimizer-v5-f20-broader-development-sol-validation-v1"
FREEZE_ID = "hbq-human-alignment-optimizer-v5-f20-broader-development-freeze-v1"
FREEZE_COMMIT = "436da1ef3f8cf239203ac6a80afe8f72708c0415"
FREEZE_SHA256 = "507e3c0bec1af6d0acef6e806cf6874a2633e892c9bbf567728f436af30f84bf"
RESULT_ID = "hbq-human-alignment-optimizer-v5-f20-broader-development-grok-result-v2-v3-exec"
RESULT_RELATIVE = f"evaluation-results/{RESULT_ID}/result.json"
RESULT_VERIFIER = HERE.parent / RESULT_ID / "verify.py"
RESULT_VERIFIER_COMMIT = "5f50fbc2c345a55203cd2891d80037a797c6a1b4"
RESULT_VERIFIER_SHA256 = "4966a54961a19453ea407129303f8baba1f66d0506f4551552e7a28c5529d855"
RESULT_FILES = {
    f"evaluation-results/{RESULT_ID}/README.md": "f0f814d4389c1ef3b19ae80667e433682c80faf0c13d82305c2cc3e948fefeca",
    f"evaluation-results/{RESULT_ID}/result.json": "89d18aa68e8285dd9cbe8f996413672aec3c19b740c869b2bbca66c54ccd3a32",
    f"evaluation-results/{RESULT_ID}/study-contract.json": "feca308b29b1a7eb4db1ac81c6e5e2eebba33273082a3a9c61c9da0799f86a06",
    f"evaluation-results/{RESULT_ID}/verify.py": RESULT_VERIFIER_SHA256,
    "tests/test_hbq_human_alignment_optimizer_v5_f20_broader_development_grok_result_v2_v3_exec.py": "649c79f0b5a6b94a11f236e35bb330bb07407d7084cc73c26e43df3eae1e420e",
}
V4_ID = "hbq-human-alignment-optimizer-v5-f20-nextwave-sol6-validation-exec-v4-threadsafe-route-load"
V4 = HERE.parent / V4_ID / "executor.py"
V4_COMMIT = "a95b9df6668da612af26a25c8abd8e8f5cb4027d"
V4_SHA256 = "ef2b44a5457292d71151a4ab48346a298956acb8126106d0cc186696efeb537c"
BASELINE = "candidate-102cc7f06c9a99a7"
PARENT = "normalized-nextwave-08-conservative-hybrid"
CHILDREN = frozenset({
    "broader-nextwave-11-scope_materiality",
    "broader-nextwave-12-construct_framing",
    "broader-nextwave-13-missing_evidence_not_no",
    "broader-nextwave-14-human_reference_variant",
})
DIMENSIONS = ("Relevance", "Coherence", "Empathy", "Surprise", "Engagement", "Complexity")
MAX_CONCURRENCY = 2
CELL_WAIT_SECONDS = 120.0
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


def _disjoint(output_root: Path, *sources: Path) -> None:
    output = Path(os.path.abspath(output_root))
    _safe(output.parent, directory=True)
    for source in sources:
        source = _safe(Path(source))
        if output == source or output in source.parents or source in output.parents:
            raise ValueError("output root must be disjoint from every source and queue root")


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
    if type(value) is not dict:
        raise ValueError(f"{label} must be an object")
    return value


def _load(path: Path, digest: str, name: str) -> ModuleType:
    raw = stable(path)
    if sha256(raw) != digest:
        raise ValueError("pinned dependency drifted")
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


def _git_blob(repo: Path, commit: str, relative: str) -> bytes:
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("commit must be a full SHA-1")
    result = subprocess.run(["git", "-C", str(repo), "show", f"{commit}:{relative}"], capture_output=True, check=False)
    if result.returncode:
        raise ValueError("pinned Git blob is absent")
    return result.stdout


def _pinned(path: Path, digest: str, commit: str, relative: str, name: str) -> ModuleType:
    raw = stable(path)
    if sha256(raw) != digest or _git_blob(HERE.parents[1], commit, relative) != raw:
        raise ValueError("pinned dependency drifted or is not committed")
    return _load(path, digest, name)


def _sources() -> tuple[ModuleType, ModuleType, ModuleType]:
    freeze = _pinned(HERE.parent / FREEZE_ID / "study.py", FREEZE_SHA256, FREEZE_COMMIT, f"evaluation-results/{FREEZE_ID}/study.py", "_broader_sol_freeze")
    v4 = _pinned(V4, V4_SHA256, V4_COMMIT, f"evaluation-results/{V4_ID}/executor.py", "_broader_sol_v4")
    repo = HERE.parents[1]
    for relative, digest in RESULT_FILES.items():
        raw = stable(repo / relative)
        if sha256(raw) != digest or _git_blob(repo, RESULT_VERIFIER_COMMIT, relative) != raw:
            raise ValueError("completed Grok result dependency drifted or is not committed")
    verifier = _load(RESULT_VERIFIER, RESULT_VERIFIER_SHA256, "_broader_sol_result")
    return freeze, v4, verifier


def _targets(freeze: ModuleType, frozen_successor_path: Path, hanna_csv_path: Path) -> Mapping[str, Mapping[str, float]]:
    study, _harness, _frozen, _split, _parents = freeze._v3()._material(frozen_successor_path=Path(frozen_successor_path), hanna_csv_path=Path(hanna_csv_path))
    return freeze._v3().v2_module()._human_targets(study=study, frozen_successor_path=Path(frozen_successor_path), hanna_csv_path=Path(hanna_csv_path))


def _winner(result: Mapping[str, Any]) -> str:
    authority, selection, metrics = result.get("authority"), result.get("selection"), result.get("metrics")
    if (result.get("study_id") != RESULT_ID or not isinstance(authority, Mapping) or authority.get("selection") != "grok_development_only"
            or not isinstance(selection, Mapping) or not isinstance(selection.get("candidate_id"), str) or not isinstance(metrics, list)):
        raise ValueError("Grok result identity or authority drifted")
    candidates = {row.get("candidate_id") for row in metrics if isinstance(row, Mapping)}
    if candidates != {PARENT, *CHILDREN}:
        raise ValueError("Grok result candidate geometry drifted")
    winner = selection["candidate_id"]
    if winner == BASELINE or winner not in candidates:
        raise ValueError("Grok winner is not admitted for Sol validation")
    return winner


def _baseline_rows(freeze: ModuleType, schedule: Mapping[str, Any], targets: Mapping[str, Mapping[str, float]], materialization_root: Path, frozen_successor_path: Path, hanna_csv_path: Path) -> list[dict[str, Any]]:
    materialization_raw = stable(materialization_root / "materialization.json")
    if materialization_raw != canonical(strict(materialization_raw, "materialization")):
        raise ValueError("materialization must be canonical")
    if materialization_raw != stable(materialization_root / "materialization.json") or sha256(materialization_raw) != schedule.get("materialization_file_sha256"):
        raise ValueError("frozen materialization commitment drifted")
    materialization = strict(materialization_raw, "materialization")
    artifacts = materialization.get("artifacts")
    if (materialization.get("provider_calls_made") != 0 or materialization.get("process_launches") != 0
            or not isinstance(artifacts, Mapping)):
        raise ValueError("baseline materialization authority drifted")
    instruction = stable(materialization_root / "parent-instruction.bin")
    profile = stable(materialization_root / "parent-profile.bin")
    if artifacts.get("parent-instruction.bin") != sha256(instruction) or artifacts.get("parent-profile.bin") != sha256(profile):
        raise ValueError("baseline parent material binding drifted")
    source_freeze = freeze._v3().v2_module().parent_modules()[2]
    sources = source_freeze._source_material(frozen_successor_path=Path(frozen_successor_path), hanna_csv_path=Path(hanna_csv_path))
    candidate = {"candidate_id": BASELINE, "instruction_bytes": instruction, "profile_bytes": profile}
    rows: list[dict[str, Any]] = []
    for group in schedule["groups"]:
        item_id = group.get("item_id")
        target = targets.get(item_id)
        source = sources.get(item_id)
        if not isinstance(target, Mapping) or not isinstance(source, Mapping):
            raise ValueError("baseline source/target reconstruction drifted")
        payload_value = json.loads(source_freeze._payload_bytes(item=source, candidate=candidate).decode("utf-8"))
        payload_value["study_id"] = STUDY_ID
        payload = canonical(payload_value)
        key = {"study_id": STUDY_ID, "candidate_id": BASELINE, "prompt_group_id": group["prompt_group_id"], "item_id": item_id}
        rows.append({"cell_id": "broader-sol-" + sha256(key)[:16], "source_cell_id": None, "candidate_id": BASELINE, "prompt_group_id": group["prompt_group_id"], "item_id": item_id, "story_id": item_id, "payload_base64": base64.b64encode(payload).decode("ascii"), "payload_sha256": sha256(payload), "target": {key: float(target[key]) for key in DIMENSIONS}})
    if len(rows) != 7 or len({row["cell_id"] for row in rows}) != 7:
        raise ValueError("baseline seven-cell geometry drifted")
    return rows


def _rows(freeze: ModuleType, schedule: Mapping[str, Any], result: Mapping[str, Any], targets: Mapping[str, Mapping[str, float]], execution_root: Path, materialization_root: Path, frozen_successor_path: Path, hanna_csv_path: Path) -> tuple[dict[str, Any], ...]:
    winner = _winner(result)
    selected = {BASELINE, PARENT} if winner == PARENT else {BASELINE, PARENT, winner}
    cells = schedule.get("cells")
    groups = schedule.get("groups")
    if (schedule.get("study_id") != FREEZE_ID or not isinstance(cells, list) or not isinstance(groups, list)
            or len(groups) != 7 or {row.get("candidate_id") for row in cells if isinstance(row, Mapping)} != {PARENT, *CHILDREN}):
        raise ValueError("broader frozen schedule geometry drifted")
    rows = list(_baseline_rows(freeze, schedule, targets, materialization_root, frozen_successor_path, hanna_csv_path))
    for source in cells:
        if not isinstance(source, Mapping) or source.get("candidate_id") not in selected:
            continue
        payload = base64.b64decode(source.get("payload_base64", ""), validate=True)
        target = targets.get(source.get("item_id"))
        root = execution_root / str(source.get("cell_id"))
        if (sha256(payload) != source.get("payload_sha256") or not isinstance(target, Mapping)
                or stable(root / "outbound-payload.json") != payload):
            raise ValueError("Grok source payload/target binding drifted")
        rows.append({"cell_id": "broader-sol-" + str(source["cell_id"]), "source_cell_id": source["cell_id"], "candidate_id": source["candidate_id"], "prompt_group_id": source["prompt_group_id"], "item_id": source["item_id"], "story_id": source["item_id"], "payload_base64": source["payload_base64"], "payload_sha256": source["payload_sha256"], "target": {key: float(target[key]) for key in DIMENSIONS}})
    expected = 14 if winner == PARENT else 21
    if (len(rows) != expected or len({row["cell_id"] for row in rows}) != expected
            or any(sum(row["candidate_id"] == candidate for row in rows) != 7 for candidate in selected)):
        raise ValueError("Sol validation geometry drifted")
    return tuple(sorted(rows, key=lambda row: row["cell_id"]))


def _replay(verifier: ModuleType, *, frozen_root: Path, normalized_root: Path, materialization_root: Path, frozen_successor_path: Path, hanna_csv_path: Path, grok_execution_root: Path, grok_collector_path: Path) -> dict[str, Any]:
    return verifier.replay(frozen_root=frozen_root, normalized_root=normalized_root, materialization_root=materialization_root, frozen_successor_path=frozen_successor_path, hanna_csv_path=hanna_csv_path, output_root=grok_execution_root, collector_path=grok_collector_path)


def _resolve(*, frozen_root: Path, normalized_root: Path, materialization_root: Path, frozen_successor_path: Path, hanna_csv_path: Path, grok_execution_root: Path, grok_collector_path: Path, grok_result_path: Path, grok_result_commit: str) -> dict[str, Any]:
    freeze, _v4, verifier = _sources()
    schedule = freeze.validate_frozen_root(Path(frozen_root))
    result_raw = stable(Path(grok_result_path))
    if _git_blob(HERE.parents[1], grok_result_commit, RESULT_RELATIVE) != result_raw:
        raise ValueError("Grok result is not the exact committed Git blob")
    result = strict(result_raw, "Grok result")
    replayed = _replay(verifier, frozen_root=Path(frozen_root), normalized_root=Path(normalized_root), materialization_root=Path(materialization_root), frozen_successor_path=Path(frozen_successor_path), hanna_csv_path=Path(hanna_csv_path), grok_execution_root=Path(grok_execution_root), grok_collector_path=Path(grok_collector_path))
    if result.get("metrics") != replayed.get("metrics") or result.get("selection") != replayed.get("selection"):
        raise ValueError("committed Grok result does not independently replay")
    result_internal = result.get("result_internal_sha256")
    if not isinstance(result_internal, str) or not re.fullmatch(r"[0-9a-f]{64}", result_internal) or result_internal != replayed.get("result_internal_sha256"):
        raise ValueError("Grok result internal commitment drifted")
    rows = _rows(freeze, schedule, result, _targets(freeze, Path(frozen_successor_path), Path(hanna_csv_path)), _safe(Path(grok_execution_root), directory=True), Path(materialization_root), Path(frozen_successor_path), Path(hanna_csv_path))
    return {"rows": rows, "schedule": schedule, "result": result, "bindings": {"grok_result_commit": grok_result_commit, "grok_result_sha256": sha256(result_raw), "grok_result_internal_sha256": result_internal, "grok_collector_sha256": sha256(stable(Path(grok_collector_path))), "hanna_csv_sha256": sha256(stable(Path(hanna_csv_path)))}}


def _configured_base(resolution: Mapping[str, Any]) -> ModuleType:
    _freeze, v4, _verifier = _sources()
    base, _unused = v4._sources()
    rows, bindings = resolution["rows"], resolution["bindings"]
    with _configuration_lock:
        base.STUDY_ID = STUDY_ID
        base.ROWS = rows
        base.PUBLIC_RESULT_COMMIT = bindings["grok_result_commit"]
        base.SOURCE_RESULT_FILE_SHA256 = bindings["grok_result_sha256"]
        base.SOURCE_EXECUTOR_COMMIT = "independently_replayed_broader_grok_v2"
        base.SOURCE_EXECUTOR_SHA256 = bindings["grok_result_internal_sha256"]
        base.SCHEDULE_SHA256 = resolution["schedule"]["schedule_sha256"]
        base.COLLECTOR_SHA256 = bindings["grok_collector_sha256"]
        base.ALIAS_MANIFEST_SHA256 = "0" * 64
        base.RESULT_INTERNAL_SHA256 = bindings["grok_result_internal_sha256"]
        base.TARGET_CSV_SHA256 = bindings["hanna_csv_sha256"]
        base._validate_target = lambda row, _path: dict(row["target"])
        route = base._route
        base._route = lambda *args, **kwargs: _locked_route(route, *args, **kwargs)
        original_prepared = base._prepared
        def prepared(row: Mapping[str, Any], payload: bytes, schema: bytes, target: Mapping[str, float], route_value: Mapping[str, Any], evidence: Mapping[str, Any], acknowledgement: str) -> dict[str, bytes]:
            files = original_prepared(row, payload, schema, target, route_value, evidence, acknowledgement)
            value = json.loads(files["prepared.json"])
            source = dict(value["source"])
            source.pop("alias_manifest_sha256", None)
            source["completed_broader_grok_result_sha256"] = bindings["grok_result_sha256"]
            source["completed_broader_grok_result_internal_sha256"] = bindings["grok_result_internal_sha256"]
            value["source"] = source
            files["prepared.json"] = base.canonical(value)
            return files
        base._prepared = prepared
    return base


def _locked_route(route: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    with _route_load_lock:
        return route(*args, **kwargs)


def _acquire_slot(locks: Path, cell_id: str) -> Path:
    deadline = time.monotonic() + CELL_WAIT_SECONDS
    while time.monotonic() < deadline:
        for index in range(MAX_CONCURRENCY):
            path = locks / f"slot-{index}.lock"
            try:
                with path.open("x", encoding="ascii") as handle:
                    handle.write(cell_id)
                return path
            except FileExistsError:
                continue
        time.sleep(0.01)
    raise TimeoutError("global Sol two-slot semaphore did not become available")


def _release(path: Path | None) -> None:
    if path is not None and path.exists():
        _plain(path, directory=False)
        path.unlink()


def _terminal(root: Path) -> bool:
    return any((root / name).exists() for name in ("launch-intent.json", "execution-receipt.json", "result.json", "precontact-failure.json"))


def _claim_cell(locks: Path, root: Path, cell_id: str) -> Path:
    deadline = time.monotonic() + CELL_WAIT_SECONDS
    path = locks / (cell_id + ".lock")
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
    raise TimeoutError("same-cell execution claim did not become available")


def _locks(output_root: Path) -> Path:
    locks = output_root.parent / ("." + output_root.name + ".sol-validation-locks")
    locks.mkdir(exist_ok=True)
    _plain(locks, directory=True)
    return locks


def _execute_prepared(*, base: ModuleType, row: Mapping[str, Any], output_root: Path, queue_root: Path, authorization_acknowledgement_sha256: str, allow_remote: bool, locks: Path, broker_factory: Callable[[Path], Any] | None, call_codex: Callable[..., Any] | None) -> dict[str, Any]:
    root = output_root / row["cell_id"]
    claim = slot = None
    try:
        claim = _claim_cell(locks, root, row["cell_id"])
        slot = _acquire_slot(locks, row["cell_id"])
        return base.execute_one(output_root=output_root, cell_id=row["cell_id"], queue_root=queue_root, authorization_acknowledgement_sha256=authorization_acknowledgement_sha256, allow_remote=allow_remote, broker_factory=broker_factory, call_codex=call_codex)
    finally:
        _release(slot)
        _release(claim)


def prepare_all(*, output_root: Path, queue_root: Path, authorization_acknowledgement_sha256: str, broker_factory: Callable[[Path], Any] | None = None, **inputs: Any) -> dict[str, Any]:
    if Path(output_root).exists():
        raise ValueError("fresh output root required")
    _disjoint(Path(output_root), Path(queue_root), *(Path(value) for value in inputs.values() if isinstance(value, Path)))
    resolution = _resolve(**inputs)
    base = _configured_base(resolution)
    route, evidence, _v3 = base._route(Path(queue_root), broker_factory)
    Path(output_root).mkdir(parents=True)
    for row in resolution["rows"]:
        root = Path(output_root) / row["cell_id"]
        root.mkdir()
        payload = base64.b64decode(row["payload_base64"], validate=True)
        schema = base.canonical(json.loads(payload.decode("utf-8"))["response_schema"])
        for name, raw in base._prepared(row, payload, schema, row["target"], route, evidence, authorization_acknowledgement_sha256).items():
            base._write_new(root / name, raw)
    return {"study_id": STUDY_ID, "cells": len(resolution["rows"]), "groups": 7, "state": "prepared_no_contact", "provider_calls_made": 0, "process_launches": 0, "max_concurrency": MAX_CONCURRENCY, "authority": "descriptive_sol_validation_only"}


def execute_one(*, output_root: Path, queue_root: Path, authorization_acknowledgement_sha256: str, cell_id: str, allow_remote: bool, broker_factory: Callable[[Path], Any] | None = None, call_codex: Callable[..., Any] | None = None, **inputs: Any) -> dict[str, Any]:
    if allow_remote is not True:
        raise ValueError("execution requires explicit allow_remote=True")
    resolution = _resolve(**inputs)
    base = _configured_base(resolution)
    rows = {row["cell_id"]: row for row in resolution["rows"]}
    if cell_id not in rows:
        raise ValueError("unknown validation cell")
    if {path.name for path in Path(output_root).iterdir()} != set(rows):
        raise ValueError("prepared output inventory drifted")
    locks = _locks(Path(output_root))
    try:
        return _execute_prepared(base=base, row=rows[cell_id], output_root=Path(output_root), queue_root=Path(queue_root), authorization_acknowledgement_sha256=authorization_acknowledgement_sha256, allow_remote=True, locks=locks, broker_factory=broker_factory, call_codex=call_codex)
    finally:
        if locks.exists() and not any(locks.iterdir()):
            locks.rmdir()


def execute_wave(*, output_root: Path, queue_root: Path, authorization_acknowledgement_sha256: str, allow_remote: bool, broker_factory: Callable[[Path], Any] | None = None, call_codex: Callable[..., Any] | None = None, **inputs: Any) -> list[dict[str, Any]]:
    if allow_remote is not True:
        raise ValueError("execution requires explicit allow_remote=True")
    resolution = _resolve(**inputs)
    base = _configured_base(resolution)
    rows = resolution["rows"]
    if {path.name for path in Path(output_root).iterdir()} != {row["cell_id"] for row in rows}:
        raise ValueError("prepared output inventory drifted")
    locks = _locks(Path(output_root))
    def run(row: Mapping[str, Any]) -> dict[str, Any]:
        return _execute_prepared(base=base, row=row, output_root=Path(output_root), queue_root=Path(queue_root), authorization_acknowledgement_sha256=authorization_acknowledgement_sha256, allow_remote=True, locks=locks, broker_factory=broker_factory, call_codex=call_codex)
    try:
        with _wave_lock, ThreadPoolExecutor(max_workers=MAX_CONCURRENCY) as pool:
            return list(pool.map(run, rows))
    finally:
        if locks.exists() and not any(locks.iterdir()):
            locks.rmdir()


def _validate_contract(contract: Mapping[str, Any]) -> None:
    expected = {"format_version": 1, "study_id": STUDY_ID, "kind": "provider_free_dynamic_broader_sol_validation_preparation", "geometry": {"development_groups": 7, "sol_cells_if_parent_wins": 14, "sol_cells_if_descendant_wins": 21}, "authority": {"confirmation": "unopened", "endpoint_pooling": "forbidden", "generalization": "none", "promotion": "none", "runtime": "none", "selection": "grok_development_only_then_sol_descriptive"}, "pinned_dependencies": {"broader_freeze": {"commit": FREEZE_COMMIT, "study_sha256": FREEZE_SHA256}, "completed_grok_result": {"commit": RESULT_VERIFIER_COMMIT, "readme_sha256": RESULT_FILES[f"evaluation-results/{RESULT_ID}/README.md"], "result_sha256": RESULT_FILES[RESULT_RELATIVE], "contract_sha256": RESULT_FILES[f"evaluation-results/{RESULT_ID}/study-contract.json"], "verifier_sha256": RESULT_VERIFIER_SHA256, "test_sha256": RESULT_FILES["tests/test_hbq_human_alignment_optimizer_v5_f20_broader_development_grok_result_v2_v3_exec.py"]}, "sol_route": {"commit": V4_COMMIT, "executor_sha256": V4_SHA256}}, "replay_inputs": ["frozen_root", "normalized_root", "materialization_root", "frozen_successor_path", "hanna_csv_path", "grok_execution_root", "grok_collector_path", "grok_result_path", "grok_result_commit"]}
    if dict(contract) != expected:
        raise ValueError("package contract drifted or overclaims authority")


def validate_package() -> dict[str, Any]:
    expected = {"README.md", "study-contract.json", "executor.py"}
    if {path.name for path in HERE.iterdir() if path.name != "__pycache__"} != expected:
        raise ValueError("package inventory drifted")
    contract = strict(stable(HERE / "study-contract.json"), "study contract")
    _validate_contract(contract)
    return contract


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--prepare", action="store_true")
    mode.add_argument("--execute-wave", action="store_true")
    for name in ("output-root", "queue-root", "frozen-root", "normalized-root", "materialization-root", "frozen-successor", "hanna-csv", "grok-execution-root", "grok-collector", "grok-result"):
        parser.add_argument("--" + name, type=Path, required=True)
    for name in ("grok-result-commit", "authorization-acknowledgement-sha256"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--allow-remote", action="store_true")
    args = parser.parse_args(argv)
    validate_package()
    common = {"output_root": args.output_root, "queue_root": args.queue_root, "authorization_acknowledgement_sha256": args.authorization_acknowledgement_sha256, "frozen_root": args.frozen_root, "normalized_root": args.normalized_root, "materialization_root": args.materialization_root, "frozen_successor_path": args.frozen_successor, "hanna_csv_path": args.hanna_csv, "grok_execution_root": args.grok_execution_root, "grok_collector_path": args.grok_collector, "grok_result_path": args.grok_result, "grok_result_commit": args.grok_result_commit}
    if args.prepare:
        if args.allow_remote:
            parser.error("prepare forbids remote execution")
        value = prepare_all(**common)
    else:
        if not args.allow_remote:
            parser.error("execute-wave requires explicit remote authorization")
        value = execute_wave(**common, allow_remote=True)
    print(canonical(value).decode("utf-8"), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
