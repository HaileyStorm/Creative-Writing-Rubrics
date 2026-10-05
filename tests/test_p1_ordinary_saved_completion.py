"""Synthetic boundary proof for the fixed, non-contacting Grok209 recipient."""
import copy
import importlib.util
from pathlib import Path
import unittest


PATH = Path(__file__).resolve().parents[1] / 'evaluation-results/hbq-native-transport-recovery-v1/reconcile_p1_ordinary_completion.py'
SPEC = importlib.util.spec_from_file_location('test_p1_ordinary_recipient', PATH)
p = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(p)


class OrdinarySavedCompletionTests(unittest.TestCase):
    def test_exact_final_lf_and_ordinary_native_lifecycle(self):
        generic = p.load('test_p1_ordinary_generic', p.HERE / p.CODE['generic'][0])
        summary = {'created_at': '2026-10-05T00:00:00Z', 'updated_at': '2026-10-05T00:00:04Z',
                   'current_model_id': 'grok-4.7', 'reasoning_effort': 'high', 'request_id': 'request'}
        assistant = {'model_id': 'grok-4.7-build', 'reasoning_effort': 'high'}
        kinds = ['user_message_chunk', 'agent_thought_chunk', 'agent_message_chunk', 'turn_completed']
        rows = []
        for index, kind in enumerate(kinds):
            meta = {'eventId': str(index), 'agentTimestampMs': index}
            update = {'sessionUpdate': kind}
            if kind == 'turn_completed':
                update.update(elapsed_ms=3000, prompt_id='request', stop_reason='end_turn', usage={})
            else:
                update['content'] = {'type': 'text', 'text': 'abc' if index == 0 else 'synthetic'}
                if kind == 'user_message_chunk':
                    update['_meta'] = {'modelId': 'grok-4.7', 'promptIndex': 0}
                else:
                    meta.update(totalTokens=1, promptId='request', streamStartMs=0, turnStartMs=0,
                                updateType='AgentThoughtChunk' if index == 1 else 'AgentMessageChunk', chunkId=index)
            rows.append({'timestamp': f'2026-10-05T00:00:0{index}Z',
                         'method': '_x.ai/session/update' if index == 3 else 'session/update',
                         'params': {'sessionId': p.SESSION, 'update': update, '_meta': meta}})
        p.ordinary_records(generic, rows, summary, p.SESSION, b'abc\n', 'abc', assistant)
        for prompt, history, user in [(b'abc\n', 'abc ', 'abc '), (b'abc\n', 'abc\n', 'abc\n'),
                                      (b'abc\n', 'abc', 'abC'), (b'abc', 'abc', 'abc')]:
            with self.subTest(prompt=prompt, history=history, user=user), self.assertRaises(ValueError):
                p.exact_native_prompt(prompt, history, user)
        mutations = []
        foreign = copy.deepcopy(rows)
        foreign[1]['params']['sessionId'] = 'foreign'
        mutations.append(foreign)
        wrong_prompt = copy.deepcopy(rows)
        wrong_prompt[2]['params']['_meta']['promptId'] = 'foreign'
        mutations.append(wrong_prompt)
        unknown = copy.deepcopy(rows)
        unknown[1]['params']['update']['sessionUpdate'] = 'retry_state'
        mutations.append(unknown)
        tool = copy.deepcopy(rows)
        tool[1]['params']['update']['sessionUpdate'] = 'tool_call'
        mutations.append(tool)
        incomplete = copy.deepcopy(rows)
        incomplete[-1]['params']['update']['stop_reason'] = 'cancelled'
        mutations.extend([incomplete, rows[:-1]])
        stale = copy.deepcopy(rows)
        stale[2]['timestamp'] = '2026-10-06T00:00:00Z'
        mutations.append(stale)
        for changed in mutations:
            with self.subTest(changed=mutations.index(changed)), self.assertRaises(ValueError):
                p.ordinary_records(generic, changed, summary, p.SESSION, b'abc\n', 'abc', assistant)
        for changed in [dict(assistant, reasoning_effort='low'), dict(assistant, model_id='other')]:
            with self.assertRaises(ValueError):
                p.ordinary_records(generic, rows, summary, p.SESSION, b'abc\n', 'abc', changed)

    def test_same_original_identity_and_semantic_rejection_preserved(self):
        row = {'endpoint': 'grok', 'endpoint_ordinal': 209, 'logical_sample_id': p.LOGICAL,
               'request_sha256': p.REQUEST_SHA}
        started = {'session_id': p.SESSION, 'job_sha256': p.JOB_SHA}
        native = {'session_id': p.SESSION}
        response = b'{"method":"ttcw14","verdicts":[]}'
        before = copy.deepcopy((row, started, native))
        for accepted, state in [(True, 'accepted'), (False, 'semantic_rejected')]:
            result = p.observation(row, started, native, response,
                                   {'accepted': accepted, 'errors': [] if accepted else ['synthetic missing leaf']})
            self.assertEqual(result['state'], state)
            self.assertEqual(result['response_sha256'], p.digest(response))
            self.assertEqual(result['admission']['accepted'], accepted)
            self.assertEqual((result['original_state'], result['new_votes'], result['same_original_observation_only'],
                              result['no_resend'], result['native']['original_strict_v5_admission_satisfied']),
                             ('ambiguous', 0, True, True, False))
        self.assertEqual((row, started, native), before)
        for changed in [dict(row, endpoint_ordinal=210), dict(row, logical_sample_id='foreign'),
                        dict(row, request_sha256='foreign')]:
            with self.assertRaises(ValueError):
                p.observation(changed, started, native, response, {'accepted': True})
        for changed in [dict(started, session_id='foreign'), dict(started, job_sha256='foreign')]:
            with self.assertRaises(ValueError):
                p.observation(row, changed, native, response, {'accepted': True})
        with self.assertRaises(ValueError):
            p.observation(row, started, {'session_id': 'foreign'}, response, {'accepted': True})


if __name__ == '__main__':
    unittest.main()
