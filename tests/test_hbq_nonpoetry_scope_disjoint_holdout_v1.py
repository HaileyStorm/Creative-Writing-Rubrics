from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from copy import deepcopy
from itertools import product

import pytest
from hbqrs.paths import book_root
from tests import _hbq_s2_historical_runtime as historical_runtime


ROOT = book_root() / "evaluation-results" / "hbq-nonpoetry-scope-disjoint-holdout-v1"


def study():
    spec = importlib.util.spec_from_file_location("s2_disjoint_holdout", ROOT / "study.py")
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    try:
        return historical_runtime.install(module, source_commit="c4ba06453785bdb52bce374926b65d3cab542a9a")
    except historical_runtime.HistoricalRuntimeUnbound as exc:
        pytest.skip(f"historical runtime unbound: {exc}")


def test_contract_freezes_zero_call_48_slot_disjoint_holdout():
    s = study()
    report = s.validate_public_package()
    assert report["provider_calls"] == 0
    assert report["planned_future_calls"] == 48
    assert report["fixtures"] == 8
    assert report["promotion"] == "none"
    assert len(report["opaque_slot_ids"]) == len(set(report["opaque_slot_ids"])) == 48
    contract = s.load_json(ROOT / "study-contract.json")
    assert contract["earned_by_public_commit"] == "271e30a6adf08e6fc8f9da40cf48638d60b412eb"
    assert contract["provider_execution"]["permitted_now"] is False
    assert contract["provider_execution"]["post_response_retries_permitted"] is False
    assert contract["geometry"] == {
        "fixtures_exact": 8,
        "public_domain_carriers_exact": 6,
        "activation_controls_exact": 2,
        "states_exact": 4,
        "fixtures_per_state_exact": 2,
        "arms": ["baseline", "candidate"],
        "repeats": 3,
        "slots_exact": 48,
    }


def test_candidate_changes_only_text_and_preserves_canonical_owner_policy():
    s = study()
    source = s.source_leaf()
    candidate = s.candidate_leaf()
    assert candidate["text"] == s.CANDIDATE_TEXT
    assert candidate["text"] != source["text"]
    assert s.source_owner() == {"module_id": "scope.passage", "question_id": s.LEAF_ID}
    for field in s.PRESERVED_FIELDS:
        assert candidate[field] == source[field]


def test_plan_is_same_fixture_ab_with_p4_only_delta():
    s = study()
    plan = s.build_public_plan()
    assert len(plan) == 48
    assert {row["leaf_id"] for row in plan} == {s.LEAF_ID}
    assert {row["repeat"] for row in plan} == {1, 2, 3}
    assert {row["arm"] for row in plan} == {"baseline", "candidate"}
    assert {row["fixture_commitment_sha256"] for row in plan} == set(s.FIXTURE_COMMITMENTS)
    for fixture_id in s.FIXTURE_IDS:
        for repeat in s.REPEATS:
            pair = [row for row in plan if row["slot_id"].startswith(f"{fixture_id}-") and row["repeat"] == repeat]
            assert len(pair) == 2
            assert len({row["p0_p3_commitment_sha256"] for row in pair}) == 1
            assert {row["p4_question"]["text"] for row in pair} == {s.source_leaf()["text"], s.CANDIDATE_TEXT}


def test_public_package_is_commitment_only_and_contains_no_source_or_fixture_content():
    forbidden = (
        "Pride and Prejudice",
        "Moby Dick",
        "A Tale of Two Cities",
        "The Souls of Black Folk",
        "Alice's Adventures in Wonderland",
        "Frankenstein",
        "Call me Ishmael",
        "EDITORIAL MEMO",
        "ACQUISITIONS NOTICE",
    )
    public_text = "\n".join(
        (ROOT / name).read_text(encoding="utf-8")
        for name in ("README.md", "run.py", "study-contract.json", "study.py")
    )
    assert not any(value in public_text for value in forbidden)
    contract = json.loads((ROOT / "study-contract.json").read_text(encoding="utf-8"))
    assert "expected_verdict" not in json.dumps(contract, sort_keys=True)
    assert {path.name for path in ROOT.iterdir() if path.is_file()} == {"README.md", "run.py", "study-contract.json", "study.py"}


