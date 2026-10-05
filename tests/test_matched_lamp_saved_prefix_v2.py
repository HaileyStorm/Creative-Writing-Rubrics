"""Focused local proof for frozen-prefix dispatch and qualified saved representations."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import sys
import threading
from types import SimpleNamespace
from unittest.mock import patch

import pytest

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('test_lamp_saved_prefix_v2', REPO / 'evaluation-results/hbq-matched-lamp-20261004/collector_saved_prefix_v2.py')
m = importlib.util.module_from_spec(spec); sys.modules[spec.name] = m; spec.loader.exec_module(m)


def synthetic_rows():
    return [{'endpoint': 'grok', 'endpoint_ordinal': n, 'logical_sample_id': str(n).zfill(64),
             'request_sha256': 'request-' + str(n)} for n in range(1, 8905)]


def test_once_only_prefix_identity_and_unknown_failure_stop_drains_started_sibling(tmp_path):
    rows = synthetic_rows()
    prefix = {'entries': [{'ordinal': row['endpoint_ordinal'], 'request_sha256': row['request_sha256'],
        'logical_sample_id': row['logical_sample_id'], 'effective_terminal': {'state': 'accepted',
        'native_thread_id': 'native-' + str(row['endpoint_ordinal'])}} for row in rows[:122]]}
    manifest = {'requests': rows}
    pending, states, ids = m.inventory(manifest, {}, tmp_path, None, None, None, prefix, None)
    assert len(pending) == 8782 and len(states) == len(ids) == 122
    assert pending[0]['endpoint_ordinal'] == 123 and len(pending) + len(states) == 8904
    duplicate = deepcopy(prefix); duplicate['entries'][121]['effective_terminal']['native_thread_id'] = 'native-1'
    with pytest.raises(ValueError, match='Duplicate effective'):
        m.inventory(manifest, {}, tmp_path, None, None, None, duplicate, None)
    with patch.object(m.c, 'collect_one') as native:
        with pytest.raises(ValueError, match='Reserved prefix'):
            m.collect_one(rows[121], {}, {}, tmp_path, None, None, None, None, m.c.CommitState(), None)
        native.assert_not_called()
    m.c.sample_path(tmp_path, rows[0]).mkdir()
    with pytest.raises(ValueError, match='redispatched'):
        m.inventory(manifest, {}, tmp_path, None, None, None, prefix, None)
    parent = m.c.CommitState(); barrier = threading.Barrier(2); started, settled = [], []
    def strict(row, *args, commit, **kwargs):
        started.append(row['endpoint_ordinal']); barrier.wait(timeout=3)
        if row['endpoint_ordinal'] == 123: commit.stop.set(); return 'ambiguous'
        parent.stop.wait(timeout=3); settled.append(row['endpoint_ordinal']); return 'accepted'
    with patch.object(m.c, 'collect_one', strict), patch.object(m, 'project', side_effect=ValueError('Unknown completion')):
        with pytest.raises(ValueError, match='Unknown completion'):
            m.c.dispatch(rows[122:130], 2, lambda row: m.collect_one(row, {}, {}, tmp_path, None, None, None,
                                                                  None, parent, None), parent)
    assert parent.stop.is_set() and sorted(started) == [123, 124] and settled == [124]
    assert m.d.SampleCommit(parent).stop.is_set()


def test_ordinary_saved_prompt_accepts_only_exact_or_200a_and_preserves_native_records():
    def fixture(text):
        updates = [{'params': {'sessionId': 'own', 'update': {'sessionUpdate': kind}}}
                   for kind in ('user_message_chunk', 'agent_thought_chunk', 'agent_message_chunk', 'turn_completed')]
        updates[0]['params']['update']['content'] = {'type': 'text', 'text': text}
        return updates, [{'session_id': 'own', 'prompt': text}]
    prompt = b'exact source and task \n'; updates, histories = fixture(prompt.decode())
    before = m.canonical(updates)
    assert m.qualified_prompt(prompt, updates, histories, 'own') == (prompt, 'exact')
    assert m.canonical(updates) == before
    updates, histories = fixture('exact source and task')
    assert m.qualified_prompt(prompt, updates, histories, 'own') == (prompt[:-2], 'terminal_200a_omission')
    for frozen in (b'exact source and task\n', b'exact source and task\t\n', b'exact source and task\r\n',
                   b'exact source and task  \n', b'altered source and task \n'):
        with pytest.raises(ValueError): m.qualified_prompt(frozen, updates, histories, 'own')
    updates[0]['params']['sessionId'] = 'other'
    with pytest.raises(ValueError): m.qualified_prompt(prompt, updates, histories, 'own')


def test_qualified_saved_response_and_rejection_remain_same_observation_on_snapshot_replay(tmp_path):
    row = synthetic_rows()[122]; sample = m.c.sample_path(tmp_path, row); sample.mkdir()
    original = b'{"state":"ambiguous","accepted":false}\n'; (sample / 'terminal.json').write_bytes(original)
    response = {'winner': 'A', 'evidence': [{'quote': 'absent quotation'}]}
    receipt = {'policy': m.POLICY, 'source_artifacts': m.d.artifacts(sample), 'response': response,
        'acceptance': {'accepted': False, 'abstention': False, 'errors': ['Pair quote is not on the declared side']},
        'effective_terminal': {'state': 'semantic_rejected', 'native_thread_id': 'same-own-observation',
                               'strict_v5_satisfied': False, 'exact_original_outbound_bytes_proven': False},
        'history_commitments': {}, 'new_votes': 0, 'original_strict_v5_admission_satisfied': False}
    reads = SimpleNamespace(raws={'updates': b'original native history'})
    parent = m.c.CommitState()
    def strict(*args, commit, **kwargs): commit.stop.set(); return 'ambiguous'
    with patch.object(m.c, 'collect_one', strict), patch.object(m, 'project', return_value=(receipt, reads)):
        assert m.collect_one(row, {}, {}, tmp_path, None, None, None, None, parent, None) == 'semantic_rejected'
    assert not parent.stop.is_set() and parent.native_ids == {'same-own-observation'}
    saved = json.loads(m.d.receipt_path(tmp_path, row).read_bytes())
    assert saved['response'] == response and saved['acceptance']['accepted'] is False and saved['new_votes'] == 0
    assert (sample / 'terminal.json').read_bytes() == original
    assert (tmp_path / ('decode-snapshot-' + sample.name) / 'updates').read_bytes() == reads.raws['updates']
    rows = synthetic_rows(); prefix = {'entries': [{'ordinal': value['endpoint_ordinal'], 'request_sha256': value['request_sha256'],
        'logical_sample_id': value['logical_sample_id'], 'effective_terminal': {'state': 'accepted',
        'native_thread_id': 'prefix-' + str(value['endpoint_ordinal'])}} for value in rows[:122]]}
    with patch.object(m, 'project', return_value=(receipt, reads)):
        pending, states, ids = m.inventory({'requests': rows}, {}, tmp_path, None, None, None, prefix, None)
    assert states[-1] == 'semantic_rejected' and len(pending) == 8781 and len(ids) == 123
    (sample / 'terminal.json').write_bytes(b'changed original')
    with pytest.raises(ValueError, match='Immutable sample'):
        m.inventory({'requests': rows}, {}, tmp_path, None, None, None, prefix, None)
