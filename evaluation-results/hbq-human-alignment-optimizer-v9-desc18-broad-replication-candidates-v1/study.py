"""Freeze an open-split Fresh96 replication of descendant13 against child20."""
from __future__ import annotations

import argparse
import base64
import hashlib
import importlib.util
import json
import os
from collections.abc import Mapping
from copy import deepcopy
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
STUDY_ID = "hbq-human-alignment-optimizer-v9-desc18-broad-replication-candidates-v1"
SOURCE = HERE.parent / "hbq-human-alignment-hanna96-validation-freeze-v1" / "study.py"
SOURCE_SHA256 = "d8b99c651cfbc0c04207101a6ad15373168a5ffad3711f7d17fb589e8a13542e"
SOURCE_SCHEDULE_SHA256 = "639c34bb1d07266759280249b6b74a51c05d51f60ed27eb3aed0b2ea6c3bfee2"
DESC16 = HERE.parent / "hbq-human-alignment-optimizer-v7-desc16-referent-evidence-candidates-v1" / "study.py"
DESC16_SHA256 = "31735918ae0d9a1e2871e0b40ac00b3c587388531f9c721a73e7334900f2f29a"
PARENT_ID = "broader-nextwave-13-missing_evidence_not_no"
PARENT_CANDIDATE_SHA256 = "d8e55620d3a91ac17762d9ac40f7be3bb8aa87a478d6593f6ebda906d28b4684"
CHILD_ID = "broader-nextwave-20-missing_evidence_not_no-referent-evidence"
CHILD_CANDIDATE_SHA256 = "572d5e6b96251eacf19951a10574aaefb811beb9d7890e9f702b524d3c5465bb"
CHILD_PROFILE_SHA256 = "07cd3652f4792aef082a0e2d9d615229013663b14599abd011637daf8f185a20"
CONTRACT_SHA256 = "5115e46f3f8c858e7954ceffa77d2d9dbff3e781f36a5aaf04fb2506c7c07dd2"


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def digest(value: bytes | Any) -> str:
    return hashlib.sha256(value if isinstance(value, bytes) else canonical(value)).hexdigest()


