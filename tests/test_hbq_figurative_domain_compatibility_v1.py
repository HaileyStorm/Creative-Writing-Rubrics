from __future__ import annotations

from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest

from hbqrs.paths import book_root


ROOT = book_root() / "evaluation-results" / "hbq-figurative-domain-compatibility-v1"


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
    return load_module("figurative_domain_compatibility_v1", ROOT / "study.py")


def test_frozen_public_geometry_is_exact_and_provider_free():
    report = study().verify_public_package()
    assert report == {
        "study_id": "hbq-figurative-domain-compatibility-v1",
        "provider_calls": 0,
        "public_fixtures": 8,
        "slots": 144,
        "sealed_holdout_content_opened": False,
    }
    contract = json.loads((ROOT / "study-contract.json").read_text(encoding="utf-8"))
    assert contract["leaves"] == {
        "target": "penalty.purple_prose.metaphor",
        "controls": ["core.freshness_and_non_genericness.no_default_metaphors", "penalty.purple_prose.proportion"],
    }
    assert contract["provider_execution"] == {"permitted": False, "new_provider_calls_exact": 0, "one_leaf_per_request": True}
    assert contract["stop_gate"]["both_arms_perfect"] == "NO_GO"
    assert contract["stop_gate"]["single_fixture_gain"] == "NO_GO"


def test_grid_oracles_are_orthogonal_and_mutation_fails_closed(monkeypatch):
    s = study()
    corpus = s.load_corpus()
    labels = s.load_labels()
    assert len(corpus["fixtures"]) == 8
    assert len(labels["expected_verdicts"]) == 8
    mutated = deepcopy(labels)
    mutated["expected_verdicts"]["dev-compete-specific-charged"]["penalty.purple_prose.metaphor"] = "YES"
    monkeypatch.setattr(s, "load_labels", lambda: mutated)
    with pytest.raises(ValueError, match="Orthogonal construction oracle drifted"):
        s.verify_corpus(corpus)


def test_expected_labels_never_render_and_leaf_aid_stays_target_only():
    s = study()
    slots = s.plan_slots()
    assert len(slots) == 144
    target_treatment = next(slot for slot in slots if slot["arm"] == "p1_appendix_plus_leaf_aid" and slot["leaf_id"] == s.TARGET)
    target_baseline = next(slot for slot in slots if slot["arm"] == "p1_appendix_only" and slot["case_id"] == target_treatment["case_id"] and slot["leaf_id"] == s.TARGET and slot["repeat"] == target_treatment["repeat"])
    control_treatment = next(slot for slot in slots if slot["arm"] == "p1_appendix_plus_leaf_aid" and slot["case_id"] == target_treatment["case_id"] and slot["leaf_id"] == s.CONTROLS[0] and slot["repeat"] == target_treatment["repeat"])
    treated_prompt = s.render_provider_prompt(target_treatment["slot_id"])
    baseline_prompt = s.render_provider_prompt(target_baseline["slot_id"])
    control_prompt = s.render_provider_prompt(control_treatment["slot_id"])
    assert s.P1_APPENDIX in baseline_prompt and s.P1_APPENDIX in treated_prompt and s.P1_APPENDIX in control_prompt
    assert s.LEAF_AID in treated_prompt
    assert s.LEAF_AID not in baseline_prompt and s.LEAF_AID not in control_prompt
    assert "expected_verdicts" not in treated_prompt
    assert target_treatment["case_id"] not in treated_prompt


def test_dry_run_and_render_are_provider_free():
    dry = subprocess.run([sys.executable, str(ROOT / "run.py"), "--dry-run"], text=True, capture_output=True, check=True)
    rendered = subprocess.run([sys.executable, str(ROOT / "run.py"), "--render"], text=True, capture_output=True, check=True)
    dry_value, rendered_value = json.loads(dry.stdout), json.loads(rendered.stdout)
    assert dry_value["provider_calls"] == 0 and dry_value["verification"]["slots"] == 144
    assert rendered_value["provider_calls"] == 0 and rendered_value["prompt_count"] == 144
