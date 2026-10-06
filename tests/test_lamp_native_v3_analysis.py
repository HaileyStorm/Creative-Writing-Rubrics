"""Synthetic source-shaped boundaries; no retained outcomes are opened."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

PATH = Path(__file__).resolve().parents[1] / 'evaluation-results/hbq-matched-lamp-20261004/analysis_chain_v3.py'


def load():
    spec = importlib.util.spec_from_file_location('lamp_native_v3_boundary', PATH)
    value = importlib.util.module_from_spec(spec); spec.loader.exec_module(value)
    return value


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding='utf-8')


def test_sol_placeholder_failed_missing_global_identity_and_attempted_gate(tmp_path):
    a = load(); reader = a.identity_reader(); project = reader.lexical_reader()
    sample = tmp_path / '0001-original'; row = {'endpoint': 'sol', 'logical_sample_id': 'original', 'endpoint_ordinal': 1}
    thread = 'fce76243-a938-4c0b-9d97-5061ecfba174'
    write(sample / 'native-identity.json', {'logical_sample_id': 'original', 'session_id': None})
    write(sample / 'receipts/native.json', {'thread_id': thread, 'turn_id': 'own-turn'})
    pin = {'path': 'receipts/native.json', 'sha256': a.sha((sample / 'receipts/native.json').read_bytes())}
    write(sample / 'native-result.json', {'provider_artifacts': {'codex_receipt': pin}, 'reported': {'session_id': thread}})
    events = sample / 'responses/own.events.jsonl'; events.parent.mkdir()
    events.write_bytes(json.dumps({'type': 'thread.started', 'thread_id': thread}).encode() + b'\n')
    c = SimpleNamespace(SETTLED={'accepted', 'semantic_rejected'},
        pinned=lambda root, name, meta: a.checked(root / name, meta['sha256']))
    ids = reader.native_ids(sample, row, {'state': 'accepted'}, c, project)
    assert ids == [('sol_thread', a.sha(thread.encode()))]
    joined, records, seen = {}, [], set()
    terminal = {'state': 'semantic_rejected', 'accepted': False}
    a.merge(joined, records, seen, row, terminal, None, ids, {}, True)
    assert not records and joined[('sol', 1)]['state'] == 'semantic_rejected'
    with pytest.raises(ValueError, match='occupied twice'):
        a.merge(joined, records, seen, row, terminal, None, ids, {}, True)
    with pytest.raises(ValueError, match='Native identity reused'):
        a.merge(joined, records, seen, dict(row, endpoint_ordinal=2), terminal, None, ids, {}, True)
    with pytest.raises(ValueError, match='cannot supply a vote'):
        a.merge({}, [], set(), row, terminal, {'private': 'rejected'}, ids, {}, True)
    events.write_bytes(json.dumps({'type': 'thread.started', 'thread_id': '4e379ec4-8fa3-4d02-844e-c1e2d195b106'}).encode())
    with pytest.raises(ValueError, match='Foreign native thread'):
        reader.native_ids(sample, row, {'state': 'accepted'}, c, project)
    # A verified failed disposition remains missing; a precontact terminal is
    # insufficient even when every planned position has a filesystem terminal.
    rows = [{'endpoint': ep, 'endpoint_ordinal': n} for ep in ('sol', 'grok') for n in range(1, 8905)]
    ledger = {(r['endpoint'], r['endpoint_ordinal']): {'descriptor_sha256': a.sha(a.canonical(r)),
        'state': 'ambiguous', 'terminal_verified': True, 'attempted_verified': True, 'native_identity_commitments': []} for r in rows}
    proofs = [{'endpoint': ep, 'kind': k, 'verified': True} for ep in ('sol', 'grok') for k in ('original', 'suffix')]
    assert a.label_gate({'requests': rows}, ledger, proofs, True)['human_release_eligible']
    assert not a.label_gate({'requests': rows}, ledger, proofs, False)['human_release_eligible']
    ledger[('sol', 1153)]['attempted_verified'] = False
    assert not a.label_gate({'requests': rows}, ledger, proofs, True)['human_release_eligible']


def test_exact_executed_suffix_owning_contract_and_failed_replay(tmp_path):
    a = load(); spec = a.SUFFIXES['grok']; life = tmp_path / 'life'; output = tmp_path / 'results'
    invpath = life / 'invocation.json'; launch = a.PROGRAM / 'lamp-reference' / spec['launcher'][0]
    argv = [str(a.REPO / '.venv/Scripts/python.exe'), '-B', str(a.PROGRAM / 'lamp-reference' / spec['collector'][0]),
        '--adapter-sha256', spec['collector'][1], '--owning-invocation', str(invpath), '--execute-native', '--endpoint-headroom', '2']
    flags = dict.fromkeys(('global_headroom_verified', 'returned_allocation_verified', 'current_route_verified', 'outbound_disclosure_confirmed'), True)
    inv = {'argv': argv, 'route_sha256': 'route', 'persistence_guard_policy': 'free_disk_before_native_contact_v1',
        'minimum_free_disk_bytes': 268435456, 'owner_attestations': flags, 'time': '2026-10-06T01:00:00Z',
        'source_release': {'source_outer_sha256': 'prior-outer', 'inventory_sha256': 'prior-inventory'}}
    write(invpath, inv); invsha = a.sha(invpath.read_bytes())
    job = {'route_sha256': 'route', 'persistence_guard_policy': inv['persistence_guard_policy'], 'minimum_free_disk_bytes': 268435456,
        'owning_invocation_binding_verified': True, 'execution_opt_in': True, 'owner_global_headroom_confirmation': True,
        'owning_invocation': {'path': str(invpath), 'sha256': invsha, 'bytes': len(invpath.read_bytes()),
            'launcher_sha256': spec['launcher'][1], 'source_outer_sha256': 'prior-outer', 'source_inventory_sha256': 'prior-inventory'}}
    write(output / 'job.json', job); jobsha = a.sha((output / 'job.json').read_bytes())
    source = {'results_root': str(output), 'job_sha256': jobsha}
    pins = {'invocation': {'path': str(invpath), 'sha256': invsha}}
    handle = {'argv': [str(a.REPO / '.venv/Scripts/python.exe'), '-B', str(launch), '--run', '--invocation-sha256', invsha],
        'creation_time_basis': 'Windows GetProcessTimes on owned Popen handle', 'creationflags': 134218240, 'process_creation_utc': '2026-10-06T01:00:01Z'}
    native = {'creation_time_basis': handle['creation_time_basis'], 'creationflags': 134217728, 'process_creation_utc': '2026-10-06T01:00:03Z'}
    outer = {'time': '2026-10-06T01:01:00Z', 'native_job': {'path': str(output / 'job.json'), 'sha256': jobsha, 'bytes': len((output / 'job.json').read_bytes())}}
    a.suffix_lifecycle(source, job, pins, inv, {'time': '2026-10-06T01:00:02Z'}, handle, native, outer, spec)
    inv['owner_attestations']['current_route_verified'] = False
    with pytest.raises(ValueError, match='owner/persistence'):
        a.suffix_lifecycle(source, job, pins, inv, {'time': '2026-10-06T01:00:02Z'}, handle, native, outer, spec)
    # Actual frozen collector failed branch verifies original artifacts and
    # returns None without reading a response, schema or native answer.
    old = a.predecessor(); c = old.c; sample = output / '0344-original'
    row = {'endpoint': 'grok', 'endpoint_ordinal': 344, 'logical_sample_id': 'original'}
    write(sample / 'condition.json', row)
    retained = {'condition.json': {'sha256': a.sha((sample / 'condition.json').read_bytes()), 'bytes': len((sample / 'condition.json').read_bytes())}}
    terminal = {'state': 'ambiguous', 'accepted': False, 'no_resend': True, 'logical_sample_id': 'original',
        'manifest_sha256': a.GROK_FREEZE, 'job_sha256': jobsha, 'retained_artifacts': retained, 'retention_errors': []}
    write(sample / 'terminal.json', terminal)
    reject = Mock(side_effect=AssertionError('Failed native observation must not decode an answer'))
    c.h.q.native_answer = reject
    adapter = SimpleNamespace(base={'FROZEN': tmp_path}, replay=reject)
    effective, answer = a.replay_suffix(adapter, c, sample, row, {}, dict(job, manifest_sha256=a.GROK_FREEZE), None, None, None)
    assert effective == terminal and answer is None and not reject.called
