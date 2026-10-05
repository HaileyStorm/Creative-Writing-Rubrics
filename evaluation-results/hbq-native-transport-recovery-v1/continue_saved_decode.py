"""Frozen saved-decode prefixes and untouched Grok suffixes; execution is explicit."""
from collections import Counter
from copy import deepcopy
import argparse
import json
from pathlib import Path
import sys
import threading

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import continue_failed_transport as f

r = f.r
canonical, digest, require, meta, write = f.canonical, f.digest, f.require, f.meta, f.write
POLICY = 'saved_decode_prefix_untouched_suffix_v1'
PREDECESSOR_SHA = 'c9079969a868f0800ef22e681d4304424af9c738ed514755f3a3aaf968fa243e'
READER_SHA = 'f285d228607c26cca0009d17626e7d6915f3d715e3b29f02784a25c682f4be68'
FIXED_RECEIPT = 'semantic-crossform/grok-decode-saved-reconciliation-001/reconciliation.json'
FIXED_SHA = '5fb54f10124a7e06737f4f0894dd72d3ccf30c3b9c0f195f5495df55ca02e233'
SOURCES = {
    'p1': {'directory': 'semantic-crossform', 'through': 176, 'overlays': [175, 176],
           'plan_sha256': '1d8b0b917aab8ceda558445e4a87a35c44b2d69ad027a125f543bbe6f45b063f',
           'job_sha256': 'c3b0f80a3a945efb364ab9c7a12494f592ff33e5d68f0d11feec1ed8c42c2a3f',
           'lifecycle_sha256': 'd66b2004747e77bc11a32da2d400dc354b6f92610d699288b05e06adef00cefd',
           'endpoint_denominator': 792, 'full_planned_denominator': 1584},
    'mfa': {'directory': 'mfa-canary', 'through': 147, 'overlays': [142],
            'plan_sha256': '3ea8e9d5ffaf7fed58bf71304460ca70c69338883807efbc88df937ef25645ff',
            'job_sha256': 'c1180d6ccb9f2b1d24229bc8bd92c2cb40f4c58606975e22c37a24f32fd1013e',
            'lifecycle_sha256': 'cafc35fe5b1cfa20c71dd28cc12d2352ce61634357e60a2c90bb4a9f2eba2893',
            'endpoint_denominator': 434, 'full_planned_denominator': 868}}


def reader():
    require(digest(Path(f.__file__).read_bytes()) == PREDECESSOR_SHA, 'Frozen predecessor differs')
    path = HERE / 'reconcile_failed_suffix.py'
    require(digest(path.read_bytes()) == READER_SHA, 'Exact saved decode reader differs')
    return r.load('continuation_saved_decode_private_reader', path)


def joined_prefix(prefix, rows, overlays, *, through, job_sha):
    """Overlay admissions, never identity or original disposition."""
    require(len(overlays) == len({e['endpoint_ordinal'] for e in overlays}), 'Duplicate saved overlay')
    by_ordinal = {e['endpoint_ordinal']: e for e in overlays}
    rows_by_ordinal = {row['endpoint_ordinal']: row for row in rows}
    result = deepcopy(prefix)
    require([e['endpoint_ordinal'] for e in result] == list(range(1, through + 1)), 'Noncontiguous reserved prefix')
    require(len({e['logical_sample_id'] for e in result}) == through, 'Duplicate reserved logical vote')
    require(set(by_ordinal) <= set(rows_by_ordinal), 'Saved overlay outside source membership')
    for entry in result:
        row = rows_by_ordinal[entry['endpoint_ordinal']]
        require(entry['endpoint'] == row['endpoint'] == 'grok'
                and entry['logical_sample_id'] == row['logical_sample_id']
                and entry['request_sha256'] == row['request_sha256'], 'Reserved original request differs')
        overlay = by_ordinal.get(entry['endpoint_ordinal'])
        if overlay is None:
            continue
        require(entry['state'] == overlay['original_state'] == 'ambiguous'
                and overlay['endpoint'] == 'grok'
                and overlay['logical_sample_id'] == row['logical_sample_id']
                and overlay['request_sha256'] == row['request_sha256']
                and overlay['source_job_sha256'] == job_sha
                and overlay['source_terminal_sha256'] == entry['source_terminal_sha256']
                and overlay['native']['saved_history']['session_id'] == entry['native_identity']
                and overlay['state'] in {'accepted', 'semantic_rejected'}
                and overlay['same_original_observation_only'] is True
                and overlay['new_votes'] == 0 and overlay['no_resend'] is True,
                'Saved overlay does not bind the exact original observation')
        entry.update(original_state=entry['state'], state=overlay['state'], saved_decode_admission=deepcopy(overlay),
                     saved_decode_receipt_sha256=FIXED_SHA, original_strict_v5_admission_satisfied=False)
    return result


