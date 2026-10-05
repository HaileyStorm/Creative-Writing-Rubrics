"""P1 Grok reserved prefix215 and untouched suffix; named saved completions only."""
from collections import Counter
from copy import deepcopy
import argparse
import json
from pathlib import Path
import sys
import threading

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import continue_saved_decode as old

f, r = old.f, old.r
canonical, digest, require, meta, write = old.canonical, old.digest, old.require, old.meta, old.write
POLICY = 'p1_saved_prefix_untouched_suffix_v2'
ORDINARY = 'saved_grok_ordinary_four_record_completed_history_v1'
PROGRAM = Path(r'C:\Users\Haile\Documents\cwr-resume-control-20260919-r1\successor-program-20261004')
BASE = PROGRAM / 'semantic-crossform'
PLAN_ROOT = BASE / 'saved-prefix-v2-001'
SOURCE = BASE / 'judging-grok-saved-decode-001'
FROZEN = BASE / 'matched-frozen-002'
PARENT = BASE / 'saved-decode-grok-plan-001/plan.json'
PARENT_SHA = '417c211cd33e56a730ec57bad4a99d83aa4465c6c7afda7149abcbec641beffa'
MANIFEST_SHA = '4e139dc1ef859be838cbe9ee8c579285845074032c6a00867a1b03859fdec2ff'
JOB_SHA = 'b667fa6c7a5dd1893cc5e7b73b647a427945a3665c685064960d6dffda5da58b'
OUTER = BASE / 'saved-decode-grok-lifecycle-001/terminal.json'
OUTER_SHA = '7d226e3867e5a134f2f37eff42907d6d64ea9cc832e67b9cd08aa0c184521409'
FIXED = BASE / 'slot209-ordinary-completion-reconciliation-001/reconciliation.json'
FIXED_SHA = 'a4babf3ee0413ca2ba7803f7128bf31cc2642074fdc5c7dc4fb43cba3d1a8579'
TOOLS = Path(r'C:\Users\Haile\.codex\tools')
CODE = {
    'old': ('continue_saved_decode.py', '993ef94ac1f032fd44d880fc953238a4653d6777f9fba964bbb73aa1c12ff7d2'),
    'failed': ('continue_failed_transport.py', 'c9079969a868f0800ef22e681d4304424af9c738ed514755f3a3aaf968fa243e'),
    'generic': ('reconcile.py', 'fbedc8e50d08de7dff0547483f26c9fd081a8b4c9e62f0713609ce043e0fb34c'),
    'decode': ('reconcile_failed_suffix.py', 'f285d228607c26cca0009d17626e7d6915f3d715e3b29f02784a25c682f4be68'),
    'fixed': ('reconcile_p1_ordinary_completion.py', 'c86b0895e21a94be435b96faf17aa052fd2b1ea99ce76829bd82cae1c56a3b3e'),
    'history': ('../hbq-matched-ttcw-20261004/reconcile_history.py', 'a9e27d3c5da5ff341f0f7172d7dfffd6c139fe8f569b2655e55fbf7279c676ed'),
    'collector': ('../hbq-semantic-crossform-p1b-matched-v1/collector.py', '71e4a5e1a21ff45338796b060fadde638367067da922786e0a810eec42e8feaa')}


def pinned(path, sha):
    raw = path.read_bytes()
    require(digest(raw) == sha, 'Exact saved-prefix source pin differs: ' + path.name)
    return raw


def implementation(key):
    relative, sha = CODE[key]
    pinned(HERE / relative, sha)
    return r.load('p1_saved_prefix_v2_private_' + key, HERE / relative)


