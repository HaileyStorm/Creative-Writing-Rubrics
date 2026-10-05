"""Named LAMP decode-completion continuation; original v5 evidence stays immutable."""
from collections import Counter
from datetime import datetime, timezone
import argparse
import json
from pathlib import Path
import sys
import threading
import uuid
from urllib.parse import unquote

import importlib.util

HERE = Path(__file__).resolve().parent
SOURCE_SHA = 'd5a146f0ab615994792f422ef7dc01bac5f7dca9e38ac6c0a4a085c5b8ceb698'
SOURCE_JOB_SHA = 'b2699b2a39b2cbd38dc684ed52ecdb87e34ed25a2593eb97101f07f5d7a8bc71'
POLICY = 'matched_lamp_saved_decode_completion_continuation_v1'
INCOMPLETE_PREFIX_POLICY = 'matched_lamp_reserved_ambiguous_prefix_no_resend_v1'
PROGRAM = Path(r'C:\Users\Haile\Documents\cwr-resume-control-20260919-r1\successor-program-20261004')
SOURCE = PROGRAM / 'lamp-reference/judging-grok-parallel-001'
TARGET = PROGRAM / 'lamp-reference/judging-grok-decode-continuation-001'
SESSIONS = Path(r'C:\Users\Haile\.grok\sessions')
READER = HERE.parent / 'hbq-native-transport-recovery-v1/reconcile_failed_suffix.py'


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


c = load('lamp_decode_original_collector', HERE / 'collector.py')
canonical, digest, require = c.canonical, c.digest, c.require
c.p.checked(HERE / 'collector.py', SOURCE_SHA)


def implementation(reader_sha):
    c.p.checked(READER, reader_sha)
    reader = load('lamp_decode_saved_reader', READER)
    require(callable(getattr(reader, 'saved_completion', None)), 'Pure saved completion reader unavailable')
    return reader


def artifacts(directory):
    return {path.relative_to(directory).as_posix(): {'sha256': digest(path.read_bytes()), 'bytes': path.stat().st_size}
            for path in sorted(directory.rglob('*')) if path.is_file()}


def verify_artifacts(directory, pins):
    require(artifacts(directory) == pins, 'Immutable sample artifact inventory differs')


def session_directory(session, route_root, sessions=SESSIONS):
    require(str(uuid.UUID(session)) == session, 'Own native UUID unavailable')
    matches = [path for path in sessions.glob('*/' + session)
               if Path(unquote(path.parent.name)).parent.resolve() == route_root.resolve()
               and Path(unquote(path.parent.name)).name.startswith('grok-exec-')]
    require(len(matches) == 1, 'Unique own saved session under exact broker root missing')
    return matches[0]


