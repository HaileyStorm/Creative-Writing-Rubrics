"""Provider-free desc17 lower-step generalization candidates and schedule freeze."""
from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
from collections.abc import Mapping
from copy import deepcopy
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
STUDY_ID = "hbq-human-alignment-optimizer-v8-desc17-generalization-candidates-v1"
PREDECESSOR = HERE.parent / "hbq-human-alignment-optimizer-v7-desc16-referent-evidence-candidates-v1"
PREDECESSOR_STUDY_SHA256 = "31735918ae0d9a1e2871e0b40ac00b3c587388531f9c721a73e7334900f2f29a"
PREDECESSOR_CONTRACT_SHA256 = "ffd560d68e5ddf6d73d9534342121c5e56519b6058446b5f34a99d1acb7acd9f"
PARENT_ID = "broader-nextwave-20-missing_evidence_not_no-referent-evidence"
PARENT_CANDIDATE_SHA256 = "572d5e6b96251eacf19951a10574aaefb811beb9d7890e9f702b524d3c5465bb"
PARENT_PROFILE_SHA256 = "07cd3652f4792aef082a0e2d9d615229013663b14599abd011637daf8f185a20"
PARENT_SOL_VETO_RESULT = {
    "commit": "cdefecdc9925559d240c4d0816395e7a7c7ad88c",
    "internal_result_sha256": "9a75197577ca14a012288ac699d730a20873a17872620e11e86a90975151244c",
    "result_file_sha256": "1860b579c7983d9de4296a2f845006b6432a0b7efa682b9090c985028ba838ff",
    "study_id": "hbq-human-alignment-optimizer-v7-desc16-referent-evidence-sol-veto-result-v1",
}
CONTRACT_SHA256 = "f0ba08d13796728254e886a6dd535a93c277f4562907569f637f78cf81f62105"
CHILDREN = (
    (
        "broader-nextwave-25-human-reference-six-slot-evidence-ledger",
        "human_reference_variant",
        "Check every dimension once in canonical order before finalizing any output. For each, locate dimension-bearing material or note internally that no qualifying material is supplied. Do not let a skipped or empty check inherit a neighboring score.",
    ),
    (
        "broader-nextwave-26-construct-framing-human-reader-clean-room",
        "construct_framing",
        "Read the supplied artifact as an ordinary reader of the declared task, then apply only the six fixed definitions. Do not import style-guide, toxicity, moral, genre-familiarity, or general literary-quality judgments unless explicitly declared. Human-reference framing describes reader response; it does not create an overall target score.",
    ),
    (
        "broader-nextwave-27-human-reference-full-scale-realization",
        "human_reference_variant",
        "Use the supplied numeric scale as warranted: reserve the midpoint for genuinely middling realization, and use low or high values only when observed realization supports them. Do not compress every dimension toward the middle or force artificial spread. Ties remain valid when evidence is genuinely indistinguishable.",
    ),
)


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()


def digest(value: bytes | Any) -> str:
    return hashlib.sha256(value if isinstance(value, bytes) else canonical(value)).hexdigest()


