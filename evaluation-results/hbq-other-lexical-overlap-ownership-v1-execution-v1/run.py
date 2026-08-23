"""Explicit command boundary for L2 singleton execution."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from study import dry_run, execute, render_plan


def main() -> None:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--render-plan", action="store_true")
    mode.add_argument("--execute", action="store_true")
    mode.add_argument("--resume", action="store_true")
    parser.add_argument("--private-root", required=True, type=Path)
    parser.add_argument("--allow-remote", action="store_true")
    parser.add_argument("--acknowledge-zero-incremental-charge", action="store_true")
    args = parser.parse_args()
    if args.dry_run or args.render_plan:
        if args.allow_remote or args.acknowledge_zero_incremental_charge:
            parser.error("--dry-run has no remote or billing acknowledgement")
        result = dry_run(args.private_root) if args.dry_run else render_plan(args.private_root)
    else:
        if not args.allow_remote or not args.acknowledge_zero_incremental_charge:
            parser.error("--execute/--resume require --allow-remote and --acknowledge-zero-incremental-charge")
        result = execute(args.private_root, resume=args.resume, allow_remote=True, acknowledged_zero_incremental_charge=True)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
