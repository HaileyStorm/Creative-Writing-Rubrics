from __future__ import annotations

import json
import re
from copy import deepcopy

import pytest

from hbqrs.paths import book_root


ROOT = book_root() / "evaluation-results" / "hbq-figurative-hinge-treatment-successor-v5-public-result-v1"
RESULT = ROOT / "public-result.json"

EXPECTED = {
    "format_version": 1,
    "study_id": "hbq-figurative-hinge-treatment-successor-v5",
    "source_bindings": {
        "execution_claim_sha256": "3757ca2a4e30a37e932586816ed533ba336db0ed5abd2c39549e6d14c58ade8d",
        "execution_result_sha256": "090f4ee025db2833b73a9c2bbd7702b5b0a0f39dba9c50a2a674218fd36350b5",
        "preexecution_go_review_sha256": "ccccade1dfd1987cd2b6367df24c5b875e1a4251637a9d6d89239aac38237f19",
    },
    "public_synthetic_geometry": {
        "case_ids": ["f1", "g2", "h3", "j4"],
        "cases": 4,
        "repetitions_per_case": 2,
        "planned_contacts": 8,
        "accepted_first_attempt_contacts": 8,
        "retries": 0,
        "rejections": 0,
    },
    "exact_expected_state": {
        "matched": 7,
        "total": 8,
        "by_case": {
            "f1": {"matched": 2, "total": 2},
            "g2": {"matched": 2, "total": 2},
            "h3": {"matched": 2, "total": 2},
            "j4": {"matched": 1, "total": 2},
        },
    },
    "repeat_stability": {"stable_cases": 3, "total_cases": 4},
    "decisions": [
        "MANUAL_HINGE_TREATMENT_POSITIVE_SIGNAL_BUT_UNSTABLE_NO_GO",
        "PROMOTION_NONE",
        "FRESH_18_CALL_CONFIRMATION_CLOSED",
    ],
}


def read_result() -> dict:
    return json.loads(RESULT.read_text(encoding="utf-8"))


def assert_public_projection(value: dict) -> None:
    if value != EXPECTED:
        raise ValueError("public aggregate projection drifted")
    for commitment in value["source_bindings"].values():
        if not isinstance(commitment, str) or not re.fullmatch(r"[0-9a-f]{64}", commitment):
            raise ValueError("invalid source commitment")
    public_text = "\n".join(path.read_text(encoding="utf-8") for path in ROOT.iterdir() if path.is_file())
    forbidden = (
        "C:\\Users\\",
        "session_id",
        "slot_id",
        "exact_quote",
        "artifact_text",
        "checkpoint",
        "ledger",
        "prompt.txt",
        "response",
        "run.json",
    )
    if any(marker in public_text for marker in forbidden):
        raise ValueError("non-aggregate material in public package")


def test_public_result_is_exact_aggregate_only_and_hash_bound() -> None:
    assert_public_projection(read_result())


@pytest.mark.parametrize(
    "mutate",
    (
        lambda value: value["exact_expected_state"].update({"matched": 8}),
        lambda value: value["exact_expected_state"]["by_case"]["j4"].update({"matched": 2}),
        lambda value: value["source_bindings"].update({"execution_result_sha256": "0" * 64}),
        lambda value: value["decisions"].remove("PROMOTION_NONE"),
        lambda value: value.update({"private_path": "C:/private"}),
    ),
)
def test_public_result_tampering_is_rejected(mutate) -> None:
    altered = deepcopy(read_result())
    mutate(altered)
    with pytest.raises(ValueError):
        assert_public_projection(altered)
