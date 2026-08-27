from __future__ import annotations
import importlib.util,json,sys
from pathlib import Path
import pytest
REPO=Path(__file__).resolve().parents[1]; PUBLIC=REPO/'evaluation-results'/'hbq-qpc24-two-pass-product-confirmation-v3'; PRIVATE=Path(r'C:\Users\Haile\Documents\cwr-qpc24-two-pass-product-confirmation-v3-4ce1204-20260825')

ARCHIVED_OLD_RUNTIME = pytest.mark.skip(reason='Archived QPC24 two-pass v3 controller mechanics require the frozen 4ce1204 runtime; current bindings have advanced.')

def mod(path:Path,name:str):
 s=importlib.util.spec_from_file_location(name,path);assert s and s.loader;m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
def public():return mod(PUBLIC/'study.py','qpc24v3public')
def private():return mod(PRIVATE/'freeze.py','qpc24v3freeze')
def live():
 previous=sys.modules.get('freeze');sys.modules['freeze']=private()
 try:return mod(PRIVATE/'live_controller.py','qpc24v3live')
 finally:
  if previous is None:sys.modules.pop('freeze',None)
  else:sys.modules['freeze']=previous
def clean(monkeypatch,l):
 for key in l.API_KEYS:monkeypatch.delenv(key,raising=False)
def test_current_head_fails_closed_while_v3_public_plan_remains_exact():
 p=public();v=p.contract();assert v['source_head']==p.HEAD==HEAD
 assert v['execution']['dispatch_surface']=='absent' and v['execution']['remote_provider_call_count_now']==0
 assert {k:v['geometry'][k] for k in ('complete_eligible_question_count','questions_per_provider_call','full_batches_per_pass','final_remainder_questions','calls_per_pass','inherited_complete_voting_calls','new_voting_calls','target_voting_calls','target_voting_positions','maximum_new_unique_contacts')}=={'complete_eligible_question_count':221,'questions_per_provider_call':24,'full_batches_per_pass':9,'final_remainder_questions':5,'calls_per_pass':10,'inherited_complete_voting_calls':30,'new_voting_calls':30,'target_voting_calls':60,'target_voting_positions':1326,'maximum_new_unique_contacts':30}
 assert v['fidelity']['per_selected_pass']=='full_prose.novel_221_leaves_in_9x24_plus_5' and v['fidelity']['historical_five_repeat_plan']=='retained_as_extended_validation_path_not_replaced'
 assert v['non_claims']=={'runtime_default':'none','new_evaluation_mode':'none','replacement_of_five_repeat_validation':'none'}
 assert v['eligible_question_set']['bundle_id']=='prose.novel' and v['eligible_question_set']['question_sequence_sha256']=='22c7c011189072b746eef4cd6aaf0b4da8cb21fd4786e9920593a4e9828602ce'
 with pytest.raises(ValueError,match='V3 exact-head drift'):p.validate()

HEAD='4ce1204d8dd97feff2c7bd88237e265fac742adb'

@ARCHIVED_OLD_RUNTIME
def test_freeze_validates_30_inherited_acceptances_and_new_disjoint_slots():
 f=private().verify_freeze();assert len(f['v2_lineage']['inherited_complete_acceptances'])==30
 assert f['selection']['new_request_indexes']==list(range(71,81))+list(range(101,121))
 assert f['v2_lineage']['contacted_request_indexes']==list(range(1,14))+[21]+list(range(31,68))
 assert set(f['selection']['new_request_indexes']).isdisjoint(f['v2_lineage']['contacted_request_indexes'])
 discarded=f['v2_lineage']['discarded_whole_pass'];assert discarded['pass_id']=='gpt_5_6_pro_rewrite-r2' and discarded['base_request_indexes']==list(range(61,71)) and sum(v['claimed'] for v in discarded['slots'].values())==7
@ARCHIVED_OLD_RUNTIME
@pytest.mark.parametrize('tamper',('terminal_receipt','call_reported_receipt','identity_slot_claim','call_approval','process_absence'))
def test_inherited_chain_tampering_is_rejected(tamper:str,monkeypatch):
 f=private();original=f.read
 monkeypatch.setattr(f,'_validate_inherited_content',lambda request,raw:None)
 def altered(path:Path):
  value=original(path)
  if not str(path).startswith(str(f.V2)) or path.name=='private-freeze.v3.json':return value
  if tamper=='terminal_receipt' and path.parent.name=='terminals':value['receipt_sha256']='0'*64
  if tamper=='call_reported_receipt' and path.parent.name=='call-receipts':value['reported_identity_receipt_sha256']='0'*64
  if tamper=='identity_slot_claim' and path.parent.name=='reported-identity-receipts':value['slot_id']='wrong'
  if tamper=='call_approval' and path.parent.name=='call-receipts':value['approval_sha256']='0'*64
  if tamper=='process_absence' and path.parent.name=='call-receipts':value['process_tree_proof']['status']='UNPROVEN'
  return value
 monkeypatch.setattr(f,'read',altered)
 with pytest.raises(ValueError,match='Inherited receipt commitment drift'):f.inherited()
