"""P1 descriptive one-vote chain join; metadata inspection never opens responses."""
from collections import Counter
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
PROGRAM = Path(r'C:\Users\Haile\Documents\cwr-resume-control-20260919-r1\successor-program-20261004')
POLICY = 'descriptive_p1_saved_decode_chain_analysis_v1'
MANIFEST_SHA = '4e139dc1ef859be838cbe9ee8c579285845074032c6a00867a1b03859fdec2ff'
PLAN_PINS = {'sol': '54278689cceca3f032ef0af5d98e1755fd25ef51c668d02567db8ac6ac7dbffc',
             'grok': '417c211cd33e56a730ec57bad4a99d83aa4465c6c7afda7149abcbec641beffa'}
CODE = {
    'analysis': ('../hbq-semantic-crossform-p1b-matched-v1/analysis.py', 'e158e278b29a0a2ade3aeae4691a86ba70d1a9f1f618b3a94a2d33d43ee5fd04'),
    'sol': ('continue_failed_transport.py', 'c9079969a868f0800ef22e681d4304424af9c738ed514755f3a3aaf968fa243e'),
    'grok': ('continue_saved_decode.py', '993ef94ac1f032fd44d880fc953238a4653d6777f9fba964bbb73aa1c12ff7d2'),
    'reader': ('reconcile_failed_suffix.py', 'f285d228607c26cca0009d17626e7d6915f3d715e3b29f02784a25c682f4be68')}
STATES = {'accepted', 'semantic_rejected', 'ambiguous', 'unadmitted_no_resend', 'definitely_not_contacted',
          'unavailable', 'started_unresolved', 'untouched'}
TOKEN_FIELDS = ('input_tokens', 'cached_input_tokens', 'output_tokens', 'latency_seconds')


def require(ok, message):
    if not ok:
        raise ValueError(message)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False) + '\n').encode()


def pinned_raw(path, expected):
    raw = path.read_bytes()
    require(digest(raw) == expected, 'Exact retained source pin differs: ' + path.name)
    return raw


