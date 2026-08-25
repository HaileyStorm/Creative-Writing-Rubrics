"""Provider-free CLI for the S1 v2 execution preclaim successor."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from study import claim_only, derive_snapshot, set_roots, validate_package


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--frozen-root", required=True, type=Path)
    parser.add_argument("--work-root", required=True, type=Path)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--validate", action="store_true")
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--claim-only", action="store_true")
    args = parser.parse_args()
    set_roots(frozen_root=args.frozen_root, work_root=args.work_root)
    result = validate_package() if args.validate else derive_snapshot() if args.dry_run else claim_only()
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
