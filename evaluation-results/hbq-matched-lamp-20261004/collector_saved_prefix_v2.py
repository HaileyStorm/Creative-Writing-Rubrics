"""LAMP v2: frozen 122-slot lineage and qualified own saved completions."""
from collections import Counter
from datetime import datetime, timezone
import argparse
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import uuid
import importlib.util

HERE = Path(__file__).resolve().parent
POLICY = 'matched_lamp_frozen122_saved_representation_continuation_v2'
ORDINARY_POLICY = 'saved_ordinary_exact_or_terminal_200a_qualified_representation_v2'
DECODE_SHA = 'f9bd97b14220e50c174930d0938f540e4f566022be786a4f3a4f24d0b568e30a'
CODE = {
    'decode_reader': ('../hbq-native-transport-recovery-v1/reconcile_failed_suffix.py', 'f285d228607c26cca0009d17626e7d6915f3d715e3b29f02784a25c682f4be68'),
    'generic': ('../hbq-native-transport-recovery-v1/reconcile.py', 'fbedc8e50d08de7dff0547483f26c9fd081a8b4c9e62f0713609ce043e0fb34c'),
    'history': ('../hbq-matched-ttcw-20261004/reconcile_history.py', 'a9e27d3c5da5ff341f0f7172d7dfffd6c139fe8f569b2655e55fbf7279c676ed'),
    'fixed5': ('../hbq-native-transport-recovery-v1/reconcile_lamp_final_stream.py', 'fe04fb5b85b41ba236bdf577deeaf4c8862f4df54bffe00369a57410a64fc055'),
    'fixed120121': ('../hbq-native-transport-recovery-v1/reconcile_lamp_prompt_suffix.py', '015c5a42d892f9fdf2da9e67425312ae6ec3f24d1078c5a83dcd66294622a81b'),
    'source_decode': ('collector_decode.py', DECODE_SHA),
}


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec); sys.modules[name] = module
    spec.loader.exec_module(module); return module


d = load('lamp_saved_v2_retained_decode', HERE / 'collector_decode.py')
c = d.c
canonical, digest, require = c.canonical, c.digest, c.require
PROGRAM, FROZEN = d.PROGRAM, d.PROGRAM / 'lamp-reference/frozen-001'
SOURCE = d.TARGET
TARGET = PROGRAM / 'lamp-reference/judging-grok-saved-prefix-v2-001'
TOOLS = Path(r'C:\Users\Haile\.codex\tools')
ROUTE_ROOT = Path(r'C:\Users\Haile\.codex\state\model-work-queue-cwr-placeholder-r31')
SOURCE_JOB_SHA = '1c32c40d6bfbbe5323823e2a99171ea23eb0667ab812b2add5c61635847c3d9c'
OUTER = PROGRAM / 'lamp-reference/decode-lifecycle/grok-001/terminal.json'
OUTER_SHA = '4b52fa75938756f5805c893298b858808afbd5e956edfcfc2a64d35c2fa77424'
DISPATCH_SHA = 'c2f22e96509e13857cf935b5628255dd454dee1c07d81a330b9b53a8d3a8c7ea'
ADOPTIONS = {
    'fixed5': (PROGRAM / 'lamp-reference/slot5-final-stream-reconciliation-001/reconciliation.json',
               'a754cceb7fd68e56824d082ccf315ca17f85abfe83352dbfba7787e76ef10e96'),
    'fixed120121': (PROGRAM / 'lamp-reference/slots120-121-prompt-suffix-reconciliation-001/reconciliation.json',
                    '8579ec7d8a466c191c9a5206cb938ec21fc395a3ece49b8dadf1b0e5b0094df9'),
}


def implementation(key):
    relative, sha = CODE[key]; path = HERE / relative
    c.p.checked(path, sha); return load('lamp_saved_v2_' + key, path)


