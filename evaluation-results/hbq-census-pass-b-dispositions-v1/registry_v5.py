"""Join two replay declarations to existing historical revision metadata."""
from __future__ import annotations

import argparse
from collections import Counter
import importlib.util
import json
import os
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
POLICY = "historical_disposition_coverage_registry_v5"
V4_SHA = "ef46d47a4f7e5ac1e665633d2a4242d772f48b142144a0d6b3a5dda72bcb5d8e"
PROJECTION_SHA = "2d650f301eeb1f38642a4d008274337a2b01268720075a58df27d6c63a369f37"
TARGETS = (
    "cwr-guided-revision-gain-v2-live-exec-v8-crlf-replay-result-v1",
    "cwr-guided-revision-gain-v2-live-exec-v9-historical-input-replay-result-v1",
)
RESULT_FIELDS = {key: True for key in (
    "format_version", "study_id", "kind", "pinned_v7_commit", "pinned_v7_executor_sha256",
    "provider_calls_made", "endpoint_results_are_not_pooled")}
DESCRIPTOR = {key: True for key in ("path", "sha256", "bytes")}
RESULT_FIELDS.update(source_artifacts=[DESCRIPTOR], underlying_endpoint_rows=[{
    "endpoint_event_id": True, "judge_route_id": True, "measure_id": True,
    "receipt": DESCRIPTOR, "adapter_stdout": DESCRIPTOR, "adapter_control": DESCRIPTOR}])