def build_plan(config):
    pin = SOURCES[config['study']]
    d = reader()
    program = Path(config['program_root_local_only']).resolve()
    require(program == d.PROGRAM.resolve(), 'Only the committed program sources are supported')
    base = program / pin['directory']
    parent_path = base / 'failed-transport-grok-plan-001/plan.json'
    parent, ctx = f.verify_plan(parent_path, pin['plan_sha256'])
    source = base / 'judging-grok-failed-transport-001'
    job_raw = (source / 'job.json').read_bytes()
    require(digest(job_raw) == pin['job_sha256'], 'Exact stopped suffix job differs')
    job = json.loads(job_raw)
    require(job == f.existing_binding(parent, pin['plan_sha256'], job['workers'], source), 'Stopped suffix execution binding differs')
    lifecycle_path = base / 'failed-transport-grok-lifecycle-001/terminal.json'
    lifecycle_raw = lifecycle_path.read_bytes()
    require(digest(lifecycle_raw) == pin['lifecycle_sha256'] and json.loads(lifecycle_raw)['exit_code'] == 3,
            'Stopped outer lifecycle differs')
    receipt_path = program / FIXED_RECEIPT
    fixed = d.verify(receipt_path, FIXED_SHA)
    overlays = [e for e in fixed['observations'] if e['study'] == pin['directory']]
    require(sorted(e['endpoint_ordinal'] for e in overlays) == pin['overlays'], 'Fixed observation membership differs')
    rows = [row for row in ctx['manifest']['requests'] if row['endpoint'] == 'grok']
    require(len(rows) == pin['endpoint_denominator'] and len(ctx['manifest']['requests']) == pin['full_planned_denominator'],
            'Full original denominator differs')
    attempted = rows[parent['reserved_through']:pin['through']]
    module = ctx['module']
    require({p.name for p in source.iterdir() if p.is_dir()} == {module.sample_path(source, row).name for row in attempted},
            'Stopped suffix inventory is not the exact settled prefix')
    prefix = deepcopy(parent['prefix'])
    for row in attempted:
        sample = module.sample_path(source, row)
        state, _, _ = f.replay(ctx, row, source, job)
        require(state in module.SETTLED or row['endpoint_ordinal'] in pin['overlays'], 'Unsettled prefix has no fixed saved proof')
        prefix.append({'endpoint': 'grok', 'endpoint_ordinal': row['endpoint_ordinal'],
                       'logical_sample_id': row['logical_sample_id'], 'request_sha256': row['request_sha256'],
                       'state': state, 'source_root_local_only': str(source), 'source_job_sha256': pin['job_sha256'],
                       'source_terminal_sha256': digest((sample / 'terminal.json').read_bytes()),
                       'source_inventory': {p.relative_to(sample).as_posix(): meta(p.read_bytes())
                                            for p in sorted(sample.rglob('*')) if p.is_file()},
                       'native_identity': json.loads((sample / 'native-identity.json').read_bytes())['session_id'],
                       'no_resend': True, 'new_votes': 0})
    prefix = joined_prefix(prefix, rows, overlays, through=pin['through'], job_sha=pin['job_sha256'])
    identities = []
    for entry in prefix:
        sample = module.sample_path(Path(entry['source_root_local_only']), entry)
        identity = json.loads((sample / 'native-identity.json').read_bytes())['session_id']
        require(entry.get('native_identity', identity) == identity, 'Prefix native identity differs')
        entry['native_identity'] = identity
        identities.append(identity)
    require(len(set(identities)) == len(identities), 'Duplicate prefix native identity')
    files = {'implementation/continue_saved_decode.py': Path(__file__).read_bytes(),
             'implementation/continue_failed_transport.py': Path(f.__file__).read_bytes(),
             'implementation/reconcile_failed_suffix.py': Path(d.__file__).read_bytes(),
             'parent-plan.json': parent_path.read_bytes(), 'source-job.json': job_raw,
             'source-lifecycle-terminal.json': lifecycle_raw, 'saved-reconciliation.json': receipt_path.read_bytes()}
    plan = {'schema_version': 1, 'policy': POLICY, 'config': config, 'study': config['study'], 'endpoint': 'grok',
            'collector_sha256': digest(Path(__file__).read_bytes()), 'saved_reader_sha256': READER_SHA,
            'original_manifest_sha256': parent['original_manifest_sha256'],
            'parent_plan_sha256': pin['plan_sha256'], 'source_job_sha256': pin['job_sha256'],
            'source_root_local_only': str(source), 'source_lifecycle_sha256': pin['lifecycle_sha256'],
            'saved_receipt_path_local_only': str(receipt_path), 'saved_receipt_sha256': FIXED_SHA,
            'reserved_through': pin['through'], 'prefix': prefix,
            'untouched_request_sha256s': [row['request_sha256'] for row in rows[pin['through']:]],
            'source_binding': job, 'endpoint_denominator': pin['endpoint_denominator'],
            'full_planned_denominator': pin['full_planned_denominator'],
            'timeout_seconds': 900, 'attempts_per_logical_sample': 1, 'automatic_retries': 0,
            'allowed_workers': [1, 10], 'project_endpoint_concurrency_limit': 10,
            'execution_descendant': POLICY, 'prospective_saved_completion_policy': d.POLICY,
            'human_label_gate': 'all_original_planned_slots_verified_terminal_plus_explicit_postprediction_release_v1',
            'human_targets_opened': False, 'provider_calls': 0, 'new_votes': 0,
            'original_native_envelopes_reconstructed': False, 'physical_contact_cardinality_proven': False,
            'artifacts': {name: meta(raw) for name, raw in files.items()}}
    files['plan.json'] = canonical(plan)
    ctx.update(saved_decode_reader=d, saved_decode_source=source, saved_decode_receipt=receipt_path,
               saved_decode_parent=parent_path)
    return plan, files, ctx


