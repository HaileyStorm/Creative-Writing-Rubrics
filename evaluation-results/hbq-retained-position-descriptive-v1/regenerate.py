"""Regenerate aggregate-only TTCW order counts from exact retained inputs."""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
import math
from pathlib import Path
import random
import sys

PINS = {
    "joined": "cbf6192a025521990b17cb3c3f4d2c56e9443eb0ac3084a85eba8fcee9be96f4",
    "manifest": "b1868f8b6dee6daba3125b73628e6276b34f7049fad049f17262cbe3c859b7b7",
    "labels": "1916ec27eaa8810a8427ed7000e2aefa3535fd2a33b2ae1d372cccdab3fc6516",
    "condition": "219d1388e13bd796d13b93a7511ed7ee55d0cf120479783debf022a622d83dde",
    "cohort_freeze": "917522aedc84c045ae01fef9dcf3bb36a0f016c3449187f89dcc64c570141442",
    "features": "4c68971294cdac2696cd39e4161c7cf02e764fe1741978661966aafd264aecf8",
}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def checked(path, expected):
    raw = path.read_bytes()
    require(digest(raw) == expected, "Input commitment differs")
    return raw


def frozen_bytes(root, locator, expected):
    rel = Path(locator)
    require(not rel.is_absolute() and ".." not in rel.parts, "Unsafe frozen locator")
    node = root
    for part in rel.parts:
        node = node / part
        stat = node.lstat()
        require(not node.is_symlink() and not getattr(stat, "st_file_attributes", 0) & 1024,
                "Reparse frozen input refused")
    return checked(node, expected)


def spearman(x, y):
    def ranks(values):
        order = sorted(range(len(values)), key=values.__getitem__)
        result = [0.0] * len(values)
        i = 0
        while i < len(order):
            j = i + 1
            while j < len(order) and values[order[j]] == values[order[i]]:
                j += 1
            for index in order[i:j]:
                result[index] = (i + 1 + j) / 2
            i = j
        return result
    a, b = ranks(x), ranks(y)
    am, bm = sum(a) / len(a), sum(b) / len(b)
    numerator = sum((v - am) * (w - bm) for v, w in zip(a, b))
    denominator = math.sqrt(sum((v - am) ** 2 for v in a) * sum((w - bm) ** 2 for w in b))
    return None if denominator == 0 else numerator / denominator


