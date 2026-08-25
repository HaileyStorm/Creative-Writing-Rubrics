from __future__ import annotations

import json
import re
from copy import deepcopy

import pytest

from hbqrs.paths import book_root


ROOT = book_root() / "evaluation-results" / "hbq-poetry-free-verse-repetition-four-state-applicability-treatment-v1-execution-v6-public-result-v1"
RESULT = ROOT / "public-result.json"

EXPECTED = {
    "format_version": 1,
    "study_id": "hbq-poetry-free-verse-repetition-four-state-applicability-treatment-v1-execution-v6",
    "source_bindings": {
        "execution_claim_sha256": "49da5ba992f721cffb3ae48cd04f7775d920f79067d55547f1c8cec646064efa",
        "study_manifest_sha256": "250d93ac833c7b32b39187db19d2576eee7145416e36816b5e5b68a61369f79c",
        "dispatch_failure_receipt_sha256": "15b06ca8e307db9c204d67fc4704ff7841f99d072af23922084eb69f5c033804",
        "rejected_attempt_receipt_sha256": "8202c905268c5829b92319bc3df0477dca429e5635b647396d264897ed40cc69",
        "zero_charge_acknowledgement_sha256": "a294c8775a49c91e8c51c92981de85e832d865cfa66f469d2dd9e2ba2806d02d",
    },
    "attempt_accounting": {
        "claimed_one_shot_root": True,
        "zero_charge_acknowledgements": 1,
        "dispatches": 1,
        "runs": 1,
        "physical_provider_attempts": 1,
        "provider_contacted": True,
        "rejected_provider_retryable_failures": 1,
        "http_status": 400,
        "raw_content_bytes": 0,
        "accepted_checkpoints": 0,
        "accepted_verdicts": 0,
        "settlements": 0,
        "terminal_results": 0,
        "untouched_slots": 11,
    },
    "failure": {
        "kind": "invalid_json_schema",
        "response_schema_defect": "missing_type_for_evidence_kind_const_and_verdict_enum",
    },
    "formal_result": "NO_RESULT",
    "inference": "none_completion_unproven",
    "wording_or_fixture_failure": "not_established",
    "dspy": "not_authorized",
    "holdout": "not_authorized",
    "promotion": "none",
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


def test_public_transport_failure_is_exact_aggregate_only_and_not_evaluation_evidence() -> None:
    assert_public_projection(read_result())


@pytest.mark.parametrize(
    "mutate",
    (
        lambda value: value["attempt_accounting"].update({"accepted_verdicts": 1}),
        lambda value: value["attempt_accounting"].update({"untouched_slots": 0}),
        lambda value: value["source_bindings"].update({"rejected_attempt_receipt_sha256": "0" * 64}),
        lambda value: value.update({"formal_result": "NO_GO"}),
        lambda value: value.update({"private_path": "C:/private"}),
    ),
)
def test_public_transport_failure_tampering_is_rejected(mutate) -> None:
    altered = deepcopy(read_result())
    mutate(altered)
    with pytest.raises(ValueError):
        assert_public_projection(altered)
