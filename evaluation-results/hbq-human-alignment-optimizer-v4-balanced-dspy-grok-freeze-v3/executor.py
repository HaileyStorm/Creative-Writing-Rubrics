#!/usr/bin/env python3
"""Provider-free admission for one complete feedback-bound Grok v3 wave."""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import stat
from pathlib import Path
from types import ModuleType
from typing import Any, Mapping


HERE = Path(__file__).resolve().parent
STUDY_ID = "hbq-human-alignment-optimizer-v4-balanced-dspy-grok-freeze-v3"
CONTRACT_PATH = HERE / "study-contract.json"
CONTRACT_SHA256 = "7834dd010e0d346673042810e9ed322935a28fd34ca9736edaf934cf1428f86a"
V3_PATH = HERE.parent / "hbq-human-alignment-optimizer-v4-balanced-dspy-grok-exec-v3" / "executor.py"
V3_SHA256 = "44279db49369029b97a4e2f1216caf99e876b0548910f157bdb3f60f7ea42d4a"
V3_CONTRACT_SHA256 = "b3f5d39e4d127d7ebd29ab9bbbd9c757f347349448b8c2b4d8c97510202888e2"


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _plain(path: Path, *, directory: bool | None = None) -> bool:
    info = os.lstat(path)
    if stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)): return False
    return directory is None or (stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode))


def stable_bytes(path: Path) -> bytes:
    absolute = Path(os.path.abspath(path)); current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current /= part
        if not _plain(current): raise ValueError(f"feedback Grok freeze v3 unsafe path: {current}")
    before = os.lstat(absolute)
    with absolute.open("rb") as handle:
        opened = os.fstat(handle.fileno())
        if (before.st_dev, before.st_ino, before.st_size) != (opened.st_dev, opened.st_ino, opened.st_size): raise ValueError("feedback Grok freeze v3 file identity drifted")
        raw = handle.read(); after = os.fstat(handle.fileno())
    if (opened.st_dev, opened.st_ino, opened.st_size) != (after.st_dev, after.st_ino, after.st_size): raise ValueError("feedback Grok freeze v3 file changed during read")
    return raw


def _load_v3() -> ModuleType:
    raw = stable_bytes(V3_PATH)
    if sha256(raw) != V3_SHA256 or sha256(stable_bytes(V3_PATH.with_name("study-contract.json"))) != V3_CONTRACT_SHA256: raise ValueError("feedback Grok freeze v3 pinned generator drifted")
    module = ModuleType("_feedback_grok_freeze_v3_generator"); module.__file__ = str(V3_PATH); exec(compile(raw, str(V3_PATH), "exec"), module.__dict__)
    if stable_bytes(V3_PATH) != raw: raise ValueError("feedback Grok freeze v3 generator changed during load")
    return module


def _contract() -> None:
    raw = stable_bytes(CONTRACT_PATH)
    if sha256(raw) != CONTRACT_SHA256: raise ValueError("feedback Grok freeze v3 contract drifted")
    value = json.loads(raw.decode("utf-8"))
    expected = {"authority": {"confirmation": {"cells": 0, "status": "unopened"}, "evaluation": False, "promotion": False, "runtime_authority": False, "selection": False}, "format_version": 1, "input": {"v3_contract_sha256": V3_CONTRACT_SHA256, "v3_executor_sha256": V3_SHA256, "v3_git_commit": "6aebdbd1f2ec8dcdeaed80fb83872420096616b2"}, "study_id": STUDY_ID}
    if not isinstance(value, dict) or canonical(value) != raw or value != expected: raise ValueError("feedback Grok freeze v3 contract semantics drifted")


def _object(raw: bytes, label: str) -> dict[str, Any]:
    try: value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error: raise ValueError(f"feedback Grok freeze v3 {label} is invalid") from error
    if not isinstance(value, dict) or canonical(value) != raw: raise ValueError(f"feedback Grok freeze v3 {label} is not canonical")
    return value


def _wave_roots(root: Path) -> list[tuple[str, Path]]:
    if not root.is_dir() or not _plain(root, directory=True): raise ValueError("feedback Grok freeze v3 output root is unsafe")
    entries = list(root.iterdir())
    if len(entries) != 10 or any(not _plain(entry, directory=True) for entry in entries): raise ValueError("feedback Grok freeze v3 requires exactly ten plain sample roots")
    parsed: list[tuple[str, int, Path]] = []
    for entry in entries:
        match = re.fullmatch(r"([a-z0-9][a-z0-9-]{2,63})-sample-(0[1-9]|10)", entry.name)
        if not match: raise ValueError("feedback Grok freeze v3 sample namespace is invalid")
        parsed.append((match.group(1), int(match.group(2)), entry))
    waves = {wave for wave, _number, _entry in parsed}
    if len(waves) != 1 or {number for _wave, number, _entry in parsed} != set(range(1, 11)): raise ValueError("feedback Grok freeze v3 wave geometry is invalid")
    return [(entry.name, entry) for _wave, _number, entry in sorted(parsed, key=lambda row: row[1])]


