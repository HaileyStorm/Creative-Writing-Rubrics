from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation-results" / "hbq-poetry-whole-poem-architecture-treatment-v2"


def load_study():
    spec = importlib.util.spec_from_file_location("whole_poem_architecture_treatment_v2", PACKAGE / "study.py")
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_v2_freeze_is_provider_free_and_has_exact_singleton_geometry() -> None:
    study = load_study()
    assert study.verify_package() == {"study_id": study.STUDY_ID, "status": "frozen_provider_free_scope_wording_treatment", "provider_calls": 0, "fixtures": 7, "slots": 42}
    slots = study.plan_slots()
    assert len(slots) == len({slot["slot_id"] for slot in slots}) == 42
    assert {slot["arm"] for slot in slots} == set(study.ARMS)
    assert sum(slot["candidate_expected"] != "UNOPENED" for slot in slots) == 21


def test_candidate_is_the_reviewed_inter_part_wording_byte_for_byte() -> None:
    study = load_study()
    expected = "If the declared evaluation scope is not a whole poem, answer NOT_APPLICABLE. If whole-poem scope is declared but the supplied text is not confirmed complete enough for whole-poem judgment, answer CANNOT_ASSESS. Only after completeness is established, answer NOT_APPLICABLE when the poem has fewer than two major parts at whole-poem scale. Otherwise, does a specific structural relationship among those major parts—their ordering, framing, recurrence, juxtaposition, or relative proportion—depend on their placement or scale strongly enough that materially rearranging or resizing them would weaken the poem-wide architecture? YES requires evidence of that inter-part relationship. A merely final or contrasting part, or a plausible thematic or narrative progression by itself, is insufficient. Do not judge local formal mechanics, stanza-boundary effects, turns, ending quality, or movement quality here."
    assert study.CANDIDATE_TEXT == expected
    assert study.REJECTED_WORDING != study.CANDIDATE_TEXT


def test_v2_has_five_fresh_discriminators_and_two_truthfully_inherited_scope_controls() -> None:
    study = load_study()
    cases = {case["case_id"]: case for case in study.load_corpus()["cases"]}
    assert {case["candidate_expected"] for case in cases.values()} == study.VERDICTS
    assert cases["inter_part_positive"]["candidate_expected"] == "YES"
    assert cases["permutation_neutral"]["candidate_expected"] == "NO"
    assert cases["ending_only_coda"]["candidate_expected"] == "NO"
    assert cases["semantic_progression_without_inter_part_relation"]["candidate_expected"] == "NO"
    assert cases["declared_whole_poem_incomplete"]["candidate_expected"] == "CANNOT_ASSESS"
    assert cases["complete_single_part"]["candidate_expected"] == "NOT_APPLICABLE"
    assert cases["declared_excerpt"]["candidate_expected"] == "NOT_APPLICABLE"
    fresh = [case for case in cases.values() if case["fixture_origin"] == "new_public_synthetic"]
    inherited = [case for case in cases.values() if case["fixture_origin"] == "inherited_stable_public_synthetic_scope_control"]
    assert len(fresh) == 5 and len(inherited) == 2
    assert {case["source_fixture_id"] for case in inherited} == {"scope-treatment-v1-03", "scope-treatment-v1-04"}
    assert all(case["candidate_expected"] in {"YES", "NO", "CANNOT_ASSESS"} for case in fresh)
    assert all(case["candidate_expected"] == "NOT_APPLICABLE" for case in inherited)


def test_treatment_fails_closed_on_bound_runtime_drift(monkeypatch) -> None:
    study = load_study()
    original = study.git_show_bytes
    monkeypatch.setattr(study, "git_show_bytes", lambda path: b"drift" if path == "src/hbqrs/runner.py" else original(path))
    with pytest.raises(ValueError, match="Runtime binding drifted"):
        study.verify_package()
