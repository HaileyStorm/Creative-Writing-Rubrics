"""Offline aggregate analysis for the sealed HANNA polarity pilot."""
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import os
from collections import defaultdict
from pathlib import Path
import statistics
import sys
import tempfile
from typing import Any, Mapping, Sequence

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
CONTRACT_PATH = HERE / "study-contract.json"
STAGE_FILES = {
    "stage1": ("stage1-evidence.json", "stage1-raw-evidence.json"),
    "stage2": ("stage2-evidence.json", "stage2-raw-evidence.json"),
    "stage3": ("stage3-evidence.json", "stage3-raw-evidence.json"),
}
FOCAL = ("single_positive_batch1", "single_negative_batch1")
GLOBAL = ("global_positive_batch32", "global_negative_batch32")
ASSESSED = {"YES", "NO"}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path.name}")
    return value


def contract() -> dict[str, Any]:
    value = read_json(CONTRACT_PATH)
    required = {"format_version", "study_id", "kind", "source_study_id", "scope", "inputs", "reporting"}
    if set(value) != required or value["format_version"] != 1 or value["study_id"] != "hbq-hanna-polarity-paired-analysis-v1":
        raise ValueError("Analysis contract drifted")
    if value["reporting"] != {"raw_prose": "forbidden", "raw_prompt": "forbidden", "raw_provider_responses": "forbidden", "recommendation": None, "production_change": "forbidden"}:
        raise ValueError("Analysis reporting boundary drifted")
    return value


def bound(path: Path, expected: str) -> dict[str, Any]:
    if not path.is_file() or sha256(path) != expected:
        raise ValueError(f"Bound input drifted: {path.name}")
    return {"bytes": path.stat().st_size, "sha256": expected}


def load_pilot(root: Path, expected: Mapping[str, str]) -> Any:
    for name, digest in expected.items():
        bound(root / name, digest)
    if str(REPO / "src") not in sys.path:
        sys.path.insert(0, str(REPO / "src"))
    specification = importlib.util.spec_from_file_location("hbq_hanna_polarity_paired_analysis_pilot", root / "study.py")
    if specification is None or specification.loader is None:
        raise ValueError("Cannot load bound pilot")
    module = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = module
    specification.loader.exec_module(module)
    return module


def bind_stage(name: str, work: Path, private: Path, expected: Mapping[str, str]) -> dict[str, Any]:
    evidence_name, raw_name = STAGE_FILES[name]
    files = {
        "plan": bound(work / "pilot-contract.json", str(expected["plan"])),
        "evidence": bound(work / evidence_name, str(expected["evidence"])),
        "raw": bound(private / raw_name, str(expected["raw"])),
    }
    return files


def canonical_cells(pilot: Any, stage1_work: Path, stage3_private: Path) -> dict[str, list[dict[str, Any]]]:
    plan = pilot.load_plan(stage1_work)
    rows = read_json(stage3_private / "stage3-raw-evidence.json").get("rows")
    if not isinstance(rows, list) or len(rows) != 11:
        raise ValueError("Stage 3 raw evidence does not contain the eleven non-parent cells")
    result = pilot.verify_evidence(plan, rows)
    if len(result) != 12 or sum(len(value) for value in result.values()) != 1236:
        raise ValueError("Pilot evidence does not reconstruct 12 cells and 1,236 verdicts")
    return result


def cell_rows(cells: Mapping[str, Sequence[Mapping[str, Any]]], condition: str, repetition: int) -> list[Mapping[str, Any]]:
    value = cells.get(f"{condition}:{repetition}")
    if not isinstance(value, Sequence):
        raise ValueError("Expected sealed condition/repetition cell is missing")
    return list(value)


