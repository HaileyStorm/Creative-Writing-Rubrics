#!/usr/bin/env python3
"""Publish sanitized run artifacts, repeatability metrics, and accessible SVGs."""

from __future__ import annotations

import argparse
from collections import Counter
from itertools import combinations
import hashlib
import json
from pathlib import Path
import statistics
from typing import Any, Iterable


HERE = Path(__file__).resolve().parent
CONTRACT = json.loads((HERE / "study-contract.json").read_text(encoding="utf-8"))


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected an object: {path}")
    return value


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def _write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(value)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _numeric(values: list[float]) -> dict[str, Any]:
    differences = [abs(left - right) for left, right in combinations(values, 2)]
    return {
        "values": values,
        "mean": statistics.fmean(values),
        "sample_standard_deviation": statistics.stdev(values) if len(values) > 1 else 0.0,
        "minimum": min(values),
        "maximum": max(values),
        "range": max(values) - min(values),
        "mean_absolute_pairwise_difference": statistics.fmean(differences) if differences else 0.0,
    }


def _alpha_nominal(rows: Iterable[list[str]]) -> float | None:
    rows = list(rows)
    observed_pairs = disagreeing_pairs = 0
    pooled: Counter[str] = Counter()
    for row in rows:
        pooled.update(row)
        for left, right in combinations(row, 2):
            observed_pairs += 1
            disagreeing_pairs += left != right
    if not observed_pairs:
        return None
    observed = disagreeing_pairs / observed_pairs
    total = sum(pooled.values())
    if total < 2:
        return None
    expected = sum(count * (total - count) for count in pooled.values()) / (total * (total - 1))
    if expected == 0:
        return 1.0 if observed == 0 else None
    return 1.0 - observed / expected


