"""Reserve three bound terminal failures as missing; dispatch untouched suffixes."""
from collections import Counter
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
import argparse
import json
import os
from pathlib import Path
import sys
import threading
from urllib.parse import unquote

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import continue_capacity as c

r=c.r
canonical,digest,require,meta,write=c.canonical,c.digest,c.require,c.meta,c.write
POLICY='failed_transport_missing_untouched_suffix_v1'
TRANSPORT_SHA='20f654ab4e7d09c2555b45f172147664d473109b8072fa78f72de1f580b03313'
CAPACITY_SHA='ed1db65b99275615cec36bb6a545cf284b1d2e4f085dfde26d8c1e7046493982'
ROUTE_SHA='87cc6467a6f10ab8d986f09bb8a5c6f9176659c79e421220a4825adcc70cded4'
FAILURE_SHA='62fe284a30196a58b781e3486a94a23cbaba953da57d23e53525eb55e1d62c14'
SOURCES={
 'p1-sol':{'study':'p1','endpoint':'sol','source':'semantic-crossform/matched-transport-sol-001','through':269,
  'job_sha256':'ba177a6a0439520f489d735c5834507c7b578345b0919d7baf2d134064692650',
  'terminal_sha256':'c87c6730c26e675ea64387e2bb41d55e7bfa63cf93182e25e90062d11b8f07d8',
  'events_sha256':'ff7836e481f17c681de3a1ffedc7e633ec31bd1dc3aeb9a5379524fb28397022',
  'rollout_sha256':'a08e9a905b70817a9732ab9b4312216874c4f73dd21a723bcbd5898586be41d7'},
 'p1-grok':{'study':'p1','endpoint':'grok','source':'semantic-crossform/matched-transport-grok-001','through':148,
  'job_sha256':'c70d4946618ef899cdf1f1a32b39787faafc7d4b3ca68ec210fcbc22eea676e8',
  'terminal_sha256':'428543a7fe44e7a4577bf054d94ea463799c5cd97473de249e0d0cb7827bea44',
  'session_id':'0b325e70-ab50-4da1-bff7-75d83dbab5c8','cwd_leaf':'grok-exec-w8a1p05j','retries':40,'thoughts':0,
  'updates_sha256':'f426618fdeddfc033b28936a98c430c99cbad92cbb1c47abce747fb836f2d994'},
 'mfa-grok':{'study':'mfa','endpoint':'grok','source':'mfa-canary/transport-grok-001','through':131,
  'job_sha256':'c29883c4b1b19360d854e0533d761113620a70804406caae38ed68f23cec62a0',
  'terminal_sha256':'0291ad99725d138dc3e36f8511fb5c3ee31e848971c229679cfffc79a54e1c4d',
  'session_id':'85edeaab-b482-430f-9b86-7c5bdd5f4907','cwd_leaf':'grok-exec-63a83vx2','retries':35,'thoughts':1,
  'updates_sha256':'fe1c8e67f6374c66769f2b5cf5d0b80af09e841efe1a63f284870bab512ef203'}}
PARENTS={
 'p1':('semantic-crossform/transport-reconciliation-001/reconciliation.json','6975644429b44d728c099036f49f07a9cba21460fee8ce6e88094ec03107f7fc'),
 'mfa':('mfa-canary/transport-reconciliation-001/reconciliation.json','a59f3940ec56097f711c1ad0e27ee76deb3424bf3210737c6d5725ad691995cc')}


def context(config):
 s=SOURCES[config['source']];program=Path(config['program_root_local_only']);parent,pin=PARENTS[s['study']]
 require(digest(Path(c.__file__).read_bytes())==CAPACITY_SHA,'Shared capacity primitives differ')
 transport=r.load('failed_transport_predecessor',HERE/'collector.py')
 require(digest(Path(transport.__file__).read_bytes())==TRANSPORT_SHA,'Frozen transport collector differs')
 receipt,ctx=r.verify(program/parent,pin)
 source=program/s['source'];require(digest((source/'job.json').read_bytes())==s['job_sha256'],'Exact stopped job differs')
 binding=transport.verify_job_binding(source,receipt,pin,ctx,s['endpoint'])
 if s['endpoint']=='grok':require(binding['route_sha256']==ROUTE_SHA,'Reviewed v5 source route differs')
 ctx.update(transport=transport,receipt=receipt,binding=binding,source_root=source,source=s,config=config,
            parent_path=program/parent,parent_sha256=pin)
 return ctx


