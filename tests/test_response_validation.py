"""Explicit offline acceptance checks; only public catalog and invented text."""
from copy import deepcopy
import json
import unittest
from unittest.mock import patch

from hbqrs import core, paths, runner
from hbqrs.response_validation import ResponseBankValidationError, validate_response_bank


class ResponseBankValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.modules = core.load_modules(paths.registry_path())
        cls.bundle = core.resolve_bundle(core.load_bundles(paths.bundles_path()), "prose.scene")
        cls.task = {
            "contract_version": 1, "contract_id": "invented-contract", "artifact_id": "invented-artifact",
            "context": {"artifact_kind": "prose_fiction", "declared_scope": "scene", "completion_status": "unknown",
                        "background": [], "constraints": [], "audience": []},
            "preferences": [], "priorities": [], "weighted_goals": [], "binding_requirements": [],
        }
        cls.artifact = "An invented lantern rests beside an invented window."
        cls.contexts = ["The invented marker is required."]

    def setUp(self):
        for name in ("run_judge", "_call_codex", "_call_openai", "_call_grok"):
            guard = patch.object(runner, name, side_effect=AssertionError("Provider execution forbidden"))
            guard.start()
            self.addCleanup(guard.stop)

    def ids(self, contract=None):
        compiled = core.compile_bundle(self.modules, self.bundle, task_contract=contract or self.task)
        roles = {"hard_gate": 0, "domain": 1, "penalty": 2, "supplemental": 3}
        return [row["question"]["id"] for row in sorted(core.compiled_questions(compiled), key=lambda row: roles[row["role"]])]

    def batches(self, contract=None, size=7):
        ids, batches = self.ids(contract), []
        for start in range(0, len(ids), size):
            selected = ids[start:start + size]
            payload = {"verdicts": [{
                "question_id": qid, "verdict": "YES", "confidence": 0.8,
                "evidence": [{"kind": "exact_quote", "reference": "invented source",
                              "exact_quote": "invented lantern", "summary": None} for _ in range(3)],
                "note": "Invented observation.",
            } for qid in reversed(selected)]}
            batches.append({"question_ids": selected, "response_text": json.dumps(payload)})
        return batches

    def validate(self, batches, contract=None, modules=None, bundle=None):
        return validate_response_bank(
            self.modules if modules is None else modules, self.bundle if bundle is None else bundle, batches,
            artifact_id="invented-artifact", artifact_text=self.artifact, context_texts=self.contexts,
            task_contract=self.task if contract is None else contract,
        )

    def reject(self, kind, action):
        with self.assertRaises(ResponseBankValidationError) as captured:
            action()
        self.assertEqual(captured.exception.failure_type, kind)
        self.assertNotIn("invented lantern", str(captured.exception))
        self.assertTrue(captured.exception.__suppress_context__)

    def test_complete_dynamic_bank_retains_abstentions_without_provenance(self):
        task = deepcopy(self.task)
        task["contract_version"] = 2
        task["weighted_goals"] = [{
            "goal_id": "marker", "atomic_question": "Does the invented marker appear?", "weight": 1,
            "source": {"kind": "driving_prompt", "reference": "invented context", "exact_excerpt": self.contexts[0]},
            "applies_to": ["scene"], "rationale": "Invented declared goal.",
        }]
        batches = self.batches(task, size=11)
        first = json.loads(batches[0]["response_text"])
        first["verdicts"][0].update(verdict="CANNOT_ASSESS", note="")
        first["verdicts"][1].update(verdict="NOT_APPLICABLE", note="Invented activation explanation.")
        first["verdicts"][2]["evidence"][0]["exact_quote"] = self.contexts[0]
        batches[0]["response_text"] = json.dumps(first)
        before = deepcopy((self.modules, self.bundle, batches, task, self.contexts))
        result = self.validate(batches, task)
        self.assertEqual(result["question_count"], len(self.ids()) + 1)
        self.assertEqual([v["question_id"] for v in result["normalized_verdicts"]], self.ids(task))
        self.assertTrue(result["membership_complete"])
        self.assertFalse(result["all_binary_assessed"])
        self.assertEqual(result["verdict_counts"]["CANNOT_ASSESS"], 1)
        self.assertEqual(result["verdict_counts"]["NOT_APPLICABLE"], 1)
        self.assertEqual(result["status"], "SEMANTICS_VALIDATED_ONLY")
        self.assertIsNone(result["native_provenance"])
        self.assertIsNone(result["score"])
        self.assertFalse(result["quality_verified"])
        self.assertEqual(result["repairs"], [])
        self.assertTrue(all("judge_id" not in v and "run_id" not in v for v in result["normalized_verdicts"]))
        self.assertEqual((self.modules, self.bundle, batches, task, self.contexts), before)

    def test_request_partition_rejects_before_response_parsing(self):
        batches = self.batches()
        reordered = deepcopy(batches)
        reordered[0]["question_ids"].reverse()
        with patch.object(runner, "_parse_model_json", side_effect=AssertionError("Partition must be checked first")):
            for values, kind in (([], "BANK_MEMBERSHIP"), ([*batches, batches[0]], "DUPLICATE_REQUEST_ID"),
                                 (reordered, "REQUEST_ORDER")):
                with self.subTest(kind=kind):
                    self.reject(kind, lambda: self.validate(values))

    def test_raw_response_schema_semantics_and_strict_import_are_enforced(self):
        batches = self.batches()
        cases = [
            ('{"verdicts":[],"verdicts":[]}', "RESPONSE_JSON"),
            ('{"verdicts":[],"extra":NaN}', "RESPONSE_JSON"),
        ]
        for change, kind in (
            (lambda v: v["verdicts"][0].update(confidence=True), "RESPONSE_SCHEMA"),
            (lambda v: v["verdicts"][0].update(question_id=v["verdicts"][1]["question_id"]), "RESPONSE_SEMANTICS"),
            (lambda v: v["verdicts"][0]["evidence"][0].update(exact_quote="ABSENT_INVENTED_QUOTE"), "RESPONSE_SEMANTICS"),
            (lambda v: v["verdicts"][0].update(verdict="NOT_APPLICABLE", note=""), "IMPORT_ADMISSION"),
        ):
            payload = json.loads(batches[0]["response_text"])
            change(payload)
            cases.append((json.dumps(payload), kind))
        for raw, kind in cases:
            with self.subTest(kind=kind, case=cases.index((raw, kind))):
                changed = deepcopy(batches)
                changed[0]["response_text"] = raw
                self.reject(kind, lambda: self.validate(changed))

    def test_nested_definition_and_numeric_errors_are_typed_without_hiding_bugs(self):
        batches = self.batches()
        malformed = deepcopy(next(record for record in self.modules if record.get("tree")))
        pending = [node for record in self.modules for node in record.get("tree", [])]
        while pending:
            node = pending.pop()
            if node.get("type") == "group":
                group = deepcopy(node)
                break
            pending.extend(node.get("children", []))
        else:
            self.fail("Public catalog group fixture unavailable")
        group["children"] = [None]
        malformed["tree"] = [group]
        with patch.object(core, "compile_bundle", side_effect=AssertionError("Invalid schema reached compiler")):
            self.reject("INPUT_DATA", lambda: self.validate(batches, modules=[None]))
            self.reject("BANK_DEFINITION_OR_TASK", lambda: self.validate(batches, modules=[malformed]))
        huge = deepcopy(self.task)
        huge["weighted_goals"] = [{
            "goal_id": "marker", "atomic_question": "Does the invented marker appear?", "weight": 10**400,
            "source": {"kind": "driving_prompt", "reference": "invented context", "exact_excerpt": self.contexts[0]},
            "applies_to": ["scene"], "rationale": "Invented declared goal.",
        }]
        self.reject("BANK_DEFINITION_OR_TASK", lambda: self.validate(batches, huge))
        with patch.object(core, "compile_bundle", side_effect=AttributeError("invented_internal_bug")):
            with self.assertRaisesRegex(AttributeError, "invented_internal_bug"):
                self.validate(batches)


if __name__ == "__main__":
    unittest.main()
