"""Exact scalar diagnostics from an opened, historical matched repeat panel."""
from __future__ import annotations

import argparse
import ast
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from fractions import Fraction
import hashlib
from itertools import combinations
import json
from pathlib import Path
import random
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
PROFILE_SHA = "88da3f3c9d2572957bfb512c4414587cdf7ce0796194eb42d45120e26a7a13f1"
POLICY = "historical_multisample_matched_floor_discrimination_v1"
HBQ = "hbq_short_story_batch32"
EXTREMES = ("exact_minimum", "exact_maximum", "near_minimum", "near_maximum")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()


def checked(root, pin):
    path = (root / pin["locator"]).resolve()
    require(path.is_relative_to(root.resolve()), "Source locator escapes its root")
    raw = path.read_bytes()
    require(len(raw) == pin["bytes"] and sha(raw) == pin["sha256"], "Source commitment differs")
    return raw


def reject_constant(value):
    raise ValueError("Nonfinite selected JSON number: " + value)


def extract(raw, names, namespace):
    tree = ast.parse(raw)
    nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
    require(len(nodes) == len(names) and {node.name for node in nodes} == set(names),
            "Pinned function extraction differs")
    exec(compile(ast.Module(body=nodes, type_ignores=[]), "pinned-function-extraction", "exec"), namespace)
    return namespace


def scalar(value):
    require(not isinstance(value, bool) and isinstance(value, (int, Decimal)) and
            (not isinstance(value, Decimal) or value.is_finite()), "Invalid selected native score")
    return Fraction(value)


def fraction(value):
    value = Fraction(value)
    return {"numerator": value.numerator, "denominator": value.denominator}


def extreme_flags(value, bounds):
    lower, upper = bounds
    normalized = 100 * (value - lower) / (upper - lower)
    return dict(zip(EXTREMES, (value == lower, value == upper, normalized <= 10, normalized >= 90)))


def distribution(values, planned, bounds):
    require(len(values) == planned, "Required score denominator differs")
    counts = {metric: sum(extreme_flags(value, bounds)[metric] for value in values) for metric in EXTREMES}
    return {"planned": planned, "available": len(values), "missing": 0,
            "observed_native_minimum": fraction(min(values)), "observed_native_maximum": fraction(max(values)),
            "distinct_scores": len(set(values)), "extremes": {
                metric: {"count": count, "denominator": planned, "rate": fraction(Fraction(count, planned))}
                for metric, count in counts.items()}}


def ties(values):
    denominator = len(values) * (len(values) - 1) // 2
    require(denominator > 0, "Between-item tie denominator is empty")
    count = sum(left == right for left, right in combinations(values, 2))
    return {"tied_item_pairs": count, "planned_item_pairs": denominator,
            "available_item_pairs": denominator, "missing_item_pairs": 0,
            "tie_rate": fraction(Fraction(count, denominator))}


