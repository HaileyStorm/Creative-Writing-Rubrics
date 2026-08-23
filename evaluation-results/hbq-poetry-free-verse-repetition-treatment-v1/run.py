"""Provider-free command surface for the S1 free-verse repetition treatment."""
from __future__ import annotations

import argparse
import hashlib
import json

from study import canonical_json, opaque_schedule, validate_package


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", required=True)
    args = parser.parse_args()
    if args.dry_run:
        schedule = opaque_schedule()
        print(json.dumps({"mode": "dry_run", "provider_calls": 0, "verification": validate_package(), "opaque_slot_ids": [row["opaque_slot_id"] for row in schedule], "opaque_schedule_sha256": hashlib.sha256(canonical_json(schedule)).hexdigest()}, sort_keys=True))


if __name__ == "__main__":
    main()
