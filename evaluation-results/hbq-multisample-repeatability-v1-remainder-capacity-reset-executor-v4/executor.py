#!/usr/bin/env python3
"""Fresh one-cell executor after the sealed v3 pre-dispatch failure."""
from __future__ import annotations
import argparse, hashlib, importlib.util, json, os, re, subprocess, sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping

HERE=Path(__file__).resolve().parent; REPO=HERE.parents[1]
V2=HERE.parent/'hbq-multisample-repeatability-v1-remainder-capacity-reset-successor-v2'
V3=HERE.parent/'hbq-multisample-repeatability-v1-remainder-capacity-reset-executor-v3'
CONTRACT=HERE/'study-contract.json'; BINDING='executor-binding.json'; SCHEDULE='schedule.jsonl'; JOURNAL='execution-journal.jsonl'; CLAIM='active-epoch-claim.json'; PROOFS='capacity-proofs'
FAILED=Path(r'C:\Users\Haile\Documents\cwr-multisample-capacity-reset-v3-live-90f5769-20260822')
FAILED_ROWS=[('active-epoch-claim.json',346,'b829f11750a3aab8813dc094ce70b19e8fb0a64b86998453f8ab8b90b5f14e39'),('capacity-probe-result.json',14,'b342fc286d0216cc212e0d7ba234894e2e7283ddf14f959adf0fe7fd5924308a'),('capacity-probe.schema.json',215,'70a849c87addb91ead24b84744f148c461308bf5406d268771d612ef084695af'),('capacity-proofs/1eb78b06751a7246a294ee4114dd5ced941334191679e22c15a71a5ebb4e824b.json',399,'1eb78b06751a7246a294ee4114dd5ced941334191679e22c15a71a5ebb4e824b'),('execution-journal.jsonl',320,'d4eb639cb0d41dad44f7be4f0b2f0cfcc604e2f06bf7e3b93f1f355a1735fee7'),('executor-binding.json',1824,'d45e16361baf07ff5474f7acb49eab1efee0b347863b1f91e3057c6bbe410d4f'),('schedule.jsonl',21657,'28d353f633500bb2fbfcf5db1784d4e20f3fad2a50874474ce3689f412d19562')]

def canonical(x:Any)->bytes:return json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()
def sha(p:Path)->str:return hashlib.sha256(p.read_bytes()).hexdigest()
def obj(p:Path)->dict[str,Any]:
 x=json.loads(p.read_text(encoding='utf-8'))
 if not isinstance(x,dict):raise ValueError('Expected JSON object')
 return x
def contract()->dict[str,Any]:
 x=obj(CONTRACT); e={'format_version':1,'study_id':'hbq-multisample-repeatability-v1-remainder-capacity-reset-executor-v4','failed_v3_commit':'90f5769b8119d9011ed6435742ad23c208eb69e4','schedule':{'count':153,'first_sequence':178,'last_sequence':330,'sha256':'96b91f124d2a889f4fa47b70d67c16604927f33928ca4ad5d302713c84f8f086'},'provider':{'provider':'codex','model':'gpt-5.6-sol','reasoning':'high','paid_api':False,'human_judgment':False},'capacity':{'max_age_seconds':600,'per_send_revalidation':True,'probe_authorizes_provider_contact':False},'execution':{'cells_per_epoch':1,'resend_after_unresolved_attempt':False,'outcome_selection':False}}
 if x!=e:raise ValueError('V4 contract drifted')
 return x
def _load(path:Path,name:str)->Any:
 prior=sys.modules.get('study'); spec=importlib.util.spec_from_file_location(name,path)
 if spec is None or spec.loader is None:raise RuntimeError('Cannot load dependency')
 m=importlib.util.module_from_spec(spec); sys.path.insert(0,str(path.parent))
 try:spec.loader.exec_module(m);return m
 finally:
  sys.path.remove(str(path.parent)); sys.modules.pop('study',None) if prior is None else sys.modules.__setitem__('study',prior)
def v2()->Any:return _load(V2/'run_capacity_reset.py','v4_v2')
def _file(p:Path,root:Path)->dict[str,Any]:return {'path':p.resolve().relative_to(root).as_posix(),'bytes':p.stat().st_size,'sha256':sha(p)}
def _projection(root:Path,files:tuple[str,...],commit:str)->dict[str,Any]:
 rows=[_file(root/x,REPO) for x in files]
 for row in rows:
  if subprocess.check_output(['git','rev-parse',f'{commit}:{row["path"]}'],cwd=REPO,text=True).strip()!=subprocess.check_output(['git','hash-object',row['path']],cwd=REPO,text=True).strip():raise ValueError('Pushed runtime drifted')
 return {'commit':commit,'files':rows,'sha256':hashlib.sha256(canonical(rows)).hexdigest()}
