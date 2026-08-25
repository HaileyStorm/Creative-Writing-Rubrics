from __future__ import annotations

import json
import re
from copy import deepcopy
import pytest

from hbqrs.paths import book_root


ROOT = book_root() / "evaluation-results" / "hbq-poetry-free-verse-repetition-clean-na-successor-v1-execution-v1-public-result-v1"
RESULT = ROOT / "public-result.json"

EXPECTED = {
    "format_version": 1,
    "study_id": "hbq-poetry-free-verse-repetition-clean-na-successor-v1-execution-v1",
    "source_bindings": {
        "execution_claim_sha256": "c72f94de5461e1bac2d59d716c15846ecbfd3438194ea15ee7118f80bdeec226",
        "settlement_sha256": "6eb6bbb9ecd676076596376210499933f23cabe20555a179afc8d80a706984f4",
        "source_public_aggregate_sha256": "109ef97b15213edf9f57d80374da4a3d43a27c8ec5b0e40bcd6b8e08b3c57d42",
    },
    "execution": {
        "planned_slots": 3,
        "completed_slots": 3,
        "accepted_provider_calls": 3,
        "batch_attempts_per_slot": 1,
        "post_response_retries": 0,
    },
    "aggregate": {
        "expected_verdict": "NOT_APPLICABLE",
        "matched": 0,
        "total": 3,
        "valid_no_verdicts": 3,
    },
    "decision": "NO_GO",
    "promotion": "none",
    "interpretation": "isolated_clean_control_miss_not_broader_wording_falsification",
    "next_step": "no_automatic_follow_on",
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
    forbidden = ("C:\\Users\\", "session_id", "slot_id", "exact_quote", "artifact_text", "provider_artifacts")
    if any(marker in public_text for marker in forbidden):
        raise ValueError("private material in public package")


def test_public_result_is_exact_aggregate_only_and_bound_to_settled_evidence() -> None:
    assert_public_projection(read_result())


@pytest.mark.parametrize(
    "mutate",
    (
        lambda value: value["aggregate"].update({"matched": 3}),
        lambda value: value["source_bindings"].update({"settlement_sha256": "0" * 64}),
        lambda value: value.update({"decision": "HOLDOUT_ELIGIBLE_ON_SUCCESS"}),
        lambda value: value.update({"private_path": "C:/private"}),
    ),
)
def test_public_result_tampering_is_rejected(mutate) -> None:
    altered = deepcopy(read_result())
    mutate(altered)
    with pytest.raises(ValueError):
        assert_public_projection(altered)
