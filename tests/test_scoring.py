"""Ported HBQ-RS scoring and registry tests without internal reconstruction."""

from __future__ import annotations

from typing import Any

import pytest
import yaml

from hbqrs import book_root, compile_bundle, score_bundle, validate_registry, walk_tree

ROOT = book_root()


def _verdict(question_id: str, state: str = "YES") -> dict[str, Any]:
    record: dict[str, Any] = {
        "artifact_id": "test-artifact",
        "question_id": question_id,
        "verdict": state,
        "confidence": 1.0 if state in {"YES", "NO"} else 0.5,
        "evidence": [{"reference": "test:1", "quote": "Synthetic test evidence."}]
        if state in {"YES", "NO"}
        else [],
    }
    if state == "NOT_APPLICABLE":
        record["note"] = "Synthetic activation condition is false."
    if state == "CANNOT_ASSESS":
        record["note"] = "Synthetic evidence is intentionally unavailable."
    return record


def _full_verdicts(
    modules: list[dict[str, Any]],
    bundle: dict[str, Any],
    default: str = "YES",
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    compiled = compile_bundle(modules, bundle)
    qids: list[str] = []
    qids.extend(item["question"]["id"] for item in compiled["domain_questions"])
    qids.extend(item["question"]["id"] for item in compiled["hard_gates"])
    qids.extend(item["question"]["id"] for item in compiled["supplemental_questions"])
    qids.extend(
        item["question"]["id"]
        for group in compiled["penalty_groups"]
        for item in group["questions"]
    )
    return compiled, [_verdict(qid, default) for qid in dict.fromkeys(qids)]


def test_inventory_counts(modules, bundles, manifest) -> None:
    questions = sum(1 for module in modules for _ in walk_tree(module["tree"]))
    assert len(modules) == 277
    assert len(bundles) == 85
    assert questions == 2139
    assert manifest["module_count"] == 277
    assert manifest["question_count"] == 2139
    assert manifest["bundle_count"] == 85


def test_aggregate_parity_and_criterion_ownership(modules, bundles) -> None:
    yaml_modules = yaml.safe_load((ROOT / "registry" / "all_modules.yaml").read_text(encoding="utf-8"))
    yaml_bundles = yaml.safe_load((ROOT / "bundles" / "all_bundles.yaml").read_text(encoding="utf-8"))
    assert yaml_modules == modules
    assert yaml_bundles == bundles

    import json

    expected_owners = json.loads(
        (ROOT / "registry" / "criterion_ownership.json").read_text(encoding="utf-8")
    )
    actual_owners: dict[str, dict[str, str]] = {}
    for module in modules:
        for leaf, _, _ in walk_tree(module["tree"]):
            assert leaf["criterion_key"] not in actual_owners
            actual_owners[leaf["criterion_key"]] = {
                "module_id": module["module_id"],
                "question_id": leaf["id"],
            }
    assert actual_owners == expected_owners


def test_registry_and_schema_validation(modules, bundles) -> None:
    import json

    module_schema = json.loads((ROOT / "schema" / "hbq_rubric.schema.json").read_text(encoding="utf-8"))
    bundle_schema = json.loads((ROOT / "schema" / "hbq_bundle.schema.json").read_text(encoding="utf-8"))
    errors = validate_registry(
        modules,
        bundles,
        module_schema=module_schema,
        bundle_schema=bundle_schema,
    )
    assert errors == []


def test_every_bundle_compiles_without_duplicate_scoring(modules, bundles) -> None:
    for bundle in bundles:
        assert sum(float(domain["points"]) for domain in bundle["domains"]) == pytest.approx(100.0)
        compiled = compile_bundle(modules, bundle)
        ids = [item["question"]["id"] for item in compiled["domain_questions"]]
        assert ids
        assert len(ids) == len(set(ids)), bundle["bundle_id"]
        assert compiled["hard_gates"], bundle["bundle_id"]


def test_all_yes_produces_full_score_and_valid_gates(modules, bundle_by_id) -> None:
    _, verdicts = _full_verdicts(modules, bundle_by_id["prose.scene"])
    report = score_bundle(modules, bundle_by_id["prose.scene"], verdicts)
    assert report["hard_gate_status"] == "VALID"
    assert report["coverage"] == pytest.approx(1.0)
    assert report["base_score"]["observed"] == pytest.approx(100.0)
    assert report["penalty_deduction"]["observed"] == pytest.approx(0.0)
    assert report["final_score"]["observed"] == pytest.approx(100.0)
    assert report["status"] == "SCORED"


def test_failed_hard_gate_invalidates_without_erasing_quality_score(modules, bundle_by_id) -> None:
    compiled, verdicts = _full_verdicts(modules, bundle_by_id["prose.scene"])
    gate_id = compiled["hard_gates"][0]["question"]["id"]
    next(item for item in verdicts if item["question_id"] == gate_id)["verdict"] = "NO"
    report = score_bundle(modules, bundle_by_id["prose.scene"], verdicts)
    assert report["hard_gate_status"] == "INVALID"
    assert report["status"] == "INELIGIBLE"
    assert report["base_score"]["observed"] == pytest.approx(100.0)


def test_cannot_assess_creates_coverage_and_score_interval(modules, bundle_by_id) -> None:
    compiled, verdicts = _full_verdicts(modules, bundle_by_id["prose.scene"])
    uncertain_ids = [item["question"]["id"] for item in compiled["domain_questions"][:20]]
    for item in verdicts:
        if item["question_id"] in uncertain_ids:
            item.update(_verdict(item["question_id"], "CANNOT_ASSESS"))
    report = score_bundle(modules, bundle_by_id["prose.scene"], verdicts)
    assert report["coverage"] < 1.0
    assert report["base_score"]["lower"] < report["base_score"]["upper"]
    assert report["final_score"]["lower"] <= report["final_score"]["observed"]
    assert report["final_score"]["observed"] <= report["final_score"]["upper"]


def test_repetition_penalty_reaches_but_does_not_exceed_cap(modules, bundle_by_id) -> None:
    compiled, verdicts = _full_verdicts(modules, bundle_by_id["prose.scene"])
    repetition_ids = {
        item["question"]["id"]
        for group in compiled["penalty_groups"]
        if group["module_id"] == "penalty.repetition"
        for item in group["questions"]
    }
    for item in verdicts:
        if item["question_id"] in repetition_ids:
            item.update(_verdict(item["question_id"], "NO"))
    report = score_bundle(modules, bundle_by_id["prose.scene"], verdicts)
    repetition = next(item for item in report["penalties"] if item["module_id"] == "penalty.repetition")
    assert repetition["deduction"]["observed"] == pytest.approx(5.0)
    assert repetition["deduction"]["upper"] <= repetition["cap_points"]
    assert report["final_score"]["observed"] == pytest.approx(95.0)


def test_holistic_thresholds_are_cumulative(modules, bundle_by_id) -> None:
    compiled, verdicts = _full_verdicts(modules, bundle_by_id["prose.scene"])
    thresholds = [
        item["question"]["id"]
        for item in compiled["domain_questions"]
        if item["question"]["question_type"] == "subjective_threshold"
    ]
    assert len(thresholds) == 4
    for item in verdicts:
        if item["question_id"] == thresholds[0]:
            item.update(_verdict(item["question_id"], "NO"))
        elif item["question_id"] in thresholds[1:]:
            item.update(_verdict(item["question_id"], "YES"))
    report = score_bundle(modules, bundle_by_id["prose.scene"], verdicts)
    holistic = next(domain for domain in report["domains"] if domain["domain_id"] == "holistic")
    assert holistic["score"]["observed"] == pytest.approx(0.0)
    assert any("Subjective ladder" in issue for issue in report["issues"])


def test_inactive_conditional_domain_is_reallocated(modules, bundle_by_id) -> None:
    compiled, verdicts = _full_verdicts(modules, bundle_by_id["poetry.haiku.strict_575"])
    sequence_ids = {
        item["question"]["id"]
        for item in compiled["domain_questions"]
        if item["domain_id"] == "sequence"
    }
    for item in verdicts:
        if item["question_id"] in sequence_ids:
            item.update(_verdict(item["question_id"], "NOT_APPLICABLE"))
    report = score_bundle(modules, bundle_by_id["poetry.haiku.strict_575"], verdicts)
    assert report["inactive_points_reallocated"] == pytest.approx(6.0)
    assert report["base_score"]["observed"] == pytest.approx(100.0)
    assert report["final_score"]["observed"] == pytest.approx(100.0)


def test_missing_verdict_is_unassessed_not_failed(modules, bundle_by_id) -> None:
    compiled, verdicts = _full_verdicts(modules, bundle_by_id["poetry.general"])
    missing_id = compiled["domain_questions"][0]["question"]["id"]
    verdicts = [item for item in verdicts if item["question_id"] != missing_id]
    report = score_bundle(modules, bundle_by_id["poetry.general"], verdicts)
    assert report["coverage"] < 1.0
    assert any(missing_id in issue and "Missing verdict" in issue for issue in report["issues"])


def test_stable_role_ids_survive_display_rewrites(module_by_id) -> None:
    assert "workflow.model_a_high_context_role_fitness" in module_by_id
    assert "workflow.model_b_fast_generation_role_fitness" in module_by_id
    assert module_by_id["workflow.model_a_high_context_role_fitness"]["title"] == (
        "High-context critic/editor role fitness"
    )
    assert module_by_id["workflow.model_b_fast_generation_role_fitness"]["title"] == (
        "Fast generator/screener role fitness"
    )
