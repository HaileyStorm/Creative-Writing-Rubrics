"""Build the public Fresh96 validation payload schedule without provider contact."""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import math
import os
import stat
from collections.abc import Mapping
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
STUDY_ID = "hbq-human-alignment-hanna96-validation-freeze-v1"
MANIFEST = REPO / "evaluation-results" / "hbq-human-alignment-hanna96-fresh-split-v1" / "manifest.json"
MANIFEST_SHA256 = "ca5adea2288d9c01ddf3aeb0c6239ac2c550d26095a2c66a928d90511f4afb16"
PROFILE = REPO / "evaluation-results" / "hbq-human-alignment-optimizer-v5-f20-recommended-development-profile-v1" / "profile.json"
PROFILE_SHA256 = "0b9b7b7417c37534689ef3c159e7de1d7cc7a6eb0fb593e4f671a5e2686e9f28"
BASELINE = "candidate-102cc7f06c9a99a7"
DESCENDANT = "broader-nextwave-13-missing_evidence_not_no"
DIMENSIONS = ("Relevance", "Coherence", "Empathy", "Surprise", "Engagement", "Complexity")


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def compact(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def sha256(value: bytes | Any) -> str:
    return hashlib.sha256(value if isinstance(value, bytes) else canonical(value)).hexdigest()


def _plain(path: Path, directory: bool) -> None:
    info = os.lstat(path)
    if stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)):
        raise ValueError("reparsed filesystem artifact")
    if stat.S_ISDIR(info.st_mode) != directory:
        raise ValueError("unexpected filesystem artifact type")


def _safe_ancestry(path: Path) -> Path:
    absolute = Path(os.path.abspath(path))
    current = Path(absolute.anchor)
    if current.exists():
        _plain(current, directory=True)
    for part in absolute.parts[1:]:
        current /= part
        if current.exists():
            _plain(current, directory=current != absolute or current.is_dir())
    return absolute


def _stable(path: Path) -> bytes:
    path = _safe_ancestry(Path(path))
    _plain(path, directory=False)
    before = os.lstat(path)
    with path.open("rb") as handle:
        opened = os.fstat(handle.fileno())
        raw = handle.read()
        after = os.fstat(handle.fileno())
    identity = lambda value: (value.st_dev, value.st_ino, value.st_size)
    if identity(before) != identity(opened) or identity(opened) != identity(after):
        raise ValueError("stable read drift")
    return raw


def _strict_raw(raw: bytes, label: str) -> dict[str, Any]:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in items:
            if key in value:
                raise ValueError("duplicate JSON key")
            value[key] = item
        return value
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs, parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise ValueError(f"invalid {label}") from error
    if not isinstance(value, dict) or canonical(value) != raw:
        raise ValueError(f"noncanonical {label}")
    return value


def strict(path: Path, label: str) -> dict[str, Any]:
    return _strict_raw(_stable(Path(path)), label)


def _baseline() -> tuple[bytes, bytes, dict[str, Any]]:
    factors = {"construct_framing": "human_reference_descriptive", "scope_materiality": "localized_revision_note", "missing_evidence_not_no": "implicit", "human_reference_variant": "dimension_first_overall_last"}
    instruction = (
        b"Assess the supplied writing using the fixed six HANNA dimensions.\n"
        b"Construct framing: human_reference_descriptive.\n"
        b"Scope/materiality: localized_revision_note.\n"
        b"Missing evidence policy: implicit.\n"
        b"Human-reference presentation: dimension_first_overall_last.\n"
        b"Use the immutable CWR mapping and response schema committed in the profile.\n"
        b"Return no demonstrations, examples, or unstated scoring dimensions.\n"
    )
    profile = {"format_version": 1, "study_id": "hbq-human-alignment-optimizer-v1", "factors": factors, "instruction_sha256": sha256(instruction), "fixed_mapping": "Fresh88 v3 mapping_sets_sha256", "dimension_weights": {dimension: 1 for dimension in DIMENSIONS}, "demonstrations": 0, "sampler": {"algorithm": "deterministic_candidate_profile_v1", "seed": 628811, "temperature": 0}, "same_bytes_for_models": ["gpt-5.6-sol", "grok-4.6"], "immutable_cwr_commitments": {"execution_contract_sha256": "6b3bfcd2407442c9997631cd38d7df7e01bd5017782feb62ad360840399b1726", "runtime_source_manifest_sha256": "381e3c8a767da6003a22d8b47695dac722f946fd1d63f771c6ddde655eef2c06", "mapping_sets_sha256": "33de035935dc1304cf782d596038354f65efb00b019babe0cf61aa9474d142c5", "baseline_control_profile_sha256": "e3a83b5eeeafea14e3056fbd961a0c8935608bc2df2d0300f8dc1bf65291a957", "response_schema": {"format_version": 1, "dimensions": list(DIMENSIONS), "score_type": "finite_numeric_per_dimension"}}}
    profile_raw = compact(profile)
    if sha256(instruction) != "f318da394124d72dea4e9fb896d0345c6c5136d4839feae2cff1e389ea642de1" or sha256(profile_raw) != "3d90b5bdd1b1cd1673cc45b834485754eb0ee01f89e2c3c7ddf5d31e7d24c74f":
        raise ValueError("baseline committed constructor drifted")
    return instruction, profile_raw, {"candidate_id": BASELINE, "instruction_sha256": sha256(instruction), "profile_sha256": sha256(profile_raw), "candidate_sha256": sha256({"candidate_id": BASELINE, "instruction_sha256": sha256(instruction), "profile_sha256": sha256(profile_raw)})}