def context():
    for key in CODE: c.p.checked(HERE / CODE[key][0], CODE[key][1])
    sys.path.insert(0, str(c.p.REPO / 'src')); sys.path.insert(0, str(TOOLS))
    raw = c.p.checked(FROZEN / 'manifest.json', c.MANIFEST_SHA); manifest = json.loads(raw)
    require(digest(canonical({k: v for k, v in manifest.items() if k != 'manifest_content_sha256'}))
            == manifest['manifest_content_sha256'], 'Frozen manifest content differs')
    c.validate_design(manifest, {'compiled.json': c.pinned(FROZEN, 'compiled.json', manifest['artifacts']['compiled.json'])})
    source = c.source_settings(manifest, FROZEN)
    require(Path(source['external_pins']['tools_root_local_only']).resolve() == TOOLS.resolve(), 'Frozen tools root differs')
    for current, frozen in [(HERE / 'prepare.py', 'implementation/prepare.py'),
            (c.p.REPO / 'src/hbqrs/core.py', 'implementation/core.py'),
            (c.p.REPO / 'src/hbqrs/runner.py', 'implementation/runner.py'),
            (c.p.REPO / 'src/hbqrs/scoring_v2.py', 'implementation/scoring_v2.py'),
            (c.p.REPO / 'src/hbqrs/codex_receipts.py', 'implementation/codex_receipts.py'),
            (TOOLS / 'model_work_queue/broker.py', 'implementation/broker.py'),
            (TOOLS / 'model_work_queue/adapters/grok_exec.py', 'implementation/grok_exec.py')]:
        c.p.checked(current, manifest['artifacts'][frozen]['sha256'])
    c.p.checked(TOOLS / 'adaptive_settings/account_probe.py', source['external_pins']['account_probe_sha256'])
    modules = []
    for name in ('schema_subset', 'validate_response', 'codex_receipts'):
        relative = 'implementation/' + name + '.py'
        c.pinned(FROZEN, relative, manifest['artifacts'][relative])
        modules.append(load('lamp_saved_v2_frozen_' + name, FROZEN / relative))
    return manifest, *modules


def qualified_prompt(prompt, updates, histories, session):
    require([row['params']['update']['sessionUpdate'] for row in updates] ==
            ['user_message_chunk', 'agent_thought_chunk', 'agent_message_chunk', 'turn_completed'],
            'Ordinary saved completion must have exactly four original records')
    saved = updates[0]['params']['update']['content']['text'].encode('utf-8')
    require(updates[0]['params']['sessionId'] == session and len(histories) == 1
            and histories[0]['session_id'] == session and histories[0]['prompt'].encode('utf-8') == saved,
            'Own native user and prompt history differ')
    exact = saved == prompt
    require(exact or prompt.endswith(b' \n') and saved == prompt[:-2],
            'Only exact prompt or exact terminal 200a omission is eligible')
    return saved, 'exact' if exact else 'terminal_200a_omission'


