from __future__ import annotations

import hashlib
import json

import pytest
from jsonschema import Draft202012Validator

from hbqrs.repeatability import (
    RepeatabilityContractError,
    content_address,
    derived_reuse_receipt,
    fresh_replicate_receipt,
    paired_comparison_commitment,
    paired_response_envelope,
    run_config_sha256,
    summarize_replicate_group,
    validate_paired_comparison,
)
from hbqrs.paths import book_root


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _controls() -> dict[str, dict[str, object]]:
    return {
        "seed": {"state": "unsupported", "value": None},
        "temperature": {"state": "unsupported", "value": None},
    }


def _address(*, artifact: str = "artifact", contexts: tuple[str, ...] = ("context-a", "context-b")) -> dict[str, object]:
    return content_address(
        artifact_sha256=_hash(artifact),
        context_sha256=[_hash(context) for context in contexts],
        compiled_bundle_sha256=_hash("compiled-bundle"),
        question_sha256=_hash("ordered-questions"),
        prompt_sha256=_hash("compiled-prompt"),
        response_schema_sha256=_hash("response-schema"),
        judge_stack={"configured_provider_kind": "codex_cli", "reported_provider": "openai"},
        provider="codex",
        model="gpt-5.6-sol",
        reasoning="high",
        deterministic_control_support=_controls(),
    )


def _run_config(batch_attempts: int = 3) -> str:
    return run_config_sha256({"retry_policy": {"batch_attempts": batch_attempts}, "strict_ai": True})


def _fresh(address: str, index: int, score: float, *, sessions: tuple[str, ...] | None = None) -> object:
    return fresh_replicate_receipt(
        replicate_group_id="current-judge-contract-repeat",
        replicate_index=index,
        content_address_sha256=address,
        run_config_sha256=_run_config(),
        accepted_session_ids=sessions or (f"accepted-session-{index}",),
        run_receipt_sha256=_hash(f"run-receipt-{index}"),
        score=score,
    )


def test_content_address_is_path_independent_but_context_order_is_bound_and_retries_are_not() -> None:
    first = _address()
    second = _address()
    assert first == second
    assert first["content_address_sha256"] != _address(contexts=("context-b", "context-a"))["content_address_sha256"]
    assert _run_config(3) != _run_config(4)
    address = first["content_address_sha256"]
    assert isinstance(address, str)
    three_attempts = fresh_replicate_receipt(
        replicate_group_id="retry-not-replicate", replicate_index=1, content_address_sha256=address,
        run_config_sha256=_run_config(3), accepted_session_ids=("session-three-1", "session-three-2", "session-three-3"),
        run_receipt_sha256=_hash("run-three"), score=79.0,
    )
    four_attempts = fresh_replicate_receipt(
        replicate_group_id="retry-not-replicate", replicate_index=2, content_address_sha256=address,
        run_config_sha256=_run_config(4), accepted_session_ids=("session-four",),
        run_receipt_sha256=_hash("run-four"), score=80.0,
    )
    assert three_attempts.content_address_sha256 == four_attempts.content_address_sha256
    assert three_attempts.run_config_sha256 != four_attempts.run_config_sha256
    same_config_other = fresh_replicate_receipt(
        replicate_group_id="retry-not-replicate", replicate_index=2, content_address_sha256=address,
        run_config_sha256=_run_config(3), accepted_session_ids=("session-three-other",),
        run_receipt_sha256=_hash("run-three-other"), score=80.0,
    )
    assert summarize_replicate_group([three_attempts, same_config_other])["independent_observation_count"] == 2
    with pytest.raises(RepeatabilityContractError, match="one run configuration"):
        summarize_replicate_group([three_attempts, four_attempts])
    with pytest.raises(RepeatabilityContractError, match="local-path"):
        run_config_sha256({"codex_bin": "C:/local/codex.exe"})
    with pytest.raises(RepeatabilityContractError, match="Codex"):
        content_address(
            artifact_sha256=_hash("artifact"), context_sha256=[], compiled_bundle_sha256=_hash("bundle"),
            question_sha256=_hash("questions"), prompt_sha256=_hash("prompt"),
            response_schema_sha256=_hash("schema"), judge_stack={}, provider="codex", model="gpt-5.6-sol",
            reasoning="high", deterministic_control_support={"seed": {"state": "supported", "value": 7}, "temperature": {"state": "unsupported", "value": None}},
        )


