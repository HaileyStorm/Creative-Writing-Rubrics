"""Independent math/uncertainty proofs; no provider or private-file writes."""
from __future__ import annotations

import unittest
import copy
import sys
from unittest.mock import patch

import analysis


class AnalysisTests(unittest.TestCase):
    def test_tied_ranks_constant_and_missingness_bounds(self) -> None:
        self.assertEqual(analysis.ranks([3, 1, 1, 2]), [4, 1.5, 1.5, 3])
        self.assertAlmostEqual(analysis.rho([3, 1, 1, 2], [30, 10, 10, 20]), 1)
        self.assertIsNone(analysis.rho([1, 1, 1], [1, 2, 3]))
        metric = analysis.bounded_agreement(2.5, 4, 10)
        self.assertEqual(metric["fraction"], .625)
        self.assertEqual(metric["full_denominator_bounds"], [.25, .85])
        self.assertEqual(metric["state"], "inconclusive_missing_over_10_percent")
        self.assertEqual(analysis.bounded_agreement(0, 0, 0)["state"], "undefined_no_informative_denominator")

    def test_plot_resampling_is_clustered_deterministic_and_retains_undefined(self) -> None:
        rows = [(plot, value) for plot in range(12) for value in range(3)]
        observed_cluster_sizes = []

        def statistic(sample):
            self.assertEqual(len(sample), 36)
            counts = {plot: sum(row[0] == plot for row in sample) for plot in range(12)}
            self.assertTrue(all(count % 3 == 0 for count in counts.values()))
            observed_cluster_sizes.append(counts)
            return None

        result = analysis.cluster_bootstrap(rows, statistic, reps=31)
        self.assertEqual(result["undefined_replicates"], 31)
        self.assertEqual(result["defined_replicates"], 0)
        self.assertFalse(result["redraw_undefined"])
        self.assertEqual(len(observed_cluster_sizes), 31)
        self.assertEqual(analysis.cluster_bootstrap(rows, lambda rs: sum(r[0] for r in rs) / len(rs), 31),
                         analysis.cluster_bootstrap(rows, lambda rs: sum(r[0] for r in rs) / len(rs), 31))
        self.assertEqual(analysis.cluster_bootstrap(rows[:3], lambda rs: 1, 31)["state"], "not_estimated")

    def test_ttcw_abstention_does_not_become_no_or_a_complete_score(self) -> None:
        rows = [{"test_id": f"ttcw-{i:02d}", "verdict": "YES" if i == 1 else "CANNOT_ASSESS"} for i in range(1, 15)]
        profile = analysis.score_story("ttcw14", [{"response": {"verdicts": rows}}], {})
        self.assertIsNone(profile["score"])
        self.assertEqual(profile["coverage"]["assessed_binary"], 1)
        ballots = {"s": {i: ["YES", "NO", "YES"] for i in range(1, 15)}}
        result = analysis.ttcw_agreement({"s": profile}, ballots, {"s": 0}, 10)
        self.assertEqual(result["expert_majority"]["assessed_denominator"], 1)
        self.assertEqual(result["expert_majority"]["matches"], 1)
        self.assertEqual(result["individual_ballots"]["assessed_denominator"], 3)
        self.assertEqual(result["individual_ballots"]["matches"], 2)
        self.assertEqual(result["expert_majority"]["unassessed"], 503)

    def test_hbq_missing_packets_never_calls_scorer(self) -> None:
        class Forbidden:
            def score_bundle(self, *args, **kwargs):
                raise AssertionError("Scorer must not receive incomplete native evidence")

        result = analysis.score_story("hbq", [], {"core": Forbidden(), "questions": []})
        self.assertIsNone(result["score"])
        self.assertEqual(result["state"], "incomplete_native_packets_no_score")
        self.assertEqual(result["coverage"]["native_leaves"], 0)

    def test_complete_hbq_wire_normalization_and_uncertainty_with_sealed_contract(self) -> None:
        sys.path.insert(0, str(analysis.REPO / "src"))
        from hbqrs import core
        modules = core.load_modules(analysis.REPO / "registry/all_modules.json")
        bundle = core.resolve_bundle(core.load_bundles(analysis.REPO / "bundles/all_bundles.json"), "prose.short_story")
        questions = sorted(core.compiled_questions(core.compile_bundle(modules, bundle)),
                           key=lambda q: {"hard_gate": 0, "domain": 1, "penalty": 2, "supplemental": 3}[q["role"]])
        ids = [q["question"]["id"] for q in questions]
        hbq = analysis.load_hbq({"runtime": {"question_ids": ids,
            "compiled_bundle_sha256": "f11f55e8263e3fcc8a2d4b9a00021cf34f0ba2acac843e530999d1ed845fe2f8",
            "question_payload_sha256": "d66c9a9e8471bb57d9ad80c4780349126464c177663b8dca012f44ff2ce52c11"}})
        for state in ("YES", "CANNOT_ASSESS"):
            records = []
            for batch, start in enumerate(range(0, 178, 8), 1):
                rows = [{"question_id": qid, "verdict": state, "confidence": 1.0, "note": "Explicit fixture state.",
                         "evidence": [{"reference": "fixture", "kind": "summary", "exact_quote": None,
                                       "summary": "Declared fixture evidence; not a model alignment claim."}]} for qid in ids[start:start + 8]]
                records.append({"request": {"artifact_id": "fixture", "batch": batch, "question_ids": ids[start:start + 8],
                                            "endpoint": "grok", "logical_sample_id": str(batch)}, "response": {"verdicts": rows}})
            before = copy.deepcopy(records)
            result = analysis.score_story("hbq", records, hbq)
            self.assertEqual(records, before)
            if state == "YES":
                self.assertEqual(result["state"], "SCORED")
                self.assertEqual(result["score"], 100)
            else:
                self.assertEqual(result["state"], "PROVISIONAL")
                self.assertIsNone(result["score"])
                self.assertEqual(result["uncertainty_bounds"], {"lower": 0.0, "observed": None, "upper": 100.0})
                self.assertEqual(result["coverage"]["states"], {"CANNOT_ASSESS": 178})

    def test_within_plot_tie_credit_and_expert_tie_exclusion(self) -> None:
        pairs = [{"left": "a", "right": "b", "plot": 0}, {"left": "a", "right": "c", "plot": 0},
                 {"left": "b", "right": "c", "plot": 0}]
        result = analysis.within_plot({"a": 5, "b": 5}, {"a": 3, "b": 2, "c": 2}, pairs, 10)
        self.assertEqual(result["expert_ties_excluded"], 1)
        self.assertEqual(result["expected_denominator"], 2)
        self.assertEqual(result["assessed_denominator"], 1)
        self.assertEqual(result["matches"], .5)
        self.assertEqual(result["full_denominator_bounds"], [.25, .75])

    def test_pair_order_reversal_is_separate_from_abstention_and_global_rank(self) -> None:
        pair = {"id": "p", "left": "a", "right": "b", "plot": 0}
        manifest = {"pairs": [pair], "repeat_pair_ids": ["p"]}
        # Choosing the displayed A in both orders reverses canonical direction.
        records = {str(order): {"request": {"arm": "pairwise", "pair_id": "p", "repeat": 0, "orientation": order},
                               "response": {"winner": "A"}} for order in (0, 1)}
        result = analysis.pairwise_analysis(records, manifest, {"a": 3, "b": 2}, 10)
        self.assertEqual(result["paired_order_opposite_direction_pairs"], 1)
        self.assertEqual(result["order_averaged_within_plot_agreement"]["consensus_ties"], 1)
        self.assertIsNone(result["global_rho"])
        records["1"]["response"]["winner"] = "CANNOT_ASSESS"
        result = analysis.pairwise_analysis(records, manifest, {"a": 3, "b": 2}, 10)
        self.assertEqual(result["paired_order_complete_pairs"], 0)
        self.assertEqual(result["all_collection_explicit_abstentions"], 1)

    def test_disjoint_continuation_preserves_gap_and_rejects_duplicate_attempt(self) -> None:
        original = ({"a": {"request": "a"}}, {"statuses": {"a": "accepted", "b": "terminal_unadmitted", "c": "not_collected"}, "public": {"job_sha256": "old"}})
        suffix = ({"c": {"request": "c"}}, {"statuses": {"c": "accepted"}, "public": {"job_sha256": "new"}})
        accepted, public = analysis.join_results([original, suffix], {"a", "b", "c"})
        self.assertEqual(set(accepted), {"a", "c"})
        self.assertEqual(public["scheduled"], 3)
        self.assertEqual(public["statuses"]["terminal_unadmitted"], 1)
        self.assertEqual(len(public["jobs"]), 2)
        repair = ({"b": {}}, {"statuses": {"b": "accepted"}, "public": {}})
        with self.assertRaises(ValueError):
            analysis.join_results([original, repair], {"a", "b", "c"})

    def test_continuation_keeps_exact_request_conditions(self) -> None:
        base = {key: {"frozen": key} for key in ("study_id", "source_pins", "runtime", "context", "implementation",
                "public_asset_hashes", "stories", "sentinels", "pairs", "repeat_pair_ids", "artifacts")}
        base["requests"] = [{"endpoint": "grok", "logical_sample_id": sid, "prompt_sha256": sid, "endpoint_ordinal": i}
                            for i, sid in enumerate(("a", "b"), 1)]
        derived = {**copy.deepcopy(base), "requests": [copy.deepcopy(base["requests"][1])], "transport_timeout_seconds": 900}
        derived["manifest_content_sha256"] = analysis.prepare.digest(analysis.prepare.canonical(derived))
        self.assertEqual(analysis.validate_continuation(derived, base, "grok"), {"b"})
        derived["requests"][0]["prompt_sha256"] = "changed"
        body = {k: v for k, v in derived.items() if k != "manifest_content_sha256"}
        derived["manifest_content_sha256"] = analysis.prepare.digest(analysis.prepare.canonical(body))
        with self.assertRaises(ValueError):
            analysis.validate_continuation(derived, base, "grok")

    def test_parent_lineage_addition_is_exact_and_other_artifacts_are_rejected(self) -> None:
        base = {key: {"frozen": key} for key in ("study_id", "source_pins", "runtime", "context", "implementation",
                "public_asset_hashes", "stories", "sentinels", "pairs", "repeat_pair_ids")}
        base["artifacts"] = {"input.txt": {"sha256": "original-input-pin", "bytes": 12}}
        base["requests"] = [{"endpoint": "grok", "logical_sample_id": "suffix", "prompt_sha256": "unchanged"}]
        raw = analysis.prepare.canonical(base)
        parent_sha = analysis.prepare.digest(raw)
        derived = copy.deepcopy(base)
        derived["artifacts"]["lineage/parent-manifest.json"] = {"sha256": parent_sha, "bytes": len(raw)}
        derived["continuation"] = {"parent_manifest_sha256": parent_sha}

        def freeze(value):
            body = {k: v for k, v in value.items() if k != "manifest_content_sha256"}
            value["manifest_content_sha256"] = analysis.prepare.digest(analysis.prepare.canonical(body))
            return value

        kwargs = {"base_raw": raw, "derived_root": analysis.HERE / "fixture-lineage"}
        with patch.object(analysis.prepare, "checked", return_value=raw):
            self.assertEqual(analysis.validate_continuation(freeze(derived), base, "grok", **kwargs), {"suffix"})
            for change in ("original_pin", "extra_artifact", "parent_commitment", "lineage_pin"):
                invalid = copy.deepcopy(derived)
                if change == "original_pin":
                    invalid["artifacts"]["input.txt"]["sha256"] = "changed"
                elif change == "extra_artifact":
                    invalid["artifacts"]["lineage/other.json"] = {"sha256": parent_sha, "bytes": len(raw)}
                elif change == "parent_commitment":
                    invalid["continuation"]["parent_manifest_sha256"] = "changed"
                else:
                    invalid["artifacts"]["lineage/parent-manifest.json"]["bytes"] += 1
                with self.assertRaises(ValueError, msg=change):
                    analysis.validate_continuation(freeze(invalid), base, "grok", **kwargs)
        with patch.object(analysis.prepare, "checked", return_value=b"changed lineage bytes"):
            with self.assertRaises(ValueError):
                analysis.validate_continuation(derived, base, "grok", **kwargs)


if __name__ == "__main__":
    unittest.main()
