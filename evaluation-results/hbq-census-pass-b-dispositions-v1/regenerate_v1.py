"""Regenerate finite historical cohort metadata once; never sum overlapping votes."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
POLICY = "historical_cohort_count_regeneration_v1"
READER = REPO / "evaluation-results/hbq-matched-hanna-20261004/prepare.py"
READER_SHA = "2d82e4959c3296ccaa6e6521adb46f85588427d429a544b36a2891ebaea8c7b0"


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return (json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"),
                       allow_nan=False) + "\n").encode()


def checked(pin, roots):
    root = roots[pin["root"]].resolve()
    path = (root / pin["locator"]).resolve()
    require(path.is_relative_to(root), "Pin leaves source root")
    raw = path.read_bytes()
    require(sha(raw) == pin["sha256"] and len(raw) == pin["bytes"], "Source pin differs")
    return raw


def load(path, identity):
    spec = importlib.util.spec_from_file_location("regenerate_v1_" + identity, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def project(raw, fields):
    require(sha(READER.read_bytes()) == READER_SHA, "Lexical reader differs")
    return load(READER, "lexical").project_json(raw, fields)


def owned_cohorts(recipe):
    cohorts = recipe["cohorts"]
    require(len({c["id"] for c in cohorts}) == len(cohorts), "Duplicate cohort would repeat observations")
    require(all(c["interface"] in {"run", "disjoint", "five_root", "retained_f"} for c in cohorts),
            "Unsupported regeneration interface")
    return cohorts


def invoke(item, roots):
    checked(item["implementation"], roots)
    raw = checked(item["recipe"], roots)
    if item["interface"] == "retained_f":
        return retained_f(item, roots)
    module = load(roots["repository"] / item["implementation"]["locator"], item["id"])
    recipe = json.loads(raw)  # Pinned recipes contain only metadata projections and commitments.
    if item["interface"] == "run":
        return module.run(recipe, roots["documents"])
    if item["interface"] == "disjoint":
        report, slots, artifacts, _ = module.census(roots["documents"],
                                                  roots["repository"] / item["recipe"]["locator"])
        return report, {"positions": slots, "artifact_index": artifacts}
    report, slots, artifacts = module.census(roots["documents"], recipe, raw)
    return report, {"metadata_positions": slots, "artifact_index": artifacts}


def f_membership(base, joined):
    positions = base["positions"]
    slots = {p["ordinal"]: p for p in positions}
    require(len(slots) == len(positions), "Duplicate retained F ordinal")
    require(len({p["ordinal"] for p in joined}) == len(joined), "Duplicate F prefix ordinal")
    for row in joined:
        require(row["ordinal"] in slots and slots[row["ordinal"]]["proof"] is None,
                "Prefix would add a second observation")
        slot = slots[row["ordinal"]]
        require(all(row[k] == slot[k] for k in ("pass_id_sha256", "source_sha256", "question_ids",
                    "leaves", "historical_replay_input_commitments_sha256")), "Prefix membership differs")
    witnesses = []
    for row in positions + joined:
        leaves = row["leaves"]
        require([x["question_id"] for x in leaves] == row["question_ids"] and
                len(set(row["question_ids"])) == len(leaves) and
                all(x["verdict"] in {"YES", "NO", "NOT_APPLICABLE", "CANNOT_ASSESS"} for x in leaves),
                "Ordered retained F leaf metadata differs")
        proof = row["proof"]
        if proof and proof.get("native_identity"):
            witnesses.append(proof["native_identity"])
    identity = lambda value: tuple(value[k] for k in ("request_id_hash", "session_id_hash"))
    identities = [identity(v) for v in witnesses]
    ordinary = [identity(v) for v in base["ordinary_native_identities"]]
    excluded = [identity(v) for v in base["historical_excluded_native_identities"]]
    require(all(len(x) == 64 and set(x) <= set("0123456789abcdef") for p in identities + ordinary + excluded for x in p),
            "Native identity metadata malformed")
    require(all(len({p[i] for p in identities}) == len(identities) and
                len({p[i] for p in ordinary}) == len(ordinary) and
                len({p[i] for p in excluded}) == len(excluded) and
                not {p[i] for p in identities} & {p[i] for p in excluded} for i in (0, 1)),
            "Duplicate or excluded native identity")
    require(set(identities) == set(ordinary), "Native metadata membership differs")
    return {"logical_positions": len(positions), "ordered_metadata_leaves": sum(len(p["leaves"]) for p in positions),
            "native_identity_members": len(ordinary), "historical_excluded_identities": len(excluded),
            "previously_proof_null_positions_joined": len(joined),
            "new_votes_from_prefix_join": 0}


def retained_f(item, roots):
    assets = {name: checked(pin, roots) for name, pin in item["retained_metadata"].items()}
    leaf = {"question_id": True, "verdict": True}
    shared = {key: True for key in ("ordinal", "pass_id_sha256", "source_sha256", "question_ids",
                                  "historical_replay_input_commitments_sha256")}
    # These hash-pinned generated proof objects contain commitments/identity/disposition only,
    # as established by the pinned F/join_prefix writers; their raw provider bodies are separate.
    shared.update(leaves=[leaf], proof=True)
    base = project(assets["base_ledger"], {"positions": [{**shared, "prompt_sha256": True, "schema_sha256": True,
         "disposition": True}], "ordinary_native_identities": [{"request_id_hash": True, "session_id_hash": True}],
         "historical_excluded_native_identities": [{"request_id_hash": True, "session_id_hash": True}],
         "report_sha256": True, "artifacts": [{"source_locator": True, "source_sha256": True, "source_bytes": True}]})
    prefix = project(assets["prefix_ledger"], {"positions": [shared], "report_sha256": True,
         "artifacts": [{"source_locator": True, "source_sha256": True, "source_bytes": True}]})
    for which, value in (("base", base), ("prefix", prefix)):
        terminal = project(assets[which + "_terminal"], {"state": True, "report_sha256": True, "private_ledger_sha256": True})
        report_raw, ledger_raw = assets[which + "_report"], assets[which + "_ledger"]
        require(report_raw.endswith(b"}\n") and ledger_raw.endswith(b"}\n"), "Frozen F writer serialization differs")
        require(value["report_sha256"] == terminal["report_sha256"] == sha(report_raw[:-1]) and
                terminal["private_ledger_sha256"] == sha(ledger_raw[:-1]) and
                terminal["state"] == item["terminal_states"][which], "Retained F receipt binding differs")
    counts = f_membership(base, prefix["positions"])
    require(counts == item["expected_counts"], "Retained F count geometry differs")
    require(sorted(p["ordinal"] for p in prefix["positions"]) == [*range(1, 88), 89, 90, 91],
            "F prefix selection differs; 88/92 remain deduplicated")
    require(next(p for p in prefix["positions"] if p["ordinal"] == 70)["proof"]["native_identity"] is None,
            "Adoption70 manufactured a native identity")
    descriptors = {}
    for artifact in base["artifacts"] + prefix["artifacts"]:
        key = artifact["source_locator"]
        require(key not in descriptors or descriptors[key] == artifact, "Artifact representation commitments conflict")
        descriptors[key] = artifact
    for artifact in descriptors.values():
        checked({"root": "documents", "locator": artifact["source_locator"],
                 "sha256": artifact["source_sha256"], "bytes": artifact["source_bytes"]}, roots)
    counts["unique_source_artifacts_hash_rechecked"] = len(descriptors)
    report = {"policy": "dryad_grok_retained_census_metadata_count_descendant_v1",
              "basis": "regenerated_from_retained_census_metadata", "observed": counts,
              "source_pins": item["retained_metadata"], "provider_calls_made": 0, "new_provider_votes": 0,
              "native_semantic_attestation": "not_reexecuted", "physical_contact_cardinality": None}
    return report, {"positions": base["positions"], "prefix_existing_positions": prefix["positions"],
                    "artifact_index": list(descriptors.values())}


def package_dispositions(registry, cohorts):
    owners = {c["id"]: c for c in cohorts}
    packages = []
    for package in registry["declaration_packages"]:
        edges = [e for e in registry["coverage_edges"] if e["source_type"] == "declaration_package"
                 and e["source"] == package["id"]]
        mapped = sorted({e["census"] for e in edges if e.get("census") in owners})
        packages.append({"id": package["id"], "locator": package["locator"],
                         "artifact_commitments": package["artifact_commitments"],
                         "coverage_edges": edges, "regeneration_cohorts": mapped,
                         "status": "mapped_qualified_scope_only" if mapped else "unresolved_locator",
                         "additional_observed_votes_from_declaration": 0})
    require(len({p["id"] for p in packages}) == len(packages), "Duplicate declaration package")
    return packages


def read_reuse(root, expected_sha):
    raw = (root / "checkpoint.json").read_bytes()
    require(sha(raw) == expected_sha, "Reuse checkpoint differs")
    checkpoint = json.loads(raw)
    require(checkpoint["policy"] == POLICY and checkpoint["recipe_sha256"] ==
            sha((root / "regenerate-v1.recipe.json").read_bytes()),
            "Reuse recipe/policy differs")
    return checkpoint["completed"]


def reuse_cohort(item, root, receipt):
    require(receipt["implementation_sha256"] == item["implementation"]["sha256"] and
            receipt["recipe_sha256"] == item["recipe"]["sha256"] and
            receipt.get("cohort_descriptor_sha256") == sha(canonical(item)), "Reuse cohort pins differ")
    base = root / "cohorts" / item["id"]
    raw, private_raw = (base / "report.json").read_bytes(), (base / "private.json").read_bytes()
    require(sha(raw) == receipt["report_sha256"] and sha(private_raw) == receipt["private_sha256"],
            "Reuse saved cohort artifacts differ")
    return json.loads(raw), json.loads(private_raw)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    for name in ("documents-root", "control-root", "output-root"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--reuse-root", type=Path)
    parser.add_argument("--reuse-checkpoint-sha256")
    args = parser.parse_args(argv)
    roots = {"repository": REPO, "documents": args.documents_root.resolve(),
             "control": args.control_root.resolve()}
    output = args.output_root.resolve()
    raw = (HERE / "regenerate-v1.recipe.json").read_bytes()
    recipe = json.loads(raw)
    require(recipe["policy"] == POLICY, "Regeneration policy differs")
    cohorts = owned_cohorts(recipe)
    require(not output.exists() and not output.is_relative_to(REPO) and
            output.is_relative_to(roots["control"]), "Fresh task-local output outside repository required")
    source_roots = [(roots[recipe["registry"]["root"]] / recipe["registry"]["locator"]).parent]
    for item in cohorts:
        checked(item["implementation"], roots)
        source_recipe = json.loads(checked(item["recipe"], roots))
        source_roots.extend((roots[pin["root"]] / pin["locator"]).parent
                            for pin in item.get("retained_metadata", {}).values())
        source_roots.extend(roots["documents"] / x["locator"] for x in source_recipe.get("roots", []))
        source_roots.extend(roots["documents"] / x["root_relative_to_documents"]
                            for x in source_recipe.get("families", []))
    require(all(not output.is_relative_to(p.resolve()) and not p.resolve().is_relative_to(output)
                for p in source_roots), "Output overlaps retained evidence")
    registry = project(checked(recipe["registry"], roots), {
        "declaration_packages": True, "coverage_edges": True, "original_records": True,
        "original_references": True, "retained_sources": True, "inventory": True})
    require(registry["inventory"]["declaration_packages"] == 76 and
            registry["inventory"]["coverage_edges"] == 115, "Registry geometry differs")
    packages = package_dispositions(registry, cohorts)
    reuse = {}
    require(bool(args.reuse_root) == bool(args.reuse_checkpoint_sha256), "Reuse needs exact checkpoint pin")
    if args.reuse_root:
        require(output != args.reuse_root.resolve(), "Reuse never overwrites its source")
        reuse = read_reuse(args.reuse_root, args.reuse_checkpoint_sha256)
        require(set(reuse) <= {c["id"] for c in cohorts}, "Unknown reused cohort")
    completed, rows, private = {}, [], {}
    if not args.dry_run:
        output.mkdir(parents=True, exist_ok=False)
        (output / "regenerate-v1.recipe.json").write_bytes(raw)
        (output / "regenerate_v1.py").write_bytes(Path(__file__).read_bytes())
    try:
        for item in cohorts:
            checked(item["implementation"], roots)
            checked(item["recipe"], roots)
            report, ledger = (reuse_cohort(item, args.reuse_root, reuse[item["id"]])
                              if item["id"] in reuse else invoke(item, roots))
            require(report.get("provider_calls_made", report.get("provider_calls", 0)) == 0 and
                    report.get("new_provider_votes", report.get("new_votes", 0)) == 0,
                    "Cohort added contacts or votes")
            receipt = {"implementation_sha256": item["implementation"]["sha256"],
                       "recipe_sha256": item["recipe"]["sha256"],
                       "cohort_descriptor_sha256": sha(canonical(item)), "report_sha256": sha(canonical(report)),
                       "private_sha256": sha(canonical(ledger))}
            completed[item["id"]] = receipt
            rows.append({"id": item["id"], "disposition": item["disposition"],
                         "basis": "explicit_root_owned_saved_reuse" if item["id"] in reuse else
                                  report.get("basis", "regenerated_from_pinned_source_metadata"),
                         "commitments": receipt, "report": report})
            private[item["id"]] = ledger
            if not args.dry_run:
                base = output / "cohorts" / item["id"]
                base.mkdir(parents=True, exist_ok=False)
                for name, value in (("report.json", report), ("private.json", ledger)):
                    (base / name).write_bytes(canonical(value))
                checkpoint = {"policy": POLICY, "recipe_sha256": sha(raw), "completed": completed}
                # Versioned checkpoints retain a completed prefix through a later failure.
                (output / ("checkpoint-" + str(len(completed)) + ".json")).write_bytes(canonical(checkpoint))
    except Exception as error:
        failure = {"policy": POLICY, "state": "failed_partial_prefix_retained", "failed_cohort": item["id"],
                   "error_type": type(error).__name__, "completed": completed, "recipe_sha256": sha(raw),
                   "provider_calls": 0, "new_votes": 0}
        if not args.dry_run:
            (output / "checkpoint.json").write_bytes(canonical(failure))
        print(json.dumps(failure, sort_keys=True))
        return 3
    result = {"schema_version": 1, "policy": POLICY, "status": "partial_program_count_regeneration",
              "registry_pin": recipe["registry"], "cohorts": rows, "declaration_packages": packages,
              "original_records": registry["original_records"], "original_references": registry["original_references"],
              "retained_sources": registry["retained_sources"], "recipe_sha256": sha(raw),
              "implementation_sha256": sha(Path(__file__).read_bytes()), "lexical_reader_sha256": READER_SHA,
              "inventory": {"declared_packages": len(packages), "executed_or_reused_cohorts": len(completed),
                  "unmapped_packages": sum(not p["regeneration_cohorts"] for p in packages)},
              "independent_vote_total": None, "physical_contact_cardinality": None,
              "current_admission": "not_replayed", "provider_calls": 0, "new_votes": 0,
              "human_labels_opened": False, "scoring_performed": False,
              "limitations": recipe["limitations"]}
    receipt = {"policy": POLICY, "report_sha256": sha(canonical(result)), "recipe_sha256": sha(raw),
               "implementation_sha256": result["implementation_sha256"], "inventory": result["inventory"],
               "cohort_commitments": completed, "provider_calls": 0, "new_votes": 0,
               "output_written": not args.dry_run}
    receipt["cohort_counts"] = {}
    for row in rows:
        if "report" not in row:
            continue
        detail = row["report"]
        counts = {key: detail[key] for key in ("observed", "inherited_declarations") if key in detail}
        if "families" in detail:
            counts["families"] = [{key: family[key] for key in
                ("family", "observed", "observed_metadata", "inherited_declaration") if key in family}
                for family in detail["families"]]
        receipt["cohort_counts"][row["id"]] = counts
    if not args.dry_run:
        for name, value in (("report.json", result), ("terminal.json", receipt),
                            ("checkpoint.json", {"policy": POLICY, "recipe_sha256": sha(raw), "completed": completed})):
            (output / name).write_bytes(canonical(value))
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
