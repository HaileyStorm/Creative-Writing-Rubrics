from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from copy import deepcopy

import pytest
from hbqrs.paths import book_root


ROOT = book_root() / "evaluation-results" / "hbq-nonpoetry-scope-final-manual-v1"


def study():
    spec = importlib.util.spec_from_file_location("s2_final_manual", ROOT / "study.py")
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def attestation(s, *, candidate_passes=True):
    return {
        "visibility": "private_controller_only",
        "controller_contract_commitment_sha256": s.PRIVATE_CONTROLLER_COMMITMENT,
        "completed_calls": 24,
        "candidate_all_four_cells_3_of_3": candidate_passes,
        "no_localized_or_inactive_regression": True,
    }


def test_final_manual_contract_is_provider_free_and_selects_fresh_24_call_ab():
    s = study()
    assert s.validate_package() == {"study_id": s.STUDY_ID, "provider_calls": 0, "planned_new_calls": 24, "reused_calls": 0, "holdout_eligible_on_success": True}
    contract = s.load_json("study-contract.json")
    assert contract["provider_execution"]["permitted_now"] is False
    assert contract["provider_execution"]["provider_calls_made_now_exact"] == 0
    assert contract["reuse"]["selected_mode"] == "fresh_24_call_ab"
    assert contract["private_controller"]["controller_contract_commitment_sha256"] == s.PRIVATE_CONTROLLER_COMMITMENT
    assert contract["development_gate"]["failure_action"] == "NO_GO_DSPY_ELIGIBLE_ONLY"
    assert contract["development_gate"]["success_action"] == "HOLDOUT_ELIGIBLE_ON_SUCCESS"


def test_exact_corrected_candidate_preserves_leaf_owner_and_policy_fields():
    s = study()
    source, candidate = s.source_leaf(), s.candidate_leaf()
    assert candidate["text"] == "For a passage explicitly declared to be an excerpt or fragment, does the supplied evaluation avoid penalizing it for not being a complete work?"
    assert s.source_owner() == {"module_id": "scope.passage", "question_id": "scope.passage.status"}
    for field in s.PRESERVED_FIELDS:
        assert candidate[field] == source[field]
    assert candidate["question_type"] == "diagnostic"
    assert candidate["applies_when"] == source["applies_when"]
    assert candidate["evidence_policy"] == source["evidence_policy"]


def test_public_plan_is_exactly_opaque_four_fixture_ab_with_one_leaf_requests():
    s = study()
    plan = s.build_plan()
    assert len(plan) == len({row["slot_id"] for row in plan}) == 24
    assert {row["fixture_commitment_sha256"] for row in plan} == set(s.FIXTURE_COMMITMENTS)
    assert {row["leaf_id"] for row in plan} == {s.LEAF_ID}
    assert all("expected_verdict" not in row and "fixture_text" not in row and "state" not in row for row in plan)


def test_attestation_is_commitment_bound_and_never_exposes_private_results():
    s = study()
    assert s.assess_private_controller_attestation(attestation(s))["decision"] == "HOLDOUT_ELIGIBLE_ON_SUCCESS"
    assert s.assess_private_controller_attestation(attestation(s, candidate_passes=False))["decision"] == "NO_GO_DSPY_ELIGIBLE_ONLY"
    invalid = attestation(s)
    invalid["completed_calls"] = 23
    with pytest.raises(ValueError, match="geometry"):
        s.assess_private_controller_attestation(invalid)


def test_contract_or_private_attestation_drift_fails_closed():
    s = study()
    contract = deepcopy(s.load_json("study-contract.json"))
    contract["provider_execution"]["planned_new_provider_calls_exact"] = 23
    original = s.load_json
    s.load_json = lambda name: contract if name == "study-contract.json" else original(name)
    with pytest.raises(ValueError, match="contract"):
        s.validate_package()
    invalid = attestation(s)
    invalid["visibility"] = "public"
    with pytest.raises(ValueError, match="visibility"):
        s.assess_private_controller_attestation(invalid)


def test_dry_run_is_the_only_command_surface_and_makes_zero_calls():
    completed = subprocess.run([sys.executable, str(ROOT / "run.py"), "--dry-run"], capture_output=True, text=True, check=True)
    report = json.loads(completed.stdout)
    assert report["provider_calls"] == 0
    assert len(report["opaque_slot_ids"]) == 24
    source = (ROOT / "run.py").read_text(encoding="utf-8").casefold()
    assert "requests" not in source and "execute" not in source and "dspy" not in source
