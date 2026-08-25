from __future__ import annotations
import importlib.util,sys
from pathlib import Path
import pytest
REPO=Path(__file__).resolve().parents[1];PUBLIC=REPO/'evaluation-results'/'hbq-qpc24-two-pass-product-confirmation-v4';PRIVATE=Path(r'C:\Users\Haile\Documents\cwr-qpc24-two-pass-product-confirmation-v4-4ce1204-20260825')
def load(path,name):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
def live():
 previous=sys.modules.get('freeze');sys.modules['freeze']=load(PRIVATE/'freeze.py','v4freeze_live')
 try:return load(PRIVATE/'live_controller.py','v4l')
 finally:
  if previous is None:sys.modules.pop('freeze',None)
  else:sys.modules['freeze']=previous
def test_public_geometry():
 r=load(PUBLIC/'study.py','v4p').validate();assert r['provider_calls']==0 and r['inherited_complete_calls']==50 and r['planned_new_calls']==10 and r['total_voting_calls']==60 and r['verdict_positions']==1326
def test_private_inheritance_orphan_and_untouched_control_r3():
 f=load(PRIVATE/'freeze.py','v4f');v=f.verify_freeze();assert len(v['v3_lineage']['all_21_v3_accepted_receipts'])==21 and len(v['v3_lineage']['semantic_v3_acceptances'])==20
 assert v['v3_lineage']['excluded_whole_pass']=='public_control_story-r2';assert v['selection']['new_request_indexes']==list(range(121,131));assert sum(s['question_count'] for s in v['slots'])==221
def test_new_claim_never_resends(tmp_path):
 f=load(PRIVATE/'freeze.py','v4f2');assert f.claim_next(tmp_path)['slot_id']=='public_control_story-r3-b01';assert f.claim_next(tmp_path)['slot_id']=='public_control_story-r3-b02'
def test_preflight_zero_provider(tmp_path,monkeypatch):
 l=live()
 for key in l.API:monkeypatch.delenv(key,raising=False)
 r=l.preflight(tmp_path/'state');assert r['provider_calls']==0 and r['inherited_complete_calls']==50 and r['next_slot']=='public_control_story-r3-b01'
