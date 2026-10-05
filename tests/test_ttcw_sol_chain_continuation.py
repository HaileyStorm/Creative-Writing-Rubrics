"""Synthetic exact-native fixtures prove reservation, not provider execution."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import uuid

import pytest

REPO = Path(__file__).resolve().parents[1]
HERE = REPO / 'evaluation-results/hbq-matched-ttcw-20261004'
sys.path.insert(0, str(HERE))
import continue_sol_chain as chain
import continue_sol as predecessor
from prepare import canonical, digest

spec = importlib.util.spec_from_file_location('sol_chain_historical_fixture', HERE / 'test_continue_sol.py')
legacy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(legacy)
frozen, source = legacy.frozen, legacy.source
write = legacy.write


def failed(results, row, artifacts, *, identity=None, partial=False):
    sample = results / f"{row['endpoint_ordinal']:04d}-{row['logical_sample_id'][:12]}"
    sample.mkdir()
    (sample / 'responses').mkdir()
    write(sample / 'condition.json', row)
    (sample / 'schema.json').write_bytes(artifacts[row['schema_path']])
    write(sample / 'native-identity.json', {'session_id': None, 'logical_sample_id': row['logical_sample_id']})
    write(sample / 'attempt-started.json', {'state': 'before_contact', 'session_id': None, 'no_resend': True})
    events = canonical({'type': 'thread.started', 'thread_id': str(uuid.UUID(int=identity or row['endpoint_ordinal']))})
    events += canonical({'type': 'turn.started'}) + canonical({'type': 'error', 'message': 'Synthetic transport failure'})
    events += canonical({'type': 'turn.completed', 'usage': {}})
    if partial:
        events += b'{"unfinished":'
    relative = 'responses/events.jsonl'
    (sample / relative).write_bytes(events)
    write(sample / 'terminal.json', {'state': 'unadmitted_no_resend', 'accepted': False, 'no_resend': True,
        'error_class': '_ProviderAttemptFailure', 'provider_record': {'provider_artifacts': {
            'codex_events': {'path': relative, 'sha256': digest(events), 'bytes': len(events)}}}})
    return sample


@pytest.fixture
def source_chain(source, tmp_path):
    path, first, helper, original, artifacts, rows = source
    descendant, files = predecessor.build(path, first, secondary_helper=helper)
    derived = tmp_path / 'derived'
    for name, raw in files.items():
        target = derived / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
    second = tmp_path / 'second-results'
    second.mkdir()
    job = json.loads((first / 'job.json').read_bytes())
    job.update(manifest_sha256=digest(files['manifest.json']), collector_policy=chain.POLICY,
               collector_sha256=digest((HERE / 'collector_v2.py').read_bytes()))
    write(second / 'job.json', job)
    legacy.settled(second, rows[3], artifacts, accepted=False)
    failed(second, rows[4], artifacts)
    failed(second, rows[5], artifacts, partial=True)
    return path, [(path, first), (derived / 'manifest.json', second)], helper, original, artifacts, rows


def build(source_chain):
    path, jobs, helper, *_ = source_chain
    return chain.build(path, jobs, secondary_helper=helper)


def test_entire_chain_reserved_without_failed_votes_and_exact_suffix(source_chain):
    path, jobs, _, original, original_artifacts, rows = source_chain
    before = deepcopy(original)
    manifest, artifacts = build(source_chain)
    assert manifest['requests'] == rows[6:]
    assert manifest['counts']['reserved_prefix_requests'] == 6
    assert manifest['historical_registration']['counts'] == original['counts']
    receipts = manifest['continuation']['prefix_receipts']
    assert [r['source_job_index'] for r in receipts] == [0, 0, 0, 1, 1, 1]
    assert [r['terminal_state'] for r in receipts] == ['accepted', 'semantic_rejected', 'accepted', 'semantic_rejected', 'unadmitted_no_resend', 'unadmitted_no_resend']
    assert sum(r['accepted_vote'] for r in receipts) == 2
    assert all(r['new_votes'] == 0 and r['no_resend'] for r in receipts)
    assert all(not r['completion_inferred'] and r['native_turn_id_sha256'] is None for r in receipts[-2:])
    assert receipts[-1]['unreadable_event_lines'] == 1
    assert receipts[-1]['event_counts']['turn.completed'] == 1
    assert manifest['continuation']['collector_v2_execution_timeout_seconds'] == 300
    assert manifest['collection_policy'] == {'name': chain.POLICY, 'collector_sha256': digest((HERE / 'collector_v2.py').read_bytes())}
    assert artifacts['lineage/parent-manifest.json'] == path.read_bytes()
    assert all(artifacts[name] == raw for name, raw in original_artifacts.items())
    assert original == before
    legacy.settled(jobs[1][1], rows[3], original_artifacts, accepted=True)
    assert build(source_chain)[0]['requests'] == rows[6:]


@pytest.mark.parametrize('damage', ['job_pin', 'gap', 'duplicate_job', 'unknown_terminal', 'started', 'schema', 'event_pin', 'duplicate_thread'])
def test_invalid_chain_or_failed_receipt_blocks_reselection(source_chain, damage):
    path, jobs, _, _, artifacts, rows = source_chain
    second = jobs[1][1]
    sample = second / f"0005-{rows[4]['logical_sample_id'][:12]}"
    if damage == 'job_pin':
        job = json.loads((second / 'job.json').read_bytes()); job['manifest_sha256'] = digest(path.read_bytes())
        write(second / 'job.json', job)
    elif damage == 'gap':
        sample.rename(sample.with_name('retained-gap'))
    elif damage == 'duplicate_job':
        jobs.append(jobs[1])
    elif damage == 'started':
        (sample / 'attempt-started.json').unlink()
    elif damage == 'schema':
        (sample / 'schema.json').write_bytes(b'{}')
    elif damage == 'event_pin':
        (sample / 'responses/events.jsonl').write_bytes(b'{}')
    elif damage == 'duplicate_thread':
        terminal = json.loads((sample / 'terminal.json').read_bytes())
        relative = terminal['provider_record']['provider_artifacts']['codex_events']['path']
        events = canonical({'type': 'thread.started', 'thread_id': str(uuid.UUID(int=1))})
        (sample / relative).write_bytes(events)
        terminal['provider_record']['provider_artifacts']['codex_events'].update(sha256=digest(events), bytes=len(events))
        write(sample / 'terminal.json', terminal)
    else:
        terminal = json.loads((sample / 'terminal.json').read_bytes()); terminal['error_class'] = 'UnknownLocalError'
        write(sample / 'terminal.json', terminal)
    with pytest.raises((ValueError, FileNotFoundError)):
        build(source_chain)


def test_real_cli_is_provider_free_and_requires_fresh_output(source_chain, tmp_path):
    path, jobs, helper, *_ = source_chain
    output = tmp_path / 'fresh-output'
    command = [sys.executable, '-B', str(HERE / 'continue_sol_chain.py'), '--manifest', str(path),
               '--secondary-helper', str(helper), '--private-output', str(output), '--dry-run']
    for source_path, results in jobs:
        command += ['--prefix-job', f'{source_path}={results}']
    run = subprocess.run(command, capture_output=True, text=True, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    assert run.returncode == 0, run.stderr
    report = json.loads(run.stdout)
    assert report['provider_calls_made'] == 0
    assert report['reserved_prefix_states'] == {'accepted': 2, 'semantic_rejected': 2, 'unadmitted_no_resend': 2}
    assert not output.exists()
    output.mkdir()
    run = subprocess.run(command, capture_output=True, text=True, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    assert run.returncode != 0 and 'already exists' in run.stderr
    with pytest.raises(ValueError, match='overlaps'):
        chain.fresh_private_output(jobs[1][1] / 'new', jobs[1][1])