def sol_dns_proof(events_raw,rollout_raw,*,prompt,cwd,started):
 reader=r.codex_receipts;events=[v for _,v in reader._rows(events_raw)]
 require(events[0]['type']=='thread.started','Missing own native thread')
 thread=reader._uuid(events[0]['thread_id']);body=events[1:]
 if body and body[0]['type']=='item.completed':
  require(body.pop(0)['item'].get('message')==reader.STARTUP_DIAGNOSTIC,'Unknown startup diagnostic')
 reconnect=lambda n,message:{'type':'error','message':f'Reconnecting... {n}/5 ({message})'}
 expected=[{'type':'turn.started'},*[reconnect(n,r.SOL_WS) for n in range(2,6)],
  {'type':'item.completed','item':{'id':'item_1','type':'error','message':r.SOL_FALLBACK}},
  *[reconnect(n,'Connection failed: error sending request') for n in range(1,6)],
  {'type':'error','message':'Connection failed: error sending request'},
  {'type':'turn.failed','error':{'message':'Connection failed: error sending request'}}]
 require(body==expected,'Not the exact exhausted DNS failure')
 rows=[v for _,v in reader._rows(rollout_raw)]
 select=lambda kind,sub=None:[v['payload'] for v in rows if v['type']==kind and (sub is None or v['payload'].get('type')==sub)]
 metas,starts,contexts,ends=select('session_meta'),select('event_msg','task_started'),select('turn_context'),select('event_msg','task_complete')
 require(len(metas)==len(starts)==len(contexts)==len(ends)==1,'DNS failure requires one own turn')
 m,st,ct,end=metas[0],starts[0],contexts[0],ends[0];turn=reader._uuid(st['turn_id'])
 require(m['id']==thread and m['source']=='exec' and m['model_provider']=='openai' and m.get('forked_from_id') is None
  and Path(m['cwd']).resolve()==cwd.resolve(),'Own failure session differs')
 require(ct['turn_id']==end['turn_id']==turn and ct['model']=='gpt-6.1-sol' and ct['effort']=='high'
  and Path(ct['cwd']).resolve()==cwd.resolve(),'Own Sol/high context differs')
 require(end.get('last_agent_message','absent') is None and end.get('error')=={'message':'Connection failed: error sending request',
  'codex_error_info':{'http_connection_failed':{'http_status_code':None}}},'DNS failure has a final/different error')
 prompts=[]
 for v in rows:
  p=v['payload'];kind=v['type'];md=p.get('internal_chat_message_metadata_passthrough',{})
  require(kind in {'session_meta','event_msg','turn_context','world_state','response_item','token_usage_record'}
   and p.get('turn_id',turn)==turn and p.get('thread_id',thread)==thread and md.get('turn_id',turn)==turn,'Foreign native failure record')
  if kind=='event_msg':
   require(p['type'] in {'task_started','task_complete','token_count','item_completed'},'Unknown native activity')
   if 'item' in p:require(p['item']['type'] in {'UserMessage','Reasoning'},'Failure contains assistant/tool activity')
  if kind=='response_item':
   require(p['type']=='reasoning' or (p['type']=='message' and p.get('role') in {'user','system','developer'}),'Failure contains assistant/tool activity')
   if p.get('role')=='user' and md.get('content_item_kinds')==['user.text']:prompts.append(reader._text(p,'input_text'))
 require(prompts==[prompt],'Own submitted failure prompt differs')
 require(r.timestamp(st['started_at']).date()==r.timestamp(started['time']).date()
  and r.timestamp(st['started_at'])<=r.timestamp(end['completed_at']),'Failure lifecycle time differs')
 return {'thread_id':thread,'turn_id':turn,'zero_assistant_messages':True,'null_final':True,
  'native_reasoning_present':bool(select('response_item','reasoning')),'completed_answer':False}


