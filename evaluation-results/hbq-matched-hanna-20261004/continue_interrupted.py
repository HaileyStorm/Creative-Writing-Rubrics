"""Provider-free reservation and untouched-suffix plans for the exact HANNA interruption."""
from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
POLICY = 'matched_hanna_interrupted_untouched_suffix_v1'
AUDIT_SHA = '497134c4243c31330668519394b3785a88424c7b74fd2cdab20213ecd2ce78f5'
MANIFEST_SHA = 'd4f8c8c7847b7715d97ccb9d0a46fdc0651e79777f17309019fc2e75ad02bedc'
COLLECTOR_SHA = '327bfa1deeed417f7a558914d650297fda3c0999adccd2c2a8b0a661b182cf83'
RECONCILER_SHA = 'eb7a5232e92daf00573e7bcc1dc341bbbcf083fb1eae6fe2da302e9b457185bb'
JOBS = {'sol': 'ae211908de20c69438d29a726b6f6cc9e64e6af232e5aa2d3ed06ba520457927',
        'grok': 'ed14bc805e5a6a99ab19584de2e26566cc8058b70ab7a9a26627ff53ca18c94c'}
THROUGH = {'sol': 9, 'grok': 5}
STRICT = {'sol': set(range(1, 7)), 'grok': {1, 3}}
ADOPTIONS = {7: 'bdb97a3c05653b7ba9ed0ba75d0f4c32179448876b04306db2ca28cb4f47f4cc',
             8: 'a5b9163d076ade62d2c6f3b014070a956e93f82a6e1f5468c7211557f0731a79'}


def canonical(value): return (json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False) + '\n').encode()
def digest(raw): return hashlib.sha256(raw).hexdigest()
def meta(raw): return {'sha256': digest(raw), 'bytes': len(raw)}
def require(ok, message):
    if not ok: raise ValueError(message)


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec); sys.modules[name] = module
    spec.loader.exec_module(module); return module


def bind_prefix(row, condition, started, identity, job, job_sha, manifest_sha):
    require(condition == row and digest(canonical({k: v for k, v in row.items() if k != 'request_sha256'}))
            == row['request_sha256'], 'Original condition identity differs')
    require(started['logical_sample_id'] == row['logical_sample_id'] and started['manifest_sha256'] == manifest_sha
            and started['job_sha256'] == job_sha and started['attempt'] == 1 and started['no_resend'] is True
            and started['prompt_sha256'] == row['prompt_sha256'] and started['schema_sha256'] == row['schema_sha256'],
            'Original started identity differs')
    require(identity == {'logical_sample_id': row['logical_sample_id'], 'session_id': started['session_id']}
            and (started['session_id'] is None) == (row['endpoint'] == 'sol'), 'Own native identity differs')
    require(job['endpoint'] == row['endpoint'] and job['attempts_per_logical_sample'] == 1
            and job['automatic_retries'] == 0 and job['planned_study_requests'] == 6864, 'Original job contract differs')


def suffix_rows(manifest, endpoint, through, occupied):
    rows = [r for r in manifest['requests'] if r['endpoint'] == endpoint]
    require([r['endpoint_ordinal'] for r in rows] == list(range(1, len(rows) + 1)), 'Original endpoint order differs')
    require(occupied == {f"{r['endpoint_ordinal']:04d}-{r['logical_sample_id'][:12]}" for r in rows[:through]},
            'Occupied original prefix is not exact; no prefix resend permitted')
    return rows[through:]


def label_gate(plan, verified_suffix_terminals=0, explicit=False):
    # Reserved unknown tails cannot become verified merely because all untouched requests finish.
    return {'planned': 6864, 'strict_prefix_terminals': 8, 'saved_projection_adoptions': 2,
            'prefix_native_terminal_settlement_unproved': 4, 'verified_suffix_terminals': verified_suffix_terminals,
            'explicit_postprediction_release': explicit, 'all_original_slots_verified_terminal': False,
            'human_release_eligible': False, 'human_targets_opened': False, 'provider_calls': 0,
            'remaining_requirement': 'Separate owning-root evidence for Sol9 and Grok2/4/5 native-terminal settlement'}