def verify_plan(path, sha):
    raw = path.read_bytes()
    require(digest(raw) == sha, 'Exact saved-decode continuation plan differs')
    saved = json.loads(raw)
    for name, pin in saved['artifacts'].items():
        require(meta((path.parent / name).read_bytes()) == pin, 'Frozen continuation artifact differs')
    actual, _, ctx = build_plan(saved['config'])
    require(actual == saved, 'Saved prefix/source/code commitments differ')
    return saved, ctx


def validate_output(output, ctx, plan_root=None):
    f.validate_output(output, ctx, plan_root)
    protected = [ctx['saved_decode_source'], ctx['saved_decode_receipt'].parent, ctx['saved_decode_parent'].parent]
    require(all(not output.is_relative_to(p.resolve()) and not p.resolve().is_relative_to(output) for p in protected),
            'Output overlaps saved-decode source evidence')


def job_binding(plan, sha, workers, route, route_sha):
    require(type(workers) is int and 1 <= workers <= 10, 'Workers must fit the owner-allocated endpoint headroom')
    f.validate_execution_route(plan['source_binding']['route'], route, route_sha)
    binding = deepcopy(plan['source_binding'])
    binding.update(policy=POLICY, collector_sha256=digest(Path(__file__).read_bytes()),
                   saved_decode_plan_sha256=sha, source_job_sha256=plan['source_job_sha256'],
                   saved_decode_receipt_sha256=FIXED_SHA, saved_completion_reader_sha256=READER_SHA,
                   saved_completion_policy=plan['prospective_saved_completion_policy'],
                   reserved_prefix=plan['reserved_through'], reserved_prefix_sha256=digest(canonical(plan['prefix'])),
                   untouched_requests=len(plan['untouched_request_sha256s']),
                   untouched_request_commitment_sha256=digest(canonical(plan['untouched_request_sha256s'])),
                   full_planned_denominator=plan['full_planned_denominator'], workers=workers,
                   project_endpoint_concurrency_limit=10, route=deepcopy(route), route_sha256=route_sha,
                   source_route_sha256=plan['source_binding']['route_sha256'], execution_route_sha256=route_sha,
                   execution_route_selection='explicit_cli_sha256', saved_transport_recovery_enabled=True,
                   new_votes_from_reserved_failure=0, original_native_envelopes_reconstructed=False)
    return binding