def predecessor():
    study_path = PREDECESSOR / "study.py"
    contract_path = PREDECESSOR / "study-contract.json"
    if digest(study_path.read_bytes()) != PREDECESSOR_STUDY_SHA256 or digest(contract_path.read_bytes()) != PREDECESSOR_CONTRACT_SHA256:
        raise ValueError("desc16 predecessor bytes drifted")
    spec = importlib.util.spec_from_file_location("_desc16_predecessor", study_path)
    if spec is None or spec.loader is None:
        raise ValueError("desc16 predecessor cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def contract() -> dict[str, Any]:
    prior = predecessor()
    raw, _identity = prior.predecessor().stable(HERE / "study-contract.json")
    if digest(raw) != CONTRACT_SHA256:
        raise ValueError("study contract bytes drifted")
    value = prior.predecessor().strict(raw, "study contract")
    expected_children = [
        {"addendum": addendum, "candidate_id": candidate_id, "factor": factor}
        for candidate_id, factor, addendum in CHILDREN
    ]
    if (
        value.get("study_id") != STUDY_ID
        or value.get("children") != expected_children
        or value.get("geometry") != {"candidates": 4, "development_groups": 7, "development_items": 13, "grok_cells": 52, "sol_cells": 0}
        or value.get("lineage", {}).get("parent_candidate_sha256") != PARENT_CANDIDATE_SHA256
        or value.get("accepted_parent_result") != PARENT_SOL_VETO_RESULT
    ):
        raise ValueError("study contract drifted")
    return value


def parent(source_schedule: Mapping[str, Any]) -> dict[str, Any]:
    prior = predecessor()
    if source_schedule.get("schedule_sha256") != prior.digest({key: item for key, item in source_schedule.items() if key != "schedule_sha256"}):
        raise ValueError("desc16 predecessor schedule commitment drifted")
    rows = [row for row in source_schedule.get("candidates", []) if row.get("candidate_id") == PARENT_ID]
    if len(rows) != 1:
        raise ValueError("desc16 parent candidate inventory drifted")
    row = deepcopy(rows[0])
    profile_raw = base64.b64decode(row["profile_base64"], validate=True)
    if (
        row.get("candidate_sha256") != PARENT_CANDIDATE_SHA256
        or row.get("profile_sha256") != PARENT_PROFILE_SHA256
        or digest(profile_raw) != PARENT_PROFILE_SHA256
    ):
        raise ValueError("desc16 parent candidate binding drifted")
    row["kind"] = "admitted_cross_model_parent"
    return row


def candidate(parent_row: Mapping[str, Any], candidate_id: str, factor: str, addendum: str) -> dict[str, Any]:
    profile = json.loads(base64.b64decode(parent_row["profile_base64"], validate=True))
    factors = profile.get("factors")
    if not isinstance(factors, dict) or not isinstance(factors.get(factor), str):
        raise TypeError("parent factor surface drifted")
    child = deepcopy(profile)
    child["factors"][factor] = factors[factor] + "\n" + addendum
    changed = [key for key in factors if child["factors"].get(key) != factors[key]]
    if changed != [factor] or child["factors"][factor].count(addendum) != 1:
        raise ValueError("candidate must change exactly one declared factor")
    profile_bytes = json.dumps(child, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    identity = {
        "study_id": STUDY_ID,
        "parent_candidate_sha256": PARENT_CANDIDATE_SHA256,
        "candidate_id": candidate_id,
        "factor": factor,
        "addendum": addendum,
        "instruction_sha256": parent_row["instruction_sha256"],
        "profile_sha256": digest(profile_bytes),
    }
    return {
        "addendum": addendum,
        "candidate_id": candidate_id,
        "candidate_sha256": digest(identity),
        "factor": factor,
        "instruction_base64": parent_row["instruction_base64"],
        "instruction_sha256": parent_row["instruction_sha256"],
        "kind": "one_factor_lower_step_descendant",
        "parent_candidate_id": PARENT_ID,
        "parent_candidate_sha256": PARENT_CANDIDATE_SHA256,
        "profile_base64": base64.b64encode(profile_bytes).decode(),
        "profile_sha256": digest(profile_bytes),
    }


def materialize(development_payloads: Mapping[str, bytes]) -> dict[str, Any]:
    contract()
    prior = predecessor()
    source_schedule = prior.materialize(development_payloads)
    parent_row = parent(source_schedule)
    children = [candidate(parent_row, *child) for child in CHILDREN]
    rows = [parent_row, *children]
    source_cells = {row["item_id"]: row for row in source_schedule["cells"] if row["candidate_id"] == PARENT_ID}
    development_items = prior.predecessor().DEVELOPMENT_ITEMS
    if set(source_cells) != {item for item, _group in development_items}:
        raise ValueError("desc16 parent cell inventory drifted")

    cells = []
    for item_id, group in development_items:
        source_cell = source_cells[item_id]
        parent_payload = base64.b64decode(source_cell["payload_base64"], validate=True)
        if source_cell["payload_sha256"] != digest(parent_payload):
            raise ValueError("desc16 parent payload commitment drifted")
        parent_value = prior.predecessor().strict(parent_payload, "desc16 parent payload")
        for candidate_row in rows:
            value = deepcopy(parent_value)
            value["instruction"] = base64.b64decode(candidate_row["instruction_base64"], validate=True).decode()
            value["profile"] = json.loads(base64.b64decode(candidate_row["profile_base64"], validate=True))
            payload = canonical(value)
            payload_sha256 = digest(payload)
            cells.append(
                {
                    "candidate_id": candidate_row["candidate_id"],
                    "candidate_sha256": candidate_row["candidate_sha256"],
                    "candidate_instruction_sha256": candidate_row["instruction_sha256"],
                    "candidate_profile_sha256": candidate_row["profile_sha256"],
                    "cell_id": "desc17-grok-" + digest({"candidate": candidate_row["candidate_id"], "item": item_id})[:16],
                    "endpoint_payload_sha256s": {"grok_primary": payload_sha256, "sol_veto_if_qualified": payload_sha256},
                    "item_id": item_id,
                    "ordinal": len(cells) + 1,
                    "partition": "development",
                    "payload_base64": base64.b64encode(payload).decode(),
                    "payload_sha256": payload_sha256,
                    "prompt_group_id": group,
                    "route_name": "grok_primary",
                }
            )
    result = {
        "authority": {"confirmation": "unopened", "dspy_optuna_runtime": "forbidden", "process_launches": 0, "provider_calls_made": 0, "reserve": "unopened", "selection": "none", "sol": "veto_only_after_grok_qualification"},
        "candidates": rows,
        "cells": cells,
        "format_version": 1,
        "geometry": {"candidates": 4, "development_groups": 7, "development_items": 13, "grok_cells": 52, "sol_cells": 0},
        "kind": "provider_free_desc17_lower_step_generalization_development_schedule",
        "lineage": {"parent_candidate_id": PARENT_ID, "parent_candidate_sha256": PARENT_CANDIDATE_SHA256, "parent_profile_sha256": PARENT_PROFILE_SHA256, "predecessor_commit": "2fb8b1e1dd9acc0d0869c3ebf51c384653ac3ee5"},
        "study_id": STUDY_ID,
    }
    result["schedule_sha256"] = digest(result)
    validate(result, source_schedule)
    return result


def validate(value: Mapping[str, Any], source_schedule: Mapping[str, Any]) -> None:
    prior = predecessor()
    expected_geometry = {"candidates": 4, "development_groups": 7, "development_items": 13, "grok_cells": 52, "sol_cells": 0}
    if value.get("study_id") != STUDY_ID or value.get("geometry") != expected_geometry:
        raise ValueError("schedule geometry drifted")
    cells = value.get("cells")
    if not isinstance(cells, list) or len(cells) != 52:
        raise ValueError("schedule cell count drifted")
    candidate_ids = (PARENT_ID, *(candidate_id for candidate_id, _factor, _addendum in CHILDREN))
    development_items = prior.predecessor().DEVELOPMENT_ITEMS
    expected = {(candidate_id, item_id) for candidate_id in candidate_ids for item_id, _group in development_items}
    observed = {(row.get("candidate_id"), row.get("item_id")) for row in cells}
    if observed != expected or len(observed) != 52 or {row.get("route_name") for row in cells} != {"grok_primary"}:
        raise ValueError("schedule pairing drifted")
    if value.get("schedule_sha256") != digest({key: item for key, item in value.items() if key != "schedule_sha256"}):
        raise ValueError("schedule commitment drifted")
    source_parent = {row["item_id"]: base64.b64decode(row["payload_base64"], validate=True) for row in source_schedule["cells"] if row["candidate_id"] == PARENT_ID}
    candidate_rows = {row["candidate_id"]: row for row in value.get("candidates", [])}
    if set(candidate_rows) != set(candidate_ids):
        raise ValueError("candidate inventory drifted")
    if candidate_rows[PARENT_ID] != parent(source_schedule):
        raise ValueError("parent candidate drifted")
    parent_profile = json.loads(base64.b64decode(candidate_rows[PARENT_ID]["profile_base64"], validate=True))
    for candidate_id, factor, addendum in CHILDREN:
        child = candidate_rows[candidate_id]
        child_profile = json.loads(base64.b64decode(child["profile_base64"], validate=True))
        changed = [key for key in parent_profile["factors"] if child_profile["factors"].get(key) != parent_profile["factors"][key]]
        if changed != [factor] or child_profile["factors"][factor] != parent_profile["factors"][factor] + "\n" + addendum:
            raise ValueError("one-factor candidate drifted")
        if child != candidate(candidate_rows[PARENT_ID], candidate_id, factor, addendum):
            raise ValueError("child candidate identity drifted")
    expected_groups = dict(development_items)
    for row in cells:
        payload = base64.b64decode(row["payload_base64"], validate=True)
        if digest(payload) != row.get("payload_sha256") or row.get("endpoint_payload_sha256s") != {"grok_primary": row["payload_sha256"], "sol_veto_if_qualified": row["payload_sha256"]}:
            raise ValueError("payload endpoint binding drifted")
        decoded = prior.predecessor().strict(payload, "desc17 payload")
        prior.predecessor()._reject_private_fields(decoded)
        if row.get("partition") != "development" or row.get("prompt_group_id") != expected_groups[row["item_id"]]:
            raise ValueError("frozen partition binding drifted")
        rendered = payload.decode().lower()
        if any(marker in rendered for marker in ("fresh96", "private-freeze", "future_confirmation", "c:/users/", "\\\\users\\\\", '"reference_score"')):
            raise ValueError("forbidden private partition or target leakage")
        if row["candidate_id"] == PARENT_ID and payload != source_parent[row["item_id"]]:
            raise ValueError("parent payload bytes changed")


def freeze(output_root: Path, development_payloads: Mapping[str, bytes]) -> dict[str, Any]:
    prior = predecessor().predecessor()
    root = Path(output_root)
    if root.exists():
        raise ValueError("freeze output root must be fresh")
    prior._ancestry(root.parent, directory=True)
    schedule = materialize(development_payloads)
    if schedule != materialize(development_payloads):
        raise ValueError("inputs changed between materialization phases")
    root.mkdir()
    root_ancestry = prior._ancestry(root, directory=True)
    prior._safe_write(root / "schedule.json", canonical(schedule), expected_root_ancestry=root_ancestry)
    manifest = {"candidate_sha256s": [row["candidate_sha256"] for row in schedule["candidates"]], "schedule_sha256": schedule["schedule_sha256"], "study_id": STUDY_ID}
    prior._safe_write(root / "manifest.json", canonical(manifest), expected_root_ancestry=root_ancestry)
    validate_frozen_root(root, development_payloads, expected_root_ancestry=root_ancestry)
    return schedule


def validate_frozen_root(root: Path, development_payloads: Mapping[str, bytes], *, expected_root_ancestry=None) -> dict[str, Any]:
    prior = predecessor().predecessor()
    root = Path(root)
    root_ancestry = prior._ancestry(root, directory=True)
    if expected_root_ancestry is not None and root_ancestry != expected_root_ancestry:
        raise ValueError("freeze root changed before final validation")
    if {path.name for path in root.iterdir()} != {"manifest.json", "schedule.json"}:
        raise ValueError("freeze inventory drifted")
    schedule = prior.strict(prior.stable(root / "schedule.json")[0], "schedule")
    rebuilt = materialize(development_payloads)
    if schedule != rebuilt:
        raise ValueError("persisted schedule or input drifted")
    manifest = prior.strict(prior.stable(root / "manifest.json")[0], "manifest")
    expected_manifest = {"candidate_sha256s": [row["candidate_sha256"] for row in schedule["candidates"]], "schedule_sha256": schedule["schedule_sha256"], "study_id": STUDY_ID}
    if manifest != expected_manifest:
        raise ValueError("manifest commitment drifted")
    if prior._ancestry(root, directory=True) != root_ancestry:
        raise ValueError("freeze root changed during final validation")
    return schedule
