"""Provenance-bound offline reducer for published HBQ polarity/confidence aggregates."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
CONTRACT = json.loads((HERE / "study-contract.json").read_text(encoding="utf-8"))
STATES = ("YES", "NO", "NOT_APPLICABLE", "CANNOT_ASSESS")
REVERSE_NEGATIVE = {"YES": "NO", "NO": "YES", "NOT_APPLICABLE": "NOT_APPLICABLE", "CANNOT_ASSESS": "CANNOT_ASSESS"}


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object: {path.name}")
    return value


def bound_inputs() -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for name, binding in CONTRACT["inputs"].items():
        path = REPO / binding["path"]
        if not path.is_file() or sha256(path) != binding["sha256"]:
            raise ValueError(f"Pinned input drifted: {name}")
        result[name] = {"path": binding["path"], "sha256": binding["sha256"]}
    return result


def conflict_type(positive: str, negative_raw: str) -> str:
    if positive not in STATES or negative_raw not in STATES:
        raise ValueError("Unknown four-state verdict")
    negative = REVERSE_NEGATIVE[negative_raw]
    if positive == "NOT_APPLICABLE" or negative == "NOT_APPLICABLE":
        return "not_applicable_retained" if positive == negative else "not_applicable_mismatch_invalid_excluded"
    if positive == "CANNOT_ASSESS" or negative == "CANNOT_ASSESS":
        return "cannot_assess_retained" if positive == negative else "determinate_cannot_assess_conflict"
    return "determinate_agreement" if positive == negative else "yes_no_contradiction"


def validate_matrix(matrix: Any) -> dict[str, dict[str, int]]:
    if not isinstance(matrix, Mapping) or set(matrix) != set(STATES):
        raise ValueError("A four-state matrix must have exactly four rows")
    clean: dict[str, dict[str, int]] = {}
    for row in STATES:
        values = matrix[row]
        if not isinstance(values, Mapping) or set(values) != set(STATES):
            raise ValueError("A four-state matrix must have exactly four columns")
        clean[row] = {}
        for column in STATES:
            value = values[column]
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ValueError("Four-state matrix counts must be non-negative integers")
            clean[row][column] = value
    return clean


def reduce_matrix(matrix: Any) -> dict[str, Any]:
    clean = validate_matrix(matrix)
    types = {row: {column: conflict_type(row, column) for column in STATES} for row in STATES}
    totals: dict[str, int] = {}
    for row in STATES:
        for column in STATES:
            category = types[row][column]
            totals[category] = totals.get(category, 0) + clean[row][column]
    return {
        "classification": types,
        "counts": {name: totals.get(name, 0) for name in ("determinate_agreement", "yes_no_contradiction", "determinate_cannot_assess_conflict", "not_applicable_retained", "not_applicable_mismatch_invalid_excluded", "cannot_assess_retained")},
        "invalid_excluded_count": totals.get("not_applicable_mismatch_invalid_excluded", 0),
    }


def reducer_policy() -> dict[str, dict[str, str]]:
    return {row: {column: conflict_type(row, column) for column in STATES} for row in STATES}


def _require(source: Mapping[str, Any], *keys: str) -> Any:
    current: Any = source
    for key in keys:
        if not isinstance(current, Mapping) or key not in current:
            raise ValueError(f"Published aggregate lacks required field: {'.'.join(keys)}")
        current = current[key]
    return current


def source_metrics() -> dict[str, Any]:
    bound_inputs()
    polarity = read_object(REPO / CONTRACT["inputs"]["polarity_summary"]["path"])
    confidence = read_object(REPO / CONTRACT["inputs"]["confidence_summary"]["path"])
    disagreement = _require(polarity, "focal_batch1", "disagreement")
    reconstruction = _require(polarity, "reconstruction")
    resampling = _require(confidence, "partial_repeatability_aggregate", "equal_budget_resampling")
    strategies = _require(resampling, "strategies")
    uniform = _require(strategies, "uniform_one_extra_per_leaf")
    low = _require(strategies, "low_initial_confidence_reallocation")
    required_disagreement = {"focal_leaf_count", "matched_pair_count", "matched_pair_disagreement_count", "any_matched_polarity_disagreement_leaf_count", "any_six_observation_instability_leaf_count"}
    if set(disagreement) != required_disagreement or set(reconstruction) != {"canonical_verdict_count", "cell_count"}:
        raise ValueError("Published polarity aggregate schema drifted")
    required_resampling = {"status", "seed", "draws", "total_response_draws_per_simulation", "initial_response_draws", "additional_response_draws", "tie_rule", "strategies", "interpretation"}
    if set(resampling) != required_resampling or set(uniform) != {"mean_proxy_accuracy_on_decided", "mean_decided_leaf_fraction"} or set(low) != {"mean_proxy_accuracy_on_decided", "mean_decided_leaf_fraction", "minus_uniform_proxy_accuracy"}:
        raise ValueError("Published confidence aggregate schema drifted")
    if resampling["additional_response_draws"] != resampling["initial_response_draws"] or resampling["total_response_draws_per_simulation"] != 2 * resampling["initial_response_draws"]:
        raise ValueError("Published confidence control is not equal-cost")
    difference = low["mean_proxy_accuracy_on_decided"] - uniform["mean_proxy_accuracy_on_decided"]
    if abs(difference - low["minus_uniform_proxy_accuracy"]) > 1e-12 or difference >= 0:
        raise ValueError("Published confidence result is not the expected negative control")
    return {
        "polarity": {"focal_leaf_count": disagreement["focal_leaf_count"], "matched_pair_count": disagreement["matched_pair_count"], "matched_pair_disagreement_count": disagreement["matched_pair_disagreement_count"], "any_matched_polarity_disagreement_leaf_count": disagreement["any_matched_polarity_disagreement_leaf_count"], "canonical_verdict_count": reconstruction["canonical_verdict_count"], "published_four_state_matrix": "not_available_in_published_aggregate"},
        "confidence": {"status": resampling["status"], "seed": resampling["seed"], "draws": resampling["draws"], "initial_response_draws": resampling["initial_response_draws"], "additional_response_draws": resampling["additional_response_draws"], "total_response_draws_per_simulation": resampling["total_response_draws_per_simulation"], "uniform_mean_proxy_accuracy_on_decided": uniform["mean_proxy_accuracy_on_decided"], "low_initial_confidence_mean_proxy_accuracy_on_decided": low["mean_proxy_accuracy_on_decided"], "low_minus_uniform_proxy_accuracy": low["minus_uniform_proxy_accuracy"], "result": "negative_low_confidence_reallocation_did_not_beat_uniform"},
    }


def build_summary() -> dict[str, Any]:
    return {
        "format_version": 1,
        "study_id": CONTRACT["study_id"],
        "status": CONTRACT["status"],
        "canonical_hbq_unchanged": True,
        "source_inputs": bound_inputs(),
        "polarity": {**source_metrics()["polarity"], "four_state_policy": reducer_policy()},
        "confidence": source_metrics()["confidence"],
        "limits": CONTRACT["limits"],
        "privacy": CONTRACT["privacy"],
        "production_change": "forbidden",
    }


def output_manifest(summary: Mapping[str, Any]) -> dict[str, Any]:
    rendered = canonical(summary)
    return {"format_version": 1, "study_id": CONTRACT["study_id"], "files": {"summary.json": {"bytes": len(rendered), "sha256": hashlib.sha256(rendered).hexdigest()}}}


def write_output(output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    summary = build_summary()
    payloads = {"summary.json": canonical(summary), "manifest.json": canonical(output_manifest(summary))}
    paths = []
    for name, rendered in payloads.items():
        path = output_dir / name
        if path.exists() and path.read_bytes() != rendered:
            raise ValueError(f"Existing output differs: {name}")
        path.write_bytes(rendered)
        paths.append(path)
    return tuple(paths)  # type: ignore[return-value]
