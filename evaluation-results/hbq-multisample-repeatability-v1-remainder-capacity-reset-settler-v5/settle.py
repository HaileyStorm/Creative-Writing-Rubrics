from __future__ import annotations
import argparse,hashlib,json,os,importlib.util,sys
from pathlib import Path
from typing import Any
ROOT=Path(r'C:\Users\Haile\Documents\cwr-multisample-capacity-reset-v4-live-1c587bc-20260822'); HERE=Path(__file__).resolve().parent
V2ROOT=Path(r'C:\Users\Haile\Documents\cwr-multisample-capacity-reset-v2-v3-bootstrap-20260822'); EXECUTION_SHA='64ed8367a152bebe17fa44fb69a200092d131eaf6b2a6c39b7cc223caebd0aa0'
EXPECTED_TREE='b084bc32f1df05b279a3816f188d98e1e7f95da0e4453a46d5e2b7fa81af6009'; EXPECTED_RUN='42b223e0ef9ae6d258c68b35ae1a08f1ecce1d073b64b7f19b77b95e3b584f70'; EXPECTED_VERDICTS='28d3cbbb616be02f4d2cab063f9ef56ca9be8d4689025cb1ef998274aeac091a'; EXPECTED_SESSIONS='ebde6b1ccd743548bb2ce7c03b04971aabbc13c451c29e153f2132f369a704f5'
def sha(p:Path)->str:return hashlib.sha256(p.read_bytes()).hexdigest()
def canon(x:Any)->bytes:return json.dumps(x,sort_keys=True,separators=(',',':')).encode()
def obj(p:Path)->dict:
 x=json.loads(p.read_text(encoding='utf-8'))
 if not isinstance(x,dict):raise ValueError('expected object')
 return x
def _owner_validator():
 v2=Path(__file__).resolve().parents[1]/'hbq-multisample-repeatability-v1-remainder-capacity-reset-successor-v2'/'run_capacity_reset.py'; prior=sys.modules.get('study');spec=importlib.util.spec_from_file_location('v5_v2',v2)
 if spec is None or spec.loader is None:raise RuntimeError('v2 loader missing')
 m=importlib.util.module_from_spec(spec);sys.path.insert(0,str(v2.parent))
 try:spec.loader.exec_module(m);return m._previous().validate_fresh_sessions
 finally:
  sys.path.remove(str(v2.parent));sys.modules.pop('study',None) if prior is None else sys.modules.__setitem__('study',prior)
def execution():
 p=V2ROOT/'remainder-execution-contract.json';x=obj(p)
 if sha(p)!=EXECUTION_SHA or x.get('closed_successor_binding_sha256')!='88672b40136655cd6f18807b988b3c2c308eab632f06d75dc7659879c744cb51' or x.get('lineage_sessions',{}).get('source',{}).get('unique_count')!=146 or x.get('lineage_sessions',{}).get('closed',{}).get('unique_count')!=183:raise ValueError('committed lineage execution drifted')
 return x
def rows(p:Path)->list[dict]:
 b=p.read_bytes()
 if not b.endswith(b'\n'):raise ValueError('partial journal')
 return [json.loads(x) for x in b.splitlines()]
def freeze(root:Path=ROOT)->dict:
 if not root.is_dir():raise ValueError('failed v4 root missing')
 files=[]
 for p in sorted(root.rglob('*')):
  if p.is_file():files.append({'path':p.relative_to(root).as_posix(),'bytes':p.stat().st_size,'sha256':sha(p)})
 tree=hashlib.sha256(canon(files)).hexdigest()
 if tree!=EXPECTED_TREE:raise ValueError('v4 frozen manifest/tree drifted')
 journal=rows(root/'execution-journal.jsonl')
 if len(journal)!=2 or [x.get('event') for x in journal]!=['capacity-checked','attempt-intent'] or not (root/'active-epoch-claim.json').is_file():raise ValueError('v4 claim/journal drifted')
 run=list((root/'runs').rglob('run.json')); verdict=list((root/'runs').rglob('verdicts.jsonl')); batches=list((root/'runs').rglob('batch-????.json'))
 if len(run)!=1 or len(verdict)!=1 or len(batches)!=6 or sha(run[0])!=EXPECTED_RUN or sha(verdict[0])!=EXPECTED_VERDICTS:raise ValueError('v4 accepted run provenance drifted')
 config=obj(run[0]).get('configuration',{}); questions=config.get('question_ids'); lines=[json.loads(x) for x in verdict[0].read_text(encoding='utf-8').splitlines()]
 if not isinstance(questions,list) or len(questions)!=179 or len(lines)!=179 or [x.get('question_id') for x in lines]!=questions or any(x.get('judge_id')!='codex:gpt-5.6-sol' or x.get('run_id')!=obj(run[0]).get('run_id') for x in lines):raise ValueError('v4 ordered verdict replay failed')
 sessions=[]
 for p in batches:
  x=json.loads(p.read_text(encoding='utf-8'));stack=[x];found=[]
  while stack:
   y=stack.pop()
   if isinstance(y,dict):
    if isinstance(y.get('session_id'),str):found.append(y['session_id'])
    stack.extend(y.values())
   elif isinstance(y,list):stack.extend(y)
  if len(found)!=1:raise ValueError('batch session evidence is missing or ambiguous')
  s=found[0]
  sessions.append(s)
 sessionhash=hashlib.sha256(canon(sorted(hashlib.sha256(x.encode()).hexdigest() for x in sessions))).hexdigest()
 if len(set(sessions))!=6 or sessionhash!=EXPECTED_SESSIONS:raise ValueError('batch session set drifted')
 _owner_validator()(root/'runs',execution())
 return {'root':str(root),'tree_sha256':tree,'files':files,'journal_sha256':sha(root/'execution-journal.jsonl'),'claim_sha256':sha(root/'active-epoch-claim.json'),'run_sha256':sha(run[0]),'verdicts_sha256':sha(verdict[0]),'batch_count':6,'verdict_count':179,'session_sha256':sessionhash}
def settle(work:Path,root:Path=ROOT)->dict:
 if work.exists() and any(work.iterdir()):raise ValueError('fresh recovery root required')
 f=freeze(root);work.mkdir(parents=True,exist_ok=True); record={'format_version':1,'kind':'offline_recovered_completion_v5','sequence':178,'provider_calls':0,'failed_v4':f,'completion_sha256':f['run_sha256'],'reason':'post-run session-validator AttributeError; six batches and 179 verdicts already accepted'};(work/'offline-recovered-completion.json').write_bytes(canon(record)+b'\n');return record
def main():
 p=argparse.ArgumentParser();p.add_argument('work',type=Path);p.add_argument('--failed-root',type=Path,default=ROOT);a=p.parse_args();print(json.dumps(settle(a.work,a.failed_root),sort_keys=True))
if __name__=='__main__':main()
