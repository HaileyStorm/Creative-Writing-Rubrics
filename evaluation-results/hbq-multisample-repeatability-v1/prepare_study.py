#!/usr/bin/env python3
"""Create the one-time, external-only frozen multi-sample study contract."""
from __future__ import annotations

import argparse
from pathlib import Path

from study import freeze

parser = argparse.ArgumentParser()
parser.add_argument("--data-dir", required=True, type=Path)
parser.add_argument("--work-dir", required=True, type=Path)
parser.add_argument("--fetch", action="store_true", help="Fetch only the contract-pinned HANNA CSV and license.")
args = parser.parse_args()
frozen = freeze(args.data_dir.resolve(), args.work_dir.resolve(), fetch=args.fetch)
print({"samples": len(frozen["samples"]), "scheduled_runs": len(frozen["schedule"]), "schedule_sha256": frozen["schedule_sha256"]})