def source_inventory(sample):
    return {p.relative_to(sample).as_posix(): meta(p.read_bytes()) for p in sorted(sample.rglob('*')) if p.is_file()
            and p.relative_to(sample).parts[0] not in {'decode-native', 'decode-reconciliation.json'}}


def projected_sample(ctx, row, output, binding, *, saved=None):
    module, d = ctx['module'], ctx['saved_decode_reader']
    sample = module.sample_path(output, row)
    terminal, _ = module.replay(sample, row, ctx['manifest'], binding, ctx['root'], r.codex_receipts, ctx['subset'], ctx['validator'])
    failure = json.loads((sample / 'native-result.json').read_bytes())
    require(terminal['state'] == failure['state'] == 'ambiguous' and terminal['no_resend'] is True
            and failure['result'] is None and failure['failure']['code'] in
            {'validation_tool_policy_attestation', 'unclassified_after_launch'}
            and not (sample / 'native-envelope.json').exists(), 'Failure outside bounded decode recovery')
    started, prompt, schema, texts, context = r.validate_started(module, sample, row, binding,
                                                               binding['manifest_sha256'], ctx['root'], ctx['manifest'])
    session = json.loads((sample / 'native-identity.json').read_bytes())['session_id']
    if saved:
        selected = Path(saved['native_sources']['summary']['source_locator_local_only']).parent
    else:
        matches = list(d.SESSIONS.glob('*/' + r.codex_receipts._uuid(session)))
        require(len(matches) == 1, 'Exact own saved session missing or ambiguous')
        selected = matches[0]
    require(selected.resolve().is_relative_to(d.SESSIONS.resolve()) and selected.name == session, 'Own saved session locator differs')
    answer, native, reads = d.saved_completion(sample, prompt, selected, started, binding,
                                              snapshot=sample if saved else None,
                                              commitments=saved['native_sources'] if saved else None)
    ctx['subset'].validate_schema(json.loads(schema))
    admission = ctx['validator'].semantic_validate(row['arm'], answer, row, texts, ctx['subset'], context=context, schema=json.loads(schema))
    commitments = reads.commitments()
    for name, pin in commitments.items():
        pin['snapshot'] = 'decode-native/' + name + '.bin'
    receipt = {'schema_version': 1, 'policy': d.POLICY, 'reader_sha256': READER_SHA,
               'collector_sha256': digest(Path(__file__).read_bytes()), 'job_sha256': digest((output / 'job.json').read_bytes()),
               'logical_sample_id': row['logical_sample_id'], 'request_sha256': row['request_sha256'],
               'manifest_sha256': binding['manifest_sha256'], 'original_state': terminal['state'],
               'source_terminal_sha256': digest((sample / 'terminal.json').read_bytes()),
               'source_inventory': source_inventory(sample), 'native_identity': session,
               'native': native, 'native_sources': commitments, 'admission': admission,
               'state': 'accepted' if admission['accepted'] else 'semantic_rejected',
               'response': answer, 'response_sha256': digest(canonical(answer)),
               'same_original_observation_only': True, 'new_votes': 0, 'no_resend': True,
               'human_targets_opened': False, 'original_strict_v5_admission_satisfied': False,
               'original_native_envelopes_reconstructed': False, 'physical_contact_cardinality_proven': False}
    if saved:
        require(receipt == saved, 'Own saved-decode descendant replay differs')
    else:
        for name, raw in reads.raws.items():
            write(sample / commitments[name]['snapshot'], raw)
        module.record(sample / 'decode-reconciliation.json', receipt)
    return receipt['state'], answer if admission['accepted'] else None


