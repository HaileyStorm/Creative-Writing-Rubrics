"""Native P5 evaluation descendant with exact frozen inputs and one-attempt replay."""
from collections import Counter
from datetime import datetime, timedelta, timezone
import argparse
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
import uuid

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
OWNER = '01a10839-a735-7bf2-a05a-68afadb52755'
POLICY = 'p5_blind_development_native_once_v1'
MANIFEST_SHA = '2bfa2df083cf3d39ccadac4a236665f10de62d73b3b72c541dee064b057f4ec7'
CONTENT_SHA = '142742d255306f672956952232f462b09269f1b22521e04023caeef63cee03b1'
LAMP = HERE.parent / 'hbq-matched-lamp-20261004/collector.py'
LAMP_SHA = 'd5a146f0ab615994792f422ef7dc01bac5f7dca9e38ac6c0a4a085c5b8ceb698'
PREPARE_SHA = '5e04e7f2e5d0d91ac5d5e2118085e4047f96e87108e4ef261679d473b010471b'
MIN_LAUNCH_FREE = 1024 ** 3
MIN_CONTACT_FREE = 256 * 1024 ** 2


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


sys.path.insert(0, str(HERE))
p = load('p5_native_preparation', HERE / 'prepare_evaluation.py')
canonical, digest = p.canonical, p.sha


def require(condition, message):
    if not condition:
        raise ValueError(message)


require(digest(LAMP.read_bytes()) == LAMP_SHA, 'Retained native collector changed')
c = load('p5_private_retained_lamp', LAMP)
h, t = c.h, c.t
pinned, record, write_bytes, within = h.pinned, h.record, h.write_bytes, h.within
SETTLED = h.SETTLED
sample_path, admission, native_answer = h.sample_path, h.admission, h.native_answer
CommitState, dispatch, execution_workers = h.CommitState, h.dispatch, h.execution_workers
output_preflight = h.output_preflight


def grok_contact_allowed(route, at_time=None):
    expiry = datetime.fromisoformat(route['cost_evidence']['expires_at'].replace('Z', '+00:00'))
    return (at_time or datetime.now(timezone.utc)) + timedelta(seconds=960) < min(h.q.CUTOFF, expiry)


def source_settings(manifest, root):
    runtime, pins = manifest['runtime']['sol'], manifest['external_pins']
    helper_path = Path(pins['secondary_helper_path'])
    require(helper_path.read_bytes() == pinned(root, 'implementation/secondary-helper.py',
            manifest['artifacts']['implementation/secondary-helper.py'])
            and digest(helper_path.read_bytes()) == pins['secondary_helper_sha256'], 'Secondary helper changed')
    cli = Path(pins['cli_path'])
    require(digest(cli.read_bytes()) == pins['cli_sha256'], 'Pinned CLI changed')
    helper = load('p5_static_secondary_helper', helper_path)
    home = helper.COLLECTION_HOME.resolve()
    require(helper.CLI.resolve() == cli.resolve() and home.name == 'cwr-sol-secondary'
            and home.parent.name == 'collection-accounts'
            and digest(str(home).encode()) == runtime['secondary_home_sha256']
            and runtime['expected_account_sha256'] == t.SECONDARY_ACCOUNT_SHA256
            and runtime['model'] == 'gpt-6.1-sol' and runtime['reasoning_effort'] == 'high'
            and runtime['receipt_policy'] == 'codex_native_rollout_v1', 'Frozen secondary runtime differs')
    # This is a typed compatibility projection, not a live account probe.
    return {'runtime': {'model': runtime['model'], 'reasoning': runtime['reasoning_effort'],
        'account_identity_sha256': runtime['expected_account_sha256'],
        'codex_home_sha256': runtime['secondary_home_sha256'], 'receipt_policy': runtime['receipt_policy']},
        'external_pins': {'secondary_helper_path_local_only': str(helper_path),
            'cli_path_local_only': str(cli), 'cli_sha256': pins['cli_sha256'],
            'collection_home_path_local_only': str(home)}}


