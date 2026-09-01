#!/usr/bin/env python3
"""Two-lane Sol extension over the three nonwinner lower-step descendants."""
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
STUDY_ID = "hbq-human-alignment-optimizer-v6-desc13-lower-step-sol-nonwinner-extension-exec-v1"
ANALYZER_ID = "hbq-human-alignment-optimizer-v6-desc13-lower-step-grok-result-v2-v3-exec"
ANALYZER = HERE.parent / ANALYZER_ID / "verify.py"
ANALYZER_CONTRACT = ANALYZER.parent / "study-contract.json"
ANALYZER_COMMIT = "7bf7923f36edee85c82000104b46a6f7f0f5f96d"
ANALYZER_SHA256 = "a080cfe32f44e9cca4536445fddaca9c0c79cad724d6a6365dadbeeecdc39b86"
ANALYZER_CONTRACT_SHA256 = "abf2346599fd1221a2d58ce3b8ce80a0ae4c75c9b12cce132ef32e8eb147ca05"
GROK_EXECUTOR_ID = "hbq-human-alignment-optimizer-v6-desc13-lower-step-grok-exec-v3-callback-prompt"
RESULT_SHA256 = "7b31b817a324bb874f24e270b1446b03e142dc1ea0f71edf45da14504ce7d5a2"
SOURCE_COMMIT = "02bdbf5c1adc4fa44a0b39b46e5bb9895f4d95d4"
CWR_CHECKPOINT_COMMIT = "c40a9a5150053e4edebb0c68c4fdfb029fbe3c60"
CWR_SOL_RESULT = HERE.parent / "hbq-human-alignment-optimizer-v6-desc13-lower-step-sol-result-v1" / "result.json"
CWR_SOL_RESULT_SHA256 = "da575fc017c461ecfd0756a50265387b8a5b4145cdfaf3b21d32020410371047"
CANDIDATES_ID = "hbq-human-alignment-optimizer-v6-desc13-lower-step-candidates-v1"
CANDIDATES = HERE.parent / CANDIDATES_ID
CANDIDATE_HASHES = {
    CANDIDATES / "study.py": "511066c8b8723b1df04a07eae4eb0daa7fb375169ba2a23c442fc848b2ef8dae",
    CANDIDATES / "study-contract.json": "74aa271918c4e9d15cd48f797f4b94814f7cf41344ace7a2c65a56a9fa06acfa",
    CANDIDATES / "README.md": "a62ffb01d9ac453470a886270251689d6d472080b4cce58090227e8add95bc67",
}
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
EXTENSION_CHILDREN = (
    "broader-nextwave-15-construct_framing-speaker-attribution",
    "broader-nextwave-16-scope_materiality-temporal-causality",
    "broader-nextwave-17-scope_materiality-sustained-stakes",
)
DIMENSIONS = ("Relevance", "Coherence", "Empathy", "Surprise", "Engagement", "Complexity")
MAX_CONCURRENCY = 2
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


def candidate_study() -> ModuleType:
    for path, digest in CANDIDATE_HASHES.items():
        if sha256(stable(path)) != digest or _blob(SOURCE_COMMIT, path.relative_to(REPO).as_posix()) != stable(path):
            raise ValueError("candidate freeze dependency drifted")
    return _load(CANDIDATES / "study.py", "_desc13_sol_candidate_freeze")


def broader_study() -> ModuleType:
    for path, digest in BROADER_HASHES.items():
        if sha256(stable(path)) != digest or _blob(BROADER_COMMIT, path.relative_to(REPO).as_posix()) != stable(path):
            raise ValueError("broader development dependency drifted")
    return _load(BROADER / "study.py", "_desc13_sol_broader")


def sol_v4() -> ModuleType:
    return _pinned(V4, V4_SHA256, V4_COMMIT, f"evaluation-results/{V4_ID}/executor.py", "_desc13_sol_v4")


