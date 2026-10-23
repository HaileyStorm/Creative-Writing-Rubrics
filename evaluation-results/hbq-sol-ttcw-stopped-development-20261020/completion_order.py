"""Prepare a private completion-first order from frozen request metadata only.

No collector, account, reservation, provider or payload file is opened. The output
is an unbound proposal, not a resumable worker or authority to contact a provider.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path


PINS = {
    "manifest": "00b4e3cd33a8d9ed3cc24e6e3e8d07ec20511a6dd87c6507f888d43eb59391bc",
    "census": "f3449263b753175f788e7b266fca69985021db0c6e65cd54a79164b1b64b7aad",
    "frontier": "8a4ea8723bfec8b0c5e8a54d382cd282ee8a8195585f6f7fbce3e8664a30e2ce",
}
SCALAR = {"hbq", "ttcw14", "holistic", "compact", "oregon"}
POLICY = "complete_scalar_banks_then_pair_orders_then_blocked_remainders_v1"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def encoded(value):
    return (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False) + "\n").encode()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def prepare(manifest, census, baseline):
    requests = manifest["requests"]
    require(len(requests) == len(census) == 1044, "Frozen request count differs")
    by_n = {}
    states = {}
    groups = defaultdict(list)
    methods = defaultdict(lambda: defaultdict(list))
    pairs = defaultdict(list)
    for position, (row, cell) in enumerate(zip(requests, census), 1):
        n = row["ordinal"]
        require(n == row["endpoint_ordinal"] == cell["ordinal"] == position, "Ordinal binding differs")
        require(row["repeat"] == 0 and all(row[k] == cell[k] for k in ("arm", "logical_sample_id", "request_sha256")), "Census identity differs")
        by_n[n] = row
        states[n] = cell["state"]
        if row["arm"] in SCALAR:
            require(len(row["sources"]) == 1, "Scalar source count differs")
            aid = row["sources"][0]["id"]
            groups[aid].append(n)
            methods[aid][row["arm"]].append(n)
        else:
            require(row["arm"] == "pairwise" and len(row["sources"]) == 2, "Unexpected arm")
            pairs[tuple(sorted(s["id"] for s in row["sources"]))].append(n)
    accepted = {n for n, state in states.items() if state == "accepted_saved_prediction"}
    blocked = {n for n, state in states.items() if state == "occupied_unadmitted_no_resend"}
    untouched = {n for n, state in states.items() if state == "untouched_held_for_usage_eligibility"}
    require(accepted == set(range(1, 333)) - {22, 81, 128, 129}, "Accepted set changed; replan from current evidence")
    require(blocked == {22, 81, 128, 129, 333} and untouched == set(range(334, 1045)), "Held or no-resend set changed")
    require(len(groups) == len(pairs) == 36, "Source geometry differs")
    for arm_groups in methods.values():
        require(set(arm_groups) == SCALAR and len(arm_groups["hbq"]) == 23 and all(len(arm_groups[arm]) == 1 for arm in SCALAR - {"hbq"}), "Bank membership differs")
    require(all(len(ns) == 2 for ns in pairs.values()), "Pair order membership differs")

    def remaining(ns):
        return sorted(set(ns) & untouched)

    eligible = [(aid, remaining(ns)) for aid, ns in groups.items() if not (set(ns) & blocked)]
    eligible.sort(key=lambda item: (len(item[1]), max(item[1], default=0), item[0]))
    pair_units = [(ids, remaining(ns)) for ids, ns in pairs.items() if remaining(ns)]
    pair_units.sort(key=lambda item: (len(item[1]), max(item[1]), item[0]))
    entries = []
    scheduled = set()

    def append(ns, phase):
        for n in ns:
            require(n in untouched and n not in scheduled, "Duplicate or ineligible planned contact")
            row = by_n[n]
            scheduled.add(n)
            entries.append({"sequence": len(entries) + 1, "source_ordinal": n, "phase": phase,
                            "logical_sample_id": row["logical_sample_id"], "request_sha256": row["request_sha256"],
                            "frozen_row_sha256": sha(encoded(row))})

    for _, ns in eligible:
        append(ns, "complete_scalar_banks")
    for _, ns in pair_units:
        append(ns, "complete_pair_orders")
    append(sorted(untouched - scheduled), "blocked_bank_remainders")
    require(scheduled == untouched and len(entries) == 711, "Untouched requests were dropped")
    for arm_groups in methods.values():
        expected = remaining(arm_groups["hbq"])
        actual = [entry["source_ordinal"] for entry in entries if entry["source_ordinal"] in expected]
        require(actual == expected, "Within-bank HBQ packet order changed")

    position = {entry["source_ordinal"]: entry["sequence"] for entry in entries}
    scalar_milestones = sorted(max((position[n] for n in ns if n in position), default=0)
                               for ns in groups.values() if not (set(ns) & blocked))
    pair_milestones = sorted(max((position[n] for n in ns if n in position), default=0)
                             for ns in pairs.values() if not (set(ns) & blocked))
    baseline_points = baseline["ascending_order_frontier"]
    comparison = [{"complete_request_banks": rank, "completion_first_contacts": count,
                   "ascending_contacts": baseline_points[rank - 1]["suffix_requests_attempted"]}
                  for rank, count in enumerate(scalar_milestones, 1)]
    require(len(comparison) == 32, "Reachable bank count differs")
    execution = {"policy": POLICY, "parent_scientific_condition_sha256": manifest["scientific_condition_sha256"],
                 "input_pins": PINS, "request_order": [entry["source_ordinal"] for entry in entries],
                 "selection_basis": "Only frozen request membership, admission states, request counts and stable identity tie breaks.",
                 "tie_break": "Fewest untouched requests, then smallest last original ordinal, then stable source IDs.",
                 "within_bank_packet_order": "Original relative order retained; internal AB/BA payloads unchanged.",
                 "equivalence_claim": "No claim of unchanged backend cache, temporal drift, latency, cost or judgment distribution."}
    plan = {"schema_version": 1, "state": "PREPARED_UNBOUND_NO_CONTACT", "execution_condition": execution,
            "execution_condition_sha256": sha(encoded(execution)), "entries": entries,
            "requires_consumer_change": "Select by explicit source ordinals and frozen row hashes; track attempted and accepted sets. A maximum ordinal is not a contiguous prefix.",
            "provider_contact_allowed": False, "ledger_or_queue_mutated": False,
            "resume_prerequisites": "Existing same-account eligibility, native/tools-off/resource/ownership controls and cap11 remain; a supported new consumer must bind this order explicitly. Never restart the terminal collector."}
    summary = {"schema_version": 1, "policy": POLICY, "state": plan["state"], "source_pins": PINS,
               "plan_sha256": sha(encoded(plan)), "execution_condition_sha256": plan["execution_condition_sha256"],
               "planned_contacts": len(entries), "retained_no_resend_requests": len(blocked),
               "scalar_completion_comparison": comparison,
               "pair_order_completion_after_contacts": pair_milestones,
               "phase_counts": {phase: sum(entry["phase"] == phase for entry in entries) for phase in ("complete_scalar_banks", "complete_pair_orders", "blocked_bank_remainders")},
               "provider_calls": 0, "scorer_calls": 0, "human_targets_read": False,
               "limits": ["Prospective request membership only; all new contacts assumed accepted, not guaranteed numeric scores or valid judgments.",
                          "Fewest requests is not a claim of minimum tokens, spend or time. Availability-based early subsets need not represent the cohort.",
                          "All711untouched requests retained; no failed or ambiguous resend. Original study and historical inputs remain unchanged.",
                          "Prepared only. No collector, live order, reservation, held queue or provider stop changed."]}
    return plan, summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in PINS:
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True, help="New private directory; contains opaque request identities")
    args = parser.parse_args()
    try:
        data = {}
        for name, pin in PINS.items():
            raw = getattr(args, name).read_bytes()
            require(sha(raw) == pin, name + " source changed")
            data[name] = json.loads(raw)
        plan, summary = prepare(data["manifest"], data["census"], data["frontier"])
        args.output.mkdir()
        for name, raw in (("private-plan.json", encoded(plan)), ("summary.json", encoded(summary)), ("source.py", Path(__file__).read_bytes())):
            with (args.output / name).open("xb") as stream:
                stream.write(raw)
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(2, f"completion order: {error}\n")
    print(json.dumps({"state": summary["state"], "planned_contacts": summary["planned_contacts"],
                      "first_scalar_completion": summary["scalar_completion_comparison"][0],
                      "last_scalar_completion": summary["scalar_completion_comparison"][-1],
                      "plan_sha256": summary["plan_sha256"]}))


if __name__ == "__main__":
    main()