def project(sample, row, manifest, binding, root, subset, validator, reader,
            route_root, *, snapshot=None, commitments=None):
    terminal = json.loads((sample / 'terminal.json').read_bytes())
    require(terminal['state'] == 'ambiguous' and terminal['accepted'] is False and terminal['no_resend'] is True,
            'Only completed saved decode ambiguity is eligible')
    failure = json.loads((sample / 'native-result.json').read_bytes())
    require(failure['state'] == 'ambiguous' and failure['result'] is None
            and failure['failure']['code'] == 'validation_tool_policy_attestation'
            and not (sample / 'native-envelope.json').exists(), 'Native failure outside named decode policy')
    started = json.loads((sample / 'attempt-started.json').read_bytes())
    identity = json.loads((sample / 'native-identity.json').read_bytes())
    require(json.loads((sample / 'condition.json').read_bytes()) == row
            and identity['logical_sample_id'] == started['logical_sample_id'] == terminal['logical_sample_id'] == row['logical_sample_id']
            and started['session_id'] == identity['session_id']
            and started['manifest_sha256'] == terminal['manifest_sha256'] == binding['manifest_sha256']
            and started['job_sha256'] == terminal['job_sha256'] == digest((sample.parent / 'job.json').read_bytes())
            and started['attempt_id'] == terminal['attempt_id'] and started['attempt'] == 1 and started['no_resend'] is True
            and started['prompt_sha256'] == row['prompt_sha256'] and started['schema_sha256'] == row['schema_sha256'],
            'Own source attempt/identity binding differs')
    invocation = json.loads(c.pinned(sample.parent, started['execution_invocation']['path'], started['execution_invocation']))
    require(invocation['job_sha256'] == terminal['job_sha256'] and invocation['workers'] == binding['workers']
            and c.execution_workers(invocation['argv']) == binding['workers']
            and '--owner-global-headroom-verified' in invocation['argv'], 'Own source invocation differs')
    prompt, schema, texts, context = c.inputs(root, manifest, row)
    require((sample / 'prompt.txt').read_bytes() == prompt and (sample / 'schema.json').read_bytes() == schema
            and (sample / 'task-context.json').read_bytes() == context.encode()
            and all((sample / 'sources' / (key + '.txt')).read_bytes() == text.encode() for key, text in texts.items()),
            'Exact frozen rendered source/context differs')
    native_root = session_directory(identity['session_id'], route_root) if snapshot is None else Path(commitments['summary']['source_locator']).parent
    answer, native, reads = reader.saved_completion(sample, prompt, native_root, started, binding,
                                                   snapshot=snapshot, commitments=commitments, profile=reader.LAMP_POLICY)
    require(subset.matches_schema(answer, json.loads(schema)), 'Saved final violates frozen output schema')
    if row['arm'] == 'hbq':
        require([value['question_id'] for value in answer['verdicts']] == row['question_ids'], 'Saved final question order differs')
    acceptance = c.admission(root, row, manifest, answer, schema, texts, context, subset, validator)
    effective = {**terminal, 'state': 'accepted' if acceptance['accepted'] else 'semantic_rejected',
                 'accepted': acceptance['accepted'], 'abstention': acceptance['abstention'],
                 'native_thread_id': identity['session_id'], 'admission_basis': POLICY,
                 'original_terminal_state': terminal['state'], 'strict_v5_satisfied': False}
    pins = {name: {'source_locator': str(reads.paths[name]), 'snapshot': name, 'sha256': digest(raw), 'bytes': len(raw)}
            for name, raw in sorted(reads.raws.items())}
    receipt = {'policy': POLICY, 'source_sample_local_only': str(sample.resolve()),
               'source_job_sha256': terminal['job_sha256'], 'request_sha256': row['request_sha256'],
               'source_artifacts': artifacts(sample), 'effective_terminal': effective,
               'response': answer, 'acceptance': acceptance, 'native': native, 'history_commitments': pins,
               'provider_calls_made': 0, 'original_native_envelope_reconstructed': False,
               'physical_contact_cardinality_proven': False}
    return receipt, reads


