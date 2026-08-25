from __future__ import annotations

import json
import re
from copy import deepcopy

import pytest

from hbqrs.paths import book_root


ROOT = book_root() / "evaluation-results" / "hbq-poetry-free-verse-repetition-four-state-applicability-treatment-v1-execution-v2-public-result-v1"
RESULT = ROOT / "public-result.json"

EXPECTED = {
    "format_version": 1,
    "study_id": "hbq-poetry-free-verse-repetition-four-state-applicability-treatment-v1-execution-v2",
    "source_bindings": {
        "execution_claim_sha256": "af6032f1a84398f23216ae7b16c78c8fe5c60a95dedc61d677b3a0ad9a552141",
        "study_manifest_sha256": "8d12ecfeb06fbd2424790f0a847074ceb15f4efdfbec00d1b99db6998a66367a",
        "preexecution_disclosure_sha256": "9b5345c101cf3d7ab69ea470a34598ee9c8c52838eb573d67820e86635499fee",
        "prompt_privacy_receipt_sha256": "e31fec72dd10554a5413c1a8d8e0077c8ead9d8aced07ea2001ceab578b0088a",
        "zero_charge_acknowledgement_sha256": "db2d4afb64767a334307cfb8d52301b00741e684305b241dadef57ecb02e1fce",
    },
    "execution": {
        "planned_contacts": 12,
        "accepted_contacts": 12,
        "unique_contacts": 12,
        "first_attempt_contacts": 12,
        "retries": 0,
        "rejections": 0,
        "normalization_events": 0,
    },
    "semantic_oracle_agreement": {
        "matched": 12,
        "total": 12,
        "cells": {
            "NOT_APPLICABLE": {"matched": 3, "total": 3},
            "NO": {"matched": 3, "total": 3},
            "YES": {"matched": 3, "total": 3},
            "CANNOT_ASSESS": {"matched": 3, "total": 3},
        },
    },
    "strict_evidence_gate": {
        "matched": 10,
        "total": 12,
        "summary_items": 2,
        "reason": "generic_prompt_allowed_summary_but_frozen_study_required_verbatim_evidence",
    },
    "formal_result": "NO_RESULT",
    "postexecution_artifacts": {
        "settlement": "not_written",
        "aggregate": "not_written",
        "terminal_result": "not_written",
    },
    "promotion": "none",
    "holdout": "not_authorized",
    "dspy": "not_authorized",
}


def read_result() -> dict:
    return json.loads(RESULT.read_text(encoding="utf-8"))


def assert_public_projection(value: dict) -> None:
    if value != EXPECTED:
        raise ValueError("public no-result projection drifted")
    for commitment in value["source_bindings"].values():
        if not isinstance(commitment, str) or not re.fullmatch(r"[0-9a-f]{64}", commitment):
            raise ValueError("invalid source commitment")
    public_text = "\n".join(path.read_text(encoding="utf-8") for path in ROOT.iterdir() if path.is_file())
    forbidden = ("C:\\Users\\", "session_id", "slot_id", "exact_quote", "artifact_text", "provider_artifacts")
    if any(marker in public_text for marker in forbidden):
        raise ValueError("private material in public package")


def test_public_no_result_is_exact_and_aggregate_only() -> None:
    assert_public_projection(read_result())


@pytest.mark.parametrize(
    "mutate",
    (
        lambda value: value["semantic_oracle_agreement"].update({"matched": 11}),
        lambda value: value["strict_evidence_gate"].update({"matched": 12}),
        lambda value: value["source_bindings"].update({"execution_claim_sha256": "0" * 64}),
        lambda value: value.update({"formal_result": "HOLDOUT_ELIGIBLE_ON_SUCCESS"}),
        lambda value: value.update({"private_path": "C:/private"}),
    ),
)
def test_public_no_result_tampering_is_rejected(mutate) -> None:
    altered = deepcopy(read_result())
    mutate(altered)
    with pytest.raises(ValueError):
        assert_public_projection(altered)
