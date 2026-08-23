from __future__ import annotations

import copy
import math

import pytest

from hbqrs.study_identity import condition_sha256, logical_sample_id, private_projection, public_projection, validate_schedule


def _condition(**changes: object) -> dict[str, object]:
    return {"arm": "baseline", "prompt_sha256": "b" * 64, "rubric_sha256": "c" * 64, **changes}


def _records() -> list[dict[str, object]]:
    rows = []
    for repetition in (1, 2, 3):
        rows.append(
            {
                "study_id": "figurative-dev-v1",
                "artifact_id": "synthetic-01",
                "artifact_sha256": "a" * 64,
                "condition": _condition(),
                "repetition": repetition,
                "rubric_revision": "1.2.0",
                "verified_run": {"accepted_provider_call_count": 2, "rejected_retry_count": 0, "batch_attempt_count": 2},
                "normalization_events": [{"kind": "quote"}] if repetition == 1 else [],
                "repair_attempts": [{"repair_id": "quote-repair-01", "condition": _condition(prompt_sha256="d" * 64), "rubric_revision": "1.2.1"}] if repetition == 1 else [],
            }
        )
    return rows


def test_identity_is_deterministic_committed_and_study_bound() -> None:
    condition = _condition()
    assert condition_sha256(condition) != condition_sha256(_condition(prompt_sha256="d" * 64))
    assert condition_sha256(condition) != condition_sha256(_condition(rubric_sha256="d" * 64))
    first = logical_sample_id(study_id="figurative-dev-v1", artifact_id="synthetic-01", artifact_sha256="a" * 64, condition=condition, repetition=1, rubric_revision="1.2.0")
    assert first != logical_sample_id(study_id="another-study", artifact_id="synthetic-01", artifact_sha256="a" * 64, condition=condition, repetition=1, rubric_revision="1.2.0")


@pytest.mark.parametrize("condition", [_condition(artifact_path="C:/private/source.txt"), _condition(source="C:/private/source.txt"), _condition(value=math.inf), {"arm": "baseline"}])
def test_condition_rejects_paths_nonfinite_values_and_missing_commitments(condition: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        condition_sha256(condition)


def test_schedule_requires_complete_nonpooled_series_and_unique_repairs() -> None:
    rows = _records()
    samples = validate_schedule(rows, repetitions=3)
    assert [sample["repetition"] for sample in samples] == [1, 2, 3]

    duplicate = rows + [copy.deepcopy(rows[0])]
    with pytest.raises(ValueError, match="duplicate logical sample"):
        validate_schedule(duplicate, repetitions=3)
    with pytest.raises(ValueError, match="missing or noncontiguous repetitions"):
        validate_schedule(rows[:2], repetitions=3)

    revised = copy.deepcopy(rows)
    revised[2]["rubric_revision"] = "1.2.1"
    with pytest.raises(ValueError, match="missing or noncontiguous repetitions"):
        validate_schedule(revised, repetitions=3)

    two_studies = copy.deepcopy(rows)
    two_studies[2]["study_id"] = "another-study"
    with pytest.raises(ValueError, match="exactly one study_id"):
        validate_schedule(two_studies, repetitions=3)

    duplicate_repair = copy.deepcopy(rows)
    duplicate_repair[1]["repair_attempts"] = copy.deepcopy(rows[0]["repair_attempts"])
    with pytest.raises(ValueError, match="duplicate repair_id"):
        validate_schedule(duplicate_repair, repetitions=3)


def test_hashes_and_verified_run_counts_are_strict() -> None:
    malformed = _records()
    malformed[0]["artifact_sha256"] = "A" * 64
    with pytest.raises(ValueError, match="lowercase 64-hex"):
        validate_schedule(malformed, repetitions=3)
    invalid_counts = _records()
    invalid_counts[0]["verified_run"] = {"accepted_provider_call_count": 2, "rejected_retry_count": 0, "batch_attempt_count": 1}
    with pytest.raises(ValueError, match="must equal batch_attempt_count"):
        validate_schedule(invalid_counts, repetitions=3)


def test_private_and_public_projections_keep_batch_attempts_out_of_n_and_public_safe() -> None:
    private = private_projection(_records(), repetitions=3)
    assert private["logical_samples"][0]["accepted_provider_call_count"] == 2
    assert private["logical_samples"][0]["repair_attempts"][0]["repair_logical_sample_id"].startswith("sample:")

    public = public_projection(_records(), repetitions=3)
    assert public["logical_repetition_count"] == 3
    row = public["conditions"][0]
    assert row["accepted_provider_call_count"] == 6
    assert row["rejected_retry_count"] == 0
    assert row["repair_attempt_count"] == 1
    assert {"rubric_revision", "study_id", "artifact_id", "condition", "repair_id", "artifact_path"}.isdisjoint(row)