def prefix(manifest, root, tools, receipts, subset, validator, reader, route_root, *, allow_incomplete=False):
    require(SOURCE.resolve() == (root.parent / 'judging-grok-parallel-001').resolve(), 'Exact retained prefix root differs')
    c.p.checked(SOURCE / 'job.json', SOURCE_JOB_SHA)
    binding = c.verify_job_binding(SOURCE, manifest, root, c.MANIFEST_SHA, 'grok', tools)
    rows = [row for row in manifest['requests'] if row['endpoint'] == 'grok']
    occupied = {path.name for path in SOURCE.iterdir() if path.is_dir()}
    require(occupied == {c.sample_path(SOURCE, row).name for row in rows[:5]}, 'Retained source must contain exact five started slots')
    terminals = list(SOURCE.glob('dispatch-terminal-*.json'))
    require(len(terminals) == 1, 'Unique stopped source dispatch terminal missing')
    dispatch = json.loads(terminals[0].read_bytes())
    require(dispatch['stopped'] is True and dispatch['inflight_at_terminal'] == 0
            and dispatch['settled_this_execution'] == 5 and dispatch['states'] == {'accepted': 1, 'ambiguous': 4},
            'Source prefix is not stopped and drained')
    reserved_ids = []
    for row in rows[:5]:
        sample = c.sample_path(SOURCE, row)
        identity = json.loads((sample / 'native-identity.json').read_bytes())
        started = json.loads((sample / 'attempt-started.json').read_bytes())
        require(identity['logical_sample_id'] == started['logical_sample_id'] == row['logical_sample_id']
                and identity['session_id'] == started['session_id']
                and str(uuid.UUID(identity['session_id'])) == identity['session_id'], 'Imported own native identity differs')
        reserved_ids.append(identity['session_id'])
    require(len(set(reserved_ids)) == 5, 'Duplicate reserved source native UUID')
    entries, snapshots, identities = [], {}, set()
    for row in rows[:5]:
        sample = c.sample_path(SOURCE, row)
        terminal, _ = c.replay(sample, row, manifest, binding, root, receipts, subset, validator)
        if terminal['state'] in c.SETTLED:
            require(row['endpoint_ordinal'] == 3 and terminal['state'] == 'accepted', 'Exact source strict admission differs')
            entry = {'policy': 'original_strict_v5', 'source_sample_local_only': str(sample.resolve()),
                     'source_artifacts': artifacts(sample), 'effective_terminal': {**terminal, 'admission_basis': 'original_strict_v5'}}
        else:
            try:
                entry, reads = project(sample, row, manifest, binding, root, subset, validator, reader, route_root)
                snapshots[str(row['endpoint_ordinal'])] = reads.raws
            except ValueError as error:
                require(allow_incomplete and row['endpoint_ordinal'] == 5
                        and str(error) == 'Saved stream lacks exact completed assistant response',
                        'Source projection is outside the named incomplete-prefix policy')
                native_root = session_directory(reserved_ids[4], route_root)
                prompt_history = native_root.parent / 'prompt_history.jsonl'
                entry = {'policy': INCOMPLETE_PREFIX_POLICY, 'source_sample_local_only': str(sample.resolve()),
                         'source_artifacts': artifacts(sample), 'projection_error': str(error),
                         'saved_session_root_local_only': str(native_root.resolve()),
                         'saved_history_artifacts': artifacts(native_root),
                         'saved_prompt_history': {'path': str(prompt_history.resolve()),
                             'sha256': digest(prompt_history.read_bytes()), 'bytes': prompt_history.stat().st_size},
                         'effective_terminal': {**terminal, 'native_thread_id': reserved_ids[4],
                             'admission_basis': INCOMPLETE_PREFIX_POLICY, 'strict_v5_satisfied': False}}
        native_id = entry['effective_terminal']['native_thread_id']
        require(native_id == reserved_ids[row['endpoint_ordinal'] - 1], 'Imported projection changes own native identity')
        require(native_id not in identities, 'Duplicate imported own native UUID'); identities.add(native_id)
        entries.append(entry)
    return {'policy': POLICY, 'source_root_local_only': str(SOURCE.resolve()), 'source_job_sha256': SOURCE_JOB_SHA,
            'source_dispatch_sha256': digest(terminals[0].read_bytes()), 'reserved_through': 5,
            'strict_admissions': 1, 'projected_admissions': len(snapshots), 'native_ids': reserved_ids,
            'allow_incomplete_prefix': allow_incomplete,
            'unresolved_source_observations': [5] if any(e['policy'] == INCOMPLETE_PREFIX_POLICY for e in entries) else [],
            'human_release_eligible': False, 'entries': entries}, snapshots


def job_binding(manifest, root, tools, route, workers, collector_sha, reader_sha, imported):
    binding = c.job_binding(manifest, root, c.MANIFEST_SHA, 'grok', tools, route, SOURCE_SHA, workers)
    binding.update(policy=POLICY, collector_sha256=collector_sha, saved_completion_reader_sha256=reader_sha,
                   saved_completion_profile=implementation(reader_sha).LAMP_POLICY,
                   retained_lamp_collector_sha256=SOURCE_SHA, imported_prefix_sha256=digest(canonical(imported)),
                   source_job_sha256=SOURCE_JOB_SHA, reserved_through=5,
                   allow_incomplete_prefix=imported['allow_incomplete_prefix'],
                   unresolved_source_observations=imported['unresolved_source_observations'],
                   human_release_eligible=False,
                   strict_v5_policy_preserved=True, completion_promotion_policy=POLICY)
    return binding


def receipt_path(output, row):
    return output / ('decode-admission-' + c.sample_path(output, row).name + '.json')


