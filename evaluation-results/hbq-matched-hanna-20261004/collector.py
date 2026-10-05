"""Native HANNA collection: bounded owner-allocated parallelism, one attempt, no label reads."""
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from datetime import datetime, timezone
import argparse
import json
import os
from pathlib import Path
import sys
import threading
import uuid
import importlib.util

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('hanna_collection_prepare', HERE / 'prepare.py')
p = importlib.util.module_from_spec(spec); spec.loader.exec_module(p)
POETRY = HERE.parent / 'hbq-poetry-human-reference-v1/collector.py'
POETRY_SHA = 'e06cc12c339d6eadadd8f7baa445d93b1777a43d21a57f33edc48b0d69573dd7'
p.checked(POETRY, POETRY_SHA)
# Private module instance: adaptations never modify the retained collector or its live instances.
q = p.load_module('hanna_retained_poetry_collection', POETRY)
t = q.t
POLICY = 'matched_hanna_native_parallel_owner_amendment_v1'
MANIFEST_SHA = 'd4f8c8c7847b7715d97ccb9d0a46fdc0651e79777f17309019fc2e75ad02bedc'
canonical, digest, require = p.canonical, p.digest, p.require
pinned, record, write_bytes, within = t.pinned, t.record, t.write_bytes, t.within
SETTLED, TERMINAL_STATES = q.SETTLED, q.TERMINAL_STATES
sample_path, admission = q.sample_path, q.admission
grok_contact_allowed = q.grok_contact_allowed


def source_settings(manifest, root):
    raw = pinned(root, 'private/source-runtime-manifest.json', manifest['artifacts']['private/source-runtime-manifest.json'])
    require(digest(raw) == manifest['generation_manifest_file_sha256'] == p.RUNTIME_SHA, 'Source runtime pin differs')
    source = json.loads(raw)
    require(source['runtime']['model'] == 'gpt-6.1-sol' and source['runtime']['reasoning'] == 'high'
            and source['runtime']['account_identity_sha256'] == t.SECONDARY_ACCOUNT_SHA256
            and source['runtime']['receipt_policy'] == 'codex_native_rollout_v1', 'Secondary runtime differs')
    pins = source['external_pins']
    require(manifest['external_pins'] == pins, 'External runtime pins differ')
    p.checked(Path(pins['secondary_helper_path_local_only']), source['artifacts']['implementation/secondary-helper.py']['sha256'])
    p.checked(Path(pins['cli_path_local_only']), pins['cli_sha256'], pins['cli_bytes'])
    home = Path(pins['collection_home_path_local_only']).resolve()
    require(home.name == 'cwr-sol-secondary' and home.parent.name == 'collection-accounts'
            and digest(str(home).encode()) == source['runtime']['codex_home_sha256'], 'Secondary home differs')
    return source


def inputs(root, manifest, row):
    from hbqrs import runner
    prompt = pinned(root, row['prompt_path'], manifest['artifacts'][row['prompt_path']])
    schema = pinned(root, row['schema_path'], manifest['artifacts'][row['schema_path']])
    texts = {s['id']: pinned(root, s['input_path'], s).decode('utf-8') for s in row['sources']}
    pretty = pinned(root, row['task_context']['path'], row['task_context']).decode('utf-8')
    origin = pinned(root, row['originating_prompt']['path'], row['originating_prompt']).decode('utf-8')
    require(pretty.encode() in prompt and origin.encode() in prompt
            and all(text.encode() in prompt for text in texts.values()), 'Literal source/context/origin absent from outbound prompt')
    task = json.loads(pinned(root, row['task_contract_path'], manifest['artifacts'][row['task_contract_path']]))
    require(pretty == json.dumps(runner._task_contract_judge_context(task), ensure_ascii=False, indent=2), 'Exact pretty context differs')
    return prompt, schema, texts, pretty + '\n' + origin


