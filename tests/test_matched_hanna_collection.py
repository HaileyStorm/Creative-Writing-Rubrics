"""Provider-free HANNA lifecycle and parallel scheduling witnesses; no native claims."""
from copy import deepcopy
from datetime import timedelta
import importlib.util
import json
from pathlib import Path
import sys
import threading
from types import SimpleNamespace
import uuid
from unittest.mock import patch

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'src'))
def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module); return module
c = load('test_hanna_collection', REPO / 'evaluation-results/hbq-matched-hanna-20261004/collector.py')
fixtures = load('hanna_collection_source_fixtures', REPO / 'tests/test_matched_hanna_preparation.py')


@pytest.fixture(scope='module')
def frozen(tmp_path_factory):
    runtime = Path(r'C:\Users\Haile\Documents\cwr-resume-control-20260919-r1\successor-program-20261004\semantic-crossform\frozen-001\manifest.json')
    if not runtime.exists(): pytest.skip('Pinned local native runtime metadata unavailable')
    test_path = Path('synthetic-tests.json')
    tests = c.canonical([{'ttcw_idx': n, 'full_prompt': 'Synthetic definition.\n\nGiven the story, evaluate it.',
        'question': 'Does the story meet synthetic criterion ' + str(n) + '?', 'torrance_dimension': 'synthetic', 'category': 'synthetic'} for n in range(1, 15)])
    checked = c.p.checked
    with patch.object(c.p, 'checked', side_effect=lambda path, pin, size=None: tests if Path(path) == test_path else checked(path, pin, size)):
        manifest, files = c.p.build(fixtures.items(), {'source_commitments': {}}, runtime, test_path)
    root = tmp_path_factory.mktemp('hanna-frozen')
    for name, raw in files.items(): c.write_bytes(root / name, raw)
    sys.path.insert(0, str(manifest['external_pins']['tools_root_local_only']))
    return {'manifest': manifest, 'files': files, 'root': root, 'sha': c.digest(files['manifest.json']),
        'tools': Path(manifest['external_pins']['tools_root_local_only']),
        'subset': c.p.load_module('hanna_test_subset', root / 'implementation/schema_subset.py'),
        'validator': c.p.load_module('hanna_test_validator', root / 'implementation/validate_response.py')}


class Receipts:
    reject = False
    def verify(self, sample, native, **kwargs):
        if self.reject: raise ValueError('Fixture native rejection')
        assert kwargs['model'] == 'gpt-6.1-sol' and kwargs['reasoning'] == 'high'
        assert kwargs['prompt'] == (sample / 'prompt.txt').read_bytes().decode()
        for meta in native['provider_artifacts'].values(): c.pinned(sample, meta['path'], meta)
    def event_identity(self, events, final): return json.loads(events)['thread_id'], []


def answer(row):
    return {'verdicts': [{'question_id': qid, 'verdict': 'CANNOT_ASSESS', 'confidence': 1, 'note': 'Fixture uncertainty.',
        'evidence': [{'kind': 'summary', 'reference': 'available source', 'exact_quote': None, 'summary': 'Mechanical fixture witness.'}]} for qid in row['question_ids']]}


@pytest.fixture
def job(tmp_path, frozen):
    output = tmp_path / 'results'; output.mkdir()
    binding = c.job_binding(frozen['manifest'], frozen['root'], frozen['sha'], 'sol', frozen['tools'], workers=3)
    c.record(output / 'job.json', binding); c.record(output / 'account-binding.json', c.t.account_receipt(binding))
    c.write_bytes(output / 'frozen-manifest.json', frozen['files']['manifest.json'])
    invocation_raw = c.canonical({'argv': ['collector', '--workers', '3', '--owner-global-headroom-verified'],
        'workers': 3, 'job_sha256': c.digest((output / 'job.json').read_bytes())})
    c.write_bytes(output / 'invocation.json', invocation_raw)
    invocation = {'path': 'invocation.json', 'sha256': c.digest(invocation_raw), 'bytes': len(invocation_raw)}
    state = {'contacts': 0, 'invalid': False, 'native_fail': False, 'identity': None}
    def call(**kwargs):
        assert kwargs['timeout'] == 900 and kwargs['attempt_number'] == 1 and kwargs['reasoning'] == 'high'
        assert kwargs['codex_receipt_policy'] == 'codex_native_rollout_v1'
        kwargs['before_provider_attempt'](); state['contacts'] += 1
        sample = kwargs['output_dir']; row = json.loads((sample / 'condition.json').read_bytes())
        if state['native_fail']:
            c.write_bytes(sample / 'failure.txt', b'fixture timeout'); raise TimeoutError('Fixture native timeout')
        response = answer(row)
        if state['invalid']: response['verdicts'][-1]['question_id'] = response['verdicts'][0]['question_id']
        final = c.canonical(response); identity = state['identity'] or str(uuid.uuid4()); artifacts = {}
        for key, name, raw in [('codex_message', 'final.json', final), ('codex_events', 'events.json', c.canonical({'thread_id': identity}))]:
            c.write_bytes(sample / name, raw); artifacts[key] = {'path': name, 'bytes': len(raw), 'sha256': c.digest(raw)}
        return final.decode(), {'receipt_policy': 'codex_native_rollout_v1', 'provider_artifacts': artifacts}
    return {**frozen, 'output': output, 'binding': binding, 'state': state, 'call': call, 'receipts': Receipts(),
        'helper': SimpleNamespace(CLI=Path('not-executed.exe')), 'commit': c.CommitState(invocation=invocation),
        'rows': [r for r in frozen['manifest']['requests'] if r['endpoint'] == 'sol' and r['arm'] == 'hbq']}


