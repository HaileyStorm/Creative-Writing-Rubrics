from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import pytest

from hbqrs.paths import book_root


ROOT = book_root() / "evaluation-results" / "hbq-figurative-metaphor-checklist-successor-v1"


def study():
    spec = importlib.util.spec_from_file_location("figurative_metaphor_checklist_successor_v1", ROOT / "study.py")
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    sys.path.insert(0, str(ROOT))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.remove(str(ROOT))
    return module


def records(slots, *, wrong_cases=(), wrong_control=None):
    wrong_cases = set(wrong_cases)
    output = []
    for slot in slots:
        verdict = slot["expected_verdict"]
        if slot["leaf_id"] == "penalty.purple_prose.metaphor" and slot["case_id"] in wrong_cases:
            verdict = "NO" if verdict == "YES" else "YES"
        if wrong_control and slot["leaf_id"] == wrong_control and slot["repeat"] == 1:
            verdict = "NO" if verdict == "YES" else "YES"
        output.append({"slot_id": slot["slot_id"], "verdict": verdict})
    return output


def test_public_freeze_is_exact_provider_free_and_does_not_open_excerpt_text():
    s = study()
    assert s.verify_public_package() == {
        "study_id": "hbq-figurative-metaphor-checklist-successor-v1",
        "provider_calls": 0,
        "phase_a_slots": 72,
        "phase_b_slots": 24,
        "real_holdout_excerpt_text_opened": False,
    }
    contract = json.loads((ROOT / "study-contract.json").read_text(encoding="utf-8"))
    assert contract["provider_execution"] == {"permitted": False, "new_provider_calls_exact": 0, "one_leaf_per_request": True}
    assert contract["eventual_executor"] == {"enabled": False, "route": "codex", "model": "gpt-5.6-sol", "reasoning": "high", "one_leaf_per_request": True, "batch_size": 1, "repeats_per_slot": 3, "physical_attempts_per_slot": 1, "retry_or_resume": "forbidden", "attempt_lifecycle_policy": "terminal_sidecar_v1", "zero_incremental_charge_only": True, "paid_fallback": "forbidden"}
    assert contract["leaves"]["controls"] == [
        "core.freshness_and_non_genericness.no_default_metaphors",
        "penalty.purple_prose.proportion",
    ]
    assert contract["promotion"]["qpc24"] == "none"


def test_successor_v2_uses_actual_figurative_load_and_grounded_same_subject_semantics(monkeypatch):
    s = study()
    corpus = s.source_corpus()
    assert corpus["fixture_design"] == "v2_semantic_construction_actual_figurative_load"
    constructions = [row["semantic_construction"] for row in corpus["fixtures"]]
    assert all(construction["target_subject"] == "the argument" for construction in constructions)
    assert {len(construction["figures"]) for construction in constructions} == {3, 7}
    for construction in constructions:
        targets = [figure for figure in construction["figures"] if figure["role"] == "target_pair"]
        extras = [figure for figure in construction["figures"] if figure["role"] == "unrelated_extra"]
        assert len(targets) == 2 and {figure["subject"] for figure in targets} == {"the argument"}
        assert all(figure["subject"] != "the argument" for figure in extras)
        assert construction["reviewer_rationale"].strip()
    cooperative = next(construction for construction in constructions if [figure["relational_implication"] for figure in construction["figures"] if figure["role"] == "target_pair"] == ["connects", "supports_connection"])
    competing = next(construction for construction in constructions if [figure["relational_implication"] for figure in construction["figures"] if figure["role"] == "target_pair"] == ["connects", "isolates"])
    assert "bridge construction" in cooperative["reviewer_rationale"]
    assert "opposite relational implications" in competing["reviewer_rationale"]
    assert corpus != json.loads((ROOT.parent / "hbq-figurative-domain-compatibility-v1" / "public-synthetic-corpus.json").read_text(encoding="utf-8"))
    assert s.load_contract()["fixture_provenance"]["predecessor_modified"] is False
    mutated = deepcopy(corpus)
    mutated["fixtures"][0]["semantic_construction"]["figures"].pop()
    monkeypatch.setattr(s, "source_corpus", lambda: mutated)
    with pytest.raises(ValueError, match="Source semantic construction drifted"):
        s.verify_source_corpus()


