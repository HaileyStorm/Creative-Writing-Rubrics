from __future__ import annotations
import argparse,json
from pathlib import Path
HERE=Path(__file__).resolve().parent; STUDY_ID='hbq-qpc24-two-pass-product-confirmation-v4'
def validate():
 v=json.loads((HERE/'study-contract.json').read_text())
 if v.get('study_id')!=STUDY_ID or v.get('source_head')!='4ce1204d8dd97feff2c7bd88237e265fac742adb':raise ValueError('V4 identity drift')
 if v['geometry']!={'complete_eligible_question_count':221,'calls_per_pass':10,'inherited_complete_calls':50,'new_calls':10,'target_voting_calls':60,'target_voting_positions':1326,'maximum_new_unique_contacts':10}:raise ValueError('V4 geometry drift')
 if v['execution']['remote_provider_call_count_now']!=0 or v['execution']['dispatch_surface']!='absent':raise ValueError('V4 provider boundary drift')
 return {'study_id':STUDY_ID,'provider_calls':0,'inherited_complete_calls':50,'planned_new_calls':10,'total_voting_calls':60,'verdict_positions':1326,'status':'FROZEN_PROVIDER_FREE_PREEXECUTION'}
def main(argv=None):
 p=argparse.ArgumentParser();p.add_argument('command',choices=('verify',));p.parse_args(argv);print(json.dumps(validate(),sort_keys=True));return 0
if __name__=='__main__':raise SystemExit(main())
