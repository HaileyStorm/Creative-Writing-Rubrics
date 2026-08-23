from __future__ import annotations

from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest

from hbqrs.paths import book_root


ROOT = book_root() / "evaluation-results" / "hbq-premise-scale-ownership-v1"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    sys.path.insert(0, str(ROOT))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.remove(str(ROOT))
    return module


def study():
    return load_module("premise_scale_ownership_study", ROOT / "study.py")


def test_frozen_package_has_exact_geometry_four_states_and_current_wording_bindings():
    s = study()
    report = s.verify_package()
    corpus = s.load_corpus()
    slots = s.plan_slots()
    assert report == {
        "study_id": "hbq-premise-scale-ownership-v1",
        "status": "frozen_development_only_current_wording_screen",
        "provider_calls": 0,
        "artifacts": 12,
        "slots": 72,
        "current_wording_bound": True,
    }
    assert len(corpus["artifacts"]) == 12
    assert len({item["pair_id"] for item in corpus["artifacts"]}) == 6
    assert {item["carrier"] for item in corpus["artifacts"]} == {"isolated", "composite"}
    assert {verdict for item in corpus["artifacts"] for verdict in item["expected_verdicts"].values()} == s.VERDICTS
    assert len(slots) == len({slot["slot_id"] for slot in slots}) == 72
    assert {slot["leaf_id"] for slot in slots} == set(s.LEAVES)
    assert {slot["repeat"] for slot in slots} == {1, 2, 3}
    assert all(slot["expected_verdict"] in s.VERDICTS for slot in slots)


def test_exact_source_leaf_and_ownership_invariants_are_pinned():
    s = study()
    assert s.source_leaf_records() == s.CANONICAL_LEAVES
    assert s.CANONICAL_LEAVES["artifact.support.premise_story_seed.extensibility"]["text"] == "Can it sustain the intended length and medium?"
    assert s.CANONICAL_LEAVES["op.ideation.premise_stress_test.scale"]["text"] == "Can the premise sustain the intended length and form without padding or premature exhaustion?"
    assert s.source_leaf_hashes() == s.load_contract()["bindings"]["source_leaves"]


def test_mutated_contract_and_mutated_corpus_fail_closed(monkeypatch):
    s = study()
    original_contract = deepcopy(s.load_contract())
    contract = deepcopy(original_contract)
    contract["geometry"]["slots_exact"] = 71
    monkeypatch.setattr(s, "load_contract", lambda: contract)
    with pytest.raises(ValueError, match="Study geometry drifted"):
        s.verify_package()
    corpus = deepcopy(s.load_corpus())
    corpus["artifacts"][0]["expected_verdicts"][s.LEAVES[0]] = "MAYBE"
    with pytest.raises(ValueError, match="Expected verdicts drifted"):
        s.verify_corpus(corpus)
    corpus = deepcopy(s.load_corpus())
    mismatched = next(item for item in corpus["artifacts"] if item["pair_id"] == "mismatched-form")
    mismatched["operation_target"] = mismatched["artifact_target"]
    with pytest.raises(ValueError, match="opposed and observable"):
        s.verify_corpus(corpus)
    corpus = deepcopy(s.load_corpus())
    operation_only = next(item for item in corpus["artifacts"] if item["case_id"] == "operation-only-isolated")
    operation_only["artifact_type"] = "planning_artifact"
    with pytest.raises(ValueError, match="Operation-only reference control"):
        s.verify_corpus(corpus)
    contract = deepcopy(original_contract)
    contract["scoring"]["cannot_assess"] = "scored"
    monkeypatch.setattr(s, "load_contract", lambda: contract)
    with pytest.raises(ValueError, match="Scoring gate drifted"):
        s.verify_package()


def test_typed_evidence_uses_production_shape_and_rejects_ungrounded_records():
    s = study()
    artifact = s.load_corpus()["artifacts"][0]
    s.validate_typed_evidence([
        {"kind": "exact_quote", "reference": "premise", "exact_quote": "Every winter, a city must choose one resident to forget", "summary": None},
        {"kind": "summary", "reference": "operation", "exact_quote": None, "summary": "The active operation declares the target."},
    ], artifact)
    with pytest.raises(ValueError, match="ungrounded"):
        s.validate_typed_evidence([
            {"kind": "exact_quote", "reference": "premise", "exact_quote": "not present", "summary": None},
        ], artifact)
    with pytest.raises(ValueError, match="shape"):
        s.validate_typed_evidence([
            {"section": "secret", "kind": "summary", "reference": "secret", "exact_quote": None, "summary": "not allowed"},
        ], artifact)


