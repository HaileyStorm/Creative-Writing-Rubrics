"""Provider-free command boundary for the frozen execution successor."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from study import prepare, validate_package


def main() -> None:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--verify", action="store_true")
    mode.add_argument("--prepare", action="store_true")
    parser.add_argument("--private-root", type=Path)
    args = parser.parse_args()
    if args.verify:
        if args.private_root is not None:
            parser.error("--verify does not write a private root")
        result = validate_package()
    else:
        if args.private_root is None:
            parser.error("--prepare requires --private-root")
        result = prepare(args.private_root)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
