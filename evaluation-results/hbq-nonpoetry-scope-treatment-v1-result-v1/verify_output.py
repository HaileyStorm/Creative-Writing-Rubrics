"""Verify S2 nonpoetry scope treatment's aggregate-only public result."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path


HERE = Path(__file__).resolve().parent
AGGREGATE_NAME = "s2-nonpoetry-scope-treatment-public-aggregate.v1.json"
README_NAME = "README.md"
AGGREGATE_SHA256 = "9782f9565d995adaa61075d6b3fe3e98762455d486109566689f517a31951ca2"
README_SHA256 = "d30d960af609cc5bb293df180a0fd9ff63181f0717aebde47cf6b716ba9bd1cd"
ALLOWED_FILES = {AGGREGATE_NAME, README_NAME, Path(__file__).name}
EXPECTED_COMMITMENTS = {
    "source_aggregate_sha256": "f0baee7af87c8c84e43f9891d8b7308553aeed0f0a8254e19f61f2b5df845e90",
    "settlement_sha256": "6b048295ce0c931b139b405264a6dcef4cb2cdceddac60ccc3e981a3a26bf6b8",
    "execution_manifest_sha256": "fddd5ba5abc87822a489a15297a8a0b32af09ce525c3f4a5a1993cafe3a7a09a",
    "runtime_schedule_sha256": "a8eba3c0ae6c33826b9a4c6fb8d94e121539a3b99300187f4fd93405777b1f4b",
    "study_contract_sha256": "315df2babfbf99f585f7c830b336cecb896f6472f892ef4f3926d6b3fd92f2b2",
    "study_source_sha256": "ad37ee94f4b169b32091a21e80322c03ef81e73f149f8a4f2a301359de01392a",
    "runner_source_sha256": "2292b5628a9a6ad24fe508da6a9c66a34fcce2a062800018c01c6b64a8e19e4e",
}
FORBIDDEN_PATTERNS = (
    ("Windows path", r"[A-Za-z]:[\\/]"),
    ("home-directory path", r"(?:^|[\\/])(?:Users|home)(?:[\\/]|$)"),
    ("private directory", r"\.private"),
    ("session identifier", r"session_id"),
    ("request identifier", r"request_id"),
    ("run identifier", r"run_id"),
    ("slot identifier", r"slot_id"),
    ("fixture identifier", r"fixture_id"),
    ("exact quote", r"exact_quote"),
    ("provider response", r"accepted-\d+\.message|verdicts\.jsonl"),
)
EXPECTED_LIMITATIONS = [
    "Aggregate-only public projection: no fixtures, expected labels, individual outcomes, prompts, model outputs, private evidence, paths, or provider-session metadata.",
    "The candidate wording improved only the missing-required-evidence cell from 2/3 to 3/3; it did not correct material failure, which remained 0/3 in both arms.",
    "The candidate arm did not satisfy its four-passage-cell gate, and all corrected nonpassage controls failed; this result does not establish a treatment effect.",
    "This development-only diagnostic failure authorizes no prompt, rubric, leaf, ownership, split, or weight change.",
    "The sealed private settlement remains the authority for receipt-level verification.",
]


def _json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def check(root: Path = HERE) -> list[str]:
    failures: list[str] = []
    files = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and path.parent.name != "__pycache__"
    }
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
        "format_version", "study_id", "public_cwr_lineage", "evidence_scope", "protocol_geometry",
        "aggregate_counts", "treatment_gate", "decision", "promotion", "limitations",
        "opaque_private_receipt_commitments",
    }
    if set(data) != expected_keys:
        failures.append("aggregate top-level allowlist mismatch")
        return failures
    if data["format_version"] != 1 or data["study_id"] != "hbq-nonpoetry-scope-treatment-v1-execution-v1":
        failures.append("aggregate identity differs from the public contract")
    if data["public_cwr_lineage"] != {
        "frozen_execution_commit": "a7e23b3",
        "frozen_treatment_commit": "6366bb3901e900ff73ddf5f5981d617954ea4a28",
    }:
        failures.append("aggregate CWR lineage differs from the public contract")
    if data["evidence_scope"] != "development_only" or data["decision"] != "DIAGNOSTIC_FAIL" or data["promotion"] != "none":
        failures.append("public decision, evidence scope, or promotion differs from the public contract")
    if data["limitations"] != EXPECTED_LIMITATIONS:
        failures.append("aggregate limitations differ from the public contract")
    if data["opaque_private_receipt_commitments"] != EXPECTED_COMMITMENTS:
        failures.append("opaque private receipt commitments differ from the public contract")

    geometry = data["protocol_geometry"]
    counts = data["aggregate_counts"]
    gate = data["treatment_gate"]
    if geometry != {
        "new_singleton_provider_requests": 27,
        "immutable_reused_accepted_calls": 6,
        "total_accepted_calls_evaluated": 33,
        "repetitions_per_cell": 3,
        "baseline_passage_cells": 4,
        "candidate_passage_cells": 4,
        "corrected_nonpassage_control_cells": 3,
        "one_leaf_per_provider_request": True,
        "execution_route": "codex_gpt_5_6_sol_high",
    }:
        failures.append("protocol geometry differs from the public contract")
    if counts != {
        "new_accepted_first_attempt": 27,
        "new_retries": 0,
        "immutable_reused_accepted_calls": 6,
        "total_accepted_calls_evaluated": 33,
    }:
        failures.append("aggregate counts differ from the public contract")
    if gate != {
        "baseline_passage_cells_passing": {"passed": 2, "total": 4},
        "candidate_passage_cells_passing": {"passed": 3, "total": 4},
        "corrected_nonpassage_controls_passing": {"passed": 0, "total": 3},
        "only_improved_baseline_failure": "missing_required_evidence",
        "no_regression_of_baseline_passes": True,
        "material_failure": {
            "baseline": {"correct": 0, "denominator": 3},
            "candidate": {"correct": 0, "denominator": 3},
        },
    }:
        failures.append("treatment gate differs from the public contract")
    elif not (
        counts["new_accepted_first_attempt"] + counts["immutable_reused_accepted_calls"]
        == counts["total_accepted_calls_evaluated"] == geometry["total_accepted_calls_evaluated"]
        and counts["new_retries"] == 0
        and gate["baseline_passage_cells_passing"]["passed"] == 2
        and gate["candidate_passage_cells_passing"]["passed"] == 3
        and gate["corrected_nonpassage_controls_passing"]["passed"] == 0
        and gate["material_failure"]["baseline"]["correct"] == 0
        and gate["material_failure"]["candidate"]["correct"] == 0
    ):
        failures.append("aggregate arithmetic is inconsistent")

    readme = readme_path.read_text(encoding="utf-8")
    for claim in (
        "aggregate-only public result",
        "27 new singleton requests were accepted on their first attempt, with zero\nretries",
        "Six immutable accepted calls were reused",
        "**DIAGNOSTIC_FAIL**",
        "passed 2/4; candidate passage cells passed 3/4; corrected nonpassage controls\npassed 0/3",
        "only improvement was `missing_required_evidence`, from 2/3 in\nthe baseline to 3/3 in the candidate",
        "Material failure remained 0/3 in both",
        "No promotion follows from this result.",
        "sealed private settlement remains the authority",
    ):
        if claim not in readme:
            failures.append(f"required reader claim is missing: {claim!r}")
    return failures


def main() -> int:
    failures = check()
    if failures:
        print("S2 nonpoetry scope treatment public result verification failed:")
        print("\n".join(f"- {failure}" for failure in failures))
        return 1
    print("S2 nonpoetry scope treatment public result verification passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
