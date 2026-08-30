#!/usr/bin/env python3
"""Provider-free balanced replay after one immutable Grok terminal."""
from __future__ import annotations

import hashlib
import json
import os
import stat
from pathlib import Path
from types import ModuleType
from typing import Any, Mapping, Sequence


HERE = Path(__file__).resolve().parent
STUDY_ID = "hbq-human-alignment-optimizer-v4-lean-training-balanced-v1"
CONTRACT_PATH = HERE / "study-contract.json"
CONTRACT_SHA256 = "b0382ecc6d95ee0c69e94ec9c960a204c99a57eb44cbffc1a5ef35f4b108a3ff"
BASE_PATH = HERE.parent / "hbq-human-alignment-optimizer-v4-lean-training-verifier-v1" / "verifier.py"
BASE_SHA256 = "926880d3173c2d3df2a02a51dbe0c9c16ad2985a48b07429ad2d0fd7fd7f45df"
FAILED_CELL_ID = "v4-cell-327fe788866eb61b"
FAILED_TERMINAL_INVENTORY_SHA256 = "48f1f9b8ca0aaa4289bbeb185629e5403d7d736d486ff31c973d26467c68ac66"
FAILED_TERMINAL_RESULT_SHA256 = "ae47330428b9cb459d5dee6f8225406fa7712b237101415a54c38baf3237ceb8"
REFERENCE_KEYS = frozenset({"cell_id", "execution_root"})
MANIFEST_KEYS = frozenset({"format_version", "study_id", "kind", "base_verifier_sha256", "schedule_sha256", "cells", "failed_terminal", "provider_calls_made", "confirmation"})
TERMINAL_KEYS = frozenset({"cell_id", "execution_root", "inventory", "inventory_sha256", "result_sha256"})


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _plain(path: Path, *, directory: bool | None = None) -> None:
    info = os.lstat(path)
    if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400):
        raise ValueError(f"HANNA balanced verifier path is reparsed: {path}")
    if directory is True and not stat.S_ISDIR(info.st_mode):
        raise ValueError(f"HANNA balanced verifier expected directory: {path}")
    if directory is False and not stat.S_ISREG(info.st_mode):
        raise ValueError(f"HANNA balanced verifier expected plain file: {path}")


def _stable_bytes(path: Path) -> bytes:
    absolute, current = Path(os.path.abspath(path)), Path(Path(os.path.abspath(path)).anchor)
    for part in absolute.parts[1:]:
        current /= part
        _plain(current)
    _plain(absolute, directory=False)
    before = os.lstat(absolute)
    with absolute.open("rb") as handle:
        opened = os.fstat(handle.fileno())
        if (before.st_dev, before.st_ino, before.st_size) != (opened.st_dev, opened.st_ino, opened.st_size):
            raise ValueError("HANNA balanced verifier file identity drifted")
        raw = handle.read()
        after = os.fstat(handle.fileno())
        if (opened.st_dev, opened.st_ino, opened.st_size) != (after.st_dev, after.st_ino, after.st_size):
            raise ValueError("HANNA balanced verifier file changed during read")
    return raw


def _object(path: Path, label: str) -> dict[str, Any]:
    try:
        raw = _stable_bytes(path)
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"HANNA balanced verifier {label} is unavailable or invalid") from error
    if not isinstance(value, dict) or canonical(value) != raw:
        raise ValueError(f"HANNA balanced verifier {label} is noncanonical")
    return value


def contract() -> dict[str, Any]:
    value = _object(CONTRACT_PATH, "study contract")
    if sha256_bytes(_stable_bytes(CONTRACT_PATH)) != CONTRACT_SHA256 or value.get("study_id") != STUDY_ID:
        raise ValueError("HANNA balanced verifier study contract identity drifted")
    if value.get("source_terminal") != {"cell_id": FAILED_CELL_ID, "inventory_sha256": FAILED_TERMINAL_INVENTORY_SHA256, "result_sha256": FAILED_TERMINAL_RESULT_SHA256}:
        raise ValueError("HANNA balanced verifier study contract terminal commitment drifted")
    return value


def _base() -> ModuleType:
    contract()
    raw = _stable_bytes(BASE_PATH)
    if sha256_bytes(raw) != BASE_SHA256:
        raise ValueError("HANNA balanced verifier parent source drifted")
    module = ModuleType("_hanna_lean_training_base"); module.__file__ = str(BASE_PATH)
    exec(compile(raw, str(BASE_PATH), "exec"), module.__dict__)
    if sha256_bytes(_stable_bytes(BASE_PATH)) != BASE_SHA256:
        raise ValueError("HANNA balanced verifier parent source changed during load")
    return module


