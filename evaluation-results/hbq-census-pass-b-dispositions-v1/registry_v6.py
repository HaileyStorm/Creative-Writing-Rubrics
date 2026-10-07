"""Qualify the saved WPB metadata census without replaying historical measurements."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
POLICY = "historical_disposition_coverage_registry_v6"
V5_SHA = "ba72c637c77dec8a04f2a402d0e2a812f5e15c09dce08e4271a0e3cd99f1b8d5"
TARGET = "hbq-human-alignment-wpb-sol-completed-result-v1"
CENSUS_ID = "wpb_completed_metadata"
REPORT_FIELDS = {key: True for key in (
    "policy", "original_records", "original_references", "ancestor", "completed_censuses",
    "declaration_packages", "coverage_edges", "retained_sources", "relationship_semantics", "inventory",
    "input_commitment_sha256", "private_ledger_sha256", "lexical_reader_sha256", "provider_calls_made",
    "new_provider_votes", "native_admission", "scoring", "physical_contact_cardinality", "limitations",
    "recipe_file_sha256", "implementation_sha256", "historical_predecessor", "historical_predecessor_v3",
    "historical_predecessor_v4", "inherited_census_reference_binding", "inherited_revision_cohort_binding")}


def load_census(recipe):
    pin = recipe["wpb"]["implementation"]
    path = REPO / pin["locator"]
    raw = path.read_bytes()
    if pin["root"] != "repository" or hashlib.sha256(raw).hexdigest() != pin["sha256"] or len(raw) != pin["bytes"]:
        raise ValueError("WPB metadata implementation differs")
    spec = importlib.util.spec_from_file_location("registry_v6_wpb_metadata", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def declared_pins(value):
    if isinstance(value, dict):
        if {"root", "locator", "sha256", "bytes"}.issubset(value):
            yield {key: value[key] for key in ("root", "locator", "sha256", "bytes")}
        else:
            for nested in value.values():
                yield from declared_pins(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from declared_pins(nested)


def run(recipe, roots):
    census = load_census(recipe)
    v2 = census.common()
    require, project = v2.require, v2.project
    require(recipe["policy"] == POLICY and recipe["schema_version"] == 6, "Wrong registry policy")
    ledger = []

    def checked(pin):
        raw = census.checked(pin, roots)
        ledger.append(pin)
        return raw

    previous = recipe["predecessor"]
    old = {key: checked(pin) for key, pin in previous.items()}
    require(previous["implementation"]["sha256"] == V5_SHA and
            v2.sha((HERE / "registry_v5.py").read_bytes()) == V5_SHA, "Saved/current v5 implementation differs")
    report = project(old["report"], REPORT_FIELDS)
    terminal_fields = {key: True for key in (
        "state", "report_sha256", "recipe_file_sha256", "implementation_sha256", "private_ledger_sha256",
        "inventory", "provider_calls_made", "new_provider_votes", "dry_run")}
    terminal = project(old["receipt"], terminal_fields)
    require(terminal == {"state": "completed", "report_sha256": v2.sha(old["report"]),
        "recipe_file_sha256": v2.sha(old["recipe"]), "implementation_sha256": V5_SHA,
        "private_ledger_sha256": v2.sha(old["private_ledger"]), "inventory": report["inventory"],
        "provider_calls_made": 0, "new_provider_votes": 0, "dry_run": False} and
        report["policy"] == "historical_disposition_coverage_registry_v5" and
        report["recipe_file_sha256"] == v2.sha(old["recipe"]) and
        report["implementation_sha256"] == V5_SHA and
        report["private_ledger_sha256"] == v2.sha(old["private_ledger"]), "Saved v5 report/receipt binding differs")
    old_recipe = json.loads(old["recipe"])
    require(old_recipe["policy"] == report["policy"], "Saved v5 recipe policy differs")
    for pin in declared_pins(old_recipe):
        checked(pin)
    inv = report["inventory"]
    require([inv[key] for key in ("declaration_packages", "coverage_edges", "completed_censuses",
        "metadata_only_qualified_packages", "unresolved_declaration_packages")] == [76, 115, 8, 5, 58],
        "Saved v5 inventory differs")
    assets = {key: checked(pin) for key, pin in recipe["wpb"].items()}
    wpb_recipe = json.loads(assets["recipe"])
    saved_fields = {key: True for key in (
        "policy", "observed", "source_descriptor_sha256", "static_source_descriptor_sha256", "input_commitment_sha256", "committed_files",
        "measurement_commitment_sha256", "ancestor_occurrence_commitment_sha256", "public_source_binding",
        "recipe_file_sha256", "implementation_sha256", "private_ledger_sha256", "provider_calls_made",
        "new_provider_votes", "human_labels_opened", "native_admission", "scoring", "observed_leaf_coverage",
        "physical_contact_cardinality", "internal_retry_cardinality", "requested_model",
        "requested_reasoning_effort", "reasoning_attested")}
    saved = project(assets["report"], saved_fields)
    receipt = project(assets["receipt"], {key: True for key in (
        "policy", "state", "report_sha256", "recipe_file_sha256", "implementation_sha256",
        "private_ledger_sha256", "observed", "provider_calls_made", "new_provider_votes", "dry_run")})
    require(receipt == {"policy": census.POLICY, "state": "completed",
        "report_sha256": v2.sha(assets["report"]), "recipe_file_sha256": v2.sha(assets["recipe"]),
        "implementation_sha256": recipe["wpb"]["implementation"]["sha256"],
        "private_ledger_sha256": v2.sha(assets["private_ledger"]), "observed": saved["observed"],
        "provider_calls_made": 0, "new_provider_votes": 0, "dry_run": False}, "WPB completed receipt differs")
    require(saved["policy"] == wpb_recipe["policy"] == census.POLICY and
        saved["recipe_file_sha256"] == v2.sha(assets["recipe"]) and
        saved["implementation_sha256"] == recipe["wpb"]["implementation"]["sha256"] and
        saved["private_ledger_sha256"] == v2.sha(assets["private_ledger"]) and
        saved["static_source_descriptor_sha256"] == v2.sha(v2.canonical(wpb_recipe["sources"])) and
        saved["observed"] == wpb_recipe["expected_counts"] == recipe["expected_wpb_counts"] and
        saved["provider_calls_made"] == saved["new_provider_votes"] == 0 and
        saved["human_labels_opened"] is False and saved["native_admission"] == saved["scoring"] == "not_replayed" and
        saved["observed_leaf_coverage"] == "not_established" and saved["physical_contact_cardinality"] is None and
        saved["internal_retry_cardinality"] is None and saved["reasoning_attested"] is False,
        "WPB census scope/source binding differs")
    private = project(assets["private_ledger"], {"policy": True, "artifact_ledger": True,
        "measurements": True, "ancestor_status_occurrences": True})
    require(private["policy"] == census.POLICY and
        private["artifact_ledger"][:len(wpb_recipe["sources"])] == wpb_recipe["sources"] and
        len(private["artifact_ledger"]) == saved["committed_files"] == 158 and
        saved["source_descriptor_sha256"] == saved["input_commitment_sha256"] == v2.sha(v2.canonical(private["artifact_ledger"])) and
        saved["measurement_commitment_sha256"] == v2.sha(v2.canonical(private["measurements"])) and
        saved["ancestor_occurrence_commitment_sha256"] == v2.sha(v2.canonical(private["ancestor_status_occurrences"])),
        "WPB private aggregate commitments differ")
    for pin in private["artifact_ledger"]:
        checked(pin)
    indexed = {pin["id"]: pin for pin in private["artifact_ledger"]}
    require(len(indexed) == 158, "Duplicate WPB private artifact identity")
    require(saved["public_source_binding"] == {key: indexed[key] for key in (
        "public-provenance", "public-aggregate", "final-report", "completion")}, "WPB public/private sources differ")
    packages = [package for package in report["declaration_packages"] if package["id"] == TARGET]
    require(len(packages) == 1 and all({key: indexed[name][key] for key in ("root", "locator", "sha256", "bytes")}
        in packages[0]["artifact_commitments"] for name in ("public-provenance", "public-aggregate")),
        "WPB public sources differ from saved v5 declaration")
    old_edges = [edge for edge in report["coverage_edges"] if edge["source_type"] == "declaration_package" and edge["source"] == TARGET]
    require(len(old_edges) == 1 and old_edges[0]["relationship"] == "unresolved_locator" and
        old_edges[0].get("census") is None and all(c["id"] != CENSUS_ID for c in report["completed_censuses"]),
        "Expected one unresolved WPB edge and fresh census name")
    replacement = {"source_type": "declaration_package", "source": TARGET, "relationship": "metadata_membership_only",
        "census": CENSUS_ID, "census_namespace": "completed_census", "basis": "saved_completed_wpb_metadata_source_commitment_join_only",
        "metadata_counts": saved["observed"], "fresh_observations": 0, "new_provider_votes": 0,
        "observed_leaf_coverage": "not_established", "native_admission": "not_replayed", "scoring": "not_replayed",
        "physical_contact_cardinality": None, "internal_retry_cardinality": None}
    current = [replacement if edge == old_edges[0] else edge for edge in report["coverage_edges"]]
    require(len({(e["source_type"], e["source"], e["relationship"], e.get("census")) for e in current}) == len(current) == 115,
        "Registry edge identity/count differs")
    report["completed_censuses"].append({"id": CENSUS_ID, "recipe": recipe["wpb"]["recipe"],
        "report": recipe["wpb"]["report"], "receipt": recipe["wpb"]["receipt"], "receipt_kind": "completed_terminal",
        "basis": "saved_metadata_only_proof_hash_binding_not_reexecuted", "observed_leaf_coverage": "not_established"})
    report.update(schema_version=6, policy=POLICY, coverage_edges=current,
        historical_predecessor_v5={"pins": previous, "superseded_locator_edges": old_edges,
            "input_commitment_sha256": report["input_commitment_sha256"],
            "private_ledger_sha256": report["private_ledger_sha256"]},
        qualified_wpb_metadata_binding={"id": CENSUS_ID, "pins": recipe["wpb"], "counts": saved["observed"],
            "source_descriptor_sha256": saved["source_descriptor_sha256"], "fresh_observations": 0})
    report["inventory"] = {**inv, "completed_censuses": 9, "metadata_only_qualified_packages": 6,
        "unresolved_declaration_packages": 57, "relationships": dict(sorted(Counter(e["relationship"] for e in current).items()))}
    report["limitations"].append("WPB contributes a completed metadata-only census and qualifies one existing declaration edge; 129 historical receipt joins and 40 namespaced ancestor status occurrences add no votes, leaves or physical contact counts.")
    private_output = {"policy": POLICY, "artifact_ledger": ledger}
    report.update(input_commitment_sha256=v2.sha(v2.canonical(ledger)),
                  private_ledger_sha256=v2.sha(v2.canonical(private_output)))
    return report, private_output, census


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    for name in ("documents-root", "control-root", "output-root"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    recipe_raw = (HERE / "registry-v6.recipe.json").read_bytes()
    recipe = json.loads(recipe_raw)
    census = load_census(recipe)
    v2 = census.common()
    roots = {"repository": REPO, "documents": args.documents_root.resolve(), "control": args.control_root.resolve()}
    output = census.output_preflight(args.output_root, list(declared_pins(recipe)), roots)
    v2.require(all(not output.is_relative_to(census.source_path(binding["report"], roots).parent)
        for binding in (recipe["predecessor"], recipe["wpb"])), "Output overlaps retained census/registry directory")
    source_recipe = json.loads(census.checked(recipe["wpb"]["recipe"], roots))
    v2.require(source_recipe["policy"] == census.POLICY, "Wrong saved WPB source recipe")
    census.output_preflight(output, source_recipe["sources"], roots)
    v2.require(all(not output.is_relative_to((roots["documents"] / locator).resolve()) for locator in
        (census.CAMPAIGN, *census.PREFIX_ROOTS)), "Output overlaps retained WPB campaign root")
    final_report_pin = next(pin for pin in source_recipe["sources"] if pin["id"] == "final-report")
    v2.require(not output.is_relative_to(census.source_path(final_report_pin, roots).parent),
        "Output overlaps retained WPB final report directory")
    implementation_raw = Path(__file__).read_bytes()
    report, private, _ = run(recipe, roots)
    report.update(recipe_file_sha256=v2.sha(recipe_raw), implementation_sha256=v2.sha(implementation_raw))
    report_raw = v2.canonical(report)
    receipt = {"policy": POLICY, "report_sha256": v2.sha(report_raw), "recipe_file_sha256": v2.sha(recipe_raw),
        "implementation_sha256": report["implementation_sha256"], "private_ledger_sha256": report["private_ledger_sha256"],
        "inventory": report["inventory"], "provider_calls_made": 0, "new_provider_votes": 0, "dry_run": args.dry_run}
    for pin in private["artifact_ledger"]:
        census.checked(pin, roots)
    v2.require((HERE / "registry-v6.recipe.json").read_bytes() == recipe_raw and
        Path(__file__).read_bytes() == implementation_raw, "Registry source changed during execution")
    if not args.dry_run:
        output.mkdir(parents=True, exist_ok=False)
        for name, content in {"registry.json": report_raw, "private-ledger.json": v2.canonical(private),
            "registry-v6.recipe.json": recipe_raw, "registry_v6.py": implementation_raw}.items():
            with (output / name).open("xb") as stream:
                stream.write(content)
        with (output / "terminal.json").open("xb") as stream:
            stream.write(v2.canonical({**receipt, "state": "completed"}))
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.dont_write_bytecode = True
    raise SystemExit(main())
