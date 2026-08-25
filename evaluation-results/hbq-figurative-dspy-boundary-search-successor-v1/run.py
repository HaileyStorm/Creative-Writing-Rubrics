from __future__ import annotations

import argparse
import json
from pathlib import Path

import study


def main() -> int:
    parser = argparse.ArgumentParser(description="Frozen figurative DSPy boundary-search successor")
    parser.add_argument("--private-root", required=True, type=Path)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--execute", action="store_true")
    parser.add_argument("--allow-remote", action="store_true")
    parser.add_argument("--acknowledge-zero-incremental-charge", action="store_true")
    args = parser.parse_args()
    if args.execute:
        if not (args.allow_remote and args.acknowledge_zero_incremental_charge):
            parser.error("--execute requires --allow-remote and --acknowledge-zero-incremental-charge")
        print(json.dumps(study.execute(args.private_root, allow_remote=True, acknowledged_zero_incremental_charge=True), sort_keys=True))
        return 0
    if args.allow_remote or args.acknowledge_zero_incremental_charge:
        parser.error("acknowledgements belong only to the sealed execution mode")
    print(json.dumps(study.dry_run(args.private_root), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
