from __future__ import annotations

import importlib.util
import json
from functools import lru_cache
from pathlib import Path
import sys

import pytest

from hbqrs.paths import book_root
from tests import _hbq_figurative_historical_runtime as cli_runtime
from tests import _hbq_l2_historical_runtime as historical_runtime


ROOT = book_root() / "evaluation-results" / "hbq-l2-line-breaks-contextual-justification-treatment-v1"


def raw_study():
    spec = importlib.util.spec_from_file_location("l2_contextual_justification_treatment_v1", ROOT / "study.py")
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@lru_cache(maxsize=1)
def study():
    module = raw_study()
    return historical_runtime.install_source(module, source_commit=module.EXECUTOR["commit"])


def test_exact_sol_candidate_is_the_only_question_delta_across_twelve_renders():
    s = study()
    assert s.CANDIDATE_TEXT == "Does each supplied line break make a controlled, legible, and contextually justified contribution to rhythm, syntax, emphasis, image, ambiguity, or pace? A detectable pause, syntactic interruption, or repeated pattern alone is not enough; YES evidence must explain what the break contributes in its immediate context."
    pairs = s.render_pairs()
    assert len(pairs) == 6
    canonical = s.canonical_question()["question"]["text"]
    assert len(canonical) < len(s.CANDIDATE_TEXT)
    for pair in pairs.values():
        assert pair["candidate"].count(s.CANDIDATE_TEXT) == 1
        assert pair["canonical"].count(canonical) == 1
        assert pair["candidate"].replace(s.CANDIDATE_TEXT, canonical, 1) == pair["canonical"]


def test_current_checkout_drift_remains_fail_closed():
    with pytest.raises(ValueError, match="Pinned production runtime bytes drifted"):
        raw_study().verify_package()


def test_treatment_only_plan_is_six_line_break_cells_by_three_without_necessity():
    s = study()
    slots = s.plan_treatment_slots()
    assert len(slots) == len({slot["slot_id"] for slot in slots}) == 18
    assert {slot["case_id"] for slot in slots} == set(s.CASE_IDS)
    assert {slot["repeat"] for slot in slots} == {1, 2, 3}
    assert {slot["leaf_id"] for slot in slots} == {s.LINE_BREAKS}
    assert s.NECESSITY not in {slot["leaf_id"] for slot in slots}
    assert s.source_leaf_hashes()[s.NECESSITY] == s.COMPILED_LEAF_HASHES[s.NECESSITY]


def test_reused_frozen_cases_and_fresh_positive_negative_are_protected():
    s = study()
    cases = s.materialize_artifacts()
    assert cases["t01"]["text"] == "Before dawn\nthe tram rail\ngives back\nthe green of its signal."
    assert cases["t02"]["text"] == "Clerks archived the\nminutes beneath the\ncabinet after the\nnoon delivery."
    assert cases["t03"]["text"] == "The mineral exhibit dimmed behind its glass at closing."
    assert cases["t04"]["text"] == "A narrow moon hangs white above the lane;\nthe last bus leaves, and leaves the rain again."
    assert cases["t05"]["text"] == "At the quay\nthe bell answers:\nonce\nfor departure,\nonce\nfor return,\nonce\nfor the dark."
    assert cases["t06"]["text"] == "At closing, staff recorded gallery temperatures\nbefore wheeling two sealed crates through the service\ndoor."
    assert "the\n" not in cases["t06"]["text"] and "a\n" not in cases["t06"]["text"]
    assert s.load_ledger()["cells"] == {"t01": "YES", "t02": "NO", "t03": "NOT_APPLICABLE", "t04": "YES", "t05": "YES", "t06": "NO"}


def test_public_result_executor_freeze_runtime_and_compiled_leaf_bindings_are_exact():
    s = study()
    s.verify_bindings()
    contract = s.load_contract()
    assert contract["bindings"]["public_result"] == s.PUBLIC_RESULT
    assert contract["bindings"]["executor"] == s.EXECUTOR
    assert contract["bindings"]["freeze"] == s.FREEZE
    assert contract["bindings"]["runtime"] == s.RUNTIME
    assert contract["bindings"]["compiled_source_leaves"] == s.COMPILED_LEAF_HASHES
    assert s.PUBLIC_RESULT["commit"].startswith("f1dd530")
    assert s.EXECUTOR["commit"].startswith("b7a3f8e")


def test_rendered_prompts_are_blind_to_ledger_variant_and_holdout_metadata():
    s = study()
    rendered = "\n".join(prompt for pair in s.render_pairs().values() for prompt in pair.values()).casefold()
    for forbidden in ("expected-ledger", "ledger", "baseline", "treatment", "holdout", "arm", "t01", "t02", "t03", "t04", "t05", "t06"):
        assert forbidden not in rendered
    assert "necessity" not in rendered


def test_package_is_freeze_only_without_images_remote_execution_dspy_or_promotion():
    s = study()
    assert s.verify_package() == {"study_id": s.STUDY_ID, "status": "frozen_provider_free_contextual_justification_treatment", "new_remote_calls": 0, "pair_renders": 12, "future_treatment_slots": 18}
    contract = s.load_contract()
    assert contract["scope"] == {"necessity": "excluded_from_pairs_and_future_treatment_but_bound_unchanged", "images": "forbidden", "remote_contact": "forbidden", "dspy": "forbidden", "promotion": "none"}
    original_path = tuple(sys.path)
    dry = cli_runtime.run_cli(s, ROOT / "run.py", "--dry-run")
    plan = cli_runtime.run_cli(s, ROOT / "run.py", "--render-plan")
    assert dry[0] == plan[0] == 0
    assert json.loads(dry[1])["verification"]["new_remote_calls"] == 0
    assert len(json.loads(plan[1])["prompt_sha256s"]) == 6
    assert tuple(sys.path) == original_path
    for path in ROOT.rglob("*"):
        if path.suffix not in {".py", ".json", ".md"}:
            continue
        text = path.read_text(encoding="utf-8").casefold()
        assert "import dspy" not in text and "from dspy" not in text
        assert "requests." not in text and "http://" not in text and "https://" not in text
        assert "--execute" not in text and "codex exec" not in text


def test_binding_drift_fails_closed(monkeypatch: pytest.MonkeyPatch):
    s = study()
    original = s.sha256_file

    def drifted(path: Path) -> str:
        if path == s.REPOSITORY / "src/hbqrs/runner.py":
            return "0" * 64
        return original(path)

    monkeypatch.setattr(s, "sha256_file", drifted)
    with pytest.raises(ValueError, match="runtime bytes drifted"):
        s.verify_bindings()
