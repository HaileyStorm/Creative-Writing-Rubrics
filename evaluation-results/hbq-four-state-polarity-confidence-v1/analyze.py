"""Write the provenance-bound offline diagnostic."""
from __future__ import annotations

import argparse
from pathlib import Path

from study import write_output


def main() -> int:
    parser = argparse.ArgumentParser(description="Write the offline aggregate-only polarity/confidence diagnostic.")
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    write_output(args.output_dir.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
