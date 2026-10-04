import copy
import importlib.util
import json
from pathlib import Path
import unittest

spec=importlib.util.spec_from_file_location('mfa_blind_projector',Path(__file__).with_name('project.py'))
project=importlib.util.module_from_spec(spec)
spec.loader.exec_module(project)

class ProjectTests(unittest.TestCase):
    def data(self):
        return {'target':{'written_by_writer':[['winner-label','rater',{'id':1,'Excerpt1':'left prose','Excerpt2':'right prose',
            'Preference':'answer-label','Rationale':'private-rationale','unexpected_target':'private-extra'}]]}}

    def test_targets_and_rationales_never_affect_projection(self):
        original=self.data()
        before=copy.deepcopy(original)
        first=project.project(original,'quality_fewshot_expert_anon.json')
        self.assertEqual(original,before)
        changed=copy.deepcopy(original)
        row=changed['target']['written_by_writer'][0]
        row[0]='other-label'
        row[2].update(Preference='different',Rationale='different',unexpected_target='different')
        self.assertEqual(first,project.project(changed,'quality_fewshot_expert_anon.json'))
        serialized=json.dumps(first)
        for forbidden in ('winner-label','answer-label','private-rationale','private-extra','left prose','right prose','rater','written_by_writer'):
            # rater_hash is a field name, while the original rater value is absent.
            if forbidden=='rater':
                self.assertNotIn('"rater"',serialized)
            else:
                self.assertNotIn(forbidden,serialized)

    def test_source_order_preserved_pair_reuse_counted_across_tasks(self):
        data=self.data()
        first=project.project(data,'quality_fewshot_expert_anon.json')
        record=data['target']['written_by_writer'][0][2]
        record['Excerpt1'],record['Excerpt2']=record['Excerpt2'],record['Excerpt1']
        second=project.project(data,'style_fewshot_expert_anon.json')
        self.assertEqual(first[0]['pair_hash'],second[0]['pair_hash'])
        self.assertEqual(first[0]['excerpt_hashes'],list(reversed(second[0]['excerpt_hashes'])))
        summary=project.aggregate(first+second)
        self.assertEqual(summary['judgment_rows'],2)
        self.assertEqual(summary['distinct_pairs_across_tasks'],1)
        self.assertEqual(summary['distinct_exact_excerpts'],2)

    def test_missing_rater_and_excerpt_fail_without_emitting_values(self):
        data=self.data()
        data['target']['written_by_writer'][0][1]=''
        with self.assertRaisesRegex(ValueError,'Missing rater'):
            project.project(data,'quality_fewshot_expert_anon.json')
        data=self.data()
        del data['target']['written_by_writer'][0][2]['Excerpt1']
        with self.assertRaisesRegex(ValueError,'Missing source excerpt'):
            project.project(data,'quality_fewshot_expert_anon.json')

if __name__=='__main__':
    unittest.main()
