from __future__ import annotations

import json
import re
from copy import deepcopy

import pytest

from hbqrs.paths import book_root


ROOT = book_root() / "evaluation-results" / "hbq-poetry-free-verse-repetition-four-state-disjoint-holdout-v2-execution-v3-public-result-v1"
RESULT = ROOT / "public-result.json"

EXPECTED = {
    "format_version": 1,
    "study_id": "hbq-poetry-free-verse-repetition-four-state-disjoint-holdout-v2-execution-v3",
    "source_bindings": {
        "execution_claim_sha256": "3a4352084c7b8b40b5f73b64b474c963399852a11e81fc800253cd1653f89500",
        "independent_driver_review_sha256": "8fc6fc4c8f44bf175425d7b43c7b9a162109e97a6b36f778fe1b7204a92dd0d7",
        "execution_terminal_sha256": "d3bc263ddd7f9c1df624b6b627803b96f2e19412944d5e4d1c0af63397f67ea9",
    },
    "route": {"provider": "openai", "model": "gpt-5.6-sol", "reasoning": "high"},
    "public_synthetic_geometry": {"independent_carriers": 4, "repetitions_per_carrier": 3, "planned_contacts": 12},
    "attempt_accounting": {
        "accepted_first_attempt_contacts": 12,
        "retries": 0,
        "rejections": 0,
        "normalization_events": 0,
        "grounded_source_evidence": 12,
    },
    "expected_state_agreement": {
        "matched": 10,
        "total": 12,
        "by_expected_state": {
            "CANNOT_ASSESS": {"matched": 3, "total": 3},
            "NOT_APPLICABLE": {"matched": 3, "total": 3},
            "YES": {"matched": 3, "total": 3},
            "NO": {"matched": 1, "total": 3, "observed": {"NO": 1, "YES": 2}},
        },
    },
    "repeat_stability": {"stable_carriers": 3, "total_carriers": 4},
    "terminal_disposition": "INVALID_POSTCONTACT_NO_RETRY",
    "settlement": "not_authorized",
    "retry_or_resume": "not_authorized",
    "promotion": "none",
    "dspy": "not_authorized",
}


def read_result() -> dict:
    return json.loads(RESULT.read_text(encoding="utf-8"))


def assert_public_projection(value: dict) -> None:
    if value != EXPECTED:
        raise ValueError("public S1-v3 result projection drifted")
    for commitment in value["source_bindings"].values():
        if not isinstance(commitment, str) or not re.fullmatch(r"[0-9a-f]{64}", commitment):
            raise ValueError("invalid source commitment")
    public_text = "\n".join(path.read_text(encoding="utf-8") for path in ROOT.iterdir() if path.is_file())
    forbidden = (
        "C:\\Users\\",
        "case_id",
        "slot_id",
        "artifact_id",
        "artifact_text",
        "prompt",
        "response",
        "session",
        "exact_quote",
        "u-8c13",
        "s1v-",
    )
    if any(marker in public_text for marker in forbidden):
        raise ValueError("private material in public package")


def test_public_result_is_exact_aggregate_only() -> None:
    assert_public_projection(read_result())


@pytest.mark.parametrize(
    "mutate",
    (
        lambda value: value["attempt_accounting"].update({"accepted_first_attempt_contacts": 11}),
        lambda value: value["expected_state_agreement"].update({"matched": 12}),
        lambda value: value["expected_state_agreement"]["by_expected_state"]["NO"].update({"matched": 3}),
        lambda value: value["repeat_stability"].update({"stable_carriers": 4}),
        lambda value: value.update({"terminal_disposition": "FORMAL_PASS"}),
        lambda value: value.update({"settlement": "completed"}),
        lambda value: value.update({"promotion": "eligible"}),
        lambda value: value.update({"private_path": "C:/private"}),
    ),
)
def test_public_result_tampering_is_rejected(mutate) -> None:
    altered = deepcopy(read_result())
    mutate(altered)
    with pytest.raises(ValueError):
        assert_public_projection(altered)
