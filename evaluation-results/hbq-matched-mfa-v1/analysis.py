"""Descriptive development canary analysis; labels require explicit postprediction release.

Reports contain aggregates and commitments. Raw prose, ballots and crossed identity
ledgers remain in their task-private sources. Two targets support no powered inference.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import statistics
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import collector as c

DECODER = "author_style_released_preference_exact_excerpt_v1"
DECODER_SOURCE = "https://github.com/tuhinjubcse/Author-Style-Personalization/blob/d7e4925307ebe354a376ca7f38d8bd014775b6f2/StatAnalysis/01_build_data.R"
DECODER_SOURCE_SHA256 = "e8b65a34c6390b6875fd6142d2167dc4d614313f9b489ca8297a431167d078ef"


def fraction(a, b):
    return a / b if b else None


def label_release_gate(states, planned):
    c.require(states.get("untouched", 0) == 0 and states.get("started_unresolved", 0) == 0
              and sum(states.values()) == planned, "All planned attempts must be terminal before label release")


def source_ballots(selection, source_root):
    """Open only selected positional labels after the caller's terminal release gate."""
    c.require(selection["partition"] == "development" and all(u["partition"] == "development" for u in selection["evaluation_units"]), "Confirmation release forbidden")
    ballots = []
    for receipt in selection["source_receipts"]:
        raw = c.within(source_root, "author-style/" + receipt["path"]).read_bytes()
        c.require(len(raw) == receipt["bytes"] and c.prepare.sha(raw) == receipt["sha256"]
                  and hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest() == receipt["git_blob_sha1"], "Released source pin differs")
        data = json.loads(raw)
        rows = [r for r in selection["metadata_rows"] if r["source_path"] == receipt["path"]]
        c.prepare.extract.selected_texts(data, rows)
        for row in rows:
            _, writers = list(data.items())[row["target_position"]]
            _, judgments = list(writers.items())[row["writer_position"]]
            record = judgments[row["source_position"]][-1]
            preference = record.get("Preference")
            c.require(preference in ("Excerpt1", "Excerpt2"), "Unsupported released Preference profile; no alias/fallback")
            ballots.append({"metadata_row_sha256": c.prepare.sha(c.prepare.canonical(row)), "row": row,
                            "winner_sha256": row["excerpt_hashes"][0 if preference == "Excerpt1" else 1]})
    c.require(len(ballots) == len(selection["metadata_rows"]), "Released selected ballot inventory incomplete")
    return ballots


def collect_evidence(manifest, manifest_sha, root, results, subset, validator, receipts):
    records, states = [], Counter()
    for endpoint in c.prepare.ENDPOINTS:
        output = results[endpoint]
        binding = None
        if output.exists():
            binding = json.loads((output / "job.json").read_bytes())
            c.require(binding["manifest_sha256"] == manifest_sha and binding["endpoint"] == endpoint
                      and binding["runtime"] == manifest["runtime"][endpoint]
                      and binding["collector_sha256"] == c.prepare.sha((HERE / "collector.py").read_bytes())
                      and binding["artifacts_commitment_sha256"] == c.prepare.sha(c.prepare.canonical(manifest["artifacts"]))
                      and binding["extraction_sha256"] == manifest["extraction_sha256"] and binding["workers"] == 1
                      and binding["timeout_seconds"] == 900 and binding["automatic_retries"] == 0, "Collection job differs from frozen contract")
            if endpoint == "grok":
                route = binding["route"]
                c.require(binding["route_sha256"] == c.prepare.sha(c.prepare.canonical(route).rstrip(b"\n"))
                          and route["model"] == manifest["runtime"]["grok"]["model"]
                          and route["reasoning_effort"] == "high" and route["timeout_seconds"] == 900
                          and binding["campaign_deadline"] == c.CUTOFF.isoformat() and binding["deadline_margin_seconds"] == 900
                          and binding["payload_classification"] == "public_repo"
                          and binding["payload_classification"] in route["allowed_payload_classes"], "Retained Grok route differs")
        for row in (r for r in manifest["requests"] if r["endpoint"] == endpoint):
            sample = c.sample_path(output, row)
            if not sample.exists():
                states["untouched"] += 1
                continue
            if not (sample / "terminal.json").exists():
                states["started_unresolved"] += 1
                continue
            terminal, answer = c.replay(sample, row, manifest, binding, root, receipts, subset, validator)
            states[terminal["state"]] += 1
            if answer is not None:
                records.append({"request": row, "response": answer})
    return records, dict(states)