def grok_failure_proof(raws,*,prompt,session,source,started):
 summary=json.loads(raws['summary.json']);updates=[json.loads(v) for v in raws['updates.jsonl'].splitlines()]
 events=[json.loads(v) for v in raws['events.jsonl'].splitlines()];history=[json.loads(v) for v in raws['chat_history.jsonl'].splitlines()]
 require(summary['info']['id']==session and Path(summary['info']['cwd']).name==source['cwd_leaf']
  and summary['reasoning_effort']=='high' and summary['current_model_id']=='grok-4.7' and summary['session_kind']=='headless','Own Grok session differs')
 require(json.loads(raws['tool_definitions.json'])==[],'Native tools were available')
 created,ended=r.timestamp(summary['created_at']),r.timestamp(summary['updated_at'])
 require(abs((created-r.timestamp(started['time'])).total_seconds())<=120 and created<=ended,'Own Grok start time differs')
 counts=Counter();ids=set();previous=None;users=[]
 reasons={r.GROK_DNS,r.GROK_DECODE,'Connection problem; retrying request',
  'request error: error sending request for url (https://cli-chat-proxy.grok.com/v1/responses): client error (SendRequest): connection error: connection reset'}
 for row in updates:
  p=row['params'];u=p['update'];md=p['_meta'];kind=u['sessionUpdate'];at=r.timestamp(row['timestamp'])
  require(p['sessionId']==session and md['eventId'] not in ids and (previous is None or previous<=at)
   and created.timestamp()-120<=at.timestamp()<=ended.timestamp()+120,'Own update identity/time differs')
  ids.add(md['eventId']);previous=at;counts[kind]+=1
  require(kind in {'user_message_chunk','agent_thought_chunk','retry_state'},'Native completed answer/tool/unknown update')
  if kind=='retry_state':require(row['method']=='_x.ai/session/update' and u['type']=='retrying'
   and u['error_type']=='http' and u['max_retries']==(3 if u['reason']=='Connection problem; retrying request' else 15)
   and type(u['attempt']) is int and 1<=u['attempt']<=u['max_retries'] and u['reason'] in reasons,'Unknown retry failure')
  if kind=='user_message_chunk':
   require(u['_meta']=={'modelId':'grok-4.7','promptIndex':0} and u['content']['type']=='text','User model/prompt index differs')
   users.append(u['content']['text'])
 require(len(users)==1 and (users[0]==prompt or (prompt.endswith('\n') and users[0]==prompt[:-1]))
  and counts==Counter({'user_message_chunk':1,'retry_state':source['retries'],**({'agent_thought_chunk':source['thoughts']} if source['thoughts'] else {})}),'Own failure update inventory differs')
 native_prompt=users[0]
 require(all(v['type'] in {'system','user'} for v in history),'Saved history contains assistant/tool activity')
 own=[v for v in history if v.get('prompt_index')==0]
 require(len(own)==1 and own[0]['type']=='user' and own[0]['content']==[{'type':'text','text':native_prompt}],'Saved history prompt differs')
 histories=[json.loads(v) for v in raws['prompt_history.jsonl'].splitlines()]
 require(len(histories)==1 and histories[0]['session_id']==session and histories[0]['is_bash'] is False
  and histories[0]['prompt']==native_prompt and created.timestamp()-120<=r.timestamp(histories[0]['timestamp']).timestamp()<=ended.timestamp(),
  'Saved prompt/session history differs')
 require(raws['system_prompt.txt']==b'Act as an isolated structured-output evaluator. Do not use memory, tools, web, plans, or subagents.',
  'Native isolated evaluator instruction differs')
 turns=[v for v in events if v['type']=='turn_started']
 require(len(turns)==1 and turns[0]['session_id']==session and turns[0]['model_id']=='grok-4.7'
  and turns[0]['turn_number']==0,'Own Grok turn differs')
 require(all(v['type'] in {'mcp_config_resolved','mcp_server_starting','mcp_server_connected','mcp_init_completed',
  'turn_started','loop_started','phase_changed','first_token'} for v in events),'Native completion/tool/unknown event')
 return {'session_id':session,'retry_updates':source['retries'],'thought_updates':source['thoughts'],
  'zero_assistant_messages':True,'completed_answer':False,'session_completion_present':False,
  'physical_contact_cardinality_proven':False,'native_retries_filtered':False,
  'native_prompt_projection':'exact' if native_prompt==prompt else 'single_terminal_lf_omission',
  'native_prompt_sha256':digest(native_prompt.encode()),'original_prompt_sha256':digest(prompt.encode())}


