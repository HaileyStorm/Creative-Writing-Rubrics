"""Explicit Grok native-once execution descendant for the frozen 008 suffix.

Native/envelope/semantic replay and STOP/drain use an isolated pinned v3 instance.
Preparation and validate-only grant no allocation, label release, or execution.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sys
from threading import Event

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
POLICY = "ttcw_untouched_suffix_execution_v4"
PERSISTENCE_GUARD_POLICY = "free_disk_before_native_contact_v1"
MINIMUM_FREE_DISK_BYTES = 256 * 1024 * 1024
NATIVE_BASE_SHA = "bfa5f34895d1eaa76ed6d1f5aca39f2b76919c2fb97780e5ed3531d7814599be"
MANIFEST_SHA = "cce67e7abb0d44ffb4c9cfd972d112c5fd8712b1732fe0071cd5aaccaf9aaf4c"
CONTENT_SHA = "21ceae90ccadd02281b9ef359ee543d67a4a649222e4177a31da880e145d9b16"
SOURCE_MANIFEST_SHA = "7da4c9202c97fa972fc53447e8046c6f56ab5db2f0be75ffb28951095a8e642f"
SOURCE_JOB_SHA = "ece262548f5fa0b9bf91dcfb5872816adac9a8aea127cce33a0e48953c7a76dd"
SOURCE_INVENTORY_SHA = "3594947ce66ed790d9e7466a65a1b7d1083a055b592c1bdab126a077719cdce3"
RELEASE_INVOCATION_SHA = "983701d65c56c5eb381fc56eba2e65428f17dc931627b90027fd35348a3188f6"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def native_base():
    path = HERE / "collector_suffix_v3.py"
    require(sha(path.read_bytes()) == NATIVE_BASE_SHA, "Pinned native base differs")
    name = "ttcw_suffix_v3_frozen_utilities"
    previous = sys.modules.get(name)
    try:
        spec = importlib.util.spec_from_file_location("ttcw_suffix_v4_isolated_native_base", path)
        loaded = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(loaded)
    finally:
        if previous is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = previous
    loaded.MANIFEST_SHA = MANIFEST_SHA
    loaded.POLICY = POLICY
    return loaded


base = native_base()
canonical, pinned, record = base.canonical, base.pinned, base.record
ROUTE_SHA, TOOLS = base.ROUTE_SHA, base.TOOLS
_native_guard = base.guard


def guard(binding, output, halt, route_root=None, now=None):
    require(shutil.disk_usage(output.parent).free >= MINIMUM_FREE_DISK_BYTES,
            "At least256MiB free disk space required before native contact")
    return _native_guard(binding, output, halt, route_root, now)


# collect_one resolves this guard in its private v3 module immediately before contact.
base.guard = guard


def load_manifest(path, expected, endpoint):
    require(endpoint == "grok", "008 is a Grok-only suffix")
    raw = path.read_bytes()
    require(expected == MANIFEST_SHA == sha(raw), "Explicit frozen008 manifest SHA differs")
    manifest, root = json.loads(raw), path.resolve().parent
    body = {k: v for k, v in manifest.items() if k != "manifest_content_sha256"}
    require(sha(canonical(body) + b"\n") == CONTENT_SHA == manifest["manifest_content_sha256"], "008 content differs")
    require(manifest["execution_authority"] is False and manifest["executor_contract"]["execution_enabled"] is False
            and manifest["executor_contract"]["actual_headroom_verified"] is False
            and manifest["executor_contract"]["execution_route_sha256"] == ROUTE_SHA
            and manifest["executor_contract"]["expiry_margin_seconds"] == 960, "008 preparation controls differ")
    artifacts = {name: pinned(root, name, pin["sha256"]) for name, pin in manifest["artifacts"].items()}
    require(all(len(artifacts[name]) == pin["bytes"] for name, pin in manifest["artifacts"].items()), "Frozen artifact size differs")
    continuation = manifest["continuation"]
    parent_raw = artifacts["lineage/parent-manifest.json"]
    require(sha(parent_raw) == continuation["parent_manifest_sha256"], "Original parent commitment differs")
    parent = json.loads(parent_raw)
    for name in ("study_id", "source_pins", "runtime", "context", "implementation", "public_asset_hashes",
                 "stories", "sentinels", "pairs", "repeat_pair_ids"):
        require(manifest.get(name) == parent.get(name), "008 changes a frozen scientific condition")
    require(parent["counts"]["requests_total"] == 3108 and parent["counts"]["requests_per_endpoint"] == 1554
            and parent["counts"]["stories"] == len(manifest["stories"]) == 36, "Original scientific denominator differs")
    require(manifest["artifacts"] == dict(parent["artifacts"], **{
        "lineage/parent-manifest.json": {"sha256": sha(parent_raw), "bytes": len(parent_raw)}}),
        "Scientific artifact inventory differs")
    originals = [r for r in parent["requests"] if r["endpoint"] == "grok"]
    rows = manifest["requests"]
    require([r["endpoint_ordinal"] for r in originals] == list(range(1, 1555)) and rows == originals[322:]
            and len(rows) == manifest["counts"]["requests_total"] == 1232
            and continuation["reserved_endpoint"] == endpoint and continuation["reserved_through_endpoint_ordinal"] == 322
            and continuation["no_resend_reserved_prefix"] is True and continuation["source_manifest_sha256"] == SOURCE_MANIFEST_SHA,
            "008 narrows/reorders original323..1554 suffix")
    receipts, jobs = continuation["prefix_receipts"], continuation["prefix_jobs"]
    require([r["endpoint_ordinal"] for r in receipts] == list(range(1, 323)), "Reserved prefix322 differs")
    for receipt, row in zip(receipts, originals):
        require(receipt["logical_sample_id"] == row["logical_sample_id"] and receipt["request_sha256"] == row["request_sha256"]
                and receipt["no_resend"] is True and receipt["terminal_sha256"], "Reserved original receipt differs")
    latest = jobs[-1]
    inventory = latest["source_inventory"]
    require(latest["job_sha256"] == SOURCE_JOB_SHA and latest["collector_sha256"] == NATIVE_BASE_SHA
            and latest["manifest_sha256"] == SOURCE_MANIFEST_SHA
            and latest["source_inventory_sha256"] == SOURCE_INVENTORY_SHA == sha(canonical(inventory) + b"\n")
            and latest["retained_release_invocation_sha256"] == RELEASE_INVOCATION_SHA
            and [r["ordinal"] for r in inventory] == list(range(280, 323)), "Retained007 metadata lineage differs")
    for retained, receipt in zip(inventory, receipts[279:]):
        require(retained["logical_sample_id"] == receipt["logical_sample_id"]
                and retained["request_sha256"] == receipt["request_sha256"]
                and retained["metadata_pins"]["terminal.json"]["sha256"] == receipt["terminal_sha256"]
                and retained["state_metadata_only"] == receipt["terminal_state"]
                and retained["native_identity_sha256"] == receipt["native_session_id_sha256"],
                "Retained007 receipt membership differs")
    sys.path.insert(0, str(TOOLS))
    from model_work_queue.adapters import json_schema_subset as subset
    require(sha(Path(subset.__file__).read_bytes()) == manifest["implementation"]["schema_subset_sha256"]
            and sha((HERE / "validate_response.py").read_bytes()) == manifest["implementation"]["semantic_validator_sha256"],
            "Frozen admission implementation differs")
    validator = base.load_module("ttcw_suffix_v4_semantic_validator", HERE / "validate_response.py")
    for row in rows:
        require(sha(canonical({k: v for k, v in row.items() if k != "request_sha256"}) + b"\n") == row["request_sha256"],
                "Original request descriptor differs")
        for kind in ("prompt", "schema"):
            raw = artifacts[row[kind + "_path"]]
            require(sha(raw) == row[kind + "_sha256"] and len(raw) == row[kind + "_bytes"], "Frozen request payload differs")
        subset.validate_schema(json.loads(artifacts[row["schema_path"]]))
        require(all(sha(artifacts[s["input_path"]]) == s["sha256"] for s in row["sources"]), "Original source differs")
    return manifest, root, rows, subset, validator


def job_binding(manifest, endpoint, workers, headroom, route, *, owner_attestations=None):
    require(endpoint == "grok" and manifest["continuation"]["reserved_through_endpoint_ordinal"] == 322
            and manifest["counts"]["requests_total"] == 1232, "008 execution geometry differs")
    binding = base.job_binding(manifest, endpoint, workers, headroom, route)
    binding.update(collector_policy=POLICY, collector_sha256=sha(Path(__file__).read_bytes()),
        persistence_guard_policy=PERSISTENCE_GUARD_POLICY, minimum_free_disk_bytes=MINIMUM_FREE_DISK_BYTES,
        native_base_collector_sha256=NATIVE_BASE_SHA, native_base_policy="ttcw_untouched_suffix_execution_v3",
        manifest_sha256=MANIFEST_SHA, manifest_content_sha256=CONTENT_SHA, reserved_through_endpoint_ordinal=322,
        selected_requests_per_endpoint=1232, first_endpoint_ordinal=323, last_endpoint_ordinal=1554, original_stories=36,
        owner_attestations=owner_attestations or {"global_headroom_verified": False, "returned_allocation_verified": False,
            "current_route_verified": False, "outbound_disclosure_confirmed": False},
        own_lifecycle_binding_verified=False, returned_allocation_natively_verified=False)
    return binding


def replay(sample, row, binding, root, subset, validator, receipts=None):
    require(binding["collector_policy"] == POLICY and binding["collector_sha256"] == sha(Path(__file__).read_bytes())
            and binding["native_base_collector_sha256"] == NATIVE_BASE_SHA and binding["manifest_sha256"] == MANIFEST_SHA
            and binding["reserved_through_endpoint_ordinal"] == 322 and 323 <= row["endpoint_ordinal"] <= 1554,
            "008 replay job/original suffix differs")
    return base.replay(sample, row, binding, root, subset, validator, receipts)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--manifest-sha256", required=True)
    parser.add_argument("--results-dir", required=True, type=Path)
    parser.add_argument("--endpoint", required=True, choices=("grok",))
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--endpoint-headroom", required=True, type=int)
    parser.add_argument("--route-root", required=True, type=Path)
    parser.add_argument("--route-sha256", required=True)
    parser.add_argument("--limit", type=int)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--validate-only", action="store_true")
    mode.add_argument("--execute-native", action="store_true")
    parser.add_argument("--owner-global-headroom-verified", action="store_true")
    parser.add_argument("--owner-returned-allocation-verified", action="store_true")
    parser.add_argument("--owner-current-route-verified", action="store_true")
    parser.add_argument("--owner-outbound-disclosure-confirmed", action="store_true")
    args = parser.parse_args()
    attestations = {"global_headroom_verified": args.owner_global_headroom_verified,
        "returned_allocation_verified": args.owner_returned_allocation_verified,
        "current_route_verified": args.owner_current_route_verified,
        "outbound_disclosure_confirmed": args.owner_outbound_disclosure_confirmed}
    require(not args.execute_native or all(attestations.values()), "Native dispatch requires all explicit owning-root attestations")
    require(args.limit is None or args.limit > 0, "Positive explicit limit required")
    output = args.results_dir.resolve()
    require(not output.exists(), "Fresh results required; occupied attempts never resent")
    for protected in (REPO, args.manifest.resolve().parent):
        require(not output.is_relative_to(protected) and not protected.is_relative_to(output), "Results overlap retained inputs")
    manifest, root, rows, subset, validator = load_manifest(args.manifest, args.manifest_sha256, args.endpoint)
    route = base.reviewed_route(args.route_root.resolve(), args.route_sha256)
    binding = job_binding(manifest, args.endpoint, args.workers, args.endpoint_headroom, route, owner_attestations=attestations)
    halt = Event()
    base.guard(binding, output, halt, args.route_root)
    if args.validate_only:
        print(json.dumps({"state": "validated_without_contact", "policy": POLICY, "manifest_sha256": MANIFEST_SHA,
            "manifest_content_sha256": CONTENT_SHA, "collector_sha256": binding["collector_sha256"],
            "native_base_collector_sha256": NATIVE_BASE_SHA, "job_binding_sha256": sha(canonical(binding)),
            "requests": len(rows), "original_requests_total": 3108, "original_stories": 36,
            "reserved_through": 322, "workers": args.workers, "owner_declared_headroom": args.endpoint_headroom,
            "available_headroom_verified": False, "own_lifecycle_binding_verified": False,
            "provider_calls": 0, "account_probe_performed": False, "outputs_written": False,
            "human_labels_read": False, "native_execution_verified": False}, sort_keys=True))
        return 0
    sys.path.insert(0, str(TOOLS))
    from model_work_queue.broker import Broker
    broker = Broker(args.route_root.resolve())
    base.guard(binding, output, halt, args.route_root)
    output.mkdir(parents=True, exist_ok=False)
    record(output / "job.json", binding)
    selected = rows if args.limit is None else rows[:args.limit]
    _, stopped = base.dispatch(selected, output, args.workers,
        lambda row, signal: base.collect_one(row, binding, root, output, subset, validator, signal,
                                            args.route_root, broker),
        lambda signal: base.guard(binding, output, signal, args.route_root))
    return 3 if stopped else 0


if __name__ == "__main__":
    raise SystemExit(main())
