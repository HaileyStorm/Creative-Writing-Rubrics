from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from _scoped_module_loader import load_module


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation-results" / "hbq-four-state-polarity-confidence-v1"
study = load_module(PACKAGE / "study.py", name="four_state_polarity_confidence_v1")
verify_output = load_module(
    PACKAGE / "verify_output.py",
    name="four_state_polarity_confidence_verify_v1",
    aliases={"study": study},
)


def _matrix(cells: dict[tuple[str, str], int] | None = None) -> dict[str, dict[str, int]]:
    cells = cells or {}
    return {row: {column: cells.get((row, column), 0) for column in study.STATES} for row in study.STATES}


def test_full_four_by_four_reducer_has_every_required_typed_outcome() -> None:
    result = study.reduce_matrix(_matrix({(row, column): 1 for row in study.STATES for column in study.STATES}))
    assert result["counts"] == {
        "determinate_agreement": 2,
        "yes_no_contradiction": 2,
        "determinate_cannot_assess_conflict": 4,
        "not_applicable_retained": 1,
        "not_applicable_mismatch_invalid_excluded": 6,
        "cannot_assess_retained": 1,
    }
    assert result["invalid_excluded_count"] == 6
    assert result["classification"]["YES"]["YES"] == "yes_no_contradiction"
    assert result["classification"]["YES"]["NO"] == "determinate_agreement"
    assert result["classification"]["YES"]["CANNOT_ASSESS"] == "determinate_cannot_assess_conflict"
    assert result["classification"]["NOT_APPLICABLE"]["NOT_APPLICABLE"] == "not_applicable_retained"
    assert result["classification"]["CANNOT_ASSESS"]["NOT_APPLICABLE"] == "not_applicable_mismatch_invalid_excluded"


def test_reducer_rejects_non_four_state_or_non_integer_matrix() -> None:
    malformed = _matrix()
    malformed.pop("YES")
    with pytest.raises(ValueError, match="four rows"):
        study.reduce_matrix(malformed)
    malformed = _matrix()
    malformed["YES"]["NO"] = 0.5
    with pytest.raises(ValueError, match="non-negative integers"):
        study.reduce_matrix(malformed)


def test_summary_is_bound_to_published_aggregate_negative_results() -> None:
    summary = study.build_summary()
    assert summary["status"] == "offline_aggregate_only_diagnostic_no_go"
    assert summary["canonical_hbq_unchanged"] is True
    assert summary["production_change"] == "forbidden"
    assert summary["polarity"]["matched_pair_count"] == 81
    assert summary["polarity"]["matched_pair_disagreement_count"] == 8
    assert summary["polarity"]["published_four_state_matrix"] == "not_available_in_published_aggregate"
    confidence = summary["confidence"]
    assert confidence["initial_response_draws"] == confidence["additional_response_draws"]
    assert confidence["total_response_draws_per_simulation"] == 2 * confidence["initial_response_draws"]
    assert confidence["low_minus_uniform_proxy_accuracy"] < 0
    assert all(len(binding["sha256"]) == 64 for binding in summary["source_inputs"].values())


def test_verifier_recomputes_provenance_semantics_metrics_and_manifest(tmp_path: Path) -> None:
    output = tmp_path / "result"
    study.write_output(output)
    verified = verify_output.verify(output)
    assert verified["confidence"]["result"] == "negative_low_confidence_reallocation_did_not_beat_uniform"

    summary_path = output / "summary.json"
    original_summary = json.loads(summary_path.read_text(encoding="utf-8"))
    altered = deepcopy(original_summary)
    altered["polarity"]["four_state_policy"]["YES"]["YES"] = "determinate_agreement"
    summary_path.write_text(json.dumps(altered), encoding="utf-8")
    with pytest.raises(ValueError, match="metrics or provenance"):
        verify_output.verify(output)

    summary_path.write_text(json.dumps(original_summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    manifest_path = output / "manifest.json"
    altered_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    altered_manifest["files"]["summary.json"]["sha256"] = "0" * 64
    manifest_path.write_text(json.dumps(altered_manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="manifest"):
        verify_output.verify(output)


def test_pinned_source_hash_and_nested_privacy_mutation_are_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    altered_contract = deepcopy(study.CONTRACT)
    altered_contract["inputs"]["polarity_summary"]["sha256"] = "0" * 64
    monkeypatch.setattr(study, "CONTRACT", altered_contract)
    with pytest.raises(ValueError, match="Pinned input drifted"):
        study.bound_inputs()
    monkeypatch.undo()

    output = tmp_path / "result"
    study.write_output(output)
    summary_path = output / "summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["privacy"] = "aggregate-only but relaxed"
    summary_path.write_text(json.dumps(summary), encoding="utf-8")
    with pytest.raises(ValueError, match="limits, or privacy"):
        verify_output.verify(output)
