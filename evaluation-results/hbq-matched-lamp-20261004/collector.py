"""LAMP native collection, with explicit shared-headroom allocation and sealed labels."""
from collections import Counter, defaultdict
from datetime import datetime, timezone
import argparse
import json
import os
from pathlib import Path
import sys
import uuid
import importlib.util

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('lamp_collection_prepare', HERE / 'prepare.py')
p = importlib.util.module_from_spec(spec); spec.loader.exec_module(p)
HANNA = HERE.parent / 'hbq-matched-hanna-20261004/collector.py'
HANNA_SHA = '327bfa1deeed417f7a558914d650297fda3c0999adccd2c2a8b0a661b182cf83'
HANNA_PREPARE_SHA = '2d82e4959c3296ccaa6e6521adb46f85588427d429a544b36a2891ebaea8c7b0'
p.checked(HANNA, HANNA_SHA)
p.checked(HANNA.with_name('prepare.py'), HANNA_PREPARE_SHA)
# This instance owns its adaptations; retained collectors and their live modules stay unchanged.
h = p.load('lamp_retained_parallel_native', HANNA)
t = h.t
POLICY = 'matched_lamp_native_parallel_owner_amendment_v1'
MANIFEST_SHA = '480aa86df271078e322ac85cf8cfe5fe6ed02344138e218900cfe03c069b6ab6'
canonical, digest, require = p.canonical, p.digest, p.require
pinned, record, write_bytes, within = h.pinned, h.record, h.write_bytes, h.within
SETTLED, TERMINAL_STATES = h.SETTLED, h.TERMINAL_STATES
sample_path, admission, native_answer = h.sample_path, h.admission, h.native_answer
CommitState, dispatch, execution_workers = h.CommitState, h.dispatch, h.execution_workers
grok_contact_allowed, output_preflight = h.grok_contact_allowed, h.output_preflight


def source_settings(manifest, root):
    raw = pinned(root, 'sources/generation-runtime-manifest.json', manifest['artifacts']['sources/generation-runtime-manifest.json'])
    require(digest(raw) == manifest['generation_runtime_manifest_sha256'] == p.GENERATION_SHA, 'Generation runtime pin differs')
    source = json.loads(raw); runtime, pins = source['runtime'], source['external_pins']
    require(runtime['model'] == 'gpt-6.1-sol' and runtime['reasoning'] == 'high'
            and runtime['account_identity_sha256'] == t.SECONDARY_ACCOUNT_SHA256
            and runtime['receipt_policy'] == 'codex_native_rollout_v1', 'Designated secondary runtime differs')
    require(manifest['runtime']['sol']['account_identity_sha256'] == runtime['account_identity_sha256']
            and manifest['runtime']['sol']['secondary_home_sha256'] == runtime['codex_home_sha256'], 'Prepared account differs')
    helper_sha = source['artifacts']['implementation/secondary-helper.py']['sha256']
    require(manifest['external_pins']['secondary_helper_sha256'] == helper_sha
            == manifest['artifacts']['implementation/secondary-helper.py']['sha256'], 'Frozen helper pin differs')
    for name in ('cli_path_local_only', 'cli_sha256', 'collection_home_path_local_only'):
        require(manifest['external_pins'][name] == pins[name], 'External runtime pin differs')
    p.checked(Path(pins['secondary_helper_path_local_only']), helper_sha)
    p.checked(Path(pins['cli_path_local_only']), pins['cli_sha256'], pins['cli_bytes'])
    home = Path(pins['collection_home_path_local_only']).resolve()
    require(home.name == 'cwr-sol-secondary' and home.parent.name == 'collection-accounts'
            and digest(str(home).encode()) == runtime['codex_home_sha256'], 'Secondary home differs')
    return source


