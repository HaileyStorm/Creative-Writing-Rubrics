from __future__ import annotations

import json
import math
import re
import statistics
from itertools import combinations
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
AGGREGATE = ROOT / "aggregate.v1.json"
ALLOWED_FILES = {"README.md", "aggregate.v1.json", "verify_output.py"}
IGNORED_GENERATED_DIRECTORIES = {"__pycache__"}
EXPECTED_RUNS = {
    "off": [
        (1, 79.0707, 76.5849, 80.5622, 0.9602, "477aaf37744c377d39fe2a71b943e295d7a07e877e9b8ac0940a3d00328aa831"),
        (2, 80.2437, 80.2437, 80.2437, 1.0, "a74bd875cf8cb48816f3d40d8b84249caf6c6f4d112dd09405c039e4da9c2249"),
        (3, 91.1706, 89.182, 91.1706, 0.9801, "6b5c04cb1d9dce528f34bbfb0b8de8544d08f880540427692a19cf6d80852667"),
    ],
    "creative_reasoning": [
        (1, 90.7115, 89.2483, 90.9309, 0.9832, "8f14e8d22615c0d5b8bea523afb2eb7500e5e14018ee0eaf3ac458c1ec2faf0a"),
        (2, 93.75, 93.75, 93.75, 1.0, "0c44c4d94e7e006657641c24cf8690410d3c53ea186aa9903f36c7d807a36cb0"),
        (3, 92.2414, 92.2414, 92.2414, 1.0, "55e0df99312ff3d6ca21f115c7ced3bd60628f939a0703908a1a086483dcfce2"),
    ],
}
FORBIDDEN_FIELD_NAMES = {
    "absolute_path",
    "artifact_text",
    "context_text",
    "exact_quote",
    "private_path",
    "raw_prompt",
    "raw_response",
    "request_id",
    "session_id",
}


def _read() -> dict[str, Any]:
    value = json.loads(AGGREGATE.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Aggregate result must be an object")
    return value


def _summary(values: list[float]) -> dict[str, float]:
    median = statistics.median(values)
    deviations = [abs(value - median) for value in values]
    pairs = [abs(left - right) for left, right in combinations(values, 2)]
    return {
        "median": median,
        "mad": statistics.median(deviations),
        "sample_standard_deviation": statistics.stdev(values),
        "range": max(values) - min(values),
        "mean_absolute_pairwise_difference": statistics.fmean(pairs),
    }


def _round_summary(value: dict[str, float]) -> dict[str, float]:
    return {key: round(item, 4) for key, item in value.items()}


def _assert_public_surface(value: Any) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str) or key.lower() in FORBIDDEN_FIELD_NAMES:
                raise ValueError("Aggregate result exposes a restricted field")
            _assert_public_surface(item)
        return
    if isinstance(value, list):
        for item in value:
            _assert_public_surface(item)
        return
    if isinstance(value, str) and re.search(r"(?:^[A-Za-z]:[\\/]|^/|^~[\\/]|(?:^|[\\/])(?:home|users)[\\/])", value):
        raise ValueError("Aggregate result exposes a private path")