def saved_completion(sample, prompt, session_root, started, job, *, snapshot=None, commitments=None, profile=POLICY):
    require(profile == POLICY and isinstance(prompt, bytes), 'Named v2 saved recipient differs')
    generic = implementation('generic')
    class Reads(generic.ReadSet):
        def raw(self, name, path):
            require(self.snapshot is None or name in self.expected, 'Frozen saved representation commitment missing')
            return super().raw(name, path)
        def json(self, name, path): return json.loads(self.raw(name, path))
        def lines(self, name, path): return [json.loads(row) for row in self.raw(name, path).splitlines()]
    reads = Reads(snapshot, commitments)
    updates = reads.lines('updates', session_root / 'updates.jsonl')
    if [row['params']['update']['sessionUpdate'] for row in updates] != [
            'user_message_chunk', 'agent_thought_chunk', 'agent_message_chunk', 'turn_completed']:
        decode = implementation('decode_reader')
        return decode.saved_completion(sample, prompt, session_root, started, job,
                                       snapshot=snapshot, commitments=commitments, profile=decode.LAMP_POLICY)
    session = json.loads((sample / 'native-identity.json').read_bytes())['session_id']
    histories = reads.lines('prompt_history', session_root.parent / 'prompt_history.jsonl')
    saved, projection = qualified_prompt(prompt, updates, histories, session)
    summary = reads.json('summary', session_root / 'summary.json')
    try: generic.grok_projection(updates, summary, session, saved.decode('utf-8'))
    except ValueError as error:
        require(str(error) == 'No demonstrated Grok DNS recovery', 'Ordinary native field/lifecycle validation failed')
    else: raise ValueError('Ordinary completion cannot contain recovery diagnostics')
    history = implementation('history')
    response, native = history.history_response(reads, session_root, {'session_id': session}, started,
            {'model': job['runtime']['model'], 'route': job['route'], 'cutoff': job['campaign_deadline']}, saved)
    require(native['prompt_projection'] == 'exact', 'Saved representation itself is not exact')
    reads.raws['saved_prompt_projection'], reads.paths['saved_prompt_projection'] = saved, 'derived:' + ORDINARY_POLICY
    if snapshot is not None:
        pin = reads.expected.get('saved_prompt_projection')
        require(pin is not None and digest(saved) == pin['sha256'] and len(saved) == pin['bytes']
                and (snapshot / pin['snapshot']).read_bytes() == saved, 'Saved prompt projection snapshot differs')
    native['prompt_projection'] = 'exact_saved_representation_not_attested_original_outbound'
    proof = {'policy': ORDINARY_POLICY, 'saved_history': native, 'history_reader_sha256': CODE['history'][1],
             'qualification': {'projection': projection, 'omitted_terminal_bytes_hex': '' if projection == 'exact' else '200a',
                 'original_frozen_prompt_sha256': digest(prompt), 'original_frozen_prompt_bytes': len(prompt),
                 'saved_prompt_sha256': digest(saved), 'saved_prompt_bytes': len(saved),
                 'all_preceding_bytes_exact': True, 'native_user_equals_prompt_history': True,
                 'exact_original_outbound_bytes_proven': False, 'original_strict_v5_admission_satisfied': False},
             'original_native_envelope_reconstructed': False, 'physical_contact_cardinality_proven': False}
    return json.loads(response), proof, reads


def project(sample, row, manifest, binding, subset, validator, route_root, *, snapshot=None, commitments=None):
    receipt, reads = d.project(sample, row, manifest, binding, FROZEN, subset, validator,
            SimpleNamespace(saved_completion=saved_completion, LAMP_POLICY=POLICY), route_root,
            snapshot=snapshot, commitments=commitments)
    receipt.update(policy=POLICY, original_strict_v5_admission_satisfied=False, exact_original_outbound_bytes_proven=False,
                   same_original_observation_only=True, new_votes=0)
    receipt['effective_terminal'].update(admission_basis=POLICY, exact_original_outbound_bytes_proven=False)
    return receipt, reads