def validate_design(manifest, files):
    from hbqrs import core
    require(manifest['study_id'] == p.STUDY and manifest['execution_authority'] is False
            and manifest['labels_read'] is False and manifest['labels_released'] is False
            and manifest['provider_calls_made'] == 0 and manifest['scoring']['candidate'] is None, 'Source-only/closed-label preparation differs')
    require(manifest['runtime']['timeout_seconds'] == 900 and manifest['runtime']['workers_initially'] == 1
            and manifest['runtime']['batch_attempts'] == 1 and manifest['runtime']['automatic_retries'] == 0, 'Prepared runtime differs')
    require(manifest['counts']['requests_total'] == 6864 and manifest['counts']['requests_per_endpoint'] == 3432
            and manifest['human_gate']['required_verified_terminal_requests'] == 6864
            and manifest['human_gate']['release_granted'] is False, 'Full planned denominator differs')
    banks = {}
    for name, raw in files.items():
        if name.startswith('compiled/') and name != 'compiled/canonical.json':
            ids = [x['question']['id'] for x in core.compiled_questions(json.loads(raw))]
            require(len(ids) == len(set(ids)) == 171, 'Complete per-source bank differs')
            banks[name] = ids
    require(len(banks) == 120, 'Complete source cohort differs')
    endpoints = {}
    for endpoint in p.ENDPOINTS:
        rows = [r for r in manifest['requests'] if r['endpoint'] == endpoint]
        require(len(rows) == 3432 and [r['endpoint_ordinal'] for r in rows] == list(range(1, 3433))
                and Counter(r['arm'] for r in rows) == Counter(manifest['counts']['by_arm_per_endpoint']), 'Matched endpoint cardinality differs')
        require(len({r['logical_sample_id'] for r in rows}) == len(rows), 'Duplicate logical request')
        groups = defaultdict(list)
        endpoints[endpoint] = {r['logical_sample_id'] for r in rows}
        for row in rows:
            require(digest(canonical({k: v for k, v in row.items() if k != 'request_sha256'})) == row['request_sha256'], 'Request commitment differs')
            condition = {k: v for k, v in row.items() if k not in {'request_sha256', 'logical_sample_id', 'endpoint', 'endpoint_ordinal', 'ordinal'}}
            require(digest(canonical(condition)) == row['logical_sample_id'], 'Logical condition commitment differs')
            groups[(row['artifact_id'], row['repeat'])].append(row)
        require(len(groups) == 132, 'Full cohort/repeat membership differs')
        require({aid for aid, cycle in groups if cycle == 0} == {Path(n).stem for n in banks}, 'Baseline cohort incomplete')
        for cycle in (1, 2):
            require({aid for aid, c in groups if c == cycle} == set(manifest['sentinel_ids']), 'Sentinel repeat membership differs')
        for (aid, _), group in groups.items():
            require(Counter(r['arm'] for r in group) == Counter({'hbq': 22, 'ttcw14': 1, 'holistic': 1, 'compact': 1, 'oregon': 1}), 'Matched arm coverage differs')
            hbq = sorted((r for r in group if r['arm'] == 'hbq'), key=lambda r: r['batch'])
            require([r['batch'] for r in hbq] == list(range(1, 23))
                    and [qid for r in hbq for qid in r['question_ids']] == banks['compiled/' + aid + '.json']
                    and all(len(r['question_ids']) == 8 for r in hbq[:-1]) and len(hbq[-1]['question_ids']) == 3, 'Ordered full171 bank differs')
            require(len({canonical(r['task_context']) for r in group}) == 1
                    and len({canonical(r['originating_prompt']) for r in group}) == 1
                    and len({canonical(r['sources']) for r in group}) == 1, 'Arms do not share source/context')
    require(endpoints['sol'] == endpoints['grok'], 'Matched logical endpoint membership differs')


