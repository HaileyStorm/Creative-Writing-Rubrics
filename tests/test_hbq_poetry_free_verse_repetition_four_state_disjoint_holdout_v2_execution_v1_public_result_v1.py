from __future__ import annotations

import json
import re
from copy import deepcopy

import pytest

from hbqrs.paths import book_root


ROOT = book_root() / "evaluation-results" / "hbq-poetry-free-verse-repetition-four-state-disjoint-holdout-v2-execution-v1-public-result-v1"
RESULT = ROOT / "public-result.json"

EXPECTED = {
    "format_version": 1,
    "study_id": "hbq-poetry-free-verse-repetition-four-state-disjoint-holdout-v2-execution-v1",
    "source_bindings": {
        "execution_claim_sha256": "cd1924031f8e75e4b0357ba42106d9e0591954d9ec649e555fa3b1423783d7d4",
        "live_driver_review_sha256": "989668f75456f79d652fef98249b330820beacae2e9286cde963b7804559c910",
        "execution_terminal_sha256": "6dcd80f0692881d42e7f84ff8cba4489dc27d0e848855b04192f0f2e71b7140e",
        "run_sha256": "91c7d0ad6e1bd6b63372e8009da3ddb4d5db5c5e80265c774b2407c417a73a0b",
        "accepted_checkpoint_sha256": "fda9c827f3a8430a4525ebb8a401f0485367f8215f880739c32f0558ed76562b",
        "accepted_response_sha256": "fe41f77a2ea49be4fae8f6199bf423ac22de9dcabd9aef7a5768fa79e95eb660",
        "attempt_start_sha256": "2d8d1431937154540ce78bd88a08eedb03048a6ad5ce44e14f79f899c557bd9b",
        "attempt_lifecycle_sha256": "939c456d07ff25c87ae2395481e5a00ec063a006e390d7774a31ecf5dac66ae2",
    },
    "route": {"provider": "openai", "model": "gpt-5.6-sol", "reasoning": "high"},
    "attempt_accounting": {
        "execution_claims": 1,
        "live_driver_reviews": 1,
        "physical_provider_attempts": 1,
        "accepted_first_attempts": 1,
        "retries": 0,
        "completed_slots": 0,
        "non_voting_semantic_outputs": 1,
        "untouched_slots": 11,
        "terminal_results": 1,
    },
    "accepted_response": {"verdict": "YES", "grounded_quote_evidence": True, "semantic_inference": "non_voting"},
    "transport_comparison": {
        "accepted_runner_prompt": {"bytes": 4659, "sha256": "0d06606807fb6b7db4cc1dcd4b948cc32632c1052ef5c1b5a9691e078721c05a", "crlf_count": 6, "line_feed_count": 80},
        "frozen_prompt": {"bytes": 4733, "sha256": "cf47236baafcba33ec85ef6ab7ebf595f5495526cbc137ca5c78d80762afda18", "crlf_count": 80, "line_feed_count": 80},
        "crlf_to_lf_canonical_bytes_equal": True,
        "canonical_sha256": "23e70b335557adc668f0a0ce26088a4f44b04f27cb760b394af1512ff61c6ee8",
    },
    "formal_result": "NO_RESULT_PROMPT_BYTE_BINDING_FAILURE",
    "failure_subtype": "TRANSPORT_NEWLINE_MISMATCH",
    "retry_or_resume": "not_authorized",
    "dspy": "not_authorized",
    "promotion": "none",
}


def read_result() -> dict:
    return json.loads(RESULT.read_text(encoding="utf-8"))


def assert_public_projection(value: dict) -> None:
    if value != EXPECTED:
        raise ValueError("public newline-mismatch no-result projection drifted")
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
        "exact_quote",
        "session_id",
        "q-46ac81",
        "cinderwake",
        "northgate",
    )
    if any(marker in public_text for marker in forbidden):
        raise ValueError("private material in public package")


def test_public_newline_mismatch_result_is_exact_aggregate_only() -> None:
    assert_public_projection(read_result())


@pytest.mark.parametrize(
    "mutate",
    (
        lambda value: value["attempt_accounting"].update({"completed_slots": 1}),
        lambda value: value["attempt_accounting"].update({"untouched_slots": 10}),
        lambda value: value["accepted_response"].update({"semantic_inference": "voting"}),
        lambda value: value["transport_comparison"].update({"crlf_to_lf_canonical_bytes_equal": False}),
        lambda value: value["source_bindings"].update({"execution_terminal_sha256": "0" * 64}),
        lambda value: value.update({"promotion": "eligible"}),
        lambda value: value.update({"private_path": "C:/private"}),
    ),
)
def test_public_newline_mismatch_tampering_is_rejected(mutate) -> None:
    altered = deepcopy(read_result())
    mutate(altered)
    with pytest.raises(ValueError):
        assert_public_projection(altered)
