"""Provider-free validator for the aggregate-only figurative public result."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT.parent / "hbq-figurative-isolated-anchor-pilot-v1-execution-v1"
STUDY_ID = "hbq-figurative-isolated-anchor-pilot-v1-execution-v1-public-result-v1"


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"Expected JSON object: {path.name}")
    return value


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate() -> dict[str, Any]:
    aggregate = _load(ROOT / "aggregate.v1.json")
    provenance = _load(ROOT / "provenance.v1.json")
    if aggregate.get("format_version") != 1 or aggregate.get("study_id") != STUDY_ID:
        raise ValueError("Public aggregate identity drifted")
    if provenance.get("format_version") != 1 or provenance.get("study_id") != STUDY_ID:
        raise ValueError("Public provenance identity drifted")
    if aggregate.get("decision") != "MANUAL_TARGET_UNSTABLE_NO_GO_DSPY_ELIGIBLE":
        raise ValueError("Formal decision drifted")
    execution = aggregate.get("execution")
    if not isinstance(execution, dict) or execution.get("planned_slots") != 18 or execution.get("completed_slots") != 18:
        raise ValueError("Execution aggregate drifted")
    controls = aggregate.get("controls")
    if not isinstance(controls, dict) or set(controls) != {
        "core.freshness_and_non_genericness.no_default_metaphors",
        "penalty.purple_prose.proportion",
    }:
        raise ValueError("Control ownership drifted")
    if controls != {
        "core.freshness_and_non_genericness.no_default_metaphors": {
            "role": "stockness_owner",
            "correct": 6,
            "total": 6,
            "passed": True,
        },
        "penalty.purple_prose.proportion": {
            "role": "density_owner",
            "correct": 6,
            "total": 6,
            "passed": True,
        },
    }:
        raise ValueError("Control result drifted")
    target = aggregate.get("target")
    if not isinstance(target, dict) or target.get("correct") != 5 or target.get("total") != 6:
        raise ValueError("Target aggregate drifted")
    if target.get("cells") != {
        "cooperative_anchor": {"correct": 3, "total": 3},
        "incompatible_imagery_anchor": {"correct": 2, "total": 3},
    }:
        raise ValueError("Target cell aggregate drifted")
    interpretation = aggregate.get("interpretation")
    if not isinstance(interpretation, dict) or interpretation.get("not_supported") != "stable substantive wording failure" or interpretation.get("promotion") != "none":
        raise ValueError("Interpretation boundary drifted")
    source = provenance.get("source")
    bindings = source.get("package_files_sha256") if isinstance(source, dict) else None
    if not isinstance(bindings, dict):
        raise TypeError("Source package bindings are unavailable")
    for name, expected in bindings.items():
        if _sha256(SOURCE / name) != expected:
            raise ValueError(f"Source package file drifted: {name}")
    evidence = provenance.get("settled_evidence_sha256")
    if not isinstance(evidence, dict) or evidence.get("execution_claim.v1.json") != "02141f3c8a9ba5ddd6135110f0e0dfa9c0f4d92791870d16cf6fbf0514d99442" or evidence.get("anchor-pilot-settlement.v1.json") != "0e2802d0b2cc95cd4cb52d824478091a577fb3ad43fb6cb140d29f10ac683460" or evidence.get("public-aggregate.v1.json") != "08ee680929cb8256339c1f5af7e43820581b8b53d3367c6d94414a512f020099":
        raise ValueError("Settled evidence commitments drifted")
    publication = provenance.get("publication")
    if not isinstance(publication, dict) or publication.get("scope") != "aggregate_only" or any(
        publication.get(key) is not False
        for key in ("private_paths", "prose", "prompts", "responses", "session_identifiers", "per_call_records")
    ):
        raise ValueError("Aggregate-only privacy boundary drifted")
    return {
        "study_id": STUDY_ID,
        "state": "valid_aggregate_only_public_result",
        "completed_slots": 18,
        "controls_correct": 12,
        "target_correct": 5,
        "decision": aggregate["decision"],
        "promotion": "none",
    }


if __name__ == "__main__":
    print(json.dumps(validate(), sort_keys=True))
