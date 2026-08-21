#!/usr/bin/env python3
"""Create the immutable development-to-confirmatory HANNA v3 gate."""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

from analyze_study import verify_development_analysis
from study import canonical_json, sha256_path, validate_frozen_contract, write_json


def create_gate(work_dir: Path, development_analysis: Path) -> None:
    frozen = validate_frozen_contract(work_dir)
    verify_development_analysis(work_dir, frozen, development_analysis)
    manifest, summary = development_analysis / "manifest.json", development_analysis / "summary.json"
    if not manifest.is_file() or not summary.is_file():
        raise ValueError("Development analysis manifest and summary are required")
    gate = work_dir / "confirmation-gate.json"
    if gate.exists():
        raise ValueError("Refusing to overwrite immutable confirmation gate")
    write_json(gate, {
        "format_version": 2,
        "study_id": frozen["study_id"],
        "frozen_contract_sha256": sha256_path(work_dir / "frozen-run-contract.json"),
        "study_contract_sha256": frozen["study_contract_sha256"],
        "package_commit": frozen["package_commit"],
        "runtime_sha256": frozen["runtime_sha256"],
        "mapping_sets_sha256": frozen["mapping_sets_sha256"],
        "question_ids_sha256": hashlib.sha256(canonical_json(frozen["question_ids"])).hexdigest(),
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
