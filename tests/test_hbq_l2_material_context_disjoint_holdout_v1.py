from __future__ import annotations

from copy import deepcopy
import importlib.util
import json
import subprocess
import sys

import pytest

from hbqrs.paths import book_root


ROOT = book_root() / "evaluation-results" / "hbq-l2-material-context-disjoint-holdout-v1"


def study():
    spec = importlib.util.spec_from_file_location("hbq_l2_material_context_disjoint_holdout_v1_test", ROOT / "study.py")
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_exact_five_case_geometry_and_decision_rule_are_frozen():
    s = study()
    assert s.verify_package() == {"study_id": s.STUDY_ID, "provider_calls": 0, "cases": 5, "cells": 5, "future_slots": 15, "image_input_slots": 0}
    assert s.load_ledger()["cells"] == {"h01": "YES", "h02": "YES", "h03": "NO", "h04": "NO", "h05": "NOT_APPLICABLE"}
    assert len(s.plan_slots()) == len({slot["slot_id"] for slot in s.plan_slots()}) == 15
    assert {slot["repeat"] for slot in s.plan_slots()} == {1, 2, 3}
    assert s.load_contract()["decision_rule"] == {"all_cells_three_of_three": "PROMOTION_REVIEW_ELIGIBLE", "any_complete_valid_miss": "NO_GO", "invalid_or_incomplete": "no_result"}


def test_fresh_case_mechanisms_are_exact_and_controls_have_no_dangling_article_split():
    s = study()
    cases = s.materialize_artifacts()
    assert {case_id: case["mechanism"] for case_id, case in cases.items()} == {case_id: details[2] for case_id, details in s.EXPECTED_CASES.items()}
    assert cases["h01"]["text"].splitlines() == ["The witness examined", "by the quiet magistrate trembled."]
    assert cases["h02"]["text"].splitlines() == ["Before curfew", "one window remained lit", "above the harbor."]
    assert cases["h03"]["text"].splitlines() == ["Riveters documented each transverse fastening", "along the spillway and forwarded the numbered", "entries to the docket clerk."]
    assert cases["h04"]["text"].splitlines() == ["The anemometer reads eight."] * 3
    assert "\n" not in cases["h05"]["text"]
    for case in (cases["h03"], cases["h04"]):
        assert all(line.casefold() not in {"the", "a", "an", "and the"} for line in case["text"].splitlines())
    assert all(motif not in "\n".join(case["text"] for case in cases.values()).casefold() for motif in ("horse", "barn", "elevator", "rain", "threshold", "depot", "courier"))


def test_candidate_delta_is_question_text_only():
    s = study()
    canonical = s.canonical_question()
    candidate = s.candidate_question()
    restored = deepcopy(candidate)
    restored["question"]["text"] = canonical["question"]["text"]
    assert restored == canonical
    assert candidate["question"]["text"] == s.CANDIDATE_TEXT


def test_rendered_provider_inputs_are_metadata_and_ledger_blind_text_only():
    s = study()
    rendered = s.render_all_provider_inputs()
    assert len(rendered) == 15
    assert all(request["image_inputs"] == [] for request in rendered.values())
    prompts = "\n".join(request["prompt"] for request in rendered.values())
    assert s.CANDIDATE_TEXT in prompts
    for forbidden in ("h01", "h02", "h03", "h04", "h05", "expected-ledger", "semantic_reduced_relative_garden_path_sole_break_contributes", "clause_insensitive_neutral_prose_wrap", "PROMOTION_REVIEW_ELIGIBLE", "NO_GO", "holdout"):
        assert forbidden.casefold() not in prompts.casefold()


def test_rendering_is_ledger_free_for_all_fifteen_slots(monkeypatch: pytest.MonkeyPatch):
    s = study()

    def forbidden_ledger_load() -> dict[str, object]:
        raise AssertionError("rendering must not read expected labels")

    monkeypatch.setattr(s, "load_ledger", forbidden_ledger_load)
    rendered = s.render_all_provider_inputs()
    assert len(rendered) == 15


def test_disjointness_rejects_a_prior_trigram_and_declared_motif(monkeypatch: pytest.MonkeyPatch):
    s = study()
    inventory = s.load_inventory()
    monkeypatch.setattr(s, "prior_inventory_texts", lambda: ["The witness examined by"])
    with pytest.raises(ValueError, match="lexical trigram"):
        s.verify_disjointness()
    monkeypatch.undo()
    inventory["sources"][0]["declared_motifs"] = ["lichen"]
    monkeypatch.setattr(s, "load_inventory", lambda: inventory)
    with pytest.raises(ValueError, match="declared motif"):
        s.verify_disjointness()


def test_pinned_lineage_and_runtime_bindings_fail_closed(monkeypatch: pytest.MonkeyPatch):
    s = study()
    original = s._git

    def drifted(*args: str) -> str:
        if args == ("rev-parse", f"{s.EXECUTOR_COMMIT}^{{tree}}"):
            return "0" * 40
        return original(*args)

    monkeypatch.setattr(s, "_git", drifted)
    with pytest.raises(ValueError, match="tree"):
        s.verify_bindings()


def test_result_commitments_compile_owners_inventory_and_prompt_receipts_are_bound():
    s = study()
    bindings = s.load_contract()["bindings"]
    assert all(len(bindings[key]) == 40 for key in ("treatment_freeze_commit", "executor_commit", "public_result_commit"))
    assert set(("src/hbqrs/core.py", "src/hbqrs/__init__.py")) <= set(bindings["runtime"])
    assert bindings["compiled_line_break_leaf_sha256"] == s.COMPILED_LEAF_HASH
    assert len(bindings["prompt_bindings"]["slots"]) == 15
    assert bindings["prompt_bindings"]["aggregate_sha256"] == "60676fcaf45fcdffb89932cf378e8e948bb781480e34a93d91acf598ca37b388"
    assert all(len(source["git_blob"]) == 40 for source in s.load_inventory()["sources"])


def test_inventory_bytes_and_complete_object_are_immutable_bindings(monkeypatch: pytest.MonkeyPatch):
    s = study()
    binding = s.load_contract()["bindings"]["prior_corpus_motif_inventory"]
    assert binding["object"] == s.load_inventory()
    assert binding["sha256"] == s.sha256_file(s.ROOT / binding["path"])
    mutated = deepcopy(s.load_inventory())
    mutated["sources"].pop()
    monkeypatch.setattr(s, "load_inventory", lambda: mutated)
    with pytest.raises(ValueError, match="inventory"):
        s.verify_bindings()


def test_exact_provider_and_scope_policy_objects_reject_drift(monkeypatch: pytest.MonkeyPatch):
    s = study()
    contract = deepcopy(s.load_contract())
    contract["provider_execution"]["permitted"] = True
    monkeypatch.setattr(s, "load_contract", lambda: contract)
    with pytest.raises(ValueError, match="policy"):
        s.verify_render_surface()


def test_command_surface_is_provider_free_and_dry_rendering_is_deterministic():
    dry = subprocess.run([sys.executable, str(ROOT / "run.py"), "--dry-run"], text=True, capture_output=True, check=True)
    plan = subprocess.run([sys.executable, str(ROOT / "run.py"), "--render-plan"], text=True, capture_output=True, check=True)
    assert json.loads(dry.stdout)["verification"]["provider_calls"] == 0
    assert len(json.loads(plan.stdout)["slots"]) == 15
    for path in ROOT.rglob("*"):
        if path.suffix in {".py", ".json", ".md"}:
            source = path.read_text(encoding="utf-8")
            assert "import dspy" not in source and "from dspy" not in source and "--execute" not in source
