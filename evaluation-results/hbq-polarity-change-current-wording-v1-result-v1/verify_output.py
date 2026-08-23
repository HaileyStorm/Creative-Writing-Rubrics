"""Verify P1's aggregate-only public result without opening private receipts."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path


HERE = Path(__file__).resolve().parent
AGGREGATE_NAME = "p1-public-aggregate.v1.json"
README_NAME = "README.md"
AGGREGATE_SHA256 = "e85500c3d8dc02f51d503fbfc946b680d9de6711adcead5e9003613623d07070"
README_SHA256 = "190401d75aab1a19d28170231af87e33f2e849332dc5612a243b1c9b92eefaf4"
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
    "form.audio.audio_drama_production.no_as_you_know": {"CANNOT_ASSESS": 6, "NO": 3, "NOT_APPLICABLE": 0, "YES": 3},
    "form.multimodal.text_audio_alignment.no_narrow": {"CANNOT_ASSESS": 3, "NO": 3, "NOT_APPLICABLE": 3, "YES": 3},
    "form.poetry.general_poetry.oral_test": {"CANNOT_ASSESS": 3, "NO": 1, "NOT_APPLICABLE": 0, "YES": 8},
    "form.poetry.haiku_in_english.kigo_legible": {"CANNOT_ASSESS": 3, "NO": 5, "NOT_APPLICABLE": 1, "YES": 3},
    "form.poetry.lyric_song_lyric.no_filler": {"CANNOT_ASSESS": 3, "NO": 3, "NOT_APPLICABLE": 1, "YES": 5},
    "form.poetry.spoken_word_performance_poetry.page_independence": {"CANNOT_ASSESS": 3, "NO": 4, "NOT_APPLICABLE": 2, "YES": 3},
    "form.visual.visual_prompt_and_canon_fidelity.subjects": {"CANNOT_ASSESS": 6, "NO": 3, "NOT_APPLICABLE": 3, "YES": 0},
    "op.critique.rubric_directed_critique.criteria": {"CANNOT_ASSESS": 4, "NO": 5, "NOT_APPLICABLE": 3, "YES": 0},
    "op.ingest.source_ingestion_fidelity.no_invention": {"CANNOT_ASSESS": 5, "NO": 4, "NOT_APPLICABLE": 3, "YES": 0},
    "op.ingest.source_ingestion_fidelity.no_omission": {"CANNOT_ASSESS": 3, "NO": 3, "NOT_APPLICABLE": 3, "YES": 3},
    "sampler.freshness_gain.no_ornate_proxy": {"CANNOT_ASSESS": 3, "NO": 3, "NOT_APPLICABLE": 3, "YES": 3},
}
EXPECTED_LIMITATIONS = [
    "Aggregate-only public projection: no fixture text, per-slot records, prompts, model outputs, private evidence, or session identifiers.",
    "This staged synthetic diagnostic does not establish a general result or authorize a prompt, rubric, leaf, ownership, split, or weight change.",
    "Causal diagnosis remains unresolved: the study does not isolate missing NOT_APPLICABLE-versus-CANNOT_ASSESS guidance from a missing symmetric-evidence rule.",
    "Oral-fixture ambiguity and three positive carrier-evidence confounds remain unresolved.",
    "One duplicated run label from second-resolution runner generation is non-invalidating; no identifier or private record is published.",
    "The sealed private settlement remains the verification authority.",
]
EXPECTED_COMMITMENTS = {
    "source_aggregate_sha256": "8802a49ae6f29c1af3c9e603716b4f0cc8cee547b79f11e0a8ec2f58493f34ea",
    "settlement_sha256": "46798e257640c511c51d9e0d8fc5e7d7e39fa08f68d2c6fea49a530f180f6981",
    "execution_manifest_sha256": "43adc2ea41420adfcb4fc747a4fad5a0fe8b2e0a85b7fa496fcbd6ef6a672ce7",
    "execution_contract_sha256": "a70cd541917113a778975a811087081940d7b6c382295908770f637168b65f6a",
}
FORBIDDEN_PATTERNS = (
    ("Windows path", r"[A-Za-z]:[\\/]"),
    ("home-directory path", r"(?:^|[\\/])(?:Users|home)(?:[\\/]|$)"),
    ("private directory", r"\.private"),
    ("session identifier", r"session_id"),
    ("request identifier", r"request_id"),
    ("run identifier", r"run_id"),
    ("slot identifier", r"slot_id"),
    ("fixture alias", r"p1-artifact-\d+"),
    ("fixture label", r"p1-v1-[a-z0-9-]+"),
    ("exact quote", r"exact_quote"),
)
REQUIRED_READER_CLAIMS = (
    "aggregate-only public result",
    "132 of 132 singleton slots",
    "accepted on their first\nattempt",
    "**DIAGNOSTIC_FAIL**",
    "29 of 33 scored cells passed",
    "6 of 11 completed-but-unscored NOT_APPLICABLE controls matched",
    "CANNOT_ASSESS 33/33, NO 31/33, NOT_APPLICABLE 22/33, and YES\n24/33",
    "No promotion follows from this result.",
    "missing NOT_APPLICABLE-versus-CANNOT_ASSESS\nguidance from a missing symmetric-evidence rule",
    "oral-fixture\nambiguity and three positive carrier-evidence confounds",
    "One duplicated run\nlabel arose from second-resolution runner generation; it is non-invalidating",
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
        "decision", "promotion", "aggregate_counts", "accuracy", "canonical_four_state_counts",
        "limitations", "opaque_private_receipt_commitments",
    }
    if set(data) != expected_keys:
        failures.append("aggregate top-level allowlist mismatch")
        return failures
    if data["format_version"] != 1 or data["study_id"] != "hbq-polarity-change-current-wording-v1-execution-v1":
        failures.append("aggregate identity differs from the public contract")
    if data["public_cwr_lineage"] != {
        "frozen_screen_commit": "5665e2f4a91b754685ae9137bd94bfb7601f5cc6",
        "execution_runtime_commit": "e3fdd51c54a588dfc86d3ba702baad6d6d65e17a",
    }:
        failures.append("aggregate CWR lineage differs from the public contract")
    if data["public_leaf_ids"] != EXPECTED_LEAVES:
        failures.append("selected-leaf allowlist differs from the public contract")
    if data["decision"] != "DIAGNOSTIC_FAIL" or data["promotion"] != "none":
        failures.append("public decision or promotion differs from the public contract")
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
        "synthetic_artifacts": 44, "selected_leaves": 11, "four_states": 4,
        "repetitions_per_cell": 3, "logical_slots": 132,
        "one_leaf_per_provider_request": True, "execution_route": "codex_gpt_5_6_sol_high",
    }:
        failures.append("protocol geometry differs from the public contract")
    if counts != {
        "planned_slots": 132, "completed_slots": 132, "first_attempt_accepted_slots": 132,
        "scored_cells": 33, "scored_cells_passing": 29, "not_applicable_control_cells": 11,
        "not_applicable_control_cells_matching": 6,
    }:
        failures.append("aggregate counts differ from the public contract")
    if accuracy != {
        "CANNOT_ASSESS": {"correct": 33, "denominator": 33},
        "NO": {"correct": 31, "denominator": 33},
        "NOT_APPLICABLE": {"correct": 22, "denominator": 33},
        "YES": {"correct": 24, "denominator": 33},
    }:
        failures.append("state accuracy differs from the public contract")
    elif not (
        geometry["synthetic_artifacts"] * geometry["repetitions_per_cell"] == counts["planned_slots"]
        == counts["completed_slots"] == counts["first_attempt_accepted_slots"] == geometry["logical_slots"]
        and counts["scored_cells"] + counts["not_applicable_control_cells"] == geometry["selected_leaves"] * 4
        and sum(sum(state_counts.values()) for state_counts in EXPECTED_FOUR_STATE_COUNTS.values())
        == counts["completed_slots"]
        and all(value["denominator"] == counts["scored_cells"] for value in accuracy.values())
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
        print("P1 public result verification failed:")
        print("\n".join(f"- {failure}" for failure in failures))
        return 1
    print("P1 public result verification passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