def test_production_response_is_projected_onto_a_separate_slot_ledger():
    s = study()
    slot = s.plan_slots()[0]
    response = {
        "question_id": slot["leaf_id"],
        "verdict": slot["expected_verdict"],
        "confidence": 0.8,
        "evidence": [{"kind": "exact_quote", "reference": "premise", "exact_quote": "Every winter, a city must choose one resident to forget", "summary": None}],
        "note": "Grounded synthetic result.",
    }
    assert s.project_production_verdict(slot["slot_id"], response)["matches_expected"] is True
    response["question_id"] = s.LEAVES[1]
    with pytest.raises(ValueError, match="surface or leaf"):
        s.project_production_verdict(slot["slot_id"], response)


def test_all_singleton_prompts_use_the_production_renderer_and_hide_oracle_ledger_metadata():
    s = study()
    rendered = s.render_all_provider_prompts()
    assert len(rendered) == 72
    mismatched_slot = next(slot for slot in s.plan_slots() if slot["case_id"] == "mismatched-form-isolated" and slot["leaf_id"] == s.LEAVES[1])
    prompt = rendered[mismatched_slot["slot_id"]]
    assert "artifact_target" in prompt and "stage play" in prompt and "one act" in prompt
    assert "operation_target" in prompt and "serial audio drama" in prompt and "20 episodes" in prompt
    assert "operation_active=True" in prompt
    assert mismatched_slot["slot_id"] not in prompt
    assert mismatched_slot["case_id"] not in prompt
    assert "expected_verdict" not in prompt


def test_real_text_gate_and_clarification_boundaries_are_explicit():
    contract = study().load_contract()
    holdout = contract["real_text_holdout_commitment"]
    assert holdout == study().HOLDOUT_CONTRACT_BINDING
    assert holdout["status"] == "sealed_from_evaluation"
    assert holdout["current_wording_diagnostic_access"] == "forbidden"
    assert "no_treatment_optimizer_or_confirmation" in holdout["later_execution_gate"]
    assert study().verify_real_text_holdout(contract) is None
    s = study()
    original_load_json = s.load_json
    altered = deepcopy(s.HOLDOUT_PUBLIC)
    altered["status"] = "opened"
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(s, "load_json", lambda path: altered if path.name == "external-real-text-holdout-commitment.json" else original_load_json(path))
    try:
        with pytest.raises(ValueError, match="Public real-text holdout commitment drifted"):
            s.verify_real_text_holdout(contract)
    finally:
        monkeypatch.undo()
    successor = contract["clarification_successor"]
    assert successor["maximum_exact"] == 1
    assert successor["requires_all_72_slots_settled"] is True
    assert successor["requires_independent_pair_types_minimum"] == 2
    assert successor["requires_same_scope_or_control_error_repeats_minimum"] == 2
    assert successor["requires_independent_sol_attribution"] == "one_missing_rendering_rule"
    assert "rubric_or_route_duplication" in successor["forbidden_if"]


def test_dry_run_and_render_plan_are_provider_free():
    dry = subprocess.run([sys.executable, str(ROOT / "run.py"), "--dry-run"], text=True, capture_output=True, check=True)
    rendered = subprocess.run([sys.executable, str(ROOT / "run.py"), "--render-plan"], text=True, capture_output=True, check=True)
    assert json.loads(dry.stdout)["verification"]["provider_calls"] == 0
    plan = json.loads(rendered.stdout)
    assert plan["mode"] == "render_plan"
    assert len(plan["rendered_slots"]) == 72
    source = (ROOT / "run.py").read_text(encoding="utf-8")
    assert "requests" not in source.lower()
    assert "subprocess" not in source.lower()
    assert "--execute" not in source


def test_public_package_contains_only_public_synthetic_material_and_no_private_path():
    forbidden = ("C:\\Users\\", "C:/Users/", "Gray Blood", "raw_response", "session_id", "api_key")
    for path in ROOT.iterdir():
        if path.suffix not in {".py", ".json", ".md"}:
            continue
        text = path.read_text(encoding="utf-8")
        assert all(fragment not in text for fragment in forbidden)
        assert "import dspy" not in text and "from dspy" not in text
