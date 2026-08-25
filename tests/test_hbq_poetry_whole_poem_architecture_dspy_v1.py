from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys

import pytest

from hbqrs.paths import book_root


PACKAGE = book_root() / "evaluation-results" / "hbq-poetry-whole-poem-architecture-dspy-v1"


def study():
    spec = importlib.util.spec_from_file_location("whole_poem_architecture_dspy_v1", PACKAGE / "study.py")
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_provider_free_contract_has_exact_development_and_transfer_geometry() -> None:
    module = study()
    assert module.verify_package() == {
        "study_id": "hbq-poetry-whole-poem-architecture-dspy-v1",
        "status": "FROZEN_PROVIDER_FREE",
        "provider_calls": 0,
        "train_cases": 12,
        "dev_cases": 8,
        "transfer_calls": 16,
    }
    contract = module.load_contract()
    assert contract["optimizer"] == {
        "kind": "MIPROv2",
        "program": "Predict",
        "instruction_only": True,
        "demos_exact": 0,
        "bootstrap": "overridden_to_none",
        "data_aware_proposer": False,
        "fewshot_aware_proposer": False,
        "auto": None,
        "seed": 20260825,
        "num_candidates": 4,
        "num_trials": 4,
        "threads": 1,
        "retries": 0,
        "physical_compile_send_cap": 64,
    }
    assert contract["promotion"]["on_transfer_pass"] == "candidate_for_manual_review_only"
    assert all(value == "none" for key, value in contract["promotion"].items() if key != "on_transfer_pass")


def test_public_synthetic_cases_are_disjoint_four_state_and_replace_disputed_negatives() -> None:
    module = study()
    cases = module.load_corpus()["cases"]
    assert len(cases) == 20
    assert sum(case["split"] == "TRAIN" for case in cases) == 12
    assert sum(case["split"] == "DEV" for case in cases) == 8
    assert {case["expected_verdict"] for case in cases} == module.VERDICTS
    assert len({case["case_id"] for case in cases}) == len({case["text"] for case in cases}) == 20
    descendants = [case for case in cases if case["fixture_origin"] == "new_public_synthetic_clear_descendant"]
    assert len(descendants) == 6
    assert {case["case_id"] for case in descendants} == {
        "train_clear_ending_only_descendant",
        "train_clear_progression_only_descendant",
        "train_clear_contrast_only_descendant",
        "dev_clear_ending_only_descendant",
        "dev_clear_progression_only_descendant",
        "dev_clear_contrast_only_descendant",
    }
    assert module.load_corpus()["future_holdout"] is False


def test_metric_requires_exact_state_and_a_real_artifact_span() -> None:
    module = study()
    assert module.validate_grounded_four_state(expected="YES", observed="YES", evidence="a real relation", artifact_text="a real relation appears")
    assert not module.validate_grounded_four_state(expected="YES", observed="NO", evidence="a real relation", artifact_text="a real relation appears")
    with pytest.raises(ValueError, match="Grounding"):
        module.validate_grounded_four_state(expected="YES", observed="YES", evidence="invented", artifact_text="a real relation appears")


def test_static_export_is_short_instruction_only_and_public_package_has_no_dspy_import() -> None:
    text = (PACKAGE / "static-export.txt").read_text(encoding="utf-8")
    assert 0 < len(text.split()) <= 180
    words = set(re.findall(r"[A-Za-z_]+", text.casefold()))
    assert not words & {"yes", "no", "not_applicable", "cannot_assess", "train", "dev", "fixture", "runtime", "model", "call", "retry", "prompt"}
    for path in PACKAGE.iterdir():
        if path.suffix in {".py", ".json", ".md", ".txt"}:
            contents = path.read_text(encoding="utf-8")
            assert "import dspy" not in contents and "from dspy" not in contents


def test_dry_run_is_provider_free_and_transfer_plan_is_exact() -> None:
    completed = subprocess.run([sys.executable, str(PACKAGE / "run.py"), "--dry-run"], text=True, capture_output=True, check=True)
    value = json.loads(completed.stdout)
    assert value["mode"] == "dry_run"
    assert value["verification"]["provider_calls"] == 0
    transfer = study().production_transfer_plan()
    assert len(transfer) == len({slot["slot_id"] for slot in transfer}) == 16
    assert {slot["pass"] for slot in transfer} == {1, 2}
