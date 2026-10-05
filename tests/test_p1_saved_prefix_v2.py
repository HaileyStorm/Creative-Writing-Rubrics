"""Synthetic prefix reservation, saved lifecycle, and failure-drain witnesses."""
import copy
import importlib.util
from pathlib import Path
import threading
import unittest

PATH = Path(__file__).resolve().parents[1] / 'evaluation-results/hbq-native-transport-recovery-v1/continue_p1_saved_prefix_v2.py'
SPEC = importlib.util.spec_from_file_location('test_p1_saved_prefix_v2_owned', PATH)
p = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(p)


class SavedPrefixV2Tests(unittest.TestCase):
    def test_prefix_fixed_identity_once_and_untouched_suffix_never_resends(self):
        rows = [{'endpoint': 'grok', 'endpoint_ordinal': n, 'logical_sample_id': f'logical-{n}',
                 'request_sha256': f'request-{n}'} for n in range(1, 793)]
        prefix = [dict(row, state='ambiguous' if row['endpoint_ordinal'] in (148, 209) else 'accepted',
                       source_job_sha256=p.JOB_SHA, source_terminal_sha256=f'terminal-{row["endpoint_ordinal"]}',
                       native_identity=f'native-{row["endpoint_ordinal"]}', no_resend=True, new_votes=0)
                  for row in rows[:215]]
        fixed = dict(prefix[208], original_state='ambiguous', state='accepted',
                     native={'saved_history': {'session_id': 'native-209'}},
                     same_original_observation_only=True, human_labels_opened=False, admission={'accepted': True})
        before = copy.deepcopy(prefix)
        joined = p.reserve_once(prefix, rows, fixed)
        self.assertEqual(prefix, before)
        self.assertEqual(joined[147]['state'], 'ambiguous')
        self.assertEqual(joined[208]['state'], 'accepted')
        self.assertEqual(joined[208]['original_state'], 'ambiguous')
        plan = {'endpoint': 'grok', 'reserved_through': 215,
                'untouched_request_sha256s': [row['request_sha256'] for row in rows[215:]]}
        suffix = p.f.suffix_rows(plan, {'manifest': {'requests': rows}})
        self.assertEqual([row['endpoint_ordinal'] for row in suffix], list(range(216, 793)))
        self.assertEqual(len(suffix), 577)
        with self.assertRaises(ValueError):
            p.reserve_once(joined, rows, fixed)
        for changed in [dict(fixed, request_sha256='foreign'), dict(fixed, source_job_sha256='foreign'),
                        dict(fixed, native={'saved_history': {'session_id': 'foreign'}})]:
            with self.assertRaises(ValueError):
                p.reserve_once(prefix, rows, changed)
        duplicate = copy.deepcopy(prefix)
        duplicate[1]['native_identity'] = duplicate[0]['native_identity']
        with self.assertRaises(ValueError):
            p.reserve_once(duplicate, rows, fixed)
        rejected = dict(fixed, state='semantic_rejected', admission={'accepted': False})
        self.assertEqual(p.reserve_once(prefix, rows, rejected)[208]['state'], 'semantic_rejected')

    def test_ordinary_byte_contract_and_failure_drains_started_calls(self):
        summary = {'created_at': '2026-10-05T00:00:00Z', 'updated_at': '2026-10-05T00:00:04Z',
                   'current_model_id': 'grok-4.7', 'reasoning_effort': 'high', 'request_id': 'request'}
        assistant = {'model_id': 'grok-4.7-build', 'reasoning_effort': 'high'}
        kinds = ['user_message_chunk', 'agent_thought_chunk', 'agent_message_chunk', 'turn_completed']
        rows = []
        for index, kind in enumerate(kinds):
            meta = {'eventId': str(index), 'agentTimestampMs': index}
            update = {'sessionUpdate': kind}
            if index == 3:
                update.update(elapsed_ms=3000, prompt_id='request', stop_reason='end_turn', usage={})
            else:
                update['content'] = {'type': 'text', 'text': 'synthetic' if index else 'abc'}
                if index == 0:
                    update['_meta'] = {'modelId': 'grok-4.7', 'promptIndex': 0}
                else:
                    meta.update(totalTokens=1, promptId='request', streamStartMs=0, turnStartMs=0,
                                updateType='AgentThoughtChunk' if index == 1 else 'AgentMessageChunk', chunkId=index)
            rows.append({'timestamp': f'2026-10-05T00:00:0{index}Z',
                         'method': '_x.ai/session/update' if index == 3 else 'session/update',
                         'params': {'sessionId': 'own', 'update': update, '_meta': meta}})
        for prompt in (b'abc', b'abc\n'):
            p.ordinary_records(rows, summary, 'own', prompt, 'abc', assistant)
        for history in ('abc ', 'abc\n'):
            with self.assertRaises(ValueError):
                p.ordinary_records(rows, summary, 'own', b'abc\n', history, assistant)
        foreign = copy.deepcopy(rows)
        foreign[1]['params']['sessionId'] = 'foreign'
        unknown = copy.deepcopy(rows)
        unknown[1]['params']['update']['sessionUpdate'] = 'retry_state'
        for changed in (foreign, unknown, rows[:-1]):
            with self.assertRaises(ValueError):
                p.ordinary_records(changed, summary, 'own', b'abc\n', 'abc', assistant)
        barrier, stop, failed_ready = threading.Barrier(2), threading.Event(), threading.Event()
        started, retained = [], []
        def call(ordinal):
            started.append(ordinal)
            barrier.wait(timeout=3)
            if ordinal == 1:
                stop.set()
                failed_ready.set()
                return 'ambiguous'
            self.assertTrue(failed_ready.wait(timeout=3))
            retained.append(ordinal)
            return 'accepted'
        observed, failed = p.f.dispatch([1, 2, 3], call, 2, stop.is_set, {'accepted', 'semantic_rejected'})
        self.assertTrue(failed)
        self.assertEqual(set(started), {1, 2})
        self.assertEqual(retained, [2])
        self.assertEqual(dict(observed), {1: 'ambiguous', 2: 'accepted'})


if __name__ == '__main__':
    unittest.main()