def inputs(root, manifest, row):
    prompt = pinned(root, row['prompt_path'], manifest['artifacts'][row['prompt_path']])
    schema = pinned(root, row['schema_path'], manifest['artifacts'][row['schema_path']])
    require(digest(prompt) == row['prompt_sha256'] and len(prompt) == row['prompt_bytes']
            and digest(schema) == row['schema_sha256'] and len(schema) == row['schema_bytes'], 'Request payload differs')
    texts = {s['id']: pinned(root, s['input_path'], s).decode('utf-8') for s in row['sources']}
    require(len(texts) == len(row['sources']), 'Duplicate source identity')
    context_parts = []
    for descriptor in row['contexts']:
        raw = pinned(root, descriptor['path'], descriptor)
        require(raw in prompt, 'Declared context absent from frozen prompt')
        context_parts.append(raw.decode('utf-8'))
    require(all(text.encode() in prompt for text in texts.values()), 'Exact source absent from prompt')
    require([task['artifact_id'] for task in row['task_contracts']] == [s['id'] for s in row['sources']],
            'Task/source identities differ')
    projections = [part for descriptor, part in zip(row['contexts'], context_parts)
                   if descriptor['kind'] == 'task_context']
    require(len(projections) == len(row['task_contracts']), 'Task context coverage differs')
    from hbqrs import runner
    for contract, projection in zip(row['task_contracts'], projections):
        raw = pinned(root, contract['path'], manifest['artifacts'][contract['path']])
        require(digest(raw) == contract['sha256'], 'Task contract differs')
        task = json.loads(raw)
        require(task['artifact_id'] == contract['artifact_id'] and json.loads(projection)
                == runner._task_contract_judge_context(task), 'Exact task projection differs')
    return prompt, schema, texts, '\n'.join(context_parts)


def load_manifest(path, expected_sha, collector_sha, tools):
    raw = path.read_bytes()
    manifest, root = json.loads(raw), path.resolve().parent
    require(digest(raw) == expected_sha == MANIFEST_SHA
            and digest(Path(__file__).read_bytes()) == collector_sha, 'Exact manifest/collector pin differs')
    require(digest(canonical({k: v for k, v in manifest.items() if k != 'content_sha256'}))
            == manifest['content_sha256'] == CONTENT_SHA, 'Manifest content differs')
    require(manifest['stage'] == 'blind_development_evaluation' and manifest['provider_calls'] == 0
            and manifest['held_back_prose_released'] is False and manifest['utility_measured'] is False
            and manifest['runtime']['attempts'] == 1 and manifest['runtime']['automatic_retry'] is False
            and manifest['runtime']['actual_judge_tool_calls_required'] == 0
            and manifest['runtime']['endpoint_concurrency_cap_each'] == 10
            and manifest['runtime']['new_launch_min_free_bytes'] == MIN_LAUNCH_FREE
            and manifest['runtime']['before_contact_min_free_bytes'] == MIN_CONTACT_FREE
            and manifest['runtime']['timeout'] == 900, 'Frozen development execution controls differ')
    files = {name: pinned(root, name, meta) for name, meta in manifest['artifacts'].items()}
    require(digest((HERE / 'prepare_evaluation.py').read_bytes()) == PREPARE_SHA, 'P5 preparation changed')
    p.validate_design(manifest, files)
    current = {name: REPO / 'src/hbqrs' / (name + '.py')
               for name in ('core', 'runner', 'scoring_v2', 'codex_receipts')}
    current.update(schema_subset=tools / 'model_work_queue/adapters/json_schema_subset.py',
                   grok_exec=tools / 'model_work_queue/adapters/grok_exec.py',
                   prepare_evaluation=HERE / 'prepare_evaluation.py',
                   prepare_feedback=HERE / 'prepare_feedback.py', validate_evaluation=HERE / 'validate_evaluation.py')
    for name, local in current.items():
        require(local.read_bytes() == files['implementation/' + name + '.py'], 'Frozen runtime changed: ' + name)
    source_settings(manifest, root)
    subset = load('p5_frozen_response_subset', root / 'implementation/schema_subset.py')
    validator = load('p5_frozen_source_admission', root / 'implementation/validate_evaluation.py')
    receipts = load('p5_frozen_native_receipts', root / 'implementation/codex_receipts.py')
    checked_schemas = set()
    for row in manifest['requests']:
        require(digest(canonical({k: v for k, v in row.items() if k != 'request_sha256'}))
                == row['request_sha256'], 'Request commitment differs')
        require(manifest['artifacts'][row['retained_schema_path']]['sha256'] == row['retained_schema_sha256'],
                'Retained schema commitment differs')
        if row['schema_path'] not in checked_schemas:
            subset.validate_schema(json.loads(files[row['schema_path']]))
            checked_schemas.add(row['schema_path'])
        inputs(root, manifest, row)
    return manifest, root, subset, validator, receipts


