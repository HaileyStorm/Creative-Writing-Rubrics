"""Add a saved metadata-membership proof without executing historical censuses."""
from __future__ import annotations

import argparse
from collections import Counter
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
POLICY = "historical_disposition_coverage_registry_v3"
V2_SHA = "311d8f79f667cb4730af5045e1b2e936b7fb8c53a12fed3d9649beb9d8879940"
FAMILIES = {
    "sentinel": "hbq-nonpoetry-scope-sentinel-v1-result-v1",
    "treatment": "hbq-nonpoetry-scope-treatment-v1-result-v1",
    "semantic": "hbq-nonpoetry-scope-semantic-boundary-successor-v1-public-result-v1",
    "disjoint": "hbq-nonpoetry-scope-disjoint-holdout-v1-execution-v1-public-result-v1",
    "clean": "hbq-poetry-free-verse-repetition-clean-na-successor-v1-execution-v1-public-result-v1",
}


def predecessor():
    import hashlib
    path = HERE / "registry_v2.py"
    if hashlib.sha256(path.read_bytes()).hexdigest() != V2_SHA:
        raise ValueError("Predecessor implementation differs")
    spec = importlib.util.spec_from_file_location("registry_v3_pinned_v2", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def metadata_edges(v2, report_raw, recipe_raw, packages, proof):
    fields = {"families": [{"family": True, "source_root_locator": True, "public_artifact": True}],
              "implementation_sha256": True, "recipe_sha256": True,
              "artifact_ledger_sha256": True, "provider_calls": True,
              "new_votes": True, "human_labels_opened": True}
    saved = v2.project(report_raw, fields)
    source = v2.project(recipe_raw, {"families": [{"id": True,
        "root_relative_to_documents": True, "public_artifact": True}]})
    v2.require(saved["implementation_sha256"] == proof["implementation"]["sha256"] and
               saved["recipe_sha256"] == v2.sha(recipe_raw) and
               saved["artifact_ledger_sha256"] == proof["receipt"]["sha256"],
               "Metadata proof identity differs")
    v2.require(saved["provider_calls"] == 0 and saved["new_votes"] == 0 and
               saved["human_labels_opened"] is False, "Metadata proof exceeds scope")
    roots = {f["id"]: f for f in source["families"]}
    observed = {f["family"]: f for f in saved["families"]}
    v2.require(len(source["families"]) == len(saved["families"]) == 5 and
               set(roots) == set(observed) == set(FAMILIES), "Five-root membership differs")
    pool = {p["id"]: p for p in packages}
    edges = []
    for family, package_id in FAMILIES.items():
        original, retained = roots[family], observed[family]
        v2.require(retained["source_root_locator"] == original["root_relative_to_documents"] and
                   retained["public_artifact"] == original["public_artifact"],
                   "Saved family locator/artifact differs")
        public = original["public_artifact"]
        v2.require(package_id in pool and
                   {"root": "repository", **public} in pool[package_id]["artifact_commitments"],
                   "Five-root public declaration is outside predecessor commitments")
        edges.append({"source_type": "declaration_package", "source": package_id,
                      "relationship": "metadata_membership_only", "census": proof["id"],
                      "family": family, "public_artifact": public,
                      "basis": "saved_frozen_membership_metadata_not_observed_leaves",
                      "observed_leaf_coverage": "not_established", "native_admission": "not_replayed",
                      "new_provider_votes": 0, "physical_contact_cardinality": None})
    return edges


def current_edges(v2, old, additions):
    replaced = set(FAMILIES.values())
    historical = [e for e in old if e["source_type"] == "declaration_package" and e["source"] in replaced]
    v2.require(len(historical) == 5 and {e["source"] for e in historical} == replaced and
               all(e["relationship"] == "unresolved_locator" and e.get("census") is None
                   for e in historical), "Superseded locator edges differ")
    current = [e for e in old if e not in historical] + additions
    identities = [(e["source_type"], e["source"], e["relationship"], e.get("census")) for e in current]
    v2.require(len(set(identities)) == len(current) == len(old), "Duplicate/current edge geometry differs")
    return current, historical


def run(recipe, roots):
    v2 = predecessor()
    v2.require(recipe["policy"] == POLICY, "Wrong registry policy")
    ledger = []
    previous = recipe["predecessor"]
    raw = {name: v2.checked(pin, roots, ledger) for name, pin in previous.items()}
    v2.require(previous["implementation"]["sha256"] == V2_SHA, "Wrong predecessor source")
    retained_recipe = json.loads(raw["recipe"])
    fields = {key: True for key in (
        "policy", "original_records", "original_references", "ancestor", "completed_censuses",
        "declaration_packages", "coverage_edges", "retained_sources", "relationship_semantics",
        "inventory", "input_commitment_sha256", "private_ledger_sha256", "lexical_reader_sha256",
        "provider_calls_made", "new_provider_votes", "native_admission", "scoring",
        "physical_contact_cardinality", "limitations", "recipe_file_sha256", "implementation_sha256")}
    report = v2.project(raw["report"], fields)
    terminal = v2.project(raw["receipt"], {"state": True, "report_sha256": True,
        "recipe_file_sha256": True, "implementation_sha256": True})
    v2.require(terminal == {"state": "completed", "report_sha256": v2.sha(raw["report"]),
        "recipe_file_sha256": v2.sha(raw["recipe"]), "implementation_sha256": V2_SHA},
        "Predecessor owning receipt differs")
    v2.require(report["policy"] == v2.POLICY and report["recipe_file_sha256"] == v2.sha(raw["recipe"])
               and report["implementation_sha256"] == V2_SHA, "Predecessor report differs")
    inv = report["inventory"]
    v2.require([inv[k] for k in ("original_records", "original_references", "completed_censuses",
        "declaration_packages", "coverage_edges", "unresolved_declaration_packages")] == [22, 7, 7, 76, 115, 66],
        "Predecessor frozen inventory differs")
    v2.require(report["coverage_edges"] == retained_recipe["coverage_edges"], "Predecessor edges differ")
    proof = recipe["metadata_census"]
    v2.require(proof["receipt_kind"] == "artifact_inventory_without_terminal", "Wrong metadata receipt kind")
    proof_raw = {name: v2.checked(proof[name], roots, ledger) for name in
                 ("implementation", "recipe", "report", "receipt")}
    additions = metadata_edges(v2, proof_raw["report"], proof_raw["recipe"],
                               report["declaration_packages"], proof)
    edges, historical = current_edges(v2, report["coverage_edges"], additions)
    census = {key: proof[key] for key in ("id", "implementation", "recipe", "report", "receipt", "receipt_kind")}
    census["basis"] = "saved_metadata_membership_proof_hash_binding_only_not_reexecuted"
    v2.require(proof["id"] not in {p["id"] for p in report["completed_censuses"]}, "Duplicate saved proof")
    report.update(schema_version=3, policy=POLICY, coverage_edges=edges,
                  completed_censuses=report["completed_censuses"] + [census],
                  historical_predecessor={"pins": previous, "superseded_locator_edges": historical,
                    "input_commitment_sha256": report["input_commitment_sha256"],
                    "private_ledger_sha256": report["private_ledger_sha256"]})
    report["relationship_semantics"]["metadata_membership_only"] = (
        "Qualified frozen slot/leaf/repeat membership locators only; no observed leaf, native admission or contact proof.")
    report["inventory"] = {**inv, "completed_censuses": 8, "coverage_edges": len(edges),
        "unresolved_declaration_packages": 61, "metadata_only_qualified_packages": 5,
        "relationships": dict(sorted(Counter(e["relationship"] for e in edges).items()))}
    report["limitations"].append("Five replaced locator gaps have metadata bindings only; observed-leaf/current-native/request/contact completeness remains unresolved.")
    private = {"policy": POLICY, "artifact_ledger": ledger}
    report.update(input_commitment_sha256=v2.sha(v2.canonical(ledger)),
                  private_ledger_sha256=v2.sha(v2.canonical(private)))
    return report, private


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--control-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    v2 = predecessor()
    roots = {"repository": REPO, "control": args.control_root.resolve()}
    output = args.output_root.resolve()
    raw = (HERE / "registry-v3.recipe.json").read_bytes()
    recipe = json.loads(raw)
    pins = [*recipe["predecessor"].values(), *(recipe["metadata_census"][k] for k in
             ("implementation", "recipe", "report", "receipt"))]
    v2.require(not output.exists() and not output.is_relative_to(REPO) and
        all(not output.is_relative_to((roots[p["root"]] / p["locator"]).parent) for p in pins),
        "Output must be fresh, outside repository and retained input directories")
    report, private = run(recipe, roots)
    report.update(recipe_file_sha256=v2.sha(raw), implementation_sha256=v2.sha(Path(__file__).read_bytes()))
    report_raw = v2.canonical(report)
    receipt = {"policy": POLICY, "report_sha256": v2.sha(report_raw), "recipe_file_sha256": v2.sha(raw),
        "implementation_sha256": report["implementation_sha256"], "private_ledger_sha256": report["private_ledger_sha256"],
        "inventory": report["inventory"], "provider_calls_made": 0, "new_provider_votes": 0, "dry_run": args.dry_run}
    if not args.dry_run:
        output.mkdir(parents=True, exist_ok=False)
        for name, content in {"registry.json": report_raw, "private-ledger.json": v2.canonical(private),
            "registry-v3.recipe.json": raw, "registry_v3.py": Path(__file__).read_bytes(),
            "terminal.json": v2.canonical({**receipt, "state": "completed"})}.items():
            with (output / name).open("xb") as stream:
                stream.write(content)
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
