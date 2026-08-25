from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation-results" / "cwr-exact-duplicate-repeatability-v1-public-result-v1"


def load_verifier():
    spec = importlib.util.spec_from_file_location("cwr_exact_duplicate_repeatability", PACKAGE / "verify_output.py")
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_public_repeatability_aggregate_recomputes_directional_summary() -> None:
    value = load_verifier().verify()
    assert value["result_classification"] == "EXPLORATORY_DIRECTIONAL_ADVANTAGE_NO_PROMOTION"
    assert value["promotion"] == "none"
    assert value["derived"]["group_summaries"]["off"] == {
        "median": 80.2437,
        "mad": 1.173,
        "sample_standard_deviation": 6.6731,
        "range": 12.0999,
        "mean_absolute_pairwise_difference": 8.0666,
    }
    assert value["derived"]["median_gap"] == 11.9977
    assert value["derived"]["median_minus_mad_gap"] == 11.6621
    assert value["derived"]["creative_reasoning_cross_replicate_wins"] == 8
    assert value["derived"]["cross_replicate_comparisons"] == 9
    assert all(
        run["run_status"] == "SCORED" and run["hard_gate"] == "VALID"
        and run["lower_score"] <= run["observed_score"] <= run["upper_score"]
        for group in value["replicate_groups"].values()
        for run in group["runs"]
    )


@pytest.mark.parametrize(
    ("path", "replacement"),
    [
        (("promotion",), "default"),
        (("replicate_groups", "off", "runs", 0, "reported_run_sha256"), "not-a-hash"),
        (("replicate_groups", "off", "runs", 0, "lower_score"), 81.0),
        (("reported_stack_bindings", "omitted_fields"), []),
    ],
)
def test_public_repeatability_aggregate_fails_closed_on_drift(tmp_path: Path, path: tuple[object, ...], replacement: object) -> None:
    verifier = load_verifier()
    payload = json.loads((PACKAGE / "aggregate.v1.json").read_text(encoding="utf-8"))
    target = payload
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = replacement
    result = tmp_path / "aggregate.v1.json"
    result.write_text(json.dumps(payload), encoding="utf-8")
    original = verifier.AGGREGATE
    verifier.AGGREGATE = result
    try:
        with pytest.raises(ValueError):
            verifier.verify()
    finally:
        verifier.AGGREGATE = original


@pytest.mark.parametrize("tamper", ["nested_forbidden_field", "extra_group_field", "extra_row_field"])
def test_public_repeatability_aggregate_fails_closed_on_nested_privacy_or_shape_tampering(tmp_path: Path, tamper: str) -> None:
    verifier = load_verifier()
    payload = json.loads((PACKAGE / "aggregate.v1.json").read_text(encoding="utf-8"))
    if tamper == "nested_forbidden_field":
        payload["replicate_groups"]["off"]["runs"][0]["session_id"] = "not-public"
    elif tamper == "extra_group_field":
        payload["replicate_groups"]["off"]["unverified"] = True
    else:
        payload["replicate_groups"]["off"]["runs"][0]["unverified"] = True
    result = tmp_path / "aggregate.v1.json"
    result.write_text(json.dumps(payload), encoding="utf-8")
    original = verifier.AGGREGATE
    verifier.AGGREGATE = result
    try:
        with pytest.raises(ValueError):
            verifier.verify()
    finally:
        verifier.AGGREGATE = original
