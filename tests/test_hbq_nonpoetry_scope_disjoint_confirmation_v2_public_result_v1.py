from __future__ import annotations

import json
import re
from copy import deepcopy

import pytest

from hbqrs.paths import book_root


ROOT = book_root() / "evaluation-results" / "hbq-nonpoetry-scope-disjoint-confirmation-v2-public-result-v1"
RESULT = ROOT / "public-result.json"

EXPECTED = {
    "format_version": 1,
    "study_id": "hbq-nonpoetry-scope-disjoint-confirmation-v2",
    "source_bindings": {
        "execution_claim_sha256": "9463b8a5f3fe6e1b60d4095e88060f0495f3f17a079461dd1721923e60a1148f",
        "raw_results_sha256": "ef6dca15ebf641b0225197472a04935c717466ca658f8ac55c6895546d4e441c",
        "terminal_sidecar_sha256": "0910eb2316c1eefadbb8a459bd56b9ed1f92ef80eaa8d567c30672ffd42f0523",
        "settlement_sha256": "d7855d4148395d46f8399ca6e7858ec1976c0064b58cda0368d1ff44e944dc12",
        "runtime_schedule_sha256": "bc4790853b4b2fa0355fcdbed5ca40855903f462a6f9977d9f9606fc4492e9eb",
        "preexecution_disclosure_sha256": "90435707f761c53a17a11956f6aa507e2d0281fdc93fb5dd3df702ebb032207d",
        "zero_charge_acknowledgement_sha256": "867fbf6bc3639cc0af9b6a0cbfa1d129b0d7c472ba2d94eacc1bea000481f82a",
    },
    "execution": {
        "planned_slots": 6,
        "accepted_provider_calls": 6,
        "first_attempt_accepted_calls": 6,
        "unique_sessions": 6,
        "retries": 0,
        "normalization_events": 0,
    },
    "aggregate_cells": {
        "visible_whole_work_penalty": {"expected": "NO", "matched": 2, "total": 2},
        "bounded_complete_evaluation": {"expected": "YES", "matched": 2, "total": 2},
        "absent_evaluation_record": {"expected": "CANNOT_ASSESS", "matched": 2, "total": 2},
    },
    "decision": "INDEPENDENT_WORDING_ONLY_PROMOTION_REVIEW_ELIGIBLE",
    "independent_wording_review": "GO_FOR_EXACT_CANDIDATE",
    "promotion": "none_pending_integration",
    "unchanged_until_integration": [
        "registry wording",
        "leaf identity",
        "criterion ownership",
        "weight",
        "split",
        "prompt",
        "runtime",
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
    forbidden = ("C:\\Users\\", "session_id", "fixture_id", "slot_id", "exact_quote", "artifact_text", "provider_artifacts")
    if any(marker in public_text for marker in forbidden):
        raise ValueError("private material in public package")


def test_public_result_is_exact_aggregate_only_and_bound_to_settlement() -> None:
    assert_public_projection(read_result())


@pytest.mark.parametrize(
    "mutate",
    (
        lambda value: value["aggregate_cells"]["absent_evaluation_record"].update({"matched": 1}),
        lambda value: value["source_bindings"].update({"settlement_sha256": "0" * 64}),
        lambda value: value.update({"independent_wording_review": "NO_GO"}),
        lambda value: value.update({"promotion": "integrated"}),
        lambda value: value.update({"private_path": "C:/private"}),
    ),
)
def test_public_result_tampering_is_rejected(mutate) -> None:
    altered = deepcopy(read_result())
    mutate(altered)
    with pytest.raises(ValueError):
        assert_public_projection(altered)