def reserve_once(prefix, rows, fixed):
    require([entry['endpoint_ordinal'] for entry in prefix] == list(range(1, 216)), 'Reserved prefix must be exactly1..215')
    require(len({entry['logical_sample_id'] for entry in prefix}) == 215
            and len({entry['native_identity'] for entry in prefix}) == 215, 'Duplicate original prefix identity')
    require(len(rows) == 792 and len({row['request_sha256'] for row in rows}) == 792, 'Full original Grok geometry differs')
    for entry, row in zip(prefix, rows):
        require(entry['endpoint'] == row['endpoint'] == 'grok' and entry['endpoint_ordinal'] == row['endpoint_ordinal']
                and entry['logical_sample_id'] == row['logical_sample_id'] and entry['request_sha256'] == row['request_sha256']
                and entry['no_resend'] is True and entry['new_votes'] == 0, 'Reserved original request differs')
    result = deepcopy(prefix)
    entry = result[208]
    require(entry['state'] == fixed['original_state'] == 'ambiguous'
            and fixed['endpoint_ordinal'] == 209 and fixed['endpoint'] == 'grok'
            and entry['logical_sample_id'] == fixed['logical_sample_id']
            and entry['request_sha256'] == fixed['request_sha256']
            and entry['source_job_sha256'] == fixed['source_job_sha256'] == JOB_SHA
            and entry['source_terminal_sha256'] == fixed['source_terminal_sha256']
            and entry['native_identity'] == fixed['native']['saved_history']['session_id']
            and fixed['same_original_observation_only'] is True and fixed['new_votes'] == 0
            and fixed['no_resend'] is True and fixed['human_labels_opened'] is False,
            'Fixed209 proof differs from the once-only original failure')
    accepted = fixed['admission']['accepted']
    require(type(accepted) is bool and fixed['state'] == ('accepted' if accepted else 'semantic_rejected'), 'Fixed semantic disposition differs')
    entry.update(original_state='ambiguous', state=fixed['state'], qualified_ordinary_admission=deepcopy(fixed),
                 qualified_ordinary_receipt_sha256=FIXED_SHA, original_strict_v5_admission_satisfied=False)
    return result


