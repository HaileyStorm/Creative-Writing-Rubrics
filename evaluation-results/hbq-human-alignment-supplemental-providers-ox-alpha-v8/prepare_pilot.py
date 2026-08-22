#!/usr/bin/env python3
"""Freeze the Fresh88- and v7-bound Ox Alpha v8 pilot without provider contact."""
from __future__ import annotations

import argparse
from pathlib import Path

from study import freeze_work

parser = argparse.ArgumentParser()
parser.add_argument("--fresh88-work-dir", required=True, type=Path)
parser.add_argument("--fresh88-authority-dir", required=True, type=Path)
parser.add_argument("--repair1-artifacts-dir", required=True, type=Path)
parser.add_argument("--zero-cost-proof", required=True, type=Path)
parser.add_argument("--v7-work-dir", required=True, type=Path)
parser.add_argument("--work-dir", required=True, type=Path)

if __name__ == "__main__":
    args = parser.parse_args()
    freeze_work(args.fresh88_work_dir.resolve(), args.fresh88_authority_dir.resolve(), args.repair1_artifacts_dir.resolve(), args.zero_cost_proof.resolve(), args.v7_work_dir.resolve(), args.work_dir.resolve())
