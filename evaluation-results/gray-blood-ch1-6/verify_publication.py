#!/usr/bin/env python3
"""Verify the public-only invariants for the Gray Blood publication package."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sanitize_publication import FORBIDDEN_KEY_PARTS, FORBIDDEN_TEXT_PATTERNS, files_for_audit, tree_hash


JUDGE = {"model": "gpt-5.6-sol", "provider": "codex", "reasoning": "high"}
NGRAM_SIZES = {"4", "8", "12", "20", "40"}


def forbidden_keys(value, location: str = "$") -> list[str]:
    findings: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_location = f"{location}.{key}"
            if any(part in key.lower() for part in FORBIDDEN_KEY_PARTS):
                findings.append(child_location)
            findings.extend(forbidden_keys(child, child_location))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            findings.extend(forbidden_keys(child, f"{location}[{index}]"))
    return findings


def exact_keys(value, expected: set[str], location: str) -> list[str]:
    if not isinstance(value, dict):
        return [f"invalid metadata object at {location}"]
    if set(value) != expected:
        return [f"invalid metadata keys at {location}"]
    return []


def validate_metadata(manifest: dict, audit: dict, expected_files: dict[str, str]) -> list[str]:
    failures: list[str] = []
    failures.extend(
        exact_keys(manifest, {"evaluation_id", "files", "protocol", "publication", "results"}, "manifest")
    )
    if manifest.get("evaluation_id") != "gray-blood-chapters-1-6-current-comparison-v2":
        failures.append("invalid manifest evaluation identifier")
    if manifest.get("files") != expected_files:
        failures.append("invalid manifest file metadata")
    protocol = manifest.get("protocol")
    failures.extend(
        exact_keys(
            protocol,
            {
                "binary_judge",
                "bundle_versions",
                "chapter_bundle",
                "chapter_count_per_draft",
                "chapter_verdicts_per_draft",
                "comparison_scope",
                "global_bundle",
                "minimum_coverage",
                "orientation_and_synthesis",
                "standard",
                "structured_judge",
                "whole_work_verdicts_per_draft",
            },
            "manifest.protocol",
        )
    )
    if isinstance(protocol, dict):
        if protocol.get("binary_judge") != JUDGE or protocol.get("structured_judge") != JUDGE:
            failures.append("invalid manifest judge metadata")
        if protocol.get("orientation_and_synthesis") != JUDGE:
            failures.append("invalid manifest synthesis metadata")
        if protocol.get("bundle_versions") != {"prose.chapter": 1, "prose.novel": 1}:
            failures.append("invalid manifest bundle metadata")
        if protocol.get("standard") != {"id": "HBQ-RS", "version": "1.0.0"}:
            failures.append("invalid manifest standard metadata")
        expected_scalars = {
            "chapter_bundle": "prose.chapter",
            "chapter_count_per_draft": 6,
            "chapter_verdicts_per_draft": 1368,
            "comparison_scope": "complete current six-chapter WIP protocol; not a sampled-to-full comparison",
            "global_bundle": "prose.novel",
            "minimum_coverage": 0.8,
            "whole_work_verdicts_per_draft": 239,
        }
        if any(protocol.get(key) != value for key, value in expected_scalars.items()):
            failures.append("invalid manifest protocol values")
    publication = manifest.get("publication")
    failures.extend(
        exact_keys(
            publication,
            {"evidence_text_included", "execution_metadata_included", "manuscript_prose_included", "published_verdicts"},
            "manifest.publication",
        )
    )
    if publication != {
        "evidence_text_included": False,
        "execution_metadata_included": False,
        "manuscript_prose_included": False,
        "published_verdicts": 3214,
    }:
        failures.append("invalid manifest publication metadata")
    results = manifest.get("results")
    failures.extend(exact_keys(results, {"original", "rewrite"}, "manifest.results"))
    if isinstance(results, dict):
        for draft in ("original", "rewrite"):
            failures.extend(
                exact_keys(results.get(draft), {"whole_work_observed", "wip_70_30_observed"}, f"manifest.results.{draft}")
            )
            if isinstance(results.get(draft), dict) and not all(
                isinstance(value, (int, float)) for value in results[draft].values()
            ):
                failures.append(f"invalid manifest result values for {draft}")

    failures.extend(
        exact_keys(
            audit,
            {
                "audited_file_count",
                "audited_total_bytes",
                "exact_source_prose_ngram_hits",
                "explicit_private_term_hits",
                "forbidden_pattern_hits",
                "format_version",
                "ngram_normalization",
                "tree_sha256",
            },
            "privacy-audit",
        )
    )
    if audit.get("format_version") != 2:
        failures.append("invalid privacy-audit version")
    if audit.get("ngram_normalization") != "lowercase ASCII alphanumeric tokens; exact contiguous token sequences":
        failures.append("invalid privacy-audit normalization")
    if not isinstance(audit.get("tree_sha256"), str) or not re.fullmatch(r"[0-9a-f]{64}", audit["tree_sha256"]):
        failures.append("invalid privacy-audit tree hash")
    if not isinstance(audit.get("audited_file_count"), int) or audit["audited_file_count"] <= 0:
        failures.append("invalid privacy-audit file count")
    if not isinstance(audit.get("audited_total_bytes"), int) or audit["audited_total_bytes"] <= 0:
        failures.append("invalid privacy-audit byte count")
    patterns = audit.get("forbidden_pattern_hits")
    if not isinstance(patterns, dict) or set(patterns) != set(FORBIDDEN_TEXT_PATTERNS):
        failures.append("invalid privacy-audit pattern metadata")
    elif any(not isinstance(count, int) or count != 0 for count in patterns.values()):
        failures.append("invalid privacy-audit pattern values")
    terms = audit.get("explicit_private_term_hits")
    if not isinstance(terms, dict) or not terms or any(
        not re.fullmatch(r"[0-9a-f]{64}", key) or not isinstance(count, int) or count != 0
        for key, count in terms.items()
    ):
        failures.append("invalid privacy-audit private-literal metadata")
    ngrams = audit.get("exact_source_prose_ngram_hits")
    if not isinstance(ngrams, dict) or set(ngrams) != {"original", "rewrite"}:
        failures.append("invalid privacy-audit n-gram metadata")
    elif any(
        not isinstance(ngrams[draft], dict)
        or set(ngrams[draft]) != NGRAM_SIZES
        or any(not isinstance(count, int) or count != 0 for count in ngrams[draft].values())
        for draft in ("original", "rewrite")
    ):
        failures.append("invalid privacy-audit n-gram values")
    return failures


def check(root: Path) -> list[str]:
    failures: list[str] = []
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    audit = json.loads((root / "privacy-audit.json").read_text(encoding="utf-8"))
    if tree_hash(root) != audit.get("tree_sha256"):
        failures.append("privacy-audit tree hash does not match package")
    expected_files = {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in files_for_audit(root)
    }
    for path in files_for_audit(root):
        if b"\r" in path.read_bytes():
            failures.append(f"non-LF byte in audited file: {path.relative_to(root)}")
    if manifest.get("files") != expected_files:
        failures.append("manifest file hashes do not match package")
    failures.extend(validate_metadata(manifest, audit, expected_files))
    package_text = "\n".join(
        path.read_text(encoding="utf-8", errors="ignore") for path in files_for_audit(root)
    )
    for name, pattern in FORBIDDEN_TEXT_PATTERNS.items():
        if pattern.search(package_text):
            failures.append(f"forbidden public pattern: {name}")
        if not isinstance(audit.get("forbidden_pattern_hits"), dict) or audit["forbidden_pattern_hits"].get(name) != 0:
            failures.append(f"privacy audit did not record zero hits: {name}")
    ngram_hits = audit.get("exact_source_prose_ngram_hits")
    if not isinstance(ngram_hits, dict):
        failures.append("privacy audit has no source-prose n-gram results")
    else:
        for draft in ("original", "rewrite"):
            draft_hits = ngram_hits.get(draft)
            if not isinstance(draft_hits, dict):
                failures.append(f"privacy audit has no n-gram results for {draft}")
                continue
            for size, count in draft_hits.items():
                if not isinstance(count, int) or count != 0:
                    failures.append(f"privacy audit found source-prose overlap for {draft}/{size}")
    literal_hits = audit.get("explicit_private_term_hits")
    if not isinstance(literal_hits, dict) or not literal_hits:
        failures.append("privacy audit has no private-literal commitments")
    elif any(not isinstance(count, int) or count != 0 for count in literal_hits.values()):
        failures.append("privacy audit found a committed private literal")
    for path in sorted(root.rglob("*.json")):
        if path.name in {"manifest.json", "privacy-audit.json"}:
            continue
        for key in forbidden_keys(json.loads(path.read_text(encoding="utf-8"))):
            failures.append(f"forbidden public key in {path.relative_to(root)}: {key}")
    for path in sorted((root / "verdicts").glob("*.jsonl")):
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            for key in forbidden_keys(json.loads(line)):
                failures.append(f"forbidden public key in {path.name}:{line_number}: {key}")
    verdict_count = 0
    allowed = {"bundle", "confidence", "question_id", "scope", "verdict"}
    for path in sorted((root / "verdicts").glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            record = json.loads(line)
            verdict_count += 1
            if set(record) != allowed:
                failures.append(f"unexpected verdict fields in {path.name}")
                break
    publication = manifest.get("publication")
    expected_verdicts = publication.get("published_verdicts") if isinstance(publication, dict) else None
    if verdict_count != expected_verdicts:
        failures.append(f"expected {expected_verdicts} verdicts, got {verdict_count}")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", default=Path(__file__).parent, type=Path)
    args = parser.parse_args()
    failures = check(args.root.resolve())
    if failures:
        raise SystemExit("\n".join(failures))
    print("Gray Blood public package verification passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
