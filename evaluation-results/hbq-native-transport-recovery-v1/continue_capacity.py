"""Reserve proved Sol capacity failures as missing; collect only untouched suffixes."""
from copy import deepcopy
from collections import Counter
from datetime import datetime
import argparse
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import reconcile as r

POLICY='capacity_missing_untouched_suffix_v1'
CAPACITY='Selected model is at capacity. Please try a different model.'
SOURCES={
    'mfa':{'manifest':'mfa-canary/frozen-001/manifest.json','manifest_sha256':'ce8a735c40a18c676c82cc0585b36f91cbb6a9faa98ac2289f86fdfb52cadd80',
        'source':'mfa-canary/transport-sol-001','job_sha256':'9fbfa0e1143ade33228ad03f3085eec871c1825fc392c668c737913e1e199b42',
        'collector_sha256':'20f654ab4e7d09c2555b45f172147664d473109b8072fa78f72de1f580b03313',
        'reconciliation':'mfa-canary/transport-reconciliation-001/reconciliation.json',
        'reconciliation_sha256':'a59f3940ec56097f711c1ad0e27ee76deb3424bf3210737c6d5725ad691995cc',
        'through':229,'endpoint_denominator':434,'full_denominator':868},
    'p4':{'manifest':'longform-dependency/judging-frozen-001/manifest.json','manifest_sha256':'d0cb6589924a4900b123206f40595035a6d792c623bac1c8303de9d95bac1ac4',
        'source':'longform-dependency/judging-sol-001','job_sha256':'d1ab2ec9c8dcbf10351d109e4d4e97793071a7678f0a223f6fb23fc19b9108e3',
        'collector_sha256':'0425421d9cdcbcc706c69e5eae16724079ddd05d0d670962707105724721525f',
        'through':97,'endpoint_denominator':232,'full_denominator':464}}
canonical,digest,require=r.canonical,r.digest,r.require


def meta(raw):return {'sha256':digest(raw),'bytes':len(raw)}


def write(path,raw):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('xb') as stream:stream.write(raw)


def record(path,value):write(path,canonical(value))


def context(config):
    study=config['study'];s=SOURCES[study];program=Path(config['program_root_local_only']);tools=Path(config['tools_root_local_only'])
    manifest_path=program/s['manifest'];source_root=program/s['source']
    require(digest(manifest_path.read_bytes())==s['manifest_sha256'] and digest((source_root/'job.json').read_bytes())==s['job_sha256'],'Original manifest/job differs')
    if study=='mfa':
        transport=r.load('capacity_mfa_transport',HERE/'collector.py')
        require(digest(Path(transport.__file__).read_bytes())==s['collector_sha256'],'Frozen MFA transport differs')
        receipt,ctx=r.verify(program/s['reconciliation'],s['reconciliation_sha256'])
        binding=transport.verify_job_binding(source_root,receipt,s['reconciliation_sha256'],ctx,'sol')
        ctx.update(transport=transport,receipt=receipt)
    else:
        module=r.load('capacity_p4_collector',r.REPO/'evaluation-results/hbq-longform-dependency-pilot-v1/collector.py')
        manifest,root,subset,validator,receipts=module.load_manifest(manifest_path,s['manifest_sha256'],s['collector_sha256'],tools)
        binding=json.loads((source_root/'job.json').read_bytes())
        require(binding==module.job_binding(manifest,root,s['manifest_sha256'],'sol',tools,collector_sha=s['collector_sha256']),'Frozen P4 job differs')
        require((source_root/'frozen-manifest.json').read_bytes()==manifest_path.read_bytes(),'Saved original P4 manifest differs')
        ctx={'module':module,'manifest':manifest,'root':root,'subset':subset,'validator':validator,'tools':tools,'receipts':receipts}
    require(ctx['tools'].resolve()==tools.resolve(),'Tools binding differs')
    ctx.update(source_root=source_root,binding=binding,config=config,source=s)
    return ctx


