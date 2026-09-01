"""Provider-free desc15 referent candidates and development schedule freeze."""
from __future__ import annotations

import base64
import hashlib
import json
import os
import stat
from collections.abc import Mapping
from copy import deepcopy
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
STUDY_ID = "hbq-human-alignment-optimizer-v6-desc15-referent-candidates-v1"
PARENT = HERE.parent / "hbq-human-alignment-optimizer-v5-f20-recommended-development-profile-v1" / "profile.json"
PARENT_SHA256 = "0b9b7b7417c37534689ef3c159e7de1d7cc7a6eb0fb593e4f671a5e2686e9f28"
PARENT_ID = "broader-nextwave-13-missing_evidence_not_no"
PARENT_CANDIDATE_SHA256 = "d8e55620d3a91ac17762d9ac40f7be3bb8aa87a478d6593f6ebda906d28b4684"
PUBLIC_EVIDENCE_COMMIT = "c40a9a5150053e4edebb0c68c4fdfb029fbe3c60"
CHILDREN = (
    ("broader-nextwave-19-construct_framing-referent-boundary", "construct_framing", "Step-05 referent boundary: resolve a referent only when the supplied local passage has one clear antecedent; if multiple remain plausible, retain the ambiguity without choosing one."),
    ("broader-nextwave-20-missing_evidence_not_no-referent-evidence", "missing_evidence_not_no", "Step-05 referent evidence: an absent or ambiguous antecedent is neutral; lower Coherence only for a locally explicit contradiction."),
    ("broader-nextwave-21-scope_materiality-referent-materiality", "scope_materiality", "Step-05 referent materiality: keep ambiguity a localized Coherence note unless it blocks the passage's meaning."),
)
DEVELOPMENT_ITEMS = (
    ("item-028fc3ac6963b50f", "prompt-132112dd8eeb2d4d"), ("item-25d5a1163ca56b27", "prompt-132112dd8eeb2d4d"),
    ("item-2ba42c130da729fa", "prompt-3f844c5cdc6b51ae"), ("item-8776b34674d81280", "prompt-3f844c5cdc6b51ae"),
    ("item-d5fe1ae06099a06e", "prompt-6450c4baa52d6998"), ("item-f6e3af87c879383c", "prompt-6450c4baa52d6998"),
    ("item-1568277c2dde9944", "prompt-6a99e79cf010b289"), ("item-242fe0ddf52e6278", "prompt-6a99e79cf010b289"),
    ("item-2377fcf24510aac5", "prompt-7c393c4bcb3a7484"), ("item-85b393b19a363e89", "prompt-7c393c4bcb3a7484"),
    ("item-0cb9c7afe8527434", "prompt-8997770ce6efe4d5"), ("item-1b27b9076eef2bc5", "prompt-8d3d397a4f6ba0ea"), ("item-9a254f1a6661a875", "prompt-8d3d397a4f6ba0ea"),
)
REQUIRED_PAYLOAD_KEYS = frozenset({"format_version", "instruction", "profile", "prompt", "response_schema", "study_id", "task", "writing"})
FORBIDDEN_PAYLOAD_KEYS = frozenset({"confirmation", "human_scores", "partition", "reference_score", "reserve", "reserve_target", "target", "target_score", "targets"})
SOURCE_STUDY_ID = "hbq-human-alignment-optimizer-v5-f20-broader-development-freeze-v1"
SOURCE_TASK = "score the supplied writing against the supplied prompt using the exact six-dimension schema"
RESPONSE_SCHEMA = {"additionalProperties": False, "format_version": 1, "properties": {"coverage": {"additionalProperties": False, "properties": {name: {"type": "boolean"} for name in ("Coherence", "Complexity", "Empathy", "Engagement", "Relevance", "Surprise")}, "required": ["Relevance", "Coherence", "Empathy", "Surprise", "Engagement", "Complexity"], "type": "object"}, "evidence": {"additionalProperties": False, "properties": {name: {"minLength": 1, "type": "string"} for name in ("Coherence", "Complexity", "Empathy", "Engagement", "Relevance", "Surprise")}, "required": ["Relevance", "Coherence", "Empathy", "Surprise", "Engagement", "Complexity"], "type": "object"}, "scores": {"additionalProperties": False, "properties": {name: {"maximum": 5, "minimum": 0, "type": "number"} for name in ("Coherence", "Complexity", "Empathy", "Engagement", "Relevance", "Surprise")}, "required": ["Relevance", "Coherence", "Empathy", "Surprise", "Engagement", "Complexity"], "type": "object"}}, "required": ["scores", "evidence", "coverage"], "type": "object"}
RESPONSE_SCHEMA_SHA256 = "38fb4d0c4c2f491542ea328c15cb5253da954321121229cd54a5936559a4c096"


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()


