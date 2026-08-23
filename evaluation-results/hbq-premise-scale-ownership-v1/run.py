"""Provider-free command surface for the frozen premise-scale ownership screen."""
from __future__ import annotations

import argparse
import hashlib
import json

from study import render_all_provider_prompts, verify_package


def main() -> None:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--render-plan", action="store_true")
    args = parser.parse_args()
    report = verify_package()
    if args.dry_run:
        print(json.dumps({"mode": "dry_run", "verification": report}, sort_keys=True))
    else:
        prompts = render_all_provider_prompts()
        print(json.dumps({"mode": "render_plan", "verification": report, "rendered_slots": sorted(prompts), "prompt_sha256s": {slot_id: hashlib.sha256(prompt.encode("utf-8")).hexdigest() for slot_id, prompt in prompts.items()}}, sort_keys=True))


if __name__ == "__main__":
    main()
