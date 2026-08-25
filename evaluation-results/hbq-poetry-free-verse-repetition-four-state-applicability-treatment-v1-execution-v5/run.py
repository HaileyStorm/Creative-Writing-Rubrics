from __future__ import annotations
import argparse
import json
from pathlib import Path
from study import dry_run, execute
parser = argparse.ArgumentParser(); mode = parser.add_mutually_exclusive_group(required=True)
mode.add_argument("--dry-run", action="store_true"); mode.add_argument("--execute", action="store_true")
parser.add_argument("--private-root", required=True, type=Path); parser.add_argument("--allow-remote", action="store_true"); parser.add_argument("--acknowledge-zero-incremental-charge", action="store_true")
args = parser.parse_args()
if args.dry_run:
    if args.allow_remote or args.acknowledge_zero_incremental_charge: parser.error("dry run accepts no remote acknowledgement")
    value = dry_run(args.private_root)
else:
    if not args.allow_remote or not args.acknowledge_zero_incremental_charge: parser.error("execute requires explicit authority")
    value = execute(args.private_root, allow_remote=True, acknowledged_zero_incremental_charge=True)
print(json.dumps(value, sort_keys=True))
