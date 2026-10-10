"""Synthetic selection and composition boundaries; no provider or sample reader."""
import copy
import importlib.util
import json
from pathlib import Path
import shutil
import unittest
from unittest.mock import patch
import uuid

PATH = Path(__file__).with_name("analysis_sol_live_prefix_v2.py")
SPEC = importlib.util.spec_from_file_location("cumulative_prefix_v2", PATH)
m = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)


class CumulativeSelectionFixtures(unittest.TestCase):
    def setUp(self):
        self.root = m.REPO / ("cwr-prefix-v2-fixture-" + uuid.uuid4().hex)
        self.assertEqual(self.root.resolve(), self.root)
        self.root.mkdir()
        self.addCleanup(self.clean)
        self.probe = patch.object(m, "PROBE", self.root)
        self.probe.start()
        self.addCleanup(self.probe.stop)
        self.path = self.root / "selection.json"
        self.as_of = "2026-10-09T01:02:03+00:00"
        self.chunk = "synthetic_read"
        self.job, self.invocation = b'{"fixture":"job"}', b'{"fixture":"invocation"}'
        self.ready = {"schema_version": 1, "state": "WAITING_FOR_NATIVE_ACTIVE_GOAL_PERMIT", "endpoint_ordinal": 957,
                      "logical_sample_id": "a" * 64, "request_sha256": "b" * 64, "owner": m.TASK,
                      "ready_utc": self.as_of, "sample_created": False, "model_contact_started": False, "no_resend": True,
                      "job_sha256": m.sha(self.job), "invocation_sha256": m.sha(self.invocation)}
        self.observation = {"state": "waiting_for_goal_permit", "terminal": None, "settled": 2, "accepted": 1,
                            "semantic_rejected": 1, "unadmitted": 0, "ready": self.ready, "ready_sha256": m.sha(m.canonical(self.ready))}
        self.boundary = {"schema_version": 2, "owner": m.TASK, "state": "FROZEN_CUMULATIVE_SOL008_SELECTION_RELEASE_HELD",
                         "provider_contact": False, "target_release": False, "reservation_settlement": False,
                         "scientific_admission_established": False,
                         "frozen_settled_prefix": {"source": "sol008", "original_first": 955, "original_through": 956,
                             "as_of_ready": 957, "settled": 2, "accepted": 1, "semantic_rejected": 1,
                             "as_of_actual_read": {"status": "fulfilled", "value": {"chunk_id": self.chunk, "exit_code": 0,
                                                                                      "output": json.dumps(self.observation)}}},
                         "source_pins": {"Sol008_job": m.sha(self.job),
                             "continue_sol.py": "09ce5e25dfa9998ce4af8307858dfd9ed29906ba6bd1c61ec1f831833f55c4eb",
                             "src/hbqrs/codex_receipts.py": "5d1c7af681e881a77201dee7cece4a14fa11cadc86d119714766492e547e1116"}}
        self.commitment = self.put(self.boundary)
        self.engine = m.bound_engine(self.commitment)
        self.sources = {self.path: m.canonical(self.boundary), self.engine.OUT / "job.json": self.job,
                        self.engine.LIFE / "invocation.json": self.invocation,
                        self.engine.ORIGINAL: m.canonical({"requests": [{"endpoint": "sol", **{key: self.ready[key] for key in
                            ("endpoint_ordinal", "logical_sample_id", "request_sha256")}}]})}

    def clean(self):
        self.assertEqual(self.root.resolve(), self.root)
        self.assertTrue(self.root.is_relative_to(m.REPO) and self.root != m.REPO)
        shutil.rmtree(self.root)

    def put(self, boundary):
        raw = m.canonical(boundary)
        self.path.write_bytes(raw)
        return {"path": str(self.path), "sha256": m.sha(raw), "bytes": len(raw), "actual_read_chunk": self.chunk}

    def check(self, boundary=None, *, through=956, counts=None, as_of=None, chunk=None):
        boundary = self.boundary if boundary is None else boundary
        commitment = self.put(boundary)
        if chunk is not None:
            commitment["actual_read_chunk"] = chunk
        sources = {**self.sources, self.path: m.canonical(boundary)}
        m.validate_selection(self.engine, sources, commitment, through=through,
                             counts={"accepted": 1, "semantic_rejected": 1} if counts is None else counts,
                             as_of_utc=self.as_of if as_of is None else as_of)

    def spec(self):
        return {"schema_version": 2, "policy": m.POLICY, "owner": m.TASK, "reader_sha256": m.SOURCE_SHA256,
                "dependency_reader": m.dependency_commitment(), "selection_commitment": self.commitment,
                "cumulative_prefix": True, "prior_prefix_additive_input": False}

    def test_selection_is_explicit_and_source_bound(self):
        self.check()
        with self.assertRaises(ValueError):
            self.check(chunk="different_observation")
        with self.assertRaises(ValueError):
            self.check(through=955)
        with self.assertRaises(ValueError):
            self.check(counts={"accepted": 2, "semantic_rejected": 0})
        with self.assertRaises(ValueError):
            self.check(as_of="2026-10-09T01:02:04+00:00")
        with self.assertRaises(ValueError):
            m.validate_selection(self.engine, self.sources, {**self.commitment, "sha256": "0" * 64},
                                 through=956, counts={"accepted": 1, "semantic_rejected": 1}, as_of_utc=self.as_of)
        with self.assertRaises(ValueError):
            m.selection_commitment({**self.commitment, "path": str(self.root / "nested" / "selection.json")})

    def test_receipt_cannot_replace_ready_identity_or_relax_scope(self):
        for role in ("ready_hash", "native_job", "logical_request", "contact", "scope", "observation_exit"):
            with self.subTest(role=role):
                boundary = copy.deepcopy(self.boundary)
                value = boundary["frozen_settled_prefix"]["as_of_actual_read"]["value"]
                observation = json.loads(value["output"])
                if role == "ready_hash":
                    observation["ready_sha256"] = "0" * 64
                elif role == "scope":
                    boundary["target_release"] = True
                elif role == "observation_exit":
                    value["exit_code"] = 1
                else:
                    key = {"native_job": "job_sha256", "logical_request": "logical_sample_id", "contact": "model_contact_started"}[role]
                    observation["ready"][key] = True if role == "contact" else "0" * 64
                    observation["ready_sha256"] = m.sha(m.canonical(observation["ready"]))
                value["output"] = json.dumps(observation)
                with self.assertRaises(ValueError):
                    self.check(boundary)

    def test_loaded_source_and_dependency_are_separate_commitments(self):
        spec = self.spec()
        self.assertEqual(m.validate_bindings(spec), self.commitment)
        self.assertEqual(self.engine.SELF, m.SELF)
        self.assertEqual(self.engine.reader_pin(), m.SOURCE_SHA256)
        self.assertEqual(self.engine.METADATA_PINS[m.DEPENDENCY], (m.DEPENDENCY_SHA256, m.DEPENDENCY_BYTES))
        self.assertNotIn(self.engine.PROBE / "sol008-prefix-admission-review-118.json", self.engine.METADATA_PINS)
        for key, value in (("reader_sha256", m.DEPENDENCY_SHA256), ("dependency_reader", {**m.dependency_commitment(), "sha256": "0" * 64}),
                           ("prior_prefix_additive_input", True), ("schema_version", 1)):
            with self.subTest(key=key), self.assertRaises(ValueError):
                m.validate_bindings({**spec, key: value})
        with patch.object(m, "SOURCE_SHA256", "0" * 64), self.assertRaises(ValueError):
            m.bound_engine(self.commitment)
        with patch.object(m, "DEPENDENCY_SHA256", "0" * 64), self.assertRaises(ValueError):
            m.bound_engine(self.commitment)

    def test_composition_reuses_validation_and_own_turn_guard(self):
        self.assertEqual(Path(self.engine.own_turn_as_of.__code__.co_filename), m.DEPENDENCY)
        start = self.engine.instant("2026-10-09T01:01:00+00:00")
        def rollout(end):
            return b"\n".join(m.canonical(row).rstrip() for row in (
                {"type": "event_msg", "timestamp": "2026-10-09T01:01:00+00:00", "payload": {"type": "task_started"}},
                {"type": "event_msg", "timestamp": end, "payload": {"type": "task_complete"}}))
        self.engine.own_turn_as_of(rollout(self.as_of), started=start, as_of=self.engine.instant(self.as_of))
        with self.assertRaises(ValueError):
            self.engine.own_turn_as_of(rollout("2026-10-09T01:02:04+00:00"), started=start, as_of=self.engine.instant(self.as_of))
        with self.assertRaises(ValueError):
            self.engine.own_turn_as_of(rollout(self.as_of) + b"\n" + rollout(self.as_of), started=start, as_of=self.engine.instant(self.as_of))
        spec = {**self.spec(), "first_original_endpoint_ordinal": 955, "last_reserved_original_endpoint_ordinal": 1554,
                "original_denominator": 3108, "human_labels_opened": False, "provider_calls": 0,
                "state": "FROZEN_SETTLED_PREFIX", "as_of_utc": self.as_of, "through_original_endpoint_ordinal": 956,
                "metadata_commitments": {}, "samples": [], "expected_counts": {"accepted": 1, "semantic_rejected": 1}}
        # The untouched legacy validator still rejects omitted original samples.
        class Snapshot:
            def commitments(self):
                return {}
        with patch.object(self.engine, "metadata", return_value=(self.sources, {}, {}, {"started_utc": self.as_of})), patch.object(
                self.engine, "descriptor_rows", return_value=({}, {}, [{"endpoint_ordinal": 955}])):
            with self.assertRaisesRegex(ValueError, "Frozen prefix count differs"):
                self.engine.validate_spec(spec, Snapshot(), captured=True)

    def test_v2_output_retains_both_sources_and_is_create_only(self):
        report = {**self.spec(), "state": "QUALIFIED_FROZEN_SETTLED_PREFIX_RELEASE_HELD", "source_commitments": {
            str(m.SELF): {"sha256": m.SOURCE_SHA256, "bytes": len(m.SOURCE)},
            str(m.DEPENDENCY): {"sha256": m.DEPENDENCY_SHA256, "bytes": m.DEPENDENCY_BYTES},
            str(self.path): {"sha256": self.commitment["sha256"], "bytes": self.commitment["bytes"]}}}
        result = {"report": report, "records": [], "predictions": {"sol": [], "grok": []}, "identities": [],
                  "metadata_commitments": report["source_commitments"], "runtime_commitments": {}}
        output = self.root / "qualified"
        manifest = m.write_output(result, output, owned_output_root=self.root)
        self.assertEqual(manifest["schema_version"], 2)
        self.assertEqual(manifest["reader_sha256"], m.SOURCE_SHA256)
        self.assertEqual(manifest["dependency_reader"], m.dependency_commitment())
        self.assertEqual(manifest["selection_commitment"], self.commitment)
        self.assertEqual((output / "manifest.json").read_bytes(), m.canonical(manifest))
        with self.assertRaises(ValueError):
            m.write_output(result, output, owned_output_root=self.root)


if __name__ == "__main__":
    unittest.main()