def test_phase_a_is_current_only_and_phase_b_is_target_only_checklist():
    s = study()
    a = next(slot for slot in s.phase_a_slots() if slot["leaf_id"] == s.TARGET)
    b = next(slot for slot in s.phase_b_slots() if slot["case_id"] == a["case_id"] and slot["repeat"] == a["repeat"])
    control = next(slot for slot in s.phase_a_slots() if slot["case_id"] == a["case_id"] and slot["leaf_id"] == s.CONTROLS[0] and slot["repeat"] == a["repeat"])
    prompt_a, prompt_b, prompt_control = (s.render_provider_prompt(slot["slot_id"]) for slot in (a, b, control))
    assert s.CANDIDATE_CHECKLIST not in prompt_a and s.CANDIDATE_CHECKLIST not in prompt_control
    assert s.CANDIDATE_CHECKLIST in prompt_b
    assert "expected_verdicts" not in prompt_b and a["case_id"] not in prompt_b
    assert "Applicability and evidence-sufficiency rules" not in prompt_a and "Applicability and evidence-sufficiency rules" not in prompt_b


def test_phase_a_stops_for_control_failure_or_current_sufficiency_then_allows_phase_b_only_on_stable_misses():
    s = study()
    phase_a = s.phase_a_slots()
    control_bad = s.phase_a_decision(records(phase_a, wrong_control=s.CONTROLS[0]))
    assert control_bad["decision"] == "FIXTURE_OR_OWNERSHIP_INVALID"
    sufficient = s.phase_a_decision(records(phase_a))
    assert sufficient["decision"] == "CURRENT_TARGET_SUFFICIENT_NO_CHANGE"
    only_one = s.phase_a_decision(records(phase_a, wrong_cases=["successor-v2-05"]))
    assert only_one["decision"] == "STABLE_MISS_EVIDENCE_INSUFFICIENT_NO_CHANGE"
    same_stratum = s.phase_a_decision(records(phase_a, wrong_cases=["successor-v2-01", "successor-v2-05"]))
    assert same_stratum["decision"] == "STABLE_MISS_EVIDENCE_INSUFFICIENT_NO_CHANGE" and same_stratum["stable_miss_strata_count"] == 1
    unstable_records = records(phase_a)
    unstable_records[0]["verdict"] = "NO" if unstable_records[0]["verdict"] == "YES" else "YES"
    unstable = s.phase_a_decision(unstable_records)
    assert unstable["decision"] == "CURRENT_TARGET_UNSTABLE_NO_CHANGE" and unstable["target_unstable_cell_count"] == 1
    eligible = s.phase_a_decision(records(phase_a, wrong_cases=["successor-v2-05", "successor-v2-08"]))
    assert eligible["decision"] == "PHASE_B_ELIGIBLE"
    assert eligible["stable_miss_case_count"] == 2 and eligible["stable_miss_strata_count"] == 2


def test_phase_b_requires_all_target_slots_and_repairs_across_two_strata():
    s = study()
    misses = ["successor-v2-05", "successor-v2-08"]
    phase_a = records(s.phase_a_slots(), wrong_cases=misses)
    passing = s.phase_b_decision(phase_a, records(s.phase_b_slots()))
    assert passing == {
        "decision": "PHASE_B_PASS_HOLDOUT_ELIGIBLE",
        "candidate_target_correct": 24,
        "candidate_target_total": 24,
        "repaired_stable_miss_cases": 2,
        "repaired_stable_miss_strata": 2,
        "phase_a_controls_perfect": True,
        "promotion": "none",
    }
    failed_records = records(s.phase_b_slots(), wrong_cases=["successor-v2-05"])
    assert s.phase_b_decision(phase_a, failed_records)["decision"] == "NO_PROMOTION"
    with pytest.raises(ValueError, match="Phase B is forbidden"):
        s.phase_b_decision(records(s.phase_a_slots()), records(s.phase_b_slots()))


def test_dry_run_and_render_are_provider_free_and_holdout_is_commitment_only():
    dry = subprocess.run([sys.executable, str(ROOT / "run.py"), "--dry-run"], text=True, capture_output=True, check=True)
    rendered = subprocess.run([sys.executable, str(ROOT / "run.py"), "--render"], text=True, capture_output=True, check=True)
    dry_value, rendered_value = json.loads(dry.stdout), json.loads(rendered.stdout)
    assert dry_value["provider_calls"] == 0 and dry_value["verification"]["phase_a_slots"] == 72
    assert rendered_value["provider_calls"] == 0 and rendered_value["prompt_count"] == 96
    holdout = json.loads((ROOT / "real-holdout-commitment.json").read_text(encoding="utf-8"))
    assert holdout["carrier_status"] == "not_authored_or_sourced"
    assert "Gray Blood" in holdout["prohibitions"]
    assert "provider submission before Phase B pass and separate private carrier freeze" in holdout["prohibitions"]
    assert holdout["execution_gate"] == "Phase_B_pass_and_separate_private_carrier_freeze_with_eight_disjoint_excerpt_hashes_before_any_provider_call"
