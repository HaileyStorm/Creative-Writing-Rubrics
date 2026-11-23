"""Regenerate pinned census exports without executing their historical readers."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
POLICY = "historical_cohort_count_regeneration_v3"
IDS = {"architecture", "disjoint", "figurative", "fullbook", "native_f",
       "poetryr3", "qpc24", "revision", "scope_five_root_metadata"}
# Versioned metadata sources; a different snapshot needs a new reviewed version.
PINS = {
    "reuse_checkpoint": "d43d8516d7bb8cee71f0e90a9c33b0f140dbe8084cbbd00f92110823d6661ad3",
    "reuse_terminal": "167ab2e2c66a18e6c1dffd6ed6646702f77b19301f0d2bb58549ca20be9eacbd",
    "reuse_report": "2fb127a2ff42903e0153e4816228699a3289e3dd8ac6744f308854754358f6bb",
    "reuse_recipe": "ba9cb39f5913b98258a9b71056f4647e532fb2936a8535417f8c76fba45582f5",
    "cohort_recipe": "6c95958202ade8b067473a08d6601e9d319b94733cb40380461e8e15620ab0e1",
    "registry_report": "d70d04b4504b65ff74d271778441e2f7f1a7afc6afa2759c258c12d147bb7dfd",
    "registry_implementation": "a060e596c531c5dc9924ac5a53ec168d2bbbc8bb0494d57173a8d06c47b230a9",
    "registry_recipe": "d646f7d0c97ad4c0f82d89f0894e796d58b662140f51d3d741f2deab256f08bd",
    "ttcw_snapshot": "106814f9cac14def735c3764dffde20a441284d3bdee0ec84fa242a2fa363228",
    "ttcw_delta": "4b0f78d7e782202586ed39b09e943badceb94449cb1af9e6bbf384f1768bc1af",
}
DENOMINATOR = {"planned_total": 3108, "planned_per_endpoint": 1554,
               "planned_hbq_banks_per_endpoint": 54, "planned_pairs": 36,
               "planned_initial_orders": 72, "planned_repeat_comparisons": 24}


def require(value, message):
    if not value:
        raise ValueError(message)


def canonical(value):
    return (json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"),
                       allow_nan=False) + "\n").encode("utf-8")


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def commitment(path):
    digest, size = hashlib.sha256(), 0
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
            size += len(block)
    return {"sha256": digest.hexdigest(), "bytes": size}


def checked(pin, roots, expected=None):
    require(set(pin) == {"root", "locator", "sha256", "bytes"}, "Invalid pin fields")
    root = roots[pin["root"]]
    locator = Path(pin["locator"])
    require(not locator.is_absolute(), "Pin locator must be relative")
    path = (root / locator).resolve()
    require(path.is_relative_to(root), "Pin leaves source root")
    require(expected is None or pin["sha256"] == expected, "Versioned source pin differs")
    require(commitment(path) == {k: pin[k] for k in ("sha256", "bytes")},
            "Source bytes differ: " + str(path))
    return path


def metadata(path, expected_sha):
    # Only generated reports, recipes and checkpoints reach this decoder.
    require(path.stat().st_size <= 2_000_000, "Metadata input exceeds finite bound")
    raw = path.read_bytes()
    require(len(raw) <= 2_000_000 and sha(raw) == expected_sha, "Consumed metadata pin differs")
    return json.loads(raw)


def select(value, keys):
    return {key: value[key] for key in keys}


def packages(registry):
    result = []
    for package in registry["declaration_packages"]:
        edges = [e for e in registry["coverage_edges"]
                 if e["source_type"] == "declaration_package" and e["source"] == package["id"]]
        require(edges, "Declaration has no disposition")
        unresolved = any(e["relationship"] == "unresolved_locator" for e in edges)
        require(not unresolved or all(e["relationship"] == "unresolved_locator" for e in edges),
                "Conflicting unresolved declaration")
        status = ("unresolved_locator" if unresolved else
                  "metadata_membership_only" if any(e["relationship"] == "metadata_membership_only" for e in edges) else
                  "inherited_reference_joined" if any(e.get("census_namespace") == "original_reference" for e in edges) else
                  "mapped_qualified_scope_only" if any(e.get("census") in IDS for e in edges) else
                  "qualified_scope_not_regenerated")
        result.append({**package, "coverage_edges": edges, "status": status,
                       "additional_observed_votes_from_declaration": 0})
    require(len({p["id"] for p in result}) == 76 and len(result) == 76, "Package identity differs")
    require(sum(p["status"] == "unresolved_locator" for p in result) == 57 and
            sum(p["status"] == "metadata_membership_only" for p in result) == 6,
            "Registry declaration dispositions differ")
    return result


def ttcw(snapshot, delta, snapshot_pin):
    require(select(snapshot, DENOMINATOR) == select(delta, DENOMINATOR) == DENOMINATOR,
            "TTCW planned denominator differs")
    require(snapshot["actual_admitted"] == {"grok": 302, "sol": 658} and
            snapshot["Grok_accepted_not_admitted_ordinals"] == [114] and
            snapshot["Grok_terminal_states"] == {"accepted": 303, "semantic_rejected": 12, "ambiguous": 7},
            "TTCW snapshot disposition differs")
    expected = {"selected_ordinals": [114], "admitted_records": 1,
                "prior_admitted_identity_exclusions": 302, "total_historical_grok_admitted": 303,
                "exact037_matched_records_reused": 1, "full_source_context_match": True,
                "selected_native_request_id_missing": 0, "new_native_session_commitments": 1,
                "new_native_request_commitments": 1, "new_native_replay_attempts": 1,
                "new_semantic_replays": 1, "complete_order_pairs": 0,
                "reverse_read_or_admitted": False, "reserved_prefix_native_replayed": False}
    require(select(delta, expected) == expected, "TTCW qualification delta differs")
    require(any(pin["sha256"] == snapshot_pin["sha256"] and pin["bytes"] == snapshot_pin["bytes"]
                for pin in delta["source_pins"].values()), "Delta lacks exact snapshot parent")
    limits = {"provider_calls": 0, "new_votes": 0, "capacity_released": 0,
              "tools_off_eligible_records": 0, "labels_read": False, "human_targets_opened": False,
              "source_attempts_resent": False, "candidate_promoted": False, "full_goal_complete": False}
    require(select(snapshot, limits) == select(delta, limits) == limits, "TTCW evidence limits differ")
    require(delta["scoring_calls"] == delta["compiler_calls"] == 0 and
            delta["provider_or_billing_quiescence_proven"] is False, "Delta acceptance bounds differ")
    return {"planned": DENOMINATOR, "snapshot_051": {
                **select(snapshot, ("scope", "actual_admitted", "Grok_terminal_states",
                                    "Grok_accepted_not_admitted_ordinals", "Sol_saved_dispositions")),
                "sha256": snapshot_pin["sha256"]},
            "qualification_delta_052": {**expected, "scope": delta["scope"],
                                        "sha256": PINS["ttcw_delta"]},
            "historical_admitted_after_delta": {"grok": 303, "sol": 658},
            "limits": limits, "aggregation": "same observations; Sol reuse adds no vote",
            "scalar_and_order_summaries": "not updated from snapshot by this export"}


def prepare(recipe, roots):
    require(recipe["policy"] == POLICY and set(recipe["sources"]) == set(PINS) | {"registry_terminal"},
            "Recipe policy or finite source set differs")
    paths = {role: checked(pin, roots, PINS.get(role)) for role, pin in recipe["sources"].items()}
    reuse = paths["reuse_checkpoint"].parent
    require(reuse.is_relative_to(roots["control"]) and
            all(paths[role].parent == reuse for role in
                ("reuse_checkpoint", "reuse_terminal", "reuse_report", "reuse_recipe")),
            "Reuse inputs must share one saved run")
    checkpoint, terminal, old_report = [metadata(paths[key], PINS[key]) for key in
                                      ("reuse_checkpoint", "reuse_terminal", "reuse_report")]
    require(checkpoint["policy"] == terminal["policy"] == old_report["policy"] ==
            "historical_cohort_count_regeneration_v2" and
            checkpoint["recipe_sha256"] == terminal["recipe_sha256"] == old_report["recipe_sha256"] == PINS["reuse_recipe"],
            "Saved v2 policy/recipe differs")
    require(terminal["output_written"] is True and terminal["provider_calls"] == terminal["new_votes"] == 0 and
            terminal["report_sha256"] == PINS["reuse_report"] and
            checkpoint["completed"] == terminal["cohort_commitments"] and
            set(checkpoint["completed"]) == IDS, "Complete saved nine-cohort run required")
    descriptors = metadata(paths["cohort_recipe"], PINS["cohort_recipe"])["cohorts"]
    require(len(descriptors) == 9 and {c["id"] for c in descriptors} == IDS,
            "Cohort descriptor identity differs")
    saved_rows = {c["id"]: c for c in old_report["cohorts"]}
    require(len(old_report["cohorts"]) == len(saved_rows) == 9 and set(saved_rows) == IDS,
            "Saved report cohort membership differs")
    rows, copies = [], []
    for item in sorted(descriptors, key=lambda c: c["id"]):
        receipt = checkpoint["completed"][item["id"]]
        require(receipt["cohort_descriptor_sha256"] == sha(canonical(item)) and
                receipt["implementation_sha256"] == item["implementation"]["sha256"] and
                receipt["recipe_sha256"] == item["recipe"]["sha256"], "Cohort descriptor differs")
        checked(item["implementation"], roots)
        checked(item["recipe"], roots)
        folder = reuse / "cohorts" / item["id"]
        report_path, private_path = folder / "report.json", folder / "private.json"
        require(folder.resolve().is_relative_to(reuse), "Cohort escapes reuse root")
        for path, key in ((report_path, "report_sha256"), (private_path, "private_sha256")):
            pin = commitment(path)
            require(path.resolve().is_relative_to(reuse) and pin["sha256"] == receipt[key],
                    "Saved cohort artifact differs")
            copies.append((path, Path("cohorts") / item["id"] / path.name, pin))
        report = metadata(report_path, receipt["report_sha256"])
        require(report == saved_rows[item["id"]]["report"] and
                receipt == saved_rows[item["id"]]["commitments"], "Saved cohort report binding differs")
        rows.append({"id": item["id"], "disposition": item["disposition"],
                     "execution": "opaque_saved_export_reuse", "commitments": receipt,
                     "counts": terminal["cohort_counts"][item["id"]], "report": report})
    registry = metadata(paths["registry_report"], PINS["registry_report"])
    rt = metadata(paths["registry_terminal"], recipe["sources"]["registry_terminal"]["sha256"])
    require(registry["policy"] == rt["policy"] == "historical_disposition_coverage_registry_v6" and
            rt["state"] == "completed" and rt["report_sha256"] == PINS["registry_report"] and
            registry["implementation_sha256"] == rt["implementation_sha256"] == PINS["registry_implementation"] and
            registry["recipe_file_sha256"] == rt["recipe_file_sha256"] == PINS["registry_recipe"] and
            registry["inventory"] == rt["inventory"], "Registry receipt binding differs")
    require(registry["inventory"]["declaration_packages"] == len(registry["declaration_packages"]) == 76 and
            registry["inventory"]["coverage_edges"] == len(registry["coverage_edges"]) == 115 and
            dict(Counter(e["relationship"] for e in registry["coverage_edges"])) == registry["inventory"]["relationships"] and
            registry["provider_calls_made"] == registry["new_provider_votes"] == 0 and
            rt["provider_calls_made"] == rt["new_provider_votes"] == 0, "Registry inventory/evidence differs")
    report = {"schema_version": 3, "policy": POLICY, "status": "partial_program_count_regeneration",
              "cohorts": rows, "registry_inventory": registry["inventory"],
              "declaration_packages": packages(registry),
              "registry_bindings": select(registry, ("inherited_census_reference_binding",
                   "inherited_revision_cohort_binding", "qualified_wpb_metadata_binding")),
              "original_records": registry["original_records"], "original_references": registry["original_references"],
              "retained_sources": registry["retained_sources"],
              "ttcw": ttcw(metadata(paths["ttcw_snapshot"], PINS["ttcw_snapshot"]),
                            metadata(paths["ttcw_delta"], PINS["ttcw_delta"]), recipe["sources"]["ttcw_snapshot"]),
              "source_pins": recipe["sources"], "cohort_counts": terminal["cohort_counts"],
              "independent_vote_total": None, "physical_contact_cardinality": None,
              "provider_calls": 0, "new_votes": 0, "historical_readers_executed": 0,
              "private_ledgers_decoded": 0, "current_admission": "not_replayed",
              "scoring_performed": False, "human_labels_opened": False, "full_goal_complete": False,
              "limitations": ["Saved count/disposition exports only; source reports retain their scope qualifications.",
                  "Overlapping census namespaces are not summed into votes or physical contacts.",
                  "Registry metadata membership does not prove native admission or leaf coverage.",
                  "TTCW 052 qualifies one 051 observation; it does not update saved scalar/order summaries.",
                  "Historical evidence does not establish tools-disabled collection, capacity or human alignment.",
                  "Unresolved declarations and full research requirements remain open."]}
    return report, copies, paths


def write_new(path, raw):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(raw)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    for name in ("control-root", "recipe", "output-root"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--recipe-sha256", required=True)
    parser.add_argument("--dry-run", action="store_true", help="Verify all pins; create no files")
    args = parser.parse_args(argv)
    roots = {"repository": REPO, "control": args.control_root.resolve()}
    recipe_path, output = args.recipe.resolve(), args.output_root.resolve()
    require(recipe_path.is_relative_to(roots["control"]) or recipe_path.is_relative_to(REPO),
            "Recipe outside declared roots")
    raw = recipe_path.read_bytes()
    source_raw = Path(__file__).read_bytes()
    require(sha(raw) == args.recipe_sha256, "Recipe pin differs")
    require(not output.exists() and output.is_relative_to(roots["control"]) and
            not output.is_relative_to(REPO) and not recipe_path.is_relative_to(output),
            "Fresh output outside repository and recipe required")
    report, copies, paths = prepare(json.loads(raw), roots)
    inputs = [p.resolve() for p in paths.values()] + [p.resolve() for p, _, _ in copies]
    require(all(not p.is_relative_to(output) and not output.is_relative_to(p.parent) for p in inputs),
            "Output overlaps retained inputs")
    report.update(implementation_sha256=sha(source_raw), recipe_sha256=sha(raw))
    report_raw = canonical(report)
    result = {"policy": POLICY, "state": "verified" if args.dry_run else "completed",
              "output_written": not args.dry_run, "report_sha256": sha(report_raw),
              "implementation_sha256": report["implementation_sha256"], "recipe_sha256": sha(raw),
              "cohorts_reused": len(IDS), "registry_inventory": report["registry_inventory"],
              "historical_ttcw_admitted": report["ttcw"]["historical_admitted_after_delta"],
              "provider_calls": 0, "new_votes": 0, "historical_readers_executed": 0,
              "private_ledgers_decoded": 0}
    if not args.dry_run:
        output.mkdir(parents=True, exist_ok=False)
        write_new(output / "regenerate-v3.recipe.json", raw)
        write_new(output / "regenerate_v3.py", source_raw)
        for source, relative, pin in copies:
            destination = output / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            with source.open("rb") as reader, destination.open("xb") as writer:
                for block in iter(lambda: reader.read(1024 * 1024), b""):
                    writer.write(block)
            require(commitment(destination) == pin and commitment(source) == pin, "Opaque copy differs")
        write_new(output / "report.json", report_raw)
        write_new(output / "terminal.json", canonical(result))
    print(json.dumps(result, sort_keys=True))
    return result


if __name__ == "__main__":
    main()
