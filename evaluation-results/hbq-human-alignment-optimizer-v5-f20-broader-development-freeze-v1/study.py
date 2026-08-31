"""Provider-free freeze for the next 35-cell Grok development wave."""
from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
import os
import stat
from copy import deepcopy
from pathlib import Path
from types import ModuleType
from typing import Any, Mapping


HERE = Path(__file__).resolve().parent
STUDY_ID = "hbq-human-alignment-optimizer-v5-f20-broader-development-freeze-v1"
PARENT_FILE = "nextwave-08-conservative-hybrid.json"
PARENT_ARTIFACT_SHA256 = "48055e2ab5d7c2b347aecf0895b46b8e468c2de2af06b25db3215fd3a0af158c"
PARENT_ID = "normalized-nextwave-08-conservative-hybrid"
FROZEN_SUCCESSOR_SHA256 = "b0f6dd24415c388a3104f8c9304ce301193cf0a48631a86c4886bc8ce48468e7"
HANNA_CSV_SHA256 = "ef59054d27fa32def06cfdc57243b1dd09c7e71f40b6d9d43fecfbf60e59026b"
MATERIALIZATION_SHA256 = "9a6db38703b0e34b96e856a956436e4bba76c9770f899943d75ecc436aca1a84"
V3_PATH = HERE.parent / "hbq-human-alignment-optimizer-v3" / "study.py"
V3_SHA256 = "8928b9af075486483f5d117daf34d10ed71b98407b897c8948181b66d1cb99c3"

CHILDREN = (
    ("11", "scope_materiality", "Step-05 calibration: retain the parent calibration for each dimension unless that same dimension has direct, discriminating local evidence; evidence for one dimension cannot move another."),
    ("12", "construct_framing", "Step-05 local-connective guard: require a concrete local relation before changing a relationship-sensitive judgment; global intent, fluency, and prestige are not evidence."),
    ("13", "missing_evidence_not_no", "Step-05 evidence balance: evaluate positive and negative local evidence with the same standard; missing evidence is neutral, never NO or an automatic midpoint."),
    ("14", "human_reference_variant", "Step-05 human-reference guard: treat examples as calibration anchors rather than targets to imitate; use them only to orient evidence interpretation, and retain the parent profile for all unrelated criteria."),
)


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def sha256(value: bytes | Any) -> str:
    return hashlib.sha256(value if isinstance(value, bytes) else canonical(value)).hexdigest()


def strict_json(path: Path, label: str) -> dict[str, Any]:
    raw = Path(path).read_bytes()
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=lambda pairs: _pairs(pairs, label), parse_constant=lambda token: (_ for _ in ()).throw(ValueError(token)))
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise ValueError(f"{label} is not strict JSON") from error
    if not isinstance(value, dict) or canonical(value) != raw:
        raise ValueError(f"{label} must be canonical JSON")
    return value


def _plain(path: Path, directory: bool) -> None:
    info = os.lstat(path)
    if stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)):
        raise ValueError("unsafe reparse artifact")
    if bool(stat.S_ISDIR(info.st_mode)) != directory:
        raise ValueError("unexpected artifact type")


def _pairs(pairs: list[tuple[str, Any]], label: str) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"duplicate key in {label}")
        value[key] = item
    return value


def _v3() -> ModuleType:
    raw = V3_PATH.read_bytes()
    if sha256(raw) != V3_SHA256:
        raise ValueError("pinned v3 source drifted")
    spec = importlib.util.spec_from_file_location("_broader_freeze_v3", V3_PATH)
    if spec is None or spec.loader is None:
        raise ValueError("cannot load pinned v3 source")
    module = importlib.util.module_from_spec(spec)
    exec(compile(raw, str(V3_PATH), "exec"), module.__dict__)
    return module


