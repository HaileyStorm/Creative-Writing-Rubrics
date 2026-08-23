"""Verify P1's aggregate-only NO_EFFECT holdout result."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path


HERE = Path(__file__).resolve().parent
AGGREGATE_NAME = "p1-manual-treatment-holdout-public-aggregate.v1.json"
README_NAME = "README.md"
AGGREGATE_SHA256 = "b6e5169dd044675cbb4665c0e39ab13348ec1fea6268398fb05e714ec0d6feec"
README_SHA256 = "5d84f965645745c0242c6942f960d9b676f2aae4cb359b02c56560edecdb339e"
ALLOWED_FILES = {AGGREGATE_NAME, README_NAME, Path(__file__).name}
EXPECTED_COMMITMENTS = {
    "source_aggregate_sha256": "1b5cbfb4897bb258bf774e4ac6a4fce0d984c62b497274ede4caa29580392dca",
    "settlement_sha256": "36b4f2b49950924c7a16f464ef201782dc60345620b999ae2c2b3e4d2be38858",
    "study_manifest_sha256": "c91d33fbc5e9d0c28756bf33dd82843ede6b2ec79b76cb90c905d2561e276916",
    "runtime_schedule_sha256": "c69632f5d91e658e61091759243ae4cf130ad1f0353087ee24ee0df3acb48c91",
    "study_contract_sha256": "86691961131402886826568cfda40fad17d9943771612441ceb6882a87ddff2c",
    "candidate_appendix_sha256": "00ce0c5f1063c1fb36cc663bd2c522ce5eda254ee8f9079ec21774277e0d3722",
    "private_corpus_sha256": "2baff4dcd7c96054cd6208bd61b243a4435f15de323c42db152702dc2299ff1b",
    "sealed_expected_ledger_sha256": "231448f3bbcfcd88f12ed4cf8510c16ddd48d907cc203d3a99d6ba62893536e9",
    "runtime_bundle_sha256": "6379be533d969477c6650a71c385573b4d3694e188ac46e3e8a356fffaa6168e",
    "remote_disclosure_sha256": "6019095bdfa7fa18da59367eab02af16475bb5b96a853d3ee4f6c9273d77394d",
}
FORBIDDEN_PATTERNS = (
    ("Windows path", r"[A-Za-z]:[\\/]"),
    ("home-directory path", r"(?:^|[\\/])(?:Users|home)(?:[\\/]|$)"),
    ("private directory", r"\.private"),
    ("private fixture alias", r"\bH(?:0[1-9]|1\d|20)\b"),
    ("private fixture label", r"\b(?:expected_label|fixture_id|artifact_id|fixture_alias)\b"),
    ("private outcome detail", r'"(?:cells|slot_id|judge_id|run_id|session_id|request_id|verdict)"'),
    ("private prompt or response", r"\b(?:raw_prompt|raw_response|exact_quote)\b"),
    ("private artifact filename", r"(?:sealed-expected-ledger|private-corpus|settlement\.json)"),
    ("equivalence claim", r"\b(?:equivalent|equivalence|statistically indistinguishable|no difference|same performance)\b"),
)
REQUIRED_READER_CLAIMS = (
    "aggregate-only public result",
    "All 120 of 120 singleton slots completed and were accepted on their first\nattempt, with zero retries",
    "**NO_EFFECT**: no treatment benefit is demonstrated\nunder this frozen aggregate gate",
    "Current and treatment controls each passed\n12/12. Both arms passed 15/16 target cells",
    "47/48 for current and 46/48 for treatment",
    "zero target\nimprovements, and no stable defect was found in both families",
    "NO_EFFECT means no qualifying cell benefit met the frozen gate",
    "does not\nestablish identical per-fixture outcomes or equal general performance",
    "private cell mapping and all expected labels remain sealed",
    "exact candidate appendix has been exhausted",
    "figurative gate remains closed",
    "No promotion\nfollows from this result",
    "sealed private settlement remains the receipt-level verification authority",
)


def _json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


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

    public_text = "\n".join((_read_text(aggregate_path), _read_text(readme_path))).lower()
    for label, pattern in FORBIDDEN_PATTERNS:
        if re.search(pattern, public_text, flags=re.IGNORECASE):
            failures.append(f"forbidden public content: {label}")

    data = _json(aggregate_path)
    expected_keys = {
        "format_version", "study_id", "evidence_scope", "public_cwr_lineage", "protocol_geometry",
        "decision", "promotion", "promotion_scope", "aggregate_counts", "gate_results", "limitations",
        "opaque_private_receipt_commitments",
    }
    if set(data) != expected_keys:
        return [*failures, "aggregate top-level allowlist mismatch"]
    if data["format_version"] != 1 or data["study_id"] != "hbq-polarity-change-manual-treatment-holdout-v1-execution-v1":
        failures.append("aggregate identity differs from the public contract")
    if data["evidence_scope"] != "sealed_same_fixture_ab_holdout":
        failures.append("aggregate evidence scope differs from the public contract")
    if data["public_cwr_lineage"] != {"execution_runtime_commit": "6366bb3"}:
        failures.append("aggregate lineage differs from the public contract")
    if data["decision"] != "NO_EFFECT" or data["promotion"] != "none" or data["promotion_scope"] != "none":
        failures.append("public decision or promotion differs from the public contract")
    if data["opaque_private_receipt_commitments"] != EXPECTED_COMMITMENTS:
        failures.append("opaque private receipt commitments differ from the public contract")

    geometry = data["protocol_geometry"]
    counts = data["aggregate_counts"]
    gates = data["gate_results"]
    if geometry != {
        "synthetic_artifacts": 20, "target_artifacts": 16, "control_artifacts": 4, "arms": 2,
        "repetitions_per_cell": 3, "logical_slots": 120, "one_leaf_per_provider_request": True,
        "execution_route": "codex_gpt_5_6_sol_high",
    }:
        failures.append("protocol geometry differs from the public contract")
    if counts != {"planned_slots": 120, "completed_slots": 120, "first_attempt_accepted_slots": 120, "retries": 0}:
        failures.append("aggregate counts differ from the public contract")
    expected_gates = {
        "current_controls": {"passed": 12, "total": 12},
        "treatment_controls": {"passed": 12, "total": 12},
        "combined_controls": {"passed": 24, "total": 24},
        "current_target_cells": {"passed": 15, "total": 16},
        "treatment_target_cells": {"passed": 15, "total": 16},
        "current_raw_target_matches": {"matched": 47, "total": 48},
        "treatment_raw_target_matches": {"matched": 46, "total": 48},
        "target_improvements": 0,
        "stable_defect_in_both_families": False,
    }
    if gates != expected_gates:
        failures.append("NO_EFFECT gate results differ from the public contract")
    elif not (
        geometry["target_artifacts"] + geometry["control_artifacts"] == geometry["synthetic_artifacts"]
        and geometry["synthetic_artifacts"] * geometry["arms"] * geometry["repetitions_per_cell"] == counts["planned_slots"]
        == counts["completed_slots"] == counts["first_attempt_accepted_slots"] == geometry["logical_slots"]
        and gates["current_controls"]["passed"] + gates["treatment_controls"]["passed"] == gates["combined_controls"]["passed"]
        and gates["current_controls"]["total"] + gates["treatment_controls"]["total"] == gates["combined_controls"]["total"]
        and gates["current_target_cells"]["passed"] == gates["treatment_target_cells"]["passed"]
        and gates["target_improvements"] == 0
        and gates["stable_defect_in_both_families"] is False
    ):
        failures.append("NO_EFFECT gate arithmetic is inconsistent")

    expected_limitations = [
        "Aggregate-only public projection: no fixture text, fixture aliases, expected labels, per-cell or per-slot outcomes, prompts, model outputs, private evidence, paths, or provider/session/request metadata.",
        "NO_EFFECT means no treatment benefit is demonstrated under this frozen aggregate gate; it does not establish identical per-fixture outcomes or equal general performance.",
        "The exact candidate appendix was exhausted: no qualifying cell benefit was shown, so the figurative gate remains closed.",
        "This holdout result authorizes no prompt, rubric, leaf, ownership, split, or weight change. Promotion is none.",
        "The sealed private settlement remains the receipt-level verification authority; this package binds retained source commitments through opaque SHA-256 commitments without copying private material.",
    ]
    if data["limitations"] != expected_limitations:
        failures.append("aggregate limitations differ from the public contract")

    readme = _read_text(readme_path)
    for claim in REQUIRED_READER_CLAIMS:
        if claim not in readme:
            failures.append(f"required reader claim is missing: {claim!r}")
    return failures


def main() -> int:
    failures = check()
    if failures:
        print("P1 NO_EFFECT public result verification failed:")
        print("\n".join(f"- {failure}" for failure in failures))
        return 1
    print("P1 NO_EFFECT public result verification passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
