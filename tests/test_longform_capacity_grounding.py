"""Synthetic capacity-binding and same-vote grounding witnesses; no native proof."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('test_p4_capacity_grounding',ROOT/'evaluation-results/hbq-longform-dependency-pilot-v1/analysis_capacity_grounding.py')
v = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)


def membership():
    sol = [{'endpoint':'sol','endpoint_ordinal':n,'logical_sample_id':f'l{n}', 'request_sha256':f's{n}'} for n in range(1,233)]
    manifest = {'requests':sol+[{'endpoint':'grok','request_sha256':f'g{n}'} for n in range(1,233)]}
    plan = {'full_planned_denominator':464,'endpoint_denominator':232,'reserved_through':97,
        'prefix':[{**row,'state':'accepted' if row['endpoint_ordinal']<97 else 'unadmitted_no_resend'} for row in sol[:97]],
        'untouched_request_sha256s':[r['request_sha256'] for r in sol[97:]],
        'capacity_failure_admitted':False,'failure_counts_as_missing':True}
    return plan,manifest


def test_reserved_prefix_and_suffix_membership_cannot_overlap_or_reorder():
    plan,manifest = membership()
    assert len(v.validate_membership(plan,manifest))==232
    for change in ('reserved','order','duplicate','admitted'):
        changed = deepcopy(plan)
        if change=='reserved':changed['untouched_request_sha256s'][0]=changed['prefix'][-1]['request_sha256']
        if change=='order':changed['untouched_request_sha256s'][:2]=reversed(changed['untouched_request_sha256s'][:2])
        if change=='duplicate':changed['prefix'][1]=deepcopy(changed['prefix'][0])
        if change=='admitted':changed['capacity_failure_admitted']=True
        with pytest.raises(ValueError):v.validate_membership(changed,manifest)


def test_correct_job_hash_cannot_hide_wrong_capacity_binding(tmp_path,monkeypatch):
    plan,manifest = membership()
    plan.update(config={'study':'p4'},original_manifest_sha256=v.a.MANIFEST_SHA)
    ctx={'manifest':manifest,'source':{'collector_sha256':v.a.COLLECTOR_SHA}}
    monkeypatch.setattr(v.cc,'verify_plan',lambda *_:(plan,ctx))
    monkeypatch.setattr(v.cc,'job_binding',lambda *_:{'capacity_plan_sha256':v.PLAN_SHA,'endpoint':'sol'})
    wrong = v.c.canonical({'capacity_plan_sha256':'different-plan','endpoint':'sol'})
    (tmp_path/'job.json').write_bytes(wrong)
    monkeypatch.setattr(v,'JOB_SHA',v.c.digest(wrong))
    with pytest.raises(ValueError,match='continuation job'):
        v.verify_capacity(tmp_path/'plan.json',tmp_path)


def test_grounding_keeps_original_bytes_and_changes_only_proven_quote(tmp_path,monkeypatch):
    row={'endpoint':'sol','logical_sample_id':'l98','request_sha256':'s98','arm':'hbq','work_id':'w'}
    original={'verdicts':[{'question_id':'q','verdict':'YES','confidence':1,'note':'Synthetic witness',
                         'evidence':[{'exact_quote':'a\nb'}]}]}
    raw=v.c.canonical(original)
    (tmp_path/'response.json').write_bytes(raw)
    (tmp_path/'terminal.json').write_bytes(v.c.canonical({'state':'semantic_rejected'}))
    admission={'accepted':False,'errors':['Not an exact source substring'],'abstention':False}
    (tmp_path/'acceptance.json').write_bytes(v.c.canonical(admission))
    class Validator:
        def semantic_validate(self,arm,response,request,texts,subset,**kwargs):
            quote=response['verdicts'][0]['evidence'][0]['exact_quote']
            accepted=quote in texts['w']
            return {'accepted':accepted,'errors':[] if accepted else admission['errors'],'abstention':False}
    subset=SimpleNamespace(matches_schema=lambda *_:True)
    sources={'available':{'text':'start a\r\nb end','path':'source.txt'}}
    monkeypatch.setattr(v.ag,'available_sources',lambda *_:(sources,'',{}))
    ctx={'root':tmp_path,'manifest':{},'subset':subset,'validator':Validator()}
    entry=v.terminal_descendant(ctx,row,tmp_path,{'state':'semantic_rejected'},'job')
    assert entry['grounding_state']=='projected_accepted' and entry['new_votes']==0 and entry['no_resend']
    assert entry['response']['verdicts'][0]['evidence'][0]['exact_quote']=='a\r\nb'
    assert entry['original_response_file_sha256']==v.c.digest(raw)
    assert (tmp_path/'response.json').read_bytes()==raw and original['verdicts'][0]['evidence'][0]['exact_quote']=='a\nb'
    proof=entry['certificate']['quotes'][0]
    assert proof['locations'][0]['source_char']==[6,10] and proof['state']=='projected_exact_span'


def test_reserved_failure_and_started_suffix_never_reach_grounding(tmp_path,monkeypatch):
    original=tmp_path/'original';output=tmp_path/'suffix';original.mkdir();output.mkdir()
    reserved={'endpoint':'sol','endpoint_ordinal':97,'logical_sample_id':'l97','request_sha256':'s97'}
    unresolved={'endpoint':'sol','endpoint_ordinal':117,'logical_sample_id':'l117','request_sha256':'s117'}
    manifest={'requests':[reserved,unresolved,{'endpoint':'grok','request_sha256':'g1'}]}
    sample=v.c.sample_path(original,reserved);sample.mkdir()
    terminal=v.c.canonical({'state':'unadmitted_no_resend'})
    (sample/'terminal.json').write_bytes(terminal)
    pending=v.c.sample_path(output,unresolved);pending.mkdir()
    (pending/'condition.json').write_bytes(v.c.canonical(unresolved));(pending/'attempt-started.json').write_bytes(b'{}\n')
    (output/'job.json').write_bytes(b'{}\n')
    prefix={'request_sha256':'s97','state':'unadmitted_no_resend','source_terminal_sha256':v.c.digest(terminal),
            'source_inventory':{'terminal.json':{'sha256':v.c.digest(terminal),'bytes':len(terminal)}}}
    ctx={'manifest':manifest,'source_root':original,'root':tmp_path}
    monkeypatch.setattr(v.a.d,'native_metrics',lambda *_:{})
    monkeypatch.setattr(v.cc.r,'validate_started',lambda *_:None)
    monkeypatch.setattr(v.g,'derive',lambda *_:pytest.fail('Unresolved/failure cannot be projected'))
    records,inventory,ledger=v.collect_capacity({'prefix':[prefix],'source_job_sha256':'job'},ctx,output,{})
    assert not records and len(inventory)==3 and len(ledger)==1
    assert [i['state'] for i in inventory]==['unadmitted_no_resend','started_unresolved','not_supplied']
    assert ledger[0]['response'] is None
