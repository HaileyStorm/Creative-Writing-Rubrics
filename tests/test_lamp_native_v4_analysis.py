"""Provider-free boundaries for LAMP004 failed evidence and owning/full gates."""
import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('lamp_v4_analysis_checks',
    REPO / 'evaluation-results/hbq-matched-lamp-20261004/analysis_chain_v4.py')
a = importlib.util.module_from_spec(spec); spec.loader.exec_module(a)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def save(path, value):
    raw = json.dumps(value, sort_keys=True).encode()
    path.write_bytes(raw)
    return {'path': str(path), 'sha256': digest(raw)}


def test_failed_body_stays_opaque_and_retained_bytes_remain_required(tmp_path):
    sample = tmp_path / '0401-synthetic'; sample.mkdir()
    job = {'manifest_sha256': 'frozen'}; save(tmp_path / 'job.json', job)
    prompt, schema = b'synthetic prompt\n', b'{}'
    row = {'logical_sample_id': 'synthetic', 'prompt_sha256': digest(prompt), 'prompt_bytes': len(prompt),
           'schema_sha256': digest(schema), 'schema_bytes': len(schema)}
    save(sample / 'condition.json', row)
    (sample / 'prompt.txt').write_bytes(prompt); (sample / 'schema.json').write_bytes(schema)
    (sample / 'native-failure.json').write_bytes(b'{"body":"opaque synthetic diagnostic"}')
    pins = {p.name: {'sha256': digest(p.read_bytes()), 'bytes': p.stat().st_size} for p in sample.iterdir()}
    save(sample / 'terminal.json', {'state': 'unadmitted_no_resend', 'accepted': False, 'no_resend': True,
        'manifest_sha256': 'frozen', 'job_sha256': digest((tmp_path / 'job.json').read_bytes()),
        'logical_sample_id': 'synthetic', 'retained_artifacts': pins,
        'provider_record': {'body': 'excluded synthetic diagnostic'}})
    calls = []
    def pinned(root, name, pin):
        raw = (root / name).read_bytes(); calls.append(name)
        if digest(raw) != pin['sha256'] or len(raw) != pin['bytes']:
            raise ValueError('Retained bytes changed')
        return raw
    c = SimpleNamespace(SETTLED={'accepted', 'semantic_rejected'}, TERMINAL_STATES={'accepted', 'semantic_rejected', 'unadmitted_no_resend'},
                        digest=digest, pinned=pinned)
    project = a.predecessor().identity_reader().lexical_reader()
    terminal, response = a.failed_terminal(sample, row, job, c, project)
    assert response is None and 'provider_record' not in terminal and set(calls) == set(pins)
    (sample / 'native-failure.json').write_bytes(b'changed')
    with pytest.raises(ValueError, match='Retained bytes changed'):
        a.failed_terminal(sample, row, job, c, project)


def test_own_dispatch_counts_invocation_and_unstarted_full_cohort_fail_closed(tmp_path):
    prior = a.predecessor()
    argv = ['python', '-B', 'synthetic_collector.py', '--workers', '2']
    invpin = save(tmp_path / 'invocation.json', {'argv': argv, 'time': '2026-10-06T00:00:00+00:00'})
    outerpin = save(tmp_path / 'outer.json', {'time': '2026-10-06T00:01:00+00:00'})
    execution = {'argv': argv[2:], 'workers': 2, 'job_sha256': 'synthetic_job', 'time': '2026-10-06T00:00:01+00:00',
                 'owner_global_headroom_confirmation': True, 'owner_declared_endpoint_headroom': 2}
    ep = save(tmp_path / 'execution-invocation-00000000-0000-0000-0000-000000000000.json', execution)
    ep['path'] = Path(ep['path']).name; ep['bytes'] = (tmp_path / ep['path']).stat().st_size
    dispatch = {'policy': a.CURRENT['policy'], 'workers': 2, 'inflight_at_terminal': 0, 'automatic_retries': 0,
        'human_release_eligible': False, 'stopped': True, 'execution_invocation': ep,
        'states': {'accepted': 1, 'unadmitted_no_resend': 1}, 'settled_this_execution': 2}
    dp = save(tmp_path / 'dispatch-terminal-00000000-0000-0000-0000-000000000000.json', dispatch)
    source = {'results_root': str(tmp_path), 'job_sha256': 'synthetic_job',
        'lifecycle': {'invocation': invpin, 'outer_terminal': outerpin, 'dispatch_terminal': dp}}
    a.dispatcher(source, {'policy': a.CURRENT['policy'], 'workers': 2}, prior, ['accepted', 'unadmitted_no_resend'])
    with pytest.raises(ValueError, match='replayed terminal counts'):
        a.dispatcher(source, {'policy': a.CURRENT['policy'], 'workers': 2}, prior, ['accepted'])
    execution['argv'] = ['foreign_collector.py', '--workers', '2']
    fresh = save(tmp_path / ep['path'], execution); ep.update(sha256=fresh['sha256'], bytes=(tmp_path / ep['path']).stat().st_size)
    source['lifecycle']['dispatch_terminal'] = save(Path(dp['path']), dispatch)
    with pytest.raises(ValueError, match='execution/invocation binding'):
        a.dispatcher(source, {'policy': a.CURRENT['policy'], 'workers': 2}, prior)
    life = prior.PROGRAM / 'lamp-reference/untouched-suffix-v5-lifecycle/grok-001'
    pins = {name: {'path': str(life / filename), 'sha256': a.CURRENT_LIFECYCLE_PINS.get(name, 'future')}
            for name, filename in {'outer_terminal': 'terminal.json', 'invocation': 'invocation.json', 'run_started': 'run-started.json',
                                   'handle': 'handle.json', 'native_handle': 'native-handle.json'}.items()}
    pins['invocation']['sha256'] = 'foreign'; pins['dispatch_terminal'] = dp
    with pytest.raises(ValueError, match='Actual own lifecycle commitment'):
        a.owning_return({'endpoint': 'grok', 'kind': 'suffix004', 'job_sha256': a.JOB_SHA, 'manifest_sha256': a.FROZEN_SHA,
            'results_root': str(prior.PROGRAM / 'lamp-reference' / a.CURRENT['output']), 'lifecycle': pins}, {}, prior)
    rows = [{'endpoint': ep, 'endpoint_ordinal': n} for ep in ('sol', 'grok') for n in range(1, 8905)]
    ledger = {(r['endpoint'], r['endpoint_ordinal']): {'descriptor_sha256': prior.sha(prior.canonical(r)),
        'state': 'unadmitted_no_resend', 'terminal_verified': True, 'attempted_verified': True,
        'native_identity_commitments': []} for r in rows}
    proofs = [{'endpoint': ep, 'kind': kind, 'verified': True} for ep in ('sol', 'grok') for kind in ('original', 'suffix')]
    proofs.append({'endpoint': 'grok', 'kind': 'suffix004', 'verified': True})
    assert not a.label_gate({'requests': rows}, ledger, proofs, False)['human_release_eligible']
    ledger[('grok', 401)]['attempted_verified'] = False
    assert not a.label_gate({'requests': rows}, ledger, proofs, True)['human_release_eligible']
    with pytest.raises(ValueError, match='All five owning returns'):
        a.label_gate({'requests': rows}, ledger, proofs[:-1], True)
