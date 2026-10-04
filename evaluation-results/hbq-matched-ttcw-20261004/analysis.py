"""Deterministic, provider-free analysis of the matched TTCW development study.

Default output is a public aggregate on stdout. --output writes only to the
public study tree and refuses an existing file. No private evidence is written.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import importlib.util
from itertools import combinations
import json
import math
from pathlib import Path
import random
import statistics
import sys
from typing import Any, Callable

import prepare
from validate_response import semantic_validate

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
LABEL_SHA = "1916ec27eaa8810a8427ed7000e2aefa3535fd2a33b2ae1d372cccdab3fc6516"
MANIFEST_CONTENT_SHA = "00df72ef1103ae734b79eee4c2bb8589521fcef6bb50860f23c3a27c9c085466"
ARMS = (*prepare.ARM_ORDER, "pairwise")
RANGES = {"hbq": (0, 100), "ttcw14": (0, 1), "holistic": (1, 7), "compact": (1, 5), "oregon": (6, 36)}
BOOTSTRAP_SEED = 20261004


def fraction(numerator: float, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def ranks(values: list[float]) -> list[float]:
    ordered = sorted(range(len(values)), key=values.__getitem__)
    result = [0.0] * len(values)
    start = 0
    while start < len(ordered):
        end = start + 1
        while end < len(ordered) and values[ordered[end]] == values[ordered[start]]:
            end += 1
        mean_rank = (start + 1 + end) / 2
        for position in ordered[start:end]:
            result[position] = mean_rank
        start = end
    return result


def rho(left: list[float], right: list[float]) -> float | None:
    if len(left) != len(right):
        raise ValueError("Correlation inputs must be paired")
    if len(left) < 2:
        return None
    x, y = ranks(left), ranks(right)
    xm, ym = statistics.mean(x), statistics.mean(y)
    denominator = math.sqrt(sum((v - xm) ** 2 for v in x) * sum((v - ym) ** 2 for v in y))
    return sum((a - xm) * (b - ym) for a, b in zip(x, y)) / denominator if denominator else None


def percentile(values: list[float], probability: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    location = probability * (len(ordered) - 1)
    lo, hi = math.floor(location), math.ceil(location)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (location - lo)


def cluster_bootstrap(rows: list[tuple], statistic: Callable[[list[tuple]], float | None],
                      reps: int = 2000, seed: int = BOOTSTRAP_SEED) -> dict[str, Any]:
    """Resample the twelve plot clusters, retaining undefined replicates."""
    if not 1 <= reps <= 2000:
        raise ValueError("Bootstrap repetitions must be between one and 2000")
    groups: dict[int, list[tuple]] = defaultdict(list)
    for row in rows:
        groups[row[0]].append(row)
    if set(groups) != set(range(12)):
        return {"state": "not_estimated", "reason": "All twelve plot clusters must be represented", "represented_clusters": len(groups)}
    rng = random.Random(seed)
    values = []
    undefined = 0
    for _ in range(reps):
        sample = [row for _draw in range(12) for row in groups[rng.randrange(12)]]
        value = statistic(sample)
        if value is None or not math.isfinite(value):
            undefined += 1
        else:
            values.append(value)
    return {"state": "estimated" if values else "undefined", "plot_clusters": 12, "seed": seed,
            "replicates": reps, "defined_replicates": len(values), "undefined_replicates": undefined,
            "redraw_undefined": False, "percentile_95": [percentile(values, .025), percentile(values, .975)]}


def bounded_agreement(matches: float, assessed: int, expected: int) -> dict[str, Any]:
    if not 0 <= matches <= assessed <= expected:
        raise ValueError("Agreement denominator differs")
    missing = expected - assessed
    return {"matches": matches, "assessed_denominator": assessed, "expected_denominator": expected,
            "fraction": fraction(matches, assessed), "unassessed": missing,
            "full_denominator_bounds": [fraction(matches, expected), fraction(matches + missing, expected)],
            "state": "undefined_no_informative_denominator" if not expected else
                     "inconclusive_missing_over_10_percent" if missing > .1 * expected else "descriptive_development"}


def distribution(scores: dict[str, float], arm: str) -> dict[str, Any]:
    values = list(scores.values())
    counts = Counter(values)
    low, high = RANGES[arm]
    return {"n": len(values), "minimum": min(values) if values else None, "maximum": max(values) if values else None,
            "mean": statistics.mean(values) if values else None, "distinct_scores": len(counts),
            "tied_score_groups": sum(n > 1 for n in counts.values()), "items_in_ties": sum(n for n in counts.values() if n > 1),
            "tied_unordered_pairs": sum(n * (n - 1) // 2 for n in counts.values()),
            "native_range": [low, high], "floor_count": counts[low], "ceiling_count": counts[high],
            **({"at_or_below_10": sum(v <= 10 for v in values), "at_or_above_90": sum(v >= 90 for v in values)} if arm == "hbq" else {})}


def association(scores: dict[str, float], targets: dict[str, float], groups: dict[str, int], reps: int) -> dict[str, Any]:
    ids = sorted(set(scores) & set(targets))
    rows = [(groups[sid], scores[sid], targets[sid]) for sid in ids]
    estimate = rho([row[1] for row in rows], [row[2] for row in rows])
    complete_enough = len(ids) >= 33
    return {"rho": estimate, "works": len(ids), "expected_works": 36, "missing_works": 36 - len(ids),
            "state": "descriptive_development" if complete_enough else "inconclusive_missing_over_10_percent",
            "undefined_reason": "Too few paired works or a constant rank vector" if estimate is None else None,
            "unobserved_outcome_bounds": [-1, 1] if len(ids) < 36 else None,
            "bootstrap": cluster_bootstrap(rows, lambda rs: rho([r[1] for r in rs], [r[2] for r in rs]), reps)
                         if complete_enough else {"state": "not_estimated", "reason": "Incomplete cohort; missing over ten percent"}}


def direction(value: float) -> int:
    return (value > 0) - (value < 0)


def within_plot(scores: dict[str, float], targets: dict[str, float], pairs: list[dict], reps: int) -> dict[str, Any]:
    expert_ties = 0
    rows, matched, predicted_ties = [], 0.0, 0
    informative = 0
    for pair in pairs:
        left, right = pair["left"], pair["right"]
        target_direction = direction(targets[left] - targets[right])
        if not target_direction:
            expert_ties += 1
            continue
        informative += 1
        if left not in scores or right not in scores:
            continue
        predicted = direction(scores[left] - scores[right])
        credit = .5 if predicted == 0 else float(predicted == target_direction)
        matched += credit
        predicted_ties += predicted == 0
        rows.append((pair["plot"], credit))
    result = bounded_agreement(matched, len(rows), informative)
    result.update(expert_ties_excluded=expert_ties, unordered_pairs=len(pairs), predicted_ties=predicted_ties,
                  bootstrap=cluster_bootstrap(rows, lambda rs: statistics.mean(r[1] for r in rs), reps)
                  if result["state"] == "descriptive_development" else {"state": "not_estimated", "reason": "Incomplete informative pairs"})
    return result


def load_labels(path: Path, manifest: dict) -> tuple[dict[str, float], dict[str, dict[int, list[str]]]]:
    raw = prepare.checked(path, LABEL_SHA)
    labels = json.loads(raw)
    stories = {s["id"]: s for s in manifest["stories"]}
    if not isinstance(labels, list) or len(labels) != 36:
        raise ValueError("Exactly thirty-six opened development label records required")
    targets, ballots = {}, {}
    for row in labels:
        sid = row["pass_id"].rsplit("/", 1)[-1]
        if sid not in stories or sid in targets or row["plot_group"] != stories[sid]["plot"]:
            raise ValueError("Expert story/plot identity differs")
        if [test["ttcw_idx"] for test in row["tests"]] != list(range(1, 15)):
            raise ValueError("Expert test identity/order differs")
        tests = {test["ttcw_idx"]: test["verdicts"] for test in row["tests"]}
        if any(len(v) != 3 or any(x not in {"YES", "NO"} for x in v) for v in tests.values()):
            raise ValueError("Exactly three binary expert ballots per test required")
        targets[sid] = sum(v.count("YES") for v in tests.values()) / 42
        ballots[sid] = tests
    return targets, ballots


def load_manifest(path: Path) -> tuple[dict, str]:
    raw = path.read_bytes()
    manifest = json.loads(raw)
    body = {k: v for k, v in manifest.items() if k != "manifest_content_sha256"}
    if (prepare.digest(prepare.canonical(body)) != manifest.get("manifest_content_sha256")
            or manifest["manifest_content_sha256"] != MANIFEST_CONTENT_SHA):
        raise ValueError("Frozen matched manifest content differs")
    return manifest, prepare.digest(raw)


def load_hbq(manifest: dict) -> dict[str, Any]:
    sys.path.insert(0, str(REPO / "src"))
    from hbqrs import core, runner, scoring_v2
    modules = core.load_modules(REPO / "registry/all_modules.json")
    bundle = core.resolve_bundle(core.load_bundles(REPO / "bundles/all_bundles.json"), "prose.short_story")
    compiled = core.compile_bundle(modules, bundle)
    questions = sorted(core.compiled_questions(compiled), key=lambda q: {"hard_gate": 0, "domain": 1, "penalty": 2, "supplemental": 3}[q["role"]])
    expected = manifest["runtime"]
    if (len(questions) != 178 or [q["question"]["id"] for q in questions] != expected["question_ids"]
            or prepare.digest(runner._json_bytes(compiled)) != expected["compiled_bundle_sha256"]
            or prepare.digest(runner._json_bytes(runner._question_payload(questions))) != expected["question_payload_sha256"]):
        raise ValueError("Canonical HBQ compiled/payload commitments differ")
    return {"core": core, "runner": runner, "strict": scoring_v2, "modules": modules, "bundle": bundle, "questions": questions,
            "provenance": {"condition": "new_native_collection_sealed_core_v1_with_strict_import_v1",
                "compiled_bundle_sha256": expected["compiled_bundle_sha256"], "question_payload_sha256": expected["question_payload_sha256"],
                "source_sha256": {name: prepare.digest((REPO / name).read_bytes()) for name in (
                    "src/hbqrs/core.py", "src/hbqrs/runner.py", "src/hbqrs/scoring_v2.py", "registry/all_modules.json", "bundles/all_bundles.json")},
                "role_counts": dict(Counter(q["role"] for q in questions)), "report_version": 1}}


def validate_continuation(derived: dict, base: dict, endpoint: str, *, base_raw: bytes | None = None,
                          derived_root: Path | None = None) -> set[str]:
    body = {k: v for k, v in derived.items() if k != "manifest_content_sha256"}
    if prepare.digest(prepare.canonical(body)) != derived.get("manifest_content_sha256"):
        raise ValueError("Continuation manifest content hash differs")
    for key in ("study_id", "source_pins", "runtime", "context", "implementation", "public_asset_hashes",
                "stories", "sentinels", "pairs", "repeat_pair_ids"):
        if derived.get(key) != base.get(key):
            raise ValueError("Continuation changes a frozen scientific condition")
    original_artifacts = base["artifacts"]
    derived_artifacts = derived["artifacts"]
    if any(derived_artifacts.get(path) != pin for path, pin in original_artifacts.items()):
        raise ValueError("Continuation changes or omits an original artifact pin")
    added_artifacts = set(derived_artifacts) - set(original_artifacts)
    if added_artifacts:
        lineage_path = "lineage/parent-manifest.json"
        if added_artifacts != {lineage_path}:
            raise ValueError("Continuation has an unsupported added artifact")
        if base_raw is None or derived_root is None or json.loads(base_raw) != base:
            raise ValueError("Continuation parent lineage requires exact original manifest bytes")
        parent_sha = prepare.digest(base_raw)
        if (derived_artifacts[lineage_path] != {"sha256": parent_sha, "bytes": len(base_raw)}
                or derived.get("continuation", {}).get("parent_manifest_sha256") != parent_sha):
            raise ValueError("Continuation parent lineage commitment differs")
        if prepare.checked(derived_root / lineage_path, parent_sha, len(base_raw)) != base_raw:
            raise ValueError("Continuation parent lineage bytes differ")
    originals = {r["logical_sample_id"]: r for r in base["requests"] if r["endpoint"] == endpoint}
    selected = set()
    for request in derived["requests"]:
        sid = request["logical_sample_id"]
        if request["endpoint"] != endpoint:
            continue
        if sid in selected or originals.get(sid) != request:
            raise ValueError("Continuation request duplicates or changes original descriptor")
        selected.add(sid)
    if not selected:
        raise ValueError("Continuation has no exact original requests for endpoint")
    return selected


def join_results(parts: list[tuple[dict, dict]], expected_ids: set[str]) -> tuple[dict, dict]:
    """Disjoint attempts only; ambiguous attempts are never replaced silently."""
    accepted, attempted = {}, set()
    joined_statuses = {sid: "not_collected" for sid in expected_ids}
    for admitted, inventory in parts:
        occupied = {sid for sid, status in inventory["statuses"].items() if status != "not_collected"}
        if not occupied <= expected_ids or attempted & occupied:
            raise ValueError("Duplicate attempted logical samples require explicit owner-reviewed repair lineage")
        attempted.update(occupied)
        joined_statuses.update({sid: inventory["statuses"][sid] for sid in occupied})
        accepted.update(admitted)
    public = {"scheduled": len(expected_ids), "statuses": dict(Counter(joined_statuses.values())),
              "native_accepted_requests": len(accepted), "jobs": [inv["public"] for _accepted, inv in parts],
              "attempt_overlap_policy": "Reject duplicate actual attempts; no implicit ambiguity repair or vote replacement"}
    return accepted, public


def load_endpoint(root: Path, endpoint: str, manifest: dict, manifest_sha: str, input_root: Path, subset: Any,
                  selected_ids: set[str] | None = None) -> tuple[dict, dict]:
    rows = [r for r in manifest["requests"] if r["endpoint"] == endpoint]
    if selected_ids is not None:
        rows = [r for r in rows if r["logical_sample_id"] in selected_ids]
    statuses: dict[str, str] = {}
    accepted = {}
    commitments = []
    job_path = root / "job.json"
    job = json.loads(job_path.read_bytes()) if job_path.exists() else None
    if job is not None and (job.get("manifest_sha256") != manifest_sha or job.get("endpoint") != endpoint):
        raise ValueError("Endpoint job does not bind frozen manifest")
    context = prepare.checked(input_root / manifest["context"]["path"], manifest["context"]["sha256"]).decode("utf-8")
    texts: dict[str, str] = {}
    for row in rows:
        sid = row["logical_sample_id"]
        sample = root / f"{row['endpoint_ordinal']:04d}-{sid[:12]}"
        terminal_path = sample / "terminal.json"
        if not sample.exists():
            statuses[sid] = "not_collected"
            continue
        if not terminal_path.exists():
            statuses[sid] = "in_progress_or_unresolved"
            continue
        try:
            terminal = json.loads(terminal_path.read_bytes())
        except (OSError, ValueError):
            statuses[sid] = "in_progress_or_unreadable_terminal"
            continue
        if terminal.get("state") != "accepted" or terminal.get("accepted") is not True:
            statuses[sid] = "terminal_unadmitted"
            continue
        if job is None:
            statuses[sid] = "missing_job_binding_unadmitted"
            continue
        try:
            if json.loads((sample / "condition.json").read_bytes()) != row:
                raise ValueError("condition")
            raw = {name: prepare.checked(sample / f"{name}.json", terminal[f"{name.replace('-', '_')}_sha256"])
                   for name in ("response", "acceptance", "native-result")}
        except (OSError, ValueError, KeyError):
            statuses[sid] = "integrity_unadmitted"
            continue
        answer, original_acceptance = json.loads(raw["response"]), json.loads(raw["acceptance"])
        schema = json.loads(prepare.checked(input_root / row["schema_path"], row["schema_sha256"]))
        for source in row["sources"]:
            if source["id"] not in texts:
                texts[source["id"]] = prepare.checked(input_root / source["input_path"], source["sha256"]).decode("utf-8")
        admission = semantic_validate(row["arm"], answer, row, texts, subset, context=context, schema=schema)
        if original_acceptance.get("accepted") is not True or admission != original_acceptance:
            statuses[sid] = "semantic_replay_unadmitted"
            continue
        statuses[sid] = "accepted"
        accepted[sid] = {"request": row, "response": answer, "abstention": admission["abstention"],
                         "source_text": texts[row["sources"][0]["id"]], "context_text": context}
        commitments.append({"request_sha256": row["request_sha256"], "terminal_sha256": prepare.digest(terminal_path.read_bytes()),
                            **{name + "_sha256": prepare.digest(value) for name, value in raw.items()}})
    public_binding = None if job is None else {k: job[k] for k in (
        "endpoint", "model", "destination", "reasoning", "sampler", "workers", "collector_sha256", "validator_sha256",
        "runner_sha256", "receipt_reader_sha256", "zero_charge_only", "automatic_retries") if k in job}
    if job is not None and isinstance(job.get("route"), dict):
        public_binding["route_timeout_seconds"] = job["route"].get("timeout_seconds")
    inventory = {"scheduled": len(rows), "statuses": dict(Counter(statuses.values())), "native_accepted_requests": len(accepted),
                 "accepted_request_commitment_sha256": prepare.digest(prepare.canonical(sorted(commitments, key=lambda x: x["request_sha256"]))),
                 "job_sha256": prepare.digest(job_path.read_bytes()) if job is not None else None,
                 "result_manifest_sha256": manifest_sha, "condition": "original" if selected_ids is None else "exact-request continuation",
                 "binding": public_binding,
                 "proof_scope": "Collector terminal hash bindings and frozen semantic replay; independent provider-native receipt re-audit is not performed"}
    return accepted, {"statuses": statuses, "public": inventory}


def score_story(arm: str, records: list[dict], hbq: dict) -> dict[str, Any]:
    if arm == "hbq":
        leaves = [v for record in records for v in record["response"]["verdicts"]]
        states = Counter(v["verdict"] for v in leaves)
        counts = {"native_leaves": len(leaves), "expected_leaves": 178, "states": dict(states),
                  "applicable": len(leaves) - states["NOT_APPLICABLE"], "assessed_binary": states["YES"] + states["NO"]}
        counts["assessed_over_applicable"] = fraction(counts["assessed_binary"], counts["applicable"])
        if len(records) != 23 or len(leaves) != 178 or {v["question_id"] for v in leaves} != set(q["question"]["id"] for q in hbq["questions"]):
            return {"score": None, "state": "incomplete_native_packets_no_score", "coverage": counts, "leaves": leaves}
        artifact = records[0]["request"]["artifact_id"]
        try:
            normalized = [leaf for record in sorted(records, key=lambda r: r["request"]["batch"])
                          for leaf in hbq["runner"]._normalize_batch(
                              record["response"], expected_ids=record["request"]["question_ids"],
                              artifact_id=artifact, bundle_id="prose.short_story",
                              judge_id=record["request"]["endpoint"], run_id=record["request"]["logical_sample_id"],
                              artifact_text=record.get("source_text", ""), context_texts=[record.get("context_text", "")])]
            hbq["strict"].validate_import_admission(hbq["modules"], hbq["bundle"], normalized,
                                                    artifact_id=artifact, admission_policy="strict_import_v1")
            report = hbq["core"].score_bundle(hbq["modules"], hbq["bundle"], normalized, artifact_id=artifact)
        except ValueError:
            return {"score": None, "state": "strict_import_unadmitted", "coverage": counts, "leaves": leaves}
        score = report["final_score"]["observed"] if report["status"] == "SCORED" else None
        return {"score": score, "state": report["status"], "coverage": counts, "weighted_coverage": report["coverage"],
                "uncertainty_bounds": report["final_score"], "issue_count": len(report["issues"]), "leaves": leaves}
    if not records:
        return {"score": None, "state": "not_admitted", "coverage": {"applicable": 14 if arm == "ttcw14" else 1, "assessed_binary": 0}}
    response = records[0]["response"]
    if arm == "ttcw14":
        rows = response["verdicts"]
        assessed = sum(r["verdict"] in {"YES", "NO"} for r in rows)
        return {"score": sum(r["verdict"] == "YES" for r in rows) / 14 if assessed == 14 else None,
                "state": "assessed" if assessed == 14 else "partial_abstention_no_complete_score",
                "coverage": {"applicable": 14, "assessed_binary": assessed, "cannot_assess": 14 - assessed,
                             "assessed_over_applicable": assessed / 14}, "leaves": rows}
    if response["status"] == "CANNOT_ASSESS":
        return {"score": None, "state": "explicit_abstention", "coverage": {"applicable": 1, "assessed_binary": 0}}
    field = {"holistic": "score", "compact": "overall_score", "oregon": "total_score"}[arm]
    return {"score": response["result"][field], "state": "assessed", "coverage": {"applicable": 1, "assessed_binary": 1}}


def ttcw_agreement(story_records: dict[str, dict], ballots: dict, groups: dict, reps: int) -> dict[str, Any]:
    majority_matches = individual_matches = assessed = 0
    by_test = {i: {"majority_matches": 0, "individual_matches": 0, "assessed": 0} for i in range(1, 15)}
    cluster_rows = []
    for sid, record in story_records.items():
        for leaf in record.get("leaves", []):
            if leaf["verdict"] not in {"YES", "NO"}:
                continue
            index = int(leaf["test_id"].split("-")[-1])
            human = ballots[sid][index]
            majority = "YES" if human.count("YES") >= 2 else "NO"
            match = int(leaf["verdict"] == majority)
            individual = human.count(leaf["verdict"])
            majority_matches += match
            individual_matches += individual
            assessed += 1
            by_test[index]["majority_matches"] += match
            by_test[index]["individual_matches"] += individual
            by_test[index]["assessed"] += 1
            cluster_rows.append((groups[sid], match, individual / 3))
    result = {"expert_majority": bounded_agreement(majority_matches, assessed, 504),
              "individual_ballots": bounded_agreement(individual_matches, assessed * 3, 1512),
              "by_test": {str(i): {"majority": bounded_agreement(v["majority_matches"], v["assessed"], 36),
                                    "individual_ballots": bounded_agreement(v["individual_matches"], v["assessed"] * 3, 108)}
                          for i, v in by_test.items()}}
    for key, column in (("expert_majority", 1), ("individual_ballots", 2)):
        result[key]["bootstrap"] = cluster_bootstrap(cluster_rows, lambda rs, col=column: statistics.mean(r[col] for r in rs), reps) \
            if assessed >= .9 * 504 else {"state": "not_estimated", "reason": "Incomplete assessed test/story cells"}
    return result


def repeat_summary(arm: str, profiles: dict[tuple[str, int], dict], sentinel_ids: set[str]) -> dict[str, Any]:
    comparisons = []
    triples = 0
    rank_results = {}
    for sid in sentinel_ids:
        values = [profiles.get((sid, cycle), {}).get("score") for cycle in range(3)]
        triples += all(v is not None for v in values)
        for cycle in (1, 2):
            if values[0] is not None and values[cycle] is not None:
                comparisons.append((values[0], values[cycle]))
    for left_cycle, right_cycle in combinations(range(3), 2):
        matched = sorted(sid for sid in sentinel_ids if profiles.get((sid, left_cycle), {}).get("score") is not None
                         and profiles.get((sid, right_cycle), {}).get("score") is not None)
        left = [profiles[(sid, left_cycle)]["score"] for sid in matched]
        right = [profiles[(sid, right_cycle)]["score"] for sid in matched]
        lr, rr = ranks(left), ranks(right)
        rank_results[f"{left_cycle}_vs_{right_cycle}"] = {
            "paired_works": len(matched), "expected_works": 9, "rho": rho(left, right),
            "mean_absolute_rank_change": statistics.mean(abs(a - b) for a, b in zip(lr, rr)) if matched else None}
    result = {"sentinel_works": 9, "complete_three_sample_works": triples,
              "initial_vs_repeat_exact_score_agreement": bounded_agreement(sum(a == b for a, b in comparisons), len(comparisons), 18),
              "mean_absolute_score_change": statistics.mean(abs(a - b) for a, b in comparisons) if comparisons else None,
              "rank_instability": rank_results, "independent_work_count_added": 0}
    if arm in {"hbq", "ttcw14"}:
        raw_matches = raw_count = binary_matches = binary_count = activation_flips = 0
        field = "question_id" if arm == "hbq" else "test_id"
        for sid in sentinel_ids:
            initial = {r[field]: r["verdict"] for r in profiles.get((sid, 0), {}).get("leaves", [])}
            for cycle in (1, 2):
                repeated = {r[field]: r["verdict"] for r in profiles.get((sid, cycle), {}).get("leaves", [])}
                for qid in set(initial) & set(repeated):
                    left, right = initial[qid], repeated[qid]
                    raw_count += 1
                    raw_matches += left == right
                    activation_flips += (left == "NOT_APPLICABLE") != (right == "NOT_APPLICABLE")
                    if left in {"YES", "NO"} and right in {"YES", "NO"}:
                        binary_count += 1
                        binary_matches += left == right
        expected = 9 * 2 * (178 if arm == "hbq" else 14)
        result.update(raw_state_agreement_includes_NA_CA=bounded_agreement(raw_matches, raw_count, expected),
                      assessed_binary_agreement=bounded_agreement(binary_matches, binary_count, expected),
                      not_applicable_activation_flips=activation_flips)
    return result


def pairwise_analysis(accepted: dict, manifest: dict, targets: dict, reps: int) -> dict[str, Any]:
    decisions = {}
    abstentions = 0
    for record in accepted.values():
        row, answer = record["request"], record["response"]
        if row["arm"] != "pairwise":
            continue
        winner = answer["winner"]
        if winner == "CANNOT_ASSESS":
            abstentions += 1
            continue
        value = .5 if winner == "TIE" else float(winner == "A")
        decisions[(row["pair_id"], row["repeat"], row["orientation"])] = 1 - value if row["orientation"] else value
    consensus, order_gaps = {}, []
    direct_matches = direct_assessed = informative_orders = expert_ties = 0
    for pair in manifest["pairs"]:
        target = direction(targets[pair["left"]] - targets[pair["right"]])
        if not target:
            expert_ties += 1
        else:
            informative_orders += 2
        values = [decisions.get((pair["id"], 0, orientation)) for orientation in (0, 1)]
        if all(v is not None for v in values):
            consensus[pair["id"]] = statistics.mean(values)
            order_gaps.append(abs(values[0] - values[1]))
        if target:
            for value in values:
                if value is not None:
                    direct_assessed += 1
                    direct_matches += .5 if value == .5 else direction(value - .5) == target
    rows, matches, ties, informative = [], 0.0, 0, len(manifest["pairs"]) - expert_ties
    for pair in manifest["pairs"]:
        target = direction(targets[pair["left"]] - targets[pair["right"]])
        if not target or pair["id"] not in consensus:
            continue
        prediction = direction(consensus[pair["id"]] - .5)
        credit = .5 if not prediction else float(prediction == target)
        matches += credit
        ties += not prediction
        rows.append((pair["plot"], credit))
    agreement = bounded_agreement(matches, len(rows), informative)
    agreement.update(expert_ties_excluded=expert_ties, consensus_ties=ties)
    agreement["bootstrap"] = cluster_bootstrap(rows, lambda rs: statistics.mean(r[1] for r in rs), reps) \
        if agreement["state"] == "descriptive_development" else {"state": "not_estimated", "reason": "Incomplete informative pairs"}
    repeated = []
    for pair_id in manifest["repeat_pair_ids"]:
        for cycle in (1, 2):
            for orientation in (0, 1):
                left, right = decisions.get((pair_id, 0, orientation)), decisions.get((pair_id, cycle, orientation))
                if left is not None and right is not None:
                    repeated.append(left == right)
    return {"state": "inconclusive_missing_over_10_percent" if len(consensus) < 33 else "descriptive_development",
            "unordered_pairs": 36, "initial_assessed_orders": sum(k[1] == 0 for k in decisions),
            "initial_expected_orders": 72, "all_collection_explicit_abstentions": abstentions,
            "paired_order_complete_pairs": len(order_gaps), "paired_order_disagreements": sum(gap != 0 for gap in order_gaps),
            "paired_order_opposite_direction_pairs": sum(gap == 1 for gap in order_gaps),
            "mean_absolute_canonical_order_gap": statistics.mean(order_gaps) if order_gaps else None,
            "each_order_against_expert": bounded_agreement(direct_matches, direct_assessed, informative_orders),
            "order_averaged_within_plot_agreement": agreement,
            "repeat_same_order_agreement": bounded_agreement(sum(repeated), len(repeated), 24),
            "global_rho": None, "global_rho_reason": "Twelve disconnected three-story graphs; no global rank inference"}


def analyze(manifest: dict, targets: dict, ballots: dict, endpoints: dict, hbq: dict, reps: int = 2000) -> dict:
    groups = {s["id"]: s["plot"] for s in manifest["stories"]}
    sentinel_ids = {s["id"] for s in manifest["sentinels"]}
    result = {}
    for endpoint, accepted in endpoints.items():
        by_condition: dict[tuple, list] = defaultdict(list)
        for record in accepted.values():
            row = record["request"]
            if row["arm"] != "pairwise":
                by_condition[(row["arm"], row["story_id"], row["repeat"])].append(record)
        arms, scores_by_arm = {}, {}
        for arm in prepare.ARM_ORDER:
            profiles = {}
            for story in manifest["stories"]:
                for cycle in range(3 if story["id"] in sentinel_ids else 1):
                    key = (story["id"], cycle)
                    profiles[key] = score_story(arm, by_condition.get((arm, *key), []), hbq)
            initial = {sid: profile for (sid, cycle), profile in profiles.items() if cycle == 0}
            scores = {sid: record["score"] for sid, record in initial.items() if record["score"] is not None}
            scores_by_arm[arm] = scores
            native_states = Counter()
            for record in initial.values():
                native_states.update(record.get("coverage", {}).get("states", {}))
            value = {"story_score_association": association(scores, targets, groups, reps),
                     "within_plot_pair_agreement": within_plot(scores, targets, manifest["pairs"], reps),
                     "score_distribution": distribution(scores, arm), "initial_states": dict(Counter(r["state"] for r in initial.values())),
                     "initial_assessed_story_scores": len(scores), "expected_story_scores": 36,
                     "repeatability": repeat_summary(arm, profiles, sentinel_ids)}
            initial_scheduled = sum(r["endpoint"] == endpoint and r["arm"] == arm and r["repeat"] == 0 for r in manifest["requests"])
            initial_admitted = [r for r in accepted.values() if r["request"]["arm"] == arm and r["request"]["repeat"] == 0]
            value["request_coverage"] = {"initial_scheduled": initial_scheduled, "initial_native_admitted": len(initial_admitted),
                                         "initial_unadmitted_or_missing": initial_scheduled - len(initial_admitted),
                                         "initial_schema_accepted_any_abstention": sum(r["abstention"] for r in initial_admitted)}
            if arm == "hbq":
                counts = {key: sum(r["coverage"].get(key, 0) for r in initial.values())
                          for key in ("native_leaves", "applicable", "assessed_binary")}
                counts.update(expected_native_leaves=6408, uncollected_native_leaves=6408 - counts["native_leaves"],
                              native_states=dict(native_states), assessed_over_received_applicable=fraction(counts["assessed_binary"], counts["applicable"]))
                full = [r for r in initial.values() if r["state"] not in {"incomplete_native_packets_no_score", "strict_import_unadmitted"}]
                value.update(canonical_scope={"questions": 178, "packets": 23, "scoring_ready_stories": len(full),
                                             "hard_gates": 0, "partial_story_scoring": False}, initial_leaf_coverage=counts,
                             scoring_provenance=hbq["provenance"],
                             complete_native_weighted_coverage_range=[min(r["weighted_coverage"] for r in full), max(r["weighted_coverage"] for r in full)] if full else None,
                             complete_native_mean_score_bounds={bound: {
                                 "mean": statistics.mean(values) if (values := [r["uncertainty_bounds"][bound] for r in full
                                                                               if r["uncertainty_bounds"][bound] is not None]) else None,
                                 "stories_with_bound": len(values)} for bound in ("lower", "observed", "upper")} if full else None,
                             scorer_issue_count=sum(r.get("issue_count", 0) for r in full))
            elif arm == "ttcw14":
                assessed = sum(r["coverage"]["assessed_binary"] for r in initial.values())
                received = sum(len(r.get("leaves", [])) for r in initial.values())
                value.update(initial_test_coverage={"assessed": assessed, "expected": 504,
                                                    "received_native_tests": received, "native_cannot_assess": received - assessed,
                                                    "uncollected_test_positions": 504 - received,
                                                    "unassessed": 504 - assessed, "fraction": assessed / 504},
                             expert_agreement=ttcw_agreement(initial, ballots, groups, reps))
            arms[arm] = value
        paired = {}
        for left, right in combinations(prepare.ARM_ORDER, 2):
            shared = sorted(set(scores_by_arm[left]) & set(scores_by_arm[right]))
            rows = [(groups[sid], scores_by_arm[left][sid], scores_by_arm[right][sid], targets[sid]) for sid in shared]
            statistic = lambda rs: None if (a := rho([r[1] for r in rs], [r[3] for r in rs])) is None or (b := rho([r[2] for r in rs], [r[3] for r in rs])) is None else a - b
            paired[f"{left}_minus_{right}"] = {"shared_works": len(shared), "expected_works": 36,
                "delta_rho": statistic(rows), "state": "descriptive_development" if len(shared) >= 33 else "inconclusive_missing_over_10_percent",
                "unobserved_delta_bounds": [-2, 2] if len(shared) < 36 else None,
                "bootstrap": cluster_bootstrap(rows, statistic, reps) if len(shared) >= 33 else {"state": "not_estimated", "reason": "Incomplete shared denominator"}}
        arms["pairwise"] = pairwise_analysis(accepted, manifest, targets, reps)
        result[endpoint] = {"arms": arms, "paired_scalar_associations": paired}
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--grok-results", type=Path, required=True)
    parser.add_argument("--sol-results", type=Path, required=True)
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--continuation", action="append", default=[], metavar="ENDPOINT=RESULT_ROOT=DERIVED_MANIFEST",
                        help="Exact-descriptor continuation; repeat for disjoint source jobs")
    parser.add_argument("--bootstrap-reps", type=int, default=2000)
    parser.add_argument("--output", type=Path, help="Fresh public aggregate file inside this study tree; default stdout")
    args = parser.parse_args()
    if not 1 <= args.bootstrap_reps <= 2000:
        parser.error("Use one to 2000 finite bootstrap repetitions")
    if args.output is not None and (not args.output.resolve().is_relative_to(HERE) or args.output.exists()):
        parser.error("Output must be a fresh public file inside the study tree")
    manifest, manifest_sha = load_manifest(args.manifest)
    targets, ballots = load_labels(args.labels, manifest)
    subset_path = Path.home() / ".codex/tools/model_work_queue/adapters/json_schema_subset.py"
    subset = prepare.load_subset(subset_path)
    for path, expected in ((HERE / "validate_response.py", manifest["implementation"]["semantic_validator_sha256"]),
                           (subset_path, manifest["implementation"]["schema_subset_sha256"])):
        prepare.checked(path, expected)
    hbq = load_hbq(manifest)
    endpoints, inventory, continuation_parts = {}, {}, defaultdict(list)
    for specification in args.continuation:
        parts = specification.split("=", 2)
        if len(parts) != 3 or parts[0] not in prepare.ENDPOINTS:
            parser.error("Continuation must be grok|sol=RESULT_ROOT=DERIVED_MANIFEST")
        endpoint, result_root, derived_path = parts
        raw_derived = Path(derived_path).read_bytes()
        derived = json.loads(raw_derived)
        selected = validate_continuation(derived, manifest, endpoint, base_raw=args.manifest.read_bytes(),
                                         derived_root=Path(derived_path).resolve().parent)
        continuation_parts[endpoint].append((Path(result_root), prepare.digest(raw_derived), selected))
    for endpoint, root in (("grok", args.grok_results), ("sol", args.sol_results)):
        parts = [load_endpoint(root, endpoint, manifest, manifest_sha, args.manifest.parent, subset)]
        for result_root, result_manifest_sha, selected in continuation_parts[endpoint]:
            parts.append(load_endpoint(result_root, endpoint, manifest, result_manifest_sha, args.manifest.parent, subset, selected))
        expected_ids = {r["logical_sample_id"] for r in manifest["requests"] if r["endpoint"] == endpoint}
        endpoints[endpoint], inventory[endpoint] = join_results(parts, expected_ids)
    summary = {"schema_version": 1, "study_id": manifest["study_id"], "evidence_class": "opened_development_baseline_comparator_analysis",
        "promotion_authority": False, "provider_calls_made": 0, "new_human_labels": 0,
        "cohort": {"works": 36, "plot_clusters": 12, "expert_test_story_cells": 504, "individual_expert_ballots": 1512,
                   "independent_works_added_by_repeats": 0},
        "provenance": {"manifest_sha256": manifest_sha, "manifest_content_sha256": manifest["manifest_content_sha256"],
                       "source_pins": manifest["source_pins"], "development_labels_sha256": LABEL_SHA,
                       "analysis_sha256": prepare.digest(Path(__file__).read_bytes()),
                       "config": {"bootstrap_reps": args.bootstrap_reps, "seed": BOOTSTRAP_SEED,
                                  "missing_over_10_percent": "inconclusive", "score_samples": "initial only",
                                  "pair_consensus": "mean of two assessed canonical-order decisions; threshold at0.5"}},
        "native_inventory": inventory,
        "endpoints": analyze(manifest, targets, ballots, endpoints, hbq, args.bootstrap_reps),
        "limits": ["Opened development evidence; no untouched confirmation or candidate promotion.",
                   "Individual ballots and repeats do not enlarge the work sample.",
                   "Missing, invalid and abstaining responses are unassessed, never NO or ties.",
                   "No global pairwise rho from disconnected plot graphs.",
                   "Public aggregate contains no story prose, per-story scores, individual labels or rater IDs."]}
    raw = (json.dumps(summary, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")
    if args.output is not None:
        with args.output.open("xb") as stream:
            stream.write(raw)
        print(json.dumps({"public_summary_sha256": prepare.digest(raw), "provider_calls_made": 0}))
    else:
        print(raw.decode("utf-8"), end="")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError, KeyError) as exc:
        print(f"Analysis failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(2) from None
