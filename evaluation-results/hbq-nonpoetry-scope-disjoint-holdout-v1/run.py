from __future__ import annotations

import argparse
import json

from study import validate_public_package


def main() -> int:
    parser = argparse.ArgumentParser(description="Provider-free S2 disjoint holdout freeze")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if not args.dry_run:
        parser.error("only --dry-run is supported; this freeze cannot contact a provider")
    print(json.dumps(validate_public_package(), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
