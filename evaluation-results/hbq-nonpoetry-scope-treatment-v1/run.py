"""Provider-free command surface for the frozen S2 treatment plan."""
from __future__ import annotations

import argparse
import hashlib
import json

from study import render_plan, validate_package


def main() -> None:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--render-plan", action="store_true")
    args = parser.parse_args()
    report = validate_package()
    if args.dry_run:
        print(json.dumps({"mode": "dry_run", "provider_calls": 0, "verification": report}, sort_keys=True))
    else:
        prompts = render_plan()
        print(json.dumps({"mode": "render_plan", "provider_calls": 0, "rendered_slots": sorted(prompts), "prompt_sha256s": {key: hashlib.sha256(value.encode("utf-8")).hexdigest() for key, value in prompts.items()}}, sort_keys=True))


if __name__ == "__main__":
    main()
