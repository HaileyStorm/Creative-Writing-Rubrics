"""One-contact untouched continuation with own saved-DNS recovery descendants."""
from __future__ import annotations

import argparse
from copy import deepcopy
import json
import os
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import reconcile as recon


def suffix_rows(manifest, receipt, endpoint):
    rows = [r for r in manifest["requests"] if r["endpoint"] == endpoint and r["endpoint_ordinal"] > receipt["reserved_through"][endpoint]]
    recon.require([r["request_sha256"] for r in rows] == receipt["untouched_request_sha256s"][endpoint], "Untouched continuation commitment differs")
    return rows


def job_binding(receipt, receipt_sha, context, endpoint, route=None):
    source = next(s for s in receipt["config"]["sources"] if s["endpoint"] == endpoint)
    binding = deepcopy(recon.bound_source(context, receipt["config"], source))
    binding.update(policy=recon.POLICY, collector_sha256=recon.digest(Path(__file__).read_bytes()),
        reconciler_sha256=recon.digest((HERE / "reconcile.py").read_bytes()), reconciliation_sha256=receipt_sha,
        source_job_sha256=source["job_sha256"], reserved_prefix=receipt["reserved_through"][endpoint],
        untouched_requests=len(receipt["untouched_request_sha256s"][endpoint]),
        untouched_request_commitment_sha256=recon.digest(recon.canonical(receipt["untouched_request_sha256s"][endpoint])),
        full_planned_denominator=receipt["planned_denominator"], saved_transport_recovery_enabled=True,
        timeout_seconds=900, workers=1, automatic_retries=0, provider_contact_cardinality_proven=False)
    if endpoint == "grok":
        recon.require(route is not None and route["name"] == "grok-build-grok-4.7" and route["model"] == "grok-4.7"
            and route["reasoning_effort"] == "high" and route["timeout_seconds"] == 900
            and binding["payload_classification"] in route["allowed_payload_classes"], "Exact reviewed continuation route differs")
        binding.update(route=route, route_sha256=recon.digest(recon.canonical(route).rstrip(b"\n")))
    return binding


def verify_job_binding(output, receipt, receipt_sha, context, endpoint):
    job = json.loads((output / "job.json").read_bytes())
    recon.require(job == job_binding(receipt, receipt_sha, context, endpoint, job.get("route")), "Native transport continuation job differs")
    return job


def replay_sample(sample, row, receipt, context, binding):
    module = context["module"]
    terminal, answer = module.replay(sample, row, context["manifest"], binding, context["root"], recon.codex_receipts, context["subset"], context["validator"])
    if not (sample / "transport-reconciliation.json").exists():
        recon.require(not (sample / "effective-terminal.json").exists(), "Effective terminal has no saved-native descendant")
        return terminal["state"], answer, False
    raw = (sample / "transport-reconciliation.json").read_bytes()
    effective = json.loads((sample / "effective-terminal.json").read_bytes())
    recon.require(effective["reconciliation_sha256"] == recon.digest(raw) and effective["no_resend"] is True, "Effective native descendant binding differs")
    saved = json.loads(raw)
    source = {"endpoint": row["endpoint"], "root_local_only": str(sample.parent), "job_sha256": recon.digest((sample.parent / "job.json").read_bytes())}
    actual, _ = recon.recover_slot(context, receipt["config"], source, row, binding, saved, sample / "transport-native")
    recon.require(actual == saved and actual["transport_recovered"] and effective["state"] == actual["state"], "Saved DNS projection/admission replay differs")
    return actual["state"], actual["response"], True


