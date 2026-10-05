"""Join original MFA slots and untouched continuation once under context admission v2."""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import sys
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import context_reconciliation as recon
import collector_context_v2 as continuation
old = recon.old
analysis = old.prepare.load_module("mfa_analysis_context_predecessor_v1", HERE / "analysis.py")


def joined_evidence(manifest, manifest_sha, root, receipt, receipt_sha, suffixes, tools, receipts, subset, validator, runner):
    records, states, seen = [], Counter(), set()
    wrapped = recon.admission(root, manifest, validator, runner)
    for endpoint in old.prepare.ENDPOINTS:
        prefix = {r["logical_sample_id"]: r for r in receipt["endpoints"][endpoint]["prefix"]}
        source = Path(receipt["endpoints"][endpoint]["source_root_local_only"])
        output = suffixes[endpoint]
        binding = continuation.verify_job_binding(output, manifest, manifest_sha, receipt, receipt_sha, endpoint, tools) if output.exists() else None
        suffix_rows = continuation.suffix_rows(manifest, receipt, endpoint)
        if output.exists():
            expected = {old.sample_path(output, r).name for r in suffix_rows}
            recon.require({p.name for p in output.iterdir() if p.is_dir()} <= expected, "Continuation contains a reserved or unknown slot")
        for row in (r for r in manifest["requests"] if r["endpoint"] == endpoint):
            identity = (endpoint, row["logical_sample_id"])
            recon.require(identity not in seen, "Duplicate native logical request in joined evidence")
            seen.add(identity)
            if row["logical_sample_id"] in prefix:
                entry = prefix[row["logical_sample_id"]]
                state = entry["state"]
                states[state] += 1
                if state == "accepted":
                    records.append({"request": row, "response": json.loads((old.sample_path(source, row) / "response.json").read_bytes())})
                continue
            sample = old.sample_path(output, row)
            if not sample.exists():
                states["untouched"] += 1
                continue
            if not (sample / "terminal.json").exists():
                states["started_unresolved"] += 1
                continue
            terminal, answer = old.replay(sample, row, manifest, binding, root, receipts, subset, wrapped)
            states[terminal["state"]] += 1
            if answer is not None:
                records.append({"request": row, "response": answer})
    recon.require(len(seen) == 868, "Full original planned denominator differs")
    return records, dict(states)


def context_runner(manifest, root, runner):
    rows = {r["logical_sample_id"]: r for r in manifest["requests"]}
    def normalize(payload, **kwargs):
        row = rows[kwargs["run_id"]]
        kwargs["context_texts"] = [recon.rendered_context(root, manifest, row, runner)]
        return runner._normalize_batch(payload, **kwargs)
    return SimpleNamespace(_normalize_batch=normalize)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--manifest-sha256", required=True)
    parser.add_argument("--reconciliation", type=Path, required=True)
    parser.add_argument("--reconciliation-sha256", required=True)
    parser.add_argument("--tools-root", type=Path, required=True)
    parser.add_argument("--sol-suffix", type=Path, required=True)
    parser.add_argument("--grok-suffix", type=Path, required=True)
    parser.add_argument("--release-development-labels-postprediction", action="store_true")
    parser.add_argument("--sealed-source-root", type=Path)
    args = parser.parse_args()
    manifest, root, subset, validator = old.load_manifest(args.manifest, args.manifest_sha256, args.tools_root.resolve())
    from hbqrs import core, scoring_v2, codex_receipts
    for name, module in (("core", core), ("scoring_v2", scoring_v2)):
        recon.require(recon.digest(Path(module.__file__).read_bytes()) == manifest["artifacts"]["implementation/" + name + ".py"]["sha256"], "Frozen scorer implementation differs")
    receipt = recon.verify_descendant(args.reconciliation, args.reconciliation_sha256, manifest, args.manifest_sha256, root, codex_receipts, subset, validator)
    runner = recon.frozen_runner(root, manifest)
    records, states = joined_evidence(manifest, args.manifest_sha256, root, receipt, args.reconciliation_sha256,
        {"sol": args.sol_suffix.resolve(), "grok": args.grok_suffix.resolve()}, args.tools_root, codex_receipts, subset, validator, runner)
    hbq = {"core": core, "strict": scoring_v2, "runner": context_runner(manifest, root, runner),
           "modules": core.load_modules(root / "registry/all_modules.yaml")}
    hbq["bundle"] = next(b for b in core.load_bundles(root / "bundles/all_bundles.yaml") if b["bundle_id"] == "prose.short_form")
    selection = json.loads((root / "selection.json").read_bytes())
    banks = analysis.profiles(manifest, records, hbq, root)
    decisions, orders = analysis.pair_decisions(selection, records, banks)
    report = {"study_id": manifest["study_id"], "evidence_class": "two_target_development_canary_descriptive",
        "admission_policy": recon.POLICY, "manifest_sha256": args.manifest_sha256, "reconciliation_sha256": args.reconciliation_sha256,
        "analysis_sha256": recon.digest(Path(__file__).read_bytes()), "predecessor_analysis_sha256": recon.digest((HERE / "analysis.py").read_bytes()),
        "source_prefix_reconciliation": {e: r["summary"] for e, r in receipt["endpoints"].items()}, "terminal_states": states,
        "admitted_requests": len(records), "denominators": receipt["denominators"], "labels_opened": False,
        "extra_votes": 0, "source_texts_and_native_verdicts_unchanged": True, "arithmetic": manifest["scoring"]["baseline"],
        "candidate_gain_claim": False, "powered_inference": False, "fresh_confirmation_claim": False,
        "diagnostics": analysis.diagnostics(banks, decisions, orders, selection),
        "inference_limits": "Two selected development targets with crossed target/writer/rater reuse; no powered or confirmation claim."}
    if args.release_development_labels_postprediction:
        recon.require(args.sealed_source_root is not None, "Explicit label release requires retained source")
        analysis.label_release_gate(states, len(manifest["requests"]))
        ballots = analysis.source_ballots(selection, args.sealed_source_root.resolve())
        report.update(labels_opened=True, decoder=analysis.DECODER, decoder_source=analysis.DECODER_SOURCE,
                      decoder_source_sha256=analysis.DECODER_SOURCE_SHA256, agreement=analysis.agreement(selection, ballots, decisions))
    else:
        recon.require(args.sealed_source_root is None, "Sealed source root requires explicit postprediction release")
    print(json.dumps(report, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