def cell_summary(rows: Sequence[Mapping[str, Any]], mappings: Mapping[str, Sequence[str]]) -> dict[str, Any]:
    by_id = {str(row["question_id"]): row for row in rows}
    assessed = [row for row in rows if row["verdict"] in ASSESSED]
    dimensions: dict[str, float] = {}
    for dimension, identifiers in mappings.items():
        values = [by_id[item]["verdict"] == "YES" for item in identifiers if item in by_id and by_id[item]["verdict"] in ASSESSED]
        if not values:
            raise ValueError("Mapped dimension has no assessed observations")
        dimensions[str(dimension)] = statistics.fmean(values)
    return {
        "yes_fraction": statistics.fmean(row["verdict"] == "YES" for row in assessed),
        "coverage": len(assessed) / len(rows),
        "mean_confidence": statistics.fmean(float(row["confidence"]) for row in rows),
        "dimension_means": dimensions,
    }


def mode_summary(cells: Mapping[str, Sequence[Mapping[str, Any]]], conditions: Sequence[str], mappings: Mapping[str, Sequence[str]]) -> dict[str, Any]:
    repetitions = [cell_summary(cell_rows(cells, condition, repetition), mappings) for condition in conditions for repetition in (1, 2, 3)]
    return {
        "cell_count": len(repetitions),
        "mean_yes_fraction": statistics.fmean(value["yes_fraction"] for value in repetitions),
        "mean_coverage": statistics.fmean(value["coverage"] for value in repetitions),
        "mean_confidence": statistics.fmean(value["mean_confidence"] for value in repetitions),
        "dimension_means": {dimension: statistics.fmean(value["dimension_means"][dimension] for value in repetitions) for dimension in mappings},
    }


def stability(cells: Mapping[str, Sequence[Mapping[str, Any]]], conditions: Sequence[str]) -> dict[str, Any]:
    observations: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for condition in conditions:
        for repetition in (1, 2, 3):
            for row in cell_rows(cells, condition, repetition):
                observations[str(row["question_id"])].append(row)
    if not observations:
        raise ValueError("No observations for stability analysis")
    stable, unstable = [], []
    for rows in observations.values():
        target = stable if len({row["verdict"] for row in rows}) == 1 else unstable
        target.extend(float(row["confidence"]) for row in rows)
    return {
        "leaf_count": len(observations),
        "stable_leaf_count": sum(len({row["verdict"] for row in rows}) == 1 for rows in observations.values()),
        "unstable_leaf_count": sum(len({row["verdict"] for row in rows}) != 1 for rows in observations.values()),
        "stable_confidence_mean": statistics.fmean(stable) if stable else None,
        "unstable_confidence_mean": statistics.fmean(unstable) if unstable else None,
    }


def focal_disagreement(cells: Mapping[str, Sequence[Mapping[str, Any]]]) -> dict[str, int]:
    positive = {str(row["question_id"]) for row in cell_rows(cells, FOCAL[0], 1)}
    negative = {str(row["question_id"]) for row in cell_rows(cells, FOCAL[1], 1)}
    identifiers = sorted(positive & negative)
    if len(identifiers) != 27:
        raise ValueError("Focal comparison does not contain 27 matched leaves")
    any_disagreement = 0
    any_matrix_instability = 0
    matched_disagreement = 0
    for identifier in identifiers:
        values = []
        matched_values = []
        for repetition in (1, 2, 3):
            left = {str(row["question_id"]): row for row in cell_rows(cells, FOCAL[0], repetition)}[identifier]["verdict"]
            right = {str(row["question_id"]): row for row in cell_rows(cells, FOCAL[1], repetition)}[identifier]["verdict"]
            values.extend((left, right))
            matched_values.append(left != right)
            matched_disagreement += left != right
        any_disagreement += any(matched_values)
        any_matrix_instability += len(set(values)) > 1
    return {"focal_leaf_count": len(identifiers), "any_matched_polarity_disagreement_leaf_count": any_disagreement, "matched_pair_disagreement_count": matched_disagreement, "matched_pair_count": len(identifiers) * 3, "any_six_observation_instability_leaf_count": any_matrix_instability}


