#!/usr/bin/env python3
"""Bind completed development evidence before the held-out confirmatory phase."""
from __future__ import annotations

import argparse
from pathlib import Path

from analyze_study import verify_phase_runs
from study import canonical_json, sha256_path, validate_frozen_contract, write_json


def create_gate(work_dir: Path, development_analysis: Path) -> None:
    frozen = validate_frozen_contract(work_dir)
    verify_phase_runs(work_dir, frozen, "development")
    manifest = development_analysis / "manifest.json"
    summary = development_analysis / "summary.json"
    if not manifest.is_file() or not summary.is_file():
        raise ValueError("Confirmation gate requires a completed development analysis and manifest")
    manifest_value, summary_value = __import__("json").loads(manifest.read_text(encoding="utf-8")), __import__("json").loads(summary.read_text(encoding="utf-8"))
    commitments = {"study_id": frozen["study_id"], "phase": "development", "package_commit": frozen["package_commit"], "mapping_sets_sha256": frozen["mapping_sets_sha256"], "question_ids_sha256": __import__("hashlib").sha256(canonical_json(frozen["question_ids"])).hexdigest()}
    if any(manifest_value.get(key) != value for key, value in commitments.items()) or summary_value.get("study_id") != frozen["study_id"] or summary_value.get("phase") != "development":
        raise ValueError("Development analysis does not bind the frozen study commitments")
    if any(not (development_analysis / relative).is_file() or sha256_path(development_analysis / relative) != record["sha256"] for relative, record in manifest_value.get("files", {}).items()):
        raise ValueError("Development analysis manifest file hashes do not verify")
    destination = work_dir / "confirmation-gate.json"
    if destination.exists():
        raise ValueError("Confirmation gate already exists; it is immutable")
    write_json(destination, {
        "format_version": 1,
        "study_id": frozen["study_id"],
        "frozen_contract_sha256": sha256_path(work_dir / "frozen-run-contract.json"),
        "package_commit": frozen["package_commit"],
        "mapping_sets_sha256": frozen["mapping_sets_sha256"],
        "question_ids_sha256": __import__("hashlib").sha256(canonical_json(frozen["question_ids"])).hexdigest(),
        "development_analysis_manifest_sha256": sha256_path(manifest),
        "development_analysis_summary_sha256": sha256_path(summary),
        "development_analysis_dir": str(development_analysis),
    })


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--work-dir", required=True, type=Path)
    parser.add_argument("--development-analysis-dir", required=True, type=Path)
    args = parser.parse_args()
    create_gate(args.work_dir.resolve(), args.development_analysis_dir.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
