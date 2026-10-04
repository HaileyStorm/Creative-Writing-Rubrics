"""Behavioral proof for opt-in score completeness and interval decisions."""

from copy import deepcopy
import hashlib
import json
import os
import subprocess
import sys

import pytest

from hbqrs import HBQError, score_bundle
from hbqrs.core import score_bundle as score_bundle_v1
from hbqrs.decision_readiness import decision_readiness, interval_comparison
from test_scoring import _full_verdicts, _task_contract, _verdict


@pytest.fixture
def report(modules, bundle_by_id):
    bundle = bundle_by_id["prose.short_story"]
    _, verdicts = _full_verdicts(modules, bundle)
    return score_bundle_v1(modules, bundle, verdicts)


def test_real_unknown_penalties_are_not_a_fully_assessed_point(modules, bundle_by_id):
    bundle = bundle_by_id["prose.short_story"]
    compiled, verdicts = _full_verdicts(modules, bundle)
    penalties = {row["question"]["id"] for group in compiled["penalty_groups"] for row in group["questions"]}
    for record in verdicts:
        if record["question_id"] in penalties:
            record.update(_verdict(record["question_id"], "CANNOT_ASSESS"))
    for scorer in (score_bundle_v1, score_bundle):
        scored = scorer(modules, bundle, verdicts)
        before = deepcopy(scored)
        scored["retained_digest"] = "original-digest"
        before["retained_digest"] = "original-digest"
        result = decision_readiness(scored, threshold=90)
        assert scored == before
        assert scored["status"] == "SCORED"
        assert scored["final_score"] == {"observed": 100, "lower": 82, "upper": 100}
        assert result["positive"]["weighted_coverage"] == 1
        assert result["positive"]["complete"]
        assert result["penalties"]["assessed_coverage"] == 0
        assert not result["penalties"]["complete"]
        assert result["scalar_interval"]["width"] == 18
        assert not result["fully_assessed_point_score"]
        assert result["threshold"]["relation"] == "UNRESOLVED"


def test_fully_assessed_and_clamped_incomplete_are_distinct(report):
    ready = decision_readiness(report)
    assert ready["fully_assessed_point_score"]
    # Clamping may erase interval width without assessing the missing verdict.
    report["final_score"] = {"observed": 0, "lower": 0, "upper": 0}
    report["penalties"][0]["questions"][0]["verdict"] = "CANNOT_ASSESS"
    result = decision_readiness(report)
    assert result["scalar_interval"]["width"] == 0
    assert not result["fully_assessed"]
    assert not result["fully_assessed_point_score"]


def test_na_and_supplements_do_not_create_scalar_missingness(report):
    report["penalties"][0]["questions"][0]["verdict"] = "NOT_APPLICABLE"
    for row in report["supplemental"]:
        row["verdict"] = "CANNOT_ASSESS"
    assert decision_readiness(report)["fully_assessed_point_score"]


def test_positive_incompleteness_survives_rounded_coverage(report):
    report["domains"][0]["questions"][0]["verdict"] = "CANNOT_ASSESS"
    report["domains"][0]["questions"][0]["weight"] = 0
    report["coverage"] = 1
    result = decision_readiness(report)
    assert not result["positive"]["complete"]
    assert not result["fully_assessed_point_score"]


def test_missing_bundle_revision_cannot_establish_compatibility(report):
    del report["bundle_version"]
    result = interval_comparison(report, report)
    assert result["relation"] == "INCOMPARABLE"
    assert result["reason"] == "report_scoring_context_incomplete"


@pytest.mark.parametrize("change,reason", [
    ("policy", "scoring_policy_differs"),
    ("compiled", "scoring_context_commitments_differ"),
    ("contract", "scoring_context_commitments_differ"),
])
def test_scoring_policy_and_context_commitments_precede_ordering(report, change, reason):
    report["scoring_policy"] = "uncertainty_preserving_ladder_v1"
    report["scoring_context"] = {"compiled_bundle_sha256": "a" * 64, "task_contract_sha256": None}
    other = deepcopy(report)
    other["final_score"] = {"observed": 0, "lower": 0, "upper": 0}
    if change == "policy":
        del other["scoring_policy"]
        del other["scoring_context"]
    elif change == "compiled":
        other["scoring_context"]["compiled_bundle_sha256"] = "b" * 64
    else:
        other["scoring_context"]["task_contract_sha256"] = "c" * 64
    result = interval_comparison(report, other, comparison_context_sha256="d" * 64)
    assert result["relation"] == "INCOMPARABLE"
    assert result["reason"] == reason


