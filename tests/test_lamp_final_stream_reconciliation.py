"""Canonical saved-answer and immutable descendant boundaries; no provider calls."""
from copy import deepcopy
import importlib.util
from pathlib import Path
import sys

import pytest

REPO = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec); sys.modules[name] = module
    spec.loader.exec_module(module); return module


m = load('test_lamp_final_projection', REPO / 'evaluation-results/hbq-native-transport-recovery-v1/reconcile_lamp_final_stream.py')
decode = load('test_lamp_final_decode', m.HERE / 'reconcile_failed_suffix.py')
generic = load('test_lamp_final_generic', m.HERE / 'reconcile.py')


def fixture(monkeypatch):
    early, final = '{"unfinished":', '{"verdicts":[]}'
    monkeypatch.setattr(m, 'EARLY_SHA', m.digest(early.encode())); monkeypatch.setattr(m, 'EARLY_BYTES', len(early))
    monkeypatch.setattr(m, 'FINAL_SHA', m.digest(final.encode())); monkeypatch.setattr(m, 'FINAL_BYTES', len(final))
    summary = {'created_at': '2026-10-05T19:00:00Z', 'updated_at': '2026-10-05T19:01:00Z', 'reasoning_effort': 'high', 'request_id': 'request'}
    kinds = ['user_message_chunk', 'agent_thought_chunk', 'retry_state', 'agent_message_chunk',
             'retry_state', 'agent_thought_chunk', 'agent_message_chunk', 'turn_completed']
    rows = []
    for n, kind in enumerate(kinds):
        meta = {'eventId': str(n), 'agentTimestampMs': 1000 + n}; update = {'sessionUpdate': kind}
        if kind == 'retry_state':
            update.update(type='retrying', attempt=1 if n == 2 else 2, max_retries=15, reason=decode.DECODE, error_type='http')
        elif kind == 'turn_completed': update.update(elapsed_ms=10, prompt_id='request', stop_reason='end_turn', usage={})
        else:
            update['content'] = {'type': 'text', 'text': 'prompt' if n == 0 else early if n == 3 else final if n == 6 else 'synthetic thought'}
            if n == 0: update['_meta'] = {'modelId': 'grok-4.7', 'promptIndex': 0}
            else: meta.update(totalTokens=2, promptId='request', streamStartMs=100 if n < 5 else 200, turnStartMs=50,
                              updateType='AgentThoughtChunk' if kind == 'agent_thought_chunk' else 'AgentMessageChunk', chunkId=n)
        rows.append({'timestamp': '2026-10-05T19:00:10Z', 'method': '_x.ai/session/update' if kind in {'retry_state', 'turn_completed'} else 'session/update',
                     'params': {'sessionId': 'session', 'update': update, '_meta': meta}})
    return rows, summary, [{'type': 'assistant', 'content': final}]


def test_only_incomplete_earlier_stream_and_unique_own_canonical_final_can_project(monkeypatch):
    rows, summary, chat = fixture(monkeypatch); raw = m.canonical(rows)
    project = lambda values, messages=chat: m.final_stream_projection(generic.grok_projection, decode.observed_decode_stream_projection,
                                                                     values, summary, 'session', 'prompt', messages)
    kept, diagnostics = project(rows)
    assert kept == [rows[n] for n in (0, 5, 6, 7)] and [v['attempt'] for v in diagnostics] == [1, 2]
    assert m.canonical(rows) == raw
    bad = deepcopy(rows); bad[5]['params']['_meta']['streamStartMs'] = 300
    with pytest.raises(ValueError, match='stream binding'): project(bad)
    with pytest.raises(ValueError, match='ambiguous'): project(rows, chat * 2)
    bad = deepcopy(rows); bad[2]['params']['update']['reason'] = 'unknown retry'
    with pytest.raises(ValueError): project(bad)
    bad = deepcopy(rows); bad[3]['params']['update']['content']['text'] = '{}'
    monkeypatch.setattr(m, 'EARLY_SHA', m.digest(b'{}')); monkeypatch.setattr(m, 'EARLY_BYTES', 2)
    with pytest.raises(ValueError, match='complete alternative'): project(bad)


def test_fresh_output_snapshot_and_original_provenance_are_not_overwritten(tmp_path, monkeypatch):
    output = tmp_path / 'descendant'; assert m.fresh_output(output) == output.resolve()
    with pytest.raises(ValueError, match='outside retained'): m.fresh_output(m.SOURCE / 'new')
    output.mkdir()
    with pytest.raises(ValueError, match='fresh'): m.fresh_output(output)
    source = tmp_path / 'original'; source.write_bytes(b'original')
    saved = {'implementation_sha256': m.digest(b'fixture'), 'source_commitments': {
        'raw': {'source_locator_local_only': str(source), 'sha256': m.digest(b'original'), 'bytes': 8, 'snapshot': 'raw.bin'}}}
    raw = m.canonical(saved); path = output / 'reconciliation.json'; path.write_bytes(raw)
    (output / m.Path(m.__file__).name).write_bytes(b'fixture'); (output / 'raw.bin').write_bytes(b'original')
    (output / 'response.json').write_bytes(b'response'); (output / 'acceptance.json').write_bytes(b'acceptance')
    monkeypatch.setattr(m, 'reconcile', lambda **kwargs: (saved, None, b'response', b'acceptance'))
    assert m.verify(path, m.digest(raw)) == saved and source.read_bytes() == b'original'
    (output / 'raw.bin').write_bytes(b'corrupt!')
    with pytest.raises(ValueError, match='snapshot differs'): m.verify(path, m.digest(raw))
    (output / 'raw.bin').write_bytes(b'original'); source.write_bytes(b'changed!')
    with pytest.raises(ValueError, match='Original source bytes changed'): m.verify(path, m.digest(raw))
    assert source.read_bytes() == b'changed!'
