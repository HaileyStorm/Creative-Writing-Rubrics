"""Behavioral source, context and full-bank boundaries; synthetic data only."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
import threading
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('matched_lamp_preparation_test', REPO / 'evaluation-results/hbq-matched-lamp-20261004/prepare.py')
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)
sys.path.insert(0, str(REPO / 'src'))
from hbqrs import core, runner


class LampPreparationTests(unittest.TestCase):
    def test_membership_projection_cannot_consume_outcomes(self):
        class Forbidden(dict):
            def __getitem__(self, key):
                if key != 'id':
                    raise AssertionError('Outcome field read')
                return super().__getitem__(key)
        document = {'groups': [Forbidden(id='g1'), Forbidden(id='g2')]}
        self.assertEqual(p.membership_ids(document), {'g1', 'g2'})
        document['groups'].append(Forbidden(id='g1'))
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            p.membership_ids(document)

    def test_instruction_slice_preserves_nonascii_whitespace_and_bounds(self):
        instruction = 'écrire\r\n  '.encode()
        prefix = b'## Context: source-writing-instruction\n\n'
        suffix = b'\n\n## Artifact: sample.txt\n\npassage\n\n## Questions\n\n[]'
        prompt = prefix + instruction + suffix
        start, end = len(prefix), len(prefix) + len(instruction)
        locator = [0, 'g', 1, len(prompt), p.digest(prompt), start, end,
                   len(prefix.decode()), len((prefix + instruction).decode()), len(instruction), p.digest(instruction)]
        self.assertEqual(p.instruction_slice(prompt, locator, 'sample'), instruction)
        with self.assertRaisesRegex(ValueError, 'boundary'):
            p.instruction_slice(prompt, locator, 'foreign')
        locator[-1] = p.digest(instruction.rstrip())
        with self.assertRaisesRegex(ValueError, 'slice'):
            p.instruction_slice(prompt, locator, 'sample')

    def test_historical_trimming_never_changes_new_source(self):
        instruction, source = b'Keep the image. ', b'A window. '
        legacy = (b'## Context: source-writing-instruction\n\n' + instruction +
                  b'\n\n## Artifact: s.txt\n\n' + source[:-1] + b'\n\n## Questions\n\n[]')
        self.assertEqual(p.crosscheck_prompt(legacy, 's', instruction, source), 1)
        with self.assertRaisesRegex(ValueError, 'paragraph'):
            p.crosscheck_prompt(legacy.replace(b'A window.', b'A door.'), 's', instruction, source)
        task = p.task_contract('opaque')
        projection = runner._task_contract_judge_context(task)
        prompt = p.exact_hbq_prompt(runner, 'Judge independently.', 'opaque', source, instruction, projection, [])
        self.assertIn(b'\n\nA window. \n\n## Questions', prompt)
        self.assertIn(instruction + b'\n\n## Artifact', prompt)
        self.assertIn(json.dumps(projection, ensure_ascii=False, indent=2).encode(), prompt)

    def test_canonical_fullbank_and_unknown_completion_context(self):
        modules = core.load_modules(REPO / 'registry/all_modules.yaml')
        bundle = core.resolve_bundle(core.load_bundles(REPO / 'bundles/all_bundles.yaml'), 'prose.short_form')
        task = p.task_contract('opaque')
        compiled = core.compile_bundle(modules, bundle, task_contract=task)
        questions = core.compiled_questions(compiled)
        ids = [q['question']['id'] for q in questions]
        self.assertEqual(len(set(ids)), 170)
        self.assertEqual([len(ids[n:n+8]) for n in range(0, len(ids), 8)], [8]*21 + [2])
        self.assertEqual(task['context']['completion_status'], 'unknown')
        self.assertEqual(task['weighted_goals'], [])
        self.assertEqual(task['binding_requirements'], [])
        for offset in range(0, len(questions), 8):
            packet = questions[offset:offset+8]
            schema = runner._batch_response_schema([q['question']['id'] for q in packet])
            self.assertEqual(schema['properties']['verdicts']['minItems'], len(packet))

    def test_metadata_sentinels_ignore_prose_and_roles(self):
        groups = [{'id': f'g{s}-{n}', 'stratum': s, 'prose': object(), 'role': object()}
                  for s in range(6) for n in range(2)]
        result = p.select_sentinels(groups)
        self.assertEqual(len(set(result)), 6)
        self.assertEqual(result, p.select_sentinels(list(reversed(groups))))
        for s, key in enumerate(result):
            self.assertTrue(key.startswith(f'g{s}-'))

    def test_exact_pin_and_fresh_private_destination(self):
        mfa = p.load('lamp_test_paths', REPO / 'evaluation-results/hbq-matched-mfa-v1/extract.py')
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / 'source'
            source.mkdir()
            artifact = source / 'paragraph.txt'
            artifact.write_bytes(b'unchanged ')
            with self.assertRaisesRegex(ValueError, 'Pinned'):
                p.checked(artifact, p.digest(b'unchanged'))
            with self.assertRaisesRegex(ValueError, 'overlaps'):
                mfa.private_output(source / 'new', [source])
            with self.assertRaisesRegex(ValueError, 'fresh'):
                mfa.private_output(source, [])
            self.assertEqual(mfa.private_output(root / 'fresh', [source]), root / 'fresh')


class LampNativeCollectionTests(unittest.TestCase):
    """Local fixtures prove collection boundaries, not provider execution."""
    @classmethod
    def setUpClass(cls):
        cls.c = p.load('lamp_native_boundary_test', REPO / 'evaluation-results/hbq-matched-lamp-20261004/collector.py')

    def test_allocation_requires_explicit_owner_headroom_and_single_workers_argument(self):
        c = self.c
        c.allocation(10, ['collector.py', '--workers=10'], False, False)
        with self.assertRaisesRegex(ValueError, 'headroom'):
            c.allocation(10, ['collector.py', '--workers=10'], False, True)
        c.allocation(10, ['collector.py', '--workers', '10'], True, True)
        for workers, argv in [(11, ['--workers=11']), (1, ['--workers=1', '--workers', '1']), (2, ['--workers=1'])]:
            with self.assertRaises(ValueError): c.allocation(workers, argv, True, True)

    def test_exact_source_and_rendered_context_bind_own_task(self):
        c = self.c
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); files = {}
            def artifact(name, raw):
                (root / name).write_bytes(raw)
                meta = {'sha256': p.digest(raw), 'bytes': len(raw)}
                files[name] = meta
                return {'path': name, **meta}
            text = b'A window. '
            source = artifact('source.txt', text)
            task = p.task_contract('s')
            contract = artifact('contract.json', p.canonical(task))
            pretty = json.dumps(runner._task_contract_judge_context(task), ensure_ascii=False, indent=2).encode()
            context = artifact('context.json', pretty)
            shared = artifact('shared.txt', b'Preserve the image.\r\n ')
            prompt = artifact('prompt.txt', pretty + b'\n' + (root / 'shared.txt').read_bytes() + b'\n' + text)
            schema = artifact('schema.json', b'{}')
            row = {'prompt_path': 'prompt.txt', 'prompt_sha256': prompt['sha256'], 'prompt_bytes': prompt['bytes'],
                'schema_path': 'schema.json', 'schema_sha256': schema['sha256'], 'schema_bytes': schema['bytes'],
                'sources': [{'id': 's', 'input_path': 'source.txt', 'sha256': source['sha256'], 'bytes': source['bytes']}],
                'task_context': context, 'shared_work_context': shared,
                'task_contracts': [{'artifact_id': 's', 'path': 'contract.json', 'sha256': contract['sha256']}]}
            _, _, texts, admitted_context = c.inputs(root, {'artifacts': files}, row)
            self.assertEqual(texts['s'], 'A window. ')
            self.assertEqual(admitted_context, pretty.decode() + '\nPreserve the image.\r\n ')
            task['context']['completion_status'] = 'complete'
            changed = artifact('contract.json', p.canonical(task)); row['task_contracts'][0]['sha256'] = changed['sha256']
            with self.assertRaisesRegex(ValueError, 'task/context'):
                c.inputs(root, {'artifacts': files}, row)

    def test_grok_route_must_keep_v5_and_one_turn_before_job_creation(self):
        c = self.c
        for route in ({'nonvisual_transport_contract': 'grok_nonvisual_history_v6', 'nonvisual_max_turns': 1},
                      {'nonvisual_transport_contract': 'grok_nonvisual_history_v5', 'nonvisual_max_turns': 2}):
            with self.assertRaisesRegex(ValueError, 'one-turn v5'):
                c.job_binding({}, Path('.'), 'm', 'grok', Path('.'), route)

    def test_failure_or_stop_drains_started_calls_without_new_dispatch(self):
        c = self.c
        for external_stop in (False, True):
            commit = c.CommitState(); both = threading.Barrier(2); release = threading.Event(); settled = []
            def execute(row):
                both.wait(timeout=3)
                if row == 1:
                    commit.stop.set(); release.set()
                    return 'accepted' if external_stop else 'ambiguous'
                self.assertTrue(release.wait(timeout=3)); settled.append(row)
                return 'accepted'
            result = c.dispatch([1, 2, 3], 2, execute, commit, lambda: external_stop and commit.stop.is_set())
            self.assertEqual(settled, [2])
            self.assertEqual(len(result), 2)
            self.assertTrue(commit.stop.is_set())

    def test_reserved_unresolved_or_failed_slot_never_reenters_pending(self):
        c = self.c
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory); row = {'endpoint': 'sol', 'endpoint_ordinal': 1, 'logical_sample_id': 'a'*64}
            binding = {'endpoint': 'sol', 'manifest_sha256': 'm'}
            c.record(output / 'job.json', binding)
            sample = c.sample_path(output, row); sample.mkdir(); c.record(sample / 'condition.json', row)
            with self.assertRaisesRegex(ValueError, 'unresolved; no resend'):
                c.inventory({'requests': [row]}, binding, output, output, None, None, None)
            c.record(sample / 'terminal.json', {'no_resend': True, 'manifest_sha256': 'm',
                'logical_sample_id': row['logical_sample_id'], 'job_sha256': c.digest((output / 'job.json').read_bytes()),
                'state': 'ambiguous', 'accepted': False, 'retained_artifacts': {}})
            pending, states, identities = c.inventory({'requests': [row]}, binding, output, output, None, None, None)
            self.assertEqual((pending, states, identities), ([], ['ambiguous'], set()))

    def test_label_gate_requires_full_terminal_denominator_and_explicit_release(self):
        c = self.c
        with tempfile.TemporaryDirectory() as directory:
            outputs = {'sol': Path(directory), 'grok': Path(directory)}
            with patch.object(c, 'verify_job_binding', return_value={}), patch.object(c, 'inventory', return_value=([], ['semantic_rejected']*8904, set())):
                report = c.label_release_gate({}, Path(directory), 'm', Path(directory), outputs, None, None, None)
                self.assertTrue(report['all_planned_verified_terminal']); self.assertFalse(report['human_release_eligible'])
                self.assertTrue(c.label_release_gate({}, Path(directory), 'm', Path(directory), outputs, None, None, None, True)['human_release_eligible'])
            with patch.object(c, 'verify_job_binding', return_value={}), patch.object(c, 'inventory', return_value=([{}], ['accepted']*8903, set())):
                report = c.label_release_gate({}, Path(directory), 'm', Path(directory), outputs, None, None, None, True)
                self.assertFalse(report['human_release_eligible']); self.assertEqual(report['planned'], 17808)


if __name__ == '__main__':
    unittest.main()
