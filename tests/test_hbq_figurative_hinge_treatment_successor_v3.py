from __future__ import annotations
import importlib.util,json,sys,tempfile
from pathlib import Path
import pytest
from hbqrs.paths import book_root
ROOT=book_root()/"evaluation-results"/"hbq-figurative-hinge-treatment-successor-v3"
def study():
 s=importlib.util.spec_from_file_location("hingev3",ROOT/"study.py");m=importlib.util.module_from_spec(s);assert s and s.loader;sys.modules[s.name]=m;s.loader.exec_module(m);return m
def test_contract_and_balancing():
 m=study();assert m.validate()=={"study_id":m.STUDY_ID,"slots":8,"provider_calls":0,"promotion":"none"};assert len(m.slots())==8
def test_verify_post_call_fails_closed_on_missing_run():
 m=study();p=Path(tempfile.mkdtemp());s=m.slots()[0]
 with pytest.raises(FileNotFoundError):m.verify_post_call(p,s)
def test_execute_checks_head_before_review(monkeypatch):
 m=study();monkeypatch.setattr(m,"head",lambda:(_ for _ in ()).throw(ValueError("head drift")))
 with pytest.raises(ValueError,match="head drift"):m.execute(Path(tempfile.mkdtemp()),allow_remote=True,acknowledged_zero_incremental_charge=True)
def test_execution_requires_go_record_and_does_not_claim(monkeypatch):
 m=study();p=Path(tempfile.mkdtemp());r=m.root(p);r.mkdir(parents=True);(r/"dry-manifest.v1.json").write_text(json.dumps({"bindings":{},"source_head":m.HEAD,"provider_calls":0}),encoding="utf-8");monkeypatch.setattr(m,"head",lambda:None)
 with pytest.raises(FileNotFoundError):m.execute(p,allow_remote=True,acknowledged_zero_incremental_charge=True)
 assert not (r/"execution-claim.v1.json").exists()

def setup_execution(m,p):
 r=m.root(p);r.mkdir(parents=True);manifest={"bindings":{},"source_head":m.HEAD,"provider_calls":0};(r/"dry-manifest.v1.json").write_text(json.dumps(manifest),encoding="utf-8");return r,manifest
def test_go_binding_and_material_drift_fail_before_claim(monkeypatch):
 m=study();p=Path(tempfile.mkdtemp());r,_=setup_execution(m,p);monkeypatch.setattr(m,"head",lambda:None);monkeypatch.setattr(m,"bindings",lambda _p:{})
 (p/m.REVIEW).write_text(json.dumps({"study_id":m.STUDY_ID,"source_head":m.HEAD,"decision":"GO","bindings":{}}),encoding="utf-8")
 with pytest.raises(ValueError,match="GO"):m.execute(p,allow_remote=True,acknowledged_zero_incremental_charge=True)
 assert not (r/"execution-claim.v1.json").exists()
 (p/m.REVIEW).write_text(json.dumps({"study_id":m.STUDY_ID,"source_head":m.HEAD,"decision":"GO","bindings":{"manifest":m.sha(r/"dry-manifest.v1.json")}}),encoding="utf-8")
 monkeypatch.setattr(m,"bindings",lambda _p:{"drift":"x"})
 with pytest.raises(ValueError,match="material drifted"):m.execute(p,allow_remote=True,acknowledged_zero_incremental_charge=True)
 assert not (r/"execution-claim.v1.json").exists()
def test_one_shot_claim_prevents_second_dispatch(monkeypatch):
 m=study();p=Path(tempfile.mkdtemp());r,_=setup_execution(m,p);monkeypatch.setattr(m,"head",lambda:None);monkeypatch.setattr(m,"bindings",lambda _p:{})
 (p/m.REVIEW).write_text(json.dumps({"study_id":m.STUDY_ID,"source_head":m.HEAD,"decision":"GO","bindings":{"manifest":m.sha(r/"dry-manifest.v1.json")}}),encoding="utf-8")
 with pytest.raises(FileNotFoundError):m.execute(p,allow_remote=True,acknowledged_zero_incremental_charge=True,runner_call=lambda *a,**k:None)
 assert (r/"execution-claim.v1.json").exists()
 with pytest.raises(ValueError,match="one-shot"):m.execute(p,allow_remote=True,acknowledged_zero_incremental_charge=True,runner_call=lambda *a,**k:None)
