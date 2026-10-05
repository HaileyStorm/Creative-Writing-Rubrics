"""Declared-scale distinctions and the immutable metadata-only input boundary."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('p1_affine_bands_test', REPO / 'evaluation-results/hbq-semantic-crossform-p1b-matched-v1/analysis_affine_bands.py')
a = importlib.util.module_from_spec(spec)
spec.loader.exec_module(a)


def profile(arm, score, artifact='one', dimensions=None):
    return {'endpoint': 'sol', 'form': 'poetry', 'arm': arm, 'artifact_id': artifact, 'cycle': 0,
            'score': score, 'dimensions': dimensions or {}}


class AffineBandsTests(unittest.TestCase):
    def test_affine_bands_do_not_inherit_one_increment_thresholds(self):
        holistic = a.distribution([6], [1, 7], 1)
        compact = a.distribution([4], [1, 5], 1)
        hbq = a.distribution([92, 92, None, 0, 100], [0, 100], 5)
        self.assertAlmostEqual(holistic['affine_maximum'], 83.33333333333333)
        self.assertEqual(compact['affine_maximum'], 75)
        self.assertEqual((holistic['affine_ceiling_ge_90'], compact['affine_ceiling_ge_90']), (0, 0))
        self.assertEqual(hbq['affine_ceiling_ge_90'], 3)
        self.assertEqual((hbq['exact_floor'], hbq['exact_ceiling'], hbq['missing_or_abstained']), (1, 1, 1))
        self.assertEqual((hbq['distinct_scores'], hbq['tied_observations'], hbq['tied_pairs']), (3, 2, 1))
        self.assertEqual(a.distribution([10, 90], [0, 100], 5)['affine_floor_le_10'], 1)

    def test_absence_missingness_and_pinned_lexical_fresh_output_boundary(self):
        dimension = lambda value: {'value': value, 'scale': [1, 5], 'increment': 1, 'absence_zero': True}
        rows = [profile('poemetric', 1, dimensions={'item_7': dimension(0)}),
                profile('poemetric', None, 'two', {'item_7': dimension(1)}),
                profile('poemetric', 5, 'three')]
        group = a.analyze(rows)['groups'][0]
        self.assertEqual(group['primary']['planned_items'], 3)
        d = group['dimensions']['item_7']
        self.assertEqual((d['absence_zero_count'], d['exact_floor'], d['missing_or_abstained'], d['assessed_nonabsence']), (1, 1, 1, 1))
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            a.analyze(rows + [rows[0]])
        raw = a.canonical({'analysis_policy': a.SOURCE_POLICY, 'item_profiles': rows,
                           'human_labels': {'DO_NOT_DECODE': 'excluded'}, 'other_metrics': 'DO_NOT_DECODE'})
        original_decode = json.JSONDecoder.raw_decode

        def guarded_decode(decoder, text, index=0):
            if text[index:].startswith(('"DO_NOT_DECODE"', '{"DO_NOT_DECODE"')):
                raise AssertionError('Excluded target decoded')
            return original_decode(decoder, text, index)

        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / 'source' / 'stdout.json'
            source.parent.mkdir()
            source.write_bytes(raw)
            output = Path(temporary) / 'derived'
            with patch.object(a, 'SOURCE_SHA', a.digest(raw)), patch.object(json.JSONDecoder, 'raw_decode', guarded_decode):
                report, receipt = a.prepare(source, output)
            self.assertEqual(report['planned_item_profiles'], 3)
            self.assertFalse(output.exists())
            self.assertEqual(source.read_bytes(), raw)
            self.assertFalse(receipt['labels_opened'])
            with self.assertRaisesRegex(ValueError, 'source bytes differ'):
                a.project(raw + b' ')
            output.mkdir()
            with self.assertRaisesRegex(ValueError, 'fresh'):
                a.prepare(source, output)
            with self.assertRaisesRegex(ValueError, 'overlaps source'):
                a.prepare(source, source.parent / 'derived')


if __name__ == '__main__':
    unittest.main()