def _descendant_bytes(result: Mapping[str, Any]) -> tuple[bytes, bytes]:
    descendant = result.get("descendant")
    if not isinstance(descendant, Mapping) or set(descendant) != {"descendant_instruction_base64", "descendant_profile_base64"}: raise ValueError("feedback Grok freeze v3 descendant shape is invalid")
    try: return base64.b64decode(str(descendant["descendant_instruction_base64"]).encode("ascii"), validate=True), base64.b64decode(str(descendant["descendant_profile_base64"]).encode("ascii"), validate=True)
    except (UnicodeEncodeError, ValueError) as error: raise ValueError("feedback Grok freeze v3 descendant bytes are invalid") from error


def freeze_all_ten(*, output_root: Path, manifest_path: Path) -> dict[str, Any]:
    _contract(); root = Path(output_root); target = Path(manifest_path); root_absolute = Path(os.path.abspath(root)); target_absolute = Path(os.path.abspath(target))
    if target_absolute == root_absolute or root_absolute in target_absolute.parents: raise ValueError("feedback Grok freeze v3 manifest target must stay outside output root")
    v3 = _load_v3(); rows: list[dict[str, Any]] = []; shared: set[tuple[str, str, str, int, str, str, str, str, str]] = set(); contacts: set[str] = set(); descendants: set[str] = set(); instruction_bytes: set[bytes] = set(); profile_bytes: set[bytes] = set()
    for sample, cell in _wave_roots(root):
        admitted = v3._admit_completed_root(cell, sample)
        prepared = _object(stable_bytes(cell / "prepared.json"), "prepared record"); receipt = stable_bytes(cell / "execution-receipt.json"); result_raw = stable_bytes(cell / "result.json"); result = _object(result_raw, "result"); runtime = _object(stable_bytes(cell / "runtime-identity.json"), "runtime identity")
        identity = (str(prepared.get("feedback_sha256")), str(prepared.get("r4_result_sha256")), str(prepared.get("r4_selection_sha256")), prepared.get("seed"), str(prepared.get("wave_id")), str(prepared.get("parent_candidate_id")), str(prepared.get("parent_instruction_sha256")), str(prepared.get("parent_profile_sha256")), str(prepared.get("preparation_file_sha256")))
        if not isinstance(identity[3], int) or any(not re.fullmatch(r"[0-9a-f]{64}", item) for item in (*identity[:3], *identity[6:])): raise ValueError("feedback Grok freeze v3 shared lineage is invalid")
        shared.add(identity); request, session, descendant = runtime.get("request_id_hash"), runtime.get("session_id_hash"), admitted.get("descendant_sha256")
        if not all(isinstance(item, str) and re.fullmatch(r"[0-9a-f]{64}", item) for item in (request, session, descendant)) or request == session or request in contacts or session in contacts or descendant in descendants: raise ValueError("feedback Grok freeze v3 cross-root identity is duplicated or invalid")
        instruction, profile = _descendant_bytes(result)
        if instruction in instruction_bytes or profile in profile_bytes: raise ValueError("feedback Grok freeze v3 descendant instruction/profile is duplicated")
        contacts.update({request, session}); descendants.add(descendant); instruction_bytes.add(instruction); profile_bytes.add(profile)
        rows.append({"sample_id": sample, "receipt_sha256": sha256(receipt), "result_sha256": sha256(result_raw), "descendant_sha256": descendant, "request_id_hash": request, "session_id_hash": session})
    if len(shared) != 1 or len(rows) != len(descendants) != len(instruction_bytes) != len(profile_bytes) != 10 or len(contacts) != 20: raise ValueError("feedback Grok freeze v3 aggregate cardinality drifted")
    manifest = {"format_version": 1, "study_id": STUDY_ID, "kind": "feedback_bound_grok_v3_all_ten_frozen", "v3_executor_sha256": V3_SHA256, "shared_lineage": {"feedback_sha256": next(iter(shared))[0], "r4_result_sha256": next(iter(shared))[1], "r4_selection_sha256": next(iter(shared))[2], "seed": next(iter(shared))[3], "wave_id": next(iter(shared))[4], "parent_candidate_id": next(iter(shared))[5], "parent_instruction_sha256": next(iter(shared))[6], "parent_profile_sha256": next(iter(shared))[7], "preparation_file_sha256": next(iter(shared))[8]}, "samples": rows, "confirmation": {"status": "unopened", "cells": 0}, "evaluation_authority": "none", "selection_authority": "none", "promotion_authority": "none", "runtime_authority": "none", "freeze_provider_calls_made": 0, "source_provider_calls_made": 10}
    manifest["manifest_sha256"] = sha256(canonical(manifest))
    if target.exists(): raise ValueError("feedback Grok freeze v3 refuses to overwrite a manifest")
    parent = target.parent; absolute = Path(os.path.abspath(parent)); current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current /= part
        if current.exists() and not _plain(current, directory=True): raise ValueError("feedback Grok freeze v3 manifest ancestry is unsafe")
    parent.mkdir(parents=True, exist_ok=True)
    with target.open("xb") as handle: handle.write(canonical(manifest)); handle.flush(); os.fsync(handle.fileno())
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument("--output-root", type=Path, required=True); parser.add_argument("--manifest-path", type=Path, required=True); args = parser.parse_args(argv)
    print(canonical(freeze_all_ten(output_root=args.output_root, manifest_path=args.manifest_path)).decode("utf-8"), end=""); return 0


if __name__ == "__main__": raise SystemExit(main())
