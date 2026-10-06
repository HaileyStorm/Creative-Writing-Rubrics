"""Join one public declaration to retained Census E source commitments."""
from __future__ import annotations

import argparse
from collections import Counter
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
POLICY = "historical_disposition_coverage_registry_v4"
V3_SHA = "229a0edb42e52ba5f974f8630b58e78f4c1347d8500ef597b4e88ec4e5a55fd7"
TARGET = "hbq-multisample-repeatability-v1-completed-result-v1"


def predecessor():
    import hashlib
    path = HERE / "registry_v3.py"
    if hashlib.sha256(path.read_bytes()).hexdigest() != V3_SHA:
        raise ValueError("Predecessor implementation differs")
    spec = importlib.util.spec_from_file_location("registry_v4_pinned_v3", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.predecessor()


def source_binding(v2, recipe, packages, references, assets):
    source = recipe["census_e"]
    require = v2.require
    public_pin = source["public_manifest"]
    matches = [p for p in packages if p["id"] == TARGET]
    require(len(matches) == 1 and public_pin in matches[0]["artifact_commitments"],
            "Multisample declaration commitment differs")
    reference = [r for r in references if r["id"] == "E"]
    require(len(reference) == 1 and {key: reference[0][key] for key in source["summary"]} == source["summary"],
            "Census E original reference differs")
    public = v2.project(assets["public_manifest"], {"completed_analysis_commitments": {
        "summary_sha256": True, "consolidation_provenance_sha256": True}})["completed_analysis_commitments"]
    private = v2.project(assets["private_manifest"], {"files": {
        "summary.json": {"sha256": True, "bytes": True},
        "consolidation-provenance.json": {"sha256": True, "bytes": True}}})["files"]
    e_recipe = v2.project(assets["recipe"], {"assets": {"summary": True, "provenance": True, "manifest": True},
        "expected_counts": {"accepted_logical_cells": True, "accepted_units": True, "native_leaf_rows": True}})
    for name, field in (("source_summary", "summary"), ("source_provenance", "provenance"),
                        ("private_manifest", "manifest")):
        pin = source[name]
        require(e_recipe["assets"][field] == [pin["locator"], pin["sha256"], pin["bytes"]],
                "Census E recipe source differs")
        if field != "manifest":
            key = "summary_sha256" if field == "summary" else "consolidation_provenance_sha256"
            filename = "summary.json" if field == "summary" else "consolidation-provenance.json"
            require(public[key] == pin["sha256"] and private[filename] == {
                "sha256": pin["sha256"], "bytes": pin["bytes"]}, "Public/private source commitment differs")
    summary = v2.project(assets["summary"], {"implementation_sha256": True, "recipe_file_sha256": True,
        "observed": {"accepted_logical_cells": True, "accepted_units": True, "native_leaf_rows": True},
        "provider_calls_made": True, "new_provider_votes": True})
    require(summary["implementation_sha256"] == source["implementation"]["sha256"] and
            summary["recipe_file_sha256"] == source["recipe"]["sha256"] and
            summary["observed"] == e_recipe["expected_counts"] == recipe["inherited_counts"] and
            summary["provider_calls_made"] == summary["new_provider_votes"] == 0,
            "Retained Census E count/source binding differs")
    return {"source_type": "declaration_package", "source": TARGET,
            "relationship": "joins_existing_positions", "census": "E", "census_namespace": "original_reference",
            "basis": "saved_census_e_source_commitment_join_only_not_reexecuted",
            "inherited_counts": summary["observed"], "fresh_observations": 0,
            "current_native_admission": "not_replayed", "physical_contact_cardinality": None,
            "new_provider_votes": 0}


def replace_edge(v2, edges, replacement):
    old = [e for e in edges if e["source_type"] == "declaration_package" and e["source"] == TARGET]
    v2.require(len(old) == 1 and old[0]["relationship"] == "unresolved_locator" and
               old[0].get("census") is None, "Expected one unresolved multisample edge")
    current = [replacement if e == old[0] else e for e in edges]
    identities = [(e["source_type"], e["source"], e["relationship"], e.get("census")) for e in current]
    v2.require(len(set(identities)) == len(current), "Duplicate registry edge")
    return current, old


def run(recipe, roots):
    v2 = predecessor()
    v2.require(recipe["policy"] == POLICY, "Wrong registry policy")
    ledger = []
    previous = recipe["predecessor"]
    raw = {key: v2.checked(pin, roots, ledger) for key, pin in previous.items()}
    v2.require(previous["implementation"]["sha256"] == V3_SHA, "Wrong predecessor source")
    fields = {key: True for key in (
        "policy", "original_records", "original_references", "ancestor", "completed_censuses",
        "declaration_packages", "coverage_edges", "retained_sources", "relationship_semantics", "inventory",
        "input_commitment_sha256", "private_ledger_sha256", "lexical_reader_sha256", "provider_calls_made",
        "new_provider_votes", "native_admission", "scoring", "physical_contact_cardinality", "limitations",
        "recipe_file_sha256", "implementation_sha256", "historical_predecessor")}
    report = v2.project(raw["report"], fields)
    terminal = v2.project(raw["receipt"], {"state": True, "report_sha256": True,
        "recipe_file_sha256": True, "implementation_sha256": True})
    v2.require(terminal == {"state": "completed", "report_sha256": v2.sha(raw["report"]),
        "recipe_file_sha256": v2.sha(raw["recipe"]), "implementation_sha256": V3_SHA} and
        report["policy"] == "historical_disposition_coverage_registry_v3" and
        report["recipe_file_sha256"] == v2.sha(raw["recipe"]) and report["implementation_sha256"] == V3_SHA,
        "Saved v3 report/receipt binding differs")
    inv = report["inventory"]
    v2.require([inv[k] for k in ("declaration_packages", "coverage_edges", "completed_censuses",
        "metadata_only_qualified_packages", "unresolved_declaration_packages")] == [76, 115, 8, 5, 61],
        "V3 inventory differs")
    assets = {key: v2.checked(pin, roots, ledger) for key, pin in recipe["census_e"].items()}
    replacement = source_binding(v2, recipe, report["declaration_packages"], report["original_references"], assets)
    current, old = replace_edge(v2, report["coverage_edges"], replacement)
    private = {"policy": POLICY, "artifact_ledger": ledger}
    report.update(schema_version=4, policy=POLICY, coverage_edges=current,
        historical_predecessor_v3={"pins": previous, "superseded_locator_edges": old,
            "input_commitment_sha256": report["input_commitment_sha256"],
            "private_ledger_sha256": report["private_ledger_sha256"]},
        inherited_census_reference_binding={"id": "E", "pins": recipe["census_e"],
            "counts": recipe["inherited_counts"], "basis": replacement["basis"]})
    report["inventory"] = {**inv, "unresolved_declaration_packages": 60,
        "relationships": dict(sorted(Counter(e["relationship"] for e in current).items()))}
    report["limitations"].append("Multisample locator joins retained Census E source commitments only; its counts are inherited and native/body/admission/scoring evidence is not reexecuted.")
    report.update(input_commitment_sha256=v2.sha(v2.canonical(ledger)),
                  private_ledger_sha256=v2.sha(v2.canonical(private)))
    return report, private


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    for name in ("documents-root", "control-root", "output-root"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    v2 = predecessor()
    roots = {"repository": REPO, "documents": args.documents_root.resolve(), "control": args.control_root.resolve()}
    raw = (HERE / "registry-v4.recipe.json").read_bytes()
    recipe = json.loads(raw)
    pins = [*recipe["predecessor"].values(), *recipe["census_e"].values()]
    output = args.output_root.resolve()
    v2.require(not output.exists() and not output.is_relative_to(REPO) and
        all(not output.is_relative_to((roots[p["root"]] / p["locator"]).parent) for p in pins),
        "Fresh output outside repository/retained inputs required")
    report, private = run(recipe, roots)
    report.update(recipe_file_sha256=v2.sha(raw), implementation_sha256=v2.sha(Path(__file__).read_bytes()))
    report_raw = v2.canonical(report)
    receipt = {"policy": POLICY, "report_sha256": v2.sha(report_raw), "recipe_file_sha256": v2.sha(raw),
        "implementation_sha256": report["implementation_sha256"], "private_ledger_sha256": report["private_ledger_sha256"],
        "inventory": report["inventory"], "inherited_counts": recipe["inherited_counts"],
        "provider_calls_made": 0, "new_provider_votes": 0, "dry_run": args.dry_run}
    if not args.dry_run:
        output.mkdir(parents=True, exist_ok=False)
        for name, content in {"registry.json": report_raw, "private-ledger.json": v2.canonical(private),
            "registry-v4.recipe.json": raw, "registry_v4.py": Path(__file__).read_bytes(),
            "terminal.json": v2.canonical({**receipt, "state": "completed"})}.items():
            with (output / name).open("xb") as stream:
                stream.write(content)
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
