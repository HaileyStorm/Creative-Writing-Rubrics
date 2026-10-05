"""Failure reservation preserves observations; bounded dispatch never retries."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import threading
from types import SimpleNamespace
import uuid

import pytest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('test_failed_transport',ROOT/'evaluation-results/hbq-native-transport-recovery-v1/continue_failed_transport.py')
f=importlib.util.module_from_spec(spec);spec.loader.exec_module(f)


def lines(rows):return b''.join(f.canonical(v) for v in rows)


def grok_trace():
 session=str(uuid.uuid4());prompt='Exact synthetic prompt.';at='2026-10-05T07:02:42+00:00'
 source={'cwd_leaf':'grok-exec-fixture','retries':3,'thoughts':1}
 summary={'info':{'id':session,'cwd':'C:/fixture/grok-exec-fixture'},'reasoning_effort':'high',
  'current_model_id':'grok-4.7','session_kind':'headless','created_at':at,'updated_at':at}
 updates=[]
 for n,u in enumerate([{'sessionUpdate':'user_message_chunk','content':{'type':'text','text':prompt},'_meta':{'modelId':'grok-4.7','promptIndex':0}},
  {'sessionUpdate':'agent_thought_chunk','content':{'type':'text','text':'Private reasoning.'}},
  *[{'sessionUpdate':'retry_state','type':'retrying','attempt':i,'max_retries':15,'error_type':'http','reason':f.r.GROK_DNS} for i in (1,2)],
  {'sessionUpdate':'retry_state','type':'retrying','attempt':1,'max_retries':3,'error_type':'http','reason':'Connection problem; retrying request'}]):
  updates.append({'timestamp':1791183762,'method':'_x.ai/session/update' if u['sessionUpdate']=='retry_state' else 'session/update',
   'params':{'sessionId':session,'update':u,'_meta':{'eventId':str(n),'agentTimestampMs':1791183762000}}})
 raw={'summary.json':f.canonical(summary),'updates.jsonl':lines(updates),'tool_definitions.json':b'[]',
  'prompt_history.jsonl':lines([{'session_id':session,'is_bash':False,'prompt':prompt,'timestamp':at}]),
  'system_prompt.txt':b'Act as an isolated structured-output evaluator. Do not use memory, tools, web, plans, or subagents.',
  'events.jsonl':lines([{'type':'turn_started','session_id':session,'model_id':'grok-4.7','turn_number':0}]),
  'chat_history.jsonl':lines([{'type':'user','prompt_index':0,'content':[{'type':'text','text':prompt}]}])}
 return raw,dict(prompt=prompt,session=session,source=source,started={'time':at})


def test_ambiguous_grok_requires_own_prompt_and_no_completion_or_tools():
 raw,kwargs=grok_trace();original=deepcopy(raw)
 proof=f.grok_failure_proof(raw,**kwargs)
 assert raw==original and proof['completed_answer'] is False and proof['native_retries_filtered'] is False
 assert proof['thought_updates']==1 and not proof['physical_contact_cardinality_proven']
 assert f.grok_failure_proof(raw,**{**kwargs,'prompt':kwargs['prompt']+'\n'})['native_prompt_projection']=='single_terminal_lf_omission'
 changes=[('tool_definitions.json',b'[{}]'),('events.jsonl',raw['events.jsonl']+lines([{'type':'turn_completed'}])),
  ('chat_history.jsonl',raw['chat_history.jsonl']+lines([{'type':'assistant','content':'answer'}]))]
 for name,value in changes:
  changed={**raw,name:value}
  with pytest.raises(ValueError):f.grok_failure_proof(changed,**kwargs)
 with pytest.raises(ValueError):f.grok_failure_proof(raw,**{**kwargs,'prompt':'Different prompt.'})


def test_exhausted_sol_dns_preserves_reasoning_but_refuses_answer(tmp_path):
 thread=str(uuid.uuid4());turn=str(uuid.uuid4());prompt='Bound synthetic prompt.';at='2026-10-05T07:02:17+00:00'
 reconnect=lambda n,message:{'type':'error','message':f'Reconnecting... {n}/5 ({message})'}
 events=[{'type':'thread.started','thread_id':thread},{'type':'turn.started'},
  *[reconnect(n,f.r.SOL_WS) for n in range(2,6)],
  {'type':'item.completed','item':{'id':'item_1','type':'error','message':f.r.SOL_FALLBACK}},
  *[reconnect(n,'Connection failed: error sending request') for n in range(1,6)],
  {'type':'error','message':'Connection failed: error sending request'},
  {'type':'turn.failed','error':{'message':'Connection failed: error sending request'}}]
 rows=[{'type':'session_meta','payload':{'id':thread,'source':'exec','model_provider':'openai','cwd':str(tmp_path)}},
  {'type':'event_msg','payload':{'type':'task_started','turn_id':turn,'started_at':1791183737}},
  {'type':'turn_context','payload':{'turn_id':turn,'model':'gpt-6.1-sol','effort':'high','cwd':str(tmp_path)}},
  {'type':'response_item','payload':{'type':'message','role':'user','content':[{'type':'input_text','text':prompt}],
   'internal_chat_message_metadata_passthrough':{'content_item_kinds':['user.text']}}},
  {'type':'response_item','payload':{'type':'reasoning'}},
  {'type':'event_msg','payload':{'type':'task_complete','turn_id':turn,'last_agent_message':None,
   'error':{'message':'Connection failed: error sending request','codex_error_info':{'http_connection_failed':{'http_status_code':None}}},'completed_at':1791184093}}]
 kwargs=dict(prompt=prompt,cwd=tmp_path,started={'time':at})
 proof=f.sol_dns_proof(lines(events),lines(rows),**kwargs)
 assert proof['native_reasoning_present'] and proof['null_final'] and not proof['completed_answer']
 for change in ('answer','context','unknown_error'):
  es,rs=deepcopy((events,rows))
  if change=='answer':rs.insert(-1,{'type':'response_item','payload':{'type':'message','role':'assistant','content':[]}})
  elif change=='context':rs[2]['payload']['cwd']=str(tmp_path/'different')
  else:es[-1]['error']['message']='Unknown error.'
  with pytest.raises(ValueError):f.sol_dns_proof(lines(es),lines(rs),**kwargs)


def test_suffix_identity_job_binding_and_occupied_failures_are_not_pending(tmp_path,monkeypatch):
 rows=[{'endpoint':'grok','endpoint_ordinal':n,'request_sha256':str(n),'logical_sample_id':str(n)} for n in range(1,5)]
 plan={'endpoint':'grok','reserved_through':2,'untouched_request_sha256s':['3','4'],'prefix':[{},{}],
  'source_binding':{'workers':1,'route':{'frozen':True},'route_sha256':'route'},'source_job_sha256':'old','execution_descendant':'bounded_endpoint_workers_v1','full_planned_denominator':8}
 ctx={'manifest':{'requests':rows},'module':SimpleNamespace(sample_path=lambda root,row:root/str(row['endpoint_ordinal']),SETTLED={'accepted','semantic_rejected'})}
 binding=f.job_binding(plan,'plan',3)
 assert binding['workers']==3 and plan['source_binding']['workers']==1 and binding['route']==plan['source_binding']['route']
 for workers in (0,11):
  with pytest.raises(ValueError):f.job_binding(plan,'plan',workers)
 output=tmp_path/'results';output.mkdir();f.write(output/'job.json',f.canonical(binding));(output/'3').mkdir()
 monkeypatch.setattr(f,'replay',lambda *args:('ambiguous',None,False))
 pending,states=f.inventory(plan,ctx,output,binding)
 assert states==['ambiguous'] and [v['endpoint_ordinal'] for v in pending]==[4]
 with pytest.raises(ValueError,match='Occupied failed suffix'):
  f.collect(plan,ctx,output,binding,None)
 plan['untouched_request_sha256s'][0]='changed'
 with pytest.raises(ValueError):f.suffix_rows(plan,ctx)


def test_explicit_route_renewal_preserves_controls_and_saved_job_replay(tmp_path):
 source={'name':'fixture','model':'grok-4.7','reasoning_effort':'high','timeout_seconds':900,'max_concurrency':10,
  'command':['frozen-command'],'nonvisual_max_turns':1,'allowed_payload_classes':['public_repo'],
  'cost_evidence':{'expires_at':'old'},'subscription_receipt_hash':'old'}
 renewed={**source,'cost_evidence':{'expires_at':'new'},'subscription_receipt_hash':'new'}
 sha=f.digest(f.canonical(renewed).rstrip(b'\n'))
 plan={'endpoint':'grok','source_binding':{'route':source,'route_sha256':'source-route','workers':1},
  'source_job_sha256':'source-job','reserved_through':2,'prefix':[{},{}],'untouched_request_sha256s':['3'],
  'execution_descendant':'bounded_endpoint_workers_v1','full_planned_denominator':6}
 f.write(tmp_path/'routes.json',f.canonical({'routes':[renewed]}))
 with pytest.raises(ValueError,match='explicit execution-route'):
  f.select_execution_route(plan,tmp_path,None)
 selected=f.select_execution_route(plan,tmp_path,sha);binding=f.job_binding(plan,'plan',2,selected,sha)
 assert plan['source_binding']['route']==source and binding['source_route_sha256']=='source-route' and binding['route_sha256']==sha
 output=tmp_path/'results';output.mkdir();f.write(output/'job.json',f.canonical(binding))
 assert f.existing_binding(plan,'plan',2,output)==binding
 for key,value in [('command',['changed']),('max_concurrency',11),('nonvisual_max_turns',2),('reasoning_effort','low')]:
  changed={**renewed,key:value}
  with pytest.raises(ValueError,match='non-evidence route control'):
   f.validate_execution_route(source,changed,f.digest(f.canonical(changed).rstrip(b'\n')))
 with pytest.raises(ValueError,match='SHA differs'):f.validate_execution_route(source,renewed,'different')


def test_bounded_failure_drains_started_tail_stops_admission_and_full_gate():
 rendezvous=threading.Barrier(3);release=threading.Event();failed=threading.Event();calls=[]
 def call(row):
  calls.append(row);rendezvous.wait(timeout=5)
  if row==1:failed.set();release.set();return 'ambiguous'
  release.wait(timeout=5);return 'accepted'
 results,stopped=f.dispatch(list(range(1,9)),call,3,failed.is_set,{'accepted','semantic_rejected'})
 assert stopped and sorted(calls)==[1,2,3] and dict(results)=={1:'ambiguous',2:'accepted',3:'accepted'}
 plan={'endpoint':'grok','original_manifest_sha256':'original','full_planned_denominator':8,'prefix':[{},{}],
  'human_label_gate':'explicit_and_complete'}
 other={'original_manifest_sha256':'original','full_planned_denominator':8,'prefix':[{},{}]}
 assert not f.gate(plan,['accepted'],[4],other,['accepted','accepted'],[],True)['human_release_eligible']
 assert not f.gate(plan,['accepted','ambiguous'],[],other,['accepted','accepted'],[],False)['human_release_eligible']
 assert f.gate(plan,['accepted','ambiguous'],[],other,['accepted','accepted'],[],True)['human_release_eligible']
 other['original_manifest_sha256']='different'
 with pytest.raises(ValueError):f.gate(plan,[],[],other)