def project(joined, manifest, labels, frozen_root, cohort_freeze, features):
    stories = {s["id"]: s for s in manifest["stories"]}
    pairs = {p["id"]: p for p in manifest["pairs"]}
    require(len(stories) == len(labels) == len(pairs) == 36, "Fixed cohort differs")
    targets = {}
    for row in labels:
        sid = row["pass_id"].rsplit("/", 1)[-1]
        require(sid in stories and sid not in targets and row["plot_group"] == stories[sid]["plot"],
                "Reference identity or plot differs")
        require([test["ttcw_idx"] for test in row["tests"]] == list(range(1, 15)), "Reference tests differ")
        votes = [vote for test in row["tests"] for vote in test["verdicts"]]
        require(len(votes) == 42 and all(len(test["verdicts"]) == 3 for test in row["tests"]) and
                all(vote in ("YES", "NO") for vote in votes), "Expected 42 binary source ballots")
        targets[sid] = votes.count("YES")
    originals = defaultdict(list)
    for record in manifest["requests"]:
        originals[record["logical_sample_id"]].append(record)

    rows = [row for row in joined["records"] if row["arm"] == "pairwise"]
    require(len(rows) == 72, "Expected exactly 72 saved pairwise orders")
    orders, positions, agreement, plots = defaultdict(dict), Counter(), Counter(), set()
    lengths, story_word_counts, length_baseline = {}, {}, Counter()
    for record in rows:
        d = record["condition_descriptor"]
        require(record["endpoint"] == "sol" and d["repeat"] == 0 and d["orientation"] in (0, 1) and
                record["scientific_condition_sha256"] == PINS["condition"] and
                record["semantic_acceptance"]["accepted"] is True and
                record["semantic_acceptance"]["abstention"] is False, "Saved qualification differs")
        original = d["original_request"]
        require(sum(item == original for item in originals[d["original_logical_sample_id"]]) == 1 and
                d["pair_id"] == original["pair_id"] and d["orientation"] == original["orientation"] and
                d["sources"] == original["sources"] and d["prompt_sha256"] == original["prompt_sha256"],
                "Frozen request binding differs")
        pair = pairs[d["pair_id"]]
        ordered = (pair["left"], pair["right"]) if d["orientation"] == 0 else (pair["right"], pair["left"])
        sources = d["sources"]
        require(len(sources) == 2 and tuple(s["id"] for s in sources) == ordered and
                [s["side"] for s in sources] == ["A", "B"] and
                stories[ordered[0]]["plot"] == stories[ordered[1]]["plot"] == pair["plot"],
                "Pair source or plot differs")
        prompt = frozen_bytes(frozen_root, d["prompt_path"], d["prompt_sha256"])
        a, b = [frozen_bytes(frozen_root, s["input_path"], s["sha256"]) for s in sources]
        require(prompt.count(a) == prompt.count(b) == 1 and prompt.find(a) < prompt.find(b) and
                b"## Story A\n\n" + a in prompt and b"## Story B\n\n" + b in prompt,
                "Frozen prompt source order differs")
        winner = record["response"]["winner"]
        require(winner in ("A", "B") and targets[ordered[0]] != targets[ordered[1]],
                "Tie or abstention needs separate treatment")
        orientation = d["orientation"]
        word_counts = tuple(len(text.decode("utf-8").split()) for text in (a, b))
        for story_id, count in zip(ordered, word_counts):
            require(story_id not in story_word_counts or story_word_counts[story_id] == count,
                    "Story word count differs across saved prompts")
            story_word_counts[story_id] = count
        if d["pair_id"] in lengths:
            prior_sources, prior_counts = lengths[d["pair_id"]]
            require(dict(zip(ordered, word_counts)) == dict(zip(prior_sources, prior_counts)),
                    "Pair word counts differ across orders")
        else:
            lengths[d["pair_id"]] = (ordered, word_counts)
        if word_counts[0] != word_counts[1]:
            longer = 0 if word_counts[0] > word_counts[1] else 1
            expert = 0 if targets[ordered[0]] > targets[ordered[1]] else 1
            length_baseline["ordered_judgments"] += 1
            length_baseline["judge_matches_expert"] += (winner == ("A" if expert == 0 else "B"))
            length_baseline["judge_selects_longer"] += (winner == ("A" if longer == 0 else "B"))
            if orientation == 0:
                length_baseline["comparable_pairs"] += 1
                length_baseline["longer_matches_expert"] += (longer == expert)
        elif orientation == 0:
            length_baseline["tied_length_pairs"] += 1
        require(orientation not in orders[d["pair_id"]], "Duplicate order")
        orders[d["pair_id"]][orientation] = (winner, (sources[0]["sha256"], sources[1]["sha256"]))
        positions[winner] += 1
        higher_first = targets[ordered[0]] > targets[ordered[1]]
        reference_position = "first" if higher_first else "second"
        agreement[(reference_position, winner == ("A" if higher_first else "B"))] += 1
        plots.add(pair["plot"])

    require(len(orders) == 36 and len(plots) == 12 and all(set(v) == {0, 1} for v in orders.values()),
            "Pair or plot geometry differs")
    require(length_baseline["comparable_pairs"] + length_baseline["tied_length_pairs"] == 36 and
            length_baseline["ordered_judgments"] == 2 * length_baseline["comparable_pairs"],
            "Length baseline denominator differs")
    patterns = Counter()
    for pair in orders.values():
        a, b = pair[0], pair[1]
        require(a[1] == tuple(reversed(b[1])), "Pair source content did not reverse")
        patterns[(a[0], b[0])] += 1
    results = []
    for position in ("first", "second"):
        matches, misses = agreement[(position, True)], agreement[(position, False)]
        require(matches + misses == 36, "Reference position denominator differs")
        results.append({"expert_higher_story_position": position, "matches": matches,
                        "mismatches": misses, "orders": matches + misses})
    require(positions == {"A": 37, "B": 35} and
            patterns == {("A", "B"): 18, ("B", "A"): 15, ("A", "A"): 2, ("B", "B"): 1} and
            [(r["matches"], r["mismatches"]) for r in results] == [(31, 5), (30, 6)],
            "Saved outcome counts differ from reviewed results")
    require(features["cohort_membership"] == cohort_freeze["cohorts"] and
            cohort_freeze["private_features437"]["sha256"] == PINS["features"],
            "Fixed cohort provenance differs")
    members = cohort_freeze["cohorts"]["all_five_28"]
    rows = {row["story_id"]: row for row in features["features_and_existing_targets"]}
    require(len(members) == len(set(members)) == 28 and len(rows) == 29 and
            set(members) <= set(rows) <= set(stories) and len(story_word_counts) == 36,
            "Fixed cohort membership differs")
    for sid in members:
        row = rows[sid]
        require(row["source_sha256"] == stories[sid]["sha256"] and row["plot"] == stories[sid]["plot"] and
                math.isclose(row["expert_mean"], targets[sid] / 42, rel_tol=0, abs_tol=1e-12),
                "Saved score, source, or existing reference join differs")
        require(all(isinstance(row["saved_scores"][arm], (int, float)) and
                    not isinstance(row["saved_scores"][arm], bool) and
                    math.isfinite(row["saved_scores"][arm])
                    for arm in ("hbq", "ttcw14", "holistic", "compact", "oregon")),
                "Fixed matched score unavailable")
    within_plot = {arm: Counter() for arm in
                   ("hbq", "ttcw14", "holistic", "compact", "oregon", "shorter")}
    pair_judge = Counter()
    pair_plots = set()
    expert_ties = 0
    for pair_id, pair in pairs.items():
        left, right = pair["left"], pair["right"]
        if left not in members or right not in members:
            continue
        expert_delta = targets[left] - targets[right]
        if not expert_delta:
            expert_ties += 1
            continue
        pair_plots.add(pair["plot"])
        for arm, counts in within_plot.items():
            if arm == "shorter":
                delta = story_word_counts[right] - story_word_counts[left]
            else:
                delta = rows[left]["saved_scores"][arm] - rows[right]["saved_scores"][arm]
            counts["ties" if delta == 0 else "matches" if (delta > 0) == (expert_delta > 0) else "mismatches"] += 1
        for orientation, (winner, _) in orders[pair_id].items():
            selected = (left, right)[(0 if winner == "A" else 1) ^ orientation]
            pair_judge["matches" if (selected == left) == (expert_delta > 0) else "mismatches"] += 1
    pair_count = sum(within_plot["hbq"].values())
    require(pair_count > 0 and all(sum(value.values()) == pair_count for value in within_plot.values()) and
            sum(pair_judge.values()) == 2 * pair_count, "Same-cohort within-plot denominators differ")
    within_plot_result = {
        "cohort": "all_five_28",
        "informative_pairs": pair_count,
        "plots_with_informative_pairs": len(pair_plots),
        "expert_ties_excluded": expert_ties,
        "scoring_rules": {arm: {"matches": c["matches"], "mismatches": c["mismatches"], "ties": c["ties"],
                                "tie_half_credit_agreement": (c["matches"] + c["ties"] / 2) / pair_count}
                          for arm, c in within_plot.items()},
        "direct_judge": {"ordered_judgments": 2 * pair_count, "matches": pair_judge["matches"],
                         "mismatches": pair_judge["mismatches"]},
    }
    length_associations = []
    for generator in (None, "Claude", "GPT3.5", "GPT4"):
        ids = [sid for sid in members if generator is None or stories[sid]["generator"] == generator]
        expected = {None: 28, "Claude": 10, "GPT3.5": 10, "GPT4": 8}[generator]
        require(len(ids) == expected, "Fixed generator partition differs")
        target = [rows[sid]["expert_mean"] for sid in ids]
        length_associations.append({
            "group": "all_five_28" if generator is None else generator,
            "works": len(ids), "plots": len({stories[sid]["plot"] for sid in ids}),
            "length_distinct_values": len({story_word_counts[sid] for sid in ids}),
            "length_expert_rho": spearman([story_word_counts[sid] for sid in ids], target),
            "hbq_expert_rho": spearman([rows[sid]["saved_scores"]["hbq"] for sid in ids], target),
            "ttcw14_expert_rho": spearman([rows[sid]["saved_scores"]["ttcw14"] for sid in ids], target),
        })
    require(round(length_associations[0]["hbq_expert_rho"], 3) == .712 and
            round(length_associations[0]["ttcw14_expert_rho"], 3) == .423,
            "Published matched correlations do not reproduce")
    # This direction was chosen after inspecting the opened cohort. Resampling
    # preserves all observed works in each selected plot, including duplicates.
    plot_members = defaultdict(list)
    for sid in members:
        plot_members[stories[sid]["plot"]].append(sid)
    plot_keys = sorted(plot_members)
    require(len(plot_keys) == 12, "Fixed cohort plot count differs")
    rng = random.Random(20261103)
    differences, undefined = [], 0
    for _ in range(2000):
        sampled = [sid for key in rng.choices(plot_keys, k=len(plot_keys)) for sid in plot_members[key]]
        target = [rows[sid]["expert_mean"] for sid in sampled]
        hbq = spearman([rows[sid]["saved_scores"]["hbq"] for sid in sampled], target)
        shorter = spearman([-story_word_counts[sid] for sid in sampled], target)
        if hbq is None or shorter is None:
            undefined += 1
        else:
            differences.append(hbq - shorter)
    differences.sort()
    def percentile(probability):
        if not differences:
            return None
        offset = (len(differences) - 1) * probability
        lower = math.floor(offset)
        upper = math.ceil(offset)
        return differences[lower] + (differences[upper] - differences[lower]) * (offset - lower)
    length_sensitivity = {
        "baseline_direction": "shorter story; chosen after observing these development data",
        "contrast": "HBQ rho minus shorter-story rho on the same sampled works",
        "observed_difference": length_associations[0]["hbq_expert_rho"] + length_associations[0]["length_expert_rho"],
        "cluster_unit": "plot",
        "observed_plots": len(plot_keys),
        "draws": 2000,
        "seed": 20261103,
        "random_sampling": "Python random.Random.choices with replacement",
        "python_version": sys.version.split()[0],
        "defined_draws": len(differences),
        "undefined_draws": undefined,
        "conditional_percentile_2_5": percentile(.025),
        "conditional_percentile_97_5": percentile(.975),
        "percentile_rule": "linear interpolation of sorted defined draws; undefined count retained",
    }
    return {
        "format_version": 2,
        "state": "RETAINED_TTCW_POSITION_DESCRIPTIVE_DEVELOPMENT",
        "scope": {"works": 36, "plot_clusters": 12, "pairs": 36, "ordered_judgments": 72,
                  "same_order_repeat_judgments": 0, "population": "existing expert-reference development"},
        "position_selections": {"first": positions["A"], "second": positions["B"]},
        "pairs_with_reversed_presentation": len(orders),
        "pair_outcomes": {"first_in_both_orders": patterns[("A", "A")],
                          "second_in_both_orders": patterns[("B", "B")],
                          "first_then_second_same_work": patterns[("A", "B")],
                          "second_then_first_same_work": patterns[("B", "A")]},
        "expert_higher_story_position": results,
        "posthoc_whitespace_word_count_baseline": {
            "rule": "select the story with more whitespace-separated UTF-8 decoded tokens; abstain on ties",
            "comparable_pairs": length_baseline["comparable_pairs"],
            "tied_length_pairs": length_baseline["tied_length_pairs"],
            "longer_matches_expert": length_baseline["longer_matches_expert"],
            "ordered_judgments_on_comparable_pairs": length_baseline["ordered_judgments"],
            "judge_matches_expert_on_those_orders": length_baseline["judge_matches_expert"],
            "judge_selects_longer_on_those_orders": length_baseline["judge_selects_longer"],
        },
        "posthoc_fixed28_length_associations": length_associations,
        "posthoc_fixed28_within_plot_agreement": within_plot_result,
        "posthoc_plot_clustered_shorter_baseline_sensitivity": length_sensitivity,
        "source_commitments": {"saved_joined_sha256": PINS["joined"],
                               "frozen_manifest_sha256": PINS["manifest"],
                               "existing_labels_sha256": PINS["labels"],
                               "scientific_condition_sha256": PINS["condition"],
                               "fixed_cohort_freeze_sha256": PINS["cohort_freeze"],
                               "saved_features_sha256": PINS["features"]},
        "implementation_sha256": digest(Path(__file__).read_bytes()),
        "limits": [
            "Expert direction derives from pre-existing creativity-test ratings, not direct preference ballots.",
            "The 36 pairs share stories and cluster in 12 plots; neither orders nor ballots are independent works or people.",
            "The reference-position split is post-hoc and supplies no population significance or causal position-effect claim.",
            "The word-count baseline is post-hoc on the same dependent development pairs; comparisons are descriptive, not held-out evaluation.",
            "Fixed-cohort and within-generator length correlations are exploratory, use the opened 28-work cohort, and do not establish causation or model superiority.",
            "Within-plot scoring comparisons use the same availability-conditioned work pairs and count score ties as half only in the summary; direct judgments use two dependent presentation orders.",
            "Shorter was selected after observing the data; the paired plot-resampling range is conditional on the selected incomplete cohort, not a prospective test or a remedy for missing works.",
            "Same-order repeats were not collected; historical client versions and missing fields limit current-contract equivalence.",
            "Saved admission is reused; prompt and source bytes are checked, but native or semantic admission is not replayed.",
            "No provider calls, new votes, human labels or candidate promotion occur.",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    for name in ("joined", "manifest", "labels", "frozen-root", "cohort-freeze", "features", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    joined = json.loads(checked(args.joined, PINS["joined"]))
    manifest = json.loads(checked(args.manifest, PINS["manifest"]))
    labels = json.loads(checked(args.labels, PINS["labels"]))
    cohort_freeze = json.loads(checked(args.cohort_freeze, PINS["cohort_freeze"]))
    features = json.loads(checked(args.features, PINS["features"]))
    result = project(joined, manifest, labels, args.frozen_root.resolve(strict=True), cohort_freeze, features)
    raw = (json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")
    with args.output.open("xb") as output:
        output.write(raw)
    require(args.output.read_bytes() == raw, "Output readback differs")
    print(json.dumps({"sha256": digest(raw), "bytes": len(raw)}))


if __name__ == "__main__":
    main()
