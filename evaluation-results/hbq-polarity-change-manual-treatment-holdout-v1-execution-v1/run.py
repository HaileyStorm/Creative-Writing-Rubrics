"""CLI boundary for the sealed P1 A/B holdout executor."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from study import dry_run, execute

parser = argparse.ArgumentParser(); mode = parser.add_mutually_exclusive_group(required=True)
mode.add_argument("--dry-run", action="store_true"); mode.add_argument("--execute", action="store_true"); mode.add_argument("--resume", action="store_true")
parser.add_argument("--private-root", required=True, type=Path); parser.add_argument("--allow-remote", action="store_true"); parser.add_argument("--acknowledge-zero-incremental-charge", action="store_true")
args = parser.parse_args()
if args.dry_run:
    if args.allow_remote or args.acknowledge_zero_incremental_charge: parser.error("dry run is provider-free")
    result = dry_run(args.private_root)
else:
    if not args.allow_remote or not args.acknowledge_zero_incremental_charge: parser.error("execution requires explicit remote and billing acknowledgement")
    result = execute(args.private_root, resume=args.resume, allow_remote=True, acknowledged_zero_incremental_charge=True)
print(json.dumps(result, sort_keys=True))
