#!/usr/bin/env python3
import argparse
from pathlib import Path
from study import freeze_work
parser = argparse.ArgumentParser(); parser.add_argument("--v8-work-dir", required=True, type=Path); parser.add_argument("--zero-cost-proof", required=True, type=Path); parser.add_argument("--work-dir", required=True, type=Path)
if __name__ == "__main__":
    args = parser.parse_args(); freeze_work(args.v8_work_dir.resolve(), args.zero_cost_proof.resolve(), args.work_dir.resolve())
