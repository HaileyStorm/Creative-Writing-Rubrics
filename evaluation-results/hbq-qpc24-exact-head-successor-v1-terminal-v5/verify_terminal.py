from __future__ import annotations

import json
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent
TERMINAL = HERE / "qpc24-public-terminal-v5-aggregate.json"
EXPECTED = {
    "format_version": 1,
    "study_id": "hbq-qpc24-exact-head-successor-v1",
    "classification": "TERMINAL_LOCAL_POST_OUTPUT_LAPTOP_SLEEP_TIMEOUT",
    "cause": "LOCAL_CONTROLLER_TIMEOUT_AFTER_COMPLETE_STRUCTURED_OUTPUT",
    "planned_provider_calls": 150,
    "planned_verdict_positions": 3315,
    "contacted_provider_calls": 13,
    "structured_response_count": 13,
    "structured_verdict_positions": 293,
    "accepted_provider_calls": 12,
    "accepted_verdict_positions": 269,
    "voting_provider_calls": 12,
    "voting_verdict_positions": 269,
    "nonvoting_structured_provider_calls": 1,
    "nonvoting_structured_verdict_positions": 24,
    "untouched_provider_calls": 137,
    "untouched_verdict_positions": 3022,
}
COMMITMENT_KEY = "opaque_private_receipt_tree_commitment_sha256"
FORBIDDEN_DETAIL = {
    "question",
    "leaf",
    "state",
    "source",
    "path",
    "session",
    "quote",
    "prose",
    "slot",
}


def _read() -> dict[str, Any]:
    value = json.loads(TERMINAL.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Public QPC24 terminal projection must be an object")
    return value


def _require_exact_scalar_contract(value: dict[str, Any]) -> None:
    if any(token in key.lower() for key in value if key != COMMITMENT_KEY for token in FORBIDDEN_DETAIL):
        raise ValueError("Public QPC24 terminal projection exposes private detail")
    if set(value) != {*EXPECTED, COMMITMENT_KEY}:
        raise ValueError("Public QPC24 terminal projection contains extra detail")
    if any(isinstance(item, (dict, list)) for item in value.values()):
        raise ValueError("Public QPC24 terminal projection must remain aggregate-only")
    if any(type(value[key]) is not int for key, expected in EXPECTED.items() if type(expected) is int):
        raise ValueError("Public QPC24 terminal counts must be integers")
    if any(type(value[key]) is not str for key, expected in EXPECTED.items() if type(expected) is str):
        raise ValueError("Public QPC24 terminal labels must be strings")


def _verify_arithmetic(value: dict[str, Any]) -> None:
    if value["contacted_provider_calls"] != (
        value["accepted_provider_calls"] + value["nonvoting_structured_provider_calls"]
    ):
        raise ValueError("Contacted provider-call arithmetic drift")
    if value["structured_response_count"] != value["contacted_provider_calls"]:
        raise ValueError("Structured-response arithmetic drift")
    if value["voting_provider_calls"] != value["accepted_provider_calls"]:
        raise ValueError("Voting provider-call arithmetic drift")
    if value["planned_provider_calls"] != (
        value["accepted_provider_calls"]
        + value["nonvoting_structured_provider_calls"]
        + value["untouched_provider_calls"]
    ):
        raise ValueError("Planned provider-call arithmetic drift")
    if value["structured_verdict_positions"] != (
        value["accepted_verdict_positions"] + value["nonvoting_structured_verdict_positions"]
    ):
        raise ValueError("Structured verdict-position arithmetic drift")
    if value["voting_verdict_positions"] != value["accepted_verdict_positions"]:
        raise ValueError("Voting verdict-position arithmetic drift")
    if value["planned_verdict_positions"] != (
        value["accepted_verdict_positions"]
        + value["nonvoting_structured_verdict_positions"]
        + value["untouched_verdict_positions"]
    ):
        raise ValueError("Planned verdict-position arithmetic drift")


def verify() -> dict[str, Any]:
    value = _read()
    _require_exact_scalar_contract(value)
    if {key: value[key] for key in EXPECTED} != EXPECTED:
        raise ValueError("Public QPC24 terminal aggregate drift")
    commitment = value[COMMITMENT_KEY]
    if (
        type(commitment) is not str
        or len(commitment) != 64
        or any(character not in "0123456789abcdef" for character in commitment)
    ):
        raise ValueError("Public QPC24 terminal receipt-tree commitment drift")
    _verify_arithmetic(value)
    return value


if __name__ == "__main__":
    print(json.dumps(verify(), sort_keys=True))
