from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
AGGREGATE = ROOT / "aggregate.v1.json"
ALLOWED_FILES = {"README.md", "aggregate.v1.json", "verify_output.py"}
IGNORED_GENERATED_DIRECTORIES = {"__pycache__"}
FORBIDDEN_FIELD_NAMES = {
    "absolute_path",
    "exact_quote",
    "fixture_text",
    "question_id",
    "raw_prompt",
    "raw_response",
    "request_id",
    "response_id",
    "session_id",
    "slot_id",
}
EXPECTED = {
    "archived_validation": {
        "accepted_receipt_chains": {"total": 60, "v2": 30, "v3": 20, "v5": 10},
        "valid_evidence_normalizations": {"total": 170, "v5": 10},
    },
    "decision": "MIXED_DISCRIMINATION_STRONG_CONTROL_SEPARATION_LIMITED_AUTHOR_REWRITE_SIGNAL",
    "excluded_incomplete_pass": {"artifact": "public_control_story", "repetition": 2},
    "format_version": 1,
    "opaque_execution_commitments": {
        "private_settlement_v1_sha256": "80d3e7af8eaa75a05157eb40d706f7238e0dc44f741cafc53ebcc2e35aba765a",
        "private_settlement_v2_sha256": "6e4f1654b4d5493eeb3a99fcebd4b110fe68790a9011440784551e94e151b74e",
        "settler_v2_sha256": "ebaeb7a9ce6c8ac016e0880618fe728e01436439750fe8c4e1e35d546dc1b7d5",
    },
    "protocol_geometry": {"accepted_new_calls": 10, "complete_passes": 6, "inherited_complete_calls": 50, "verdict_positions": 1326},
    "source_head": "4ce1204d8dd97feff2c7bd88237e265fac742adb",
    "study_id": "hbq-qpc24-two-pass-product-confirmation-v5",
}
EXPECTED_COUNTS = [
    {"artifact": "author_original", "repetition": 4, "verdict_counts": {"CANNOT_ASSESS": 14, "NO": 50, "NOT_APPLICABLE": 9, "YES": 148}},
    {"artifact": "author_original", "repetition": 5, "verdict_counts": {"CANNOT_ASSESS": 9, "NO": 48, "NOT_APPLICABLE": 16, "YES": 148}},
    {"artifact": "gpt_5_6_pro_rewrite", "repetition": 1, "verdict_counts": {"CANNOT_ASSESS": 4, "NO": 54, "NOT_APPLICABLE": 16, "YES": 147}},
    {"artifact": "gpt_5_6_pro_rewrite", "repetition": 3, "verdict_counts": {"CANNOT_ASSESS": 14, "NO": 49, "NOT_APPLICABLE": 13, "YES": 145}},
    {"artifact": "public_control_story", "repetition": 1, "verdict_counts": {"CANNOT_ASSESS": 7, "NO": 6, "NOT_APPLICABLE": 16, "YES": 192}},
    {"artifact": "public_control_story", "repetition": 3, "verdict_counts": {"CANNOT_ASSESS": 3, "NO": 3, "NOT_APPLICABLE": 16, "YES": 199}},
]
EXPECTED_WITHIN = {
    "author_original": {"different": 14, "same": 207},
    "gpt_5_6_pro_rewrite": {"different": 21, "same": 200},
    "public_control_story": {"different": 7, "same": 214},
}
EXPECTED_REPRESENTATIVE = {
    "author_original_vs_gpt_5_6_pro_rewrite": {"different": 28, "no_left_only": 7, "no_right_only": 11, "same": 193},
    "author_original_vs_public_control_story": {"different": 63, "no_left_only": 46, "no_right_only": 2, "same": 158},
    "gpt_5_6_pro_rewrite_vs_public_control_story": {"different": 57, "no_left_only": 50, "no_right_only": 2, "same": 164},
}
EXPECTED_STABLE = {
    "author_original_vs_gpt_5_6_pro_rewrite": {"common_stable_leaves": 189, "different": 4, "no_left_only": 3, "no_right_only": 0},
    "author_original_vs_public_control_story": {"common_stable_leaves": 200, "different": 48, "no_left_only": 41, "no_right_only": 1},
    "gpt_5_6_pro_rewrite_vs_public_control_story": {"common_stable_leaves": 195, "different": 43, "no_left_only": 41, "no_right_only": 1},
}


def _read() -> dict[str, Any]:
    value = json.loads(AGGREGATE.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Aggregate result must be an object")
    return value


def _walk(value: Any) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if key.lower() in FORBIDDEN_FIELD_NAMES:
                raise ValueError(f"Restricted public field: {key}")
            _walk(item)
    elif isinstance(value, list):
        for item in value:
            _walk(item)


def verify() -> dict[str, Any]:
    value = _read()
    expected_keys = {*EXPECTED, "complete_pass_state_counts", "within_artifact_two_pass_agreement", "representative_pass_cross_artifact_differences", "stable_two_pass_cross_artifact_differences"}
    if set(value) != expected_keys:
        raise ValueError("Aggregate result contains an unexpected field")
    if {key: value.get(key) for key in EXPECTED} != EXPECTED:
        raise ValueError("Aggregate identity drifted")
    if value.get("complete_pass_state_counts") != EXPECTED_COUNTS:
        raise ValueError("Aggregate counts drifted")
    if value.get("within_artifact_two_pass_agreement") != EXPECTED_WITHIN:
        raise ValueError("Within-artifact agreement drifted")
    if value.get("representative_pass_cross_artifact_differences") != EXPECTED_REPRESENTATIVE:
        raise ValueError("Representative-pass difference drifted")
    if value.get("stable_two_pass_cross_artifact_differences") != EXPECTED_STABLE:
        raise ValueError("Stable two-pass difference drifted")
    if sum(sum(row["verdict_counts"].values()) for row in EXPECTED_COUNTS) != value["protocol_geometry"]["verdict_positions"]:
        raise ValueError("Aggregate arithmetic drifted")
    if any(not isinstance(item, str) or not re.fullmatch(r"[0-9a-f]{64}", item) for item in value["opaque_execution_commitments"].values()):
        raise ValueError("Opaque commitment is malformed")
    _walk(value)
    files = {path.name for path in ROOT.iterdir() if path.is_file()}
    directories = {path.name for path in ROOT.iterdir() if path.is_dir()}
    if files != ALLOWED_FILES or directories - IGNORED_GENERATED_DIRECTORIES:
        raise ValueError("Aggregate package surface drifted")
    text = "\n".join((ROOT / name).read_text(encoding="utf-8") for name in {"README.md", "aggregate.v1.json"})
    if "C:\\Users\\" in text or "exact_quote" in text or "raw_response" in text:
        raise ValueError("Public package text exposes a private transport field")
    return value


if __name__ == "__main__":
    print(json.dumps(verify(), sort_keys=True))
