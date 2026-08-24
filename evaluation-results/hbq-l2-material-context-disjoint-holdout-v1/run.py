"""Provider-free command surface for the fresh disjoint holdout."""
import argparse
import json

from study import dry_run_report, plan_slots, render_all_provider_inputs

parser = argparse.ArgumentParser()
parser.add_argument("--dry-run", action="store_true")
parser.add_argument("--render-plan", action="store_true")
args = parser.parse_args()
if args.dry_run == args.render_plan:
    parser.error("choose exactly one provider-free operation")
if args.dry_run:
    print(json.dumps(dry_run_report(), sort_keys=True))
else:
    print(json.dumps({"mode": "render_plan", "slots": plan_slots(), "rendered_slots": sorted(render_all_provider_inputs())}, sort_keys=True))
