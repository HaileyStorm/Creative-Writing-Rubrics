"""Freeze an untouched Grok suffix after an ordered, settled source-job chain."""
from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
import json
from pathlib import Path
import re

from analysis import validate_continuation
from collector_v2 import POLICY
from continue_manifest import fresh_private_output, prefix_receipt
from prepare import canonical, checked, digest, within

HERE = Path(__file__).resolve().parent


def _manifest(path: Path) -> tuple[dict, bytes]:
    raw = path.read_bytes()
    manifest = json.loads(raw)
    body = {key: value for key, value in manifest.items() if key != "manifest_content_sha256"}
    if digest(canonical(body)) != manifest["manifest_content_sha256"]:
        raise ValueError("Source manifest content hash differs")
    return manifest, raw


def _job(results: Path, manifest: dict, raw_manifest: bytes) -> tuple[dict, bytes]:
    raw = (results / "job.json").read_bytes()
    job = json.loads(raw)
    route = job.get("route", {})
    if (job.get("endpoint") != "grok" or job.get("manifest_sha256") != digest(raw_manifest)
            or job.get("model") != route.get("model")
            or job.get("route_sha256") != digest(canonical(route)[:-1])
            or job.get("zero_charge_only") is not True or route.get("zero_charge") is not True
            or job.get("automatic_retries") != 0
            or job.get("validator_sha256") != manifest["implementation"]["semantic_validator_sha256"]):
        raise ValueError("Source job manifest, route, admission, or zero-charge binding differs")
    policy = job.get("collector_policy")
    source = HERE / ("collector.py" if policy is None else "collector_v2.py")
    if policy not in {None, POLICY} or job.get("collector_sha256") != digest(source.read_bytes()):
        raise ValueError("Source job collector binding differs")
    frozen_policy = manifest.get("collection_policy")
    if frozen_policy is not None and frozen_policy != {"name": policy, "collector_sha256": job["collector_sha256"]}:
        raise ValueError("Source job frozen collection policy differs")
    return job, raw


