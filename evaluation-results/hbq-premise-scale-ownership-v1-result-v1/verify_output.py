"""Verify the aggregate-only public premise-scale ownership result."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path


HERE = Path(__file__).resolve().parent
AGGREGATE_NAME = "premise-scale-ownership-public-aggregate.v1.json"
README_NAME = "README.md"
AGGREGATE_SHA256 = "bd2fd0f9cb6fcf7e30df54b1759548b48648a7643f361d118e8c72b0a479cc33"
README_SHA256 = "0924a1415cca7bf5e17d5221a24b13a602b7f5e74965731b333ee19700812850"
ALLOWED_FILES = {AGGREGATE_NAME, README_NAME, Path(__file__).name}
EXPECTED_COMMITMENTS = {
    "settlement_repair_settlement_sha256": "397c5691ea31fd6518760211f8c685c0165ee8277d33baf40b1b95df8e7153ff",
    "settlement_repair_public_aggregate_sha256": "1cc855d75221ab1e1770b5d211dae49e64b8508428f5d49ecb63c4a39b83ca57",
    "settlement_repair_contract_sha256": "c5d615a04b4353eee1a38851889fda374c02cc065a043989a42e214ff85f9c6c",
    "settlement_repair_runtime_sha256": "894767d419065d9dbde309de67ac8b088abbe18384302512e5e2047892fe72b2",
    "execution_contract_sha256": "235ef070ed0689d44843bd39a093324046448e3ce58910e67522a61680f909dc",
    "execution_runtime_sha256": "960ee843f9fbde0b32756872409665fbc65a930f3699c51f07c24782ee084b43",
    "execution_tree_sha1": "2c4dc6fee8332eaf52e04288e107c0f0c7fe317c",
    "settlement_repair_tree_sha1": "7438cba2c96441ec46814c029f35e482adcef0a3",
}
FORBIDDEN_PATTERNS = (
    ("Windows path", r"[A-Za-z]:[\\/]"),
    ("home-directory path", r"(?:^|[\\/])(?:Users|home)(?:[\\/]|$)"),
    ("private directory", r"\.private"),
    ("fixture alias", r"\b(?:fixture_id|artifact_id|case_id|pair_id)\b"),
    ("expected label", r"\b(?:expected_label|expected_verdict|expected_state)\b"),
    ("per-case result", r'"(?:cells|cell_id|slot_id|verdict)"|\b(?:cell_id|slot_id|verdict)\b'),
    ("prompt or response", r"\b(?:raw_prompt|raw_response|exact_quote|model_output)\b"),
    ("provider metadata", r"\b(?:session_id|request_id|run_id|judge_id)\b"),
    ("private artifact filename", r"(?:settlement-repair-v1\.json|public-aggregate-repair-v1\.json|runtime-schedule\.json)"),
)
REQUIRED_READER_CLAIMS = (
    "aggregate-only public result",
    "All 72 of 72 singleton slots completed and were accepted on their first\nattempt",
    "**DIAGNOSTIC_FAIL**",
    "Nine of 20 scored cells passed",
    "37/72 overall raw matches",
    "does not identify fixtures, cells,\nslot outcomes, or their expected states",
    "No promotion follows from this result",
    "no prompt, rubric, leaf,\nownership, split, or weight change",
    "sealed private settlement remains the\nreceipt-level verification authority",
)


def _json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("aggregate must be a JSON object")
    return value


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

    public_text = "\n".join((aggregate_path.read_text(encoding="utf-8"), readme_path.read_text(encoding="utf-8")))
    for label, pattern in FORBIDDEN_PATTERNS:
        if re.search(pattern, public_text, flags=re.IGNORECASE):
            failures.append(f"forbidden public content: {label}")

    try:
        data = _json(aggregate_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return [*failures, f"aggregate is malformed: {exc}"]
    expected_keys = {
        "format_version", "study_id", "evidence_scope", "public_cwr_lineage", "protocol_geometry",
        "decision", "promotion", "promotion_scope", "aggregate_counts", "limitations",
        "opaque_private_receipt_commitments",
    }
    if set(data) != expected_keys:
        return [*failures, "aggregate top-level allowlist mismatch"]
    if data["format_version"] != 1 or data["study_id"] != "hbq-premise-scale-ownership-v1-settlement-repair-v1":
        failures.append("aggregate identity differs from the public contract")
    if data["evidence_scope"] != "aggregate_only_completed_premise_scale_ownership_screen":
        failures.append("aggregate evidence scope differs from the public contract")
    if data["public_cwr_lineage"] != {
        "frozen_screen_commit": "95a86b8353b4d27c85914d4258e4da33d080f9d7",
        "execution_runtime_commit": "3258e6f44bb728ce17ebcd85b4964d472aaf87c2",
        "settlement_repair_commit": "80f57bddb659f9f42831f096a23108642ec0be9c",
    }:
        failures.append("aggregate CWR lineage differs from the public contract")
    if data["decision"] != "DIAGNOSTIC_FAIL" or data["promotion"] != "none" or data["promotion_scope"] != "none":
        failures.append("public decision or promotion differs from the public contract")
    if data["opaque_private_receipt_commitments"] != EXPECTED_COMMITMENTS:
        failures.append("opaque private receipt commitments differ from the public contract")

    geometry = data["protocol_geometry"]
    counts = data["aggregate_counts"]
    if geometry != {
        "synthetic_artifacts": 12, "selected_leaves": 2, "repetitions_per_cell": 3, "logical_slots": 72,
        "one_leaf_per_provider_request": True, "execution_route": "codex_gpt_5_6_sol_high",
    }:
        failures.append("protocol geometry differs from the public contract")
    if counts != {
        "planned_slots": 72, "completed_slots": 72, "first_attempt_accepted_slots": 72,
        "scored_cells": 20, "scored_cells_passing": 9, "overall_raw_matches": 37,
        "overall_raw_match_total": 72,
    }:
        failures.append("aggregate counts differ from the public contract")
    elif not (
        geometry["synthetic_artifacts"] * geometry["selected_leaves"] * geometry["repetitions_per_cell"]
        == counts["planned_slots"] == counts["completed_slots"] == counts["first_attempt_accepted_slots"]
        == geometry["logical_slots"] == counts["overall_raw_match_total"]
        and counts["scored_cells_passing"] < counts["scored_cells"]
        and counts["overall_raw_matches"] < counts["overall_raw_match_total"]
    ):
        failures.append("aggregate arithmetic is inconsistent")
    if data["limitations"] != [
        "Aggregate-only public projection: no fixture text, fixture aliases, expected labels, per-cell or per-slot outcomes, prompts, responses, private evidence, paths, or provider/session/request/run identifiers.",
        "DIAGNOSTIC_FAIL does not establish a general result or causal diagnosis.",
        "This result authorizes no prompt, rubric, leaf, ownership, split, or weight change. Promotion is none.",
        "The sealed private settlement remains the receipt-level verification authority; this package binds retained source commitments through opaque SHA-256 commitments without copying private material.",
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
        print("Premise-scale public result verification failed:")
        print("\n".join(f"- {failure}" for failure in failures))
        return 1
    print("Premise-scale public result verification passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
