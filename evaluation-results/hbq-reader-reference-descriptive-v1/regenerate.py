"""Project the exact reviewed reader aggregate; no raw-data replay or scoring."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re

INPUT_SHA256 = "589fe871852a25792bee3738337474f0fbd23ef4258764843ebcd1cc52f65e90"


def checked(path: Path) -> dict:
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != INPUT_SHA256:
        raise ValueError("The exact reviewed reader-results aggregate is required")
    return json.loads(raw)


def commitment(reference: dict) -> dict:
    return {key: reference[key] for key in ("sha256", "bytes")}


def project(source: dict) -> dict:
    """Copy reported measurements and denominators without new inference."""
    dryad = source["dryad"]
    kyoto = source["kyoto_qsf12"]
    contrasts = {}
    for name, row in dryad["contrast_results"].items():
        contrasts[name] = {key: row[key] for key in (
            "arm", "axis", "kind", "planned", "available", "missing", "point",
            "HBQ_rho_on_common_set", "comparator_rho_on_common_set",
            "arm_dependent_attrition", "interpretation", "inconclusive_reasons")}
        contrasts[name]["conditional_story_bootstrap"] = {
            key: row["conditional_story_bootstrap"][key]
            for key in ("replicates", "undefined_draws")}
    targets = {}
    for axis, row in kyoto["targets"].items():
        targets[axis] = {key: row[key] for key in (
            "planned_stories", "available_story_means", "missing_story_means", "states",
            "missing_raters", "excluded_raters")}
        targets[axis]["recorded_valid_responses"] = row["valid_raters"]
        targets[axis]["distinct_participants_established"] = False
    differences = {}
    for family in ("hbq_ttcw_primary_differences", "ladder_primary_differences"):
        differences[family] = {
            name: {key: row[key] for key in (
                "primary_fixed12", "secondary_exact_common_diagnostic",
                "arm_dependent_attrition", "attrition_inconclusive", "interval_estimated")}
            for name, row in kyoto[family].items()}
    return {
        "schema_version": 1,
        "policy": "retained_reader_aggregate_only_descriptive_synthesis_v1",
        "input_aggregate_sha256": INPUT_SHA256,
        "source_commitments": {name: commitment(ref) for name, ref in source["sources"].items()},
        "dryad": {
            "planned_stories": dryad["planned"],
            "planned_native_packets": sum(row["planned_packets"] for row in dryad["arms"].values()),
            "native_admitted_packets": dryad["native_admitted"],
            "hbq_complete_stories": dryad["hbq_complete"],
            "fixed_all_five_numeric_common_stories": dryad["common_five"],
            "target_use": dryad["target_use"],
            "arms": dryad["arms"],
            "fixed_all_five_common_distributions": dryad["common_distributions"],
            "fixed_all_five_common_rhos": dryad["common_rhos"],
            "pairwise_availability_conditioned_contrasts": contrasts,
            "limits": [
                "Selected exposed DEV30 stories and pooled reader means only; no population or crossed-rater interval.",
                "Dryad common-set and contrast interpretations remain inconclusive with arm-dependent availability; point estimates are descriptive.",
                "Conditional resampling is conditional on selected observed stories; no confidence intervals are reproduced in this package.",
                "Native packet completeness and numeric score availability differ; abstention does not become a numeric score.",
                "Different native scales and tie granularity do not establish stronger alignment, calibration or a method winner.",
            ],
        },
        "kyoto_qsf12": {
            "planned_stories": kyoto["planned"], "topics": kyoto["topics"],
            "planned_native_packets": kyoto["native_admitted"] + kyoto["native_rejected"],
            "native_admitted_packets": kyoto["native_admitted"],
            "native_rejected_packets": kyoto["native_rejected"],
            "method_story_profile_cells": kyoto["profile_cells"],
            "methods": kyoto["methods"], "targets": targets,
            "primary_fixed12_rhos": kyoto["primary_rhos"], **differences,
            "limits": [
                "Twelve selected stories across three topics; no independent-story or independent-reader uncertainty claim.",
                "Reader enjoyment and pleasing style are separate constructs; no expert-population, broad-quality or improvement claim.",
                "HBQ, TTCW and lexical-control fixed12 points are available; these complete comparisons are not attrition-inconclusive.",
                "Holistic, compact and Oregon have 11 numeric stories; their fixed12 primary is unavailable and secondary11 never substitutes for it.",
                "Constant-vector correlation is undefined despite complete coverage.",
                "Recorded valid-response sums of 115 per axis do not establish 115 distinct participants; rater identities are not established.",
                "Historical preprocessing and exclusion counts remain partly unknown.",
                "After the frozen condition was fixed, source-only mapping incidentally encountered upstream aggregate ICC weights; those values were not returned to or used by this analysis lane. Global prior use remains unknown.",
                "Ladder aggregate distributions/correlations match HBQ and reported rho differences are zero; these aggregates alone do not prove paired score equality.",
                "No additional native packets were obtained for the ladder projection; its admitted parent packets are shared with HBQ.",
                "No fitting, sign selection, bootstrap or confidence interval was performed for these Kyoto points.",
            ],
        },
        "lineage_clarification": (
            "Structured execution lineage identifies collection generation637 and its actual owning joins. "
            "Frozen Dryad lineage captions name618 and Kyoto captions sayPOST618. "
            "This derived clarification preserves the raw reports unchanged."),
        "boundaries": {
            "cohorts_pooled": False, "fresh_census": False, "new_judge_votes": 0,
            "new_provider_or_native_calls": 0, "new_scoring_or_semantic_validation_calls": 0, "new_human_labels_or_judge_training": False,
            "raw_text_ratings_memberships_or_account_details_published": False,
            "confidence_intervals_reproduced": False, "expert_population_claim": False,
            "human_alignment_gain_established": False, "method_winner_established": False,
            "candidate_or_baseline_promoted": False, "full_program_complete": False,
        },
    }


def encode(result: dict) -> bytes:
    text = json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n"
    if re.search(r"(?i)([a-z]:[\\/]|[\w.+-]+@[\w.-]+|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})", text):
        raise ValueError("Private operational marker in public projection")
    return text.encode("utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reader-results", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    raw = encode(project(checked(args.reader_results)))
    with args.output.open("xb") as stream:
        stream.write(raw)
    if args.output.read_bytes() != raw:
        raise RuntimeError("Output readback differs")
    print(json.dumps({"state": "RETAINED_READER_AGGREGATES_PROJECTED", "bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(), "new_scientific_calls": 0}))


if __name__ == "__main__":
    main()
