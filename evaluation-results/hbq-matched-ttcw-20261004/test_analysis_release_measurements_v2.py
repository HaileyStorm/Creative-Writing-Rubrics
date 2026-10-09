"""Synthetic composition and denial checks; these fixtures prove no native return."""
import copy
from pathlib import Path
import unittest
from unittest.mock import patch

import analysis
import analysis_chain as chain
import analysis_chain_v3 as v3
import analysis_chain_v4 as v4
import analysis_release_measurements_v2 as bridge
import test_analysis_release_measurements_v1 as fixtures


class QualifiedCacheBridgeTests(unittest.TestCase):
    def test_serialized_membership_rejects_collision_substitution_and_omission(self):
        request = {"endpoint": "sol", "logical_sample_id": "synthetic-sol"}
        vote = {"request": request, "synthetic": True}
        record = {"request": request, "accepted": vote, "state": "accepted"}
        rows = [{"identity": ["sol", "synthetic-sol"], "record": record}]
        endpoints = {"sol": [vote], "grok": []}
        original = copy.deepcopy((rows, endpoints))
        joined, admitted = bridge.decode_join(rows, endpoints)
        self.assertEqual(admitted["sol"], {"synthetic-sol": vote})
        self.assertEqual(joined[("sol", "synthetic-sol")], record)
        self.assertEqual((rows, endpoints), original)
        variants = [(rows + rows, endpoints),
                    (rows, {"sol": [vote, vote], "grok": []}),
                    (rows, {"sol": [], "grok": []}),
                    ([{"identity": ["grok", "synthetic-sol"], "record": record}], endpoints),
                    (rows, {"sol": [], "grok": [vote]})]
        for changed_rows, changed_endpoints in variants:
            with self.subTest(rows=changed_rows[0]["identity"] if changed_rows else []):
                with self.assertRaises(ValueError):
                    bridge.decode_join(changed_rows, changed_endpoints)

    def test_full_chain_denials_precede_saved_inspection_and_target_loaders(self):
        helper = fixtures.ReleaseMeasurementsTests()
        with fixtures.scratch() as directory:
            args = helper.inputs(directory)
            with patch.object(bridge, "saved_lifecycle", side_effect=AssertionError("Inspector must stay closed")) as inspect:
                with self.assertRaises(ValueError):
                    bridge.release_labels(*args)
                key = ("sol", "sol-0001")
                removed = args[2].pop(key)
                with self.assertRaises(ValueError):
                    bridge.release_labels(*args, explicit_release=True)
                args[2][key] = removed
                removed["state"] = "definitely_not_contacted"
                removed["accepted"] = None
                args[3]["sol"].clear()
                with self.assertRaises(ValueError):
                    bridge.release_labels(*args, explicit_release=True)
                inspect.assert_not_called()
                self.assertEqual(helper.calls, {"labels": 0, "hbq": 0, "analysis": 0, "lifecycle": 0})
        with fixtures.scratch() as directory:
            args = helper.inputs(directory)
            args[0]["sources"][0]["proof_profile"] = "saved_owned_sol_unregistered"
            with self.assertRaisesRegex(ValueError, "Unknown saved lifecycle profile"):
                bridge.release_labels(*args, explicit_release=True)
            self.assertEqual(helper.calls["labels"], 0)
            self.assertEqual(helper.calls["hbq"], 0)
            self.assertEqual(helper.calls["lifecycle"], 0)
        with fixtures.scratch() as directory:
            args = helper.inputs(directory)
            args[0]["sources"] = args[0]["sources"][:1]
            with self.assertRaisesRegex(ValueError, "Both own endpoint lifecycles required"):
                bridge.release_labels(*args, explicit_release=True)
            self.assertEqual(helper.calls["lifecycle"], 1)
            self.assertEqual(helper.calls["labels"], 0)
            self.assertEqual(helper.calls["hbq"], 0)

    def test_private_binding_traverses_frozen_release_and_actual_measurements(self):
        helper = fixtures.ReleaseMeasurementsTests()
        with fixtures.scratch() as directory:
            args = helper.inputs(directory)
            source = args[0]["sources"][0]
            source["proof_profile"] = "saved_owned_sol_005_strict_v1"
            args[0]["source_specifications_path"] = "synthetic-registry-unopened"
            before = copy.deepcopy(args[:5])
            bindings = (analysis.analyze, chain.release_labels, v3.release_labels,
                        v3.verify_lifecycle, v4.release_labels, bridge.previous.release_labels)
            # Exercise the new registered dispatch while keeping native proof
            # explicitly synthetic. Grok still traverses the historical fallback.
            returned = ({"endpoint": "sol", "synthetic": True, "exit_code": 5},
                        v3.timestamp("2026-10-08T00:00:00+00:00"),
                        v3.timestamp("2026-10-08T00:00:02+00:00"))
            with patch.object(bridge, "registered_specifications", return_value={"sources": [source]}) as registry:
                with patch.object(bridge, "saved_lifecycle", return_value=returned) as inspect:
                    result = bridge.release_labels(*args, explicit_release=True)
                    registry.assert_called_once_with("synthetic-registry-unopened")
                    inspect.assert_called_once_with(source, source)
            self.assertEqual(helper.calls["labels"], 1)
            self.assertEqual(helper.calls["hbq"], 1)
            self.assertEqual(helper.calls["lifecycle"], 1)
            self.assertEqual(args[:5], before)
            self.assertEqual((analysis.analyze, chain.release_labels, v3.release_labels,
                              v3.verify_lifecycle, v4.release_labels, bridge.previous.release_labels), bindings)
            self.assertTrue(result["own_lifecycles_verified"])
            self.assertFalse(result["qualified_cache_release_bridge"]["arbitrary_exit5_allowed"])
            self.assertFalse(result["qualified_cache_release_bridge"]["promotion_established"])
            self.assertIn("measurement_extension", result["endpoints"]["sol"])
            before_failure = dict(helper.calls)
            with patch.object(bridge, "registered_specifications", return_value={"sources": [source]}):
                with patch.object(bridge, "saved_lifecycle", side_effect=ValueError("Synthetic saved verifier denied")) as inspect:
                    with self.assertRaisesRegex(ValueError, "Synthetic saved verifier denied"):
                        bridge.release_labels(*args, explicit_release=True)
                    inspect.assert_called_once_with(source, source)
            self.assertEqual(helper.calls, before_failure)

    def proof_fixture(self, profile):
        """Invent metadata for a pure contract check; never call an inspector."""
        _, _, exit_code, first, _, count = bridge.PROFILES[profile]
        pins = {role: {"sha256": role + "-synthetic-pin"}
                for role in ("invocation", "outer_terminal", "run_started")}
        specification = {"proof_profile": profile, "lifecycle": pins,
                         "manifest_sha256": "synthetic-manifest", "job_sha256": "synthetic-job",
                         "recorded_beginning": "2026-10-08T00:00:00+00:00",
                         "recorded_ending": "2026-10-08T00:01:00+00:00"}
        rows = [{"endpoint": "sol", "endpoint_ordinal": ordinal,
                 "logical_sample_id": f"synthetic-{ordinal}"} for ordinal in range(first, 1555)]
        counts = {"accepted": count, "semantic_rejected": 0, "unadmitted_no_resend": 0}
        inspected = {"state": "VERIFIED_OWNED_LOCAL_RETURN_REPLAY_REQUIRED",
                     "source_lifecycle_verified": True, "exit_code": exit_code,
                     "original_denominator": 3108, "sample_bodies_read": 0,
                     "accepted_votes_admitted": 0, "labels_opened": False,
                     "remote_or_billing_quiescence_proven": False, "full_label_release_gate_passed": False,
                     "invocation_sha256": pins["invocation"]["sha256"],
                     "outer_terminal_sha256": pins["outer_terminal"]["sha256"],
                     "manifest_sha256": specification["manifest_sha256"], "rows": rows,
                     "declared_terminal_counts": counts}
        job = {"endpoint": "sol", "manifest_sha256": specification["manifest_sha256"]}
        started = {"started_utc": specification["recorded_beginning"]}
        outer = {"completed_utc": specification["recorded_ending"], "exit_code": exit_code,
                 "native_exit_confirmed": True, "no_resend": True,
                 "invocation_sha256": pins["invocation"]["sha256"], "terminal_counts": counts}
        return specification, inspected, {"requests": rows}, job, started, outer

    def test_saved_profiles_bind_exit_proof_scope_and_aware_chronology(self):
        for profile in bridge.PROFILES:
            args = self.proof_fixture(profile)
            proof, beginning, ending = bridge.verify_saved_return(*args)
            self.assertEqual(proof["exit_code"], bridge.PROFILES[profile][2])
            self.assertLessEqual(beginning, ending)
            self.assertFalse(proof["physical_remote_settlement_proven"])
            self.assertNotIn("rows", proof)
            variations = [(1, "state", "HELD_AWAITING_OWNED_LOCAL_RETURN"),
                          (1, "source_lifecycle_verified", 1),
                          (1, "outer_terminal_sha256", "other-outer"),
                          (1, "invocation_sha256", "other-invocation"),
                          (1, "accepted_votes_admitted", False),
                          (1, "labels_opened", True),
                          (1, "exit_code", 0),
                          (4, "started_utc", "2026-10-08T00:00:00"),
                          (5, "completed_utc", "2026-10-07T23:59:00+00:00")]
            if bridge.PROFILES[profile][2] != 5:
                variations.append((1, "exit_code", 5))
            for index, field, value in variations:
                changed = copy.deepcopy(args)
                changed[index][field] = value
                with self.subTest(profile=profile, field=field):
                    with self.assertRaises(ValueError):
                        bridge.verify_saved_return(*changed)
            changed = copy.deepcopy(args)
            changed[1]["rows"].pop()
            with self.assertRaises(ValueError):
                bridge.verify_saved_return(*changed)

    def test_substituted_saved_code_and_root_are_denied_before_execution(self):
        profile = "saved_owned_sol_005_strict_v1"
        name, digest, *_ = bridge.PROFILES[profile]
        registered = {"proof_profile": profile, "results_root": "registered-root",
                      "lifecycle_verifier": {"path": name, "sha256": digest}}
        for replacement in ("foreign-root", "changed-code"):
            actual = copy.deepcopy(registered)
            if replacement == "foreign-root":
                actual["results_root"] = replacement
            else:
                actual["lifecycle_verifier"]["sha256"] = replacement
            with patch.object(bridge, "checked", side_effect=AssertionError("No code read permitted")) as read:
                with self.assertRaisesRegex(ValueError, "Saved source specification substituted"):
                    bridge.saved_lifecycle(actual, registered)
                read.assert_not_called()


if __name__ == "__main__":
    unittest.main()