def capacity_projection(events_raw,rollout_raw,*,prompt,cwd,started):
    """A failure receipt, deliberately distinct from a completed-answer receipt."""
    reader=r.codex_receipts;events=[row for _,row in reader._rows(events_raw)]
    require(events[0].get('type')=='thread.started','Capacity events lack initial thread')
    thread=reader._uuid(events[0].get('thread_id'));remaining=events[1:]
    if remaining and remaining[0].get('type')=='item.completed':
        item=remaining.pop(0).get('item',{})
        require(item.get('type')=='error' and item.get('message')==reader.STARTUP_DIAGNOSTIC,'Unknown startup diagnostic')
    require(remaining==[{'type':'turn.started'},{'type':'error','message':CAPACITY},
        {'type':'turn.failed','error':{'message':CAPACITY}}],'Native events are not the exact terminal capacity failure')
    rows=reader._rows(rollout_raw);require(all(isinstance(v.get('payload'),dict) for _,v in rows),'Malformed rollout payload')
    metas=[(line,v['payload']) for line,v in rows if v['type']=='session_meta']
    starts=[(line,v['payload']) for line,v in rows if v['type']=='event_msg' and v['payload'].get('type')=='task_started']
    contexts=[(line,v['payload']) for line,v in rows if v['type']=='turn_context']
    ends=[(line,v['payload']) for line,v in rows if v['type']=='event_msg' and v['payload'].get('type')=='task_complete']
    require(len(metas)==len(starts)==len(contexts)==len(ends)==1,'Capacity rollout requires one own turn')
    m,st,c,end=metas[0][1],starts[0][1],contexts[0][1],ends[0][1];turn=reader._uuid(st.get('turn_id'))
    require(m.get('id')==thread and m.get('source')=='exec' and m.get('model_provider')=='openai'
        and m.get('forked_from_id') is None and Path(m.get('cwd','')).resolve()==cwd.resolve(),'Own native session differs')
    require(c.get('turn_id')==end.get('turn_id')==turn and c.get('model')=='gpt-6.1-sol'
        and c.get('effort')=='high' and c.get('model_provider','openai')=='openai'
        and Path(c.get('cwd','')).resolve()==cwd.resolve(),'Own native Sol/high context differs')
    require('last_agent_message' in end and end['last_agent_message'] is None
        and end.get('error')=={'message':CAPACITY,'codex_error_info':'server_overloaded'},'Capacity completion has a final or different error')
    prompts=[];allowed={'session_meta','turn_context','event_msg','response_item','world_state','token_usage_record'}
    for line,v in rows:
        kind,payload=v['type'],v['payload'];metadata=payload.get('internal_chat_message_metadata_passthrough',{})
        require(kind in allowed and isinstance(metadata,dict) and payload.get('turn_id',turn)==turn
            and metadata.get('turn_id',turn)==turn and payload.get('thread_id',thread)==thread,'Foreign or unsupported native record')
        if kind=='event_msg':
            require(payload.get('type') in {'task_started','task_complete','token_count','item_started','item_updated','item_completed'},'Unknown native event')
            if 'item' in payload:require(isinstance(payload['item'],dict) and payload['item'].get('type')=='UserMessage','Capacity rollout contains assistant/tool activity')
        if kind=='response_item':
            require(payload.get('type')=='message' and payload.get('role') in {'user','developer','system'},'Capacity rollout contains assistant/tool activity')
            if payload['role']=='user':
                kinds=metadata.get('content_item_kinds')
                if kinds==['user.text']:prompts.append((line,reader._text(payload,'input_text')))
                else:require(kinds==['environments.environment_context'],'Unexpected native user message')
    require(len(prompts)==1 and prompts[0][1]==prompt,'Own submitted prompt differs')
    selected=[metas[0][0],starts[0][0],contexts[0][0],prompts[0][0],ends[0][0]]
    positions=[[line for line,_ in rows].index(line) for line in selected]
    require(positions[0]==0 and positions==sorted(set(positions)),'Own failure lifecycle order differs')
    at=r.timestamp(started['time']);native_start=r.timestamp(st['started_at']);native_end=r.timestamp(end['completed_at'])
    require(native_start.date()==at.date() and native_start<=native_end and r.timestamp(rows[0][1]['timestamp'])<=native_end,'Own failure time differs')
    return {'policy':POLICY,'thread_id':thread,'turn_id':turn,'model':'gpt-6.1-sol','reasoning':'high',
        'cwd':str(cwd.resolve()),'prompt_sha256':digest(prompt.encode()),'events_sha256':digest(events_raw),
        'rollout_sha256':digest(rollout_raw),'selected_line_sha256':[digest(line) for line in selected],
        'error_code':'server_overloaded','zero_assistant_messages':True,'null_final':True,
        'completed_answer':False,'accepted':False,'new_votes':0,'no_resend':True,
        'provider_backend_model_attested':False,'physical_contact_cardinality_proven':False}


