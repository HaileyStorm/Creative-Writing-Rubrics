#!/usr/bin/env python3
"""Create the immutable, outcome-blind Ox Alpha work freeze."""
from __future__ import annotations

import argparse
from pathlib import Path

from study import freeze_work


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--primary-work-dir", required=True, type=Path)
    parser.add_argument("--gpt-output-dir", required=True, type=Path)
    parser.add_argument("--zero-cost-proof", required=True, type=Path)
    parser.add_argument("--work-dir", required=True, type=Path)
    args = parser.parse_args()
    freeze_work(args.primary_work_dir.resolve(), args.gpt_output_dir.resolve(), args.zero_cost_proof.resolve(), args.work_dir.resolve())
