"""Independent numerical and composed-runtime proofs using invented data only."""
import copy
import unittest

import analysis
import analysis_measurements_v1 as adapter
from measurement_diagnostics_v1 import leaf_repeat_transitions, scalar_extremes, state_transitions


class MeasurementTests(unittest.TestCase):
    def test_four_states_and_prevalence_distinguish_equal_raw_agreement(self):
        balanced = state_transitions([("YES", "YES"), ("NO", "NO"), ("YES", "NO"), ("NO", "YES")])
        skewed = state_transitions([("YES", "YES"), ("YES", "YES"), ("YES", "CANNOT_ASSESS"), ("NO", "YES")])
        self.assertEqual(balanced["raw_agreement"], skewed["raw_agreement"])
        self.assertEqual(balanced["marginal_expected_agreement"], .5)
        self.assertAlmostEqual(skewed["cohens_kappa"], -1 / 7)
        self.assertEqual(skewed["repeat_marginal_counts"]["CANNOT_ASSESS"], 1)
        crossed = state_transitions([("YES", "NO"), ("YES", "CANNOT_ASSESS"), ("NOT_APPLICABLE", "YES")])
        self.assertEqual(crossed["transition_counts"]["YES"]["NO"], 1)
        self.assertEqual(crossed["transition_counts"]["YES"]["CANNOT_ASSESS"], 1)
        self.assertEqual(sum(sum(row.values()) for row in crossed["transition_counts"].values()), 3)
        self.assertAlmostEqual(crossed["cohens_kappa"], -2 / 7)

    def test_absence_is_separate_and_degenerate_agreement_is_undefined(self):
        result = state_transitions([(None, "CANNOT_ASSESS"), ("NO", None), (None, None), ("YES", "YES")])
        self.assertEqual(result["observed_pairs"], 1)
        self.assertEqual(result["missing_positions"], {"initial_only_absent": 1, "repeat_only_absent": 1, "both_absent": 1})
        self.assertEqual(result["raw_agreement"], 1)
        self.assertIsNone(result["cohens_kappa"])
        self.assertEqual(result["undefined_reason"], "expected_agreement_one")
        self.assertEqual(state_transitions([])["undefined_reason"], "no_observed_pairs")
        with self.assertRaises(ValueError):
            state_transitions([("MISSING", "YES")])

    def test_complete_inventory_preserves_missing_cycles_and_rejects_duplicates(self):
        profiles = {("s", 0): {"leaves": [{"test_id": "a", "verdict": "YES"}]},
                    ("s", 1): {"leaves": [{"test_id": "a", "verdict": "CANNOT_ASSESS"}]}}
        result = leaf_repeat_transitions(profiles, {"s"}, ["a", "b"], "test_id")
        aggregate = result["aggregate_initial_vs_repeats"]
        self.assertEqual(aggregate["expected_positions"], 4)
        self.assertEqual(aggregate["observed_pairs"], 1)
        self.assertEqual(aggregate["missing_positions"]["repeat_only_absent"], 1)
        self.assertEqual(aggregate["missing_positions"]["both_absent"], 2)
        self.assertEqual(result["by_cycle"]["0_vs_2"]["observed_pairs"], 0)
        profiles[("s", 1)]["leaves"] *= 2
        with self.assertRaises(ValueError):
            leaf_repeat_transitions(profiles, {"s"}, ["a", "b"], "test_id")

    def test_every_native_scale_has_declared_boundaries_without_mutation(self):
        for bounds in [(0, 100), (0, 1), (1, 7), (1, 5), (6, 36)]:
            low, high = bounds
            values = [low, low + .1 * (high - low), (low + high) / 2, low + .9 * (high - low), high]
            before = values[:]
            result = scalar_extremes(values, bounds)
            self.assertEqual(result["counts"], {"exact_floor": 1, "exact_ceiling": 1, "mapped_at_or_below_10": 2, "mapped_at_or_above_90": 2})
            self.assertEqual(result["rates"]["exact_floor"], .2)
            self.assertEqual(values, before)
        empty = scalar_extremes([], (1, 7))
        self.assertTrue(all(value is None for value in empty["rates"].values()))
        for invalid in [[float("nan")], [float("inf")], [True], [-1], [101], [None]]:
            with self.assertRaises(ValueError):
                scalar_extremes(invalid, (0, 100))

    def test_actual_analyzer_composition_preserves_missingness_and_native_bindings(self):
        stories = [{"id": f"s{i}", "plot": i // 3} for i in range(36)]
        pairs = [{"left": f"s{3*p+a}", "right": f"s{3*p+b}", "plot": p, "id": f"p{p}_{a}_{b}"}
                 for p in range(12) for a, b in [(0, 1), (0, 2), (1, 2)]]
        manifest = {"stories": stories, "sentinels": stories[:9], "pairs": pairs, "requests": [],
                    "repeat_pair_ids": [], "runtime": {"question_ids": [f"q{i}" for i in range(178)]}}
        targets = {row["id"]: i % 3 for i, row in enumerate(stories)}
        endpoints = {"invented": {}}
        before = copy.deepcopy((manifest, targets, endpoints))
        original = (analysis.distribution, analysis.repeat_summary, analysis.analyze)
        result = adapter.analyze(analysis, manifest, targets, {}, endpoints, {"provenance": {"synthetic": True}}, reps=1)
        self.assertEqual((manifest, targets, endpoints), before)
        self.assertEqual((analysis.distribution, analysis.repeat_summary, analysis.analyze), original)
        for arm in analysis.prepare.ARM_ORDER:
            self.assertEqual(result["invented"]["arms"][arm]["score_distribution"]["scalar_extremes_v1"]["observed_score_denominator"], 0)
        transitions = result["invented"]["arms"]["hbq"]["repeatability"]["four_state_transitions_v1"]["aggregate_initial_vs_repeats"]
        self.assertEqual(transitions["expected_positions"], 3204)
        self.assertEqual(transitions["missing_positions"]["both_absent"], 3204)
        self.assertIsNone(transitions["cohens_kappa"])
        self.assertFalse(result["invented"]["measurement_extension"]["target_access_authorized"])

        # An invented observed repeat exercises the real score-to-profile path.
        admitted = {}
        for cycle, verdict in [(0, "YES"), (1, "NO")]:
            request = {"arm": "ttcw14", "story_id": "s0", "repeat": cycle, "endpoint": "invented"}
            admitted[str(cycle)] = {"request": request, "abstention": False,
                                    "response": {"verdicts": [{"test_id": f"ttcw-{i:02d}", "verdict": verdict} for i in range(1, 15)]}}
        manifest["requests"] = [record["request"] for record in admitted.values()]
        ballots = {"s0": {i: ["YES", "NO", "YES"] for i in range(1, 15)}}
        result = adapter.analyze(analysis, manifest, targets, ballots, {"invented": admitted}, {"provenance": {"synthetic": True}}, reps=1)
        scalar = result["invented"]["arms"]["ttcw14"]["score_distribution"]["scalar_extremes_v1"]
        self.assertEqual(scalar["counts"]["exact_ceiling"], 1)
        self.assertEqual(scalar["observed_score_denominator"], 1)
        states = result["invented"]["arms"]["ttcw14"]["repeatability"]["four_state_transitions_v1"]["aggregate_initial_vs_repeats"]
        self.assertEqual(states["transition_counts"]["YES"]["NO"], 14)
        self.assertEqual(states["observed_pairs"], 14)
        self.assertEqual(states["missing_positions"]["repeat_only_absent"], 14)
        self.assertEqual(states["missing_positions"]["both_absent"], 224)
        self.assertEqual((analysis.distribution, analysis.repeat_summary, analysis.analyze), original)


if __name__ == "__main__":
    unittest.main()
