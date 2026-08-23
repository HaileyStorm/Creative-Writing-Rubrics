"""Provider-free command boundary for the S1 settlement successor."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from study import settle, validate_package


def main() -> None:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("verify")
    settle_parser = commands.add_parser("settle")
    settle_parser.add_argument("--source-root", required=True, type=Path)
    settle_parser.add_argument("--settlement-root", required=True, type=Path)
    args = parser.parse_args()
    result = validate_package() if args.command == "verify" else settle(args.source_root, args.settlement_root)
    if args.command == "settle":
        result = {key: result[key] for key in ("study_id", "decision", "completed_execution_slots", "required_execution_slots", "promotion", "provider_calls")}
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
