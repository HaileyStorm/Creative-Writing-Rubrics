"""Prediction-only scoring and sealed-label boundaries, with synthetic responses."""
import copy
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('lamp_analysis_test', REPO / 'evaluation-results/hbq-matched-lamp-20261004/analysis.py')
a = importlib.util.module_from_spec(spec); spec.loader.exec_module(a)
sys.path.insert(0, str(REPO / 'src'))
from hbqrs import core, runner, scoring_v2


class LampAnalysisTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        modules = core.load_modules(REPO / 'registry/all_modules.yaml')
        bundle = core.resolve_bundle(core.load_bundles(REPO / 'bundles/all_bundles.yaml'), 'prose.short_form')
        compiled = core.compile_bundle(modules, bundle)
        cls.questions = core.compiled_questions(compiled)
        cls.compiled_raw = a.c.canonical(compiled)
        cls.hbq = {'core': core, 'runner': runner, 'scorer': scoring_v2, 'modules': modules, 'bundle': bundle,
                   'ids': [q['question']['id'] for q in cls.questions]}

    def bank(self, state='YES'):
        planned, records = [], []
        for n in range(22):
            questions = self.questions[n*8:n*8+8]
            row = {'batch': n+1, 'logical_sample_id': 'logical-' + str(n), 'artifact_id': 's', 'bundle_id': 'prose.short_form',
                'endpoint': 'sol', 'question_ids': [q['question']['id'] for q in questions], 'compiled_sha256': a.c.digest(self.compiled_raw),
                'sources': [{'id': 's'}], 'task_contracts': [{'path': 'task.json'}]}
            planned.append(row)
            leaves = []
            for q in questions:
                evidence = [{'kind': 'exact_quote', 'reference': 'synthetic passage '+str(i), 'exact_quote': 'fixture', 'summary': None}
                            for i in range(max(1, q['question'].get('evidence_policy', {}).get('minimum_references', 0)))]
                leaves.append({'question_id': q['question']['id'], 'verdict': state, 'confidence': .5, 'evidence': evidence,
                               'note': 'Synthetic test evidence only.'})
            records.append({'request': row, 'response': {'verdicts': leaves}})
        return planned, records

    def test_incomplete_or_duplicate_full_bank_cannot_reach_scorer(self):
        planned, records = self.bank()
        with patch.object(scoring_v2, 'score_bundle', side_effect=AssertionError('Incomplete bank scored')):
            missing = a.score_bank(planned, records[:-1], self.hbq, Path('unused'), {})
            self.assertIsNone(missing['score']); self.assertEqual(missing['coverage']['expected_leaves'], 170)
            duplicate = copy.deepcopy(records)
            duplicate[-1]['response']['verdicts'][-1]['question_id'] = duplicate[0]['response']['verdicts'][0]['question_id']
            self.assertIsNone(a.score_bank(planned, duplicate, self.hbq, Path('unused'), {})['score'])

    def test_complete_bank_uses_current_strict_scorer_and_retains_provisional(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); task = a.c.canonical(a.c.p.task_contract('s')); (root / 'task.json').write_bytes(task)
            manifest = {'artifacts': {'task.json': {'sha256': a.c.digest(task), 'bytes': len(task)},
                                     'compiled.json': {'sha256': a.c.digest(self.compiled_raw)}}}
            source = (b'', b'', {'s': 'fixture'}, 'fixture')
            with patch.object(a.c, 'inputs', return_value=source):
                for state in ('YES', 'CANNOT_ASSESS'):
                    planned, records = self.bank(state)
                    original = copy.deepcopy(records)
                    report = a.score_bank(planned, records, self.hbq, root, manifest)
                    self.assertEqual(records, original)
                    self.assertEqual(report['report_version'], 2)
                    self.assertEqual(report['coverage']['native_leaves'], 170)
                    if state == 'YES': self.assertEqual(report['score'], 100)
                    else:
                        self.assertEqual(report['state'], 'PROVISIONAL'); self.assertIsNone(report['score'])
                        self.assertEqual(report['weighted_coverage'], 0)
                        self.assertEqual(report['coverage']['states']['CANNOT_ASSESS'], 170)

    def test_labels_stay_closed_and_explicit_release_uses_unchanged_native_gate(self):
        args = ({}, Path('unused'), 'm', Path('unused'), {}, None, None, None)
        with patch.object(a, 'load_human_orders', side_effect=AssertionError('Human ranks decoded before gate')), \
             patch.object(a.c, 'label_release_gate', side_effect=AssertionError('Gate called before explicit release')):
            self.assertEqual(a.human_alignment(*args, False)['state'], 'sealed_skipped_before_decode')
        with patch.object(a, 'load_human_orders', side_effect=AssertionError('Human ranks decoded before gate')), \
             patch.object(a.c, 'label_release_gate', return_value={'human_release_eligible': False}) as gate:
            with self.assertRaisesRegex(ValueError, 'all17808'): a.human_alignment(*args, True)
            gate.assert_called_once_with(*args, True)
        with patch.object(a.c, 'label_release_gate', return_value={'human_release_eligible': True}), \
             patch.object(a, 'load_human_profile', return_value={'targets': []}), \
             patch.object(a, 'load_human_orders', return_value=['synthetic only']) as loader, \
             patch.object(a, 'human_metrics', return_value={'synthetic': True}):
            with self.assertRaisesRegex(ValueError, 'exact control root'): a.human_alignment(*args, True)
            loader.assert_not_called()
            report = a.human_alignment(*args, True, control=Path('synthetic'), banks={}, records=[])
            self.assertTrue(report['human_targets_opened']); self.assertTrue(report['synthetic'])
            loader.assert_called_once()

    def test_rank_decoder_requires_admitted_exact_permutations_and_preserves_assessor_reuse(self):
        receipt = {'groups_key': 'groups', 'groups': 1, 'assessor_orders': 3}
        bridge = {'old-group': {'id': 'new-group', 'variants': {'old-a': 'a', 'old-b': 'b', 'old-c': 'c'}}}
        document = {'schema_version': 1, 'groups': [{'id': 'old-group', 'assessors': {
            'source-'+str(n): {'instruction_id_local_only': 17, 'ordered_variant_ids_local_only': rank}
            for n, rank in enumerate([['old-a', 'old-b', 'old-c'], ['old-b', 'old-a', 'old-c'], ['old-a', 'old-c', 'old-b']])}}]}
        orders = a.decode_rankings(document, receipt, bridge)
        self.assertEqual(orders[0]['order'], ['a', 'b', 'c'])
        self.assertEqual(orders[1]['source_assessor_id'], 'source-1')
        for rank in (['old-a', 'old-a', 'old-c'], ['old-a', 'old-b', 'excluded']):
            invalid = copy.deepcopy(document)
            invalid['groups'][0]['assessors']['source-0']['ordered_variant_ids_local_only'] = rank
            with self.assertRaisesRegex(ValueError, 'permutation'): a.decode_rankings(invalid, receipt, bridge)
        invalid = copy.deepcopy(document); invalid['groups'][0]['id'] = 'excluded-group'
        with self.assertRaisesRegex(ValueError, 'admitted membership'): a.decode_rankings(invalid, receipt, bridge)

    def test_human_pair_arithmetic_keeps_majority_individual_ties_and_missing_denominators(self):
        manifest = {'selection': {'groups': [{'id': 'g'+str(n)} for n in range(94)], 'pairs': [
            {'pair_id': 'ab', 'group_id': 'g0', 'left': 'a', 'right': 'b'},
            {'pair_id': 'ac', 'group_id': 'g0', 'left': 'a', 'right': 'c'},
            {'pair_id': 'bc', 'group_id': 'g0', 'left': 'b', 'right': 'c'}]}}
        orders = [{'group_id': 'g0', 'source_assessor_id': 'r'+str(n), 'order': rank}
                  for n, rank in enumerate([['a', 'b', 'c'], ['b', 'a', 'c'], ['a', 'c', 'b']])]
        ballots = a.human_ballots(manifest, orders)
        self.assertEqual([v for _, v in ballots['ab']], [1, -1, 1])
        report, complete, _ = a.human_direction_metrics(manifest, ballots, {'ab': 1, 'ac': 0}, 10)
        self.assertEqual(report['majority_pairs']['complete_case_half_tie_credit_agreement'], .75)
        self.assertEqual(report['individual_correlated_pair_ballots']['observed'], 6)
        self.assertAlmostEqual(report['individual_correlated_pair_ballots']['complete_case_half_tie_credit_agreement'], 3.5/6)
        self.assertEqual(report['majority_pairs']['all_planned_agreement_bounds'], [1.5/282, 281.5/282])
        self.assertEqual(report['model_zero_directions'], 1); self.assertEqual(complete, {})
        self.assertEqual(report['state'], 'inconclusive_source_group_loss')
        full = {'selection': {'groups': [], 'pairs': []}}; full_orders = []; banks = {}; records = []
        for n in range(94):
            gid = 'g'+str(n); ids = [gid+v for v in 'abc']
            full['selection']['groups'].append({'id': gid})
            for r, ordering in enumerate((ids, [ids[1], ids[0], ids[2]], [ids[0], ids[2], ids[1]])):
                full_orders.append({'group_id': gid, 'source_assessor_id': 'r'+str((n+r)%11), 'order': ordering})
            for ep in ('sol', 'grok'):
                banks.update({(ep, 'holistic', aid, 0): {'score': 3-i} for i, aid in enumerate(ids)})
            for i, j in ((0, 1), (0, 2), (1, 2)):
                pid = gid+str(i)+str(j)
                full['selection']['pairs'].append({'pair_id': pid, 'group_id': gid, 'left': ids[i], 'right': ids[j]})
                for ep in ('sol', 'grok'):
                    for orientation, ordered in (('AB', [ids[i], ids[j]]), ('BA', [ids[j], ids[i]])):
                        records.append({'request': {'endpoint': ep, 'arm': 'pairwise', 'repeat': 0, 'pair_id': pid,
                            'orientation': orientation, 'sources': [{'id': aid, 'side': side} for side, aid in zip('AB', ordered)]},
                            'response': {'winner': 'A' if ep == 'sol' else 'TIE'}})
        metrics = a.human_metrics(full, full_orders, banks, records, 1)
        holistic = metrics['arms']['sol:holistic']
        self.assertEqual(holistic['majority_pairs']['complete_case_half_tie_credit_agreement'], 1)
        self.assertAlmostEqual(holistic['individual_correlated_pair_ballots']['complete_case_half_tie_credit_agreement'], 7/9)
        self.assertEqual(holistic['triplet_bootstrap']['percentile_95'], [1, 1])
        self.assertEqual(metrics['arms']['sol:pairwise']['majority_pairs']['complete_case_half_tie_credit_agreement'], .5)
        self.assertEqual(metrics['arms']['sol:pairwise']['native_order_consensus_kinds']['zero_consensus_with_order_conflict'], 282)
        self.assertEqual(metrics['arms']['sol:pairwise']['native_order_consensus_kinds']['two_native_ties'], 0)
        self.assertEqual(metrics['arms']['grok:pairwise']['native_order_consensus_kinds']['two_native_ties'], 282)

    def test_pair_orientation_is_canonicalized_without_global_ranking_or_fake_tie(self):
        manifest = {'selection': {'pairs': [{'pair_id': 'p', 'group_id': 'g', 'left': 'left', 'right': 'right'}], 'sentinel_group_ids': []}}
        records = []
        for orientation, sources in [('AB', ['left', 'right']), ('BA', ['right', 'left'])]:
            records.append({'request': {'endpoint': 'sol', 'arm': 'pairwise', 'pair_id': 'p', 'repeat': 0,
                'orientation': orientation, 'sources': [{'id': v, 'side': side} for v, side in zip(sources, 'AB')]}, 'response': {'winner': 'A'}})
        report = a.pair_diagnostics(manifest, records)['sol']
        self.assertEqual(report['order_disagreements'], 1); self.assertEqual(report['mean_AB_minus_BA_canonical_left_preference'], 1)
        self.assertEqual(report['native_initial_winner_states'], {'A': 2})
        self.assertEqual(report['consensus_ties_including_order_conflicts'], 1); self.assertFalse(report['global_pair_graph_ranking'])

    def test_four_states_missingness_and_triplet_bootstrap_preserve_units(self):
        report = a.transitions({'s': {'q1': 'YES', 'q2': 'CANNOT_ASSESS', 'q3': 'NO'}},
            {'s': {'q1': 'NO', 'q2': 'NOT_APPLICABLE'}}, ['s'])
        self.assertEqual(report['observed_pairs'], 2)
        self.assertEqual(report['four_state_counts'], {'YES->NO': 1, 'CANNOT_ASSESS->NOT_APPLICABLE': 1})
        self.assertEqual(report['not_applicable_activation_flips'], 1)
        groups = [str(n) for n in range(94)]
        values = {g: 0 for g in groups}
        self.assertEqual(a.triplet_bootstrap(values, groups, 10)['percentile_95'], [0, 0])
        del values[groups[-1]]
        self.assertEqual(a.triplet_bootstrap(values, groups, 10)['state'], 'not_estimated')
        self.assertEqual(a.distribution([1, 4, 7], 'holistic')['affine_mean'], 50)

    def test_within_triplet_rank_ties_and_cross_endpoint_order_conflict_stay_distinct(self):
        manifest = {'selection': {'pairs': [
            {'pair_id': 'p1', 'group_id': 'g', 'left': 'a', 'right': 'b'},
            {'pair_id': 'p2', 'group_id': 'g', 'left': 'a', 'right': 'c'},
            {'pair_id': 'p3', 'group_id': 'g', 'left': 'b', 'right': 'c'}], 'sentinel_group_ids': []}}
        profiles = {(ep, 'holistic', aid, 0): {'score': value}
                    for ep, values in [('sol', {'a': 3, 'b': 2, 'c': 2}), ('grok', {'a': 1, 'b': 2, 'c': 2})]
                    for aid, value in values.items()}
        rank = a.within_triplet_rank(manifest, profiles, 'holistic')
        self.assertEqual(rank['within_triplet_kendall_tau_b'], -1)
        self.assertEqual(rank['direction_counts']['both_ties'], 1)
        self.assertEqual(rank['complete_case_exact_direction_agreement'], 1/3)
        self.assertEqual(rank['unresolved_pairs'], 279)
        self.assertEqual(rank['full_denominator_exact_direction_agreement_bounds'], [1/282, 280/282])
        records = []
        for ep in ('sol', 'grok'):
            for orientation, ids in [('AB', ['a', 'b']), ('BA', ['b', 'a'])]:
                records.append({'request': {'endpoint': ep, 'arm': 'pairwise', 'pair_id': 'p1', 'repeat': 0,
                    'orientation': orientation, 'sources': [{'id': v, 'side': side} for v, side in zip(ids, 'AB')]},
                    'response': {'winner': 'A' if ep == 'sol' else 'TIE'}})
        cross = a.pair_diagnostics(manifest, records)['cross_endpoint']
        self.assertEqual(cross['same_order']['disagreements'], 2)
        self.assertEqual(cross['same_order']['one_native_tie'], 2)
        self.assertEqual(cross['AB_BA_consensus']['exact_agreements'], 1)
        self.assertEqual(cross['AB_BA_consensus']['equal_consensus_with_any_order_conflict'], 1)
        self.assertEqual(cross['AB_BA_consensus']['both_endpoints_two_native_ties'], 0)


if __name__ == '__main__': unittest.main()
