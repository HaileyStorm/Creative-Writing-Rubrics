#!/usr/bin/env python3
"""Reject imported aggregates until local per-run recomputation exists."""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Mapping

from study import checked_output_path, read_json, require_disjoint_paths


NON_AUTHORITATIVE = "Imported optimizer aggregates are development-only and non-authoritative; recompute metrics from exact per-run evidence before publication"


def validate_aggregate(_value: Mapping[str, Any], **_ignored: Any) -> None:
    raise ValueError(NON_AUTHORITATIVE)


def analyze(input_path: Path, output: Path, *, split_manifest_path: Path, disclosure_path: Path, execution_freeze_path: Path) -> None:
    output = checked_output_path(output)
    require_disjoint_paths(output, input_path, split_manifest_path, disclosure_path, execution_freeze_path)
    for path in (input_path, split_manifest_path, disclosure_path, execution_freeze_path):
        read_json(path)
    raise ValueError(NON_AUTHORITATIVE)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--split-manifest", required=True, type=Path)
    parser.add_argument("--disclosure", required=True, type=Path)
    parser.add_argument("--execution-freeze", required=True, type=Path)
    args = parser.parse_args()
    analyze(args.input, args.output_dir, split_manifest_path=args.split_manifest, disclosure_path=args.disclosure, execution_freeze_path=args.execution_freeze)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
