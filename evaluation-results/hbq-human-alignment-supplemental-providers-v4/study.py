"""Provider-free v4 successor for the immutable failed v2 transport record."""
from __future__ import annotations

import hashlib
import json
import os
import random
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
CONTRACT_PATH = HERE / "study-contract.json"
PREDECESSOR_ROOTS = {
    "v1": ROOT / "evaluation-results" / "hbq-human-alignment-supplemental-providers-v1",
    "v2": ROOT / "evaluation-results" / "hbq-human-alignment-supplemental-providers-v2",
    "v3": ROOT / "evaluation-results" / "hbq-human-alignment-supplemental-providers-v3",
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fingerprint(path: Path) -> dict[str, Any]:
    return {"name": path.name, "bytes": path.stat().st_size, "sha256": sha(path)}


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"Expected JSON object: {path}")
    return value


def immutable_json(path: Path, value: Mapping[str, Any]) -> None:
    rendered = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as output:
            output.write(rendered)
            output.flush()
            os.fsync(output.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            if path.read_text(encoding="utf-8") != rendered:
                raise ValueError(f"Immutable record drifted: {path.name}")
    finally:
        Path(temporary).unlink(missing_ok=True)


def load_contract() -> dict[str, Any]:
    contract = read_json(CONTRACT_PATH)
    if contract.get("format_version") != 1 or contract.get("study_id") != "hbq-human-alignment-supplemental-providers-v4" or contract.get("frozen_before_execution") is not True:
        raise ValueError("v4 contract is not frozen")
    policy = contract.get("pilot_policy")
    required = {"cells": 3, "batch_size": 8, "batch_attempts": 1, "workers": 1, "timeout_seconds": 600, "maximum_completion_seconds_exclusive": 100}
    if not isinstance(policy, Mapping) or any(policy.get(key) != item for key, item in required.items()):
        raise ValueError("v4 batch-8 policy drifted")
    snapshot = contract.get("compatibility_snapshot")
    expected_snapshot = {
        "historical_cell_question_count": 16,
        "execution_ready": False,
        "future_execution_requires": ["a new exact 8-question schedule", "per-cell disclosure", "current zero-charge route evidence", "native runner and request bindings"],
    }
    if snapshot != expected_snapshot:
        raise ValueError("v4 compatibility snapshot drifted")
    if contract.get("execution_status") != "CLOSED_PENDING_REVIEWED_DISCLOSURE_ZERO_CHARGE_ROUTE_AND_NATIVE_RUNNER":
        raise ValueError("v4 execution closure drifted")
    return contract


CONTRACT = load_contract()


def verify_predecessors() -> dict[str, dict[str, str]]:
    observed: dict[str, dict[str, str]] = {}
    for version, binding in CONTRACT["predecessors"].items():
        root = PREDECESSOR_ROOTS[version]
        if binding.get("study_id") != f"hbq-human-alignment-supplemental-providers-{version}":
            raise ValueError(f"{version} package identity is malformed")
        files = binding.get("files")
        if not isinstance(files, Mapping):
            raise TypeError(f"{version} package file inventory is malformed")
        for relative, digest in files.items():
            path = root / relative
            if not path.is_file() or sha(path) != digest:
                raise ValueError(f"{version} predecessor drifted: {relative}")
        observed[version] = dict(files)
    return observed


def _tree(root: Path, excluded: set[str]) -> dict[str, Any]:
    entries = [
        {"path": item.relative_to(root).as_posix(), "bytes": item.stat().st_size, "sha256": sha(item)}
        for item in sorted(root.rglob("*"))
        if item.is_file() and item.name not in excluded
    ]
    return {
        "files": len(entries),
        "sha256": hashlib.sha256(json.dumps(entries, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest(),
    }


def _static_v2_cells(v2_frozen: Mapping[str, Any]) -> tuple[Path, list[dict[str, Any]]]:
    parent_root = Path(str(v2_frozen.get("parent_work_dir", "")))
    parent_frozen = parent_root / "frozen-provider-contract.json"
    if not parent_root.is_dir() or v2_frozen.get("parent_frozen") != fingerprint(parent_frozen):
        raise ValueError("failed v2 parent freeze binding drifted")
    v1 = read_json(parent_frozen)
    if v1.get("study_id") != CONTRACT["predecessors"]["v1"]["study_id"]:
        raise ValueError("failed v2 parent is not the pinned v1 study")
    selection = v1.get("selection")
    if not isinstance(selection, Mapping):
        raise TypeError("failed v2 v1 selection is malformed")
    development = selection.get("partitions", {}).get("development")
    seed = selection.get("selection", {}).get("seed")
    question_ids = selection.get("question_ids")
    if not isinstance(development, list) or not isinstance(question_ids, list) or len(question_ids[:16]) != 16 or len(set(question_ids[:16])) != 16:
        raise ValueError("failed v2 v1 cell geometry drifted")
    rows = [{"kind": "development", "repetition": 1, **row} for row in development]
    random.Random(seed).shuffle(rows)
    cells: list[dict[str, Any]] = []
    commitments = v1.get("input_commitments", {}).get("development", {})
    for number, scheduled in enumerate(rows[:3], 1):
        item_id = str(scheduled.get("item_id", ""))
        selection_row = next((row for row in development if row.get("item_id") == item_id), None)
        expected_inputs = commitments.get(item_id) if isinstance(commitments, Mapping) else None
        folder = Path(str(v1.get("primary_work_dir", ""))) / "inputs" / "development" / item_id
        if not isinstance(selection_row, Mapping) or not isinstance(expected_inputs, Mapping) or not folder.is_dir():
            raise ValueError("failed v2 v1 input lineage is incomplete")
        observed_inputs = {name: fingerprint(folder / name) for name in ("source.md", "prompt.md", "task-contract.json")}
        if observed_inputs != expected_inputs:
            raise ValueError("failed v2 v1 input bytes drifted")
        cells.append({"cell_id": f"pilot-{number:02d}", "item_id": item_id, "selection": dict(selection_row), "inputs": observed_inputs, "question_ids": question_ids[:16]})
    if len(cells) != 3 or len({cell["item_id"] for cell in cells}) != 3:
        raise ValueError("failed v2 v1 selection cannot supply three independent cells")
    return parent_root, cells


def failed_v2_commitments(root: Path) -> dict[str, Any]:
    root = root.resolve()
    expected = CONTRACT["failed_v2"]
    commitments: dict[str, Any] = {}
    for relative, commitment in expected["commitments"].items():
        path = root / relative
        if not path.is_file() or fingerprint(path) != {"name": path.name, **commitment}:
            raise ValueError(f"failed v2 evidence drifted: {relative}")
        commitments[relative] = {"path": relative, **commitment}
    tree_spec = expected["raw_evidence_tree"]
    tree_root = root / tree_spec["path"]
    observed_tree = {"path": tree_spec["path"], **_tree(tree_root, set(tree_spec["excluded"])), "excluded": tree_spec["excluded"]}
    if observed_tree != tree_spec:
        raise ValueError("failed v2 raw evidence tree drifted")
    failed_receipts = [(path, read_json(path)) for path in tree_root.rglob("receipt.json")]
    terminal_failures = [(path, receipt) for path, receipt in failed_receipts if receipt.get("status") == "failure"]
    if len(terminal_failures) != 1:
        raise ValueError("failed v2 evidence no longer has one terminal failure receipt")
    events_path = terminal_failures[0][0].parent / "events.jsonl"
    if not events_path.is_file():
        raise ValueError("failed v2 terminal receipt lacks sibling events")
    events = [json.loads(line) for line in events_path.read_text(encoding="utf-8").splitlines()]
    statuses = [event.get("data", {}).get("status") for event in events if event.get("event_type") == "http_attempt"]
    journal = read_json(root / "pilot-journal" / "0001-pilot-01.json")
    if statuses != expected["terminal_http_statuses"] or journal.get("status") != "failed" or journal.get("cell_id") != "pilot-01":
        raise ValueError("failed v2 terminal failure record drifted")
    v2_frozen = read_json(root / "frozen-transport-contract.json")
    if v2_frozen.get("study_id") != CONTRACT["predecessors"]["v2"]["study_id"] or v2_frozen.get("contract_sha256") != CONTRACT["predecessors"]["v2"]["files"]["study-contract.json"]:
        raise ValueError("failed v2 frozen protocol binding drifted")
    parent_root, cells = _static_v2_cells(v2_frozen)
    if v2_frozen.get("cells") != cells:
        raise ValueError("failed v2 frozen cells no longer match static v1 input lineage")
    return {"work_dir": str(root), "commitments": commitments, "raw_evidence_tree": observed_tree, "v1_parent_work_dir": str(parent_root), "cells": cells}


def runtime_bindings() -> dict[str, dict[str, Any]]:
    runner = ROOT / "src" / "hbqrs" / "runner.py"
    launcher = Path.home() / ".codex" / "tools" / "launch-bridge.ps1"
    bridge = launcher.parent / "nous_codex_bridge.py"
    required = {"runner": runner, "launcher": launcher, "bridge": bridge}
    if any(not path.is_file() for path in required.values()):
        raise ValueError("current canonical Nous runtime is unavailable")
    return {name: fingerprint(path) for name, path in required.items()}


def _is_reparse(path: Path) -> bool:
    is_junction = getattr(path, "is_junction", None)
    return path.is_symlink() or (callable(is_junction) and is_junction())


def _create_fresh_work_root(work: Path) -> None:
    parent = work.parent
    if not parent.is_dir() or _is_reparse(parent):
        raise ValueError("v4 freeze parent must be an existing non-reparse directory")
    if work.exists() or _is_reparse(work):
        raise ValueError("v4 freeze requires a fresh nonexistent non-reparse work root; no orphan adoption or resend")
    try:
        work.mkdir()
    except FileExistsError as error:
        raise ValueError("v4 freeze work root raced or already exists") from error


def freeze_work(failed_v2_work: Path, work: Path) -> dict[str, Any]:
    predecessors = verify_predecessors()
    failed = failed_v2_commitments(failed_v2_work)
    runtime = runtime_bindings()
    _create_fresh_work_root(work)
    value = {
        "format_version": 1,
        "study_id": CONTRACT["study_id"],
        "frozen_before_execution": True,
        "contract_sha256": sha(CONTRACT_PATH),
        "predecessors": predecessors,
        "failed_v2": failed,
        "runtime": runtime,
        "pilot": CONTRACT["pilot_policy"],
        "compatibility_snapshot": CONTRACT["compatibility_snapshot"],
        "execution_status": CONTRACT["execution_status"],
        "provider_calls_made": 0,
    }
    immutable_json(work / "frozen-transport-contract.json", value)
    return value


def execution_is_closed() -> None:
    raise ValueError("v4 execution is closed pending reviewed disclosure, zero-charge route, and native runner binding")