def original_replay(ctx,row,root=None,binding=None):
    module=ctx['module'];output=root or ctx['source_root'];binding=binding or ctx['binding'];sample=module.sample_path(output,row)
    if ctx['config']['study']=='mfa' and root is None:
        state,answer,recovered=ctx['transport'].replay_sample(sample,row,ctx['receipt'],ctx,binding)
        return state,answer,recovered
    terminal,answer=module.replay(sample,row,ctx['manifest'],binding,ctx['root'],r.codex_receipts,ctx['subset'],ctx['validator'])
    return terminal['state'],answer,False


def failure_proof(ctx,row,saved=None):
    module=ctx['module'];sample=module.sample_path(ctx['source_root'],row);terminal=json.loads((sample/'terminal.json').read_bytes())
    # P4 retains account admission in its native transport predecessor.
    start_reader=module if hasattr(module,'account_receipt') else SimpleNamespace(inputs=module.inputs,account_receipt=module.t.account_receipt)
    started,prompt,_,_,_=r.validate_started(start_reader,sample,row,ctx['binding'],ctx['source']['manifest_sha256'],ctx['root'],ctx['manifest'])
    require(terminal['state']=='unadmitted_no_resend' and terminal['accepted'] is False and terminal['no_resend'] is True
        and terminal['error_class']=='_ProviderAttemptFailure','Not an eligible original capacity failure')
    require(not any((sample/name).exists() for name in ('response.json','native-result.json','acceptance.json','effective-terminal.json','transport-reconciliation.json')),'Failure has a saved answer/descendant')
    artifacts=terminal['provider_record']['provider_artifacts'];require(set(artifacts)=={'codex_events'},'Unexpected native failure artifacts')
    event_meta=artifacts['codex_events'];events=module.pinned(sample,event_meta['path'],event_meta)
    thread=r.codex_receipts._uuid(r.codex_receipts._rows(events)[0][1].get('thread_id'))
    if ctx['config']['study']=='mfa':home=Path(ctx['receipt']['config']['secondary_home_local_only']).resolve()
    else:
        pins=module.source_settings(ctx['manifest'],ctx['root'])['external_pins'];home=Path(pins['collection_home_path_local_only']).resolve()
        require(terminal['job_sha256']==started['job_sha256'] and terminal['attempt_id']==started['attempt_id'],'P4 failed attempt identity differs')
    require(digest(str(home).encode())==ctx['binding']['runtime']['secondary_home_sha256'],'Own secondary home differs')
    path=Path(saved['rollout_locator_local_only']) if saved else r.codex_receipts.locate(home,thread,started_at=r.timestamp(started['time']))
    require(path.resolve().is_relative_to(home/'sessions'),'Own capacity rollout leaves secondary home')
    rollout=r.codex_receipts.read_bounded(path)
    proof=capacity_projection(events,rollout,prompt=prompt.decode(),cwd=sample,started=started)
    return {**proof,'rollout_locator_local_only':str(path),'terminal_sha256':digest((sample/'terminal.json').read_bytes()),
        'attempt_started_sha256':digest((sample/'attempt-started.json').read_bytes())},events,rollout