def load_manifest(path, expected_sha, collector_sha, tools):
    raw = path.read_bytes(); root = path.resolve().parent; manifest = json.loads(raw)
    require(digest(raw) == expected_sha == MANIFEST_SHA and digest(Path(__file__).read_bytes()) == collector_sha, 'Exact manifest/collector pin differs')
    p.checked(q.TRANSPORT_PATH, q.TRANSPORT_SHA)
    require(digest(canonical({k: v for k, v in manifest.items() if k != 'manifest_content_sha256'})) == manifest['manifest_content_sha256'], 'Manifest content commitment differs')
    files = {name: pinned(root, name, meta) for name, meta in manifest['artifacts'].items()}
    sys.path.insert(0, str(p.REPO / 'src')); validate_design(manifest, files)
    source = source_settings(manifest, root)
    require(tools.resolve() == Path(source['external_pins']['tools_root_local_only']).resolve(), 'Tools root differs')
    sys.path.insert(0, str(tools))
    for current, frozen in [(HERE / 'prepare.py', 'implementation/prepare.py'),
            (HERE.parent / 'hbq-matched-ttcw-20261004/validate_response.py', 'implementation/validate_response.py'),
            (p.REPO / 'src/hbqrs/core.py', 'implementation/core.py'),
            (p.REPO / 'src/hbqrs/runner.py', 'implementation/runner.py'),
            (p.REPO / 'src/hbqrs/scoring_v2.py', 'implementation/scoring_v2.py'),
            (p.REPO / 'src/hbqrs/codex_receipts.py', 'implementation/codex_receipts.py')]:
        require(digest(current.read_bytes()) == manifest['artifacts'][frozen]['sha256'], 'Frozen implementation differs')
    subset = p.load_module('hanna_frozen_subset', root / 'implementation/schema_subset.py')
    validator = p.load_module('hanna_frozen_validator', root / 'implementation/validate_response.py')
    receipts = p.load_module('hanna_frozen_receipts', root / 'implementation/codex_receipts.py')
    for schema_path in {row['schema_path'] for row in manifest['requests']}:
        subset.validate_schema(json.loads(files[schema_path]))
    seen = set()
    for row in manifest['requests']:
        key = canonical({name: row[name] for name in ('prompt_path', 'schema_path', 'sources', 'task_context', 'originating_prompt', 'task_contract_path')})
        if key not in seen:
            inputs(root, manifest, row); seen.add(key)
    return manifest, root, subset, validator, receipts


def job_binding(manifest, root, manifest_sha, endpoint, tools, route=None, collector_sha=None, workers=1):
    require(endpoint in p.ENDPOINTS and 1 <= workers <= 10, 'Endpoint/workers allocation invalid')
    source = source_settings(manifest, root)
    runtime = dict(source['runtime']) if endpoint == 'sol' else {'model': 'grok-4.7', 'reasoning': 'high'}
    if endpoint == 'sol':
        runtime.update(secondary_home_sha256=runtime['codex_home_sha256'], codex_receipt_policy='codex_native_rollout_v1')
    binding = {'schema_version': 1, 'policy': POLICY, 'manifest_sha256': manifest_sha, 'endpoint': endpoint,
        'collector_sha256': collector_sha or digest(Path(__file__).read_bytes()), 'retained_poetry_collector_sha256': POETRY_SHA,
        'retained_native_transport_sha256': q.TRANSPORT_SHA, 'runtime': runtime, 'timeout_seconds': 900, 'workers': workers,
        'owner_execution_amendment': {'prepared_workers_initially': 1, 'allocated_workers': workers,
            'project_global_max_simultaneous_per_endpoint': 10, 'launching_owner_must_verify_global_headroom': True,
            'stop_new_dispatch_and_settle_inflight': True},
        'workers_cli_argument': ['--workers', str(workers)], 'tools_root_local_only': str(tools.resolve()),
        'attempts_per_logical_sample': 1, 'automatic_retries': 0, 'no_ambiguous_resend': True,
        'planned_endpoint_requests': 3432, 'planned_study_requests': 6864,
        'source_generation_manifest_sha256': manifest['generation_manifest_file_sha256'],
        'artifacts_commitment_sha256': digest(canonical(manifest['artifacts'])), 'human_label_gate': manifest['human_gate'],
        'payload_classification': 'public_repo', 'outbound_artifacts': manifest['disclosure'],
        'preparation_grants_execution_authority': False, 'human_targets_opened': False, 'native_execution_proven': False,
        'source_helper_sha256': source['artifacts']['implementation/secondary-helper.py']['sha256'],
        'cli_sha256': source['external_pins']['cli_sha256'], 'runner_sha256': manifest['artifacts']['implementation/runner.py']['sha256'],
        'receipt_reader_sha256': manifest['artifacts']['implementation/codex_receipts.py']['sha256'],
        'admission_sha256': manifest['artifacts']['implementation/validate_response.py']['sha256']}
    for name, relative in {'account_probe': 'adaptive_settings/account_probe.py', 'broker': 'model_work_queue/broker.py',
                           'grok_adapter': 'model_work_queue/adapters/grok_exec.py'}.items():
        binding[name + '_sha256'] = digest((tools / relative).read_bytes())
    if endpoint == 'grok':
        require(route is not None and route['name'] == 'grok-build-grok-4.7' and route['model'] == 'grok-4.7'
                and route['reasoning_effort'] == 'high' and route['timeout_seconds'] == 900
                and route['zero_charge'] is True and route['armed'] is True and 'public_repo' in route['allowed_payload_classes'], 'Reviewed zero-charge Grok route differs')
        binding.update(route=route, route_sha256=digest(canonical(route).rstrip(b'\n')),
                       campaign_deadline=q.CUTOFF.isoformat(), deadline_margin_seconds=900)
    return binding