def build_plan():
    for relative, sha in CODE.values():
        pinned(HERE / relative, sha)
    parent_raw = pinned(PARENT, PARENT_SHA)
    parent = json.loads(parent_raw)
    require(parent['reserved_through'] == 176 and parent['original_manifest_sha256'] == MANIFEST_SHA
            and parent['full_planned_denominator'] == 1584 and parent['endpoint_denominator'] == 792,
            'Frozen original prefix/ancestor geometry differs')
    # Preserve the verified ancestor commitments without executing its176 native replays again.
    for name, pin in parent['artifacts'].items():
        require(meta((PARENT.parent / name).read_bytes()) == pin, 'Frozen ancestor artifact differs')
    module, decoder, fixed_reader = implementation('collector'), implementation('decode'), implementation('fixed')
    manifest, root, subset, validator = module.load_manifest(FROZEN / 'manifest.json', MANIFEST_SHA, TOOLS)
    require(len(manifest['requests']) == 1584 and manifest['human_alignment_claim'] is False, 'Full descriptive P1 contract differs')
    ctx = {'module': module, 'manifest': manifest, 'root': root, 'subset': subset, 'validator': validator,
           'tools': TOOLS, 'saved_decode_reader': decoder}
    job_raw = pinned(SOURCE / 'job.json', JOB_SHA)
    job = json.loads(job_raw)
    require(job == old.job_binding(parent, PARENT_SHA, job['workers'], job['route'], job['execution_route_sha256']),
            'Stopped source job/account/route binding differs')
    for key, path in [('broker_sha256', 'model_work_queue/broker.py'),
                      ('grok_adapter_sha256', 'model_work_queue/adapters/grok_exec.py'),
                      ('account_probe_sha256', 'adaptive_settings/account_probe.py')]:
        pinned(TOOLS / path, job[key])
    outer_raw = pinned(OUTER, OUTER_SHA)
    require(json.loads(outer_raw)['exit_code'] == 3, 'True source outer lifecycle is not terminal')
    rows = [row for row in manifest['requests'] if row['endpoint'] == 'grok']
    attempted = rows[176:215]
    require({p.name for p in SOURCE.iterdir() if p.is_dir()} == {module.sample_path(SOURCE, row).name for row in attempted},
            'Stopped source is not exactly the settled39-slot prefix')
    prefix = deepcopy(parent['prefix'])
    for row in attempted:
        sample = module.sample_path(SOURCE, row)
        state, answer = old.effective_replay(ctx, row, SOURCE, job)
        require(state in module.SETTLED or row['endpoint_ordinal'] == 209 and state == 'ambiguous',
                'Unknown or incomplete source observation cannot be reserved as settled')
        entry = {'endpoint': 'grok', 'endpoint_ordinal': row['endpoint_ordinal'],
                 'logical_sample_id': row['logical_sample_id'], 'request_sha256': row['request_sha256'],
                 'state': state, 'source_root_local_only': str(SOURCE), 'source_job_sha256': JOB_SHA,
                 'source_terminal_sha256': digest((sample / 'terminal.json').read_bytes()),
                 'source_inventory': {p.relative_to(sample).as_posix(): meta(p.read_bytes()) for p in sorted(sample.rglob('*')) if p.is_file()},
                 'native_identity': json.loads((sample / 'native-identity.json').read_bytes())['session_id'],
                 'response': answer if state == 'accepted' else None, 'no_resend': True, 'new_votes': 0}
        prefix.append(entry)
    fixed = fixed_reader.verify(FIXED, FIXED_SHA)
    prefix = reserve_once(prefix, rows, fixed)
    raw_response = (FIXED.parent / 'response.json').read_bytes()
    prefix[208]['response'] = json.loads(raw_response) if fixed['admission']['accepted'] else None
    files = {'implementation/continue_p1_saved_prefix_v2.py': Path(__file__).read_bytes(),
             **{'implementation/' + key + '.py': (HERE / relative).read_bytes() for key, (relative, _) in CODE.items()},
             'parent-plan.json': parent_raw, 'source-job.json': job_raw, 'source-lifecycle-terminal.json': outer_raw,
             'fixed209-reconciliation.json': FIXED.read_bytes(), 'fixed209-response.json': raw_response,
             'original-manifest.json': (FROZEN / 'manifest.json').read_bytes()}
    plan = {'schema_version': 1, 'policy': POLICY, 'endpoint': 'grok', 'study': 'p1',
            'collector_sha256': digest(Path(__file__).read_bytes()), 'original_manifest_sha256': MANIFEST_SHA,
            'manifest_path_local_only': str(FROZEN / 'manifest.json'), 'parent_plan_sha256': PARENT_SHA,
            'source_job_sha256': JOB_SHA, 'source_lifecycle_sha256': OUTER_SHA,
            'fixed209_receipt_sha256': FIXED_SHA, 'fixed209_reader_sha256': CODE['fixed'][1],
            'reserved_through': 215, 'prefix': prefix, 'source_binding': job,
            'untouched_request_sha256s': [row['request_sha256'] for row in rows[215:]],
            'full_planned_denominator': 1584, 'endpoint_denominator': 792,
            'timeout_seconds': 900, 'attempts_per_logical_sample': 1, 'automatic_retries': 0,
            'allowed_workers': [1, 10], 'project_endpoint_concurrency_limit': 10,
            'prospective_saved_completion_policies': [ORDINARY, decoder.POLICY],
            'generic_reader_sha256': CODE['generic'][1], 'history_reader_sha256': CODE['history'][1],
            'saved_decode_reader_sha256': CODE['decode'][1], 'original148_reserved_unresolved': True,
            'human_label_gate': parent['human_label_gate'], 'human_targets_opened': False,
            'provider_calls': 0, 'new_votes': 0, 'original_native_envelopes_reconstructed': False,
            'original_strict_v5_admission_satisfied_for_projections': False, 'physical_contact_cardinality_proven': False,
            'cost_token_cache_latency_attestation': False, 'ancestor_verification': 'exact_frozen_plan_and_artifacts_no_native_replay',
            'artifacts': {name: meta(raw) for name, raw in files.items()}}
    files['plan.json'] = canonical(plan)
    return plan, files, ctx


def verify_plan(path, sha):
    raw = pinned(path, sha)
    saved = json.loads(raw)
    for name, pin in saved['artifacts'].items():
        require(meta((path.parent / name).read_bytes()) == pin, 'Frozen saved-prefix artifact differs')
    actual, _, ctx = build_plan()
    require(actual == saved, 'Exact prefix/source/runtime/projection binding differs')
    return saved, ctx


def validate_output(output, plan_root=None):
    protected = [r.REPO, FROZEN, SOURCE, PARENT.parent, FIXED.parent, old.reader().SESSIONS]
    if plan_root:
        protected.append(plan_root)
    require(output.is_relative_to(BASE.resolve()) and all(not output.is_relative_to(path.resolve())
            and not path.resolve().is_relative_to(output) for path in protected), 'Private output overlaps retained inputs')