def effective_replay(ctx, row, output, binding):
    sample = ctx['module'].sample_path(output, row)
    path = sample / 'decode-reconciliation.json'
    if path.exists():
        return projected_sample(ctx, row, output, binding, saved=json.loads(path.read_bytes()))
    state, answer, _ = f.replay(ctx, row, output, binding)
    return state, answer


def inventory(plan, ctx, output, binding):
    rows = f.suffix_rows(plan, ctx)
    pending, states = [], []
    identities = {entry['native_identity'] for entry in plan['prefix']}
    if output.exists():
        require(json.loads((output / 'job.json').read_bytes()) == binding, 'Exact continuation job differs')
        require({p.name for p in output.iterdir() if p.is_dir()} <= {ctx['module'].sample_path(output, row).name for row in rows},
                'Reserved or unknown logical slot occupied')
    for row in rows:
        sample = ctx['module'].sample_path(output, row)
        if not sample.exists():
            pending.append(row)
            continue
        require((sample / 'terminal.json').exists(), 'Started/incomplete slot remains reserved; no resend')
        state, _ = effective_replay(ctx, row, output, binding)
        native = json.loads((sample / 'native-identity.json').read_bytes())['session_id']
        require(native not in identities, 'Duplicate original native observation')
        identities.add(native)
        states.append(state)
    return pending, states


def label_gate(plan, states, pending, *, explicit=False):
    # Complementary endpoint and older unresolved native observations need a separate verified analysis join.
    return {'policy': plan['human_label_gate'], 'planned': plan['full_planned_denominator'],
            'endpoint_planned': plan['endpoint_denominator'], 'reserved_prefix': len(plan['prefix']),
            'verified_suffix_terminal': len(states), 'untouched_suffix': len(pending),
            'reserved_missing': sum(e['state'] not in {'accepted', 'semantic_rejected'} for e in plan['prefix']),
            'all_original_slots_verified_terminal': False, 'explicit_postprediction_release': explicit,
            'human_release_eligible': False, 'human_targets_opened': False,
            'remaining_join_limitation': 'Exact complementary endpoint and unresolved original observations remain required',
            'provider_calls': 0}