def verify_job_binding(output, manifest, root, manifest_sha, endpoint, tools):
    binding = json.loads((output / 'job.json').read_bytes())
    require(binding == job_binding(manifest, root, manifest_sha, endpoint, tools, binding.get('route'), workers=binding['workers'])
            and (output / 'frozen-manifest.json').read_bytes() == (root / 'manifest.json').read_bytes(), 'Existing job/raw manifest differs')
    if endpoint == 'sol':
        require(json.loads((output / 'account-binding.json').read_bytes()) == t.account_receipt(binding), 'Account receipt differs')
    return binding


def native_answer(sample, row, binding, prompt, schema, receipts):
    if row['endpoint'] == 'grok':
        adapter_path = Path(binding['tools_root_local_only']) / 'model_work_queue/adapters/grok_exec.py'
        p.checked(adapter_path, binding['grok_adapter_sha256'])
        from model_work_queue.adapters.grok_exec import _parse_grok_envelope
        native = json.loads((sample / 'native-result.json').read_bytes())
        runtime = native['result']['runtime']; contract = runtime['execution_contract']
        require(runtime['adapter_version'] == 5 and runtime['execution_policy'] == 'bounded_nonvisual_deny_wins_attested'
                and contract['tools'] == 'deny_wins_none_attested' and contract['max_turns'] == 1
                and contract['staged_prompt_sha256'] == digest(prompt) and contract['staged_prompt_byte_length'] == len(prompt)
                and contract['nonvisual_transport_contract']['name'] == 'grok_nonvisual_history_v5'
                and contract['nonvisual_transport_contract_sha256'] == digest(canonical(contract['nonvisual_transport_contract']).rstrip(b'\n'))
                and runtime['nonvisual_max_turns'] == 1 and len(runtime['tool_policy_attestation_hash']) == 64
                and runtime['transport']['exit_code'] == 0, 'Gv5 native no-tool/transport attestation differs')
        raw = (sample / 'native-envelope.json').read_bytes()
        session = json.loads((sample / 'native-identity.json').read_bytes())['session_id']
        answer, identities, usage = _parse_grok_envelope(raw, model=binding['runtime']['model'],
            reported_model=binding['route']['reported_model'], session_id=session, schema=json.loads(schema), max_turns=1, exact_turns=True)
        require(answer == native['result']['output'] and all(runtime[k] == v for k, v in identities.items())
                and runtime['usage_telemetry'] == usage, 'Retained native Grok parser projection differs')
        require(json.loads((sample / 'attempt-started.json').read_bytes())['session_id']
                == json.loads((sample / 'native-identity.json').read_bytes())['session_id'], 'Own started Grok session differs')
    return q_native_answer(sample, row, binding, prompt, schema, receipts)


# Retained replay checks all saved raw artifacts, own prompt/account/native identity and admission.
q_native_answer = q.native_answer
q.inputs = inputs; q.native_answer = native_answer
q_replay = q.replay


def execution_workers(argv):
    values = []
    for index, argument in enumerate(argv):
        if argument == '--workers':
            require(index + 1 < len(argv), 'Execution workers argument missing')
            values.append(argv[index + 1])
        elif argument.startswith('--workers='):
            values.append(argument.split('=', 1)[1])
    require(len(values) == 1, 'Execution workers argument must occur once')
    return int(values[0])


def replay(sample, row, manifest, binding, root, receipts, subset, validator):
    terminal, answer = q_replay(sample, row, manifest, binding, root, receipts, subset, validator)
    if terminal['state'] in SETTLED:
        started = json.loads((sample / 'attempt-started.json').read_bytes())
        invocation = json.loads(pinned(sample.parent, started['execution_invocation']['path'], started['execution_invocation']))
        require(invocation['job_sha256'] == terminal['job_sha256'] and invocation['workers'] == binding['workers']
                and execution_workers(invocation['argv']) == binding['workers']
                and '--owner-global-headroom-verified' in invocation['argv'], 'Execution argv/allocation binding differs')
    return terminal, answer


q.replay = replay
inventory = q.inventory