def job_binding(plan, sha, workers, route, route_sha):
    require(type(workers) is int and 1 <= workers <= 10, 'Workers must fit explicit owner endpoint headroom1..10')
    f.validate_execution_route(plan['source_binding']['route'], route, route_sha)
    binding = deepcopy(plan['source_binding'])
    binding.update(policy=POLICY, collector_sha256=digest(Path(__file__).read_bytes()), saved_prefix_v2_plan_sha256=sha,
                   source_job_sha256=JOB_SHA, reserved_prefix=215, reserved_prefix_sha256=digest(canonical(plan['prefix'])),
                   untouched_requests=577, untouched_request_commitment_sha256=digest(canonical(plan['untouched_request_sha256s'])),
                   fixed209_receipt_sha256=FIXED_SHA, saved_completion_policies=plan['prospective_saved_completion_policies'],
                   saved_completion_policy='qualified_p1_completed_saved_history_selection_v2',
                   saved_completion_reader_sha256=digest(Path(__file__).read_bytes()),
                   generic_reader_sha256=CODE['generic'][1], history_reader_sha256=CODE['history'][1],
                   saved_decode_reader_sha256=CODE['decode'][1],
                   full_planned_denominator=1584, workers=workers, project_endpoint_concurrency_limit=10,
                   route=deepcopy(route), route_sha256=route_sha, source_route_sha256=plan['source_binding']['route_sha256'],
                   execution_route_sha256=route_sha, execution_route_selection='explicit_cli_sha256', new_votes_from_reserved_failure=0)
    return binding


def ordinary_records(updates, summary, session, prompt, history_text, assistant):
    require([row['params']['update']['sessionUpdate'] for row in updates] ==
            ['user_message_chunk', 'agent_thought_chunk', 'agent_message_chunk', 'turn_completed'], 'Unknown ordinary lifecycle')
    saved = history_text.encode('utf-8')
    require(updates[0]['params']['update']['content']['text'].encode('utf-8') == saved
            and (saved == prompt or prompt.endswith(b'\n') and saved == prompt[:-1]), 'Native user/history differs from exact prompt or single finalLF omission')
    require(summary['current_model_id'] == 'grok-4.7' and summary['reasoning_effort'] == 'high'
            and assistant['model_id'] == 'grok-4.7-build' and assistant['reasoning_effort'] == 'high', 'Native model/effort differs')
    try:
        r.grok_projection(updates, summary, session, prompt.decode('utf-8'))
    except ValueError as error:
        require(str(error) == 'No demonstrated Grok DNS recovery', 'Ordinary native record validation failed')
    else:
        raise ValueError('Ordinary history cannot admit retry diagnostics')


def saved_completion(ctx, sample, prompt, selected, started, binding, *, saved=None):
    class Reads(r.ReadSet):
        def raw(self, name, path):
            require(self.snapshot is None or name in self.expected, 'Own native snapshot commitment missing')
            return super().raw(name, path)
        def json(self, name, path):
            return json.loads(self.raw(name, path))
        def lines(self, name, path):
            return [json.loads(line) for line in self.raw(name, path).splitlines()]
    reads = Reads(sample if saved else None, saved['native_sources'] if saved else None)
    updates = reads.lines('updates', selected / 'updates.jsonl')
    if len(updates) == 5:
        answer, native, reads = ctx['saved_decode_reader'].saved_completion(sample, prompt, selected, started, binding,
            snapshot=sample if saved else None, commitments=saved['native_sources'] if saved else None)
        return answer, native, reads, ctx['saved_decode_reader'].POLICY
    summary = reads.json('summary', selected / 'summary.json')
    histories = reads.lines('prompt_history', selected.parent / 'prompt_history.jsonl')
    chat = reads.lines('chat', selected / 'chat_history.jsonl')
    assistants = [item for item in chat if item.get('type') == 'assistant']
    require(len(histories) == len(assistants) == 1, 'Ordinary native request/answer is not unique')
    ordinary_records(updates, summary, selected.name, prompt, histories[0]['prompt'], assistants[0])
    history = implementation('history')
    raw_response, native = history.history_response(reads, selected, {'session_id': selected.name}, started,
        {'model': binding['route']['model'], 'route': binding['route'], 'cutoff': binding['campaign_deadline']}, prompt)
    native.update(policy=ORDINARY, original_strict_v5_admission_satisfied=False)
    return json.loads(raw_response), native, reads, ORDINARY