def _module(path: Path, expected_sha256: str, name: str):
    if digest(path.read_bytes()) != expected_sha256:
        raise ValueError(f"{name} bytes drifted")
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ValueError(f"{name} cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def source_module():
    return _module(SOURCE, SOURCE_SHA256, "_desc18_fresh96_source")


def desc16_module():
    return _module(DESC16, DESC16_SHA256, "_desc18_desc16_source")


def contract() -> dict[str, Any]:
    source = source_module()
    raw = source._stable(HERE / "study-contract.json")
    if CONTRACT_SHA256 and digest(raw) != CONTRACT_SHA256:
        raise ValueError("study contract bytes drifted")
    value = source._strict_raw(raw, "study contract")
    expected = {
        "authority": {"confirmation": "unopened", "dspy_optuna_runtime": "forbidden", "process_launches": 0, "provider_calls_made": 0, "reserve": "unopened", "selection": "none", "sol": "veto_only_after_grok_qualification"},
        "format_version": 1,
        "geometry": {"candidates": 2, "grok_cells": 64, "open_validation_groups": 16, "open_validation_items": 32, "sol_cells": 0},
        "kind": "provider_free_desc18_open_fresh96_validation_replication_schedule",
        "lineage": {"child_candidate_id": CHILD_ID, "parent_candidate_id": PARENT_ID, "source_study_id": source.STUDY_ID},
        "prohibitions": ["no provider calls or process launches", "no confirmation or reserve access", "no selection or promotion", "no runtime DSPy or Optuna dependency"],
        "study_id": STUDY_ID,
    }
    if value != expected:
        raise ValueError("study contract drifted")
    return value


def _source_schedule() -> tuple[Any, dict[str, Any]]:
    source = source_module()
    schedule = source.build()
    source.validate_schedule(schedule)
    if schedule.get("schedule_sha256") != SOURCE_SCHEDULE_SHA256:
        raise ValueError("Fresh96 validation schedule commitment drifted")
    if schedule.get("geometry") != {"groups": 16, "items": 32, "candidates": 2, "endpoint_neutral_logical_cells": 64}:
        raise ValueError("Fresh96 validation geometry drifted")
    return source, schedule


def _candidates(source: Any, source_schedule: Mapping[str, Any]) -> list[dict[str, Any]]:
    instruction, profile_raw, identity = source._descendant()
    source_parent = next((row for row in source_schedule.get("candidates", []) if row.get("candidate_id") == PARENT_ID), None)
    if not isinstance(source_parent, Mapping) or identity.get("candidate_sha256") != PARENT_CANDIDATE_SHA256 or source_parent.get("candidate_sha256") != PARENT_CANDIDATE_SHA256:
        raise ValueError("descendant13 parent binding drifted")
    parent = {
        "candidate_id": PARENT_ID,
        "candidate_sha256": PARENT_CANDIDATE_SHA256,
        "instruction_base64": base64.b64encode(instruction).decode("ascii"),
        "instruction_sha256": identity["instruction_sha256"],
        "kind": "retained_parent",
        "profile_base64": base64.b64encode(profile_raw).decode("ascii"),
        "profile_sha256": identity["profile_sha256"],
    }
    desc16 = desc16_module()
    desc15 = desc16.predecessor()
    child_spec = next((row for row in desc15.CHILDREN if row[0] == CHILD_ID), None)
    if child_spec is None:
        raise ValueError("retained child20 specification drifted")
    child = desc15.candidate(*child_spec, instruction, json.loads(profile_raw))
    if child.get("candidate_sha256") != CHILD_CANDIDATE_SHA256 or child.get("profile_sha256") != CHILD_PROFILE_SHA256:
        raise ValueError("retained child20 binding drifted")
    child = {key: child[key] for key in ("addendum", "candidate_id", "candidate_sha256", "factor", "instruction_base64", "instruction_sha256", "kind", "parent_candidate_id", "parent_candidate_sha256", "profile_base64", "profile_sha256")}
    return [parent, child]


def materialize() -> dict[str, Any]:
    contract()
    source, source_schedule = _source_schedule()
    candidates = _candidates(source, source_schedule)
    parent, child = candidates
    source_cells = [row for row in source_schedule["cells"] if row.get("candidate_id") == PARENT_ID]
    if len(source_cells) != 32 or len({row.get("item_id") for row in source_cells}) != 32:
        raise ValueError("Fresh96 descendant13 cell inventory drifted")
    cells: list[dict[str, Any]] = []
    for source_cell in source_cells:
        parent_payload = base64.b64decode(source_cell["payload_base64"], validate=True)
        if digest(parent_payload) != source_cell.get("payload_sha256"):
            raise ValueError("Fresh96 parent payload commitment drifted")
        for candidate in (parent, child):
            if candidate["candidate_id"] == PARENT_ID:
                payload = parent_payload
            else:
                value = source._strict_raw(parent_payload, "Fresh96 parent payload")
                value["instruction"] = base64.b64decode(candidate["instruction_base64"], validate=True).decode("utf-8")
                value["profile"] = json.loads(base64.b64decode(candidate["profile_base64"], validate=True))
                payload = canonical(value)
            payload_sha256 = digest(payload)
            cells.append({
                "candidate_id": candidate["candidate_id"],
                "candidate_sha256": candidate["candidate_sha256"],
                "candidate_instruction_sha256": candidate["instruction_sha256"],
                "candidate_profile_sha256": candidate["profile_sha256"],
                "cell_id": "desc18-grok-" + digest({"candidate": candidate["candidate_id"], "item": source_cell["item_id"]})[:16],
                "endpoint_payload_sha256s": {"grok_primary": payload_sha256, "sol_veto_if_qualified": payload_sha256},
                "item_id": source_cell["item_id"],
                "ordinal": len(cells) + 1,
                "partition": "open_validation_development",
                "payload_base64": base64.b64encode(payload).decode("ascii"),
                "payload_sha256": payload_sha256,
                "prompt_group_id": source_cell["prompt_group_id"],
                "route_name": "grok_primary",
                "source_binding_sha256": source_cell["source_binding_sha256"],
                "target": deepcopy(source_cell["target"]),
                "target_sha256": source_cell["target_sha256"],
            })
    value = {
        "authority": {"confirmation": "unopened", "dspy_optuna_runtime": "forbidden", "process_launches": 0, "provider_calls_made": 0, "reserve": "unopened", "selection": "none", "sol": "veto_only_after_grok_qualification"},
        "candidates": candidates,
        "cells": cells,
        "format_version": 1,
        "geometry": {"candidates": 2, "grok_cells": 64, "open_validation_groups": 16, "open_validation_items": 32, "sol_cells": 0},
        "kind": "provider_free_desc18_open_fresh96_validation_replication_schedule",
        "lineage": {"child_candidate_id": CHILD_ID, "child_candidate_sha256": CHILD_CANDIDATE_SHA256, "parent_candidate_id": PARENT_ID, "parent_candidate_sha256": PARENT_CANDIDATE_SHA256, "source_schedule_sha256": SOURCE_SCHEDULE_SHA256, "source_study_id": source.STUDY_ID},
        "source": {"fresh96_validation_freeze_study_sha256": SOURCE_SHA256, "public_open_validation_only": True, "private_freeze_read": False},
        "study_id": STUDY_ID,
    }
    value["schedule_sha256"] = digest(value)
    validate(value, source_schedule)
    return value


def validate(value: Mapping[str, Any], source_schedule: Mapping[str, Any] | None = None) -> None:
    source, rebuilt_source = _source_schedule()
    if source_schedule is None:
        source_schedule = rebuilt_source
    elif source_schedule != rebuilt_source:
        raise ValueError("Fresh96 source schedule changed during validation")
    expected_geometry = {"candidates": 2, "grok_cells": 64, "open_validation_groups": 16, "open_validation_items": 32, "sol_cells": 0}
    if value.get("study_id") != STUDY_ID or value.get("geometry") != expected_geometry or value.get("schedule_sha256") != digest({key: item for key, item in value.items() if key != "schedule_sha256"}):
        raise ValueError("schedule identity or geometry drifted")
    cells = value.get("cells")
    if not isinstance(cells, list) or len(cells) != 64 or len({row.get("cell_id") for row in cells if isinstance(row, Mapping)}) != 64:
        raise ValueError("schedule cell identity drifted")
    expected_pairs = {(candidate_id, row["item_id"]) for candidate_id in (PARENT_ID, CHILD_ID) for row in source_schedule["cells"] if row.get("candidate_id") == PARENT_ID}
    observed_pairs = {(row.get("candidate_id"), row.get("item_id")) for row in cells}
    if observed_pairs != expected_pairs or {row.get("route_name") for row in cells} != {"grok_primary"} or {row.get("partition") for row in cells} != {"open_validation_development"}:
        raise ValueError("open validation pairing drifted")
    source_parent = {row["item_id"]: row for row in source_schedule["cells"] if row.get("candidate_id") == PARENT_ID}
    candidates = {row.get("candidate_id"): row for row in value.get("candidates", [])}
    if set(candidates) != {PARENT_ID, CHILD_ID} or candidates != {row["candidate_id"]: row for row in _candidates(source, source_schedule)}:
        raise ValueError("candidate bindings drifted")
    for row in cells:
        source_row = source_parent.get(row["item_id"])
        if source_row is None or row.get("prompt_group_id") != source_row["prompt_group_id"] or row.get("source_binding_sha256") != source_row["source_binding_sha256"] or row.get("target") != source_row["target"] or row.get("target_sha256") != source_row["target_sha256"]:
            raise ValueError("open validation source binding drifted")
        payload = base64.b64decode(row.get("payload_base64", ""), validate=True)
        if digest(payload) != row.get("payload_sha256") or row.get("endpoint_payload_sha256s") != {"grok_primary": row["payload_sha256"], "sol_veto_if_qualified": row["payload_sha256"]}:
            raise ValueError("endpoint payload binding drifted")
        decoded = source._strict_raw(payload, "desc18 payload")
        if decoded.get("study_id") != source.STUDY_ID or set(decoded) != {"format_version", "instruction", "profile", "response_schema", "study_id", "writing"}:
            raise ValueError("provider-ready payload shape drifted")
        rendered = payload.decode("utf-8").lower()
        if any(marker in rendered for marker in ("future_confirmation", "private-freeze", "c:/users/", "\\\\users\\\\")):
            raise ValueError("private partition leakage")
        if row["candidate_id"] == PARENT_ID and payload != base64.b64decode(source_row["payload_base64"], validate=True):
            raise ValueError("descendant13 parent payload bytes changed")


def _exclusive_write(path: Path, raw: bytes) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    with os.fdopen(os.open(path, flags, 0o600), "wb") as handle:
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())
    if path.read_bytes() != raw:
        raise ValueError("frozen artifact write drifted")


