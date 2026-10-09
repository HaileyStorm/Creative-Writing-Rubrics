"""Synthetic trust-boundary checks; no production samples or provider contact."""
import importlib.util
import json
from pathlib import Path
import shutil
import unittest
from unittest.mock import patch
import uuid

PATH = Path(__file__).with_name("analysis_sol_live_prefix_v1.py")
SPEC = importlib.util.spec_from_file_location("live_prefix", PATH)
m = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)


class PrefixFixtures(unittest.TestCase):
    def setUp(self):
        self.root = m.REPO / ("cwr-prefix-fixture-" + uuid.uuid4().hex)
        self.assertTrue(self.root.is_relative_to(m.REPO) and self.root != m.REPO)
        self.root.mkdir()
        self.addCleanup(self.cleanup_fixture)
        self.out = self.root / "samples"
        self.gates = self.root / "gates"
        self.observations = self.root / "observations"
        for folder in (self.out, self.gates, self.observations):
            folder.mkdir()
        self.patchers = [patch.object(m, name, value) for name, value in
                         (("OUT", self.out), ("GATES", self.gates), ("OBSERVATIONS", self.observations))]
        for item in self.patchers:
            item.start()
        for item in self.patchers:
            self.addCleanup(item.stop)
        self.runtime = m.runtime(m.Snapshot())
        self.native = self.runtime[1].__globals__["codex_receipts"]

    def cleanup_fixture(self):
        self.assertTrue(self.root.resolve() == self.root and self.root.is_relative_to(m.REPO) and self.root != m.REPO)
        shutil.rmtree(self.root)

    def put(self, path, value):
        raw = value if isinstance(value, bytes) else m.canonical(value)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        return raw

    def fixture(self, *, duplicate=False):
        schema = {"type": "object", "properties": {
            "status": {"type": "string", "enum": ["CANNOT_ASSESS"]},
            "result": {"type": "null"}, "abstention_reason": {"type": "string"}},
            "required": ["status", "result", "abstention_reason"], "additionalProperties": False}
        artifacts = {"context.txt": b"Context kept out of prediction cache", "input.txt": b"Frozen source prose",
                     "prompt.txt": b"Judge this frozen request", "schema.json": m.canonical(schema)}
        rows, pins = [], []
        for index in range(2):
            ordinal = 955 + index
            row = {"endpoint": "sol", "endpoint_ordinal": ordinal, "ordinal": ordinal * 2,
                   "logical_sample_id": m.sha(str(ordinal).encode()), "arm": "holistic", "repeat": 0,
                   "sources": [{"id": "story", "input_path": "input.txt", "sha256": m.sha(artifacts["input.txt"])}],
                   "prompt_path": "prompt.txt", "prompt_sha256": m.sha(artifacts["prompt.txt"]), "prompt_bytes": len(artifacts["prompt.txt"]),
                   "schema_path": "schema.json", "schema_sha256": m.sha(artifacts["schema.json"]), "schema_bytes": len(artifacts["schema.json"])}
            row["request_sha256"] = m.sha(m.canonical(row))
            rows.append(row)
            sample = self.out / f"{ordinal:04d}-{row['logical_sample_id'][:12]}"
            sample.mkdir()
            response = {"status": "CANNOT_ASSESS", "result": None, "abstention_reason": "Unavailable" if index == 0 else ""}
            final = m.canonical(response)
            identity_index = 0 if duplicate else index
            thread, turn = str(uuid.UUID(int=identity_index + 1)), str(uuid.UUID(int=identity_index + 10))
            timestamp = "2026-10-09T04:17:05+00:00"
            metadata = {"turn_id": turn}
            rollout = [
                {"type": "session_meta", "payload": {"id": thread, "source": "exec", "model_provider": "openai", "cwd": str(sample)}},
                {"type": "event_msg", "timestamp": timestamp, "payload": {"type": "task_started", "turn_id": turn}},
                {"type": "turn_context", "payload": {"turn_id": turn, "model": "gpt-6.1-sol", "effort": "high", "cwd": str(sample)}},
                {"type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": artifacts["prompt.txt"].decode()}],
                    "internal_chat_message_metadata_passthrough": {**metadata, "content_item_kinds": ["user.text"]}}},
                {"type": "response_item", "payload": {"type": "message", "role": "assistant", "phase": "final_answer", "content": [{"type": "output_text", "text": final.decode()}],
                    "internal_chat_message_metadata_passthrough": metadata}},
                {"type": "event_msg", "timestamp": "2026-10-09T04:17:10+00:00", "payload": {"type": "task_complete", "turn_id": turn, "last_agent_message": final.decode()}},
            ]
            events = [{"type": "thread.started", "thread_id": thread}, {"type": "turn.started"},
                      {"type": "item.completed", "item": {"type": "agent_message", "text": final.decode()}},
                      {"type": "turn.completed", "usage": {}}]
            rr, er = b"".join(m.canonical(r) for r in rollout), b"".join(m.canonical(r) for r in events)
            receipt = self.native.project(rr, er, final, prompt=artifacts["prompt.txt"].decode(), model="gpt-6.1-sol", reasoning="high", cwd=sample)
            receipt["reader_sha256"] = self.native.binding()["reader_sha256"]
            retained = {"codex_events": ("responses/events.jsonl", er), "codex_message": ("responses/message.json", final),
                        "codex_rollout": ("responses/rollout.jsonl", rr), "codex_receipt": ("responses/receipt.json", m.canonical(receipt))}
            provider = {"receipt_policy": self.native.POLICY, "reported": receipt["reported"],
                        "command": self.runtime[-1](sample), "provider_artifacts": {}}
            for name, (relative, raw) in retained.items():
                self.put(sample / relative, raw)
                provider["provider_artifacts"][name] = {"path": relative, "sha256": m.sha(raw), "bytes": len(raw)}
            acceptance = self.runtime[4].semantic_validate("holistic", response, row, {"story": artifacts["input.txt"].decode()}, self.runtime[3], schema=schema)
            native_raw, response_raw, acceptance_raw = m.canonical(provider), m.canonical(response), m.canonical(acceptance)
            terminal = {"state": "accepted" if index == 0 else "semantic_rejected", "accepted": index == 0,
                        "abstention": True, "no_resend": True, "native_result_sha256": m.sha(native_raw),
                        "response_sha256": m.sha(response_raw), "acceptance_sha256": m.sha(acceptance_raw)}
            raw_files = {"condition.json": m.canonical(row), "terminal.json": m.canonical(terminal), "native-result.json": native_raw,
                         "native-identity.json": m.canonical({"logical_sample_id": row["logical_sample_id"], "session_id": None}),
                         "attempt-started.json": m.canonical({"state": "before_contact", "time": "2026-10-09T04:17:04+00:00", "session_id": None, "no_resend": True}),
                         "schema.json": artifacts["schema.json"], "response.json": response_raw, "acceptance.json": acceptance_raw}
            for name, raw in raw_files.items():
                self.put(sample / name, raw)
            ready = {"schema_version": 1, "state": "WAITING_FOR_NATIVE_ACTIVE_GOAL_PERMIT", "owner": m.TASK,
                     "endpoint_ordinal": ordinal, "logical_sample_id": row["logical_sample_id"], "request_sha256": row["request_sha256"],
                     "invocation_sha256": m.sha(b"invocation"), "job_sha256": m.sha(b"job"), "ready_utc": "2026-10-09T04:17:01+00:00",
                     "sample_created": False, "model_contact_started": False, "no_resend": True}
            permit = {"owner": m.TASK, "goal_thread_id": m.TASK, "goal_status": "active", "goal_source": "actual native tools.get_goal",
                      "goal_updated_at": 10, "goal_tokens_used": 20, "ready_sha256": m.sha(m.canonical(ready)),
                      "observed_utc": "2026-10-09T04:17:02+00:00", **{key: ready[key] for key in ("endpoint_ordinal", "logical_sample_id", "request_sha256", "invocation_sha256")}}
            observation = {"schema_version": 1, "owner": m.TASK, "permit": permit, "ready_metadata": ready,
                           "ready_sha256": m.sha(m.canonical(ready)), "native_goal": {"goal": {
                               "threadId": m.TASK, "status": "active", "updatedAt": 10, "tokensUsed": 20}}}
            self.put(self.gates / f"{ordinal:04d}-ready.json", ready)
            self.put(self.gates / f"{ordinal:04d}-permit.json", permit)
            self.put(self.observations / f"{ordinal:04d}-observation.json", observation)
            _, captured, sponsorship = m.sample_capture(m.Snapshot(), row)
            pins.append({"prefix_position": index + 1, "original_endpoint_ordinal": ordinal, "original_request_ordinal": ordinal * 2,
                         "logical_sample_id": row["logical_sample_id"], "request_sha256": row["request_sha256"],
                         "files": {name: {"sha256": m.sha(raw), "bytes": len(raw)} for name, raw in captured.items()},
                         "sponsorship": {name: {"sha256": m.sha(raw), "bytes": len(raw)} for name, raw in sponsorship.items()}})
        source = {"requests": rows, "artifacts": {name: {"sha256": m.sha(raw), "bytes": len(raw)} for name, raw in artifacts.items()},
                  "implementation": {"semantic_validator_sha256": m.CODE_PINS[m.HERE / "validate_response.py"], "schema_subset_sha256": m.CODE_PINS[m.SUBSET]}}
        source["manifest_content_sha256"] = m.sha(m.canonical(source))
        for name, raw in artifacts.items():
            self.put(self.root / "frozen" / name, raw)
        spec = {"as_of_utc": "2026-10-09T04:18:00+00:00", "samples": pins, "expected_counts": {"accepted": 1, "semantic_rejected": 1}, "prior_native_identities": []}
        job = {"model": "gpt-6.1-sol", "reasoning": "high", "validator_sha256": source["implementation"]["semantic_validator_sha256"],
               "receipt_reader_sha256": m.CODE_PINS[m.REPO / "src/hbqrs/codex_receipts.py"]}
        metadata = {m.ORIGINAL: m.canonical(source), m.LIFE / "invocation.json": b"invocation", self.out / "job.json": b"job"}
        return spec, (metadata, job, {}, {"started_utc": "2026-10-09T04:17:00+00:00"}, source, source, rows)

    def replay(self, spec, fixture):
        # This seam isolates per-attempt qualification. Metadata/scheduling checks
        # are exercised independently below; fixtures do not certify production.
        with patch.object(m, "validate_spec", return_value=fixture), patch.object(m, "MANIFEST", self.root / "frozen/manifest.json"):
            return m.replay_prefix(spec, specification_sha256=m.sha(m.canonical(spec)))

    def test_native_and_semantic_replay_retains_rejection_and_closed_gates(self):
        spec, fixture = self.fixture()
        result = self.replay(spec, fixture)
        self.assertEqual([r["record"]["state"] for r in result["records"]], ["accepted", "semantic_rejected"])
        self.assertIsNone(result["records"][1]["record"]["accepted"])
        self.assertEqual(result["report"]["original_endpoint_positions"], [955, 956])
        self.assertEqual(result["report"]["original_request_positions"], [1910, 1912])
        self.assertEqual(len(result["predictions"]["sol"]), 1)
        self.assertEqual(result["predictions"]["grok"], [])
        self.assertNotIn("source_text", result["predictions"]["sol"][0]["vote"])
        self.assertNotIn("context_text", result["predictions"]["sol"][0]["vote"])
        self.assertFalse(result["report"]["reservation_released"])
        self.assertFalse(result["report"]["full_label_release_gate_passed"])
        self.assertFalse(result["report"]["production_wire_catalog_attested"])
        output = self.root / "output"
        manifest = m.write_output(result, output, owned_output_root=self.root)
        self.assertEqual(manifest["qualified_accepted"], 1)
        with self.assertRaisesRegex(ValueError, "Fresh caller-owned"):
            m.write_output(result, output, owned_output_root=self.root)

    def test_duplicate_verified_native_identity_rejected(self):
        spec, fixture = self.fixture(duplicate=True)
        with self.assertRaisesRegex(ValueError, "Duplicate native identity"):
            self.replay(spec, fixture)

    def test_exact_startup_command_and_frozen_bytes_cannot_be_substituted(self):
        spec, fixture = self.fixture()
        row = fixture[-1][0]
        sample = self.out / f"0955-{row['logical_sample_id'][:12]}"
        native = json.loads((sample / "native-result.json").read_bytes())
        native["command"].append("--enable-tools")
        native_raw = self.put(sample / "native-result.json", native)
        terminal = json.loads((sample / "terminal.json").read_bytes())
        terminal["native_result_sha256"] = m.sha(native_raw)
        self.put(sample / "terminal.json", terminal)
        with self.assertRaisesRegex(ValueError, "Frozen prefix artifact"):
            self.replay(spec, fixture)
        _, raw, _ = m.sample_capture(m.Snapshot(), row)
        spec["samples"][0]["files"] = {name: {"sha256": m.sha(value), "bytes": len(value)} for name, value in raw.items()}
        with self.assertRaisesRegex(ValueError, "all-tools-disabled"):
            self.replay(spec, fixture)

    def test_rich_goal_and_chronology_are_independent_of_native_success(self):
        spec, fixture = self.fixture()
        row = fixture[-1][0]
        _, raw, sponsorship = m.sample_capture(m.Snapshot(), row)
        kwargs = dict(iv_sha=m.sha(b"invocation"), job_sha=m.sha(b"job"), child_started=m.instant("2026-10-09T04:17:00+00:00"), as_of=m.instant(spec["as_of_utc"]))
        changed = dict(sponsorship)
        observation = json.loads(changed["observation"])
        observation["native_goal"]["goal"]["tokensUsed"] += 1
        changed["observation"] = m.canonical(observation)
        with self.assertRaisesRegex(ValueError, "Rich native Goal"):
            m.sponsorship_check(row, raw, changed, **kwargs)
        started = json.loads(raw["attempt-started.json"])
        started["time"] = "2026-10-09T04:17:01+00:00"
        changed_raw = {**raw, "attempt-started.json": m.canonical(started)}
        with self.assertRaisesRegex(ValueError, "chronology"):
            m.sponsorship_check(row, changed_raw, sponsorship, **kwargs)

    def test_future_native_completion_and_prior_overlap_fail_closed(self):
        spec, fixture = self.fixture()
        spec["as_of_utc"] = "2026-10-09T04:17:06+00:00"
        with self.assertRaisesRegex(ValueError, "completion outside frozen as-of"):
            self.replay(spec, fixture)
        spec["as_of_utc"] = "2026-10-09T04:18:00+00:00"
        spec["prior_native_identities"] = [["sol_thread", m.sha(str(uuid.UUID(int=1)).encode())]]
        with self.assertRaisesRegex(ValueError, "Duplicate native identity"):
            self.replay(spec, fixture)

    def test_path_containment_aliases_and_stable_readback(self):
        for name in ("../outside", "responses/../../outside", "C:/outside", "file:stream", "/outside"):
            with self.assertRaises(ValueError):
                m.within(self.root, name)
        snapshot = m.Snapshot()
        path = self.root / "frozen.json"
        self.put(path, {"state": "settled"})
        snapshot.get(path)
        self.put(path, {"state": "changed"})
        with self.assertRaisesRegex(ValueError, "changed during qualification"):
            snapshot.stable()
        with patch.object(m.Path, "is_symlink", return_value=True):
            with self.assertRaisesRegex(ValueError, "Reparse"):
                m.plain(path)

    def test_original_geometry_and_spec_positions_cannot_be_renumbered(self):
        rows = []
        for ordinal in range(1, 4):
            for endpoint in ("grok", "sol"):
                row = {"endpoint": endpoint, "endpoint_ordinal": ordinal, "ordinal": len(rows) + 1,
                       "logical_sample_id": m.sha(f"{endpoint}{ordinal}".encode())}
                row["request_sha256"] = m.sha(m.canonical(row))
                rows.append(row)
        base = {"requests": rows, "labels_read": False}
        source = {"requests": [row for row in rows if row["endpoint"] == "sol" and row["endpoint_ordinal"] >= 2],
                  "continuation": {"reserved_through_endpoint_ordinal": 1}, "labels_read": False}
        sources = {m.ORIGINAL: m.canonical(base), m.MANIFEST: m.canonical(source)}
        with patch.object(m, "FIRST", 2), patch.object(m, "LAST", 3), patch.object(m, "DENOMINATOR", 6):
            self.assertEqual([r["ordinal"] for r in m.descriptor_rows(sources, 2)[2]], [4])
            source["requests"].reverse()
            sources[m.MANIFEST] = m.canonical(source)
            with self.assertRaisesRegex(ValueError, "reorders or substitutes"):
                m.descriptor_rows(sources, 2)

    def test_as_of_selection_requires_retained_actual_settled_observation(self):
        ready = {"endpoint_ordinal": 957, "ready_utc": "2026-10-09T04:18:00+00:00", "owner": m.TASK,
                 "sample_created": False, "model_contact_started": False,
                 "invocation_sha256": m.sha(b"invocation"), "job_sha256": m.sha(b"job")}
        observation = {"state": "waiting_for_goal_permit", "terminal": None, "settled": 2, "accepted": 1,
                       "semantic_rejected": 1, "unadmitted": 0, "ready": ready, "ready_sha256": m.sha(m.canonical(ready))}
        boundary = {"owner": m.TASK, "schema_version": 1,
                    "state": "SOURCE_REVIEW_LIVE_PREFIX_REQUIRES_VERSIONED_QUALIFICATION_READER",
                    "provider_contact": False, "target_release": False, "reservation_settlement": False,
                    "scientific_admission_established": False,
                    "source_pins": {"Sol008_job": m.sha(b"job"), "continue_sol.py": m.CODE_PINS[m.HERE / "continue_sol.py"],
                                    "src/hbqrs/codex_receipts.py": m.CODE_PINS[m.REPO / "src/hbqrs/codex_receipts.py"]},
                    "frozen_initial_prefix": {"source": "sol008", "original_first": 955, "original_through": 956,
                        "as_of_ready": 957, "settled": 2, "accepted": 1, "semantic_rejected": 1,
                        "as_of_actual_read": {"status": "fulfilled", "value": {"exit_code": 0, "chunk_id": "633291", "output": json.dumps(observation)}}}}
        sources = {m.SELECTION: m.canonical(boundary), m.LIFE / "invocation.json": b"invocation", self.out / "job.json": b"job"}
        kwargs = {"as_of_utc": ready["ready_utc"], "through": 956, "counts": {"accepted": 1, "semantic_rejected": 1}}
        m.selection_check(sources, **kwargs)
        observation["settled"] = 3
        boundary["frozen_initial_prefix"]["as_of_actual_read"]["value"]["output"] = json.dumps(observation)
        sources[m.SELECTION] = m.canonical(boundary)
        with self.assertRaisesRegex(ValueError, "initial as-of observation differs"):
            m.selection_check(sources, **kwargs)


if __name__ == "__main__":
    unittest.main()