def source_inventory(sample):
    return {p.relative_to(sample).as_posix(): meta(p.read_bytes()) for p in sorted(sample.rglob('*')) if p.is_file()
            and p.relative_to(sample).parts[0] not in {'qualified-native', 'qualified-completion.json'}}


def projected_sample(ctx, row, output, binding, *, saved=None):
    module = ctx['module']
    sample = module.sample_path(output, row)
    terminal, _ = module.replay(sample, row, ctx['manifest'], binding, ctx['root'], r.codex_receipts, ctx['subset'], ctx['validator'])
    failure = json.loads((sample / 'native-result.json').read_bytes())
    require(terminal['state'] == failure['state'] == 'ambiguous' and terminal['no_resend'] is True
            and failure['result'] is None and failure['failure']['code'] in {'unclassified_after_launch', 'validation_tool_policy_attestation'}
            and not (sample / 'native-envelope.json').exists(), 'Failure outside named saved completion policy')
    started, prompt, schema, texts, context = r.validate_started(module, sample, row, binding, MANIFEST_SHA, ctx['root'], ctx['manifest'])
    session = r.codex_receipts._uuid(json.loads((sample / 'native-identity.json').read_bytes())['session_id'])
    if saved:
        selected = Path(saved['native_sources']['summary']['source_locator_local_only']).parent
    else:
        matches = list(ctx['saved_decode_reader'].SESSIONS.glob('*/' + session))
        require(len(matches) == 1, 'Exact own saved session missing or ambiguous')
        selected = matches[0]
    require(selected.name == session and selected.resolve().is_relative_to(ctx['saved_decode_reader'].SESSIONS.resolve()), 'Own session locator differs')
    answer, native, reads, policy = saved_completion(ctx, sample, prompt, selected, started, binding, saved=saved)
    ctx['subset'].validate_schema(json.loads(schema))
    admission = ctx['validator'].semantic_validate(row['arm'], answer, row, texts, ctx['subset'], context=context, schema=json.loads(schema))
    commitments = reads.commitments()
    for name, pin in commitments.items():
        pin['snapshot'] = 'qualified-native/' + name + '.bin'
    receipt = {'schema_version': 1, 'policy': policy, 'collector_sha256': digest(Path(__file__).read_bytes()),
               'generic_reader_sha256': CODE['generic'][1], 'history_reader_sha256': CODE['history'][1],
               'saved_decode_reader_sha256': CODE['decode'][1], 'job_sha256': digest((output / 'job.json').read_bytes()),
               'logical_sample_id': row['logical_sample_id'], 'request_sha256': row['request_sha256'],
               'manifest_sha256': MANIFEST_SHA, 'source_terminal_sha256': digest((sample / 'terminal.json').read_bytes()),
               'source_inventory': source_inventory(sample), 'native_identity': session, 'native': native, 'native_sources': commitments,
               'admission': admission, 'state': 'accepted' if admission['accepted'] else 'semantic_rejected',
               'response': answer, 'response_sha256': digest(canonical(answer)), 'original_state': 'ambiguous',
               'same_original_observation_only': True, 'new_votes': 0, 'no_resend': True, 'human_targets_opened': False,
               'original_strict_v5_admission_satisfied': False, 'original_native_envelopes_reconstructed': False,
               'physical_contact_cardinality_proven': False, 'cost_token_cache_latency_attestation': False}
    if saved:
        require(receipt == saved, 'Own qualified saved completion replay differs')
    else:
        for name, raw in reads.raws.items():
            write(sample / commitments[name]['snapshot'], raw)
        module.record(sample / 'qualified-completion.json', receipt)
    return receipt['state'], answer if admission['accepted'] else None


def effective_replay(ctx, row, output, binding):
    sample = ctx['module'].sample_path(output, row)
    path = sample / 'qualified-completion.json'
    if path.exists():
        return projected_sample(ctx, row, output, binding, saved=json.loads(path.read_bytes()))
    terminal, answer = ctx['module'].replay(sample, row, ctx['manifest'], binding, ctx['root'], r.codex_receipts, ctx['subset'], ctx['validator'])
    return terminal['state'], answer