def test_gate_is_exact_and_never_self_promotes():
    s = study()
    contract = s.load_json(ROOT / "study-contract.json")
    gate = contract["decision_gate"]
    assert gate["pass"] == "PROMOTION_REVIEW_ELIGIBLE"
    assert gate["pass_requires"] == [
        "candidate_24_of_24_raw_and_8_of_8_cells_3_of_3",
        "both_control_states_correct_in_both_arms",
        "candidate_improves_at_least_one_fixture_cell_in_each_target_state",
    ]
    assert gate["no_effect"] == "candidate_perfect_all_controls_correct_in_both_arms_but_two_target_state_improvement_floor_not_met"
    assert gate["no_go"] == "any_candidate_mismatch_any_control_mismatch_in_either_arm_invalid_route_or_post_response_retry"
    assert contract["promotion"] == "none_until_pass_and_independent_sol_review"


def test_gate_truth_table_is_exhaustive_and_baseline_only_control_mismatch_is_no_go():
    s = study()
    boolean_fields = (
        "candidate_all_eight_cells_3_of_3",
        "baseline_controls_all_correct",
        "candidate_controls_all_correct",
        "improved_material_failure_cell",
        "improved_missing_evidence_cell",
        "route_and_receipts_valid",
    )
    observed = set()
    for values in product((False, True), repeat=len(boolean_fields)):
        for retries in (0, 1):
            attestation = dict(zip(boolean_fields, values, strict=True))
            attestation["post_response_retries"] = retries
            if (
                not attestation["route_and_receipts_valid"]
                or retries != 0
                or not attestation["candidate_all_eight_cells_3_of_3"]
                or not attestation["baseline_controls_all_correct"]
                or not attestation["candidate_controls_all_correct"]
            ):
                expected = "NO_GO"
            elif attestation["improved_material_failure_cell"] and attestation["improved_missing_evidence_cell"]:
                expected = "PROMOTION_REVIEW_ELIGIBLE"
            else:
                expected = "NO_EFFECT"
            actual = s.classify_gate(attestation)
            observed.add(actual)
            assert actual == expected
    assert observed == {"PROMOTION_REVIEW_ELIGIBLE", "NO_EFFECT", "NO_GO"}
    baseline_only_mismatch = {
        "candidate_all_eight_cells_3_of_3": True,
        "baseline_controls_all_correct": False,
        "candidate_controls_all_correct": True,
        "improved_material_failure_cell": True,
        "improved_missing_evidence_cell": True,
        "route_and_receipts_valid": True,
        "post_response_retries": 0,
    }
    assert s.classify_gate(baseline_only_mismatch) == "NO_GO"


def test_gate_attestation_surface_and_types_fail_closed():
    s = study()
    valid = {
        "candidate_all_eight_cells_3_of_3": True,
        "baseline_controls_all_correct": True,
        "candidate_controls_all_correct": True,
        "improved_material_failure_cell": True,
        "improved_missing_evidence_cell": True,
        "route_and_receipts_valid": True,
        "post_response_retries": 0,
    }
    assert s.classify_gate(valid) == "PROMOTION_REVIEW_ELIGIBLE"
    for field in tuple(valid):
        mutation = deepcopy(valid)
        mutation.pop(field)
        with pytest.raises(ValueError, match="surface"):
            s.classify_gate(mutation)
    mutation = deepcopy(valid)
    mutation["baseline_controls_all_correct"] = 1
    with pytest.raises(ValueError, match="boolean"):
        s.classify_gate(mutation)
    mutation = deepcopy(valid)
    mutation["post_response_retries"] = True
    with pytest.raises(ValueError, match="retry"):
        s.classify_gate(mutation)


def test_contract_drift_fails_closed():
    s = study()
    contract = deepcopy(s.load_json(ROOT / "study-contract.json"))
    contract["geometry"]["slots_exact"] = 47
    original = s.load_json
    s.load_json = lambda path: contract if path.name == "study-contract.json" else original(path)
    with pytest.raises(ValueError, match="contract"):
        s.validate_public_package()


def test_private_root_validator_is_callable():
    s = study()
    assert callable(s.validate_private_root)


def test_dry_run_is_provider_free_and_only_supported_command():
    completed = historical_runtime.run_cli(study(), ROOT / "run.py", "--dry-run")
    assert completed.returncode == 0
    report = json.loads(completed.stdout)
    assert report["provider_calls"] == 0
    assert len(report["opaque_slot_ids"]) == 48
    rejected = historical_runtime.run_cli(study(), ROOT / "run.py")
    assert rejected.returncode != 0
    source = (ROOT / "run.py").read_text(encoding="utf-8").casefold()
    assert "requests" not in source and "subprocess" not in source and "dspy" not in source
