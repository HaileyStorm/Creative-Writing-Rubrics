from __future__ import annotations

import importlib.util
import json
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
    study.verify_corpus(study.load_corpus())
    slots = study.plan_slots()
    contract = study.load_contract()
    assert contract["status"] == "frozen_provider_free_scope_wording_treatment"
    assert contract["provider_execution"] == {"permitted": False, "new_provider_calls_exact": 0, "paid_route": "forbidden", "one_leaf_per_request": True}
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
    question_index = study.REPOSITORY / "registry" / "question_index.jsonl"
    source = next(
        record
        for record in (json.loads(line) for line in question_index.read_text(encoding="utf-8").splitlines())
        if record.get("id") == study.SOURCE_LEAF_ID
    )
    assert source == {
        "module_id": "scope.poetry_poem",
        "module_title": "Single-poem scope overlay",
        "kind": "scope_overlay",
        "group_ids": ["scope.poetry_poem.quality"],
        "id": "scope.poetry_poem.form",
        "type": "question",
        "criterion_key": "scope.poetry_poem.form",
        "text": "Does the form feel necessary to that movement?",
        "pass_answer": "YES",
        "weight": 2.0,
        "question_type": "scored",
        "severity": "material",
        "applies_when": "The criterion is relevant to the requested artifact, scope, and operation.",
        "evidence_policy": {"required": True, "minimum_references": 1, "reference_style": "artifact span, unit ID, timestamp, or source ID"},
        "tags": [],
    }
    ownership = json.loads((study.REPOSITORY / "registry" / "criterion_ownership.json").read_text(encoding="utf-8"))
    assert ownership[study.SOURCE_LEAF_ID] == {"module_id": "scope.poetry_poem", "question_id": study.SOURCE_LEAF_ID}
    module_text = (study.REPOSITORY / "registry" / "modules" / "scope.poetry_poem.yaml").read_text(encoding="utf-8")
    index_text = question_index.read_text(encoding="utf-8")
    assert study.CANDIDATE_TEXT not in module_text and study.CANDIDATE_TEXT not in index_text


def test_current_checkout_fails_closed_before_archival_mechanics() -> None:
    study = load_study()
    with pytest.raises(ValueError, match="Pinned bound paths drifted from the exact Git parent"):
        study.verify_package()