def recover_current(sample, row, receipt, context, binding):
    source = {"endpoint": row["endpoint"], "root_local_only": str(sample.parent), "job_sha256": recon.digest((sample.parent / "job.json").read_bytes())}
    try:
        entry, snapshots = recon.recover_slot(context, receipt["config"], source, row, binding)
    except (OSError, ValueError, KeyError, TypeError):
        return json.loads((sample / "terminal.json").read_bytes())["state"], False
    if not entry["transport_recovered"]:
        return entry["state"], False
    store = sample / "transport-native"
    store.mkdir(exist_ok=False)
    for relative, raw in snapshots.items():
        path = store / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as stream:
            stream.write(raw)
    raw = recon.canonical(entry)
    with (sample / "transport-reconciliation.json").open("xb") as stream:
        stream.write(raw)
    context["module"].record(sample / "effective-terminal.json", {"state": entry["state"], "no_resend": True,
        "reconciliation_sha256": recon.digest(raw), "original_native_state": entry["original_state"], "new_votes": 0})
    state, _, recovered = replay_sample(sample, row, receipt, context, binding)
    return state, recovered


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reconciliation", type=Path, required=True)
    parser.add_argument("--reconciliation-sha256", required=True)
    parser.add_argument("--endpoint", choices=("grok", "sol"), required=True)
    parser.add_argument("--results-dir", type=Path, required=True)
    parser.add_argument("--route-root", type=Path)
    parser.add_argument("--route-sha256")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    recon.require(args.limit is None or args.limit > 0, "Positive contact limit required")
    receipt, context = recon.verify(args.reconciliation, args.reconciliation_sha256)
    module, manifest, root = (context[k] for k in ("module", "manifest", "root"))
    output = args.results_dir.resolve()
    protected = [recon.REPO, root, args.reconciliation.resolve().parent, *(Path(s["root_local_only"]) for s in receipt["config"]["sources"])]
    protected.extend(Path(receipt["config"][k]) for k in ("secondary_home_local_only", "grok_sessions_root_local_only"))
    recon.require(all(not output.is_relative_to(p.resolve()) and not p.resolve().is_relative_to(output) for p in protected), "Continuation overlaps retained evidence")
    route = None
    if args.endpoint == "grok":
        recon.require(args.route_root is not None and args.route_sha256 is not None, "Exact reviewed Grok route pin required")
        route = next(r for r in json.loads((args.route_root / "routes.json").read_bytes())["routes"] if r["name"] == "grok-build-grok-4.7")
        recon.require(recon.digest(recon.canonical(route).rstrip(b"\n")) == args.route_sha256, "Reviewed Grok route pin differs")
    binding = job_binding(receipt, args.reconciliation_sha256, context, args.endpoint, route)
    planned = suffix_rows(manifest, receipt, args.endpoint)
    if output.exists():
        recon.require(json.loads((output / "job.json").read_bytes()) == binding, "Existing continuation job differs")
        expected = {module.sample_path(output, row).name for row in planned}
        recon.require({p.name for p in output.iterdir() if p.is_dir()} <= expected, "Continuation contains reserved/unknown slot")
    pending, settled = [], 0
    for row in planned:
        sample = module.sample_path(output, row)
        if sample.exists():
            state, _, _ = replay_sample(sample, row, receipt, context, binding)
            recon.require(state in module.SETTLED, "Started/unknown native slot occupies identity; no resend")
            settled += 1
        else:
            pending.append(row)
    if args.validate_only:
        print(json.dumps({"state": "provider_free_validated", "endpoint": args.endpoint, "reserved_prefix": binding["reserved_prefix"],
            "untouched": len(pending), "settled_suffix": settled, "full_planned_denominator": receipt["planned_denominator"], "provider_calls": 0}))
        return 0
    if (output / "STOP").exists():
        module.note_stop(output)
        return 3
    if not pending:
        return 0
    helper = call_codex = broker = None
    if args.endpoint == "sol":
        if receipt["config"]["study"] == "mfa":
            source = manifest
            pins = manifest["external_pins"]
            runner = context["runner"]
        else:
            source = module.source_settings(manifest, root)
            pins = source["external_pins"]
            from hbqrs import runner
        helper = recon.load("transport_secondary_helper", Path(pins["secondary_helper_path_local_only"]))
        env = module.secondary_binding(source, helper)
        os.environ.clear()
        os.environ.update(env)
        sys.path.insert(0, str(context["tools"]))
        from adaptive_settings.account_probe import probe
        module.secondary_binding(source, helper, probe(helper.CLI))
        call_codex = runner._call_codex
    else:
        sys.path.insert(0, str(context["tools"]))
        from model_work_queue.broker import Broker
        broker = Broker(args.route_root.resolve())
    if not output.exists():
        output.mkdir(parents=True, exist_ok=False)
        module.record(output / "job.json", binding)
    if args.endpoint == "sol":
        account = module.account_receipt(binding)
        if (output / "account-binding.json").exists():
            recon.require(json.loads((output / "account-binding.json").read_bytes()) == account, "Continuation account receipt differs")
        else:
            module.record(output / "account-binding.json", account)
    for row in pending[:args.limit]:
        if (output / "STOP").exists():
            module.note_stop(output)
            return 3
        if args.endpoint == "grok" and not module.grok_contact_allowed():
            print(json.dumps({"state": "campaign_deadline_prevents_new_contact"}), flush=True)
            return 3
        state = module.collect_one(row, manifest, binding, root, output, context["subset"], context["validator"], recon.codex_receipts, helper, call_codex, broker)
        recovered = False
        if state not in module.SETTLED:
            state, recovered = recover_current(module.sample_path(output, row), row, receipt, context, binding)
        print(json.dumps({"ordinal": row["endpoint_ordinal"], "state": state, "transport_recovered": recovered}), flush=True)
        if state not in module.SETTLED:
            return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
