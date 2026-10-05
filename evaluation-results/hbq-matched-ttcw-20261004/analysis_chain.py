"""Read-only full-denominator TTCW chain replay; human labels require release.

--config is pinned metadata: manifest_path/manifest_sha256,
secondary_helper_path/secondary_helper_sha256, sources (endpoint, manifest_path,
manifest_sha256, results_root, job_sha256), and optional reconciliations
(path, sha256). Paths and native evidence stay private; stdout is aggregate only.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import importlib.util
import json
from pathlib import Path
import re
import sys

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
POLICY = "matched_ttcw_chain_analysis_v1"
DENOMINATOR = 3108
TERMINAL = {"accepted", "semantic_rejected", "ambiguous", "definitely_not_contacted",
            "unavailable", "unadmitted_no_resend", "completed_schema_rejected"}


def require(value, message):
    if not value:
        raise ValueError(message)


def modules():
    names = ("prepare", "validate_response", "collector_v2", "analysis", "continue_manifest",
             "continue_chain", "continue_sol", "continue_sol_chain", "reconcile_history", "reconcile_sol_transport")
    previous, paths = {name: sys.modules.get(name) for name in names}, list(sys.path)
    result = {}
    try:
        sys.path.insert(0, str(HERE))
        for name in names:
            spec = importlib.util.spec_from_file_location(name, HERE / (name + ".py"))
            module = importlib.util.module_from_spec(spec)
            sys.modules[name] = module
            spec.loader.exec_module(module)
            result[name] = module
    finally:
        sys.path[:] = paths
        for name, old in previous.items():
            if old is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = old
    return result


def planned_rows(manifest, expected=DENOMINATOR):
    rows = manifest["requests"]
    require(len(rows) == expected, "Original full planned denominator differs")
    for endpoint in ("sol", "grok"):
        selected = [row for row in rows if row["endpoint"] == endpoint]
        require(len(selected) == expected // 2 and [row["endpoint_ordinal"] for row in selected] == list(range(1, expected // 2 + 1)), "Original endpoint geometry differs")
    require(len({(row["endpoint"], row["logical_sample_id"]) for row in rows}) == len(rows), "Duplicate original logical vote")
    return {(row["endpoint"], row["logical_sample_id"]): row for row in rows}


def merge(parts, originals):
    joined = {identity: {"request": row, "state": "not_collected", "accepted": None,
                         "terminal_sha256": None, "source_index": None} for identity, row in originals.items()}
    for part in parts:
        for identity, record in part.items():
            require(identity in joined and record["request"] == originals[identity], "Source changes original logical condition")
            require(joined[identity]["state"] == "not_collected", "Duplicate attempted logical vote; no implicit replacement")
            joined[identity] = record
    return joined


def label_release_gate(joined, expected=DENOMINATOR):
    require(len(joined) == expected and all(record["state"] in TERMINAL for record in joined.values()),
            "Human labels require every original planned slot terminal; untouched/in-flight evidence remains")


def lineage(manifest, endpoint, earlier, jobs):
    continuation = manifest.get("continuation")
    if not continuation:
        require(not earlier, "An original job cannot follow its continuations")
        return
    through = continuation["reserved_through_endpoint_ordinal"]
    require(continuation["reserved_endpoint"] == endpoint and continuation["no_resend_reserved_prefix"] is True,
            "Continuation reserved endpoint/no-resend binding differs")
    by_ordinal = {record["request"]["endpoint_ordinal"]: record for record in earlier.values()}
    require(set(by_ordinal) == set(range(1, through + 1)), "Continuation prior prefix is absent or noncontiguous")
    receipts = continuation["prefix_receipts"]
    require(len(receipts) == through, "Continuation prefix denominator differs")
    for ordinal, receipt in enumerate(receipts, 1):
        record = by_ordinal[ordinal]
        require(receipt["endpoint_ordinal"] == ordinal and receipt["logical_sample_id"] == record["request"]["logical_sample_id"]
                and receipt["request_sha256"] == record["request"]["request_sha256"]
                and receipt["terminal_sha256"] == record["terminal_sha256"], "Continuation prefix lineage differs")
        require(record["state"] in TERMINAL, "Continuation reserves an unsettled prefix")
    source_jobs = continuation.get("prefix_jobs")
    if source_jobs is not None:
        require([job["job_sha256"] for job in source_jobs] == jobs, "Continuation source-job chain differs")
    else:
        require(len(jobs) == 1 and continuation["prefix_job_sha256"] == jobs[0], "Continuation original source-job pin differs")


def replay_semantics(row, sample, artifacts, subset, validator):
    response = json.loads((sample / "response.json").read_bytes())
    acceptance = json.loads((sample / "acceptance.json").read_bytes())
    texts = {source["id"]: artifacts[source["input_path"]].decode("utf-8") for source in row["sources"]}
    context = artifacts["context.txt"].decode("utf-8")
    actual = validator.semantic_validate(row["arm"], response, row, texts, subset, context=context,
                                         schema=json.loads(artifacts[row["schema_path"]]))
    require(actual == acceptance, "Frozen semantic/grounding replay differs")
    return None if not actual["accepted"] else {"request": row, "response": response, "abstention": actual["abstention"],
        "source_text": texts[row["sources"][0]["id"]], "context_text": context}


def replay_source(specification, base, base_raw, artifacts, helper, loaded, subset, index):
    prepare, old = loaded["prepare"], loaded["analysis"]
    endpoint = specification["endpoint"]
    require(endpoint in {"sol", "grok"}, "Unknown endpoint")
    path, results = Path(specification["manifest_path"]), Path(specification["results_root"])
    raw = prepare.checked(path, specification["manifest_sha256"])
    source = json.loads(raw)
    old.validate_continuation(source, base, endpoint, base_raw=base_raw, derived_root=path.parent)
    through = source.get("continuation", {}).get("reserved_through_endpoint_ordinal", 0)
    originals = [row for row in base["requests"] if row["endpoint"] == endpoint]
    require([row for row in source["requests"] if row["endpoint"] == endpoint] == originals[through:], "Continuation narrows/reorders original suffix")
    for name, pin in source["artifacts"].items():
        prepare.checked(prepare.within(path.parent, name), pin["sha256"], pin["bytes"])
    prepare.checked(results / "job.json", specification["job_sha256"])
    if endpoint == "sol":
        job, job_raw = loaded["continue_sol"].source_job(results, source, raw, helper)
    else:
        job, job_raw = loaded["continue_chain"]._job(results, source, raw)
        require(job["model"] == "grok-4.7" and job["route"]["reasoning_effort"] == "high", "Frozen Grok model/effort differs")
    allowed = {f"{row['endpoint_ordinal']:04d}-{row['logical_sample_id'][:12]}": row for row in source["requests"] if row["endpoint"] == endpoint}
    attempts = sorted(p for p in results.iterdir() if p.is_dir() and re.match(r"\d{4}-", p.name))
    require(all(p.name in allowed for p in attempts), "Source attempt outside own original descriptors")
    records, identities = {}, []
    for sample in attempts:
        row = allowed[sample.name]
        record = {"request": row, "state": "in_progress_or_unresolved", "accepted": None,
                  "terminal_sha256": None, "source_index": index}
        try:
            terminal_raw = (sample / "terminal.json").read_bytes()
            terminal = json.loads(terminal_raw)
        except (OSError, ValueError):
            records[(endpoint, row["logical_sample_id"])] = record
            continue
        state = terminal.get("state")
        record["terminal_sha256"] = prepare.digest(terminal_raw)
        require(json.loads((sample / "condition.json").read_bytes()) == row and terminal.get("no_resend") is True,
                "Original terminal condition/no-resend binding differs")
        require(state in TERMINAL - {"completed_schema_rejected"}, "Unknown original terminal disposition")
        if endpoint == "sol":
            if state in {"accepted", "semantic_rejected"}:
                receipt, thread, turn = loaded["continue_sol"].prefix_receipt(results, row, artifacts, job)
            else:
                receipt, thread, turn = loaded["continue_sol_chain"].failure_receipt(results, row, artifacts, job)
            if thread: identities.append(("sol_thread", prepare.digest(thread.encode())))
            if turn: identities.append(("sol_turn", prepare.digest(turn.encode())))
        else:
            receipt = loaded["continue_manifest"].prefix_receipt(results, row, artifacts, job)
            native = json.loads((sample / "native-result.json").read_bytes())
            session = json.loads((sample / "native-identity.json").read_bytes())["session_id"]
            identities.append(("grok_session", prepare.digest(session.encode())))
            if native["state"] == "completed":
                runtime = native["result"]["runtime"]
                for runtime_key, route_key in (("subscription_receipt_hash", "subscription_receipt_hash"),
                        ("requested_reasoning_effort", "reasoning_effort"), ("command_identity", "grok_command_identity"),
                        ("cli_version", "grok_cli_version")):
                    require(runtime.get(runtime_key) == job["route"].get(route_key), "Native Grok source-route receipt differs")
                if runtime.get("request_id_hash"): identities.append(("grok_request", runtime["request_id_hash"]))
        require(receipt["terminal_sha256"] == record["terminal_sha256"], "Source terminal changed during replay")
        record["state"] = state
        record["evidence_sha256"] = prepare.digest(prepare.canonical(receipt))
        if state in {"accepted", "semantic_rejected"}:
            record["accepted"] = replay_semantics(row, sample, artifacts, subset, loaded["validate_response"])
            require((record["accepted"] is not None) == (state == "accepted"), "Source terminal admission differs")
        records[(endpoint, row["logical_sample_id"])] = record
    return source, records, identities, {"endpoint": endpoint, "manifest_sha256": prepare.digest(raw),
        "job_sha256": prepare.digest(job_raw), "collector_sha256": job["collector_sha256"],
        "attempts": len(records), "states": dict(Counter(record["state"] for record in records.values()))}


def apply_reconciliation(specification, joined, source_specs, artifacts, loaded, subset):
    prepare, history = loaded["prepare"], loaded["reconcile_history"]
    path = Path(specification["path"])
    raw = prepare.checked(path, specification["sha256"])
    saved = json.loads(raw)
    require(saved.get("no_resend") is True, "Reconciliation lacks no-resend binding")
    sid = saved["logical_sample_id"]
    identity = (saved.get("endpoint", "grok"), sid)
    transport_profile = saved.get("policy") == loaded["reconcile_sol_transport"].POLICY
    expected_state = "unadmitted_no_resend" if transport_profile else "ambiguous"
    require(identity in joined and joined[identity]["state"] == expected_state, "Reconciliation must join one original failed slot")
    record, row = joined[identity], joined[identity]["request"]
    source = source_specs[record["source_index"]]
    sample = Path(source["results_root"]) / f"{row['endpoint_ordinal']:04d}-{sid[:12]}"
    if transport_profile:
        require(identity[0] == source["endpoint"] == "sol" and saved["provider_calls_made"] == saved["new_logical_votes"] == 0
                and saved["human_labels_released"] is False and saved["full_planned_denominator"] == DENOMINATOR
                and saved["original_native_envelope_reconstructed"] is False
                and saved["implementation_sha256"] == prepare.digest((HERE / "reconcile_sol_transport.py").read_bytes()),
                "Saved Sol transport policy/implementation differs")
        commitments = saved["source_commitments"]
        require(commitments["manifest"]["sha256"] == source["manifest_sha256"]
                and commitments["job"]["sha256"] == source["job_sha256"]
                and commitments["terminal"]["sha256"] == record["terminal_sha256"]
                and saved["endpoint_ordinal"] == row["endpoint_ordinal"]
                and saved["request_sha256"] == row["request_sha256"], "Saved Sol transport original source lineage differs")
        actual, response_raw, acceptance, inputs = loaded["reconcile_sol_transport"].reconcile(
            Path(source["manifest_path"]), Path(source["results_root"]), sample.name, loaded["reconcile_sol_transport"].HOME,
            Path(commitments["rollout"]["source_locator_local_only"]), snapshot=path.parent, commitments=commitments)
        require(actual == saved and prepare.checked(path.parent / "response.json", saved["response_sha256"]) == response_raw
                and prepare.checked(path.parent / "acceptance.json", saved["acceptance_sha256"]) == prepare.canonical(acceptance),
                "Saved Sol transport snapshot/descendant replay differs")
        terminal = json.loads((path.parent / "terminal.json").read_bytes())
        require(terminal["reconciliation_sha256"] == specification["sha256"] and terminal["state"] == saved["state"]
                and terminal["no_resend"] is True, "Saved Sol transport descendant terminal differs")
        state = "accepted" if acceptance["accepted"] else "semantic_rejected"
    elif saved.get("evidence_class") == "saved_history_reconciliation_v1":
        require(identity[0] == "grok", "Saved history requires the original Grok endpoint")
        require(saved["provider_calls_made"] == 0 and saved["original_native_envelope_reconstructed"] is False
                and saved["implementation_sha256"] == prepare.digest((HERE / "reconcile_history.py").read_bytes()), "Saved-history policy/reader binding differs")
        commitments = saved["source_commitments"]
        require(commitments["manifest"]["sha256"] == source["manifest_sha256"]
                and commitments["job"]["sha256"] == source["job_sha256"]
                and commitments["terminal"]["sha256"] == record["terminal_sha256"], "Saved-history original source lineage differs")
        pins = {name: (pin["sha256"], pin["bytes"]) for name, pin in commitments.items()}
        actual, response_raw, acceptance, inputs = history.reconcile(Path(source["manifest_path"]), Path(source["results_root"]),
            sample.name, Path(commitments["summary"]["source_locator"]).parent, pins)
        require(actual == saved and prepare.checked(path.parent / "response.json", saved["response_sha256"]) == response_raw
                and prepare.checked(path.parent / "acceptance.json", saved["acceptance_sha256"]) == prepare.canonical(acceptance), "Saved-history descendant replay differs")
        terminal = json.loads((path.parent / "terminal.json").read_bytes())
        require(terminal["reconciliation_sha256"] == specification["sha256"] and terminal["state"] == saved["state"], "Saved-history descendant terminal differs")
        state = "accepted" if acceptance["accepted"] else "semantic_rejected"
    elif saved.get("policy") == "saved_schema_rejection_reconciliation_v1":
        require(identity[0] == "grok", "Saved schema rejection requires the original Grok endpoint")
        require(saved["new_provider_calls"] == saved["new_votes"] == 0 and saved["accepted_vote"] is False
                and saved["original_ambiguity_unchanged"] is True and saved["native_envelope_reconstructed"] is False
                and saved["state"] == "completed_schema_rejected"
                and saved["history_verifier_sha256"] == prepare.digest((HERE / "reconcile_history.py").read_bytes()), "Saved schema-rejection policy differs")
        commitments = saved["source_inputs"]
        require(commitments["manifest"]["sha256"] == source["manifest_sha256"]
                and commitments["job"]["sha256"] == source["job_sha256"]
                and commitments["terminal"]["sha256"] == record["terminal_sha256"]
                and saved["endpoint_ordinal"] == row["endpoint_ordinal"], "Schema-rejection original lineage differs")
        inputs = history.Inputs({name: (pin["sha256"], pin["bytes"]) for name, pin in commitments.items()})
        for name, pin in commitments.items():
            inputs.raw(name, Path(pin["source_locator"]))
        require(inputs.json("condition", sample / "condition.json") == row, "Schema-rejection condition differs")
        response_raw, native = history.history_response(inputs, Path(commitments["summary"]["source_locator"]).parent,
            inputs.json("identity", sample / "native-identity.json"), inputs.json("started", sample / "attempt-started.json"),
            inputs.json("job", Path(source["results_root"]) / "job.json"), artifacts[row["prompt_path"]])
        require(native == saved["native"] and (path.parent / "response.json").read_bytes() == response_raw,
                "Schema-rejection own final/native receipt differs")
        require(not subset.matches_schema(json.loads(response_raw), json.loads(artifacts[row["schema_path"]])), "Schema-rejection descendant unexpectedly matches frozen schema")
        acceptance, state = {"accepted": False, "abstention": False}, "completed_schema_rejected"
    else:
        raise ValueError("Unsupported named reconciliation profile")
    record["original_state"] = record["state"]
    record["state"], record["reconciliation_sha256"] = state, specification["sha256"]
    if acceptance["accepted"]:
        response = json.loads(response_raw)
        texts = {s["id"]: artifacts[s["input_path"]].decode() for s in row["sources"]}
        record["accepted"] = {"request": row, "response": response, "abstention": acceptance["abstention"],
            "source_text": texts[row["sources"][0]["id"]], "context_text": artifacts["context.txt"].decode()}


def build(config, loaded=None):
    loaded = modules() if loaded is None else loaded
    prepare, old = loaded["prepare"], loaded["analysis"]
    path = Path(config["manifest_path"])
    raw = prepare.checked(path, config["manifest_sha256"])
    manifest, pin = old.load_manifest(path)
    originals = planned_rows(manifest)
    artifacts = {name: prepare.checked(prepare.within(path.parent, name), value["sha256"], value["bytes"])
                 for name, value in manifest["artifacts"].items()}
    for row in manifest["requests"]:
        require(prepare.digest(prepare.canonical({k: v for k, v in row.items() if k != "request_sha256"})) == row["request_sha256"], "Original request commitment differs")
        for kind in ("prompt", "schema"):
            require(prepare.digest(artifacts[row[kind + "_path"]]) == row[kind + "_sha256"]
                    and len(artifacts[row[kind + "_path"]]) == row[kind + "_bytes"], "Original request bytes differ")
        for source in row["sources"]:
            require(prepare.digest(artifacts[source["input_path"]]) == source["sha256"], "Original source bytes differ")
    helper = Path(config["secondary_helper_path"])
    prepare.checked(helper, config["secondary_helper_sha256"])
    subset_path = loaded["reconcile_history"].TOOLS / "model_work_queue/adapters/json_schema_subset.py"
    prepare.checked(subset_path, manifest["implementation"]["schema_subset_sha256"])
    prepare.checked(HERE / "validate_response.py", manifest["implementation"]["semantic_validator_sha256"])
    subset = prepare.load_subset(subset_path)
    earlier, jobs, parts, provenance, native_ids, roots = defaultdict(dict), defaultdict(list), [], [], set(), set()
    for index, source in enumerate(config["sources"]):
        root = Path(source["results_root"]).resolve()
        require(root not in roots, "Duplicate source-job result root")
        roots.add(root)
        frozen, records, ids, public = replay_source(source, manifest, raw, artifacts, helper, loaded, subset, index)
        endpoint = source["endpoint"]
        lineage(frozen, endpoint, earlier[endpoint], jobs[endpoint])
        require(not set(earlier[endpoint]) & set(records), "Duplicate original logical attempt across chain")
        require(not native_ids & set(ids) and len(set(ids)) == len(ids), "Duplicate native session/request/turn across chain")
        native_ids.update(ids)
        earlier[endpoint].update(records)
        jobs[endpoint].append(source["job_sha256"])
        parts.append(records)
        provenance.append(public)
    require(set(jobs) == {"sol", "grok"}, "Both endpoint source chains required")
    joined = merge(parts, originals)
    for reconciliation in config.get("reconciliations", []):
        apply_reconciliation(reconciliation, joined, config["sources"], artifacts, loaded, subset)
    endpoints = {endpoint: {sid: record["accepted"] for (ep, sid), record in joined.items()
                 if ep == endpoint and record["accepted"] is not None} for endpoint in ("sol", "grok")}
    report = {"policy": POLICY, "study_id": manifest["study_id"], "evidence_class": "matched_development_prefix_status",
        "manifest_sha256": pin, "analysis_sha256": prepare.digest(Path(__file__).read_bytes()),
        "predecessor_analysis_sha256": prepare.digest((HERE / "analysis.py").read_bytes()),
        "planned_denominator": DENOMINATOR, "scheduled_per_endpoint": DENOMINATOR // 2,
        "endpoint_states": {endpoint: dict(Counter(record["state"] for (ep, _), record in joined.items() if ep == endpoint)) for endpoint in ("sol", "grok")},
        "admitted_requests": {endpoint: len(records) for endpoint, records in endpoints.items()},
        "source_jobs": provenance, "reconciliation_sha256s": [r["sha256"] for r in config.get("reconciliations", [])],
        "slot_ledger_sha256": prepare.digest(prepare.canonical([
            {"request_sha256": row["request_sha256"], **{key: joined[identity].get(key) for key in
                ("state", "original_state", "terminal_sha256", "evidence_sha256", "reconciliation_sha256", "source_index")}}
            for identity, row in originals.items()])),
        "labels_opened": False, "provider_calls_made": 0, "extra_votes": 0, "promotion_authority": False,
        "physical_contact_cardinality_proven": False, "wholebank_scores_reported": False}
    return report, joined, endpoints, manifest, loaded


def release_labels(report, joined, endpoints, manifest, loaded, labels):
    label_release_gate(joined)
    old = loaded["analysis"]
    targets, ballots = old.load_labels(labels, manifest)
    hbq = old.load_hbq(manifest)
    result = dict(report, labels_opened=True, evidence_class="opened_development_baseline_comparator_analysis",
        development_labels_sha256=old.LABEL_SHA, wholebank_scores_reported=True,
        config={"bootstrap_reps": 2000, "seed": old.BOOTSTRAP_SEED, "missing_over_10_percent": "inconclusive",
                "score_samples": "initial only", "pair_graph": "disconnected plot graphs; no global pairwise rho"},
        endpoints=old.analyze(manifest, targets, ballots, endpoints, hbq, reps=2000))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--config-sha256", required=True)
    parser.add_argument("--release-development-labels-postprediction", action="store_true")
    parser.add_argument("--labels", type=Path)
    args = parser.parse_args()
    loaded = modules()
    config = json.loads(loaded["prepare"].checked(args.config, args.config_sha256))
    require(args.release_development_labels_postprediction == (args.labels is not None), "Labels require explicit postprediction release")
    report, joined, endpoints, manifest, _ = build(config, loaded)
    if args.release_development_labels_postprediction:
        report = release_labels(report, joined, endpoints, manifest, loaded, args.labels)
    print(json.dumps(report, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