def build_plan(config,saved=None):
    ctx=context(config);s=ctx['source'];module=ctx['module'];manifest=ctx['manifest'];source=ctx['source_root']
    rows=[row for row in manifest['requests'] if row['endpoint']=='sol']
    require(len(manifest['requests'])==s['full_denominator'] and len(rows)==s['endpoint_denominator'],'Full original denominators differ')
    prefix=[];reserved=0
    if config['study']=='mfa':
        reserved=ctx['receipt']['reserved_through']['sol']
        prefix=[{k:e[k] for k in ('endpoint_ordinal','logical_sample_id','request_sha256','state','source_root_local_only','source_terminal_sha256')}
            for e in ctx['receipt']['prefix'] if e['endpoint']=='sol']
    attempted=rows[reserved:s['through']]
    expected={module.sample_path(source,row).name for row in attempted}
    require({p.name for p in source.iterdir() if p.is_dir()}==expected,'Attempted source prefix is missing, extended or noncontiguous')
    capacity=None;events=rollout=None
    for row in attempted:
        state,answer,recovered=original_replay(ctx,row)
        if row['endpoint_ordinal']==s['through']:
            require(state=='unadmitted_no_resend' and answer is None and not recovered,'Reserved endpoint is not the capacity failure')
            capacity,events,rollout=failure_proof(ctx,row,saved.get('capacity_failure') if saved else None)
        else:require(state in module.SETTLED,'Earlier prefix includes an unresolved/unknown native failure')
        sample=module.sample_path(source,row)
        prefix.append({'endpoint_ordinal':row['endpoint_ordinal'],'logical_sample_id':row['logical_sample_id'],
            'request_sha256':row['request_sha256'],'state':state,'source_root_local_only':str(source),
            'source_terminal_sha256':digest((sample/'terminal.json').read_bytes()),
            'source_inventory':{p.relative_to(sample).as_posix():meta(p.read_bytes()) for p in sorted(sample.rglob('*')) if p.is_file()},
            'new_votes':0,'no_resend':True})
    require([e['endpoint_ordinal'] for e in prefix]==list(range(1,s['through']+1))
        and len({e['logical_sample_id'] for e in prefix})==s['through'],'Reserved original prefix differs')
    files={'implementation/continue_capacity.py':Path(__file__).read_bytes(),'parent-manifest.json':(ctx['root']/'manifest.json').read_bytes(),
        'source-job.json':(source/'job.json').read_bytes(),'source-account.json':(source/'account-binding.json').read_bytes(),
        'capacity/events.jsonl':events,'capacity/rollout.jsonl':rollout}
    if config['study']=='mfa':
        files['parent-reconciliation.json']=(Path(config['program_root_local_only'])/s['reconciliation']).read_bytes()
        files['implementation/source-collector.py']=Path(ctx['transport'].__file__).read_bytes()
        files['implementation/reconcile.py']=Path(r.__file__).read_bytes()
    else:files['implementation/source-collector.py']=Path(module.__file__).read_bytes()
    files['implementation/native-reader.py']=Path(r.codex_receipts.__file__).read_bytes()
    plan={'schema_version':1,'policy':POLICY,'config':config,'collector_sha256':digest(Path(__file__).read_bytes()),
        'original_manifest_sha256':s['manifest_sha256'],'source_job_sha256':s['job_sha256'],
        'original_runtime_collector_sha256':s['collector_sha256'],'reserved_through':s['through'],'prefix':prefix,
        'capacity_failure':capacity,'reserved_failure_state':'unadmitted_no_resend','failure_counts_as_missing':True,
        'capacity_failure_admitted':False,'new_votes':0,'new_provider_calls':0,'human_targets_opened':False,
        'full_planned_denominator':s['full_denominator'],'endpoint_denominator':s['endpoint_denominator'],
        'untouched_request_sha256s':[row['request_sha256'] for row in rows[s['through']:]],
        'source_binding':ctx['binding'],'timeout_seconds':900,'workers':1,'attempts_per_logical_sample':1,'automatic_retries':0,
        'human_label_gate':'all_original_planned_slots_verified_terminal_plus_explicit_postprediction_release_v1',
        'artifacts':{name:meta(raw) for name,raw in files.items()}}
    files['plan.json']=canonical(plan);return plan,files,ctx


def verify_plan(path,sha):
    raw=path.read_bytes();require(digest(raw)==sha,'Exact capacity plan differs');saved=json.loads(raw)
    for name,m in saved['artifacts'].items():require(meta((path.parent/name).read_bytes())==m,'Frozen capacity plan artifact differs')
    actual,_,ctx=build_plan(saved['config'],saved)
    require(actual==saved,'Original prefix/native proof/continuation implementation differs')
    return actual,ctx


def suffix_rows(plan,ctx):
    rows=[row for row in ctx['manifest']['requests'] if row['endpoint']=='sol' and row['endpoint_ordinal']>plan['reserved_through']]
    require([row['request_sha256'] for row in rows]==plan['untouched_request_sha256s'],'Untouched suffix differs');return rows


def job_binding(plan,sha):
    binding=deepcopy(plan['source_binding'])
    binding.update(policy=POLICY,collector_sha256=digest(Path(__file__).read_bytes()),capacity_plan_sha256=sha,
        source_job_sha256=plan['source_job_sha256'],reserved_prefix=plan['reserved_through'],
        reserved_prefix_sha256=digest(canonical(plan['prefix'])),untouched_requests=len(plan['untouched_request_sha256s']),
        untouched_request_commitment_sha256=digest(canonical(plan['untouched_request_sha256s'])),
        full_planned_denominator=plan['full_planned_denominator'],capacity_failure_admitted=False,
        failure_counts_as_missing=True,saved_transport_recovery_enabled=False,new_votes_from_reserved_failure=0)
    return binding


