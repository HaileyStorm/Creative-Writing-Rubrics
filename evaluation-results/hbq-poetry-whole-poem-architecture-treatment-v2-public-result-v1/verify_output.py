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
    "candidate_outcome": {"correct": 16, "total": 21},
    "decision": "NO_GO_CANDIDATE",
    "format_version": 1,
    "opaque_execution_commitments": {
        "execution_contract_sha256": "512e45c41c4edb04ad1726c10a2e3a80d100c84112f9cb2562bdcda03decc5f3",
        "execution_manifest_sha256": "f36b34a041cb26c385dfeb74e39f9ec365659638dbf6c47dffd5cbf774f4bbe1",
        "sealed_settlement_sha256": "75351b53d49ebed043d0d0bf1aabddf17cc07687594df4d945a7074a9199e16a",
    },
    "promotion": "none",
    "protocol_geometry": {"candidate_calls": 21, "current_calls": 21, "planned_calls": 42, "valid_terminals": 42},
    "stable_3_of_3_arm_gap_case_ids": ["complete_single_part", "declared_excerpt"],
    "study_id": "hbq-poetry-whole-poem-architecture-treatment-v2-execution-v1",
}
EXPECTED_CASES = {
    "complete_single_part": {"candidate": {"NOT_APPLICABLE": 3}, "candidate_expected_matches": 3, "current": {"YES": 3}},
    "declared_excerpt": {"candidate": {"NOT_APPLICABLE": 3}, "candidate_expected_matches": 3, "current": {"YES": 3}},
    "declared_whole_poem_incomplete": {"candidate": {"CANNOT_ASSESS": 3}, "candidate_expected_matches": 3, "current": {"CANNOT_ASSESS": 3}},
    "ending_only_coda": {"candidate": {"NO": 2, "YES": 1}, "candidate_expected_matches": 2, "current": {"YES": 3}},
    "inter_part_positive": {"candidate": {"YES": 3}, "candidate_expected_matches": 3, "current": {"YES": 3}},
    "permutation_neutral": {"candidate": {"NO": 2, "NOT_APPLICABLE": 1}, "candidate_expected_matches": 2, "current": {"YES": 3}},
    "semantic_progression_without_inter_part_relation": {"candidate": {"YES": 3}, "candidate_expected_matches": 0, "current": {"YES": 3}},
}
FORBIDDEN_FIELD_NAMES = {"absolute_path", "exact_quote", "fixture_text", "question_id", "raw_prompt", "raw_response", "request_id", "session_id", "slot_id"}


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
