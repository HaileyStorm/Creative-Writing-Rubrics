"""One-vote native transport descendant joins using frozen study scoring."""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import reconcile as recon
continuation = recon.load("transport_analysis_continuation", HERE / "collector.py")


def joined_evidence(receipt, receipt_sha, context, suffixes):
    manifest, module = context["manifest"], context["module"]
    prefix = {(e["endpoint"], e["logical_sample_id"]): e for e in receipt["prefix"]}
    recon.require(len(prefix) == len(receipt["prefix"]), "Duplicate reserved logical vote")
    bindings = {}
    for endpoint, output in suffixes.items():
        rows = continuation.suffix_rows(manifest, receipt, endpoint)
        if output.exists():
            bindings[endpoint] = continuation.verify_job_binding(output, receipt, receipt_sha, context, endpoint)
            expected = {module.sample_path(output, row).name for row in rows}
            recon.require({p.name for p in output.iterdir() if p.is_dir()} <= expected, "Continuation contains reserved/unknown logical vote")
    records, inventory, seen = [], [], set()
    for row in manifest["requests"]:
        identity = (row["endpoint"], row["logical_sample_id"])
        recon.require(identity not in seen, "Duplicate planned logical vote")
        seen.add(identity)
        state, answer, recovered = "untouched", None, False
        if identity in prefix:
            entry = prefix[identity]
            recon.require(entry["request_sha256"] == row["request_sha256"] and entry["endpoint_ordinal"] == row["endpoint_ordinal"], "Reserved request binding differs")
            state, answer, recovered = entry["state"], entry["response"], entry["transport_recovered"]
        else:
            sample = module.sample_path(suffixes[row["endpoint"]], row)
            if sample.exists():
                if not (sample / "terminal.json").exists():
                    state = "started_unresolved"
                else:
                    state, answer, recovered = continuation.replay_sample(sample, row, receipt, context, bindings[row["endpoint"]])
        inventory.append({"request": row, "state": state, "transport_recovered": recovered,
                          "native_metrics": {"input_tokens": None, "cached_input_tokens": None, "output_tokens": None, "latency_seconds": None}})
        if state == "accepted":
            recon.require(answer is not None, "Admitted logical vote lacks exact native response")
            records.append({"request": row, "response": answer})
    recon.require(len(seen) == receipt["planned_denominator"], "Full planned denominator differs")
    return records, inventory


def report(receipt, receipt_sha, context, records, inventory):
    manifest, root = context["manifest"], context["root"]
    if receipt["config"]["study"] == "p1":
        previous = recon.load("transport_p1_analysis", recon.REPO / "evaluation-results/hbq-semantic-crossform-p1b-matched-v1/analysis.py")
        hbq = previous.load_hbq(manifest, root)
        result = previous.analyze(manifest, records, inventory, hbq, root)
    else:
        previous = context["module"].prepare.load_module("transport_mfa_analysis", recon.REPO / "evaluation-results/hbq-matched-mfa-v1/analysis.py")
        context_analysis = context["module"].prepare.load_module("transport_mfa_context_analysis", recon.REPO / "evaluation-results/hbq-matched-mfa-v1/analysis_context_v2.py")
        from hbqrs import core, scoring_v2
        for name, module in (("core", core), ("scoring_v2", scoring_v2)):
            recon.require(recon.digest(Path(module.__file__).read_bytes()) == manifest["artifacts"]["implementation/" + name + ".py"]["sha256"], "Frozen study scorer differs")
        hbq = {"core": core, "strict": scoring_v2, "runner": context_analysis.context_runner(manifest, root, context["runner"]),
               "modules": core.load_modules(root / "registry/all_modules.yaml")}
        hbq["bundle"] = next(b for b in core.load_bundles(root / "bundles/all_bundles.yaml") if b["bundle_id"] == "prose.short_form")
        selection = json.loads((root / "selection.json").read_bytes())
        banks = previous.profiles(manifest, records, hbq, root)
        decisions, orders = previous.pair_decisions(selection, records, banks)
        result = {"study_id": manifest["study_id"], "evidence_class": "two_target_development_canary_descriptive",
                  "diagnostics": previous.diagnostics(banks, decisions, orders, selection), "labels_opened": False,
                  "powered_inference": False, "fresh_confirmation_claim": False, "candidate_gain_claim": False}
    result.update(admission_policy=recon.POLICY, manifest_sha256=receipt["manifest_sha256"], reconciliation_sha256=receipt_sha,
        analysis_sha256=recon.digest(Path(__file__).read_bytes()), predecessor_analysis_sha256=recon.digest(Path(previous.__file__).read_bytes()),
        planned_denominator=receipt["planned_denominator"], admitted_requests=len(records), terminal_states=dict(Counter(i["state"] for i in inventory)),
        extra_votes=0, source_native_verdicts_unchanged=True, physical_contact_cardinality_proven=False)
    return result, previous


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reconciliation", type=Path, required=True)
    parser.add_argument("--reconciliation-sha256", required=True)
    parser.add_argument("--sol-suffix", type=Path, required=True)
    parser.add_argument("--grok-suffix", type=Path, required=True)
    parser.add_argument("--release-development-labels-postprediction", action="store_true")
    parser.add_argument("--sealed-source-root", type=Path)
    args = parser.parse_args()
    receipt, context = recon.verify(args.reconciliation, args.reconciliation_sha256)
    records, inventory = joined_evidence(receipt, args.reconciliation_sha256, context, {"sol": args.sol_suffix.resolve(), "grok": args.grok_suffix.resolve()})
    result, previous = report(receipt, args.reconciliation_sha256, context, records, inventory)
    if args.release_development_labels_postprediction:
        recon.require(receipt["config"]["study"] == "mfa" and args.sealed_source_root is not None, "Only explicit MFA development-label release is supported")
        previous.label_release_gate(result["terminal_states"], receipt["planned_denominator"])
        selection = json.loads((context["root"] / "selection.json").read_bytes())
        ballots = previous.source_ballots(selection, args.sealed_source_root.resolve())
        from hbqrs import core, scoring_v2
        context_analysis = context["module"].prepare.load_module("transport_label_context_analysis", recon.REPO / "evaluation-results/hbq-matched-mfa-v1/analysis_context_v2.py")
        hbq = {"core": core, "strict": scoring_v2, "runner": context_analysis.context_runner(context["manifest"], context["root"], context["runner"]),
               "modules": core.load_modules(context["root"] / "registry/all_modules.yaml")}
        hbq["bundle"] = next(b for b in core.load_bundles(context["root"] / "bundles/all_bundles.yaml") if b["bundle_id"] == "prose.short_form")
        banks = previous.profiles(context["manifest"], records, hbq, context["root"])
        decisions, _ = previous.pair_decisions(selection, records, banks)
        result.update(labels_opened=True, decoder=previous.DECODER, decoder_source=previous.DECODER_SOURCE,
                      decoder_source_sha256=previous.DECODER_SOURCE_SHA256, agreement=previous.agreement(selection, ballots, decisions))
    else:
        recon.require(args.sealed_source_root is None, "Sealed sources require explicit postprediction release")
    print(json.dumps(result, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
