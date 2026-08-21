#!/usr/bin/env python3
"""Create the immutable v2 work freeze from a valid v1 supplemental work directory."""
from __future__ import annotations

import argparse
from pathlib import Path

from study import freeze_work


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--parent-work-dir", type=Path, required=True)
    parser.add_argument("--work-dir", type=Path, required=True)
    args = parser.parse_args()
    freeze_work(args.parent_work_dir.resolve(), args.work_dir.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
