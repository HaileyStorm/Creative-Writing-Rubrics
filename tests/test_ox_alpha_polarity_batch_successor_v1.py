from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import re

import pytest
from hbqrs.paths import book_root

ROOT = book_root() / "evaluation-results" / "hbq-ox-alpha-polarity-batch-successor-v1"
V9 = Path(os.environ["HBQ_OX_ALPHA_V9_ROOT"]).expanduser() if os.environ.get("HBQ_OX_ALPHA_V9_ROOT") else None
spec = importlib.util.spec_from_file_location("ox_polarity_batch_successor", ROOT / "study.py")
assert spec and spec.loader
study = importlib.util.module_from_spec(spec)
spec.loader.exec_module(study)


def test_contract_selection_and_exact_30_call_screen_are_frozen():
    assert study.load_contract()["geometry"]["screen_provider_calls"] == 30
    rows = study.schedule()
    assert len(rows) == 30
    assert {row["story_id"] for row in rows} == set(study.STORIES)
    assert {row["condition_id"] for row in rows} == {item["id"] for item in study.CONDITIONS}
    assert sum(len(row["question_ids"]) for row in rows if row["condition_id"] == "positive_batch1") == 12
    assert sum(len(row["question_ids"]) for row in rows if row["condition_id"] == "positive_batch4") == 12
    with pytest.raises(ValueError, match="first-stage gate"):
        study.schedule(2)
    with pytest.raises(ValueError): study.schedule(3)


def test_reviewed_polarity_and_v9_source_bind_each_selected_leaf(tmp_path):
    pairs = study.reviewed_pairs()
    assert tuple(pairs) == study.QUESTION_IDS
    if V9 is None or not V9.is_dir(): pytest.skip("set HBQ_OX_ALPHA_V9_ROOT to verify frozen v9 evidence")
    bound = study.source_v9_provenance(V9)
    assert bound["stories"] == list(study.STORIES)
    assert bound["question_ids"] == list(study.QUESTION_IDS)
    plan = study.freeze_plan(V9, tmp_path / "screen-plan.json")
    assert plan["provider_calls_this_screen"] == 30
    assert plan["remote_calls"] == "forbidden_by_this_package"
    assert set(plan["positive_wording_source"]["question_text_sha256"]) == set(study.QUESTION_IDS)
    assert not re.search(r"[A-Za-z]:[\\/]", (tmp_path / "screen-plan.json").read_text(encoding="utf-8"))


def test_polarity_questions_and_canonical_reverse_decode():
    row = next(item for item in study.schedule() if item["condition_id"] == "negative_failure_batch4")
    questions = study.request_questions(row)
    assert [item["question_id"] for item in questions] == list(study.QUESTION_IDS)
    assert questions[0]["question"] == study.reviewed_pairs()[study.QUESTION_IDS[0]]
    assert study.canonicalize_verdict("YES", "negative_failure") == "NO"
    assert study.canonicalize_verdict("NO", "negative_failure") == "YES"
    assert study.canonicalize_verdict("NOT_APPLICABLE", "negative_failure") == "NOT_APPLICABLE"
    assert study.canonicalize_verdict("CANNOT_ASSESS", "negative_failure") == "CANNOT_ASSESS"


def test_batch_chunking_and_deterministic_quote_normalization_need_no_repair_call():
    single = next(item for item in study.schedule() if item["condition_id"] == "positive_batch1")
    grouped = next(item for item in study.schedule() if item["condition_id"] == "positive_batch4")
    assert len(single["question_ids"]) == 1 and len(grouped["question_ids"]) == 4
    normalized, audit = study.normalize_evidence([{"reference": "artifact", "kind": "exact_quote", "exact_quote": "not present", "summary": None}], question_id=study.QUESTION_IDS[0], artifact_text="present")
    assert normalized == [{"reference": "artifact", "summary": "not present"}]
    assert audit[0]["to"] == "summary"


def test_availability_is_bounded_and_charge_or_non524_never_retries():
    assert study.availability_outcome(http_status=524) == "eligible_524"
    assert study.availability_outcome(http_status=500) == "quarantined"
    assert study.availability_outcome(http_status=402) == "global_stop"
    assert study.availability_outcome(charge_signal=True) == "global_stop"
    assert study.availability_policy(2) == {"state": "cooldown", "minutes": 15}
    assert study.availability_policy(3) == {"state": "cooldown", "minutes": 30}
    assert study.availability_policy(6) == {"state": "paused", "minutes": None}
    assert study.availability_policy(0, eligible_524_for_unit=5) == {"state": "unit_retry_exhausted", "minutes": None}
    assert study.availability_policy(6, eligible_524_for_unit=5) == {"state": "paused", "minutes": None}
    with pytest.raises(ValueError): study.availability_policy(0, eligible_524_for_unit=6)


