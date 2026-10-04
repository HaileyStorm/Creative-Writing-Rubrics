"""Prepare the untouched Grok suffix offline; reserve every settled prefix slot."""
from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
import json
from pathlib import Path
import re
import uuid

from prepare import canonical, checked, digest, within, REPO

THROUGH = 6
PREFIX_FILES = ("condition.json", "terminal.json", "native-result.json", "native-identity.json",
                "attempt-started.json", "schema.json", "response.json", "acceptance.json", "native-envelope.json")


def fresh_private_output(output: Path, *inputs: Path) -> Path:
    output = output.resolve()
    for root in (REPO, *inputs):
        root = root.resolve()
        if output.is_relative_to(root) or root.is_relative_to(output):
            raise ValueError("Private descendant overlaps repository or retained inputs")
    if output.exists():
        raise ValueError("Private descendant already exists; use a fresh path")
    return output


def prefix_receipt(results: Path, row: dict, artifacts: dict[str, bytes], job: dict) -> dict:
    name = f"{row['endpoint_ordinal']:04d}-{row['logical_sample_id'][:12]}"
    sample = results / name
    retained = {name: (sample / name).read_bytes() for name in PREFIX_FILES if (sample / name).is_file()}
    required = set(PREFIX_FILES[:6])
    if not required <= retained.keys():
        raise ValueError("Prefix attempt is unsettled or missing retained evidence")
    condition, terminal, native, identity, started = (
        json.loads(retained[name]) for name in PREFIX_FILES[:5]
    )
    if condition != row or retained["schema.json"] != artifacts[row["schema_path"]]:
        raise ValueError("Prefix condition or schema differs from its original request")
    session_id = identity.get("session_id")
    if (not isinstance(session_id, str) or str(uuid.UUID(session_id)) != session_id
            or identity.get("logical_sample_id") != row["logical_sample_id"]
            or started.get("session_id") != session_id or started.get("state") != "before_contact"
            or started.get("no_resend") is not True or terminal.get("no_resend") is not True):
        raise ValueError("Prefix native identity or no-resend receipt differs")
    state, native_state = terminal.get("state"), native.get("state")
    expected = {"accepted": "completed", "semantic_rejected": "completed", "ambiguous": "ambiguous",
                "definitely_not_contacted": "definitely_not_contacted", "unavailable": "unavailable"}
    if state not in expected or native_state != expected[state] or terminal.get("accepted") is not (state == "accepted"):
        raise ValueError("Prefix attempt has an unsettled or conflicting terminal state")
    if native_state == "completed":
        if not {"response.json", "acceptance.json", "native-envelope.json"} <= retained.keys():
            raise ValueError("Completed prefix attempt is missing admission evidence")
        for key, filename in (("response_sha256", "response.json"), ("acceptance_sha256", "acceptance.json"),
                              ("native_result_sha256", "native-result.json")):
            if terminal.get(key) != digest(retained[filename]):
                raise ValueError("Prefix terminal artifact hash differs")
        result = native["result"]
        response, acceptance, envelope = (json.loads(retained[name]) for name in
                                         ("response.json", "acceptance.json", "native-envelope.json"))
        runtime = result["runtime"]
        schema = json.loads(artifacts[row["schema_path"]])
        prompt = artifacts[row["prompt_path"]].decode("utf-8")
        if (response != result["output"] or response != envelope.get("structuredOutput")
                or acceptance.get("accepted") is not (state == "accepted")
                or envelope.get("sessionId") != session_id
                or runtime.get("session_id_hash") != digest(session_id.encode())
                or runtime.get("requested_model") != job["model"]
                or runtime.get("reported_model") != job["route"]["reported_model"]
                or result.get("request_hash") != digest(canonical({"prompt": prompt})[:-1])
                or result.get("output_hash") != digest(canonical(response)[:-1])
                or runtime["execution_contract"].get("output_schema_hash") != digest(canonical(schema)[:-1])
                or result["native_envelope_artifact"].get("sha256") != digest(retained["native-envelope.json"])
                or result["native_envelope_artifact"].get("byte_length") != len(retained["native-envelope.json"])):
            raise ValueError("Prefix native response or execution binding differs")
    return {"endpoint_ordinal": row["endpoint_ordinal"], "logical_sample_id": row["logical_sample_id"],
            "request_sha256": row["request_sha256"], "condition_sha256": digest(retained["condition.json"]),
            "terminal_sha256": digest(retained["terminal.json"]), "terminal_state": state,
            "native_state": native_state, "no_resend": True,
            "artifacts": {name: {"sha256": digest(raw), "bytes": len(raw)} for name, raw in sorted(retained.items())}}