def _parent(normalized_root: Path) -> tuple[dict[str, Any], bytes, bytes]:
    record_path = Path(normalized_root) / PARENT_FILE
    raw = record_path.read_bytes()
    if sha256(raw) != PARENT_ARTIFACT_SHA256:
        raise ValueError("admitted parent artifact drifted")
    record = strict_json(record_path, "admitted parent artifact")
    normalized = record.get("normalized")
    if (record.get("study_id") != "hbq-human-alignment-optimizer-v5-f20-nextwave-grok-normalize-v1"
            or record.get("kind") != "locally_normalized_provisional_grok_descendant"
            or not isinstance(normalized, Mapping) or set(normalized) != {"instruction", "instruction_sha256", "profile", "profile_sha256"}):
        raise ValueError("admitted parent shape drifted")
    instruction = normalized["instruction"]
    profile = normalized["profile"]
    if not isinstance(instruction, str) or not isinstance(profile, dict):
        raise ValueError("admitted parent bytes are absent")
    instruction_bytes = instruction.encode("utf-8")
    profile_bytes = json_bytes(profile)
    if normalized["instruction_sha256"] != sha256(instruction_bytes) or normalized["profile_sha256"] != sha256(profile_bytes):
        raise ValueError("admitted parent byte bindings drifted")
    return record, instruction_bytes, profile_bytes


def descendants(normalized_root: Path) -> list[dict[str, Any]]:
    record, instruction, profile_raw = _parent(normalized_root)
    parent_profile = json.loads(profile_raw.decode("utf-8"))
    result = [{"candidate_id": PARENT_ID, "candidate_sha256": PARENT_ARTIFACT_SHA256, "instruction_bytes": instruction, "profile_bytes": profile_raw, "instruction_sha256": sha256(instruction), "profile_sha256": sha256(profile_raw), "parent_artifact_sha256": PARENT_ARTIFACT_SHA256, "kind": "admitted_parent"}]
    for ordinal, factor, addendum in CHILDREN:
        profile = deepcopy(parent_profile)
        factors = profile.get("factors")
        if not isinstance(factors, dict) or set(factors) != set(parent_profile["factors"]) or not isinstance(factors.get(factor), str):
            raise ValueError("parent factor surface drifted")
        old = factors[factor]
        factors[factor] = old + "\n" + addendum
        changed = [key for key in factors if factors[key] != parent_profile["factors"][key]]
        if changed != [factor] or factors[factor].count(addendum) != 1:
            raise ValueError("descendant must append exactly one factor addendum")
        profile_bytes = json_bytes(profile)
        identity = {"study_id": STUDY_ID, "parent_artifact_sha256": PARENT_ARTIFACT_SHA256, "ordinal": ordinal, "factor": factor, "instruction_sha256": sha256(instruction), "profile_sha256": sha256(profile_bytes)}
        digest = sha256(identity)
        result.append({"candidate_id": f"broader-nextwave-{ordinal}-{factor}", "candidate_sha256": digest, "instruction_bytes": instruction, "profile_bytes": profile_bytes, "instruction_sha256": sha256(instruction), "profile_sha256": sha256(profile_bytes), "parent_artifact_sha256": PARENT_ARTIFACT_SHA256, "kind": "single_factor_addendum_descendant", "factor": factor, "addendum": addendum, "requested_step_fraction": 0.05, "step_semantics": "planning_prior_not_numeric_or_semantic_distance"})
    if len(result) != 5 or len({row["candidate_id"] for row in result}) != 5:
        raise ValueError("broader candidate geometry drifted")
    return result


