"""Replay one complete broader Grok development wave without provider contact."""
from __future__ import annotations

import argparse
import base64
import hashlib
import importlib.util
import json
import math
import os
import re
import stat
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path
from types import ModuleType
from typing import Any


HERE = Path(__file__).resolve().parent
STUDY_ID = "hbq-human-alignment-optimizer-v5-f20-broader-development-grok-result-v1"
FREEZE_ID = "hbq-human-alignment-optimizer-v5-f20-broader-development-freeze-v1"
FREEZE_COMMIT = "436da1ef3f8cf239203ac6a80afe8f72708c0415"
FREEZE = HERE.parent / FREEZE_ID / "study.py"
FREEZE_FILES = {
    f"evaluation-results/{FREEZE_ID}/study.py": "507e3c0bec1af6d0acef6e806cf6874a2633e892c9bbf567728f436af30f84bf",
    f"evaluation-results/{FREEZE_ID}/study-contract.json": "3b31c9b0d5ec4c71d6b562045dcd52b2646380cb318d72b83d2119e760543a77",
    f"evaluation-results/{FREEZE_ID}/README.md": "5f8956e96df28ddfe37533e631c163f1cdbf711e820e05e2607618975bf0e75f",
    "tests/test_hbq_human_alignment_optimizer_v5_f20_broader_development_freeze_v1.py": "5c58ac8eb15227703a090c4f2bd3aedd547b040fd4cb3ea66788018a78419656",
}
SCHEDULE_SHA256 = "bdb40b0f24f07ea938d57951768101a93ff62575919075abcd7bb9534e12c52c"
V2_ID = "hbq-human-alignment-optimizer-v5-f20-broader-development-grok-exec-v2-slot-acquire-transition"
V2_RELATIVE = f"evaluation-results/{V2_ID}"
DIMENSIONS = ("Relevance", "Coherence", "Empathy", "Surprise", "Engagement", "Complexity")
PARENT = "normalized-nextwave-08-conservative-hybrid"
PUBLIC_FILES = {"README.md", "study-contract.json", "verify.py"}
PATH_PATTERN = re.compile(r"(?:[A-Za-z]:[\\/]|\\\\[^\\]+\\[^\\]+|/(?:Users|home|private|tmp)/)")


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def sha256(value: bytes | Any) -> str:
    return hashlib.sha256(value if isinstance(value, bytes) else canonical(value)).hexdigest()


def _plain(path: Path, *, directory: bool | None = None) -> None:
    info = os.lstat(path)
    if stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)):
        raise ValueError("unsafe or reparsed path")
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


def _canonical(path: Path, label: str) -> tuple[bytes, dict[str, Any]]:
    raw = stable(path)
    value = strict(raw, label)
    if raw != canonical(value):
        raise ValueError(f"{label} is not canonical")
    return raw, value


def _git_blob(repo: Path, commit: str, relative: str) -> bytes:
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("pinned commit must be a full SHA-1")
    result = subprocess.run(["git", "-C", str(repo), "show", f"{commit}:{relative}"], capture_output=True, check=False)
    if result.returncode != 0:
        raise ValueError("pinned Git source is absent")
    return result.stdout


def _load(path: Path, name: str) -> ModuleType:
    raw = stable(path)
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ValueError("cannot load pinned module")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(name, None)
    if stable(path) != raw:
        raise ValueError("pinned module changed during load")
    return module


def _load_freeze(repo: Path) -> ModuleType:
    for relative, digest in FREEZE_FILES.items():
        raw = stable(repo / relative)
        if sha256(raw) != digest or _git_blob(repo, FREEZE_COMMIT, relative) != raw:
            raise ValueError("pinned broader freeze dependency drifted")
    return _load(FREEZE, "_broader_grok_result_freeze")