def score_bank(planned, admitted, hbq, root, manifest):
    expected = [qid for row in sorted(planned, key=lambda r: r["batch"]) for qid in row["question_ids"]]
    leaves = [v for item in admitted for v in item["response"]["verdicts"]]
    states = Counter(v["verdict"] for v in leaves)
    coverage = {"planned_packets": len(planned), "accepted_packets": len(admitted), "expected_leaves": len(expected),
                "native_leaves": len(leaves), "states": dict(states), "assessed_binary": states["YES"] + states["NO"],
                "applicable_observed": len(leaves) - states["NOT_APPLICABLE"]}
    coverage["assessed_over_observed_applicable"] = fraction(coverage["assessed_binary"], coverage["applicable_observed"])
    if (len(planned) != 22 or len(expected) != 170 or len(set(expected)) != 170 or len(admitted) != len(planned)
            or len(leaves) != 170 or Counter(v["question_id"] for v in leaves) != Counter(expected)):
        return {"score": None, "state": "incomplete_full_bank_no_scalar", "coverage": coverage}
    row = planned[0]
    contract = json.loads(c.pinned(root, row["task_contract_path"], manifest["artifacts"][row["task_contract_path"]]))
    compiled = hbq["core"].compile_bundle(hbq["modules"], hbq["bundle"], task_contract=contract)
    c.require({q["question"]["id"] for q in hbq["core"].compiled_questions(compiled)} == set(expected), "Frozen compiler bank differs")
    try:
        normalized = []
        for item in sorted(admitted, key=lambda x: x["request"]["batch"]):
            r = item["request"]
            _, _, texts, context = c.inputs(root, manifest, r)
            normalized.extend(hbq["runner"]._normalize_batch(item["response"], expected_ids=r["question_ids"], artifact_id=r["artifact_id"],
                bundle_id=r["bundle_id"], judge_id=r["endpoint"], run_id=r["logical_sample_id"], artifact_text=texts[r["sources"][0]["id"]], context_texts=[context]))
        hbq["strict"].validate_import_admission(hbq["modules"], hbq["bundle"], normalized,
            artifact_id=row["artifact_id"], task_contract=contract, admission_policy="strict_import_v1")
        report = hbq["core"].score_bundle(hbq["modules"], hbq["bundle"], normalized, artifact_id=row["artifact_id"], task_contract=contract)
    except ValueError:
        return {"score": None, "state": "strict_import_unadmitted_no_scalar", "coverage": coverage}
    return {"score": report["final_score"]["observed"] if report["status"] == "SCORED" else None,
            "state": report["status"], "coverage": coverage, "weighted_coverage": report["coverage"], "uncertainty_bounds": report["final_score"]}


def profiles(manifest, records, hbq, root):
    planned, admitted = defaultdict(list), defaultdict(list)
    key = lambda r: (r["endpoint"], r["arm"], r["artifact_id"], r["repeat"])
    for row in manifest["requests"]:
        if row["arm"] != "pairwise":
            planned[key(row)].append(row)
    for item in records:
        if item["request"]["arm"] != "pairwise":
            admitted[key(item["request"])].append(item)
    out = {}
    for identity, rows in planned.items():
        items = admitted[identity]
        if identity[1] == "hbq":
            out[identity] = score_bank(rows, items, hbq, root, manifest)
        elif len(items) != 1:
            out[identity] = {"score": None, "state": "missing_unadmitted_no_scalar"}
        else:
            response = items[0]["response"]
            out[identity] = {"score": None if response["status"] == "CANNOT_ASSESS" else response["result"]["score" if identity[1] == "holistic" else "overall_score"],
                             "state": "explicit_abstention" if response["status"] == "CANNOT_ASSESS" else "assessed"}
    return out


