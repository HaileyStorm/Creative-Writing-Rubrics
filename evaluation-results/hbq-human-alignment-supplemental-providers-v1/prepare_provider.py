#!/usr/bin/env python3
"""Create the one-way supplemental work freeze from an existing GPT v3 freeze."""
from __future__ import annotations

import argparse
from pathlib import Path

from study import freeze_provider_work


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gpt-work-dir", type=Path, required=True)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--work-dir", type=Path, required=True)
    args = parser.parse_args()
    freeze_provider_work(args.gpt_work_dir.resolve(), args.data_dir.resolve(), args.work_dir.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