def build_prefix(manifest, subset, validator, receipts, *, adopt_fixed_slot5):
    c.p.checked(OUTER, OUTER_SHA); outer = json.loads(OUTER.read_bytes())
    terminals = list(SOURCE.glob('dispatch-terminal-*.json'))
    require(len(terminals) == 1, 'Unique original dispatch terminal missing')
    c.p.checked(terminals[0], DISPATCH_SHA); dispatch = json.loads(terminals[0].read_bytes())
    require(outer['exit_code'] == 3 and outer['no_resend'] is True and dispatch['stopped'] is True
            and dispatch['inflight_at_terminal'] == 0 and dispatch['workers'] == 4, 'Original source is not stopped/drained')
    c.p.checked(SOURCE / 'job.json', SOURCE_JOB_SHA)
    job = json.loads((SOURCE / 'job.json').read_bytes())
    imported = json.loads((SOURCE / 'imported-prefix.json').read_bytes())
    require(job == d.job_binding(manifest, FROZEN, TOOLS, job['route'], job['workers'], DECODE_SHA,
                               CODE['decode_reader'][1], imported)
            and (SOURCE / 'frozen-manifest.json').read_bytes() == (FROZEN / 'manifest.json').read_bytes(),
            'Original continuation job/freeze differs')
    rows = [row for row in manifest['requests'] if row['endpoint'] == 'grok']
    require({path.name for path in SOURCE.iterdir() if path.is_dir() and path.name[:4].isdigit()}
            == {c.sample_path(SOURCE, row).name for row in rows[5:122]}, 'Source must contain exactly untouched-prefix slots 6..122')
    overlays = {}
    suffix_path, suffix_sha = ADOPTIONS['fixed120121']
    fixed = implementation('fixed120121').verify(suffix_path, suffix_sha)
    for entry in fixed['observations']:
        overlays[entry['request_sha256']] = (entry, {'path': str(suffix_path), 'sha256': suffix_sha, 'policy': fixed['policy']})
    if adopt_fixed_slot5:
        path, sha = ADOPTIONS['fixed5']; entry = implementation('fixed5').verify(path, sha)
        overlays[entry['request_sha256']] = (entry, {'path': str(path), 'sha256': sha, 'policy': entry['policy']})
    entries, native_ids = [], set(); decode = d.implementation(CODE['decode_reader'][1])
    for row in rows[:122]:
        sample = c.sample_path(d.SOURCE if row['endpoint_ordinal'] <= 5 else SOURCE, row)
        identity = json.loads((sample / 'native-identity.json').read_bytes())
        started = json.loads((sample / 'attempt-started.json').read_bytes())
        require(identity['logical_sample_id'] == started['logical_sample_id'] == row['logical_sample_id']
                and identity['session_id'] == started['session_id']
                and str(uuid.UUID(identity['session_id'])) == identity['session_id']
                and identity['session_id'] not in native_ids, 'Duplicate/foreign reserved native identity')
        native_ids.add(identity['session_id'])
        if row['request_sha256'] in overlays:
            adopted, adoption = overlays[row['request_sha256']]
            require(adopted['source_sample_local_only'] == str(sample.resolve())
                    and adopted['source_job_sha256'] == (d.SOURCE_JOB_SHA if row['endpoint_ordinal'] <= 5 else SOURCE_JOB_SHA)
                    and adopted['source_artifacts'] == d.artifacts(sample)
                    and adopted['effective_terminal']['native_thread_id'] == identity['session_id'],
                    'Fixed receipt does not bind the same original observation')
            terminal = adopted['effective_terminal']; source_policy = adopted['policy']
        else:
            terminal, _ = d.effective_replay(c.sample_path(SOURCE, row), row, manifest, job, FROZEN, receipts, subset, validator,
                    output=SOURCE, reader=decode, route_root=ROUTE_ROOT, imported=imported)
            source_policy, adoption = terminal['admission_basis'], None
        require(terminal.get('native_thread_id') == identity['session_id'], 'Effective prefix changes own native identity')
        entries.append({'ordinal': row['endpoint_ordinal'], 'request_sha256': row['request_sha256'],
            'logical_sample_id': row['logical_sample_id'], 'source_sample_local_only': str(sample.resolve()),
            'source_job_sha256': started['job_sha256'], 'source_artifacts': d.artifacts(sample),
            'effective_terminal': terminal, 'source_admission_policy': source_policy, 'adoption': adoption})
        if source_policy != 'original_strict_v5':
            entries[-1].update(original_strict_v5_admission_satisfied=False, exact_original_outbound_bytes_proven=False,
                               same_original_observation_only=True, new_votes=0)
    require(len(entries) == len(native_ids) == 122, 'Complete once-only reserved prefix differs')
    return {'schema_version': 2, 'policy': POLICY, 'implementation_sha256': digest(Path(__file__).read_bytes()),
        'manifest_sha256': c.MANIFEST_SHA, 'reserved_through': 122, 'planned': 8904, 'study_planned': 17808,
        'untouched': 8782, 'adopt_fixed_slot5': adopt_fixed_slot5, 'entries': entries,
        'states': dict(Counter(entry['effective_terminal']['state'] for entry in entries)),
        'native_ids': sorted(native_ids), 'unresolved_source_observations': [entry['ordinal'] for entry in entries
            if entry['effective_terminal']['state'] not in c.SETTLED],
        'lineage_pins': {str(path): digest(path.read_bytes()) for path in [OUTER, terminals[0], SOURCE / 'job.json',
            SOURCE / 'imported-prefix.json', d.SOURCE / 'job.json', *(HERE / value[0] for value in CODE.values())]},
        'provider_calls': 0, 'new_votes': 0, 'human_targets_opened': False, 'human_release_eligible': False,
        'physical_contact_cardinality_proven': False}


