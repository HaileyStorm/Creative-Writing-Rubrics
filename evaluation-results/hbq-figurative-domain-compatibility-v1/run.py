"""Fail-closed CLI for the frozen figurative domain-compatibility package."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from study import render_all_provider_prompts, verify_package, verify_public_package


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--render", action="store_true")
    parser.add_argument("--private-holdout-root", type=Path)
    args = parser.parse_args()
    if not (args.dry_run or args.render) or (args.dry_run and args.render):
        parser.error("Use exactly one provider-free mode: --dry-run or --render.")
    root = args.private_holdout_root or (Path(os.environ["HBQ_FIGURATIVE_DOMAIN_HOLDOUT_ROOT"]) if os.environ.get("HBQ_FIGURATIVE_DOMAIN_HOLDOUT_ROOT") else None)
    verification = verify_package(root) if root is not None else verify_public_package()
    if args.dry_run:
        print(json.dumps({"mode": "dry_run", "provider_calls": 0, "result_artifacts_written": 0, "verification": verification}, sort_keys=True))
    else:
        prompts = render_all_provider_prompts()
        print(json.dumps({"mode": "render", "provider_calls": 0, "prompt_count": len(prompts), "prompt_sha256": {slot: __import__("hashlib").sha256(prompt.encode("utf-8")).hexdigest() for slot, prompt in prompts.items()}}, sort_keys=True))


if __name__ == "__main__":
    main()
