from __future__ import annotations

import json
import re
from copy import deepcopy
import pytest

from hbqrs.paths import book_root


ROOT = book_root() / "evaluation-results" / "hbq-nonpoetry-scope-semantic-boundary-successor-v1-public-result-v1"
RESULT = ROOT / "public-result.json"

EXPECTED = {
    "format_version": 1,
    "study_id": "hbq-nonpoetry-scope-semantic-boundary-successor-v1",
    "source_bindings": {
        "execution_claim_sha256": "e80a6f5d14a8fbb2471d96c7a70afb194820cecaea3927f3d0fa7e8dff91a025",
        "terminal_sidecar_sha256": "2f9fc34080725cd3f44e7de74e15d314bb5f9cabe0d3fcac61ab5c0546a0386d",
        "settlement_sha256": "d979d194d9f5b67e2c18e0827625f797abee5c38fe6b6e2409eb50a5fd36b0a1",
    },
    "execution": {
        "planned_slots": 6,
        "completed_slots": 6,
        "accepted_provider_calls": 6,
        "batch_attempts_per_slot": 1,
        "post_response_retries": 0,
    },
    "aggregate_cells": {
        "visible_whole_work_penalty": {"expected": "NO", "matched": 2, "total": 2},
        "supplied_evaluation_without_completeness_penalty": {"expected": "YES", "matched": 2, "total": 2},
        "no_evaluation_record": {"expected": "CANNOT_ASSESS", "matched": 2, "total": 2},
    },
    "decision": "FRESH_DISJOINT_CONFIRMATION_REVIEW_ELIGIBLE",
    "promotion": "none",
    "next_step": "independent_review_then_fresh_disjoint_confirmation_only",
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
        lambda value: value["aggregate_cells"]["no_evaluation_record"].update({"matched": 1}),
        lambda value: value["source_bindings"].update({"terminal_sidecar_sha256": "0" * 64}),
        lambda value: value.update({"promotion": "wording_change"}),
        lambda value: value.update({"private_path": "C:/private"}),
    ),
)
def test_public_result_tampering_is_rejected(mutate) -> None:
    altered = deepcopy(read_result())
    mutate(altered)
    with pytest.raises(ValueError):
        assert_public_projection(altered)