def job_binding(manifest, root, manifest_sha, endpoint, tools, route=None, collector_sha=None, workers=1):
    require(endpoint in p.ENDPOINTS and 1 <= workers <= 10, 'Endpoint/workers allocation invalid')
    source = source_settings(manifest, root)
    runtime = dict(source['runtime']) if endpoint == 'sol' else dict(manifest['runtime']['grok'])
    if endpoint == 'sol':
        runtime.update(secondary_home_sha256=runtime['codex_home_sha256'], codex_receipt_policy='codex_native_rollout_v1')
    else:
        # The retained v5 parser compares this legacy request metadata. The adapter
        # executes Grok's native defaults; this field does not attest high reasoning.
        require(route is not None and route['reasoning_effort'] == 'high', 'Legacy route metadata differs')
        runtime.update(reasoning=route['reasoning_effort'], reasoning_selector_applied=False, reasoning_attested=False)
    binding = {'schema_version': 1, 'policy': POLICY, 'manifest_sha256': manifest_sha, 'endpoint': endpoint,
        'collector_sha256': collector_sha or digest(Path(__file__).read_bytes()),
        'retained_lamp_collector_sha256': LAMP_SHA, 'retained_parallel_collector_sha256': c.HANNA_SHA,
        'retained_poetry_collector_sha256': h.POETRY_SHA, 'retained_native_transport_sha256': h.q.TRANSPORT_SHA,
        'runtime': runtime, 'timeout_seconds': 900, 'workers': workers,
        'owner_execution_amendment': {'allocated_workers': workers, 'project_global_max_simultaneous_per_endpoint': 10,
            'launching_owner_must_verify_global_headroom': True, 'stop_new_dispatch_and_settle_inflight': True},
        'tools_root_local_only': str(tools.resolve()), 'attempts_per_logical_sample': 1,
        'automatic_retries': 0, 'no_ambiguous_resend': True,
        'planned_endpoint_requests': 1296, 'planned_study_requests': 2592,
        'artifacts_commitment_sha256': digest(canonical(manifest['artifacts'])),
        'design_sha256': manifest['design_sha256'], 'analysis_sha256': manifest['analysis_sha256'],
        'payload_classification': 'public_synthetic',
        'outbound_artifacts': 'Only selected frozen AI development prose, neutral task/work contexts, prompts and response schemas; no feedback, intervention metadata, held-back prose or human references',
        'preparation_grants_execution_authority': False, 'held_back_prose_released': False,
        'native_execution_proven': False, 'source_helper_sha256': manifest['external_pins']['secondary_helper_sha256'],
        'cli_sha256': manifest['external_pins']['cli_sha256'],
        'runner_sha256': manifest['artifacts']['implementation/runner.py']['sha256'],
        'receipt_reader_sha256': manifest['artifacts']['implementation/codex_receipts.py']['sha256'],
        'admission_sha256': manifest['artifacts']['implementation/validate_evaluation.py']['sha256'],
        'actual_judge_tool_calls_required': 0, 'new_launch_min_free_bytes': MIN_LAUNCH_FREE,
        'before_contact_min_free_bytes': MIN_CONTACT_FREE, 'cost_token_cache_attestation': False}
    for name, relative in {'account_probe': 'adaptive_settings/account_probe.py', 'broker': 'model_work_queue/broker.py',
                           'grok_adapter': 'model_work_queue/adapters/grok_exec.py'}.items():
        binding[name + '_sha256'] = digest((tools / relative).read_bytes())
    if endpoint == 'grok':
        require(route['name'] == 'grok-build-grok-4.7' and route['model'] == 'grok-4.7'
                and route['nonvisual_transport_contract'] == 'grok_nonvisual_history_v5'
                and route['nonvisual_max_turns'] == 1 and route['timeout_seconds'] == 900
                and route['max_concurrency'] == 10 and route['zero_charge'] is True
                and route['armed'] is True and route['trusted'] is True
                and 'public_synthetic' in route['allowed_payload_classes'], 'Reviewed synthetic zero-charge v5 route differs')
        binding.update(route=route, route_sha256=digest(canonical(route).rstrip(b'\n')),
                       campaign_deadline=h.q.CUTOFF.isoformat(), deadline_margin_seconds=960)
    return binding