def preflight(source, profile, repository_raw, source_raw):
    require(profile["policy"] == POLICY and profile["schema_version"] == 1, "Wrong frozen profile")
    require(profile["bootstrap"]["seed"] == 560820 and profile["bootstrap"]["draws"] == 1000 and
            profile["thresholds"]["near_minimum_affine_percent_lte"] == 10 and
            profile["thresholds"]["near_maximum_affine_percent_gte"] == 90, "Frozen analysis controls differ")
    manifest = json.loads(source_raw["manifest.json"])
    for name in ("summary.json", "consolidation-provenance.json"):
        pin = profile["source_pins"][name]
        require(manifest["files"][name] == {"bytes": pin["bytes"], "sha256": pin["sha256"]},
                "Consolidation manifest binding differs")
    public = json.loads(repository_raw["completed_public_manifest"])
    require(public["study_id"] == "hbq-multisample-repeatability-v1" and
            public["completed_analysis_commitments"]["summary_sha256"] == sha(source_raw["summary.json"]) and
            public["completed_analysis_commitments"]["consolidation_provenance_sha256"] ==
            sha(source_raw["consolidation-provenance.json"]), "Published source binding differs")
    contract = json.loads(repository_raw["exposure_contract"])
    require(contract["study_id"] == public["study_id"] and contract["repetitions"] == 5 and
            "one-development-item-per-model" in contract["dataset"]["selection_rule"],
            "Opened development exposure contract differs")
    namespace = extract(repository_raw["lexical_reader"], ("require", "project_json"), {
        "json": SimpleNamespace(JSONDecoder=lambda: json.JSONDecoder(
            parse_float=Decimal, parse_constant=reject_constant))})
    scale = extract(repository_raw["scale_source"], ("_scale",), {})["_scale"]
    arms = tuple(profile["native_ranges"])
    for arm in arms:
        require(list(scale(arm)) == profile["native_ranges"][arm], "Pinned native range differs")
    cohort_fields = {name: {"item_ids": True, "sample_count": True} for name in profile["cohorts"]}
    fields = {"study_id": True, "sample_count": True, "repetitions": True, "prompt_cluster_count": True,
              "arms": {arm: {"per_sample": [{"item_id": True, "prompt_sha256": True, "values": True}]}
                       for arm in arms}}
    fields["arms"][HBQ]["quality_sensitivity"] = {"status": True, "cohorts": cohort_fields}
    selected = namespace["project_json"](source_raw["summary.json"], fields)
    require(selected["study_id"] == public["study_id"] and selected["sample_count"] == 11 and
            selected["repetitions"] == 5 and selected["prompt_cluster_count"] == 10 and len(arms) == 6,
            "Required panel geometry differs")
    panel, prompts = {}, {}
    for arm in arms:
        rows = selected["arms"][arm]["per_sample"]
        require(len(rows) == 11 and len({row["item_id"] for row in rows}) == 11, "Arm item geometry differs")
        panel[arm] = {}
        bounds = profile["native_ranges"][arm]
        for row in rows:
            item, prompt = row["item_id"], row["prompt_sha256"]
            require(isinstance(item, str) and isinstance(prompt, str) and len(prompt) == 64 and
                    all(char in "0123456789abcdef" for char in prompt), "Item/prompt commitment is malformed")
            require(item not in prompts or prompts[item] == prompt, "Matched prompt assignment differs")
            prompts[item] = prompt
            require(isinstance(row["values"], list) and len(row["values"]) == 5,
                    "Required five repetitions missing")
            values = tuple(scalar(value) for value in row["values"])
            require(all(bounds[0] <= value <= bounds[1] for value in values), "Native score outside frozen range")
            panel[arm][item] = values
    require(all(set(rows) == set(prompts) for rows in panel.values()) and len(prompts) == 11 and
            len(set(prompts.values())) == 10, "Matched item/cluster inventory differs")
    quality = selected["arms"][HBQ]["quality_sensitivity"]
    require(quality["status"] == "version_cohorted_not_pooled", "HBQ version qualification differs")
    cohorts = {}
    for name, declaration in profile["cohorts"].items():
        saved = quality["cohorts"][name]
        items = sorted(saved["item_ids"])
        require(len(set(items)) == len(items) == saved["sample_count"] == declaration["planned_items"] and
                sha(canonical(items)) == declaration["sorted_membership_sha256"] and
                len({prompts[item] for item in items}) == declaration["planned_prompt_clusters"] and
                len(items) * 5 == declaration["planned_scores_per_arm"], "Frozen cohort membership differs")
        cohorts[name] = items
    membership = list(cohorts.values())
    require(len(membership) == 2 and set(membership[0]).isdisjoint(membership[1]) and
            set(membership[0]) | set(membership[1]) == set(prompts), "Cohorts do not partition the panel")
    require(profile["planned"] == {"arms": 6, "items": 11, "prompt_clusters": 10, "repetitions": 5,
            "raw_scores": 330, "item_repeat_means": 66, "arm_cohort_rows": 12,
            "original_cohort_raw_scores": 180, "later_cohort_raw_scores": 150}, "Frozen denominators differ")
    return panel, prompts, cohorts


def percentile(values, probability):
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    lower = position.numerator // position.denominator
    upper = min(lower + 1, len(ordered) - 1)
    return ordered[lower] + (position - lower) * (ordered[upper] - ordered[lower])


