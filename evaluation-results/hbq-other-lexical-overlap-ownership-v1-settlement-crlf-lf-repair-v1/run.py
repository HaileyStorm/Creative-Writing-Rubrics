"""Settlement-only command boundary for the L2 CRLF/LF repair."""
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
    settle_parser.add_argument("--execution-root", required=True, type=Path)
    settle_parser.add_argument("--settlement-root", required=True, type=Path)
    args = parser.parse_args()
    result = validate_package() if args.command == "verify" else settle(args.execution_root, args.settlement_root)
    if args.command == "settle":
        result = {
            key: result[key]
            for key in ("study_id", "decision", "completed_execution_slots", "required_execution_slots", "three_repeat_cells", "visual_attachment_slots", "promotion", "provider_calls")
            if key in result
        }
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