def pair_decisions(selection, records, bank_profiles):
    pairs = {p["pair_id"]: p for p in selection["pairs"]}
    orders = {}
    for item in records:
        row, answer = item["request"], item["response"]
        if row["arm"] != "pairwise" or answer["winner"] == "CANNOT_ASSESS":
            continue
        left = pairs[row["pair_id"]]["excerpt_hashes"][0]
        chosen = None if answer["winner"] == "TIE" else next(s["sha256"] for s in row["sources"] if s["side"] == answer["winner"])
        orders[(row["endpoint"], row["pair_id"], row["repeat"], row["orientation"])] = .5 if chosen is None else float(chosen == left)
    decisions = {}
    for endpoint in c.prepare.ENDPOINTS:
        for pair in selection["pairs"]:
            for cycle in range(3):
                values = [orders.get((endpoint, pair["pair_id"], cycle, orientation)) for orientation in ("AB", "BA")]
                decisions[(endpoint, "pairwise", pair["pair_id"], cycle)] = statistics.mean(values) if all(v is not None for v in values) else None
                for arm in ("hbq", "holistic", "compact"):
                    scores = [bank_profiles.get((endpoint, arm, "mfa-" + h, cycle), {}).get("score") for h in pair["excerpt_hashes"]]
                    decisions[(endpoint, arm, pair["pair_id"], cycle)] = None if any(v is None for v in scores) else (.5 if scores[0] == scores[1] else float(scores[0] > scores[1]))
    return decisions, orders


def diagnostics(bank_profiles, decisions, orders, selection):
    out = {}
    for endpoint in c.prepare.ENDPOINTS:
        for arm, low, high in (("hbq", 0, 100), ("holistic", 1, 7), ("compact", 1, 5)):
            initial = [v for k, v in bank_profiles.items() if k[0] == endpoint and k[1] == arm and k[3] == 0]
            scores = [v["score"] for v in initial if v["score"] is not None]
            deltas = []
            for artifact in selection["bank_sentinel_ids"]:
                values = [bank_profiles.get((endpoint, arm, artifact, cycle), {}).get("score") for cycle in range(3)]
                for v in values[1:]:
                    if values[0] is not None and v is not None:
                        deltas.append(abs(v - values[0]))
            out[endpoint + ":" + arm] = {"native_scale": [low, high], "planned_initial": len(initial), "scalars": len(scores),
                "missing_or_abstained": len(initial) - len(scores), "states": dict(Counter(v["state"] for v in initial)),
                "floor": sum(v == low for v in scores), "ceiling": sum(v == high for v in scores),
                "near_floor_10_percent_range": sum(v <= low + .1 * (high - low) for v in scores),
                "near_ceiling_10_percent_range": sum(v >= high - .1 * (high - low) for v in scores),
                "repeat_comparisons": len(deltas), "repeat_mean_absolute_native_delta": statistics.mean(deltas) if deltas else None,
                "hbq_packet_coverage": [v["coverage"] for v in initial] if arm == "hbq" else None}
        gaps, repeat = [], []
        for pair in selection["pairs"]:
            values = [orders.get((endpoint, pair["pair_id"], 0, o)) for o in ("AB", "BA")]
            if all(v is not None for v in values):
                gaps.append(abs(values[0] - values[1]))
        for pair_id in selection["pair_sentinel_ids"]:
            base = decisions.get((endpoint, "pairwise", pair_id, 0))
            for cycle in (1, 2):
                value = decisions.get((endpoint, "pairwise", pair_id, cycle))
                if base is not None and value is not None:
                    repeat.append(abs(base - value))
        out[endpoint + ":pairwise"] = {"complete_initial_AB_BA_pairs": len(gaps), "planned_pairs": len(selection["pairs"]),
            "order_disagreements": sum(v > 0 for v in gaps), "mean_order_gap": statistics.mean(gaps) if gaps else None,
            "repeat_comparisons": len(repeat), "repeat_mean_absolute_consensus_delta": statistics.mean(repeat) if repeat else None,
            "initial_consensus_ties": sum(v == .5 for k, v in decisions.items() if k[0] == endpoint and k[1] == "pairwise" and k[3] == 0)}
    return out


