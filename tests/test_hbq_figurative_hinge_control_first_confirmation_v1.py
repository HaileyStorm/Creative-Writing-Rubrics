from __future__ import annotations
import importlib.util,json,re,sys
from pathlib import Path
from types import SimpleNamespace
import pytest
from hbqrs.paths import book_root
BOOK=book_root();ROOT=BOOK/"evaluation-results"/"hbq-figurative-hinge-control-first-confirmation-v1"
def study():
 s=importlib.util.spec_from_file_location("hingecf",ROOT/"study.py");m=importlib.util.module_from_spec(s);assert s and s.loader;sys.modules[s.name]=m;s.loader.exec_module(m);return m
def test_control_first_eighteen_call_geometry():
 m=study();assert m.validate()=={"study_id":m.STUDY_ID,"slots":18,"provider_calls":0,"promotion":"none"};schedule=m.slots();assert len(schedule)==18;assert all(x['stage']=='control' for x in schedule[:6]);assert all(x['stage']=='target' for x in schedule[6:])
def test_balanced_and_disjoint_carriers():
 m=study();rows=m.corpus();assert [x['case_id'] for x in rows]==['a1','a2','b3','b4','b5','b6'];assert [x['stage'] for x in rows]==['control','control','target','target','target','target']
 carriers={token for row in rows for token in row['carrier_ids']};assert len(carriers)==16
 prior=set()
 for path in BOOK.glob('evaluation-results/hbq-figurative-hinge-treatment-successor-v*/public-synthetic-corpus.json'):
  for row in json.loads(path.read_text(encoding='utf-8')).get('cases',[]): prior.update(re.findall(r'[a-z]+',row['text'].casefold()))
 assert not carriers&prior
def test_exact_v7_text_and_dynamic_terminal_count(tmp_path):
 m=study();v7=json.loads((BOOK/'evaluation-results'/'hbq-figurative-hinge-treatment-successor-v7'/'study-contract.json').read_text(encoding='utf-8'));assert m.contract()['treatment']['exact_text']==v7['treatment']['exact_text']
 result=m._terminal(tmp_path, 'CONTROL_FIXTURE_OR_PROMPT_NO_GO', [{'slot_id':'x'}], False);assert result['completed_slots']==1 and result['planned_slots']==18 and not result['target_dispatched']

def test_current_checkout_fails_closed_then_provider_free_mechanics_smoke(tmp_path,monkeypatch):
 m=study(); calls=[]
 with pytest.raises(ValueError,match="exact source HEAD required"):
  m.head()
 monkeypatch.setattr(m,"head",lambda:None)
 (tmp_path/m.LEDGER).write_text(json.dumps({'format_version':1,'study_id':m.STUDY_ID,'labels':{'a1':'YES','a2':'NO','b3':'YES','b4':'YES','b5':'NO','b6':'NO'}},sort_keys=True,separators=(',',':'))+'\n',encoding='utf-8')
 def render(command,**_kwargs):
  calls.append(command);assert '--allow-remote' not in command
  output=Path(command[command.index('--output')+1]);output.parent.mkdir(parents=True,exist_ok=True);output.write_text('provider-free rendered prompt\n',encoding='utf-8')
  return SimpleNamespace(returncode=0,stdout='',stderr='')
 value=m.dry_run(tmp_path,runner_call=render); private=tmp_path/m.PRIVATE
 assert value['provider_calls']==0 and len(calls)==len(m.slots())==18
 manifest=json.loads((private/'dry-manifest.v1.json').read_text(encoding='utf-8'))
 assert manifest['provider_calls']==0 and manifest['max_future_provider_calls']==18
 assert len(list((private/'prompts').glob('*.txt')))==18