def digest(value: bytes | Any) -> str:
    return hashlib.sha256(value if isinstance(value, bytes) else canonical(value)).hexdigest()


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result: raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _ancestry(path: Path, *, directory: bool) -> tuple[tuple[str, int, int, int, int | None], ...]:
    result = []
    for index, current in enumerate((Path(os.path.abspath(path)), *Path(os.path.abspath(path)).parents)):
        info = os.lstat(current)
        if stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)):
            raise ValueError("unsafe reparse artifact ancestry")
        expected = directory if index == 0 else True
        if stat.S_ISDIR(info.st_mode) != expected: raise ValueError("unexpected artifact ancestry type")
        result.append((str(current), info.st_dev, info.st_ino, stat.S_IFMT(info.st_mode), None if expected else info.st_size))
    return tuple(result)


def stable(path: Path) -> tuple[bytes, tuple[tuple[str, int, int, int, int | None], ...]]:
    before = _ancestry(path, directory=False)
    with Path(path).open("rb") as handle:
        opened = os.fstat(handle.fileno()); raw = handle.read(); after_open = os.fstat(handle.fileno())
    after = _ancestry(path, directory=False); identity = (opened.st_dev, opened.st_ino, stat.S_IFMT(opened.st_mode), opened.st_size)
    if before != after or before[0][1:] != identity or identity != (after_open.st_dev, after_open.st_ino, stat.S_IFMT(after_open.st_mode), after_open.st_size):
        raise ValueError("stable full-ancestry read drift")
    return raw, before


def strict(raw: bytes, label: str) -> dict[str, Any]:
    try: value = json.loads(raw.decode(), object_pairs_hook=_pairs, parse_constant=lambda token: (_ for _ in ()).throw(ValueError(token)))
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error: raise ValueError(f"invalid {label}") from error
    if type(value) is not dict or canonical(value) != raw: raise ValueError(f"noncanonical {label}")
    return value


def contract() -> dict[str, Any]:
    raw, _identity = stable(HERE / "study-contract.json")
    value = strict(raw, "study contract")
    expected = {"authority": {"confirmation": "unopened", "dspy_optuna_runtime": "forbidden", "process_launches": 0, "provider_calls_made": 0, "selection": "none", "sol": "out_of_scope"}, "children": [{"addendum": addendum, "candidate_id": candidate_id, "factor": factor} for candidate_id, factor, addendum in CHILDREN], "development_items": [{"item_id": item_id, "prompt_group_id": group} for item_id, group in DEVELOPMENT_ITEMS], "format_version": 1, "geometry": {"candidates": 4, "development_groups": 7, "development_items": 13, "grok_cells": 52, "sol_cells": 0}, "kind": "provider_free_desc15_development_schedule", "lineage": {"parent_candidate_id": PARENT_ID, "parent_candidate_sha256": PARENT_CANDIDATE_SHA256, "parent_document_sha256": PARENT_SHA256, "public_evidence_commit": PUBLIC_EVIDENCE_COMMIT}, "study_id": STUDY_ID}
    if value != expected: raise ValueError("study contract drifted")
    return value


