#!/usr/bin/env python3
"""Sol veto validation over the frozen desc16 Grok-qualified candidates."""
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
from collections.abc import Callable, Mapping
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import ModuleType
from typing import Any

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
STUDY_ID = "hbq-human-alignment-optimizer-v7-desc16-referent-evidence-sol-veto-exec-v1"
ANALYZER_ID = "hbq-human-alignment-optimizer-v7-desc16-referent-evidence-development-optimizer-v1"
ANALYZER = HERE.parent / ANALYZER_ID / "analyzer.py"
ANALYZER_CONTRACT = ANALYZER.parent / "study-contract.json"
ANALYZER_COMMIT = "bdf96b88a89d8daebcf4aaec75d43229a7ca2698"
ANALYZER_SHA256 = "6f219737c0979087c7ed3302dd391b4ed0228ddf33ec110586c390d4175c30be"
ANALYZER_CONTRACT_SHA256 = "8a0dc402deb0ede247dde73654cbe65dc79d6466d85a2c4b5ed5e9dfc2001fb6"
GROK_EXECUTOR_ID = "hbq-human-alignment-optimizer-v7-desc16-referent-evidence-grok-exec-v1"
GROK_EXECUTOR = HERE.parent / GROK_EXECUTOR_ID / "executor.py"
GROK_EXECUTOR_COMMIT = "989f1d6d438812d369d1344a706ee42cca105848"
GROK_EXECUTOR_SHA256 = "33ecfb6806364a121df9f383be343985d0f667411cfdba553e1a290091312f88"
RESULT_FILE_SHA256 = "53dd32cc52c2f7975f2562e172f735576ae755bf702f3ee687f8e0418c2bdd54"
RESULT_INTERNAL_SHA256 = "e0c00248520c18676d5ea760c8464195b9b2ea0863f16e2c6cb840ac027f2f9a"
SOURCE_COMMIT = "2fb8b1e1dd9acc0d0869c3ebf51c384653ac3ee5"
CANDIDATES_ID = "hbq-human-alignment-optimizer-v7-desc16-referent-evidence-candidates-v1"
PARENT_SOL_RESULT = HERE.parent / "hbq-human-alignment-optimizer-v6-desc15-referent-sol-veto-result-v1" / "result.json"
PARENT_SOL_RESULT_COMMIT = "79a90ad72ec96d8dcc391f3e8036bfee5b5342d8"
PARENT_SOL_RESULT_SHA256 = "23988d59a94988b2604317786f2874fa59b0a411c9aafa677f9be28df32e2e71"
PARENT_CANDIDATE_ID = "broader-nextwave-20-missing_evidence_not_no-referent-evidence"
PARENT_SOL_EQUAL_GROUP_MAE = 1.0101190476190476
BROADER_ID = "hbq-human-alignment-optimizer-v5-f20-broader-development-freeze-v1"
BROADER = HERE.parent / BROADER_ID
BROADER_COMMIT = "436da1ef3f8cf239203ac6a80afe8f72708c0415"
BROADER_HASHES = {
    BROADER / "study.py": "507e3c0bec1af6d0acef6e806cf6874a2633e892c9bbf567728f436af30f84bf",
    BROADER / "study-contract.json": "3b31c9b0d5ec4c71d6b562045dcd52b2646380cb318d72b83d2119e760543a77",
    BROADER / "README.md": "5f8956e96df28ddfe37533e631c163f1cdbf711e820e05e2607618975bf0e75f",
}
V4_ID = "hbq-human-alignment-optimizer-v5-f20-nextwave-sol6-validation-exec-v4-threadsafe-route-load"
V4 = HERE.parent / V4_ID / "executor.py"
V4_COMMIT = "a95b9df6668da612af26a25c8abd8e8f5cb4027d"
V4_SHA256 = "ef2b44a5457292d71151a4ab48346a298956acb8126106d0cc186696efeb537c"
QUALIFIED_CHILDREN = (
    "broader-nextwave-22-missing_evidence_not_no-referent-contradiction-threshold",
    "broader-nextwave-24-missing_evidence_not_no-referent-dimension-isolation",
)
DIMENSIONS = ("Relevance", "Coherence", "Empathy", "Surprise", "Engagement", "Complexity")
MAX_CONCURRENCY = 10
CELL_WAIT_SECONDS = 120.0
_configuration_lock = threading.Lock()
_route_load_lock = threading.Lock()
_wave_lock = threading.Lock()


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
    identity = lambda item: (item.st_dev, item.st_ino, stat.S_IFMT(item.st_mode), item.st_size)
    if identity(before) != identity(opened) or identity(opened) != identity(after):
        raise ValueError("stable read drift")
    return raw


def _tree_commitment(path: Path) -> str:
    root = _safe(Path(path))
    if root.is_file():
        return sha256({"path": root.name, "type": "file", "sha256": sha256(stable(root))})
    records: list[dict[str, str]] = []
    for child in sorted(root.rglob("*"), key=lambda value: value.relative_to(root).as_posix()):
        is_directory = stat.S_ISDIR(os.lstat(child).st_mode)
        _plain(child, directory=is_directory)
        relative = child.relative_to(root).as_posix()
        if child.is_dir():
            records.append({"path": relative, "type": "directory"})
        else:
            records.append({"path": relative, "type": "file", "sha256": sha256(stable(child))})
    return sha256({"path": root.name, "type": "directory", "records": records})


def _input_commitments(inputs: Mapping[str, Path]) -> dict[str, str]:
    return {name: _tree_commitment(path) for name, path in sorted(inputs.items())}


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
    if type(value) is not dict or canonical(value) != raw:
        raise ValueError(f"noncanonical {label}")
    return value


def _blob(commit: str, relative: str) -> bytes:
    if re.fullmatch(r"[0-9a-f]{40}", commit) is None:
        raise ValueError("commit must be a full SHA-1")
    result = subprocess.run(["git", "-C", str(REPO), "show", f"{commit}:{relative}"], capture_output=True, check=False)
    if result.returncode:
        raise ValueError("pinned Git blob is absent")
    return result.stdout


