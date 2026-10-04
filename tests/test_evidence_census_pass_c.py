import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from copy import deepcopy


SOURCE = Path(__file__).resolve().parents[1] / "evaluation-results/hbq-evidence-census-pass-c-v1/census.py"
SPEC = importlib.util.spec_from_file_location("evidence_census_c", SOURCE)
census = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(census)


class CensusPassCTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.inputs = census.Inputs(self.root)

    def write(self, path, value, raw=False):
        data = value if raw else census.canonical(value) + b"\n"
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        return census.sha(data)

    def packet(self, accepted=True, repeat=False):
        self.inputs = census.Inputs(self.root)
        self.base = "collection/sol/request-0001"
        prompt, schema = b"synthetic prompt\n", b"{}\n"
        self.row = {"ordinal": 1, "sample_id": "synthetic", "group_id_local_only": "group",
                    "source_sha256": "source", "prompt_sha256": census.sha(prompt), "prompt_bytes": len(prompt),
                    "schema_sha256": census.sha(schema), "schema_bytes": len(schema), "question_ids": ["q1", "q2"]}
        if repeat:
            self.row.update(original_ordinal=9, planned_repeat_id="batch35-repeat-1|main-ordinal-9")
        self.manifest = {"disclosure_sha256": "disclosure"}
        start = {"ordinal": 1, "attempt_number": 1, "manifest_sha256": "manifest", "plan_sha256": "plan",
                 "prompt_sha256": self.row["prompt_sha256"], "schema_sha256": self.row["schema_sha256"],
                 "session_id": "synthetic-client", "model": "gpt-6-sol", "effort": "xhigh"}
        self.write(self.base + "/attempt-start.json", start)
        self.write(self.base + "/contact-admission.json", {"ordinal": 1, "session_id": "synthetic-client",
                                                          "disclosure_sha256": "disclosure"})
        self.write(self.base + "/prompt.txt", prompt, True)
        self.write(self.base + "/schema.json", schema, True)
        raw_values = [{"question_id": q, "verdict": "YES", "evidence": []} for q in ["q1", "q2"]]
        final = census.canonical({"verdicts": raw_values}) + b"\n"
        events = [{"type": "thread.started", "thread_id": "synthetic-thread"}]
        if accepted:
            events.extend([{"type": "turn.started"}, {"type": "item.completed", "item": {
                "type": "agent_message", "text": final.decode()}}, {"type": "turn.completed", "usage": {}}])
        events_raw = b"".join(census.canonical(event) + b"\n" for event in events)
        self.write(self.base + "/events.jsonl", events_raw, True)
        completion = {"events_sha256": census.sha(events_raw), "events_bytes": len(events_raw),
                      "state": "exited" if accepted else "unknown_exit_requires_reconciliation",
                      "exit_code": 0 if accepted else None, "final_sha256": census.sha(final), "final_bytes": len(final)}
        completion_sha = self.write(self.base + "/process-completion.json", completion)
        terminal = {"ordinal": 1, "manifest_sha256": "manifest", "plan_sha256": "plan", "session_id": "synthetic-client",
                    "state": "accepted" if accepted else "unknown_exit_requires_reconciliation",
                    "process_completion_sha256": completion_sha}
        if accepted:
            self.write(self.base + "/final.json", final, True)
            terminal.update(final_sha256=census.sha(final), native_identity={"thread_id": "synthetic-thread",
                "native_event_count": len(events), "tool_events": 0, "turn_completed": True},
                verdicts=[dict(v, artifact_id="synthetic", bundle_id="prose.short_form") for v in raw_values])
        else:
            terminal["native_thread_ids"] = ["synthetic-thread"]
        self.terminal = terminal
        self.receipt = {"ordinal": 1, "state": terminal["state"],
                        "terminal_sha256": self.write(self.base + "/terminal.json", terminal)}
        if repeat and accepted:
            self.write(self.base + "/planned-repeat-identity.json", {"endpoint": "sol", "repeat_ordinal": 1,
                "original_ordinal": 9, "logical_repeat_id": "batch35-repeat-1|sol|main-ordinal-9",
                "plan_sha256": "plan", "terminal_sha256": self.receipt["terminal_sha256"]})

    def project(self, scope="main"):
        return census.project_packet(self.inputs, scope, "sol", "collection", self.row,
                                     self.receipt, self.manifest, "manifest", "plan")

    def replace_terminal(self):
        self.receipt["terminal_sha256"] = self.write(self.base + "/terminal.json", self.terminal)

    def test_exact_own_native_completion_and_repeat_identity(self):
        self.packet(repeat=True)
        slot = self.project("repeat")
        self.assertEqual([v["question_id"] for v in slot["leaves"]], ["q1", "q2"])
        self.assertEqual(slot["logical_repeat_id"], "batch35-repeat-1|sol|main-ordinal-9")
        self.assertEqual(slot["original_ordinal"], 9)
        self.assertNotIn("synthetic-thread", json.dumps(slot))

    def test_wrong_native_thread_fails_even_with_coherent_terminal_hash(self):
        self.packet()
        self.terminal["native_identity"]["thread_id"] = "another-thread"
        self.replace_terminal()
        with self.assertRaisesRegex(ValueError, "native identity/completion"):
            self.project()

    def test_grok_native_binding_and_definitely_not_contacted_slot(self):
        self.packet()
        sol_base = self.base
        self.base = "collection/grok/request-0001"
        start = json.loads((self.root / sol_base / "attempt-start.json").read_bytes())
        self.write(self.base + "/attempt-start.json", start)
        self.manifest["grok_route_sha256"] = "route"
        self.write(self.base + "/contact-admission.json", {"ordinal": 1, "session_id": start["session_id"],
            "disclosure_sha256": "disclosure", "route_sha256": "route"})
        native = {"session_id_hash": census.sha(start["session_id"].encode()), "request_id_hash": "request", "observed_turns": 1}
        runtime = dict(native, envelope_hash="envelope", execution_contract={
            "staged_prompt_sha256": self.row["prompt_sha256"], "staged_prompt_byte_length": self.row["prompt_bytes"]})
        outcome = {"state": "completed", "failure": None, "result": {"runtime": runtime,
            "native_envelope_artifact": {"sha256": "envelope", "byte_length": 100},
            "output": {"verdicts": [{"question_id": q, "verdict": "YES"} for q in ["q1", "q2"]]}}}
        self.terminal = {"ordinal": 1, "manifest_sha256": "manifest", "plan_sha256": "plan",
            "session_id": start["session_id"], "state": "accepted", "native_identity": native,
            "native_envelope_sha256": "envelope", "broker_outcome_sha256": self.write(self.base + "/broker-outcome.json", outcome),
            "verdicts": self.terminal["verdicts"]}
        self.replace_terminal()
        project = lambda: census.project_packet(census.Inputs(self.root), "main", "grok", "collection",
            self.row, self.receipt, self.manifest, "manifest", "plan")
        self.assertTrue(project()["accepted"])
        self.terminal["native_identity"]["request_id_hash"] = "other-native"
        self.replace_terminal()
        with self.assertRaisesRegex(ValueError, "Grok native envelope/identity"):
            project()
        (self.root / self.base / "contact-admission.json").unlink()
        self.terminal = {"ordinal": 1, "manifest_sha256": "manifest", "plan_sha256": "plan",
            "session_id": start["session_id"], "state": "definitely_not_contacted",
            "broker_outcome_sha256": self.write(self.base + "/broker-outcome.json", {
                "state": "definitely_not_contacted", "failure": {}, "result": None})}
        self.receipt["state"] = "definitely_not_contacted"
        self.replace_terminal()
        slot = project()
        self.assertEqual(slot["leaves"], [])
        self.assertIsNone(slot["native_identity_sha256"])
        self.assertFalse(slot["lineage"]["contact_admission_exists"])

    def test_foreign_tool_event_is_not_a_completed_native_vote(self):
        self.packet()
        path = self.root / self.base / "events.jsonl"
        events = [json.loads(line) for line in path.read_bytes().splitlines()]
        events.insert(2, {"type": "item.completed", "item": {"type": "command_execution"}})
        raw = b"".join(census.canonical(event) + b"\n" for event in events)
        self.write(self.base + "/events.jsonl", raw, True)
        completion = json.loads((self.root / self.base / "process-completion.json").read_bytes())
        completion.update(events_sha256=census.sha(raw), events_bytes=len(raw))
        self.terminal["process_completion_sha256"] = self.write(self.base + "/process-completion.json", completion)
        self.terminal["native_identity"]["native_event_count"] = len(events)
        self.replace_terminal()
        with self.assertRaisesRegex(ValueError, "foreign or tool events"):
            self.project()

    def test_reordered_or_missing_leaf_fails(self):
        for change in (lambda values: values.reverse(), lambda values: values.pop()):
            with self.subTest(change=change):
                self.packet()
                change(self.terminal["verdicts"])
                self.replace_terminal()
                with self.assertRaisesRegex(ValueError, "leaf order or coverage"):
                    self.project()

    def test_unknown_exit_remains_unadmitted_without_reading_a_final(self):
        self.packet(accepted=False, repeat=True)
        slot = self.project("repeat")
        self.assertFalse(slot["accepted"])
        self.assertEqual(slot["leaves"], [])
        self.assertEqual(slot["disposition"], "unknown_exit_requires_reconciliation")
        self.assertTrue(slot["no_resend"])
        self.assertEqual(slot["planned_question_count"], 2)
        self.assertEqual(slot["original_ordinal"], 9)

    def test_contact_and_repeat_identity_bindings_fail_closed(self):
        self.packet()
        self.write(self.base + "/contact-admission.json", {"ordinal": 1, "session_id": "another-client",
                                                          "disclosure_sha256": "disclosure"})
        with self.assertRaisesRegex(ValueError, "Contact admission"):
            self.project()
        self.packet(repeat=True)
        path = self.base + "/planned-repeat-identity.json"
        identity = json.loads((self.root / path).read_bytes())
        identity["original_ordinal"] = 10
        self.write(path, identity)
        with self.assertRaisesRegex(ValueError, "Repeat native receipt identity"):
            self.project("repeat")

    def test_missing_repair_never_promotes_controller_failure(self):
        self.packet()
        self.terminal = {"ordinal": 1, "session_id": "synthetic-client", "state": "unclassified_controller_exception"}
        self.receipt["state"] = "runner_exception"
        self.replace_terminal()
        with self.assertRaisesRegex(ValueError, "terminal state/condition"):
            self.project()

    def test_same_text_planned_repeats_preserve_parents_and_replay_is_rejected(self):
        base = {"sample_id": "sample", "source_sha256": "same-source", "prompt_sha256": "same-prompt",
                "schema_sha256": "schema", "question_ids": ["q"], "cohort": "batch3", "group_id_local_only": "group",
                "variant_id_local_only": "variant", "prompt_bytes": 12, "schema_bytes": 3}
        main = {"requests": [dict(base, ordinal=1), dict(base, ordinal=2)]}
        repeat = {"main_plan_sha256": "parent", "blind_predictions_sha256": "predictions",
                  "exact_prompt_bytes_reused_from_main": True, "repeat_identity_is_distinct_from_main": True,
                  "logical_repeat_id_template": "batch35-repeat-1|{endpoint}|main-ordinal-{original_ordinal}",
                  "requests": [dict(base, ordinal=i, original_ordinal=i,
                                    planned_repeat_id=f"batch35-repeat-1|main-ordinal-{i}") for i in [1, 2]]}
        census.validate_repeat_requests(main, repeat, "parent", "predictions")
        replay = deepcopy(repeat)
        replay["requests"][1] = dict(replay["requests"][0], ordinal=2)
        with self.assertRaisesRegex(ValueError, "Duplicate or absent repeat parent"):
            census.validate_repeat_requests(main, replay, "parent", "predictions")
        wrong = deepcopy(repeat)
        wrong["requests"][1]["prompt_sha256"] = "changed"
        with self.assertRaisesRegex(ValueError, "Repeat parent prompt"):
            census.validate_repeat_requests(main, wrong, "parent", "predictions")

    def test_overlap_intent_and_source_pin_fail_closed(self):
        path = "collection/waves/grok-wave-0001"
        intent = {"endpoint": "grok", "manifest_sha256": "manifest", "ordinals": [1, 2]}
        intent_sha = self.write(path + ".intent.json", intent)
        result = {"ordinals": [1, 2], "intent_sha256": intent_sha,
                  "terminals": [{"ordinal": i, "state": "accepted", "terminal_sha256": str(i)} for i in [1, 2]]}
        result_sha = self.write(path + ".result.json", result)
        seen = set()
        census.wave_packets(self.inputs, "collection", "grok", [1], 2, "manifest", seen)
        with self.assertRaisesRegex(ValueError, "Overlapping"):
            census.wave_packets(self.inputs, "collection", "grok", [1], 2, "manifest", seen)
        intent["endpoint"] = "sol"
        result["intent_sha256"] = self.write(path + ".intent.json", intent)
        self.write(path + ".result.json", result)
        with self.assertRaisesRegex(ValueError, "intent/result binding"):
            census.wave_packets(census.Inputs(self.root), "collection", "grok", [1], 2, "manifest", set())
        with self.assertRaisesRegex(ValueError, "Source hash differs"):
            census.Inputs(self.root).raw(path + ".result.json", result_sha)

    def test_existing_or_input_output_is_rejected(self):
        descriptor = {"control_subdirectory": "lamp-evaluation-r227"}
        with self.assertRaisesRegex(ValueError, "fresh nonexistent"):
            census.output_preflight(self.root, self.root, descriptor)
        with self.assertRaisesRegex(ValueError, "overlaps retained"):
            census.output_preflight(self.root / "lamp-evaluation-r227/new", self.root, descriptor)


if __name__ == "__main__":
    unittest.main()
