from __future__ import annotations

import argparse
import json

import study


def main() -> int:
    parser = argparse.ArgumentParser(description="Provider-free whole-poem architecture v2 treatment verifier")
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--plan", action="store_true")
    args = parser.parse_args()
    if args.verify == args.plan:
        parser.error("choose exactly one provider-free mode")
    value = study.verify_package() if args.verify else study.plan_slots()
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