def _load(path: Path, name: str) -> ModuleType:
    raw = stable(path)
    module = ModuleType(name)
    module.__file__ = str(path)
    sys.modules[name] = module
    try:
        exec(compile(raw, str(path), "exec"), module.__dict__)  # noqa: S102 - exact pinned source replay
    finally:
        sys.modules.pop(name, None)
    if stable(path) != raw:
        raise ValueError("pinned dependency changed during load")
    return module


def _pinned(path: Path, digest: str, commit: str, relative: str, name: str) -> ModuleType:
    raw = stable(path)
    if sha256(raw) != digest or _blob(commit, relative) != raw:
        raise ValueError("pinned dependency drifted or is not committed")
    return _load(path, name)


def broader_study() -> ModuleType:
    for path, digest in BROADER_HASHES.items():
        if sha256(stable(path)) != digest or _blob(BROADER_COMMIT, path.relative_to(REPO).as_posix()) != stable(path):
            raise ValueError("broader development dependency drifted")
    return _load(BROADER / "study.py", "_desc16_sol_broader")


def sol_v4() -> ModuleType:
    return _pinned(V4, V4_SHA256, V4_COMMIT, f"evaluation-results/{V4_ID}/executor.py", "_desc16_sol_v4")


def grok_executor() -> ModuleType:
    return _pinned(
        GROK_EXECUTOR,
        GROK_EXECUTOR_SHA256,
        GROK_EXECUTOR_COMMIT,
        f"evaluation-results/{GROK_EXECUTOR_ID}/executor.py",
        "_desc16_sol_grok_executor",
    )


def result_analyzer() -> ModuleType:
    module = _pinned(
        ANALYZER,
        ANALYZER_SHA256,
        ANALYZER_COMMIT,
        f"evaluation-results/{ANALYZER_ID}/analyzer.py",
        "_desc16_sol_result_analyzer",
    )
    contract = stable(ANALYZER_CONTRACT)
    if (
        sha256(contract) != ANALYZER_CONTRACT_SHA256
        or _blob(ANALYZER_COMMIT, f"evaluation-results/{ANALYZER_ID}/study-contract.json") != contract
    ):
        raise ValueError("committed Grok result analyzer contract drifted")
    module.validate_package()
    if module.STUDY_ID != ANALYZER_ID:
        raise ValueError("committed Grok result analyzer identity drifted")
    return module


def _targets(broader: ModuleType, frozen_successor_path: Path, hanna_csv_path: Path) -> Mapping[str, Mapping[str, float]]:
    study, _harness, _freeze, _split, _parents = broader._v3()._material(frozen_successor_path=Path(frozen_successor_path), hanna_csv_path=Path(hanna_csv_path))
    return broader._v3().v2_module()._human_targets(study=study, frozen_successor_path=Path(frozen_successor_path), hanna_csv_path=Path(hanna_csv_path))


def _parent_sol_reference() -> dict[str, Any]:
    raw = stable(PARENT_SOL_RESULT)
    relative = PARENT_SOL_RESULT.relative_to(REPO).as_posix()
    value = strict(raw, "frozen descendant-15 Sol veto result")
    validation = value.get("sol_validation")
    metrics = validation.get("metrics") if isinstance(validation, Mapping) else None
    if not isinstance(metrics, list):
        raise TypeError("frozen descendant-15 Sol result lacks metrics")
    parent = [row for row in metrics if isinstance(row, Mapping) and row.get("candidate_id") == PARENT_CANDIDATE_ID]
    if (
        sha256(raw) != PARENT_SOL_RESULT_SHA256
        or _blob(PARENT_SOL_RESULT_COMMIT, relative) != raw
        or value.get("study_id") != "hbq-human-alignment-optimizer-v6-desc15-referent-sol-veto-result-v1"
        or not isinstance(validation, Mapping)
        or validation.get("parent_candidate_id") != "broader-nextwave-13-missing_evidence_not_no"
        or len(parent) != 1
        or parent[0].get("equal_group_mae") != PARENT_SOL_EQUAL_GROUP_MAE
    ):
        raise ValueError("frozen descendant-15 Sol parent reference drifted")
    return {
        "candidate_id": PARENT_CANDIDATE_ID,
        "equal_group_mae": PARENT_SOL_EQUAL_GROUP_MAE,
        "result_commit": PARENT_SOL_RESULT_COMMIT,
        "result_file_sha256": PARENT_SOL_RESULT_SHA256,
    }


def _result_projection(
    *,
    analyzer: ModuleType,
    freeze_root: Path,
    development_freeze_root: Path,
    normalized_root: Path,
    materialization_root: Path,
    frozen_successor_path: Path,
    hanna_csv_path: Path,
    grok_execution_root: Path,
    grok_collector_path: Path,
    grok_result_path: Path,
) -> tuple[dict[str, Any], dict[str, Any], bytes]:
    result_raw = stable(Path(grok_result_path))
    if sha256(result_raw) != RESULT_FILE_SHA256:
        raise ValueError("wrong immutable development optimizer result file")
    persisted = strict(result_raw, "development optimizer result")
    replayed = analyzer.analyze(
        freeze_root=Path(freeze_root), development_freeze_root=Path(development_freeze_root),
        normalized_root=Path(normalized_root), materialization_root=Path(materialization_root),
        frozen_successor_path=Path(frozen_successor_path), hanna_csv_path=Path(hanna_csv_path),
        output_root=Path(grok_execution_root), collector_path=Path(grok_collector_path),
    )
    if persisted != replayed:
        raise ValueError("optimizer result differs from independent replay")
    qualification, source = replayed.get("qualification"), replayed.get("source")
    if (
        replayed.get("study_id") != ANALYZER_ID
        or replayed.get("result_sha256") != RESULT_INTERNAL_SHA256
        or not isinstance(qualification, Mapping)
        or qualification.get("frozen_before_sol") is not True
        or tuple(qualification.get("qualifiers", ())) != QUALIFIED_CHILDREN
        or qualification.get("parent_candidate_id") != PARENT_CANDIDATE_ID
        or not isinstance(source, Mapping)
        or source.get("collector_sha256") != "83cdb82482a6b1b2a23a6146ddb1fd8ec4f7387d4feb232eda0a1119136246b9"
        or source.get("executor_sha256") != GROK_EXECUTOR_SHA256
    ):
        raise ValueError("optimizer result authority or frozen qualifiers drifted")
    schedule = strict(stable(Path(grok_execution_root) / "schedule.json"), "persisted Grok schedule")
    expected = grok_executor().frozen_schedule(Path(freeze_root))
    if schedule != expected or schedule.get("study_id") != GROK_EXECUTOR_ID:
        raise ValueError("Grok schedule differs from immutable descendant-16 freeze")
    return schedule, replayed, result_raw