def collect(job, row):
    return c.collect_one(row, job['manifest'], job['binding'], job['root'], job['output'], job['subset'], job['validator'],
        job['receipts'], job['helper'], job['call'], commit=job['commit'])


def replay(job, row):
    return c.replay(c.sample_path(job['output'], row), row, job['manifest'], job['binding'], job['root'], job['receipts'], job['subset'], job['validator'])


def test_complete_geometry_exact_context_and_explicit_execution_amendment(frozen, tmp_path):
    c.validate_design(frozen['manifest'], frozen['files'])
    row = frozen['manifest']['requests'][0]
    prompt, _, texts, context = c.inputs(frozen['root'], frozen['manifest'], row)
    origin = frozen['files'][row['originating_prompt']['path']].decode()
    assert context.endswith('\n' + origin) and origin.encode() in prompt
    assert all(text.encode() in prompt for text in texts.values())
    broken = deepcopy(frozen['manifest']); broken['requests'].pop()
    with pytest.raises(ValueError, match='cardinality'): c.validate_design(broken, frozen['files'])
    for workers in (1, 3, 10):
        binding = c.job_binding(frozen['manifest'], frozen['root'], frozen['sha'], 'sol', frozen['tools'], workers=workers)
        assert binding['workers'] == workers and binding['owner_execution_amendment']['prepared_workers_initially'] == 1
        assert binding['planned_study_requests'] == 6864 and binding['automatic_retries'] == 0
    with pytest.raises(ValueError): c.job_binding(frozen['manifest'], frozen['root'], frozen['sha'], 'sol', frozen['tools'], workers=11)
    path = frozen['root'] / row['sources'][0]['input_path']; raw = path.read_bytes()
    path.write_bytes(raw + b'changed')
    try:
        with pytest.raises(ValueError, match='artifact'): c.inputs(frozen['root'], frozen['manifest'], row)
    finally: path.write_bytes(raw)


def test_semantic_rejection_continues_native_failure_and_duplicate_never_resend(job):
    first, second, third, fourth = job['rows'][:4]
    job['state']['invalid'] = True
    assert collect(job, first) == 'semantic_rejected' and replay(job, first)[1] is None and not job['commit'].stop.is_set()
    job['state'].update(invalid=False, identity=str(uuid.uuid4()))
    assert collect(job, second) == 'accepted' and replay(job, second)[1]
    assert collect(job, third) == 'unadmitted_no_resend' and replay(job, third)[1] is None
    assert job['commit'].stop.is_set()
    with pytest.raises(FileExistsError): collect(job, third)
    assert job['state']['contacts'] == 3
    job['commit'] = c.CommitState(invocation=job['commit'].invocation); job['state']['native_fail'] = True
    assert collect(job, fourth) == 'unadmitted_no_resend' and replay(job, fourth)[1] is None
    with pytest.raises(FileExistsError): collect(job, fourth)
    assert job['state']['contacts'] == 4
    sample = c.sample_path(job['output'], second)
    path = sample / 'task-context.json'; raw = path.read_bytes(); path.write_bytes(raw + b'changed')
    with pytest.raises(ValueError): replay(job, second)
    path.write_bytes(raw)