def hanna_means(csv_path: Path, plan: Mapping[str, Any]) -> dict[str, dict[str, float]]:
    with csv_path.open(encoding="utf-8", newline="") as handle:
        rows = [row for row in csv.DictReader(handle) if row.get("Story ID") == "225"]
    dimensions = ("Relevance", "Coherence", "Empathy", "Surprise", "Engagement", "Complexity")
    if len(rows) != 3 or any(set(row) < {"Story", "Prompt", *dimensions} for row in rows):
        raise ValueError("Pinned HANNA item 225 rows are malformed")
    parent = plan["parent"]["parent_cell"]
    if any(
        hashlib.sha256(row["Story"].encode("utf-8")).hexdigest() != parent["artifact"]["sha256"]
        or hashlib.sha256(row["Prompt"].encode("utf-8")).hexdigest() != parent["contexts"][0]["sha256"]
        for row in rows
    ):
        raise ValueError("HANNA item 225 does not match the sealed pilot parent")
    ratings: dict[str, list[float]] = {}
    for dimension in dimensions:
        try:
            values = [float(row[dimension]) for row in rows]
        except (TypeError, ValueError) as exc:
            raise ValueError("Published HANNA rating is malformed") from exc
        if any(value not in {1.0, 2.0, 3.0, 4.0, 5.0} for value in values):
            raise ValueError("Published HANNA rating is malformed")
        ratings[dimension] = values
    means = {dimension: statistics.fmean(values) for dimension, values in ratings.items()}
    return {
        "primary_endpoint_aligned": {dimension: (value - 1) / 4 for dimension, value in means.items()},
        "sensitivity_divide_by_max": {dimension: value / 5 for dimension, value in means.items()},
    }


def build_summary(cells: Mapping[str, Sequence[Mapping[str, Any]]], mappings: Mapping[str, Sequence[str]], human: Mapping[str, Mapping[str, float]], bindings: Mapping[str, Any]) -> dict[str, Any]:
    focal = {"positive": mode_summary(cells, (FOCAL[0],), mappings), "negative": mode_summary(cells, (FOCAL[1],), mappings), "paired": mode_summary(cells, FOCAL, mappings)}
    errors = {
        normalization: {
            name: statistics.fmean(abs(float(value["dimension_means"][dimension]) - float(targets[dimension])) for dimension in targets)
            for name, value in focal.items()
        }
        for normalization, targets in human.items()
    }
    return {
        "format_version": 1,
        "study_id": contract()["study_id"],
        "scope": "one_story_descriptive_only",
        "evidence_binding": bindings,
        "reconstruction": {"cell_count": len(cells), "canonical_verdict_count": sum(len(value) for value in cells.values())},
        "focal_batch1": {**focal, "disagreement": focal_disagreement(cells), "stability": {name: stability(cells, conditions) for name, conditions in {"positive": (FOCAL[0],), "negative": (FOCAL[1],), "paired": FOCAL}.items()}},
        "global_batch32_controls": {name: mode_summary(cells, (name,), mappings) for name in GLOBAL},
        "hanna_dimension_targets": {name: dict(values) for name, values in human.items()},
        "mean_absolute_dimension_error": errors,
        "interpretation_limits": [
            "Descriptive one-story analysis; no production recommendation.",
            "Same-polarity batch-32 controls are not equal-call-budget comparisons.",
            "The focal paired average did not beat focal positive on mean absolute dimension error for this story.",
            "That ordering is unchanged under endpoint-aligned and divide-by-maximum HANNA normalization.",
            "Paired averaging remains a hypothesis for separately preregistered, held-out evaluation.",
        ],
        "recommendation": None,
        "production_change": "forbidden",
    }