def inputs(root, manifest, row):
    from hbqrs import runner
    prompt = pinned(root, row['prompt_path'], manifest['artifacts'][row['prompt_path']])
    schema = pinned(root, row['schema_path'], manifest['artifacts'][row['schema_path']])
    require(digest(prompt) == row['prompt_sha256'] and len(prompt) == row['prompt_bytes']
            and digest(schema) == row['schema_sha256'] and len(schema) == row['schema_bytes'], 'Request payload pin differs')
    texts = {s['id']: pinned(root, s['input_path'], s).decode('utf-8') for s in row['sources']}
    require(len(texts) == len(row['sources']), 'Duplicate source identity')
    pretty = pinned(root, row['task_context']['path'], row['task_context']).decode('utf-8')
    shared = pinned(root, row['shared_work_context']['path'], row['shared_work_context']).decode('utf-8')
    require(pretty.encode() in prompt and shared.encode() in prompt
            and all(text.encode() in prompt for text in texts.values()), 'Exact source/instruction/context absent from prompt')
    require({c['artifact_id'] for c in row['task_contracts']} == set(texts), 'Task/source identities differ')
    for contract in row['task_contracts']:
        raw = pinned(root, contract['path'], manifest['artifacts'][contract['path']])
        require(digest(raw) == contract['sha256'], 'Task contract pin differs')
        task = json.loads(raw)
        require(task == p.task_contract(contract['artifact_id'])
                and pretty == json.dumps(runner._task_contract_judge_context(task), ensure_ascii=False, indent=2), 'Neutral passage task/context differs')
    return prompt, schema, texts, pretty + '\n' + shared