def verify_job_binding(output, manifest, root, manifest_sha, endpoint, tools):
    binding = json.loads((output / 'job.json').read_bytes())
    require(binding == job_binding(manifest, root, manifest_sha, endpoint, tools, binding.get('route'),
            workers=binding['workers']) and (output / 'frozen-manifest.json').read_bytes()
            == (root / 'manifest.json').read_bytes(), 'Existing immutable job/freeze differs')
    if endpoint == 'sol':
        require(json.loads((output / 'account-binding.json').read_bytes()) == t.account_receipt(binding), 'Account receipt differs')
    return binding


# Preserve both collection and replay globals inside this private module instance.
h.inputs = inputs
h.q.inputs = inputs
h.grok_contact_allowed = grok_contact_allowed
collect_one, replay, inventory = h.collect_one, h.replay, h.inventory


def development_gate(manifest, root, manifest_sha, tools, outputs, receipts, subset, validator):
    counts, identities = {}, set()
    for endpoint in p.ENDPOINTS:
        output = outputs[endpoint]
        if not output.exists():
            counts[endpoint] = {'untouched': 1296, 'verified_terminal': 0, 'states': {}}
            continue
        binding = verify_job_binding(output, manifest, root, manifest_sha, endpoint, tools)
        pending, states, own_ids = inventory(manifest, binding, root, output, receipts, subset, validator)
        require(not identities & own_ids, 'Native identity reused across endpoints')
        identities.update(own_ids)
        counts[endpoint] = {'untouched': len(pending), 'verified_terminal': len(states), 'states': dict(Counter(states))}
    ready = all(v['untouched'] == 0 and v['verified_terminal'] == 1296
                and sum(v['states'].get(s, 0) for s in SETTLED) == 1296 for v in counts.values())
    return {'policy': POLICY, 'manifest_sha256': manifest_sha, 'planned': 2592, 'endpoints': counts,
        'complete_native_development_admission': ready, 'held_back_prose_released': False,
        'explicit_recorded_controller_decision_and_separate_unchanged_mechanism_freeze_still_required': True,
        'utility_measured': False, 'provider_calls': 0}


def disk_guard(output, minimum):
    require(not (output / 'STOP').exists(), 'Owned STOP prevents launch/contact')
    require(shutil.disk_usage(output.parent).free >= minimum, 'Disk guard prevents launch/contact')