def collect(plan, ctx, output, binding, route_root, *, execute_native=False, headroom=False, route_confirmed=False, limit=None):
    require(execute_native and headroom and route_confirmed, 'Native execution needs explicit current owner headroom and route confirmation')
    pending, states = inventory(plan, ctx, output, binding)
    module = ctx['module']
    require(all(state in module.SETTLED for state in states), 'Occupied failed slot cannot be resent or silently skipped')
    if (output / 'STOP').exists():
        module.note_stop(output)
        return 3
    if not pending:
        return 0
    require(module.grok_contact_allowed(), 'Campaign cutoff prevents another 900-second contact')
    f.reviewed_route(binding, route_root)
    sys.path.insert(0, str(ctx['tools']))
    from model_work_queue.broker import Broker
    broker = Broker(route_root)
    if not output.exists():
        output.mkdir(parents=True, exist_ok=False)
        module.record(output / 'job.json', binding)
    stop = threading.Event()
    def stopped():
        return stop.is_set() or (output / 'STOP').exists()
    def call(row):
        if stopped():
            return 'dispatch_stopped_before_slot'
        if not module.grok_contact_allowed():
            stop.set()
            return 'campaign_deadline_prevents_contact'
        try:
            state = module.collect_one(row, ctx['manifest'], binding, ctx['root'], output,
                                       ctx['subset'], ctx['validator'], r.codex_receipts, broker=broker)
            if state not in module.SETTLED:
                try:
                    state, _ = projected_sample(ctx, row, output, binding)
                except (OSError, ValueError, KeyError, TypeError):
                    # Unsupported or incomplete saved observations remain the original failed slots.
                    stop.set()
            actual, _ = effective_replay(ctx, row, output, binding)
            require(actual == state, 'New terminal/descendant replay differs')
        except BaseException:
            stop.set()
            raise
        if state not in module.SETTLED:
            stop.set()
        print(json.dumps({'ordinal': row['endpoint_ordinal'], 'state': state}), flush=True)
        return state
    _, failed = f.dispatch(pending[:limit], call, binding['workers'], stopped, module.SETTLED)
    if (output / 'STOP').exists():
        module.note_stop(output)
    return 3 if failed else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    sub = parser.add_subparsers(dest='mode', required=True)
    prep = sub.add_parser('prepare')
    prep.add_argument('--study', choices=SOURCES, required=True)
    prep.add_argument('--program-root', type=Path, required=True)
    prep.add_argument('--output-root', type=Path, required=True)
    prep.add_argument('--dry-run', action='store_true')
    run = sub.add_parser('collect')
    run.add_argument('--plan', type=Path, required=True)
    run.add_argument('--plan-sha256', required=True)
    run.add_argument('--results-dir', type=Path, required=True)
    run.add_argument('--route-root', type=Path, required=True)
    run.add_argument('--execution-route-sha256', required=True)
    run.add_argument('--workers', type=int, default=1)
    run.add_argument('--limit', type=int)
    action = run.add_mutually_exclusive_group(required=True)
    action.add_argument('--validate-only', action='store_true')
    action.add_argument('--execute-native', action='store_true')
    run.add_argument('--owner-global-headroom-verified', action='store_true')
    run.add_argument('--owner-current-route-verified', action='store_true')
    args = parser.parse_args()
    if args.mode == 'prepare':
        config = {'study': args.study, 'program_root_local_only': str(args.program_root.resolve())}
        plan, files, ctx = build_plan(config)
        output = args.output_root.resolve()
        validate_output(output, ctx)
        require(not output.exists(), 'Plan output must be fresh')
        if not args.dry_run:
            for name, raw in files.items():
                write(output / name, raw)
        print(json.dumps({'state': 'provider_free_saved_decode_plan', 'study': args.study,
                          'plan_sha256': digest(files['plan.json']), 'reserved_through': plan['reserved_through'],
                          'untouched': len(plan['untouched_request_sha256s']),
                          'prefix_states': dict(Counter(e['state'] for e in plan['prefix'])),
                          'saved_observations_adopted_once': len(SOURCES[args.study]['overlays']),
                          'full_planned_denominator': plan['full_planned_denominator'],
                          'provider_calls': 0, 'new_votes': 0, 'human_targets_opened': False,
                          'output_written': not args.dry_run}))
        return 0
    require(args.limit is None or args.limit > 0, 'Positive contact limit required')
    plan, ctx = verify_plan(args.plan, args.plan_sha256)
    output = args.results_dir.resolve()
    validate_output(output, ctx, args.plan.parent)
    route = f.select_execution_route(plan, args.route_root, args.execution_route_sha256)
    binding = job_binding(plan, args.plan_sha256, args.workers, route, args.execution_route_sha256)
    f.reviewed_route(binding, args.route_root)
    if args.validate_only:
        pending, states = inventory(plan, ctx, output, binding)
        print(json.dumps({'state': 'provider_free_validated', 'study': plan['study'], 'workers': args.workers,
                          **label_gate(plan, states, pending)}))
        return 0
    return collect(plan, ctx, output, binding, args.route_root, execute_native=args.execute_native,
                   headroom=args.owner_global_headroom_verified, route_confirmed=args.owner_current_route_verified,
                   limit=args.limit)


if __name__ == '__main__':
    raise SystemExit(main())
