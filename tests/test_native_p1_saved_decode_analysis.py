"""Synthetic-only one-vote chain and incomplete-bank scoring witnesses."""
import importlib.util
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

PATH = Path(__file__).resolve().parents[1] / 'evaluation-results/hbq-native-transport-recovery-v1/analysis_p1_saved_decode.py'
spec = importlib.util.spec_from_file_location('test_p1_saved_decode_analysis_owned', PATH)
a = importlib.util.module_from_spec(spec)
spec.loader.exec_module(a)


def planned():
    return {'requests': [{'endpoint': endpoint, 'endpoint_ordinal': ordinal,
                          'logical_sample_id': f'logical-{ordinal}', 'request_sha256': f'{endpoint}-{ordinal}'}
                         for endpoint in ('sol', 'grok') for ordinal in range(1, 793)]}


def observed(row, state='accepted', native=None):
    return {'request': row, 'state': state, 'native_identity': native or row['request_sha256'],
            'response': {'score': 3}, 'new_votes': 0}


class P1SavedDecodeAnalysisTests(unittest.TestCase):
    def test_entire_original_geometry_keeps_gap_and_incomplete_bank_has_no_scalar(self):
        previous = a.load('analysis')
        manifest = planned()
        questions = [{'question': {'id': f'q-{i}'}} for i in range(178)]
        packets = [questions[i:i + 8] for i in range(0, 178, 8)]
        bank = manifest['requests'][:23]
        for index, (row, packet) in enumerate(zip(bank, packets), 1):
            row.update(form='short_narrative', arm='hbq', repeat=0, artifact_id='fixture', bundle_id='prose.short_story',
                       batch=index, question_ids=[q['question']['id'] for q in packet])
        observations = [dict(observed(row), response={'verdicts': [{'question_id': qid, 'verdict': 'YES'}
                                                                  for qid in row['question_ids']]}) for row in bank[:-1]]
        observations.append(observed(manifest['requests'][792]))
        records, inventory, commitments = a.join_once(manifest, observations)
        self.assertEqual(len(inventory), 1584)
        self.assertEqual(len(records), 23)
        self.assertEqual(inventory[22]['state'], 'untouched')
        self.assertEqual(len(commitments), 23)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            path = root / 'compiled/prose.short_story.json'
            path.parent.mkdir()
            raw = a.canonical({'questions': questions})
            path.write_bytes(raw)
            manifest['artifacts'] = {'compiled/prose.short_story.json': {'sha256': a.digest(raw), 'bytes': len(raw)}}
            hbq = {'core': SimpleNamespace(compiled_questions=lambda frozen: frozen['questions'])}
            profile = previous.score_bank(bank, records[:22], hbq, root, manifest)
        self.assertIsNone(profile['score'])
        self.assertIsNone(profile['weighted_coverage'])
        self.assertEqual(profile['native_coverage']['expected_leaves'], 178)
        self.assertEqual(profile['native_coverage']['observed_native_leaves'], 176)
        self.assertEqual(profile['state'], 'incomplete_or_nonunique_full_bank_no_scalar')

    def test_duplicates_altered_identity_and_rejected_content_cannot_be_scored(self):
        manifest = planned()
        first, second = manifest['requests'][:2]
        for observations in ([observed(first), observed(first)],
                             [observed(first), observed(second, native=first['request_sha256'])],
                             [observed(dict(first, request_sha256='foreign'))],
                             [observed(dict(first, endpoint_ordinal=2))]):
            with self.subTest(observations=observations), self.assertRaises(ValueError):
                a.join_once(manifest, observations)
        records, inventory, _ = a.join_once(manifest, [observed(first, 'semantic_rejected'), observed(second, 'ambiguous')])
        self.assertEqual(records, [])
        self.assertEqual([item['state'] for item in inventory[:3]], ['semantic_rejected', 'ambiguous', 'untouched'])
        self.assertTrue(all(value is None for value in inventory[0]['native_metrics'].values()))


if __name__ == '__main__':
    unittest.main()
