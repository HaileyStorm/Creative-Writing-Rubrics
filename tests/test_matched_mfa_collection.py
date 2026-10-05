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

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("mfa_collector_test", REPO / "evaluation-results/hbq-matched-mfa-v1/collector.py")
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)


class MatchedMFACollectionTests(unittest.TestCase):
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
        self.subset = c.prepare.load_module("mfa_collection_test_subset", Path("C:/Users/Haile/.codex/tools/model_work_queue/adapters/json_schema_subset.py"))
        self.validator = c.prepare.load_module("mfa_collection_test_validator", c.HERE / "validate_response.py")
        raw = {"prompt.txt": b"Synthetic excerpt quality task", "schema.json": (c.HERE / "arms/holistic.schema.json").read_bytes(),
               "input.txt": b"A synthetic first line.\r\nA synthetic second line.", "context.txt": b"Excerpt scope"}
        for name, data in raw.items():
            (self.root / name).write_bytes(data)
        self.manifest = {"runtime": {"timeout_seconds": 900}, "artifacts": {n: {"sha256": c.prepare.sha(b), "bytes": len(b)} for n, b in raw.items()}}
        self.row = {"endpoint": "sol", "endpoint_ordinal": 1, "logical_sample_id": "a" * 64, "arm": "holistic",
                    "prompt_path": "prompt.txt", "prompt_sha256": c.prepare.sha(raw["prompt.txt"]), "schema_path": "schema.json",
                    "schema_sha256": c.prepare.sha(raw["schema.json"]), "sources": [{"id": "synthetic", "input_path": "input.txt", "sha256": c.prepare.sha(raw["input.txt"])}]}
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

    def test_secondary_binding_rejects_primary_or_unconfirmed_identity(self):
        home = Path(self.temp.name) / "collection-accounts/cwr-sol-secondary"
        cli = Path(self.temp.name) / "codex.exe"
        env = {"CODEX_HOME": str(home)}
        helper = SimpleNamespace(CLI=cli, COLLECTION_HOME=home, collection_environment=lambda: env)
        manifest = {"runtime": {"sol": {"secondary_home_sha256": c.prepare.sha(str(home.resolve()).encode()),
                    "account_identity_sha256": c.prepare.SECONDARY_ACCOUNT_SHA256}}, "external_pins": {"cli_path_local_only": str(cli)}}
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
        raw = c.prepare.canonical({"sessionId": session, "structuredOutput": self.answer})
        (sample / "native-envelope.json").write_bytes(raw)
        prompt, schema, _, _ = c.inputs(self.root, self.manifest, self.row)
        compact = lambda value: c.prepare.canonical(value).rstrip(b"\n")
        runtime = {"session_id_hash": c.prepare.sha(session.encode()), "requested_model": "grok-4.7",
                   "requested_reasoning_effort": "high", "reported_model": "grok-4.7-build",
                   "execution_contract": {"output_schema_hash": c.prepare.sha(compact(json.loads(schema)))}}
        native = {"state": "completed", "result": {"output": self.answer, "runtime": runtime,
                  "request_hash": c.prepare.sha(compact({"prompt": prompt.decode()})), "output_hash": c.prepare.sha(compact(self.answer)),
                  "native_envelope_artifact": {"sha256": c.prepare.sha(raw), "byte_length": len(raw)}}}
        row = {**self.row, "endpoint": "grok"}
        binding = {"runtime": {"model": "grok-4.7", "reasoning": "high"}, "route": {"reported_model": "grok-4.7-build"}}
        c.record(sample / "native-result.json", native)
        self.assertEqual(c.validate_native(sample, row, binding, prompt, schema, self.receipts), self.answer)
        for field, value in (("session_id_hash", "x"), ("requested_reasoning_effort", "low")):
            wrong = deepcopy(native)
            wrong["result"]["runtime"][field] = value
            (sample / "native-result.json").write_bytes(c.prepare.canonical(wrong))
            with self.assertRaises(ValueError):
                c.validate_native(sample, row, binding, prompt, schema, self.receipts)
        (sample / "native-result.json").write_bytes(c.prepare.canonical(native))
        with self.assertRaises(ValueError):
            c.validate_native(sample, row, binding, b"Different prompt", schema, self.receipts)


if __name__ == "__main__":
    unittest.main()
