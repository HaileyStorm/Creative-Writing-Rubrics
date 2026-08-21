#!/usr/bin/env python3
"""Verify the public established-v4 analysis package."""

from __future__ import annotations

import hashlib
from itertools import combinations
import json
import math
from pathlib import Path
import re
from collections import Counter


HERE = Path(__file__).resolve().parent
MANIFEST = HERE / "publication-manifest.json"
PRIVATE_TEXT = re.compile(r"(?:^|[^A-Za-z])[A-Za-z]:[\\/]|/home/|\\Users\\|session_id|api[_-]?key|OPENAI_API_KEY|NOUS_API_KEY|provider_artifacts|raw_(?:content|response)", re.IGNORECASE)


def _ratio(numerator: int, denominator: int) -> dict:
    return {"numerator": numerator, "denominator": denominator, "proportion": numerator / denominator}


def _score_variability(values: list[float]) -> tuple[float, float, float, float]:
    mean = sum(values) / len(values)
    sample_variance = sum((value - mean) ** 2 for value in values) / (len(values) - 1)
    pairwise = [abs(left - right) for left, right in combinations(values, 2)]
    return mean, math.sqrt(sample_variance), sum(pairwise) / len(pairwise), max(values) - min(values)


def _derived_metrics(summary: dict, leaves: list[dict], repetitions: int, hbq_runtime: dict) -> dict:
    if repetitions != 5:
        raise ValueError("Established-v4 publication requires exactly five repetitions")
    hbq_arm = summary["arms"]["hbq_short_story_batch32"]
    question_ids = [str(item["question_id"]) for item in leaves]
    question_sequence_sha256 = hashlib.sha256(("\n".join(question_ids) + "\n").encode("utf-8")).hexdigest()
    if (
        hbq_arm["question_count"] != hbq_runtime.get("question_count")
        or len(leaves) != hbq_runtime.get("question_count")
        or len(set(question_ids)) != len(question_ids)
        or question_sequence_sha256 != hbq_runtime.get("question_id_sequence_sha256")
        or any(len(item["labels"]) != repetitions for item in leaves)
    ):
        raise ValueError("HBQ leaf publication does not match the frozen question and repetition counts")
    if len(hbq_arm["observed_score"]["values"]) != repetitions or len(hbq_arm["retry_provenance"]["runs"]) != repetitions:
        raise ValueError("HBQ score or retry sequence does not match the frozen repetition count")
    pair_count = math.comb(repetitions, 2)
    agreement: dict[str, dict] = {}
    modal_counts = Counter(max(Counter(item["labels"]).values()) / repetitions for item in leaves)
    agreement["hbq_short_story_batch32"] = {
        "output_units": len(leaves),
        "all_five_agree": _ratio(sum(len(set(item["labels"])) == 1 for item in leaves), len(leaves)),
        "pairwise_repeat_agreement": _ratio(sum(sum(left == right for left, right in combinations(item["labels"], 2)) for item in leaves), len(leaves) * pair_count),
        "modal_judgments": _ratio(sum(max(Counter(item["labels"]).values()) for item in leaves), len(leaves) * repetitions),
        "modal_proportion_distribution": {f"{value:.1f}": modal_counts[value] for value in sorted(modal_counts, reverse=True)},
    }
    maxima = {
        "naplan_narrative_2022": {"audience": 6, "text_structure": 4, "ideas": 5, "character_and_setting": 4, "vocabulary": 5, "cohesion": 4, "paragraphing": 2, "sentence_structure": 6, "punctuation": 5, "spelling": 6},
        "cambridge_igcse_0500_p2_mj_2024": {"content_and_structure": 16, "style_and_accuracy": 24},
        "oregon_narrative_2017": {"ideas_and_content": 6, "organization": 6, "voice": 6, "word_choice": 6, "sentence_fluency": 6, "conventions": 6},
    }
    for arm_id in maxima:
        arm = summary["arms"][arm_id]
        criteria_by_id = arm["criteria"]
        if set(criteria_by_id) != set(maxima[arm_id]) or arm.get("criterion_count") != len(maxima[arm_id]):
            raise ValueError(f"{arm_id} publication does not contain the exact frozen criteria")
        criteria = list(criteria_by_id.values())
        if (
            len(arm["total_score"]["values"]) != repetitions
            or len(arm["retry_provenance"]["runs"]) != repetitions
            or any(len(item["values"]) != repetitions for item in criteria)
        ):
            raise ValueError(f"{arm_id} publication does not match the frozen repetition count")
        agreement[arm_id] = {
            "output_units": len(criteria),
            "all_five_agree": _ratio(sum(len(set(item["values"])) == 1 for item in criteria), len(criteria)),
            "pairwise_repeat_agreement": _ratio(sum(sum(left == right for left, right in combinations(item["values"], 2)) for item in criteria), len(criteria) * pair_count),
            "modal_judgments": _ratio(sum(max(Counter(item["values"]).values()) for item in criteria), len(criteria) * repetitions),
        }
    widths = {
        "hbq_short_story_batch32": (0, 100),
        "naplan_narrative_2022": (0, 47),
        "cambridge_igcse_0500_p2_mj_2024": (0, 40),
        "oregon_narrative_2017": (6, 36),
    }
    variability = {}
    for arm_id, (minimum, maximum) in widths.items():
        arm = summary["arms"][arm_id]
        numeric = arm.get("observed_score", arm.get("total_score"))
        _, sample_standard_deviation, mean_absolute_pairwise_difference, score_range = _score_variability(
            numeric["values"]
        )
        width = maximum - minimum
        variability[arm_id] = {
            "scale_minimum": minimum,
            "scale_maximum": maximum,
            "scale_width": width,
            "sample_standard_deviation_percent_of_width": sample_standard_deviation / width * 100,
            "mean_absolute_pairwise_difference_percent_of_width": mean_absolute_pairwise_difference / width * 100,
            "range_percent_of_width": score_range / width * 100,
        }
    hbq_values = summary["arms"]["hbq_short_story_batch32"]["observed_score"]["values"]
    hbq_mean, _, _, _ = _score_variability(hbq_values)
    ceilings = {
        "hbq_short_story_batch32": {
            "total_ceiling_hits": sum(value == 100 for value in hbq_values),
            "total_observations": len(hbq_values),
            "mean_total_gap": round(100 - hbq_mean, 4),
            "criterion_ceiling": None,
            "criterion_note": "Binary leaf labels are not ordinal criterion scores.",
        }
    }
    for arm_id, criterion_maxima in maxima.items():
        arm = summary["arms"][arm_id]
        total_maximum = widths[arm_id][1]
        values = arm["total_score"]["values"]
        criterion_values = [(value, criterion_maxima[name]) for name, item in arm["criteria"].items() for value in item["values"]]
        ceilings[arm_id] = {
            "total_ceiling_hits": sum(value == total_maximum for value in values),
            "total_observations": len(values),
            "mean_total_gap": sum(total_maximum - value for value in values) / len(values),
            "criterion_ceiling_hits": sum(value == maximum for value, maximum in criterion_values),
            "criterion_observations": len(criterion_values),
            "summed_criterion_gap": sum(maximum - value for value, maximum in criterion_values),
        }
    conformance = {}
    hbq_retry = summary["arms"]["hbq_short_story_batch32"]["retry_provenance"]
    hbq_runs = hbq_retry["runs"]
    hbq_rejected = sum(run["rejected_attempt_count"] for run in hbq_runs)
    hbq_recovered = sum(run["recovered_acceptance_count"] for run in hbq_runs)
    hbq_repairs = sum(run["normalization_repair_count"] for run in hbq_runs)
    if (
        hbq_retry["accepted_run_count"] != len(hbq_runs)
        or hbq_retry["rejected_attempt_count"] != hbq_rejected
        or hbq_retry["rejected_run_count"] != sum(run["rejected_attempt_count"] > 0 for run in hbq_runs)
        or hbq_retry["recovered_acceptance_count"] != hbq_recovered
        or hbq_retry["normalization_repair_count"] != hbq_repairs
    ):
        raise ValueError("HBQ retry aggregates do not match their per-run records")
    conformance["hbq_short_story_batch32"] = {
        "accepted_provider_calls": sum(run["accepted_checkpoint_count"] for run in hbq_runs),
        "rejected_provider_calls": hbq_rejected,
        "deterministic_quote_to_summary_repairs": hbq_repairs,
        "additional_provider_calls": hbq_rejected,
    }
    for arm_id in maxima:
        retry = summary["arms"][arm_id]["retry_provenance"]
        runs = retry["runs"]
        attempt_count = sum(run["attempt_count"] for run in runs)
        rejected_count = sum(run["rejected_attempt_count"] for run in runs)
        failed_count = sum(run["failed_attempt_count"] for run in runs)
        semantic_count = sum(run["semantic_rejection_count"] for run in runs)
        if (
            retry["attempt_count"] != attempt_count
            or retry["rejected_attempt_count"] != rejected_count
            or retry["failed_attempt_count"] != failed_count
            or retry["semantic_rejection_count"] != semantic_count
        ):
            raise ValueError(f"{arm_id} retry aggregates do not match their per-run records")
        conformance[arm_id] = {
            "accepted_provider_calls": len(runs),
            "rejected_provider_calls": rejected_count,
            "deterministic_quote_to_summary_repairs": 0,
            "additional_provider_calls": attempt_count - len(runs),
        }
    return {"agreement": agreement, "scale_width_normalized_variability": variability, "ceiling_exposure": ceilings, "conformance": conformance}


