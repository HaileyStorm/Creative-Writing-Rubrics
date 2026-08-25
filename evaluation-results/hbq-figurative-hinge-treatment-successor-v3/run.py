from __future__ import annotations
import argparse,json
from pathlib import Path
import study
p=argparse.ArgumentParser();p.add_argument("--private-root",required=True,type=Path);m=p.add_mutually_exclusive_group(required=True);m.add_argument("--dry-run",action="store_true");m.add_argument("--execute",action="store_true");p.add_argument("--allow-remote",action="store_true");p.add_argument("--acknowledge-zero-incremental-charge",action="store_true");a=p.parse_args()
if a.execute: print(json.dumps(study.execute(a.private_root,allow_remote=a.allow_remote,acknowledged_zero_incremental_charge=a.acknowledge_zero_incremental_charge),sort_keys=True))
else: print(json.dumps(study.dry_run(a.private_root),sort_keys=True))
