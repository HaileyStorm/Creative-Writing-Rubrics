"""Independent verifier for the provenance-bound four-state diagnostic."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from study import CONTRACT, STATES, REPO, canonical, conflict_type, output_manifest, read_object, sha256


def _bound_inputs() -> dict[str, dict[str, str]]:
    result = {}
    for name, binding in CONTRACT["inputs"].items():
        path = REPO / binding["path"]
        if not path.is_file() or sha256(path) != binding["sha256"]:
            raise ValueError(f"Pinned input drifted: {name}")
        result[name] = {"path": binding["path"], "sha256": binding["sha256"]}
    return result


def _policy() -> dict[str, dict[str, str]]:
    return {row: {column: conflict_type(row, column) for column in STATES} for row in STATES}


def _metrics() -> dict[str, Any]:
    polarity = read_object(REPO / CONTRACT["inputs"]["polarity_summary"]["path"])
    confidence = read_object(REPO / CONTRACT["inputs"]["confidence_summary"]["path"])
    disagreement = polarity["focal_batch1"]["disagreement"]
    reconstruction = polarity["reconstruction"]
    resampling = confidence["partial_repeatability_aggregate"]["equal_budget_resampling"]
    uniform = resampling["strategies"]["uniform_one_extra_per_leaf"]
    low = resampling["strategies"]["low_initial_confidence_reallocation"]
    if resampling["additional_response_draws"] != resampling["initial_response_draws"] or resampling["total_response_draws_per_simulation"] != 2 * resampling["initial_response_draws"]:
        raise ValueError("Confidence control lost equal request cost")
    difference = low["mean_proxy_accuracy_on_decided"] - uniform["mean_proxy_accuracy_on_decided"]
    if abs(difference - low["minus_uniform_proxy_accuracy"]) > 1e-12 or difference >= 0:
        raise ValueError("Confidence negative result drifted")
    return {
        "polarity": {"focal_leaf_count": disagreement["focal_leaf_count"], "matched_pair_count": disagreement["matched_pair_count"], "matched_pair_disagreement_count": disagreement["matched_pair_disagreement_count"], "any_matched_polarity_disagreement_leaf_count": disagreement["any_matched_polarity_disagreement_leaf_count"], "canonical_verdict_count": reconstruction["canonical_verdict_count"], "published_four_state_matrix": "not_available_in_published_aggregate", "four_state_policy": _policy()},
        "confidence": {"status": resampling["status"], "seed": resampling["seed"], "draws": resampling["draws"], "initial_response_draws": resampling["initial_response_draws"], "additional_response_draws": resampling["additional_response_draws"], "total_response_draws_per_simulation": resampling["total_response_draws_per_simulation"], "uniform_mean_proxy_accuracy_on_decided": uniform["mean_proxy_accuracy_on_decided"], "low_initial_confidence_mean_proxy_accuracy_on_decided": low["mean_proxy_accuracy_on_decided"], "low_minus_uniform_proxy_accuracy": low["minus_uniform_proxy_accuracy"], "result": "negative_low_confidence_reallocation_did_not_beat_uniform"},
    }


def verify(output_dir: Path) -> dict[str, Any]:
    summary_path, manifest_path = output_dir / "summary.json", output_dir / "manifest.json"
    if not summary_path.is_file() or not manifest_path.is_file():
        raise ValueError("Missing diagnostic summary or manifest")
    summary = read_object(summary_path)
    manifest = read_object(manifest_path)
    required = {"format_version", "study_id", "status", "canonical_hbq_unchanged", "source_inputs", "polarity", "confidence", "limits", "privacy", "production_change"}
    if set(summary) != required or summary["format_version"] != 1 or summary["study_id"] != CONTRACT["study_id"] or summary["status"] != CONTRACT["status"] or summary["canonical_hbq_unchanged"] is not True or summary["production_change"] != "forbidden" or summary["limits"] != CONTRACT["limits"] or summary["privacy"] != CONTRACT["privacy"]:
        raise ValueError("Diagnostic status, limits, or privacy drifted")
    expected_metrics = _metrics()
    if summary["source_inputs"] != _bound_inputs() or summary["polarity"] != expected_metrics["polarity"] or summary["confidence"] != expected_metrics["confidence"]:
        raise ValueError("Diagnostic metrics or provenance drifted")
    expected_manifest = output_manifest(summary)
    if manifest != expected_manifest or hashlib.sha256(summary_path.read_bytes()).hexdigest() != manifest["files"]["summary.json"]["sha256"] or len(summary_path.read_bytes()) != manifest["files"]["summary.json"]["bytes"]:
        raise ValueError("Output manifest drifted")
    raw = canonical(summary).lower()
    if any(token in raw for token in (b"artifact_id", b"question_id", b"provider_response", b"session_id", b"c:\\\\users\\")):
        raise ValueError("Diagnostic output contains private/raw material")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify the offline aggregate-only polarity/confidence diagnostic.")
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    verify(args.output_dir.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