class CommitState:
    def __init__(self, native_ids=(), invocation=None):
        self.lock = threading.Lock(); self.native_ids = set(native_ids); self.stop = threading.Event(); self.invocation = invocation

    def reserve_identity(self, identity):
        with self.lock:
            require(identity not in self.native_ids, 'Duplicate own native UUID')
            self.native_ids.add(identity)


def collect_one(row, manifest, binding, root, output, subset, validator, receipts,
                helper=None, call_codex=None, broker=None, commit=None):
    commit = commit or CommitState()
    sample = sample_path(output, row); sample.mkdir(exist_ok=False); record(sample / 'condition.json', row)
    prompt, schema, texts, context = inputs(root, manifest, row)
    for name, raw in [('prompt.txt', prompt), ('schema.json', schema), ('task-context.json', context.encode())]:
        write_bytes(sample / name, raw)
    for tid, text in texts.items(): write_bytes(sample / 'sources' / (tid + '.txt'), text.encode())
    session = str(uuid.uuid4()) if row['endpoint'] == 'grok' else None
    record(sample / 'native-identity.json', {'session_id': session, 'logical_sample_id': row['logical_sample_id']})
    terminal = {'manifest_sha256': binding['manifest_sha256'], 'logical_sample_id': row['logical_sample_id'],
                'no_resend': True, 'job_sha256': digest((output / 'job.json').read_bytes()), 'accepted': False}

    def before():
        require(not commit.stop.is_set() and not (output / 'STOP').exists(), 'STOP prevents new contact')
        require(row['endpoint'] != 'grok' or grok_contact_allowed(binding['route']), 'Route expiry/deadline prevents contact')
        require(commit.invocation is not None, 'Own execution argv receipt missing')
        pinned(output, commit.invocation['path'], commit.invocation)
        terminal['attempt_id'] = str(uuid.uuid4())
        record(sample / 'attempt-started.json', {'time': datetime.now(timezone.utc).isoformat(), 'attempt_id': terminal['attempt_id'],
            'attempt': 1, 'no_resend': True, 'manifest_sha256': binding['manifest_sha256'], 'logical_sample_id': row['logical_sample_id'],
            'job_sha256': terminal['job_sha256'], 'prompt_sha256': row['prompt_sha256'], 'schema_sha256': row['schema_sha256'],
            'execution_invocation': commit.invocation,
            'session_id': session, 'account_binding_sha256': digest((output / 'account-binding.json').read_bytes()) if row['endpoint'] == 'sol' else None})
    try:
        if row['endpoint'] == 'sol':
            content, native = call_codex(executable=str(helper.CLI), model=binding['runtime']['model'], reasoning='high',
                prompt=prompt.decode(), output_dir=sample, response_schema=sample / 'schema.json', batch_number=1, attempt_number=1,
                timeout=900, before_provider_attempt=before, codex_receipt_policy='codex_native_rollout_v1')
        else:
            native = broker.run_grok_native_request(binding['route']['name'], {'prompt': prompt.decode()}, output_schema=json.loads(schema),
                nonvisual_max_turns=1, session_id=session, before_contact=before, expected_route_sha256=binding['route_sha256'])
        record(sample / 'native-result.json', native)
        if row['endpoint'] == 'grok':
            if native['state'] != 'completed':
                terminal['state'] = native['state'] if native['state'] in TERMINAL_STATES - SETTLED else 'unadmitted_no_resend'
                raise RuntimeError('Native Grok attempt did not complete')
            write_bytes(sample / 'native-envelope.json', broker.read_grok_native_envelope(native['result']['native_envelope_artifact']))
        answer, identity, parseable = native_answer(sample, row, binding, prompt, schema, receipts)
        require((sample / 'attempt-started.json').is_file(), 'Own contact-start receipt missing')
        if row['endpoint'] == 'sol':
            if parseable: require(answer == json.loads(content), 'Returned content differs from native final')
            else: require(content == within(sample, native['provider_artifacts']['codex_message']['path']).read_bytes().decode().replace('\r\n', '\n').replace('\r', '\n'), 'Returned malformed final differs')
        commit.reserve_identity(identity)
        terminal['native_thread_id'] = identity
        record(sample / 'response.json', answer); record(sample / 'native-final-parse.json', {'json_parseable': parseable})
        accepted = admission(root, row, manifest, answer, schema, texts, context, subset, validator)
        record(sample / 'acceptance.json', accepted)
        terminal.update(state='accepted' if accepted['accepted'] else 'semantic_rejected', accepted=accepted['accepted'], abstention=accepted['abstention'])
        terminal['artifact_sha256s'] = {x.relative_to(sample).as_posix(): digest(x.read_bytes()) for x in sample.rglob('*') if x.is_file()}
    except BaseException as error:
        commit.stop.set()
        terminal.update(state=terminal.get('state') if terminal.get('state') in TERMINAL_STATES - SETTLED else 'unadmitted_no_resend', accepted=False, error_class=type(error).__name__)
        if hasattr(error, 'provider_record'): terminal['provider_record'] = error.provider_record
        terminal['retained_artifacts'] = {x.relative_to(sample).as_posix(): {'sha256': digest(x.read_bytes()), 'bytes': x.stat().st_size} for x in sample.rglob('*') if x.is_file()}
        with commit.lock: record(sample / 'terminal.json', terminal)
        if not isinstance(error, Exception): raise
        return terminal['state']
    with commit.lock: record(sample / 'terminal.json', terminal)
    return terminal['state']