def verify_prefix(path, sha, ctx):
    saved = json.loads(c.p.checked(path, sha))
    c.p.checked(path.parent / Path(__file__).name, saved['implementation_sha256'])
    require(saved == build_prefix(*ctx, adopt_fixed_slot5=saved['adopt_fixed_slot5']), 'Frozen prefix/source/receipt replay differs')
    return saved


def inventory(manifest, binding, output, subset, validator, receipts, prefix, route_root):
    rows = [row for row in manifest['requests'] if row['endpoint'] == 'grok']
    require(len(rows) == 8904 and [row['endpoint_ordinal'] for row in rows] == list(range(1, 8905)), 'Full ordered denominator differs')
    entries = prefix['entries']
    require(len(entries) == 122 and [entry['ordinal'] for entry in entries] == list(range(1, 123)), 'Reserved prefix geometry differs')
    pending, states, ids = [], [], set()
    for row in rows:
        sample = c.sample_path(output, row)
        if row['endpoint_ordinal'] <= 122:
            require(not sample.exists(), 'Reserved prefix cannot be redispatched')
            entry = entries[row['endpoint_ordinal'] - 1]
            require(entry['request_sha256'] == row['request_sha256'] and entry['logical_sample_id'] == row['logical_sample_id'],
                    'Reserved logical/request identity differs')
            terminal = entry['effective_terminal']
        elif not sample.exists(): pending.append(row); continue
        elif d.receipt_path(output, row).exists():
            saved = json.loads(d.receipt_path(output, row).read_bytes()); d.verify_artifacts(sample, saved['source_artifacts'])
            actual, _ = project(sample, row, manifest, binding, subset, validator, route_root,
                    snapshot=output / ('decode-snapshot-' + sample.name), commitments=saved['history_commitments'])
            require(saved == actual, 'Qualified saved completion replay differs'); terminal = saved['effective_terminal']
        else: terminal, _ = c.replay(sample, row, manifest, binding, FROZEN, receipts, subset, validator)
        states.append(terminal['state']); identity = terminal.get('native_thread_id')
        if identity:
            require(identity not in ids, 'Duplicate effective native identity'); ids.add(identity)
    require(len(pending) + len(states) == 8904, 'Once-only full denominator differs')
    return pending, states, ids


def collect_one(row, manifest, binding, output, subset, validator, receipts, broker, commit, route_root):
    require(row['endpoint'] == 'grok' and row['endpoint_ordinal'] > 122, 'Reserved prefix cannot contact provider')
    local = d.SampleCommit(commit)
    try:
        state = c.collect_one(row, manifest, binding, FROZEN, output, subset, validator, receipts, broker=broker, commit=local)
        if state in c.SETTLED: return state
        receipt, reads = project(c.sample_path(output, row), row, manifest, binding, subset, validator, route_root)
        commit.reserve_identity(receipt['effective_terminal']['native_thread_id'])
        d.persist_projection(output, row, receipt, reads)
        return receipt['effective_terminal']['state']
    except BaseException:
        commit.stop.set(); raise