def calculate(panel, prompts, cohorts, profile):
    rng = random.Random(profile["bootstrap"]["seed"])
    rows = []
    contrasts = []
    for cohort, items in cohorts.items():
        item_rates = {}
        for arm, by_item in panel.items():
            bounds = profile["native_ranges"][arm]
            repeated = [by_item[item] for item in items]
            means = [sum(values, Fraction()) / 5 for values in repeated]
            raw = [value for values in repeated for value in values]
            rows.append({"cohort": cohort, "arm": arm, "native_range": bounds,
                "planned_items": len(items), "available_items": len(items), "missing_items": 0,
                "planned_prompt_clusters": len({prompts[item] for item in items}),
                "available_prompt_clusters": len({prompts[item] for item in items}), "missing_prompt_clusters": 0,
                "planned_repetitions": 5, "available_repetitions_per_item": 5, "missing_repetitions": 0,
                "raw_repeat_scores": distribution(raw, len(items) * 5, bounds),
                "item_repeat_means": distribution(means, len(items), bounds),
                "between_item_ties_by_repetition": [{"repetition": repetition + 1,
                    **ties([values[repetition] for values in repeated])} for repetition in range(5)],
                "between_item_repeat_mean_ties": ties(means)})
            item_rates[arm] = {
                "raw_repeat_scores": {metric: [sum(extreme_flags(v, bounds)[metric] for v in values) / Fraction(5)
                    for values in repeated] for metric in EXTREMES},
                "item_repeat_means": {metric: [Fraction(extreme_flags(v, bounds)[metric]) for v in means]
                    for metric in EXTREMES}}
        clusters = defaultdict(list)
        for index, item in enumerate(items):
            clusters[prompts[item]].append(index)
        groups = [clusters[key] for key in sorted(clusters)]
        boot = defaultdict(list)
        for _ in range(profile["bootstrap"]["draws"]):
            indices = [index for _ in groups for index in rng.choice(groups)]
            for arm in panel:
                if arm == HBQ:
                    continue
                for unit in ("raw_repeat_scores", "item_repeat_means"):
                    for metric in EXTREMES:
                        rates = item_rates[arm][unit][metric]
                        baseline = item_rates[HBQ][unit][metric]
                        boot[(arm, unit, metric)].append(
                            sum((rates[i] - baseline[i] for i in indices), Fraction()) / len(indices))
        for (arm, unit, metric), values in sorted(boot.items()):
            estimate = sum((a - b for a, b in zip(item_rates[arm][unit][metric],
                item_rates[HBQ][unit][metric])), Fraction()) / len(items)
            contrasts.append({"cohort": cohort, "arm": arm, "baseline": HBQ, "unit": unit,
                "metric": metric, "orientation": "comparator_minus_hbq", "estimate": fraction(estimate),
                "ci95_percentile": {"low": fraction(percentile(values, Fraction(1, 40))),
                                    "high": fraction(percentile(values, Fraction(39, 40)))},
                "prompt_clusters": len(groups), "draws": len(values), "descriptive_only": True})
    require(len(rows) == 12 and sum(row["raw_repeat_scores"]["available"] for row in rows) == 330 and
            sum(row["item_repeat_means"]["available"] for row in rows) == 66 and len(contrasts) == 80,
            "Calculated panel denominator differs")
    return rows, contrasts


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args(argv)
    source, output = args.source_root.resolve(), args.output_root.resolve()
    require(not output.exists() and not output.is_relative_to(REPO) and not REPO.is_relative_to(output) and
            not output.is_relative_to(source) and not source.is_relative_to(output),
            "Fresh output outside repository and retained source required")
    profile_raw = (HERE / "profile.json").read_bytes()
    require(sha(profile_raw) == PROFILE_SHA, "Frozen profile differs")
    profile = json.loads(profile_raw)
    source_raw = {name: checked(source, pin) for name, pin in profile["source_pins"].items()}
    repository_raw = {name: checked(REPO, pin) for name, pin in profile["repository_pins"].items()}
    panel, prompts, cohorts = preflight(source, profile, repository_raw, source_raw)
    rows, contrasts = calculate(panel, prompts, cohorts, profile)
    source_code = Path(__file__).read_bytes()
    report = {"schema_version": 1, "policy": POLICY, "profile_sha256": sha(profile_raw),
        "implementation_sha256": sha(source_code), "source_pins": profile["source_pins"],
        "repository_pins": profile["repository_pins"], "exposure": profile["exposure"],
        "cohorts": profile["cohorts"], "planned": profile["planned"],
        "available_items": 11, "missing_items": 0, "available_prompt_clusters": 10, "missing_prompt_clusters": 0,
        "available_raw_scores": 330, "missing_raw_scores": 0, "available_item_repeat_means": 66,
        "missing_item_repeat_means": 0, "thresholds": profile["thresholds"],
        "arithmetic": profile["arithmetic"], "bootstrap": profile["bootstrap"], "rows": rows,
        "paired_extreme_rate_contrasts": contrasts, "interpretation": profile["interpretation"],
        "limitations": ["Historical opened development panel only; the six-item and five-item cohorts differ jointly in items and HBQ rubric version.",
            "No pooled HBQ primary estimate, current-contract inference, calibrated absolute quality or human-alignment improvement claim.",
            "Paired percentile intervals are descriptive with only six/four prompt clusters; repeated scores and item pairs are not independent observations, and multiplicity is not controlled.",
            "Saved scalar and native-source claims are inherited without source-body, label, response, semantic or native-admission replay; historical tool declarations are not retroactive tool qualification."],
        "human_targets_decoded": False, "prose_decoded": False, "native_replayed": False,
        "provider_calls_made": 0, "new_provider_votes": 0}
    report_raw = canonical(report)
    output.mkdir(parents=True, exist_ok=False)
    contents = {"report.json": report_raw, "profile.json": profile_raw, "analyze.py": source_code}
    for name, raw in contents.items():
        with (output / name).open("xb") as stream:
            stream.write(raw)
        require((output / name).read_bytes() == raw, "Output readback differs")
    terminal = {"schema_version": 1, "policy": POLICY, "state": "completed",
        "completed_utc": datetime.now(timezone.utc).isoformat(), "report_sha256": sha(report_raw),
        "profile_sha256": sha(profile_raw), "implementation_sha256": sha(source_code),
        "raw_scores": 330, "item_repeat_means": 66, "arm_cohort_rows": 12,
        "provider_calls_made": 0, "new_provider_votes": 0}
    with (output / "terminal.json").open("xb") as stream:
        stream.write(canonical(terminal))
    print(json.dumps(terminal, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
