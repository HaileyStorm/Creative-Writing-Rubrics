"""Independent estimator and closed-field guards for this new calculation."""
import csv
from fractions import Fraction
import importlib.util
from pathlib import Path
import random
from types import SimpleNamespace
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("dryad_story_bootstrap", HERE / "source.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class BehavioralGuards(unittest.TestCase):
    def test_duplicate_story_draw_recomputes_ties(self):
        left, right = [1, 2, 3, 4], [1, 3, 2, 4]
        self.assertAlmostEqual(module.weighted_spearman(
            module.tie_groups(left), module.tie_groups(right), [2, 1, 1, 0]), 7 / 9)
        profile = __import__("json").loads((HERE / "profile.json").read_bytes())
        parent = module.parent_module(profile)
        rng = random.Random(321)
        for _ in range(30):
            left = [Fraction(rng.randrange(4), rng.randrange(1, 4)) for _ in range(7)]
            right = [Fraction(rng.randrange(4), rng.randrange(1, 4)) for _ in range(7)]
            indices = [rng.randrange(7) for _ in range(7)]
            weights = [indices.count(index) for index in range(7)]
            expected = parent.spearman_average_ties([left[i] for i in indices], [right[i] for i in indices])
            actual = module.weighted_spearman(module.tie_groups(left), module.tie_groups(right), weights)
            if expected is None:
                self.assertIsNone(actual)
            else:
                self.assertAlmostEqual(actual, expected, places=14)
        self.assertIsNone(module.weighted_spearman([[0, 1]], [[0], [1]], [1, 1]))
        self.assertIsNone(module.weighted_spearman([[0], [1]], [[0], [1]], [1, 0]))

    def test_csv_lexer_and_confirmation_field_firewall(self):
        # Byte delimiters are inspected; prohibited fields need not even be UTF-8.
        raw = (b'evaluator_index,story_slot,story_id,condition,topic,story_text,axis\r\n'
               b'0,0,t,c,x,"prose, ""quoted""\n\xff",4\r\n'
               b'1,0,d,c,x,\xff,5\r\n'
               b'9,0,z,c,x,"\xff",not-a-rating-\xff\r\n')
        contract = {"measurement": {"axes": ["axis"]}, "evaluator_split": {"seed": "unused"},
                    "partitions": {"open": {"TRAIN": 1, "DEV": 1}}}
        seen = []
        def halves(ids, seed):
            seen.extend(sorted(ids))
            return {ident: "A" for ident in ids}
        parent = SimpleNamespace(PARTITIONS=("TRAIN", "DEV"), evaluator_halves=halves)
        records, accounting = module.measurements(raw, {"t": "TRAIN", "d": "DEV", "z": "CONFIRMATION"},
                                                  contract, parent)
        self.assertEqual(seen, ["0", "1", "9"])
        self.assertEqual(records["TRAIN"]["t"]["A"]["axis"], [4])
        self.assertEqual(accounting["rating_fields_decoded"], 2)
        self.assertEqual(accounting["confirmation_rows_metadata_only"], 1)
        self.assertEqual(accounting["story_text_fields_decoded"], 0)
        self.assertEqual(accounting["confirmation_rating_fields_decoded"], 0)
        for text in ['a,b,\r\n"line\nnext","x""y",z\r\n', '"",,"last"']:
            decoded = [[module.decode_field(text.encode(), span) for span in row]
                       for row in module.csv_spans(text.encode())]
            self.assertEqual(decoded, list(csv.reader(text.splitlines(keepends=True))))
        with self.assertRaises(ValueError):
            list(module.csv_spans(b'"bad"suffix,x\n'))

    def test_undefined_draw_is_retained_and_interval_withheld(self):
        records = {partition: {str(index): {half: {"axis": [value, value]} for half in ("A", "B")}
                              for index, value in enumerate((1, 2))} for partition in ("TRAIN", "DEV")}
        points = [{"partition": p, "axis": "axis", "spearman_average_ties": 1.0}
                  for p in ("TRAIN", "DEV")]
        rows, distributions = module.bootstrap_rows(records, ["axis"], 2,
                                                     {"seed": "toy", "draws_per_partition": 20}, points)
        for row in rows:
            self.assertGreater(row["bootstrap_undefined"], 0)
            self.assertEqual(row["bootstrap_defined"] + row["bootstrap_undefined"], 20)
            self.assertIsNone(row["conditional_percentile_95"])
        self.assertTrue(all(len(values) == 20 for values in distributions.values()))


if __name__ == "__main__":
    unittest.main()
