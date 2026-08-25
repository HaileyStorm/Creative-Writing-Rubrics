"""Command surface for the frozen six-call S2 semantic-boundary successor."""
from __future__ import annotations

import argparse
import json

from study import dry_run, execute, set_private_root, settle, validate_package


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--private-root", required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--validate", action="store_true")
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--execute", action="store_true")
    mode.add_argument("--settle", action="store_true")
    parser.add_argument("--allow-remote", action="store_true")
    parser.add_argument("--acknowledge-zero-incremental-charge", action="store_true")
    args = parser.parse_args()
    set_private_root(args.private_root)
    if args.validate:
        result = validate_package()
    elif args.dry_run:
        result = dry_run()
    elif args.execute:
        result = execute(allow_remote=args.allow_remote, acknowledged_zero_incremental_charge=args.acknowledge_zero_incremental_charge)
    else:
        result = settle()
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
