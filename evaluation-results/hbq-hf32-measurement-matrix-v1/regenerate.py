"""Project the published HF32 aggregate into source-bound comparison rows."""
import argparse
import hashlib
import json
from pathlib import Path

PINS = {
    "pilot": ("evaluation-results/hbq-hf32-frozen708-human-reference-v1/aggregate.json", "ac187d94306f8179173915857d06d54f8a1ceca74c3008e19eaca02bbfdb914e"),
    "length": ("evaluation-results/hbq-hf32-length-baseline-v1/aggregate.json", "19ba6f3e0cc2f986a2d97742a8356d65e9e85d42ca0c4fef443dce2b9f27d037"),
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    docs, refs = {}, {}
    for name, (path, expected) in PINS.items():
        raw = (args.repo_root / path).read_bytes()
        actual = hashlib.sha256(raw).hexdigest()
        if actual != expected:
            raise ValueError(f"{name} source hash mismatch")
        docs[name] = json.loads(raw)
        refs[name] = {"path": path, "sha256": actual, "bytes": len(raw)}

    pilot, length = docs["pilot"], docs["length"]
    rows = []
    common = pilot["same_input_common_views"]["historical__candidate__ttcw14"]
    for axis, length_axis in (("expert_mean2", "expert"), ("nonexpert_median", "reader")):
        view, ext = common[axis], length["matched_results"][length_axis]
        if view["paired_n"] != ext["matched_works"]:
            raise ValueError("matched-work count mismatch")
        if view["signed_spearman"]["historical"] != ext["spearman_hbq_reference"] or view["signed_spearman"]["ttcw14"] != ext["spearman_ttcw_reference"]:
            raise ValueError("published common-view correlations differ")
        for arm in ("historical", "candidate", "ttcw14", "word_count"):
            source = "length" if arm == "word_count" else "pilot"
            pointer = (f"/matched_results/{length_axis}/spearman_length_reference" if arm == "word_count" else
                       f"/same_input_common_views/historical__candidate__ttcw14/{axis}/signed_spearman/{arm}")
            point = ext["spearman_length_reference"] if arm == "word_count" else view["signed_spearman"][arm]
            rows.append({"dataset": "HF32", "population": axis, "form": "not_specified_in_public_aggregate",
                         "endpoint": "not_recatalogued_mixed_historical" if arm != "word_count" else "not_applicable",
                         "arm": arm, "reference_axis": pilot["target_constructs"][axis],
                         "cohort_view": "all_three_scored_arms_and_reference", "metric": "signed_spearman",
                         "unit": "work", "denominators": {k: view[k] for k in ("planned_n", "score_common_n", "paired_n", "missing_from_fixed32_n")},
                         "point": point, "source_ref": refs[source], "source_pointer": pointer,
                         "interval": {"status": "not_reported_for_individual_arm", "value": None},
                         "limitations": ["selected development cohort", "historical and candidate use the same verdict bank", "expert and reader cohorts need not be identical", "mixed historical execution qualifications", "word count was selected after results"]})
        sensitivity = pilot["conditional_sensitivity"]["views"]["historical__candidate__ttcw14"][axis]["contrasts"]["historical__minus__ttcw14"]
        rows.append({"dataset": "HF32", "population": axis, "form": "not_specified_in_public_aggregate",
                     "endpoint": "not_recatalogued_mixed_historical", "arm": "historical_minus_ttcw14",
                     "reference_axis": pilot["target_constructs"][axis], "cohort_view": "all_three_scored_arms_and_reference",
                     "metric": "signed_spearman_difference", "unit": "work", "denominators": {k: view[k] for k in ("planned_n", "score_common_n", "paired_n", "missing_from_fixed32_n")},
                     "point": sensitivity["point"], "interval": {"status": "conditional_work_exchangeability_sensitivity_not_population_confidence_interval", "value": sensitivity["range_2_5_97_5"], "draws": sensitivity["defined_draws"]},
                     "source_ref": refs["pilot"], "source_pointer": f"/conditional_sensitivity/views/historical__candidate__ttcw14/{axis}/contrasts/historical__minus__ttcw14",
                     "limitations": ["selected development cohort", "not cluster-aware uncertainty", "mixed historical execution qualifications"]})
    encoded = "".join(json.dumps(row, sort_keys=True, allow_nan=False) + "\n" for row in rows).encode("utf-8")
    with args.output.open("xb") as out:
        out.write(encoded)
    print(json.dumps({"rows": len(rows), "sha256": hashlib.sha256(encoded).hexdigest()}))


if __name__ == "__main__":
    main()
