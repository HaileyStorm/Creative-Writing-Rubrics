#!/usr/bin/env python3
"""Fetch only direct HANNA files, then freeze a v3 external work directory."""
from __future__ import annotations

import argparse
from pathlib import Path

from study import freeze_external_work


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", required=True, type=Path)
    parser.add_argument("--work-dir", required=True, type=Path)
    parser.add_argument("--fetch", action="store_true", help="fetch only contract-listed CSV and MIT license")
    args = parser.parse_args()
    frozen = freeze_external_work(args.data_dir.resolve(), args.work_dir.resolve(), fetch=args.fetch)
    print({"development": len(frozen["partitions"]["development"]), "confirmatory": len(frozen["partitions"]["confirmatory"]), "repeatability": len(frozen["repeatability"]["items"])})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
