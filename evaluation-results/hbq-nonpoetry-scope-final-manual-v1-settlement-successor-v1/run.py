from __future__ import annotations
import argparse, json
from pathlib import Path
from study import settle
p = argparse.ArgumentParser(); p.add_argument("--private-root", type=Path, required=True)
args = p.parse_args(); print(json.dumps(settle(args.private_root), sort_keys=True))
