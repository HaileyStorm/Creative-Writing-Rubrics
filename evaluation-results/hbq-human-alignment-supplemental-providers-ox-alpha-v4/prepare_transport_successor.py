#!/usr/bin/env python3
"""Freeze one fresh Ox Alpha v4 transport root."""
from __future__ import annotations

import argparse
from pathlib import Path

from study import freeze_work


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--failed-v3-work-dir", required=True, type=Path)
    parser.add_argument("--zero-cost-proof", required=True, type=Path)
    parser.add_argument("--work-dir", required=True, type=Path)
    arguments = parser.parse_args()
    freeze_work(arguments.failed_v3_work_dir.resolve(), arguments.zero_cost_proof.resolve(), arguments.work_dir.resolve())
