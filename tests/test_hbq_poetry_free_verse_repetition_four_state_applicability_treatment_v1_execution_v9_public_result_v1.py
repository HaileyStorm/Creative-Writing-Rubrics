from __future__ import annotations

import json
import re
from copy import deepcopy

import pytest

from hbqrs.paths import book_root


ROOT = book_root() / "evaluation-results" / "hbq-poetry-free-verse-repetition-four-state-applicability-treatment-v1-execution-v9-public-result-v1"
RESULT = ROOT / "public-result.json"

EXPECTED = {
    "format_version": 1,
    "study_id": "hbq-poetry-free-verse-repetition-four-state-applicability-treatment-v1-execution-v9",
    "source_bindings": {
        "execution_claim_sha256": "166d881ace0a095c7f1b142308697b7e9ae7bfa677e2a4301d6774adb1e7b8a2",
        "study_manifest_sha256": "d778e839822a9ee633f7d097f9e14e7ff0a680e44dee95d0a5c37f08c3db013a",
        "zero_charge_acknowledgement_sha256": "37ac50d2ae5c3a2314b425109ac3fcb354b0b77ff76e1cd654a7ba64aaed53b4",
        "provider_free_dry_run_sha256": "e9f025248c858bac132369d92675785ec0c709f09f1f2f4862ccf60f704e9604",
        "evidence_protocol_scan_sha256": "6e34133f7a57c21afde0a0661035ed79610304f49c543fb408bf3165b7a71fa9",
        "execution_package_study_sha256": "a471e80aaca58d06b70515390ea82953897870070a419ae543c4a95fe45be048",
    },
    "attempt_accounting": {
        "execution_claims": 1,
        "zero_charge_acknowledgements": 1,
        "dispatches": 0,
        "runs": 0,
        "physical_provider_attempts": 0,
        "provider_contacted": False,
        "raw_outputs": 0,
        "accepted_checkpoints": 0,
        "accepted_verdicts": 0,
        "settlements": 0,
        "terminal_results": 0,
        "untouched_slots": 12,
    },
    "failure": {
        "kind": "precontact_render_drift",
        "description": "Frozen surrogate prompts did not byte-match the actual inherited execution renderer.",
        "evidence_status": "reconstructed_from_frozen_materials_and_inherited_renderer",
    },
    "formal_result": "NO_RESULT",
    "disposition": "NO_RESULT_PRECONTACT_RENDER_DRIFT",
    "inference": "none_completion_unproven",
    "wording_or_fixture_failure": "not_established",
    "dspy": "not_authorized",
    "holdout": "not_authorized",
    "promotion": "none",
    "retry_or_resume": "not_authorized",
}


def read_result() -> dict:
    return json.loads(RESULT.read_text(encoding="utf-8"))


def assert_public_projection(value: dict) -> None:
    if value != EXPECTED:
        raise ValueError("public pre-provider no-result projection drifted")
    for commitment in value["source_bindings"].values():
        if not isinstance(commitment, str) or not re.fullmatch(r"[0-9a-f]{64}", commitment):
            raise ValueError("invalid source commitment")
    public_text = "\n".join(path.read_text(encoding="utf-8") for path in ROOT.iterdir() if path.is_file())
    forbidden = (
        "C:\\Users\\",
        "private_root",
        "fixture_id",
        "slot_id",
        "artifact_text",
        "exact_quote",
        "rendered-prompts",
        "q-200000",
    )
    if any(marker in public_text for marker in forbidden):
        raise ValueError("private material in public package")


def test_public_pre_provider_no_result_is_exact_aggregate_only() -> None:
    assert_public_projection(read_result())


@pytest.mark.parametrize(
    "mutate",
    (
        lambda value: value["attempt_accounting"].update({"provider_contacted": True}),
        lambda value: value["attempt_accounting"].update({"untouched_slots": 11}),
        lambda value: value["attempt_accounting"].update({"dispatches": 1}),
        lambda value: value["source_bindings"].update({"execution_claim_sha256": "0" * 64}),
        lambda value: value.update({"formal_result": "NO_GO"}),
        lambda value: value.update({"private_path": "C:/private"}),
    ),
)
def test_public_pre_provider_no_result_tampering_is_rejected(mutate) -> None:
    altered = deepcopy(read_result())
    mutate(altered)
    with pytest.raises(ValueError):
        assert_public_projection(altered)
