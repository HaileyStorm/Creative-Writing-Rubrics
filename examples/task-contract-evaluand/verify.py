"""Validate/render invented examples using an explicit local public checkout."""
from __future__ import annotations
import argparse,hashlib,json,os,subprocess,sys
from pathlib import Path
from jsonschema import Draft202012Validator
HERE=Path(__file__).resolve().parent
QID='form.prose.short_story.scope'
sha=lambda b:hashlib.sha256(b).hexdigest()
def require(ok,message):
 if not ok:raise ValueError(message)
def without_context(prompt):
 start='<<< BEGIN UNTRUSTED FROZEN TASK-CONTRACT EVALUATION DATA >>>';end='<<< END UNTRUSTED FROZEN TASK-CONTRACT EVALUATION DATA >>>';a=prompt.index(start);b=prompt.index(end,a)+len(end);return prompt[:a]+prompt[b:]
def cli_text(raw):
 # Windows text stdout translates LF to CRLF. Preserve raw stdout hashes while
 # comparing its text using the same universal-newline convention as text IO.
 return raw.decode('utf-8').replace('\r\n','\n')
def main():
 parser=argparse.ArgumentParser();parser.add_argument('public_checkout',type=Path);args=parser.parse_args();public=args.public_checkout.resolve(strict=True);schema_path=public/'schema/hbq_task_contract.v2.schema.json';schema=json.loads(schema_path.read_bytes());env=dict(os.environ);env.update(PYTHONPATH=str(public/'src'),HBQRS_ROOT=str(public),PYTHONDONTWRITEBYTECODE='1',PYTHONIOENCODING='utf-8');prompts=[];records=[]
 for mode in ['delivered','adaptation']:
  path=HERE/(mode+'.contract.json');raw=path.read_bytes();contract=json.loads(raw);Draft202012Validator(schema).validate(contract);override_path=HERE/(mode+'.scope-override.json');override=json.loads(override_path.read_bytes());require(override['task_contract_sha256']==sha(raw),'exact contract/override byte binding');require(override['reviewer']=='Invented render-fixture reviewer; not a real compatibility approval','explicit invented approval status')
  command=[sys.executable,'-B','-m','hbqrs','render-judge','--bundle','prose.short_story','--artifact','synopsis.txt','--artifact-id','invented-synopsis','--question-id',QID,'--task-contract',mode+'.contract.json','--scope-compatibility-override',mode+'.scope-override.json'];result=subprocess.run(command,cwd=HERE,env=env,capture_output=True,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),check=False);require(result.returncode==0,'actual render CLI failed: '+result.stderr.decode('utf-8',errors='replace'));prompt=cli_text(result.stdout);marker='\n## Questions\n\n```json\n';a=prompt.rindex(marker);payload=json.loads(prompt[a+len(marker):-5]);require(len(payload)==1 and payload[0]['question_id']==QID,'one requested canonical leaf');require(contract['context']['background'][0] in prompt and contract['context']['constraints'][0] in prompt,'declared evaluand context reaches prompt');require(contract['weighted_goals']==contract['binding_requirements']==[],'no synthetic scores/gates');prompts.append(prompt);records.append({'mode':mode,'contract_sha256':sha(raw),'override_sha256':sha(override_path.read_bytes()),'prompt_sha256':sha(result.stdout),'prompt_bytes':len(result.stdout),'question_payload':payload})
 require(records[0]['question_payload']==records[1]['question_payload'],'canonical question payload unchanged');require(prompts[0]!=prompts[1] and without_context(prompts[0])==without_context(prompts[1]),'only frozen context block differs')
 # A mismatched contract must be refused, rather than borrowing the other mode's decision.
 bad=[sys.executable,'-B','-m','hbqrs','render-judge','--bundle','prose.short_story','--artifact','synopsis.txt','--artifact-id','invented-synopsis','--question-id',QID,'--task-contract','adaptation.contract.json','--scope-compatibility-override','delivered.scope-override.json'];rejected=subprocess.run(bad,cwd=HERE,env=env,capture_output=True,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),check=False);require(rejected.returncode!=0 and b'does not bind' in rejected.stderr,'mismatched scope decision rejected')
 print(json.dumps({'status':'PASS','contracts_schema_valid':2,'actual_cli_renders':2,'mismatched_override_rejected':True,'question_payloads_equal':True,'prompt_difference':'frozen task-contract evaluation-data block only','provider_calls':0,'files_written_by_check':False,'records':[{k:v for k,v in z.items() if k!='question_payload'} for z in records],'public_source_sha256':{name:sha((public/name).read_bytes()) for name in ['src/hbqrs/cli.py','src/hbqrs/runner.py','src/hbqrs/core.py','schema/hbq_task_contract.v2.schema.json']}},sort_keys=True))
if __name__=='__main__':main()
