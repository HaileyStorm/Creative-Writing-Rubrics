"""Provider-free witnesses for reserved observations and bounded suffix dispatch."""
import importlib.util
import json
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

PATH = Path(__file__).resolve().parents[1] / 'evaluation-results/hbq-native-transport-recovery-v1/continue_saved_decode.py'
spec = importlib.util.spec_from_file_location('test_saved_decode_continuation_owned', PATH)
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)


def row(ordinal):
    return {'endpoint': 'grok', 'endpoint_ordinal': ordinal, 'logical_sample_id': f'logical-{ordinal}',
            'request_sha256': f'request-{ordinal}'}


def prefix(ordinal, state='accepted'):
    return dict(row(ordinal), state=state, source_terminal_sha256=f'terminal-{ordinal}',
                native_identity=f'native-{ordinal}', no_resend=True)


def overlay(ordinal):
    return dict(row(ordinal), original_state='ambiguous', state='accepted', source_job_sha256='job',
                source_terminal_sha256=f'terminal-{ordinal}', native={'saved_history': {'session_id': f'native-{ordinal}'}},
                same_original_observation_only=True, new_votes=0, no_resend=True)


class SavedDecodeContinuationTests(unittest.TestCase):
    def test_overlay_keeps_original_missing_and_never_adds_a_slot(self):
        original = [prefix(1, 'ambiguous'), prefix(2, 'ambiguous'), prefix(3)]
        joined = c.joined_prefix(original, [row(n) for n in range(1, 5)], [overlay(2)], through=3, job_sha='job')
        self.assertEqual([e['state'] for e in joined], ['ambiguous', 'accepted', 'accepted'])
        self.assertEqual(joined[1]['original_state'], 'ambiguous')
        self.assertEqual(original[1]['state'], 'ambiguous')
        plan = {'endpoint': 'grok', 'reserved_through': 3, 'untouched_request_sha256s': ['request-4']}
        self.assertEqual(c.f.suffix_rows(plan, {'manifest': {'requests': [row(n) for n in range(1, 5)]}}), [row(4)])

    def test_duplicate_or_foreign_saved_observation_rejected(self):
        for changes in ({'source_job_sha256': 'foreign'}, {'source_terminal_sha256': 'stale'},
                        {'logical_sample_id': 'other'}, {'native': {'saved_history': {'session_id': 'foreign'}}}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                c.joined_prefix([prefix(1, 'ambiguous')], [row(1)], [dict(overlay(1), **changes)], through=1, job_sha='job')
        with self.assertRaisesRegex(ValueError, 'Duplicate saved overlay'):
            c.joined_prefix([prefix(1, 'ambiguous')], [row(1)], [overlay(1), overlay(1)], through=1, job_sha='job')

    def test_started_slot_is_reserved_before_any_replay_or_resend(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder)
            binding = {'workers': 1}
            (output / 'job.json').write_text(json.dumps(binding))
            sample = output / '0002-logical-2'
            sample.mkdir()
            (sample / 'attempt-started.json').write_text('{}')
            module = SimpleNamespace(sample_path=lambda root, r: root / f"{r['endpoint_ordinal']:04d}-{r['logical_sample_id']}")
            ctx = {'manifest': {'requests': [row(1), row(2)]}, 'module': module}
            plan = {'endpoint': 'grok', 'reserved_through': 1, 'untouched_request_sha256s': ['request-2'], 'prefix': [prefix(1)]}
            with patch.object(c, 'effective_replay') as replay, self.assertRaisesRegex(ValueError, 'Started/incomplete'):
                c.inventory(plan, ctx, output, binding)
            replay.assert_not_called()

    def test_reserved_prefix_cannot_appear_in_fresh_suffix_inventory(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder)
            binding = {}
            (output / 'job.json').write_text('{}')
            (output / '0001-logical-1').mkdir()
            module = SimpleNamespace(sample_path=lambda root, r: root / f"{r['endpoint_ordinal']:04d}-{r['logical_sample_id']}")
            ctx = {'manifest': {'requests': [row(1), row(2)]}, 'module': module}
            plan = {'endpoint': 'grok', 'reserved_through': 1, 'untouched_request_sha256s': ['request-2'], 'prefix': [prefix(1)]}
            with self.assertRaisesRegex(ValueError, 'Reserved or unknown'):
                c.inventory(plan, ctx, output, binding)

    def test_native_is_explicit_and_stop_prevents_broker_import_or_contact(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder)
            (output / 'STOP').touch()
            module = SimpleNamespace(SETTLED={'accepted', 'semantic_rejected'}, note_stop=lambda p: None)
            ctx = {'module': module}
            with patch.object(c, 'inventory', return_value=([row(2)], [])), patch.object(c.f, 'reviewed_route') as route:
                with self.assertRaisesRegex(ValueError, 'explicit current owner'):
                    c.collect({}, ctx, output, {}, None)
                self.assertEqual(c.collect({}, ctx, output, {}, None, execute_native=True, headroom=True, route_confirmed=True), 3)
            route.assert_not_called()

    def test_failure_drains_already_started_calls_without_next_dispatch(self):
        entered = threading.Event()
        release = threading.Event()
        drained = threading.Event()
        observed = []
        def call(value):
            observed.append(value)
            if value == 1:
                if not entered.wait(2):
                    raise AssertionError('Second bounded call did not start')
                release.set()
                return 'ambiguous'
            entered.set()
            if not release.wait(2):
                raise AssertionError('First failure did not settle')
            drained.set()
            return 'accepted'
        _, failed = c.f.dispatch([1, 2, 3], call, 2, lambda: False, {'accepted'})
        self.assertTrue(failed)
        self.assertTrue(drained.is_set())
        self.assertEqual(sorted(observed), [1, 2])

    def test_endpoint_completion_and_explicit_flag_cannot_open_full_study_labels(self):
        plan = {'human_label_gate': 'registered-full-study-gate', 'full_planned_denominator': 868,
                'endpoint_denominator': 434, 'prefix': [prefix(1, 'ambiguous')]}
        gate = c.label_gate(plan, ['accepted'] * 433, [], explicit=True)
        self.assertFalse(gate['human_release_eligible'])
        self.assertFalse(gate['human_targets_opened'])
        self.assertEqual(gate['planned'], 868)
        self.assertEqual(gate['reserved_missing'], 1)

    def test_mock_only_saved_descendant_replays_without_rewriting_failed_terminal(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / 'output'
            output.mkdir()
            session = '12345678-1234-4234-8234-123456789abc'
            sessions = Path(folder) / 'sessions'
            selected = sessions / 'own-cwd' / session
            selected.mkdir(parents=True)
            (selected / 'summary.json').write_bytes(b'{}')
            item = dict(row(2), arm='fixture', prompt_sha256=c.digest(b'prompt'), schema_sha256=c.digest(b'{}'))
            binding = {'manifest_sha256': 'manifest'}
            job_raw = c.canonical(binding)
            (output / 'job.json').write_bytes(job_raw)
            sample = output / '0002-logical-2'
            sample.mkdir()
            terminal = {'state': 'ambiguous', 'no_resend': True}
            started = {'manifest_sha256': 'manifest', 'logical_sample_id': item['logical_sample_id'], 'attempt': 1,
                       'no_resend': True, 'job_sha256': c.digest(job_raw), 'session_id': session,
                       'prompt_sha256': item['prompt_sha256'], 'schema_sha256': item['schema_sha256']}
            for name, data in {'terminal.json': terminal, 'condition.json': item, 'attempt-started.json': started,
                               'native-identity.json': {'logical_sample_id': item['logical_sample_id'], 'session_id': session},
                               'native-result.json': {'state': 'ambiguous', 'result': None,
                                                      'failure': {'code': 'validation_tool_policy_attestation'}}}.items():
                (sample / name).write_bytes(c.canonical(data))
            (sample / 'prompt.txt').write_bytes(b'prompt')
            (sample / 'schema.json').write_bytes(b'{}')
            before = (sample / 'terminal.json').read_bytes()
            calls = []
            def saved_completion(sample, prompt, selected, started, job, *, snapshot=None, commitments=None):
                calls.append(snapshot is not None)
                reads = c.r.ReadSet(snapshot, commitments)
                reads.raw('summary', selected / 'summary.json')
                return {'score': 2}, {'policy': 'fixed-five-row-profile', 'saved_history': {'session_id': session}}, reads
            module = SimpleNamespace(sample_path=lambda root, row: root / '0002-logical-2',
                                     replay=lambda *args: (terminal, None),
                                     inputs=lambda *args: (b'prompt', b'{}', [], 'same-frozen-context'),
                                     record=lambda path, value: c.write(path, c.canonical(value)))
            admission = SimpleNamespace(semantic_validate=lambda arm, answer, row, texts, subset, **kwargs:
                                        {'accepted': answer == {'score': 2} and kwargs['context'] == 'same-frozen-context'})
            ctx = {'module': module, 'manifest': {}, 'root': output, 'validator': admission,
                   'subset': SimpleNamespace(validate_schema=lambda schema: None),
                   'saved_decode_reader': SimpleNamespace(POLICY='fixed-five-row-profile', SESSIONS=sessions,
                                                         saved_completion=saved_completion)}
            self.assertEqual(c.projected_sample(ctx, item, output, binding)[0], 'accepted')
            self.assertEqual(c.effective_replay(ctx, item, output, binding), ('accepted', {'score': 2}))
            self.assertEqual(calls, [False, True])
            self.assertEqual((sample / 'terminal.json').read_bytes(), before)
            self.assertFalse((sample / 'native-envelope.json').exists())
            receipt = json.loads((sample / 'decode-reconciliation.json').read_bytes())
            self.assertEqual(receipt['new_votes'], 0)
            self.assertFalse(receipt['original_strict_v5_admission_satisfied'])
            (sample / 'condition.json').write_bytes(c.canonical(dict(item, logical_sample_id='foreign')))
            with self.assertRaisesRegex(ValueError, 'Reserved condition differs'):
                c.effective_replay(ctx, item, output, binding)
            (sample / 'condition.json').write_bytes(c.canonical(item))
            rejected_output = Path(folder) / 'rejected-output'
            rejected_output.mkdir()
            (rejected_output / 'job.json').write_bytes(job_raw)
            rejected_sample = rejected_output / sample.name
            rejected_sample.mkdir()
            for original in sample.iterdir():
                if original.is_file() and original.name != 'decode-reconciliation.json':
                    (rejected_sample / original.name).write_bytes(original.read_bytes())
            ctx['validator'] = SimpleNamespace(semantic_validate=lambda *args, **kwargs: {'accepted': False})
            self.assertEqual(c.projected_sample(ctx, item, rejected_output, binding), ('semantic_rejected', None))
            self.assertEqual(c.effective_replay(ctx, item, rejected_output, binding), ('semantic_rejected', None))
            rejected_receipt = json.loads((rejected_sample / 'decode-reconciliation.json').read_bytes())
            self.assertEqual(rejected_receipt['response'], {'score': 2})
            self.assertEqual((rejected_sample / 'terminal.json').read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
