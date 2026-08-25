from __future__ import annotations

import json
import re
from copy import deepcopy

import pytest

from hbqrs.paths import book_root


ROOT = book_root() / "evaluation-results" / "hbq-figurative-hinge-treatment-successor-v7-public-result-v1"
RESULT = ROOT / "public-result.json"

EXPECTED = {
    "format_version": 1,
    "study_id": "hbq-figurative-hinge-treatment-successor-v7",
    "source_bindings": {
        "execution_claim_sha256": "cecaba9458bb87e92e643563374eb047937a4524e02fb77dffe916eee2db9d48",
        "execution_result_sha256": "17f875ba22be96b95331da537a41c9dd1cc7948c4d0b76a3360670042b2f8bec",
        "preexecution_go_review_sha256": "b0f72d2510cdb428311b5d8aafebcd4582236a468fad36652b4cbec9cdb7905b",
        "dry_manifest_sha256": "d6a62d5140873774fc76632890fde49cfc12fb40a6010e26b370785e43f2f153",
    },
    "public_synthetic_geometry": {
        "case_ids": ["n1", "o2", "p3"],
        "cases": 3,
        "repetitions_per_case": 2,
        "planned_contacts": 6,
        "receipt_proven_first_attempt_contacts": 6,
        "exact_expected_state": {"matched": 6, "total": 6},
        "by_case": {
            "n1": {"matched": 2, "total": 2},
            "o2": {"matched": 2, "total": 2},
            "p3": {"matched": 2, "total": 2},
        },
        "retries": 0,
        "rejections": 0,
    },
    "stdout_reporting_defect": {
        "hardcoded_reported_contacts": 8,
        "receipt_proven_contacts": 6,
        "effect": "reporting_only_no_rerun",
    },
    "decisions": [
        "HINGE_TREATMENT_V7_SMALL_DIAGNOSTIC_PASS",
        "FRESH_18_CALL_CONTROL_FIRST_CONFIRMATION_ONLY",
        "PROMOTION_NONE",
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
        lambda value: value["public_synthetic_geometry"].update({"receipt_proven_first_attempt_contacts": 8}),
        lambda value: value["public_synthetic_geometry"]["by_case"]["p3"].update({"matched": 1}),
        lambda value: value["stdout_reporting_defect"].update({"effect": "rerun"}),
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
