"""Ported HBQ-RS scoring and registry tests without internal reconstruction."""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from typing import Any

import pytest
import yaml
from jsonschema import Draft202012Validator

from hbqrs import HBQError, book_root, compile_bundle, score_bundle, validate_registry, walk_tree

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
    *,
    task_contract: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    compiled = compile_bundle(modules, bundle, task_contract=task_contract)
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


def _task_contract() -> dict[str, Any]:
    source = {"kind": "user_preference", "reference": "brief:goal-1", "exact_excerpt": "Keep Amelia morally dark."}
    return {
        "contract_id": "gray-blood-test",
        "weighted_goals": [
            {
                "goal_id": "darker-amelia",
                "atomic_question": "Does Amelia retain morally dark behavior?",
                "weight": 2.0,
                "source": source,
            }
        ],
        "binding_requirements": [
            {
                "requirement_id": "first-person",
                "atomic_question": "Is the artifact written in first person?",
                "objective": True,
                "non_negotiable": True,
                "weight": 1.0,
                "source": {**source, "kind": "explicit_user_requirement", "reference": "brief:req-1"},
                "verification": {
                    "method": "absence",
                    "expected": "No third-person narration appears.",
                },
            }
        ],
    }


def test_inventory_counts(modules, bundles, manifest) -> None:
    questions = sum(1 for module in modules for _ in walk_tree(module["tree"]))
    assert len(modules) == 278
    assert len(bundles) == 85
    assert questions == 2145
    assert manifest["module_count"] == 278
    assert manifest["question_count"] == 2145
    assert manifest["bundle_count"] == 85
    assert manifest["package"] == "creative-writing-rubrics"
    assert manifest["standard"] == {"id": "HBQ-RS", "version": "1.2.1"}


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


def test_authored_content_treatment_fidelity_module_contract(module_by_id, bundles) -> None:
    module = module_by_id["modifier.style.authored_content_treatment_fidelity"]
    expected_ids = [
        "modifier.style.authored_content_treatment_fidelity.directness_level",
        "modifier.style.authored_content_treatment_fidelity.detail_density",
        "modifier.style.authored_content_treatment_fidelity.lexical_specificity",
        "modifier.style.authored_content_treatment_fidelity.euphemism_alignment",
        "modifier.style.authored_content_treatment_fidelity.treatment_register",
        "modifier.style.authored_content_treatment_fidelity.depiction_scope",
    ]
    axes = [
        "directness-level",
        "detail-density",
        "lexical-specificity",
        "preferred or disfavored euphemism-pattern",
        "treatment-register",
        "depiction-scope",
    ]
    bidirectional_targets = [
        "more evasive or more explicit",
        "neither summarizing away material chosen for detail nor adding granular depiction",
        "vagueness below the effective target and anatomical, technical, or other specificity beyond it",
        "undeclared coyness or bluntness",
        "softer, harsher",
        "neither eliding material chosen for direct depiction nor expanding material chosen for summary or omission",
    ]
    leaves = [leaf for leaf, _, _ in walk_tree(module["tree"])]
    assert module["kind"] == "modifier"
    assert module["requires"] == []
    assert module["incompatible_with"] == []
    assert module["modifier_actions"] == []
    assert "Opt in only" in module["activation"]
    assert "Do not activate from topic, genre, audience, rating" in module["activation"]
    assert [leaf["id"] for leaf in leaves] == expected_ids
    assert [leaf["criterion_key"] for leaf in leaves] == expected_ids
    assert all(leaf["id"] == leaf["criterion_key"] for leaf in leaves)
    assert all(leaf["question_type"] == "scored" and not leaf.get("hard_gate", False) for leaf in leaves)
    assert all("explicitly active" in leaf["applies_when"] for leaf in leaves)
    assert all("Topic, genre, audience, rating, and subject matter alone do not activate" in leaf["applies_when"] for leaf in leaves)
    assert all(
        f"declares a {axis} target" in leaf["applies_when"]
        for leaf, axis in zip(leaves, axes)
    )
    assert "Return NOT_APPLICABLE when no preferred or disfavored euphemism patterns are declared." in leaves[3]["applies_when"]
    assert "unselected axes are not applicable" in module["tree"][0]["description"]
    assert module["notes"][2] == "Apply only selected axes; an undeclared axis receives NOT_APPLICABLE rather than an inferred target."
    assert all(target in leaf["text"] for leaf, target in zip(leaves, bidirectional_targets))
    assert module["notes"][1] == "This is a style-fidelity rubric, not a moderation, permission, refusal, safety, consent, audience, or moral gate."
    assert not {"permission", "refusal", "moderation", "safety", "consent", "audience", "moral"} & set(module)
    assert module["module_id"] not in json.dumps(bundles)


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
    contract = _task_contract()
    compiled, verdicts = _full_verdicts(
        modules,
        bundle_by_id["prose.scene"],
        task_contract=contract,
    )
    gate_id = compiled["task_contract"]["binding_requirement_ids"][0]
    next(item for item in verdicts if item["question_id"] == gate_id)["verdict"] = "NO"
    report = score_bundle(
        modules,
        bundle_by_id["prose.scene"],
        verdicts,
        task_contract=contract,
    )
    assert report["hard_gate_status"] == "INVALID"
    assert report["status"] == "INELIGIBLE"
    assert report["base_score"]["observed"] == pytest.approx(100.0)


