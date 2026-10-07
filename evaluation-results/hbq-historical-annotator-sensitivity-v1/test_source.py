"""Global omission and prohibited-field behavioral proof on synthetic rows."""
import importlib.util
from pathlib import Path
import unittest

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('annotator_sensitivity',HERE/'source.py')
module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
lexer=module.load_module(module.LEXER,'58ec8ffa744035f897b3f9cedc7b1df130df8cfd9f098eb9bbb1240a0257658c','test_pinned_byte_lexer')

class BehavioralGuards(unittest.TestCase):
    def test_global_worker_omission_and_field_firewall(self):
        axes=['Relevance','Coherence','Empathy','Surprise','Engagement','Complexity']
        header=['Story ID','Prompt','Story','Name',*axes,'Worker ID','Assignment ID']
        raw=(','.join(header)+'\n').encode()
        identity={'a':[],'b':[]}
        specifications=[('a','u',1),('a','v',5),('a','w',3),('b','w',5),('b','u',1),('b','v',3)]
        for index,(story,worker,value) in enumerate(specifications,1):
            assignment='assignment-'+str(index)
            raw+=b','.join([story.encode(),b'\xff',b'\xff',b'\xff',*[str(value).encode()]*6,worker.encode(),assignment.encode()])+b'\n'
            identity[story].append({'source_row':index,'within_story_position':len(identity[story]),
                                    'worker_id':worker,'assignment_id':assignment})
        raw+=b','.join([b'closed',b'\xff',b'\xff',b'\xff',*[b'not-a-rating-\xff']*6,b'\xff',b'\xff'])+b'\n'
        rows,accounting=module.collect_selected(raw,['a','b'],axes,lexer,identity)
        baseline,_=module.targets(rows)
        omitted,counts=module.targets(rows,'u')
        self.assertEqual(baseline,{'hanna-a':3,'hanna-b':3})
        self.assertEqual(omitted,{'hanna-a':4,'hanna-b':4})
        self.assertEqual(counts,{'hanna-a':2,'hanna-b':2})
        self.assertEqual(module.targets(rows,'not-present')[0],baseline)
        self.assertEqual(accounting['rating_fields_decoded'],36)
        self.assertEqual(accounting['unselected_rows_metadata_only'],1)
        self.assertEqual(accounting['story_prompt_Name_fields_decoded'],0)
        self.assertEqual(accounting['unselected_rating_fields_decoded'],0)

    def test_undefined_contrasts_stay_undefined(self):
        self.assertIsNone(module.difference(None,.5))
        self.assertIsNone(module.difference(.5,None))
        self.assertEqual(module.difference(.5,.5),0)
        self.assertEqual(module.summarize([None,None]),{'planned':2,'defined':0,'undefined':2,'minimum':None,'maximum':None})
        self.assertEqual(module.summarize([None,-.5,.5]),{'planned':3,'defined':2,'undefined':1,'minimum':-.5,'maximum':.5})

if __name__=='__main__': unittest.main()