def build(manifest_path: Path, results: Path, *, timeout_seconds: int = 900) -> tuple[dict, dict[str, bytes]]:
    if not 1 <= timeout_seconds <= 3600:
        raise ValueError("Requested runtime timeout is out of bounds")
    root, results = manifest_path.resolve().parent, results.resolve()
    raw = manifest_path.read_bytes()
    original = json.loads(raw)
    body = {key: value for key, value in original.items() if key != "manifest_content_sha256"}
    if digest(canonical(body)) != original["manifest_content_sha256"]:
        raise ValueError("Original manifest content hash differs")
    job_raw = (results / "job.json").read_bytes()
    job = json.loads(job_raw)
    if job.get("endpoint") != "grok" or job.get("manifest_sha256") != digest(raw):
        raise ValueError("Original raw manifest differs from the retained Grok job")
    artifacts = {name: checked(within(root, name), pin["sha256"], pin["bytes"])
                 for name, pin in original["artifacts"].items()}
    endpoint_rows = [row for row in original["requests"] if row["endpoint"] == "grok"]
    if ([row["endpoint_ordinal"] for row in endpoint_rows] != list(range(1, len(endpoint_rows) + 1))
            or len({row["logical_sample_id"] for row in endpoint_rows}) != len(endpoint_rows)
            or len(endpoint_rows) <= THROUGH):
        raise ValueError("Original endpoint request order or identity differs")
    for row in original["requests"]:
        descriptor = {key: value for key, value in row.items() if key != "request_sha256"}
        if digest(canonical(descriptor)) != row["request_sha256"]:
            raise ValueError("Original request descriptor hash differs")
        for path_key, sha_key, size_key in (("prompt_path", "prompt_sha256", "prompt_bytes"),
                                            ("schema_path", "schema_sha256", "schema_bytes")):
            payload = artifacts[row[path_key]]
            if digest(payload) != row[sha_key] or len(payload) != row[size_key]:
                raise ValueError("Original request artifact pin differs")
        for source in row["sources"]:
            if digest(artifacts[source["input_path"]]) != source["sha256"]:
                raise ValueError("Original source artifact pin differs")
    prefix = endpoint_rows[:THROUGH]
    expected_dirs = {f"{row['endpoint_ordinal']:04d}-{row['logical_sample_id'][:12]}" for row in prefix}
    attempted_dirs = {path.name for path in results.iterdir()
                      if path.is_dir() and re.fullmatch(r"\d{4}-[0-9a-f]{12}", path.name)}
    if attempted_dirs != expected_dirs:
        raise ValueError("Prefix is incomplete or the requested suffix already contains an attempt")
    receipts = [prefix_receipt(results, row, artifacts, job) for row in prefix]
    suffix = endpoint_rows[THROUGH:]
    descendant = deepcopy(original)
    descendant.pop("manifest_content_sha256")
    descendant["historical_registration"] = {"counts": original["counts"], "bytes": original["bytes"],
                                               "manifest_content_sha256": original["manifest_content_sha256"]}
    descendant["continuation"] = {
        "policy": "untouched_grok_suffix_after_reserved_prefix_v1", "preparer_sha256": digest(Path(__file__).read_bytes()),
        "parent_manifest_sha256": digest(raw), "prefix_job_sha256": digest(job_raw),
        "reserved_endpoint": "grok", "reserved_through_endpoint_ordinal": THROUGH,
        "selection": "Every original Grok request with endpoint_ordinal > 6, independent of prefix outcomes",
        "prefix_receipts": receipts, "no_resend_reserved_prefix": True,
        "previous_runtime_timeout_seconds": job["route"]["timeout_seconds"],
        "requested_runtime_timeout_seconds": timeout_seconds,
        "runtime_authority": "Requires a separately reviewed route; preparation grants no execution authority",
    }
    descendant["requests"] = suffix
    initial = [row for row in suffix if row["repeat"] == 0]
    descendant["counts"] = {
        "reserved_prefix_requests": THROUGH, "requests_per_endpoint": len(suffix), "requests_total": len(suffix),
        "initial_requests_per_endpoint": len(initial), "repeat_requests_per_endpoint": len(suffix) - len(initial),
        "by_arm_per_endpoint": dict(sorted(Counter(row["arm"] for row in suffix).items())),
        "hbq_initial_verdict_positions_per_endpoint": sum(len(row["question_ids"]) for row in initial if row["arm"] == "hbq"),
        "ttcw14_initial_test_positions_per_endpoint": 14 * sum(row["arm"] == "ttcw14" for row in initial),
    }
    if "lineage/parent-manifest.json" in artifacts:
        raise ValueError("Source is already a lineage descendant")
    artifacts["lineage/parent-manifest.json"] = raw
    descendant["artifacts"] = {name: {"sha256": digest(payload), "bytes": len(payload)} for name, payload in sorted(artifacts.items())}
    prompt_bytes = sum(row["prompt_bytes"] for row in suffix)
    descendant["bytes"] = {"prompt_transmission_per_endpoint": prompt_bytes, "prompt_transmission_total": prompt_bytes,
                           "schema_transmission_total": sum(row["schema_bytes"] for row in suffix),
                           "unique_artifacts_total": sum(len(payload) for payload in artifacts.values())}
    descendant["manifest_content_sha256"] = digest(canonical(descendant))
    artifacts["manifest.json"] = canonical(descendant)
    return descendant, artifacts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--prefix-results", type=Path, required=True)
    parser.add_argument("--private-output", type=Path, required=True)
    parser.add_argument("--runtime-timeout-seconds", type=int, default=900)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    output = fresh_private_output(args.private_output, args.manifest.resolve().parent, args.prefix_results)
    manifest, artifacts = build(args.manifest, args.prefix_results, timeout_seconds=args.runtime_timeout_seconds)
    if not args.dry_run:
        output.mkdir(parents=True, exist_ok=False)
        for name, payload in artifacts.items():
            path = within(output, name)
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("xb") as handle:
                handle.write(payload)
    print(json.dumps({"state": "prepared_without_contact" if not args.dry_run else "dry_run_without_contact",
                      "manifest_sha256": digest(artifacts["manifest.json"]),
                      "manifest_content_sha256": manifest["manifest_content_sha256"],
                      "parent_manifest_sha256": manifest["continuation"]["parent_manifest_sha256"],
                      "counts": manifest["counts"], "bytes": manifest["bytes"],
                      "reserved_prefix_states": [r["terminal_state"] for r in manifest["continuation"]["prefix_receipts"]],
                      "provider_calls_made": 0}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
