from __future__ import annotations
import importlib.util, sys
from pathlib import Path
import pytest

ROOT=Path(__file__).resolve().parents[1]
PACKAGE=ROOT/'evaluation-results'/'hbq-multisample-repeatability-v1-remainder-capacity-reset-executor-v4'
def runner():
 spec=importlib.util.spec_from_file_location('v4',PACKAGE/'executor.py');assert spec and spec.loader;m=importlib.util.module_from_spec(spec);sys.modules['v4']=m;spec.loader.exec_module(m);return m
def test_failed_v3_tree_is_exact_two_row_pre_dispatch_failure():
 r=runner(); got=r.failed_v3();assert got['files']==7 and got['journal_rows']==2
def test_v1_owner_api_is_required(monkeypatch:pytest.MonkeyPatch,tmp_path:Path):
 r=runner()
 class V2:
  def _verify_prepared(*a,**k):return None,[{'sequence':178}],{}
  def _previous(*a):return type('R',(),{'validate_executor_binding':lambda *a:None,'_previous_runner':lambda *a:object()})()
  def canonical(*a):return b'[]'
 monkeypatch.setattr(r,'v2',lambda:V2())
 with pytest.raises(ValueError,match='owner API drifted'):r._base(tmp_path/'c',tmp_path/'s',tmp_path/'w')
def test_contract_is_exact():assert runner().contract()['failed_v3_commit'].startswith('90f5769')
def test_verify_rejects_missing_or_tampered_prepare_binding(monkeypatch:pytest.MonkeyPatch,tmp_path:Path):
 r=runner(); work=tmp_path/'work';work.mkdir();schedule=[{'sequence':178}];expected={'provider':{'model':'gpt-5.6-sol'}}
 monkeypatch.setattr(r,'_expected_binding',lambda *a:(None,None,schedule,{},expected))
 with pytest.raises(ValueError,match='provenance drifted'):r._verify(tmp_path/'c',tmp_path/'s',tmp_path/'v2',work)
 (work/r.BINDING).write_text('{"provider":{"model":"gpt-5.6-luna"}}',encoding='utf-8');(work/r.SCHEDULE).write_text('{"sequence":178}\n',encoding='utf-8')
 with pytest.raises(ValueError,match='provenance drifted'):r._verify(tmp_path/'c',tmp_path/'s',tmp_path/'v2',work)
def test_failed_v3_tree_drift_fails_closed(monkeypatch:pytest.MonkeyPatch,tmp_path:Path):
 r=runner(); root=tmp_path/'failed';root.mkdir();monkeypatch.setattr(r,'FAILED',root)
 with pytest.raises(ValueError,match='tree drifted'):r.failed_v3()
def test_execute_enters_verify_before_capacity_or_claim(monkeypatch:pytest.MonkeyPatch,tmp_path:Path):
 r=runner();calls=[]
 monkeypatch.setattr(r,'_verify',lambda *a:(calls.append('verify') or (_ for _ in ()).throw(ValueError('drift'))))
 with pytest.raises(ValueError,match='drift'):r.execute_one(tmp_path/'c',tmp_path/'s',tmp_path/'v',tmp_path/'w',tmp_path/'p',allow_remote=True)
 assert calls==['verify']
