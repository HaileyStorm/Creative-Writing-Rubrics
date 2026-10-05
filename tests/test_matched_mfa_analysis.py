"""Synthetic descriptive-analysis and postprediction-release witnesses."""
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
import sys

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("mfa_analysis_test", REPO / "evaluation-results/hbq-matched-mfa-v1/analysis.py")
a = importlib.util.module_from_spec(spec)
spec.loader.exec_module(a)
spec = importlib.util.spec_from_file_location("mfa_analysis_preparation_fixture", REPO / "tests/test_matched_mfa_preparation.py")
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)


class MatchedMFAAnalysisTests(unittest.TestCase):
    def test_complete_canonical_bank_uses_strict_admission_and_native_scale(self):
        sys.path.insert(0, str(REPO / "src"))
        from hbqrs import core, runner, scoring_v2
        modules = core.load_modules(REPO / "registry/all_modules.yaml")
        bundle = next(b for b in core.load_bundles(REPO / "bundles/all_bundles.yaml") if b["bundle_id"] == "prose.short_form")
        contract = a.c.prepare.contract("synthetic")
        compiled = core.compile_bundle(modules, bundle, task_contract=contract)
        ids = [q["question"]["id"] for q in core.compiled_questions(compiled)]
        self.assertEqual(len(ids), 170)
        planned, admitted = [], []
        for i in range(0, len(ids), 8):
            row = {"batch": i // 8 + 1, "question_ids": ids[i:i + 8], "task_contract_path": "contract.json", "artifact_id": "synthetic",
                   "bundle_id": "prose.short_form", "endpoint": "sol", "logical_sample_id": str(i), "sources": [{"id": "synthetic"}]}
            planned.append(row)
            admitted.append({"request": row, "response": {"verdicts": [{"question_id": q, "verdict": "YES", "confidence": .8,
                "evidence": [{"kind": "exact_quote", "reference": "artifact", "exact_quote": "synthetic", "summary": None},
                             {"kind": "summary", "reference": "artifact", "exact_quote": None, "summary": "Synthetic declared evidence"}],
                "note": "Synthetic test only"} for q in row["question_ids"]]}})
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = a.c.prepare.canonical(contract)
            (root / "contract.json").write_bytes(raw)
            manifest = {"artifacts": {"contract.json": {"sha256": a.c.prepare.sha(raw), "bytes": len(raw)}}}
            with patch.object(a.c, "inputs", return_value=(b"", b"{}", {"synthetic": "synthetic excerpt"}, "Excerpt scope")):
                result = a.score_bank(planned, admitted, {"core": core, "runner": runner, "strict": scoring_v2,
                                                       "modules": modules, "bundle": bundle}, root, manifest)
            self.assertIsNotNone(result["score"], result)
            self.assertTrue(0 <= result["score"] <= 100)
            self.assertEqual(result["coverage"]["accepted_packets"], 22)

    def test_incomplete_or_duplicate_bank_never_scores(self):
        rows = [{"batch": i + 1, "question_ids": [f"q{j}" for j in range(i * 8, min(170, (i + 1) * 8))]} for i in range(22)]
        admitted = [{"response": {"verdicts": [{"question_id": q, "verdict": "YES"} for q in row["question_ids"]]}} for row in rows]
        scorer = Mock()
        hbq = {"core": scorer}
        result = a.score_bank(rows, admitted[:-1], hbq, Path("unused"), {})
        self.assertIsNone(result["score"])
        self.assertEqual(result["coverage"]["native_leaves"], 168)
        wrong = deepcopy(admitted)
        wrong[-1]["response"]["verdicts"][0]["question_id"] = "q0"
        self.assertIsNone(a.score_bank(rows, wrong, hbq, Path("unused"), {})["score"])
        scorer.score_bundle.assert_not_called()

    def test_ab_ba_map_to_committed_texts_and_missing_order_is_not_tie(self):
        selection = {"pairs": [{"pair_id": "pair", "excerpt_hashes": ["left", "right"]}]}
        def item(orientation, winner):
            return {"request": {"endpoint": "sol", "arm": "pairwise", "pair_id": "pair", "repeat": 0,
                "orientation": orientation, "sources": [{"side": "A", "sha256": "left" if orientation == "AB" else "right"},
                                                          {"side": "B", "sha256": "right" if orientation == "AB" else "left"}]},
                    "response": {"winner": winner}}
        decisions, orders = a.pair_decisions(selection, [item("AB", "A"), item("BA", "B")], {})
        self.assertEqual(decisions[("sol", "pairwise", "pair", 0)], 1)
        self.assertEqual(orders[("sol", "pair", 0, "BA")], 1)
        self.assertIsNone(a.pair_decisions(selection, [item("AB", "A")], {})[0][("sol", "pairwise", "pair", 0)])
        self.assertEqual(a.pair_decisions(selection, [item("AB", "TIE"), item("BA", "TIE")], {})[0][("sol", "pairwise", "pair", 0)], .5)

    def test_release_requires_every_planned_slot_terminal(self):
        for states in ({"accepted": 1}, {"accepted": 1, "untouched": 1}, {"accepted": 1, "started_unresolved": 1}):
            with self.assertRaises(ValueError):
                a.label_release_gate(states, 2)
        a.label_release_gate({"accepted": 1, "unadmitted_no_resend": 1}, 2)

    def source_fixture(self, preference="Excerpt1"):
        metadata, ledger, receipts, sources = fixture.fixture()
        for data in sources.values():
            for writers in data.values():
                for judgments in writers.values():
                    judgments[0][-1]["Preference"] = preference
        for receipt in receipts:
            raw = json.dumps(sources[receipt["path"]], ensure_ascii=False).encode()
            receipt.update(sha256=a.c.prepare.sha(raw), bytes=len(raw), git_blob_sha1=hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest())
        selection = a.c.prepare.extract.select(metadata, ledger, receipts)
        return selection, sources

    def test_exact_released_decoder_and_source_position_rater_binding(self):
        for preference in ("Excerpt1", "Excerpt2", "Paragraph1", None, " Excerpt1", "excerpt1"):
            selection, sources = self.source_fixture(preference)
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                for path, data in sources.items():
                    a.c.prepare.extract.write_new(root / "author-style" / path, json.dumps(data, ensure_ascii=False).encode())
                if preference in ("Excerpt1", "Excerpt2"):
                    ballots = a.source_ballots(selection, root)
                    index = 0 if preference == "Excerpt1" else 1
                    self.assertTrue(all(b["winner_sha256"] == b["row"]["excerpt_hashes"][index] for b in ballots))
                    wrong = deepcopy(selection)
                    wrong["metadata_rows"][0]["rater_hash"] = "0" * 64
                    with self.assertRaises(ValueError):
                        a.source_ballots(wrong, root)
                else:
                    with self.assertRaisesRegex(ValueError, "Unsupported released"):
                        a.source_ballots(selection, root)

    def test_panel_condition_units_and_missingness_are_separate(self):
        selection, _ = self.source_fixture()
        ballots = [{"metadata_row_sha256": a.c.prepare.sha(a.c.prepare.canonical(row)), "row": row,
                    "winner_sha256": row["excerpt_hashes"][0]} for row in selection["metadata_rows"]]
        decisions = {("sol", "holistic", p["pair_id"], 0): .5 for p in selection["pairs"]}
        report = a.agreement(selection, ballots, decisions)
        expert = report["sol:holistic:expert:fewshot"]
        self.assertEqual(expert["raw_ballot_agreement_assessed"], .5)
        self.assertEqual(expert["raw_ballot_all_planned_bounds"], [.5, .5])
        missing = report["grok:holistic:lay:fewshot"]
        self.assertIsNone(missing["equal_target_agreement_assessed"])
        self.assertEqual(missing["raw_ballot_all_planned_bounds"], [0, 1])
        self.assertEqual(missing["coverage"], 0)


if __name__ == "__main__":
    unittest.main()
