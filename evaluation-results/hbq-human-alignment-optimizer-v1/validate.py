#!/usr/bin/env python3
"""Validate source-bound, provider-free HANNA schedules."""
from __future__ import annotations

import argparse
from pathlib import Path

from study import execution_disclosure, read_json, require_disjoint_paths, validate_execution_manifest, validate_split_manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--split-manifest", required=True, type=Path)
    parser.add_argument("--disclosure", required=True, type=Path)
    parser.add_argument("--execution-manifest", required=True, type=Path)
    parser.add_argument("--development-manifest", type=Path)
    parser.add_argument("--frozen-successor-contract", required=True, type=Path)
    parser.add_argument("--hanna-csv", required=True, type=Path)
    args = parser.parse_args()
    require_disjoint_paths(args.split_manifest, args.disclosure, args.execution_manifest, *([args.development_manifest] if args.development_manifest else []))
    roots = {"frozen_successor_path": args.frozen_successor_contract, "hanna_csv_path": args.hanna_csv}
    validate_split_manifest(read_json(args.split_manifest), **roots)
    manifest = read_json(args.execution_manifest)
    development_manifest = read_json(args.development_manifest) if args.development_manifest else None
    validate_execution_manifest(manifest, **roots, development_manifest=development_manifest)
    if read_json(args.disclosure) != execution_disclosure(manifest, **roots, development_manifest=development_manifest):
        raise ValueError("Optimizer disclosure does not bind the prepared schedule")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
