from __future__ import annotations

import json
import re
from copy import deepcopy

import pytest

from hbqrs.paths import book_root


ROOT = book_root() / "evaluation-results" / "hbq-figurative-dspy-boundary-search-successor-v1-public-result-v1"
RESULT = ROOT / "public-result.json"

EXPECTED = {
    "format_version": 1,
    "study_id": "hbq-figurative-dspy-boundary-search-successor-v1",
    "source_bindings": {
        "execution_claim_sha256": "98938ee86b54c3fef637c751d7b06e7eedd90822ccbec8c8a984621c7907fcc5",
        "sealed_result_sha256": "ad8c89f508c5aae183f99968b8d973e77b04ae667bf93f1dcba8c37f918c3075",
        "aggregate_publication_go_review_sha256": "f88345e09d63438fe9bd4d3ecf2d25f195aa0cd687b7b5d57a422f66f3fef118",
        "dry_run_sha256": "f1385a8041d09643c70ce01b7c58090a4af6049e7d12fe402020a7e58fba5976",
    },
    "execution": {
        "planned_contacts": 72,
        "accepted_first_attempt_contacts": 72,
        "unique_sessions": 72,
        "source_exact_evidence_contacts": 72,
        "retries": 0,
        "rejections": 0,
        "normalization_events": 0,
    },
    "train": {
        "D": {"matched": 9, "total": 12},
        "C": {"matched": 8, "total": 12},
        "A": {"matched": 7, "total": 12},
        "B": {"matched": 7, "total": 12},
        "selected": ["D", "C"],
    },
    "dev": {
        "D": {"matched": 8, "total": 12},
        "C": {"matched": 8, "total": 12},
        "positive_expectations": {"matched": 8, "total": 8},
        "negative_expectations": {"matched": 0, "total": 4},
        "repeat_stable_cells": {"matched": 6, "total": 6},
        "verdict_pattern": "all_yes",
    },
    "decisions": [
        "GO_AGGREGATE_ONLY_PUBLICATION",
        "NO_GO_STATIC_CANDIDATE_ADVANCEMENT",
        "NO_GO_FRESH_18_CALL_CONTROL_FIRST_CONFIRMATION",
        "PROMOTION_NONE",
    ],
    "next_treatment": "artifact_grounded_hinge_beyond_conjunction_and_opposing_implications",
    "dspy": "development_only_not_runtime",
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
    forbidden = ("C:\\Users\\", "session_id", "slot_id", "case_id", "exact_quote", "artifact_text", "provider_artifacts")
    if any(marker in public_text for marker in forbidden):
        raise ValueError("private material in public package")


def test_public_result_is_exact_aggregate_only_and_bound_to_reviews() -> None:
    assert_public_projection(read_result())


@pytest.mark.parametrize(
    "mutate",
    (
        lambda value: value["train"]["D"].update({"matched": 12}),
        lambda value: value["dev"]["negative_expectations"].update({"matched": 4}),
        lambda value: value["source_bindings"].update({"sealed_result_sha256": "0" * 64}),
        lambda value: value["decisions"].remove("NO_GO_STATIC_CANDIDATE_ADVANCEMENT"),
        lambda value: value.update({"private_path": "C:/private"}),
    ),
)
def test_public_result_tampering_is_rejected(mutate) -> None:
    altered = deepcopy(read_result())
    mutate(altered)
    with pytest.raises(ValueError):
        assert_public_projection(altered)
