import copy
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "evaluation-results/hbq-census-pass-b-dispositions-v1/registry_v3.py"
spec = importlib.util.spec_from_file_location("census_registry_v3_test", PATH)
r = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r)


def test_five_exact_bindings_replace_only_locator_edges_and_skip_excluded_values():
    v2 = r.predecessor()
    recipe = json.loads((PATH.parent / "registry-v3.recipe.json").read_bytes())
    proof = recipe["metadata_census"]
    old = json.loads((PATH.parent / "registry-v2.recipe.json").read_bytes())
    packages = [{"id": p["id"], "artifact_commitments": p["artifacts"]}
                for p in old["declaration_packages"]]
    sources = []
    families = []
    for family, package_id in r.FAMILIES.items():
        artifacts = next(p["artifact_commitments"] for p in packages if p["id"] == package_id)
        artifact = next(p for p in artifacts if p["locator"].endswith(".json"))
        public = {key: artifact[key] for key in ("locator", "sha256", "bytes")}
        sources.append({"id": family, "root_relative_to_documents": family, "public_artifact": public})
        families.append({"family": family, "source_root_locator": family, "public_artifact": public})
    source_raw = v2.canonical({"families": sources})
    saved = {"families": families, "implementation_sha256": proof["implementation"]["sha256"],
             "recipe_sha256": v2.sha(source_raw), "artifact_ledger_sha256": proof["receipt"]["sha256"],
             "provider_calls": 0, "new_votes": 0, "human_labels_opened": False}
    # Invalid excluded string escape demonstrates lexical skipping before value decoding.
    raw = v2.canonical(saved).rstrip()[:-1] + b',"observed_metadata":"\\q"}'
    edges = r.metadata_edges(v2, raw, source_raw, packages, proof)
    current, historical = r.current_edges(v2, old["coverage_edges"], edges)
    assert len(current) == 115 and len(historical) == 5
    assert [e for e in current if e not in edges] == [e for e in old["coverage_edges"] if e not in historical]
    assert {e["source"] for e in edges} == set(r.FAMILIES.values())
    assert all(e["new_provider_votes"] == 0 and e["physical_contact_cardinality"] is None and
               e["observed_leaf_coverage"] == "not_established" for e in edges)
    altered = copy.deepcopy(saved)
    altered["families"][0]["public_artifact"]["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="locator/artifact differs"):
        r.metadata_edges(v2, v2.canonical(altered), source_raw, packages, proof)
    with pytest.raises(ValueError, match="Superseded locator"):
        r.current_edges(v2, current, edges)
