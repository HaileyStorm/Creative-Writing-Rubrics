"""Synthetic provenance/context recovery witnesses; no native/provider proof."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
HERE = REPO / "evaluation-results/hbq-matched-mfa-v1"
sys.path.insert(0, str(HERE))
import context_reconciliation as r
import collector_context_v2 as continuation
import analysis_context_v2 as analysis
spec = importlib.util.spec_from_file_location("mfa_context_recovery_fixture", REPO / "tests/test_matched_mfa_collection.py")
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)


class MatchedMFAContextRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.f = fixture.MatchedMFACollectionTests()
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        sys.path.insert(0, str(REPO / "src"))
        from hbqrs import runner
        self.runner = runner
        task = r.old.prepare.contract("synthetic")
        raw_task = r.canonical(task)
        (self.f.root / "contract.json").write_bytes(raw_task)
        self.f.manifest["artifacts"]["contract.json"] = {"sha256": r.digest(raw_task), "bytes": len(raw_task)}
        literal = json.dumps(runner._task_contract_judge_context(task), ensure_ascii=False, indent=2)
        raw_prompt = ("Synthetic fixture\n" + literal + "\nRubric instruction outside task context.").encode()
        (self.f.root / "prompt.txt").write_bytes(raw_prompt)
        self.f.manifest["artifacts"]["prompt.txt"] = {"sha256": r.digest(raw_prompt), "bytes": len(raw_prompt)}
        schema = r.old.prepare.portable_schema(runner._batch_response_schema(["q1"]))
        raw_schema = r.canonical(schema)
        (self.f.root / "schema.json").write_bytes(raw_schema)
        self.f.manifest["artifacts"]["schema.json"] = {"sha256": r.digest(raw_schema), "bytes": len(raw_schema)}
        self.f.row.update(arm="hbq", artifact_id="synthetic", bundle_id="prose.short_form", question_ids=["q1"],
                          task_contract_path="contract.json", task_contract_sha256=r.digest(raw_task),
                          prompt_sha256=r.digest(raw_prompt), schema_sha256=r.digest(raw_schema), request_sha256="c" * 64)
        self.f.manifest["requests"] = [self.f.row]
        self.f.answer = {"verdicts": [{"question_id": "q1", "verdict": "YES", "confidence": .8,
            "evidence": [{"kind": "exact_quote", "reference": "context", "exact_quote": '"audience": []', "summary": None}],
            "note": "Synthetic applicability observation"}]}
        (self.f.output / "STOP").touch()
        (self.f.output / "STOP").unlink()

    def project(self):
        with patch.object(r, "source_binding", return_value=self.f.binding):
            return r.project_prefix(self.f.manifest, self.f.binding["manifest_sha256"], self.f.root, self.f.output,
                "sol", r.digest((self.f.output / "job.json").read_bytes()), self.f.receipts, self.f.subset, self.f.validator, self.runner)

    def complete_old(self):
        self.assertEqual(self.f.collect(), "semantic_rejected")
        (self.f.output / "STOP").touch()
        r.old.record(self.f.output / "stop-observed.json", {"synthetic": True})

    def test_rendered_projection_corrects_context_admission_without_new_vote_or_edit(self):
        self.complete_old()
        sample = r.old.sample_path(self.f.output, self.f.row)
        before = r.inventory(sample)
        result = self.project()
        self.assertEqual(result["summary"]["correctable_context_rejections"], 1)
        entry = result["prefix"][0]
        self.assertEqual((entry["original_state"], entry["state"], entry["new_votes"]), ("semantic_rejected", "accepted", 0))
        self.assertEqual(before, r.inventory(sample))
        self.assertEqual(json.loads((sample / "terminal.json").read_bytes())["state"], "semantic_rejected")

    def test_instruction_literal_in_prompt_is_not_admissible_context(self):
        self.f.answer["verdicts"][0]["evidence"][0]["exact_quote"] = "Rubric instruction outside task context."
        self.complete_old()
        result = self.project()
        self.assertEqual(result["summary"]["correctable_context_rejections"], 0)
        self.assertEqual(result["prefix"][0]["state"], "semantic_rejected")

    def test_projection_must_be_literal_in_exact_pinned_prompt(self):
        raw = b"Synthetic prompt without rendered projection"
        (self.f.root / "prompt.txt").write_bytes(raw)
        self.f.manifest["artifacts"]["prompt.txt"] = {"sha256": r.digest(raw), "bytes": len(raw)}
        with self.assertRaisesRegex(ValueError, "absent"):
            r.rendered_context(self.f.root, self.f.manifest, self.f.row, self.runner)

    def test_unsettled_prefix_and_changed_native_bytes_fail_closed(self):
        self.complete_old()
        sample = r.old.sample_path(self.f.output, self.f.row)
        native = sample / "message.json"
        native.write_bytes(b"{}")
        with self.assertRaises(ValueError):
            self.project()
        (sample / "terminal.json").unlink()
        with self.assertRaisesRegex(ValueError, "unresolved"):
            self.project()

    def test_source_job_pin_checked_before_any_replay(self):
        with self.assertRaisesRegex(ValueError, "Exact original source job"):
            r.source_binding(self.f.output, "sol", self.f.manifest, self.f.binding["manifest_sha256"], "0" * 64)

    def test_suffix_reserves_entire_prefix_regardless_original_rejection(self):
        rows = [{"endpoint": "sol", "endpoint_ordinal": n, "request_sha256": str(n)} for n in range(1, 5)]
        receipt = {"endpoints": {"sol": {"reserved_prefix": 2, "untouched_request_sha256s": ["3", "4"],
                   "prefix": [{"original_state": "accepted"}, {"original_state": "semantic_rejected"}]}}}
        self.assertEqual(continuation.suffix_rows({"requests": rows}, receipt, "sol"), rows[2:])
        wrong = deepcopy(receipt)
        wrong["endpoints"]["sol"]["untouched_request_sha256s"] = ["2", "3", "4"]
        with self.assertRaises(ValueError):
            continuation.suffix_rows({"requests": rows}, wrong, "sol")

    def test_strict_normalization_adapter_receives_exact_rendered_context(self):
        observed = {}
        class Runner:
            _task_contract_judge_context = staticmethod(self.runner._task_contract_judge_context)
            def _normalize_batch(self, payload, **kwargs):
                observed.update(kwargs)
                return [payload]
        row = self.f.row
        wrapped = analysis.context_runner(self.f.manifest, self.f.root, Runner())
        wrapped._normalize_batch(self.f.answer, run_id=row["logical_sample_id"], context_texts=["old incomplete context"])
        self.assertEqual(observed["context_texts"], [r.rendered_context(self.f.root, self.f.manifest, row, self.runner)])

    def test_join_counts_reconciled_prefix_once_and_rejects_reserved_suffix_copy(self):
        self.complete_old()
        prefix = self.project()
        rows = []
        for endpoint in ("grok", "sol"):
            for ordinal in range(1, 435):
                row = deepcopy(self.f.row)
                row.update(endpoint=endpoint, endpoint_ordinal=ordinal,
                           logical_sample_id=f"{endpoint}-{ordinal}", request_sha256=f"{endpoint}-{ordinal}")
                if endpoint == "sol" and ordinal == 1:
                    row = self.f.row
                rows.append(row)
        manifest = dict(self.f.manifest, requests=rows)
        prefix["untouched_request_sha256s"] = [row["request_sha256"] for row in rows if row["endpoint"] == "sol" and row["endpoint_ordinal"] > 1]
        receipt = {"endpoints": {"sol": prefix, "grok": {"prefix": [], "reserved_prefix": 0,
            "source_root_local_only": str(self.f.output.parent / "grok-source"),
            "untouched_request_sha256s": [row["request_sha256"] for row in rows if row["endpoint"] == "grok"]}}}
        suffixes = {endpoint: self.f.output.parent / (endpoint + "-suffix") for endpoint in ("grok", "sol")}
        records, states = analysis.joined_evidence(manifest, "synthetic", self.f.root, receipt, "synthetic", suffixes,
            Path("synthetic-tools"), self.f.receipts, self.f.subset, self.f.validator, self.runner)
        self.assertEqual((len(records), states), (1, {"untouched": 867, "accepted": 1}))
        self.assertIs(records[0]["request"], self.f.row)
        reserved = r.old.sample_path(suffixes["sol"], self.f.row)
        reserved.mkdir(parents=True)
        with patch.object(continuation, "verify_job_binding", return_value=self.f.binding):
            with self.assertRaisesRegex(ValueError, "reserved or unknown"):
                analysis.joined_evidence(manifest, "synthetic", self.f.root, receipt, "synthetic", suffixes,
                    Path("synthetic-tools"), self.f.receipts, self.f.subset, self.f.validator, self.runner)


if __name__ == "__main__":
    unittest.main()