def _snapshot(root: Path) -> dict[str, Any]:
    absolute = Path(os.path.abspath(root))
    _plain(absolute, directory=True)
    directories: list[str] = []
    files: dict[str, str] = {}
    stack = [absolute]
    while stack:
        current = stack.pop()
        relative = current.relative_to(absolute).as_posix()
        directories.append(relative)
        entries = sorted(current.iterdir(), key=lambda entry: entry.name, reverse=True)
        for entry in entries:
            _plain(entry)
            if entry.is_dir():
                stack.append(entry)
            else:
                files[entry.relative_to(absolute).as_posix()] = sha256_bytes(_stable_bytes(entry))
    return {"directories": sorted(directories), "files": dict(sorted(files.items()))}


def _terminal(root: Path, base: ModuleType) -> dict[str, Any]:
    first = _snapshot(root)
    result_raw = _stable_bytes(root / "result.json")
    result = _object(root / "result.json", "failed terminal result")
    expected = {
        "format_version": 1, "study_id": base.COLLECTOR_PATH.parent.name, "kind": "reconcile_required_after_process_launch",
        "cell_id": FAILED_CELL_ID, "error_type": "_ProviderAttemptFailure", "provider_calls_made": 1, "process_launches": 1,
    }
    if result != expected:
        raise ValueError("HANNA balanced verifier failed terminal result drifted")
    inventory_sha256, result_sha256 = sha256_bytes(canonical(first)), sha256_bytes(result_raw)
    if inventory_sha256 != FAILED_TERMINAL_INVENTORY_SHA256 or result_sha256 != FAILED_TERMINAL_RESULT_SHA256:
        raise ValueError("HANNA balanced verifier failed terminal does not match the pinned source")
    second = _snapshot(root)
    if first != second:
        raise ValueError("HANNA balanced verifier failed terminal inventory changed during replay")
    return {
        "cell_id": FAILED_CELL_ID, "execution_root": str(root), "inventory": first,
        "inventory_sha256": inventory_sha256, "result_sha256": result_sha256,
    }


def _balanced_rows(base: ModuleType, *, frozen_successor_path: Path, hanna_csv_path: Path) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    _collector, optimizer, _native, _exec_v1, _exec_v3 = base._dependencies()
    schedule, all_rows = base._rows(optimizer, Path(frozen_successor_path), Path(hanna_csv_path))
    failed = next((row for row in all_rows if row["cell_id"] == FAILED_CELL_ID), None)
    if failed is None or failed["route_name"] != "grok_primary":
        raise ValueError("HANNA balanced verifier failed Grok row drifted")
    excluded = [row for row in all_rows if row["route_name"] == "grok_primary" and row["prompt_group_id"] == failed["prompt_group_id"]]
    kept = [row for row in all_rows if row not in excluded]
    grok = [row for row in kept if row["route_name"] == "grok_primary"]
    sol = [row for row in kept if row["route_name"] == "sol_validation"]
    candidates = set(schedule["candidate_ids"])
    groups = {row["prompt_group_id"] for row in grok}
    if (len(excluded), len(grok), len(sol), len(groups), len(candidates)) != (5, 20, 10, 4, 5):
        raise ValueError("HANNA balanced verifier geometry drifted")
    if {row["candidate_id"] for row in excluded} != candidates or {row["item_id"] for row in excluded} != {failed["item_id"]}:
        raise ValueError("HANNA balanced verifier excluded group is incomplete")
    for group in groups:
        members = [row for row in grok if row["prompt_group_id"] == group]
        if len(members) != 5 or {row["candidate_id"] for row in members} != candidates:
            raise ValueError("HANNA balanced verifier retained Grok group is incomplete")
    train = [*grok, *sol]
    development = [*schedule["partitions"]["grok_development"], *schedule["partitions"]["sol_validation_templates"]]
    if ({row["item_id"] for row in train} & {row["item_id"] for row in development}
            or {row["prompt_group_id"] for row in train} & {row["prompt_group_id"] for row in development}):
        raise ValueError("HANNA balanced verifier train/development partition overlap")
    return schedule, kept, excluded, failed


