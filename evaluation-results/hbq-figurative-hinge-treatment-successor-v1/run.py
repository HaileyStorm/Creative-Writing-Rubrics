from __future__ import annotations
import argparse
import json
from pathlib import Path
import study

parser = argparse.ArgumentParser()
parser.add_argument("--private-root", required=True, type=Path)
parser.add_argument("--dry-run", action="store_true", required=True)
args = parser.parse_args()
print(json.dumps(study.dry_run(args.private_root), sort_keys=True))
