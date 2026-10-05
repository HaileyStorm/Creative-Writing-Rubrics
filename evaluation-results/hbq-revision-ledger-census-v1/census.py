"""Provider-free, selective six-root historical revision receipt census."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPOSITORY = HERE.parents[1]
HELPERS = {
    "common": (HERE.parent / "hbq-evidence-census-pass-c-v1/census.py",
               "42415af5418ae32303bfa7933712b2ad398c0ed66df32a7553a9e3d55f5de49b"),
    "selective": (HERE.parent / "hbq-matched-hanna-20261004/prepare.py",
                  "2d82e4959c3296ccaa6e6521adb46f85588427d429a544b36a2891ebaea8c7b0"),
}


def load_helper(name):
    path, pin = HELPERS[name]
    if hashlib.sha256(path.read_bytes()).hexdigest() != pin:
        raise ValueError("Pinned provider-free helper differs: " + name)
    spec = importlib.util.spec_from_file_location("revision_census_" + name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_common, _selective = load_helper("common"), load_helper("selective")
Inputs, sha, canonical, digest, require, inside = (
    _common.Inputs, _common.sha, _common.canonical, _common.digest, _common.require, _common.inside)
project_json = _selective.project_json
POLICY = "revision_six_root_historical_metadata_join_v1"
SCALARS = frozenset("kind event_id original_event_id replacement_event_id phase state status process_launches provider_calls_made no_resend provider_model requested_model reasoning requested_reasoning_effort tools_enabled frozen_manifest_sha256 prepared_record_sha256 launch_intent_sha256 payload_sha256 response_sha256 transmitted_payload_sha256 returned_response_sha256 thread_id_sha256 events_hash raw_output_hash evidence_class native_endpoint_contact_cardinality command_identity_hash auth_receipt_hash session_id provider_request_id session_id_hash request_id_hash envelope_hash source_native_receipt_sha256 normalized_native_receipt_sha256 adapter_output_schema_sha256 underlying_pilot_response_schema_sha256".split())
COMMITMENT = {key: True for key in ("path", "root", "bytes", "sha256")}
CONTAINERS = frozenset("native native_receipt actual_native_receipt runtime local_lifecycle prepared receipt source_receipt payload target_manifest outbound_payload imported_verified_receipt source_reconciled_receipt verified_receipt raw_stdout".split())
LIMITS = [
    "Historical metadata only: no response, prose, ratings, findings or rationale decoding; no semantic or native-envelope replay.",
    "Native identities and response hashes join retained declarations; they do not establish modern admission, backend model attestation or physical contact cardinality.",
    "Original failures remain reserved without admitted responses; imports, carry-forward and replacement wrappers add no independent votes.",
    "Development endpoint scope is 40 cells (20 per endpoint); the distinct 48-cell heldout source is excluded.",
    "External target-context and predecessor native sources are not opened; full census and scoring closure remain unmet.",
]


def safe_spec(spec):
    require(isinstance(spec, dict), "Metadata specification must be an object")
    for key, child in spec.items():
        if child is True:
            require(key in SCALARS or key in COMMITMENT, "Outcome/prose field cannot be selected")
        else:
            require(key in CONTAINERS and isinstance(child, dict), "Unsupported metadata container")
            safe_spec(child)


def identity(metadata):
    for value in (metadata, metadata.get("local_lifecycle", {})):
        if value.get("thread_id_sha256"):
            return "sol:" + value["thread_id_sha256"]
    for value in (metadata.get("native", {}), metadata.get("native_receipt", {}),
                  metadata.get("actual_native_receipt", {}), metadata.get("runtime", {})):
        request = value.get("provider_request_id") or value.get("request_id_hash")
        session = value.get("session_id") or value.get("session_id_hash")
        if request and session:
            return "grok:" + digest([request, session])
    return None


def response_commitment(metadata):
    if metadata.get("response_sha256"):
        return metadata["response_sha256"]
    for value in (metadata, metadata.get("actual_native_receipt", {}), metadata.get("native_receipt", {})):
        if value.get("returned_response_sha256"):
            return value["returned_response_sha256"]
    return None


def run(recipe, source_root):
    require(recipe["policy"] == POLICY, "Recipe policy differs")
    require(recipe["helper_pins"] == {key: pin for key, (_, pin) in HELPERS.items()}, "Recipe helper pins differ")
    reader = Inputs(Path(source_root))
    metadata, file_pins, wrappers, bindings = {}, {}, [], []
    for root in recipe["roots"]:
        require(reader.path(root["locator"]).is_dir(), "Missing reviewed revision root: " + root["id"])
        for entry in root["files"]:
            locator = root["locator"] + "/" + entry["locator"]
            raw = reader.raw(locator, entry["sha256"], entry["bytes"])
            file_pins[(root["id"], entry["locator"])] = sha(raw)
            if entry.get("spec") is not None:
                spec = recipe["specifications"][entry["spec"]]
                safe_spec(spec)
                metadata[(root["id"], entry["locator"])] = project_json(raw, spec)
    observations, native_responses, native_logical_ids, native_conditions, seen_wrappers = {}, {}, {}, {}, set()
    for row in recipe["wrappers"]:
        key = (row["root_id"], row["locator"])
        require(key not in seen_wrappers, "Duplicate retained wrapper")
        seen_wrappers.add(key)
        value = metadata[key]
        for binding in row.get("bindings", []):
            claimed = value
            for part in binding["field"].split("."):
                claimed = claimed[part]
            actual = file_pins[(binding.get("root_id", row["root_id"]), binding["locator"])]
            require(claimed == actual, "Historical metadata commitment differs: " + binding["field"])
            bindings.append({"wrapper_sha256": file_pins[key], "field": binding["field"], "source_sha256": actual})
        native, response = identity(value), response_commitment(value)
        prepared_metadata = value.get("prepared", {})
        prepared_binding = next((binding for binding in row.get("bindings", [])
                                 if binding["field"].endswith("prepared_record_sha256")
                                 or binding["field"] == "prepared.sha256"), None)
        if prepared_binding is not None:
            prepared_metadata = metadata.get((prepared_binding.get("root_id", row["root_id"]),
                                              prepared_binding["locator"]), prepared_metadata)
        condition = {name: value.get(name, value.get("actual_native_receipt", {}).get(name,
                                                                                    prepared_metadata.get(name)))
                     for name in ("phase", "provider_model", "reasoning", "frozen_manifest_sha256")}
        if row["role"] == "source_link":
            source_sha = value["source_receipt"]["sha256"]
            parent = observations.get(source_sha)
            require(parent is not None, "Imported receipt source is outside earlier finite receipt join")
            native, response = parent["native"], parent["response"]
            condition = parent["condition"]
        if row["role"] in {"receipt", "replacement_authority", "source_link"}:
            require(native is not None and response is not None, "Receipt lacks selected native/response metadata")
            require(native not in native_responses or native_responses[native] == response,
                    "One retained native identity has conflicting response commitments")
            require(native not in native_logical_ids or native_logical_ids[native] == row["logical_id"],
                    "One retained native identity has conflicting logical observations")
            native_responses[native] = response
            native_logical_ids[native] = row["logical_id"]
            require(native not in native_conditions or native_conditions[native] == condition,
                    "One retained native identity has conflicting condition metadata")
            native_conditions[native] = condition
            observations[file_pins[key]] = {"native": native, "response": response, "condition": condition}
        else:
            native, response = None, None
        wrappers.append({"root_id": row["root_id"], "locator": row["locator"],
                         "logical_id_sha256": digest(row["logical_id"]), "role": row["role"],
                         "file_sha256": file_pins[key], "metadata": redact_native(value),
                         "condition": condition,
                         "unresolved_commitments": row.get("unresolved_commitments", []),
                         "native_identity_sha256": digest(native) if native else None,
                         "response_commitment_sha256": response})
    by_root = []
    for root in recipe["roots"]:
        rows = [row for row in wrappers if row["root_id"] == root["id"]]
        by_root.append({"id": root["id"], "declared": root.get("declared", {}),
                        "observed": {"committed_files": len(root["files"]),
                                     "wrapper_roles": dict(sorted(Counter(row["role"] for row in rows).items())),
                                     "receipt_native_identities": len({row["native_identity_sha256"] for row in rows
                                                                      if row["native_identity_sha256"]})},
                        "status": root["status"]})
    joined = [row for row in wrappers if row["native_identity_sha256"]]
    private = {"policy": POLICY, "wrappers": wrappers, "verified_bindings": bindings,
               "artifact_index": list(reader.artifacts.values()), "external_references": recipe["external_references"]}
    report = {"schema_version": 1, "policy": POLICY, "status": "bounded_historical_metadata_join",
              "roots": by_root, "observed": {"committed_files": len(reader.artifacts),
                      "committed_bytes": sum(row["source_bytes"] for row in reader.artifacts.values()),
                      "verified_metadata_hash_bindings": len(bindings),
                      "unresolved_local_commitments": sum(len(row["unresolved_commitments"]) for row in wrappers),
                      "receipt_wrappers": len(joined), "distinct_native_response_metadata_joins": len(native_responses),
                      "distinct_metadata_joins_by_phase": dict(sorted(Counter(
                          condition["phase"] or "unavailable" for condition in native_conditions.values()).items())),
                      "distinct_metadata_joins_by_declared_provider_model": dict(sorted(Counter(
                          condition["provider_model"] or "unavailable" for condition in native_conditions.values()).items())),
                      "repeated_native_response_wrappers": len(joined) - len(native_responses),
                      "failed_reserved_observations": sum(row["role"] == "failed_reserved" for row in wrappers),
                      "preparation_only_cells": sum(row["role"] == "preparation_only" for row in wrappers)},
              "inherited_native_admission": "not_replayed", "provider_calls_made": 0, "new_provider_votes": 0,
              "recipe_canonical_sha256": digest(recipe), "implementation_sha256": sha(Path(__file__).read_bytes()),
              "input_commitment_sha256": digest(list(reader.artifacts.values())),
              "private_ledger_sha256": sha(canonical(private) + b"\n"),
              "external_references": recipe["external_references"], "limitations": LIMITS}
    return report, private


def redact_native(value):
    if isinstance(value, dict):
        return {key + "_sha256" if key in {"provider_request_id", "session_id"} else key:
                digest(child) if key in {"provider_request_id", "session_id"} else redact_native(child)
                for key, child in value.items()}
    return value


def destination(path, source_root, recipe):
    output = Path(path).resolve()
    require(not output.exists() and not inside(output, REPOSITORY), "Output must be fresh and outside repository")
    require(all(not inside(output, Path(source_root) / root["locator"]) for root in recipe["roots"]),
            "Output overlaps retained revision root")
    return output


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    raw = (HERE / "recipe.json").read_bytes()
    recipe = json.loads(raw)
    output = destination(args.output_root, args.source_root, recipe)
    report, private = run(recipe, args.source_root)
    report["recipe_file_sha256"] = sha(raw)
    report_raw = canonical(report) + b"\n"
    receipt = {"policy": POLICY, "report_sha256": sha(report_raw),
               "recipe_file_sha256": sha(raw), "recipe_canonical_sha256": digest(recipe),
               "implementation_sha256": report["implementation_sha256"],
               "input_commitment_sha256": report["input_commitment_sha256"],
               "private_ledger_sha256": report["private_ledger_sha256"],
               "observed": report["observed"], "provider_calls_made": 0, "new_provider_votes": 0,
               "dry_run": args.dry_run}
    if not args.dry_run:
        output.mkdir(parents=True, exist_ok=False)
        snapshots = {"recipe.json": raw, "census.py": Path(__file__).read_bytes(),
                     "census.json": report_raw, "private-ledger.json": canonical(private) + b"\n",
                     "invocation.json": canonical({"source_root_local_only": str(args.source_root.resolve()),
                                                   "output_root_local_only": str(output)}) + b"\n",
                     "terminal.json": canonical({**receipt, "state": "completed"}) + b"\n"}
        snapshots.update({name + ".py": path.read_bytes() for name, (path, _) in HELPERS.items()})
        for name, content in snapshots.items():
            with (output / name).open("xb") as stream:
                stream.write(content)
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
