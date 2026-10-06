import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("regeneration_v2_test", ROOT /
    "evaluation-results/hbq-census-pass-b-dispositions-v1/regenerate_v2.py")
r = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r)


def test_inherited_join_is_not_a_new_cohort_or_unresolved_locator():
    v1 = r.predecessor()
    pin = {"root": "repository", "locator": "E.json", "sha256": "a" * 64, "bytes": 10}
    counts = {"accepted_logical_cells": 330, "accepted_units": 605, "native_leaf_rows": 9845}
    binding = {"id": "E", "pins": {"summary": pin}, "counts": counts, "basis": "inherited"}
    def edge(source, relationship, census=None, **extra):
        return {"source_type": "declaration_package", "source": source,
                "relationship": relationship, "census": census, **extra}
    inherited = edge("reference", "joins_existing_positions", "E", census_namespace="original_reference",
                     inherited_counts=counts, basis="inherited", fresh_observations=0, new_provider_votes=0)
    registry = {"declaration_packages": [{"id": p, "locator": p, "artifact_commitments": []}
        for p in ("reference", "unknown", "ancestor", "metadata", "nonvoting")],
        "coverage_edges": [inherited, edge("unknown", "unresolved_locator"),
            edge("ancestor", "excluded_ancestor", "observed"),
            edge("ancestor", "joins_existing_positions", "observed"),
            edge("metadata", "metadata_membership_only", "metadata"),
            edge("nonvoting", "nonvoting_output", "observed")],
        "original_references": [{"id": "E", **pin}], "inherited_census_reference_binding": binding,
        "inventory": {"unresolved_declaration_packages": 1}}
    cohorts = [{"id": "observed"}, {"id": "metadata"}]
    packages = r.package_dispositions(v1, registry, cohorts)
    assert packages[0]["status"] == "inherited_reference_joined"
    assert packages[0]["regeneration_cohorts"] == []
    assert packages[0]["inherited_reference_joins"][0]["counts"] == counts
    assert sum(not p["regeneration_cohorts"] for p in packages) == 2
    assert sum(p["status"] == "unresolved_locator" for p in packages) == 1
    assert packages[2]["regeneration_cohorts"] == ["observed"]
    assert sum(p["additional_observed_votes_from_declaration"] for p in packages) == 0
    inherited["inherited_counts"] = {**counts, "accepted_units": 606}
    with pytest.raises(ValueError, match="inherited reference binding differs"):
        r.package_dispositions(v1, registry, cohorts)


def test_historical_reuse_binds_recipe_descriptor_and_saved_artifacts(tmp_path):
    v1 = r.predecessor()
    recipe = json.loads((r.HERE / "regenerate-v2.recipe.json").read_bytes())
    saved_recipe = (r.HERE / "regenerate-v1.recipe.json").read_bytes()
    old = json.loads(saved_recipe)
    item = next(c for c in old["cohorts"] if c["id"] == "native_f")
    report = {"basis": "regenerated_from_retained_census_metadata", "observed": {"logical_positions": 2300}}
    private = {"positions": []}
    receipt = {"implementation_sha256": item["implementation"]["sha256"],
        "recipe_sha256": item["recipe"]["sha256"], "cohort_descriptor_sha256": v1.sha(v1.canonical(item)),
        "report_sha256": v1.sha(v1.canonical(report)), "private_sha256": v1.sha(v1.canonical(private))}
    checkpoint = v1.canonical({"policy": v1.POLICY, "recipe_sha256": v1.sha(saved_recipe),
                               "completed": {item["id"]: receipt}})
    (tmp_path / "regenerate-v1.recipe.json").write_bytes(saved_recipe)
    (tmp_path / "checkpoint.json").write_bytes(checkpoint)
    base = tmp_path / "cohorts" / item["id"]
    base.mkdir(parents=True)
    (base / "report.json").write_bytes(v1.canonical(report))
    (base / "private.json").write_bytes(v1.canonical(private))
    reused, provenance = r.read_reuse(v1, tmp_path, v1.sha(checkpoint), recipe)
    assert provenance["policy"] == v1.POLICY
    assert v1.reuse_cohort(item, tmp_path, reused[item["id"]]) == (report, private)
    item["retained_metadata"]["base_ledger"]["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="Reuse cohort pins differ"):
        v1.reuse_cohort(item, tmp_path, reused[item["id"]])
    (tmp_path / "regenerate-v1.recipe.json").write_bytes(saved_recipe + b"\n")
    with pytest.raises(ValueError, match="Reuse recipe/policy differs"):
        r.read_reuse(v1, tmp_path, v1.sha(checkpoint), recipe)
