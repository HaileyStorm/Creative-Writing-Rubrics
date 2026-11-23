"""Provider-free projection for correcting HANNA repeatability score summaries.

This separate projection does not modify historical reports or certify their
inputs. Callers must authenticate the report and its original run provenance.
"""

from __future__ import annotations

import math
import statistics
import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


def corrected_score_summary(report: dict[str, Any]) -> dict[str, Any]:
    """Recompute score variation, explicitly retaining insufficient observations."""
    planned = report.get("repetitions")
    items = report.get("per_item")
    if type(planned) is not int or planned < 2 or not isinstance(items, list) or not items:
        raise ValueError("A nonempty item list and at least two planned repetitions are required")
    if type(report.get("item_count")) is not int or report["item_count"] != len(items):
        raise ValueError("Item count does not match the input report")

    result = []
    ids: set[str] = set()
    for item in items:
        if not isinstance(item, dict) or not isinstance(item.get("item_id"), str):
            raise ValueError("Each item must have a string identity")
        item_id = item["item_id"]
        if not item_id or item_id in ids:
            raise ValueError("Item identities must be nonempty and unique")
        ids.add(item_id)
        score = item.get("score")
        values = score.get("values") if isinstance(score, dict) else None
        if not isinstance(values, list) or len(values) > planned:
            raise ValueError("Score values must be a list no longer than the planned repetitions")
        if any(type(v) not in (int, float) or not 0 <= v <= 100 or not math.isfinite(v) for v in values):
            raise ValueError("Scores must be finite non-boolean values on the 0..100 scale")
        count = len(values)
        result.append({
            "item_id": item_id,
            "observed_count": count,
            "unscored_or_unobserved_count": planned - count,
            "complete": count == planned,
            "sample_standard_deviation": statistics.stdev(values) if count >= 2 else None,
            "range": max(values) - min(values) if count >= 2 else None,
        })

    deviations = [row["sample_standard_deviation"] for row in result if row["sample_standard_deviation"] is not None]
    ranges = [row["range"] for row in result if row["range"] is not None]
    return {
        "schema": "hanna-repeatability-score-summary-v2",
        "planned_repetitions_per_item": planned,
        "item_count": len(result),
        "complete_item_count": sum(row["complete"] for row in result),
        "insufficient_score_item_count": sum(row["observed_count"] < 2 for row in result),
        "per_item": result,
        "defined_only_summary": {
            "item_count": len(deviations),
            "mean_sample_standard_deviation": statistics.fmean(deviations) if deviations else None,
            "minimum_sample_standard_deviation": min(deviations) if deviations else None,
            "maximum_sample_standard_deviation": max(deviations) if deviations else None,
            "mean_range": statistics.fmean(ranges) if ranges else None,
            "maximum_range": max(ranges) if ranges else None,
        },
    }


def project_document(raw: bytes) -> dict[str, Any]:
    """Project a retained repeatability.json or v3 summary.json without writes."""
    def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate JSON key")
            result[key] = value
        return result

    def reject_constant(value: str) -> None:
        raise ValueError(f"Non-finite JSON number: {value}")

    document = json.loads(raw.decode("utf-8"), object_pairs_hook=unique_object, parse_constant=reject_constant)
    if not isinstance(document, dict):
        raise ValueError("Report must be a JSON object")
    if "repeatability" in document:
        if document.get("format_version") != 3 or document.get("phase") != "repeatability":
            raise ValueError("Expected a v3 repeatability summary")
        report = document["repeatability"]
    else:
        report = document
    if not isinstance(report, dict):
        raise ValueError("Repeatability report must be a JSON object")
    return {
        "source_sha256": hashlib.sha256(raw).hexdigest(),
        "source_provenance_verified": False,
        "scope": "score_variation_only; original_report_unchanged",
        "corrected_score_summary": corrected_score_summary(report),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Read a retained HANNA report and emit a separate score-variation projection")
    parser.add_argument("input", type=Path, help="Existing repeatability.json or v3 summary.json")
    args = parser.parse_args()
    result = project_document(args.input.read_bytes())
    json.dump(result, sys.stdout, sort_keys=True, allow_nan=False, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