def failure_proof(ctx,row,saved=None):
 module=ctx['module'];s=ctx['source'];sample=module.sample_path(ctx['source_root'],row)
 terminal_raw=(sample/'terminal.json').read_bytes();terminal=json.loads(terminal_raw)
 require(digest(terminal_raw)==s['terminal_sha256'],'Exact authorized failed terminal differs')
 started,prompt,_,_,_=r.validate_started(module,sample,row,ctx['binding'],ctx['binding']['manifest_sha256'],ctx['root'],ctx['manifest'])
 require(terminal['accepted'] is False and terminal['no_resend'] is True and not any((sample/n).exists()
  for n in ('response.json','acceptance.json','native-envelope.json','effective-terminal.json','transport-reconciliation.json'))
  and not list(sample.glob('responses/*.message.json')),'Failure has a saved answer/descendant')
 raws={};locator=None
 if s['endpoint']=='sol':
  require(terminal['state']=='unadmitted_no_resend' and terminal['error_class']=='_ProviderAttemptFailure'
   and not (sample/'native-result.json').exists(),'Not the authorized native DNS failure')
  artifacts=terminal['provider_record']['provider_artifacts'];require(set(artifacts)=={'codex_events'},'Unexpected failure artifacts')
  raws['events.jsonl']=module.pinned(sample,artifacts['codex_events']['path'],artifacts['codex_events'])
  require(digest(raws['events.jsonl'])==s['events_sha256'],'Exact failed DNS events differ')
  thread=r.codex_receipts._rows(raws['events.jsonl'])[0][1]['thread_id'];home=Path(ctx['receipt']['config']['secondary_home_local_only'])
  require(digest(str(home.resolve()).encode())==ctx['binding']['runtime']['secondary_home_sha256'],'Secondary home differs')
  locator=Path(saved['native_locator_local_only']) if saved else r.codex_receipts.locate(home,thread,started_at=r.timestamp(started['time']))
  require(locator.resolve().is_relative_to(home.resolve()/'sessions'),'Own rollout leaves secondary home')
  raws['rollout.jsonl']=r.codex_receipts.read_bounded(locator)
  require(digest(raws['rollout.jsonl'])==s['rollout_sha256'],'Exact own DNS rollout differs')
  proof=sol_dns_proof(raws['events.jsonl'],raws['rollout.jsonl'],prompt=prompt.decode(),cwd=sample,started=started)
 else:
  native_raw=(sample/'native-result.json').read_bytes();native=json.loads(native_raw)
  require(digest(native_raw)==FAILURE_SHA and terminal['state']==native['state']=='ambiguous' and native['result'] is None
   and native['failure']['provider_error_type']=='GrokBuildWrapperFailure' and native['failure']['code']=='unclassified_after_launch'
   and native['failure']['revocation']=='not_applicable','Not the authorized ambiguous wrapper failure')
  session=json.loads((sample/'native-identity.json').read_bytes())['session_id'];require(session==s['session_id'],'Own failed session differs')
  home=Path(ctx['receipt']['config']['grok_sessions_root_local_only'])
  matches=[Path(saved['native_locator_local_only'])] if saved else list(home.glob('*/'+session))
  require(len(matches)==1 and matches[0].resolve().is_relative_to(home.resolve()),'Own native Grok locator differs');locator=matches[0]
  for name in ('summary.json','updates.jsonl','events.jsonl','chat_history.jsonl','tool_definitions.json','prompt_context.json'):
   raws[name]=r.codex_receipts.read_bounded(locator/name)
  raws['prompt_history.jsonl']=r.codex_receipts.read_bounded(locator.parent/'prompt_history.jsonl')
  raws['system_prompt.txt']=r.codex_receipts.read_bounded(locator/'system_prompt.txt')
  require(digest(raws['updates.jsonl'])==s['updates_sha256'],'Exact own retry updates differ')
  require(Path(json.loads(raws['summary.json'])['info']['cwd']).resolve()==Path(unquote(locator.parent.name)).resolve(),
   'Saved Grok session directory/cwd differs')
  proof=grok_failure_proof(raws,prompt=prompt.decode(),session=session,source=s,started=started)
 return {**proof,'policy':POLICY,'native_locator_local_only':str(locator),'native_commitments':{n:meta(v) for n,v in raws.items()},
  'terminal_sha256':digest(terminal_raw),'accepted':False,'new_votes':0,'no_resend':True},raws


def replay(ctx,row,output=None,binding=None):
 module=ctx['module'];sample=module.sample_path(output or ctx['source_root'],row)
 if output is None:
  return ctx['transport'].replay_sample(sample,row,ctx['receipt'],ctx,ctx['binding'])
 terminal,answer=module.replay(sample,row,ctx['manifest'],binding,ctx['root'],r.codex_receipts,ctx['subset'],ctx['validator'])
 return terminal['state'],answer,False


