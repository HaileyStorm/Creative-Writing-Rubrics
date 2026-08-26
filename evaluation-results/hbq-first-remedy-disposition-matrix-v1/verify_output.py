"""Verify the aggregate-only first-remedy disposition matrix."""

from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import sys

import yaml


sys.dont_write_bytecode = True


HERE = Path(__file__).resolve().parent
REPOSITORY_ROOT = HERE.parents[1]
MATRIX_NAME = "matrix.v1.json"
README_NAME = "README.md"
MATRIX_SHA256 = "9cc03064952dad3d649459ba6f4f25b1dc34d79cc014c494e1c26d58283178b6"
README_SHA256 = "a9e47e3e47ea0f2962e8bdcc71af787cbe75cf57727659625008ad9f5fa3cfdc"
ALLOWED_FILES = {MATRIX_NAME, README_NAME, Path(__file__).name}
ALLOWED_DISPOSITIONS = {
    "PROMOTED_WORDING_ONLY",
    "NO_CHANGE_NO_PROMOTION",
    "NO_EFFECT_NO_PROMOTION",
    "DIAGNOSTIC_FAIL_NO_PROMOTION",
    "DEFERRED_UNTESTED",
    "WATCH",
}
EXPECTED_GEOMETRY = {"R0": 2, "L1": 1, "L2": 3, "P1": 11, "S1": 35, "S2": 25}
EXPECTED_PROMOTED = {
    "form.poetry.free_verse.repetition",
    "scope.passage.status",
}
EXPECTED_BINDINGS = {
    "portfolio_manifest": {"path": "evaluation-results/hbq-first-remedy-portfolio-v1/manifest.json", "sha256": "eebe2ac7a7b592459e5b084d8f6806a56ccd7a8c077e6508b34e0a0818111d32"},
    "findings": {"path": "evaluation-results/hbq-full-leaf-structural-audit-v1/findings.jsonl", "sha256": "06c08ef035a09288fa6710db51786ec1a73b71116ac9b23e4c2a09ece8fa14a1"},
    "triage": {"path": "evaluation-results/hbq-full-leaf-structural-audit-v1/sol-triage.jsonl", "sha256": "f5427aead55b3a17fbe24917d56dba7a50efd8c4a6ce55602c6280b3ddee67e9"},
}
SETTLED_PUBLIC_RESULTS = {
    "r0_figurative_no_go": {"path": "evaluation-results/hbq-figurative-scope-treatment-v1-execution-v1/public-result.json", "sha256": "1527cbf9299d9ca83c328101cd15e146e5f8e841c495d1b192a33f51e759534e", "expected": {"decision": "NO_GO"}},
    "l1_premise_diagnostic_fail": {"path": "evaluation-results/hbq-premise-scale-ownership-v1-result-v1/premise-scale-ownership-public-aggregate.v1.json", "sha256": "bd2fd0f9cb6fcf7e30df54b1759548b48648a7643f361d118e8c72b0a479cc33", "expected": {"decision": "DIAGNOSTIC_FAIL", "promotion": "none"}},
    "l2_necessity_negative_discrimination": {"path": "evaluation-results/hbq-free-verse-necessity-scope-ablation-v1-public-result-v1/aggregate.v1.json", "sha256": "7b21d67529a86313f3b1d4a62c90b22960ac47ec4a57cbb9d49ac05b11c12911", "expected": {"classification": "VALID_EXECUTION_NEGATIVE_DISCRIMINATION_NO_PROMOTION", "promotion": "none"}},
    "l2_original_completed_diagnostic_settlement": {"path": "evaluation-results/hbq-other-lexical-overlap-ownership-v1-settlement-crlf-lf-repair-v1/study-contract.json", "sha256": "a88893f79b2c49db33c0334908c1baf07149f792df5b9c0dc53e507853f18abd", "expected": {"study_id": "hbq-other-lexical-overlap-ownership-v1-settlement-crlf-lf-repair-v1", "geometry": {"execution_slots": 216, "three_repeat_cells": 72, "visual_attachment_slots": 72}, "public_result_policy": "aggregate_only_verified_diagnostic_fail_or_incomplete_no_promotion", "promotion": "none"}},
    "l2_public_completion_statement": {"path": "docs/VALIDATION_AND_REPAIR_JOURNEY.md", "normalized_excerpt": "L2 verified 216 completed slots after a narrowly bounded CRLF-to-LF settlement repair but remained a diagnostic failure.", "normalized_excerpt_sha256": "6125dee67a35560ca79a54db1dffcb97be7b9e76d120d996e8b5b4b5a4100133"},
    "l2_visual_control_no_go": {"path": "evaluation-results/hbq-l2-c03-visual-control-successor-v1-execution-v1-public-result-v1/public-result.json", "sha256": "3b13893b7bea1f7f95d9700e796619635cbc14a80170d22f511b8ad9721e75b3", "expected": {"decision": "NO_GO", "promotion": "none"}},
    "p1_no_effect": {"path": "evaluation-results/hbq-polarity-change-manual-treatment-holdout-v1-result-v1/p1-manual-treatment-holdout-public-aggregate.v1.json", "sha256": "b6e5169dd044675cbb4665c0e39ab13348ec1fea6268398fb05e714ec0d6feec", "expected": {"decision": "NO_EFFECT", "promotion": "none"}},
    "s1_repetition_settled_evidence": {"path": "evaluation-results/hbq-poetry-free-verse-repetition-incidental-determiner-holdout-v2-execution-v2-public-result-v1/public-result.json", "sha256": "8fe7b6c9a1649cbd85de51056772660dd12a60a6fcc070b96480d5288ac7fc56", "expected": {"settlement_decision": "HOLDOUT_ELIGIBLE_ON_SUCCESS", "promotion": "none_pending_final_review"}},
    "s2_status_settled_evidence": {"path": "evaluation-results/hbq-nonpoetry-scope-disjoint-confirmation-v2-public-result-v1/public-result.json", "sha256": "3a4ea6e9a2c81b58aa1c211903df8840df1e392d8a2e37da02be9521a75f9df3", "expected": {"decision": "INDEPENDENT_WORDING_ONLY_PROMOTION_REVIEW_ELIGIBLE", "independent_wording_review": "GO_FOR_EXACT_CANDIDATE", "promotion": "none_pending_integration"}},
}
CURRENT_REGISTRY_LEAF_BINDINGS = {
    "form.poetry.free_verse.necessity": {"path": "registry/modules/form.poetry.free_verse.yaml", "canonical_leaf_sha256": "7914f1d01d564b15a9e0d052b5d743002fd1670864e8e91c0c1a76e3320cf7c3"},
    "form.poetry.free_verse.repetition": {"path": "registry/modules/form.poetry.free_verse.yaml", "canonical_leaf_sha256": "96d3d0be58fda40ba83eeacdf72c4e8bb60cd0b5bac13f80b42013b29d3c0be8"},
    "scope.passage.status": {"path": "registry/modules/scope.passage.yaml", "canonical_leaf_sha256": "dbb3cd01d1e47c9f57a6a13057c7def508c44a29c532178c5177ef0804fa7edd"},
}
SETTLED_ROW_KEYS = {
    "c4d62097ce12016c7f3def32d2b8102c19344c316844f38c3b0b1256e2f602c4": "r0_figurative_no_go",
    "f87df46f698107ebebffe8a5dbd420efc332694897aa34c7f2a8efa6ce18ac62": "r0_figurative_no_go",
    "e570a82272e16eceda10aa5d59ad35f17e85734bd3f524c71027410fcf0565b5": "l1_premise_diagnostic_fail",
    "338b510127809018cc8f14b2674e5960ac6bb70d8692e7af300d74a3eab0ed80": "l2_necessity_negative_discrimination",
    "984e94e56c811360f817c98f76022d74e2c399454dec8874078bc70e59198bc4": "l2_original_completed_diagnostic_settlement",
    "ff3c0acd77e9eae45b077e6ffe458c8c7b34e00fac6606f1e581d5a37755cb9a": "l2_visual_control_no_go",
    "0bd6d60cc6d3fc8cc68812761f59acfcab4c2de7b1ae6e5c711d6cbb42edce37": "s1_repetition_settled_evidence",
    "eb17cc18285de2bf8614389623255d9b5df9d5e0f85fac16fde6a79a2c8023d6": "s2_status_settled_evidence",
}
SETTLED_ROW_KEYS.update({
    finding_id: "p1_no_effect"
    for finding_id in (
        "cd890d802fe78388cbbe684615894473dffda2b5b1eab8b3ae6ca6acfa806e26", "8e14f58a8faf4f80734ef6b10fa18bbdfce3c8e58cdf1823f54314c70638db65", "c7ee0bdfcaf98db40d37f38f4de67d66dd709f56db748df0a83ffba39f979cf2", "8a6326c8c665cccf14c2f931a4acde9ebc1117211e6cec1454829dc4dd507afe", "82d1e80a0970c07c6c4b8a6340aed3744a5182fddf8793863e93ca315875c14d", "11d98b6de654dd40e64af4e784061fb6ef59d57e9bd0f866407efa9ae52964db", "e6e5ad3862be84811980db705f4dd6e5ac29533f3d049c78db47df4d51e82b28", "dd6f1489415df0938adf2d8388d07bfe95363f45d9500850d086651493ef9b6d", "bb38fcb28b25e66341d4e56065fbb6f5476bf07c4afb5990002fe20bde0472ae", "3f93b906a04f9c76134f1f91dbf1c895023afa548035dfe1afea8cbb21017d34", "d0e5d4aa61643ec9b73e240f9fa93ce47711fca5473becb2f4f8788695fab354",
    )
})
FORBIDDEN_PUBLIC_PATTERNS = (
    ("Windows path", r"[A-Za-z]:[\\/]"),
    ("home-directory path", r"(?:^|[\\/])(?:Users|home)(?:[\\/]|$)"),
    ("non-public directory", r"\.private"),
    ("session identifier", r"session_id"),
    ("request identifier", r"request_id"),
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _jsonl(path: Path) -> dict[str, dict]:
    return {row["finding_id"]: row for row in (json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line)}


def _find_leaf(value: object, leaf_id: str) -> dict | None:
    if isinstance(value, dict):
        if value.get("id") == leaf_id:
            return value
        for child in value.values():
            found = _find_leaf(child, leaf_id)
            if found is not None:
                return found
    if isinstance(value, list):
        for child in value:
            found = _find_leaf(child, leaf_id)
            if found is not None:
                return found
    return None


def _canonical_leaf_sha256(path: Path, leaf_id: str) -> str:
    leaf = _find_leaf(yaml.safe_load(path.read_text(encoding="utf-8")), leaf_id)
    if leaf is None:
        raise ValueError(f"Missing registry leaf: {leaf_id}")
    return hashlib.sha256(json.dumps(leaf, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _completion_statement_failure(path: Path, binding: dict) -> str | None:
    if not path.is_file():
        return "L2 public completion statement is missing"
    document = path.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")
    excerpt = binding["normalized_excerpt"].replace("\r\n", "\n").replace("\r", "\n")
    if document.count(excerpt) != 1:
        return "L2 public completion statement is missing or non-unique"
    if hashlib.sha256(excerpt.encode("utf-8")).hexdigest() != binding["normalized_excerpt_sha256"]:
        return "L2 public completion statement commitment drifted"
    return None


def check(root: Path = HERE) -> list[str]:
    failures: list[str] = []
    entries = {path.relative_to(root).as_posix() for path in root.rglob("*")}
    if entries != ALLOWED_FILES:
        failures.append(f"public package tree allowlist mismatch: {sorted(entries)}")
    matrix_path = root / MATRIX_NAME
    readme_path = root / README_NAME
    if not matrix_path.is_file() or not readme_path.is_file():
        return [*failures, "required package files are missing"]
    if _sha256(matrix_path) != MATRIX_SHA256:
        failures.append("matrix SHA-256 does not match the fixed public projection")
    if _sha256(readme_path) != README_SHA256:
        failures.append("README SHA-256 does not match the fixed public interpretation")
    public_text = "\n".join(path.read_text(encoding="utf-8") for path in (matrix_path, readme_path))
    for label, pattern in FORBIDDEN_PUBLIC_PATTERNS:
        if re.search(pattern, public_text, flags=re.IGNORECASE):
            failures.append(f"forbidden public material: {label}")
    data = _json(matrix_path)
    expected_keys = {"format", "scope", "source_bindings", "settled_public_results", "current_registry_leaf_bindings", "package_geometry", "promoted_wording_only_leaf_ids", "rows"}
    if set(data) != expected_keys:
        return [*failures, "matrix top-level allowlist mismatch"]
    if data["format"] != "hbq-first-remedy-disposition-matrix-v1" or data["scope"] != "aggregate_only_public":
        failures.append("matrix identity or scope drifted")
    if data["source_bindings"] != EXPECTED_BINDINGS:
        failures.append("source bindings drifted")
    if data["settled_public_results"] != SETTLED_PUBLIC_RESULTS:
        failures.append("settled public-result bindings drifted")
    if data["current_registry_leaf_bindings"] != CURRENT_REGISTRY_LEAF_BINDINGS:
        failures.append("current registry leaf bindings drifted")
    if data["package_geometry"] != EXPECTED_GEOMETRY:
        failures.append("package geometry drifted")
    if set(data["promoted_wording_only_leaf_ids"]) != EXPECTED_PROMOTED or len(data["promoted_wording_only_leaf_ids"]) != 2:
        failures.append("wording-only promotion set drifted")
    for binding in EXPECTED_BINDINGS.values():
        path = REPOSITORY_ROOT / binding["path"]
        if not path.is_file() or _sha256(path) != binding["sha256"]:
            failures.append(f"bound source drifted: {binding['path']}")
    for key, binding in SETTLED_PUBLIC_RESULTS.items():
        if key == "l2_public_completion_statement":
            failure = _completion_statement_failure(REPOSITORY_ROOT / binding["path"], binding)
            if failure:
                failures.append(failure)
            continue
        path = REPOSITORY_ROOT / binding["path"]
        if not path.is_file() or _sha256(path) != binding["sha256"]:
            failures.append(f"settled public result drifted: {key}")
            continue
        result = _json(path)
        if any(result.get(field) != value for field, value in binding["expected"].items()):
            failures.append(f"settled public result semantics drifted: {key}")
    for leaf_id, binding in CURRENT_REGISTRY_LEAF_BINDINGS.items():
        path = REPOSITORY_ROOT / binding["path"]
        if not path.is_file() or _canonical_leaf_sha256(path, leaf_id) != binding["canonical_leaf_sha256"]:
            failures.append(f"current registry leaf binding drifted: {leaf_id}")
    portfolio = _json(REPOSITORY_ROOT / EXPECTED_BINDINGS["portfolio_manifest"]["path"])
    expected_ids = [finding_id for package in portfolio["packages"] for finding_id in package["finding_ids"]]
    source_findings = _jsonl(REPOSITORY_ROOT / EXPECTED_BINDINGS["findings"]["path"])
    source_triage = _jsonl(REPOSITORY_ROOT / EXPECTED_BINDINGS["triage"]["path"])
    rows = data["rows"]
    if len(rows) != 77 or len({row.get("finding_id") for row in rows}) != 77:
        failures.append("matrix must contain 77 unique finding rows")
        return failures
    if [row["finding_id"] for row in rows] != expected_ids:
        failures.append("finding membership or order drifted from the frozen portfolio")
    if Counter(row["package_id"] for row in rows) != EXPECTED_GEOMETRY:
        failures.append("row package counts drifted")
    allowed_row_keys = {"finding_id", "package_id", "subjects", "disposition", "wording_promotion_leaf_ids", "structural_changes"}
    for row in rows:
        if set(row) != allowed_row_keys:
            failures.append(f"row field allowlist drifted: {row.get('finding_id')}")
            continue
        finding_id = row["finding_id"]
        if row["subjects"] != source_findings.get(finding_id, {}).get("subjects"):
            failures.append(f"subject binding drifted: {finding_id}")
        if source_triage.get(finding_id, {}).get("decision") != "needs_empirical_test":
            failures.append(f"triage binding drifted: {finding_id}")
        if row["disposition"] not in ALLOWED_DISPOSITIONS:
            failures.append(f"unknown disposition: {finding_id}")
        if row["structural_changes"] != {"split": False, "owner_change": False, "weight_change": False}:
            failures.append(f"unsupported structural change: {finding_id}")
        promoted = set(row["wording_promotion_leaf_ids"])
        if not promoted.issubset(set(row["subjects"])) or not promoted.issubset(EXPECTED_PROMOTED):
            failures.append(f"invalid wording promotion scope: {finding_id}")
        if bool(promoted) != (row["disposition"] == "PROMOTED_WORDING_ONLY"):
            failures.append(f"disposition and wording promotion mismatch: {finding_id}")
        if row["disposition"] == "DEFERRED_UNTESTED" and finding_id in SETTLED_ROW_KEYS:
            failures.append(f"settled finding is incorrectly deferred: {finding_id}")
        if row["disposition"] != "DEFERRED_UNTESTED" and SETTLED_ROW_KEYS.get(finding_id) is None:
            failures.append(f"asserted settled disposition lacks public result binding: {finding_id}")
    promoted_rows = [row for row in rows if row["disposition"] == "PROMOTED_WORDING_ONLY"]
    if {leaf for row in promoted_rows for leaf in row["wording_promotion_leaf_ids"]} != EXPECTED_PROMOTED or len(promoted_rows) != 2:
        failures.append("promoted wording rows drifted")
    l2 = [row for row in rows if row["package_id"] == "L2"]
    if l2[0]["wording_promotion_leaf_ids"] or l2[0]["disposition"] != "NO_CHANGE_NO_PROMOTION" or "scope.poetry_poem.form" not in l2[0]["subjects"]:
        failures.append("L2 paired-scope treatment drifted")
    if any(row["disposition"] != "NO_EFFECT_NO_PROMOTION" for row in rows if row["package_id"] == "P1"):
        failures.append("P1 no-effect disposition drifted")
    if rows[2]["disposition"] != "DIAGNOSTIC_FAIL_NO_PROMOTION":
        failures.append("L1 diagnostic disposition drifted")
    return failures


def main() -> int:
    failures = check()
    if failures:
        print("First-remedy disposition matrix verification failed:")
        print("\n".join(f"- {failure}" for failure in failures))
        return 1
    print("First-remedy disposition matrix verification passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
