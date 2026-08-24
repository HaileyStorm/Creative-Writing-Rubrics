from __future__ import annotations

import json
from copy import deepcopy

import pytest

from hbqrs.paths import book_root

ROOT = book_root() / "evaluation-results" / "hbq-nonpoetry-scope-disjoint-holdout-v1-execution-v1-public-result-v1"
RESULT = ROOT / "public-result.json"


EXPECTED = {
    "format_version": 1,
    "study_id": "hbq-nonpoetry-scope-disjoint-holdout-v1-execution-v1",
    "source_bindings": {
        "execution_claim_sha256": "40dba65881591d8d6e9453225a705c0d86cdd459e59cb23a831d8af9fa2d916a",
        "settlement_sha256": "4ea1cf86d985eb0768fc773fa4fabd8f618b41a43c3f115ebb696ca81b279ec8",
        "public_aggregate_sha256": "41706feb7c9dae20addb7e77bd450b4f540b194730aba338be9799c801bd18f3",
    },
    "execution": {
        "planned_slots": 48,
        "completed_slots": 48,
        "accepted_provider_calls": 48,
        "batch_attempts_per_slot": 1,
        "post_response_retries": 0,
    },
    "aggregate_cells": {
        "total_per_arm": 8,
        "baseline_passed": 5,
        "candidate_passed": 6,
        "control_cells_per_arm": 4,
        "baseline_controls_correct": 4,
        "candidate_controls_correct": 4,
        "candidate_all_eight_cells_3_of_3": False,
    },
    "target_states": {
        "material_failure": {"baseline_passed": 0, "candidate_passed": 2, "total": 2, "improved": True},
        "missing_required_evidence": {
            "baseline_passed": 1,
            "candidate_passed": 0,
            "total": 2,
            "improved": False,
            "interpretation": "semantic_oracle_dispute_silent_disposition_yes_vs_cannot_assess",
        },
        "improved_count": 1,
    },
    "decision": "NO_GO",
    "promotion": "none",
    "dspy": "not_used",
}


def read_result() -> dict:
    return json.loads(RESULT.read_text(encoding="utf-8"))


def assert_public_projection(value: dict) -> None:
    if value != EXPECTED:
        raise ValueError("public aggregate projection drifted")
    for commitment in value["source_bindings"].values():
        if not isinstance(commitment, str) or len(commitment) != 64:
            raise ValueError("invalid source commitment")
    public_text = "\n".join(path.read_text(encoding="utf-8") for path in ROOT.iterdir() if path.is_file())
    forbidden = ("C:\\Users\\", "s2dh-", "session_id", "logical_sample", "fixture_commitment", "exact_quote")
    if any(marker in public_text for marker in forbidden):
        raise ValueError("private identifier in public package")


def test_public_result_has_exact_aggregate_and_source_commitments() -> None:
    value = read_result()
    assert_public_projection(value)
    assert value["target_states"]["material_failure"] == {
        "baseline_passed": 0,
        "candidate_passed": 2,
        "total": 2,
        "improved": True,
    }
    assert value["target_states"]["missing_required_evidence"]["interpretation"] == (
        "semantic_oracle_dispute_silent_disposition_yes_vs_cannot_assess"
    )


@pytest.mark.parametrize(
    "mutate",
    (
        lambda value: value["aggregate_cells"].update({"candidate_passed": 8}),
        lambda value: value["target_states"]["material_failure"].update({"candidate_passed": 1}),
        lambda value: value["source_bindings"].update({"settlement_sha256": "0" * 64}),
        lambda value: value.update({"decision": "PROMOTION_REVIEW_ELIGIBLE"}),
        lambda value: value.update({"private_path": "C:/private"}),
    ),
)
def test_public_result_tampering_is_rejected(mutate) -> None:
    altered = deepcopy(read_result())
    mutate(altered)
    with pytest.raises(ValueError):
        assert_public_projection(altered)
