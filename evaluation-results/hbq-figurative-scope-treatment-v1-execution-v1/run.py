"""Explicit execution entry point; preparation and dry-runs never contact a provider."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from study import dry_run, execute


def main() -> None:
    parser = argparse.ArgumentParser()
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--dry-run", action="store_true")
    modes.add_argument("--execute", action="store_true")
    modes.add_argument("--resume", action="store_true")
    parser.add_argument("--private-root", required=True, type=Path)
    parser.add_argument("--allow-remote", action="store_true")
    parser.add_argument("--acknowledge-zero-incremental-charge", action="store_true")
    args = parser.parse_args()
    if args.dry_run:
        if args.allow_remote:
            parser.error("--dry-run has no remote action")
        result = dry_run(args.private_root)
    else:
        if not args.allow_remote:
            parser.error("--execute and --resume require --allow-remote after reviewing the disclosure")
        if not args.acknowledge_zero_incremental_charge:
            parser.error("--execute and --resume require --acknowledge-zero-incremental-charge")
        result = execute(args.private_root, resume=args.resume, acknowledged_zero_incremental_charge=True)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
