"""Known-count nominal agreement and prevalence degeneracy guard."""
import unittest
from fractions import Fraction
from pathlib import Path
from uuid import uuid4
from source import metric, safe_output


class NominalAgreement(unittest.TestCase):
    def test_known_counts_and_degenerate_margin(self):
        a = ['YES', 'YES', 'NO', 'NOT_APPLICABLE', 'CANNOT_ASSESS']
        b = ['NO', 'NO', 'NOT_APPLICABLE', 'CANNOT_ASSESS', 'CANNOT_ASSESS']
        result = metric([a, b])
        self.assertEqual(result['state_counts'], {'YES': 2, 'NO': 3, 'NOT_APPLICABLE': 2, 'CANNOT_ASSESS': 3})
        self.assertEqual(result['same_label_pairs'], 3)
        self.assertEqual(result['observed_agreement'], Fraction(3, 20))
        self.assertEqual(result['marginal_chance_agreement'], Fraction(13, 50))
        self.assertEqual(result['fleiss_form_kappa'], Fraction(-11, 74))
        self.assertEqual(result['subject_categories']['changing_with_yes_and_no'], 1)
        self.assertEqual(result['subject_categories']['changing_without_yes_and_no'], 1)
        reversed_result = metric([a[::-1], b[::-1]])
        for field in ('observed_agreement', 'marginal_chance_agreement', 'fleiss_form_kappa', 'subject_categories'):
            self.assertEqual(result[field], reversed_result[field])
        self.assertEqual(metric([['YES'] * 5, ['NO'] * 5])['fleiss_form_kappa'], 1)
        all_yes = metric([['YES'] * 5, ['YES'] * 5])
        self.assertEqual(all_yes['observed_agreement'], 1)
        self.assertIsNone(all_yes['fleiss_form_kappa'])
        with self.assertRaises(ValueError): metric([['YES'] * 4])
        with self.assertRaises(ValueError): metric([['YES', 'NO', 'NA', 'YES', 'NO']])

    def test_retained_source_output_boundaries(self):
        fixture_parent = Path(__file__).absolute().parent
        root = fixture_parent / ('cwr-leaf-output-guard-' + uuid4().hex)
        root.mkdir()
        retained = root / 'retained'; file_parent = root / 'file-parent'
        try:
            self.assertTrue(root.resolve().is_relative_to(fixture_parent.resolve()))
            retained.mkdir()
            plain = lambda path: path.lstat()
            safe_output(root / 'result', {retained}, plain)
            for output, protected in ((retained / 'result', {retained}),
                                      (root / 'fresh-parent', {root / 'fresh-parent/input'}),
                                      (root / 'nested/../result', {retained}),
                                      (Path('relative-result'), {retained})):
                with self.assertRaises(ValueError): safe_output(output, protected, plain)
            file_parent.write_bytes(b'fixture')
            with self.assertRaises(ValueError): safe_output(file_parent / 'result', {retained}, plain)
        finally:
            # Exact owned fixture, nonrecursive empty-directory cleanup only.
            self.assertTrue(root.resolve().is_relative_to(fixture_parent.resolve()))
            if file_parent.exists(): file_parent.unlink()
            if retained.exists(): retained.rmdir()
            root.rmdir()


if __name__ == '__main__': unittest.main()