def _development_material(*, frozen_successor_path: Path, hanna_csv_path: Path) -> tuple[ModuleType, list[dict[str, str]], Mapping[str, Any]]:
    if sha256(Path(frozen_successor_path).read_bytes()) != FROZEN_SUCCESSOR_SHA256:
        raise ValueError("frozen successor contract drifted")
    if sha256(Path(hanna_csv_path).read_bytes()) != HANNA_CSV_SHA256:
        raise ValueError("HANNA annotations drifted")
    v3 = _v3()
    _study, _harness, _freeze, split, _parents = v3._material(frozen_successor_path=Path(frozen_successor_path), hanna_csv_path=Path(hanna_csv_path))
    grouped: dict[str, list[str]] = {}
    disallowed: set[str] = set()
    for row in split["items"]:
        partition, group, item = row.get("partition"), row.get("prompt_group_id"), row.get("item_id")
        if not isinstance(group, str) or not isinstance(item, str):
            raise ValueError("frozen split item drifted")
        if partition == "development":
            grouped.setdefault(group, []).append(item)
        elif partition in {"train", "confirmation"}:
            disallowed.add(group)
        else:
            raise ValueError("unexpected frozen split partition")
    result = [{"partition": "development", "prompt_group_id": group, "item_id": min(items)} for group, items in sorted(grouped.items())]
    if len(result) != 7 or len({row["prompt_group_id"] for row in result}) != 7 or any(row["prompt_group_id"] in disallowed for row in result):
        raise ValueError("train or confirmation leakage in broader schedule")
    return v3, result, split


def groups(*, frozen_successor_path: Path, hanna_csv_path: Path) -> list[dict[str, str]]:
    _module, result, _split = _development_material(frozen_successor_path=frozen_successor_path, hanna_csv_path=hanna_csv_path)
    return [dict(row) for row in result]


def _payload(*, freeze: ModuleType, item: Mapping[str, Any], candidate: Mapping[str, Any]) -> bytes:
    inherited = freeze._payload_bytes(item=item, candidate=candidate)
    value = json.loads(inherited.decode("utf-8"))
    if value.get("study_id") != "hbq-human-alignment-optimizer-v1":
        raise ValueError("predecessor payload study identity drifted")
    value["study_id"] = STUDY_ID
    projected = canonical(value)
    if {key: item for key, item in value.items() if key != "study_id"} != {key: item for key, item in json.loads(inherited.decode("utf-8")).items() if key != "study_id"}:
        raise ValueError("local payload projection changed more than study identity")
    return projected


def _manifest(row: Mapping[str, Any]) -> dict[str, Any]:
    keys = ("candidate_id", "candidate_sha256", "instruction_sha256", "profile_sha256", "parent_artifact_sha256", "kind")
    value = {key: row[key] for key in keys}
    if row["kind"] != "admitted_parent":
        value |= {key: row[key] for key in ("factor", "addendum", "requested_step_fraction", "step_semantics")}
    value["manifest_sha256"] = sha256(value)
    return value


def contract() -> dict[str, Any]:
    return strict_json(HERE / "study-contract.json", "study contract")


def _validate_contract(schedule: Mapping[str, Any]) -> None:
    copied = dict(schedule)
    declared = copied.pop("schedule_sha256", None)
    if not isinstance(declared, str) or sha256(copied) != declared:
        raise ValueError("frozen schedule commitment drifted")
    value = contract()
    expected = value.get("frozen_commitments")
    actual_children = [row for row in schedule["candidates"] if row["kind"] != "admitted_parent"]
    if (not isinstance(expected, Mapping) or expected.get("child_manifests") != actual_children
            or expected.get("schedule_sha256") != declared):
        raise ValueError("frozen descendant or schedule commitment drifted")


