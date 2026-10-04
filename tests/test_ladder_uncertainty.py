"""Historical compatibility and effective-state uncertainty witnesses."""

from copy import deepcopy
import hashlib
import json
import os
import subprocess
import sys

import pytest

from hbqrs import HBQError
from hbqrs import scoring_v2
from hbqrs.core import compile_bundle
from hbqrs.decision_readiness import decision_readiness, interval_comparison
from hbqrs.ladder_uncertainty import POLICY, score_bundle
from hbqrs.repeatability import canonical_json_sha256
from test_scoring import _full_verdicts, _task_contract, _verdict


def _typed(records, bundle):
    for record in records:
        record["bundle_id"] = bundle["bundle_id"]
        for evidence in record["evidence"]:
            if "quote" in evidence:
                evidence["summary"] = evidence.pop("quote")
    return records


@pytest.fixture
def ladder():
    module = {
        "module_id": "synthetic.ladder",
        "tree": [{"id": f"synthetic.ladder.threshold_{i}", "type": "question",
                  "question_type": "subjective_threshold", "weight": 1,
                  "text": "Arithmetic fixture", "evidence_policy": {"required": True, "minimum_references": 1}}
                 for i in (1, 2)],
    }
    bundle = {
        "bundle_id": "synthetic.bundle", "version": 1,
        "standard": {"id": "HBQ-RS", "version": "1.2.1"},
        "domains": [{"domain_id": "holistic", "points": 100,
                     "components": [{"module_id": module["module_id"]}]}],
        "coverage_policy": {"minimum_weighted_coverage": .8},
    }
    return [module], bundle


@pytest.mark.parametrize("raw,effective,observed,bounds,coverage", [
    (("CANNOT_ASSESS", "YES"), ("CANNOT_ASSESS", "CANNOT_ASSESS"), None, (0, 100), 0),
    (("NO", "YES"), ("NO", "NO"), 0, (0, 0), 1),
    (("YES", "CANNOT_ASSESS"), ("YES", "CANNOT_ASSESS"), 100, (50, 100), .5),
    (("NOT_APPLICABLE", "YES"), ("NOT_APPLICABLE", "CANNOT_ASSESS"), None, (0, 100), 0),
    (("NOT_APPLICABLE", "NOT_APPLICABLE"), ("NOT_APPLICABLE", "NOT_APPLICABLE"), None, (None, None), 0),
    (("YES", "YES"), ("YES", "YES"), 100, (100, 100), 1),
])
def test_arithmetic_states_preserve_parent_and_project_consistently(ladder, raw, effective, observed, bounds, coverage):
    modules, bundle = ladder
    records = _typed([_verdict(f"synthetic.ladder.threshold_{i}", state) for i, state in enumerate(raw, 1)], bundle)
    originals = deepcopy((modules, bundle, records))
    result = score_bundle(modules, bundle, records)
    parent, candidate = result["historical_report"], result["candidate_report"]
    assert parent == scoring_v2.score_bundle(modules, bundle, records, admission_policy="strict_import_v1")
    assert (modules, bundle, records) == originals
    assert tuple(row["verdict"] for row in candidate["domains"][0]["questions"]) == effective
    assert candidate["final_score"] == {"observed": observed, "lower": bounds[0], "upper": bounds[1]}
    assert candidate["coverage"] == coverage
    assert candidate["status"] == ("SCORED" if coverage == 1 else "PROVISIONAL")
    assert not any("Subjective ladder" in issue for issue in candidate["issues"])
    lineage = candidate["ladder_projection"]
    assert lineage["raw_verdicts_sha256"] == canonical_json_sha256(records)
    assert lineage["historical_parent_report_sha256"] == canonical_json_sha256(parent)
    assert candidate["scoring_context"]["compiled_bundle_sha256"] == canonical_json_sha256(compile_bundle(modules, bundle))
    if raw == ("CANNOT_ASSESS", "YES"):
        assert parent["final_score"] == {"observed": 0, "lower": 0, "upper": 50}
        assert parent["coverage"] == .5
        assert lineage["changes"] == [{
            "question_id": "synthetic.ladder.threshold_2", "module_id": "synthetic.ladder",
            "raw_state": "YES", "effective_state": "CANNOT_ASSESS",
            "reason": "unavailable_lower_prerequisite",
            "blocking_question_ids": ["synthetic.ladder.threshold_1"],
        }]


def test_omitted_prerequisite_is_uncertainty_not_a_synthetic_failure(ladder):
    modules, bundle = ladder
    records = _typed([_verdict("synthetic.ladder.threshold_2")], bundle)
    before = deepcopy(records)
    result = score_bundle(modules, bundle, records)
    candidate = result["candidate_report"]
    assert candidate["final_score"] == {"observed": None, "lower": 0, "upper": 100}
    assert candidate["coverage"] == 0
    assert candidate["import_admission"]["omitted_questions"] == 1
    assert candidate["ladder_projection"]["changes"][0]["blocking_question_ids"] == ["synthetic.ladder.threshold_1"]
    assert any("Missing verdict" in issue for issue in candidate["issues"])
    assert records == before


