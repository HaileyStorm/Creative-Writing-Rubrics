"""Project reviewed retained aggregate inputs into the public synthesis.

Requires the named private aggregate inputs, not raw judgments or source texts.
This command performs no scientific replay, validation, scoring or inference.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re


INPUT_PINS = {
    "p1b": "073105954b39e2e44b1c0b74eeaeae2b68934b3b553f07bc3bde79080e50cd8c",
    "p1b_sources": "e61b79c022f5bdca9c79ba2ee1de87a53743f07b6d80c7990e2537bc3097a0c8",
    "longform": "ec2da64111928afedfdf234d256938d0d74407562bfec7d3ae65abee9de589dc",
}
P1B_FIELDS = (
    "historical_plan", "historical_terminal_counts", "historical_endpoint_inventory_sums",
    "historical_analysis_sha256", "matched_manifest_sha256", "admission_bases",
    "historical_analysis_flags", "intent_review_002", "matched_contrast_basis",
    "existing_cycle0_scalar_aggregates", "existing_HBQ_repeat_aggregates",
    "existing_Sol_initial_HBQ_vs_arm_direction_aggregates",
    "existing_cycle0_pair_orientation_aggregates", "existing_interendpoint_pairwise_aggregates",
    "existing_pairwise_repeat_aggregates", "existing_HBQ_interendpoint_cycle0_aggregates",
    "historical_analysis_limitations", "source_date_policy",
)


def checked(path: Path, name: str) -> dict:
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != INPUT_PINS[name]:
        raise ValueError(f"The exact reviewed {name} input is required")
    return json.loads(raw)


def commitment(reference: dict) -> dict:
    return {key: reference[key] for key in ("sha256", "bytes")}


def project(p1b: dict, p1b_sources: dict, longform: dict) -> dict:
    """Copy existing measurements without recomputing or combining cohorts."""
    result = {
        "schema_version": 1,
        "policy": "retained_crossform_aggregate_only_descriptive_synthesis_v1",
        "input_aggregate_sha256": INPUT_PINS,
        "p1b": {key: p1b[key] for key in P1B_FIELDS},
        "p1b_source_commitments": {
            name: commitment(reference)
            for name, reference in p1b_sources["source_refs"].items()
        },
        "longform": {
            key: longform[key]
            for key in ("legacy_dependency_pilot", "later_pg43_bank", "limits")
        },
        "longform_source_commitments": {
            name: commitment(reference)
            for name, reference in longform["sources"].items()
        },
        "boundaries": {
            "fresh_census": False,
            "new_judge_votes": 0,
            "new_provider_or_native_calls": 0,
            "new_scoring_or_semantic_validation_calls": 0,
            "raw_text_response_judgment_label_or_account_details_published": False,
            "human_alignment_gain_established": False,
            "candidate_or_baseline_promoted": False,
            "full_program_complete": False,
            "historical_event_date_inferred_from_filename": False,
        },
    }
    return result


def encode(result: dict) -> bytes:
    text = json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if re.search(r"(?i)([a-z]:[\\/]|@gmail\.com)", text):
        raise ValueError("Private operational marker in public projection")
    return text.encode("utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--p1b", type=Path, required=True)
    parser.add_argument("--p1b-sources", type=Path, required=True)
    parser.add_argument("--longform", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = project(checked(args.p1b, "p1b"), checked(args.p1b_sources, "p1b_sources"),
                     checked(args.longform, "longform"))
    raw = encode(result)
    with args.output.open("xb") as stream:
        stream.write(raw)
    if args.output.read_bytes() != raw:
        raise RuntimeError("Output readback differs")
    print(json.dumps({"state": "RETAINED_AGGREGATES_PROJECTED", "bytes": len(raw),
                      "sha256": hashlib.sha256(raw).hexdigest(), "new_scientific_calls": 0}))


if __name__ == "__main__":
    main()