def dispatch(rows, workers, execute, commit, stopped=lambda: False, on_result=lambda row, state: None):
    require(1 <= workers <= 10, 'Workers must be 1..10')
    remaining = iter(rows); inflight = {}; states = []; exhausted = False
    with ThreadPoolExecutor(max_workers=workers) as pool:
        while inflight or not exhausted:
            while not exhausted and len(inflight) < workers and not commit.stop.is_set() and not stopped():
                try: row = next(remaining)
                except StopIteration: exhausted = True; break
                inflight[pool.submit(execute, row)] = row
            if stopped(): commit.stop.set()
            if not inflight: break
            try: done, _ = wait(inflight, return_when=FIRST_COMPLETED)
            except BaseException:
                commit.stop.set(); raise
            for future in done:
                row = inflight.pop(future)
                try: state = future.result()
                except BaseException:
                    commit.stop.set()
                    # The executor settles other already-started calls before propagating interruption.
                    for other in inflight: other.result()
                    raise
                states.append(state); on_result(row, state)
                if state not in SETTLED: commit.stop.set()
    return states


def label_release_gate(manifest, root, manifest_sha, tools, outputs, receipts, subset, validator, explicit_release=False):
    counts = {}; identities = set(); missing = 0
    for endpoint in p.ENDPOINTS:
        output = outputs[endpoint]
        if not output.exists(): counts[endpoint] = {'untouched': 3432, 'verified_terminal': 0, 'states': {}}; missing += 3432; continue
        binding = verify_job_binding(output, manifest, root, manifest_sha, endpoint, tools)
        pending, states, native_ids = inventory(manifest, binding, root, output, receipts, subset, validator)
        require(not identities & native_ids, 'Native UUID reused across endpoints'); identities.update(native_ids)
        counts[endpoint] = {'untouched': len(pending), 'verified_terminal': len(states), 'states': dict(Counter(states))}; missing += len(pending)
    ready = missing == 0 and sum(c['verified_terminal'] for c in counts.values()) == 6864
    return {'policy': 'matched_hanna_postprediction_explicit_label_gate_v1', 'manifest_sha256': manifest_sha, 'planned': 6864,
        'endpoints': counts, 'all_planned_verified_terminal': ready, 'explicit_postprediction_release': explicit_release,
        'human_release_eligible': ready and explicit_release, 'human_targets_opened': False, 'provider_calls': 0}


