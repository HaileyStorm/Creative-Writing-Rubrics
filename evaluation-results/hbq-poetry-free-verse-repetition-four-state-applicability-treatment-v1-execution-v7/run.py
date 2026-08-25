from __future__ import annotations
import argparse,json
from pathlib import Path
from study import dry_run,execute
p=argparse.ArgumentParser();m=p.add_mutually_exclusive_group(required=True);m.add_argument("--dry-run",action="store_true");m.add_argument("--execute",action="store_true");p.add_argument("--private-root",required=True,type=Path);p.add_argument("--allow-remote",action="store_true");p.add_argument("--acknowledge-zero-incremental-charge",action="store_true");a=p.parse_args()
if a.dry_run:
    if a.allow_remote or a.acknowledge_zero_incremental_charge:p.error("dry run accepts no remote acknowledgement")
    x=dry_run(a.private_root)
else:
    if not a.allow_remote or not a.acknowledge_zero_incremental_charge:p.error("execute requires explicit authority")
    x=execute(a.private_root,allow_remote=True,acknowledged_zero_incremental_charge=True)
print(json.dumps(x,sort_keys=True))
