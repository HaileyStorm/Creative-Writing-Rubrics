"""Provider-free CLI for the S1 fresh-carrier execution successor."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from study import dry_freeze, set_work_root, validate_package


def main() -> None:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--validate", action="store_true")
    mode.add_argument("--dry-run", action="store_true")
    parser.add_argument("--work-root", type=Path)
    args = parser.parse_args()
    if args.validate:
        result = validate_package()
    else:
        if args.work_root is None:
            raise ValueError("--dry-run requires an explicit external --work-root")
        set_work_root(args.work_root)
        result = dry_freeze()
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
