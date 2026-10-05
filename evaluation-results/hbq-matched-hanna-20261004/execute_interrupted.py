"""Named native executor for only the frozen HANNA interruption's untouched suffix."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import sys
import uuid

HERE = Path(__file__).resolve().parent
POLICY = 'matched_hanna_interrupted_suffix_native_executor_v1'
PREPARER_SHA = '38fd6971c4ec8707092a29b834fec0868ef19ce5635e7b90d0e079a1a14bdc89'


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec); sys.modules[name] = module
    spec.loader.exec_module(module); return module


p = load('hanna_suffix_preparer', HERE / 'continue_interrupted.py')
require = p.require


def context(plan_path, plan_sha, workers, route_root=None, route_sha=None):
    require(p.digest((HERE / 'continue_interrupted.py').read_bytes()) == PREPARER_SHA, 'Frozen preparer differs')
    plan = p.verify_plan(plan_path, plan_sha)
    root = Path(plan['program_root_local_only']) / 'hanna-reference/frozen-001'
    manifest_raw = (root / 'manifest.json').read_bytes(); manifest = json.loads(manifest_raw)
    rows = p.selected_rows(plan, manifest)
    c = load('hanna_suffix_private_collector', HERE / 'collector.py')
    tools = Path(manifest['external_pins']['tools_root_local_only'])
    sys.path.insert(0, str(tools)); sys.path.insert(0, str(p.REPO / 'src'))
    subset = c.p.load_module('hanna_suffix_subset', root / 'implementation/schema_subset.py')
    validator = c.p.load_module('hanna_suffix_validator', root / 'implementation/validate_response.py')
    receipts = c.p.load_module('hanna_suffix_receipts', root / 'implementation/codex_receipts.py')
    route = None
    if plan['endpoint'] == 'grok':
        require(route_root is not None and route_sha is not None, 'Explicit reviewed execution route required')
        route = next(v for v in json.loads((route_root / 'routes.json').read_bytes())['routes']
                     if v['name'] == plan['source_binding']['route']['name'])
    else: require(route_root is None and route_sha is None, 'Route applies only to Grok')
    # This is the expected binding for an authorized launch, not a headroom observation.
    binding = p.execution_binding(plan, plan_sha, workers, owner_global_headroom_verified=True, route=route, route_sha=route_sha)
    binding.update(execution_policy=POLICY, executor_sha256=p.digest(Path(__file__).read_bytes()),
                   execution_adapter_implemented=True, frozen_plan_execution_adapter_implemented=plan['execution_adapter_implemented'])
    return {'plan': plan, 'plan_path': plan_path.resolve(), 'plan_sha': plan_sha, 'manifest': manifest,
            'manifest_raw': manifest_raw, 'root': root, 'rows': rows, 'collector': c, 'tools': tools,
            'subset': subset, 'validator': validator, 'receipts': receipts, 'binding': binding, 'route_root': route_root}


def preflight(output, ctx):
    h = Path(ctx['plan']['program_root_local_only']) / 'hanna-reference'; output = output.resolve()
    protected = [p.REPO, ctx['root'], h / 'parallel-lifecycle', ctx['plan_path'].parent,
                 *(h / f'interrupted-{e}-plan-001' for e in p.THROUGH),
                 *(h / f'judging-{e}-parallel-001' for e in p.THROUGH),
                 *(h / f'sol-slot{n}-saved-reconciliation-001' for n in p.ADOPTIONS)]
    require(output.is_relative_to(h.resolve()) and all(not output.is_relative_to(path.resolve())
            and not path.resolve().is_relative_to(output) for path in protected), 'Suffix result root overlaps retained inputs')
    return output


def seeded_identities(plan):
    return {entry['native_identity'] for entry in plan['prefix'] if entry['endpoint'] == plan['endpoint']}


def inventory(ctx, output):
    c = ctx['collector']; binding = ctx['binding']; rows = ctx['rows']
    native_ids = seeded_identities(ctx['plan']); pending = []; states = []
    if output.exists():
        require(json.loads((output / 'job.json').read_bytes()) == binding
                and (output / 'frozen-manifest.json').read_bytes() == ctx['manifest_raw']
                and (output / 'frozen-plan.json').read_bytes() == ctx['plan_path'].read_bytes(), 'Existing named execution binding differs')
        require({path.name for path in output.iterdir() if path.is_dir()}
                <= {c.sample_path(output, row).name for row in rows}, 'Reserved prefix or foreign suffix directory; no resend')
        if ctx['plan']['endpoint'] == 'sol':
            require(json.loads((output / 'account-binding.json').read_bytes()) == c.t.account_receipt(binding), 'Own suffix account differs')
    for row in rows:
        sample = c.sample_path(output, row)
        if not sample.exists(): pending.append(row); continue
        terminal, _ = c.replay(sample, row, ctx['manifest'], binding, ctx['root'], ctx['receipts'], ctx['subset'], ctx['validator'])
        states.append(terminal['state'])
        identity = terminal.get('native_thread_id')
        if identity:
            require(identity not in native_ids, 'Suffix reused retained own native identity'); native_ids.add(identity)
    return pending, states, native_ids


def native_authority(execute_native, owner_headroom, states, settled):
    require(execute_native and owner_headroom, 'Explicit native execution and owner global headroom flags required')
    require(all(state in settled for state in states), 'Occupied native failure remains unadmitted; no resend or skip')


def collect(ctx, output, pending, states, native_ids, *, execute_native=False, owner_headroom=False, limit=None):
    c = ctx['collector']; binding = ctx['binding']
    native_authority(execute_native, owner_headroom, states, c.SETTLED)
    if (output / 'STOP').exists(): return 3
    if not pending: return 0
    helper = call_codex = broker = None
    if ctx['plan']['endpoint'] == 'sol':
        source = c.source_settings(ctx['manifest'], ctx['root'])
        helper = c.p.load_module('hanna_suffix_secondary_helper', Path(source['external_pins']['secondary_helper_path_local_only']))
        env = c.t.secondary_binding(source, helper); os.environ.clear(); os.environ.update(env)
        from adaptive_settings.account_probe import probe
        from hbqrs import runner
        c.t.secondary_binding(source, helper, probe(helper.CLI)); call_codex = runner._call_codex
    else:
        require(c.grok_contact_allowed(binding['route']), 'Execution route expiry/campaign deadline prevents contact')
        from model_work_queue.broker import Broker
        broker = Broker(ctx['route_root'].resolve())
    if not output.exists():
        output.mkdir(parents=True, exist_ok=False)
        c.record(output / 'job.json', binding); c.write_bytes(output / 'frozen-manifest.json', ctx['manifest_raw'])
        c.write_bytes(output / 'frozen-plan.json', ctx['plan_path'].read_bytes())
        if ctx['plan']['endpoint'] == 'sol': c.record(output / 'account-binding.json', c.t.account_receipt(binding))
    invocation_name = 'execution-invocation-' + str(uuid.uuid4()) + '.json'
    invocation_raw = p.canonical({'argv': sys.argv, 'workers': binding['workers'], 'job_sha256': p.digest((output / 'job.json').read_bytes()),
        'time': datetime.now(timezone.utc).isoformat(), 'owner_global_headroom_confirmation': True,
        'native_execution_explicitly_requested': True, 'plan_sha256': ctx['plan_sha'], 'executor_sha256': binding['executor_sha256']})
    c.write_bytes(output / invocation_name, invocation_raw)
    invocation = {'path': invocation_name, 'sha256': p.digest(invocation_raw), 'bytes': len(invocation_raw)}
    commit = c.CommitState(native_ids, invocation)
    selected = {row['request_sha256'] for row in ctx['rows']}
    def execute(row):
        require(row['request_sha256'] in selected and row['endpoint_ordinal'] > ctx['plan']['reserved_through'], 'Reserved prefix cannot dispatch')
        state = c.collect_one(row, ctx['manifest'], binding, ctx['root'], output, ctx['subset'], ctx['validator'],
                              ctx['receipts'], helper, call_codex, broker, commit)
        actual, _ = c.replay(c.sample_path(output, row), row, ctx['manifest'], binding, ctx['root'], ctx['receipts'], ctx['subset'], ctx['validator'])
        require(actual['state'] == state, 'New suffix terminal replay differs')
        return state
    observed = c.dispatch(pending[:limit], binding['workers'], execute, commit, lambda: (output / 'STOP').exists(),
                         lambda row, state: print(json.dumps({'ordinal': row['endpoint_ordinal'], 'state': state}), flush=True))
    c.record(output / ('dispatch-terminal-' + str(uuid.uuid4()) + '.json'), {'policy': POLICY,
        'plan_sha256': ctx['plan_sha'], 'execution_invocation': invocation, 'workers': binding['workers'],
        'settled_this_execution': len(observed), 'states': dict(Counter(observed)), 'stopped': commit.stop.is_set(),
        'inflight_at_terminal': 0, 'automatic_retries': 0, 'full_planned_denominator': 6864,
        'human_label_gate': p.label_gate(ctx['plan'], sum(state in c.SETTLED for state in states + observed)),
        'human_targets_opened': False, 'reserved_prefix_resent': False})
    return 3 if commit.stop.is_set() else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--plan', type=Path, required=True); parser.add_argument('--plan-sha256', required=True)
    parser.add_argument('--results-dir', type=Path, required=True); parser.add_argument('--workers', type=int, required=True)
    parser.add_argument('--route-root', type=Path); parser.add_argument('--route-sha256')
    parser.add_argument('--validate-only', action='store_true'); parser.add_argument('--execute-native', action='store_true')
    parser.add_argument('--owner-global-headroom-verified', action='store_true'); parser.add_argument('--limit', type=int)
    args = parser.parse_args()
    require(not (args.validate_only and args.execute_native) and (args.limit is None or args.limit > 0), 'Execution/validation mode or limit invalid')
    ctx = context(args.plan.resolve(), args.plan_sha256, args.workers, args.route_root, args.route_sha256)
    require(ctx['collector'].execution_workers(sys.argv) == args.workers, 'Explicit workers argv differs')
    output = preflight(args.results_dir, ctx); pending, states, identities = inventory(ctx, output)
    if args.validate_only:
        print(json.dumps({'policy': POLICY, 'state': 'provider_free_validated', 'endpoint': ctx['plan']['endpoint'],
            'plan_sha256': args.plan_sha256, 'executor_sha256': ctx['binding']['executor_sha256'], 'workers': args.workers,
            'full_planned_denominator': 6864, 'reserved_endpoint_prefix': ctx['plan']['reserved_through'],
            'planned_untouched_suffix': len(ctx['rows']), 'untouched': len(pending), 'terminal_states': dict(Counter(states)),
            'retained_native_identities': len(seeded_identities(ctx['plan'])), 'provider_calls': 0, 'new_votes_from_prefix': 0,
            'human_release_eligible': False, 'human_targets_opened': False, 'headroom_observed_by_validator': False}, sort_keys=True)); return 0
    return collect(ctx, output, pending, states, identities, execute_native=args.execute_native,
                   owner_headroom=args.owner_global_headroom_verified, limit=args.limit)


if __name__ == '__main__': raise SystemExit(main())
