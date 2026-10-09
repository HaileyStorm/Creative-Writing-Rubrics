"""Invented-data wiring proof; lifecycle doubles do not prove native release."""
import copy
from contextlib import contextmanager
import json
import os
from pathlib import Path
from tempfile import gettempdir
from types import FunctionType, ModuleType
import unittest
from uuid import uuid4

import analysis
import analysis_chain as chain
import analysis_chain_v3 as v3
import analysis_chain_v4 as v4
import analysis_release_measurements_v1 as release


def private_module(module, **overrides):
    result = ModuleType(module.__name__)
    result.__dict__.update(vars(module))
    result.__dict__.update(overrides)
    return result


@contextmanager
def scratch():
    root = Path(os.environ.get("CWR_RELEASE_TEST_ROOT", gettempdir())).resolve()
    directory = root / ("measurement-release-test-" + uuid4().hex)
    if not directory.resolve().is_relative_to(root):
        raise ValueError("Test scratch escapes its approved root")
    # Ordinary workspace creation inherits the writable parent's Windows DACL.
    # TemporaryDirectory's owner-only mode is inaccessible to this sandbox token.
    directory.mkdir()
    try:
        yield str(directory)
    finally:
        # Remove only the exact invented fixture, never an unknown subtree.
        sample = directory / "0001-sol-0001"
        path = sample / "attempt-started.json"
        if path.is_file():
            path.unlink()
        if sample.is_dir():
            sample.rmdir()
        directory.rmdir()


