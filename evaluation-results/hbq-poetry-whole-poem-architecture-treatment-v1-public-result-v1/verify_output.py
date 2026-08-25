from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
AGGREGATE = ROOT / "aggregate.v1.json"
ALLOWED_FILES = {"README.md", "aggregate.v1.json", "verify_output.py"}
IGNORED_GENERATED_DIRECTORIES = {"__pycache__"}
EXPECTED = {
    "candidate_outcome": {"correct": 13, "total": 21},
    "decision": "NO_GO_CANDIDATE",
    "format_version": 1,
    "opaque_execution_commitments": {
        "execution_contract_sha256": "c5fb28be4ab6e510a641e5f384845572f769c1868a1234717f8f9ae7c49f0915",
        "execution_manifest_sha256": "c3a3ccf47f008577a5dc805ecf434cb9d90bb5d18a135c54eb6cdc0dbc87b1f5",
        "sealed_settlement_sha256": "0065bee48b4bd3cbb51c87043968e063a92ec2f5bbd05847cabe72fe7a2aa8be",
    },
    "promotion": "none",
    "protocol_geometry": {"candidate_calls": 21, "current_calls": 21, "planned_calls": 42, "valid_terminals": 42},
    "stable_3_of_3_arm_gap_case_ids": ["line_excerpt", "missing_poem_coverage", "single_unit_poem"],
    "study_id": "hbq-poetry-whole-poem-architecture-treatment-v1-execution-v1",
}
EXPECTED_CASES = {
    "interchangeable_architecture": {"candidate": {"YES": 3}, "candidate_expected_matches": 0, "current": {"YES": 3}},
    "line_excerpt": {"candidate": {"NOT_APPLICABLE": 3}, "candidate_expected_matches": 3, "current": {"CANNOT_ASSESS": 3}},
    "missing_poem_coverage": {"candidate": {"NOT_APPLICABLE": 3}, "candidate_expected_matches": 0, "current": {"YES": 3}},
    "ordered_architecture": {"candidate": {"YES": 3}, "candidate_expected_matches": 3, "current": {"YES": 3}},
    "owner_positive_architecture_negative": {"candidate": {"NO": 1, "YES": 2}, "candidate_expected_matches": 1, "current": {"YES": 3}},
    "single_unit_poem": {"candidate": {"NOT_APPLICABLE": 3}, "candidate_expected_matches": 3, "current": {"YES": 3}},
    "stanza_excerpt": {"candidate": {"NOT_APPLICABLE": 3}, "candidate_expected_matches": 3, "current": {"CANNOT_ASSESS": 1, "YES": 2}},
}
FORBIDDEN_FIELD_NAMES = {"absolute_path", "exact_quote", "question_id", "raw_prompt", "raw_response", "request_id", "session_id", "slot_id"}


def _read() -> dict[str, Any]:
    value = json.loads(AGGREGATE.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Aggregate result must be an object")
    return value


def verify() -> dict[str, Any]:
    value = _read()
    expected_keys = {*EXPECTED, "per_case_outcomes"}
    if set(value) != expected_keys:
        raise ValueError("Aggregate result contains an unexpected field")
    if {key: value.get(key) for key in EXPECTED} != EXPECTED:
        raise ValueError("Aggregate result drifted")
    if value.get("per_case_outcomes") != EXPECTED_CASES:
        raise ValueError("Case aggregate outcomes drifted")
    if sum(case["candidate_expected_matches"] for case in EXPECTED_CASES.values()) != value["candidate_outcome"]["correct"]:
        raise ValueError("Candidate aggregate arithmetic drifted")
    if any(key.lower() in FORBIDDEN_FIELD_NAMES for key in value):
        raise ValueError("Aggregate result exposes a restricted field")
    commitments = value["opaque_execution_commitments"]
    if not all(isinstance(item, str) and re.fullmatch(r"[0-9a-f]{64}", item) for item in commitments.values()):
        raise ValueError("Opaque commitments are malformed")
    files = {path.name for path in ROOT.iterdir() if path.is_file()}
    directories = {path.name for path in ROOT.iterdir() if path.is_dir()}
    if files != ALLOWED_FILES or directories - IGNORED_GENERATED_DIRECTORIES:
        raise ValueError("Aggregate package surface drifted")
    return value


if __name__ == "__main__":
    print(json.dumps(verify(), sort_keys=True))
