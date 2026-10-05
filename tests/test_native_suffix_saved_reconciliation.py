"""Bounded decode-projection and retained-original witnesses; no provider calls."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import sys

import pytest

REPO = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec); sys.modules[name] = module
    spec.loader.exec_module(module); return module


m = load('test_saved_suffix', REPO / 'evaluation-results/hbq-native-transport-recovery-v1/reconcile_failed_suffix.py')
generic = load('test_saved_suffix_generic', REPO / 'evaluation-results/hbq-native-transport-recovery-v1/reconcile.py')


def fixture():
    summary = {'created_at': '2026-10-05T19:00:00Z', 'updated_at': '2026-10-05T19:01:00Z',
               'reasoning_effort': 'high', 'request_id': 'request'}
    rows = []
    for n, kind in enumerate(('user_message_chunk', 'retry_state', 'agent_thought_chunk', 'agent_message_chunk', 'turn_completed')):
        meta = {'eventId': str(n), 'agentTimestampMs': n}
        update = {'sessionUpdate': kind}
        if kind == 'retry_state': update.update(type='retrying', attempt=1, max_retries=15, reason=m.DECODE, error_type='http')
        elif kind == 'turn_completed': update.update(elapsed_ms=10, prompt_id='request', stop_reason='end_turn', usage={})
        else:
            update['content'] = {'type': 'text', 'text': 'prompt' if kind == 'user_message_chunk' else 'synthetic response'}
            if kind == 'user_message_chunk': update['_meta'] = {'modelId': 'grok-4.7', 'promptIndex': 0}
            else: meta.update(totalTokens=2, promptId='request', streamStartMs=1, turnStartMs=1,
                              updateType='AgentThoughtChunk' if kind == 'agent_thought_chunk' else 'AgentMessageChunk', chunkId=0)
        rows.append({'timestamp': '2026-10-05T19:00:10Z', 'method': '_x.ai/session/update' if kind in {'retry_state', 'turn_completed'} else 'session/update',
                     'params': {'sessionId': 'session', 'update': update, '_meta': meta}})
    return rows, summary


def test_exact_decode_projection_preserves_raw_and_rejects_foreign_unknown_duplicate():
    rows, summary = fixture(); original = m.canonical(rows)
    projected, diagnostics = m.decode_projection(generic.grok_projection, rows, summary, 'session', 'prompt\n')
    assert m.canonical(rows) == original and projected == [rows[0], *rows[2:]]
    assert diagnostics == [{'record_sha256': m.digest(m.canonical(rows[1])), 'reason': m.DECODE, 'attempt': 1}]
    cases = []
    bad = deepcopy(rows); bad[1]['params']['update']['reason'] = 'unclassified error'; cases.append(bad)
    bad = deepcopy(rows); bad[2]['params']['sessionId'] = 'foreign'; cases.append(bad)
    bad = deepcopy(rows); bad[2]['params']['_meta']['eventId'] = bad[0]['params']['_meta']['eventId']; cases.append(bad)
    bad = deepcopy(rows); bad[-1]['params']['update']['stop_reason'] = 'partial'; cases.append(bad)
    for bad in cases:
        with pytest.raises(ValueError): m.decode_projection(generic.grok_projection, bad, summary, 'session', 'prompt')
    with pytest.raises(ValueError): m.decode_projection(generic.grok_projection, rows, summary, 'session', 'different prompt')
    dns = deepcopy(rows); dns[1]['params']['update']['reason'] = generic.GROK_DNS
    with pytest.raises(ValueError, match='cannot adopt generic DNS'):
        m.decode_projection(generic.grok_projection, dns, summary, 'session', 'prompt')


def test_fixed_scope_fresh_output_and_verify_original_byte_preservation(tmp_path, monkeypatch):
    retained = tmp_path / 'retained'; retained.mkdir(); source = retained / 'original.bin'; source.write_bytes(b'original')
    output = tmp_path / 'descendant'; assert m.fresh_output(output, [retained]) == output.resolve()
    with pytest.raises(ValueError, match='fresh'): m.fresh_output(retained / 'nested', [retained])
    with pytest.raises(ValueError, match='fixed source'): m.reconcile(tmp_path, m.SESSIONS)
    output.mkdir()
    with pytest.raises(ValueError, match='fresh'): m.fresh_output(output, [retained])
    saved = {'program_root_local_only': str(m.PROGRAM), 'sessions_root_local_only': str(m.SESSIONS),
             'implementation_sha256': m.digest(b'fixture implementation'),
             'source_commitments': {'original': {'sha256': m.digest(b'original'), 'bytes': 8,
                                                'source_locator_local_only': str(source), 'snapshot': 'native/original.bin'}}}
    path = output / 'reconciliation.json'; raw = m.canonical(saved); path.write_bytes(raw)
    (output / 'reconcile_failed_suffix.py').write_bytes(b'fixture implementation')
    (output / 'native').mkdir(); (output / 'native/original.bin').write_bytes(b'original')
    monkeypatch.setattr(m, 'reconcile', lambda *args, **kwargs: (saved, None, {}, {}))
    assert m.verify(path, m.digest(raw)) == saved and source.read_bytes() == b'original'
    source.write_bytes(b'changed!')
    with pytest.raises(ValueError, match='Original source bytes changed'): m.verify(path, m.digest(raw))
    assert source.read_bytes() == b'changed!'


def test_observed_stream_profiles_keep_chunks_and_reject_cross_stream_identity_or_order(tmp_path):
    rows, summary = fixture()
    retry2 = deepcopy(rows[1]); retry2['params']['update']['attempt'] = 2
    retry3 = deepcopy(rows[1]); retry3['params']['update']['attempt'] = 3
    profiles = [[rows[0], rows[1], retry2, *rows[2:]], [rows[0], rows[1], retry2, retry3, *rows[2:]],
                [rows[0], rows[2], rows[1], rows[3], retry2, deepcopy(rows[2]), deepcopy(rows[3]), rows[4]]]
    for values in profiles:
        values = deepcopy(values)
        for n, value in enumerate(values): value['params']['_meta']['eventId'] = str(n)
        raw = m.canonical(values)
        kept, diagnostics = m.observed_decode_stream_projection(generic.grok_projection, values, summary, 'session', 'prompt')
        assert m.canonical(values) == raw and kept == [v for v in values if v['params']['update']['sessionUpdate'] != 'retry_state']
        assert [v['attempt'] for v in diagnostics] == list(range(1, len(diagnostics) + 1))
        with pytest.raises(ValueError): m.decode_projection(generic.grok_projection, values, summary, 'session', 'prompt')
    values = deepcopy(profiles[-1])
    for n, value in enumerate(values): value['params']['_meta']['eventId'] = str(n)
    bad = deepcopy(values); bad[1]['params']['_meta']['eventId'] = bad[2]['params']['_meta']['eventId']
    with pytest.raises(ValueError, match='Duplicate event across'): m.observed_decode_stream_projection(generic.grok_projection, bad, summary, 'session', 'prompt')
    bad = deepcopy(values); bad[1]['timestamp'] = '2026-10-05T19:00:11Z'
    with pytest.raises(ValueError): m.observed_decode_stream_projection(generic.grok_projection, bad, summary, 'session', 'prompt')
    bad = deepcopy(values); bad[4]['params']['update']['attempt'] = 3
    with pytest.raises(ValueError): m.observed_decode_stream_projection(generic.grok_projection, bad, summary, 'session', 'prompt')
    sample = tmp_path / 'sample'; sample.mkdir(); (sample / 'native-identity.json').write_text('{"session_id":"session"}')
    with pytest.raises(ValueError, match='snapshot commitment missing'):
        m.saved_completion(sample, b'prompt', tmp_path / 'session', {}, {}, snapshot=tmp_path, commitments={})