def _load_v2(repo: Path, *, commit: str, executor_sha256: str, contract_sha256: str) -> ModuleType:
    supplied = {"executor.py": executor_sha256, "study-contract.json": contract_sha256}
    if any(not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value) for value in supplied.values()):
        raise ValueError("V2 source hashes must be SHA-256 values")
    package = repo / V2_RELATIVE
    for name, digest in supplied.items():
        relative = f"{V2_RELATIVE}/{name}"
        raw = stable(package / name)
        if sha256(raw) != digest or _git_blob(repo, commit, relative) != raw:
            raise ValueError("pinned V2 dependency drifted or is not committed")
    module = _load(package / "executor.py", "_broader_grok_result_v2")
    if module.STUDY_ID != V2_ID:
        raise ValueError("V2 study identity drifted")
    return module


def _schedule(freeze: ModuleType, *, frozen_root: Path, normalized_root: Path, materialization_root: Path, frozen_successor_path: Path, hanna_csv_path: Path) -> tuple[dict[str, Any], dict[str, dict[str, float]]]:
    persisted = freeze.validate_frozen_root(Path(frozen_root))
    rebuilt = freeze.build(normalized_root=Path(normalized_root), materialization_root=Path(materialization_root), frozen_successor_path=Path(frozen_successor_path), hanna_csv_path=Path(hanna_csv_path))
    if canonical(persisted) != canonical(rebuilt) or persisted.get("schedule_sha256") != SCHEDULE_SHA256:
        raise ValueError("frozen broader schedule does not independently reconstruct")
    study, _harness, _freeze, _split, _parents = freeze._v3()._material(frozen_successor_path=Path(frozen_successor_path), hanna_csv_path=Path(hanna_csv_path))
    targets = freeze._v3().v2_module()._human_targets(study=study, frozen_successor_path=Path(frozen_successor_path), hanna_csv_path=Path(hanna_csv_path))
    return persisted, targets


