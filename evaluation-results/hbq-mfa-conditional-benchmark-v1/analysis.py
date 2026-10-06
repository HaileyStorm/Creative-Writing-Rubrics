"""Original-native conditional benchmark replay and separately gated label analysis."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import random
import sys

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
POLICY = "mfa_conditional_native_ladder_analysis_v1"
MANIFEST_SHA = "95e1008505a7e4b7294f505bbfae02a6e99c5dd6d30c9d98aa80b52079b6b409"
READER_SHA = "2d82e4959c3296ccaa6e6521adb46f85588427d429a544b36a2891ebaea8c7b0"
PROFILE_SHA = "1a6f179641b8aa20f7c0e91e99e116cc052d0f31bffc5027dea95f12b84492fc"
VIEWS = ("historical", "candidate", "holistic", "compact", "pairwise")
DETERMINATE = {"LEFT", "RIGHT", "TIE"}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False) + "\n").encode()


def checked(path, expected):
    raw = Path(path).read_bytes()
    require(sha(raw) == expected, "Pinned bytes differ: " + str(path))
    return raw


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def profile():
    value = json.loads(checked(HERE / "analysis-profile.json", PROFILE_SHA))
    require(value["policy"] == POLICY and value["manifest_sha256"] == MANIFEST_SHA
            and value["automatic_promotion"] is False, "Analysis profile differs")
    return value


def metadata_view(path):
    # Extract only the reviewed lexical reader, avoiding preparation/runtime imports.
    import ast
    policy = profile()
    p = HERE.parent / "hbq-matched-hanna-20261004/prepare.py"
    tree = ast.parse(checked(p, READER_SHA))
    functions = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in ("require", "project_json")]
    scope = {"json": json}
    exec(compile(ast.Module(body=functions, type_ignores=[]), "pinned_metadata_boundary", "exec"), scope)
    raw = checked(path, MANIFEST_SHA)
    fields = {k: True for k in ("counts", "study_id", "labels_read", "scoring", "candidate_mechanism_profile_sha256", "membership_profile_sha256")}
    fields["requests"] = [{k: True for k in ("endpoint", "arm", "repeat", "artifact_id", "batch", "question_ids", "logical_sample_id", "context_sha256")}]
    data = scope["project_json"](raw, fields)
    rows = data.pop("requests")
    counts = data["counts"]
    require(counts["requests_total"] == len(rows) == 10340 and counts["planned_Preference_ballots"] == 3276
            and data["labels_read"] is False and counts["unique_texts"] == 199
            and data["candidate_mechanism_profile_sha256"] == policy["candidate_profile_sha256"]
            and data["membership_profile_sha256"] == policy["membership_profile_sha256"], "Frozen denominator differs")
    banks = defaultdict(list)
    for r in rows:
        if r["arm"] == "hbq":
            banks[(r["endpoint"], r["artifact_id"], r["repeat"])].append(r)
    require(len(banks) == 406 and all(len(rs) == 22 and len({q for r in rs for q in r["question_ids"]}) == 170 for rs in banks.values()),
            "Full frozen bank geometry differs")
    return {"policy": POLICY, "manifest_sha256": MANIFEST_SHA, "analysis_profile_sha256": sha((HERE / "analysis-profile.json").read_bytes()),
            "counts": counts, "bank_geometry_verified": True, "metadata_only": True, "results_read": False,
            "source_values_read": False, "labels_opened": False, "provider_calls": 0, "candidate_promoted": False}


def collector_runtime():
    p = profile()
    checked(HERE / "collector.py", p["collector_sha256"])
    candidate = HERE.parent / "hbq-matched-mfa-v1"
    checked(candidate / "analysis_ladder_candidate.py", p["candidate_analysis_sha256"])
    candidate_profile = json.loads(checked(candidate / "ladder-candidate-profile.json", p["candidate_profile_sha256"]))
    for locator, digest in candidate_profile["source_files_sha256"].items():
        checked(REPO / locator, digest)
    c = load_module("conditional_analysis_collector", HERE / "collector.py")
    sys.path.insert(0, str(REPO / "src"))
    from hbqrs import core, runner, ladder_uncertainty, decision_readiness, codex_receipts
    return c, {"core": core, "runner": runner, "ladder": ladder_uncertainty,
               "readiness": decision_readiness, "receipts": codex_receipts}


def verify_outer(terminal_path, terminal_sha, invocation_path, invocation_sha, *, manifest_path, results, endpoint, binding, c):
    terminal = json.loads(checked(terminal_path, terminal_sha))
    invocation = json.loads(checked(invocation_path, invocation_sha))
    require(terminal.get("exit_code") in (0, 3) and terminal.get("no_resend") is True
            and terminal.get("invocation_sha256") == invocation_sha, "Pinned true outer return required")
    argv = invocation["argv"]
    require(isinstance(argv, list) and str(HERE / "collector.py") in argv and "--validate-only" not in argv,
            "Own original collector invocation required")
    def arg(name):
        require(argv.count(name) == 1, "Invocation argument missing/duplicated: " + name)
        return argv[argv.index(name) + 1]
    require(Path(arg("--manifest")).resolve() == manifest_path.resolve() and arg("--manifest-sha256") == MANIFEST_SHA
            and Path(arg("--results-dir")).resolve() == results.resolve() and arg("--endpoint") == endpoint
            and int(arg("--workers")) == binding["workers"]
            and int(arg("--endpoint-headroom")) == binding["owner_declared_endpoint_headroom"]
            and arg("--payload-classification") == binding["payload_classification"], "Outer invocation/job binding differs")
    require(datetime.fromisoformat(invocation["time"]) <= datetime.fromisoformat(terminal["time"]), "Outer chronology differs")
    return {"verified": True, "terminal_sha256": terminal_sha, "invocation_sha256": invocation_sha,
            "job_sha256": c.sha((results / "job.json").read_bytes()), "exit_code": terminal["exit_code"],
            "local_dispatch_return_only": True, "physical_remote_settlement_proven": False}


def native_identity(c, sample, row, terminal):
    path = sample / "native-identity.json"
    identity = json.loads(path.read_bytes()) if path.exists() else None
    if identity is not None:
        require(identity["logical_sample_id"] == row["logical_sample_id"], "Native logical identity differs")
    if row["endpoint"] == "grok":
        session = identity["session_id"] if identity else None
        require(terminal["state"] not in c.SETTLED or isinstance(session, str) and bool(session), "Strict native session missing")
        return session
    if terminal["state"] in c.SETTLED:
        native = json.loads((sample / "native-result.json").read_bytes())
        receipt = native["provider_artifacts"]["codex_receipt"]
        value = json.loads(c.pinned(sample, receipt["path"], receipt))
        require(bool(value["thread_id"]) and bool(value["turn_id"])
                and native["reported"]["session_id"] == value["thread_id"], "Own strict native identity missing")
        return value["thread_id"]
    return None


def collect_evidence(c, manifest, root, results, tools, subset, validator, receipts):
    records, ledger, states, jobs, seen = [], [], Counter(), {}, set()
    for endpoint in ("sol", "grok"):
        output = results[endpoint]
        binding = None
        if output.exists():
            binding = json.loads((output / "job.json").read_bytes())
            expected = c.job_binding(manifest, MANIFEST_SHA, endpoint, tools, workers=binding["workers"],
                headroom=binding["owner_declared_endpoint_headroom"], classification="public_repo", route=binding.get("route"))
            c.verify_job_binding(output, expected)
            jobs[endpoint] = binding
        for row in (r for r in manifest["requests"] if r["endpoint"] == endpoint):
            sample = c.sample_path(output, row)
            entry = {"endpoint": endpoint, "logical_sample_id": row["logical_sample_id"], "request_sha256": row["request_sha256"],
                     "state": "untouched", "original_strict_native_verified": False, "native_identity": None}
            if sample.exists():
                if not (sample / "terminal.json").exists():
                    entry["state"] = "started_unresolved"
                else:
                    require(binding is not None, "Occupied sample without own job")
                    terminal, answer = c.replay(sample, row, manifest, binding, root, receipts, subset, validator)
                    identity = native_identity(c, sample, row, terminal)
                    if identity is not None:
                        key = (endpoint, identity)
                        require(key not in seen, "Native session reused across logical observations")
                        seen.add(key)
                    entry.update(state=terminal["state"], native_identity=identity,
                        terminal_sha256=c.sha((sample / "terminal.json").read_bytes()), terminal_verified=True,
                        original_strict_native_verified=terminal["state"] in c.SETTLED)
                    if answer is not None:
                        records.append({"request": row, "response": answer, "replay": dict(entry)})
            ledger.append(entry)
            states[endpoint + ":" + entry["state"]] += 1
    return records, ledger, dict(states), jobs


def label_gate(ledger, outers, explicit_release):
    require(explicit_release is True and len(ledger) == 10340
            and len({(e["endpoint"], e["logical_sample_id"]) for e in ledger}) == 10340
            and Counter(e["endpoint"] for e in ledger) == {"sol": 5170, "grok": 5170}
            and all(e.get("terminal_verified") is True and e["state"] not in {"untouched", "started_unresolved"} for e in ledger)
            and set(outers) == {"sol", "grok"} and all(o.get("verified") is True for o in outers.values()),
            "Explicit release plus both own true outers/jobs and all 10340 verified terminals required")


def score_bank(c, planned, admitted, runtime, root, manifest):
    ordered = sorted(planned, key=lambda r: r["batch"])
    expected = [q for r in ordered for q in r["question_ids"]]
    leaves = [v for i in admitted for v in i["response"]["verdicts"]]
    coverage = {"planned_packets": len(planned), "accepted_packets": len(admitted), "expected_leaves": len(expected),
                "observed_leaves": len(leaves), "raw_states": dict(Counter(v["verdict"] for v in leaves))}
    result = {"historical": {"score": None, "state": "incomplete_full_bank_no_scalar"},
              "candidate": {"score": None, "state": "incomplete_full_bank_no_scalar"}, "coverage": coverage}
    if not (len(ordered) == 22 and [r["batch"] for r in ordered] == list(range(1, 23))
            and len(expected) == len(set(expected)) == 170 and len(admitted) == 22 and len(leaves) == 170
            and Counter(v["question_id"] for v in leaves) == Counter(expected)):
        return result
    require(len({i["request"]["request_sha256"] for i in admitted}) == 22
            and {i["request"]["request_sha256"] for i in admitted} == {r["request_sha256"] for r in ordered}
            and all(i["replay"]["original_strict_native_verified"] is True for i in admitted), "Native complete-bank provenance differs")
    row = ordered[0]
    contract = json.loads(c.pinned(root, row["task_contract_path"], manifest["artifacts"][row["task_contract_path"]]))
    core, ladder = runtime["core"], runtime["ladder"]
    compiled = core.compile_bundle(runtime["modules"], runtime["bundle"], task_contract=contract)
    require([q["question"]["id"] for q in core.compiled_questions(compiled)] == expected, "Ordered compiled bank differs")
    try:
        normalized = []
        for item in sorted(admitted, key=lambda i: i["request"]["batch"]):
            r = item["request"]
            _, _, texts, context = c.inputs(root, manifest, r)
            normalized.extend(runtime["runner"]._normalize_batch(item["response"], expected_ids=r["question_ids"],
                artifact_id=r["artifact_id"], bundle_id=r["bundle_id"], judge_id=r["endpoint"], run_id=r["logical_sample_id"],
                artifact_text=texts[r["sources"][0]["id"]], context_texts=[context]))
        reports = ladder.score_bundle(runtime["modules"], runtime["bundle"], normalized, artifact_id=row["artifact_id"],
                                     task_contract=contract, admission_policy="strict_import_v1")
    except ValueError as error:
        for arm in ("historical", "candidate"):
            result[arm] = {"score": None, "state": "strict_import_unadmitted_no_scalar"}
        result["strict_import_error"] = {"class": type(error).__name__, "sha256": sha(str(error).encode())}
        return result
    for arm in ("historical", "candidate"):
        report = reports[arm + "_report"]
        valid = report["status"] == "SCORED" and report["hard_gate_status"] == "VALID"
        result[arm] = {"score": report["final_score"]["observed"] if valid else None, "state": report["status"] if valid else "unusable_gate_or_status",
                       "readiness": runtime["readiness"].decision_readiness(report), "descriptive_bounds": report["final_score"],
                       "report_sha256": ladder.canonical_json_sha256(report)}
    result["provenance"] = {"manifest_sha256": MANIFEST_SHA, "task_contract_sha256": row["task_contract_sha256"],
        "native_replay_sha256": sha(canonical([i["replay"] for i in sorted(admitted, key=lambda i: i["request"]["batch"])])),
        "raw_normalized_sha256": ladder.canonical_json_sha256(normalized), "original_admission_count": 1,
        "new_native_votes": 0, "new_semantic_admissions": 0, "change_count": len(reports["candidate_report"]["ladder_projection"]["changes"])}
    return result


def predictions(c, manifest, selection, records, runtime, root):
    planned, admitted, profiles = defaultdict(list), defaultdict(list), {}
    key = lambda r: (r["endpoint"], r["arm"], r["artifact_id"], r["repeat"])
    for r in manifest["requests"]:
        if r["arm"] != "pairwise":
            planned[key(r)].append(r)
    for item in records:
        if item["request"]["arm"] != "pairwise":
            admitted[key(item["request"])].append(item)
    for identity, rows in planned.items():
        if identity[1] == "hbq":
            bank = score_bank(c, rows, admitted[identity], runtime, root, manifest)
            for arm in ("historical", "candidate"):
                profiles[(identity[0], arm, identity[2], identity[3])] = {**bank[arm], "coverage": bank["coverage"], "provenance": bank.get("provenance")}
        else:
            answer = admitted[identity][0]["response"] if len(admitted[identity]) == 1 else None
            value = None if answer is None or answer["status"] == "CANNOT_ASSESS" else answer["result"]["score" if identity[1] == "holistic" else "overall_score"]
            profiles[identity] = {"score": value, "state": "assessed" if value is not None else "missing_or_abstained"}
    orders = {}
    pairs = {p["pair_id"]: p for p in selection["pairs"]}
    for item in records:
        row, answer = item["request"], item["response"]
        if row["arm"] != "pairwise":
            continue
        winner = answer["winner"]
        if winner in ("TIE", "CANNOT_ASSESS"):
            decision = "TIE" if winner == "TIE" else "ABSTAIN"
        else:
            chosen = next(s["sha256"] for s in row["sources"] if s["side"] == winner)
            require(chosen in pairs[row["pair_id"]]["excerpt_hashes"], "Pair orientation/source differs")
            decision = "LEFT" if chosen == pairs[row["pair_id"]]["excerpt_hashes"][0] else "RIGHT"
        orders[(row["endpoint"], row["pair_id"], row["repeat"], row["orientation"])] = decision
    decisions = {}
    for endpoint in ("sol", "grok"):
        for pair in selection["pairs"]:
            for cycle in (0, 1, 2):
                if cycle and pair["pair_id"] not in selection["pair_sentinel_ids"]:
                    continue
                ab, ba = (orders.get((endpoint, pair["pair_id"], cycle, o)) for o in ("AB", "BA"))
                decisions[(endpoint, "pairwise", pair["pair_id"], cycle)] = ab if ab == ba and ab in DETERMINATE else "ORDER_CONFLICT" if ab in DETERMINATE and ba in DETERMINATE else "MISSING_OR_ABSTAINED"
            for arm in VIEWS[:-1]:
                for cycle in (0, 1, 2):
                    ids = ["mfa-" + h for h in pair["excerpt_hashes"]]
                    values = [profiles.get((endpoint, arm, tid, cycle), {}).get("score") for tid in ids]
                    if cycle and not all((endpoint, arm, tid, cycle) in profiles for tid in ids):
                        continue
                    require(all(v is None or isinstance(v, (int, float)) and math.isfinite(v) for v in values), "Finite native scalar required")
                    decisions[(endpoint, arm, pair["pair_id"], cycle)] = "MISSING_OR_ABSTAINED" if any(v is None for v in values) else "LEFT" if values[0] > values[1] else "RIGHT" if values[0] < values[1] else "TIE"
    return profiles, decisions


def released_ballots(c, selection, source_root, ledger, outers, explicit_release):
    label_gate(ledger, outers, explicit_release)
    require(selection["partition"] == "confirmation" and len(selection["planned_ballots"]) == 3276, "Conditional membership differs")
    metadata = {c.sha(c.canonical(r)): r for r in selection["metadata_rows"]}
    by_pair = {p["pair_id"]: p for p in selection["pairs"]}
    projectors = {}
    for receipt in selection["source_receipts"]:
        raw = c.pinned(source_root, "author-style/" + receipt["path"], receipt)
        require(hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest() == receipt["git_blob_sha1"], "Source Git blob differs")
        projectors[receipt["path"]] = c.prepare.extract.SourceProjection(raw)
    ballots, seen = [], set()
    for planned in selection["planned_ballots"]:
        require(planned["ballot_id"] not in seen and planned["source_field"] == "Preference"
                and c.sha(c.canonical({k: v for k, v in planned.items() if k != "ballot_id"})) == planned["ballot_id"], "Ballot identity differs")
        seen.add(planned["ballot_id"])
        row = metadata[planned["metadata_row_sha256"]]
        require(all(row[k] == planned[k] for k in ("target_hash", "writer_hash", "rater_hash", "panel", "condition", "source_path", "source_position", "target_position", "writer_position")), "Ballot positional membership differs")
        pair = by_pair[planned["pair_id"]]
        require(planned["ballot_id"] in pair["planned_ballot_ids"] and sorted(row["excerpt_hashes"]) == pair["excerpt_hashes"], "Ordered pair membership differs")
        p = projectors[row["source_path"]]
        target, start, _ = p.entries(p.white(0), object_keys=True)[row["target_position"]]
        writer, start, _ = p.entries(start, object_keys=True)[row["writer_position"]]
        require(c.sha(c.canonical(target)) == row["target_hash"] and c.sha(c.canonical(writer)) == row["writer_hash"], "Target/writer identity differs")
        start, _ = p.entries(start, object_keys=False)[row["source_position"]]
        envelope = p.entries(start, object_keys=False)
        require(len(envelope) == (3 if row["panel"] == "expert" else 2), "Rater envelope differs")
        entries = {name: (a, b) for name, a, b in p.entries(envelope[-1][0], object_keys=True)}
        rater = envelope[1] if row["panel"] == "expert" else entries["user"]
        require(c.sha(c.canonical(p.value(*rater))) == row["rater_hash"]
                and c.sha(c.canonical(p.value(*entries["id"]))) == row["judgment_identity_hash"], "Rater/judgment identity differs")
        require("Preference" not in entries or p.text[entries["Preference"][0]] not in "[{", "Preference is not a scalar")
        preference = p.value(*entries["Preference"]) if "Preference" in entries else None
        winner = row["excerpt_hashes"][0 if preference == "Excerpt1" else 1] if preference in ("Excerpt1", "Excerpt2") else None
        ballots.append({**planned, "human_state": "BINARY" if winner is not None else "MISSING" if "Preference" not in entries else "UNKNOWN",
                        "winner": "LEFT" if winner == pair["excerpt_hashes"][0] else "RIGHT" if winner is not None else None})
    require(len(ballots) == len(seen) == 3276, "Full ballot denominator required")
    return ballots


def percentile(values, q):
    ordered = sorted(values)
    x = (len(ordered) - 1) * q
    lo, hi = math.floor(x), math.ceil(x)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (x - lo)


def stratum_inference(ballots, decisions, endpoint, panel, condition, policy):
    bs = [b for b in ballots if b["panel"] == panel and (condition == "POOLED" or b["condition"] == condition)]
    require(bs, "Empty stratum")
    ids = {b["ballot_id"] for b in bs}
    require(len(ids) == len(bs), "Ballot denominator duplicated")
    decision = lambda b, arm: decisions.get((endpoint, arm, b["pair_id"], 0), "MISSING_OR_ABSTAINED")
    correct = lambda b, arm: int(b["human_state"] == "BINARY" and decision(b, arm) == b["winner"])
    targets = sorted({b["target_hash"] for b in bs})
    pair_targets = {(b["pair_id"], b["target_hash"]) for b in bs}
    metrics = {}
    for arm in VIEWS:
        correct_count = sum(correct(b, arm) for b in bs)
        complete_case = [b for b in bs if b["human_state"] == "BINARY" and decision(b, arm) in DETERMINATE]
        complete_case_correct = sum(correct(b, arm) for b in complete_case)
        unknown = sum(b["human_state"] != "BINARY" or decision(b, arm) not in DETERMINATE for b in bs)
        states = Counter(decisions.get((endpoint, arm, pair, 0), "MISSING_OR_ABSTAINED") for pair, _ in pair_targets)
        complete = sum(all(decisions.get((endpoint, arm, p, 0)) in DETERMINATE for p, t in pair_targets if t == target) for target in targets)
        metrics[arm] = {"planned_ballots": len(bs), "correct": correct_count, "all_planned_accuracy": correct_count / len(bs),
            "complete_case_denominator": len(complete_case), "complete_case_correct": complete_case_correct,
            "complete_case_accuracy": complete_case_correct / len(complete_case) if complete_case else None,
            "nonbinary_or_missing_human_ballots": sum(b["human_state"] != "BINARY" for b in bs),
            "nondeterminate_prediction_ballots": sum(decision(b, arm) not in DETERMINATE for b in bs),
            "best_worst_bounds": [correct_count / len(bs), (correct_count + unknown) / len(bs)],
            "planned_pairs": len(pair_targets), "pair_states": dict(states), "directional_coverage": (states["LEFT"] + states["RIGHT"]) / len(pair_targets),
            "complete_targets": complete, "planned_targets": len(targets), "complete_target_fraction": complete / len(targets)}
    sums = {t: (sum(correct(b, "candidate") - correct(b, "historical") for b in bs if b["target_hash"] == t),
                sum(b["target_hash"] == t for b in bs)) for t in targets}
    gain = (metrics["candidate"]["correct"] - metrics["historical"]["correct"]) / len(bs)
    bootstrap = policy["bootstrap"]
    bounds = None
    if len(targets) >= bootstrap["minimum_clusters"]:
        rng, draws = random.Random(bootstrap["seed"]), []
        for _ in range(bootstrap["resamples"]):
            sample = [sums[rng.choice(targets)] for _ in targets]
            draws.append(sum(x[0] for x in sample) / sum(x[1] for x in sample))
        bounds = [percentile(draws, .025), percentile(draws, .975)]
    sensitivity = {}
    sensitivity_pass = True
    for field in ("writer_hash", "rater_hash"):
        leaveouts = []
        for identity in sorted({b[field] for b in bs}):
            kept = [b for b in bs if b[field] != identity]
            gain_count = sum(correct(b, "candidate") - correct(b, "historical") for b in kept)
            contrast = gain_count / len(kept) if kept else None
            guard = bool(kept) and (20 * gain_count >= len(kept) if panel == "expert" else 100 * gain_count >= -3 * len(kept))
            leaveouts.append({"excluded_identity_hash": identity, "retained_ballots": len(kept), "point_gain": contrast, "guard_pass": guard})
        finite = [r["point_gain"] for r in leaveouts if r["point_gain"] is not None]
        passed = bool(leaveouts) and all(r["guard_pass"] for r in leaveouts)
        sensitivity_pass &= passed
        sensitivity[field] = {"leaveouts": leaveouts, "range": [min(finite), max(finite)] if finite else [None, None], "guard_pass": passed,
                              "independent_sample_or_confidence_interval": False}
    coverage = metrics["candidate"]["directional_coverage"] >= metrics["historical"]["directional_coverage"]
    a, b = (metrics[arm]["complete_target_fraction"] for arm in ("historical", "candidate"))
    attrition = max(1 - a, 1 - b) <= policy["attrition"]["maximum_source_target_loss"] + 1e-12 and abs(a - b) <= policy["attrition"]["maximum_arm_difference"] + 1e-12
    base = coverage and attrition and sensitivity_pass and bounds is not None and all(b["human_state"] == "BINARY" for b in bs)
    expert = bool(base and panel == "expert" and 20 * (metrics["candidate"]["correct"] - metrics["historical"]["correct"]) >= len(bs) and bounds[0] > 0)
    lay_ni = bool(base and panel == "lay" and bounds[0] >= -.03)
    lay_improve = bool(lay_ni and gain > 0 and bounds[0] > 0)
    return {"endpoint": endpoint, "panel": panel, "condition": condition, "task": "quality", "fine_variant": "UNKNOWN",
        "metrics": metrics, "human_states": dict(Counter(b["human_state"] for b in bs)), "point_gain": gain,
        "paired_target_cluster_95_percent_interval": bounds, "bootstrap_seed": bootstrap["seed"], "bootstrap_resamples": bootstrap["resamples"] if bounds else 0,
        "coverage_guard": coverage, "attrition_guard": attrition, "crossed_sensitivity": sensitivity,
        "expert_numeric_guard": expert, "lay_noninferiority_numeric_guard": lay_ni, "lay_improvement_numeric_guard": lay_improve,
        "conditional_benchmark_only": True, "fresh_confirmation_claim": False, "candidate_promoted": False}


def diagnostics(profiles, decisions):
    counts, repeats = Counter(), []
    for (endpoint, arm, _, cycle), value in profiles.items():
        counts[f"{endpoint}:{arm}:{cycle}:{value['state']}"] += 1
    for (endpoint, arm, artifact, cycle), value in profiles.items():
        if cycle:
            base = profiles.get((endpoint, arm, artifact, 0), {})
            delta = value["score"] - base["score"] if value["score"] is not None and base.get("score") is not None else None
            repeats.append({"endpoint": endpoint, "arm": arm, "artifact_id": artifact, "repeat": cycle, "native_delta_from_primary": delta})
    return {"profile_states": dict(counts), "registered_sentinel_scalar_repeats": repeats,
            "pair_decision_states": dict(Counter(f"{e}:{a}:{cycle}:{v}" for (e, a, _, cycle), v in decisions.items())),
            "repeat_ballots_added": 0, "readiness_bounds_are_statistical_ci": False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--metadata-only", action="store_true")
    parser.add_argument("--tools-root", type=Path)
    parser.add_argument("--extraction-receipt", type=Path)
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--release-conditional-labels-postprediction", action="store_true")
    parser.add_argument("--sealed-source-root", type=Path)
    for endpoint in ("sol", "grok"):
        parser.add_argument("--" + endpoint + "-results", type=Path)
        parser.add_argument("--" + endpoint + "-outer-terminal", type=Path)
        parser.add_argument("--" + endpoint + "-outer-sha256")
        parser.add_argument("--" + endpoint + "-invocation", type=Path)
        parser.add_argument("--" + endpoint + "-invocation-sha256")
    args = parser.parse_args(argv)
    if args.metadata_only:
        require(all(v is None or v is False for k, v in vars(args).items() if k not in {"manifest", "metadata_only"}), "Metadata mode cannot load source/results/output/runtime")
        print(json.dumps(metadata_view(args.manifest), sort_keys=True))
        return 0
    require(args.tools_root and args.extraction_receipt and args.output_root and args.sol_results and args.grok_results, "Replay inputs and fresh output required")
    require(bool(args.sealed_source_root) == args.release_conditional_labels_postprediction, "Source labels require separate explicit release")
    c, runtime = collector_runtime()
    roots = {e: getattr(args, e + "_results").resolve() for e in ("sol", "grok")}
    protected = [args.manifest.resolve().parent, args.extraction_receipt.resolve().parent, *roots.values()]
    if args.sealed_source_root:
        protected.append(args.sealed_source_root)
    output = c.prepare.extract.private_output(args.output_root, protected)
    manifest, root, subset, validator = c.load_manifest(args.manifest, MANIFEST_SHA, args.tools_root.resolve(), args.extraction_receipt)
    selection = json.loads(c.pinned(root, "selection.json", manifest["artifacts"]["selection.json"]))
    records, ledger, states, jobs = collect_evidence(c, manifest, root, roots, args.tools_root, subset, validator, runtime["receipts"])
    core = runtime["core"]
    runtime["modules"] = core.load_modules(root / "registry/all_modules.yaml")
    runtime["bundle"] = next(b for b in core.load_bundles(root / "bundles/all_bundles.yaml") if b["bundle_id"] == "prose.short_form")
    profiles, decisions = predictions(c, manifest, selection, records, runtime, root)
    report = {"policy": POLICY, "manifest_sha256": MANIFEST_SHA, "analysis_sha256": sha(Path(__file__).read_bytes()),
        "analysis_profile_sha256": sha((HERE / "analysis-profile.json").read_bytes()), "candidate_profile_sha256": profile()["candidate_profile_sha256"],
        "planned_requests": 10340, "planned_ballots": 3276, "terminal_states": states, "accepted_requests": len(records),
        "labels_opened": False, "provider_calls": 0, "candidate_promoted": False, "fresh_confirmation_claim": False,
        "human_alignment_claim": False,
        "unused_data_certified": "UNKNOWN", "fine_variant": "UNKNOWN", "diagnostics": diagnostics(profiles, decisions),
        "qualified_recovery_admitted": False, "physical_contact_cardinality_proven": False}
    outers, ballots = {}, []
    if args.release_conditional_labels_postprediction:
        for endpoint in roots:
            params = [getattr(args, endpoint + suffix) for suffix in ("_outer_terminal", "_outer_sha256", "_invocation", "_invocation_sha256")]
            require(all(params) and endpoint in jobs, "Explicit pinned true outer and invocation required")
            outers[endpoint] = verify_outer(*params, manifest_path=args.manifest, results=roots[endpoint], endpoint=endpoint, binding=jobs[endpoint], c=c)
        ballots = released_ballots(c, selection, args.sealed_source_root, ledger, outers, True)
        strata = [(endpoint, panel, condition) for endpoint in roots for panel in ("expert", "lay") for condition in ("fewshot", "finetuned", "POOLED")]
        inference = [stratum_inference(ballots, decisions, *s, profile()) for s in strata]
        guards = []
        for endpoint in roots:
            for panel in ("expert", "lay"):
                rows = [r for r in inference if r["endpoint"] == endpoint and r["panel"] == panel]
                field = "expert_numeric_guard" if panel == "expert" else "lay_noninferiority_numeric_guard"
                guards.append({"endpoint": endpoint, "panel": panel,
                    "all_reference_conditions_and_pooled_numeric_guard": len(rows) == 3 and all(r[field] for r in rows),
                    "unused_confirmation_eligibility_verified": False, "promotion_authority": False})
        report.update(labels_opened=True, inference=inference, conditional_numeric_guards=guards, outers=outers,
                      reuse_limits="Crossed writer/rater labels do not establish independent humans; leaveouts are sensitivity points, not independent-sample intervals.")
    files = {"implementation/analysis.py": Path(__file__).read_bytes(), "analysis-profile.json": (HERE / "analysis-profile.json").read_bytes(),
        "invocation.json": canonical({k: str(v) if isinstance(v, Path) else v for k, v in vars(args).items()}),
        "private-ledger.json": canonical({"original_requests": ledger, "profiles": [{"identity": list(k), **v} for k, v in profiles.items()],
            "pair_decisions": [{"identity": list(k), "decision": v} for k, v in decisions.items()], "released_ballots": ballots}), "report.json": canonical(report)}
    output.mkdir(parents=True, exist_ok=False)
    for name, raw in files.items():
        c.prepare.extract.write_new(output / name, raw)
    receipt = {"policy": POLICY, "manifest_sha256": MANIFEST_SHA, "artifacts": {n: {"sha256": sha(v), "bytes": len(v)} for n, v in files.items()},
        "labels_opened": report["labels_opened"], "new_votes": 0, "provider_calls": 0, "candidate_promoted": False}
    c.prepare.extract.write_new(output / "receipt.json", canonical(receipt))
    print(json.dumps({"policy": POLICY, "receipt_sha256": sha(canonical(receipt)), "terminal_states": states,
                      "planned_requests": 10340, "labels_opened": report["labels_opened"], "provider_calls": 0, "candidate_promoted": False}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
