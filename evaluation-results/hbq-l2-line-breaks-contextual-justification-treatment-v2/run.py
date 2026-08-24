from __future__ import annotations

import argparse
import json

from study import dry_run_report, pair_prompt_hashes, verify_package


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--render-plan", action="store_true")
    args = parser.parse_args()
    if args.dry_run == args.render_plan:
        parser.error("choose exactly one provider-free mode")
    result = dry_run_report() if args.dry_run else {"mode": "render_plan", "verification": verify_package(), "prompt_sha256s": pair_prompt_hashes()}
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
