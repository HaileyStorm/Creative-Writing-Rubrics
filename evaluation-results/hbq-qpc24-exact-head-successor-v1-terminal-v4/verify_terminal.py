from __future__ import annotations

import json
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent
TERMINAL = HERE / "qpc24-public-terminal-v4-aggregate.json"
EXPECTED = {
    "format_version": 1,
    "study_id": "hbq-qpc24-exact-head-successor-v1",
    "classification": "NO_RESULT_POSTCONTACT_EVIDENCE_VALIDATION_FAILURE",
    "cause": "FROZEN_EVIDENCE_POLICY_MISMATCH",
    "planned_provider_calls": 150,
    "contacted_provider_calls": 1,
    "structured_response_count": 1,
    "accepted_provider_calls": 0,
    "voting_provider_calls": 0,
    "untouched_provider_calls": 149,
}
FORBIDDEN = {"question_id", "state", "states", "source", "path", "session", "quote", "prose"}


def _read() -> dict[str, Any]:
    value = json.loads(TERMINAL.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Public QPC24 terminal projection must be an object")
    return value


def verify() -> dict[str, Any]:
    value = _read()
    if {key: value.get(key) for key in EXPECTED} != EXPECTED:
        raise ValueError("Public QPC24 terminal aggregate drift")
    commitment = value.get("opaque_private_receipt_commitment_sha256")
    if not isinstance(commitment, str) or len(commitment) != 64 or any(char not in "0123456789abcdef" for char in commitment):
        raise ValueError("Public QPC24 terminal receipt commitment drift")
    if set(value) != {*EXPECTED, "opaque_private_receipt_commitment_sha256"}:
        raise ValueError("Public QPC24 terminal projection contains extra detail")
    if any(token in key.lower() for key in value for token in FORBIDDEN):
        raise ValueError("Public QPC24 terminal projection exposes private detail")
    return value


if __name__ == "__main__":
    print(json.dumps(verify(), sort_keys=True))