def validate_output(output,ctx,plan_root=None):
    protected=[r.REPO,ctx['root'],ctx['source_root'],Path(ctx['config']['program_root_local_only'])/ctx['source']['source']]
    if ctx['config']['study']=='mfa':
        program=Path(ctx['config']['program_root_local_only']);protected.append((program/ctx['source']['reconciliation']).parent)
        protected.extend(Path(s['root_local_only']) for s in ctx['receipt']['config']['sources'])
        protected.extend([Path(ctx['receipt']['config']['secondary_home_local_only']),
            Path(ctx['receipt']['config']['context_reconciliation']['path_local_only']).parent])
    else:
        pins=ctx['module'].source_settings(ctx['manifest'],ctx['root'])['external_pins']
        protected.append(Path(pins['collection_home_path_local_only']))
    if plan_root:protected.append(plan_root)
    require(all(not output.is_relative_to(p.resolve()) and not p.resolve().is_relative_to(output) for p in protected),'Continuation overlaps immutable inputs')


def inventory(plan,ctx,output,binding):
    rows=suffix_rows(plan,ctx);pending=[];states=[]
    if output.exists():
        require(json.loads((output/'job.json').read_bytes())==binding,'Capacity suffix job differs')
        require({p.name for p in output.iterdir() if p.is_dir()}<={ctx['module'].sample_path(output,row).name for row in rows},'Suffix includes reserved/unknown slot')
    for row in rows:
        if not ctx['module'].sample_path(output,row).exists():pending.append(row);continue
        state,_,_=original_replay(ctx,row,output,binding);states.append(state)
    return pending,states


def label_check(plan,ctx,output,binding,grok_output,explicit):
    pending,states=inventory(plan,ctx,output,binding);s=ctx['source'];known=len(plan['prefix'])+len(states)
    other_rows=[row for row in ctx['manifest']['requests'] if row['endpoint']=='grok'];other_states=[];other_pending=0
    if ctx['config']['study']=='mfa':
        prior=ctx['receipt']['reserved_through']['grok'];other_states=[e['state'] for e in ctx['receipt']['prefix'] if e['endpoint']=='grok']
        if grok_output.exists():other_binding=ctx['transport'].verify_job_binding(grok_output,ctx['receipt'],s['reconciliation_sha256'],ctx,'grok')
        for row in other_rows[prior:]:
            if not ctx['module'].sample_path(grok_output,row).exists():other_pending+=1;continue
            state,_,_=ctx['transport'].replay_sample(ctx['module'].sample_path(grok_output,row),row,ctx['receipt'],ctx,other_binding);other_states.append(state)
    else:
        if grok_output.exists():
            other_binding=json.loads((grok_output/'job.json').read_bytes())
            require(other_binding==ctx['module'].job_binding(ctx['manifest'],ctx['root'],s['manifest_sha256'],'grok',ctx['tools'],other_binding.get('route'),s['collector_sha256'],other_binding['payload_classification']),'Original Grok job differs')
        for row in other_rows:
            if not ctx['module'].sample_path(grok_output,row).exists():other_pending+=1;continue
            state,_,_=original_replay(ctx,row,grok_output,other_binding);other_states.append(state)
    complete=not pending and not other_pending and known+len(other_states)==s['full_denominator']
    return {'policy':plan['human_label_gate'],'planned':s['full_denominator'],'verified_terminal':known+len(other_states),
        'untouched':len(pending)+other_pending,'all_original_slots_verified_terminal':complete,
        'explicit_postprediction_release':explicit,'human_release_eligible':complete and explicit,
        'human_targets_opened':False,'provider_calls':0,'reserved_capacity_failure_admitted':False,
        'terminal_states':dict(Counter([e['state'] for e in plan['prefix']]+states+other_states))}


