#!/usr/bin/env python3
"""Validate source-bound, provider-free HANNA schedules."""
from __future__ import annotations

import argparse
from pathlib import Path

from execution_freeze import execution_disclosure, validate_execution_freeze
from study import read_json, require_disjoint_paths, validate_split_manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--split-manifest", required=True, type=Path)
    parser.add_argument("--disclosure", required=True, type=Path)
    parser.add_argument("--execution-freeze", required=True, type=Path)
    parser.add_argument("--frozen-successor-contract", required=True, type=Path)
    parser.add_argument("--hanna-csv", required=True, type=Path)
    args = parser.parse_args()
    require_disjoint_paths(args.split_manifest, args.disclosure, args.execution_freeze)
    roots = {"frozen_successor_path": args.frozen_successor_contract, "hanna_csv_path": args.hanna_csv}
    validate_split_manifest(read_json(args.split_manifest), **roots)
    manifest = read_json(args.execution_freeze)
    validate_execution_freeze(manifest, **roots)
    if read_json(args.disclosure) != execution_disclosure(manifest, **roots):
        raise ValueError("Optimizer disclosure does not bind the prepared schedule")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