def write_output(output: Path, summary: Mapping[str, Any]) -> None:
    output.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    manifest = {
        "format_version": 1,
        "study_id": summary["study_id"],
        "analysis": {name: bound(path, sha256(path)) for name, path in (("analyze.py", HERE / "analyze.py"), ("study-contract.json", CONTRACT_PATH))},
        "files": {"summary.json": {"bytes": len(rendered.encode("utf-8")), "sha256": hashlib.sha256(rendered.encode("utf-8")).hexdigest()}},
    }
    for name, value in (("summary.json", rendered), ("manifest.json", json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n")):
        target = output / name
        if target.exists() and target.read_text(encoding="utf-8") != value:
            raise ValueError(f"Immutable output drifted: {name}")
        if not target.exists():
            descriptor, temporary = tempfile.mkstemp(dir=output, prefix=f".{name}.", suffix=".tmp")
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(value)
                handle.flush()
                os.fsync(handle.fileno())
            Path(temporary).replace(target)


def analyze(*, pilot_root: Path, stage1_work: Path, stage1_private: Path, stage2_work: Path, stage2_private: Path, stage3_work: Path, stage3_private: Path, parent_verdicts: Path, hanna_csv: Path, output: Path) -> dict[str, Any]:
    output = output.resolve()
    inputs = (pilot_root, stage1_work, stage1_private, stage2_work, stage2_private, stage3_work, stage3_private, parent_verdicts, hanna_csv)
    for source in inputs:
        resolved = source.resolve()
        if output == resolved or output in resolved.parents or resolved in output.parents:
            raise ValueError("Aggregate output must be disjoint from every bound input")
    spec = contract()
    bindings = {
        "pilot": {name: bound(pilot_root / name, digest) for name, digest in spec["inputs"]["pilot"].items()},
        "parent_verdicts": bound(parent_verdicts, spec["inputs"]["parent_verdicts"]),
        "hanna_csv": bound(hanna_csv, spec["inputs"]["hanna_csv"]),
        "stages": {"stage1": bind_stage("stage1", stage1_work, stage1_private, spec["inputs"]["stages"]["stage1"]), "stage2": bind_stage("stage2", stage2_work, stage2_private, spec["inputs"]["stages"]["stage2"]), "stage3": bind_stage("stage3", stage3_work, stage3_private, spec["inputs"]["stages"]["stage3"])},
    }
    pilot = load_pilot(pilot_root, spec["inputs"]["pilot"])
    plan = pilot.load_plan(stage1_work)
    cells = canonical_cells(pilot, stage1_work, stage3_private)
    summary = build_summary(cells, pilot.mapping_sets(), hanna_means(hanna_csv, plan), bindings)
    write_output(output, summary)
    return summary


def argument(name: str, environment: str) -> dict[str, Any]:
    return {"dest": name, "type": Path, "default": Path(os.environ[environment]) if environment in os.environ else None, "required": environment not in os.environ}


def main() -> int:
    parser = argparse.ArgumentParser()
    for flag, name, environment in (("--pilot-root", "pilot_root", "HBQ_HANNA_PILOT_ROOT"), ("--stage1-work", "stage1_work", "HBQ_HANNA_STAGE1_WORK"), ("--stage1-private", "stage1_private", "HBQ_HANNA_STAGE1_PRIVATE"), ("--stage2-work", "stage2_work", "HBQ_HANNA_STAGE2_WORK"), ("--stage2-private", "stage2_private", "HBQ_HANNA_STAGE2_PRIVATE"), ("--stage3-work", "stage3_work", "HBQ_HANNA_STAGE3_WORK"), ("--stage3-private", "stage3_private", "HBQ_HANNA_STAGE3_PRIVATE"), ("--parent-verdicts", "parent_verdicts", "HBQ_HANNA_PARENT_VERDICTS"), ("--hanna-csv", "hanna_csv", "HBQ_HANNA_CSV"), ("--output", "output", "HBQ_HANNA_OUTPUT")):
        parser.add_argument(flag, **argument(name, environment))
    args = parser.parse_args()
    analyze(**{name: Path(value).resolve() for name, value in vars(args).items()})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