def test_analysis_exposes_diagnostics_without_a_production_choice():
    records = []
    for condition in study.CONDITIONS:
        records.append({"status": "accepted", "story_id": "hanna-827", "condition_id": condition["id"], "polarity": condition["polarity"], "question_id": study.QUESTION_IDS[0], "verdict": "YES", "confidence": 0.8, "normalized_evidence": condition["id"] == "positive_batch1"})
    result = study.analyze(records + [{"status": "eligible_524"}, {"status": "quarantined"}])
    assert result["polarity_pairs"] == 2
    assert result["canonical_polarity_disagreement_rate"] == 1.0
    assert result["paired_mean_diagnostic"] == 0.5
    assert result["batch_polarity_interaction"] == 0.0
    assert result["attrition"]["eligible_524"] == 1
    assert result["quote_normalization_rate"] == 0.25
    assert result["production_recommendation"] is None
    assert not study.confirmation_available(result)


def test_effects_require_matched_four_condition_blocks_and_polarity_must_match_condition():
    incomplete = study.analyze([{"status": "accepted", "story_id": "hanna-827", "condition_id": "positive_batch1", "polarity": "positive", "question_id": study.QUESTION_IDS[0], "verdict": "YES", "confidence": 0.8}])
    assert incomplete["matched_story_leaf_blocks"] == 0
    assert incomplete["batch_polarity_interaction"] is None
    bad = {"status": "accepted", "story_id": "hanna-827", "condition_id": "positive_batch1", "polarity": "negative_failure", "question_id": study.QUESTION_IDS[0], "verdict": "YES", "confidence": 0.8}
    with pytest.raises(ValueError, match="mismatch"):
        study.analyze([bad])


def test_confirmation_schedule_requires_the_frozen_complete_first_stage_gate():
    records = [
        {"status": "accepted", "story_id": story_id, "condition_id": condition["id"], "polarity": condition["polarity"], "question_id": question_id, "verdict": "YES", "confidence": 0.8}
        for story_id in study.STORIES for question_id in study.QUESTION_IDS for condition in study.CONDITIONS
    ]
    result = study.analyze(records)
    assert result["accepted_records"] == 48
    assert result["matched_story_leaf_blocks"] == 12
    assert study.confirmation_available(result)
    assert len(study.schedule(2, first_screen_analysis=result)) == 30


@pytest.mark.parametrize("confidence", [True, -0.1, 1.1, float("nan"), float("inf")])
def test_invalid_confidence_and_normalization_status_are_rejected(confidence):
    row = {"status": "accepted", "story_id": "hanna-827", "condition_id": "positive_batch1", "polarity": "positive", "question_id": study.QUESTION_IDS[0], "verdict": "YES", "confidence": confidence}
    with pytest.raises(ValueError, match="Malformed"):
        study.analyze([row])
    with pytest.raises(ValueError, match="Unknown result status"):
        study.analyze([{"status": "normalized_evidence"}])


def test_na_and_cannot_assess_do_not_become_numeric_no_effects():
    records = [
        {"status": "accepted", "story_id": "hanna-827", "condition_id": condition["id"], "polarity": condition["polarity"], "question_id": study.QUESTION_IDS[0], "verdict": "NOT_APPLICABLE" if condition["id"] == "positive_batch1" else "YES", "confidence": 0.8}
        for condition in study.CONDITIONS
    ]
    result = study.analyze(records)
    assert result["matched_story_leaf_blocks"] == 1
    assert result["scoreable_matched_story_leaf_blocks"] == 0
    assert result["batch_polarity_interaction"] is None
    assert result["batch_effect"]["batch1_yes_rate"] is None
    assert result["paired_mean_diagnostic"] == 0.5


def test_tracked_successor_surface_has_no_absolute_path_or_story_text_fixture():
    paths = [*ROOT.iterdir(), Path(__file__)]
    for path in paths:
        if path.is_file():
            assert not re.search(r"[A-Za-z]:[\\/]", path.read_text(encoding="utf-8"))