def validate_design(manifest, files):
    from hbqrs import core
    require(manifest['study_id'] == p.POLICY and manifest['execution_authority'] is False
            and manifest['labels_read'] is False and manifest['provider_calls'] == 0
            and manifest['measurement']['candidate'] is None, 'Source-only sealed preparation differs')
    require(manifest['runtime']['timeout_seconds'] == 900 and manifest['runtime']['workers_initially'] == 1
            and manifest['runtime']['attempts_per_logical_sample'] == 1 and manifest['runtime']['automatic_retries'] == 0
            and manifest['runtime']['no_ambiguous_resend'] is True, 'Prepared attempt contract differs')
    counts = manifest['counts']
    require(counts['groups'] == 94 and counts['paragraphs'] == 282 and counts['requests_per_endpoint'] == 8904
            and counts['requests_total'] == len(manifest['requests']) == 17808
            and counts['leaves_per_bank'] == 170 and counts['packets_per_bank'] == 22, 'Full denominator/bank differs')
    ids = [q['question']['id'] for q in core.compiled_questions(json.loads(files['compiled.json']))]
    require(len(ids) == len(set(ids)) == 170, 'Unique full170 bank differs')
    groups = manifest['selection']['groups']; pairs = manifest['selection']['pairs']
    require(len(groups) == len({g['id'] for g in groups}) == 94
            and Counter(g['stratum'] for g in groups) == Counter(dict(enumerate(p.STRATUM_COUNTS))), 'Source membership strata differ')
    group_map = {g['id']: g['variant_ids'] for g in groups}
    require(all(len(v) == len(set(v)) == 3 for v in group_map.values())
            and len({v for vs in group_map.values() for v in vs}) == 282, 'Unique triplet paragraphs differ')
    pair_map = {pair['pair_id']: pair for pair in pairs}
    require(len(pair_map) == len(pairs) == 282, 'Unique within-triplet pairs differ')
    for group, variants in group_map.items():
        actual = [pair for pair in pairs if pair['group_id'] == group]
        require(len(actual) == 3 and {frozenset((pair['left'], pair['right'])) for pair in actual}
                == {frozenset((variants[a], variants[b])) for a, b in ((0, 1), (0, 2), (1, 2))}, 'Complete within-triplet pair set differs')
    sentinels = set(manifest['selection']['sentinel_group_ids'])
    require(sentinels == set(p.select_sentinels(groups)), 'Prospective metadata sentinel selection differs')
    endpoint_ids = {}; common = {}
    for endpoint in p.ENDPOINTS:
        rows = [r for r in manifest['requests'] if r['endpoint'] == endpoint]
        require(len(rows) == 8904 and [r['endpoint_ordinal'] for r in rows] == list(range(1, 8905))
                and Counter(r['arm'] for r in rows) == Counter({'hbq': 6996, 'ttcw14': 318, 'holistic': 318, 'compact': 318, 'oregon': 318, 'pairwise': 636}), 'Endpoint arm/order geometry differs')
        endpoint_ids[endpoint] = {r['logical_sample_id'] for r in rows}
        require(len(endpoint_ids[endpoint]) == 8904, 'Duplicate logical sample')
        solo = defaultdict(list); pair_orders = defaultdict(list)
        for row in rows:
            require(digest(canonical({k: v for k, v in row.items() if k != 'request_sha256'})) == row['request_sha256'], 'Request commitment differs')
            condition = {k: v for k, v in row.items() if k not in {'request_sha256', 'logical_sample_id', 'endpoint', 'endpoint_ordinal', 'ordinal'}}
            require(digest(canonical(condition)) == row['logical_sample_id'], 'Logical condition differs')
            require(row['repeat'] in (0, 1, 2) and row['group_id'] in group_map
                    and (row['repeat'] == 0 or row['group_id'] in sentinels)
                    and row['compiled_sha256'] == digest(files['compiled.json']), 'Source/repeat/bank condition differs')
            context = canonical([row['task_context'], row['shared_work_context']])
            require(common.setdefault(row['group_id'], context) == context, 'Triplet arms/repeats do not share exact context')
            if row['arm'] == 'pairwise':
                pair = pair_map[row['pair_id']]; orientation = row['orientation']
                require(orientation in ('AB', 'BA') and pair['group_id'] == row['group_id'], 'Pair orientation/group differs')
                wanted = [pair['left'], pair['right']] if orientation == 'AB' else [pair['right'], pair['left']]
                require([s['id'] for s in row['sources']] == wanted and [s['side'] for s in row['sources']] == ['A', 'B'], 'Ordered exact pair source differs')
                pair_orders[(row['pair_id'], row['repeat'])].append(orientation)
            else:
                require(row['artifact_id'] in group_map[row['group_id']] and [s['id'] for s in row['sources']] == [row['artifact_id']], 'Solo source membership differs')
                solo[(row['artifact_id'], row['repeat'])].append(row)
        require(len(solo) == 318 and len(pair_orders) == 318 and all(Counter(v) == Counter(['AB', 'BA']) for v in pair_orders.values()), 'Complete repeated solo/pair geometry differs')
        for cycle in (0, 1, 2):
            selected = set(group_map) if cycle == 0 else sentinels
            require({aid for aid, repeat in solo if repeat == cycle} == {aid for g in selected for aid in group_map[g]}
                    and {pid for pid, repeat in pair_orders if repeat == cycle} == {pid for pid, pair in pair_map.items() if pair['group_id'] in selected}, 'Cycle cohort incomplete')
        for group in solo.values():
            require(Counter(r['arm'] for r in group) == Counter({'hbq': 22, 'ttcw14': 1, 'holistic': 1, 'compact': 1, 'oregon': 1}), 'Solo arm bank incomplete')
            hbq = sorted((r for r in group if r['arm'] == 'hbq'), key=lambda r: r['batch'])
            require([r['batch'] for r in hbq] == list(range(1, 23)) and [qid for r in hbq for qid in r['question_ids']] == ids
                    and [len(r['question_ids']) for r in hbq] == [8]*21 + [2], 'Causal full170 packet order differs')
    require(endpoint_ids['grok'] == endpoint_ids['sol'] and [r['ordinal'] for r in manifest['requests']] == list(range(1, 17809)), 'Matched global request order differs')