def build_plan(config,saved=None):
 ctx=context(config);s=ctx['source'];endpoint=s['endpoint'];module=ctx['module'];manifest=ctx['manifest'];source=ctx['source_root']
 rows=[row for row in manifest['requests'] if row['endpoint']==endpoint]
 reserved=ctx['receipt']['reserved_through'][endpoint]
 prefix=[deepcopy(e) for e in ctx['receipt']['prefix'] if e['endpoint']==endpoint]
 attempted=rows[reserved:s['through']]
 require({p.name for p in source.iterdir() if p.is_dir()}=={module.sample_path(source,row).name for row in attempted},
  'Stopped source prefix missing, extended or noncontiguous')
 proof=None;native={};identities=set()
 def native_identity(sample):
  if endpoint=='grok':return json.loads((sample/'native-identity.json').read_bytes())['session_id']
  event=next(sample.glob('responses/*.events.jsonl'))
  return r.codex_receipts._rows(event.read_bytes())[0][1]['thread_id']
 for entry in prefix:
  identity=native_identity(module.sample_path(Path(entry['source_root_local_only']),entry))
  require(identity not in identities,'Duplicate original native prefix identity');identities.add(identity)
 for row in attempted:
  state,answer,recovered=replay(ctx,row);sample=module.sample_path(source,row)
  if row['endpoint_ordinal']==s['through']:
   require(answer is None and not recovered,'Authorized failed slot has an admitted answer/descendant')
   proof,native=failure_proof(ctx,row,saved['failed_transport'] if saved else None)
  else:require(state in module.SETTLED,'Earlier source slot is unresolved; cannot reserve an in-flight prefix')
  entry={'endpoint':endpoint,'endpoint_ordinal':row['endpoint_ordinal'],'logical_sample_id':row['logical_sample_id'],
   'request_sha256':row['request_sha256'],'state':state,'source_root_local_only':str(source),
   'source_terminal_sha256':digest((sample/'terminal.json').read_bytes()),
   'source_inventory':{p.relative_to(sample).as_posix():meta(p.read_bytes()) for p in sorted(sample.rglob('*')) if p.is_file()},
   'new_votes':0,'no_resend':True}
  # Own completed receipts, not null Sol session placeholders, establish native uniqueness.
  identity=native_identity(sample)
  require(identity not in identities,'Duplicate native identity in stopped source prefix');identities.add(identity)
  entry['native_identity']=identity;prefix.append(entry)
 require([e['endpoint_ordinal'] for e in prefix]==list(range(1,s['through']+1))
  and len({e['logical_sample_id'] for e in prefix})==s['through'],'Original prefix identities differ')
 files={'implementation/continue_failed_transport.py':Path(__file__).read_bytes(),
  'implementation/continue_capacity.py':Path(c.__file__).read_bytes(),'implementation/reconcile.py':Path(r.__file__).read_bytes(),
  'implementation/source-collector.py':Path(ctx['transport'].__file__).read_bytes(),
  'implementation/native-reader.py':Path(r.codex_receipts.__file__).read_bytes(),
  'parent-manifest.json':(ctx['root']/'manifest.json').read_bytes(),'parent-reconciliation.json':ctx['parent_path'].read_bytes(),
  'source-job.json':(source/'job.json').read_bytes(),**{'failure/'+name:raw for name,raw in native.items()}}
 if endpoint=='sol':files['source-account.json']=(source/'account-binding.json').read_bytes()
 plan={'schema_version':1,'policy':POLICY,'config':config,'endpoint':endpoint,'study':s['study'],
  'collector_sha256':digest(Path(__file__).read_bytes()),'original_manifest_sha256':ctx['binding']['manifest_sha256'],
  'source_job_sha256':s['job_sha256'],'source_reconciliation_sha256':ctx['parent_sha256'],
  'reserved_through':s['through'],'prefix':prefix,'failed_transport':proof,
  'failure_counts_as_missing':True,'failed_transport_admitted':False,'new_votes':0,'new_provider_calls':0,'human_targets_opened':False,
  'full_planned_denominator':len(manifest['requests']),'endpoint_denominator':len(rows),
  'untouched_request_sha256s':[row['request_sha256'] for row in rows[s['through']:]],'source_binding':ctx['binding'],
  'original_workers':1,'execution_descendant':'bounded_endpoint_workers_v1','allowed_workers':[1,10],
  'project_endpoint_concurrency_limit':10,'project_headroom_allocated_by_controller':True,
  'timeout_seconds':900,'attempts_per_logical_sample':1,'automatic_retries':0,
  'human_label_gate':'all_original_planned_slots_verified_terminal_plus_explicit_postprediction_release_v1',
  'artifacts':{name:meta(raw) for name,raw in files.items()}}
 files['plan.json']=canonical(plan);return plan,files,ctx


def verify_plan(path,sha):
 raw=path.read_bytes();require(digest(raw)==sha,'Exact failure continuation plan differs');saved=json.loads(raw)
 for name,m in saved['artifacts'].items():require(meta((path.parent/name).read_bytes())==m,'Frozen continuation artifact differs')
 actual,_,ctx=build_plan(saved['config'],saved);require(actual==saved,'Original prefix/proof/implementation differs')
 return saved,ctx


