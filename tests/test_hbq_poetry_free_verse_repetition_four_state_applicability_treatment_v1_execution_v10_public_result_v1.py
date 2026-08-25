from __future__ import annotations

import json
import re
from copy import deepcopy

import pytest

from hbqrs.paths import book_root


ROOT = book_root() / "evaluation-results" / "hbq-poetry-free-verse-repetition-four-state-applicability-treatment-v1-execution-v10-public-result-v1"
RESULT = ROOT / "public-result.json"

EXPECTED = {
    "format_version": 1,
    "study_id": "hbq-poetry-free-verse-repetition-four-state-applicability-treatment-v1-execution-v10",
    "source_bindings": {
        "execution_claim_sha256": "be54aa07b1943e4707148c934c11b4a6ac58a8f0abdc6a8278daee612d414f81",
        "study_manifest_sha256": "5e296bf58cf1177d8c0e3ed44a339a9d630d0033957f8a71c3a3f22449b070b8",
        "zero_charge_acknowledgement_sha256": "d2db22c2e3f7642c631f4e63380a7872451036cf7d4adee1b9f39ded41235c8d",
        "provider_free_dry_run_sha256": "3683fa4fc342536635d2410d2c38252287b1cc6d448f4b0077f51776e1d0d4a6",
        "settlement_sha256": "3ea8e8932d3d92b72af939ba44aa39b8b2df08243fa4d095a190003e9998ff55",
        "public_aggregate_sha256": "3440c2855761a832345b5d9504f27cb40cc37045de9af0f5e4c49eabc421a632",
        "terminal_sidecar_sha256": "c30da0c3470bddc65f041172699c2bd9cd788e124e76be4947ca2c9a73895a41",
        "terminal_records_sha256": "55c2716188cdcb068010c30a95e0a049d7adc05b399d21b2eeafea9bea615c5b",
    },
    "route": {"provider": "openai", "model": "gpt-5.6-sol", "reasoning": "high"},
    "attempt_accounting": {
        "execution_claims": 1,
        "zero_charge_acknowledgements": 1,
        "dispatches": 12,
        "runs": 12,
        "physical_provider_attempts": 12,
        "provider_contacted": True,
        "accepted_first_attempts": 12,
        "retries": 0,
        "rejected_attempts": 0,
        "normalization_events": 0,
        "accepted_checkpoints": 12,
        "accepted_verdicts": 12,
        "settlements": 1,
        "terminal_results": 1,
    },
    "verdict_state_counts": {"YES": 3, "NO": 3, "NOT_APPLICABLE": 3, "CANNOT_ASSESS": 3},
    "evidence": {"accepted_records_with_grounded_quotes": 12, "grounded_quote_count": 13},
    "decision": "HOLDOUT_ELIGIBLE_ON_SUCCESS",
    "success_authorizes_only": "fresh_disjoint_holdout",
    "dspy": "not_authorized",
    "promotion": "none",
}


def read_result() -> dict:
    return json.loads(RESULT.read_text(encoding="utf-8"))


def assert_public_projection(value: dict) -> None:
    if value != EXPECTED:
        raise ValueError("public completed-screen projection drifted")
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
        "session_id",
        "provider_artifacts",
    )
    if any(marker in public_text for marker in forbidden) or re.search(r"\bq-[0-9a-f]{12}\b", public_text):
        raise ValueError("private material in public package")


def test_public_completed_screen_is_exact_aggregate_only() -> None:
    assert_public_projection(read_result())


@pytest.mark.parametrize(
    "mutate",
    (
        lambda value: value["attempt_accounting"].update({"accepted_first_attempts": 11}),
        lambda value: value["attempt_accounting"].update({"normalization_events": 1}),
        lambda value: value["verdict_state_counts"].update({"YES": 4}),
        lambda value: value["source_bindings"].update({"settlement_sha256": "0" * 64}),
        lambda value: value.update({"decision": "PROMOTE"}),
        lambda value: value.update({"private_path": "C:/private"}),
    ),
)
def test_public_completed_screen_tampering_is_rejected(mutate) -> None:
    altered = deepcopy(read_result())
    mutate(altered)
    with pytest.raises(ValueError):
        assert_public_projection(altered)