def test_task_goals_are_weighted_without_becoming_gates(modules, bundle_by_id) -> None:
    contract = _task_contract()
    compiled, verdicts = _full_verdicts(
        modules,
        bundle_by_id["prose.novel"],
        task_contract=contract,
    )
    goal_id = compiled["task_contract"]["weighted_goal_ids"][0]
    requirement_id = compiled["task_contract"]["binding_requirement_ids"][0]
    next(item for item in verdicts if item["question_id"] == goal_id)["verdict"] = "NO"
    report = score_bundle(
        modules,
        bundle_by_id["prose.novel"],
        verdicts,
        task_contract=contract,
    )
    assert report["status"] == "SCORED"
    assert report["hard_gate_status"] == "VALID"
    assert report["final_score"]["observed"] < 100.0
    assert goal_id not in {item["question_id"] for item in report["hard_gates"]}
    assert requirement_id in {item["question_id"] for item in report["hard_gates"]}


@pytest.mark.parametrize(
    ("bundle_id", "domain_id"),
    [
        ("default.first_pass_screening", "hard"),
        ("default.full_manuscript_critique", "scope"),
    ],
)
def test_general_bundles_place_task_goals_in_declared_domain(
    modules, bundle_by_id, bundle_id: str, domain_id: str
) -> None:
    compiled = compile_bundle(modules, bundle_by_id[bundle_id], task_contract=_task_contract())
    goal_id = compiled["task_contract"]["weighted_goal_ids"][0]
    record = next(item for item in compiled["domain_questions"] if item["question"]["id"] == goal_id)
    assert record["domain_id"] == domain_id


def test_only_explicit_binding_requirement_can_invalidate_task_contract(modules, bundle_by_id) -> None:
    contract = _task_contract()
    compiled, verdicts = _full_verdicts(
        modules,
        bundle_by_id["prose.novel"],
        task_contract=contract,
    )
    requirement_id = compiled["task_contract"]["binding_requirement_ids"][0]
    next(item for item in verdicts if item["question_id"] == requirement_id)["verdict"] = "NO"
    report = score_bundle(
        modules,
        bundle_by_id["prose.novel"],
        verdicts,
        task_contract=contract,
    )
    assert report["hard_gate_status"] == "INVALID"
    assert report["status"] == "INELIGIBLE"


def test_absence_requirement_exposes_activation_semantics(modules, bundle_by_id) -> None:
    contract = _task_contract()
    compiled = compile_bundle(modules, bundle_by_id["prose.novel"], task_contract=contract)
    gate = next(
        item
        for item in compiled["hard_gates"]
        if item["question"]["id"] in compiled["task_contract"]["binding_requirement_ids"]
    )["question"]
    assert gate["verification"]["method"] == "absence"
    assert "NOT_APPLICABLE rather than CANNOT_ASSESS" in gate["applies_when"]


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


