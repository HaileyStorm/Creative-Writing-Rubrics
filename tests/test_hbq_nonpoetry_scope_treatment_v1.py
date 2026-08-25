from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from copy import deepcopy

import pytest
from hbqrs.paths import book_root
from tests import _hbq_s2_historical_runtime as historical_runtime

ROOT = book_root() / "evaluation-results" / "hbq-nonpoetry-scope-treatment-v1"


def study():
    spec = importlib.util.spec_from_file_location("npsst", ROOT / "study.py")
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    try:
        return historical_runtime.install(module, source_commit="c4ba06453785bdb52bce374926b65d3cab542a9a")
    except historical_runtime.HistoricalRuntimeUnbound as exc:
        pytest.skip(f"historical runtime unbound: {exc}")


def test_plan_has_exact_minimum_geometry_and_immutable_reuse_only():
    s = study()
    assert s.validate_package()["new_provider_calls_planned"] == 27
    plan = s.build_plan()
    reused = [row for row in plan if "reuse" in row]
    new = [row for row in plan if "reuse" not in row]
    assert len(plan) == 33 and len(reused) == 6 and len(new) == 27
    assert {row["state"] for row in reused} == {"material_failure", "activation_mismatch"}
    assert {row["reuse"]["predecessor_slot_id"] for row in reused} == {f"npssexec-v1-{ordinal:02d}-r{repeat}" for ordinal in (18, 20) for repeat in range(1, 4)}
    assert {row["reuse"]["immutable_condition"] for row in reused} == {"same public fixture bytes, current production wording, source leaf, and singleton route; only those six accepted calls may be reused"}
    assert sum(row["leaf_id"] == "scope.passage.status" for row in new) == 18
    assert sum(row["leaf_id"] != "scope.passage.status" for row in new) == 9


def test_candidate_preserves_identity_owner_and_influence():
    s = study()
    source = s.source_status_leaf()
    candidate = next(row["question"] for row in s.build_plan() if row["arm"] == "candidate_wording")
    assert candidate["text"] == s.STATUS_CANDIDATE
    for key in ("id", "module_id", "criterion_key", "pass_answer", "weight", "question_type", "severity"):
        assert candidate[key] == source[key]


def test_exact_five_corrections_and_sealed_holdout_boundary():
    s = study()
    fixtures = s.corrected_fixtures()
    assert tuple(fixtures) == s.CORRECTED_FIXTURE_IDS
    assert "performed transition" in fixtures["npsst-tone-local"]["contexts"][0]
    assert "explicitly active" in fixtures["npsst-tone-unknown"]["contexts"][0]
    assert "unknown" in fixtures["npsst-critique-unknown"]["contexts"][0]
    assert fixtures["npsst-passage-unknown"]["declared_scope"] == "excerpt from a novel"
    assert "explicitly exempts" in fixtures["npsst-passage-local"]["text"]
    holdout = json.loads((ROOT / "private-four-state-holdout-contract.json").read_text(encoding="utf-8"))
    s.validate_holdout(holdout)
    assert holdout["visibility"] == "private_external_only"


def test_contract_mutations_fail_closed():
    s = study()
    contract = s.load_json("study-contract.json")
    broken = deepcopy(contract)
    broken["provider_execution"]["new_provider_calls_exact"] = 25
    with pytest.raises(ValueError, match="Provider boundary"):
        original = s.load_json
        s.load_json = lambda name: broken if name == "study-contract.json" else original(name)
        try:
            s.validate_package()
        finally:
            s.load_json = original


def test_provider_free_dry_run_and_render_plan():
    s = study()
    completed = historical_runtime.run_cli(s, ROOT / "run.py", "--dry-run")
    assert completed.returncode == 0
    report = json.loads(completed.stdout)
    assert report["provider_calls"] == 0 and report["verification"]["new_provider_calls_planned"] == 27
    rendered = historical_runtime.run_cli(s, ROOT / "run.py", "--render-plan")
    assert rendered.returncode == 0
    output = json.loads(rendered.stdout)
    assert output["provider_calls"] == 0 and len(output["rendered_slots"]) == 33
    verifier = historical_runtime.run_cli(s, ROOT / "verify_output.py")
    assert verifier.returncode == 0
    assert json.loads(verifier.stdout)["sealed_private_holdout"] is True