def _project(schedule: Mapping[str, Any], collector: Mapping[str, Any], targets: Mapping[str, Mapping[str, float]], extractor: Any) -> dict[str, Any]:
    if schedule.get("study_id") != FREEZE_ID or schedule.get("schedule_sha256") != SCHEDULE_SHA256:
        raise ValueError("schedule identity drifted")
    cells = schedule.get("cells")
    groups = schedule.get("groups")
    if not isinstance(cells, list) or not isinstance(groups, list) or len(cells) != 35 or len(groups) != 7:
        raise ValueError("35-cell broader geometry drifted")
    index = {row.get("cell_id"): row for row in cells if isinstance(row, Mapping)}
    expected_groups = {row.get("prompt_group_id") for row in groups if isinstance(row, Mapping)}
    expected_candidates = {row.get("candidate_id") for row in cells if isinstance(row, Mapping)}
    expected_collector = {"format_version", "study_id", "kind", "schedule_sha256", "authorization_acknowledgement_sha256", "route", "route_evidence", "cells", "native_endpoint_contact_cardinality", "provider_calls_made", "process_launches"}
    if (set(collector) != expected_collector or collector.get("format_version") != 1 or collector.get("study_id") != V2_ID or collector.get("kind") != "complete_35_broader_grok_receipts_cardinality_unproven" or collector.get("schedule_sha256") != SCHEDULE_SHA256 or not isinstance(collector.get("route"), Mapping) or not isinstance(collector.get("route_evidence"), Mapping) or collector.get("native_endpoint_contact_cardinality") != "unproven" or collector.get("provider_calls_made") != 0 or collector.get("process_launches") != 0 or not isinstance(collector.get("authorization_acknowledgement_sha256"), str) or not re.fullmatch(r"[0-9a-f]{64}", collector["authorization_acknowledgement_sha256"])):
        raise ValueError("collector identity or caller aggregate surface drifted")
    supplied = collector.get("cells")
    if not isinstance(supplied, list) or len(supplied) != 35 or len(index) != 35 or len(expected_groups) != 7 or len(expected_candidates) != 5 or PARENT not in expected_candidates:
        raise ValueError("collector or schedule geometry drifted")
    observed: dict[str, dict[str, float]] = {candidate: {} for candidate in expected_candidates}
    seen_contacts: set[tuple[str, str]] = set()
    seen_cells: set[str] = set()
    for entry in supplied:
        required = {"cell_id", "payload_base64", "payload_sha256", "native_request_base64", "native_request_sha256", "native_response_base64", "native_response_sha256", "identity", "effective_settings", "effective_settings_sha256"}
        if not isinstance(entry, Mapping) or set(entry) != required:
            raise ValueError("collector cell fields drifted")
        cell_id = entry.get("cell_id")
        row = index.get(cell_id)
        if not isinstance(cell_id, str) or cell_id in seen_cells or not isinstance(row, Mapping):
            raise ValueError("duplicate or unknown collector cell")
        try:
            response = base64.b64decode(entry["native_response_base64"], validate=True)
            request = base64.b64decode(entry["native_request_base64"], validate=True)
        except (TypeError, ValueError) as error:
            raise ValueError("collector native bytes are invalid") from error
        identity = entry.get("identity")
        contact = (identity.get("request_id"), identity.get("session_id")) if isinstance(identity, Mapping) else (None, None)
        if (entry.get("payload_base64") != row.get("payload_base64") or entry.get("payload_sha256") != row.get("payload_sha256") or entry.get("native_request_sha256") != sha256(request) or entry.get("native_response_sha256") != sha256(response) or entry.get("effective_settings_sha256") != sha256(entry.get("effective_settings")) or not all(isinstance(value, str) and value for value in contact) or contact in seen_contacts):
            raise ValueError("collector receipt/payload/identity binding drifted")
        scores, _coverage, _reported = extractor(response, provider="xai", model="grok-4.6")
        target = targets.get(row.get("item_id"))
        if not isinstance(target, Mapping) or set(scores) != set(DIMENSIONS) or set(target) != set(DIMENSIONS):
            raise ValueError("independent HANNA target reconstruction drifted")
        observed[row["candidate_id"]][row["prompt_group_id"]] = sum(abs(scores[key] - target[key]) for key in DIMENSIONS) / len(DIMENSIONS)
        seen_cells.add(cell_id); seen_contacts.add(contact)
    if seen_cells != set(index):
        raise ValueError("partial collector")
    metrics = []
    for candidate in sorted(expected_candidates):
        group_mae = observed[candidate]
        if set(group_mae) != expected_groups:
            raise ValueError("candidate is missing an equal-group observation")
        metrics.append({"candidate_id": candidate, "cells": 7, "equal_group_mae": sum(group_mae.values()) / 7, "group_mae": dict(sorted(group_mae.items()))})
    metrics.sort(key=lambda row: (row["equal_group_mae"], row["candidate_id"]))
    parent = next(row for row in metrics if row["candidate_id"] == PARENT)
    if parent["equal_group_mae"] <= 0:
        raise ValueError("parent MAE must be positive for relative deltas")
    descendants = [{"candidate_id": row["candidate_id"], "absolute_delta": row["equal_group_mae"] - parent["equal_group_mae"], "relative_reduction": -(row["equal_group_mae"] - parent["equal_group_mae"]) / parent["equal_group_mae"]} for row in metrics if row["candidate_id"] != PARENT]
    selected = metrics[0]
    return {"format_version": 1, "study_id": STUDY_ID, "kind": "descriptive_broader_grok_development_equal_group_mae", "authority": {"selection": "grok_development_only", "confirmation": "unopened", "generalization": "none", "promotion": "none", "runtime": "none", "endpoint_pooling": "forbidden"}, "claim": "DESCRIPTIVE_GROK_DEVELOPMENT_ONLY; no Sol, generalization, confirmation, promotion, runtime, or endpoint-pooled claim", "evidence_ceiling": {"native_endpoint_contact_cardinality": "unproven", "process_lifecycle_receipts": 35, "provider_calls_made": None}, "metrics": metrics, "selection": {"candidate_id": selected["candidate_id"], "equal_group_mae": selected["equal_group_mae"], "tie_breakers": ["equal_group_mae:ascending", "candidate_id:lexicographic"]}, "parent_vs_descendant": descendants}


