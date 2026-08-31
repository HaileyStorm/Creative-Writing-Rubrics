#!/usr/bin/env python3
"""Verify the immutable, descriptive-only HANNA v5 result publication."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent
GEOMETRY = {"logical_cells": 33, "unique_payload_cells": 30, "aliases": 3, "effective_candidates": 10, "prompt_groups": 3}
SOURCE_ARTIFACTS = {
    "alias_manifest_sha256": "fe79880e3d3a719255784900e21c28d04caa5f849649d1327658971b7f86d35f",
    "collector_file_sha256": "4af3adcfabf4410e895468e929f368bbfb0f20fbf834df767a2fb646fd0b6809",
    "executor_commit": "856451a906ff387ead4d7627b28a5418c8a52f83",
    "executor_sha256": "331c9749e29779de450f83871cf9b23001e1d705227f3b4d0b0de8a650292079",
    "result_file_sha256": "ba43a42d7959ae184cb1bd341062a82bac49a04a39f68e5af1bf0405d9c4ce3d",
    "result_internal_sha256": "c3da5428731bf85da13e3aaa10f36a4407a4efc8deb232b0e473913b5237a7d6",
    "schedule_sha256": "5056e681cbcef92aef3335ed58d7a20dabf3a8c4b962f5e463752ce827d39104",
}


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def sha256(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def _read(name: str) -> dict[str, Any]:
    value = json.loads((HERE / name).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be an object")
    return value


def verify() -> dict[str, Any]:
    contract, result = _read("study-contract.json"), _read("result.json")
    source = contract.get("source_artifacts")
    if contract.get("format_version") != 1 or contract.get("kind") != "immutable_descriptive_result_publication" or source != SOURCE_ARTIFACTS or contract.get("geometry") != GEOMETRY or result.get("publication_geometry") != GEOMETRY:
        raise ValueError("publication contract drifted")
    if result.get("source_artifacts") != SOURCE_ARTIFACTS or result.get("study_id") != contract.get("study_id") or result.get("collector_sha256") != source.get("collector_file_sha256") or result.get("alias_manifest_sha256") != source.get("alias_manifest_sha256"):
        raise ValueError("result provenance drifted")
    if result.get("native_endpoint_contact_cardinality") != "unproven" or contract.get("evidence_ceiling") != "Grok-only descriptive development evidence with unproven native endpoint contact cardinality":
        raise ValueError("contact-cardinality ceiling drifted")
    authority = result.get("authority")
    expected_authority = {"selection": "none", "promotion": "none", "runtime": "none", "confirmation": {"status": "unopened", "cells": 0}}
    if authority != expected_authority or any(contract["authority"].get(key) != "none" for key in ("selection", "promotion", "runtime", "sol_validation", "general_hanna_gain")) or contract["authority"].get("strict_v5_projection") != "rejected":
        raise ValueError("publication authority drifted")
    metrics = result.get("metrics")
    if not isinstance(metrics, list) or len(metrics) != GEOMETRY["effective_candidates"] or GEOMETRY["logical_cells"] != GEOMETRY["unique_payload_cells"] + GEOMETRY["aliases"]:
        raise ValueError("candidate geometry drifted")
    seen: set[str] = set()
    prior: tuple[float, str] | None = None
    for row in metrics:
        if not isinstance(row, dict) or set(row) != {"candidate_id", "cells", "equal_group_mae", "group_mae"} or row["cells"] != 3 or not isinstance(row["candidate_id"], str) or row["candidate_id"] in seen:
            raise ValueError("candidate row drifted")
        groups = row["group_mae"]
        if not isinstance(groups, dict) or len(groups) != GEOMETRY["prompt_groups"] or any(not isinstance(value, (int, float)) for value in groups.values()):
            raise ValueError("group geometry drifted")
        mean = sum(groups.values()) / GEOMETRY["prompt_groups"]
        if row["equal_group_mae"] != mean:
            raise ValueError("equal-group MAE drifted")
        current = (row["equal_group_mae"], row["candidate_id"])
        if prior is not None and current < prior:
            raise ValueError("metrics order drifted")
        prior = current; seen.add(row["candidate_id"])
    internal = dict(result); recorded = internal.pop("result_sha256", None); internal.pop("publication_geometry", None); internal.pop("source_artifacts", None)
    if recorded != source.get("result_internal_sha256") or recorded != sha256(internal):
        raise ValueError("result commitment drifted")
    return {"effective_candidates": len(metrics), "logical_cells": GEOMETRY["logical_cells"], "unique_payload_cells": GEOMETRY["unique_payload_cells"], "result_sha256": recorded, "evidence_ceiling": contract["evidence_ceiling"]}


if __name__ == "__main__":
    print(json.dumps(verify(), sort_keys=True))
