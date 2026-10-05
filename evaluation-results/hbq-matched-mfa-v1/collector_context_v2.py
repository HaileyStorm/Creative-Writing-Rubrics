"""Collect only untouched MFA suffix slots under rendered-context admission v2."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import context_reconciliation as recon
old = recon.old


def suffix_rows(manifest, receipt, endpoint):
    reserved = receipt["endpoints"][endpoint]
    rows = [r for r in manifest["requests"] if r["endpoint"] == endpoint and r["endpoint_ordinal"] > reserved["reserved_prefix"]]
    recon.require([r["request_sha256"] for r in rows] == reserved["untouched_request_sha256s"], "Untouched suffix commitment differs")
    return rows


def job_binding(manifest, manifest_sha, receipt, receipt_sha, endpoint, tools, route=None):
    rows = suffix_rows(manifest, receipt, endpoint)
    binding = {"manifest_sha256": manifest_sha, "extraction_sha256": manifest["extraction_sha256"], "endpoint": endpoint,
        "runtime": manifest["runtime"][endpoint], "timeout_seconds": 900, "workers": 1, "automatic_retries": 0,
        "policy": recon.POLICY, "collector_sha256": recon.digest(Path(__file__).read_bytes()),
        "reconciler_sha256": recon.digest((HERE / "context_reconciliation.py").read_bytes()),
        "predecessor_collector_sha256": recon.PREDECESSOR_SHA256, "payload_classification": "public_repo",
        "implementation": manifest["implementation"], "artifacts_commitment_sha256": recon.digest(recon.canonical(manifest["artifacts"])),
        "account_probe_sha256": recon.digest((tools / "adaptive_settings/account_probe.py").read_bytes()),
        "broker_sha256": recon.digest((tools / "model_work_queue/broker.py").read_bytes()),
        "reconciliation_sha256": receipt_sha, "source_job_sha256": receipt["endpoints"][endpoint]["source_job_sha256"],
        "reserved_prefix": receipt["endpoints"][endpoint]["reserved_prefix"], "untouched_requests": len(rows),
        "untouched_request_commitment_sha256": recon.digest(recon.canonical([r["request_sha256"] for r in rows])),
        "full_planned_denominators": receipt["denominators"], "provider_contact_cardinality_proven": False,
        "cost_token_cache_attestation": False}
    if endpoint == "grok":
        recon.require(route is not None and route["model"] == "grok-4.7" and route["reasoning_effort"] == "high"
                      and route["timeout_seconds"] == 900 and "public_repo" in route["allowed_payload_classes"], "Reviewed suffix Grok route differs")
        binding.update(route=route, route_sha256=recon.digest(recon.canonical(route).rstrip(b"\n")),
                       campaign_deadline=old.CUTOFF.isoformat(), deadline_margin_seconds=900)
    return binding


def verify_job_binding(output, manifest, manifest_sha, receipt, receipt_sha, endpoint, tools):
    job = json.loads((output / "job.json").read_bytes())
    recon.require(job == job_binding(manifest, manifest_sha, receipt, receipt_sha, endpoint, tools, job.get("route")), "Suffix job binding differs")
    return job


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--manifest-sha256", required=True)
    parser.add_argument("--reconciliation", required=True, type=Path)
    parser.add_argument("--reconciliation-sha256", required=True)
    parser.add_argument("--results-dir", required=True, type=Path)
    parser.add_argument("--tools-root", required=True, type=Path)
    parser.add_argument("--endpoint", required=True, choices=old.prepare.ENDPOINTS)
    parser.add_argument("--route-root", type=Path)
    parser.add_argument("--route-sha256")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    recon.require(args.limit is None or args.limit > 0, "Limit must be positive")
    manifest, root, subset, validator = old.load_manifest(args.manifest, args.manifest_sha256, args.tools_root.resolve())
    sys.path.insert(0, str(old.REPO / "src"))
    from hbqrs import codex_receipts
    receipt = recon.verify_descendant(args.reconciliation, args.reconciliation_sha256, manifest, args.manifest_sha256, root, codex_receipts, subset, validator)
    output = args.results_dir.resolve()
    for protected in [old.REPO, root, args.reconciliation.resolve().parent, *(Path(e["source_root_local_only"]) for e in receipt["endpoints"].values())]:
        recon.require(not output.is_relative_to(protected) and not protected.is_relative_to(output), "Suffix output overlaps retained evidence")
    route = None
    if args.endpoint == "grok":
        recon.require(args.route_root is not None and args.route_sha256 is not None, "Grok requires reviewed exact route pin")
        route = next(r for r in json.loads((args.route_root / "routes.json").read_bytes())["routes"] if r["name"] == "grok-build-grok-4.7")
        recon.require(recon.digest(recon.canonical(route).rstrip(b"\n")) == args.route_sha256, "Reviewed suffix route pin differs")
    binding = job_binding(manifest, args.manifest_sha256, receipt, args.reconciliation_sha256, args.endpoint, args.tools_root, route)
    if output.exists():
        recon.require(json.loads((output / "job.json").read_bytes()) == binding, "Existing suffix job binding differs")
        expected = {old.sample_path(output, row).name for row in suffix_rows(manifest, receipt, args.endpoint)}
        recon.require({p.name for p in output.iterdir() if p.is_dir()} <= expected, "Suffix contains a reserved or unknown slot")
    runner = recon.frozen_runner(root, manifest)
    wrapped = recon.admission(root, manifest, validator, runner)
    pending, settled = [], 0
    for row in suffix_rows(manifest, receipt, args.endpoint):
        sample = old.sample_path(output, row)
        if sample.exists():
            terminal, _ = old.replay(sample, row, manifest, binding, root, codex_receipts, subset, wrapped)
            recon.require(terminal["state"] in old.SETTLED, "Suffix failed/unresolved slot requires reconciliation; no resend")
            settled += 1
        else:
            pending.append(row)
    if args.validate_only:
        print(json.dumps({"state": "provider_free_validated", "endpoint": args.endpoint, "source_prefix_reserved": binding["reserved_prefix"],
            "suffix_planned": binding["untouched_requests"], "suffix_settled": settled, "untouched": len(pending), "provider_calls": 0,
            "full_planned_denominators": receipt["denominators"]}))
        return 0
    if (output / "STOP").exists():
        old.note_stop(output)
        return 3
    if not pending:
        return 0
    helper = call_codex = broker = None
    if args.endpoint == "sol":
        helper = old.prepare.load_module("mfa_context_v2_secondary", Path(manifest["external_pins"]["secondary_helper_path_local_only"]))
        env = old.secondary_binding(manifest, helper)
        os.environ.clear()
        os.environ.update(env)
        sys.path.insert(0, str(args.tools_root))
        from adaptive_settings.account_probe import probe
        old.secondary_binding(manifest, helper, probe(helper.CLI))
        call_codex = runner._call_codex
    else:
        sys.path.insert(0, str(args.tools_root))
        from model_work_queue.broker import Broker
        broker = Broker(args.route_root.resolve())
    if not output.exists():
        output.mkdir(parents=True, exist_ok=False)
        old.record(output / "job.json", binding)
    if args.endpoint == "sol":
        account = old.account_receipt(binding)
        if (output / "account-binding.json").exists():
            recon.require(json.loads((output / "account-binding.json").read_bytes()) == account, "Suffix account binding differs")
        else:
            old.record(output / "account-binding.json", account)
    for row in pending[:args.limit]:
        if args.endpoint == "grok" and not old.grok_contact_allowed():
            print(json.dumps({"state": "campaign_deadline_prevents_new_contact"}))
            return 3
        if (output / "STOP").exists():
            old.note_stop(output)
            return 3
        state = old.collect_one(row, manifest, binding, root, output, subset, wrapped, codex_receipts, helper, call_codex, broker)
        print(json.dumps({"ordinal": row["endpoint_ordinal"], "state": state, "admission_policy": recon.POLICY}), flush=True)
        if state not in old.SETTLED:
            return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
