"""Provider-free CLI for the figurative-metaphor checklist successor freeze."""
from __future__ import annotations

import argparse
import hashlib
import json

from study import render_all_provider_prompts, verify_public_package


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--render", action="store_true")
    args = parser.parse_args()
    if args.dry_run == args.render:
        parser.error("Use exactly one provider-free mode: --dry-run or --render.")
    verification = verify_public_package()
    if args.dry_run:
        print(json.dumps({"mode": "dry_run", "provider_calls": 0, "result_artifacts_written": 0, "verification": verification}, sort_keys=True))
    else:
        prompts = render_all_provider_prompts()
        print(json.dumps({"mode": "render", "provider_calls": 0, "prompt_count": len(prompts), "prompt_sha256": {slot: hashlib.sha256(prompt.encode("utf-8")).hexdigest() for slot, prompt in prompts.items()}}, sort_keys=True))


if __name__ == "__main__":
    main()