def suffix_rows(plan,ctx):
 rows=[row for row in ctx['manifest']['requests'] if row['endpoint']==plan['endpoint'] and row['endpoint_ordinal']>plan['reserved_through']]
 require([row['request_sha256'] for row in rows]==plan['untouched_request_sha256s'],'Untouched original suffix differs');return rows


def validate_execution_route(source_route,route,expected_sha):
 require(expected_sha and digest(canonical(route).rstrip(b'\n'))==expected_sha,'Explicit execution route SHA differs')
 renewal={'cost_evidence','subscription_receipt_hash'}
 fixed=lambda value:{k:v for k,v in value.items() if k not in renewal}
 require(canonical(fixed(route))==canonical(fixed(source_route)) and renewal<=set(route),
  'Execution renewal changed a frozen non-evidence route control')


def job_binding(plan,sha,workers,execution_route=None,execution_sha=None):
 require(type(workers) is int and 1<=workers<=10,'Workers must be 1..10 within controller-allocated project headroom')
 binding=deepcopy(plan['source_binding'])
 binding.update(policy=POLICY,collector_sha256=digest(Path(__file__).read_bytes()),failed_transport_plan_sha256=sha,
  source_job_sha256=plan['source_job_sha256'],reserved_prefix=plan['reserved_through'],
  reserved_prefix_sha256=digest(canonical(plan['prefix'])),untouched_requests=len(plan['untouched_request_sha256s']),
  untouched_request_commitment_sha256=digest(canonical(plan['untouched_request_sha256s'])),
  workers=workers,original_workers=1,execution_descendant=plan['execution_descendant'],project_endpoint_concurrency_limit=10,
  full_planned_denominator=plan['full_planned_denominator'],saved_transport_recovery_enabled=False,
  failed_transport_admitted=False,failure_counts_as_missing=True,new_votes_from_reserved_failure=0)
 if plan['endpoint']=='grok':
  binding['source_route_sha256']=binding['route_sha256']
  if execution_route is not None:
   validate_execution_route(binding['route'],execution_route,execution_sha)
   binding.update(route=deepcopy(execution_route),route_sha256=execution_sha)
  else:require(execution_sha is None,'Execution route SHA has no selected route')
  binding.update(execution_route_sha256=binding['route_sha256'],
   execution_route_selection='explicit_cli_sha256' if execution_route is not None else 'source_frozen_route')
 return binding


def existing_binding(plan,sha,workers,output):
 if output.exists() and plan['endpoint']=='grok':
  job=json.loads((output/'job.json').read_bytes())
  if job.get('execution_route_selection')=='explicit_cli_sha256':
   return job_binding(plan,sha,workers,job['route'],job['execution_route_sha256'])
 return job_binding(plan,sha,workers)


def validate_output(output,ctx,plan_root=None):
 protected=[r.REPO,ctx['root'],ctx['source_root'],ctx['parent_path'].parent,
  *(Path(s['root_local_only']) for s in ctx['receipt']['config']['sources']),
  Path(ctx['receipt']['config']['secondary_home_local_only']),Path(ctx['receipt']['config']['grok_sessions_root_local_only'])]
 if plan_root:protected.append(plan_root)
 require(all(not output.is_relative_to(p.resolve()) and not p.resolve().is_relative_to(output) for p in protected),
  'Continuation overlaps immutable source/native inputs')


def inventory(plan,ctx,output,binding):
 rows=suffix_rows(plan,ctx);pending=[];states=[]
 if output.exists():
  require(json.loads((output/'job.json').read_bytes())==binding,'Continuation execution job differs')
  require({p.name for p in output.iterdir() if p.is_dir()}<={ctx['module'].sample_path(output,row).name for row in rows},'Reserved/unknown occupied suffix slot')
 for row in rows:
  sample=ctx['module'].sample_path(output,row)
  if not sample.exists():pending.append(row);continue
  state,_,_=replay(ctx,row,output,binding);states.append(state)
 return pending,states


def gate(plan,states,pending,other_plan=None,other_states=(),other_pending=(),explicit=False):
 require(not other_plan or (other_plan['original_manifest_sha256']==plan['original_manifest_sha256']
  and other_plan['full_planned_denominator']==plan['full_planned_denominator']
  and other_plan.get('endpoint','sol')!=plan['endpoint']),'Other continuation is not the exact complementary endpoint')
 verified=len(plan['prefix'])+len(states)+(len(other_plan['prefix'])+len(other_states) if other_plan else 0)
 complete=bool(other_plan) and not pending and not other_pending and verified==plan['full_planned_denominator']
 return {'policy':plan['human_label_gate'],'planned':plan['full_planned_denominator'],'verified_terminal':verified,
  'untouched':len(pending)+len(other_pending),'remaining_join_limitation':None if other_plan else 'Exact complementary endpoint continuation required',
  'all_original_slots_verified_terminal':complete,'explicit_postprediction_release':explicit,'human_release_eligible':complete and explicit,
  'failed_transport_admitted':False,'human_targets_opened':False,'provider_calls':0}