def _load_verdicts(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _hbq_metrics(work: Path, arm_id: str, repetitions: int) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    runs = [
        _load_verdicts(work / arm_id / f"run-{number:02d}" / "verdicts.jsonl")
        for number in range(1, repetitions + 1)
    ]
    question_order = [row["question_id"] for row in runs[0]]
    if any([row["question_id"] for row in run] != question_order for run in runs[1:]):
        raise ValueError(f"Question order drifted in {arm_id}")
    per_question: list[dict[str, Any]] = []
    for index, question_id in enumerate(question_order):
        labels = [run[index]["verdict"] for run in runs]
        counts = Counter(labels)
        modal = max(counts.values())
        pair_disagreements = sum(left != right for left, right in combinations(labels, 2))
        per_question.append(
            {
                "question_id": question_id,
                "labels": labels,
                "label_counts": dict(sorted(counts.items())),
                "exact_all_run_agreement": len(counts) == 1,
                "modal_label_proportion": modal / repetitions,
                "pairwise_flip_rate": pair_disagreements / (repetitions * (repetitions - 1) / 2),
            }
        )
    all_labels = [row["verdict"] for run in runs for row in run]
    scores = [
        _read_json(work / arm_id / f"run-{number:02d}" / "score.json")["final_score"]["observed"]
        for number in range(1, repetitions + 1)
    ]
    exact_quotes = total_quotes = 0
    source = (HERE / CONTRACT["source"]["path"]).read_text(encoding="utf-8")
    for run in runs:
        for verdict in run:
            for evidence in verdict.get("evidence", []):
                total_quotes += 1
                exact_quotes += evidence.get("quote", "") in source
    summary = {
        "question_count": len(question_order),
        "exact_all_run_agreement_count": sum(row["exact_all_run_agreement"] for row in per_question),
        "exact_all_run_agreement_rate": statistics.fmean(
            row["exact_all_run_agreement"] for row in per_question
        ),
        "mean_modal_label_proportion": statistics.fmean(
            row["modal_label_proportion"] for row in per_question
        ),
        "mean_pairwise_flip_rate": statistics.fmean(
            row["pairwise_flip_rate"] for row in per_question
        ),
        "nominal_krippendorff_alpha": _alpha_nominal(
            [row["labels"] for row in per_question]
        ),
        "label_prevalence": dict(sorted(Counter(all_labels).items())),
        "observed_score": _numeric(scores),
        "evidence_quote_exact_match": {
            "exact": exact_quotes,
            "total": total_quotes,
            "rate": exact_quotes / total_quotes if total_quotes else None,
        },
    }
    return summary, per_question


def _comparator_metrics(
    work: Path, arm_id: str, repetitions: int
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    runs = [
        _read_json(work / arm_id / f"run-{number:02d}" / "result.json")
        for number in range(1, repetitions + 1)
    ]
    source = (HERE / CONTRACT["source"]["path"]).read_text(encoding="utf-8")
    evidence = []
    for run in runs:
        evidence.extend(run.get("evidence", []))
        evidence.extend(item for dimension in run.get("dimensions", []) for item in dimension["evidence"])
    exact = sum(item["quote"] in source for item in evidence)
    result: dict[str, Any] = {
        "evidence_quote_exact_match": {
            "exact": exact,
            "total": len(evidence),
            "rate": exact / len(evidence) if evidence else None,
        }
    }
    if arm_id == "compact_analytic":
        expected = {
            "narrative_architecture",
            "character_relationships",
            "worldbuilding_integration",
            "prose_voice",
            "emotional_reader_effect",
            "thematic_complexity",
        }
        dimensions: dict[str, list[float]] = {key: [] for key in sorted(expected)}
        for run in runs:
            by_id = {item["dimension_id"]: item["score"] for item in run["dimensions"]}
            if set(by_id) != expected or len(run["dimensions"]) != len(expected):
                raise ValueError("Compact analytic run does not contain each frozen dimension once")
            for dimension_id in dimensions:
                dimensions[dimension_id].append(by_id[dimension_id])
        result["overall_score"] = _numeric([run["overall_score"] for run in runs])
        result["dimension_scores"] = {
            dimension_id: _numeric(values) for dimension_id, values in dimensions.items()
        }
        result["dimension_exact_all_run_agreement_rate"] = statistics.fmean(
            len(set(values)) == 1 for values in dimensions.values()
        )
    else:
        result["score"] = _numeric([run["score"] for run in runs])
    return result, runs


def _reported_provider(path: Path) -> dict[str, Any]:
    response = _read_json(path)
    reported = response.get("provider", {}).get("reported", {})
    return {
        "provider": reported.get("provider"),
        "model": reported.get("model"),
        "reasoning_effort": reported.get("reasoning_effort"),
    }


def _publish_hbq(work: Path, output: Path, arm: dict[str, Any], repetitions: int) -> None:
    arm_output = output / arm["arm_id"]
    provenance = {
        "format_version": 1,
        "arm_id": arm["arm_id"],
        "source_sha256": CONTRACT["source"]["sha256"],
        "bundle_id": arm["bundle_id"],
        "question_count": arm["question_count"],
        "question_id_sequence_sha256": arm["question_id_sequence_sha256"],
        "batch_size": arm["batch_size"],
        "runs": [],
    }
    for number in range(1, repetitions + 1):
        source_dir = work / arm["arm_id"] / f"run-{number:02d}"
        verdicts = _load_verdicts(source_dir / "verdicts.jsonl")
        for verdict in verdicts:
            verdict["run_id"] = f"run-{number:02d}"
        verdict_path = arm_output / f"run-{number:02d}-verdicts.jsonl"
        _write_text(
            verdict_path,
            "".join(
                json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in verdicts
            ),
        )
        score = _read_json(source_dir / "score.json")
        score_path = arm_output / f"run-{number:02d}-score.json"
        _write_json(score_path, score)
        response_paths = sorted((source_dir / "responses").glob("batch-*.json"))
        response_paths = [path for path in response_paths if ".message." not in path.name]
        reported = [_reported_provider(path) for path in response_paths]
        if len({json.dumps(item, sort_keys=True) for item in reported}) != 1:
            raise ValueError(f"Provider identity drifted within {arm['arm_id']} run {number}")
        provenance["runs"].append(
            {
                "run_id": f"run-{number:02d}",
                "reported_provider": reported[0],
                "provider_batches": len(response_paths),
                "verdicts_sha256": _sha256(verdict_path),
                "score_sha256": _sha256(score_path),
                "status": score["status"],
                "hard_gate_status": score["hard_gate_status"],
            }
        )
    _write_json(arm_output / "provenance.json", provenance)


def _publish_comparator(
    work: Path, output: Path, arm: dict[str, Any], repetitions: int
) -> None:
    arm_output = output / arm["arm_id"]
    prompt_path = HERE / arm["prompt"]
    schema_path = HERE / arm["schema"]
    provenance = {
        "format_version": 1,
        "arm_id": arm["arm_id"],
        "source_sha256": CONTRACT["source"]["sha256"],
        "prompt_sha256": _sha256(prompt_path),
        "schema_sha256": _sha256(schema_path),
        "runs": [],
    }
    for number in range(1, repetitions + 1):
        source_dir = work / arm["arm_id"] / f"run-{number:02d}"
        result_path = arm_output / f"run-{number:02d}.json"
        _write_json(result_path, _read_json(source_dir / "result.json"))
        response_path = source_dir / "response.json"
        provenance["runs"].append(
            {
                "run_id": f"run-{number:02d}",
                "reported_provider": _reported_provider(response_path),
                "result_sha256": _sha256(result_path),
            }
        )
    _write_json(arm_output / "provenance.json", provenance)


def _svg_document(title: str, description: str, body: str, *, height: int) -> str:
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="960" height="{height}" viewBox="0 0 960 {height}" role="img" aria-labelledby="title desc">
<title id="title">{title}</title><desc id="desc">{description}</desc>
<style>text{{font-family:system-ui,sans-serif;fill:#172033}}.muted{{fill:#58657a}}.grid{{stroke:#d8dee8;stroke-width:1}}.a{{fill:#536dfe;stroke:#3448c5}}.b{{fill:#e07a5f;stroke:#a84d37}}.c{{fill:#2a9d8f;stroke:#176e64}}.d{{fill:#8d5fd3;stroke:#6640a0}}.line{{fill:none;stroke-width:3}}.dot{{stroke:#fff;stroke-width:2}}</style>
<rect width="960" height="{height}" fill="#fbfcff"/>{body}</svg>'''


def _score_svg(summary: dict[str, Any]) -> str:
    panels = [
        ("HBQ: 24 per batch", summary["arms"]["hbq_batched_24"]["observed_score"]["values"], 0, 100, "a"),
        ("HBQ: one batch", summary["arms"]["hbq_single_batch"]["observed_score"]["values"], 0, 100, "b"),
        ("Compact analytic overall", summary["arms"]["compact_analytic"]["overall_score"]["values"], 1, 5, "c"),
        ("Holistic anchored", summary["arms"]["holistic_anchored"]["score"]["values"], 1, 7, "d"),
    ]
    body = ['<text x="40" y="42" font-size="26" font-weight="700">Five independent scores per method</text>',
            '<text x="40" y="68" class="muted" font-size="15">Panels retain native scales; positions are not cross-scale quality comparisons.</text>']
    for index, (label, values, minimum, maximum, css) in enumerate(panels):
        top = 105 + index * 105
        left, width = 300, 590
        body.append(f'<text x="40" y="{top + 28}" font-size="17" font-weight="600">{label}</text>')
        body.append(f'<line x1="{left}" y1="{top + 25}" x2="{left + width}" y2="{top + 25}" class="grid"/>')
        body.append(f'<text x="{left}" y="{top + 52}" class="muted" font-size="13">{minimum}</text>')
        body.append(f'<text x="{left + width - 18}" y="{top + 52}" class="muted" font-size="13">{maximum}</text>')
        offsets = (-12, -6, 0, 6, 12)
        for run, (value, offset) in enumerate(zip(values, offsets), start=1):
            x = left + (value - minimum) / (maximum - minimum) * width
            body.append(f'<circle cx="{x:.1f}" cy="{top + 25 + offset}" r="7" class="{css} dot"><title>run {run}: {value:.4g}</title></circle>')
        body.append(f'<text x="40" y="{top + 55}" class="muted" font-size="13">SD {statistics.stdev(values):.3f} · range {max(values)-min(values):.3f}</text>')
    return _svg_document(
        "Repeatability score distributions",
        "Four horizontal native-scale panels show all five scores with small vertical offsets so equal values remain visible.",
        "".join(body),
        height=540,
    )


def _leaf_svg(summary: dict[str, Any]) -> str:
    arms = [
        ("24 per batch", summary["arms"]["hbq_batched_24"], "a", 230),
        ("one 178-leaf batch", summary["arms"]["hbq_single_batch"], "b", 570),
    ]
    body = ['<text x="40" y="42" font-size="26" font-weight="700">Leaf-level repeatability</text>',
            '<text x="40" y="68" class="muted" font-size="15">Exact means all five runs returned the same verdict for that leaf.</text>']
    for label, arm, css, x in arms:
        exact = arm["exact_all_run_agreement_count"]
        total = arm["question_count"]
        height = 260 * exact / total
        body.append(f'<text x="{x - 95}" y="110" font-size="18" font-weight="600">{label}</text>')
        body.append(f'<rect x="{x}" y="{400-height:.1f}" width="110" height="{height:.1f}" class="{css}"/>')
        body.append(f'<rect x="{x}" y="140" width="110" height="260" fill="none" class="grid"/>')
        body.append(f'<text x="{x + 55}" y="{425}" text-anchor="middle" font-size="19" font-weight="700">{exact}/{total}</text>')
        body.append(f'<text x="{x + 55}" y="{450}" text-anchor="middle" class="muted" font-size="14">{100*exact/total:.1f}% exact</text>')
        body.append(f'<text x="{x + 55}" y="{475}" text-anchor="middle" class="muted" font-size="14">α {arm["nominal_krippendorff_alpha"]:.3f}</text>')
    return _svg_document(
        "HBQ leaf repeatability",
        "Two bars compare exact all-five-run agreement and nominal Krippendorff alpha.",
        "".join(body),
        height=510,
    )


def _batching_svg(summary: dict[str, Any]) -> str:
    left_values = summary["arms"]["hbq_batched_24"]["observed_score"]["values"]
    right_values = summary["arms"]["hbq_single_batch"]["observed_score"]["values"]
    body = ['<text x="40" y="42" font-size="26" font-weight="700">Batching changes the same rubric’s result</text>',
            '<text x="40" y="68" class="muted" font-size="15">Each line joins the two HBQ scores from the same repetition block.</text>',
            '<text x="190" y="110" text-anchor="middle" font-size="18" font-weight="600">24 per batch</text>',
            '<text x="770" y="110" text-anchor="middle" font-size="18" font-weight="600">one batch</text>']
    minimum = min(left_values + right_values) - 1
    maximum = max(left_values + right_values) + 1
    def y(value: float) -> float:
        return 420 - (value - minimum) / (maximum - minimum) * 270
    for index, (left, right) in enumerate(zip(left_values, right_values), start=1):
        color = "#536dfe" if index % 2 else "#e07a5f"
        body.append(f'<line x1="190" y1="{y(left):.1f}" x2="770" y2="{y(right):.1f}" stroke="{color}" stroke-width="2" opacity=".75"/>')
        body.append(f'<circle cx="190" cy="{y(left):.1f}" r="7" fill="{color}" class="dot"><title>run {index}: {left:.4f}</title></circle>')
        body.append(f'<circle cx="770" cy="{y(right):.1f}" r="7" fill="{color}" class="dot"><title>run {index}: {right:.4f}</title></circle>')
    body.append(f'<text x="480" y="470" text-anchor="middle" class="muted" font-size="14">Mean paired absolute score difference: {statistics.fmean(abs(a-b) for a,b in zip(left_values,right_values)):.3f} points</text>')
    return _svg_document(
        "Paired HBQ batching comparison",
        "Five lines connect each repeated score under 24-leaf and one-batch conditions.",
        "".join(body),
        height=500,
    )


def analyze(work: Path, output: Path) -> None:
    if output.exists():
        raise ValueError(f"Output already exists: {output}")
    repetitions = CONTRACT["repetitions"]
    arms = {arm["arm_id"]: arm for arm in CONTRACT["arms"]}
    for arm_id in arms:
        for number in range(1, repetitions + 1):
            run_dir = work / arm_id / f"run-{number:02d}"
            required = "score.json" if arm_id.startswith("hbq_") else "result.json"
            if not (run_dir / required).is_file():
                raise ValueError(f"Incomplete study run: {arm_id}/run-{number:02d}")
    output.mkdir(parents=True)
    summaries: dict[str, Any] = {}
    leaves: dict[str, list[dict[str, Any]]] = {}
    for arm_id in ("hbq_batched_24", "hbq_single_batch"):
        _publish_hbq(work, output, arms[arm_id], repetitions)
        summaries[arm_id], leaves[arm_id] = _hbq_metrics(work, arm_id, repetitions)
    comparator_runs: dict[str, list[dict[str, Any]]] = {}
    for arm_id in ("compact_analytic", "holistic_anchored"):
        _publish_comparator(work, output, arms[arm_id], repetitions)
        summaries[arm_id], comparator_runs[arm_id] = _comparator_metrics(
            work, arm_id, repetitions
        )
    batched = [
        {row["question_id"]: row["verdict"] for row in _load_verdicts(
            work / "hbq_batched_24" / f"run-{number:02d}" / "verdicts.jsonl"
        )}
        for number in range(1, repetitions + 1)
    ]
    single = [
        {row["question_id"]: row["verdict"] for row in _load_verdicts(
            work / "hbq_single_batch" / f"run-{number:02d}" / "verdicts.jsonl"
        )}
        for number in range(1, repetitions + 1)
    ]
    paired_agreement = [
        statistics.fmean(left[key] == right[key] for key in left)
        for left, right in zip(batched, single)
    ]
    paired_score_differences = [
        left - right
        for left, right in zip(
            summaries["hbq_batched_24"]["observed_score"]["values"],
            summaries["hbq_single_batch"]["observed_score"]["values"],
        )
    ]
    summary = {
        "format_version": 1,
        "study_id": CONTRACT["study_id"],
        "source_sha256": CONTRACT["source"]["sha256"],
        "repetitions_per_arm": repetitions,
        "arms": summaries,
        "cross_batch": {
            "same_run_leaf_agreement": _numeric(paired_agreement),
            "batched_24_minus_single_batch_score": _numeric(paired_score_differences),
            "mean_absolute_score_difference": statistics.fmean(
                abs(value) for value in paired_score_differences
            ),
        },
        "interpretation_limits": CONTRACT["interpretation_limits"],
    }
    _write_json(output / "summary.json", summary)
    _write_json(output / "leaf-repeatability.json", leaves)
    _write_text(output / "score-distributions.svg", _score_svg(summary))
    _write_text(output / "leaf-agreement.svg", _leaf_svg(summary))
    _write_text(output / "batching-comparison.svg", _batching_svg(summary))
    manifest = {
        "format_version": 1,
        "study_id": CONTRACT["study_id"],
        "source_sha256": CONTRACT["source"]["sha256"],
        "files": {
            path.relative_to(output).as_posix(): {
                "bytes": path.stat().st_size,
                "sha256": _sha256(path),
            }
            for path in sorted(output.rglob("*"))
            if path.is_file() and path.name != "manifest.json"
        },
    }
    _write_json(output / "manifest.json", manifest)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--work-dir", required=True, type=Path)
    parser.add_argument("--output-dir", type=Path, default=HERE / "results")
    args = parser.parse_args()
    analyze(args.work_dir.resolve(), args.output_dir.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
