"""Provider-free validator for the V6 aggregate-only DSPy result."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
STUDY_ID = "hbq-poetry-whole-poem-architecture-dspy-v1-public-result-v1"
EXPECTED = {
    "format_version": 1,
    "study_id": STUDY_ID,
    "classification": "HARNESS_INVALID_OPTIMIZATION_NO_TRANSFER_NO_PROMOTION",
    "source_commitments": {
        "settlement_sha256": "71472f4adab07c679752a6c54d9fe7886d25da7b5c7bf7020d93f607e7897af7",
        "static_export_sha256": "6c1ae8681ffc44f5be677f442ab0c3a35a712a604b3a69939d1e5467a38fe373",
    },
    "execution": {
        "adapter_allocations": 44,
        "provider_dispatches_started": 44,
        "confirmed_provider_contacts": 44,
        "proposal_responses": 4,
        "task_responses": 40,
        "retries": 0,
    },
    "static_export": {"words": 10, "identical_to_baseline": True},
    "mechanical_metrics": {
        "default": {"matched": 0, "total": 8},
        "trial_1": {"matched": 0, "total": 8},
        "trial_2": {"matched": 0, "total": 8},
        "trial_3": {"matched": 0, "total": 8},
        "trial_4": {"matched": 0, "total": 8},
    },
    "mechanical_evidence": {
        "allowed_literal_verdicts": {"matched": 0, "total": 40},
        "whole_evidence_exact_substrings": {"matched": 0, "total": 40},
    },
    "manual_semantic_rescore": {
        "default": {"matched": 7, "total": 8},
        "trial_1": {"matched": 5, "total": 8},
        "trial_2": {"matched": 6, "total": 8},
        "trial_3": {"matched": 5, "total": 8},
        "trial_4": {"matched": 4, "total": 8},
        "possible_generous_trial_4": {"matched": 5, "total": 8},
        "complete_single_part_na_boundary": {"missed": 5, "total": 5},
    },
    "decisions": {
        "transfer": "none",
        "wording_change": "none",
        "runtime_dspy": "none",
        "promotion": "none",
    },
    "publication": {
        "scope": "aggregate_only",
        "contains_prose_or_prompts": False,
        "contains_raw_responses": False,
        "contains_private_paths_or_identifiers": False,
    },
}


def read_result() -> dict[str, Any]:
    value = json.loads((ROOT / "aggregate.v1.json").read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError("aggregate.v1.json must contain an object")
    return value


def validate(value: dict[str, Any] | None = None) -> dict[str, Any]:
    value = read_result() if value is None else value
    if value != EXPECTED:
        raise ValueError("public aggregate projection drifted")
    for commitment in value["source_commitments"].values():
        if not isinstance(commitment, str) or not re.fullmatch(r"[0-9a-f]{64}", commitment):
            raise ValueError("invalid source commitment")
    if sum(value["execution"][key] for key in ("proposal_responses", "task_responses")) != value["execution"]["confirmed_provider_contacts"]:
        raise ValueError("response accounting drifted")
    published_files = {
        path.relative_to(ROOT).as_posix()
        for path in ROOT.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    }
    if published_files != {"aggregate.v1.json", "README.md", "verify.py"}:
        raise ValueError("public package shape drifted")
    public_text = "\n".join(
        (ROOT / name).read_text(encoding="utf-8")
        for name in ("aggregate.v1.json", "README.md")
    )
    forbidden = ("C:\\Users\\", "session_id", "slot_id", "case_id", "artifact_text", "provider_artifacts")
    if any(marker in public_text for marker in forbidden):
        raise ValueError("private material in public package")
    return {
        "study_id": STUDY_ID,
        "state": "valid_aggregate_only_public_result",
        "classification": value["classification"],
        "contacts": value["execution"]["confirmed_provider_contacts"],
        "promotion": value["decisions"]["promotion"],
    }


if __name__ == "__main__":
    print(json.dumps(validate(), sort_keys=True))
