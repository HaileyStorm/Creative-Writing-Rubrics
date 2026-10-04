"""Sol continuation uses each sample's own native receipt, never null identities."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import uuid

import pytest

import continue_sol as continuation
from analysis import validate_continuation
from prepare import canonical, digest
from test_continue_manifest import frozen, write

_spec = importlib.util.spec_from_file_location('native_test_fixture', continuation.REPO / 'tests/test_codex_receipts.py')
native_fixture = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(native_fixture)


def settled(results, row, artifacts, *, identity=None, accepted=True):
    sample = results / f"{row['endpoint_ordinal']:04d}-{row['logical_sample_id'][:12]}"
    sample.mkdir(exist_ok=True)
    (sample / 'responses').mkdir(exist_ok=True)
    write(sample / 'condition.json', row)
    (sample / 'schema.json').write_bytes(artifacts[row['schema_path']])
    write(sample / 'native-identity.json', {'session_id': None, 'logical_sample_id': row['logical_sample_id']})
    write(sample / 'attempt-started.json', {'state': 'before_contact', 'session_id': None, 'no_resend': True})
    response = {'answer': 'Synthetic answer'}
    final = canonical(response).decode()
    rollout, events, message = native_fixture.native_fixture(sample, prompt=artifacts[row['prompt_path']].decode(), final=final)
    thread = str(uuid.UUID(int=identity or row['endpoint_ordinal']))
    turn = str(uuid.UUID(int=100 + (identity or row['endpoint_ordinal'])))
    def native_raw(rows):
        return native_fixture.raw(rows).replace(native_fixture.THREAD.encode(), thread.encode()).replace(native_fixture.TURN.encode(), turn.encode())
    receipt_inputs = {'codex_rollout': native_raw(rollout), 'codex_events': native_raw(events), 'codex_message': message}
    receipt = continuation.codex_receipts.project(receipt_inputs['codex_rollout'], receipt_inputs['codex_events'], message,
                prompt=artifacts[row['prompt_path']].decode(), model='gpt-6.1-sol', reasoning='high', cwd=sample)
    receipt['reader_sha256'] = continuation.codex_receipts.binding()['reader_sha256']
    receipt_inputs['codex_receipt'] = canonical(receipt)
    pins = {}
    for name, raw in receipt_inputs.items():
        path = f'responses/{name}.json'
        (sample / path).write_bytes(raw)
        pins[name] = {'path': path, 'sha256': digest(raw), 'bytes': len(raw)}
    native = {'receipt_policy': continuation.codex_receipts.POLICY, 'reported': receipt['reported'],
              'provider_artifacts': pins, 'command': ['test-executable', '--output-schema', str(sample / 'schema.json'), '--cd', str(sample)]}
    terminal = {'state': 'accepted' if accepted else 'semantic_rejected', 'accepted': accepted, 'abstention': False, 'no_resend': True}
    for name, value in [('native-result', native), ('response', response), ('acceptance', {'accepted': accepted, 'abstention': False, 'errors': [] if accepted else ['Synthetic evidence mismatch']})]:
        terminal[name.replace('-', '_') + '_sha256'] = digest(write(sample / (name + '.json'), value))
    write(sample / 'terminal.json', terminal)
    return sample


@pytest.fixture
def source(frozen, tmp_path):
    path, _, original, artifacts, _ = frozen
    results = tmp_path / 'sol'; results.mkdir()
    helper = tmp_path / 'helper.py'; helper.write_bytes(b'# synthetic helper; never executed\n')
    sys.path.insert(0, str(Path(r'C:\Users\Haile\.codex\tools')))
    from model_work_queue.adapters import json_schema_subset
    original['implementation'] = {'semantic_validator_sha256': digest((continuation.HERE / 'validate_response.py').read_bytes()),
                                  'schema_subset_sha256': digest(Path(json_schema_subset.__file__).read_bytes())}
    original.pop('manifest_content_sha256'); original['manifest_content_sha256'] = digest(canonical(original))
    raw_manifest = write(path, original)
    job = {'endpoint': 'sol', 'manifest_sha256': digest(raw_manifest), 'model': 'gpt-6.1-sol', 'reasoning': 'high',
           'zero_charge_only': True, 'automatic_retries': 0, 'account_identity_sha256': continuation.ACCOUNT_SHA256,
           'helper_sha256': digest(helper.read_bytes()), 'runner_sha256': digest((continuation.REPO / 'src/hbqrs/runner.py').read_bytes()),
           'receipt_reader_sha256': continuation.codex_receipts.binding()['reader_sha256'],
           'validator_sha256': original['implementation']['semantic_validator_sha256'],
           'collector_sha256': digest((continuation.HERE / 'collector.py').read_bytes()),
           'destination': 'OpenAI ChatGPT subscription via native Codex exec', 'payload_classification': 'public_repo',
           'sampler': 'native defaults; requested high; temperature unsupported', 'workers': 2}
    write(results / 'job.json', job)
    rows = [r for r in original['requests'] if r['endpoint'] == 'sol']
    for row in rows[:3]:
        settled(results, row, artifacts, accepted=row['endpoint_ordinal'] != 2)
    return path, results, helper, original, artifacts, rows


def build(source):
    path, results, helper, *_ = source
    return continuation.build(path, results, secondary_helper=helper)


def test_settled_semantic_rejection_reserved_without_vote_and_exact_suffix(source, tmp_path):
    path, results, _, original, original_artifacts, rows = source
    snapshot = deepcopy(original)
    manifest, artifacts = build(source)
    assert manifest['requests'] == rows[3:]
    assert [r['endpoint_ordinal'] for r in manifest['requests']] == [4, 5, 6, 7, 8]
    receipts = manifest['continuation']['prefix_receipts']
    assert [r['terminal_state'] for r in receipts] == ['accepted', 'semantic_rejected', 'accepted']
    assert all(r['no_resend'] for r in receipts)
    assert len({r['native_thread_id_sha256'] for r in receipts}) == 3
    assert manifest['historical_registration']['counts'] == original['counts']
    assert manifest['continuation']['runtime_timeout_attestation'] is None
    assert manifest['collection_policy']['name'] == 'semantic_reject_continue_v2'
    assert artifacts['lineage/parent-manifest.json'] == path.read_bytes()
    assert set(artifacts) == {*original_artifacts, 'lineage/parent-manifest.json', 'manifest.json'}
    assert all(artifacts[k] == v for k, v in original_artifacts.items())
    derived = tmp_path / 'derived'; (derived / 'lineage').mkdir(parents=True)
    (derived / 'lineage/parent-manifest.json').write_bytes(path.read_bytes())
    assert validate_continuation(manifest, original, 'sol', base_raw=path.read_bytes(), derived_root=derived) == {r['logical_sample_id'] for r in rows[3:]}
    assert original == snapshot
    settled(results, rows[1], original_artifacts, accepted=True)
    assert build(source)[0]['requests'] == manifest['requests']


@pytest.mark.parametrize('field', ['manifest_sha256', 'account_identity_sha256', 'helper_sha256', 'runner_sha256', 'receipt_reader_sha256', 'collector_sha256', 'validator_sha256', 'collector_policy'])
def test_source_job_binding_mismatch_fails(source, field):
    job_path = source[1] / 'job.json'
    job = json.loads(job_path.read_bytes()); job[field] = 'wrong'
    write(job_path, job)
    with pytest.raises(ValueError): build(source)


@pytest.mark.parametrize('damage', ['noncontiguous', 'unresolved', 'schema', 'response', 'receipt', 'context', 'descriptor', 'duplicate_logical', 'duplicate_native'])
def test_unresolved_or_changed_attempts_fail_closed(source, damage):
    path, results, _, original, artifacts, rows = source
    sample = results / f"0002-{rows[1]['logical_sample_id'][:12]}"
    if damage == 'noncontiguous':
        sample.rename(sample.with_name('retained-missing-prefix-slot'))
    elif damage == 'unresolved':
        terminal = json.loads((sample / 'terminal.json').read_bytes()); terminal.update(state='unadmitted_no_resend', accepted=False)
        write(sample / 'terminal.json', terminal)
    elif damage in {'schema', 'response'}:
        (sample / (damage + '.json')).write_bytes(b'{}')
    elif damage == 'receipt':
        (sample / 'responses/codex_receipt.json').write_bytes(b'{}')
    elif damage == 'context':
        (path.parent / 'context.txt').write_bytes(b'changed context')
    elif damage == 'duplicate_native':
        settled(results, rows[1], artifacts, identity=1)
    else:
        selected = next(r for r in original['requests'] if r['endpoint'] == 'sol' and r['endpoint_ordinal'] == 2)
        if damage == 'descriptor': selected['repeat'] = 9
        else: selected['logical_sample_id'] = rows[0]['logical_sample_id']
        selected.pop('request_sha256'); selected['request_sha256'] = digest(canonical(selected))
        original.pop('manifest_content_sha256'); original['manifest_content_sha256'] = digest(canonical(original))
        raw = write(path, original)
        job_path = results / 'job.json'; job = json.loads(job_path.read_bytes()); job['manifest_sha256'] = digest(raw); write(job_path, job)
    with pytest.raises(ValueError): build(source)


def test_real_entrypoint_dryrun_and_fresh_output(source, tmp_path):
    path, results, helper, *_ = source
    output = tmp_path / 'fresh'
    run = subprocess.run([sys.executable, str(continuation.HERE / 'continue_sol.py'), '--manifest', str(path),
                          '--prefix-results', str(results), '--secondary-helper', str(helper),
                          '--private-output', str(output), '--dry-run'], capture_output=True, text=True)
    assert run.returncode == 0, run.stderr
    assert json.loads(run.stdout)['reserved_prefix_states'] == {'accepted': 2, 'semantic_rejected': 1}
    assert not output.exists()
    for invalid in (path.parent / 'child', results, continuation.REPO / 'private-output'):
        with pytest.raises(ValueError): continuation.fresh_private_output(invalid, path.parent, results, helper)
    output.mkdir()
    with pytest.raises(ValueError, match='already exists'): continuation.fresh_private_output(output, path.parent, results, helper)
