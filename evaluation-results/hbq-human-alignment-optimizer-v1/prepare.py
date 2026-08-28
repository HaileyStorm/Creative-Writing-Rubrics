#!/usr/bin/env python3
"""Prepare only source-bound schedules and local-first disclosures."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from execution_freeze import derive_execution_freeze, execution_disclosure
from study import atomic_output_directory, checked_output_path, derive_split_manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--frozen-successor-contract", required=True, type=Path)
    parser.add_argument("--hanna-csv", required=True, type=Path)
    args = parser.parse_args()
    output = checked_output_path(args.output_dir)
    roots = {"frozen_successor_path": args.frozen_successor_contract, "hanna_csv_path": args.hanna_csv}
    freeze = derive_execution_freeze(**roots)
    disclosure = execution_disclosure(freeze, **roots)
    files = {
        "split-manifest.json": json.dumps(derive_split_manifest(**roots), ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        "execution-freeze.json": json.dumps(freeze, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        "preflight-disclosure.json": json.dumps(disclosure, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
    }
    atomic_output_directory(output, files)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