@ARCHIVED_OLD_RUNTIME
def test_claims_are_new_only_immutable_and_never_resent(tmp_path:Path):
 f=private();one=f.claim_next(tmp_path);two=f.claim_next(tmp_path);assert one['base_request_index']==71 and two['base_request_index']==72
 assert f.summary(tmp_path)['claimed_without_terminal_nonvoting']==2
def test_identity_allows_only_optional_nonblank_session_id(monkeypatch):
 l=live();clean(monkeypatch,l);assert l.freeze.identity({**l.REPORTED,'session_id':'ok'})['session_id']=='ok'
 for bad in ({**l.REPORTED,'model':'wrong'},{**l.REPORTED,'session_id':''},{**l.REPORTED,'extra':'x'}):
  with pytest.raises(ValueError):l.freeze.identity(bad)
@ARCHIVED_OLD_RUNTIME
def test_injected_session_success_persists_identity_and_accepts(tmp_path:Path,monkeypatch):
 l=live();clean(monkeypatch,l);b=l.binding();monkeypatch.setattr(l,'binding',lambda:b);neutral=tmp_path/'neutral';monkeypatch.setattr(l,'NEUTRAL',neutral);monkeypatch.setattr(l,'_review',lambda a:'fake');monkeypatch.setattr(l,'_absence',lambda p:{'status':'ABSENT','unique_neutral_slot_root':str(p)})
 request=l.requests()[71];result=l.dispatch(tmp_path/'state',a=l.approval(),neutral=neutral,call=lambda **kw:(l.simulated(request),{'reported':{**l.REPORTED,'session_id':'ok'}}))
 assert result and result['slot_id']=='gpt_5_6_pro_rewrite-r3-b01'
 state=tmp_path/'state';assert (state/'reported-identity-receipts'/'gpt_5_6_pro_rewrite-r3-b01.v1.json').is_file();assert json.loads((state/'terminals'/'gpt_5_6_pro_rewrite-r3-b01.terminal.v1.json').read_text())['status']=='accepted'
@ARCHIVED_OLD_RUNTIME
def test_injected_identity_failure_terminalizes_and_halts(tmp_path:Path,monkeypatch):
 l=live();clean(monkeypatch,l);b=l.binding();monkeypatch.setattr(l,'binding',lambda:b);neutral=tmp_path/'neutral';monkeypatch.setattr(l,'NEUTRAL',neutral);monkeypatch.setattr(l,'_review',lambda a:'fake');monkeypatch.setattr(l,'_absence',lambda p:{'status':'ABSENT','unique_neutral_slot_root':str(p)})
 request=l.requests()[71]
 with pytest.raises(ValueError):l.dispatch(tmp_path/'state',a=l.approval(),neutral=neutral,call=lambda **kw:(l.simulated(request),{'reported':{**l.REPORTED,'model':'wrong'}}))
 state=tmp_path/'state';assert (state/'reported-identity-receipts'/'gpt_5_6_pro_rewrite-r3-b01.v1.json').is_file();assert json.loads((state/'reported-identity-receipts'/'gpt_5_6_pro_rewrite-r3-b01.v1.json').read_text())['reported']['model']=='wrong';assert json.loads((state/'terminals'/'gpt_5_6_pro_rewrite-r3-b01.terminal.v1.json').read_text())['status']=='invalid_identity_or_receipt';assert (state/'automatic-advancement-halts'/'gpt_5_6_pro_rewrite-r3-b01.v1.json').is_file()
@ARCHIVED_OLD_RUNTIME
def test_preflight_and_30_new_simulation_are_provider_free(tmp_path:Path,monkeypatch):
 l=live();clean(monkeypatch,l);assert l.preflight(tmp_path/'state',neutral=tmp_path/'neutral')['provider_calls']==0
 r=l.simulate(tmp_path/'simulation',neutral=tmp_path/'sim-neutral');assert r=={'provider_calls':0,'simulated_new_acceptances':30,'inherited_complete_calls':30,'total_complete_calls':60,'remaining':0}