def load_manifest(path, expected_sha, collector_sha, tools):
    raw = path.read_bytes(); root = path.resolve().parent; manifest = json.loads(raw)
    require(digest(raw) == expected_sha == MANIFEST_SHA and digest(Path(__file__).read_bytes()) == collector_sha, 'Exact manifest/collector pin differs')
    require(digest(canonical({k: v for k, v in manifest.items() if k != 'manifest_content_sha256'})) == manifest['manifest_content_sha256'], 'Manifest content differs')
    files = {name: pinned(root, name, meta) for name, meta in manifest['artifacts'].items()}
    sys.path.insert(0, str(p.REPO / 'src')); validate_design(manifest, files)
    source = source_settings(manifest, root)
    require(tools.resolve() == Path(source['external_pins']['tools_root_local_only']).resolve(), 'Tools root differs')
    p.checked(tools / 'adaptive_settings/account_probe.py', source['external_pins']['account_probe_sha256'])
    sys.path.insert(0, str(tools))
    for current, frozen in [(HERE / 'prepare.py', 'implementation/prepare.py'),
            (p.REPO / 'src/hbqrs/core.py', 'implementation/core.py'), (p.REPO / 'src/hbqrs/runner.py', 'implementation/runner.py'),
            (p.REPO / 'src/hbqrs/scoring_v2.py', 'implementation/scoring_v2.py'), (p.REPO / 'src/hbqrs/codex_receipts.py', 'implementation/codex_receipts.py'),
            (tools / 'model_work_queue/broker.py', 'implementation/broker.py'), (tools / 'model_work_queue/adapters/grok_exec.py', 'implementation/grok_exec.py')]:
        require(digest(current.read_bytes()) == manifest['artifacts'][frozen]['sha256'], 'Frozen implementation differs')
    subset = p.load('lamp_frozen_schema_subset', root / 'implementation/schema_subset.py')
    validator = p.load('lamp_frozen_admission', root / 'implementation/validate_response.py')
    receipts = p.load('lamp_frozen_native_receipts', root / 'implementation/codex_receipts.py')
    for name in {r['schema_path'] for r in manifest['requests']}: subset.validate_schema(json.loads(files[name]))
    seen = set()
    for row in manifest['requests']:
        key = canonical({name: row[name] for name in ('prompt_path', 'schema_path', 'sources', 'task_context', 'shared_work_context', 'task_contracts')})
        if key not in seen: inputs(root, manifest, row); seen.add(key)
    return manifest, root, subset, validator, receipts


def job_binding(manifest, root, manifest_sha, endpoint, tools, route=None, collector_sha=None, workers=1):
    if endpoint == 'grok':
        require(route is not None and route['nonvisual_transport_contract'] == 'grok_nonvisual_history_v5'
                and route['nonvisual_max_turns'] == 1, 'LAMP requires the reviewed one-turn v5 route')
    # The retained transport has the same runtime contract; source geometry stays LAMP-owned.
    transport_manifest = {**manifest, 'generation_manifest_file_sha256': manifest['generation_runtime_manifest_sha256'],
        'human_gate': manifest['measurement']['label_release_gate'], 'disclosure': manifest['outbound']}
    binding = retained_job_binding(transport_manifest, root, manifest_sha, endpoint, tools, route, collector_sha, workers)
    binding.update(policy=POLICY, collector_sha256=collector_sha or digest(Path(__file__).read_bytes()),
        retained_parallel_collector_sha256=HANNA_SHA, retained_parallel_preparation_sha256=HANNA_PREPARE_SHA,
        planned_endpoint_requests=8904, planned_study_requests=17808,
        label_gate_policy='matched_lamp_all17808_verified_terminal_explicit_release_v1',
        context_admission_policy='exact_task_projection_and_source_instruction_v1', sampler=manifest['runtime']['sampler'],
        cost_token_cache_attestation=False)
    return binding


def verify_job_binding(output, manifest, root, manifest_sha, endpoint, tools):
    binding = json.loads((output / 'job.json').read_bytes())
    require(binding == job_binding(manifest, root, manifest_sha, endpoint, tools, binding.get('route'), workers=binding['workers'])
            and (output / 'frozen-manifest.json').read_bytes() == (root / 'manifest.json').read_bytes(), 'Existing job/raw manifest differs')
    if endpoint == 'sol': require(json.loads((output / 'account-binding.json').read_bytes()) == t.account_receipt(binding), 'Account receipt differs')
    return binding


