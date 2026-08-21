"""Frozen score-blind Nous transport pilot and gated batch-16 successor."""
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
PARENT_ROOT = (HERE / "../hbq-human-alignment-supplemental-providers-v1").resolve()


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fingerprint(path: Path) -> dict[str, Any]:
    path = path.resolve()
    return {"name": path.name, "bytes": path.stat().st_size, "sha256": sha(path)}


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def _immutable_json(path: Path, value: Mapping[str, Any]) -> None:
    rendered = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
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
    if contract.get("format_version") != 1 or contract.get("study_id") != "hbq-human-alignment-supplemental-providers-v2" or contract.get("frozen_before_execution") is not True:
        raise ValueError("Transport successor contract is not the frozen v2 protocol")
    parent = contract.get("parent_v1")
    if not isinstance(parent, Mapping) or parent.get("path") != "../hbq-human-alignment-supplemental-providers-v1" or not isinstance(parent.get("files"), Mapping):
        raise ValueError("Transport successor parent binding is malformed")
    pilot = contract.get("transport_pilot")
    if not isinstance(pilot, Mapping) or pilot.get("cells") != 3 or pilot.get("batch_size") != 16 or pilot.get("question_count") != 16 or pilot.get("batch_attempts") != 1 or pilot.get("workers") != 1 or pilot.get("maximum_completion_seconds_exclusive") != 100:
        raise ValueError("Transport successor pilot policy drifted")
    if contract.get("provider") != {"provider_id": "nous_flash_max", "provider": "nous", "model": "deepseek/deepseek-v4-flash-0731", "reasoning": "max", "allow_unattested_reasoning": True}:
        raise ValueError("Transport successor provider policy drifted")
    return contract


CONTRACT = load_contract()


def _parent() -> Any:
    parent = CONTRACT["parent_v1"]
    for name, expected in parent["files"].items():
        path = PARENT_ROOT / name
        if not path.is_file() or sha(path) != expected:
            raise ValueError(f"v1 parent file drifted: {name}")
    runner = ROOT / "src/hbqrs/runner.py"
    if not runner.is_file() or sha(runner) != parent["runner_sha256"]:
        raise ValueError("v1 parent runner binding drifted")
    spec = importlib.util.spec_from_file_location("hanna_supplemental_v2_parent", PARENT_ROOT / "study.py")
    if spec is None or spec.loader is None:
        raise ValueError("v1 parent study helper is unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def runtime_bindings() -> dict[str, dict[str, Any]]:
    launcher = runner_module.NOUS_LAUNCHER_PATH
    bridge = launcher.parent / "nous_codex_bridge.py"
    required = {"runner": Path(runner_module.__file__), "launcher": launcher, "bridge": bridge}
    if any(not path.is_file() for path in required.values()):
        raise ValueError("Canonical Nous transport runtime is unavailable")
    return {name: fingerprint(path) for name, path in required.items()}


def _input_binding(parent: Any, frozen: Mapping[str, Any], item_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    folder, row = parent.primary_input(frozen, "development", item_id)
    files = {name: fingerprint(folder / name) for name in ("source.md", "prompt.md", "task-contract.json")}
    return dict(row), files


def freeze_work(parent_work: Path, work: Path) -> dict[str, Any]:
    path = work / "frozen-transport-contract.json"
    if path.exists():
        raise ValueError("Refusing to overwrite a frozen v2 transport contract")
    parent = _parent()
    parent_frozen = parent.load_frozen(parent_work)
    rows = parent.phase_rows(parent_frozen, "development")[: CONTRACT["transport_pilot"]["cells"]]
    if len(rows) != 3 or len({row.get("item_id") for row in rows}) != 3:
        raise ValueError("v1 development selection cannot provide three independent pilot cells")
    question_ids = list(parent_frozen["selection"]["question_ids"][: CONTRACT["transport_pilot"]["question_count"]])
    if len(question_ids) != 16 or len(set(question_ids)) != 16:
        raise ValueError("v1 question sequence cannot provide the frozen 16-question pilot")
    cells = []
    for number, row in enumerate(rows, 1):
        source_row, inputs = _input_binding(parent, parent_frozen, str(row["item_id"]))
        cells.append({"cell_id": f"pilot-{number:02d}", "item_id": row["item_id"], "selection": source_row, "inputs": inputs, "question_ids": question_ids})
    value = {
        "format_version": 1,
        "study_id": CONTRACT["study_id"],
        "frozen_before_execution": True,
        "contract_sha256": sha(CONTRACT_PATH),
        "parent_work_dir": str(parent_work.resolve()),
        "parent_frozen": fingerprint(parent_work / "frozen-provider-contract.json"),
        "parent_runtime": {name: {"sha256": digest} for name, digest in CONTRACT["parent_v1"]["files"].items()},
        "runtime": runtime_bindings(),
        "provider": CONTRACT["provider"],
        "pilot": CONTRACT["transport_pilot"],
        "development": CONTRACT["development"],
        "cells": cells,
    }
    _immutable_json(path, value)
    return value


def load_frozen(work: Path) -> dict[str, Any]:
    value = read_json(work / "frozen-transport-contract.json")
    expected = {"format_version": 1, "study_id": CONTRACT["study_id"], "frozen_before_execution": True, "contract_sha256": sha(CONTRACT_PATH), "provider": CONTRACT["provider"], "pilot": CONTRACT["transport_pilot"], "development": CONTRACT["development"], "runtime": runtime_bindings()}
    if any(value.get(key) != item for key, item in expected.items()):
        raise ValueError("Frozen v2 transport contract does not bind this protocol/runtime")
    parent_work = Path(str(value.get("parent_work_dir", "")))
    if not parent_work.is_dir() or value.get("parent_frozen") != fingerprint(parent_work / "frozen-provider-contract.json"):
        raise ValueError("Frozen v2 transport contract no longer binds its v1 parent work")
    parent = _parent()
    parent_frozen = parent.load_frozen(parent_work)
    if value.get("parent_runtime") != {name: {"sha256": digest} for name, digest in CONTRACT["parent_v1"]["files"].items()}:
        raise ValueError("Frozen v2 transport contract parent runtime binding drifted")
    cells = value.get("cells")
    if not isinstance(cells, list) or len(cells) != 3 or [cell.get("cell_id") for cell in cells] != ["pilot-01", "pilot-02", "pilot-03"]:
        raise ValueError("Frozen v2 transport pilot cells drifted")
    expected_rows = parent.phase_rows(parent_frozen, "development")[:3]
    for cell, row in zip(cells, expected_rows):
        source_row, inputs = _input_binding(parent, parent_frozen, str(row["item_id"]))
        if cell.get("item_id") != row["item_id"] or cell.get("selection") != source_row or cell.get("inputs") != inputs or cell.get("question_ids") != list(parent_frozen["selection"]["question_ids"][:16]):
            raise ValueError("Frozen v2 pilot inputs no longer bind the v1 parent selection")
    return value


def input_folder(frozen: Mapping[str, Any], cell: Mapping[str, Any]) -> Path:
    parent = _parent()
    parent_frozen = parent.load_frozen(Path(str(frozen["parent_work_dir"])))
    folder, _ = parent.primary_input(parent_frozen, "development", str(cell["item_id"]))
    observed = {name: fingerprint(folder / name) for name in ("source.md", "prompt.md", "task-contract.json")}
    if observed != cell.get("inputs"):
        raise ValueError("Pilot input bytes drifted")
    return folder


def immutable_json(path: Path, value: Mapping[str, Any]) -> None:
    _immutable_json(path, value)