def test_equal_scoring_commitments_still_allow_separated_order(report):
    report["scoring_policy"] = "uncertainty_preserving_ladder_v1"
    report["scoring_context"] = {"compiled_bundle_sha256": "a" * 64, "task_contract_sha256": None}
    other = deepcopy(report)
    other["final_score"] = {"observed": 0, "lower": 0, "upper": 0}
    assert interval_comparison(report, other)["relation"] == "LEFT_ABOVE"


def test_declared_successor_without_context_cannot_establish_compatibility(report):
    report["scoring_policy"] = "uncertainty_preserving_ladder_v1"
    result = interval_comparison(report, report)
    assert result["relation"] == "INCOMPARABLE"
    assert result["reason"] == "declared_scoring_policy_context_incomplete"


@pytest.mark.parametrize("state,gate", [("NO", "INVALID"), ("CANNOT_ASSESS", "UNRESOLVED")])
def test_actual_dynamic_hard_gates_override_scalar_readiness(modules, bundle_by_id, state, gate):
    bundle = bundle_by_id["prose.short_story"]
    contract = _task_contract()
    compiled, verdicts = _full_verdicts(modules, bundle, task_contract=contract)
    qid = compiled["task_contract"]["binding_requirement_ids"][0]
    next(record for record in verdicts if record["question_id"] == qid).update(_verdict(qid, state))
    scored = score_bundle_v1(modules, bundle, verdicts, task_contract=contract)
    before = deepcopy(scored)
    result = decision_readiness(scored, threshold=0)
    assert result["hard_gate_status"] == gate
    assert not result["eligible"]
    assert not result["fully_assessed_point_score"]
    assert interval_comparison(scored, scored)["relation"] == "INELIGIBLE"
    assert scored == before


@pytest.mark.parametrize("bounds,threshold,relation", [
    ((82, 100), 82, "ROBUSTLY_MEETS"),
    ((82, 100), 100, "UNRESOLVED"),
    ((82, 99), 100, "ROBUSTLY_BELOW"),
    ((100, 100), 100, "ROBUSTLY_MEETS"),
])
def test_inclusive_threshold_boundaries(report, bounds, threshold, relation):
    report["final_score"] = {"observed": bounds[1], "lower": bounds[0], "upper": bounds[1]}
    result = decision_readiness(report, threshold=threshold)
    assert result["threshold"]["convention"] == "score >= threshold"
    assert result["threshold"]["relation"] == relation


@pytest.mark.parametrize("left_bounds,right_bounds,relation", [
    ((82, 100), (70, 81), "LEFT_ABOVE"),
    ((70, 81), (82, 100), "RIGHT_ABOVE"),
    ((82, 100), (70, 82), "INCONCLUSIVE"),
    ((82, 100), (90, 95), "INCONCLUSIVE"),
    ((90, 90), (90, 90), "INCONCLUSIVE"),
])
def test_strict_interval_comparison_preserves_reports(report, left_bounds, right_bounds, relation):
    other = deepcopy(report)
    report["final_score"] = dict(zip(("observed", "lower", "upper"), (left_bounds[1], *left_bounds)))
    other["final_score"] = dict(zip(("observed", "lower", "upper"), (right_bounds[1], *right_bounds)))
    before = deepcopy((report, other))
    result = interval_comparison(report, other)
    assert result["relation"] == relation
    assert result["full_context_attestation"] == "not_established"
    assert (report, other) == before


@pytest.mark.parametrize("change", ["bundle", "version", "weight", "scope", "contract"])
def test_context_mismatch_cannot_establish_order(report, change):
    other = deepcopy(report)
    other["final_score"] = {"observed": 0, "lower": 0, "upper": 0}
    if change == "bundle":
        other["bundle_id"] = "other-bundle"
    elif change == "version":
        other["bundle_version"] = "other-version"
    elif change == "weight":
        other["domains"][0]["questions"][0]["weight"] *= 2
    elif change == "scope":
        other["domains"][0]["questions"][0]["verdict"] = "NOT_APPLICABLE"
    else:
        other["task_contract"] = {"contract_id": "other-contract"}
    assert interval_comparison(report, other)["relation"] == "INCOMPARABLE"


