from __future__ import annotations

import argparse
import json
from pathlib import Path

from study import dry_freeze, validate_package

parser = argparse.ArgumentParser()
mode = parser.add_mutually_exclusive_group(required=True)
mode.add_argument("--validate", action="store_true")
mode.add_argument("--dry-run", action="store_true")
parser.add_argument("--private-root", type=Path)
args = parser.parse_args()
if args.validate:
    result = validate_package()
else:
    if args.private_root is None:
        parser.error("--dry-run requires --private-root")
    result = dry_freeze(args.private_root)
print(json.dumps(result, ensure_ascii=False, sort_keys=True))
