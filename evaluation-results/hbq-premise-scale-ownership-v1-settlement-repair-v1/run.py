"""Provider-free command boundary for the settlement-repair successor."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from study import settle, validate_package


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("verify", "settle"))
    parser.add_argument("--private-root", type=Path)
    args = parser.parse_args()
    if args.command == "verify":
        if args.private_root is not None:
            parser.error("verify accepts no private root")
        result = validate_package()
    else:
        if args.private_root is None:
            parser.error("settle requires --private-root")
        result = settle(args.private_root)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
