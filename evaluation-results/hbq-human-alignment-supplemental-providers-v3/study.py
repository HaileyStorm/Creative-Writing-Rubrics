"""Frozen score-blind batch-8 Nous successor, bound to failed v2 evidence."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Mapping

from hbqrs import runner as runner_module

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
CONTRACT_PATH = HERE / "study-contract.json"
PARENT_ROOT = (HERE / "../hbq-human-alignment-supplemental-providers-v2").resolve()


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fingerprint(path: Path) -> dict[str, Any]:
    return {"name": path.name, "bytes": path.stat().st_size, "sha256": sha(path)}


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def immutable_json(path: Path, value: Mapping[str, Any]) -> None:
    rendered = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as output:
            output.write(rendered); output.flush(); os.fsync(output.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            if path.read_text(encoding="utf-8") != rendered:
                raise ValueError(f"Immutable record drifted: {path.name}")
    finally:
        Path(temporary).unlink(missing_ok=True)


def load_contract() -> dict[str, Any]:
    value = read_json(CONTRACT_PATH)
    pilot = value.get("transport_pilot")
    if value.get("format_version") != 1 or value.get("study_id") != "hbq-human-alignment-supplemental-providers-v3" or value.get("frozen_before_execution") is not True or not isinstance(pilot, Mapping):
        raise ValueError("v3 contract is not frozen")
    expected = {"cells": 3, "batch_size": 8, "question_count": 8, "batch_attempts": 1, "workers": 1, "timeout_seconds": 600, "maximum_completion_seconds_exclusive": 100}
    if any(pilot.get(key) != item for key, item in expected.items()):
        raise ValueError("v3 batch-8 pilot policy drifted")
    if value.get("provider") != {"provider_id": "nous_flash_max", "provider": "nous", "model": "deepseek/deepseek-v4-flash-0731", "reasoning": "max", "allow_unattested_reasoning": True}:
        raise ValueError("v3 provider policy drifted")
    return value


CONTRACT = load_contract()


def _parent_v2() -> Any:
    parent = CONTRACT["parent_v2"]
    for name, digest in parent["files"].items():
        path = PARENT_ROOT / name
        if not path.is_file() or sha(path) != digest:
            raise ValueError(f"v2 parent file drifted: {name}")
    spec = importlib.util.spec_from_file_location("hanna_supplemental_v3_parent", PARENT_ROOT / "study.py")
    if spec is None or spec.loader is None:
        raise ValueError("v2 parent study helper is unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def failed_v2_commitments(root: Path) -> dict[str, Any]:
    root = root.resolve()
    expected = CONTRACT["failed_v2"]
    observed = {}
    for relative, commitment in expected["commitments"].items():
        path = root / relative
        if not path.is_file() or fingerprint(path) != {"name": path.name, **commitment}:
            raise ValueError(f"failed v2 evidence drifted: {relative}")
        observed[relative] = {"path": relative, **commitment}
    tree = expected["raw_evidence_tree"]
    evidence_root = root / str(tree["path"])
    entries = [{"path": item.relative_to(evidence_root).as_posix(), "bytes": item.stat().st_size, "sha256": sha(item)} for item in sorted(evidence_root.rglob("*")) if item.is_file() and item.name not in set(tree["excluded"])]
    observed_tree = {"path": tree["path"], "files": len(entries), "sha256": hashlib.sha256(json.dumps(entries, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest(), "excluded": tree["excluded"]}
    if observed_tree != tree:
        raise ValueError("failed v2 raw evidence tree drifted")
    failed_receipts = [(path, read_json(path)) for path in evidence_root.rglob("receipt.json")]
    terminal_failures = [(path, receipt) for path, receipt in failed_receipts if receipt.get("status") == "failure"]
    if len(terminal_failures) != 1:
        raise ValueError("failed v2 evidence no longer has one terminal failure receipt")
    failed_events = terminal_failures[0][0].parent / "events.jsonl"
    statuses = [event.get("data", {}).get("status") for event in (json.loads(line) for line in failed_events.read_text(encoding="utf-8").splitlines()) if event.get("event_type") == "http_attempt"]
    if statuses != [524, 524]:
        raise ValueError("failed v2 evidence no longer binds the two HTTP 524 failures")
    journal = read_json(root / "pilot-journal" / "0001-pilot-01.json")
    if journal.get("status") != "failed" or journal.get("cell_id") != "pilot-01":
        raise ValueError("failed v2 journal does not permanently close v2")
    return {"work_dir": str(root), "commitments": observed, "raw_evidence_tree": observed_tree}


def _v2_parent_inputs(failed_v2_work: Path) -> tuple[Any, dict[str, Any]]:
    """Follow the pinned v2 freeze through its pinned v1 input selection."""
    v2 = _parent_v2()
    v2_frozen = v2.load_frozen(failed_v2_work)
    v1 = v2._parent()
    v1_frozen = v1.load_frozen(Path(str(v2_frozen["parent_work_dir"])))
    return v1, v1_frozen


def _expected_cells(failed_v2_work: Path) -> list[dict[str, Any]]:
    parent, parent_frozen = _v2_parent_inputs(failed_v2_work)
    rows = parent.phase_rows(parent_frozen, "development")[:3]
    question_ids = list(parent_frozen["selection"]["question_ids"][:8])
    if len(rows) != 3 or len({row.get("item_id") for row in rows}) != 3 or len(question_ids) != 8 or len(set(question_ids)) != 8:
        raise ValueError("v2 parent cannot supply the frozen v3 cells")
    cells = []
    for number, row in enumerate(rows, 1):
        folder, source = parent.primary_input(parent_frozen, "development", str(row["item_id"]))
        inputs = {name: fingerprint(folder / name) for name in ("source.md", "prompt.md", "task-contract.json")}
        cells.append({"cell_id": f"pilot-{number:02d}", "item_id": row["item_id"], "selection": dict(source), "inputs": inputs, "question_ids": question_ids})
    return cells


def runtime_bindings() -> dict[str, dict[str, Any]]:
    launcher = runner_module.NOUS_LAUNCHER_PATH
    bridge = launcher.parent / "nous_codex_bridge.py"
    required = {"runner": Path(runner_module.__file__), "launcher": launcher, "bridge": bridge}
    if any(not path.is_file() for path in required.values()):
        raise ValueError("Canonical Nous transport runtime is unavailable")
    return {name: fingerprint(path) for name, path in required.items()}


def freeze_work(failed_v2_work: Path, work: Path) -> dict[str, Any]:
    path = work / "frozen-transport-contract.json"
    if path.exists():
        raise ValueError("Refusing to overwrite a frozen v3 transport contract")
    failed = failed_v2_commitments(failed_v2_work)
    cells = _expected_cells(failed_v2_work)
    value = {"format_version": 1, "study_id": CONTRACT["study_id"], "frozen_before_execution": True, "contract_sha256": sha(CONTRACT_PATH), "failed_v2": failed, "runtime": runtime_bindings(), "provider": CONTRACT["provider"], "pilot": CONTRACT["transport_pilot"], "development": CONTRACT["development"], "cells": cells}
    immutable_json(path, value)
    return value


def load_frozen(work: Path) -> dict[str, Any]:
    value = read_json(work / "frozen-transport-contract.json")
    expected = {"format_version": 1, "study_id": CONTRACT["study_id"], "frozen_before_execution": True, "contract_sha256": sha(CONTRACT_PATH), "runtime": runtime_bindings(), "provider": CONTRACT["provider"], "pilot": CONTRACT["transport_pilot"], "development": CONTRACT["development"]}
    if any(value.get(key) != item for key, item in expected.items()):
        raise ValueError("frozen v3 contract does not bind this protocol/runtime")
    failed = value.get("failed_v2")
    if not isinstance(failed, Mapping) or failed != failed_v2_commitments(Path(str(failed.get("work_dir", "")))):
        raise ValueError("frozen v3 contract no longer binds the failed v2 evidence")
    cells = value.get("cells")
    if not isinstance(cells, list) or cells != _expected_cells(Path(str(failed["work_dir"]))):
        raise ValueError("frozen v3 pilot selection/questions/inputs drifted")
    return value


def input_folder(frozen: Mapping[str, Any], cell: Mapping[str, Any]) -> Path:
    parent, parent_frozen = _v2_parent_inputs(Path(str(frozen["failed_v2"]["work_dir"])))
    folder, _ = parent.primary_input(parent_frozen, "development", str(cell["item_id"]))
    observed = {name: fingerprint(folder / name) for name in ("source.md", "prompt.md", "task-contract.json")}
    if observed != cell.get("inputs"):
        raise ValueError("v3 pilot input bytes drifted")
    return folder