def parent(path: Path = PARENT) -> tuple[bytes, dict[str, Any], tuple[tuple[str, int, int, int, int | None], ...]]:
    raw, ancestry = stable(path)
    if digest(raw) != PARENT_SHA256: raise ValueError("immutable descendant13 parent drifted")
    value = strict(raw, "descendant13 parent")
    candidate, instruction, profile = value.get("candidate"), value.get("instruction"), value.get("profile")
    if not isinstance(candidate, Mapping) or candidate.get("candidate_id") != PARENT_ID or candidate.get("candidate_sha256") != PARENT_CANDIDATE_SHA256 or not isinstance(instruction, str) or not isinstance(profile, dict):
        raise ValueError("descendant13 parent shape drifted")
    if value.get("instruction_sha256") != digest(instruction.encode()) or value.get("profile_sha256") != digest(json.dumps(profile, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()):
        raise ValueError("descendant13 parent bindings drifted")
    return instruction.encode(), profile, ancestry


def candidate(candidate_id: str, factor: str, addendum: str, instruction: bytes, profile: Mapping[str, Any]) -> dict[str, Any]:
    factors = profile.get("factors")
    if not isinstance(factors, dict) or factor not in factors or not all(isinstance(key, str) and isinstance(value, str) for key, value in factors.items()): raise ValueError("parent factor surface drifted")
    child = deepcopy(dict(profile)); child["factors"][factor] = factors[factor] + "\n" + addendum
    if [key for key in factors if child["factors"][key] != factors[key]] != [factor] or child["factors"][factor].count(addendum) != 1: raise ValueError("candidate must change exactly one factor")
    profile_bytes = json.dumps(child, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    identity = {"study_id": STUDY_ID, "parent_document_sha256": PARENT_SHA256, "parent_candidate_sha256": PARENT_CANDIDATE_SHA256, "candidate_id": candidate_id, "factor": factor, "addendum": addendum, "instruction_sha256": digest(instruction), "profile_sha256": digest(profile_bytes)}
    return {"addendum": addendum, "candidate_id": candidate_id, "candidate_sha256": digest(identity), "factor": factor, "instruction_base64": base64.b64encode(instruction).decode(), "instruction_sha256": digest(instruction), "kind": "one_factor_one_clause_descendant", "parent_candidate_id": PARENT_ID, "parent_candidate_sha256": PARENT_CANDIDATE_SHA256, "parent_document_sha256": PARENT_SHA256, "profile_base64": base64.b64encode(profile_bytes).decode(), "profile_sha256": digest(profile_bytes)}


def candidates(parent_path: Path = PARENT) -> tuple[list[dict[str, Any]], tuple[tuple[str, int, int, int, int | None], ...]]:
    instruction, profile, ancestry = parent(parent_path)
    if len(CHILDREN) != 3 or len({row[0] for row in CHILDREN}) != 3 or len({row[2] for row in CHILDREN}) != 3: raise ValueError("three-child geometry drifted")
    return [candidate(*row, instruction, profile) for row in CHILDREN], ancestry


def _payload(raw: bytes, item_id: str, group: str, row: Mapping[str, Any], child: Mapping[str, Any]) -> bytes:
    value = strict(raw, "development payload")
    if set(value) != REQUIRED_PAYLOAD_KEYS:
        raise ValueError("development payload must have the exact provider-ready field set")
    _reject_private_fields(value)
    if value.get("format_version") != 1 or value.get("study_id") != SOURCE_STUDY_ID or value.get("task") != SOURCE_TASK or not isinstance(value.get("prompt"), str) or not isinstance(value.get("writing"), str) or digest(json.dumps(value.get("response_schema"), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()) != RESPONSE_SCHEMA_SHA256 or value.get("response_schema") != RESPONSE_SCHEMA:
        raise ValueError("development payload source identity or response schema drifted")
    if value.get("instruction") != base64.b64decode(row["instruction_base64"], validate=True).decode() or value.get("profile") != json.loads(base64.b64decode(row["profile_base64"], validate=True)):
        raise ValueError("development payload does not bind the exact parent")
    value["instruction"] = base64.b64decode(child["instruction_base64"], validate=True).decode(); value["profile"] = json.loads(base64.b64decode(child["profile_base64"], validate=True)); value["item_id"] = item_id; value["prompt_group_id"] = group
    rendered = canonical(value).decode().lower()
    if any(marker in rendered for marker in ("fresh96", "private-freeze", "future_confirmation", "c:/users/", "\\\\users\\\\")):
        raise ValueError("development payload contains forbidden partition leakage")
    return canonical(value)


def _reject_private_fields(value: Any) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str) or key.lower() in FORBIDDEN_PAYLOAD_KEYS:
                raise ValueError("development payload contains forbidden partition leakage")
            _reject_private_fields(item)
    elif isinstance(value, list):
        for item in value: _reject_private_fields(item)


def materialize(development_payloads: Mapping[str, bytes], *, parent_path: Path = PARENT) -> dict[str, Any]:
    contract()
    children, ancestry = candidates(parent_path); instruction, profile, repeat = parent(parent_path)
    if ancestry != repeat: raise ValueError("parent changed between materialization phases")
    profile_bytes = json.dumps(profile, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    parent_row = {"candidate_id": PARENT_ID, "candidate_sha256": PARENT_CANDIDATE_SHA256, "instruction_base64": base64.b64encode(instruction).decode(), "instruction_sha256": digest(instruction), "kind": "admitted_parent", "parent_document_sha256": PARENT_SHA256, "profile_base64": base64.b64encode(profile_bytes).decode(), "profile_sha256": digest(profile_bytes)}
    if set(development_payloads) != {item for item, _group in DEVELOPMENT_ITEMS}: raise ValueError("development payload inventory must be exactly the 13 frozen items")
    rows = [parent_row, *children]; cells = []
    for ordinal, (item_id, group) in enumerate(DEVELOPMENT_ITEMS, 1):
        raw = development_payloads[item_id]
        for candidate_row in rows:
            payload = _payload(raw, item_id, group, parent_row, candidate_row)
            cells.append({"candidate_id": candidate_row["candidate_id"], "candidate_sha256": candidate_row["candidate_sha256"], "candidate_instruction_sha256": candidate_row["instruction_sha256"], "candidate_profile_sha256": candidate_row["profile_sha256"], "cell_id": "desc15-grok-" + digest({"candidate": candidate_row["candidate_id"], "item": item_id})[:16], "item_id": item_id, "ordinal": len(cells) + 1, "partition": "development", "payload_base64": base64.b64encode(payload).decode(), "payload_sha256": digest(payload), "prompt_group_id": group, "route_name": "grok_primary"})
    value = {"authority": {"confirmation": "unopened", "dspy_optuna_runtime": "forbidden", "process_launches": 0, "provider_calls_made": 0, "selection": "none", "sol": "out_of_scope"}, "candidates": rows, "format_version": 1, "geometry": {"candidates": 4, "development_groups": 7, "development_items": 13, "grok_cells": 52, "sol_cells": 0}, "kind": "provider_free_desc15_development_schedule", "lineage": {"parent_candidate_id": PARENT_ID, "parent_candidate_sha256": PARENT_CANDIDATE_SHA256, "parent_document_sha256": PARENT_SHA256, "public_evidence_commit": PUBLIC_EVIDENCE_COMMIT, "luna_ideas": "provisional design lineage only; no model output is selection authority"}, "cells": cells, "study_id": STUDY_ID}
    value["schedule_sha256"] = digest(value); validate(value); return value


def validate(value: Mapping[str, Any]) -> None:
    if value.get("study_id") != STUDY_ID or value.get("geometry") != {"candidates": 4, "development_groups": 7, "development_items": 13, "grok_cells": 52, "sol_cells": 0}: raise ValueError("schedule geometry drifted")
    cells = value.get("cells")
    if not isinstance(cells, list) or len(cells) != 52: raise ValueError("schedule cell count drifted")
    expected = {(candidate_id, item_id) for candidate_id in (PARENT_ID, *(row[0] for row in CHILDREN)) for item_id, _group in DEVELOPMENT_ITEMS}
    observed = {(row.get("candidate_id"), row.get("item_id")) for row in cells}
    if observed != expected or len(observed) != 52: raise ValueError("schedule pairing drifted")
    if {row.get("prompt_group_id") for row in cells} != {group for _item, group in DEVELOPMENT_ITEMS}: raise ValueError("development group drifted")
    if value.get("schedule_sha256") != digest({key: item for key, item in value.items() if key != "schedule_sha256"}): raise ValueError("schedule commitment drifted")
    for row in cells:
        payload = base64.b64decode(row["payload_base64"], validate=True)
        if digest(payload) != row["payload_sha256"]: raise ValueError("payload commitment drifted")
    if any("fresh96" in base64.b64decode(row["payload_base64"], validate=True).decode().lower() for row in cells): raise ValueError("forbidden partition leakage")


def freeze(output_root: Path, development_payloads: Mapping[str, bytes], *, parent_path: Path = PARENT) -> dict[str, Any]:
    root = Path(output_root)
    if root.exists(): raise ValueError("freeze output root must be fresh")
    _ancestry(root.parent, directory=True); schedule = materialize(development_payloads, parent_path=parent_path); repeat = materialize(development_payloads, parent_path=parent_path)
    if schedule != repeat: raise ValueError("inputs changed between materialization phases")
    root.mkdir(); root_ancestry = _ancestry(root, directory=True)
    _safe_write(root / "schedule.json", canonical(schedule), expected_root_ancestry=root_ancestry)
    _safe_write(root / "manifest.json", canonical({"study_id": STUDY_ID, "schedule_sha256": schedule["schedule_sha256"], "candidate_sha256s": [row["candidate_sha256"] for row in schedule["candidates"]]}), expected_root_ancestry=root_ancestry)
    validate_frozen_root(root, development_payloads, parent_path=parent_path, expected_root_ancestry=root_ancestry); return schedule


def validate_frozen_root(root: Path, development_payloads: Mapping[str, bytes], *, parent_path: Path = PARENT, expected_root_ancestry: tuple[tuple[str, int, int, int, int | None], ...] | None = None) -> dict[str, Any]:
    root = Path(root); root_ancestry = _ancestry(root, directory=True)
    if expected_root_ancestry is not None and root_ancestry != expected_root_ancestry: raise ValueError("freeze root changed before final validation")
    if {path.name for path in root.iterdir()} != {"manifest.json", "schedule.json"}: raise ValueError("freeze inventory drifted")
    schedule = strict(stable(root / "schedule.json")[0], "schedule"); rebuilt = materialize(development_payloads, parent_path=parent_path)
    if schedule != rebuilt: raise ValueError("persisted schedule or input drifted")
    manifest = strict(stable(root / "manifest.json")[0], "manifest")
    if manifest != {"study_id": STUDY_ID, "schedule_sha256": schedule["schedule_sha256"], "candidate_sha256s": [row["candidate_sha256"] for row in schedule["candidates"]]}: raise ValueError("manifest commitment drifted")
    if _ancestry(root, directory=True) != root_ancestry: raise ValueError("freeze root changed during final validation")
    return schedule


def _safe_write(path: Path, raw: bytes, *, expected_root_ancestry: tuple[tuple[str, int, int, int, int | None], ...] | None = None) -> None:
    target = Path(path); parent_ancestry = _ancestry(target.parent, directory=True)
    if expected_root_ancestry is not None and parent_ancestry != expected_root_ancestry: raise ValueError("freeze root changed before exclusive write")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"): flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(target, flags, 0o600)
    except OSError as error:
        raise ValueError("freeze artifact must be a fresh plain file") from error
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(raw); handle.flush(); os.fsync(handle.fileno())
    if stable(target)[0] != raw or _ancestry(target.parent, directory=True) != parent_ancestry: raise ValueError("freeze artifact or root changed during exclusive write")