def replay(*, frozen_root: Path, normalized_root: Path, materialization_root: Path, frozen_successor_path: Path, hanna_csv_path: Path, output_root: Path, collector_path: Path, v2_commit: str, v2_executor_sha256: str, v2_contract_sha256: str) -> dict[str, Any]:
    repo = HERE.parents[1]
    freeze = _load_freeze(repo)
    schedule, targets = _schedule(freeze, frozen_root=frozen_root, normalized_root=normalized_root, materialization_root=materialization_root, frozen_successor_path=frozen_successor_path, hanna_csv_path=hanna_csv_path)
    v2 = _load_v2(repo, commit=v2_commit, executor_sha256=v2_executor_sha256, contract_sha256=v2_contract_sha256)
    replayed = v2.replay_collector(output_root=Path(output_root), frozen_root=Path(frozen_root), collector_path=Path(collector_path))
    if replayed.get("cells") != 35 or replayed.get("equal_group_projection_ready") is not True:
        raise ValueError("V2 receipt replay is incomplete")
    collector_raw, collector = _canonical(Path(collector_path), "collector")
    result = _project(schedule, collector, targets, freeze._v3().v2_module()._extract_native)
    result["source_execution"] = {"freeze_commit": FREEZE_COMMIT, "freeze_schedule_sha256": SCHEDULE_SHA256, "v2_commit": v2_commit, "v2_executor_sha256": v2_executor_sha256, "v2_contract_sha256": v2_contract_sha256, "collector_sha256": sha256(collector_raw)}
    result["result_internal_sha256"] = sha256(result)
    return result


def validate_package() -> dict[str, Any]:
    root = _safe(HERE, directory=True)
    if {path.name for path in root.iterdir()} != PUBLIC_FILES:
        raise ValueError("prepared result package inventory drifted")
    contract_raw, contract = _canonical(root / "study-contract.json", "study contract")
    readme = stable(root / "README.md").decode("utf-8")
    if PATH_PATTERN.search(readme) or PATH_PATTERN.search(contract_raw.decode("utf-8")):
        raise ValueError("prepared public surface contains a local path")
    if contract.get("study_id") != STUDY_ID or contract.get("pinned_freeze", {}).get("schedule_sha256") != SCHEDULE_SHA256:
        raise ValueError("prepared package identity drifted")
    return contract


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("frozen-root", "normalized-root", "materialization-root", "frozen-successor", "hanna-csv", "output-root", "collector-path", "v2-commit", "v2-executor-sha256", "v2-contract-sha256"):
        parser.add_argument("--" + name)
    args = parser.parse_args(argv)
    names = ("frozen_root", "normalized_root", "materialization_root", "frozen_successor", "hanna_csv", "output_root", "collector_path", "v2_commit", "v2_executor_sha256", "v2_contract_sha256")
    values = [getattr(args, name) for name in names]
    validate_package()
    if any(values) and not all(values):
        parser.error("provide every replay input or none")
    if all(values):
        result = replay(frozen_root=Path(args.frozen_root), normalized_root=Path(args.normalized_root), materialization_root=Path(args.materialization_root), frozen_successor_path=Path(args.frozen_successor), hanna_csv_path=Path(args.hanna_csv), output_root=Path(args.output_root), collector_path=Path(args.collector_path), v2_commit=args.v2_commit, v2_executor_sha256=args.v2_executor_sha256, v2_contract_sha256=args.v2_contract_sha256)
        print(canonical(result).decode("utf-8"), end="")
    else:
        print(canonical({"provider_calls_made": 0, "prepared_package": "verified", "study_id": STUDY_ID}).decode("utf-8"), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