def result_analyzer() -> ModuleType:
    module = _pinned(
        ANALYZER,
        ANALYZER_SHA256,
        ANALYZER_COMMIT,
        f"evaluation-results/{ANALYZER_ID}/verify.py",
        "_desc13_sol_result_analyzer",
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


def _checkpoint_result() -> None:
    raw = stable(CWR_SOL_RESULT)
    relative = CWR_SOL_RESULT.relative_to(REPO).as_posix()
    if sha256(raw) != CWR_SOL_RESULT_SHA256 or _blob(CWR_CHECKPOINT_COMMIT, relative) != raw:
        raise ValueError("committed CWR checkpoint result drifted")


def _targets(broader: ModuleType, frozen_successor_path: Path, hanna_csv_path: Path) -> Mapping[str, Mapping[str, float]]:
    study, _harness, _freeze, _split, _parents = broader._v3()._material(frozen_successor_path=Path(frozen_successor_path), hanna_csv_path=Path(hanna_csv_path))
    return broader._v3().v2_module()._human_targets(study=study, frozen_successor_path=Path(frozen_successor_path), hanna_csv_path=Path(hanna_csv_path))


def _baseline_candidate(broader: ModuleType, frozen_successor_path: Path, hanna_csv_path: Path) -> tuple[dict[str, Any], Mapping[str, Any]]:
    _study, _harness, _freeze, split, candidates = broader._v3()._material(frozen_successor_path=Path(frozen_successor_path), hanna_csv_path=Path(hanna_csv_path))
    baseline_id = broader._v3().BASELINE_ID
    baseline = next((dict(row) for row in candidates if row.get("candidate_id") == baseline_id), None)
    if baseline is None or not isinstance(baseline.get("instruction_bytes"), bytes) or not isinstance(baseline.get("profile_bytes"), bytes):
        raise ValueError("frozen original baseline material is absent")
    groups = {row.get("prompt_group_id") for row in split.get("items", []) if isinstance(row, Mapping) and row.get("partition") == "development"}
    if len(groups) != 7:
        raise ValueError("frozen original baseline split drifted")
    return baseline, split


def _result_projection(
    *,
    analyzer: ModuleType,
    candidate_freeze_root: Path,
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
    if sha256(result_raw) != RESULT_SHA256:
        raise ValueError("wrong immutable committed Grok result")
    persisted = strict(result_raw, "committed Grok result")
    replayed = analyzer.replay(
        candidate_freeze_root=Path(candidate_freeze_root), development_freeze_root=Path(development_freeze_root),
        normalized_root=Path(normalized_root), materialization_root=Path(materialization_root),
        frozen_successor_path=Path(frozen_successor_path), hanna_csv_path=Path(hanna_csv_path),
        output_root=Path(grok_execution_root), collector_path=Path(grok_collector_path),
    )
    if persisted != replayed:
        raise ValueError("committed Grok result differs from independent V2 replay")
    selection, source = replayed.get("selection"), replayed.get("source_execution")
    if (
        replayed.get("study_id") != ANALYZER_ID
        or not isinstance(selection, Mapping)
        or selection.get("candidate_id") != "broader-nextwave-18-construct_framing-referent-resolution"
        or not isinstance(source, Mapping)
        or source.get("collector_sha256") != "6ca1fc13244f93719d672a127ddf10cc492ea2207e5649fab1058bdbea923ae6"
        or source.get("executor_commit") != "cd67452ceb018e18f5d2d3315c544af0d47f23ef"
        or source.get("executor_sha256") != "00c1df7da792c36e4d1532765977299c5001c0119097985a089a8935fd014b14"
    ):
        raise ValueError("committed Grok result authority or referent-resolution drifted")
    schedule = strict(stable(Path(grok_execution_root) / "schedule.json"), "persisted Grok schedule")
    if schedule.get("study_id") != GROK_EXECUTOR_ID or schedule.get("development_schedule_sha256") != source.get("development_schedule_sha256"):
        raise ValueError("committed Grok result schedule binding drifted")
    return schedule, replayed, result_raw


def _rows(
    *,
    schedule: Mapping[str, Any],
    targets: Mapping[str, Mapping[str, float]],
    grok_execution_root: Path,
) -> tuple[dict[str, Any], ...]:
    candidate_ids = {row.get("candidate_id") for row in schedule.get("candidates", []) if isinstance(row, Mapping)}
    if not set(EXTENSION_CHILDREN).issubset(candidate_ids):
        raise ValueError("exact Grok schedule is missing an extension child")
    cells = schedule.get("cells")
    if not isinstance(cells, list) or len(cells) != 35:
        raise ValueError("Grok source cell geometry drifted")
    groups = {(row.get("prompt_group_id"), row.get("item_id")) for row in schedule.get("groups", []) if isinstance(row, Mapping)}
    if len(groups) != 7 or any(not all(isinstance(value, str) and value for value in group) for group in groups):
        raise ValueError("Grok development group geometry drifted")
    rows: list[dict[str, Any]] = []
    for source in cells:
        if not isinstance(source, Mapping) or source.get("candidate_id") not in EXTENSION_CHILDREN:
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
            "cell_id": "desc13-lower-sol-extension-" + sha256(key)[:16], "source_cell_id": source["cell_id"],
            "candidate_id": source["candidate_id"], "prompt_group_id": source["prompt_group_id"], "item_id": source["item_id"], "story_id": source["item_id"],
            "payload_base64": source["payload_base64"], "payload_sha256": source["payload_sha256"],
            "payload_parity": "observed_exact_grok_outbound_bytes", "target": {dimension: float(target[dimension]) for dimension in DIMENSIONS},
        })
    if (len(rows) != 21 or len({row["cell_id"] for row in rows}) != 21
            or {row["candidate_id"] for row in rows} != set(EXTENSION_CHILDREN)
            or any({(row["prompt_group_id"], row["item_id"]) for row in rows if row["candidate_id"] == candidate} != groups for candidate in EXTENSION_CHILDREN)):
        raise ValueError("fixed 21-cell Sol extension geometry drifted")
    return tuple(sorted(rows, key=lambda row: row["cell_id"]))


