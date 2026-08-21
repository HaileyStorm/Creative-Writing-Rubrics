from __future__ import annotations

import ast
import importlib.util
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1] / "evaluation-results" / "hbq-ai-writer-preface-v1"


def _study():
    specification = importlib.util.spec_from_file_location("ai_writer_preface_v1", ROOT / "study.py")
    assert specification and specification.loader
    module = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = module
    specification.loader.exec_module(module)
    return module


def test_contract_identity_current_prefix_binding_and_strictness_control():
    study = _study()
    contract = study.load_contract()
    assert contract["status"] == "preregistered_protocol_only_no_provider_or_human_execution"
    assert study.bound_asset_fingerprints()["current_judge_prefix"] == contract["bound_assets"]["current_judge_prefix"]["sha256"]
    strictness = contract["bound_assets"]["strictness_only"]["text"].lower()
    assert "feelings" not in strictness and " ai" not in strictness and "protect the system" not in strictness
    assert all(len(value) == 64 for value in study.bound_asset_fingerprints().values())


def test_judge_arms_have_identical_geometry_fresh_sessions_and_fixed_stages():
    study = _study()
    cells = study.planned_judge_cells()
    assert len(cells) == 240
    for stage, pairs in (("pilot", 4), ("development", 12), ("holdout", 24)):
        stage_cells = [cell for cell in cells if cell["stage"] == stage]
        assert len(stage_cells) == pairs * 3 * 2
        assert {cell["arm"] for cell in stage_cells} == {"none", "current_full", "strictness_only"}
        assert {cell["fresh_session"] for cell in stage_cells} == {1, 2}


def test_provenance_human_rating_and_confidence_boundaries_are_explicit():
    contract = _study().load_contract()
    assert "never sent" in contract["provenance"]["actual"].lower()
    assert "offline only" in contract["human_ratings_policy"].lower()
    assert "never changes canonical aggregation" in contract["outcomes"]["confidence"].lower()
    assert contract["experiments"]["B_writer_preface"]["blind_grading"]
    assert contract["experiments"]["C_crossover"]["no_auto_execution"] is True


def test_conditional_c_uses_only_exact_current_prefix_fragments():
    study = _study()
    contract = study.load_contract()
    raw = study.CURRENT_PREFIX.read_bytes()
    fragments = contract["bound_assets"]["production_prefix_fragments"]
    rendered_current = b"".join(raw[start:end] for start, end in ((0, 40), (40, 111), (111, 112), (112, 371), (371, 1191)))
    assert rendered_current == raw
    assert "No paraphrase" in contract["experiments"]["C_crossover"]["production_reconstruction"]
    assert "whether each differs by actual origin" in contract["experiments"]["C_crossover"]["estimands"]
    assert fragments["declared_ai_origin"]["byte_range"] == [40, 111]
    assert fragments["strictness_clause"]["byte_range"] == [112, 371]


def test_validator_rejects_five_adversarial_contract_mutations_and_has_no_execution_surface():
    study = _study()
    contract = study.load_contract()
    mutations = [
        (lambda value: value["experiments"]["A_judge_preface"]["arms"][1].update(prefix_asset="strictness_only"), "Judge-arm mapping"),
        (lambda value: value["provenance"]["actual_origin_levels"]["ai_written"].update(pilot=3), "Actual/declared provenance"),
        (lambda value: value["experiments"]["B_writer_preface"].update(blind_grading="arm identities shown"), "Blind downstream grading"),
        (lambda value: value.update(human_ratings_policy="ratings may be sent"), "HANNA outbound boundary"),
        (lambda value: value["outcomes"].update(confidence="Confidence weights the score."), "Confidence weighting"),
        (lambda value: value["experiments"]["A_judge_preface"].update(estimands=[]), "Actual-origin interaction estimand"),
        (lambda value: value["outcomes"].update(primary=[]), "Actual-origin interaction outcome"),
        (lambda value: value["experiments"]["A_judge_preface"].update(pair_definition="different texts may be compared"), "Matched-pair same-text definition"),
    ]
    for mutate, message in mutations:
        altered = json.loads(json.dumps(contract))
        mutate(altered)
        with pytest.raises(ValueError, match=message):
            study.validate_contract(altered)
    tree = ast.parse((ROOT / "study.py").read_text(encoding="utf-8"))
    imported = {alias.name.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
    imported |= {node.module.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module}
    assert not imported & study.NETWORK_IMPORTS
    assert "forbidden" in study.execution_surface()
    with pytest.raises(RuntimeError, match="cannot make provider calls"):
        study.execute()
