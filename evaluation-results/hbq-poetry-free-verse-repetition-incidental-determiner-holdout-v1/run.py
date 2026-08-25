from __future__ import annotations

import argparse
import json
from pathlib import Path

from study import dry_freeze, validate_package

parser = argparse.ArgumentParser()
parser.add_argument("--validate", action="store_true")
parser.add_argument("--dry-run", action="store_true")
parser.add_argument("--private-root", type=Path)
args = parser.parse_args()
if args.validate == args.dry_run:
    parser.error("choose exactly one of --validate or --dry-run")
if args.dry_run:
    if args.private_root is None:
        parser.error("--dry-run requires --private-root")
    result = dry_freeze(args.private_root)
else:
    result = validate_package()
print(json.dumps(result, ensure_ascii=False, sort_keys=True))