def prepare_balanced_manifest(*, references: Sequence[Mapping[str, Any]], failed_terminal_root: Path, frozen_successor_path: Path, hanna_csv_path: Path) -> dict[str, Any]:
    base = _base()
    schedule, rows, excluded, failed = _balanced_rows(base, frozen_successor_path=Path(frozen_successor_path), hanna_csv_path=Path(hanna_csv_path))
    normalized = [dict(reference) for reference in references]
    if (len(normalized) != len(rows) or any(set(reference) != REFERENCE_KEYS for reference in normalized)
            or [reference["cell_id"] for reference in normalized] != [row["cell_id"] for row in rows]
            or any(not isinstance(reference["execution_root"], str) for reference in normalized)):
        raise ValueError("HANNA balanced verifier requires exactly the ordered complete balanced rows")
    terminal = _terminal(Path(failed_terminal_root), base)
    return {
        "format_version": 1, "study_id": STUDY_ID, "kind": "balanced_lean_training_collector_receipts",
        "base_verifier_sha256": BASE_SHA256, "schedule_sha256": schedule["schedule_sha256"], "cells": normalized,
        "failed_terminal": terminal, "provider_calls_made": 0,
        "confirmation": {"status": "unopened", "cells": 0},
    }


def verify_balanced_training_receipts(*, collection_evidence_path: Path, frozen_successor_path: Path, hanna_csv_path: Path) -> dict[str, Any]:
    base = _base()
    manifest = _object(Path(collection_evidence_path), "balanced collector manifest")
    if set(manifest) != MANIFEST_KEYS or manifest.get("format_version") != 1 or manifest.get("study_id") != STUDY_ID or manifest.get("kind") != "balanced_lean_training_collector_receipts":
        raise ValueError("HANNA balanced verifier manifest identity drifted")
    if manifest.get("base_verifier_sha256") != BASE_SHA256 or manifest.get("provider_calls_made") != 0 or manifest.get("confirmation") != {"status": "unopened", "cells": 0}:
        raise ValueError("HANNA balanced verifier manifest authority drifted")
    schedule, rows, excluded, failed = _balanced_rows(base, frozen_successor_path=Path(frozen_successor_path), hanna_csv_path=Path(hanna_csv_path))
    references = manifest["cells"]
    if (manifest.get("schedule_sha256") != schedule["schedule_sha256"] or not isinstance(references, list)
            or len(references) != len(rows) or any(not isinstance(reference, Mapping) or set(reference) != REFERENCE_KEYS for reference in references)
            or [reference["cell_id"] for reference in references] != [row["cell_id"] for row in rows]):
        raise ValueError("HANNA balanced verifier refuses partial, aggregate, or unbalanced evidence")
    terminal = manifest.get("failed_terminal")
    if not isinstance(terminal, Mapping) or set(terminal) != TERMINAL_KEYS:
        raise ValueError("HANNA balanced verifier failed terminal binding is invalid")
    replayed_terminal = _terminal(Path(terminal["execution_root"]), base)
    if dict(terminal) != replayed_terminal:
        raise ValueError("HANNA balanced verifier failed terminal binding drifted")
    collector, optimizer, native, exec_v1, exec_v3 = base._dependencies()
    observations, contacts = [], set()
    for reference, row in zip(references, rows, strict=True):
        observation = base._cell(collector, optimizer, native, exec_v1, exec_v3, Path(reference["execution_root"]), row, schedule, frozen_successor_path=Path(frozen_successor_path), hanna_csv_path=Path(hanna_csv_path))
        identity = observation["identity"]
        contact = (identity["provider"], identity["contact_id"], identity["session_id"])
        if contact in contacts:
            raise ValueError("HANNA balanced verifier duplicate collector contact identity")
        contacts.add(contact); observations.append(observation)
    targets = optimizer._targets(native, rows, frozen_successor_path=Path(frozen_successor_path), hanna_csv_path=Path(hanna_csv_path))
    projection = {
        "format_version": 1, "study_id": STUDY_ID, "kind": "balanced_lean_training_optimizer_observation_projection",
        "balanced_collection_evidence_sha256": sha256_bytes(_stable_bytes(Path(collection_evidence_path))),
        "dependencies": {"balanced_verifier_source_sha256": sha256_bytes(_stable_bytes(Path(__file__))), "balanced_contract_sha256": sha256_bytes(_stable_bytes(CONTRACT_PATH)), "base_verifier_sha256": BASE_SHA256},
        "schedule_sha256": schedule["schedule_sha256"], "stage": "training", "observations": observations, "human_targets": targets,
        "geometry": {"grok_prompt_groups": 4, "grok_candidates_per_group": 5, "grok_cells": 20, "sol_cells": 10, "total_cells": 30},
        "excluded_terminal": {"cell_id": failed["cell_id"], "prompt_group_id": failed["prompt_group_id"], "grok_cells": len(excluded), "inventory_sha256": terminal["inventory_sha256"], "result_sha256": terminal["result_sha256"]},
        "confirmation": {"status": "unopened", "cells": 0}, "provider_calls_made": 0, "runtime_authority": "none",
    }
    projection["projection_sha256"] = sha256_bytes(canonical(projection))
    return projection