def freeze(output_root: Path) -> dict[str, Any]:
    source = source_module()
    root = Path(output_root)
    if root.exists():
        raise ValueError("freeze output root must be fresh")
    source._safe_ancestry(root.parent)
    schedule = materialize()
    if schedule != materialize():
        raise ValueError("source changed between materialization phases")
    root.mkdir()
    source._plain(root, directory=True)
    _exclusive_write(root / "schedule.json", canonical(schedule))
    _exclusive_write(root / "manifest.json", canonical({"candidate_sha256s": [row["candidate_sha256"] for row in schedule["candidates"]], "schedule_sha256": schedule["schedule_sha256"], "study_id": STUDY_ID}))
    validate_frozen_root(root)
    return schedule


def validate_frozen_root(root: Path) -> dict[str, Any]:
    source = source_module()
    root = source._safe_ancestry(Path(root))
    source._plain(root, directory=True)
    if {entry.name for entry in root.iterdir()} != {"manifest.json", "schedule.json"}:
        raise ValueError("freeze inventory drifted")
    schedule = source.strict(root / "schedule.json", "persisted desc18 schedule")
    if schedule != materialize():
        raise ValueError("persisted schedule differs from pinned construction")
    manifest = source.strict(root / "manifest.json", "desc18 manifest")
    if manifest != {"candidate_sha256s": [row["candidate_sha256"] for row in schedule["candidates"]], "schedule_sha256": schedule["schedule_sha256"], "study_id": STUDY_ID}:
        raise ValueError("manifest commitment drifted")
    return schedule


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path)
    args = parser.parse_args()
    value = freeze(args.output_root) if args.output_root else materialize()
    print(canonical(value).decode("utf-8"), end="")
