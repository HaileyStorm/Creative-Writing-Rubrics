"""Fail-closed execution boundary: this frozen package never makes provider calls."""
from __future__ import annotations

import argparse
import json

from study import verify_package


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if not args.dry_run:
        parser.error("Provider execution is not authorized by this frozen package; use --dry-run only.")
    print(json.dumps({"mode": "dry_run", "provider_calls": 0, "result_artifacts_written": 0, "verification": verify_package()}, sort_keys=True))


if __name__ == "__main__":
    main()