def owned_output(output, root, tools):
    require(os.environ.get('CODEX_THREAD_ID') == OWNER and output.is_relative_to(root.parent), 'Exact owning task/output required')
    sys.path.insert(0, str(tools))
    from working_sentinel import read_sentinel
    require(any(claim['task_id'] == claim['session_id'] == OWNER
        and claim['work_id'] == 'cwr-p5-ai-revision-output-20261006'
        and claim['human_owner_id'] == 'Haile' and claim['host_id'] == 'local'
        and claim['workspace_instance_id'] == 'cwr-resume-control-20260919-r1'
        and claim['reservations'] == [{'kind': 'tree', 'path': 'successor-program-20261004/revision-utility'}]
        for claim in read_sentinel(root.parent / '.working')['claims']), 'Exact P5 output claim required')


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    for name in ('manifest', 'tools-root', 'results-dir', 'route-root', 'sol-results-dir', 'grok-results-dir'):
        parser.add_argument('--' + name, type=Path, required=name in ('manifest', 'tools-root'))
    for name in ('manifest-sha256', 'collector-sha256'):
        parser.add_argument('--' + name, required=True)
    parser.add_argument('--endpoint', choices=p.ENDPOINTS)
    parser.add_argument('--route-sha256')
    parser.add_argument('--workers', type=int, required=True)
    parser.add_argument('--owner-global-headroom-verified', action='store_true')
    parser.add_argument('--limit', type=int)
    parser.add_argument('--validate-only', action='store_true')
    parser.add_argument('--development-release-check', action='store_true')
    args = parser.parse_args()
    executing = not (args.validate_only or args.development_release_check)
    require(1 <= args.workers <= 10 and execution_workers(sys.argv) == args.workers, 'Explicit workers must be 1..10')
    require(not executing or args.owner_global_headroom_verified, 'Launching owner must verify shared headroom')
    require(args.limit is None or args.limit > 0, 'Limit must be positive')
    sys.path.insert(0, str(REPO / 'src'))
    sys.path.insert(0, str(args.tools_root))
    manifest, root, subset, validator, receipts = load_manifest(args.manifest, args.manifest_sha256,
                                                             args.collector_sha256, args.tools_root.resolve())
    if args.development_release_check:
        require(args.sol_results_dir is not None and args.grok_results_dir is not None, 'Both result roots required')
        outputs = {'sol': args.sol_results_dir.resolve(), 'grok': args.grok_results_dir.resolve()}
        for output in outputs.values():
            output_preflight(output, root)
        print(json.dumps(development_gate(manifest, root, args.manifest_sha256, args.tools_root,
                                         outputs, receipts, subset, validator), sort_keys=True))
        return 0
    require(args.endpoint is not None and args.results_dir is not None, 'Endpoint/results required')
    output = args.results_dir.resolve()
    output_preflight(output, root)
    route = None
    if args.endpoint == 'grok':
        require(args.route_root is not None and args.route_sha256 is not None, 'Exact reviewed route required')
        matches = [r for r in json.loads((args.route_root / 'routes.json').read_bytes())['routes']
                   if r['name'] == 'grok-build-grok-4.7']
        require(len(matches) == 1 and digest(canonical(matches[0]).rstrip(b'\n')) == args.route_sha256, 'Route pin differs')
        route = matches[0]
    binding = job_binding(manifest, root, args.manifest_sha256, args.endpoint, args.tools_root,
                          route, args.collector_sha256, args.workers)
    if output.exists():
        require(verify_job_binding(output, manifest, root, args.manifest_sha256, args.endpoint, args.tools_root)
                == binding, 'Existing allocation differs')
    pending, states, native_ids = inventory(manifest, binding, root, output, receipts, subset, validator)
    if args.validate_only:
        print(json.dumps({'state': 'provider_free_validated', 'endpoint': args.endpoint,
            'manifest_sha256': args.manifest_sha256, 'job_binding_sha256': digest(canonical(binding)),
            'planned': 1296, 'study_planned': 2592, 'workers': args.workers, 'untouched': len(pending),
            'terminal_states': dict(Counter(states)), 'provider_calls': 0, 'account_probe_performed': False,
            'results_written': False, 'native_execution_proven': False, 'held_back_prose_released': False}, sort_keys=True))
        return 0
    require(all(state in SETTLED for state in states), 'Occupied failure needs owning reconciliation; no resend')
    if not pending:
        return 0
    owned_output(output, root, args.tools_root)
    disk_guard(output, MIN_LAUNCH_FREE)
    helper = call_codex = broker = None
    if args.endpoint == 'sol':
        source = source_settings(manifest, root)
        helper = load('p5_execution_secondary_helper', Path(source['external_pins']['secondary_helper_path_local_only']))
        env = t.secondary_binding(source, helper)
        os.environ.clear()
        os.environ.update(env)
        from adaptive_settings.account_probe import probe
        from hbqrs import runner
        t.secondary_binding(source, helper, probe(helper.CLI))
        call_codex = runner._call_codex
    else:
        require(grok_contact_allowed(route), 'Route expiry/deadline prevents contact')
        from model_work_queue.broker import Broker
        broker = Broker(args.route_root.resolve())
    if not output.exists():
        output.mkdir(parents=True, exist_ok=False)
        record(output / 'job.json', binding)
        write_bytes(output / 'frozen-manifest.json', args.manifest.read_bytes())
    if args.endpoint == 'sol' and not (output / 'account-binding.json').exists():
        record(output / 'account-binding.json', t.account_receipt(binding))
    name = 'execution-invocation-' + str(uuid.uuid4()) + '.json'
    raw = canonical({'argv': sys.argv, 'workers': args.workers,
        'job_sha256': digest((output / 'job.json').read_bytes()), 'time': datetime.now(timezone.utc).isoformat(),
        'owner_global_headroom_confirmation': True})
    write_bytes(output / name, raw)
    invocation = {'path': name, 'sha256': digest(raw), 'bytes': len(raw)}
    commit = CommitState(native_ids, invocation)

    # Keep the original account/native/contact/admission callbacks, adding disk/STOP
    # checks immediately before the unchanged provider call. One attempt per slot.
    def guarded(call, callback_name):
        def run(*values, **kwargs):
            before = kwargs[callback_name]
            def contact():
                disk_guard(output, MIN_CONTACT_FREE)
                require(args.endpoint != 'grok' or grok_contact_allowed(route), 'Route expired before contact')
                before()
                disk_guard(output, MIN_CONTACT_FREE)
            kwargs[callback_name] = contact
            return call(*values, **kwargs)
        return run

    if call_codex is not None:
        call_codex = guarded(call_codex, 'before_provider_attempt')
    if broker is not None:
        broker.run_grok_native_request = guarded(broker.run_grok_native_request, 'before_contact')
    execute = lambda row: collect_one(row, manifest, binding, root, output, subset, validator, receipts,
                                     helper, call_codex, broker, commit)
    settled = dispatch(pending[:args.limit], args.workers, execute, commit, lambda: (output / 'STOP').exists(),
        lambda row, state: print(json.dumps({'ordinal': row['endpoint_ordinal'], 'state': state}), flush=True))
    record(output / ('dispatch-terminal-' + str(uuid.uuid4()) + '.json'), {'policy': POLICY, 'workers': args.workers,
        'execution_invocation': invocation, 'settled_this_execution': len(settled), 'states': dict(Counter(settled)),
        'stopped': commit.stop.is_set(), 'inflight_at_terminal': 0, 'automatic_retries': 0,
        'held_back_prose_released': False})
    return 3 if commit.stop.is_set() else 0


if __name__ == '__main__':
    raise SystemExit(main())
