from __future__ import annotations

import argparse
import json

import study


def main() -> int:
    parser = argparse.ArgumentParser(description="Provider-free DSPy architecture freeze verifier")
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--plan-transfer", action="store_true")
    args = parser.parse_args()
    if sum((args.verify, args.dry_run, args.plan_transfer)) != 1:
        parser.error("choose exactly one provider-free mode")
    if args.plan_transfer:
        value = study.production_transfer_plan()
    else:
        value = study.verify_package()
        if args.dry_run:
            value = {"mode": "dry_run", "verification": value}
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