def test_confidence_diagnostics_are_secondary_and_role_separated(modules, bundle_by_id) -> None:
    contract = _task_contract()
    compiled, verdicts = _full_verdicts(
        modules,
        bundle_by_id["prose.scene"],
        task_contract=contract,
    )
    domain_id = compiled["domain_questions"][0]["question"]["id"]
    gate_id = compiled["hard_gates"][0]["question"]["id"]
    penalty_id = compiled["penalty_groups"][0]["questions"][0]["question"]["id"]
    supplemental_id = compiled["supplemental_questions"][0]["question"]["id"]
    for verdict in verdicts:
        if verdict["question_id"] == domain_id:
            verdict["confidence"] = 0.2
        elif verdict["question_id"] == gate_id:
            verdict["confidence"] = 0.4
        elif verdict["question_id"] == penalty_id:
            verdict["confidence"] = 0.8
        elif verdict["question_id"] == supplemental_id:
            verdict["confidence"] = 0.6
    report = score_bundle(modules, bundle_by_id["prose.scene"], verdicts, task_contract=contract)
    diagnostics = report["confidence_diagnostics"]
    assert diagnostics["status"] == "DESCRIPTIVE_UNCALIBRATED"
    assert diagnostics["calibration"] == {
        "status": "UNAVAILABLE",
        "exact_fingerprint": None,
        "reason": "A single score has no polarity comparison, repeat judgments, or outcome history; no calibration inference is made.",
    }
    assert set(diagnostics["roles"]) == {"domain", "hard_gate", "penalty", "supplemental"}
    assert diagnostics["roles"]["hard_gate"]["assessed_raw_confidence_weighted_mean"] == pytest.approx(0.4)
    assert diagnostics["roles"]["supplemental"]["assessed_raw_confidence_weighted_mean"] < 1.0
    assert diagnostics["roles"]["penalty"]["assessed_raw_confidence_weighted_mean"] < 1.0
    assert diagnostics["roles"]["domain"]["effective_confidence_mass"]["is_coverage"] is False
    assert report["hard_gate_status"] == "VALID"
    assert report["status"] == "SCORED"
    assert report["coverage"] == pytest.approx(1.0)
    assert report["penalty_deduction"] == {"observed": 0.0, "lower": 0.0, "upper": 0.0}
    assert report["final_score"] == {"observed": 100.0, "lower": 100.0, "upper": 100.0}


def test_confidence_diagnostics_exclude_not_applicable_and_include_cannot_assess_mass(modules, bundle_by_id) -> None:
    compiled, verdicts = _full_verdicts(modules, bundle_by_id["prose.scene"])
    cannot_id = compiled["domain_questions"][0]["question"]["id"]
    not_applicable_id = compiled["domain_questions"][1]["question"]["id"]
    for verdict in verdicts:
        if verdict["question_id"] == cannot_id:
            verdict.update(_verdict(cannot_id, "CANNOT_ASSESS"))
        elif verdict["question_id"] == not_applicable_id:
            verdict.update(_verdict(not_applicable_id, "NOT_APPLICABLE"))
    report = score_bundle(modules, bundle_by_id["prose.scene"], verdicts)
    aggregate = report["confidence_diagnostics"]["roles"]["domain"]
    records = compiled["domain_questions"]
    expected_applicable = sum(
        float(record["effective_weight"])
        for record in records
        if record["question"]["id"] != not_applicable_id
    )
    expected_assessed = sum(
        float(record["effective_weight"])
        for record in records
        if record["question"]["id"] not in {cannot_id, not_applicable_id}
    )
    assert aggregate["question_count"] == len(records)
    assert aggregate["applicable_count"] == len(records) - 1
    assert aggregate["assessed_count"] == len(records) - 2
    assert aggregate["applicable_effective_weight"] == pytest.approx(expected_applicable)
    assert aggregate["assessed_effective_weight"] == pytest.approx(expected_assessed)
    assert aggregate["assessed_raw_confidence_weighted_mean"] == pytest.approx(1.0)
    assert aggregate["effective_confidence_mass"]["value"] == pytest.approx(
        expected_assessed / expected_applicable, abs=0.00005
    )
    assert aggregate["effective_confidence_mass"]["is_coverage"] is False
    assert report["coverage"] < 1.0