def failed_v3()->dict[str,Any]:
 if not FAILED.is_dir():raise ValueError('Failed v3 evidence root missing')
 actual=[]
 for p in sorted(FAILED.rglob('*')):
  if p.is_file():actual.append((p.relative_to(FAILED).as_posix(),p.stat().st_size,sha(p)))
 if actual!=FAILED_ROWS:raise ValueError('Failed v3 evidence tree drifted')
 journal=(FAILED/'execution-journal.jsonl').read_text(encoding='utf-8').splitlines()
 if len(journal)!=2 or [json.loads(x).get('event') for x in journal]!=['capacity-checked','attempt-intent'] or any((FAILED/x).exists() for x in ('runs','result.json','completion.json')):raise ValueError('Failed v3 is not the sealed zero-scorer-contact pre-dispatch failure')
 return {'root_sha256':'6f17301e7b7c7ff380d1c0fcb33bc49a7796564d56a5f0cde5bddb2319cfe92d','files':len(actual),'journal_rows':2,'claim_sha256':sha(FAILED/'active-epoch-claim.json')}
def _base(closed:Path,source:Path,v2work:Path)->tuple[Any,Any,list[dict[str,Any]],dict[str,Any]]:
 m=v2(); _,schedule,execution=m._verify_prepared(closed,source,v2work,allow_executor=True,allow_authorization=True); rem=m._previous(); owner=getattr(rem,'_previous_runner',lambda:None)()
 if not callable(getattr(rem,'validate_executor_binding',None)) or not callable(getattr(owner,'_revalidate_predecessor_event',None)) or not callable(getattr(owner,'_run_event',None)):raise ValueError('Required v1 owner API drifted')
 rem.validate_executor_binding(closed,source,v2work)
 if hashlib.sha256(m.canonical(schedule)).hexdigest()!=contract()['schedule']['sha256']:raise ValueError('Schedule drifted')
 return m,owner,schedule,execution
def _append(p:Path,x:Mapping[str,Any])->None:
 fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_APPEND,0o600)
 try:
  b=canonical(x)+b'\n'
  if os.write(fd,b)!=len(b):raise OSError('partial journal write')
  os.fsync(fd)
 finally:os.close(fd)
def _rows(p:Path)->list[dict[str,Any]]:
 if not p.exists():return []
 b=p.read_bytes()
 if b and not b.endswith(b'\n'):raise ValueError('partial journal tail')
 return [json.loads(x) for x in b.splitlines()]
def _expected_binding(closed:Path,source:Path,v2work:Path)->tuple[Any,Any,list[dict[str,Any]],dict[str,Any],dict[str,Any]]:
 m,owner,schedule,execution=_base(closed,source,v2work)
 bind={'format_version':1,'study_id':contract()['study_id'],'contract':_file(CONTRACT,HERE),'provider':contract()['provider'],'failed_v3':failed_v3(),'v3_runtime':_projection(V3,('README.md','executor.py','study-contract.json'),contract()['failed_v3_commit']),'v2_binding_sha256':sha(v2work/m.CAPACITY_BINDING),'v1_executor_binding_sha256':sha(v2work/m._previous().EXECUTOR_BINDING),'schedule_sha256':hashlib.sha256(m.canonical(schedule)).hexdigest()}
 return m,owner,schedule,execution,bind
def _verify(closed:Path,source:Path,v2work:Path,work:Path)->tuple[Any,Any,list[dict[str,Any]],dict[str,Any]]:
 m,owner,schedule,execution,expected=_expected_binding(closed,source,v2work)
 if not (work/BINDING).is_file() or obj(work/BINDING)!=expected or _rows(work/SCHEDULE)!=schedule:raise ValueError('V4 prepared provenance drifted')
 return m,owner,schedule,execution
def prepare(closed:Path,source:Path,v2work:Path,work:Path)->dict[str,Any]:
 work=work.resolve()
 if REPO in work.parents or work==REPO or work.exists() and any(work.iterdir()):raise ValueError('Fresh external v4 root required')
 m,owner,schedule,execution,bind=_expected_binding(closed,source,v2work); work.mkdir(parents=True,exist_ok=True)
 (work/BINDING).write_bytes(canonical(bind)+b'\n')
 for x in schedule:_append(work/SCHEDULE,x)
 _verify(closed,source,v2work,work);return {'provider_calls':0,'cells':153,'first_sequence':178,'last_sequence':330}
