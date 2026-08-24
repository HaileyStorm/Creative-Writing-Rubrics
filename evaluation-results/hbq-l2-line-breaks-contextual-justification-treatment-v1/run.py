"""Command surface for the provider-free L2 wording-treatment freeze."""
from __future__ import annotations

import argparse
import hashlib
import json

from study import dry_run_report, render_pairs, verify_package


def main() -> None:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--render-plan", action="store_true")
    args = parser.parse_args()
    if args.dry_run:
        print(json.dumps(dry_run_report(), sort_keys=True))
        return
    verification = verify_package()
    pairs = render_pairs()
    print(json.dumps({"mode": "render_plan", "verification": verification, "prompt_sha256s": {case_id: {variant: hashlib.sha256(prompt.encode("utf-8")).hexdigest() for variant, prompt in pair.items()} for case_id, pair in pairs.items()}}, sort_keys=True))


if __name__ == "__main__":
    main()
