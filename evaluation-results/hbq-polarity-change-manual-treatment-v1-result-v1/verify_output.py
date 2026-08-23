"""Verify P1 manual treatment's aggregate-only public result."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path


HERE = Path(__file__).resolve().parent
AGGREGATE_NAME = "p1-manual-treatment-public-aggregate.v1.json"
README_NAME = "README.md"
AGGREGATE_SHA256 = "2fa3e3e598b813e562a139ca305bd1af8a22a58ca591539285044824137b2ca3"
README_SHA256 = "a57ee8f108a129a7fbc19f98f28575ba503e5f1f9a679339e1e5994a01c470a4"
ALLOWED_FILES = {AGGREGATE_NAME, README_NAME, Path(__file__).name}
EXPECTED_LEAVES = [
    "form.audio.audio_drama_production.no_as_you_know",
    "form.multimodal.text_audio_alignment.no_narrow",
    "form.poetry.general_poetry.oral_test",
    "form.poetry.haiku_in_english.kigo_legible",
    "form.poetry.lyric_song_lyric.no_filler",
    "form.poetry.spoken_word_performance_poetry.page_independence",
    "form.visual.visual_prompt_and_canon_fidelity.subjects",
    "op.critique.rubric_directed_critique.criteria",
    "op.ingest.source_ingestion_fidelity.no_invention",
    "op.ingest.source_ingestion_fidelity.no_omission",
    "sampler.freshness_gain.no_ornate_proxy",
]
EXPECTED_FOUR_STATE_COUNTS = {
    "form.audio.audio_drama_production.no_as_you_know": {"CANNOT_ASSESS": 0, "NO": 0, "NOT_APPLICABLE": 3, "YES": 0},
    "form.multimodal.text_audio_alignment.no_narrow": {"CANNOT_ASSESS": 0, "NO": 0, "NOT_APPLICABLE": 3, "YES": 0},
    "form.poetry.general_poetry.oral_test": {"CANNOT_ASSESS": 0, "NO": 3, "NOT_APPLICABLE": 3, "YES": 3},
    "form.poetry.haiku_in_english.kigo_legible": {"CANNOT_ASSESS": 0, "NO": 0, "NOT_APPLICABLE": 3, "YES": 0},
    "form.poetry.lyric_song_lyric.no_filler": {"CANNOT_ASSESS": 0, "NO": 0, "NOT_APPLICABLE": 3, "YES": 0},
    "form.poetry.spoken_word_performance_poetry.page_independence": {"CANNOT_ASSESS": 0, "NO": 0, "NOT_APPLICABLE": 3, "YES": 0},
    "form.visual.visual_prompt_and_canon_fidelity.subjects": {"CANNOT_ASSESS": 0, "NO": 3, "NOT_APPLICABLE": 3, "YES": 3},
    "op.critique.rubric_directed_critique.criteria": {"CANNOT_ASSESS": 0, "NO": 3, "NOT_APPLICABLE": 3, "YES": 3},
    "op.ingest.source_ingestion_fidelity.no_invention": {"CANNOT_ASSESS": 0, "NO": 3, "NOT_APPLICABLE": 3, "YES": 3},
    "op.ingest.source_ingestion_fidelity.no_omission": {"CANNOT_ASSESS": 0, "NO": 0, "NOT_APPLICABLE": 3, "YES": 0},
    "sampler.freshness_gain.no_ornate_proxy": {"CANNOT_ASSESS": 0, "NO": 0, "NOT_APPLICABLE": 3, "YES": 0},
}
EXPECTED_LIMITATIONS = [
    "Aggregate-only public projection: no fixture text, expected labels, per-slot records, prompts, model outputs, private evidence, or session identifiers.",
    "Four matched fixture repairs and the treatment appendix are development evidence; their causal benefit remains unproved.",
    "This development pass does not establish a general result or authorize a prompt, rubric, leaf, ownership, split, or weight change.",
    "A sealed same-fixture current-versus-treatment A/B holdout is the next gate before any promotion decision.",
    "The sealed private settlement remains the verification authority.",
]
EXPECTED_COMMITMENTS = {
    "source_aggregate_sha256": "364b4a73be61ffa0f06a7cea0d2b7a959c0d288313217099d7fab05c830648a9",
    "settlement_sha256": "b05c8194c3be5b5547c059c86ecee2c15dae41a1b4f91bd54c6ef937ff6ddc3c",
    "execution_manifest_sha256": "eb037dc89467116f754c02f6983ace04a2ed572daa7dcec075eae4651d74054c",
    "runtime_schedule_sha256": "078ff50386bd9074e35bd625e45093f0ed1ec88d146016a8b311166e2e41b482",
    "study_contract_sha256": "c6c6a151067f00f76c4349680df59a7de437a04288e1310ba31e01f5fd82b9c3",
    "treatment_appendix_sha256": "00ce0c5f1063c1fb36cc663bd2c522ce5eda254ee8f9079ec21774277e0d3722",
}
FORBIDDEN_PATTERNS = (
    ("Windows path", r"[A-Za-z]:[\\/]"),
    ("home-directory path", r"(?:^|[\\/])(?:Users|home)(?:[\\/]|$)"),
    ("private directory", r"\.private"),
    ("session identifier", r"session_id"),
    ("request identifier", r"request_id"),
    ("run identifier", r"run_id"),
    ("slot identifier", r"slot_id"),
    ("fixture alias", r"p1mt-a\d+"),
    ("fixture label", r"p1mt-s\d+"),
    ("exact quote", r"exact_quote"),
    ("provider response", r"accepted-\d+\.message|verdicts\.jsonl"),
)
REQUIRED_READER_CLAIMS = (
    "aggregate-only public result",
    "57 of 57 singleton slots",
    "accepted on their first\nattempt, with zero retries",
    "**MANUAL_TREATMENT_PASS**",
    "all 19 of 19\nscored cells passed 3/3",
    "NO 12/12, YES 12/12,\nNOT_APPLICABLE 33/33, and CANNOT_ASSESS 0/0",
    "No promotion follows from this result.",
    "four matched fixture repairs with an explicit\napplicability and evidence-sufficiency appendix",
    "causal contribution of the\nrepairs, the appendix, or their interaction",
    "sealed same-fixture current-versus-treatment A/B holdout is the next\ndecision gate",
    "sealed private settlement remains the authority",
)


def _json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def check(root: Path = HERE) -> list[str]:
    failures: list[str] = []
    files = {path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()}
    if files != ALLOWED_FILES:
        failures.append(f"public file allowlist mismatch: {sorted(files)}")

    aggregate_path = root / AGGREGATE_NAME
    readme_path = root / README_NAME
    if not aggregate_path.is_file() or not readme_path.is_file():
        return [*failures, "required public package files are missing"]
    if hashlib.sha256(aggregate_path.read_bytes()).hexdigest() != AGGREGATE_SHA256:
        failures.append("aggregate SHA-256 does not match the fixed public projection")
    if hashlib.sha256(readme_path.read_bytes()).hexdigest() != README_SHA256:
        failures.append("README SHA-256 does not match the fixed public interpretation")

    public_text = "\n".join(path.read_text(encoding="utf-8") for path in (aggregate_path, readme_path)).lower()
    for label, pattern in FORBIDDEN_PATTERNS:
        if re.search(pattern, public_text, flags=re.IGNORECASE):
            failures.append(f"forbidden public metadata: {label}")

    data = _json(aggregate_path)
    expected_keys = {
        "format_version", "study_id", "public_cwr_lineage", "protocol_geometry", "public_leaf_ids",
        "decision", "evidence_scope", "promotion", "aggregate_counts", "accuracy",
        "canonical_four_state_counts", "limitations", "opaque_private_receipt_commitments",
    }
    if set(data) != expected_keys:
        failures.append("aggregate top-level allowlist mismatch")
        return failures
    if data["format_version"] != 1 or data["study_id"] != "hbq-polarity-change-manual-treatment-v1-execution-v1":
        failures.append("aggregate identity differs from the public contract")
    if data["public_cwr_lineage"] != {"execution_runtime_commit": "6366bb3"}:
        failures.append("aggregate CWR lineage differs from the public contract")
    if data["public_leaf_ids"] != EXPECTED_LEAVES:
        failures.append("selected-leaf allowlist differs from the public contract")
    if data["decision"] != "MANUAL_TREATMENT_PASS" or data["evidence_scope"] != "development_only" or data["promotion"] != "none":
        failures.append("public decision, evidence scope, or promotion differs from the public contract")
    if data["canonical_four_state_counts"] != EXPECTED_FOUR_STATE_COUNTS:
        failures.append("four-state count table differs from the public contract")
    if data["limitations"] != EXPECTED_LIMITATIONS:
        failures.append("aggregate limitations differ from the public contract")
    if data["opaque_private_receipt_commitments"] != EXPECTED_COMMITMENTS:
        failures.append("opaque private receipt commitments differ from the public contract")

    geometry = data["protocol_geometry"]
    counts = data["aggregate_counts"]
    accuracy = data["accuracy"]
    if geometry != {
        "synthetic_artifacts": 19, "selected_leaves": 11, "canonical_states": 4,
        "repetitions_per_cell": 3, "logical_slots": 57,
        "one_leaf_per_provider_request": True, "execution_route": "codex_gpt_5_6_sol_high",
    }:
        failures.append("protocol geometry differs from the public contract")
    if counts != {
        "planned_slots": 57, "completed_slots": 57, "first_attempt_accepted_slots": 57,
        "retries": 0, "scored_cells": 19, "scored_cells_passing": 19,
    }:
        failures.append("aggregate counts differ from the public contract")
    if accuracy != {
        "CANNOT_ASSESS": {"correct": 0, "denominator": 0},
        "NO": {"correct": 12, "denominator": 12},
        "NOT_APPLICABLE": {"correct": 33, "denominator": 33},
        "YES": {"correct": 12, "denominator": 12},
    }:
        failures.append("state accuracy differs from the public contract")
    elif not (
        geometry["synthetic_artifacts"] * geometry["repetitions_per_cell"] == counts["planned_slots"]
        == counts["completed_slots"] == counts["first_attempt_accepted_slots"] == geometry["logical_slots"]
        and counts["scored_cells"] == counts["scored_cells_passing"] == geometry["synthetic_artifacts"]
        and sum(sum(state_counts.values()) for state_counts in EXPECTED_FOUR_STATE_COUNTS.values())
        == counts["completed_slots"]
        and all(value["correct"] == value["denominator"] for value in accuracy.values())
    ):
        failures.append("aggregate arithmetic is inconsistent")

    readme = readme_path.read_text(encoding="utf-8")
    for claim in REQUIRED_READER_CLAIMS:
        if claim not in readme:
            failures.append(f"required reader claim is missing: {claim!r}")
    return failures


def main() -> int:
    failures = check()
    if failures:
        print("P1 manual-treatment public result verification failed:")
        print("\n".join(f"- {failure}" for failure in failures))
        return 1
    print("P1 manual-treatment public result verification passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
