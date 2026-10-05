"""Synthetic lifecycle witnesses; mocks do not attest a native/provider execution."""
from copy import deepcopy
from datetime import timedelta
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import Mock
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("p1b_collector_test", REPO / "evaluation-results/hbq-semantic-crossform-p1b-matched-v1/collector.py")
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)


class SemanticCrossformCollectionTests(unittest.TestCase):
    def test_grok_campaign_deadline_reserves_full_900_second_call(self):
        boundary = c.CUTOFF - timedelta(seconds=900)
        self.assertTrue(c.grok_contact_allowed(boundary - timedelta(microseconds=1)))
        self.assertFalse(c.grok_contact_allowed(boundary))
        self.assertFalse(c.grok_contact_allowed(boundary + timedelta(microseconds=1)))
        self.assertFalse(c.grok_contact_allowed(c.CUTOFF))

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "frozen"
        self.output = Path(self.temp.name) / "results"
        self.root.mkdir()
        self.output.mkdir()
        self.subset = c.load_module("mfa_collection_test_subset", Path("C:/Users/Haile/.codex/tools/model_work_queue/adapters/json_schema_subset.py"))
        self.validator = c.load_module("mfa_collection_test_validator", c.HERE / "arms/validate_response.py")
        raw = {"prompt.txt": b"Synthetic excerpt quality task", "schema.json": (c.HERE.parent / "hbq-matched-mfa-v1/arms/holistic.schema.json").read_bytes(),
               "input.txt": b"A synthetic first line.\r\nA synthetic second line.", "context.json": b'{"declared_scope":"passage","completion_status":"excerpt"}', "shared.txt": b"Exact synthetic shared work context."}
        for name, data in raw.items():
            (self.root / name).write_bytes(data)
        self.manifest = {"runtime": {"timeout_seconds": 900}, "artifacts": {n: {"sha256": c.digest(b), "bytes": len(b)} for n, b in raw.items()}}
        self.row = {"endpoint": "sol", "endpoint_ordinal": 1, "logical_sample_id": "a" * 64, "arm": "holistic",
                    "form": "novel_work_segment", "task_context": {"path": "context.json", "sha256": c.digest(raw["context.json"]), "bytes": len(raw["context.json"])},
                    "shared_work_context": {"path": "shared.txt", "sha256": c.digest(raw["shared.txt"]), "bytes": len(raw["shared.txt"])},
                    "prompt_path": "prompt.txt", "prompt_sha256": c.digest(raw["prompt.txt"]), "schema_path": "schema.json",
                    "schema_sha256": c.digest(raw["schema.json"]), "sources": [{"id": "synthetic", "input_path": "input.txt", "sha256": c.digest(raw["input.txt"])}]}
        self.binding = {"manifest_sha256": "b" * 64, "account_probe_sha256": "c" * 64,
                        "runtime": {"model": "gpt-6.1-sol", "reasoning": "high", "account_identity_sha256": "d" * 64,
                                    "secondary_home_sha256": "e" * 64}}
        c.record(self.output / "job.json", self.binding)
        c.record(self.output / "account-binding.json", c.account_receipt(self.binding))
        self.answer = {"status": "SCORED", "abstention_reason": None, "result": {"method": "mfa_excerpt_holistic_v1", "score": 4,
            "rationale": "Synthetic rationale", "strengths": ["Synthetic one", "Synthetic two"], "limitations": [],
            "evidence": [{"quote": "A synthetic first line.", "explanation": "Synthetic evidence"},
                         {"quote": "A synthetic second line.", "explanation": "Synthetic evidence"}]}}
        self.receipts = SimpleNamespace(verify=Mock())
        self.helper = SimpleNamespace(CLI=Path("synthetic-never-executed.exe"))

    def call(self, **kwargs):
        self.assertEqual(kwargs["timeout"], 900)
        self.assertEqual(kwargs["codex_receipt_policy"], "codex_native_rollout_v1")
        kwargs["before_provider_attempt"]()
        raw = json.dumps(self.answer, indent=2).replace("\n", "\r\n").encode()
        (kwargs["output_dir"] / "message.json").write_bytes(raw)
        return raw.decode().replace("\r\n", "\n"), {"provider_artifacts": {"codex_message": {"path": "message.json"}}}

    def collect(self, call=None):
        return c.collect_one(self.row, self.manifest, self.binding, self.root, self.output, self.subset,
                             self.validator, self.receipts, self.helper, call or self.call)

    def replay(self):
        return c.replay(c.sample_path(self.output, self.row), self.row, self.manifest, self.binding, self.root,
                        self.receipts, self.subset, self.validator)

    def test_raw_crlf_receipt_is_verified_and_accepted_slot_replays_without_resend(self):
        self.assertEqual(self.collect(), "accepted")
        terminal, answer = self.replay()
        self.assertEqual(answer, self.answer)
        self.assertTrue(terminal["no_resend"])
        self.assertIn(b"\r\n", self.receipts.verify.call_args.kwargs["final_raw"])
        with self.assertRaises(FileExistsError):
            self.collect()
        sample = c.sample_path(self.output, self.row)
        (sample / "message.json").write_bytes(b"{}")
        with self.assertRaises(ValueError):
            self.replay()

    def test_invalid_exact_quote_is_settled_missingness_without_retry(self):
        self.answer["result"]["evidence"][0]["quote"] = "An invented source quote"
        self.assertEqual(self.collect(), "semantic_rejected")
        terminal, answer = self.replay()
        self.assertFalse(terminal["accepted"])
        self.assertIsNone(answer)

    def test_started_or_native_failure_occupies_slot_and_fails_closed(self):
        def fails(**kwargs):
            kwargs["before_provider_attempt"]()
            raise TimeoutError("Synthetic ambiguous timeout")
        self.assertEqual(self.collect(fails), "unadmitted_no_resend")
        terminal, answer = self.replay()
        self.assertIsNone(answer)
        self.assertEqual(terminal["state"], "unadmitted_no_resend")
        with self.assertRaises(FileExistsError):
            self.collect()
        (c.sample_path(self.output, self.row) / "terminal.json").unlink()
        with self.assertRaisesRegex(ValueError, "unresolved"):
            self.replay()

    def test_grok_unavailable_preserves_precontact_disposition_without_resend(self):
        self.row["endpoint"] = "grok"
        broker = SimpleNamespace(run_grok_native_request=Mock(return_value={"state": "unavailable", "result": None,
                                "failure": {"code": "synthetic_host_gate_busy"}}))
        binding = {**self.binding, "runtime": {"model": "grok-4.7", "reasoning": "high"},
                   "route": {"name": "grok-build-grok-4.7"}, "route_sha256": "f" * 64}
        state = c.collect_one(self.row, self.manifest, binding, self.root, self.output, self.subset,
                              self.validator, self.receipts, broker=broker)
        self.assertEqual(state, "unavailable")
        terminal, answer = c.replay(c.sample_path(self.output, self.row), self.row, self.manifest, binding,
                                   self.root, self.receipts, self.subset, self.validator)
        self.assertEqual(terminal["state"], "unavailable")
        self.assertTrue(terminal["no_resend"])
        self.assertIsNone(answer)
        self.assertFalse((c.sample_path(self.output, self.row) / "attempt-started.json").exists())

    def test_stop_prevents_contact_and_inflight_settles_with_stop_receipt(self):
        (self.output / "STOP").touch()
        contacted = Mock(side_effect=self.call)
        self.assertEqual(self.collect(contacted), "unadmitted_no_resend")
        self.assertFalse((c.sample_path(self.output, self.row) / "attempt-started.json").exists())
        self.assertTrue((self.output / "stop-observed.json").exists())

    def test_stop_during_call_retains_completed_native_answer(self):
        def settles(**kwargs):
            result = self.call(**kwargs)
            (self.output / "STOP").touch()
            return result
        self.assertEqual(self.collect(settles), "accepted")
        self.assertEqual(self.replay()[1], self.answer)
        self.assertTrue((self.output / "stop-observed.json").exists())

    def test_exact_frozen_form_schema_and_shared_context_reach_admission(self):
        original = self.validator.semantic_validate
        observed = []
        def admission(arm, answer, row, texts, subset, context, schema):
            observed.append((row["form"], context, schema))
            return original(arm, answer, row, texts, subset, context=context, schema=schema)
        with patch.object(self.validator, "semantic_validate", side_effect=admission):
            self.assertEqual(self.collect(), "accepted")
            self.replay()
        self.assertEqual(len(observed), 2)
        expected = (self.root / "context.json").read_bytes().decode() + "\n" + (self.root / "shared.txt").read_bytes().decode()
        self.assertTrue(all(form == "novel_work_segment" and context == expected for form, context, _ in observed))
        self.assertTrue(all(schema == json.loads((self.root / "schema.json").read_bytes()) for _, _, schema in observed))
        (self.root / "shared.txt").write_bytes(b"Changed shared work context")
        with self.assertRaises(ValueError):
            self.replay()

    def test_poetry_descendant_dispatch_uses_supplied_poemetric_schema(self):
        projection = c.load_module("p1b_test_portable_projection", c.HERE.parent / "hbq-matched-mfa-v1/prepare.py")
        raw = c.canonical(projection.portable_schema(json.loads((c.HERE / "arms/poemetric.schema.json").read_bytes())))
        self.row.update(form="poem", arm="poemetric")
        self.row["schema_sha256"] = c.digest(raw)
        self.manifest["artifacts"]["schema.json"] = {"sha256": c.digest(raw), "bytes": len(raw)}
        (self.root / "schema.json").write_bytes(raw)
        self.answer = {"status": "CANNOT_ASSESS", "result": None, "abstention_reason": "Synthetic insufficient poem context"}
        self.assertEqual(self.collect(), "accepted")
        terminal, answer = self.replay()
        self.assertTrue(terminal["abstention"])
        self.assertEqual(answer, self.answer)

    def test_secondary_binding_rejects_primary_or_unconfirmed_identity(self):
        home = Path(self.temp.name) / "collection-accounts/cwr-sol-secondary"
        cli = Path(self.temp.name) / "codex.exe"
        env = {"CODEX_HOME": str(home)}
        helper = SimpleNamespace(CLI=cli, COLLECTION_HOME=home, collection_environment=lambda: env)
        manifest = {"runtime": {"codex_home_sha256": c.digest(str(home.resolve()).encode()),
                    "account_identity_sha256": c.SECONDARY_ACCOUNT_SHA256}, "external_pins": {"cli_path_local_only": str(cli), "collection_home_path_local_only": str(home)}}
        c.secondary_binding(manifest, helper)
        for account in ({"account_type": "chatgpt", "email": "primary@example.invalid", "probe_exit_confirmed": True},
                        {"account_type": "chatgpt", "email": "hailey2collet@gmail.com", "probe_exit_confirmed": False}):
            with self.assertRaises(ValueError):
                c.secondary_binding(manifest, helper, account)
        env["OPENAI_API_KEY"] = "synthetic-not-a-key"
        with self.assertRaises(ValueError):
            c.secondary_binding(manifest, helper)

    def test_grok_own_envelope_session_prompt_schema_and_effort_are_bound(self):
        sample = self.output / "grok-synthetic"
        sample.mkdir()
        session = "00000000-0000-4000-8000-000000000001"
        c.record(sample / "native-identity.json", {"session_id": session})
        raw = c.canonical({"sessionId": session, "structuredOutput": self.answer})
        (sample / "native-envelope.json").write_bytes(raw)
        prompt, schema, _, _ = c.inputs(self.root, self.manifest, self.row)
        compact = lambda value: c.canonical(value).rstrip(b"\n")
        runtime = {"session_id_hash": c.digest(session.encode()), "requested_model": "grok-4.7",
                   "requested_reasoning_effort": "high", "reported_model": "grok-4.7-build",
                   "execution_contract": {"output_schema_hash": c.digest(compact(json.loads(schema)))}}
        native = {"state": "completed", "result": {"output": self.answer, "runtime": runtime,
                  "request_hash": c.digest(compact({"prompt": prompt.decode()})), "output_hash": c.digest(compact(self.answer)),
                  "native_envelope_artifact": {"sha256": c.digest(raw), "byte_length": len(raw)}}}
        row = {**self.row, "endpoint": "grok"}
        binding = {"runtime": {"model": "grok-4.7", "reasoning": "high"}, "route": {"reported_model": "grok-4.7-build"}}
        c.record(sample / "native-result.json", native)
        self.assertEqual(c.validate_native(sample, row, binding, prompt, schema, self.receipts), self.answer)
        for field, value in (("session_id_hash", "x"), ("requested_reasoning_effort", "low")):
            wrong = deepcopy(native)
            wrong["result"]["runtime"][field] = value
            (sample / "native-result.json").write_bytes(c.canonical(wrong))
            with self.assertRaises(ValueError):
                c.validate_native(sample, row, binding, prompt, schema, self.receipts)
        (sample / "native-result.json").write_bytes(c.canonical(native))
        with self.assertRaises(ValueError):
            c.validate_native(sample, row, binding, b"Different prompt", schema, self.receipts)


if __name__ == "__main__":
    unittest.main()
