"""Verify QPC1's aggregate-only public projection without private receipts."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path


HERE = Path(__file__).resolve().parent
AGGREGATE_NAME = "qpc1-public-aggregate.v1.json"
README_NAME = "README.md"
AGGREGATE_SHA256 = "7f81bcc76ff33579c92916d1d1299a046bc6f15235e777e719a7e0e59f0b020a"
ALLOWED_FILES = {AGGREGATE_NAME, README_NAME, Path(__file__).name}
EXPECTED_ROLES = ["author_original", "gpt_5_6_pro_rewrite", "public_control_story"]
EXPECTED_LEAVES = [
    "penalty.purple_prose.clarity",
    "penalty.purple_prose.proportion",
    "penalty.purple_prose.specificity",
    "penalty.purple_prose.tone",
    "penalty.purple_prose.metaphor",
    "penalty.purple_prose.attention",
    "penalty.purple_prose.fatigue",
]
FORBIDDEN_PATTERNS = (
    ("Windows path", r"[A-Za-z]:[\\/]"),
    ("home-directory path", r"(?:^|[\\/])(?:Users|home)(?:[\\/]|$)"),
    ("private directory", r"\.private"),
    ("session identifier", r"session_id"),
    ("request identifier", r"request_id"),
    ("run identifier", r"run_id"),
    ("blind identifier", r"blind_id"),
    ("raw prompt", r"raw_prompt"),
    ("raw response", r"raw_response"),
    ("source hash", r"(?:source|story)_sha"),
    ("source path", r"(?:input|output|source)_path"),
    ("exact quote", r"exact_quote"),
    ("known blind alias", r"qpc1-(?:aster|bramble|cinder)-\d+"),
)
REQUIRED_READER_CLAIMS = (
    "three artifacts, each repeated five times",
    "15 logical runs and\n105 distinct provider-session calls/checkpoints",
    "Every cell was 5/5\nYES",
    "normalization\naudits. Those provenance audits are not provider retries or validation repairs",
    "negative, no-discrimination result",
    "`author_original`",
    "`gpt_5_6_pro_rewrite`",
    "`public_control_story`",
    "`no_default_metaphors`, the stockness owner, was not selected",
    "complete-scope status was not rendered into the actual model-facing\ninstruction",
    "Two long works used a short-story bundle",
    "QPC24 is held",
    "does not justify a split,\nreweight, or a new density leaf",
)


def _json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def check(root: Path = HERE) -> list[str]:
    failures: list[str] = []
    files = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file()
    }
    if files != ALLOWED_FILES:
        failures.append(f"public file allowlist mismatch: {sorted(files)}")

    aggregate_path = root / AGGREGATE_NAME
    readme_path = root / README_NAME
    if not aggregate_path.is_file() or not readme_path.is_file():
        return [*failures, "required public package files are missing"]
    if hashlib.sha256(aggregate_path.read_bytes()).hexdigest() != AGGREGATE_SHA256:
        failures.append("aggregate SHA-256 does not match the fixed public projection")

    public_text = "\n".join(
        path.read_text(encoding="utf-8") for path in (aggregate_path, readme_path)
    ).lower()
    for label, pattern in FORBIDDEN_PATTERNS:
        if re.search(pattern, public_text, flags=re.IGNORECASE):
            failures.append(f"forbidden public metadata: {label}")

    data = _json(aggregate_path)
    expected_keys = {
        "format_version",
        "study_id",
        "public_cwr_parent",
        "protocol_geometry",
        "public_leaf_ids",
        "artifact_roles",
        "aggregate_counts",
        "limitations",
        "sealed_private_receipt_commitments",
    }
    if set(data) != expected_keys:
        failures.append("aggregate top-level allowlist mismatch")
        return failures
    if data["format_version"] != 1 or data["study_id"] != "qpc1-figurative-treatment-20260822":
        failures.append("aggregate identity differs from the public contract")
    if data["public_cwr_parent"] != {"commit": "c4ba06453785bdb52bce374926b65d3cab542a9a"}:
        failures.append("aggregate parent differs from the public contract")
    if data["limitations"] != [
        "Selected leaves only; no composite score or manuscript decision.",
        "A universal pass is a negative discrimination result and does not establish universal validity.",
        "The sealed private receipts remain the verification authority.",
    ]:
        failures.append("aggregate limitations differ from the public contract")
    commitments = data["sealed_private_receipt_commitments"]
    if set(commitments) != {"analysis_v2_sha256", "receipt_set_sha256"} or not all(
        isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value)
        for value in commitments.values()
    ):
        failures.append("aggregate receipt commitments are malformed")
    geometry = data["protocol_geometry"]
    counts = data["aggregate_counts"]
    if data["artifact_roles"] != EXPECTED_ROLES:
        failures.append("artifact-role labels differ from the public contract")
    if data["public_leaf_ids"] != EXPECTED_LEAVES:
        failures.append("selected-leaf allowlist differs from the public contract")
    if geometry != {
        "artifacts": 3,
        "logical_runs": 15,
        "repetitions_per_artifact": 5,
        "selected_leaves": 7,
        "one_leaf_per_provider_request": True,
        "expected_provider_sessions": 105,
    }:
        failures.append("protocol geometry differs from the public contract")
    if counts != {
        "accepted_checkpoints": 105,
        "accepted_verdicts": 105,
        "accepted_yes": 105,
        "accepted_no": 0,
        "rejected_attempts": 0,
        "provider_retry_or_validation_repair_events": 0,
        "artifact_leaf_cells": 21,
        "all_artifact_leaf_cells_unanimous_yes": 21,
    }:
        failures.append("aggregate counts differ from the public contract")
    elif not (
        geometry["artifacts"] * geometry["repetitions_per_artifact"] == geometry["logical_runs"]
        and geometry["artifacts"] * geometry["selected_leaves"] == counts["artifact_leaf_cells"]
        and counts["artifact_leaf_cells"] * geometry["repetitions_per_artifact"]
        == counts["accepted_checkpoints"]
        == counts["accepted_yes"]
        == geometry["expected_provider_sessions"]
        and counts["accepted_verdicts"] == counts["accepted_checkpoints"]
        and counts["accepted_no"] == counts["rejected_attempts"]
        == counts["provider_retry_or_validation_repair_events"]
        == 0
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
        print("QPC1 public package verification failed:")
        print("\n".join(f"- {failure}" for failure in failures))
        return 1
    print("QPC1 public package verification passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