def selected_rows(plan, manifest):
    require(digest(canonical(manifest['requests'])) == plan['source_geometry_sha256'], 'Full original request geometry differs')
    rows = [row for row in manifest['requests'] if row['endpoint'] == plan['endpoint']
            and row['endpoint_ordinal'] > plan['reserved_through']]
    require([row['request_sha256'] for row in rows] == plan['untouched_request_sha256s']
            and [row['endpoint_ordinal'] for row in rows] == plan['untouched_endpoint_ordinals'], 'Exact untouched selection differs')
    return rows


def execution_binding(plan, plan_sha, workers, *, owner_global_headroom_verified=False, route=None, route_sha=None):
    require(type(workers) is int and 1 <= workers <= 10 and owner_global_headroom_verified is True,
            'Explicit 1..10 workers and owner global headroom verification required')
    binding = deepcopy(plan['source_binding'])
    if plan['endpoint'] == 'grok':
        require(route is not None and digest(canonical(route).rstrip(b'\n')) == route_sha, 'Explicit execution route pin differs')
        renewal = {'cost_evidence', 'subscription_receipt_hash'}
        fixed = lambda value: {k: v for k, v in value.items() if k not in renewal}
        require(fixed(route) == fixed(binding['route']) and renewal <= set(route), 'Route changed a non-renewal control')
        binding.update(source_route_sha256=binding['route_sha256'], route=deepcopy(route), route_sha256=route_sha)
    else: require(route is None and route_sha is None, 'Route applies only to Grok')
    binding.update(policy=POLICY, interrupted_plan_sha256=plan_sha,
                   continuation_preparer_sha256=plan['implementation_sha256'],
                   source_job_sha256=JOBS[plan['endpoint']], reserved_prefix=plan['reserved_through'],
                   untouched_request_commitment_sha256=digest(canonical(plan['untouched_request_sha256s'])),
                   workers=workers, workers_cli_argument=['--workers', str(workers)],
                   owner_global_headroom_verified=True, preparation_grants_execution_authority=False,
                   prefix_native_terminal_settlement_proven=False, human_label_gate_closed=True)
    binding['owner_execution_amendment'].update(allocated_workers=workers, original_interrupted_workers=plan['source_binding']['workers'])
    return binding