def test_confidence_only_changes_leave_the_canonical_projection_exactly_unchanged(
    modules, bundle_by_id
) -> None:
    _, verdicts = _full_verdicts(modules, bundle_by_id["prose.scene"])
    baseline = score_bundle(modules, bundle_by_id["prose.scene"], verdicts)
    for index, verdict in enumerate(verdicts):
        verdict["confidence"] = (index % 10) / 10
    varied_confidence = score_bundle(modules, bundle_by_id["prose.scene"], verdicts)

    def canonical_projection(report: dict[str, Any]) -> dict[str, Any]:
        return {
            "status": report["status"],
            "coverage": report["coverage"],
            "minimum_coverage": report["minimum_coverage"],
            "hard_gate_status": report["hard_gate_status"],
            "hard_gates": report["hard_gates"],
            "base_score": report["base_score"],
            "penalty_deduction": report["penalty_deduction"],
            "final_score": report["final_score"],
            "domains": [
                {
                    "domain_id": domain["domain_id"],
                    "active": domain["active"],
                    "coverage": domain["coverage"],
                    "weights": domain["weights"],
                    "score": domain["score"],
                }
                for domain in report["domains"]
            ],
            "penalties": [
                {
                    "module_id": penalty["module_id"],
                    "coverage": penalty["coverage"],
                    "weights": penalty["weights"],
                    "deduction": penalty["deduction"],
                }
                for penalty in report["penalties"]
            ],
        }

    assert canonical_projection(varied_confidence) == canonical_projection(baseline)
    assert varied_confidence["confidence_diagnostics"] != baseline["confidence_diagnostics"]
    assert varied_confidence["confidence"] != baseline["confidence"]


def test_confidence_diagnostics_mark_empty_and_unassessed_role_ratios_unobserved(
    modules, bundle_by_id
) -> None:
    compiled, verdicts = _full_verdicts(modules, bundle_by_id["default.coarse_outline"])
    supplemental_ids = {
        record["question"]["id"] for record in compiled["supplemental_questions"]
    }
    for verdict in verdicts:
        if verdict["question_id"] in supplemental_ids:
            verdict.update(_verdict(verdict["question_id"], "CANNOT_ASSESS"))
    report = score_bundle(modules, bundle_by_id["default.coarse_outline"], verdicts)
    empty_penalty = report["confidence_diagnostics"]["roles"]["penalty"]
    unassessed_supplemental = report["confidence_diagnostics"]["roles"]["supplemental"]

    assert empty_penalty["question_count"] == 0
    assert unassessed_supplemental["applicable_count"] == len(supplemental_ids)
    for aggregate in (empty_penalty, unassessed_supplemental):
        assert aggregate["assessed_count"] == 0
        assert aggregate["assessed_raw_confidence_weighted_mean"] is None
        assert aggregate["assessed_raw_confidence_weighted_median"] is None
        assert aggregate["effective_confidence_mass"]["value"] is None
        assert all(
            share is None
            for share in aggregate["assessed_effective_weight_threshold_shares"].values()
        )


