"""Capacity reservation is missing evidence, never a recovered answer or retry."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import uuid

import pytest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('test_capacity_continuation',ROOT/'evaluation-results/hbq-native-transport-recovery-v1/continue_capacity.py')
c=importlib.util.module_from_spec(spec);spec.loader.exec_module(c)


def trace(cwd,prompt='Exact synthetic prompt.'):
    thread=str(uuid.uuid4());turn=str(uuid.uuid4());at='2026-10-05T05:01:35+00:00'
    events=[{'type':'thread.started','thread_id':thread},
        {'type':'item.completed','item':{'id':'item_0','type':'error','message':c.r.codex_receipts.STARTUP_DIAGNOSTIC}},
        {'type':'turn.started'},{'type':'error','message':c.CAPACITY},{'type':'turn.failed','error':{'message':c.CAPACITY}}]
    rows=[{'timestamp':at,'type':'session_meta','payload':{'id':thread,'source':'exec','model_provider':'openai','cwd':str(cwd)}},
        {'timestamp':at,'type':'event_msg','payload':{'type':'task_started','turn_id':turn,'started_at':1791176495}},
        {'timestamp':at,'type':'turn_context','payload':{'turn_id':turn,'model':'gpt-6.1-sol','effort':'high','cwd':str(cwd)}},
        {'timestamp':at,'type':'response_item','payload':{'type':'message','role':'user','content':[{'type':'input_text','text':prompt}],
            'internal_chat_message_metadata_passthrough':{'turn_id':turn,'content_item_kinds':['user.text']}}},
        {'timestamp':at,'type':'event_msg','payload':{'type':'task_complete','turn_id':turn,'last_agent_message':None,
            'error':{'message':c.CAPACITY,'codex_error_info':'server_overloaded'},'completed_at':1791176498}}]
    return events,rows,{'time':at}


def lines(rows):return b''.join(c.canonical(row) for row in rows)


def test_capacity_proof_requires_own_context_exact_error_and_no_answer(tmp_path):
    events,rows,started=trace(tmp_path)
    before=deepcopy((events,rows));proof=c.capacity_projection(lines(events),lines(rows),prompt='Exact synthetic prompt.',cwd=tmp_path,started=started)
    assert before==(events,rows) and proof['null_final'] and proof['zero_assistant_messages']
    assert not proof['accepted'] and proof['new_votes']==0 and proof['no_resend']
    for change in ('other_error','assistant','tool','final','context','prompt','incomplete'):
        e,r=deepcopy(before)
        if change=='other_error':e[-1]['error']['message']='Rate limit exceeded.'
        elif change=='assistant':r.insert(-1,{'type':'response_item','payload':{'type':'message','role':'assistant','content':[]}})
        elif change=='tool':r.insert(-1,{'type':'event_msg','payload':{'type':'item_completed','item':{'type':'ToolCall'}}})
        elif change=='final':r[-1]['payload']['last_agent_message']='A saved answer.'
        elif change=='context':r[2]['payload']['effort']='low'
        elif change=='prompt':r[3]['payload']['content'][0]['text']='Different submitted prompt.'
        else:e.pop()
        with pytest.raises(ValueError):c.capacity_projection(lines(e),lines(r),prompt='Exact synthetic prompt.',cwd=tmp_path,started=started)


def test_failure_start_job_account_and_native_artifacts_are_bound(tmp_path,monkeypatch):
    output=tmp_path/'source';sample=output/'0001-fixture';sample.mkdir(parents=True)
    home=tmp_path/'secondary';rollout=home/'sessions/own.jsonl';rollout.parent.mkdir(parents=True)
    events,rows,started=trace(sample);event_raw=lines(events);rollout.write_bytes(lines(rows))
    row={'logical_sample_id':'logical','prompt_sha256':c.digest(b'Exact synthetic prompt.'),'schema_sha256':c.digest(b'{}'),'endpoint':'sol'}
    binding={'manifest_sha256':'manifest','runtime':{'secondary_home_sha256':c.digest(str(home.resolve()).encode())}}
    account={'account_identity_sha256':'fixture'};c.record(output/'account-binding.json',account);c.record(output/'job.json',binding)
    started.update(manifest_sha256='manifest',logical_sample_id='logical',attempt=1,no_resend=True,
        job_sha256=c.digest((output/'job.json').read_bytes()),prompt_sha256=row['prompt_sha256'],schema_sha256=row['schema_sha256'],
        session_id=None,account_binding_sha256=c.digest((output/'account-binding.json').read_bytes()))
    for name,raw in [('condition.json',c.canonical(row)),('attempt-started.json',c.canonical(started)),
        ('native-identity.json',c.canonical({'logical_sample_id':'logical','session_id':None})),
        ('prompt.txt',b'Exact synthetic prompt.'),('schema.json',b'{}'),('events.jsonl',event_raw)]:c.write(sample/name,raw)
    terminal={'state':'unadmitted_no_resend','accepted':False,'no_resend':True,'error_class':'_ProviderAttemptFailure',
        'provider_record':{'provider_artifacts':{'codex_events':{'path':'events.jsonl',**c.meta(event_raw)}}}}
    c.record(sample/'terminal.json',terminal)
    def pinned(root,name,m):
        raw=(root/name).read_bytes();c.require(c.meta(raw)=={k:m[k] for k in ('sha256','bytes')},'Own native artifact differs');return raw
    module=SimpleNamespace(sample_path=lambda root,row:sample,pinned=pinned,account_receipt=lambda b:account,
        inputs=lambda *args:(b'Exact synthetic prompt.',b'{}',{},''))
    ctx={'module':module,'source_root':output,'binding':binding,'source':{'manifest_sha256':'manifest'},'root':tmp_path,
        'manifest':{},'config':{'study':'mfa'},'receipt':{'config':{'secondary_home_local_only':str(home)}}}
    monkeypatch.setattr(c.r.codex_receipts,'locate',lambda *args,**kw:rollout)
    proof,_,_=c.failure_proof(ctx,row)
    assert proof['rollout_sha256']==c.digest(rollout.read_bytes()) and not proof['completed_answer']
    # The P4 collector exposes the same account primitive through its retained transport.
    started['attempt_id']=str(uuid.uuid4());(sample/'attempt-started.json').write_bytes(c.canonical(started))
    terminal.update(job_sha256=started['job_sha256'],attempt_id=started['attempt_id'])
    (sample/'terminal.json').write_bytes(c.canonical(terminal))
    p4=SimpleNamespace(sample_path=module.sample_path,pinned=pinned,inputs=module.inputs,
        t=SimpleNamespace(account_receipt=module.account_receipt),source_settings=lambda *args:{'external_pins':{'collection_home_path_local_only':str(home)}})
    assert c.failure_proof({**ctx,'module':p4,'config':{'study':'p4'}},row)[0]['null_final']
    original=(output/'account-binding.json').read_bytes();(output/'account-binding.json').write_bytes(original+b' ')
    with pytest.raises(ValueError,match='account'):c.failure_proof(ctx,row)
    (output/'account-binding.json').write_bytes(original);c.write(sample/'response.json',b'null')
    with pytest.raises(ValueError,match='saved answer'):c.failure_proof(ctx,row)


def small_plan(tmp_path):
    rows=[{'endpoint':endpoint,'endpoint_ordinal':n,'request_sha256':f'{endpoint}-{n}','logical_sample_id':f'{endpoint}-{n}'}
        for endpoint in ('sol','grok') for n in (1,2)]
    plan={'source_binding':{'runtime':{}},'source_job_sha256':'oldjob','reserved_through':1,
        'prefix':[{'endpoint_ordinal':1,'state':'unadmitted_no_resend'}],'untouched_request_sha256s':['sol-2'],
        'full_planned_denominator':4,'human_label_gate':'fixture gate'}
    module=SimpleNamespace(sample_path=lambda output,row:output/f"{row['endpoint_ordinal']:04d}",SETTLED={'accepted','semantic_rejected'})
    ctx={'module':module,'manifest':{'requests':rows},'config':{'study':'mfa'},'root':tmp_path,'source':{'full_denominator':4,'reconciliation_sha256':'receipt'},
        'receipt':{'reserved_through':{'grok':1},'prefix':[{'endpoint':'grok','state':'accepted'}]}}
    return plan,ctx


def test_suffix_commits_unchanged_rows_and_occupied_failure_stops_dispatch(tmp_path,monkeypatch):
    plan,ctx=small_plan(tmp_path);rows=c.suffix_rows(plan,ctx)
    assert [row['endpoint_ordinal'] for row in rows]==[2]
    changed=deepcopy(ctx['manifest']);changed['requests'][1]['request_sha256']='changed'
    with pytest.raises(ValueError):c.suffix_rows(plan,{**ctx,'manifest':changed})
    output=tmp_path/'suffix';output.mkdir();binding=c.job_binding(plan,'plan');c.record(output/'job.json',binding)
    (output/'0002').mkdir()
    monkeypatch.setattr(c,'original_replay',lambda *args:('unadmitted_no_resend',None,False))
    monkeypatch.setattr(c,'verify_plan',lambda *args:(plan,ctx));monkeypatch.setattr(c,'validate_output',lambda *args:None)
    monkeypatch.setattr(c.r,'load',lambda *args:pytest.fail('No helper import or dispatch allowed'))
    monkeypatch.setattr('sys.argv',['continue_capacity','collect','--plan',str(tmp_path/'plan.json'),'--plan-sha256','plan','--results-dir',str(output)])
    with pytest.raises(ValueError,match='occupied; no resend'):c.main()
    # An unresolved directory must fail replay; it cannot become pending.
    monkeypatch.setattr(c,'original_replay',lambda *args:(_ for _ in ()).throw(ValueError('Unresolved own attempt; no resend')))
    with pytest.raises(ValueError,match='Unresolved'):c.inventory(plan,ctx,output,binding)


def test_gate_joins_reserved_missing_failure_once_and_requires_all_slots_flag(tmp_path,monkeypatch):
    plan,ctx=small_plan(tmp_path);output=tmp_path/'suffix';grok=tmp_path/'grok';grok.mkdir();(grok/'0002').mkdir()
    ctx['transport']=SimpleNamespace(verify_job_binding=lambda *args:{},replay_sample=lambda *args:('semantic_rejected',None,False))
    states={'missing':False}
    monkeypatch.setattr(c,'inventory',lambda *args:([{}] if states['missing'] else [],[] if states['missing'] else ['accepted']))
    def gate(flag):return c.label_check(plan,ctx,output,{},grok,flag)
    assert gate(False)['verified_terminal']==4 and not gate(False)['human_release_eligible']
    assert gate(True)['human_release_eligible'] and not gate(True)['human_targets_opened']
    assert gate(True)['terminal_states']['unadmitted_no_resend']==1 and not gate(True)['reserved_capacity_failure_admitted']
    states['missing']=True;assert not gate(True)['human_release_eligible']
    ctx['transport'].replay_sample=lambda *args:(_ for _ in ()).throw(ValueError('Unresolved native slot'))
    with pytest.raises(ValueError,match='Unresolved'):gate(True)