def _resolve(
    *,
    candidate_freeze_root: Path,
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
        "candidate_freeze_root": Path(candidate_freeze_root), "development_freeze_root": Path(development_freeze_root),
        "normalized_root": Path(normalized_root), "materialization_root": Path(materialization_root),
        "frozen_successor_path": Path(frozen_successor_path), "hanna_csv_path": Path(hanna_csv_path),
        "grok_execution_root": Path(grok_execution_root), "grok_collector_path": Path(grok_collector_path), "grok_result_path": Path(grok_result_path),
    }
    committed_inputs = _input_commitments(replay_inputs)
    candidate_study().validate_frozen_root(Path(candidate_freeze_root))
    broader = broader_study()
    broader.validate_frozen_root(Path(development_freeze_root))
    analyzer = result_analyzer()
    schedule, replayed, result_raw = _result_projection(
        analyzer=analyzer, candidate_freeze_root=Path(candidate_freeze_root), development_freeze_root=Path(development_freeze_root),
        normalized_root=Path(normalized_root), materialization_root=Path(materialization_root),
        frozen_successor_path=Path(frozen_successor_path), hanna_csv_path=Path(hanna_csv_path),
        grok_execution_root=Path(grok_execution_root), grok_collector_path=Path(grok_collector_path), grok_result_path=Path(grok_result_path),
    )
    if _input_commitments(replay_inputs) != committed_inputs:
        raise ValueError("replay inputs changed during independent Grok result resolution")
    targets = _targets(broader, Path(frozen_successor_path), Path(hanna_csv_path))
    _checkpoint_result()
    rows = _rows(schedule=schedule, targets=targets, grok_execution_root=Path(grok_execution_root))
    hanna_csv_sha256 = sha256(stable(Path(hanna_csv_path)))
    if _input_commitments(replay_inputs) != committed_inputs:
        raise ValueError("replay inputs changed during Sol target/row reconstruction")
    return {
        "rows": rows, "schedule": schedule, "selection": replayed,
        "bindings": {
            "result_analyzer_commit": ANALYZER_COMMIT, "result_analyzer_sha256": ANALYZER_SHA256,
            "result_analyzer_contract_sha256": ANALYZER_CONTRACT_SHA256, "grok_result_sha256": sha256(result_raw),
            "grok_result_internal_sha256": replayed["result_internal_sha256"],
            "grok_execution_commit": replayed["source_execution"]["executor_commit"],
            "grok_executor_sha256": replayed["source_execution"]["executor_sha256"],
            "grok_collector_sha256": replayed["source_execution"]["collector_sha256"],
            "hanna_csv_sha256": hanna_csv_sha256,
            "replay_input_commitments": committed_inputs,
            "cwr_checkpoint_commit": CWR_CHECKPOINT_COMMIT,
            "cwr_checkpoint_sol_result_sha256": CWR_SOL_RESULT_SHA256,
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
            source["extension_children"] = list(EXTENSION_CHILDREN)
            source["cwr_checkpoint_commit"] = bindings["cwr_checkpoint_commit"]
            source["cwr_checkpoint_sol_result_sha256"] = bindings["cwr_checkpoint_sol_result_sha256"]
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


def _prepared_inventory(base: ModuleType, output_root: Path, rows: tuple[Mapping[str, Any], ...]) -> None:
    entries = _output_inventory(output_root, rows)
    for row in rows:
        cell = entries[str(row["cell_id"])]
        base._inventory(cell)


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
    raise TimeoutError("global Sol two-slot semaphore did not become available")


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
    locks = output_root.parent / ("." + output_root.name + ".desc13-sol-nonwinner-extension-locks")
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
        "candidate_freeze_root", "development_freeze_root", "normalized_root", "materialization_root",
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
        "format_version": 1, "study_id": STUDY_ID, "kind": "prepared_21_desc13_lower_step_sol_nonwinner_extension_cells",
        "cells": 21, "groups": 7, "provider_calls_made": 0, "process_launches": 0, "max_concurrency": MAX_CONCURRENCY,
        "authority": "exact_grok_v3_payload_replay_then_sol_descriptive_extension_only",
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


def _validate_contract(contract: Mapping[str, Any]) -> None:
    expected = {
        "format_version": 1,
        "study_id": STUDY_ID,
        "kind": "provider_free_desc13_lower_step_exact_grok_v3_payload_replayed_sol_extension_preparation",
        "geometry": {"development_groups": 7, "sol_cells": 21, "max_concurrency": 2},
        "authority": {
            "selection": "none", "sol": "descriptive_extension_only",
            "confirmation": "unopened", "generalization": "none", "promotion": "none", "runtime": "none", "endpoint_pooling": "forbidden",
        },
        "pinned_dependencies": {
            "candidate_freeze": {"commit": SOURCE_COMMIT, "manifest_sha256": "0487398345b28388fb6e35d879e5ea6f771f65802488e3fc33cf0426b530cecd"},
            "broader_development_freeze": {"commit": BROADER_COMMIT, "study_sha256": BROADER_HASHES[BROADER / "study.py"]},
            "committed_cwr_checkpoint": {"commit": CWR_CHECKPOINT_COMMIT, "sol_result_sha256": CWR_SOL_RESULT_SHA256},
            "committed_grok_result_analyzer": {"commit": ANALYZER_COMMIT, "study_id": ANALYZER_ID, "verify_sha256": ANALYZER_SHA256, "study_contract_sha256": ANALYZER_CONTRACT_SHA256},
            "committed_grok_v3_result": {"result_sha256": RESULT_SHA256},
            "sol_route": {"commit": V4_COMMIT, "executor_sha256": V4_SHA256},
        },
        "replay_inputs": ["candidate_freeze_root", "development_freeze_root", "normalized_root", "materialization_root", "frozen_successor_path", "hanna_csv_path", "grok_execution_root", "grok_collector_path", "grok_result_path"],
        "selected_children": list(EXTENSION_CHILDREN),
        "prohibitions": ["no runtime optimizer dependency", "no fallback or resend", "no confirmation, promotion, runtime, pooled-endpoint, generalization, or selection claim"],
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
    for name in ("output-root", "queue-root", "candidate-freeze-root", "development-freeze-root", "normalized-root", "materialization-root", "frozen-successor", "hanna-csv", "grok-execution-root", "grok-collector", "grok-result"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--authorization-acknowledgement-sha256", required=True)
    parser.add_argument("--cell-id")
    parser.add_argument("--allow-remote", action="store_true")
    args = parser.parse_args(argv)
    validate_package()
    common = {
        "output_root": args.output_root, "queue_root": args.queue_root, "authorization_acknowledgement_sha256": args.authorization_acknowledgement_sha256,
        "candidate_freeze_root": args.candidate_freeze_root, "development_freeze_root": args.development_freeze_root, "normalized_root": args.normalized_root, "materialization_root": args.materialization_root,
        "frozen_successor_path": args.frozen_successor, "hanna_csv_path": args.hanna_csv,
        "grok_execution_root": args.grok_execution_root, "grok_collector_path": args.grok_collector, "grok_result_path": args.grok_result,
    }
    if args.prepare:
        if args.allow_remote:
            parser.error("prepare forbids remote execution")
        value = prepare_all(**common)
    elif args.execute_one:
        if not args.allow_remote or not args.cell_id:
            parser.error("execute-one requires a cell and explicit remote authorization")
        value = execute_one(**common, cell_id=args.cell_id, allow_remote=True)
    else:
        if not args.allow_remote:
            parser.error("execute-wave requires explicit remote authorization")
        value = execute_wave(**common, allow_remote=True)
    print(canonical(value).decode("utf-8"), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
