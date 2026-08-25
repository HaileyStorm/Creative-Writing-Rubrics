"""Provider-free CLI for the S1 four-state disjoint holdout freeze."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from study import dry_run, set_work_root, validate_package


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--work-root", required=True, type=Path)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--validate", action="store_true")
    mode.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    set_work_root(args.work_root)
    result = validate_package() if args.validate else dry_run()
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
