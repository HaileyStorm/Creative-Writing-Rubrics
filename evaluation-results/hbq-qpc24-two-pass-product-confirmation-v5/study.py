from __future__ import annotations
import hashlib,json,sys
from pathlib import Path

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[1]
STUDY_ID='hbq-qpc24-two-pass-product-confirmation-v5'
HEAD='4ce1204d8dd97feff2c7bd88237e265fac742adb'
QUESTION_SEQUENCE_SHA256='22c7c011189072b746eef4cd6aaf0b4da8cb21fd4786e9920593a4e9828602ce'

def question_ids():
 if str(REPO/'src') not in sys.path:sys.path.insert(0,str(REPO/'src'))
 from hbqrs.core import compile_bundle,compiled_questions,load_data,resolve_bundle
 rows=compiled_questions(compile_bundle(load_data(REPO/'registry'/'all_modules.json'),resolve_bundle(load_data(REPO/'bundles'/'all_bundles.json'),'prose.novel')))
 return [str(row['question']['id']) for row in rows]

def validate():
 v=json.loads((HERE/'study-contract.json').read_text(encoding='utf-8'))
 if v.get('study_id')!=STUDY_ID or v.get('source_head')!=HEAD:raise ValueError('V5 identity drift')
 expected={'complete_eligible_question_count':221,'calls_per_pass':10,'inherited_complete_calls':50,'new_calls':10,'target_voting_calls':60,'target_voting_positions':1326,'maximum_new_unique_contacts':10}
 if v.get('geometry')!=expected:raise ValueError('V5 geometry drift')
 ids=question_ids()
 if len(ids)!=221 or hashlib.sha256((json.dumps(ids,ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n').encode()).hexdigest()!=QUESTION_SEQUENCE_SHA256:raise ValueError('V5 public runtime question sequence drift')
 execution=v.get('execution',{})
 if execution.get('remote_provider_call_count_now')!=0 or execution.get('dispatch_surface')!='absent' or execution.get('retry')!='forbidden_per_slot':raise ValueError('V5 provider boundary drift')
 return {'study_id':STUDY_ID,'provider_calls':0,'inherited_complete_calls':50,'planned_new_calls':10,'total_voting_calls':60,'verdict_positions':1326,'status':'FROZEN_PROVIDER_FREE_PREEXECUTION'}

if __name__=='__main__':print(json.dumps(validate(),sort_keys=True))
