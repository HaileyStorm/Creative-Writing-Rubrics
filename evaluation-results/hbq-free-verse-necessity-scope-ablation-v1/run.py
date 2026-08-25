"""Provider-free command surface for the paired scope/evidence ablation."""
from __future__ import annotations

import argparse
import hashlib
import json

from study import render_all_provider_inputs, verify_package


def main() -> None:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--verify", action="store_true")
    mode.add_argument("--render-plan", action="store_true")
    args = parser.parse_args()
    report = verify_package()
    if args.verify:
        print(json.dumps({"mode": "verify", "verification": report}, sort_keys=True))
        return
    inputs = render_all_provider_inputs()
    print(json.dumps({"mode": "render_plan", "verification": report, "rendered_slots": sorted(inputs), "prompt_sha256s": {slot_id: hashlib.sha256(item["prompt"].encode("utf-8")).hexdigest() for slot_id, item in inputs.items()}}, sort_keys=True))


if __name__ == "__main__":
    main()