def verify(root: Path = HERE) -> dict:
    manifest_path = root / MANIFEST.name
    manifest_text = manifest_path.read_text(encoding="utf-8")
    if PRIVATE_TEXT.search(manifest_text):
        raise ValueError("Publication manifest contains a private runtime field")
    manifest = json.loads(manifest_text)
    if manifest.get("format_version") != 1 or not isinstance(manifest.get("files"), dict):
        raise ValueError("Publication manifest is malformed")
    expected_chart_transformation = {
        "score-distributions.svg": {
            "kind": "native_axis_correction",
            "arm_id": "oregon_narrative_2017",
            "source_axis_minimum": 0,
            "published_axis_minimum": 6,
            "axis_maximum": 36,
        }
    }
    if manifest.get("publication_transformations") != expected_chart_transformation:
        raise ValueError("Publication chart transformation is missing or changed")
    expected_files = set(manifest["files"]) | {MANIFEST.name, Path(__file__).name}
    expected_entries = set(expected_files)
    for relative in expected_files:
        parent = Path(relative).parent
        while parent != Path("."):
            expected_entries.add(parent.as_posix())
            parent = parent.parent
    python_sources = {Path(relative) for relative in expected_files if Path(relative).suffix == ".py"}

    def regenerable_cache_entry(path: Path) -> bool:
        relative = path.relative_to(root)
        if path.is_dir():
            return relative.name == "__pycache__" and any(source.parent == relative.parent for source in python_sources)
        if not path.is_file() or relative.parent.name != "__pycache__" or relative.suffix != ".pyc":
            return False
        source_parent = relative.parent.parent
        return any(source.parent == source_parent and relative.name.startswith(f"{source.stem}.") for source in python_sources)

    actual_entries = {path.relative_to(root).as_posix() for path in root.rglob("*") if not regenerable_cache_entry(path)}
    if actual_entries != expected_entries:
        raise ValueError(f"Results directory contains unexpected or missing entries: {sorted(actual_entries ^ expected_entries)}")
    for relative, expected in manifest["files"].items():
        path = root / relative
        content = path.read_bytes()
        if not path.is_file() or len(content) != expected.get("bytes") or hashlib.sha256(content).hexdigest() != expected.get("sha256"):
            raise ValueError(f"Published artifact does not match its manifest: {relative}")
        if PRIVATE_TEXT.search(content.decode("utf-8")):
            raise ValueError(f"Published artifact contains a private runtime field: {relative}")
    study_root = root.parent
    contract_path = study_root / "study-contract.json"
    contract_bytes = contract_path.read_bytes()
    if hashlib.sha256(contract_bytes).hexdigest() != manifest.get("protocol_contract_sha256"):
        raise ValueError("Parent study contract does not match the publication manifest")
    contract = json.loads(contract_bytes)
    source_spec = contract.get("source")
    if contract.get("study_id") != manifest.get("study_id") or not isinstance(source_spec, dict) or source_spec.get("publication_authorized") is not True:
        raise ValueError("Parent study contract does not authorize this publication")
    relative_source = Path(str(source_spec.get("path", "")))
    if relative_source.is_absolute():
        raise ValueError("Published source path must be repository-relative")
    source = (study_root / relative_source).resolve()
    repository = study_root.parents[2].resolve()
    try:
        source.relative_to(repository)
    except ValueError as exc:
        raise ValueError("Published source path escapes the repository") from exc
    source_content = source.read_bytes()
    if len(source_content) != source_spec.get("bytes") or hashlib.sha256(source_content).hexdigest() != source_spec.get("sha256"):
        raise ValueError("Authorized published source does not match the frozen contract")
    summary = json.loads((root / "summary.json").read_text(encoding="utf-8"))
    provenance = json.loads((root / "provenance.json").read_text(encoding="utf-8"))
    leaves = json.loads((root / "hbq-leaf-repeatability.json").read_text(encoding="utf-8"))["leaves"]
    derived = json.loads((root / "derived-repeatability.json").read_text(encoding="utf-8"))
    if summary.get("study_id") != manifest.get("study_id") or summary.get("protocol_contract_sha256") != manifest.get("protocol_contract_sha256"):
        raise ValueError("Summary does not bind to the publication manifest")
    if provenance.get("study_id") != manifest.get("study_id") or provenance.get("protocol_contract_sha256") != manifest.get("protocol_contract_sha256"):
        raise ValueError("Provenance does not bind to the publication manifest")
    if derived.get("study_id") != manifest.get("study_id") or derived.get("protocol_contract_sha256") != manifest.get("protocol_contract_sha256"):
        raise ValueError("Derived metrics do not bind to the publication manifest")
    recomputed = _derived_metrics(summary, leaves, contract.get("repetitions"), contract.get("hbq_runtime", {}))
    expected_derived_keys = {"format_version", "study_id", "protocol_contract_sha256", *recomputed}
    if derived.get("format_version") != 1 or set(derived) != expected_derived_keys:
        raise ValueError("Derived metrics have an unexpected format or section")
    for section, expected in recomputed.items():
        actual = derived.get(section)
        if section == "scale_width_normalized_variability":
            if not isinstance(actual, dict) or set(actual) != set(expected) or any(
                not isinstance(actual[arm], dict)
                or set(actual[arm]) != set(values)
                or any(
                    not math.isclose(actual[arm][key], value, rel_tol=0, abs_tol=1e-12)
                    if isinstance(value, float)
                    else actual[arm][key] != value
                    for key, value in values.items()
                )
                for arm, values in expected.items()
            ):
                raise ValueError("Scale-width-normalized variability does not match the raw summary")
        elif actual != expected:
            raise ValueError(f"Derived {section} does not match the raw results")
    oregon_scale = recomputed["scale_width_normalized_variability"]["oregon_narrative_2017"]
    axis_marker = (
        f'<text x="320" y="455" class="muted" font-size="13">{oregon_scale["scale_minimum"]}</text>'
        f'<text x="845" y="455" class="muted" font-size="13">{oregon_scale["scale_maximum"]}</text>'
    )
    if axis_marker not in (root / "score-distributions.svg").read_text(encoding="utf-8"):
        raise ValueError("Published Oregon chart axis does not match its native scale")
    return manifest


if __name__ == "__main__":
    verified = verify()
    print(f"Verified {len(verified['files'])} public established-v4 artifacts.")