def test_parallel_failure_and_stop_settle_started_without_new_dispatch():
    assert c.execution_workers(['collector', '--workers', '3']) == c.execution_workers(['collector', '--workers=3']) == 3
    with pytest.raises(ValueError): c.execution_workers(['collector', '--workers', '3', '--workers=5'])
    for stop_case in (False, True):
        commit = c.CommitState(); lock = threading.Lock(); barrier = threading.Barrier(3)
        active = 0; maximum = 0; started = []; settled = []; observed_stop = threading.Event()
        def execute(row):
            nonlocal active, maximum
            with lock: started.append(row); active += 1; maximum = max(maximum, active)
            barrier.wait(timeout=5)
            if row == 0:
                if stop_case: observed_stop.set()
                else: commit.stop.set()
            else:
                # Ensure the stop is observed before either successful sibling can release a new slot.
                while not (observed_stop.is_set() or commit.stop.is_set()): observed_stop.wait(.001)
            with lock: settled.append(row); active -= 1
            return 'accepted' if stop_case or row != 0 else 'unadmitted_no_resend'
        states = c.dispatch(range(20), 3, execute, commit, observed_stop.is_set)
        assert maximum == 3 and len(states) == len(started) == len(settled) == 3 and active == 0
        assert commit.stop.is_set() and set(started) == {0, 1, 2}


def test_route_expiry_gv5_no_tools_and_full_explicit_label_gate(frozen, tmp_path, monkeypatch):
    route = {'name': 'grok-build-grok-4.7', 'model': 'grok-4.7', 'reported_model': 'grok-4.7', 'reasoning_effort': 'high',
        'timeout_seconds': 900, 'zero_charge': True, 'armed': True, 'allowed_payload_classes': ['public_repo'],
        'cost_evidence': {'expires_at': c.q.CUTOFF.isoformat()}}
    boundary = c.q.CUTOFF - timedelta(seconds=900)
    assert c.grok_contact_allowed(route, boundary - timedelta(microseconds=1)) and not c.grok_contact_allowed(route, boundary)
    binding = c.job_binding(frozen['manifest'], frozen['root'], frozen['sha'], 'grok', frozen['tools'], route, workers=3)
    row = next(r for r in frozen['manifest']['requests'] if r['endpoint'] == 'grok' and r['arm'] == 'hbq')
    prompt, schema, _, _ = c.inputs(frozen['root'], frozen['manifest'], row)
    session = str(uuid.uuid4()); response = answer(row); compact = lambda v: c.canonical(v).rstrip(b'\n')
    request_id = str(uuid.uuid4())
    envelope = c.canonical({'sessionId': session, 'requestId': request_id, 'modelUsage': {'grok-4.7': {}},
        'structuredOutput': response, 'stopReason': 'end_turn', 'num_turns': 1})
    contract = {'name': 'grok_nonvisual_history_v5'}
    native = {'state': 'completed', 'result': {'runtime': {'adapter_version': 5, 'execution_policy': 'bounded_nonvisual_deny_wins_attested',
        'nonvisual_max_turns': 1, 'tool_policy_attestation_hash': 'a' * 64, 'transport': {'exit_code': 0},
        'request_id_hash': c.digest(request_id.encode()), 'observed_turns': 1, 'usage_telemetry': {'status': 'not_reported'},
        'session_id_hash': c.digest(session.encode()), 'requested_model': 'grok-4.7', 'reported_model': 'grok-4.7', 'requested_reasoning_effort': 'high',
        'execution_contract': {'max_turns': 1, 'tools': 'deny_wins_none_attested', 'staged_prompt_sha256': c.digest(prompt), 'staged_prompt_byte_length': len(prompt),
            'output_schema_hash': c.digest(compact(json.loads(schema))), 'nonvisual_transport_contract': contract, 'nonvisual_transport_contract_sha256': c.digest(compact(contract))}},
        'request_hash': c.digest(compact({'prompt': prompt.decode()})), 'output_hash': c.digest(compact(response)), 'output': response,
        'native_envelope_artifact': {'sha256': c.digest(envelope), 'byte_length': len(envelope)}}}
    sample = tmp_path / 'grok'; sample.mkdir(); c.record(sample / 'native-result.json', native)
    c.record(sample / 'native-identity.json', {'session_id': session}); c.record(sample / 'attempt-started.json', {'session_id': session})
    c.write_bytes(sample / 'native-envelope.json', envelope)
    assert c.native_answer(sample, row, binding, prompt, schema, None)[0] == response
    native['result']['runtime']['execution_contract']['tools'] = 'unknown'
    (sample / 'native-result.json').write_bytes(c.canonical(native))
    with pytest.raises(ValueError, match='no-tool'): c.native_answer(sample, row, binding, prompt, schema, None)
    outputs = {e: tmp_path / 'label-gate' / e for e in c.p.ENDPOINTS}
    gate = lambda release: c.label_release_gate(frozen['manifest'], frozen['root'], frozen['sha'], frozen['tools'], outputs, None, None, None, release)
    assert not gate(True)['human_release_eligible'] and gate(False)['planned'] == 6864
    for output in outputs.values(): output.mkdir(parents=True)
    monkeypatch.setattr(c, 'verify_job_binding', lambda output, *args: {'endpoint': output.name})
    monkeypatch.setattr(c, 'inventory', lambda manifest, binding, *args: ([], ['accepted'] * 3432, {binding['endpoint']}))
    assert not gate(False)['human_release_eligible'] and gate(True)['human_release_eligible']
    assert not gate(True)['human_targets_opened'] and gate(True)['provider_calls'] == 0


