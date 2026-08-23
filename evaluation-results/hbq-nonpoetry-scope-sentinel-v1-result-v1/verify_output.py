"""Verify S2's aggregate-only public result without opening private receipts."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path


HERE = Path(__file__).resolve().parent
AGGREGATE_NAME = "s2-public-aggregate.v1.json"
README_NAME = "README.md"
AGGREGATE_SHA256 = "49d6ef3843062580bbbda0b362756634f993613600269d4176be0bb157c9d453"
ALLOWED_FILES = {AGGREGATE_NAME, README_NAME, Path(__file__).name}
EXPECTED_LEAVES = [
    "craft.narrative.character_arc.end_state",
    "data.eval.evaluation_determinism.rerun",
    "modifier.genre.hybrid_or_genre_blend.tone",
    "op.critique.single_unit_critique.no_whole_claims",
    "scope.passage.status",
]
EXPECTED_FOUR_STATE_COUNTS = {
    "craft.narrative.character_arc.end_state": {"YES": 3, "NO": 3, "NOT_APPLICABLE": 3, "CANNOT_ASSESS": 3},
    "data.eval.evaluation_determinism.rerun": {"YES": 3, "NO": 3, "NOT_APPLICABLE": 3, "CANNOT_ASSESS": 3},
    "modifier.genre.hybrid_or_genre_blend.tone": {"YES": 1, "NO": 3, "NOT_APPLICABLE": 5, "CANNOT_ASSESS": 3},
    "op.critique.single_unit_critique.no_whole_claims": {"YES": 6, "NO": 3, "NOT_APPLICABLE": 3, "CANNOT_ASSESS": 0},
    "scope.passage.status": {"YES": 6, "NO": 0, "NOT_APPLICABLE": 4, "CANNOT_ASSESS": 2},
}
FORBIDDEN_PATTERNS = (
    ("Windows path", r"[A-Za-z]:[\\/]"),
    ("home-directory path", r"(?:^|[\\/])(?:Users|home)(?:[\\/]|$)"),
    ("private directory", r"\.private"),
    ("session identifier", r"session_id"),
    ("request identifier", r"request_id"),
    ("run identifier", r"run_id"),
    ("slot identifier", r"slot_id"),
    ("raw prompt", r"raw_prompt"),
    ("raw response", r"raw_response"),
    ("source hash", r"(?:source|story)_sha"),
    ("source path", r"(?:input|output|source)_path"),
    ("fixture alias", r"synthetic-\d+"),
    ("exact quote", r"exact_quote"),
)
REQUIRED_READER_CLAIMS = (
    "aggregate-only public result",
    "60 of 60 singleton slots",
    "accepted on their first\nattempt",
    "**DIAGNOSTIC_FAIL**",
    "10 of 15 scored cells passed",
    "5 of 5 completed-but-unscored NOT_APPLICABLE controls matched",
    "No promotion follows from this result.",
    "one possible wording or polarity lead for\n`scope.passage.status` and four additional fixture/oracle-isolation or\nactivation-boundary leads; causal diagnosis remains unresolved",
    "does not identify\nfixtures, cells, slot outcomes, or their expected states",
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

    public_text = "\n".join(path.read_text(encoding="utf-8") for path in (aggregate_path, readme_path)).lower()
    for label, pattern in FORBIDDEN_PATTERNS:
        if re.search(pattern, public_text, flags=re.IGNORECASE):
            failures.append(f"forbidden public metadata: {label}")

    data = _json(aggregate_path)
    expected_keys = {
        "format_version", "study_id", "public_cwr_lineage", "protocol_geometry", "public_leaf_ids",
        "decision", "promotion", "aggregate_counts", "canonical_four_state_counts", "limitations",
        "opaque_private_receipt_commitments",
    }
    if set(data) != expected_keys:
        failures.append("aggregate top-level allowlist mismatch")
        return failures
    if data["format_version"] != 1 or data["study_id"] != "hbq-nonpoetry-scope-sentinel-v1-execution-v1":
        failures.append("aggregate identity differs from the public contract")
    if data["public_cwr_lineage"] != {
        "frozen_screen_commit": "3a529c071997b26bfe4d15acd0b100be5300b2a1",
        "execution_runtime_commit": "a7e23b3a5336be76af318cfb9dc700daaa07ec36",
    }:
        failures.append("aggregate CWR lineage differs from the public contract")
    if data["public_leaf_ids"] != EXPECTED_LEAVES:
        failures.append("selected-leaf allowlist differs from the public contract")
    if data["decision"] != "DIAGNOSTIC_FAIL" or data["promotion"] != "none":
        failures.append("public decision or promotion differs from the public contract")
    if data["canonical_four_state_counts"] != EXPECTED_FOUR_STATE_COUNTS:
        failures.append("four-state count table differs from the public contract")

    geometry = data["protocol_geometry"]
    counts = data["aggregate_counts"]
    if geometry != {
        "synthetic_artifacts": 20, "selected_leaves": 5, "four_states": 4,
        "repetitions_per_cell": 3, "logical_slots": 60,
        "one_leaf_per_provider_request": True, "execution_route": "codex_gpt_5_6_sol_high",
    }:
        failures.append("protocol geometry differs from the public contract")
    if counts != {
        "planned_slots": 60, "completed_slots": 60, "first_attempt_accepted_slots": 60,
        "scored_cells": 15, "scored_cells_passing": 10, "not_applicable_control_cells": 5,
        "not_applicable_control_cells_matching": 5,
    }:
        failures.append("aggregate counts differ from the public contract")
    elif not (
        geometry["synthetic_artifacts"] * geometry["repetitions_per_cell"] == counts["planned_slots"]
        == counts["completed_slots"] == counts["first_attempt_accepted_slots"] == geometry["logical_slots"]
        and counts["scored_cells"] + counts["not_applicable_control_cells"]
        == geometry["synthetic_artifacts"]
        and counts["not_applicable_control_cells_matching"] == counts["not_applicable_control_cells"]
        and sum(sum(state_counts.values()) for state_counts in EXPECTED_FOUR_STATE_COUNTS.values())
        == counts["completed_slots"]
    ):
        failures.append("aggregate arithmetic is inconsistent")

    commitments = data["opaque_private_receipt_commitments"]
    if set(commitments) != {
        "public_aggregate_sha256", "settlement_sha256", "execution_manifest_sha256", "execution_contract_sha256",
    } or not all(isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) for value in commitments.values()):
        failures.append("opaque private receipt commitments are malformed")
    if data["limitations"] != [
        "Aggregate-only public projection: no fixture text, per-slot records, prompts, responses, private evidence, or session identifiers.",
        "This staged synthetic diagnostic does not establish a general result or authorize a prompt, rubric, leaf, ownership, split, or weight change.",
        "The result suggests one possible wording or polarity lead for scope.passage.status and four additional fixture/oracle-isolation or activation-boundary leads; causal diagnosis remains unresolved.",
        "The sealed private settlement remains the verification authority.",
    ]:
        failures.append("aggregate limitations differ from the public contract")
    readme = readme_path.read_text(encoding="utf-8")
    for claim in REQUIRED_READER_CLAIMS:
        if claim not in readme:
            failures.append(f"required reader claim is missing: {claim!r}")
    return failures


def main() -> int:
    failures = check()
    if failures:
        print("S2 public result verification failed:")
        print("\n".join(f"- {failure}" for failure in failures))
        return 1
    print("S2 public result verification passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
