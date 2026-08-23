"""Provider-free command surface for the frozen L2 construct microgate."""
from __future__ import annotations

import argparse
import hashlib
import json

from study import dry_run_report, public_attachment_record, render_all_provider_inputs, verify_package


def main() -> None:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--render-plan", action="store_true")
    args = parser.parse_args()
    if args.dry_run:
        print(json.dumps(dry_run_report(), sort_keys=True))
        return
    verification = verify_package()
    inputs = render_all_provider_inputs()
    print(json.dumps({"mode": "render_plan", "verification": verification, "rendered_slots": sorted(inputs), "prompt_sha256s": {slot_id: hashlib.sha256(item["prompt"].encode("utf-8")).hexdigest() for slot_id, item in inputs.items()}, "image_input_slots": {slot_id: [public_attachment_record(value) for value in item["image_inputs"]] for slot_id, item in inputs.items() if item["image_inputs"]}}, sort_keys=True))


if __name__ == "__main__":
    main()
