from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation-results" / "hbq-poetry-whole-poem-architecture-treatment-v1"


def load_study():
    spec = importlib.util.spec_from_file_location("whole_poem_architecture_treatment", PACKAGE / "study.py")
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_scope_treatment_is_provider_free_and_has_exact_singleton_geometry() -> None:
    study = load_study()
    report = study.verify_package()
    slots = study.plan_slots()
    assert report == {"study_id": study.STUDY_ID, "status": "frozen_provider_free_scope_wording_treatment", "provider_calls": 0, "fixtures": 7, "slots": 42}
    assert len(slots) == len({slot["slot_id"] for slot in slots}) == 42
    assert {slot["arm"] for slot in slots} == set(study.ARMS)
    assert sum(slot["candidate_expected"] != "UNOPENED" for slot in slots) == 21


def test_candidate_excludes_movement_turn_ending_and_local_form_owners() -> None:
    study = load_study()
    text = study.CANDIDATE_TEXT.lower()
    for required in ("ordering and proportion", "materially rearranging", "not local formal mechanics", "turns", "ending", "movement succeeds"):
        assert required in text
    assert "necessary to that movement" not in text
    assert study.REJECTED_WORDING != study.CANDIDATE_TEXT


def test_architecture_controls_separate_non_temporal_order_from_local_turn_success() -> None:
    study = load_study()
    corpus = {case["case_id"]: case for case in study.load_corpus()["cases"]}
    positive = corpus["ordered_architecture"]
    owner_control = corpus["owner_positive_architecture_negative"]
    assert positive["candidate_expected"] == "YES"
    assert all(token not in positive["text"].lower() for token in ("before", "after", "but", "then"))
    assert owner_control["candidate_expected"] == "NO" and "But no one comes." in owner_control["text"]


def test_treatment_fails_closed_on_bound_runtime_drift(monkeypatch) -> None:
    study = load_study()
    original = study.git_show_bytes
    monkeypatch.setattr(study, "git_show_bytes", lambda path: b"drift" if path == "src/hbqrs/runner.py" else original(path))
    with pytest.raises(ValueError, match="Runtime binding drifted"):
        study.verify_package()