def job_binding(manifest, route, workers, prefix_sha, collector_sha):
    binding = c.job_binding(manifest, FROZEN, c.MANIFEST_SHA, 'grok', TOOLS, route, d.SOURCE_SHA, workers)
    binding.update(policy=POLICY, collector_sha256=collector_sha, retained_lamp_collector_sha256=d.SOURCE_SHA,
        prefix_sha256=prefix_sha, reserved_through=122, saved_completion_policy=ORDINARY_POLICY,
        saved_decode_reader_sha256=CODE['decode_reader'][1], implementation_pins={key: value[1] for key, value in CODE.items()},
        human_release_eligible=False, original_strict_v5_policy_preserved=True)
    return binding


def output_preflight(output):
    c.output_preflight(output.resolve(), FROZEN)
    require(all(not output.resolve().is_relative_to(source.resolve()) and not source.resolve().is_relative_to(output.resolve())
                for source in (SOURCE, d.SOURCE, *(path.parent for path, _ in ADOPTIONS.values()))), 'New output overlaps retained evidence')


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    sub = parser.add_subparsers(dest='mode', required=True)
    prep = sub.add_parser('prepare', allow_abbrev=False)
    prep.add_argument('--output-root', type=Path, required=True); prep.add_argument('--dry-run', action='store_true')
    prep.add_argument('--adopt-fixed-slot5', action='store_true')
    run = sub.add_parser('collect', allow_abbrev=False)
    for name in ('prefix-root', 'results-dir', 'route-root'): run.add_argument('--' + name, type=Path, required=True)
    for name in ('prefix-sha256', 'collector-sha256', 'route-sha256'): run.add_argument('--' + name, required=True)
    run.add_argument('--workers', type=int, required=True); run.add_argument('--owner-global-headroom-verified', action='store_true')
    run.add_argument('--validate-only', action='store_true'); run.add_argument('--execute-native', action='store_true')
    run.add_argument('--limit', type=int)
    args = parser.parse_args(); ctx = context(); manifest, subset, validator, receipts = ctx
    if args.mode == 'prepare':
        output = args.output_root.resolve(); output_preflight(output); require(not output.exists(), 'Prefix output must be fresh')
        prefix = build_prefix(*ctx, adopt_fixed_slot5=args.adopt_fixed_slot5); raw = canonical(prefix)
        if not args.dry_run:
            output.mkdir(parents=True, exist_ok=False); c.write_bytes(output / 'prefix.json', raw)
            c.write_bytes(output / Path(__file__).name, Path(__file__).read_bytes())
        print(json.dumps({'state': 'provider_free_prefix_validated', 'prefix_sha256': digest(raw), 'reserved': 122,
            'untouched': 8782, 'planned': 8904, 'study_planned': 17808, 'states': prefix['states'],
            'unresolved_source_observations': prefix['unresolved_source_observations'], 'provider_calls': 0,
            'new_votes': 0, 'human_release_eligible': False, 'output_written': not args.dry_run})); return 0
    require(args.validate_only != args.execute_native, 'Choose validate-only or explicit native execution')
    c.allocation(args.workers, sys.argv, args.owner_global_headroom_verified, args.execute_native)
    require(args.limit is None or args.limit > 0, 'Limit invalid')
    c.p.checked(Path(__file__), args.collector_sha256)
    prefix = verify_prefix(args.prefix_root / 'prefix.json', args.prefix_sha256, ctx)
    output = args.results_dir.resolve(); output_preflight(output)
    require(output == TARGET.resolve() and args.route_root.resolve() == ROUTE_ROOT.resolve(), 'Named output/broker root differs')
    require(not output.is_relative_to(args.prefix_root.resolve()) and not args.prefix_root.resolve().is_relative_to(output), 'Output overlaps frozen prefix')
    routes = json.loads((args.route_root / 'routes.json').read_bytes())['routes']
    matches = [route for route in routes if route['name'] == 'grok-build-grok-4.7']; require(len(matches) == 1, 'Unique current route missing')
    route = matches[0]; require(digest(canonical(route).rstrip(b'\n')) == args.route_sha256, 'Exact current route differs')
    binding = job_binding(manifest, route, args.workers, args.prefix_sha256, args.collector_sha256)
    if output.exists():
        require(json.loads((output / 'job.json').read_bytes()) == binding
                and (output / 'frozen-prefix.json').read_bytes() == (args.prefix_root / 'prefix.json').read_bytes()
                and (output / 'frozen-manifest.json').read_bytes() == (FROZEN / 'manifest.json').read_bytes(), 'Existing v2 invocation differs')
    pending, states, ids = inventory(manifest, binding, output, subset, validator, receipts, prefix, args.route_root)
    if args.validate_only:
        print(json.dumps({'state': 'provider_free_validated', 'job_binding_sha256': digest(canonical(binding)), 'reserved': 122,
            'untouched': len(pending), 'states': dict(Counter(states)), 'planned': 8904, 'study_planned': 17808,
            'provider_calls': 0, 'human_release_eligible': False})); return 0
    require(all(state in c.SETTLED for state in states), 'Unadmitted occupied observation requires reconciliation; no resend')
    if (output / 'STOP').exists(): return 3
    if not pending: return 0
    require(c.grok_contact_allowed(route), 'Route expiry/campaign deadline prevents contact')
    from model_work_queue.broker import Broker
    broker = Broker(args.route_root)
    if not output.exists():
        output.mkdir(exist_ok=False); c.record(output / 'job.json', binding)
        c.write_bytes(output / 'frozen-prefix.json', (args.prefix_root / 'prefix.json').read_bytes())
        c.write_bytes(output / 'frozen-manifest.json', (FROZEN / 'manifest.json').read_bytes())
    name = 'execution-invocation-' + str(uuid.uuid4()) + '.json'
    raw = canonical({'argv': sys.argv, 'workers': args.workers, 'job_sha256': digest((output / 'job.json').read_bytes()),
                     'time': datetime.now(timezone.utc).isoformat(), 'owner_global_headroom_confirmation': True})
    c.write_bytes(output / name, raw); invocation = {'path': name, 'sha256': digest(raw), 'bytes': len(raw)}
    commit = c.CommitState(ids, invocation)
    execute = lambda row: collect_one(row, manifest, binding, output, subset, validator, receipts, broker, commit, args.route_root)
    try:
        settled = c.dispatch(pending[:args.limit], args.workers, execute, commit, lambda: (output / 'STOP').exists(),
                lambda row, state: print(json.dumps({'ordinal': row['endpoint_ordinal'], 'state': state}), flush=True))
    except BaseException as error:
        c.record(output / ('dispatch-terminal-' + str(uuid.uuid4()) + '.json'), {'policy': POLICY, 'workers': args.workers,
            'execution_invocation': invocation, 'stopped': True, 'inflight_at_terminal': 0,
            'error_class': type(error).__name__, 'automatic_retries': 0, 'human_release_eligible': False}); raise
    c.record(output / ('dispatch-terminal-' + str(uuid.uuid4()) + '.json'), {'policy': POLICY, 'workers': args.workers,
        'execution_invocation': invocation, 'settled_this_execution': len(settled), 'states': dict(Counter(settled)),
        'stopped': commit.stop.is_set(), 'inflight_at_terminal': 0, 'automatic_retries': 0, 'human_release_eligible': False})
    return 3 if commit.stop.is_set() else 0


if __name__ == '__main__': raise SystemExit(main())
