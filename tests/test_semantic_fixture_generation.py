"""Provider-free preparation and mocked lifecycle checks; no native/account proof."""
import importlib.util
import json
from pathlib import Path
from copy import deepcopy
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("p1b_collection_test", ROOT / "evaluation-results/hbq-semantic-crossform-p1b-v1/collect.py")
collect = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(collect)
prepare = collect.prepare
TOOLS = Path.home() / ".codex/tools"


def synthetic_answer(family):
    words = 140 if family["form"] == "poem" else 1000 if family["form"] == "novel_work_segment" else 500
    variants = {}
    for role in prepare.VARIANTS:
        tokens = [role] + ["fixture"] * (words - 1)
        text = "\n".join(" ".join(tokens[i:i+7]) for i in range(0, words, 7)) if family["form"] == "poem" else " ".join(tokens)
        variants[role] = {"variant_id": family["variant_ids"][role], "text": text,
                          "proposed_intent_note": "Mocked test intent; no literary correctness assertion."}
    return {"schema_version": 1, "family_id": family["family_id"], "form": family["form"], "scope": family["scope"],
        "work_context": " ".join(["invented-context"] * 60) if family["form"] == "novel_work_segment" else "",
        "preservation_anchors": ["synthetic anchor one", "synthetic anchor two", "synthetic anchor three"],
        "variants": variants, "proposed_review_notes": "Mock-only proposal requiring an independent review; not an oracle."}


class MockReceipts:
    """Exercises caller replay boundaries without pretending to be native evidence."""
    def __init__(self):
        self.calls = 0
        self.reject = False

    def verify(self, output, provider, *, prompt, model, reasoning, final_raw):
        self.calls += 1
        if self.reject:
            raise ValueError("mock native receipt rejected")
        if provider["mock_prompt_sha256"] != prepare.digest(prompt.encode()) or model != prepare.MODEL or reasoning != prepare.EFFORT:
            raise ValueError("mock receipt binding differs")
        for item in provider["provider_artifacts"].values():
            raw = prepare.within(output, item["path"]).read_bytes()
            if prepare.digest(raw) != item["sha256"] or len(raw) != item["bytes"]:
                raise ValueError("mock receipt artifact changed")
        message = prepare.within(output, provider["provider_artifacts"]["codex_message"]["path"]).read_bytes()
        if message != final_raw:
            raise ValueError("mock final differs")


class SemanticFixtureGenerationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.directory.cleanup)
        temp = Path(cls.directory.name)
        cli, helper = temp / "mock-codex.exe", temp / "secondary-helper.py"
        cli.write_bytes(b"not executable; provider-free mock fixture")
        home = temp / "collection-accounts/cwr-sol-secondary"
        helper.write_text(f"from pathlib import Path\nCLI = Path({str(cli)!r})\nCOLLECTION_HOME = Path({str(home)!r})\n", encoding="utf-8")
        cls.manifest, cls.files = prepare.build_plan(helper, cli, TOOLS, 300)
        cls.manifest_sha = prepare.digest(prepare.canonical(cls.manifest))
        cls.frozen = temp / "frozen"
        cls.frozen.mkdir()
        for name, raw in cls.files.items():
            prepare.write_new(cls.frozen / name, raw)
        prepare.write_new(cls.frozen / "manifest.json", prepare.canonical(cls.manifest))
        cls.subset = prepare.load_module("p1b_test_schema_subset", TOOLS / "model_work_queue/adapters/json_schema_subset.py")

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.output = Path(self.temp.name) / "results"
        self.output.mkdir()
        collect.record(self.output / "account-binding.json", collect.expected_account_binding(self.manifest))
        self.row = self.manifest["requests"][0]
        self.receipts = MockReceipts()
        self.contacts = 0

    def native_mock(self, answer, *, stop_during=False, fail=False, crlf=False):
        def call(**kwargs):
            kwargs["before_provider_attempt"]()
            self.contacts += 1
            if fail:
                raise TimeoutError("mock bounded attempt has unknown outcome")
            output = kwargs["output_dir"]
            content = prepare.canonical(answer)
            if crlf:
                content = (json.dumps(answer, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8").replace(b"\n", b"\r\n")
            artifacts = {}
            for key, name, raw in (("codex_message", "message.json", content), ("codex_events", "events.jsonl", b"mock events\n"),
                                  ("codex_rollout", "rollout.jsonl", b"mock rollout\n"), ("codex_receipt", "receipt.json", b"mock receipt\n")):
                relative = "responses/" + name
                prepare.write_new(output / relative, raw)
                artifacts[key] = {"path": relative, "sha256": prepare.digest(raw), "bytes": len(raw)}
            if stop_during:
                prepare.write_new(self.output / "STOP", b"stop\n")
            return content.decode().replace("\r\n", "\n"), {"mock_test_only": True, "receipt_policy": prepare.POLICY,
                "mock_prompt_sha256": prepare.digest(kwargs["prompt"].encode()), "provider_artifacts": artifacts}
        return call

    def run_one(self, answer=None, **kwargs):
        return collect.collect_one(self.row, self.manifest, self.manifest_sha, self.frozen, self.output,
            self.native_mock(answer or synthetic_answer(self.row["family"]), **kwargs), self.receipts, self.subset)

    def replay(self):
        return collect.verify_accepted(collect.sample_path(self.output, self.row), self.row, self.manifest,
                                      self.manifest_sha, self.frozen, self.receipts, self.subset)

    def test_prospective_geometry_ids_pairs_and_supported_canonical_schemas(self):
        prepare.validate_manifest(self.manifest)
        self.assertEqual(self.manifest["counts"]["forms"], {"short_narrative": 4, "novel_work_segment": 2, "poem": 2})
        self.assertEqual(len({v for row in self.manifest["requests"] for v in row["family"]["variant_ids"].values()}), 24)
        self.assertEqual(len(self.manifest["pairs"]), 16)
        for row in self.manifest["requests"]:
            schema = json.loads(self.files[row["schema_path"]])
            semantics = json.loads(self.files[row["semantics_path"]])
            self.subset.validate_schema(schema)
            self.assertEqual(semantics["question"]["id"], row["family"]["target_question_id"])
            self.assertTrue(self.subset.matches_schema(synthetic_answer(row["family"]), schema))
            validation = collect.mechanical_validate(row, synthetic_answer(row["family"]), schema, self.subset)
            self.assertTrue(validation["eligible_for_independent_intent_review"])
            self.assertFalse(validation["oracle_accepted"])
            self.assertFalse(validation["eligible_for_scoring"])

    def test_wrong_commitment_and_reassigned_pair_are_rejected(self):
        wrong = deepcopy(self.manifest)
        wrong["pairs"][0]["right_variant_id"] = "another-family.target_defect"
        with self.assertRaisesRegex(ValueError, "content commitment"):
            prepare.validate_manifest(wrong)
        wrong["manifest_content_sha256"] = prepare.digest(prepare.canonical({k: v for k, v in wrong.items() if k != "manifest_content_sha256"}))
        with self.assertRaisesRegex(ValueError, "pair/variant binding"):
            prepare.validate_manifest(wrong)
        with self.assertRaisesRegex(ValueError, "Frozen request artifact"):
            collect.read_pinned(self.frozen, self.row["prompt_path"], {"bytes": 1, "sha256": "wrong"})

    def test_schema_identity_mechanical_bounds_and_duplicate_texts(self):
        schema = json.loads(self.files[self.row["schema_path"]])
        cases = []
        wrong_id = synthetic_answer(self.row["family"])
        wrong_id["variants"]["target_defect"]["variant_id"] = "another-family"
        cases.append(wrong_id)
        too_short = synthetic_answer(self.row["family"])
        too_short["variants"]["target_defect"]["text"] = "too short " * 20
        cases.append(too_short)
        duplicate = synthetic_answer(self.row["family"])
        duplicate["variants"]["legitimate_style"]["text"] = duplicate["variants"]["original"]["text"]
        cases.append(duplicate)
        for answer in cases:
            result = collect.mechanical_validate(self.row, answer, schema, self.subset)
            self.assertFalse(result["accepted_generation"])
            self.assertFalse(result["oracle_accepted"])
        poem = self.manifest["requests"][-1]
        answer = synthetic_answer(poem["family"])
        answer["variants"]["original"]["text"] = answer["variants"]["original"]["text"].replace("\n", " ")
        self.assertIn("original_line_bounds", collect.mechanical_validate(poem, answer, json.loads(self.files[poem["schema_path"]]), self.subset)["reasons"])

    def test_mock_accepted_generation_replays_without_new_contact(self):
        self.assertTrue(self.run_one())
        state = self.replay()
        self.assertEqual(self.contacts, 1)
        self.assertEqual(self.receipts.calls, 2)
        self.assertEqual(state["state"], "accepted_generation")
        self.assertFalse(state["eligible_for_scoring"])
        self.receipts.reject = True
        with self.assertRaisesRegex(ValueError, "mock native receipt rejected"):
            self.replay()
        self.assertEqual(self.contacts, 1)

    def test_mock_crlf_json_preserves_creative_string_contents(self):
        self.row = self.manifest["requests"][-1]
        answer = synthetic_answer(self.row["family"])
        for variant in answer["variants"].values():
            variant["text"] = variant["text"].replace("\n", "\r\n")
        self.assertTrue(self.run_one(answer, crlf=True))
        self.assertEqual(self.replay()["state"], "accepted_generation")
        sample = collect.sample_path(self.output, self.row)
        self.assertIn(b"\r\n", (sample / "responses/message.json").read_bytes())
        for role, variant in answer["variants"].items():
            raw = (sample / "variants" / (role + ".txt")).read_bytes()
            self.assertEqual(raw, variant["text"].encode("utf-8"))
            self.assertIn(b"\r\n", raw)

    def test_started_missing_terminal_and_rejected_generation_block_resend(self):
        sample = collect.sample_path(self.output, self.row)
        sample.mkdir()
        collect.record(sample / "attempt-started.json", {"state": "started", "no_resend": True})
        with self.assertRaisesRegex(ValueError, "unresolved; no resend"):
            self.replay()
        self.assertEqual(self.contacts, 0)
        row = self.manifest["requests"][1]
        self.row = row
        answer = synthetic_answer(row["family"])
        answer["variants"]["target_defect"]["text"] = "short fixture " * 20
        self.assertFalse(self.run_one(answer))
        with self.assertRaisesRegex(ValueError, "requires reconciliation; no resend"):
            self.replay()
        self.assertEqual(self.contacts, 1)

    def test_mock_timeout_preserves_started_slot_and_never_retries(self):
        self.assertFalse(self.run_one(fail=True))
        sample = collect.sample_path(self.output, self.row)
        state = json.loads((sample / "terminal.json").read_bytes())
        self.assertEqual(state["state"], "unadmitted_no_resend")
        self.assertTrue(state["started"])
        self.assertTrue(state["no_resend"])
        with self.assertRaisesRegex(ValueError, "no resend"):
            self.replay()
        self.assertEqual(self.contacts, 1)

    def test_stop_before_contact_and_during_call_preserves_boundary(self):
        prepare.write_new(self.output / "STOP", b"stop\n")
        self.assertFalse(self.run_one())
        self.assertEqual(self.contacts, 0)
        self.assertTrue((self.output / "stop-observed.json").is_file())
        (self.output / "STOP").unlink()
        self.row = self.manifest["requests"][1]
        self.assertTrue(self.run_one(stop_during=True))
        self.assertEqual(self.contacts, 1)
        self.row = self.manifest["requests"][2]
        self.assertFalse(self.run_one())
        self.assertEqual(self.contacts, 1)

    def test_mock_secondary_binding_rejects_wrong_home_account_and_overrides(self):
        pins, runtime = self.manifest["external_pins"], deepcopy(self.manifest["runtime"])
        account = {"account_type": "chatgpt", "email": "synthetic@example.invalid", "probe_exit_confirmed": True}
        expected = prepare.digest(prepare.canonical({"type": "chatgpt", "email": account["email"]}))
        runtime["account_identity_sha256"] = expected
        manifest = dict(self.manifest, runtime=runtime)
        env = {"CODEX_HOME": pins["collection_home_path_local_only"]}
        helper = SimpleNamespace(CLI=Path(pins["cli_path_local_only"]), COLLECTION_HOME=Path(pins["collection_home_path_local_only"]),
                                 collection_environment=lambda: dict(env))
        with mock.patch.object(prepare, "SECONDARY_ACCOUNT_SHA256", expected):
            collect.secondary_binding(manifest, helper, account)
            with self.assertRaisesRegex(ValueError, "subscription identity"):
                collect.secondary_binding(manifest, helper, dict(account, email="other@example.invalid"))
            env["OPENAI_API_KEY"] = "synthetic-forbidden-override"
            with self.assertRaisesRegex(ValueError, "alternate auth/state"):
                collect.secondary_environment(manifest, helper)
            env.pop("OPENAI_API_KEY")
            env["CODEX_HOME"] = str(self.output)
            with self.assertRaisesRegex(ValueError, "secondary home/CLI"):
                collect.secondary_environment(manifest, helper)

    def test_fresh_output_and_immutable_native_final_replay(self):
        with self.assertRaisesRegex(ValueError, "fresh and nonexistent"):
            prepare.output_preflight(self.output)
        with self.assertRaisesRegex(ValueError, "outside repository"):
            collect.output_preflight(ROOT / "new-private-output", self.frozen)
        self.assertTrue(self.run_one())
        sample = collect.sample_path(self.output, self.row)
        (sample / "responses/message.json").write_bytes(b"changed mock final\n")
        with self.assertRaisesRegex(ValueError, "mock receipt artifact changed"):
            self.replay()
        self.assertEqual(self.contacts, 1)


if __name__ == "__main__":
    unittest.main()
