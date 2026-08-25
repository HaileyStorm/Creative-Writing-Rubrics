"""Provider-free command boundary for the whole-poem execution successor."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import study


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--verify", action="store_true")
    mode.add_argument("--prepare", action="store_true")
    parser.add_argument("--private-root", type=Path)
    args = parser.parse_args()
    if args.verify:
        if args.private_root is not None:
            parser.error("--verify does not write a private root")
        result = study.validate_package()
    else:
        if args.private_root is None:
            parser.error("--prepare requires --private-root")
        result = study.prepare(args.private_root)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