def output_preflight(output, root):
    require(not output.is_relative_to(p.REPO.resolve()) and not p.REPO.resolve().is_relative_to(output)
            and not output.is_relative_to(root) and not root.is_relative_to(output), 'Private result root overlaps repo/frozen input')


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    for name in ('manifest', 'tools-root'): parser.add_argument('--' + name, type=Path, required=True)
    for name in ('manifest-sha256', 'collector-sha256'): parser.add_argument('--' + name, required=True)
    for name in ('results-dir', 'route-root', 'sol-results-dir', 'grok-results-dir'): parser.add_argument('--' + name, type=Path)
    parser.add_argument('--endpoint', choices=p.ENDPOINTS); parser.add_argument('--route-sha256')
    parser.add_argument('--workers', type=int, required=True)
    parser.add_argument('--owner-global-headroom-verified', action='store_true')
    parser.add_argument('--limit', type=int); parser.add_argument('--validate-only', action='store_true')
    parser.add_argument('--label-release-check', action='store_true'); parser.add_argument('--explicit-postprediction-release', action='store_true')
    args = parser.parse_args()
    require(1 <= args.workers <= 10 and (args.limit is None or args.limit > 0), 'Workers/limit invalid')
    require(execution_workers(sys.argv) == args.workers, 'Explicit execution workers argument differs')
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
        route = next(r for r in json.loads((args.route_root / 'routes.json').read_bytes())['routes'] if r['name'] == 'grok-build-grok-4.7')
        require(digest(canonical(route).rstrip(b'\n')) == args.route_sha256, 'Reviewed route pin differs')
    binding = job_binding(manifest, root, args.manifest_sha256, args.endpoint, args.tools_root, route, args.collector_sha256, args.workers)
    if output.exists(): require(verify_job_binding(output, manifest, root, args.manifest_sha256, args.endpoint, args.tools_root) == binding, 'Existing execution allocation differs')
    pending, states, native_ids = inventory(manifest, binding, root, output, receipts, subset, validator)
    if args.validate_only:
        print(json.dumps({'state': 'provider_free_validated', 'endpoint': args.endpoint, 'manifest_sha256': args.manifest_sha256,
            'planned': 3432, 'study_planned': 6864, 'workers': args.workers, 'untouched': len(pending), 'terminal_states': dict(Counter(states)),
            'provider_calls': 0, 'human_targets_opened': False, 'human_release_eligible': False, 'native_execution_proven': False})); return 0
    require(args.owner_global_headroom_verified, 'Launching owner must verify shared project headroom before execution')
    require(all(state in SETTLED for state in states), 'Occupied native failure requires owning reconciliation; no resend')
    if (output / 'STOP').exists(): return 3
    if not pending: return 0
    helper = call_codex = broker = None
    if args.endpoint == 'sol':
        source = source_settings(manifest, root)
        helper = p.load_module('hanna_secondary_helper', Path(source['external_pins']['secondary_helper_path_local_only']))
        env = t.secondary_binding(source, helper); os.environ.clear(); os.environ.update(env)
        sys.path.insert(0, str(args.tools_root)); from adaptive_settings.account_probe import probe
        from hbqrs import runner
        t.secondary_binding(source, helper, probe(helper.CLI)); call_codex = runner._call_codex
    else:
        require(grok_contact_allowed(route), 'Route expiry/campaign deadline prevents contact')
        sys.path.insert(0, str(args.tools_root)); from model_work_queue.broker import Broker
        broker = Broker(args.route_root.resolve())
    if not output.exists():
        output.mkdir(parents=True, exist_ok=False); record(output / 'job.json', binding); write_bytes(output / 'frozen-manifest.json', args.manifest.read_bytes())
    if args.endpoint == 'sol' and not (output / 'account-binding.json').exists(): record(output / 'account-binding.json', t.account_receipt(binding))
    invocation_name = 'execution-invocation-' + str(uuid.uuid4()) + '.json'
    invocation_raw = canonical({'argv': sys.argv, 'workers': args.workers, 'job_sha256': digest((output / 'job.json').read_bytes()),
        'time': datetime.now(timezone.utc).isoformat(), 'owner_global_headroom_confirmation': True})
    write_bytes(output / invocation_name, invocation_raw)
    invocation = {'path': invocation_name, 'sha256': digest(invocation_raw), 'bytes': len(invocation_raw)}
    commit = CommitState(native_ids, invocation)
    execute = lambda row: collect_one(row, manifest, binding, root, output, subset, validator, receipts, helper, call_codex, broker, commit)
    settled = dispatch(pending[:args.limit], args.workers, execute, commit, lambda: (output / 'STOP').exists(),
        lambda row, state: print(json.dumps({'ordinal': row['endpoint_ordinal'], 'state': state}), flush=True))
    record(output / ('dispatch-terminal-' + str(uuid.uuid4()) + '.json'), {'policy': POLICY, 'workers': args.workers,
        'execution_invocation': invocation, 'settled_this_execution': len(settled), 'states': dict(Counter(settled)), 'stopped': commit.stop.is_set(), 'inflight_at_terminal': 0,
        'automatic_retries': 0, 'human_targets_opened': False})
    return 3 if commit.stop.is_set() else 0


if __name__ == '__main__': raise SystemExit(main())