def build(manifest_path: Path, prefix_jobs: list[tuple[Path, Path]], *, timeout_seconds: int = 900) -> tuple[dict, dict[str, bytes]]:
    if not prefix_jobs or not 1 <= timeout_seconds <= 3600:
        raise ValueError("A settled prefix chain and bounded runtime timeout are required")
    original, original_raw = _manifest(manifest_path)
    root = manifest_path.resolve().parent
    artifacts = {name: checked(within(root, name), pin["sha256"], pin["bytes"])
                 for name, pin in original["artifacts"].items()}
    if "lineage/parent-manifest.json" in artifacts:
        raise ValueError("--manifest must identify the original frozen study")
    originals = [row for row in original["requests"] if row["endpoint"] == "grok"]
    if ([row["endpoint_ordinal"] for row in originals] != list(range(1, len(originals) + 1))
            or len({row["logical_sample_id"] for row in originals}) != len(originals)):
        raise ValueError("Original request order or logical identities differ")
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
    receipts, commitments = [], []
    logical_ids, sessions, native_requests, result_roots = set(), set(), set(), set()
    for source_path, results in prefix_jobs:
        source_path, results = source_path.resolve(), results.resolve()
        if results in result_roots:
            raise ValueError("Duplicate source-job result root")
        result_roots.add(results)
        source, raw_source = _manifest(source_path)
        validate_continuation(source, original, "grok", base_raw=original_raw, derived_root=source_path.parent)
        job, raw_job = _job(results, source, raw_source)
        allowed = {f"{row['endpoint_ordinal']:04d}-{row['logical_sample_id'][:12]}": row
                   for row in source["requests"] if row["endpoint"] == "grok"}
        attempted = [path for path in results.iterdir() if path.is_dir() and re.match(r"\d{4}-", path.name)]
        if not attempted or any(path.name not in allowed for path in attempted):
            raise ValueError("Source job attempts are absent or outside its frozen descriptors")
        attempted.sort(key=lambda path: allowed[path.name]["endpoint_ordinal"])
        first = len(receipts) + 1
        for sample in attempted:
            row = allowed[sample.name]
            if row["endpoint_ordinal"] != len(receipts) + 1 or row["logical_sample_id"] in logical_ids:
                raise ValueError("Attempted chain prefix is duplicate or noncontiguous")
            receipt = prefix_receipt(results, row, artifacts, job)
            identity = json.loads((sample / "native-identity.json").read_bytes())
            session = identity["session_id"]
            if session in sessions:
                raise ValueError("Duplicate native session identity in prefix chain")
            sessions.add(session)
            native = json.loads((sample / "native-result.json").read_bytes())
            if native["state"] == "completed":
                runtime = native["result"]["runtime"]
                for runtime_key, route_key in (("subscription_receipt_hash", "subscription_receipt_hash"),
                                               ("requested_reasoning_effort", "reasoning_effort"),
                                               ("command_identity", "grok_command_identity"),
                                               ("cli_version", "grok_cli_version")):
                    if route_key in job["route"] and runtime.get(runtime_key) != job["route"][route_key]:
                        raise ValueError("Prefix native receipt differs from its actual source-job route")
                request_id = runtime.get("request_id_hash")
                if request_id is not None:
                    if request_id in native_requests:
                        raise ValueError("Duplicate native request identity in prefix chain")
                    native_requests.add(request_id)
            logical_ids.add(row["logical_sample_id"])
            receipt.update(source_job_index=len(commitments), native_session_id_sha256=digest(session.encode()))
            receipts.append(receipt)
        commitments.append({
            "manifest_sha256": digest(raw_source), "manifest_content_sha256": source["manifest_content_sha256"],
            "job_sha256": digest(raw_job), "route_sha256": job["route_sha256"],
            "collector_sha256": job["collector_sha256"], "collector_policy": job.get("collector_policy"),
            "runtime_timeout_seconds": job["route"]["timeout_seconds"],
            "first_endpoint_ordinal": first, "last_endpoint_ordinal": len(receipts),
            "receipt_commitment_sha256": digest(canonical(receipts[first - 1:])),
        })
    through = len(receipts)
    suffix = originals[through:]
    if not suffix:
        raise ValueError("No untouched suffix remains")
    descendant = deepcopy(original)
    descendant.pop("manifest_content_sha256")
    descendant["historical_registration"] = {"counts": original["counts"], "bytes": original["bytes"],
                                               "manifest_content_sha256": original["manifest_content_sha256"]}
    descendant["continuation"] = {
        "policy": "untouched_grok_suffix_after_reserved_chain_v2", "preparer_sha256": digest(Path(__file__).read_bytes()),
        "receipt_verifier_sha256": digest((HERE / "continue_manifest.py").read_bytes()),
        "parent_manifest_sha256": digest(original_raw), "prefix_jobs": commitments,
        "reserved_endpoint": "grok", "reserved_through_endpoint_ordinal": through,
        "selection": "Every original Grok request beyond the entire settled prefix, independent of all prefix outcomes",
        "prefix_receipts": receipts, "no_resend_reserved_prefix": True,
        "previous_runtime_timeout_seconds": commitments[-1]["runtime_timeout_seconds"],
        "requested_runtime_timeout_seconds": timeout_seconds,
        "runtime_authority": "Requires a separately reviewed route; preparation grants no execution authority",
    }
    descendant["collection_policy"] = {"name": POLICY, "collector_sha256": digest((HERE / "collector_v2.py").read_bytes())}
    descendant["requests"] = suffix
    initial = [row for row in suffix if row["repeat"] == 0]
    descendant["counts"] = {
        "reserved_prefix_requests": through, "requests_per_endpoint": len(suffix), "requests_total": len(suffix),
        "initial_requests_per_endpoint": len(initial), "repeat_requests_per_endpoint": len(suffix) - len(initial),
        "by_arm_per_endpoint": dict(sorted(Counter(row["arm"] for row in suffix).items())),
        "hbq_initial_verdict_positions_per_endpoint": sum(len(row["question_ids"]) for row in initial if row["arm"] == "hbq"),
        "ttcw14_initial_test_positions_per_endpoint": 14 * sum(row["arm"] == "ttcw14" for row in initial),
    }
    artifacts["lineage/parent-manifest.json"] = original_raw
    descendant["artifacts"] = {name: {"sha256": digest(raw), "bytes": len(raw)} for name, raw in sorted(artifacts.items())}
    prompt_bytes = sum(row["prompt_bytes"] for row in suffix)
    descendant["bytes"] = {"prompt_transmission_per_endpoint": prompt_bytes, "prompt_transmission_total": prompt_bytes,
                           "schema_transmission_total": sum(row["schema_bytes"] for row in suffix),
                           "unique_artifacts_total": sum(map(len, artifacts.values()))}
    descendant["manifest_content_sha256"] = digest(canonical(descendant))
    artifacts["manifest.json"] = canonical(descendant)
    return descendant, artifacts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--prefix-job", action="append", required=True, metavar="MANIFEST=RESULTROOT")
    parser.add_argument("--private-output", type=Path, required=True)
    parser.add_argument("--runtime-timeout-seconds", type=int, default=900)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    jobs = []
    for item in args.prefix_job:
        manifest, separator, results = item.partition("=")
        if not separator or not manifest or not results:
            parser.error("--prefix-job requires MANIFEST=RESULTROOT")
        jobs.append((Path(manifest), Path(results)))
    output = fresh_private_output(args.private_output, args.manifest.resolve().parent,
                                  *(path for job in jobs for path in (job[0].resolve().parent, job[1])))
    manifest, artifacts = build(args.manifest, jobs, timeout_seconds=args.runtime_timeout_seconds)
    if not args.dry_run:
        output.mkdir(parents=True, exist_ok=False)
        for name, raw in artifacts.items():
            path = within(output, name)
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("xb") as handle:
                handle.write(raw)
    print(json.dumps({
        "state": "dry_run_without_contact" if args.dry_run else "prepared_without_contact",
        "manifest_sha256": digest(artifacts["manifest.json"]), "manifest_content_sha256": manifest["manifest_content_sha256"],
        "parent_manifest_sha256": manifest["continuation"]["parent_manifest_sha256"],
        "counts": manifest["counts"], "historical_counts": manifest["historical_registration"]["counts"],
        "reserved_prefix_states": dict(Counter(row["terminal_state"] for row in manifest["continuation"]["prefix_receipts"])),
        "source_jobs": manifest["continuation"]["prefix_jobs"], "provider_calls_made": 0,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
