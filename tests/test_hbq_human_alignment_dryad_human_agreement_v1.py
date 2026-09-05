import importlib.util
import tempfile
import unittest
from fractions import Fraction
from pathlib import Path


PACKAGE = Path(__file__).resolve().parents[1] / "evaluation-results" / "hbq-human-alignment-dryad-human-agreement-v1" / "source.py"
SPEC = importlib.util.spec_from_file_location("dryad_human_agreement_v1", PACKAGE)
subject = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(subject)


class DryadHumanAgreementTests(unittest.TestCase):
    def test_average_tie_ranks_and_spearman(self) -> None:
        values = [Fraction(1), Fraction(2), Fraction(2), Fraction(4)]
        self.assertEqual(subject.average_ranks(values), [Fraction(1), Fraction(5, 2), Fraction(5, 2), Fraction(4)])
        self.assertEqual(subject.spearman_average_ties(values, values), 1.0)
        self.assertEqual(subject.spearman_average_ties(values, list(reversed(values))), -1.0)

    def test_confirmation_poison_never_parses_as_an_axis(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            ratings = Path(temporary) / "ratings.csv"
            rows = ["evaluator_index,story_slot,story_id,condition,topic,story_text,novel", "0,1,open,local,topic,text,1", "599,1,open,local,topic,text,9"]
            rows.extend(f"{index},1,confirmation,local,topic,text,POISON" for index in range(1, 599))
            ratings.write_text("\n".join(rows) + "\n", encoding="utf-8")
            records = subject.collect_open_measurements(
                ratings,
                {"open": "TRAIN", "confirmation": "CONFIRMATION"},
                ["novel"],
                {"TRAIN": 1, "DEV": 0},
                "test-seed",
            )
        self.assertEqual(sum(len(values) for half in records["TRAIN"]["open"].values() for values in half.values()), 2)

    def test_hash_drift_rejects_before_source_parse(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            ratings = root / "ratings.csv"
            split = root / "split.jsonl"
            ratings.write_text("drift", encoding="utf-8")
            split.write_text("drift", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Pinned source hash drift"):
                subject.run(ratings, split)


if __name__ == "__main__":
    unittest.main()