def test_replicate_summary_requires_fresh_distinct_receipts_and_never_counts_retries() -> None:
    address = _address()["content_address_sha256"]
    assert isinstance(address, str)
    rows = [_fresh(address, 1, 79.0, sessions=("accepted-session-1a", "accepted-session-1b")), _fresh(address, 2, 80.0), _fresh(address, 3, 91.0)]
    summary = summarize_replicate_group(rows)
    assert summary["median"] == 80.0
    assert summary["mad"] == 1.0
    assert summary["range"] == 12.0
    assert summary["sample_standard_deviation"] == pytest.approx(6.658328)
    assert summary["independent_observation_count"] == 3
    assert summary["batch_attempts_are_statistical_replication"] is False
    assert len(summary["per_run_receipt_sha256"]) == 3

    reused_session = fresh_replicate_receipt(
        replicate_group_id="current-judge-contract-repeat", replicate_index=2, content_address_sha256=address,
        run_config_sha256=_run_config(), accepted_session_ids=("accepted-session-1b",),
        run_receipt_sha256=_hash("different-run"), score=80.0,
    )
    with pytest.raises(RepeatabilityContractError, match="session identity"):
        summarize_replicate_group([rows[0], reused_session])
    with pytest.raises(RepeatabilityContractError, match="replicate indices"):
        summarize_replicate_group([rows[0], _fresh(address, 3, 91.0)])


def test_derived_reuse_is_bound_to_source_and_cannot_be_an_independent_observation() -> None:
    address = _address()["content_address_sha256"]
    assert isinstance(address, str)
    source = _fresh(address, 1, 79.0)
    reuse = derived_reuse_receipt(
        source=source, requested_content_address_sha256=address, reuse_purpose="paired-comparison-input"
    )
    assert reuse.source_receipt_sha256 == source.receipt_sha256
    assert reuse.content_address_sha256 == source.content_address_sha256
    assert reuse.independent_observation is False
    with pytest.raises(RepeatabilityContractError, match="derived reuse"):
        summarize_replicate_group([source, reuse])  # type: ignore[list-item]
    with pytest.raises(RepeatabilityContractError, match="does not match"):
        derived_reuse_receipt(
            source=source, requested_content_address_sha256=_hash("other-content"), reuse_purpose="bad-reuse"
        )


_REQUESTS = {"AB": b"paired request: AB", "BA": b"paired request: BA"}


def _reuse(address: str, label: str):
    source = fresh_replicate_receipt(
        replicate_group_id=f"paired-source-{label}", replicate_index=1, content_address_sha256=address,
        run_config_sha256=_run_config(), accepted_session_ids=(f"paired-source-session-{label}",),
        run_receipt_sha256=_hash(f"paired-source-run-{label}"), score=80.0,
    )
    return derived_reuse_receipt(
        source=source, requested_content_address_sha256=address, reuse_purpose="paired-comparison-input"
    )


def _commit(*, identity_control: bool = False):
    first_address = _address(artifact="creative")["content_address_sha256"]
    second_address = _address(artifact="creative" if identity_control else "off")["content_address_sha256"]
    assert isinstance(first_address, str) and isinstance(second_address, str)
    return paired_comparison_commitment(
        comparison_id="creative-vs-off", artifact_a_reuse=_reuse(first_address, "a"),
        artifact_b_reuse=_reuse(second_address, "b"), judge_stack_sha256=_hash("judge-stack"),
        paired_contract_sha256=_hash("paired-contract"), ab_request_bytes=_REQUESTS["AB"],
        ba_request_bytes=_REQUESTS["BA"], provider="codex", deterministic_control_support=_controls(),
        identity_control=identity_control,
    )


def _response(commitment: dict[str, object], order: str, winner: str, number: int) -> dict[str, object]:
    return paired_response_envelope(
        commitment=commitment, presentation_order=order, request_bytes=_REQUESTS[order],
        accepted_session_ids=(f"paired-session-{number}",),
        response_bytes=json.dumps({"winner": winner}, separators=(",", ":")).encode("utf-8"),
    )