def main():
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='mode',required=True)
    prep=sub.add_parser('prepare');prep.add_argument('--study',choices=SOURCES,required=True)
    prep.add_argument('--program-root',type=Path,required=True);prep.add_argument('--tools-root',type=Path,default=Path('C:/Users/Haile/.codex/tools'))
    prep.add_argument('--output-root',type=Path,required=True);prep.add_argument('--dry-run',action='store_true')
    for mode in ('collect','label-check'):
        command=sub.add_parser(mode);command.add_argument('--plan',type=Path,required=True);command.add_argument('--plan-sha256',required=True)
        command.add_argument('--results-dir',type=Path,required=True)
        if mode=='collect':command.add_argument('--validate-only',action='store_true');command.add_argument('--limit',type=int)
        else:command.add_argument('--grok-results-dir',type=Path,required=True);command.add_argument('--explicit-postprediction-release',action='store_true')
    args=parser.parse_args()
    if args.mode=='prepare':
        config={'study':args.study,'program_root_local_only':str(args.program_root.resolve()),'tools_root_local_only':str(args.tools_root.resolve())}
        plan,files,ctx=build_plan(config);output=args.output_root.resolve();validate_output(output,ctx)
        require(not output.exists(),'Capacity plan output must be fresh')
        if not args.dry_run:
            for name,raw in files.items():write(output/name,raw)
        print(json.dumps({'state':'provider_free_capacity_plan','study':args.study,'plan_sha256':digest(files['plan.json']),
            'reserved_through':plan['reserved_through'],'untouched':len(plan['untouched_request_sha256s']),
            'full_planned_denominator':plan['full_planned_denominator'],'prefix_states':dict(Counter(e['state'] for e in plan['prefix'])),
            'capacity_failure_admitted':False,'new_votes':0,'provider_calls':0,'human_targets_opened':False,'output_written':not args.dry_run}));return 0
    plan,ctx=verify_plan(args.plan,args.plan_sha256);output=args.results_dir.resolve();validate_output(output,ctx,args.plan.parent)
    binding=job_binding(plan,args.plan_sha256)
    if args.mode=='label-check':
        print(json.dumps(label_check(plan,ctx,output,binding,args.grok_results_dir.resolve(),args.explicit_postprediction_release)));return 0
    require(args.limit is None or args.limit>0,'Positive contact limit required')
    pending,states=inventory(plan,ctx,output,binding)
    if args.validate_only:
        print(json.dumps({'state':'provider_free_validated','reserved_through':plan['reserved_through'],'untouched':len(pending),
            'suffix_terminal':len(states),'full_planned_denominator':plan['full_planned_denominator'],'provider_calls':0,'human_targets_opened':False}));return 0
    module=ctx['module'];require(all(state in module.SETTLED for state in states),'New native failure remains occupied; no resend')
    if (output/'STOP').exists():module.note_stop(output);return 3
    if not pending:return 0
    if ctx['config']['study']=='mfa':source=ctx['manifest'];pins=source['external_pins'];runner=ctx['runner']
    else:
        source=module.source_settings(ctx['manifest'],ctx['root']);pins=source['external_pins']
        from hbqrs import runner
    helper=r.load('capacity_secondary_helper',Path(pins['secondary_helper_path_local_only']))
    secondary=module.secondary_binding if hasattr(module,'secondary_binding') else module.t.secondary_binding
    account=module.account_receipt if hasattr(module,'account_receipt') else module.t.account_receipt
    env=secondary(source,helper);os.environ.clear();os.environ.update(env)
    sys.path.insert(0,str(ctx['tools']));from adaptive_settings.account_probe import probe
    secondary(source,helper,probe(helper.CLI))
    if not output.exists():output.mkdir(parents=True,exist_ok=False);module.record(output/'job.json',binding)
    expected=account(binding)
    if (output/'account-binding.json').exists():require(json.loads((output/'account-binding.json').read_bytes())==expected,'Suffix secondary account differs')
    else:module.record(output/'account-binding.json',expected)
    for row in pending[:args.limit]:
        if (output/'STOP').exists():module.note_stop(output);return 3
        state=module.collect_one(row,ctx['manifest'],binding,ctx['root'],output,ctx['subset'],ctx['validator'],r.codex_receipts,helper,runner._call_codex)
        actual,_,_=original_replay(ctx,row,output,binding);require(actual==state,'New terminal replay differs')
        print(json.dumps({'ordinal':row['endpoint_ordinal'],'state':state}),flush=True)
        if state not in module.SETTLED:return 3
    return 0


if __name__=='__main__':raise SystemExit(main())