def dispatch(pending,call,workers,stopped,settled):
 """Stop admission, then drain already-started bounded calls; never retry a slot."""
 require(1<=workers<=10,'Workers outside bounded endpoint allocation')
 rows=iter(pending);active={};failed=False;observed=[]
 with ThreadPoolExecutor(max_workers=workers) as pool:
  def fill():
   while len(active)<workers and not failed and not stopped():
    row=next(rows,None)
    if row is None:break
    active[pool.submit(call,row)]=row
  fill()
  while active:
   done,_=wait(active,return_when=FIRST_COMPLETED)
   for future in done:
    row=active.pop(future)
    try:state=future.result()
    except Exception:failed=True;state='unresolved_local_failure'
    observed.append((row,state));failed=failed or state not in settled
   fill()
 return observed,failed or stopped()


def reviewed_route(binding,route_root):
 require(route_root is not None,'Reviewed Grok route root required')
 route=next(v for v in json.loads((route_root/'routes.json').read_bytes())['routes'] if v['name']==binding['route']['name'])
 require(canonical(route)==canonical(binding['route']) and digest(canonical(route).rstrip(b'\n'))==binding['route_sha256'],
  'Exact selected execution route differs')


def select_execution_route(plan,route_root,execution_sha):
 require(route_root is not None,'Reviewed Grok route root required')
 route=next(v for v in json.loads((route_root/'routes.json').read_bytes())['routes'] if v['name']==plan['source_binding']['route']['name'])
 if execution_sha:validate_execution_route(plan['source_binding']['route'],route,execution_sha)
 else:require(canonical(route)==canonical(plan['source_binding']['route']),'Renewed route requires explicit execution-route SHA')
 return route


def collect(plan,ctx,output,binding,route_root,limit=None):
 pending,states=inventory(plan,ctx,output,binding);module=ctx['module']
 require(all(state in module.SETTLED for state in states),'Occupied failed suffix slot cannot be resent or silently skipped')
 if (output/'STOP').exists():module.note_stop(output);return 3
 if not pending:return 0
 helper=call_codex=broker=None
 if plan['endpoint']=='sol':
  if plan['study']=='mfa':source=ctx['manifest'];runner=ctx['runner']
  else:
   source=module.source_settings(ctx['manifest'],ctx['root'])
   from hbqrs import runner
  helper=r.load('failure_suffix_secondary_helper',Path(source['external_pins']['secondary_helper_path_local_only']))
  env=module.secondary_binding(source,helper);os.environ.clear();os.environ.update(env)
  sys.path.insert(0,str(ctx['tools']));from adaptive_settings.account_probe import probe
  module.secondary_binding(source,helper,probe(helper.CLI));call_codex=runner._call_codex
 else:
  reviewed_route(binding,route_root)
  sys.path.insert(0,str(ctx['tools']));from model_work_queue.broker import Broker
  broker=Broker(route_root)
 if not output.exists():output.mkdir(parents=True,exist_ok=False);module.record(output/'job.json',binding)
 if plan['endpoint']=='sol':
  account=module.account_receipt(binding)
  if (output/'account-binding.json').exists():require(json.loads((output/'account-binding.json').read_bytes())==account,'Secondary account differs')
  else:module.record(output/'account-binding.json',account)
 stop=threading.Event()
 def stopped():return stop.is_set() or (output/'STOP').exists()
 def call(row):
  if stopped():return 'dispatch_stopped_before_slot'
  if plan['endpoint']=='grok' and not module.grok_contact_allowed():stop.set();return 'campaign_deadline_prevents_contact'
  try:
   state=module.collect_one(row,ctx['manifest'],binding,ctx['root'],output,ctx['subset'],ctx['validator'],r.codex_receipts,helper,call_codex,broker)
   actual,_,_=replay(ctx,row,output,binding);require(actual==state,'New terminal replay differs')
  except BaseException:stop.set();raise
  if state not in module.SETTLED:stop.set()
  print(json.dumps({'ordinal':row['endpoint_ordinal'],'state':state}),flush=True);return state
 _,failed=dispatch(pending[:limit],call,binding['workers'],stopped,module.SETTLED)
 if (output/'STOP').exists():module.note_stop(output)
 return 3 if failed else 0


