#!/usr/bin/env python3
"""Freeze one fresh Ox Alpha v7 transport root from the immutable v6 predecessor."""
from __future__ import annotations

import argparse
from pathlib import Path

from study import freeze_work


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--uncertain-v6-work-dir", required=True, type=Path)
    parser.add_argument("--zero-cost-proof", required=True, type=Path)
    parser.add_argument("--work-dir", required=True, type=Path)
    arguments = parser.parse_args()
    freeze_work(arguments.uncertain_v6_work_dir.resolve(), arguments.zero_cost_proof.resolve(), arguments.work_dir.resolve())