def inventory(plan, ctx, output, binding):
    rows = f.suffix_rows(plan, ctx)
    pending, states, identities = [], [], {entry['native_identity'] for entry in plan['prefix']}
    if output.exists():
        require(json.loads((output / 'job.json').read_bytes()) == binding, 'Own execution job differs')
        require({p.name for p in output.iterdir() if p.is_dir()} <= {ctx['module'].sample_path(output, row).name for row in rows}, 'Reserved/unknown slot occupied')
    for row in rows:
        sample = ctx['module'].sample_path(output, row)
        if not sample.exists():
            pending.append(row)
            continue
        require((sample / 'terminal.json').exists(), 'Started/incomplete slot is reserved; no resend')
        state, _ = effective_replay(ctx, row, output, binding)
        native = r.codex_receipts._uuid(json.loads((sample / 'native-identity.json').read_bytes())['session_id'])
        require(native not in identities, 'Duplicate native observation')
        identities.add(native)
        states.append(state)
    return pending, states


def collect(plan, ctx, output, binding, route_root, *, execute_native=False, headroom=False, route_confirmed=False, limit=None):
    require(execute_native and headroom and route_confirmed, 'Execution requires explicit current owner global headroom and route confirmation')
    pending, states = inventory(plan, ctx, output, binding)
    module = ctx['module']
    require(all(state in module.SETTLED for state in states), 'Occupied unknown failure cannot be resent or skipped')
    if (output / 'STOP').exists():
        module.note_stop(output)
        return 3
    if not pending:
        return 0
    require(module.grok_contact_allowed(), 'Cutoff prevents another900-second contact')
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
            state = module.collect_one(row, ctx['manifest'], binding, ctx['root'], output, ctx['subset'], ctx['validator'], r.codex_receipts, broker=broker)
            if state not in module.SETTLED:
                try:
                    state, _ = projected_sample(ctx, row, output, binding)
                except (OSError, ValueError, KeyError, TypeError):
                    stop.set()
            actual, _ = effective_replay(ctx, row, output, binding)
            require(actual == state, 'Own terminal/qualified completion replay differs')
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
    prep.add_argument('--output-root', type=Path, required=True)
    prep.add_argument('--dry-run', action='store_true')
    run = sub.add_parser('collect')
    for name in ('plan', 'results-dir', 'route-root'):
        run.add_argument('--' + name, type=Path, required=True)
    run.add_argument('--plan-sha256', required=True)
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
        output = args.output_root.resolve()
        require(output == PLAN_ROOT.resolve() and not output.exists(), 'Only the fresh named P1v2 plan output is supported')
        validate_output(output)
        plan, files, _ = build_plan()
        if not args.dry_run:
            for name, raw in files.items():
                write(output / name, raw)
        print(json.dumps({'state': 'provider_free_p1_saved_prefix_v2', 'plan_sha256': digest(files['plan.json']),
                          'reserved_through': 215, 'untouched': 577, 'prefix_states': dict(Counter(e['state'] for e in plan['prefix'])),
                          'fixed209_adopted_once': True, 'original148_reserved_unresolved': True, 'full_planned_denominator': 1584,
                          'endpoint_denominator': 792, 'human_release_eligible': False, 'provider_calls': 0, 'new_votes': 0,
                          'human_targets_opened': False, 'output_written': not args.dry_run}))
        return 0
    require(args.limit is None or args.limit > 0, 'Positive contact limit required')
    plan, ctx = verify_plan(args.plan.resolve(), args.plan_sha256)
    output = args.results_dir.resolve()
    validate_output(output, args.plan.parent)
    route = f.select_execution_route(plan, args.route_root, args.execution_route_sha256)
    binding = job_binding(plan, args.plan_sha256, args.workers, route, args.execution_route_sha256)
    f.reviewed_route(binding, args.route_root)
    if args.validate_only:
        pending, states = inventory(plan, ctx, output, binding)
        print(json.dumps({'state': 'provider_free_validated', 'workers': args.workers,
                          **old.label_gate(plan, states, pending)}))
        return 0
    return collect(plan, ctx, output, binding, args.route_root, execute_native=args.execute_native,
                   headroom=args.owner_global_headroom_verified, route_confirmed=args.owner_current_route_verified, limit=args.limit)


if __name__ == '__main__':
    raise SystemExit(main())