def _claim(work:Path,source:Path)->Path:
 p=work/CLAIM; value={'format_version':1,'pid':os.getpid(),'claimed_at':datetime.now(UTC).isoformat(),'contract_sha256':sha(CONTRACT),'frozen_contract_sha256':sha(source/'frozen-run-contract.json')}
 try:fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
 except FileExistsError as e:raise ValueError('Exclusive claim exists; stop without duplicate dispatch') from e
 try:
  b=canonical(value)+b'\n'
  if os.write(fd,b)!=len(b):raise OSError('partial claim')
  os.fsync(fd)
 finally:os.close(fd)
 return p
def _done(work:Path,schedule:list[dict[str,Any]],owner:Any)->list[dict[str,Any]]:
 rows=_rows(work/JOURNAL)
 if len(rows)%3:raise ValueError('Unresolved attempt intent; stop without resend')
 out=[]
 for i in range(0,len(rows),3):
  proof,intent,done=rows[i:i+3]; event=schedule[len(out)] if len(out)<len(schedule) else None; digest=proof.get('capacity_proof_sha256'); proofpath=work/PROOFS/f'{digest}.json'
  if event is None or proof.get('event')!='capacity-checked' or not isinstance(digest,str) or not proofpath.is_file() or sha(proofpath)!=digest or intent!={'event':'attempt-intent','sequence':event['sequence'],'capacity_proof_sha256':digest} or done.get('event')!='completed' or done.get('sequence')!=event['sequence'] or done.get('capacity_proof_sha256')!=digest or not isinstance(done.get('output_sha256'),str):raise ValueError('Execution journal drifted')
  target=owner._binding_path(work,event)
  if not target.is_file() or sha(target)!=done['output_sha256']:raise ValueError('Completed output drifted')
  out.append(event)
 return out
def execute_one(closed:Path,source:Path,v2work:Path,work:Path,proof:Path,*,allow_remote:bool=False,timeout:float=3600.0,now:datetime|None=None)->dict[str,Any]:
 m,owner,schedule,execution=_verify(closed,source,v2work,work)
 if not allow_remote:raise ValueError('Pass --allow-remote only after review')
 receipt=m.validate_capacity_evidence(proof,now=now); claim=_claim(work,source); settled=False
 try:
  completed=_done(work,schedule,owner)
  if len(completed)==len(schedule):settled=True;return {'provider_calls':0,'completed':153,'remaining':0}
  event=schedule[len(completed)]; b=canonical(receipt)+b'\n'; digest=hashlib.sha256(b).hexdigest(); pp=work/PROOFS/f'{digest}.json';pp.parent.mkdir(exist_ok=True)
  if pp.exists() and pp.read_bytes()!=b:raise ValueError('proof mutation')
  if not pp.exists():pp.write_bytes(b)
  _append(work/JOURNAL,{'event':'capacity-checked','sequence':event['sequence'],'capacity_proof_sha256':digest,'observed_at':receipt['observed_at']});_append(work/JOURNAL,{'event':'attempt-intent','sequence':event['sequence'],'capacity_proof_sha256':digest})
  frozen=owner.read_json(source/'frozen-run-contract.json');owner._revalidate_predecessor_event(source,frozen,event);owner._run_event(owner._v1_runner(),event,frozen,source,work,timeout);m.validate_fresh_sessions(work/'runs',execution);target=owner._binding_path(work,event);_append(work/JOURNAL,{'event':'completed','sequence':event['sequence'],'capacity_proof_sha256':digest,'output_sha256':sha(target)});settled=True;return {'provider_calls':1,'sequence':event['sequence'],'completed':len(completed)+1,'remaining':len(schedule)-len(completed)-1}
 finally:
  if settled:claim.unlink()
def main()->None:
 p=argparse.ArgumentParser();p.add_argument('closed',type=Path);p.add_argument('source',type=Path);p.add_argument('v2work',type=Path);p.add_argument('work',type=Path);p.add_argument('--dry-run',action='store_true');p.add_argument('--capacity-evidence',type=Path);p.add_argument('--allow-remote',action='store_true');p.add_argument('--timeout',type=float,default=3600.0);a=p.parse_args()
 if a.dry_run:
  if a.work.exists() and any(a.work.iterdir()):
   _,_,schedule,_,_=_expected_binding(a.closed,a.source,a.v2work);_verify(a.closed,a.source,a.v2work,a.work);print(json.dumps({'provider_calls':0,'cells':len(schedule),'first_sequence':schedule[0]['sequence'],'last_sequence':schedule[-1]['sequence'],'reloaded':True},sort_keys=True))
  else:print(json.dumps(prepare(a.closed,a.source,a.v2work,a.work),sort_keys=True))
  return
 if a.capacity_evidence is None:p.error('--capacity-evidence required')
 print(json.dumps(execute_one(a.closed,a.source,a.v2work,a.work,a.capacity_evidence,allow_remote=a.allow_remote,timeout=a.timeout),sort_keys=True))
if __name__=='__main__':main()
