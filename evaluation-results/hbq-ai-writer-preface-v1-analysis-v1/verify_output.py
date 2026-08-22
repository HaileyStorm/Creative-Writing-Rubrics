"""Verify a public aggregate-only preface-analysis output."""
from __future__ import annotations

import argparse
from pathlib import Path

from analyze import verify_output


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True, type=Path)
    verify_output(parser.parse_args().output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
