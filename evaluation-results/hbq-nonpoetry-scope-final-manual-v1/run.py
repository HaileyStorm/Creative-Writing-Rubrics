"""Provider-free command surface for the frozen final S2 manual successor."""
from __future__ import annotations

import argparse
import hashlib
import json

from study import build_plan, canonical_json, validate_package


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", required=True)
    args = parser.parse_args()
    if args.dry_run:
        plan = build_plan()
        print(json.dumps({"mode": "dry_run", "provider_calls": 0, "verification": validate_package(), "opaque_slot_ids": [row["slot_id"] for row in plan], "plan_sha256": hashlib.sha256(canonical_json(plan)).hexdigest()}, sort_keys=True))


if __name__ == "__main__":
    main()