def persist_projection(output, row, receipt, reads):
    snapshot = output / ('decode-snapshot-' + c.sample_path(output, row).name)
    snapshot.mkdir(exist_ok=False)
    for name, raw in reads.raws.items(): c.write_bytes(snapshot / name, raw)
    c.record(receipt_path(output, row), receipt)


def effective_replay(sample, row, manifest, binding, root, receipts, subset, validator,
                     *, output, reader, route_root, imported):
    if row['endpoint_ordinal'] <= 5:
        entry = imported['entries'][row['endpoint_ordinal'] - 1]
        require(Path(entry['source_sample_local_only']).resolve() == c.sample_path(SOURCE, row).resolve(), 'Imported prefix identity differs')
        sample = Path(entry['source_sample_local_only']); verify_artifacts(sample, entry['source_artifacts'])
        source_binding = json.loads((SOURCE / 'job.json').read_bytes())
        c.p.checked(SOURCE / 'job.json', SOURCE_JOB_SHA)
        if entry['policy'] == 'original_strict_v5':
            terminal, answer = c.replay(sample, row, manifest, source_binding, root, receipts, subset, validator)
            require({**terminal, 'admission_basis': 'original_strict_v5'} == entry['effective_terminal'], 'Strict imported terminal differs')
            return entry['effective_terminal'], answer
        if entry['policy'] == INCOMPLETE_PREFIX_POLICY:
            require(row['endpoint_ordinal'] == 5 and imported['allow_incomplete_prefix'] is True
                    and imported['unresolved_source_observations'] == [5], 'Unresolved source reservation differs')
            terminal, answer = c.replay(sample, row, manifest, source_binding, root, receipts, subset, validator)
            identity = json.loads((sample / 'native-identity.json').read_bytes())['session_id']
            require(terminal['state'] == 'ambiguous' and answer is None and entry['effective_terminal'] == {
                **terminal, 'native_thread_id': identity, 'admission_basis': INCOMPLETE_PREFIX_POLICY, 'strict_v5_satisfied': False},
                'Unresolved source cannot be relabeled as settled')
            verify_artifacts(Path(entry['saved_session_root_local_only']), entry['saved_history_artifacts'])
            meta = entry['saved_prompt_history']; c.p.checked(Path(meta['path']), meta['sha256'], meta['bytes'])
            return entry['effective_terminal'], None
        snapshot = output / 'prefix-snapshots' / str(row['endpoint_ordinal'])
        receipt, _ = project(sample, row, manifest, source_binding, root, subset, validator, reader, route_root,
                             snapshot=snapshot, commitments=entry['history_commitments'])
        require(receipt == entry, 'Imported projection replay differs')
    elif receipt_path(output, row).exists():
        entry = json.loads(receipt_path(output, row).read_bytes()); verify_artifacts(sample, entry['source_artifacts'])
        receipt, _ = project(sample, row, manifest, binding, root, subset, validator, reader, route_root,
                             snapshot=output / ('decode-snapshot-' + sample.name), commitments=entry['history_commitments'])
        require(receipt == entry, 'Prospective projection replay differs')
    else:
        terminal, answer = c.replay(sample, row, manifest, binding, root, receipts, subset, validator)
        return {**terminal, 'admission_basis': 'original_strict_v5'}, answer
    return entry['effective_terminal'], entry['response'] if entry['acceptance']['accepted'] else None


def effective_inventory(manifest, binding, root, output, receipts, subset, validator,
                        *, reader, route_root, imported, prepared=False):
    rows = [row for row in manifest['requests'] if row['endpoint'] == 'grok']
    require(len(rows) == 8904 and [row['endpoint_ordinal'] for row in rows] == list(range(1, 8905)), 'Full ordered Grok denominator differs')
    pending, states, identities = [], [], set()
    for row in rows:
        sample = c.sample_path(output, row)
        if row['endpoint_ordinal'] <= 5 and prepared:
            require(not sample.exists(), 'Imported prefix cannot be redispatched')
            terminal = imported['entries'][row['endpoint_ordinal'] - 1]['effective_terminal']
        elif row['endpoint_ordinal'] > 5 and not sample.exists():
            pending.append(row); continue
        else:
            require(row['endpoint_ordinal'] > 5 or not sample.exists(), 'Imported prefix cannot be redispatched')
            terminal, _ = effective_replay(sample, row, manifest, binding, root, receipts, subset, validator,
                                           output=output, reader=reader, route_root=route_root, imported=imported)
        states.append(terminal['state'])
        identity = terminal.get('native_thread_id')
        if identity:
            require(identity not in identities, 'Duplicate effective own native UUID'); identities.add(identity)
    require(len(pending) + len(states) == 8904, 'Effective inventory denominator differs')
    return pending, states, identities


