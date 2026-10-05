"""Hash-bound coverage registry; saved historical proofs are not executed again."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
POLICY = "historical_disposition_coverage_registry_v2"
SELECTIVE = REPO / "evaluation-results/hbq-matched-hanna-20261004/prepare.py"
SELECTIVE_SHA = "2d82e4959c3296ccaa6e6521adb46f85588427d429a544b36a2891ebaea8c7b0"
RELATIONSHIPS = {"replaces_declaration", "joins_existing_positions", "excluded_ancestor",
                 "nonvoting_output", "untouched", "unresolved_locator"}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                       allow_nan=False) + "\n").encode("utf-8")


def project(raw, fields):
    require(sha(SELECTIVE.read_bytes()) == SELECTIVE_SHA, "Lexical reader pin differs")
    spec = importlib.util.spec_from_file_location("registry_v2_lexical", SELECTIVE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.project_json(raw, fields)


def checked(pin, roots, ledger):
    root = roots[pin["root"]].resolve()
    path = (root / pin["locator"]).resolve()
    require(path.is_relative_to(root), "Input locator escapes its root")
    raw = path.read_bytes()
    require(sha(raw) == pin["sha256"] and len(raw) == pin["bytes"], "Input commitment differs")
    ledger.append(dict(pin))
    return raw


def coverage_edges(edges, records, censuses, packages, retained_sources=(), excluded_attempts=()):
    seen = set()
    for edge in edges:
        identity = (edge["source_type"], edge["source"], edge["relationship"], edge.get("census"))
        require(identity not in seen, "Duplicate coverage edge")
        seen.add(identity)
        require(edge["relationship"] in RELATIONSHIPS, "Unsupported coverage relationship")
        pools = {"original_record": records, "declaration_package": packages,
                 "retained_source": retained_sources}
        require(edge["source_type"] in pools, "Unsupported coverage source type")
        pool = pools[edge["source_type"]]
        require(edge["source"] in pool, "Coverage source is outside frozen inventory")
        require(not (edge["source_type"] == "original_record" and
                     edge["source"] in excluded_attempts and
                     edge["relationship"] == "joins_existing_positions"),
                "Excluded attempt cannot claim joined positions")
        require(edge.get("census") in censuses or
                (edge["relationship"] == "unresolved_locator" and edge.get("census") is None),
                "Coverage census is outside frozen inventory")
    return edges


def declaration_binding(raw, binding):
    fields = {key: True for key in binding["expected"]}
    require(project(raw, fields) == binding["expected"], "Public declaration source binding differs")


def run(recipe, roots):
    require(recipe["policy"] == POLICY, "Wrong registry policy")
    ledger = []
    ancestor = recipe["ancestor"]
    checked(ancestor["implementation"], roots, ledger)
    original_raw = checked(ancestor["recipe"], roots, ledger)
    # This recipe contains locators, hash declarations and historical declarations only.
    original = json.loads(original_raw)
    require(len(original["records"]) == 22 and len(original["prior_censuses"]) == 7,
            "Original registry membership differs")
    original_report_raw = checked(ancestor["report"], roots, ledger)
    identity = project(original_report_raw, {"recipe_file_sha256": True, "implementation_sha256": True,
                                            "records": [{"id": True}], "prior_censuses": [{"id": True}]})
    require(identity["recipe_file_sha256"] == sha(original_raw) and
            identity["implementation_sha256"] == ancestor["implementation"]["sha256"],
            "Ancestor report does not bind original implementation/recipe")
    require([r["id"] for r in original["records"]] == [r["id"] for r in identity["records"]] and
            [r["id"] for r in original["prior_censuses"]] == [r["id"] for r in identity["prior_censuses"]],
            "Ancestor report membership differs")
    for item in original["prior_censuses"]:
        checked({key: item[key] for key in ("root", "locator", "sha256", "bytes")}, roots, ledger)
    censuses = []
    for item in recipe["completed_censuses"]:
        recipe_raw = checked(item["recipe"], roots, ledger)
        report_raw = checked(item["report"], roots, ledger)
        receipt_raw = checked(item["receipt"], roots, ledger)
        if item["receipt_kind"] == "completed_terminal":
            binding = project(receipt_raw, {"state": True, "recipe_file_sha256": True, "report_sha256": True})
            require(binding == {"state": "completed", "recipe_file_sha256": sha(recipe_raw),
                                "report_sha256": sha(report_raw)}, "Saved receipt binding differs")
        else:
            require(item["receipt_kind"] == "artifact_inventory_without_terminal", "Unknown receipt kind")
            binding = project(report_raw, {"recipe_sha256": True, "artifact_ledger_sha256": True})
            require(binding == {"recipe_sha256": sha(recipe_raw), "artifact_ledger_sha256": sha(receipt_raw)},
                    "Saved inventory binding differs")
        censuses.append({"id": item["id"], "recipe": item["recipe"], "report": item["report"],
                         "receipt": item["receipt"], "receipt_kind": item["receipt_kind"],
                         "basis": "saved_proof_hash_binding_only_not_reexecuted"})
    packages = []
    for item in recipe["declaration_packages"]:
        for artifact in item["artifacts"]:
            raw = checked(artifact, roots, ledger)
            binding = item.get("source_binding")
            if binding and artifact["locator"] == binding["locator"]:
                declaration_binding(raw, binding)
        packages.append({"id": item["id"], "locator": item["locator"],
                         "artifact_commitments": item["artifacts"],
                         "source_binding": item.get("source_binding"),
                         "basis": "immediate_public_declaration_files_hash_only"})
    retained_sources = recipe["retained_sources"]
    require(len({r["id"] for r in retained_sources}) == len(retained_sources), "Duplicate retained source")
    edges = coverage_edges(recipe["coverage_edges"], {r["id"] for r in original["records"]},
                           {r["id"] for r in censuses}, {r["id"] for r in packages},
                           {r["id"] for r in retained_sources},
                           {r["id"] for r in original["records"] if r["disposition"] == "excluded_attempt"})
    by_package = {p["id"]: [] for p in packages}
    for edge in edges:
        if edge["source_type"] == "declaration_package":
            by_package[edge["source"]].append(edge)
    require(all(by_package.values()), "Declaration package has no explicit disposition")
    private = {"policy": POLICY, "artifact_ledger": ledger}
    report = {"schema_version": 2, "policy": POLICY,
              "original_records": original["records"], "original_references": original["prior_censuses"],
              "ancestor": ancestor, "completed_censuses": censuses, "declaration_packages": packages,
              "coverage_edges": edges, "retained_sources": retained_sources,
              "relationship_semantics": recipe["relationship_semantics"],
              "inventory": {"original_records": 22, "original_references": 7,
                            "completed_censuses": len(censuses), "declaration_packages": len(packages),
                            "unresolved_declaration_packages": sum(all(e["relationship"] == "unresolved_locator"
                                                                      for e in value) for value in by_package.values()),
                            "coverage_edges": len(edges), "relationships": dict(sorted(Counter(
                                e["relationship"] for e in edges).items()))},
              "input_commitment_sha256": sha(canonical(ledger)), "private_ledger_sha256": sha(canonical(private)),
              "lexical_reader_sha256": SELECTIVE_SHA, "provider_calls_made": 0, "new_provider_votes": 0,
              "native_admission": "not_replayed", "scoring": "not_replayed",
              "physical_contact_cardinality": None,
              "limitations": ["Coverage edges do not add observations or sum overlapping ancestor declarations.",
                              "Immediate pinned result packages only; unmatched declarations have no inferred private root.",
                              "Native admission, current scoring and physical evidence gaps remain in their source censuses.",
                              "Public results, prompts, prose, evidence, notes and labels are not decoded."]}
    return report, private


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--control-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    roots = {"source": args.source_root.resolve(), "control": args.control_root.resolve(), "repository": REPO}
    output = args.output_root.resolve()
    require(not output.exists() and not output.is_relative_to(REPO), "Output must be fresh and outside repository")
    raw = (HERE / "registry-v2.recipe.json").read_bytes()
    recipe = json.loads(raw)
    pins = [*recipe["ancestor"].values(), *(p for c in recipe["completed_censuses"] for p in
             (c["recipe"], c["report"], c["receipt"]))]
    require(all(not output.is_relative_to((roots[p["root"]] / p["locator"]).parent) for p in pins),
            "Output overlaps retained evidence")
    report, private = run(recipe, roots)
    report.update(recipe_file_sha256=sha(raw), implementation_sha256=sha(Path(__file__).read_bytes()))
    report_raw = canonical(report)
    receipt = {"policy": POLICY, "report_sha256": sha(report_raw), "recipe_file_sha256": sha(raw),
               "implementation_sha256": report["implementation_sha256"],
               "private_ledger_sha256": report["private_ledger_sha256"], "inventory": report["inventory"],
               "provider_calls_made": 0, "new_provider_votes": 0, "dry_run": args.dry_run}
    if not args.dry_run:
        output.mkdir(parents=True, exist_ok=False)
        for name, content in {"registry.json": report_raw, "private-ledger.json": canonical(private),
                              "registry-v2.recipe.json": raw, "registry_v2.py": Path(__file__).read_bytes(),
                              "selective.py": SELECTIVE.read_bytes(),
                              "terminal.json": canonical({**receipt, "state": "completed"})}.items():
            with (output / name).open("xb") as stream:
                stream.write(content)
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