class ReleaseMeasurementsTests(unittest.TestCase):
    def inputs(self, directory, *, lifecycle_error=False):
        self.calls = {"labels": 0, "hbq": 0, "analysis": 0, "lifecycle": 0}
        stories = [{"id": f"s{i}", "plot": i // 3} for i in range(36)]
        rows = [{"endpoint": ep, "endpoint_ordinal": i, "logical_sample_id": f"{ep}-{i:04d}",
                 "arm": "ttcw14", "story_id": "s0", "repeat": 0}
                for ep in ("sol", "grok") for i in range(1, 1555)]
        manifest = {"stories": stories, "sentinels": stories[:9], "requests": rows,
                    "pairs": [{"left": f"s{3*p+a}", "right": f"s{3*p+b}", "plot": p, "id": f"p{p}_{a}_{b}"}
                              for p in range(12) for a, b in [(0, 1), (0, 2), (1, 2)]],
                    "repeat_pair_ids": [], "runtime": {"question_ids": [f"q{i}" for i in range(178)]}}
        joined = {(r["endpoint"], r["logical_sample_id"]): {
            "request": r, "state": "ambiguous", "accepted": None, "terminal_evidence_verified": True,
            "source_index": int(r["endpoint"] == "grok")} for r in rows}
        row = rows[0]
        vote = {"request": row, "abstention": False, "response": {"verdicts": [
            {"test_id": f"ttcw-{i:02d}", "verdict": "YES"} for i in range(1, 15)]}}
        joined[("sol", row["logical_sample_id"])].update(
            state="accepted", accepted=vote, native_evidence_verified=True, qualified_startup_command_verified=True)
        endpoints = {"sol": {row["logical_sample_id"]: vote}, "grok": {}}
        sample = Path(directory) / f"0001-{row['logical_sample_id'][:12]}"
        sample.mkdir()
        (sample / "attempt-started.json").write_text(json.dumps({"time": "2026-10-08T00:00:01+00:00"}))
        config = {"sources": [{"endpoint": ep, "results_root": directory} for ep in ("sol", "grok")]}
        targets = {s["id"]: i % 3 for i, s in enumerate(stories)}
        ballots = {"s0": {i: ["YES", "NO", "YES"] for i in range(1, 15)}}
        hbq = {"provenance": {"synthetic": True}}

        def labels_loader(path, actual_manifest):
            self.calls["labels"] += 1
            self.assertIs(actual_manifest, manifest)
            return targets, ballots

        def hbq_loader(actual_manifest):
            self.calls["hbq"] += 1
            self.assertIs(actual_manifest, manifest)
            return hbq

        # Only hypothetical lifecycle verification is substituted. The real
        # v5/v4/v3 release functions, full-slot gate and base handoff all run.
        def lifecycle(specification):
            self.calls["lifecycle"] += 1
            if lifecycle_error:
                raise ValueError("Invented lifecycle denied")
            return {"endpoint": specification["endpoint"], "synthetic": True}, v3.timestamp("2026-10-08T00:00:00+00:00"), v3.timestamp("2026-10-08T00:00:02+00:00")

        private_v3 = private_module(v3, release_labels=FunctionType(v3.release_labels.__code__,
            {**v3.release_labels.__globals__, "verify_lifecycle": lifecycle}))
        base = private_module(analysis, load_labels=labels_loader, load_hbq=hbq_loader)
        loaded = {"analysis": base, "analysis_v3": private_v3, "analysis_v4": v4}
        return config, {"labels_opened": False}, joined, endpoints, manifest, loaded, chain, Path("invented-labels-unopened")

    def assert_closed(self):
        self.assertEqual(self.calls["labels"], 0)
        self.assertEqual(self.calls["hbq"], 0)
        self.assertEqual(self.calls["analysis"], 0)

    def test_denied_qualification_and_terminal_coverage_never_reach_labels(self):
        with scratch() as directory:
            args = self.inputs(directory)
            with self.assertRaises(ValueError):
                release.release_labels(*args)
            self.assert_closed()
            joined, endpoints = args[2:4]
            key = ("sol", "sol-0001")
            record = joined[key]
            for field in ("terminal_evidence_verified", "native_evidence_verified", "qualified_startup_command_verified"):
                for bad in (None, False, 1):
                    before = record.pop(field)
                    if bad is not None:
                        record[field] = bad
                    with self.assertRaises(ValueError):
                        release.release_labels(*args, explicit_release=True)
                    record[field] = before
                    self.assert_closed()
            for invalid_index in (None, False, -1, 2, 999, 1):
                record["source_index"] = invalid_index
                with self.assertRaises(ValueError):
                    release.release_labels(*args, explicit_release=True)
                self.assert_closed()
            record["source_index"] = 0
            before = joined.pop(key)
            with self.assertRaises(ValueError):
                release.release_labels(*args, explicit_release=True)
            joined[key] = before
            endpoints["grok"]["foreign"] = record["accepted"]
            with self.assertRaises(ValueError):
                release.release_labels(*args, explicit_release=True)
            endpoints["grok"].clear()
            record["state"] = "definitely_not_contacted"
            record["accepted"] = None
            endpoints["sol"].clear()
            with self.assertRaises(ValueError):
                release.release_labels(*args, explicit_release=True)
            self.assert_closed()
            self.assertEqual(self.calls["lifecycle"], 0)

    def test_real_release_chain_keeps_labels_closed_on_lifecycle_failure(self):
        with scratch() as directory:
            args = self.inputs(directory, lifecycle_error=True)
            with self.assertRaisesRegex(ValueError, "Invented lifecycle denied"):
                release.release_labels(*args, explicit_release=True)
            self.assertEqual(self.calls["lifecycle"], 1)
            self.assert_closed()

    def test_composed_handoff_uses_real_analyzer_and_preserves_existing_fields(self):
        with scratch() as directory:
            args = self.inputs(directory)
            config, report, joined, endpoints, manifest, loaded, _, _ = args
            before = copy.deepcopy((config, report, joined, endpoints, manifest))
            bindings = (analysis.analyze, chain.release_labels, v3.release_labels, v4.release_labels, loaded["analysis"])
            original_analyze = release.measurements.analyze

            def counted(*positional, **keywords):
                self.calls["analysis"] += 1
                return original_analyze(*positional, **keywords)

            # Observe this call only; the extension and frozen analyzer still run.
            release.measurements.analyze = counted
            try:
                result = release.release_labels(*args, explicit_release=True)
            finally:
                release.measurements.analyze = original_analyze
            self.assertEqual(self.calls, {"labels": 1, "hbq": 1, "analysis": 1, "lifecycle": 2})
            self.assertEqual((config, report, joined, endpoints, manifest), before)
            self.assertEqual((analysis.analyze, chain.release_labels, v3.release_labels, v4.release_labels, loaded["analysis"]), bindings)
            targets = {s["id"]: i % 3 for i, s in enumerate(manifest["stories"])}
            ballots = {"s0": {i: ["YES", "NO", "YES"] for i in range(1, 15)}}
            expected = analysis.analyze(manifest, targets, ballots, endpoints, {"provenance": {"synthetic": True}}, reps=2000)
            measured = copy.deepcopy(result["endpoints"])
            for endpoint in measured.values():
                endpoint.pop("measurement_extension")
                for arm in endpoint["arms"].values():
                    if "score_distribution" in arm:
                        arm["score_distribution"].pop("scalar_extremes_v1")
                    if "repeatability" in arm:
                        arm["repeatability"].pop("four_state_transitions_v1", None)
            self.assertEqual(measured, expected)
            self.assertTrue(result["own_lifecycles_verified"])
            self.assertFalse(result["measurement_release_extension"]["contemporary_builder_supplied"])
            self.assertFalse(result["measurement_release_extension"]["promotion_established"])


if __name__ == "__main__":
    unittest.main()
