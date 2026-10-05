"""Independent duplicate/independent-repeat and nonvoting declaration witnesses."""
import copy
import importlib.util
import json
from pathlib import Path
import unittest

PATH = Path(__file__).resolve().parents[1] / 'evaluation-results/hbq-disjoint-disposition-historical-census-v1/census.py'
SPEC = importlib.util.spec_from_file_location('test_disjoint_disposition_census_owned', PATH)
c = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(c)


class HistoricalCensusTests(unittest.TestCase):
    def test_duplicate_representations_are_one_observation_but_planned_repeats_distinct(self):
        raw = (b'{"run_id":"run1","question_id":"scope.passage.status","verdict":"YES",'
               b'"evidence":"\\uZZZZ","note":"\\uZZZZ","oracle":"\\uZZZZ"}')
        with self.assertRaises(json.JSONDecodeError):
            json.loads(raw)
        lexical = c.project_source('nonpoetry', 'runs/slot1/verdicts.jsonl', raw + b'\n')
        self.assertEqual(lexical, [{'run_id': 'run1', 'question_id': 'scope.passage.status', 'verdict': 'YES'}])
        run_raw = (b'{"run_id":"run1","config_sha256":"config",'
                   b'"configuration":{"question_ids":["scope.passage.status"],"artifact":"\\uZZZZ",'
                   b'"contexts":["\\uZZZZ"],"task_contract":{"prose":"\\uZZZZ"}}}')
        self.assertEqual(c.project_source('nonpoetry', 'runs/slot1/run.json', run_raw),
                         {'run_id': 'run1', 'config_sha256': 'config',
                          'configuration': {'question_ids': ['scope.passage.status']}})
        slot = {'slot_id': 'slot1', 'logical_sample_id': 'logical1', 'leaf_id': 'scope.passage.status', 'repeat': 1}
        row = {'question_id': 'scope.passage.status', 'verdict': 'YES',
               'evidence': ['sealed prose'], 'note': 'sealed note', 'oracle': 'sealed target'}
        representations = [[copy.deepcopy(row)] for _ in range(4)]
        first = c.singleton_observation(slot, 'run1', representations, {'checkpoint': {'sha256': 'same-bytes'}},
                                        scheduled_logical='different-runtime-logical')
        repeat = c.singleton_observation(dict(slot, slot_id='slot2', logical_sample_id='logical2', repeat=2),
                                         'run2', representations, {'checkpoint': {'sha256': 'same-bytes'}})
        self.assertEqual(first['representation_count'], 4)
        self.assertEqual(first['state'], 'YES')
        self.assertNotEqual(first['observation_identity_sha256'], repeat['observation_identity_sha256'])
        self.assertFalse(first['current_admission_verified'])
        self.assertFalse(first['manifest_runtime_logical_identity_matches'])
        self.assertNotEqual(first['logical_sample_identity_sha256'], first['runtime_schedule_logical_sample_identity_sha256'])
        self.assertIsNone(first['native_session_identity'])
        self.assertFalse(first['physical_contact_cardinality_proven'])
        self.assertEqual(first['new_votes'], 0)
        self.assertNotIn('sealed', json.dumps(first))
        self.assertNotIn('evidence', first)
        changed = copy.deepcopy(representations)
        changed[-1][0]['verdict'] = 'NO'
        with self.assertRaises(ValueError):
            c.singleton_observation(slot, 'run1', changed, {})
        with self.assertRaises(ValueError):
            c.singleton_observation(dict(slot, leaf_id='another.leaf'), 'run1', representations, {})

    def test_accepted_named_output_is_nonvoting_and_untouched_is_not_negative_contact_proof(self):
        ids = [f'slot{i}' for i in range(12)]
        declaration = {'planned_slots': 12, 'completed_slots': 0,
                       'historical_nonvoting_output_dispositions': 1, 'untouched_slots': 11}
        result = c.declared_population(ids, ['slot3'], declaration)
        occupied = next(item for item in result if item['kind'] == 'historical_output_disposition')
        occupied['accepted_named_message_sha256'] = 'same-legacy-message'
        self.assertEqual(occupied['disposition'], 'historical_nonvoting_semantic_output')
        self.assertEqual(sum(item['voting_leaf_observations'] for item in result), 0)
        self.assertEqual(sum(item['kind'] == 'inherited_untouched_declaration' for item in result), 11)
        self.assertTrue(all(item['native_contact_disposition'] == 'unresolved' for item in result))
        self.assertTrue(all(not item['current_admission_verified'] and item['new_votes'] == 0 for item in result))
        untouched = c.declared_population(ids, [], {'planned_slots': 12, 'completed_slots': 0,
                                                   'retained_output_dispositions': 0, 'untouched_slots': 12})
        self.assertEqual(len(untouched), 12)
        self.assertTrue(all(item['kind'] == 'inherited_untouched_declaration' for item in untouched))
        for planned, outputs, declared in [(ids + ['slot0'], ['slot3'], declaration),
                                          (ids, ['unknown'], declaration),
                                          (ids, ['slot3', 'slot3'], declaration),
                                          (ids, ['slot3'], dict(declaration, completed_slots=1))]:
            with self.assertRaises(ValueError):
                c.declared_population(planned, outputs, declared)


if __name__ == '__main__':
    unittest.main()