def _validate_runs(value: dict[str, Any]) -> dict[str, list[float]]:
    groups = value.get("replicate_groups")
    if not isinstance(groups, dict) or set(groups) != set(EXPECTED_RUNS):
        raise ValueError("Replicate groups drifted")
    scores: dict[str, list[float]] = {}
    for group_id, expected in EXPECTED_RUNS.items():
        group = groups[group_id]
        if not isinstance(group, dict) or set(group) != {"runs"}:
            raise ValueError(f"{group_id} group surface drifted")
        runs = group["runs"]
        if not isinstance(runs, list) or len(runs) != len(expected):
            raise ValueError(f"{group_id} runs drifted")
        rows = []
        for run, wanted in zip(runs, expected, strict=True):
            if not isinstance(run, dict) or set(run) != {"replicate", "observed_score", "lower_score", "upper_score", "coverage", "run_status", "hard_gate", "reported_run_sha256"}:
                raise ValueError(f"{group_id} run surface drifted")
            received = (run["replicate"], run["observed_score"], run["lower_score"], run["upper_score"], run["coverage"], run["reported_run_sha256"])
            if received != wanted:
                raise ValueError(f"{group_id} run data drifted")
            if run["run_status"] != "SCORED" or run["hard_gate"] != "VALID":
                raise ValueError(f"{group_id} run status drifted")
            if not 0.0 <= float(run["coverage"]) <= 1.0:
                raise ValueError(f"{group_id} coverage is outside bounds")
            if not float(run["lower_score"]) <= float(run["observed_score"]) <= float(run["upper_score"]):
                raise ValueError(f"{group_id} score bounds are invalid")
            if not re.fullmatch(r"[0-9a-f]{64}", run["reported_run_sha256"]):
                raise ValueError(f"{group_id} reported run hash is malformed")
            rows.append(float(run["observed_score"]))
        scores[group_id] = rows
    return scores


def verify() -> dict[str, Any]:
    value = _read()
    expected_keys = {"format_version", "study_id", "result_classification", "promotion", "replicate_groups", "reported_stack_bindings"}
    if set(value) != expected_keys:
        raise ValueError("Aggregate result contains an unexpected field")
    if value["format_version"] != 1 or value["study_id"] != "cwr-exact-duplicate-repeatability-v1":
        raise ValueError("Aggregate identity drifted")
    if value["result_classification"] != "EXPLORATORY_DIRECTIONAL_ADVANTAGE_NO_PROMOTION" or value["promotion"] != "none":
        raise ValueError("Aggregate decision drifted")
    if value["reported_stack_bindings"] != {
        "status": "UNVERIFIED_OMITTED",
        "omitted_fields": ["reported_compiled_bundle_sha256", "reported_full_stack_receipt_sha256"],
    }:
        raise ValueError("Unverified stack-binding treatment drifted")
    _assert_public_surface(value)

    scores = _validate_runs(value)
    off = _round_summary(_summary(scores["off"]))
    creative = _round_summary(_summary(scores["creative_reasoning"]))
    superiority = sum(candidate > control for candidate in scores["creative_reasoning"] for control in scores["off"])
    derived = {
        "group_summaries": {"off": off, "creative_reasoning": creative},
        "median_gap": round(creative["median"] - off["median"], 4),
        "median_minus_mad_gap": round((creative["median"] - creative["mad"]) - (off["median"] - off["mad"]), 4),
        "creative_reasoning_cross_replicate_wins": superiority,
        "cross_replicate_comparisons": len(scores["off"]) * len(scores["creative_reasoning"]),
        "descriptive_probability_of_superiority": round(superiority / 9, 4),
    }
    if derived != {
        "group_summaries": {
            "off": {"median": 80.2437, "mad": 1.173, "sample_standard_deviation": 6.6731, "range": 12.0999, "mean_absolute_pairwise_difference": 8.0666},
            "creative_reasoning": {"median": 92.2414, "mad": 1.5086, "sample_standard_deviation": 1.5193, "range": 3.0385, "mean_absolute_pairwise_difference": 2.0257},
        },
        "median_gap": 11.9977,
        "median_minus_mad_gap": 11.6621,
        "creative_reasoning_cross_replicate_wins": 8,
        "cross_replicate_comparisons": 9,
        "descriptive_probability_of_superiority": 0.8889,
    }:
        raise ValueError("Derived repeatability arithmetic drifted")
    if not math.isclose(derived["descriptive_probability_of_superiority"], 8 / 9, abs_tol=0.00005):
        raise ValueError("Descriptive superiority ratio drifted")
    files = {path.name for path in ROOT.iterdir() if path.is_file()}
    directories = {path.name for path in ROOT.iterdir() if path.is_dir()}
    if files != ALLOWED_FILES or directories - IGNORED_GENERATED_DIRECTORIES:
        raise ValueError("Aggregate package surface drifted")
    return {**value, "derived": derived}


if __name__ == "__main__":
    print(json.dumps(verify(), sort_keys=True))