def predecessor():
    import hashlib
    path = HERE / "registry_v4.py"
    if hashlib.sha256(path.read_bytes()).hexdigest() != V4_SHA:
        raise ValueError("Predecessor implementation differs")
    spec = importlib.util.spec_from_file_location("registry_v5_pinned_v4", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.predecessor()


def historical_code(v2, pins, ledger):
    for pin in pins:
        def git(*arguments):
            completed = subprocess.run(
                ["git", "-C", str(REPO), *arguments], cwd=REPO, stdin=subprocess.DEVNULL,
                capture_output=True, timeout=30, check=False,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
            v2.require(completed.returncode == 0, "Historical Git source unavailable")
            return completed.stdout

        oid = git("rev-parse", pin["commit"] + ":" + pin["repository_path"]).decode("ascii").strip()
        v2.require(len(oid) == 40 and all(c in "0123456789abcdef" for c in oid) and
                   ("git_blob_oid" not in pin or oid == pin["git_blob_oid"]),
                   "Historical Git source identity differs")
        raw = git("cat-file", "blob", oid)
        v2.require(v2.sha(raw) == pin["sha256"], "Historical Git source bytes differ")
        ledger.append({**pin, "git_blob_oid": oid, "bytes": len(raw), "root": "repository_git"})


def revision_binding(v2, recipe, report, assets):
    source = recipe["revision"]
    census = [c for c in report["completed_censuses"] if c["id"] == "revision"]
    v2.require(len(census) == 1, "Existing revision census absent")
    regenerated = v2.project(assets["regeneration_report"], {
        "policy": True, "registry_pin": True,
        "cohorts": [{"id": True, "commitments": True}]})
    cohorts = [c for c in regenerated["cohorts"] if c["id"] == "revision"]
    v2.require(regenerated["policy"] == "historical_cohort_count_regeneration_v2" and
               regenerated["registry_pin"] == recipe["predecessor"]["report"] and
               len(cohorts) == 1 and cohorts[0]["commitments"] == source["cohort_commitments"],
               "Saved revision cohort binding differs")
    saved = v2.project(assets["report"], {key: True for key in (
        "policy", "observed", "implementation_sha256", "recipe_canonical_sha256",
        "private_ledger_sha256", "provider_calls_made", "new_provider_votes")})
    revision_recipe = json.loads(assets["recipe"])
    canonical_recipe = v2.canonical(revision_recipe).rstrip(b"\n")
    v2.require(saved["policy"] == revision_recipe["policy"] == "revision_six_root_historical_metadata_join_v1" and
               saved["implementation_sha256"] == source["pins"]["implementation"]["sha256"] and
               saved["recipe_canonical_sha256"] == v2.sha(canonical_recipe) and
               saved["private_ledger_sha256"] == source["pins"]["private_ledger"]["sha256"] and
               saved["provider_calls_made"] == saved["new_provider_votes"] == 0 and
               saved["observed"] == source["inherited_counts"], "Revision report source/count binding differs")
    for name, field in (("implementation", "implementation_sha256"), ("recipe", "recipe_sha256"),
                        ("report", "report_sha256"), ("private_ledger", "private_sha256")):
        v2.require(source["pins"][name]["sha256"] == cohorts[0]["commitments"][field],
                   "Revision cohort artifact differs")
    roots = [r for r in revision_recipe["roots"] if r["id"] == "revision-v7b"]
    v2.require(len(roots) == 1 and roots[0]["locator"] == source["source_locator"],
               "Frozen revision source differs")
    frozen = {item["locator"]: item for item in roots[0]["files"]}
    v2.require(len(frozen) == len(roots[0]["files"]), "Duplicate frozen source locator")
    private = v2.project(assets["private_ledger"], {
        "policy": True, "artifact_index": True,
        "wrappers": [{key: True for key in (
            "root_id", "locator", "logical_id_sha256", "role", "file_sha256", "condition",
            "unresolved_commitments", "native_identity_sha256", "response_commitment_sha256")}]})
    v2.require(private["policy"] == saved["policy"], "Revision private ledger policy differs")
    artifact_index = {item["source_locator"]: item for item in private["artifact_index"]}
    v2.require(len(artifact_index) == len(private["artifact_index"]), "Duplicate ledger source locator")
    wrappers = {item["locator"]: item for item in private["wrappers"] if item["root_id"] == "revision-v7b"}
    recipe_wrappers = {item["locator"]: item for item in revision_recipe["wrappers"]
                       if item["root_id"] == "revision-v7b"}
    v2.require(len(wrappers) == sum(item["root_id"] == "revision-v7b" for item in private["wrappers"]) and
               len(recipe_wrappers) == sum(item["root_id"] == "revision-v7b" for item in revision_recipe["wrappers"]),
               "Duplicate revision receipt wrapper")
    bindings = []
    projections = []
    for package in recipe["packages"]:
        matches = [p for p in report["declaration_packages"] if p["id"] == package["id"]]
        v2.require(len(matches) == 1 and all(pin in matches[0]["artifact_commitments"]
                   for pin in package["pins"].values()), "Replay declaration commitments differ")
        public = {name: v2.checked(pin, recipe["roots"], recipe["ledger"])
                  for name, pin in package["pins"].items()}
        contract = v2.project(public["contract"], {key: True for key in package["contract"]})
        v2.require(contract == package["contract"], "Replay contract differs")
        result = v2.project(public["result"], RESULT_FIELDS)
        v2.require({key: result[key] for key in package["result_identity"]} == package["result_identity"] and
                   result["pinned_v7_commit"] == contract["pinned_v7_commit"] and
                   result["pinned_v7_executor_sha256"] == contract["pinned_v7_executor_sha256"] and
                   len(recipe["historical_code"]) == 2 and
                   recipe["historical_code"][1]["commit"] == contract["pinned_v7_commit"] and
                   recipe["historical_code"][1]["sha256"] == contract["pinned_v7_executor_sha256"] and
                   result["provider_calls_made"] == 0 and result["endpoint_results_are_not_pooled"] is True and
                   contract["geometry"] == {"endpoint_receipts": 40, "primary_guided_control_rows": 16,
                                            "arm_baseline_rows": 32}, "Replay provenance identity/geometry differs")
        if "historical_v6" in contract:
            extra = v2.project(public["result"], {"historical_v6": True})
            v2.require(extra["historical_v6"] == contract["historical_v6"] == recipe["historical_code"][0],
                       "Historical V6 declaration differs")
        rows = result["underlying_endpoint_rows"]
        source_artifacts = result["source_artifacts"]
        v2.require([a["path"] for a in source_artifacts] == ["immutable-inputs.json", "prepared-index.json"] and
                   len(rows) == 40 and len({r["endpoint_event_id"] for r in rows}) == 40 and
                   Counter(r["judge_route_id"] for r in rows) == {"gpt-5.6-sol-high": 20, "grok-4.6-high": 20} and
                   Counter(r["measure_id"] for r in rows) == {"compact": 20, "holistic": 20},
                   "Replay endpoint membership differs")
        descriptors = source_artifacts + [r[name] for r in rows for name in
                                         ("receipt", "adapter_stdout", "adapter_control")]
        v2.require(len({d["path"] for d in descriptors}) == 122, "Duplicate replay artifact locator")
        for descriptor in descriptors:
            pin = frozen.get(descriptor["path"])
            indexed = artifact_index.get(source["source_locator"] + "/" + descriptor["path"])
            v2.require(pin is not None and indexed is not None and
                       {key: pin[key] for key in ("sha256", "bytes")} ==
                       {key: descriptor[key] for key in ("sha256", "bytes")} and
                       indexed["source_sha256"] == descriptor["sha256"] and
                       indexed["source_bytes"] == descriptor["bytes"], "Replay artifact source join differs")
        native_ids = set()
        for row in rows:
            event = row["endpoint_event_id"]
            expected_dir = "cells/" + event + "/"
            v2.require(all(row[key]["path"] == expected_dir + name for key, name in (
                ("receipt", "verified-receipt.json"), ("adapter_stdout", "adapter-stdout.raw"),
                ("adapter_control", "adapter-control.json"))), "Replay receipt layout differs")
            wrapper = wrappers.get(row["receipt"]["path"])
            frozen_receipt = recipe_wrappers.get(row["receipt"]["path"])
            logical_digest = v2.sha(v2.canonical(event).rstrip(b"\n"))
            v2.require(wrapper is not None and wrapper["role"] == "receipt" and
                       wrapper["file_sha256"] == row["receipt"]["sha256"] and
                       frozen_receipt is not None and frozen_receipt["logical_id"] == event and
                       wrapper["logical_id_sha256"] == logical_digest and
                       wrapper["condition"]["phase"] == "blind_endpoint_judgment" and
                       wrapper["unresolved_commitments"] == [] and
                       wrapper["native_identity_sha256"] and wrapper["response_commitment_sha256"],
                       "Replay receipt identity join differs")
            native_ids.add(wrapper["native_identity_sha256"])
        v2.require(len(native_ids) == 40, "Replay native metadata membership differs")
        projection = {key: result[key] for key in ("source_artifacts", "underlying_endpoint_rows")}
        v2.require(v2.sha(v2.canonical(projection)) == PROJECTION_SHA, "Replay provenance projection differs")
        projections.append(projection)
        bindings.append({"source_type": "declaration_package", "source": package["id"],
            "relationship": "joins_existing_positions", "census": "revision",
            "census_namespace": "completed_census", "basis": "saved_revision_v7b_commitment_join_only_not_reexecuted",
            "matched_source_artifacts": 122, "existing_native_metadata_joins": 40,
            "provenance_projection_sha256": PROJECTION_SHA, "fresh_observations": 0,
            "current_native_admission": "not_replayed", "physical_contact_cardinality": None, "new_provider_votes": 0})
    v2.require(projections[0] == projections[1], "Replay packages differ in provenance")
    return bindings


def run(recipe, roots):
    v2 = predecessor()
    v2.require(recipe["policy"] == POLICY and tuple(p["id"] for p in recipe["packages"]) == TARGETS,
               "Wrong registry policy/package membership")
    ledger = []
    previous = recipe["predecessor"]
    raw = {key: v2.checked(pin, roots, ledger) for key, pin in previous.items()}
    v2.require(previous["implementation"]["sha256"] == V4_SHA, "Wrong predecessor source")
    fields = {key: True for key in (
        "policy", "original_records", "original_references", "ancestor", "completed_censuses",
        "declaration_packages", "coverage_edges", "retained_sources", "relationship_semantics", "inventory",
        "input_commitment_sha256", "private_ledger_sha256", "lexical_reader_sha256", "provider_calls_made",
        "new_provider_votes", "native_admission", "scoring", "physical_contact_cardinality", "limitations",
        "recipe_file_sha256", "implementation_sha256", "historical_predecessor", "historical_predecessor_v3",
        "inherited_census_reference_binding")}
    report = v2.project(raw["report"], fields)
    terminal = v2.project(raw["receipt"], {"state": True, "report_sha256": True,
        "recipe_file_sha256": True, "implementation_sha256": True})
    v2.require(terminal == {"state": "completed", "report_sha256": v2.sha(raw["report"]),
        "recipe_file_sha256": v2.sha(raw["recipe"]), "implementation_sha256": V4_SHA} and
        report["policy"] == "historical_disposition_coverage_registry_v4" and
        report["recipe_file_sha256"] == v2.sha(raw["recipe"]) and report["implementation_sha256"] == V4_SHA,
        "Saved v4 report/receipt binding differs")
    inv = report["inventory"]
    v2.require([inv[k] for k in ("declaration_packages", "coverage_edges", "completed_censuses",
        "metadata_only_qualified_packages", "unresolved_declaration_packages")] == [76, 115, 8, 5, 60],
        "V4 inventory differs")
    assets = {key: v2.checked(pin, roots, ledger) for key, pin in recipe["revision"]["pins"].items()}
    historical_code(v2, recipe["historical_code"], ledger)
    binding_recipe = {**recipe, "roots": roots, "ledger": ledger}
    replacements = revision_binding(v2, binding_recipe, report, assets)
    old = [e for e in report["coverage_edges"] if e["source_type"] == "declaration_package" and e["source"] in TARGETS]
    v2.require(len(old) == 2 and {e["source"] for e in old} == set(TARGETS) and
               all(e["relationship"] == "unresolved_locator" and e.get("census") is None for e in old),
               "Expected two unresolved replay edges")
    by_source = {e["source"]: e for e in replacements}
    current = [by_source[e["source"]] if e in old else e for e in report["coverage_edges"]]
    identities = [(e["source_type"], e["source"], e["relationship"], e.get("census")) for e in current]
    v2.require(len(set(identities)) == len(current) == 115, "Duplicate registry edge")
    private = {"policy": POLICY, "artifact_ledger": ledger}
    report.update(schema_version=5, policy=POLICY, coverage_edges=current,
        historical_predecessor_v4={"pins": previous, "superseded_locator_edges": old,
            "input_commitment_sha256": report["input_commitment_sha256"],
            "private_ledger_sha256": report["private_ledger_sha256"]},
        inherited_revision_cohort_binding={"id": "revision", "pins": recipe["revision"]["pins"],
            "counts": recipe["revision"]["inherited_counts"], "package_bindings": replacements,
            "historical_code": recipe["historical_code"], "fresh_observations": 0})
    report["inventory"] = {**inv, "unresolved_declaration_packages": 58,
        "relationships": dict(sorted(Counter(e["relationship"] for e in current).items()))}
    report["limitations"].append("V8 and V9 join the same 40 existing revision endpoint judgments; 122 provenance commitments per package add no observations. Saved source metadata is reused without source-body, native-admission, scoring or physical-contact replay.")
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
    raw = (HERE / "registry-v5.recipe.json").read_bytes()
    recipe = json.loads(raw)
    pins = [*recipe["predecessor"].values(), *recipe["revision"]["pins"].values(),
            *(pin for package in recipe["packages"] for pin in package["pins"].values())]
    output = args.output_root.resolve()
    v2.require(not output.exists() and not output.is_relative_to(REPO) and
        all(not output.is_relative_to((roots[p["root"]] / p["locator"]).parent) for p in pins),
        "Fresh output outside repository/retained inputs required")
    report, private = run(recipe, roots)
    report.update(recipe_file_sha256=v2.sha(raw), implementation_sha256=v2.sha(Path(__file__).read_bytes()))
    report_raw = v2.canonical(report)
    receipt = {"policy": POLICY, "report_sha256": v2.sha(report_raw), "recipe_file_sha256": v2.sha(raw),
        "implementation_sha256": report["implementation_sha256"], "private_ledger_sha256": report["private_ledger_sha256"],
        "inventory": report["inventory"], "inherited_counts": recipe["revision"]["inherited_counts"],
        "provider_calls_made": 0, "new_provider_votes": 0, "dry_run": args.dry_run}
    if not args.dry_run:
        output.mkdir(parents=True, exist_ok=False)
        for name, content in {"registry.json": report_raw, "private-ledger.json": v2.canonical(private),
            "registry-v5.recipe.json": raw, "registry_v5.py": Path(__file__).read_bytes(),
            "terminal.json": v2.canonical({**receipt, "state": "completed"})}.items():
            with (output / name).open("xb") as stream:
                stream.write(content)
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