def build_plan(program, endpoint):
    require(endpoint in THROUGH, 'Endpoint differs')
    h = program.resolve() / 'hanna-reference'; root = h / 'frozen-001'
    files = {}; commitments = {}
    def read(name, path, expected=None):
        raw = path.read_bytes()
        require(expected is None or meta(raw) == expected, 'Pinned retained source differs: ' + name)
        files[name] = raw; commitments[name] = {**meta(raw), 'source_locator_local_only': str(path.resolve())}
        return raw
    def value(name, path, expected=None): return json.loads(read(name, path, expected))
    audit_raw = read('interruption-audit.json', h / 'interrupted-native-tail-audit-001.json')
    require(digest(audit_raw) == AUDIT_SHA, 'Exact interruption audit differs'); audit = json.loads(audit_raw)
    require(audit['full_planned_denominator'] == 6864 and audit['no_resend'] is True
            and audit['outer_terminal_absent'] == ['sol', 'grok'] and audit['remote_settlement_proven'] is False,
            'Interruption boundary differs')
    for i, pin in enumerate(audit['pins']):
        read(f'audit-inputs/{i:02d}.bin', Path(pin['path_local_only']), {k: pin[k] for k in ('sha256', 'bytes')})
    manifest_raw = read('parent-manifest.json', root / 'manifest.json')
    require(digest(manifest_raw) == MANIFEST_SHA, 'Frozen full manifest differs'); manifest = json.loads(manifest_raw)
    require(manifest['counts']['requests_total'] == len(manifest['requests']) == 6864
            and manifest['labels_read'] is False and manifest['labels_released'] is False, 'Full source geometry/closed labels differ')
    require(digest(canonical({k: v for k, v in manifest.items() if k != 'manifest_content_sha256'}))
            == manifest['manifest_content_sha256'], 'Manifest content differs')
    for path, pin in manifest['artifacts'].items():
        raw = (root / path).read_bytes(); require(meta(raw) == pin, 'Frozen input artifact differs')
    read('implementation/collector.py', HERE / 'collector.py')
    read('implementation/reconcile_saved.py', HERE / 'reconcile_saved.py')
    require(digest(files['implementation/collector.py']) == COLLECTOR_SHA
            and digest(files['implementation/reconcile_saved.py']) == RECONCILER_SHA, 'Retained implementation differs')
    c = load('hanna_interrupted_collection', HERE / 'collector.py')
    r = load('hanna_interrupted_saved', HERE / 'reconcile_saved.py')
    tools = Path(manifest['external_pins']['tools_root_local_only'])
    sys.path.insert(0, str(tools)); sys.path.insert(0, str(REPO / 'src'))
    subset = c.p.load_module('hanna_interrupted_subset', root / 'implementation/schema_subset.py')
    validator = c.p.load_module('hanna_interrupted_validator', root / 'implementation/validate_response.py')
    receipts = c.p.load_module('hanna_interrupted_reader', root / 'implementation/codex_receipts.py')
    entries = []; jobs = {}; ids = set(); attempts = set(); untouched = {}
    for e in THROUGH:
        source = h / f'judging-{e}-parallel-001'
        job = value(f'prefix/{e}/job.json', source / 'job.json'); jobs[e] = job
        require(digest(files[f'prefix/{e}/job.json']) == JOBS[e], 'Exact interrupted job differs')
        require(c.verify_job_binding(source, manifest, root, MANIFEST_SHA, e, tools) == job, 'Original frozen job binding differs')
        read(f'prefix/{e}/frozen-manifest.json', source / 'frozen-manifest.json', meta(manifest_raw))
        require(not (source / 'terminal.json').exists(), 'Original outer terminal now exists; new audit required')
        if e == 'sol': read('prefix/sol/account-binding.json', source / 'account-binding.json')
        occupied = {p.name for p in source.iterdir() if p.is_dir()}
        untouched[e] = suffix_rows(manifest, e, THROUGH[e], occupied)
        rows = [row for row in manifest['requests'] if row['endpoint'] == e][:THROUGH[e]]
        for row in rows:
            sample = c.sample_path(source, row); n = row['endpoint_ordinal']; stem = f'prefix/{e}/{sample.name}/'
            # Only these finite occupied sample directories are inventoried; values remain private.
            inventory = {}
            for path in sorted(p for p in sample.rglob('*') if p.is_file()):
                name = path.relative_to(sample).as_posix(); inventory[name] = meta(read(stem + name, path))
            condition = json.loads(files[stem + 'condition.json']); started = json.loads(files[stem + 'attempt-started.json'])
            identity = json.loads(files[stem + 'native-identity.json'])
            bind_prefix(row, condition, started, identity, job, JOBS[e], MANIFEST_SHA)
            require(started['attempt_id'] not in attempts, 'Duplicate original attempt identity'); attempts.add(started['attempt_id'])
            invocation = started['execution_invocation']; raw = read(f'prefix/{e}/' + invocation['path'], c.within(source, invocation['path']),
                                                                     {k: invocation[k] for k in ('sha256', 'bytes')})
            argv = json.loads(raw)
            require(argv['job_sha256'] == JOBS[e] and argv['workers'] == job['workers']
                    and c.execution_workers(argv['argv']) == job['workers'] and '--owner-global-headroom-verified' in argv['argv'],
                    'Original execution invocation differs')
            require(started['account_binding_sha256'] == (digest(files['prefix/sol/account-binding.json']) if e == 'sol' else None),
                    'Original account binding differs')
            prompt, schema, texts, context = c.inputs(root, manifest, row)
            require(files[stem + 'prompt.txt'] == prompt and files[stem + 'schema.json'] == schema
                    and files[stem + 'task-context.json'] == context.encode()
                    and all(files[stem + 'sources/' + tid + '.txt'] == text.encode() for tid, text in texts.items()), 'Original source/context snapshot differs')
            terminal_present = 'terminal.json' in inventory
            native_id = identity['session_id']; state = 'reserved_unresolved'; admission = 'unadmitted'; recipient = None
            if n in STRICT[e]:
                terminal, answer = c.replay(sample, row, manifest, job, root, receipts, subset, validator)
                require(terminal['state'] == 'accepted' and answer is not None, 'Pinned strict prefix admission differs')
                state = 'accepted'; admission = 'original_strict'
                if e == 'sol': native_id = json.loads(files[stem + 'responses/batch-0001.attempt-0001.receipt.json'])['thread_id']
            elif e == 'sol' and n in ADOPTIONS:
                path = h / f'sol-slot{n}-saved-reconciliation-001/reconciliation.json'
                saved = r.verify(path, ADOPTIONS[n]); read(f'adoptions/{n}/reconciliation.json', path)
                require(saved['logical_sample_id'] == row['logical_sample_id'] and saved['request_sha256'] == row['request_sha256']
                        and saved['same_original_observation_only'] is True and saved['accepted'] is True
                        and saved['new_logical_votes'] == 0 and saved['human_labels_released'] is False,
                        'Saved descendant changed original observation/admission')
                state = 'unadmitted_no_resend'; admission = 'named_saved_projection'; recipient = ADOPTIONS[n]
                native_id = saved['native']['native_reader_receipt']['thread_id']
            else:
                require(not terminal_present and n in ({9} if e == 'sol' else {2, 4, 5}), 'Reserved unresolved terminal boundary differs')
                if e == 'sol':
                    own = [pin for pin in audit['pins'] if pin['sha256'] == 'f2f2bd356d0b7ac06165c7d1e0d0457241afcebb0127ed785b6a0bc57e05070f']
                    require(len(own) == 1, 'Exact unresolved own rollout pin missing')
                    first = json.loads(Path(own[0]['path_local_only']).read_bytes().splitlines()[0])
                    require(first['type'] == 'session_meta' and first['payload']['cwd'] == str(sample), 'Unresolved own session metadata differs')
                    native_id = first['payload']['id']
                else:
                    require(any(Path(pin['path_local_only']).parent.name == native_id for pin in audit['pins']), 'Unresolved own Grok session pin missing')
            require(native_id is not None and (e, native_id) not in ids, 'Duplicate/missing retained native identity'); ids.add((e, native_id))
            entries.append({'endpoint': e, 'endpoint_ordinal': n, 'logical_sample_id': row['logical_sample_id'],
                'request_sha256': row['request_sha256'], 'source_job_sha256': JOBS[e], 'original_state': state,
                'admission': admission, 'saved_recipient_sha256': recipient, 'native_identity': native_id,
                'native_identity_basis': 'exact_session_metadata_only' if admission == 'unadmitted' else 'verified_native_receipt',
                'attempt_id': started['attempt_id'], 'terminal_present': terminal_present, 'inventory': inventory,
                'no_resend': True, 'new_votes': 0})
    require(Counter(entry['admission'] for entry in entries) == {'original_strict': 8, 'named_saved_projection': 2, 'unadmitted': 4},
            'Exact prefix disposition differs')
    read('implementation/continue_interrupted.py', Path(__file__))
    plan = {'schema_version': 1, 'policy': POLICY, 'program_root_local_only': str(program.resolve()), 'endpoint': endpoint,
        'implementation_sha256': digest(files['implementation/continue_interrupted.py']), 'original_manifest_sha256': MANIFEST_SHA,
        'interruption_audit_sha256': AUDIT_SHA, 'full_planned_denominator': 6864, 'endpoint_denominator': 3432,
        'source_geometry_sha256': digest(canonical(manifest['requests'])), 'source_artifacts': manifest['artifacts'],
        'source_binding': jobs[endpoint], 'reserved_through': THROUGH[endpoint], 'prefix': entries,
        'untouched_request_sha256s': [row['request_sha256'] for row in untouched[endpoint]],
        'untouched_endpoint_ordinals': [row['endpoint_ordinal'] for row in untouched[endpoint]],
        'untouched_total': sum(len(rows) for rows in untouched.values()), 'source_commitments': commitments,
        'original_prepared_workers_initially': 1, 'allowed_explicit_workers': [1, 10], 'project_global_cap_each_endpoint': 10,
        'owner_must_verify_shared_headroom_before_execution': True, 'one_attempt': True, 'automatic_retries': 0,
        'stop_new_dispatch_and_settle_inflight': True, 'provider_calls': 0, 'new_votes': 0, 'human_targets_opened': False,
        'remote_settlement_proven': False, 'descendant_quiescence_proven': False, 'physical_contact_cardinality_proven': False,
        'outer_terminal_reconstructed': False, 'preparation_grants_execution_authority': False,
        'execution_adapter_implemented': False, 'retained_collector_requires_named_suffix_adapter': True,
        'execution_interfaces': {'request_selection': 'continue_interrupted.selected_rows(plan, original_manifest)',
            'source_inputs': 'collector.inputs(frozen_root, original_manifest, original_row)',
            'native_call': 'collector.collect_one with original manifest and named execution binding',
            'native_replay': 'collector.replay with named execution binding; no source-prefix alias',
            'dispatch': 'collector.dispatch and private CommitState seeded with all retained endpoint native identities',
            'invocation': 'fresh job.json/account-binding.json and workers/headroom execution-invocation receipt',
            'sol_account': 'collector.t.secondary_binding/probe and collector.t.account_receipt; no preparation probe',
            'grok_guard': 'exact renewed route SHA, reviewed broker, expiry/deadline and STOP checked before each contact',
            'remaining_adapter': 'Owned named executor must select these rows instead of frozen full-manifest inventory'}}
    plan['human_label_gate'] = label_gate(plan)
    files['plan.json'] = canonical(plan)
    return plan, files