def load(key):
    relative, sha = CODE[key]
    path = HERE / relative
    pinned_raw(path, sha)
    sys.path.insert(0, str(HERE))
    spec = importlib.util.spec_from_file_location('p1_chain_private_' + key, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def identity(row):
    return row['endpoint'], row['logical_sample_id']


def join_once(manifest, observations):
    """Validated observations occupy original descriptors; absent slots stay missing."""
    expected = {identity(row): row for row in manifest['requests']}
    require(len(expected) == len(manifest['requests']), 'Duplicate original planned descriptor')
    seen, native_ids, records, inventory, commitments = set(), set(), [], [], []
    observed = {}
    for item in observations:
        row = item['request']
        key = identity(row)
        require(key in expected and row == expected[key], 'Altered or unknown original request identity')
        require(key not in seen, 'Duplicate prefix/suffix logical vote')
        seen.add(key)
        require(item['state'] in STATES and item.get('new_votes', 0) == 0, 'Unsupported disposition or additional vote')
        native = item.get('native_identity')
        if native is not None:
            require(native not in native_ids, 'Duplicate native observation identity')
            native_ids.add(native)
        if item['state'] == 'accepted':
            require(native is not None and item.get('response') is not None, 'Accepted slot lacks its own native response/identity')
            records.append({'request': row, 'response': item['response']})
        observed[key] = item
        commitments.append({'endpoint': row['endpoint'], 'request_sha256': row['request_sha256'],
                            'logical_sample_id': row['logical_sample_id'], 'state': item['state'],
                            'native_identity_sha256': digest(native.encode()) if native else None,
                            'proof': item.get('proof', {})})
    for row in manifest['requests']:
        item = observed.get(identity(row), {})
        inventory.append({'request': row, 'state': item.get('state', 'untouched'),
                          'native_metrics': item.get('native_metrics', {field: None for field in TOKEN_FIELDS}),
                          'admission_basis': item.get('admission_basis', 'unobserved')})
    require(len(inventory) == len(manifest['requests']), 'Full original denominator differs')
    return records, inventory, commitments


def metadata_contract(manifest_path, sol_plan, grok_plan):
    manifest = json.loads(pinned_raw(manifest_path, MANIFEST_SHA))
    require(manifest['evidence_class'] == 'descriptive_ai_synthetic_stimuli' and manifest['candidate'] is None
            and manifest['oracle_accepted'] is False and manifest['fixed_synthetic_labels'] is False
            and manifest['human_alignment_claim'] is False and manifest['execution_authority'] is False,
            'Only the frozen descriptive AI fixture contract is eligible')
    require(len(manifest['requests']) == manifest['counts']['requests_total'] == 1584
            and manifest['counts']['requests_per_endpoint'] == 792
            and manifest['runtime']['timeout_seconds'] == 900 and manifest['runtime']['automatic_retries'] == 0,
            'Full P1 geometry/runtime differs')
    for endpoint, path in [('sol', sol_plan), ('grok', grok_plan)]:
        # Prefix plans can contain responses; sealed inspection hashes bytes without parsing them.
        pinned_raw(path, PLAN_PINS[endpoint])
    for relative, sha in CODE.values():
        pinned_raw(HERE / relative, sha)
    previous = load('analysis')
    sys.path.insert(0, str(REPO / 'src'))
    for name in ('core.py', 'runner.py', 'scoring_v2.py', 'codex_receipts.py'):
        pinned_raw(REPO / 'src/hbqrs' / name, manifest['artifacts']['implementation/' + name]['sha256'])
    previous.c.validate_geometry(manifest, manifest_path.parent)
    require(len({identity(row) for row in manifest['requests']}) == 1584, 'Duplicate planned logical identity')
    for row in manifest['requests']:
        require(digest(canonical({k: v for k, v in row.items() if k != 'request_sha256'})) == row['request_sha256'],
                'Original request commitment differs')
    return manifest, previous


def native_identity(sample, row, receipts):
    if row['endpoint'] == 'grok':
        return receipts._uuid(json.loads((sample / 'native-identity.json').read_bytes())['session_id'])
    paths = list(sample.glob('responses/*.events.jsonl'))
    if not paths:
        return None
    require(len(paths) == 1, 'Multiple native attempts occupy one original Sol slot')
    events = receipts._rows(paths[0].read_bytes())
    require(events and events[0][1]['type'] == 'thread.started', 'Own Sol native identity is absent')
    return receipts._uuid(events[0][1]['thread_id'])


def observation(previous, ctx, row, sample, state, answer, *, basis, proof, native=None):
    terminal_raw = (sample / 'terminal.json').read_bytes()
    terminal = json.loads(terminal_raw)
    metrics = {field: None for field in TOKEN_FIELDS}
    metrics['basis'] = 'Projected or unavailable usage remains unavailable; native latency is not attested'
    if row['endpoint'] == 'sol' and terminal['state'] in {'accepted', 'semantic_rejected'}:
        metrics = previous.native_metrics(sample, row, terminal)
    for name in ('response.json', 'transport-reconciliation.json', 'decode-reconciliation.json'):
        if (sample / name).is_file():
            proof[name + '_sha256'] = digest((sample / name).read_bytes())
    return {'request': row, 'state': state, 'response': answer if state == 'accepted' else None,
            'native_identity': native or native_identity(sample, row, receipt_reader()),
            'native_metrics': metrics, 'admission_basis': basis, 'new_votes': 0,
            'proof': {**proof, 'source_terminal_sha256': digest(terminal_raw), 'original_state': terminal['state'],
                      'effective_response_sha256': digest(canonical(answer)) if answer is not None else None,
                      'original_strict_v5_admission_satisfied': False if 'projection' in basis else None}}


def receipt_reader():
    sys.path.insert(0, str(REPO / 'src'))
    from hbqrs import codex_receipts
    return codex_receipts


def prefix_observations(plan, ctx, previous, executor):
    by_key = {identity(row): row for row in ctx['manifest']['requests']}
    result = []
    for entry in plan['prefix']:
        row = by_key[identity(entry)]
        require(row['request_sha256'] == entry['request_sha256'], 'Reserved prefix request differs')
        sample = ctx['module'].sample_path(Path(entry['source_root_local_only']), row)
        proof = {'plan_sha256': PLAN_PINS[row['endpoint']],
                 'source_job_sha256': digest((sample.parent / 'job.json').read_bytes())}
        basis = 'verified_original_or_transport_prefix'
        if 'saved_decode_admission' in entry:
            saved = entry['saved_decode_admission']
            raw = (ctx['saved_decode_receipt'].parent / 'responses' / 'semantic-crossform' / saved['slot'] / 'response.json').read_bytes()
            require(digest(raw) == saved['response_sha256'], 'Fixed saved response differs')
            state = entry['state']
            answer = json.loads(raw) if state == 'accepted' else None
            proof.update(saved_decode_receipt_sha256=plan['saved_receipt_sha256'],
                         saved_response_sha256=saved['response_sha256'], saved_acceptance_sha256=saved['acceptance_sha256'])
            basis = 'fixed_saved_decode_projection_v1'
        elif 'response' in entry:
            state, answer = entry['state'], entry['response']
            if entry.get('transport_recovered'):
                basis = 'verified_saved_transport_projection_v1'
        elif sample.parent.resolve() == ctx['source_root'].resolve():
            predecessor = executor.f if plan['endpoint'] == 'grok' else executor
            state, answer, recovered = predecessor.replay(ctx, row)
            if recovered:
                basis = 'verified_saved_transport_projection_v1'
        else:
            require('saved_decode_source' in ctx and sample.parent.resolve() == ctx['saved_decode_source'].resolve(),
                    'Unsupported prefix source root')
            state, answer, _ = executor.f.replay(ctx, row, sample.parent, plan['source_binding'])
        require(state == entry['state'], 'Effective prefix admission differs from verified plan')
        result.append(observation(previous, ctx, row, sample, state, answer, basis=basis, proof=proof,
                                  native=entry.get('native_identity')))
    return result


def suffix_observations(plan, ctx, executor, previous, output, job_sha):
    raw = pinned_raw(output / 'job.json', job_sha)
    job = json.loads(raw)
    if plan['endpoint'] == 'grok':
        bound = executor.job_binding(plan, PLAN_PINS['grok'], job['workers'], job['route'], job['execution_route_sha256'])
    else:
        bound = executor.existing_binding(plan, PLAN_PINS['sol'], job['workers'], output)
    require(job == bound, 'Exact continuation runtime/account/route job binding differs')
    rows = executor.f.suffix_rows(plan, ctx) if plan['endpoint'] == 'grok' else executor.suffix_rows(plan, ctx)
    require({p.name for p in output.iterdir() if p.is_dir()} <= {ctx['module'].sample_path(output, row).name for row in rows},
            'Continuation reoccupies a reserved or unknown original logical slot')
    result = []
    for row in rows:
        sample = ctx['module'].sample_path(output, row)
        if not sample.exists():
            continue
        if not (sample / 'terminal.json').exists():
            result.append({'request': row, 'state': 'started_unresolved', 'new_votes': 0,
                           'proof': {'source_job_sha256': job_sha}})
            continue
        if plan['endpoint'] == 'grok':
            state, answer = executor.effective_replay(ctx, row, output, bound)
            basis = 'prospective_saved_decode_projection_v1' if (sample / 'decode-reconciliation.json').exists() else 'strict_native_continuation'
        else:
            state, answer, _ = executor.replay(ctx, row, output, bound)
            basis = 'strict_native_continuation'
        result.append(observation(previous, ctx, row, sample, state, answer, basis=basis,
                                  proof={'source_job_sha256': job_sha, 'plan_sha256': PLAN_PINS[row['endpoint']]}))
    return result


def lifecycle_pin(path, sha):
    terminal = json.loads(pinned_raw(path, sha))
    require(type(terminal.get('exit_code')) is int, 'Source collector lifecycle is not terminal')
    return {'terminal_sha256': sha, 'exit_code': terminal['exit_code']}


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--manifest', type=Path, default=PROGRAM / 'semantic-crossform/matched-frozen-002/manifest.json')
    parser.add_argument('--sol-plan', type=Path, default=PROGRAM / 'semantic-crossform/failed-transport-sol-plan-001/plan.json')
    parser.add_argument('--grok-plan', type=Path, default=PROGRAM / 'semantic-crossform/saved-decode-grok-plan-001/plan.json')
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--metadata-only', action='store_true')
    mode.add_argument('--replay-terminal-sources', action='store_true')
    for endpoint in ('sol', 'grok'):
        parser.add_argument('--' + endpoint + '-results', type=Path)
        parser.add_argument('--' + endpoint + '-job-sha256')
        parser.add_argument('--' + endpoint + '-lifecycle-terminal', type=Path)
        parser.add_argument('--' + endpoint + '-lifecycle-sha256')
    args = parser.parse_args()
    manifest, previous = metadata_contract(args.manifest.resolve(), args.sol_plan.resolve(), args.grok_plan.resolve())
    provenance = {'analysis_policy': POLICY, 'analysis_sha256': digest(Path(__file__).read_bytes()),
                  'predecessor_analysis_sha256': CODE['analysis'][1], 'manifest_sha256': MANIFEST_SHA,
                  'plan_sha256s': PLAN_PINS, 'planned_denominator': 1584, 'per_endpoint_denominator': 792,
                  'labels_opened': False, 'provider_calls': 0, 'new_votes': 0,
                  'original_native_envelopes_reconstructed': False, 'physical_contact_cardinality_proven': False}
    if args.metadata_only:
        require(all(getattr(args, endpoint + '_' + field) is None for endpoint in ('sol', 'grok')
                    for field in ('results', 'job_sha256', 'lifecycle_terminal', 'lifecycle_sha256')),
                'Sealed metadata mode does not accept live source handles')
        print(json.dumps({**provenance, 'state': 'sealed_metadata_contract_verified', 'native_sources_replayed': False,
                          'response_text_decoded': False, 'native_job_or_inflight_files_read': False,
                          'verified_terminal': None, 'untouched': None, 'human_release_eligible': False,
                          'planned': manifest['counts'], 'form_leaf_counts': {'short_narrative': 178, 'novel_work_segment': 170, 'poem': 89}},
                         sort_keys=True))
        return 0
    lifecycle = {}
    for endpoint in ('sol', 'grok'):
        require(all(getattr(args, endpoint + '_' + field) is not None
                    for field in ('results', 'job_sha256', 'lifecycle_terminal', 'lifecycle_sha256')),
                'Post-terminal replay requires both exact jobs and lifecycle terminal pins')
        lifecycle[endpoint] = lifecycle_pin(getattr(args, endpoint + '_lifecycle_terminal'), getattr(args, endpoint + '_lifecycle_sha256'))
    observations = []
    context = None
    for endpoint in ('sol', 'grok'):
        executor = load(endpoint)
        plan, ctx = executor.verify_plan(getattr(args, endpoint + '_plan').resolve(), PLAN_PINS[endpoint])
        require(ctx['manifest'] == manifest and plan['full_planned_denominator'] == 1584 and plan['endpoint_denominator'] == 792,
                'Continuation chain changed the original full P1 contract')
        observations.extend(prefix_observations(plan, ctx, previous, executor))
        observations.extend(suffix_observations(plan, ctx, executor, previous, getattr(args, endpoint + '_results').resolve(),
                                                getattr(args, endpoint + '_job_sha256')))
        context = ctx
    records, inventory, commitments = join_once(manifest, observations)
    result = previous.analyze(manifest, records, inventory, previous.load_hbq(manifest, context['root']), context['root'])
    result.update(provenance, source_lifecycle_commitments=lifecycle,
                  verified_observation_commitment_sha256=digest(canonical(sorted(commitments, key=lambda e: (e['endpoint'], e['logical_sample_id'])))),
                  admission_bases=dict(Counter(item['admission_basis'] for item in inventory)),
                  native_sources_replayed=True, original_unresolved_grok148_reserved=True,
                  human_release_eligible=False)
    print(json.dumps(result, sort_keys=True, allow_nan=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
