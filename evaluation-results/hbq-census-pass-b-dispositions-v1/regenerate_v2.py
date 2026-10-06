"""Regenerate current dispositions with unchanged historical cohort ownership."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
POLICY = "historical_cohort_count_regeneration_v2"
V1_SHA = "c09d010829a1270be12b9c8f823f82096352251414f3a631fa9546182ba97b20"


def predecessor():
    path = HERE / "regenerate_v1.py"
    if hashlib.sha256(path.read_bytes()).hexdigest() != V1_SHA:
        raise ValueError("Historical regeneration implementation differs")
    spec = importlib.util.spec_from_file_location("regeneration_v2_pinned_v1", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def package_dispositions(v1, registry, cohorts):
    packages = v1.package_dispositions(registry, cohorts)
    bindings = registry["inherited_census_reference_binding"]
    for package in packages:
        edges = package["coverage_edges"]
        inherited = [e for e in edges if e.get("census_namespace") == "original_reference"]
        unresolved = any(e["relationship"] == "unresolved_locator" for e in edges)
        v1.require(not (unresolved and (package["regeneration_cohorts"] or inherited)),
                   "Conflicting current locator dispositions")
        package["inherited_reference_joins"] = []
        for edge in inherited:
            references = [r for r in registry["original_references"] if r["id"] == edge["census"]]
            v1.require(len(inherited) == 1 and len(references) == 1 and
                       edge["relationship"] == "joins_existing_positions" and
                       edge["census"] == bindings["id"] and
                       edge["inherited_counts"] == bindings["counts"] and
                       edge["basis"] == bindings["basis"] and
                       all(references[0][k] == value for k, value in bindings["pins"]["summary"].items()) and
                       edge["fresh_observations"] == edge["new_provider_votes"] == 0,
                       "Qualified inherited reference binding differs")
            package["inherited_reference_joins"].append({
                "id": edge["census"], "namespace": "original_reference", **bindings})
        package["status"] = ("inherited_reference_joined" if inherited else
            "mapped_qualified_scope_only" if package["regeneration_cohorts"] else
            "unresolved_locator" if unresolved else "qualified_scope_not_regenerated")
    v1.require(sum(p["status"] == "unresolved_locator" for p in packages) ==
               registry["inventory"]["unresolved_declaration_packages"], "Unresolved registry inventory differs")
    return packages


def read_reuse(v1, root, expected_sha, recipe):
    raw = (root / "checkpoint.json").read_bytes()
    v1.require(v1.sha(raw) == expected_sha, "Reuse checkpoint differs")
    checkpoint = json.loads(raw)  # Generated metadata-only checkpoint.
    historical = checkpoint["policy"] == v1.POLICY
    filename = "regenerate-v1.recipe.json" if historical else "regenerate-v2.recipe.json"
    saved = (root / filename).read_bytes()
    v1.require(checkpoint["policy"] in {v1.POLICY, POLICY} and
               checkpoint["recipe_sha256"] == v1.sha(saved), "Reuse recipe/policy differs")
    if historical:
        v1.require(recipe["historical_reuse_policy"] == "pinned_regeneration_v1_checkpoint_compatibility" and
                   v1.sha(saved) == recipe["predecessor"]["recipe"]["sha256"],
                   "Historical reuse recipe differs")
    else:
        v1.require(saved == (HERE / "regenerate-v2.recipe.json").read_bytes(), "V2 reuse recipe differs")
    return checkpoint["completed"], {"policy": checkpoint["policy"], "checkpoint_sha256": expected_sha,
                                    "recipe_sha256": v1.sha(saved)}


def registry_readback(v1, recipe, roots):
    raw = v1.checked(recipe["registry"], roots)
    v1.checked(recipe["registry_implementation"], roots)
    v1.checked(recipe["registry_recipe"], roots)
    terminal = v1.project(v1.checked(recipe["registry_receipt"], roots), {
        k: True for k in ("state", "policy", "report_sha256", "implementation_sha256", "recipe_file_sha256")})
    v1.require(terminal == {"state": "completed", "policy": "historical_disposition_coverage_registry_v4",
        "report_sha256": recipe["registry"]["sha256"],
        "implementation_sha256": recipe["registry_implementation"]["sha256"],
        "recipe_file_sha256": recipe["registry_recipe"]["sha256"]}, "Registry receipt differs")
    registry = v1.project(raw, {k: True for k in ("declaration_packages", "coverage_edges", "original_records",
        "original_references", "retained_sources", "inventory", "inherited_census_reference_binding")})
    v1.require([registry["inventory"][k] for k in ("declaration_packages", "coverage_edges",
        "unresolved_declaration_packages")] == [76, 115, 60], "Registry geometry differs")
    return registry


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    for name in ("documents-root", "control-root", "output-root"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--reuse-root", type=Path)
    parser.add_argument("--reuse-checkpoint-sha256")
    args = parser.parse_args(argv)
    v1 = predecessor()
    roots = {"repository": REPO, "documents": args.documents_root.resolve(), "control": args.control_root.resolve()}
    raw = (HERE / "regenerate-v2.recipe.json").read_bytes()
    recipe = json.loads(raw)
    v1.require(recipe["policy"] == POLICY and recipe["predecessor"]["implementation"]["sha256"] == V1_SHA,
               "Regeneration policy/source differs")
    v1.checked(recipe["predecessor"]["implementation"], roots)
    old = json.loads(v1.checked(recipe["predecessor"]["recipe"], roots))
    cohorts = v1.owned_cohorts(old)
    v1.require(len(cohorts) == 9, "Historical cohort geometry differs")
    output = args.output_root.resolve()
    v1.require(not output.exists() and output.is_relative_to(roots["control"]) and
               not output.is_relative_to(REPO), "Fresh task-local output outside repository required")
    inputs = [(roots[recipe["registry"]["root"]] / recipe["registry"]["locator"]).parent]
    for item in cohorts:
        v1.checked(item["implementation"], roots)
        source = json.loads(v1.checked(item["recipe"], roots))
        inputs.extend((roots[p["root"]] / p["locator"]).parent for p in item.get("retained_metadata", {}).values())
        inputs.extend(roots["documents"] / p["locator"] for p in source.get("roots", []))
        inputs.extend(roots["documents"] / p["root_relative_to_documents"] for p in source.get("families", []))
    v1.require(bool(args.reuse_root) == bool(args.reuse_checkpoint_sha256), "Reuse needs exact checkpoint pin")
    reused, reuse_provenance = {}, None
    if args.reuse_root:
        inputs.append(args.reuse_root.resolve())
        reused, reuse_provenance = read_reuse(v1, args.reuse_root, args.reuse_checkpoint_sha256, recipe)
        v1.require(set(reused) <= {c["id"] for c in cohorts}, "Unknown reused cohort")
    v1.require(all(not output.is_relative_to(p.resolve()) and not p.resolve().is_relative_to(output) for p in inputs),
               "Output overlaps retained evidence")
    registry = registry_readback(v1, recipe, roots)
    packages = package_dispositions(v1, registry, cohorts)
    completed, rows, private = {}, [], {}
    if not args.dry_run:
        output.mkdir(parents=True, exist_ok=False)
        (output / "regenerate-v2.recipe.json").write_bytes(raw)
        (output / "regenerate_v2.py").write_bytes(Path(__file__).read_bytes())
    try:
        for item in cohorts:
            report, ledger = (v1.reuse_cohort(item, args.reuse_root, reused[item["id"]]) if item["id"] in reused
                              else v1.invoke(item, roots))
            v1.require(report.get("provider_calls_made", report.get("provider_calls", 0)) == 0 and
                       report.get("new_provider_votes", report.get("new_votes", 0)) == 0, "Cohort added contacts or votes")
            receipt = {"implementation_sha256": item["implementation"]["sha256"], "recipe_sha256": item["recipe"]["sha256"],
                "cohort_descriptor_sha256": v1.sha(v1.canonical(item)), "report_sha256": v1.sha(v1.canonical(report)),
                "private_sha256": v1.sha(v1.canonical(ledger))}
            completed[item["id"]] = receipt
            rows.append({"id": item["id"], "disposition": item["disposition"],
                "basis": report.get("basis", "regenerated_from_pinned_source_metadata"),
                "execution": "explicit_root_owned_saved_reuse" if item["id"] in reused else "regenerated",
                "commitments": receipt, "report": report})
            private[item["id"]] = ledger
            if not args.dry_run:
                base = output / "cohorts" / item["id"]
                base.mkdir(parents=True, exist_ok=False)
                for name, value in (("report.json", report), ("private.json", ledger)):
                    (base / name).write_bytes(v1.canonical(value))
                (output / ("checkpoint-" + str(len(completed)) + ".json")).write_bytes(v1.canonical({
                    "policy": POLICY, "recipe_sha256": v1.sha(raw), "completed": completed}))
    except Exception as error:
        failure = {"policy": POLICY, "state": "failed_partial_prefix_retained", "failed_cohort": item["id"],
            "error_type": type(error).__name__, "completed": completed, "recipe_sha256": v1.sha(raw),
            "provider_calls": 0, "new_votes": 0}
        if not args.dry_run:
            (output / "checkpoint.json").write_bytes(v1.canonical(failure))
        print(json.dumps(failure, sort_keys=True))
        return 3
    inventory = {"declared_packages": len(packages), "executed_or_reused_cohorts": len(completed),
        "packages_without_regeneration_cohort": sum(not p["regeneration_cohorts"] for p in packages),
        "unresolved_locator_packages": sum(p["status"] == "unresolved_locator" for p in packages),
        "inherited_reference_joined_packages": sum(p["status"] == "inherited_reference_joined" for p in packages)}
    result = {"schema_version": 2, "policy": POLICY, "status": "partial_program_count_regeneration",
        "registry_pin": recipe["registry"], "registry_receipt_pin": recipe["registry_receipt"],
        "historical_predecessor": recipe["predecessor"], "reuse_provenance": reuse_provenance,
        "cohorts": rows, "declaration_packages": packages, "inventory": inventory,
        **{k: registry[k] for k in ("original_records", "original_references", "retained_sources")},
        "recipe_sha256": v1.sha(raw), "implementation_sha256": v1.sha(Path(__file__).read_bytes()),
        "lexical_reader_sha256": v1.READER_SHA, "independent_vote_total": None, "physical_contact_cardinality": None,
        "current_admission": "not_replayed", "provider_calls": 0, "new_votes": 0,
        "human_labels_opened": False, "scoring_performed": False, "limitations": old["limitations"] + recipe["limitations"]}
    counts = {}
    for row in rows:
        detail = row["report"]
        counts[row["id"]] = {k: detail[k] for k in ("observed", "inherited_declarations") if k in detail}
        if "families" in detail:
            counts[row["id"]]["families"] = [{k: family[k] for k in
                ("family", "observed", "observed_metadata", "inherited_declaration") if k in family}
                for family in detail["families"]]
    receipt = {"policy": POLICY, "report_sha256": v1.sha(v1.canonical(result)), "recipe_sha256": v1.sha(raw),
        "implementation_sha256": result["implementation_sha256"], "inventory": inventory, "cohort_counts": counts,
        "cohort_commitments": completed, "provider_calls": 0, "new_votes": 0, "output_written": not args.dry_run}
    if not args.dry_run:
        for name, value in (("report.json", result), ("terminal.json", receipt),
            ("checkpoint.json", {"policy": POLICY, "recipe_sha256": v1.sha(raw), "completed": completed})):
            (output / name).write_bytes(v1.canonical(value))
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