def build(*, normalized_root: Path, materialization_root: Path, frozen_successor_path: Path, hanna_csv_path: Path) -> dict[str, Any]:
    materialization = strict_json(Path(materialization_root) / "materialization.json", "materialization")
    if sha256(canonical(materialization)) != MATERIALIZATION_SHA256 or materialization.get("provider_calls_made") != 0 or materialization.get("process_launches") != 0:
        raise ValueError("materialization lineage drifted")
    candidates = descendants(normalized_root)
    v3, development_groups, split = _development_material(frozen_successor_path=frozen_successor_path, hanna_csv_path=hanna_csv_path)
    freeze = v3.v2_module().parent_modules()[2]
    sources = freeze._source_material(frozen_successor_path=Path(frozen_successor_path), hanna_csv_path=Path(hanna_csv_path))
    cells: list[dict[str, Any]] = []
    for group in development_groups:
        for candidate in candidates:
            payload = _payload(freeze=freeze, item=sources[group["item_id"]], candidate=candidate)
            key = {"study_id": STUDY_ID, "candidate_id": candidate["candidate_id"], "prompt_group_id": group["prompt_group_id"], "item_id": group["item_id"]}
            cells.append({"ordinal": len(cells) + 1, "cell_id": "broader-grok-" + sha256(key)[:16], "route_name": "grok_primary", **group, "candidate_id": candidate["candidate_id"], "candidate_sha256": candidate["candidate_sha256"], "candidate_instruction_sha256": candidate["instruction_sha256"], "candidate_profile_sha256": candidate["profile_sha256"], "payload_base64": base64.b64encode(payload).decode("ascii"), "payload_sha256": sha256(payload), "response_schema_sha256": sha256(canonical(json.loads(payload.decode("utf-8"))["response_schema"]))})
    if len(cells) != 35 or len({row["cell_id"] for row in cells}) != 35 or len({row["payload_sha256"] for row in cells}) != 35:
        raise ValueError("broader 35-cell geometry drifted")
    value = {"format_version": 1, "study_id": STUDY_ID, "kind": "frozen_provider_free_broader_grok_development_schedule", "parent_artifact_sha256": PARENT_ARTIFACT_SHA256, "materialization_file_sha256": MATERIALIZATION_SHA256, "frozen_successor_file_sha256": FROZEN_SUCCESSOR_SHA256, "hanna_csv_file_sha256": HANNA_CSV_SHA256, "v3_source_sha256": V3_SHA256, "candidates": [_manifest(row) for row in candidates], "groups": development_groups, "cells": cells, "geometry": {"candidates": 5, "development_groups": 7, "grok_cells": 35, "sol_cells": 0, "confirmation_cells": 0}, "authority": {"provider_calls_made": 0, "process_launches": 0, "selection": "none", "runtime": "none", "sol": "out_of_scope", "confirmation": {"status": "unopened", "cells": 0}}, "split_sha256": sha256(split)}
    value["schedule_sha256"] = sha256(value)
    _validate_contract(value)
    return value


def freeze(*, output_root: Path, normalized_root: Path, materialization_root: Path, frozen_successor_path: Path, hanna_csv_path: Path) -> dict[str, Any]:
    root = Path(output_root)
    if root.exists():
        raise ValueError("freeze output root must be fresh")
    schedule = build(normalized_root=normalized_root, materialization_root=materialization_root, frozen_successor_path=frozen_successor_path, hanna_csv_path=hanna_csv_path)
    root.mkdir(parents=True)
    for candidate in schedule["candidates"]:
        (root / f"{candidate['candidate_id']}.json").write_bytes(canonical(candidate))
    (root / "schedule.json").write_bytes(canonical(schedule))
    validate_frozen_root(root)
    return schedule


def validate_frozen_root(root: Path) -> dict[str, Any]:
    root = Path(root)
    _plain(root, directory=True)
    schedule_path = root / "schedule.json"
    _plain(schedule_path, directory=False)
    schedule = strict_json(schedule_path, "persisted schedule")
    _validate_contract(schedule)
    candidates = schedule.get("candidates")
    if not isinstance(candidates, list) or len(candidates) != 5:
        raise ValueError("persisted candidate geometry drifted")
    expected = {"schedule.json"}
    for candidate in candidates:
        if not isinstance(candidate, dict) or not isinstance(candidate.get("candidate_id"), str):
            raise ValueError("persisted candidate identity drifted")
        expected.add(candidate["candidate_id"] + ".json")
    actual = {path.name for path in root.iterdir()}
    if actual != expected:
        raise ValueError("persisted root inventory drifted")
    for candidate in candidates:
        path = root / (candidate["candidate_id"] + ".json")
        _plain(path, directory=False)
        persisted = strict_json(path, "persisted candidate manifest")
        if persisted != candidate or canonical(persisted) != canonical(candidate):
            raise ValueError("persisted candidate manifest drifted")
        body = dict(persisted)
        declared = body.pop("manifest_sha256", None)
        if not isinstance(declared, str) or sha256(body) != declared:
            raise ValueError("persisted candidate manifest commitment drifted")
    return schedule
