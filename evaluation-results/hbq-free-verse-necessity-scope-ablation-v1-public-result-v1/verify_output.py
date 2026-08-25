from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
AGGREGATE = ROOT / "aggregate.v1.json"
ALLOWED_FILES = {"README.md", "aggregate.v1.json", "verify_output.py"}
EXPECTED = {
    "format_version": 1,
    "study_id": "hbq-free-verse-necessity-scope-ablation-v1-execution-v1",
    "classification": "VALID_EXECUTION_NEGATIVE_DISCRIMINATION_NO_PROMOTION",
    "planned_provider_calls": 36,
    "accepted_provider_calls": 36,
    "terminal_provider_failures": 0,
    "cell_repeat_stable": 11,
    "cell_level_expected_matches": 8,
    "promotion": "none",
    "scope_singleton_oracle": "invalid_for_module_gate",
}
FORBIDDEN = {"question_id", "slot_id", "case_id", "expected_verdict", "raw_prompt", "raw_response", "exact_quote", "session_id", "request_id", "absolute_path"}
EXPECTED_COMMITMENT = "01e4ef01af8819142ee26f50c05d184d183eeb60cfad792959bcf4f4e5140147"


def _read() -> dict[str, Any]:
    value = json.loads(AGGREGATE.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Aggregate result must be an object")
    return value


def verify() -> dict[str, Any]:
    value = _read()
    if {key: value.get(key) for key in EXPECTED} != EXPECTED:
        raise ValueError("Aggregate execution result drifted")
    if value.get("aggregate_cell_labels") != ["complete_necessary", "complete_arbitrary", "stanza_excerpt", "line_excerpt", "missing_poem_coverage", "inactive_metadata_control"]:
        raise ValueError("Aggregate cell labels drifted")
    if value.get("necessity_arm") != {"call_level_expected_matches": 18, "calls": 18, "cells": 6, "cells_repeat_stable": 6}:
        raise ValueError("Necessity aggregate drifted")
    if value.get("paired_arms") != {"calls_with_same_verdict": 16, "cells_with_same_distribution": 5, "cells": 6, "scope_metadata_cell": "varied"}:
        raise ValueError("Paired aggregate drifted")
    commitment = value.get("opaque_private_receipt_and_settlement_commitment_sha256")
    if commitment != EXPECTED_COMMITMENT:
        raise ValueError("Opaque private commitment drifted")
    expected_keys = {*EXPECTED, "aggregate_cell_labels", "necessity_arm", "paired_arms", "opaque_private_receipt_and_settlement_commitment_sha256"}
    if set(value) != expected_keys:
        raise ValueError("Aggregate result contains an unexpected field")
    if any(key.lower() in FORBIDDEN for key in value):
        raise ValueError("Aggregate result exposes private metadata")
    files = {path.name for path in ROOT.iterdir() if path.is_file()}
    if files != ALLOWED_FILES or any(path.is_dir() for path in ROOT.iterdir()):
        raise ValueError("Aggregate package surface drifted")
    return value


if __name__ == "__main__":
    print(json.dumps(verify(), sort_keys=True))
