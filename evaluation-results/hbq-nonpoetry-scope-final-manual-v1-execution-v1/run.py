"""Explicit remote-execution boundary for the final S2 manual successor."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from study import dry_run, execute, set_private_root, settle


def main() -> None:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--execute", action="store_true")
    mode.add_argument("--resume", action="store_true")
    mode.add_argument("--settle", action="store_true")
    parser.add_argument("--allow-remote", action="store_true")
    parser.add_argument("--acknowledge-zero-incremental-charge", action="store_true")
    parser.add_argument("--private-root", type=Path, required=True)
    args = parser.parse_args()
    set_private_root(args.private_root)
    if args.dry_run or args.settle:
        if args.allow_remote or args.acknowledge_zero_incremental_charge:
            parser.error("--dry-run/--settle have no remote or billing acknowledgement")
        result = dry_run() if args.dry_run else settle()
    else:
        if not args.allow_remote or not args.acknowledge_zero_incremental_charge:
            parser.error("--execute/--resume require --allow-remote and --acknowledge-zero-incremental-charge")
        result = execute(
            resume=args.resume,
            allow_remote=args.allow_remote,
            acknowledged_zero_incremental_charge=args.acknowledge_zero_incremental_charge,
        )
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