def test_dynamic_contract_metadata_needs_external_frozen_context(modules, bundle_by_id):
    bundle = bundle_by_id["prose.short_story"]
    contract = _task_contract()
    _, verdicts = _full_verdicts(modules, bundle, task_contract=contract)
    left = score_bundle_v1(modules, bundle, verdicts, task_contract=contract)
    right = deepcopy(left)
    right["final_score"] = {"observed": 0, "lower": 0, "upper": 0}
    assert interval_comparison(left, right)["relation"] == "INCOMPARABLE"
    attested = interval_comparison(left, right, comparison_context_sha256="a" * 64)
    assert attested["relation"] == "LEFT_ABOVE"
    assert attested["full_context_attestation"] == "caller_supplied_shared_digest"
    with pytest.raises(HBQError, match="SHA-256"):
        interval_comparison(left, right, comparison_context_sha256="invalid")


def test_absent_scalar_is_unavailable(report):
    report["final_score"] = {"observed": None, "lower": None, "upper": None}
    assert decision_readiness(report, threshold=50)["threshold"]["relation"] == "UNAVAILABLE"
    assert interval_comparison(report, report)["reason"] == "observed_scalar_unavailable"


def test_actual_provisional_report_cannot_establish_separated_order(modules, bundle_by_id, report):
    bundle = bundle_by_id["prose.short_story"]
    compiled, verdicts = _full_verdicts(modules, bundle)
    domain_ids = {row["question"]["id"] for row in compiled["domain_questions"]}
    first = compiled["domain_questions"][0]["question"]["id"]
    for record in verdicts:
        if record["question_id"] in domain_ids:
            state = "NO" if record["question_id"] == first else "CANNOT_ASSESS"
            record.update(_verdict(record["question_id"], state))
    partial = score_bundle_v1(modules, bundle, verdicts)
    assert partial["status"] == "PROVISIONAL"
    assert partial["hard_gate_status"] == "VALID"
    assert partial["final_score"]["upper"] < report["final_score"]["lower"]
    result = interval_comparison(report, partial)
    assert result["relation"] == "INCONCLUSIVE"
    assert result["reason"] == "report_status_not_scored"


def test_unavailable_observed_scalar_cannot_establish_separated_order(report):
    other = deepcopy(report)
    other["final_score"] = {"observed": None, "lower": 0, "upper": 10}
    result = interval_comparison(report, other)
    assert result["relation"] == "INCONCLUSIVE"
    assert result["reason"] == "observed_scalar_unavailable"


@pytest.mark.parametrize("field,value", [
    ("penalties", None), ("coverage", float("nan")), ("coverage", True),
    ("hard_gate_status", "UNKNOWN"),
    ("final_score", {"observed": 10, "lower": 20, "upper": 10}),
    ("final_score", {"observed": None, "lower": None, "upper": 20}),
])
def test_malformed_required_fields_fail_clearly(report, field, value):
    report[field] = value
    with pytest.raises(HBQError):
        decision_readiness(report)


def test_real_module_entry_reads_without_rewriting(report, tmp_path):
    source = tmp_path / "report.json"
    source.write_text(json.dumps(report), encoding="utf-8")
    before = source.read_bytes()
    run = subprocess.run(
        [sys.executable, "-m", "hbqrs.decision_readiness", str(source),
         "--compare", str(source), "--threshold", "100"],
        capture_output=True, text=True, check=True,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    output = json.loads(run.stdout)
    assert output["readiness"]["policy"] == "descriptive_decision_readiness_v1"
    assert output["readiness"]["threshold"]["relation"] == "ROBUSTLY_MEETS"
    assert output["comparison"]["relation"] == "INCONCLUSIVE"
    assert output["report_sha256"] == hashlib.sha256(before).hexdigest()
    assert output["comparison_report_sha256"] == hashlib.sha256(before).hexdigest()
    assert source.read_bytes() == before