retained_job_binding = h.job_binding
h.source_settings = source_settings; h.inputs = inputs; h.q.inputs = inputs
h.job_binding = job_binding; h.verify_job_binding = verify_job_binding
collect_one, replay, inventory = h.collect_one, h.replay, h.inventory


def label_release_gate(manifest, root, manifest_sha, tools, outputs, receipts, subset, validator, explicit_release=False):
    counts = {}; native_ids = set()
    for endpoint in p.ENDPOINTS:
        output = outputs[endpoint]
        if not output.exists():
            counts[endpoint] = {'untouched': 8904, 'verified_terminal': 0, 'states': {}}; continue
        binding = verify_job_binding(output, manifest, root, manifest_sha, endpoint, tools)
        pending, states, identities = inventory(manifest, binding, root, output, receipts, subset, validator)
        require(not native_ids & identities, 'Native UUID reused across endpoints'); native_ids.update(identities)
        counts[endpoint] = {'untouched': len(pending), 'verified_terminal': len(states), 'states': dict(Counter(states))}
    ready = sum(c['verified_terminal'] for c in counts.values()) == 17808 and all(c['untouched'] == 0 for c in counts.values())
    return {'policy': 'matched_lamp_all17808_verified_terminal_explicit_release_v1', 'manifest_sha256': manifest_sha,
        'planned': 17808, 'endpoints': counts, 'all_planned_verified_terminal': ready, 'explicit_postprediction_release': explicit_release,
        'human_release_eligible': ready and explicit_release, 'human_targets_opened': False, 'provider_calls': 0}