def _descendant() -> tuple[bytes, bytes, dict[str, Any]]:
    raw = _stable(PROFILE)
    if sha256(raw) != PROFILE_SHA256:
        raise ValueError("committed descendant profile drifted")
    value = _strict_raw(raw, "recommended descendant profile")
    instruction = value.get("instruction")
    profile = value.get("profile")
    candidate = value.get("candidate")
    if not isinstance(instruction, str) or not isinstance(profile, Mapping) or not isinstance(candidate, Mapping) or candidate.get("candidate_id") != DESCENDANT:
        raise ValueError("recommended descendant geometry drifted")
    instruction_raw, profile_raw = instruction.encode("utf-8"), compact(profile)
    if sha256(instruction_raw) != value.get("instruction_sha256") or sha256(profile_raw) != value.get("profile_sha256"):
        raise ValueError("recommended descendant byte binding drifted")
    return instruction_raw, profile_raw, {"candidate_id": DESCENDANT, "instruction_sha256": sha256(instruction_raw), "profile_sha256": sha256(profile_raw), "candidate_sha256": candidate.get("candidate_sha256")}


def _schema() -> dict[str, Any]:
    return {"format_version": 1, "type": "object", "additionalProperties": False, "required": ["scores", "evidence", "coverage"], "properties": {name: {"type": "object", "additionalProperties": False, "required": list(DIMENSIONS), "properties": {dimension: {"type": kind, **({"minimum": 0, "maximum": 5} if name == "scores" else {"minLength": 1} if name == "evidence" else {})} for dimension in DIMENSIONS}} for name, kind in (("scores", "number"), ("evidence", "string"), ("coverage", "boolean"))}}


