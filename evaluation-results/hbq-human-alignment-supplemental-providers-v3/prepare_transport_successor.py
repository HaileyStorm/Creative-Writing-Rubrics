#!/usr/bin/env python3
from __future__ import annotations
import argparse
from pathlib import Path
from study import freeze_work

parser = argparse.ArgumentParser()
parser.add_argument("--failed-v2-work-dir", type=Path, required=True)
parser.add_argument("--work-dir", type=Path, required=True)
if __name__ == "__main__":
    args = parser.parse_args()
    freeze_work(args.failed_v2_work_dir.resolve(), args.work_dir.resolve())