def fresh_output(output, program):
    h = program.resolve() / 'hanna-reference'; output = output.resolve()
    protected = [REPO, h / 'frozen-001', h / 'parallel-lifecycle', *(h / f'judging-{e}-parallel-001' for e in THROUGH),
                 *(h / f'sol-slot{n}-saved-reconciliation-001' for n in ADOPTIONS)]
    require(output.is_relative_to(h) and not output.exists()
            and all(not output.is_relative_to(p.resolve()) and not p.resolve().is_relative_to(output) for p in protected),
            'Plan output must be fresh under HANNA reference and outside retained sources')
    return output


def verify_plan(path, expected_sha):
    raw = path.read_bytes(); require(digest(raw) == expected_sha, 'Exact continuation plan differs'); saved = json.loads(raw)
    for name, pin in saved['source_commitments'].items():
        require(meta((path.parent / name).read_bytes()) == {k: pin[k] for k in ('sha256', 'bytes')}, 'Frozen prefix snapshot differs')
    actual, _ = build_plan(Path(saved['program_root_local_only']), saved['endpoint'])
    require(actual == saved, 'Retained original prefix/implementation changed')
    return actual


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--program-root', type=Path, required=True)
    parser.add_argument('--endpoint', choices=THROUGH, required=True)
    parser.add_argument('--output-root', type=Path, required=True)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args(); output = fresh_output(args.output_root, args.program_root)
    plan, files = build_plan(args.program_root, args.endpoint)
    if not args.dry_run:
        output.mkdir(parents=True, exist_ok=False)
        for name, raw in files.items():
            if name in plan['source_commitments']:
                require(Path(plan['source_commitments'][name]['source_locator_local_only']).read_bytes() == raw, 'Source changed before snapshot')
            path = output / name; path.parent.mkdir(parents=True, exist_ok=True)
            with path.open('xb') as handle: handle.write(raw)
    print(json.dumps({'policy': POLICY, 'endpoint': args.endpoint, 'plan_sha256': digest(files['plan.json']),
        'reserved_endpoint_prefix': plan['reserved_through'], 'untouched_endpoint_requests': len(plan['untouched_request_sha256s']),
        'untouched_total': plan['untouched_total'], 'full_planned_denominator': 6864,
        'prefix_admissions': dict(Counter(e['admission'] for e in plan['prefix'])), 'pinned_snapshot_files': len(plan['source_commitments']),
        'human_release_eligible': False, 'provider_calls': 0, 'new_votes': 0, 'output_written': not args.dry_run}, sort_keys=True))


if __name__ == '__main__':
    try: main()
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise SystemExit('HANNA interruption plan pending: ' + type(error).__name__ + ': ' + str(error)) from None