def test_score_report_schema_accepts_confidence_diagnostics_and_rejects_malformed_values(
    modules, bundle_by_id
) -> None:
    _, verdicts = _full_verdicts(modules, bundle_by_id["prose.scene"])
    report = score_bundle(modules, bundle_by_id["prose.scene"], verdicts)
    schema = json.loads((ROOT / "schema" / "hbq_score_report.v2.schema.json").read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)

    assert list(validator.iter_errors(report)) == []

    without_diagnostics = deepcopy(report)
    del without_diagnostics["confidence_diagnostics"]
    assert list(validator.iter_errors(without_diagnostics)) == []

    from hbqrs.core import score_bundle as score_bundle_v1

    parent = score_bundle_v1(modules, bundle_by_id["prose.scene"], verdicts)
    parent_schema = json.loads(
        (ROOT / "schema" / "hbq_score_report.schema.json").read_text(encoding="utf-8")
    )
    assert list(Draft202012Validator(parent_schema).iter_errors(parent)) == []

    malformed = deepcopy(report)
    malformed["confidence_diagnostics"]["roles"]["domain"]["effective_confidence_mass"][
        "is_coverage"
    ] = True
    assert list(validator.iter_errors(malformed))


def test_weighted_median_uses_lower_value_at_an_exact_half_tie() -> None:
    from hbqrs.scoring_v2 import _weighted_median

    assert _weighted_median([(0.2, 1.0), (0.8, 1.0)]) == pytest.approx(0.2)


def test_v1_frozen_assets_have_lf_successor_seals_and_v2_keeps_the_canonical_projection(
    modules, bundle_by_id
) -> None:
    from hbqrs.core import score_bundle as score_bundle_v1

    schema_bytes = (ROOT / "schema" / "hbq_score_report.schema.json").read_bytes()
    assert hashlib.sha256(schema_bytes.replace(b"\r\n", b"\n")).hexdigest() == (
        "e9bf341a501ced78db81dae6ef1cd84b43eb9a740966034a5652d5b9a0dfdc4c"
    )
    core_bytes = (ROOT / "src" / "hbqrs" / "core.py").read_bytes()
    assert hashlib.sha256(core_bytes.replace(b"\r\n", b"\n")).hexdigest() == (
        "0518be16a4528b893de6af61300ecea58dc56d6b7944b5ae5fd3a3214a3794ef"
    )
    _, verdicts = _full_verdicts(modules, bundle_by_id["prose.scene"])
    parent = score_bundle_v1(modules, bundle_by_id["prose.scene"], verdicts)
    descendant = score_bundle(modules, bundle_by_id["prose.scene"], verdicts)
    for report in (parent, descendant):
        report.pop("$schema")
        report.pop("report_version", None)
        report.pop("confidence_diagnostics", None)
    assert descendant == parent