def main():
 parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='mode',required=True)
 prep=sub.add_parser('prepare');prep.add_argument('--source',choices=SOURCES,required=True)
 prep.add_argument('--program-root',type=Path,required=True);prep.add_argument('--output-root',type=Path,required=True);prep.add_argument('--dry-run',action='store_true')
 for mode in ('collect','label-check'):
  cmd=sub.add_parser(mode);cmd.add_argument('--plan',type=Path,required=True);cmd.add_argument('--plan-sha256',required=True)
  cmd.add_argument('--results-dir',type=Path,required=True);cmd.add_argument('--workers',type=int,default=1)
  if mode=='collect':
   cmd.add_argument('--route-root',type=Path);cmd.add_argument('--execution-route-sha256')
   cmd.add_argument('--validate-only',action='store_true');cmd.add_argument('--limit',type=int)
  else:
   cmd.add_argument('--other-plan',type=Path);cmd.add_argument('--other-plan-sha256');cmd.add_argument('--other-results-dir',type=Path)
   cmd.add_argument('--explicit-postprediction-release',action='store_true')
 args=parser.parse_args()
 if args.mode=='prepare':
  config={'source':args.source,'program_root_local_only':str(args.program_root.resolve())}
  plan,files,ctx=build_plan(config);output=args.output_root.resolve();validate_output(output,ctx);require(not output.exists(),'Plan output must be fresh')
  if not args.dry_run:
   for name,raw in files.items():write(output/name,raw)
  print(json.dumps({'state':'provider_free_failure_plan','source':args.source,'plan_sha256':digest(files['plan.json']),
   'reserved_through':plan['reserved_through'],'untouched':len(plan['untouched_request_sha256s']),
   'full_planned_denominator':plan['full_planned_denominator'],'prefix_states':dict(Counter(e['state'] for e in plan['prefix'])),
   'failed_transport_admitted':False,'new_votes':0,'provider_calls':0,'human_targets_opened':False,'output_written':not args.dry_run}));return 0
 plan,ctx=verify_plan(args.plan,args.plan_sha256);output=args.results_dir.resolve();validate_output(output,ctx,args.plan.parent)
 if args.mode=='collect' and plan['endpoint']=='grok':
  route=select_execution_route(plan,args.route_root,args.execution_route_sha256)
  binding=job_binding(plan,args.plan_sha256,args.workers,route if args.execution_route_sha256 else None,args.execution_route_sha256)
 else:
  if args.mode=='collect':require(args.execution_route_sha256 is None,'Execution route applies only to Grok')
  binding=existing_binding(plan,args.plan_sha256,args.workers,output)
 if args.mode=='label-check':
  pending,states=inventory(plan,ctx,output,binding)
  other=None;other_pending=other_states=()
  if args.other_plan:
   require(args.other_plan_sha256 and args.other_results_dir,'Complementary exact plan/results pins required')
   raw=json.loads(args.other_plan.read_bytes())
   if raw['policy']==c.POLICY:
    require(plan['study']=='mfa' and raw['config']['study']=='mfa','Capacity join supports only original MFA Sol')
    other,other_ctx=c.verify_plan(args.other_plan,args.other_plan_sha256)
    other_binding=c.job_binding(other,args.other_plan_sha256)
    other_pending,other_states=c.inventory(other,other_ctx,args.other_results_dir.resolve(),other_binding)
   else:
    other,other_ctx=verify_plan(args.other_plan,args.other_plan_sha256)
    job=json.loads((args.other_results_dir/'job.json').read_bytes()) if args.other_results_dir.exists() else {'workers':1}
    other_binding=existing_binding(other,args.other_plan_sha256,job['workers'],args.other_results_dir)
    other_pending,other_states=inventory(other,other_ctx,args.other_results_dir.resolve(),other_binding)
  print(json.dumps(gate(plan,states,pending,other,other_states,other_pending,args.explicit_postprediction_release)));return 0
 require(args.limit is None or args.limit>0,'Positive contact limit required')
 if args.validate_only:
  if plan['endpoint']=='grok':reviewed_route(binding,args.route_root)
  pending,states=inventory(plan,ctx,output,binding)
  print(json.dumps({'state':'provider_free_validated','endpoint':plan['endpoint'],'workers':args.workers,
   'reserved_through':plan['reserved_through'],'untouched':len(pending),'occupied_suffix':len(states),
   'full_planned_denominator':plan['full_planned_denominator'],'provider_calls':0,'human_targets_opened':False}));return 0
 return collect(plan,ctx,output,binding,args.route_root.resolve() if args.route_root else None,args.limit)


if __name__=='__main__':raise SystemExit(main())
