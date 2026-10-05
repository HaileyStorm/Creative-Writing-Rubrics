"""Finite, provider-free historical root dispositions; private sources are hashed only."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPOSITORY = HERE.parent.parent
COMMON = HERE.parent / "hbq-evidence-census-pass-c-v1/census.py"
COMMON_SHA256 = "42415af5418ae32303bfa7933712b2ad398c0ed66df32a7553a9e3d55f5de49b"
if hashlib.sha256(COMMON.read_bytes()).hexdigest() != COMMON_SHA256:
    raise ValueError("Pinned provider-free census helper differs")
_spec = importlib.util.spec_from_file_location("pass_b_dispositions_common", COMMON)
_common = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_common)
Inputs, require, sha, canonical, digest, inside = (
    _common.Inputs, _common.require, _common.sha, _common.canonical, _common.digest, _common.inside)

POLICY = "pass_b_finite_metadata_root_dispositions_v1"
DISPOSITIONS = {"verified_historical_metadata", "superseded_ancestor", "excluded_attempt",
                "declaration_only", "unresolved_join"}
LIMITS = [
    "Finite allowlist only; other declared empirical roots still need dispositions. This is not full census B closure.",
    "Private source files are hashed without JSON, prose, target or outcome decoding; file existence is not native admission.",
    "Published declared counts, observed artifacts and inherited native joins are different evidence types and are not summed.",
    "Superseded ancestors, excluded attempts, repairs and planned repeats add no independent studies or votes.",
    "Physical contact cardinality, modern strict admission, runtime equivalence and full-score replay remain unverified.",
]


def selected_count(document, path):
    value = document
    for part in path.split("."):
        value = value[part]
    require(type(value) is int and value >= 0, "Selected public metadata count is not a nonnegative integer")
    return value


def census(recipe, source_root, control_root, repository=REPOSITORY):
    require(recipe["policy"] == POLICY and recipe["common_sha256"] == COMMON_SHA256,
            "Recipe policy or common-helper commitment differs")
    roots = {"source": Path(source_root).resolve(), "control": Path(control_root).resolve(),
             "repository": Path(repository).resolve()}
    inputs = {key: Inputs(path) for key, path in roots.items()}
    prior, records, ledger = [], [], []
    identifiers = set()
    for item in recipe["prior_censuses"]:
        reader = inputs[item["root"]]
        raw = reader.raw(item["locator"], item["sha256"], item["bytes"])
        document = json.loads(raw)  # These pinned public count reports contain no human targets.
        prior.append({"id": item["id"], "source_sha256": sha(raw),
                      "inherited_counts": {name: selected_count(document, path)
                                           for name, path in item["counts"].items()},
                      "basis": "inherited_published_census_not_reexecuted"})
    for item in recipe["records"]:
        require(item["id"] not in identifiers and item["disposition"] in DISPOSITIONS,
                "Duplicate record or unsupported disposition")
        identifiers.add(item["id"])
        reader = inputs[item["root"]]
        root = reader.path(item["locator"])
        observed = {"committed_artifacts": 0, "artifact_bytes": 0,
                    "terminal_files_hashed_only": 0, "prepared_cell_files_hashed_only": 0,
                    "receipt_files_hashed_only": 0}
        disposition = item["disposition"]
        missing = []
        committed = []
        if not root.is_dir():
            disposition = "inaccessible_root"
            availability = "absent_or_not_directory"
            observed = None  # Absence never implies zero empirical rows.
        else:
            availability = "accessible"
            for entry in item["artifacts"]:
                locator = item["locator"] + "/" + entry["locator"]
                if not reader.path(locator).is_file():
                    missing.append(digest(entry["locator"]))
                    continue
                raw = reader.raw(locator, entry["sha256"], entry["bytes"])
                observed["committed_artifacts"] += 1
                observed["artifact_bytes"] += len(raw)
                observed["terminal_files_hashed_only"] += entry["locator"].startswith("terminals/")
                observed["prepared_cell_files_hashed_only"] += entry["locator"].endswith("/prepared-cell.json")
                observed["receipt_files_hashed_only"] += entry["locator"].endswith("/verified-receipt.json")
                committed.append({"locator_sha256": digest(entry["locator"]),
                                  "source_sha256": sha(raw), "source_bytes": len(raw)})
            if missing:
                disposition = "unresolved_missing_metadata"
            elif not committed and disposition != "declaration_only":
                disposition = "unresolved_join"
        declared = dict(item.get("declared", {}))
        require(all(type(v) is int and v >= 0 for v in declared.values()), "Invalid declared count")
        records.append({"id": item["id"], "family": item["family"],
                        "availability": availability, "disposition": disposition,
                        "declared": declared, "declared_basis": item.get("declared_basis"),
                        "observed": observed, "new_native_joins": None,
                        "native_join_status": "not_replayed",
                        "missing_commitments": len(missing), "parent": item.get("parent"),
                        "basis": item["basis"], "artifact_commitment_sha256": digest(committed)})
        ledger.append({"record_id_sha256": digest(item["id"]),
                       "root_locator_sha256": digest(item["locator"]),
                       "artifacts": committed, "missing_locator_sha256s": missing})
    require(all(row.get("parent") is None or row["parent"] in identifiers for row in records),
            "Lineage parent is outside the finite allowlist")
    artifact_index = [{"root": key, **row} for key, reader in inputs.items()
                      for row in reader.artifacts.values()]
    private = {"policy": POLICY, "records": ledger, "artifact_index": artifact_index}
    report = {"schema_version": 1, "policy": POLICY, "status": "bounded_historical_dispositions",
              "prior_censuses": prior, "records": records,
              "counts": {"allowlisted_records": len(records),
                         "families": dict(sorted(Counter(row["family"] for row in records).items())),
                         "dispositions": dict(sorted(Counter(row["disposition"] for row in records).items())),
                         "verified_artifacts": len(artifact_index),
                         "verified_artifact_bytes": sum(row["source_bytes"] for row in artifact_index)},
              "recipe_canonical_sha256": digest(recipe), "common_sha256": COMMON_SHA256,
              "implementation_sha256": sha(Path(__file__).read_bytes()),
              "input_commitment_sha256": digest(artifact_index),
              "private_ledger_sha256": sha(canonical(private) + b"\n"),
              "provider_calls_made": 0, "new_provider_votes": 0, "limitations": LIMITS}
    report["coverage_boundary"] = recipe.get("coverage_boundary", LIMITS[0])
    return report, private


def output_path(path, recipe, roots):
    output = Path(path).resolve()
    require(not output.exists() and not inside(output, REPOSITORY), "Output must be fresh and outside repository")
    for item in recipe["records"]:
        require(not inside(output, roots[item["root"]] / item["locator"]), "Output lies inside retained source")
    for item in recipe["prior_censuses"]:
        require(not inside(output, (roots[item["root"]] / item["locator"]).parent),
                "Output lies inside retained census input")
    return output


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--control-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    raw = (HERE / "recipe.json").read_bytes()
    recipe = json.loads(raw)
    roots = {"source": args.source_root.resolve(), "control": args.control_root.resolve(),
             "repository": REPOSITORY}
    output = output_path(args.output_root, recipe, roots)
    report, private = census(recipe, args.source_root, args.control_root)
    report["recipe_file_sha256"] = sha(raw)
    report_raw = canonical(report) + b"\n"
    receipt = {"policy": POLICY, "report_sha256": sha(report_raw),
               "recipe_file_sha256": sha(raw), "recipe_canonical_sha256": digest(recipe),
               "implementation_sha256": report["implementation_sha256"],
               "input_commitment_sha256": report["input_commitment_sha256"],
               "private_ledger_sha256": report["private_ledger_sha256"],
               "counts": report["counts"], "dry_run": args.dry_run,
               "provider_calls_made": 0, "new_provider_votes": 0}
    if not args.dry_run:
        output.mkdir(parents=True, exist_ok=False)
        snapshots = {"recipe.json": raw, "census.py": Path(__file__).read_bytes(),
                     "common.py": COMMON.read_bytes(), "census.json": report_raw,
                     "private-ledger.json": canonical(private) + b"\n",
                     "invocation.json": canonical({"source_root_local_only": str(args.source_root.resolve()),
                                                   "control_root_local_only": str(args.control_root.resolve()),
                                                   "output_root_local_only": str(output)}) + b"\n",
                     "terminal.json": canonical({**receipt, "state": "completed"}) + b"\n"}
        for name, content in snapshots.items():
            with (output / name).open("xb") as stream:
                stream.write(content)
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
