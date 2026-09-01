"""Provider-free desc16 referent-evidence micro-candidates and schedule freeze."""
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
STUDY_ID = "hbq-human-alignment-optimizer-v7-desc16-referent-evidence-candidates-v1"
PREDECESSOR = HERE.parent / "hbq-human-alignment-optimizer-v6-desc15-referent-candidates-v1"
PREDECESSOR_STUDY_SHA256 = "ee2bd2712f725fb3b3006d6223eef3eef458d60defa230824c99e765064f732c"
PREDECESSOR_CONTRACT_SHA256 = "97d4e72f9ea806f8efad68d7f98bf53fdb31e7ba309d35bb83f35d622bde823d"
PREDECESSOR_SCHEDULE_SHA256 = "d2935d770079a4bacee654ef36c165fc27bb6f700d48647cf1f867dee5c276b4"
CONTRACT_SHA256 = "ffd560d68e5ddf6d73d9534342121c5e56519b6058446b5f34a99d1acb7acd9f"
PARENT_ID = "broader-nextwave-20-missing_evidence_not_no-referent-evidence"
PARENT_CANDIDATE_SHA256 = "572d5e6b96251eacf19951a10574aaefb811beb9d7890e9f702b524d3c5465bb"
PARENT_PROFILE_SHA256 = "07cd3652f4792aef082a0e2d9d615229013663b14599abd011637daf8f185a20"
FACTOR = "missing_evidence_not_no"
CHILDREN = (
    (
        "broader-nextwave-22-missing_evidence_not_no-referent-contradiction-threshold",
        "Step-06 contradiction threshold: only two locally stated, mutually incompatible referent facts count as a contradiction; uncertainty alone remains neutral.",
    ),
    (
        "broader-nextwave-23-missing_evidence_not_no-local-antecedent-only",
        "Step-06 local antecedent: use only antecedents stated in the supplied passage; do not invent missing links or recover them from presumed intent.",
    ),
    (
        "broader-nextwave-24-missing_evidence_not_no-referent-dimension-isolation",
        "Step-06 dimension isolation: apply referent evidence only to Coherence; do not propagate referent ambiguity or contradiction into other dimension scores.",
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
        raise ValueError("desc15 predecessor bytes drifted")
    spec = importlib.util.spec_from_file_location("_desc15_predecessor", study_path)
    if spec is None or spec.loader is None:
        raise ValueError("desc15 predecessor cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def contract() -> dict[str, Any]:
    prior = predecessor()
    raw, _identity = prior.stable(HERE / "study-contract.json")
    if digest(raw) != CONTRACT_SHA256:
        raise ValueError("study contract bytes drifted")
    value = prior.strict(raw, "study contract")
    if value.get("study_id") != STUDY_ID or value.get("lineage", {}).get("parent_candidate_sha256") != PARENT_CANDIDATE_SHA256:
        raise ValueError("study contract drifted")
    if value.get("children") != [{"addendum": addendum, "candidate_id": candidate_id} for candidate_id, addendum in CHILDREN]:
        raise ValueError("study contract children drifted")
    if value.get("geometry") != {"candidates": 4, "development_groups": 7, "development_items": 13, "grok_cells": 52, "sol_cells": 0}:
        raise ValueError("study contract geometry drifted")
    return value


def parent(source_schedule: Mapping[str, Any]) -> dict[str, Any]:
    if source_schedule.get("schedule_sha256") != digest({key: item for key, item in source_schedule.items() if key != "schedule_sha256"}):
        raise ValueError("desc15 predecessor schedule commitment drifted")
    rows = [row for row in source_schedule.get("candidates", []) if row.get("candidate_id") == PARENT_ID]
    if len(rows) != 1:
        raise ValueError("desc15 parent candidate inventory drifted")
    row = deepcopy(rows[0])
    profile_raw = base64.b64decode(row["profile_base64"], validate=True)
    if row.get("candidate_sha256") != PARENT_CANDIDATE_SHA256 or row.get("profile_sha256") != PARENT_PROFILE_SHA256 or digest(profile_raw) != PARENT_PROFILE_SHA256:
        raise ValueError("desc15 parent candidate binding drifted")
    row["kind"] = "admitted_cross_model_parent"
    return row


def candidate(parent_row: Mapping[str, Any], candidate_id: str, addendum: str) -> dict[str, Any]:
    profile = json.loads(base64.b64decode(parent_row["profile_base64"], validate=True))
    factors = profile.get("factors")
    if not isinstance(factors, dict) or not isinstance(factors.get(FACTOR), str):
        raise TypeError("parent factor surface drifted")
    child = deepcopy(profile)
    child["factors"][FACTOR] = factors[FACTOR] + "\n" + addendum
    changed = [key for key in factors if child["factors"].get(key) != factors[key]]
    if changed != [FACTOR] or child["factors"][FACTOR].count(addendum) != 1:
        raise ValueError("candidate must change exactly the referent-evidence factor")
    profile_bytes = json.dumps(child, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    identity = {
        "study_id": STUDY_ID,
        "parent_candidate_sha256": PARENT_CANDIDATE_SHA256,
        "candidate_id": candidate_id,
        "factor": FACTOR,
        "addendum": addendum,
        "instruction_sha256": parent_row["instruction_sha256"],
        "profile_sha256": digest(profile_bytes),
    }
    return {
        "addendum": addendum,
        "candidate_id": candidate_id,
        "candidate_sha256": digest(identity),
        "factor": FACTOR,
        "instruction_base64": parent_row["instruction_base64"],
        "instruction_sha256": parent_row["instruction_sha256"],
        "kind": "one_factor_micro_descendant",
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
    children = [candidate(parent_row, candidate_id, addendum) for candidate_id, addendum in CHILDREN]
    rows = [parent_row, *children]
    source_cells = {
        row["item_id"]: row
        for row in source_schedule["cells"]
        if row["candidate_id"] == PARENT_ID
    }
    if set(source_cells) != {item for item, _group in prior.DEVELOPMENT_ITEMS}:
        raise ValueError("desc15 parent cell inventory drifted")

    cells = []
    for item_id, group in prior.DEVELOPMENT_ITEMS:
        source_cell = source_cells[item_id]
        parent_payload = base64.b64decode(source_cell["payload_base64"], validate=True)
        parent_value = prior.strict(parent_payload, "desc15 parent payload")
        if source_cell["payload_sha256"] != digest(parent_payload):
            raise ValueError("desc15 parent payload commitment drifted")
        for candidate_row in rows:
            value = deepcopy(parent_value)
            value["instruction"] = base64.b64decode(candidate_row["instruction_base64"], validate=True).decode()
            value["profile"] = json.loads(base64.b64decode(candidate_row["profile_base64"], validate=True))
            payload = canonical(value)
            cells.append(
                {
                    "candidate_id": candidate_row["candidate_id"],
                    "candidate_sha256": candidate_row["candidate_sha256"],
                    "candidate_instruction_sha256": candidate_row["instruction_sha256"],
                    "candidate_profile_sha256": candidate_row["profile_sha256"],
                    "cell_id": "desc16-grok-" + digest({"candidate": candidate_row["candidate_id"], "item": item_id})[:16],
                    "item_id": item_id,
                    "ordinal": len(cells) + 1,
                    "partition": "development",
                    "payload_base64": base64.b64encode(payload).decode(),
                    "payload_sha256": digest(payload),
                    "prompt_group_id": group,
                    "route_name": "grok_primary",
                }
            )

    result = {
        "authority": {
            "confirmation": "unopened",
            "dspy_optuna_runtime": "forbidden",
            "process_launches": 0,
            "provider_calls_made": 0,
            "reserve": "unopened",
            "selection": "none",
            "sol": "veto_only_after_grok_qualification",
        },
        "candidates": rows,
        "format_version": 1,
        "geometry": {"candidates": 4, "development_groups": 7, "development_items": 13, "grok_cells": 52, "sol_cells": 0},
        "kind": "provider_free_desc16_referent_evidence_development_schedule",
        "lineage": {
            "parent_candidate_id": PARENT_ID,
            "parent_candidate_sha256": PARENT_CANDIDATE_SHA256,
            "parent_profile_sha256": PARENT_PROFILE_SHA256,
            "predecessor_commit": "38ac0b7d7ed992f1b7604e813f7c766699d23a86",
            "predecessor_schedule_sha256": PREDECESSOR_SCHEDULE_SHA256,
        },
        "cells": cells,
        "study_id": STUDY_ID,
    }
    result["schedule_sha256"] = digest(result)
    validate(result, source_schedule)
    return result


def validate(value: Mapping[str, Any], source_schedule: Mapping[str, Any]) -> None:
    if value.get("study_id") != STUDY_ID or value.get("geometry") != {"candidates": 4, "development_groups": 7, "development_items": 13, "grok_cells": 52, "sol_cells": 0}:
        raise ValueError("schedule geometry drifted")
    cells = value.get("cells")
    if not isinstance(cells, list) or len(cells) != 52:
        raise ValueError("schedule cell count drifted")
    candidate_ids = (PARENT_ID, *(candidate_id for candidate_id, _addendum in CHILDREN))
    prior = predecessor()
    expected = {(candidate_id, item_id) for candidate_id in candidate_ids for item_id, _group in prior.DEVELOPMENT_ITEMS}
    observed = {(row.get("candidate_id"), row.get("item_id")) for row in cells}
    if observed != expected or len(observed) != 52:
        raise ValueError("schedule pairing drifted")
    if value.get("schedule_sha256") != digest({key: item for key, item in value.items() if key != "schedule_sha256"}):
        raise ValueError("schedule commitment drifted")
    source_parent = {
        row["item_id"]: base64.b64decode(row["payload_base64"], validate=True)
        for row in source_schedule["cells"]
        if row["candidate_id"] == PARENT_ID
    }
    for row in cells:
        payload = base64.b64decode(row["payload_base64"], validate=True)
        if digest(payload) != row["payload_sha256"]:
            raise ValueError("payload commitment drifted")
        decoded = prior.strict(payload, "desc16 payload")
        prior._reject_private_fields(decoded)
        if row["candidate_id"] == PARENT_ID and payload != source_parent[row["item_id"]]:
            raise ValueError("parent payload bytes changed")
        rendered = payload.decode().lower()
        if any(marker in rendered for marker in ("fresh96", "private-freeze", "future_confirmation", "c:/users/", "\\\\users\\\\")):
            raise ValueError("forbidden private partition or target leakage")


def freeze(output_root: Path, development_payloads: Mapping[str, bytes]) -> dict[str, Any]:
    prior = predecessor()
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
    manifest = {
        "candidate_sha256s": [row["candidate_sha256"] for row in schedule["candidates"]],
        "schedule_sha256": schedule["schedule_sha256"],
        "study_id": STUDY_ID,
    }
    prior._safe_write(root / "manifest.json", canonical(manifest), expected_root_ancestry=root_ancestry)
    validate_frozen_root(root, development_payloads, expected_root_ancestry=root_ancestry)
    return schedule


def validate_frozen_root(
    root: Path,
    development_payloads: Mapping[str, bytes],
    *,
    expected_root_ancestry=None,
) -> dict[str, Any]:
    prior = predecessor()
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
    expected_manifest = {
        "candidate_sha256s": [row["candidate_sha256"] for row in schedule["candidates"]],
        "schedule_sha256": schedule["schedule_sha256"],
        "study_id": STUDY_ID,
    }
    if manifest != expected_manifest:
        raise ValueError("manifest commitment drifted")
    if prior._ancestry(root, directory=True) != root_ancestry:
        raise ValueError("freeze root changed during final validation")
    return schedule