def build() -> dict[str, Any]:
    manifest_raw = _stable(MANIFEST)
    if sha256(manifest_raw) != MANIFEST_SHA256:
        raise ValueError("Fresh96 public manifest drifted")
    manifest = _strict_raw(manifest_raw, "Fresh96 public manifest")
    selected = manifest.get("selected_items")
    if not isinstance(selected, list) or len(selected) != 32:
        raise ValueError("Fresh96 validation item geometry drifted")
    baseline = _baseline()
    descendant = _descendant()
    candidates = [baseline, descendant]
    cells: list[dict[str, Any]] = []
    for item in sorted(selected, key=lambda row: (row.get("prompt_group_id", ""), row.get("item_id", ""))):
        if not isinstance(item, Mapping) or item.get("partition") != "validation" or item.get("status") != "open":
            raise ValueError("non-validation source item leaked")
        target = item.get("target")
        if not isinstance(target, Mapping) or set(target) != set(DIMENSIONS) or any(type(target[d]) not in (int, float) or not math.isfinite(target[d]) for d in DIMENSIONS):
            raise ValueError("invalid Fresh96 target")
        for instruction, profile_raw, candidate in candidates:
            identity = {"study_id": STUDY_ID, "candidate_id": candidate["candidate_id"], "prompt_group_id": item["prompt_group_id"], "item_id": item["item_id"]}
            payload = canonical({"format_version": 1, "study_id": STUDY_ID, "instruction": instruction.decode("utf-8"), "profile": json.loads(profile_raw), "writing": {"prompt": item["prompt"], "story": item["story"]}, "response_schema": _schema()})
            cells.append({"cell_id": "h96-" + sha256(identity)[:20], "candidate_id": candidate["candidate_id"], "candidate_sha256": candidate["candidate_sha256"], "candidate_instruction_sha256": candidate["instruction_sha256"], "candidate_profile_sha256": candidate["profile_sha256"], "prompt_group_id": item["prompt_group_id"], "item_id": item["item_id"], "source_binding_sha256": item["source_binding_sha256"], "target": {dimension: float(target[dimension]) for dimension in DIMENSIONS}, "target_sha256": sha256({dimension: float(target[dimension]) for dimension in DIMENSIONS}), "payload_base64": base64.b64encode(payload).decode("ascii"), "payload_sha256": sha256(payload), "response_schema_sha256": sha256(_schema())})
    value = {"format_version": 1, "study_id": STUDY_ID, "kind": "endpoint_neutral_fresh96_validation_schedule", "source": {"fresh96_manifest_sha256": MANIFEST_SHA256, "public_open_validation_only": True, "private_freeze_read": False}, "candidates": [{key: candidate[key] for key in ("candidate_id", "candidate_sha256", "instruction_sha256", "profile_sha256")} for _instruction, _profile, candidate in candidates], "geometry": {"groups": 16, "items": 32, "candidates": 2, "endpoint_neutral_logical_cells": 64}, "cells": cells, "authority": {"provider_calls_made": 0, "process_launches": 0, "endpoint_pooling": "forbidden", "selection": "none", "promotion": "none", "runtime": "none", "generalization": "none"}}
    value["schedule_sha256"] = sha256(value)
    validate_schedule(value)
    return value


def validate_schedule(value: Mapping[str, Any]) -> None:
    body = dict(value); declared = body.pop("schedule_sha256", None)
    if declared != sha256(body) or value.get("study_id") != STUDY_ID or value.get("geometry") != {"groups": 16, "items": 32, "candidates": 2, "endpoint_neutral_logical_cells": 64}:
        raise ValueError("schedule identity or geometry drifted")
    cells = value.get("cells")
    if not isinstance(cells, list) or len(cells) != 64 or len({row.get("cell_id") for row in cells if isinstance(row, Mapping)}) != 64:
        raise ValueError("cell identity geometry drifted")
    if {row.get("candidate_id") for row in cells} != {BASELINE, DESCENDANT} or len({row.get("item_id") for row in cells}) != 32 or len({row.get("prompt_group_id") for row in cells}) != 16:
        raise ValueError("candidate/item/group geometry drifted")
    for cell in cells:
        payload = base64.b64decode(cell.get("payload_base64", ""), validate=True)
        if sha256(payload) != cell.get("payload_sha256") or sha256(cell.get("target")) != cell.get("target_sha256"):
            raise ValueError("cell payload or target binding drifted")


def freeze(output_root: Path) -> dict[str, Any]:
    root = Path(output_root)
    if root.exists():
        raise ValueError("schedule output root must be fresh")
    value = build()
    root.mkdir(parents=True)
    (root / "schedule.json").write_bytes(canonical(value))
    validate_frozen_root(root)
    return value


def validate_frozen_root(root: Path) -> dict[str, Any]:
    """Admit a wrapper input root containing exactly the frozen schedule."""
    root = _safe_ancestry(Path(root))
    _plain(root, directory=True)
    if {entry.name for entry in root.iterdir()} != {"schedule.json"}:
        raise ValueError("frozen root inventory drifted")
    schedule = strict(root / "schedule.json", "persisted Fresh96 schedule")
    validate_schedule(schedule)
    if canonical(schedule) != canonical(build()):
        raise ValueError("persisted Fresh96 schedule differs from the pinned public construction")
    return schedule


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path)
    args = parser.parse_args()
    value = freeze(args.output_root) if args.output_root else build()
    print(canonical(value).decode("utf-8"), end="")
