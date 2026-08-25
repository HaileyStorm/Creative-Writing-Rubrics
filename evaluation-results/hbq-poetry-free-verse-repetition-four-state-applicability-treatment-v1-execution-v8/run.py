from pathlib import Path
import argparse,json
from study import dry_run
p=argparse.ArgumentParser();p.add_argument('--dry-run',action='store_true',required=True);p.add_argument('--private-root',required=True,type=Path);a=p.parse_args();print(json.dumps(dry_run(a.private_root),sort_keys=True))
