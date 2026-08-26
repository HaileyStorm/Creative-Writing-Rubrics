from __future__ import annotations

from functools import lru_cache
import importlib.util
import json
from pathlib import Path
import sys

import pytest

from hbqrs.paths import book_root
from tests import _hbq_figurative_historical_runtime as cli_runtime
from tests import _hbq_l2_historical_runtime as historical_runtime


ROOT = book_root() / "evaluation-results" / "hbq-l2-line-breaks-contextual-justification-treatment-v2"


def raw_study():
    spec = importlib.util.spec_from_file_location("l2_contextual_justification_treatment_v2", ROOT / "study.py")
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@lru_cache(maxsize=1)
def study():
    module = raw_study()
    return historical_runtime.install_source(module, source_commit=module.FREEZE_COMMIT)


def test_exact_sol_wording_and_twelve_pair_renders_only_change_question_text():
    s = study()
    assert s.CANDIDATE_TEXT == "Does each supplied line break materially strengthen its immediate poetic context through rhythm, syntax, emphasis, image, ambiguity, or pace, beyond merely creating a detectable pause, syntactic interruption, or repeated pattern?"
    canonical = s.canonical_question()["question"]["text"]
    pairs = s.render_pairs()
    assert len(pairs) * 2 == 12
    for pair in pairs.values():
        assert pair["candidate"].replace(s.CANDIDATE_TEXT, canonical, 1) == pair["canonical"]


def test_current_checkout_drift_remains_fail_closed():
    with pytest.raises(ValueError, match="Runtime binding drifted"):
        raw_study().verify_package()


def test_historical_runtime_mutation_fails_closed():
    value = study()
    path = value._historical_runtime_paths["prompts/judge/JUDGE_PREFIX.md"]
    original = path.read_bytes()
    try:
        path.write_bytes(original + b"mutation")
        with pytest.raises(ValueError, match="historical runtime bytes were mutated"):
            value.verify_package()
    finally:
        path.write_bytes(original)


def test_v2_preserves_t01_through_t05_and_replaces_t06_with_nonresonant_prose_wrap():
    s = study()
    cases = s.materialize_artifacts()
    assert cases["t01"]["text"] == "Before dawn\nthe tram rail\ngives back\nthe green of its signal."
    assert cases["t05"]["text"] == "At the quay\nthe bell answers:\nonce\nfor departure,\nonce\nfor return,\nonce\nfor the dark."
    assert cases["t06"]["text"] == "Staff logged gallery\ntemperatures before moving two sealed\ncrates to storage at closing."
    assert "gallery\ntemperatures" in cases["t06"]["text"] and "sealed\ncrates" in cases["t06"]["text"]
    assert s.load_ledger()["cells"] == {"t01": "YES", "t02": "NO", "t03": "NOT_APPLICABLE", "t04": "YES", "t05": "YES", "t06": "NO"}


def test_future_plan_is_candidate_only_six_by_three_and_package_binds_predecessors():
    s = study()
    assert s.verify_package() == {"study_id": s.STUDY_ID, "provider_calls": 0, "pair_renders": 12, "future_treatment_slots": 18}
    slots = s.plan_treatment_slots()
    assert len(slots) == 18 and {slot["leaf_id"] for slot in slots} == {s.LINE_BREAKS}
    assert s.NECESSITY not in {slot["leaf_id"] for slot in slots}
    assert s.load_contract()["bindings"]["predecessor_executor"] == s.PREDECESSOR_EXECUTOR


def test_freeze_commands_are_render_only_without_remote_images_dspy_or_promotion():
    original_path = tuple(sys.path)
    value = study()
    dry = cli_runtime.run_cli(value, ROOT / "run.py", "--dry-run")
    plan = cli_runtime.run_cli(value, ROOT / "run.py", "--render-plan")
    assert dry[0] == plan[0] == 0
    assert json.loads(dry[1])["verification"]["provider_calls"] == 0
    assert len(json.loads(plan[1])["prompt_sha256s"]) == 6
    assert tuple(sys.path) == original_path
    for path in ROOT.rglob("*"):
        if path.suffix not in {".py", ".json", ".md"}:
            continue
        text = path.read_text(encoding="utf-8").casefold()
        assert "import dspy" not in text and "from dspy" not in text and "--execute" not in text