def _rows(
    *,
    schedule: Mapping[str, Any],
    targets: Mapping[str, Mapping[str, float]],
    grok_execution_root: Path,
) -> tuple[dict[str, Any], ...]:
    candidate_ids = {row.get("candidate_id") for row in schedule.get("candidates", []) if isinstance(row, Mapping)}
    if not set(QUALIFIED_CHILDREN).issubset(candidate_ids):
        raise ValueError("exact Grok schedule is missing a frozen qualifier")
    cells = schedule.get("cells")
    if not isinstance(cells, list) or len(cells) != 52:
        raise ValueError("Grok source cell geometry drifted")
    pairs = {(row.get("prompt_group_id"), row.get("item_id")) for row in cells}
    if len(pairs) != 13 or len({group for group, _item in pairs}) != 7:
        raise ValueError("Grok development item geometry drifted")
    rows: list[dict[str, Any]] = []
    for source in cells:
        if not isinstance(source, Mapping) or source.get("candidate_id") not in QUALIFIED_CHILDREN:
            continue
        try:
            payload = base64.b64decode(source["payload_base64"], validate=True)
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError("Grok source payload is invalid") from error
        target = targets.get(source.get("item_id"))
        root = Path(grok_execution_root) / str(source.get("cell_id"))
        if (sha256(payload) != source.get("payload_sha256") or not isinstance(target, Mapping)
                or stable(root / "outbound-payload.json") != payload):
            raise ValueError("observed Grok source payload binding drifted")
        key = {"study_id": STUDY_ID, "source_cell_id": source["cell_id"]}
        rows.append({
            "cell_id": "desc16-sol-veto-" + sha256(key)[:16], "source_cell_id": source["cell_id"],
            "candidate_id": source["candidate_id"], "prompt_group_id": source["prompt_group_id"], "item_id": source["item_id"], "story_id": source["item_id"],
            "payload_base64": source["payload_base64"], "payload_sha256": source["payload_sha256"],
            "payload_parity": "observed_exact_grok_outbound_bytes", "target": {dimension: float(target[dimension]) for dimension in DIMENSIONS},
        })
    expected_cells = len(QUALIFIED_CHILDREN) * len(pairs)
    if (len(rows) != expected_cells or len({row["cell_id"] for row in rows}) != expected_cells
            or {row["candidate_id"] for row in rows} != set(QUALIFIED_CHILDREN)
            or any({(row["prompt_group_id"], row["item_id"]) for row in rows if row["candidate_id"] == candidate} != pairs for candidate in QUALIFIED_CHILDREN)):
        raise ValueError("derived Sol veto geometry drifted")
    return tuple(sorted(rows, key=lambda row: row["cell_id"]))


def _resolve(
    *,
    freeze_root: Path,
    development_freeze_root: Path,
    normalized_root: Path,
    materialization_root: Path,
    frozen_successor_path: Path,
    hanna_csv_path: Path,
    grok_execution_root: Path,
    grok_collector_path: Path,
    grok_result_path: Path,
) -> dict[str, Any]:
    replay_inputs = {
        "freeze_root": Path(freeze_root), "development_freeze_root": Path(development_freeze_root),
        "normalized_root": Path(normalized_root), "materialization_root": Path(materialization_root),
        "frozen_successor_path": Path(frozen_successor_path), "hanna_csv_path": Path(hanna_csv_path),
        "grok_execution_root": Path(grok_execution_root), "grok_collector_path": Path(grok_collector_path), "grok_result_path": Path(grok_result_path),
    }
    committed_inputs = _input_commitments(replay_inputs)
    grok_executor().frozen_schedule(Path(freeze_root))
    broader = broader_study()
    broader.validate_frozen_root(Path(development_freeze_root))
    analyzer = result_analyzer()
    schedule, replayed, result_raw = _result_projection(
        analyzer=analyzer, freeze_root=Path(freeze_root), development_freeze_root=Path(development_freeze_root),
        normalized_root=Path(normalized_root), materialization_root=Path(materialization_root),
        frozen_successor_path=Path(frozen_successor_path), hanna_csv_path=Path(hanna_csv_path),
        grok_execution_root=Path(grok_execution_root), grok_collector_path=Path(grok_collector_path), grok_result_path=Path(grok_result_path),
    )
    if _input_commitments(replay_inputs) != committed_inputs:
        raise ValueError("replay inputs changed during independent Grok result resolution")
    targets = _targets(broader, Path(frozen_successor_path), Path(hanna_csv_path))
    parent_sol_reference = _parent_sol_reference()
    rows = _rows(schedule=schedule, targets=targets, grok_execution_root=Path(grok_execution_root))
    hanna_csv_sha256 = sha256(stable(Path(hanna_csv_path)))
    if _input_commitments(replay_inputs) != committed_inputs:
        raise ValueError("replay inputs changed during Sol target/row reconstruction")
    return {
        "rows": rows, "schedule": schedule, "qualification": replayed["qualification"], "parent_sol_reference": parent_sol_reference,
        "bindings": {
            "result_analyzer_commit": ANALYZER_COMMIT, "result_analyzer_sha256": ANALYZER_SHA256,
            "result_analyzer_contract_sha256": ANALYZER_CONTRACT_SHA256, "grok_result_sha256": sha256(result_raw),
            "grok_result_internal_sha256": replayed["result_sha256"],
            "grok_execution_commit": GROK_EXECUTOR_COMMIT,
            "grok_executor_sha256": replayed["source"]["executor_sha256"],
            "grok_collector_sha256": replayed["source"]["collector_sha256"],
            "hanna_csv_sha256": hanna_csv_sha256,
            "replay_input_commitments": committed_inputs,
            "parent_sol_reference": parent_sol_reference,
        },
    }


