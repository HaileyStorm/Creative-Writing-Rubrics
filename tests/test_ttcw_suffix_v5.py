"""New009 persistence/scope guards and current-source allocation boundary."""
import copy
import importlib.util
from pathlib import Path
from threading import Event
from types import SimpleNamespace

import pytest


REPO = Path(__file__).resolve().parents[1]
PROGRAM = Path(r'C:\Users\Haile\Documents\cwr-resume-control-20260919-r1\successor-program-20261004')


def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def test009_scope_and_persistence_before_native_marker(tmp_path,monkeypatch):
    m=load('test009_native',REPO/'evaluation-results/hbq-matched-ttcw-20261004/collector_suffix_v5.py')
    life=tmp_path/'life';life.mkdir();output=tmp_path/'results';output.mkdir()
    monkeypatch.setattr(m,'LIFECYCLE',life)
    binding={'manifest_sha256':m.MANIFEST_SHA};m.record(output/'job.json',binding)
    row={'endpoint':'grok','endpoint_ordinal':338,'logical_sample_id':'a'*64,'prompt_sha256':'b'*64,'schema_sha256':'c'*64}
    monkeypatch.setattr(m.native,'inputs',lambda root,row:(b'x',b'{}',{},''))
    monkeypatch.setattr(m.v4.shutil,'disk_usage',lambda path:SimpleNamespace(free=0))
    contacts=[]
    class Broker:
        def run_grok_native_request(self,*args,**kwargs):
            kwargs['before_contact']();contacts.append('contact')
    state=m.native.collect_one(row,dict(binding,route={'name':'unused'},route_sha256='d'*64),tmp_path,output,
        None,None,Event(),tmp_path,Broker())
    assert state=='unadmitted_no_resend' and not contacts
    assert not (m.native.sample_path(output,row)/'attempt-started.json').exists()
    (life/'STOP').touch()
    with pytest.raises(ValueError,match='lifecycle STOP'):m.guard(binding,output,Event())
    old=dict(row,endpoint_ordinal=337)
    with pytest.raises(ValueError,match='Reserved/foreign'):m.collect_one(old,binding,tmp_path,output,None,None,Event(),None,None)
    assert not m.native.sample_path(output,old).exists()


def test_current_allocation_and_missing_outer_fail_before_reads(monkeypatch):
    m=load('test009_owner',PROGRAM/'ttcw-phase1/launch_grok_suffix_009_001.py')
    inv={'owner':m.OWNER,'collector_sha256':m.OTHER_COLLECTOR_SHA,'manifest_sha256':m.OTHER_MANIFEST_SHA,
        'route_sha256':m.ROUTE_SHA,'workers':2,'automatic_retries':0,'no_resend':True,'one_attempt_per_slot':True,
        'reserved_allocation':{'old_interrupted_grok':3,'hanna_interrupted_grok':3,'conditional_untouched_grok':2,'new_lamp_grok':2}}
    job={'endpoint':'grok','collector_sha256':m.OTHER_COLLECTOR_SHA,'manifest_sha256':m.OTHER_MANIFEST_SHA,
        'route_sha256':m.ROUTE_SHA,'workers':2,'automatic_retries':0}
    m.verify_other(inv,job)
    foreign=copy.deepcopy(inv);foreign['collector_sha256']='old-mfa'
    with pytest.raises(ValueError,match='current LAMP'):m.verify_other(foreign,job)
    # No mutable source is opened: a synthetic absent path exercises the first gate.
    namespace=m.derived_release.__globals__
    absent=PROGRAM/'ttcw-phase1/absent-provider-free009-source'
    assert not absent.exists()
    monkeypatch.setitem(namespace,'SOURCE_LIFE',absent)
    monkeypatch.setitem(namespace,'interfaces',lambda:pytest.fail('interfaces opened before true outer'))
    with pytest.raises(ValueError,match='Current conditional owning true outer absent'):m.release_proof('0'*64)