def test_hanna_saved_descendant_binds_same_original_identity():
    r = load('hanna_saved_identity_test', REPO / 'evaluation-results/hbq-matched-hanna-20261004/reconcile_saved.py')
    slot = '0007-cc2135de14f3'; logical = 'cc2135de14f3' + '0' * 52
    row = {'endpoint': 'sol', 'endpoint_ordinal': 7, 'logical_sample_id': logical, 'prompt_sha256': 'prompt', 'schema_sha256': 'schema'}
    row['request_sha256'] = r.digest(r.canonical(row))
    job = {'policy': c.POLICY, 'collector_sha256': r.COLLECTOR_SHA, 'manifest_sha256': r.COMMON['manifest'][0],
        'receipt_reader_sha256': r.READER_SHA, 'admission_sha256': r.VALIDATOR_SHA, 'planned_study_requests': 6864,
        'runtime': {'model': 'gpt-6.1-sol', 'reasoning': 'high'}}
    started = {'manifest_sha256': r.COMMON['manifest'][0], 'job_sha256': r.COMMON['job'][0], 'logical_sample_id': logical,
        'attempt': 1, 'no_resend': True, 'prompt_sha256': 'prompt', 'schema_sha256': 'schema', 'session_id': None}
    identity = {'session_id': None, 'logical_sample_id': logical}
    terminal = {'state': 'unadmitted_no_resend', 'accepted': False, 'no_resend': True, 'logical_sample_id': logical,
        'job_sha256': r.COMMON['job'][0], 'manifest_sha256': r.COMMON['manifest'][0], 'error_class': '_ProviderAttemptFailure'}
    original = deepcopy(terminal)
    r.bind_attempt(slot, row, {'requests': [row]}, job, started, identity, terminal)
    assert terminal == original
    identity['logical_sample_id'] = 'foreign-original-observation'
    with pytest.raises(ValueError, match='started identity'): r.bind_attempt(slot, row, {'requests': [row]}, job, started, identity, terminal)
    identity['logical_sample_id'] = logical; started['job_sha256'] = 'foreign-job'
    with pytest.raises(ValueError, match='started identity'): r.bind_attempt(slot, row, {'requests': [row]}, job, started, identity, terminal)


def test_hanna_saved_fresh_output_never_overwrites_or_aliases_source(tmp_path):
    r = load('hanna_saved_output_test', REPO / 'evaluation-results/hbq-matched-hanna-20261004/reconcile_saved.py')
    retained = tmp_path / 'retained'; retained.mkdir(); marker = retained / 'original.txt'; marker.write_bytes(b'immutable fixture')
    output = tmp_path / 'descendant'
    assert r.fresh_output(output, [retained]) == output.resolve() and not output.exists()
    output.mkdir()
    with pytest.raises(ValueError, match='fresh'): r.fresh_output(output, [retained])
    with pytest.raises(ValueError, match='fresh'): r.fresh_output(retained / 'nested', [retained])
    with pytest.raises(ValueError, match='locator'): r.reconcile(tmp_path / 'manifest.json', retained,
        '0007-cc2135de14f3', r.HOME, r.HOME / 'sessions/foreign-rollout.jsonl')
    assert marker.read_bytes() == b'immutable fixture'