def allocation(workers, argv, owner_verified, executing):
    require(1 <= workers <= 10 and execution_workers(argv) == workers, 'Explicit workers allocation must be 1..10')
    require(not executing or owner_verified, 'Launching owner must verify shared project headroom before execution')


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    for name in ('manifest', 'tools-root'): parser.add_argument('--' + name, type=Path, required=True)
    for name in ('manifest-sha256', 'collector-sha256'): parser.add_argument('--' + name, required=True)
    for name in ('results-dir', 'route-root', 'sol-results-dir', 'grok-results-dir'): parser.add_argument('--' + name, type=Path)
    parser.add_argument('--endpoint', choices=p.ENDPOINTS); parser.add_argument('--route-sha256')
    parser.add_argument('--workers', type=int, required=True); parser.add_argument('--owner-global-headroom-verified', action='store_true')
    parser.add_argument('--limit', type=int); parser.add_argument('--validate-only', action='store_true')
    parser.add_argument('--label-release-check', action='store_true'); parser.add_argument('--explicit-postprediction-release', action='store_true')
    args = parser.parse_args()
    allocation(args.workers, sys.argv, args.owner_global_headroom_verified, not (args.validate_only or args.label_release_check))
    require(args.limit is None or args.limit > 0, 'Limit invalid')
    manifest, root, subset, validator, receipts = load_manifest(args.manifest, args.manifest_sha256, args.collector_sha256, args.tools_root)
    if args.label_release_check:
        require(args.sol_results_dir is not None and args.grok_results_dir is not None, 'Both result roots required')
        outputs = {'sol': args.sol_results_dir.resolve(), 'grok': args.grok_results_dir.resolve()}
        for output in outputs.values(): output_preflight(output, root)
        print(json.dumps(label_release_gate(manifest, root, args.manifest_sha256, args.tools_root, outputs, receipts, subset, validator, args.explicit_postprediction_release))); return 0
    require(not args.explicit_postprediction_release and args.endpoint is not None and args.results_dir is not None, 'Endpoint/results or release mode invalid')
    output = args.results_dir.resolve(); output_preflight(output, root); route = None
    if args.endpoint == 'grok':
        require(args.route_root is not None and args.route_sha256 is not None, 'Exact reviewed Grok route required')
        routes = json.loads((args.route_root / 'routes.json').read_bytes())['routes']
        matches = [r for r in routes if r['name'] == 'grok-build-grok-4.7']
        require(len(matches) == 1, 'Unique reviewed route missing'); route = matches[0]
        require(digest(canonical(route).rstrip(b'\n')) == args.route_sha256, 'Reviewed route pin differs')
    binding = job_binding(manifest, root, args.manifest_sha256, args.endpoint, args.tools_root, route, args.collector_sha256, args.workers)
    if output.exists(): require(verify_job_binding(output, manifest, root, args.manifest_sha256, args.endpoint, args.tools_root) == binding, 'Existing allocation differs')
    pending, states, native_ids = inventory(manifest, binding, root, output, receipts, subset, validator)
    if args.validate_only:
        print(json.dumps({'state': 'provider_free_validated', 'endpoint': args.endpoint, 'manifest_sha256': args.manifest_sha256,
            'job_binding_sha256': digest(canonical(binding)), 'planned': 8904, 'study_planned': 17808, 'workers': args.workers,
            'untouched': len(pending), 'terminal_states': dict(Counter(states)), 'provider_calls': 0,
            'human_targets_opened': False, 'human_release_eligible': False, 'native_execution_proven': False})); return 0
    require(all(state in SETTLED for state in states), 'Occupied native failure needs owning reconciliation; no resend')
    if (output / 'STOP').exists(): return 3
    if not pending: return 0
    helper = call_codex = broker = None
    if args.endpoint == 'sol':
        source = source_settings(manifest, root)
        helper = p.load('lamp_secondary_helper', Path(source['external_pins']['secondary_helper_path_local_only']))
        env = t.secondary_binding(source, helper); os.environ.clear(); os.environ.update(env)
        from adaptive_settings.account_probe import probe
        from hbqrs import runner
        t.secondary_binding(source, helper, probe(helper.CLI)); call_codex = runner._call_codex
    else:
        require(grok_contact_allowed(route), 'Route expiry/campaign deadline prevents contact')
        from model_work_queue.broker import Broker
        broker = Broker(args.route_root.resolve())
    if not output.exists():
        output.mkdir(parents=True, exist_ok=False); record(output / 'job.json', binding); write_bytes(output / 'frozen-manifest.json', args.manifest.read_bytes())
    if args.endpoint == 'sol' and not (output / 'account-binding.json').exists(): record(output / 'account-binding.json', t.account_receipt(binding))
    name = 'execution-invocation-' + str(uuid.uuid4()) + '.json'
    raw = canonical({'argv': sys.argv, 'workers': args.workers, 'job_sha256': digest((output / 'job.json').read_bytes()),
        'time': datetime.now(timezone.utc).isoformat(), 'owner_global_headroom_confirmation': True})
    write_bytes(output / name, raw); invocation = {'path': name, 'sha256': digest(raw), 'bytes': len(raw)}
    commit = CommitState(native_ids, invocation)
    execute = lambda row: collect_one(row, manifest, binding, root, output, subset, validator, receipts, helper, call_codex, broker, commit)
    settled = dispatch(pending[:args.limit], args.workers, execute, commit, lambda: (output / 'STOP').exists(),
        lambda row, state: print(json.dumps({'ordinal': row['endpoint_ordinal'], 'state': state}), flush=True))
    record(output / ('dispatch-terminal-' + str(uuid.uuid4()) + '.json'), {'policy': POLICY, 'workers': args.workers,
        'execution_invocation': invocation, 'settled_this_execution': len(settled), 'states': dict(Counter(settled)),
        'stopped': commit.stop.is_set(), 'inflight_at_terminal': 0, 'automatic_retries': 0, 'human_targets_opened': False})
    return 3 if commit.stop.is_set() else 0


if __name__ == '__main__': raise SystemExit(main())
