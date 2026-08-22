"""Verify an aggregate-only confidence diagnostics output without provider contact."""
from __future__ import annotations

import argparse
from pathlib import Path

from study import verify_output


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    verify_output(args.output_dir.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
