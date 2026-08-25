from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sys
from types import ModuleType

import pytest

from hbqrs.paths import book_root
from tests import _hbq_figurative_historical_runtime as historical_runtime
from tests._scoped_module_loader import load_module as load_scoped_module


ROOT = book_root() / "evaluation-results" / "hbq-figurative-domain-compatibility-v1"


def load_study(name: str, path: Path):
    return load_scoped_module(path, name=name)


def study():
    return historical_runtime.install(
        load_study("figurative_domain_compatibility_v1", ROOT / "study.py"),
        source_commit="c4ba06453785bdb52bce374926b65d3cab542a9a",
    )


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


def test_pinned_historical_target_runtime_rejects_mutation():
    s = study()
    historical_runtime.assert_target_mutation_is_detected(s)
    payload = (s._historical_runtime_root / "registry/modules/penalty.purple_prose.yaml").read_bytes()
    endings = []
    cursor = 0
    while cursor < len(payload):
        next_lf = payload.find(b"\n", cursor)
        if next_lf < 0:
            break
        endings.append(b"\r\n" if next_lf and payload[next_lf - 1:next_lf] == b"\r" else b"\n")
        cursor = next_lf + 1
    assert len(payload) == 5141
    assert len(endings) == 144 and endings[3] == b"\n"
    assert all(ending == b"\r\n" for index, ending in enumerate(endings) if index != 3)


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
    s = study()
    original_study = sys.modules.get("study")
    had_original_study = "study" in sys.modules
    prior_study = ModuleType("study")
    sys.modules["study"] = prior_study
    try:
        dry_code, dry_stdout, dry_stderr = historical_runtime.run_cli(s, ROOT / "run.py", "--dry-run")
        assert sys.modules["study"] is prior_study
        rendered_code, rendered_stdout, rendered_stderr = historical_runtime.run_cli(s, ROOT / "run.py", "--render")
        assert sys.modules["study"] is prior_study
    finally:
        if had_original_study:
            sys.modules["study"] = original_study
        else:
            sys.modules.pop("study", None)
    assert dry_code == rendered_code == 0, (dry_stderr, rendered_stderr)
    dry_value, rendered_value = json.loads(dry_stdout), json.loads(rendered_stdout)
    assert dry_value["provider_calls"] == 0 and dry_value["verification"]["slots"] == 144
    assert rendered_value["provider_calls"] == 0 and rendered_value["prompt_count"] == 144