def _locked_route(route: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    with _route_load_lock:
        return route(*args, **kwargs)


def _configured_base(resolution: Mapping[str, Any]) -> ModuleType:
    v4 = sol_v4()
    base, _unused = v4._sources()
    rows, bindings = resolution["rows"], resolution["bindings"]
    with _configuration_lock:
        base.STUDY_ID = STUDY_ID
        base.ROWS = rows
        base.PUBLIC_RESULT_COMMIT = bindings["result_analyzer_commit"]
        base.SOURCE_RESULT_FILE_SHA256 = bindings["grok_result_sha256"]
        base.SOURCE_EXECUTOR_COMMIT = bindings["grok_execution_commit"]
        base.SOURCE_EXECUTOR_SHA256 = bindings["grok_executor_sha256"]
        base.SCHEDULE_SHA256 = resolution["schedule"]["schedule_sha256"]
        base.COLLECTOR_SHA256 = bindings["grok_collector_sha256"]
        base.ALIAS_MANIFEST_SHA256 = "0" * 64
        base.RESULT_INTERNAL_SHA256 = bindings["grok_result_internal_sha256"]
        base.TARGET_CSV_SHA256 = bindings["hanna_csv_sha256"]
        base._validate_target = lambda row, _path: dict(row["target"])
        route = base._route

        def frozen_route(*args: Any, **kwargs: Any) -> tuple[dict[str, Any], dict[str, Any], ModuleType]:
            route_value, evidence, v3 = _locked_route(route, *args, **kwargs)
            route_value, evidence = v4._frozen_route(route_value, evidence, v3, require_unexpired=True)
            return route_value, evidence, v3

        base._route = frozen_route
        original_prepared = base._prepared

        def prepared(row: Mapping[str, Any], payload: bytes, schema: bytes, target: Mapping[str, float], route_value: Mapping[str, Any], evidence: Mapping[str, Any], acknowledgement: str) -> dict[str, bytes]:
            files = original_prepared(row, payload, schema, target, route_value, evidence, acknowledgement)
            value = strict(files["prepared.json"], "inherited Sol preparation")
            source = dict(value["source"])
            source.pop("alias_manifest_sha256", None)
            source["independently_replayed_grok_result_sha256"] = bindings["grok_result_sha256"]
            source["independently_replayed_grok_result_internal_sha256"] = bindings["grok_result_internal_sha256"]
            source["result_analyzer_commit"] = bindings["result_analyzer_commit"]
            source["result_analyzer_sha256"] = bindings["result_analyzer_sha256"]
            source["result_analyzer_contract_sha256"] = bindings["result_analyzer_contract_sha256"]
            source["replay_input_commitments"] = bindings["replay_input_commitments"]
            source["grok_payload_parity"] = row["payload_parity"]
            source["frozen_grok_qualifiers"] = list(QUALIFIED_CHILDREN)
            source["sol_role"] = "veto_only_no_outside_candidate_substitution"
            source["parent_sol_reference"] = bindings["parent_sol_reference"]
            value["source"] = source
            files["prepared.json"] = base.canonical(value)
            return files

        base._prepared = prepared
    return base


def _output_inventory(output_root: Path, rows: tuple[Mapping[str, Any], ...]) -> dict[str, Path]:
    root = _safe(Path(output_root), directory=True)
    expected = {str(row["cell_id"]) for row in rows}
    entries = {path.name: path for path in root.iterdir()}
    if set(entries) != expected:
        raise ValueError("prepared output inventory drifted")
    for cell in entries.values():
        _plain(cell, directory=True)
    return entries


def _prepared_inventory(
    base: ModuleType,
    output_root: Path,
    rows: tuple[Mapping[str, Any], ...],
    *,
    completed: bool = False,
) -> None:
    entries = _output_inventory(output_root, rows)
    for row in rows:
        cell = entries[str(row["cell_id"])]
        base._inventory(cell, completed=completed)


def _acquire_slot(locks: Path, cell_id: str) -> Path:
    deadline = time.monotonic() + CELL_WAIT_SECONDS
    while time.monotonic() < deadline:
        for index in range(MAX_CONCURRENCY):
            path = locks / f"slot-{index}.lock"
            try:
                with path.open("x", encoding="ascii") as handle:
                    handle.write(cell_id)
                return path
            except (FileExistsError, PermissionError):
                continue
        time.sleep(0.01)
    raise TimeoutError("global Sol ten-slot semaphore did not become available")


def _release(path: Path | None) -> None:
    if path is None:
        return
    for attempt in range(40):
        try:
            if path.exists():
                _plain(path, directory=False)
                path.unlink()
            return
        except PermissionError:
            if attempt == 39:
                raise
            time.sleep(0.01)


def _terminal_state(base: ModuleType, root: Path, row: Mapping[str, Any]) -> bool:
    root = _safe(root, directory=True)
    names = {path.name for path in root.iterdir()}
    terminal = {"launch-intent.json", "execution-receipt.json", "result.json", "precontact-failure.json"} & names
    if not terminal:
        return False
    raise ValueError("terminal evidence requires a fresh root or manual reconciliation")


def _claim_cell(locks: Path, base: ModuleType, root: Path, row: Mapping[str, Any]) -> Path:
    deadline = time.monotonic() + CELL_WAIT_SECONDS
    cell_id = str(row["cell_id"])
    path = locks / (cell_id + ".lock")
    while time.monotonic() < deadline:
        if _terminal_state(base, root, row):
            raise ValueError("no resend: cell already has terminal launch evidence")
        try:
            with path.open("x", encoding="ascii") as handle:
                handle.write(cell_id)
            if _terminal_state(base, root, row):
                _release(path)
                raise ValueError("no resend: cell already has terminal launch evidence")
            return path
        except FileExistsError:
            time.sleep(0.01)
    raise TimeoutError("same-cell execution claim did not become available")


def _locks(output_root: Path) -> Path:
    locks = output_root.parent / ("." + output_root.name + ".desc16-sol-veto-locks")
    locks.mkdir(exist_ok=True)
    _plain(locks, directory=True)
    return locks


def _execute_prepared(
    *,
    base: ModuleType,
    row: Mapping[str, Any],
    output_root: Path,
    queue_root: Path,
    authorization_acknowledgement_sha256: str,
    allow_remote: bool,
    locks: Path,
    broker_factory: Callable[[Path], Any] | None,
    call_codex: Callable[..., Any] | None,
) -> dict[str, Any]:
    root = output_root / row["cell_id"]
    claim = slot = None
    try:
        claim = _claim_cell(locks, base, root, row)
        slot = _acquire_slot(locks, str(row["cell_id"]))
        return base.execute_one(
            output_root=output_root, cell_id=row["cell_id"], queue_root=queue_root,
            authorization_acknowledgement_sha256=authorization_acknowledgement_sha256, allow_remote=allow_remote,
            broker_factory=broker_factory, call_codex=call_codex,
        )
    finally:
        _release(slot)
        _release(claim)


def prepare_all(
    *,
    output_root: Path,
    queue_root: Path,
    authorization_acknowledgement_sha256: str,
    broker_factory: Callable[[Path], Any] | None = None,
    **inputs: Any,
) -> dict[str, Any]:
    validate_package()
    if Path(output_root).exists():
        raise ValueError("fresh output root required")
    required = {
        "freeze_root", "development_freeze_root", "normalized_root", "materialization_root",
        "frozen_successor_path", "hanna_csv_path", "grok_execution_root", "grok_collector_path", "grok_result_path",
    }
    if set(inputs) != required:
        raise ValueError("exact independently replayed Grok inputs are required")
    _disjoint(Path(output_root), HERE, REPO, Path(queue_root), *(Path(value) for value in inputs.values()))
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
    return {
        "format_version": 1, "study_id": STUDY_ID, "kind": "prepared_derived_desc16_referent_evidence_sol_veto_cells",
        "cells": len(resolution["rows"]), "groups": len({row["prompt_group_id"] for row in resolution["rows"]}), "provider_calls_made": 0, "process_launches": 0, "max_concurrency": MAX_CONCURRENCY,
        "authority": "exact_grok_payload_replay_then_sol_veto_only",
    }


def execute_one(
    *,
    output_root: Path,
    queue_root: Path,
    authorization_acknowledgement_sha256: str,
    cell_id: str,
    allow_remote: bool,
    broker_factory: Callable[[Path], Any] | None = None,
    call_codex: Callable[..., Any] | None = None,
    **inputs: Any,
) -> dict[str, Any]:
    validate_package()
    if allow_remote is not True:
        raise ValueError("execution requires explicit allow_remote=True")
    resolution = _resolve(**inputs)
    base = _configured_base(resolution)
    rows = {row["cell_id"]: row for row in resolution["rows"]}
    if cell_id not in rows:
        raise ValueError("unknown validation cell")
    _disjoint(Path(output_root), HERE, REPO, Path(queue_root), *(Path(value) for value in inputs.values()))
    _prepared_inventory(base, Path(output_root), tuple(rows.values()))
    locks = _locks(Path(output_root))
    try:
        return _execute_prepared(
            base=base, row=rows[cell_id], output_root=Path(output_root), queue_root=Path(queue_root),
            authorization_acknowledgement_sha256=authorization_acknowledgement_sha256, allow_remote=True, locks=locks,
            broker_factory=broker_factory, call_codex=call_codex,
        )
    finally:
        if locks.exists() and not any(locks.iterdir()):
            locks.rmdir()


def execute_wave(
    *,
    output_root: Path,
    queue_root: Path,
    authorization_acknowledgement_sha256: str,
    allow_remote: bool,
    broker_factory: Callable[[Path], Any] | None = None,
    call_codex: Callable[..., Any] | None = None,
    **inputs: Any,
) -> list[dict[str, Any]]:
    validate_package()
    if allow_remote is not True:
        raise ValueError("execution requires explicit allow_remote=True")
    resolution = _resolve(**inputs)
    base = _configured_base(resolution)
    rows = resolution["rows"]
    _disjoint(Path(output_root), HERE, REPO, Path(queue_root), *(Path(value) for value in inputs.values()))
    _prepared_inventory(base, Path(output_root), rows)
    locks = _locks(Path(output_root))

    def run(row: Mapping[str, Any]) -> dict[str, Any]:
        return _execute_prepared(
            base=base, row=row, output_root=Path(output_root), queue_root=Path(queue_root),
            authorization_acknowledgement_sha256=authorization_acknowledgement_sha256, allow_remote=True, locks=locks,
            broker_factory=broker_factory, call_codex=call_codex,
        )

    try:
        pending = tuple(row for row in rows if not _terminal_state(base, Path(output_root) / str(row["cell_id"]), row))
        with _wave_lock, ThreadPoolExecutor(max_workers=MAX_CONCURRENCY) as pool:
            return list(pool.map(run, pending))
    finally:
        if locks.exists() and not any(locks.iterdir()):
            locks.rmdir()


def _validated_reported_record(
    record: Mapping[str, Any],
    *,
    identity: Mapping[str, Any],
    settings: Mapping[str, Any],
    projection: Mapping[str, Any],
) -> dict[str, Any]:
    if set(record) != {"command", "provider_artifacts", "reported"}:
        raise ValueError("Codex record field set drifted")
    reported = record.get("reported")
    required = {"model", "provider", "reasoning_effort", "session_id"}
    if not isinstance(reported, Mapping) or set(reported) != required:
        raise ValueError("Codex reported identity field set drifted")
    if any(value is not None and (not isinstance(value, str) or not value) for value in reported.values()):
        raise ValueError("Codex reported identity value is invalid")
    provider_attested = settings.get("provider_attested")
    if type(provider_attested) is not bool:
        raise TypeError("Codex provider attestation flag is invalid")
    if not provider_attested and any(reported[key] is not None for key in ("model", "provider", "reasoning_effort")):
        raise ValueError("Codex record claims unattested provider identity")
    if reported["model"] != identity.get("provider_reported_model"):
        raise ValueError("Codex reported model differs from lifecycle identity")
    reasoning_attested = identity.get("reasoning_attested")
    if (
        type(reasoning_attested) is not bool
        or (reported["reasoning_effort"] is None) != (reasoning_attested is False)
        or (reported["reasoning_effort"] is not None and reported["reasoning_effort"] != settings.get("local_effective_reasoning_effort"))
    ):
        raise ValueError("Codex reported reasoning differs from lifecycle identity")
    if reported["provider"] is not None and reported["provider"] != identity.get("provider"):
        raise ValueError("Codex reported provider differs from lifecycle identity")
    allowed_sessions = {None, projection.get("thread_id"), identity.get("session_id")}
    if reported["session_id"] not in allowed_sessions:
        raise ValueError("Codex reported session differs from event/receipt identity")
    return dict(reported)


def _admit_completed_cell(
    base: ModuleType,
    v4: ModuleType,
    row: Mapping[str, Any],
    root: Path,
    acknowledgement_sha256: str,
) -> dict[str, Any]:
    base._inventory(root, completed=True)
    prepared = base._canonical_json(root / "prepared.json", "prepared")
    acknowledgement = base._canonical_json(root / "authorization-acknowledgement.json", "acknowledgement")
    proof = base._canonical_json(root / "zero-charge-route-proof.json", "route proof")
    target_file = base._canonical_json(root / "target-vector.json", "target vector")
    intent = base._canonical_json(root / "launch-intent.json", "launch intent")
    receipt = base._canonical_json(root / "execution-receipt.json", "receipt")
    payload = base.stable(root / "outbound-payload.json")
    schema = base.stable(root / "response-schema.json")
    final = base.stable(root / "raw-codex-final-response.bin")
    events = base.stable(root / "raw-codex-events.bin")
    response_events = base.stable(root / "responses" / "batch-0001.attempt-0001.events.jsonl")
    stderr = base.stable(root / "raw-codex-stderr.bin")
    record = base._canonical_json(root / "codex-record.json", "Codex record")
    settings = base._canonical_json(root / "effective-settings.json", "effective settings")
    v3 = base._load_v3()
    projection = v3._codex_event_projection(events, v3._load_parse_codex_events())
    answer = base._validate_answer(base._json(root / "raw-codex-final-response.bin", "final response"))
    identity = receipt.get("identity", {})
    route, evidence = v4._frozen_route(proof.get("route"), prepared.get("route_evidence"), v3, require_unexpired=False)
    expected = base._prepared(row, payload, schema, row["target"], route, evidence, acknowledgement_sha256)
    expected_settings = {
        "requested_model": "gpt-5.6-sol",
        "local_effective_model": "gpt-5.6-sol",
        "requested_reasoning_effort": "high",
        "local_effective_reasoning_effort": "high",
        "tools_enabled": False,
        "web_search_enabled": False,
        "subagents_enabled": False,
        "provider_attested": False,
        "event_projection": projection,
        "route_name": route["name"],
        "codex_command_identity": route["codex_command_identity"],
    }
    expected_record = {
        "command": v3._expected_codex_command(route["codex_command"][0], root),
        "provider_artifacts": {
            "codex_events": {
                "path": "responses/batch-0001.attempt-0001.events.jsonl",
                "bytes": len(events),
                "sha256": sha256(events),
            },
            "codex_stderr": {
                "path": "raw-codex-stderr.bin",
                "bytes": len(stderr),
                "sha256": sha256(stderr),
            },
        },
    }
    expected_identity = {
        "provider": "openai_codex",
        "route_name": route["name"],
        "requested_model": "gpt-5.6-sol",
        "requested_reasoning_effort": "high",
        "effective_model": "gpt-5.6-sol",
        "provider_reported_model": None,
        "reasoning_attested": False,
        "transport_identity": "codex_chatgpt_subscription_exec_tool_free_v3",
        "native_endpoint_contact_cardinality": "unproven",
        "thread_id": projection.get("thread_id"),
        "session_id": f"local-codex-thread-session:{projection.get('thread_id')}",
        "contact_id": f"unproven-native-endpoint-contact-for-local-thread:{projection.get('thread_id')}",
    }
    expected_intent = {
        "format_version": 1,
        "study_id": STUDY_ID,
        "kind": "process_launch_intent_not_native_contact",
        "cell_id": row["cell_id"],
        "prepared_sha256": sha256(prepared),
    }
    expected_receipt = {
        "format_version": 1,
        "study_id": STUDY_ID,
        "kind": "local_codex_lifecycle_receipt",
        "cell": dict(row),
        "process_launches": 1,
        "provider_calls_made": None,
        "native_endpoint_contact_cardinality": "unproven",
        "internal_retry_cardinality": "unproven",
        "request_sha256": sha256(payload),
        "response_schema_sha256": sha256(schema),
        "raw_events_sha256": sha256(events),
        "raw_stderr_sha256": sha256(stderr),
        "final_response_sha256": sha256(final),
        "route_evidence": evidence,
        "effective_settings_sha256": sha256(settings),
        "launch_intent_sha256": sha256(base.stable(root / "launch-intent.json")),
        "identity": expected_identity,
        "human_score_projection": answer,
    }
    reported = _validated_reported_record(record, identity=identity, settings=settings, projection=projection)
    identity_key = (identity.get("thread_id"), identity.get("session_id"), identity.get("contact_id"))
    if (
        any(base.stable(root / name) != raw for name, raw in expected.items())
        or proof.get("route") != route
        or proof.get("route_evidence") != evidence
        or acknowledgement.get("acknowledgement_sha256") != acknowledgement_sha256
        or target_file.get("target") != row["target"]
        or intent != expected_intent
        or sha256(payload) != row["payload_sha256"]
        or prepared.get("cell") != row
        or settings != expected_settings
        or record != {**expected_record, "reported": reported}
        or receipt != expected_receipt
        or final != base.stable(root / "responses" / "batch-0001.attempt-0001.message.json")
        or response_events != events
        or projection.get("completed_agent_message_text", "").encode() != final
        or not all(isinstance(value, str) and value for value in identity_key)
    ):
        raise ValueError("Sol receipt/source/identity binding drifted")
    return {
        "route": route,
        "route_evidence": evidence,
        "payload": payload,
        "final": final,
        "receipt": receipt,
        "identity": identity,
        "identity_key": identity_key,
        "settings": settings,
        "answer": answer,
    }


def finalize_collector(
    *,
    output_root: Path,
    collector_output: Path,
    authorization_acknowledgement_sha256: str,
    **inputs: Any,
) -> dict[str, Any]:
    validate_package()
    if Path(collector_output).exists():
        raise ValueError("collector output must be fresh")
    _disjoint(Path(collector_output), HERE, REPO, Path(output_root), *(Path(value) for value in inputs.values()))
    resolution = _resolve(**inputs)
    base = _configured_base(resolution)
    v4 = sol_v4()
    rows = resolution["rows"]
    _prepared_inventory(base, Path(output_root), rows, completed=True)
    cells: list[dict[str, Any]] = []
    identities: set[tuple[str, str, str]] = set()
    frozen_route = frozen_evidence = None
    for row in rows:
        admitted = _admit_completed_cell(base, v4, row, Path(output_root) / row["cell_id"], authorization_acknowledgement_sha256)
        if admitted["identity_key"] in identities:
            raise ValueError("duplicate Sol lifecycle identity")
        identities.add(admitted["identity_key"])
        if frozen_route is None:
            frozen_route, frozen_evidence = admitted["route"], admitted["route_evidence"]
        if admitted["route"] != frozen_route or admitted["route_evidence"] != frozen_evidence:
            raise ValueError("Sol route/evidence differs across cells")
        cells.append({
            "cell_id": row["cell_id"],
            "source_cell_id": row["source_cell_id"],
            "candidate_id": row["candidate_id"],
            "payload_base64": base64.b64encode(admitted["payload"]).decode("ascii"),
            "payload_sha256": sha256(admitted["payload"]),
            "final_response_base64": base64.b64encode(admitted["final"]).decode("ascii"),
            "final_response_sha256": sha256(admitted["final"]),
            "receipt_sha256": sha256(admitted["receipt"]),
            "identity": admitted["identity"],
            "effective_settings": admitted["settings"],
            "effective_settings_sha256": sha256(admitted["settings"]),
            "human_score_projection": admitted["answer"],
        })
    if frozen_route is None or frozen_evidence is None:
        raise ValueError("collector has no Sol cells")
    value = {
        "format_version": 1,
        "study_id": STUDY_ID,
        "kind": "complete_derived_desc16_sol_veto_receipts_cardinality_unproven",
        "authorization_acknowledgement_sha256": authorization_acknowledgement_sha256,
        "optimizer_result_file_sha256": RESULT_FILE_SHA256,
        "optimizer_result_internal_sha256": RESULT_INTERNAL_SHA256,
        "parent_sol_reference": resolution["parent_sol_reference"],
        "qualified_children": list(QUALIFIED_CHILDREN),
        "route": frozen_route,
        "route_evidence": frozen_evidence,
        "cells": cells,
        "native_endpoint_contact_cardinality": "unproven",
        "provider_calls_made": None,
        "process_launches": len(rows),
    }
    base._write_new(Path(collector_output), canonical(value))
    return {
        "format_version": 1,
        "study_id": STUDY_ID,
        "collector_sha256": sha256(value),
        "cells": len(rows),
        "provider_calls_made": None,
        "process_launches": len(rows),
        "native_endpoint_contact_cardinality": "unproven",
    }


def replay_collector(
    *,
    output_root: Path,
    collector_path: Path,
    **inputs: Any,
) -> dict[str, Any]:
    validate_package()
    _disjoint(Path(collector_path), HERE, REPO, Path(output_root), *(Path(value) for value in inputs.values()))
    resolution = _resolve(**inputs)
    base = _configured_base(resolution)
    v4 = sol_v4()
    rows = resolution["rows"]
    _prepared_inventory(base, Path(output_root), rows, completed=True)
    collector = strict(stable(Path(collector_path)), "Sol veto collector")
    expected_keys = {
        "format_version", "study_id", "kind", "authorization_acknowledgement_sha256",
        "optimizer_result_file_sha256", "optimizer_result_internal_sha256",
        "parent_sol_reference", "qualified_children", "route", "route_evidence", "cells",
        "native_endpoint_contact_cardinality", "provider_calls_made", "process_launches",
    }
    if (
        set(collector) != expected_keys
        or collector.get("format_version") != 1
        or collector.get("study_id") != STUDY_ID
        or collector.get("kind") != "complete_derived_desc16_sol_veto_receipts_cardinality_unproven"
        or collector.get("optimizer_result_file_sha256") != RESULT_FILE_SHA256
        or collector.get("optimizer_result_internal_sha256") != RESULT_INTERNAL_SHA256
        or collector.get("parent_sol_reference") != resolution["parent_sol_reference"]
        or tuple(collector.get("qualified_children", ())) != QUALIFIED_CHILDREN
        or collector.get("native_endpoint_contact_cardinality") != "unproven"
        or collector.get("provider_calls_made") is not None
        or collector.get("process_launches") != len(rows)
        or not isinstance(collector.get("cells"), list)
        or len(collector["cells"]) != len(rows)
    ):
        raise ValueError("Sol veto collector drifted")
    index = {row["cell_id"]: row for row in rows}
    seen_cells: set[str] = set()
    seen_identities: set[tuple[str, str, str]] = set()
    for supplied in collector["cells"]:
        expected_cell_keys = {
            "cell_id", "source_cell_id", "candidate_id", "payload_base64", "payload_sha256",
            "final_response_base64", "final_response_sha256", "receipt_sha256", "identity",
            "effective_settings", "effective_settings_sha256", "human_score_projection",
        }
        if not isinstance(supplied, Mapping) or set(supplied) != expected_cell_keys or supplied.get("cell_id") not in index:
            raise ValueError("Sol veto collector cell drifted")
        row = index[supplied["cell_id"]]
        admitted = _admit_completed_cell(base, v4, row, Path(output_root) / row["cell_id"], collector["authorization_acknowledgement_sha256"])
        payload = base64.b64decode(supplied["payload_base64"], validate=True)
        final = base64.b64decode(supplied["final_response_base64"], validate=True)
        if (
            supplied["cell_id"] in seen_cells
            or supplied.get("source_cell_id") != row["source_cell_id"]
            or supplied.get("candidate_id") != row["candidate_id"]
            or payload != admitted["payload"]
            or final != admitted["final"]
            or supplied.get("payload_sha256") != sha256(payload)
            or supplied.get("final_response_sha256") != sha256(final)
            or supplied.get("receipt_sha256") != sha256(admitted["receipt"])
            or supplied.get("identity") != admitted["identity"]
            or supplied.get("effective_settings") != admitted["settings"]
            or supplied.get("effective_settings_sha256") != sha256(admitted["settings"])
            or supplied.get("human_score_projection") != admitted["answer"]
            or admitted["route"] != collector["route"]
            or admitted["route_evidence"] != collector["route_evidence"]
            or admitted["identity_key"] in seen_identities
        ):
            raise ValueError("collector differs from persisted Sol receipt")
        seen_cells.add(supplied["cell_id"])
        seen_identities.add(admitted["identity_key"])
    if seen_cells != set(index):
        raise ValueError("partial Sol veto collector")
    return {
        "format_version": 1,
        "study_id": STUDY_ID,
        "collector_sha256": sha256(collector),
        "cells": len(rows),
        "provider_calls_made": None,
        "process_launches": len(rows),
        "native_endpoint_contact_cardinality": "unproven",
        "sol_role": "veto_only_no_outside_candidate_substitution",
        "parent_sol_reference": resolution["parent_sol_reference"],
        "qualified_children": list(QUALIFIED_CHILDREN),
        "confirmation_cells": 0,
    }


def _validate_contract(contract: Mapping[str, Any]) -> None:
    expected = {
        "format_version": 1,
        "study_id": STUDY_ID,
        "kind": "provider_free_desc16_exact_grok_payload_replayed_sol_veto_preparation",
        "geometry": {"development_groups": 7, "sol_cells": len(QUALIFIED_CHILDREN) * 13, "max_concurrency": 10},
        "authority": {
            "selection": "grok_qualification_frozen", "sol": "veto_only",
            "confirmation": "unopened", "generalization": "none", "promotion": "none", "runtime": "none", "endpoint_pooling": "forbidden",
        },
        "pinned_dependencies": {
            "candidate_freeze": {"commit": SOURCE_COMMIT, "manifest_sha256": "5aa8f797d833e387432d956b7d7e326ab71fa3a5642a368967842b26aa82909f"},
            "broader_development_freeze": {"commit": BROADER_COMMIT, "study_sha256": BROADER_HASHES[BROADER / "study.py"]},
            "committed_development_optimizer": {"commit": ANALYZER_COMMIT, "study_id": ANALYZER_ID, "analyzer_sha256": ANALYZER_SHA256, "study_contract_sha256": ANALYZER_CONTRACT_SHA256},
            "frozen_optimizer_result": {"file_sha256": RESULT_FILE_SHA256, "internal_sha256": RESULT_INTERNAL_SHA256},
            "committed_grok_executor": {"commit": GROK_EXECUTOR_COMMIT, "executor_sha256": GROK_EXECUTOR_SHA256},
            "frozen_parent_sol_result": {"commit": PARENT_SOL_RESULT_COMMIT, "file_sha256": PARENT_SOL_RESULT_SHA256, "candidate_id": PARENT_CANDIDATE_ID, "equal_group_mae": PARENT_SOL_EQUAL_GROUP_MAE},
            "sol_route": {"commit": V4_COMMIT, "executor_sha256": V4_SHA256},
        },
        "replay_inputs": ["freeze_root", "development_freeze_root", "normalized_root", "materialization_root", "frozen_successor_path", "hanna_csv_path", "grok_execution_root", "grok_collector_path", "grok_result_path"],
        "qualified_children": list(QUALIFIED_CHILDREN),
        "prohibitions": ["no runtime optimizer dependency", "no fallback or resend", "no confirmation, promotion, runtime, pooled-endpoint, generalization, or Sol-favored substitution claim"],
    }
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
    mode.add_argument("--execute-one", action="store_true")
    mode.add_argument("--execute-wave", action="store_true")
    mode.add_argument("--finalize-collector", action="store_true")
    mode.add_argument("--replay-collector", action="store_true")
    for name in ("output-root", "queue-root", "freeze-root", "development-freeze-root", "normalized-root", "materialization-root", "frozen-successor", "hanna-csv", "grok-execution-root", "grok-collector", "grok-result"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--authorization-acknowledgement-sha256")
    parser.add_argument("--cell-id")
    parser.add_argument("--collector-output", type=Path)
    parser.add_argument("--collector-path", type=Path)
    parser.add_argument("--allow-remote", action="store_true")
    args = parser.parse_args(argv)
    validate_package()
    common = {
        "output_root": args.output_root, "queue_root": args.queue_root, "authorization_acknowledgement_sha256": args.authorization_acknowledgement_sha256,
        "freeze_root": args.freeze_root, "development_freeze_root": args.development_freeze_root, "normalized_root": args.normalized_root, "materialization_root": args.materialization_root,
        "frozen_successor_path": args.frozen_successor, "hanna_csv_path": args.hanna_csv,
        "grok_execution_root": args.grok_execution_root, "grok_collector_path": args.grok_collector, "grok_result_path": args.grok_result,
    }
    if args.prepare:
        if args.allow_remote or not args.authorization_acknowledgement_sha256:
            parser.error("prepare requires acknowledgement and forbids remote execution")
        value = prepare_all(**common)
    elif args.execute_one:
        if not args.allow_remote or not args.cell_id or not args.authorization_acknowledgement_sha256:
            parser.error("execute-one requires acknowledgement, a cell, and explicit remote authorization")
        value = execute_one(**common, cell_id=args.cell_id, allow_remote=True)
    elif args.execute_wave:
        if not args.allow_remote or not args.authorization_acknowledgement_sha256:
            parser.error("execute-wave requires acknowledgement and explicit remote authorization")
        value = execute_wave(**common, allow_remote=True)
    elif args.finalize_collector:
        if args.allow_remote or not args.collector_output or not args.authorization_acknowledgement_sha256:
            parser.error("finalize-collector requires output/acknowledgement and forbids remote execution")
        local = {key: item for key, item in common.items() if key not in {"queue_root"}}
        value = finalize_collector(**local, collector_output=args.collector_output)
    else:
        if args.allow_remote or not args.collector_path:
            parser.error("replay-collector requires collector and forbids remote execution")
        local = {key: item for key, item in common.items() if key not in {"queue_root", "authorization_acknowledgement_sha256"}}
        value = replay_collector(**local, collector_path=args.collector_path)
    print(canonical(value).decode("utf-8"), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
