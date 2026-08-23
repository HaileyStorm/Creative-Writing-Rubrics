"""Provider-free entry point for the settled v2 archive."""
from __future__ import annotations

import argparse
import json

from study import verify_package


def main() -> None:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    report = verify_package()
    if args.execute:
        parser.error("v2 is settled INCOMPLETE; execution is permanently refused")
    print(json.dumps({"mode": "dry_run", "verification": report}, sort_keys=True))


if __name__ == "__main__":
    main()
