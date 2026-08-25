"""Provider-free verifier for the QPC24 V3 six-complete-pass contract."""
from __future__ import annotations
import argparse, hashlib, json, subprocess, sys
from pathlib import Path
from typing import Any
HERE=Path(__file__).resolve().parent; REPO=HERE.parents[1]; sys.path.insert(0,str(REPO/'src'))
from hbqrs.core import compile_bundle,compiled_questions,load_data,resolve_bundle
HEAD='4ce1204d8dd97feff2c7bd88237e265fac742adb'; STUDY_ID='hbq-qpc24-two-pass-product-confirmation-v3'
def sha(v:bytes)->str:return hashlib.sha256(v).hexdigest()
def canonical(v:Any)->bytes:return (json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n').encode()
def contract()->dict[str,Any]:
 v=json.loads((HERE/'study-contract.json').read_text(encoding='utf-8'))
 if v.get('format_version')!=1 or v.get('study_id')!=STUDY_ID or v.get('source_head')!=HEAD:raise ValueError('V3 public identity drift')
 g=v.get('geometry',{}); expected={'complete_eligible_question_count':221,'questions_per_provider_call':24,'full_batches_per_pass':9,'final_remainder_questions':5,'calls_per_pass':10,'inherited_complete_voting_calls':30,'new_voting_calls':30,'target_voting_calls':60,'target_voting_positions':1326,'maximum_new_unique_contacts':30}
 if {k:g.get(k) for k in expected}!=expected or v.get('execution',{}).get('dispatch_surface')!='absent' or v['execution'].get('remote_provider_call_count_now')!=0:raise ValueError('V3 geometry or provider boundary drift')
 if v.get('fidelity',{}).get('per_selected_pass')!='full_prose.novel_221_leaves_in_9x24_plus_5' or v['fidelity'].get('historical_five_repeat_plan')!='retained_as_extended_validation_path_not_replaced':raise ValueError('V3 fidelity drift')
 return v
def validate()->dict[str,Any]:
 v=contract()
 if subprocess.run(['git','rev-parse','HEAD'],cwd=REPO,text=True,capture_output=True).stdout.strip()!=HEAD:raise ValueError('V3 exact-head drift')
 for path,digest in v['runtime_bindings'].items():
  if sha((REPO/path).read_bytes())!=digest:raise ValueError(f'V3 runtime binding drift: {path}')
 rows=compiled_questions(compile_bundle(load_data(REPO/'registry'/'all_modules.json'),resolve_bundle(load_data(REPO/'bundles'/'all_bundles.json'),'prose.novel')))
 if len(rows)!=221 or sha(canonical([str(row['question']['id']) for row in rows]))!='22c7c011189072b746eef4cd6aaf0b4da8cb21fd4786e9920593a4e9828602ce':raise ValueError('V3 question geometry drift')
 return {'study_id':STUDY_ID,'provider_calls':0,'inherited_complete_voting_calls':30,'planned_new_voting_calls':30,'planned_total_voting_calls':60,'verdict_positions':1326,'status':'FROZEN_PROVIDER_FREE_PREEXECUTION'}
def main(argv:list[str]|None=None)->int:
 p=argparse.ArgumentParser();p.add_argument('command',choices=('verify',));p.parse_args(argv);print(json.dumps(validate(),sort_keys=True));return 0
if __name__=='__main__':raise SystemExit(main())
