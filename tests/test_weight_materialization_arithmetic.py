"""Materialization rejects arithmetic-invalid profiles before downstream use."""
from copy import deepcopy
import pytest
from hbqrs import HBQError, compile_bundle
from hbqrs.weights import materialize_weight_profile


def test_weight_materialization_arithmetic_admission(modules, bundle_by_id):
    bundle = bundle_by_id["prose.short_story"]
    original = deepcopy((modules, bundle))

    def profile(**overrides):
        return {"profile_version": 1, "profile_id": "arithmetic-admission", **overrides}

    for magnitude in (1e308, 1e-200):
        with pytest.raises(HBQError, match="effective weight"):
            materialize_weight_profile(modules, bundle, profile(
                component_weights=[{"domain_id": "task", "module_id": "core.task_and_brief_fidelity", "weight": magnitude}],
                question_weights=[{"question_id": "core.task_and_brief_fidelity.intervention", "weight": magnitude}],
            ))
    with pytest.raises(HBQError, match="total domain weight"):
        materialize_weight_profile(modules, bundle, profile(component_weights=[
            {"domain_id": d["domain_id"], "module_id": c["module_id"], "weight": 1e307}
            for d in bundle["domains"] for c in d["components"]
        ]))
    with pytest.raises(HBQError, match="finite total"):
        materialize_weight_profile(modules, bundle, profile(domain_weights=[
            {"domain_id": d["domain_id"], "weight": 1e308} for d in bundle["domains"]
        ]))

    # A normal admitted profile retains its exact effective scoring weight.
    changed, selected, audit = materialize_weight_profile(modules, bundle, profile(
        component_weights=[{"domain_id": "task", "module_id": "core.task_and_brief_fidelity", "weight": 2.0}],
    ))
    before = compile_bundle(modules, bundle)
    after = compile_bundle(changed, selected)
    prior = {r["question"]["id"]: r for r in before["domain_questions"]}
    for row in after["domain_questions"]:
        expected = prior[row["question"]["id"]]["effective_weight"]
        if row["module_id"] == "core.task_and_brief_fidelity":
            expected *= 2
        assert row["effective_weight"] == expected
    assert audit["identity"] is False
    assert (modules, bundle) == original
    identity = materialize_weight_profile(modules, bundle)
    assert identity[0] == modules and identity[0] is not modules
    assert identity[1] == bundle and identity[1] is not bundle
