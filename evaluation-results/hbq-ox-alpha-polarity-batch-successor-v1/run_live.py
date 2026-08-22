#!/usr/bin/env python3
"""Explicit command boundary for the private Ox polarity execution work root."""
from __future__ import annotations

import argparse
from pathlib import Path

from live import execute, prepare_work, progress, settle


parser = argparse.ArgumentParser()
parser.add_argument("--work-dir", required=True, type=Path)
parser.add_argument("--v9-work-dir", type=Path)
parser.add_argument("--zero-cost-proof", type=Path)
parser.add_argument("--prepare", action="store_true")
parser.add_argument("--settle", action="store_true")
parser.add_argument("--progress", action="store_true")
parser.add_argument("--timeout", type=float, default=600.0)
args = parser.parse_args()

if args.prepare:
    if args.v9_work_dir is None or args.zero_cost_proof is None:
        parser.error("--prepare requires --v9-work-dir and --zero-cost-proof")
    prepare_work(args.v9_work_dir, args.zero_cost_proof, args.work_dir)
elif args.settle:
    settle(args.work_dir)
elif args.progress:
    print(progress(args.work_dir))
else:
    execute(args.work_dir, timeout=args.timeout)
