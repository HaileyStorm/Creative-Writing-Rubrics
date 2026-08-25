from __future__ import annotations

import json
import re
from copy import deepcopy

import pytest

from hbqrs.paths import book_root


ROOT = book_root() / "evaluation-results" / "hbq-poetry-free-verse-repetition-incidental-determiner-holdout-v2-execution-v2-public-result-v1"
RESULT = ROOT / "public-result.json"

EXPECTED = {
    "format_version": 1,
    "study_id": "hbq-poetry-free-verse-repetition-incidental-determiner-holdout-v2-execution-v2",
    "source_bindings": {
        "execution_claim_sha256": "6fa97bc0cde28b57552f3ef62dbe20a37e1b77574daf21f63a17377f8efcee9b",
        "independent_driver_review_sha256": "858300ff7156e2d0438ae737c6b8082a7a11d0dc7e0c0ad6ca7b63817093d26f",
        "settlement_sha256": "798d102551e37312f36ebe947b1c27ea0d0edb2ea8b839dcb6ca2973dd9bee45",
        "v1_terminal_sha256": "b711e9557d7e4a763d0600626a7089de332e2760af12f513ab68db37af5eeecc",
        "v3_terminal_sha256": "d3bc263ddd7f9c1df624b6b627803b96f2e19412944d5e4d1c0af63397f67ea9",
    },
    "route": {"provider": "openai", "model": "gpt-5.6-sol", "reasoning": "high"},
    "public_synthetic_geometry": {
        "independent_carriers": 1,
        "repetitions_per_carrier": 3,
        "planned_contacts": 3,
        "continuity": "same_carrier_context_and_candidate_as_v1",
    },
    "attempt_accounting": {
        "accepted_first_attempt_contacts": 3,
        "retries": 0,
        "rejections": 0,
        "normalization_events": 0,
        "grounded_source_evidence": 3,
    },
    "raw_state_agreement": {"expected": "NO", "observed": {"NO": 3}, "matched": 3, "total": 3},
    "settlement_decision": "HOLDOUT_ELIGIBLE_ON_SUCCESS",
    "promotion": "none_pending_final_review",
    "combined_practical_matrix": {
        "clear_carriers": 4,
        "matched": 12,
        "total": 12,
        "state_counts": {"CANNOT_ASSESS": 3, "NOT_APPLICABLE": 3, "NO": 3, "YES": 3},
        "ambiguous_coordinate_carrier": "non_voting_lineage",
    },
}


def read_result() -> dict:
    return json.loads(RESULT.read_text(encoding="utf-8"))


def assert_public_projection(value: dict) -> None:
    if value != EXPECTED:
        raise ValueError("public S1 incidental-recurrence result projection drifted")
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
        "v2-3d1a",
        "v2-7fe4",
        "v2-c928",
    )
    if any(marker in public_text for marker in forbidden):
        raise ValueError("private material in public package")


def test_public_result_is_exact_aggregate_only() -> None:
    assert_public_projection(read_result())


@pytest.mark.parametrize(
    "mutate",
    (
        lambda value: value["attempt_accounting"].update({"accepted_first_attempt_contacts": 2}),
        lambda value: value["raw_state_agreement"].update({"matched": 2}),
        lambda value: value["raw_state_agreement"]["observed"].update({"YES": 1}),
        lambda value: value.update({"settlement_decision": "FORMAL_PASS"}),
        lambda value: value.update({"promotion": "eligible"}),
        lambda value: value["combined_practical_matrix"].update({"matched": 11}),
        lambda value: value.update({"private_path": "C:/private"}),
    ),
)
def test_public_result_tampering_is_rejected(mutate) -> None:
    altered = deepcopy(read_result())
    mutate(altered)
    with pytest.raises(ValueError):
        assert_public_projection(altered)
