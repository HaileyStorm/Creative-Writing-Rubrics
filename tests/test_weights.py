"""Tests for strict, general-purpose scoring-weight profiles."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
import pytest

from hbqrs import HBQError, book_root, compile_bundle, walk_tree
from hbqrs.weights import make_weight_profile, materialize_weight_profile


def _profile(**overrides: Any) -> dict[str, Any]:
    profile = {"profile_version": 1, "profile_id": "test-profile"}
    profile.update(overrides)
    return profile


def _domain_weights(bundle: dict[str, Any], *, first_weight: float = 2.0) -> list[dict[str, Any]]:
    return [
        {"domain_id": domain["domain_id"], "weight": first_weight if index == 0 else 1.0}
        for index, domain in enumerate(bundle["domains"])
    ]


def _node(module: dict[str, Any], node_id: str) -> dict[str, Any]:
    stack = list(module["tree"])
    while stack:
        node = stack.pop()
        if node["id"] == node_id:
            return node
        stack.extend(node.get("children", []))
    raise AssertionError(f"Missing node {node_id}")


def _module(modules: list[dict[str, Any]], module_id: str) -> dict[str, Any]:
    return next(module for module in modules if module["module_id"] == module_id)


def test_weight_profile_schema_is_valid() -> None:
    schema = json.loads((book_root() / "schema" / "hbq_weight_profile.schema.json").read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)


def test_no_profile_is_deep_copy_identity_for_every_real_bundle(modules, bundles) -> None:
    for bundle in bundles:
        transformed_modules, transformed_bundle, audit = materialize_weight_profile(modules, bundle)
        assert transformed_modules == modules
        assert transformed_modules is not modules
        assert transformed_bundle == bundle
        assert transformed_bundle is not bundle
        assert audit["identity"] is True
        assert audit["requested"] is None
        assert "task contract" in audit["task_contract_weight_policy"].lower()
        compile_bundle(transformed_modules, transformed_bundle)


def test_profile_materializes_all_static_scoring_layers_without_mutation(modules, bundle_by_id) -> None:
    bundle = bundle_by_id["prose.scene"]
    original_modules = deepcopy(modules)
    original_bundle = deepcopy(bundle)
    profile = _profile(
        bundle_id="prose.scene",
        domain_weights=_domain_weights(bundle),
        component_weights=[
            {"domain_id": "task", "module_id": "core.task_and_brief_fidelity", "weight": 3.0}
        ],
        group_weights=[
            {"group_id": "core.task_and_brief_fidelity.quality", "weight": 2.0},
            {"group_id": "penalty.repetition.controls", "weight": 1.25},
        ],
        question_weights=[
            {"question_id": "core.task_and_brief_fidelity.intervention", "weight": 4.0},
            {"question_id": "penalty.repetition.lexical", "weight": 2.25},
        ],
        penalty_caps=[{"module_id": "penalty.repetition", "cap_points": 7.0}],
    )

    transformed_modules, transformed_bundle, audit = materialize_weight_profile(modules, bundle, profile)

    assert modules == original_modules
    assert bundle == original_bundle
    assert sum(domain["points"] for domain in transformed_bundle["domains"]) == pytest.approx(100.0)
    assert transformed_bundle["domains"][0]["points"] == pytest.approx(20.0)
    assert all(domain["points"] == pytest.approx(10.0) for domain in transformed_bundle["domains"][1:])
    task_component = transformed_bundle["domains"][0]["components"][0]
    assert task_component["weight"] == 3.0
    assert next(
        item["cap_points"]
        for item in transformed_bundle["penalty_modules"]
        if item["module_id"] == "penalty.repetition"
    ) == 7.0

    task_module = _module(transformed_modules, "core.task_and_brief_fidelity")
    penalty_module = _module(transformed_modules, "penalty.repetition")
    assert _node(task_module, "core.task_and_brief_fidelity.quality")["weight"] == 2.0
    assert _node(task_module, "core.task_and_brief_fidelity.intervention")["weight"] == 4.0
    assert _node(penalty_module, "penalty.repetition.controls")["weight"] == 1.25
    assert _node(penalty_module, "penalty.repetition.lexical")["weight"] == 2.25

    compiled = compile_bundle(transformed_modules, transformed_bundle)
    intervention = next(
        item
        for item in compiled["domain_questions"]
        if item["question"]["id"] == "core.task_and_brief_fidelity.intervention"
    )
    lexical = next(
        item
        for group in compiled["penalty_groups"]
        for item in group["questions"]
        if item["question"]["id"] == "penalty.repetition.lexical"
    )
    assert intervention["effective_weight"] == pytest.approx(24.0)
    assert lexical["effective_weight"] == pytest.approx(2.8125)

    assert audit["identity"] is False
    assert audit["requested"] == profile
    assert audit["effective"]["domain_weights"][0] == {
        "domain_id": "task",
        "requested_weight": 2.0,
        "previous_points": 8.0,
        "effective_points": 20.0,
    }
    assert audit["effective"]["component_weights"][0]["previous_weight"] == 1.0
    assert audit["effective"]["question_weights"][0]["previous_weight"] == 2.0
    assert audit["effective"]["penalty_caps"][0]["previous_cap_points"] == 5.0

    before_metadata = [(item["module_id"], item["version"], item["title"]) for item in modules]
    after_metadata = [(item["module_id"], item["version"], item["title"]) for item in transformed_modules]
    before_text = {leaf["id"]: leaf["text"] for module in modules for leaf, _, _ in walk_tree(module["tree"])}
    after_text = {
        leaf["id"]: leaf["text"]
        for module in transformed_modules
        for leaf, _, _ in walk_tree(module["tree"])
    }
    assert after_metadata == before_metadata
    assert after_text == before_text


@pytest.mark.parametrize(
    ("collection", "records", "label"),
    [
        (
            "component_weights",
            [
                {"domain_id": "task", "module_id": "core.task_and_brief_fidelity", "weight": 1.0},
                {"domain_id": "task", "module_id": "core.task_and_brief_fidelity", "weight": 2.0},
            ],
            "Duplicate component",
        ),
        (
            "group_weights",
            [
                {"group_id": "core.task_and_brief_fidelity.quality", "weight": 1.0},
                {"group_id": "core.task_and_brief_fidelity.quality", "weight": 2.0},
            ],
            "Duplicate group",
        ),
        (
            "question_weights",
            [
                {"question_id": "core.task_and_brief_fidelity.intervention", "weight": 1.0},
                {"question_id": "core.task_and_brief_fidelity.intervention", "weight": 2.0},
            ],
            "Duplicate question",
        ),
        (
            "penalty_caps",
            [
                {"module_id": "penalty.repetition", "cap_points": 1.0},
                {"module_id": "penalty.repetition", "cap_points": 2.0},
            ],
            "Duplicate penalty cap",
        ),
    ],
)
def test_duplicate_semantic_override_keys_are_rejected(
    modules,
    bundle_by_id,
    collection: str,
    records: list[dict[str, Any]],
    label: str,
) -> None:
    with pytest.raises(HBQError, match=label):
        materialize_weight_profile(
            modules,
            bundle_by_id["prose.scene"],
            _profile(**{collection: records}),
        )


def test_duplicate_domain_key_is_rejected_before_coverage(modules, bundle_by_id) -> None:
    bundle = bundle_by_id["prose.scene"]
    weights = _domain_weights(bundle)
    weights.append({"domain_id": weights[0]["domain_id"], "weight": 3.0})
    with pytest.raises(HBQError, match="Duplicate domain"):
        materialize_weight_profile(modules, bundle, _profile(domain_weights=weights))


@pytest.mark.parametrize(
    ("profile", "message"),
    [
        (_profile(unit_weights=[{"unit_id": "chapter-1", "weight": 2.0}]), "Additional properties"),
        (_profile(question_weights=[]), "should be non-empty"),
        (
            _profile(
                question_weights=[
                    {
                        "question_id": "core.task_and_brief_fidelity.intervention",
                        "weight": 1.0,
                        "chapter_id": "chapter-1",
                    }
                ]
            ),
            "Additional properties",
        ),
        (
            _profile(
                component_weights=[
                    {"domain_id": "task", "module_id": "core.task_and_brief_fidelity", "weight": 0}
                ]
            ),
            "minimum of 0",
        ),
        (_profile(penalty_caps=[{"module_id": "penalty.repetition", "cap_points": -1}]), "minimum"),
    ],
)
def test_schema_rejects_non_strict_or_invalid_profiles(modules, bundle_by_id, profile, message) -> None:
    with pytest.raises(HBQError, match=message):
        materialize_weight_profile(modules, bundle_by_id["prose.scene"], profile)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_nonfinite_numbers_are_rejected(modules, bundle_by_id, value: float) -> None:
    profile = _profile(
        question_weights=[
            {"question_id": "core.task_and_brief_fidelity.intervention", "weight": value}
        ]
    )
    with pytest.raises(HBQError, match="finite"):
        materialize_weight_profile(modules, bundle_by_id["prose.scene"], profile)


def test_domain_overrides_require_exact_set_and_positive_total(modules, bundle_by_id) -> None:
    bundle = bundle_by_id["prose.scene"]
    missing = _domain_weights(bundle)[:-1]
    with pytest.raises(HBQError, match="exact domain set: missing"):
        materialize_weight_profile(modules, bundle, _profile(domain_weights=missing))

    unknown = _domain_weights(bundle)
    unknown[-1]["domain_id"] = "unknown-domain"
    with pytest.raises(HBQError, match="unknown unknown-domain"):
        materialize_weight_profile(modules, bundle, _profile(domain_weights=unknown))

    zero = [{**record, "weight": 0} for record in _domain_weights(bundle)]
    with pytest.raises(HBQError, match="positive total"):
        materialize_weight_profile(modules, bundle, _profile(domain_weights=zero))


def test_profile_bundle_binding_must_match(modules, bundle_by_id) -> None:
    with pytest.raises(HBQError, match="bound to bundle"):
        materialize_weight_profile(
            modules,
            bundle_by_id["prose.scene"],
            _profile(bundle_id="prose.chapter"),
        )


@pytest.mark.parametrize(
    ("profile", "message"),
    [
        (
            _profile(
                component_weights=[
                    {"domain_id": "task", "module_id": "core.language_craft", "weight": 2.0}
                ]
            ),
            "Component task/core.language_craft is outside",
        ),
        (
            _profile(group_weights=[{"group_id": "not.a.real.group", "weight": 2.0}]),
            "Unknown group_id",
        ),
        (
            _profile(
                group_weights=[
                    {"group_id": "form.audio.speech_text_fidelity.quality", "weight": 2.0}
                ]
            ),
            "outside the selected bundle",
        ),
        (
            _profile(question_weights=[{"question_id": "not.a.real.question", "weight": 2.0}]),
            "Unknown question_id",
        ),
        (
            _profile(
                question_weights=[
                    {"question_id": "form.audio.speech_text_fidelity.words", "weight": 2.0}
                ]
            ),
            "outside the selected bundle",
        ),
        (
            _profile(penalty_caps=[{"module_id": "core.language_craft", "cap_points": 2.0}]),
            "Penalty module core.language_craft is outside",
        ),
    ],
)
def test_unknown_and_out_of_bundle_catalog_keys_are_rejected(
    modules,
    bundle_by_id,
    profile: dict[str, Any],
    message: str,
) -> None:
    with pytest.raises(HBQError, match=message):
        materialize_weight_profile(modules, bundle_by_id["prose.scene"], profile)


def test_supplemental_and_hard_gate_only_question_weights_are_rejected(modules, bundle_by_id) -> None:
    with pytest.raises(HBQError, match="supplemental role.*does not affect scoring"):
        materialize_weight_profile(
            modules,
            bundle_by_id["prose.scene"],
            _profile(
                question_weights=[
                    {"question_id": "core.task_and_brief_fidelity.operation", "weight": 2.0}
                ]
            ),
        )

    with pytest.raises(HBQError, match="hard_gate role.*does not affect scoring"):
        materialize_weight_profile(
            modules,
            bundle_by_id["audio.audiobook"],
            _profile(
                question_weights=[
                    {"question_id": "form.audio.speech_text_fidelity.words", "weight": 2.0}
                ]
            ),
        )


@pytest.mark.parametrize("question_type", ["diagnostic", "hard_gate"])
def test_non_scoring_only_group_weights_are_rejected(question_type: str) -> None:
    modules = [
        {
            "module_id": "test.module",
            "version": 1,
            "title": "Synthetic module",
            "tree": [
                {
                    "id": "test.module.group",
                    "type": "group",
                    "weight": 1.0,
                    "children": [
                        {
                            "id": "test.module.question",
                            "type": "question",
                            "text": "Does the synthetic condition pass?",
                            "weight": 1.0,
                            "question_type": question_type,
                        }
                    ],
                }
            ],
        }
    ]
    bundle = {
        "bundle_id": "test.bundle",
        "version": 1,
        "domains": [
            {
                "domain_id": "test",
                "title": "Test",
                "points": 100.0,
                "components": [{"module_id": "test.module", "weight": 1.0}],
            }
        ],
        "module_ids": ["test.module"],
        "penalty_modules": [],
    }
    with pytest.raises(HBQError, match="does not affect scoring"):
        materialize_weight_profile(
            modules,
            bundle,
            _profile(group_weights=[{"group_id": "test.module.group", "weight": 2.0}]),
        )


def test_zero_domain_weight_and_zero_penalty_cap_are_valid(modules, bundle_by_id) -> None:
    bundle = bundle_by_id["prose.scene"]
    domain_weights = _domain_weights(bundle)
    domain_weights[0]["weight"] = 0
    transformed_modules, transformed_bundle, audit = materialize_weight_profile(
        modules,
        bundle,
        _profile(
            domain_weights=domain_weights,
            penalty_caps=[{"module_id": "penalty.repetition", "cap_points": 0}],
        ),
    )
    assert transformed_bundle["domains"][0]["points"] == 0
    assert audit["effective"]["penalty_caps"][0]["effective_cap_points"] == 0
    compile_bundle(transformed_modules, transformed_bundle)

    domain_weights = _domain_weights(bundle)
    domain_weights[-1]["weight"] = 0
    _, transformed_bundle, _ = materialize_weight_profile(
        modules,
        bundle,
        _profile(domain_weights=domain_weights),
    )
    assert transformed_bundle["domains"][-1]["points"] == 0
    assert sum(domain["points"] for domain in transformed_bundle["domains"]) == pytest.approx(100.0)


def test_complete_starter_profile_round_trips_every_scoring_layer(modules, bundle_by_id) -> None:
    bundle = bundle_by_id["prose.scene"]
    profile = make_weight_profile(modules, bundle, profile_id="starter")
    assert profile["bundle_id"] == "prose.scene"
    assert profile["domain_weights"]
    assert profile["component_weights"]
    assert profile["group_weights"]
    assert profile["question_weights"]
    transformed_modules, transformed_bundle, audit = materialize_weight_profile(
        modules, bundle, profile
    )
    assert audit["profile_id"] == "starter"
    assert compile_bundle(transformed_modules, transformed_bundle)["bundle_id"] == "prose.scene"