class LocalFailureFlag:
    def __init__(self, parent): self.parent, self.failure = parent, threading.Event()
    def is_set(self): return self.parent.is_set() or self.failure.is_set()
    def set(self): self.failure.set()


class SampleCommit:
    def __init__(self, parent):
        self.lock, self.invocation = parent.lock, parent.invocation
        self.stop, self.reserve_identity = LocalFailureFlag(parent.stop), parent.reserve_identity


def collect_one(row, manifest, binding, root, output, subset, validator, receipts, broker, commit, reader, route_root):
    require(row['endpoint'] == 'grok' and row['endpoint_ordinal'] > 5, 'Imported prefix cannot contact provider')
    local = SampleCommit(commit)
    try:
        state = c.collect_one(row, manifest, binding, root, output, subset, validator, receipts, broker=broker, commit=local)
        if state in c.SETTLED: return state
        receipt, reads = project(c.sample_path(output, row), row, manifest, binding, root, subset, validator, reader, route_root)
        commit.reserve_identity(receipt['effective_terminal']['native_thread_id'])
        persist_projection(output, row, receipt, reads)
        return receipt['effective_terminal']['state']
    except BaseException:
        commit.stop.set()
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    for name in ('manifest', 'tools-root', 'route-root', 'results-dir'): parser.add_argument('--' + name, type=Path, required=True)
    for name in ('manifest-sha256', 'collector-sha256', 'reader-sha256', 'route-sha256'): parser.add_argument('--' + name, required=True)
    parser.add_argument('--workers', type=int, required=True)
    parser.add_argument('--owner-global-headroom-verified', action='store_true')
    parser.add_argument('--execute-native', action='store_true')
    parser.add_argument('--validate-only', action='store_true')
    parser.add_argument('--allow-incomplete-prefix', action='store_true')
    parser.add_argument('--limit', type=int)
    args = parser.parse_args()
    require(args.execute_native != args.validate_only, 'Choose provider-free --validate-only or explicit --execute-native')
    c.allocation(args.workers, sys.argv, args.owner_global_headroom_verified, args.execute_native)
    require(args.limit is None or args.limit > 0, 'Limit invalid')
    c.p.checked(Path(__file__), args.collector_sha256)
    reader = implementation(args.reader_sha256)
    manifest, root, subset, validator, receipts = c.load_manifest(args.manifest, args.manifest_sha256, SOURCE_SHA, args.tools_root)
    output = args.results_dir.resolve(); require(output == TARGET.resolve(), 'Fresh versioned LAMP continuation root differs')
    c.output_preflight(output, root)
    require(args.route_root.resolve() == Path(r'C:\Users\Haile\.codex\state\model-work-queue-cwr-placeholder-r31').resolve(), 'Exact broker root differs')
    routes = json.loads((args.route_root / 'routes.json').read_bytes())['routes']
    route = next(item for item in routes if item['name'] == 'grok-build-grok-4.7')
    require(digest(canonical(route).rstrip(b'\n')) == args.route_sha256, 'Exact current route differs')
    if output.exists():
        imported = json.loads((output / 'imported-prefix.json').read_bytes()); snapshots = {}
        require(imported['policy'] == POLICY and imported['source_job_sha256'] == SOURCE_JOB_SHA
                and imported['source_root_local_only'] == str(SOURCE.resolve()) and imported['reserved_through'] == 5
                and len(imported['entries']) == 5, 'Imported prefix provenance differs')
        require(imported['allow_incomplete_prefix'] == args.allow_incomplete_prefix, 'Incomplete-prefix execution policy differs')
    else:
        imported, snapshots = prefix(manifest, root, args.tools_root, receipts, subset, validator, reader, args.route_root,
                                     allow_incomplete=args.allow_incomplete_prefix)
    binding = job_binding(manifest, root, args.tools_root, route, args.workers, args.collector_sha256, args.reader_sha256, imported)
    if output.exists():
        require(json.loads((output / 'job.json').read_bytes()) == binding
                and json.loads((output / 'imported-prefix.json').read_bytes()) == imported
                and (output / 'frozen-manifest.json').read_bytes() == args.manifest.read_bytes(), 'Existing continuation binding differs')
    pending, states, identities = effective_inventory(manifest, binding, root, output, receipts, subset, validator,
                    reader=reader, route_root=args.route_root, imported=imported, prepared=not output.exists())
    if args.validate_only:
        print(json.dumps({'state': 'provider_free_validated', 'policy': POLICY, 'job_binding_sha256': digest(canonical(binding)),
              'planned': 8904, 'study_planned': 17808, 'reserved_through': 5, 'untouched': len(pending),
              'terminal_states': dict(Counter(states)), 'strict_prefix': 1, 'projected_prefix': imported['projected_admissions'],
              'unresolved_source_observations': imported['unresolved_source_observations'], 'provider_calls': 0,
              'human_release_eligible': False, 'human_targets_opened': False, 'native_execution_proven': False})); return 0
    require(all(state in c.SETTLED or index == 4 and args.allow_incomplete_prefix
                and imported['unresolved_source_observations'] == [5] and state == 'ambiguous'
                for index, state in enumerate(states)), 'Unadmitted occupied slot requires owning reconciliation; no resend')
    if (output / 'STOP').exists(): return 3
    if not pending: return 0
    require(c.grok_contact_allowed(route), 'Route expiry/campaign deadline prevents contact')
    from model_work_queue.broker import Broker
    broker = Broker(args.route_root)
    if not output.exists():
        output.mkdir(exist_ok=False); c.record(output / 'job.json', binding)
        c.write_bytes(output / 'frozen-manifest.json', args.manifest.read_bytes()); c.record(output / 'imported-prefix.json', imported)
        for ordinal, files in snapshots.items():
            for name, raw in files.items(): c.write_bytes(output / 'prefix-snapshots' / ordinal / name, raw)
    name = 'execution-invocation-' + str(uuid.uuid4()) + '.json'
    raw = canonical({'argv': sys.argv, 'workers': args.workers, 'job_sha256': digest((output / 'job.json').read_bytes()),
                     'time': datetime.now(timezone.utc).isoformat(), 'owner_global_headroom_confirmation': True})
    c.write_bytes(output / name, raw); invocation = {'path': name, 'sha256': digest(raw), 'bytes': len(raw)}
    commit = c.CommitState(identities, invocation)
    execute = lambda row: collect_one(row, manifest, binding, root, output, subset, validator, receipts, broker, commit, reader, args.route_root)
    try:
        settled = c.dispatch(pending[:args.limit], args.workers, execute, commit, lambda: (output / 'STOP').exists(),
                             lambda row, state: print(json.dumps({'ordinal': row['endpoint_ordinal'], 'state': state}), flush=True))
    except BaseException as error:
        c.record(output / ('dispatch-terminal-' + str(uuid.uuid4()) + '.json'), {'policy': POLICY, 'workers': args.workers,
                 'execution_invocation': invocation, 'stopped': True, 'inflight_at_terminal': 0,
                 'error_class': type(error).__name__, 'automatic_retries': 0, 'human_targets_opened': False})
        raise
    c.record(output / ('dispatch-terminal-' + str(uuid.uuid4()) + '.json'), {'policy': POLICY, 'workers': args.workers,
             'execution_invocation': invocation, 'settled_this_execution': len(settled), 'states': dict(Counter(settled)),
             'stopped': commit.stop.is_set(), 'inflight_at_terminal': 0, 'automatic_retries': 0, 'human_targets_opened': False})
    return 3 if commit.stop.is_set() else 0


if __name__ == '__main__': raise SystemExit(main())
