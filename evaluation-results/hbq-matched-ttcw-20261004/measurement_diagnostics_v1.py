"""Pure descriptive measurements; no files, targets, admission or scoring changes."""
from __future__ import annotations

from collections import Counter
import math

STATES = ("YES", "NO", "NOT_APPLICABLE", "CANNOT_ASSESS")


def state_transitions(pairs):
    """Rows are initial states, columns repeated states; None means absent."""
    matrix = {left: {right: 0 for right in STATES} for left in STATES}
    missing = {"initial_only_absent": 0, "repeat_only_absent": 0, "both_absent": 0}
    expected = 0
    for left, right in pairs:
        expected += 1
        if any(value is not None and value not in STATES for value in (left, right)):
            raise ValueError("Unknown leaf state; absence must be None")
        if left is None or right is None:
            key = "both_absent" if left is right is None else "initial_only_absent" if left is None else "repeat_only_absent"
            missing[key] += 1
        else:
            matrix[left][right] += 1
    rows = {state: sum(matrix[state].values()) for state in STATES}
    columns = {state: sum(matrix[left][state] for left in STATES) for state in STATES}
    n = sum(rows.values())
    matches = sum(matrix[state][state] for state in STATES)
    products = sum(rows[state] * columns[state] for state in STATES)
    denominator = n * n - products
    return {"states": list(STATES), "matrix_orientation": "initial_rows_repeat_columns",
            "transition_counts": matrix, "expected_positions": expected, "observed_pairs": n,
            "missing_positions": missing, "initial_marginal_counts": rows, "repeat_marginal_counts": columns,
            "raw_agreement": matches / n if n else None,
            "marginal_expected_agreement": products / (n * n) if n else None,
            "cohens_kappa": (matches * n - products) / denominator if denominator else None,
            "undefined_reason": "no_observed_pairs" if not n else "expected_agreement_one" if not denominator else None,
            "interpretation": "Descriptive nominal agreement; prevalence can distort kappa. Marginals and raw agreement remain necessary. Repeated leaves are dependent observations, not new independent works.",
            "advancement_gate": False, "independent_work_count_added": 0}


def leaf_repeat_transitions(profiles, sentinel_ids, expected_leaf_ids, field):
    """Compare cycle0 with cycles1/2 on the declared full leaf inventory."""
    ids = tuple(expected_leaf_ids)
    if not ids or len(set(ids)) != len(ids):
        raise ValueError("Expected leaf inventory must be nonempty and unique")
    if field not in {"question_id", "test_id"}:
        raise ValueError("Unknown leaf identity field")
    allowed = set(ids)

    def leaves(sid, cycle):
        result = {}
        for row in profiles.get((sid, cycle), {}).get("leaves", []):
            qid, value = row[field], row["verdict"]
            if qid not in allowed or qid in result or value not in STATES:
                raise ValueError("Unexpected, duplicate or invalid observed leaf")
            result[qid] = value
        return result

    pairs = {1: [], 2: []}
    for sid in sorted(sentinel_ids):
        initial = leaves(sid, 0)
        for cycle in (1, 2):
            repeated = leaves(sid, cycle)
            pairs[cycle].extend((initial.get(qid), repeated.get(qid)) for qid in ids)
    return {"declared_leaf_count": len(ids), "sentinel_works": len(sentinel_ids),
            "aggregate_initial_vs_repeats": state_transitions(pairs[1] + pairs[2]),
            "by_cycle": {f"0_vs_{cycle}": state_transitions(values) for cycle, values in pairs.items()}}


def scalar_extremes(values, native_range):
    """Affine display thresholds only; native input scores remain unchanged."""
    low, high = native_range
    if isinstance(low, bool) or isinstance(high, bool) or not all(math.isfinite(v) for v in (low, high)) or not low < high:
        raise ValueError("A finite increasing native range must be declared")
    values = tuple(values)
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or not low <= v <= high for v in values):
        raise ValueError("Scores must be finite, within the declared native range; no clipping")
    n = len(values)
    counts = Counter(values)
    lower_threshold, upper_threshold = low + .1 * (high - low), low + .9 * (high - low)
    measures = {"exact_floor": counts[low], "exact_ceiling": counts[high],
                "mapped_at_or_below_10": sum(v <= lower_threshold for v in values),
                "mapped_at_or_above_90": sum(v >= upper_threshold for v in values)}
    return {"native_range": [low, high], "observed_score_denominator": n,
            "affine_display_mapping": {"range": [0, 100], "formula": "100 * (score - native_min) / (native_max - native_min)",
                                       "native_lower_threshold": lower_threshold, "native_upper_threshold": upper_threshold},
            "counts": measures, "rates": {key: count / n if n else None for key, count in measures.items()},
            "native_scores_rounded_or_clipped": False, "mapping_used_for_ranking": False,
            "interpretation": "Descriptive scale occupancy only; different ordinal scales do not establish equivalent quality.",
            "advancement_gate": False}
