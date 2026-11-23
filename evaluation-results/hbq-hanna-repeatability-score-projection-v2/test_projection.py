import copy
import hashlib
import json
import math
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import projection


def item(name, scores):
    return {"item_id": name, "score": {"values": scores, "standard_deviation": 0.0, "range": 0.0}}


class ProjectionTest(unittest.TestCase):
    def setUp(self):
        self.report = {"item_count": 4, "repetitions": 5, "per_item": [
            item("zero", []), item("one", [50]), item("two", [25, 75]),
            item("complete", [1, 2, 3, 4, 5]),
        ]}

    def test_incomplete_and_complete_observations(self):
        original = copy.deepcopy(self.report)
        result = projection.corrected_score_summary(self.report)
        self.assertEqual(self.report, original)
        self.assertEqual(result["complete_item_count"], 1)
        self.assertEqual(result["insufficient_score_item_count"], 2)
        self.assertEqual(result["defined_only_summary"]["item_count"], 2)
        zero, one, two, complete = result["per_item"]
        for row in (zero, one):
            self.assertIsNone(row["sample_standard_deviation"])
            self.assertIsNone(row["range"])
        self.assertEqual(one["unscored_or_unobserved_count"], 4)
        self.assertAlmostEqual(two["sample_standard_deviation"], math.sqrt(1250))
        self.assertEqual(two["range"], 50)
        self.assertAlmostEqual(complete["sample_standard_deviation"], math.sqrt(2.5))
        all_missing = {"item_count": 1, "repetitions": 5, "per_item": [item("x", [])]}
        self.assertIsNone(projection.corrected_score_summary(all_missing)["defined_only_summary"]["mean_sample_standard_deviation"])

    def test_rejects_malformed_inputs(self):
        bad_reports = [
            {"item_count": True, "repetitions": 5, "per_item": [item("x", [1])]},
            {"item_count": 1, "repetitions": 5, "per_item": [item("x", [True])]},
            {"item_count": 1, "repetitions": 5, "per_item": [item("x", [float("nan")])]},
            {"item_count": 1, "repetitions": 5, "per_item": [item("x", [1] * 6)]},
            {"item_count": 2, "repetitions": 5, "per_item": [item("x", [1]), item("x", [2])]},
        ]
        for value in bad_reports:
            with self.subTest(value=value), self.assertRaises(ValueError):
                projection.corrected_score_summary(value)
        for raw in (b'{"x":1,"x":2}', b'{"x":NaN}',
                    json.dumps({"format_version": 3, "phase": "development", "repeatability": self.report}).encode()):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                projection.project_document(raw)

    def test_actual_cli_and_report_binding(self):
        document = {"format_version": 3, "phase": "repeatability", "repeatability": self.report}
        raw = json.dumps(document, separators=(",", ":")).encode()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invented.json"
            path.write_bytes(raw)
            completed = subprocess.run(
                [sys.executable, "-B", str(Path(projection.__file__)), str(path)],
                capture_output=True, check=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            self.assertEqual(path.read_bytes(), raw)
        output = json.loads(completed.stdout)
        self.assertEqual(output["source_sha256"], hashlib.sha256(raw).hexdigest())
        self.assertFalse(output["source_provenance_verified"])
        self.assertEqual(output["corrected_score_summary"], projection.corrected_score_summary(self.report))


if __name__ == "__main__":
    unittest.main()