def test_v2_score_descendant_is_hash_bound_atomic_and_resumable(tmp_path, modules, bundle_by_id) -> None:
    from hbqrs.core import score_bundle as score_bundle_v1
    from hbqrs.runner_v2 import persist_v2_descendant

    _, verdicts = _full_verdicts(modules, bundle_by_id["prose.scene"])
    parent = score_bundle_v1(modules, bundle_by_id["prose.scene"], verdicts)
    parent["weight_profile"] = None
    parent_path = tmp_path / "score.json"
    parent_path.write_text(json.dumps(parent, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    verdicts_path = tmp_path / "verdicts.jsonl"
    verdicts_path.write_text("\n".join(json.dumps(item) for item in verdicts) + "\n", encoding="utf-8")
    parent_bytes = parent_path.read_bytes()

    first = persist_v2_descendant(
        output_dir=tmp_path,
        registry=ROOT / "registry" / "all_modules.json",
        bundles=ROOT / "bundles" / "all_bundles.json",
        weight_profile=None,
        task_contract_path=None,
    )
    second = persist_v2_descendant(
        output_dir=tmp_path,
        registry=ROOT / "registry" / "all_modules.json",
        bundles=ROOT / "bundles" / "all_bundles.json",
        weight_profile=None,
        task_contract_path=None,
    )
    assert first == second == tmp_path / "score.v2.json"
    assert parent_path.read_bytes() == parent_bytes
    descendant = json.loads(first.read_text(encoding="utf-8"))
    assert descendant["parent_score_sha256"] == hashlib.sha256(parent_bytes).hexdigest()


def test_score_report_version_routing_rejects_mixed_or_unknown_contracts(
    modules, bundle_by_id
) -> None:
    from hbqrs.core import score_bundle as score_bundle_v1
    from hbqrs.scoring_v2 import V2_SCHEMA, score_report_version

    _, verdicts = _full_verdicts(modules, bundle_by_id["prose.scene"])
    parent = score_bundle_v1(modules, bundle_by_id["prose.scene"], verdicts)
    descendant = score_bundle(modules, bundle_by_id["prose.scene"], verdicts)
    assert score_report_version(parent) == 1
    assert score_report_version(descendant) == 2
    mixed = deepcopy(descendant)
    mixed["$schema"] = "../schema/hbq_score_report.schema.json"
    with pytest.raises(HBQError, match="Unsupported score report version/schema pair"):
        score_report_version(mixed)
    legacy_pointer = deepcopy(parent)
    legacy_pointer["$schema"] = "https://example.invalid/legacy-score-schema.json"
    assert score_report_version(legacy_pointer) == 1
    unknown = deepcopy(parent)
    unknown["report_version"] = 3
    unknown["$schema"] = V2_SCHEMA
    with pytest.raises(HBQError, match="Unsupported score report version/schema pair"):
        score_report_version(unknown)


def test_confidence_schema_definitions_match_the_longform_projection_schema() -> None:
    score_schema = json.loads((ROOT / "schema" / "hbq_score_report.v2.schema.json").read_text(encoding="utf-8"))
    workflow_schema = json.loads(
        (ROOT / "schema" / "hbq_long_form_workflow_report.schema.json").read_text(encoding="utf-8")
    )
    names = (
        "assessed_effective_weight_threshold_shares",
        "confidence_role_aggregate",
        "confidence_diagnostics",
    )
    assert {name: score_schema["$defs"][name] for name in names} == {
        name: workflow_schema["$defs"][name] for name in names
    }


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


def test_no_assessable_point_bearing_questions_is_not_labeled_scored(modules, bundle_by_id) -> None:
    compiled, verdicts = _full_verdicts(modules, bundle_by_id["prose.scene"], "CANNOT_ASSESS")
    report = score_bundle(modules, bundle_by_id["prose.scene"], verdicts)
    assert compiled["domain_questions"]
    assert report["base_score"]["observed"] is None
    assert report["final_score"]["observed"] is None
    assert report["status"] == "PROVISIONAL"


def test_penalty_modules_reject_non_scored_leaves() -> None:
    modules = [
        {
            "module_id": "penalty.bad",
            "tree": [
                {
                    "id": "penalty.bad.gate",
                    "type": "question",
                    "question_type": "hard_gate",
                    "weight": 1,
                    "text": "Is this invalid as a penalty leaf?",
                }
            ],
        },
        {
            "module_id": "domain.good",
            "tree": [
                {
                    "id": "domain.good.score",
                    "type": "question",
                    "question_type": "scored",
                    "weight": 1,
                    "text": "Does this score?",
                }
            ],
        },
    ]
    bundle = {
        "bundle_id": "bad.penalty",
        "domains": [
            {
                "domain_id": "quality",
                "points": 100,
                "components": [{"module_id": "domain.good"}],
            }
        ],
        "module_ids": ["domain.good", "penalty.bad"],
        "penalty_modules": [{"module_id": "penalty.bad", "cap_points": 5}],
    }
    with pytest.raises(HBQError, match="contains non-scored question"):
        compile_bundle(modules, bundle)


def test_stable_role_ids_survive_display_rewrites(module_by_id) -> None:
    assert "workflow.model_a_high_context_role_fitness" in module_by_id
    assert "workflow.model_b_fast_generation_role_fitness" in module_by_id
    assert module_by_id["workflow.model_a_high_context_role_fitness"]["title"] == (
        "High-context critic/editor role fitness"
    )
    assert module_by_id["workflow.model_b_fast_generation_role_fitness"]["title"] == (
        "Fast generator/screener role fitness"
    )
