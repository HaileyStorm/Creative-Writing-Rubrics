import copy
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "evaluation-results/hbq-census-pass-b-dispositions-v1/registry_v4.py"
spec = importlib.util.spec_from_file_location("registry_v4_test", PATH)
r = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r)


def test_exact_commitment_join_inherits_counts_and_replaces_only_one_edge():
    v2 = r.predecessor()
    recipe = json.loads((PATH.parent / "registry-v4.recipe.json").read_bytes())
    e = recipe["census_e"]
    pins = {key: {field: e[key][field] for field in ("sha256", "bytes")}
            for key in ("source_summary", "source_provenance")}
    private = {"files": {"summary.json": pins["source_summary"],
                         "consolidation-provenance.json": pins["source_provenance"]}}
    public = {"completed_analysis_commitments": {"summary_sha256": e["source_summary"]["sha256"],
                "consolidation_provenance_sha256": e["source_provenance"]["sha256"]}}
    e_recipe = {"assets": {field: [e[name][k] for k in ("locator", "sha256", "bytes")]
        for name, field in (("source_summary", "summary"), ("source_provenance", "provenance"),
                            ("private_manifest", "manifest"))}, "expected_counts": recipe["inherited_counts"]}
    summary = {"implementation_sha256": e["implementation"]["sha256"],
               "recipe_file_sha256": e["recipe"]["sha256"], "observed": recipe["inherited_counts"],
               "provider_calls_made": 0, "new_provider_votes": 0}
    assets = {key: v2.canonical(value) for key, value in (("public_manifest", public),
              ("private_manifest", private), ("recipe", e_recipe), ("summary", summary))}
    # Excluded metrics are skipped lexically, before decoding their malformed value.
    assets["summary"] = assets["summary"].rstrip()[:-1] + b',"alignment_metrics":"\\q"}'
    packages = [{"id": r.TARGET, "artifact_commitments": [e["public_manifest"]]}]
    references = [{"id": "E", **e["summary"], "basis": "retained_reference_metadata"}]
    replacement = r.source_binding(v2, recipe, packages, references, assets)
    assert replacement["inherited_counts"] == {"accepted_logical_cells": 330, "accepted_units": 605, "native_leaf_rows": 9845}
    assert replacement["fresh_observations"] == replacement["new_provider_votes"] == 0
    assert replacement["census_namespace"] == "original_reference"
    old = {"source_type": "declaration_package", "source": r.TARGET,
           "relationship": "unresolved_locator", "census": None}
    other = {"source_type": "declaration_package", "source": "untouched-other",
             "relationship": "unresolved_locator", "census": None}
    current, history = r.replace_edge(v2, [old, other], replacement)
    assert current == [replacement, other] and history == [old]
    with pytest.raises(ValueError, match="one unresolved"):
        r.replace_edge(v2, [old, old, other], replacement)
    altered = copy.deepcopy(public)
    altered["completed_analysis_commitments"]["summary_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="source commitment differs"):
        r.source_binding(v2, recipe, packages, references,
                         {**assets, "public_manifest": v2.canonical(altered)})


def test_changed_source_body_rejects_without_decoding(tmp_path):
    v2 = r.predecessor()
    path = tmp_path / "summary.json"
    path.write_bytes(b'{"sealed_answer":"never decode"}')
    pin = {"root": "documents", "locator": path.name, "sha256": v2.sha(path.read_bytes()),
           "bytes": path.stat().st_size}
    path.write_bytes(b'{"sealed_answer":"changed body"}')
    with pytest.raises(ValueError, match="Input commitment differs"):
        v2.checked(pin, {"documents": tmp_path}, [])