def test_paired_commitment_binds_reuse_lineage_and_exact_order_requests() -> None:
    first_address = _address(artifact="same")["content_address_sha256"]
    assert isinstance(first_address, str)
    with pytest.raises(RepeatabilityContractError, match="identity_control"):
        paired_comparison_commitment(
            comparison_id="same", artifact_a_reuse=_reuse(first_address, "same-a"),
            artifact_b_reuse=_reuse(first_address, "same-b"), judge_stack_sha256=_hash("judge-stack"),
            paired_contract_sha256=_hash("paired-contract"), ab_request_bytes=_REQUESTS["AB"],
            ba_request_bytes=_REQUESTS["BA"], provider="codex", deterministic_control_support=_controls(),
        )
    assert _commit(identity_control=True)["identity_control"] is True
    with pytest.raises(RepeatabilityContractError, match="identity_control"):
        paired_comparison_commitment(
            comparison_id="bad-identity-control", artifact_a_reuse=_reuse(first_address, "different-a"),
            artifact_b_reuse=_reuse(_address(artifact="different")["content_address_sha256"], "different-b"),  # type: ignore[arg-type]
            judge_stack_sha256=_hash("judge-stack"), paired_contract_sha256=_hash("paired-contract"),
            ab_request_bytes=_REQUESTS["AB"], ba_request_bytes=_REQUESTS["BA"], provider="codex",
            deterministic_control_support=_controls(), identity_control=True,
        )
    with pytest.raises(RepeatabilityContractError, match="validated derived"):
        paired_comparison_commitment(
            comparison_id="bad-source", artifact_a_reuse={"not": "derived"}, artifact_b_reuse=_reuse(first_address, "b"),  # type: ignore[arg-type]
            judge_stack_sha256=_hash("judge-stack"), paired_contract_sha256=_hash("paired-contract"),
            ab_request_bytes=_REQUESTS["AB"], ba_request_bytes=_REQUESTS["BA"], provider="codex",
            deterministic_control_support=_controls(),
        )

    commitment = _commit()
    with pytest.raises(RepeatabilityContractError, match="committed presentation order"):
        paired_response_envelope(
            commitment=commitment, presentation_order="AB", request_bytes=_REQUESTS["BA"],
            accepted_session_ids=("wrong-order",), response_bytes=b'{"winner":"FIRST"}',
        )
    with pytest.raises(RepeatabilityContractError, match="committed presentation order"):
        paired_response_envelope(
            commitment=commitment, presentation_order="AB", request_bytes=b"tampered request",
            accepted_session_ids=("wrong-request",), response_bytes=b'{"winner":"FIRST"}',
        )
    envelope = _response(commitment, "AB", "FIRST", 1)
    assert envelope["commitment_sha256"] == commitment["commitment_sha256"]
    assert envelope["response_bytes_sha256"] == _hash('{"winner":"FIRST"}')
    assert envelope["response_bytes_sha256"] != paired_response_envelope(
        commitment=commitment, presentation_order="AB", request_bytes=_REQUESTS["AB"],
        accepted_session_ids=("response-byte-tamper",), response_bytes=b'{"winner":"SECOND"}',
    )["response_bytes_sha256"]
    assert paired_response_envelope(
        commitment=commitment, presentation_order="AB", request_bytes=_REQUESTS["AB"],
        accepted_session_ids=("parsed-second",), response_bytes=b'{"winner":"SECOND"}',
    )["model_output"] == {"winner": "SECOND"}
    with pytest.raises(RepeatabilityContractError, match="model output does not match"):
        validate_paired_comparison(
            commitment,
            [
                envelope | {"model_output": {"winner": "SECOND"}},
                _response(commitment, "BA", "FIRST", 2),
            ],
        )
    with pytest.raises(RepeatabilityContractError, match="only winner"):
        paired_response_envelope(
            commitment=commitment, presentation_order="AB", request_bytes=_REQUESTS["AB"],
            accepted_session_ids=("bad-response",), response_bytes=b'{"winner":"FIRST","extra":true}',
        )


@pytest.mark.parametrize(
    ("ab_winner", "ba_winner", "expected"),
    [
        ("FIRST", "SECOND", "agreement_artifact_a"),
        ("SECOND", "FIRST", "agreement_artifact_b"),
        ("TIE", "TIE", "agreement_tie"),
        ("TIE", "FIRST", "tie_mismatch"),
        ("FIRST", "FIRST", "order_primacy"),
        ("SECOND", "SECOND", "order_recency"),
    ],
)
def test_paired_ab_ba_classifications_are_closed(ab_winner: str, ba_winner: str, expected: str) -> None:
    commitment = _commit()
    ab = _response(commitment, "AB", ab_winner, 1)
    ba = _response(commitment, "BA", ba_winner, 2)
    accepted = validate_paired_comparison(commitment, [ba, ab])
    assert accepted["agreement_classification"] == expected
    assert [row["presentation_order"] for row in accepted["responses"]] == ["AB", "BA"]

    with pytest.raises(RepeatabilityContractError, match="reused a session"):
        validate_paired_comparison(commitment, [ab, _response(commitment, "BA", ba_winner, 1)])


@pytest.mark.parametrize(
    ("ab_winner", "ba_winner", "expected"),
    [
        ("TIE", "TIE", "identity_control_agreement_tie"),
        ("FIRST", "FIRST", "identity_control_position_agreement"),
        ("SECOND", "SECOND", "identity_control_position_agreement"),
        ("FIRST", "SECOND", "identity_control_position_disagreement"),
        ("TIE", "FIRST", "identity_control_tie_mismatch"),
    ],
)
def test_identity_control_classifications_never_claim_artifact_preference(
    ab_winner: str, ba_winner: str, expected: str
) -> None:
    commitment = _commit(identity_control=True)
    accepted = validate_paired_comparison(
        commitment, [_response(commitment, "AB", ab_winner, 1), _response(commitment, "BA", ba_winner, 2)]
    )
    assert accepted["agreement_classification"] == expected
    assert "artifact_" not in expected


def test_paired_response_schema_is_strict_and_matches_contract_shape() -> None:
    schema_path = book_root() / "schema" / "paired-comparison-response.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    example = {"winner": "FIRST"}
    assert not list(validator.iter_errors(example))
    assert list(validator.iter_errors({**example, "extra": True}))
