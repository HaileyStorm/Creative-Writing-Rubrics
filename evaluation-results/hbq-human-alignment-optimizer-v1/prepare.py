#!/usr/bin/env python3
"""Prepare only source-bound schedules and local-first disclosures."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from study import atomic_output_directory, checked_output_path, derive_split_manifest, execution_disclosure, preflight_disclosure, read_json, require_disjoint_paths, validate_execution_manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--frozen-successor-contract", required=True, type=Path)
    parser.add_argument("--hanna-csv", required=True, type=Path)
    parser.add_argument("--execution-manifest", type=Path)
    parser.add_argument("--development-manifest", type=Path)
    args = parser.parse_args()
    output = checked_output_path(args.output_dir)
    roots = {"frozen_successor_path": args.frozen_successor_contract, "hanna_csv_path": args.hanna_csv}
    development_manifest = read_json(args.development_manifest) if args.development_manifest else None
    if args.execution_manifest:
        require_disjoint_paths(output, args.execution_manifest, *([args.development_manifest] if args.development_manifest else []))
        manifest = read_json(args.execution_manifest)
        validate_execution_manifest(manifest, **roots, development_manifest=development_manifest)
        disclosure = execution_disclosure(manifest, **roots, development_manifest=development_manifest)
    else:
        if args.development_manifest:
            raise ValueError("Development manifest is only meaningful with an execution manifest")
        disclosure = preflight_disclosure()
    split_manifest = derive_split_manifest(**roots)
    atomic_output_directory(output, {"split-manifest.json": json.dumps(split_manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n", "preflight-disclosure.json": json.dumps(disclosure, ensure_ascii=False, sort_keys=True, indent=2) + "\n"})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
