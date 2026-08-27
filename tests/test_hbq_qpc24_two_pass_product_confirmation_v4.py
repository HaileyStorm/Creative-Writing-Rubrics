from __future__ import annotations
import importlib.util,sys
from pathlib import Path
import pytest
REPO=Path(__file__).resolve().parents[1];PUBLIC=REPO/'evaluation-results'/'hbq-qpc24-two-pass-product-confirmation-v4';PRIVATE=Path(r'C:\Users\Haile\Documents\cwr-qpc24-two-pass-product-confirmation-v4-4ce1204-20260825')

ARCHIVED_OLD_RUNTIME = pytest.mark.skip(reason='Archived QPC24 two-pass v4 controller mechanics require the frozen 4ce1204 runtime; current bindings have advanced.')

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
def test_current_head_fails_closed_before_v4_private_inheritance_replay():
 f=load(PRIVATE/'freeze.py','v4f');assert f.HEAD=='4ce1204d8dd97feff2c7bd88237e265fac742adb'
 with pytest.raises(ValueError,match='QPC24 requires exact source HEAD 4ce1204'):
  f.verify_freeze()

@ARCHIVED_OLD_RUNTIME
def test_new_claim_never_resends(tmp_path):
 f=load(PRIVATE/'freeze.py','v4f2');assert f.claim_next(tmp_path)['slot_id']=='public_control_story-r3-b01';assert f.claim_next(tmp_path)['slot_id']=='public_control_story-r3-b02'
@ARCHIVED_OLD_RUNTIME
def test_preflight_zero_provider(tmp_path,monkeypatch):
 l=live()
 for key in l.API:monkeypatch.delenv(key,raising=False)
 r=l.preflight(tmp_path/'state');assert r['provider_calls']==0 and r['inherited_complete_calls']==50 and r['next_slot']=='public_control_story-r3-b01'