def agreement(selection, ballots, decisions):
    by_row = {b["metadata_row_sha256"]: b for b in ballots}
    pair_by_row = {h: p for p in selection["pairs"] for h in p["metadata_row_sha256s"]}
    out = {}
    for endpoint in c.prepare.ENDPOINTS:
        for arm in c.prepare.ARMS:
            for panel in ("expert", "lay"):
                for condition in ("fewshot", "finetuned"):
                    units = [u for u in selection["evaluation_units"] if u["panel"] == panel and u["condition"] == condition]
                    credits, unit_means, targets = [], [], defaultdict(list)
                    assessed = ties = 0
                    for unit in units:
                        values = []
                        for member in unit["row_memberships"]:
                            ballot = by_row[member["metadata_row_sha256"]]
                            pair = pair_by_row[member["metadata_row_sha256"]]
                            prediction = decisions.get((endpoint, arm, pair["pair_id"], 0))
                            if prediction is None:
                                credits.append(None)
                                continue
                            left_won = ballot["winner_sha256"] == pair["excerpt_hashes"][0]
                            credit = .5 if prediction == .5 else float((prediction > .5) == left_won)
                            credits.append(credit)
                            values.append(credit)
                            assessed += 1
                            ties += prediction == .5
                        if values:
                            mean = statistics.mean(values)
                            unit_means.append(mean)
                            targets[unit["target_hash"]].append(mean)
                    known = [v for v in credits if v is not None]
                    total = len(credits)
                    out[":".join((endpoint, arm, panel, condition))] = {"planned_ballots": total, "assessed_ballots": assessed,
                        "committed_unique_raters": len({by_row[m["metadata_row_sha256"]]["row"]["rater_hash"] for u in units for m in u["row_memberships"]}),
                        "committed_unique_writers": len({m["writer_hash"] for u in units for m in u["row_memberships"]}),
                        "crossed_inference": "not estimated: two-target descriptive canary; reused raters/writers are not independent ballots",
                        "coverage": fraction(assessed, total), "model_tie_ballots_half_credit": ties,
                        "raw_ballot_agreement_assessed": statistics.mean(known) if known else None,
                        "raw_ballot_all_planned_bounds": [fraction(sum(known), total), fraction(sum(known) + total - assessed, total)],
                        "equal_unit_agreement_assessed": statistics.mean(unit_means) if unit_means else None,
                        "assessed_units": len(unit_means), "planned_units": len(units),
                        "equal_target_agreement_assessed": statistics.mean(statistics.mean(v) for v in targets.values()) if targets else None,
                        "assessed_targets": len(targets), "planned_targets": len({u["target_hash"] for u in units})}
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--manifest-sha256", required=True)
    parser.add_argument("--tools-root", type=Path, required=True)
    parser.add_argument("--sol-results", type=Path, required=True)
    parser.add_argument("--grok-results", type=Path, required=True)
    parser.add_argument("--release-development-labels-postprediction", action="store_true")
    parser.add_argument("--sealed-source-root", type=Path)
    args = parser.parse_args()
    manifest, root, subset, validator = c.load_manifest(args.manifest, args.manifest_sha256, args.tools_root.resolve())
    selection = json.loads((root / "selection.json").read_bytes())
    sys.path.insert(0, str(c.REPO / "src"))
    from hbqrs import core, runner, scoring_v2, codex_receipts
    hbq = {"core": core, "runner": runner, "strict": scoring_v2, "modules": core.load_modules(root / "registry/all_modules.yaml")}
    hbq["bundle"] = next(b for b in core.load_bundles(root / "bundles/all_bundles.yaml") if b["bundle_id"] == "prose.short_form")
    records, states = collect_evidence(manifest, args.manifest_sha256, root, {"sol": args.sol_results.resolve(), "grok": args.grok_results.resolve()}, subset, validator, codex_receipts)
    banks = profiles(manifest, records, hbq, root)
    decisions, orders = pair_decisions(selection, records, banks)
    report = {"study_id": manifest["study_id"], "evidence_class": "two_target_development_canary_descriptive",
        "manifest_sha256": args.manifest_sha256, "analysis_sha256": c.prepare.sha(Path(__file__).read_bytes()),
        "terminal_states": states, "admitted_requests": len(records), "labels_opened": False,
        "candidate_gain_claim": False, "powered_inference": False, "fresh_confirmation_claim": False,
        "diagnostics": diagnostics(banks, decisions, orders, selection),
        "inference_limits": "Two selected development targets; crossed target/writer/rater reuse; expert/lay and conditions separate; no independent-cohort or author generalization."}
    if args.release_development_labels_postprediction:
        c.require(args.sealed_source_root is not None, "Explicit label release requires its retained source")
        label_release_gate(states, len(manifest["requests"]))
        ballots = source_ballots(selection, args.sealed_source_root.resolve())
        report.update(labels_opened=True, decoder=DECODER, decoder_source=DECODER_SOURCE,
                      decoder_source_sha256=DECODER_SOURCE_SHA256,
                      agreement=agreement(selection, ballots, decisions))
    else:
        c.require(args.sealed_source_root is None, "Sealed source root requires explicit postprediction release")
    print(json.dumps(report, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