def test_explicit_no_dominates_an_earlier_unavailable_prerequisite(ladder):
    modules, bundle = ladder
    third = deepcopy(modules[0]["tree"][1])
    third["id"] = "synthetic.ladder.threshold_3"
    modules[0]["tree"].append(third)
    records = _typed([_verdict(f"synthetic.ladder.threshold_{i}", state)
                      for i, state in enumerate(("CANNOT_ASSESS", "NO", "YES"), 1)], bundle)
    candidate = score_bundle(modules, bundle, records)["candidate_report"]
    change = candidate["ladder_projection"]["changes"][0]
    assert change["effective_state"] == "NO"
    assert change["reason"] == "explicit_lower_no"
    assert change["blocking_question_ids"] == ["synthetic.ladder.threshold_2"]
    assert [row["verdict"] for row in candidate["domains"][0]["questions"]] == ["CANNOT_ASSESS", "NO", "NO"]


def test_default_admission_checks_original_yes_before_projection(ladder):
    modules, bundle = ladder
    records = _typed([_verdict("synthetic.ladder.threshold_1", "CANNOT_ASSESS"),
                      _verdict("synthetic.ladder.threshold_2")], bundle)
    records[1]["evidence"] = []
    before = deepcopy(records)
    with pytest.raises(HBQError, match="requires 1 evidence"):
        score_bundle(modules, bundle, records)
    assert records == before
    permissive = score_bundle(modules, bundle, records, admission_policy="historical_permissive_v1")
    assert permissive["candidate_report"]["final_score"]["observed"] is None
    assert "import_admission" not in permissive["historical_report"]


def test_actual_scene_ladder_preserves_other_roles_and_raw_lineage(modules, bundle_by_id):
    bundle = bundle_by_id["prose.scene"]
    compiled, records = _full_verdicts(modules, bundle)
    thresholds = [row["question"]["id"] for row in compiled["domain_questions"]
                  if row["question"]["question_type"] == "subjective_threshold"]
    next(row for row in records if row["question_id"] == thresholds[0]).update(_verdict(thresholds[0], "CANNOT_ASSESS"))
    _typed(records, bundle)
    before = deepcopy((modules, bundle, records))
    result = score_bundle(modules, bundle, records)
    parent, candidate = result["historical_report"], result["candidate_report"]
    holistic = next(group for group in candidate["domains"] if group["domain_id"] == "holistic")
    assert holistic["score"] == {"observed": None, "lower": 0, "upper": 8}
    assert [row["verdict"] for row in holistic["questions"]] == ["CANNOT_ASSESS"] * 4
    assert candidate["final_score"] == {"observed": 100, "lower": 92, "upper": 100}
    assert candidate["coverage"] == .92
    assert candidate["status"] == "SCORED"
    assert not decision_readiness(candidate)["fully_assessed_point_score"]
    assert len(candidate["ladder_projection"]["changes"]) == 3
    assert candidate["confidence_diagnostics"]["roles"]["domain"]["assessed_count"] == parent["confidence_diagnostics"]["roles"]["domain"]["assessed_count"] - 3
    for field in ("hard_gates", "hard_gate_status", "penalties", "penalty_deduction", "supplemental", "import_admission"):
        assert candidate[field] == parent[field]
    assert [group for group in candidate["domains"] if group["domain_id"] != "holistic"] == [group for group in parent["domains"] if group["domain_id"] != "holistic"]
    assert (modules, bundle, records) == before


def test_full_task_contract_content_is_committed_even_when_summary_is_identical(modules, bundle_by_id):
    bundle = bundle_by_id["prose.scene"]
    contract = _task_contract()
    _, records = _full_verdicts(modules, bundle, task_contract=contract)
    _typed(records, bundle)
    before = deepcopy(contract)
    first = score_bundle(modules, bundle, records, task_contract=contract)["candidate_report"]
    assert first["scoring_context"]["task_contract_sha256"] == canonical_json_sha256(contract)
    assert contract == before
    other_contract = deepcopy(contract)
    other_contract["weighted_goals"][0]["source"]["exact_excerpt"] = "Different original contract content."
    second = score_bundle(modules, bundle, records, task_contract=other_contract)["candidate_report"]
    assert first["task_contract"] == second["task_contract"]
    assert first["scoring_context"] != second["scoring_context"]
    compared = interval_comparison(first, second, comparison_context_sha256="a" * 64)
    assert compared["relation"] == "INCOMPARABLE"
    assert compared["reason"] == "scoring_context_commitments_differ"


def test_real_module_cli_emits_separate_reports_and_exact_file_hashes(modules, bundle_by_id, tmp_path):
    bundle = bundle_by_id["prose.scene"]
    contract = _task_contract()
    _, records = _full_verdicts(modules, bundle, task_contract=contract)
    _typed(records, bundle)
    source, contract_file = tmp_path / "verdicts.jsonl", tmp_path / "contract.json"
    source.write_text("\n".join(json.dumps(row) for row in records) + "\n", encoding="utf-8")
    contract_file.write_text(json.dumps(contract), encoding="utf-8")
    before = (source.read_bytes(), contract_file.read_bytes())
    run = subprocess.run(
        [sys.executable, "-m", "hbqrs.ladder_uncertainty", bundle["bundle_id"], str(source),
         "--task-contract", str(contract_file)], capture_output=True, text=True, check=True,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    output = json.loads(run.stdout)
    assert output["candidate_report"]["scoring_policy"] == POLICY
    assert "scoring_policy" not in output["historical_report"]
    assert output["inputs"] == {
        "verdicts_file_sha256": hashlib.sha256(before[0]).hexdigest(),
        "task_contract_file_sha256": hashlib.sha256(before[1]).hexdigest(),
    }
    assert (source.read_bytes(), contract_file.read_bytes()) == before
