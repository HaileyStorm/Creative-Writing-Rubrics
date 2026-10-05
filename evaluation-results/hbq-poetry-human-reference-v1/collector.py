"""One-attempt presented-poetry collection and label-gate replay; no label reads."""
from collections import Counter
from datetime import datetime, timedelta, timezone
import argparse
import json
import os
from pathlib import Path
import sys
import uuid
import importlib.util

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('poetry_collection_prepare',HERE/'prepare_judging.py')
p=importlib.util.module_from_spec(spec);spec.loader.exec_module(p)
# Retained P1 predecessor supplies native receipt/account primitives only.
TRANSPORT_PATH=HERE.parent/'hbq-semantic-crossform-p1b-matched-v1/collector.py'
TRANSPORT_SHA='71e4a5e1a21ff45338796b060fadde638367067da922786e0a810eec42e8feaa'
t=p.load('poetry_retained_native_transport',TRANSPORT_PATH)
POLICY='study2_presented_poetry_native_once_v1'
MANIFEST_SHA='c5cd2ca4b53262c4a5ab798bc13941002d2786827290ebeeb6ab26c6eb757152'
SETTLED={'accepted','semantic_rejected'}
TERMINAL_STATES=SETTLED|{'unadmitted_no_resend','ambiguous','definitely_not_contacted','unavailable'}
CUTOFF=datetime(2026,10,16,5,40,tzinfo=timezone.utc)
canonical,digest,require,pinned=p.canonical,p.digest,p.require,t.pinned
record,write_bytes,within=t.record,t.write_bytes,t.within


def grok_contact_allowed(route,at_time=None):
    expiry=datetime.fromisoformat(route['cost_evidence']['expires_at'].replace('Z','+00:00'))
    return (at_time or datetime.now(timezone.utc))+timedelta(seconds=900)<min(CUTOFF,expiry)


def source_settings(manifest,root):
    raw=pinned(root,'private/source-generation-manifest.json',manifest['artifacts']['private/source-generation-manifest.json'])
    require(digest(raw)==manifest['source_generation_manifest_file_sha256']==p.RUNTIME_SHA,'Source runtime manifest differs')
    source=json.loads(raw);p.generation.verify_external_pins(source)
    require(manifest['external_pins']==source['external_pins']
        and all(manifest['runtime'][k]==v for k,v in source['runtime'].items() if k!='outbound_artifacts'),'Frozen native runtime differs')
    return source


def inputs(root,manifest,row):
    prompt=pinned(root,row['prompt_path'],manifest['artifacts'][row['prompt_path']])
    schema=pinned(root,row['schema_path'],manifest['artifacts'][row['schema_path']])
    texts={s['id']:pinned(root,s['input_path'],s).decode('utf-8') for s in row['sources']}
    context=pinned(root,row['task_context']['path'],row['task_context']).decode('utf-8')
    require(context.encode() in prompt and all(text.encode() in prompt for text in texts.values()),'Declared source/context absent from prompt')
    return prompt,schema,texts,context


def load_manifest(path,expected_sha,collector_sha,tools):
    raw=path.read_bytes();root=path.resolve().parent;manifest=json.loads(raw)
    require(digest(raw)==expected_sha==MANIFEST_SHA and digest(Path(__file__).read_bytes())==collector_sha
        and digest(TRANSPORT_PATH.read_bytes())==TRANSPORT_SHA,'Exact manifest/collector/transport pin differs')
    require(manifest['study_id']==p.POLICY and manifest['stage']=='prospective_judging_preparation_only'
        and manifest['candidate'] is None and manifest['oracle_accepted'] is False
        and manifest['human_labels_supplied']==0 and manifest['execution_authority'] is False,'Frozen presented-poetry contract differs')
    files={name:pinned(root,name,meta) for name,meta in manifest['artifacts'].items()}
    sys.path.insert(0,str(p.REPO/'src'));p.validate_design(manifest,files)
    source=source_settings(manifest,root)
    require(tools.resolve()==Path(source['external_pins']['tools_root_local_only']).resolve(),'Frozen tools root differs')
    for current,frozen in [(HERE/'prepare_judging.py','implementation/prepare_judging.py'),
        (HERE/'arms/validate_response.py','implementation/validate_response.py'),
        (HERE.parent/'hbq-matched-mfa-v1/validate_response.py','implementation/mfa-admission.py'),
        (p.REPO/'src/hbqrs/core.py','implementation/core.py'),(p.REPO/'src/hbqrs/scoring_v2.py','implementation/scoring_v2.py')]:
        require(digest(current.read_bytes())==manifest['artifacts'][frozen]['sha256'],'Frozen implementation differs')
    for name,relative in {'account_probe':'adaptive_settings/account_probe.py','broker':'model_work_queue/broker.py',
        'grok_adapter':'model_work_queue/adapters/grok_exec.py'}.items():
        require(digest((tools/relative).read_bytes())==manifest['route_compatibility_fingerprints'][name],'Frozen route compatibility differs')
    subset=p.load('poetry_collection_frozen_subset',root/'implementation/schema_subset.py')
    validator=p.load('poetry_collection_frozen_validator',root/'implementation/validate_response.py')
    receipts=p.load('poetry_collection_frozen_receipts',root/'implementation/codex_receipts.py')
    for row in manifest['requests']:subset.validate_schema(json.loads(files[row['schema_path']]))
    return manifest,root,subset,validator,receipts


def job_binding(manifest,root,manifest_sha,endpoint,tools,route=None,collector_sha=None):
    require(endpoint in p.ENDPOINTS,'Unknown endpoint');source=source_settings(manifest,root)
    runtime={'model':'grok-4.7','reasoning':'high'} if endpoint=='grok' else dict(source['runtime'])
    if endpoint=='sol':runtime.update(secondary_home_sha256=runtime['codex_home_sha256'],codex_receipt_policy='codex_native_rollout_v1')
    binding={'schema_version':1,'policy':POLICY,'manifest_sha256':manifest_sha,'endpoint':endpoint,
        'collector_sha256':collector_sha or digest(Path(__file__).read_bytes()),'retained_native_transport_sha256':TRANSPORT_SHA,
        'runtime':runtime,'timeout_seconds':900,'workers':1,'attempts_per_logical_sample':1,'automatic_retries':0,
        'no_ambiguous_resend':True,'planned_endpoint_requests':480,'planned_study_requests':960,
        'source_generation_manifest_sha256':manifest['source_generation_manifest_file_sha256'],
        'artifacts_commitment_sha256':digest(canonical(manifest['artifacts'])),'human_label_gate':manifest['human_label_gate'],
        'payload_classification':'public_repo','payload_description':'Pre-existing publicly sourced poem projections; no synthetic-origin claim.',
        'outbound_artifacts':manifest['runtime']['outbound_artifacts'],
        'preparation_grants_execution_authority':False,'human_targets_opened':False,'native_execution_proven':False,
        'source_helper_sha256':source['artifacts']['implementation/secondary-helper.py']['sha256'],
        'cli_sha256':source['external_pins']['cli_sha256'],'runner_sha256':manifest['artifacts']['implementation/runner.py']['sha256'],
        'receipt_reader_sha256':manifest['artifacts']['implementation/codex_receipts.py']['sha256'],
        'admission_sha256':manifest['artifacts']['implementation/validate_response.py']['sha256'],
        'account_probe_sha256':digest((tools/'adaptive_settings/account_probe.py').read_bytes()),
        'broker_sha256':digest((tools/'model_work_queue/broker.py').read_bytes()),
        'grok_adapter_sha256':digest((tools/'model_work_queue/adapters/grok_exec.py').read_bytes())}
    if endpoint=='grok':
        require(route is not None and route['name']=='grok-build-grok-4.7' and route['model']=='grok-4.7'
            and route['reasoning_effort']=='high' and route['timeout_seconds']==900
            and 'public_repo' in route['allowed_payload_classes'],'Reviewed Grok route/settings/disclosure differs')
        binding.update(route=route,route_sha256=digest(canonical(route).rstrip(b'\n')),
            campaign_deadline=CUTOFF.isoformat(),deadline_margin_seconds=900)
    return binding


def verify_job_binding(output,manifest,root,manifest_sha,endpoint,tools):
    binding=json.loads((output/'job.json').read_bytes())
    require(binding==job_binding(manifest,root,manifest_sha,endpoint,tools,binding.get('route'))
        and (output/'frozen-manifest.json').read_bytes()==(root/'manifest.json').read_bytes(),'Existing job/raw manifest binding differs')
    if endpoint=='sol':require(json.loads((output/'account-binding.json').read_bytes())==t.account_receipt(binding),'Existing account receipt differs')
    return binding


def sample_path(output,row):return output/f"{row['endpoint_ordinal']:04d}-{row['logical_sample_id'][:12]}"


def admission(root,row,manifest,answer,schema,texts,context,subset,validator):
    from jsonschema import Draft202012Validator
    retained=json.loads(pinned(root,row['retained_schema_path'],manifest['artifacts'][row['retained_schema_path']]))
    if not Draft202012Validator(retained).is_valid(answer):
        return {'accepted':False,'abstention':False,'errors':['Response violates original retained schema']}
    return validator.semantic_validate(row['arm'],answer,row,texts,subset,context=context,schema=json.loads(schema))


def native_answer(sample,row,binding,prompt,schema,receipts):
    parseable=True
    if row['endpoint']=='sol':
        native=json.loads((sample/'native-result.json').read_bytes())
        final=within(sample,native['provider_artifacts']['codex_message']['path']).read_bytes()
        receipts.verify(sample,native,prompt=prompt.decode(),model=binding['runtime']['model'],reasoning='high',final_raw=final)
        identity,_=receipts.event_identity(within(sample,native['provider_artifacts']['codex_events']['path']).read_bytes(),final)
        try:answer=json.loads(final)
        except json.JSONDecodeError:answer,parseable=None,False
    else:
        answer=t.validate_native(sample,row,binding,prompt,schema,receipts)
        identity=json.loads((sample/'native-identity.json').read_bytes())['session_id']
    require(str(uuid.UUID(identity))==identity,'Own native UUID unavailable')
    return answer,identity,parseable


def replay(sample,row,manifest,binding,root,receipts,subset,validator):
    require((sample/'terminal.json').is_file(),'Occupied slot is unresolved; no resend')
    terminal=json.loads((sample/'terminal.json').read_bytes())
    require(terminal['no_resend'] is True and terminal['manifest_sha256']==binding['manifest_sha256']
        and terminal['logical_sample_id']==row['logical_sample_id'] and terminal['job_sha256']==digest((sample.parent/'job.json').read_bytes())
        and json.loads((sample/'condition.json').read_bytes())==row,'Terminal condition/job identity differs')
    require(terminal['state'] in TERMINAL_STATES,'Unknown terminal disposition')
    if terminal['state'] not in SETTLED:
        require(terminal['accepted'] is False,'Failed native attempt cannot count as admitted')
        for relative,meta in terminal['retained_artifacts'].items():pinned(sample,relative,meta)
        return terminal,None
    for relative,sha in terminal['artifact_sha256s'].items():require(digest(within(sample,relative).read_bytes())==sha,'Settled own artifact differs')
    started=json.loads((sample/'attempt-started.json').read_bytes())
    require(started['manifest_sha256']==binding['manifest_sha256'] and started['logical_sample_id']==row['logical_sample_id']
        and started['attempt_id']==terminal['attempt_id'] and started['attempt']==1 and started['no_resend'] is True
        and started['job_sha256']==terminal['job_sha256'] and started['prompt_sha256']==row['prompt_sha256']
        and started['schema_sha256']==row['schema_sha256'],'Own attempt binding differs');datetime.fromisoformat(started['time'])
    if row['endpoint']=='sol':
        account=(sample.parent/'account-binding.json').read_bytes()
        require(digest(account)==started['account_binding_sha256'] and json.loads(account)==t.account_receipt(binding),'Own secondary account differs')
    prompt,schema,texts,context=inputs(root,manifest,row)
    require((sample/'prompt.txt').read_bytes()==prompt and (sample/'schema.json').read_bytes()==schema
        and (sample/'task-context.json').read_bytes()==context.encode()
        and all((sample/'sources'/f'{tid}.txt').read_bytes()==text.encode() for tid,text in texts.items()),'Own source/context snapshots differ')
    answer,identity,parseable=native_answer(sample,row,binding,prompt,schema,receipts)
    require(identity==terminal['native_thread_id'] and answer==json.loads((sample/'response.json').read_bytes())
        and json.loads((sample/'native-final-parse.json').read_bytes())=={'json_parseable':parseable},'Native final/derived identity differs')
    accepted=admission(root,row,manifest,answer,schema,texts,context,subset,validator)
    require(accepted==json.loads((sample/'acceptance.json').read_bytes())
        and accepted['accepted']==terminal['accepted']==(terminal['state']=='accepted'),'Original schema/source admission differs')
    return terminal,answer if accepted['accepted'] else None


def inventory(manifest,binding,root,output,receipts,subset,validator):
    pending,states,native_ids=[],[],set()
    for row in (r for r in manifest['requests'] if r['endpoint']==binding['endpoint']):
        sample=sample_path(output,row)
        if not sample.exists():pending.append(row);continue
        terminal,_=replay(sample,row,manifest,binding,root,receipts,subset,validator);states.append(terminal['state'])
        identity=terminal.get('native_thread_id')
        if identity:require(identity not in native_ids,'Duplicate own native UUID');native_ids.add(identity)
    return pending,states,native_ids


def label_release_gate(manifest,root,manifest_sha,tools,outputs,receipts,subset,validator,explicit_release=False):
    counts={};identities=set();missing=0
    for endpoint in p.ENDPOINTS:
        output=outputs[endpoint]
        if not output.exists():counts[endpoint]={'untouched':480,'verified_terminal':0,'states':{}};missing+=480;continue
        binding=verify_job_binding(output,manifest,root,manifest_sha,endpoint,tools)
        pending,states,native_ids=inventory(manifest,binding,root,output,receipts,subset,validator)
        require(not(identities&native_ids),'Native UUID reused across endpoints');identities.update(native_ids)
        counts[endpoint]={'untouched':len(pending),'verified_terminal':len(states),'states':dict(Counter(states))};missing+=len(pending)
    ready=missing==0 and sum(c['verified_terminal'] for c in counts.values())==960
    return {'policy':p.HUMAN_GATE['policy'],'manifest_sha256':manifest_sha,'planned':960,'endpoints':counts,
        'all_planned_verified_terminal':ready,'explicit_postprediction_release':explicit_release,
        'human_release_eligible':ready and explicit_release,'human_targets_opened':False,'provider_calls':0}


def collect_one(row,manifest,binding,root,output,subset,validator,receipts,helper=None,call_codex=None,broker=None):
    sample=sample_path(output,row);sample.mkdir(exist_ok=False);record(sample/'condition.json',row)
    prompt,schema,texts,context=inputs(root,manifest,row)
    for name,raw in [('prompt.txt',prompt),('schema.json',schema),('task-context.json',context.encode())]:write_bytes(sample/name,raw)
    for tid,text in texts.items():write_bytes(sample/'sources'/f'{tid}.txt',text.encode())
    session=str(uuid.uuid4()) if row['endpoint']=='grok' else None
    record(sample/'native-identity.json',{'session_id':session,'logical_sample_id':row['logical_sample_id']})
    terminal={'manifest_sha256':binding['manifest_sha256'],'logical_sample_id':row['logical_sample_id'],'no_resend':True,
        'job_sha256':digest((output/'job.json').read_bytes()),'accepted':False}
    def before():
        require(not(output/'STOP').exists(),'STOP prevents new contact')
        require(row['endpoint']!='grok' or grok_contact_allowed(binding['route']),'Route expiry/campaign deadline prevents contact')
        terminal['attempt_id']=str(uuid.uuid4())
        record(sample/'attempt-started.json',{'time':datetime.now(timezone.utc).isoformat(),'attempt_id':terminal['attempt_id'],
            'attempt':1,'no_resend':True,'manifest_sha256':binding['manifest_sha256'],'logical_sample_id':row['logical_sample_id'],
            'job_sha256':terminal['job_sha256'],'prompt_sha256':row['prompt_sha256'],'schema_sha256':row['schema_sha256'],
            'session_id':session,'account_binding_sha256':digest((output/'account-binding.json').read_bytes()) if row['endpoint']=='sol' else None})
    try:
        if row['endpoint']=='sol':
            content,native=call_codex(executable=str(helper.CLI),model=binding['runtime']['model'],reasoning='high',
                prompt=prompt.decode(),output_dir=sample,response_schema=sample/'schema.json',batch_number=1,attempt_number=1,
                timeout=900,before_provider_attempt=before,codex_receipt_policy='codex_native_rollout_v1')
        else:
            native=broker.run_grok_native_request(binding['route']['name'],{'prompt':prompt.decode()},output_schema=json.loads(schema),
                nonvisual_max_turns=1,session_id=session,before_contact=before,expected_route_sha256=binding['route_sha256'])
        record(sample/'native-result.json',native)
        if row['endpoint']=='grok':
            if native['state']!='completed':
                terminal['state']=native['state'] if native['state'] in TERMINAL_STATES-SETTLED else 'unadmitted_no_resend'
                raise RuntimeError('Native Grok attempt did not complete')
            write_bytes(sample/'native-envelope.json',broker.read_grok_native_envelope(native['result']['native_envelope_artifact']))
        answer,identity,parseable=native_answer(sample,row,binding,prompt,schema,receipts)
        require((sample/'attempt-started.json').is_file(),'Own contact-start receipt missing')
        if row['endpoint']=='sol':
            if parseable:require(answer==json.loads(content),'Returned content differs from native final')
            else:require(content==within(sample,native['provider_artifacts']['codex_message']['path']).read_bytes().decode().replace('\r\n','\n').replace('\r','\n'),'Returned malformed final differs')
        for other in output.glob('*/terminal.json'):require(json.loads(other.read_bytes()).get('native_thread_id')!=identity,'Duplicate own native UUID')
        terminal['native_thread_id']=identity;record(sample/'response.json',answer);record(sample/'native-final-parse.json',{'json_parseable':parseable})
        accepted=admission(root,row,manifest,answer,schema,texts,context,subset,validator);record(sample/'acceptance.json',accepted)
        terminal.update(state='accepted' if accepted['accepted'] else 'semantic_rejected',accepted=accepted['accepted'],abstention=accepted['abstention'])
        terminal['artifact_sha256s']={x.relative_to(sample).as_posix():digest(x.read_bytes()) for x in sample.rglob('*') if x.is_file()}
    except BaseException as error:
        if terminal.get('state') in SETTLED:terminal.update(state='unadmitted_no_resend',accepted=False)
        terminal.setdefault('state','unadmitted_no_resend');terminal['error_class']=type(error).__name__
        if hasattr(error,'provider_record'):terminal['provider_record']=error.provider_record
        terminal['retained_artifacts']={x.relative_to(sample).as_posix():p.metadata(x.relative_to(sample).as_posix(),x.read_bytes()) for x in sample.rglob('*') if x.is_file()}
        record(sample/'terminal.json',terminal)
        if (output/'STOP').exists():t.note_stop(output)
        if not isinstance(error,Exception):raise
        return terminal['state']
    record(sample/'terminal.json',terminal)
    if (output/'STOP').exists():t.note_stop(output)
    return terminal['state']


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('manifest','tools-root'):parser.add_argument('--'+name,type=Path,required=True)
    for name in ('manifest-sha256','collector-sha256'):parser.add_argument('--'+name,required=True)
    for name in ('results-dir','route-root','sol-results-dir','grok-results-dir'):parser.add_argument('--'+name,type=Path)
    parser.add_argument('--endpoint',choices=p.ENDPOINTS);parser.add_argument('--route-sha256')
    parser.add_argument('--limit',type=int);parser.add_argument('--validate-only',action='store_true')
    parser.add_argument('--label-release-check',action='store_true');parser.add_argument('--explicit-postprediction-release',action='store_true')
    args=parser.parse_args();require(args.limit is None or args.limit>0,'Limit must be positive')
    manifest,root,subset,validator,receipts=load_manifest(args.manifest,args.manifest_sha256,args.collector_sha256,args.tools_root)
    if args.label_release_check:
        require(args.sol_results_dir is not None and args.grok_results_dir is not None,'Both endpoint result roots required')
        outputs={'sol':args.sol_results_dir.resolve(),'grok':args.grok_results_dir.resolve()}
        for output in outputs.values():p.generation.output_preflight(output,root)
        print(json.dumps(label_release_gate(manifest,root,args.manifest_sha256,args.tools_root,outputs,receipts,subset,validator,args.explicit_postprediction_release)));return 0
    require(not args.explicit_postprediction_release,'Release flag requires read-only label-release-check')
    require(args.endpoint is not None and args.results_dir is not None,'Collection endpoint/result root required')
    output=args.results_dir.resolve();p.generation.output_preflight(output,root);route=None
    if args.endpoint=='grok':
        require(args.route_root is not None and args.route_sha256 is not None,'Exact reviewed route required')
        route=next(r for r in json.loads((args.route_root/'routes.json').read_bytes())['routes'] if r['name']=='grok-build-grok-4.7')
        require(digest(canonical(route).rstrip(b'\n'))==args.route_sha256,'Reviewed route pin differs')
    binding=job_binding(manifest,root,args.manifest_sha256,args.endpoint,args.tools_root,route,args.collector_sha256)
    if output.exists():require(verify_job_binding(output,manifest,root,args.manifest_sha256,args.endpoint,args.tools_root)==binding,'Existing job differs')
    pending,states,_=inventory(manifest,binding,root,output,receipts,subset,validator)
    if args.validate_only:
        print(json.dumps({'state':'provider_free_validated','endpoint':args.endpoint,'manifest_sha256':args.manifest_sha256,
            'planned':480,'study_planned':960,'untouched':len(pending),'terminal_states':dict(Counter(states)),
            'provider_calls':0,'human_targets_opened':False,'human_release_eligible':False,'native_execution_proven':False}));return 0
    require(all(state in SETTLED for state in states),'Incomplete occupied native attempt requires reconciliation; no resend')
    if (output/'STOP').exists():t.note_stop(output);return 3
    if not pending:return 0
    helper=call_codex=broker=None
    if args.endpoint=='sol':
        source=source_settings(manifest,root);helper=p.load('poetry_secondary_helper',Path(source['external_pins']['secondary_helper_path_local_only']))
        env=t.secondary_binding(source,helper);os.environ.clear();os.environ.update(env)
        sys.path.insert(0,str(args.tools_root));from adaptive_settings.account_probe import probe
        from hbqrs import runner
        t.secondary_binding(source,helper,probe(helper.CLI));call_codex=runner._call_codex
    else:
        require(grok_contact_allowed(route),'Route expiry/campaign deadline prevents new contact')
        sys.path.insert(0,str(args.tools_root));from model_work_queue.broker import Broker
        broker=Broker(args.route_root.resolve())
    if not output.exists():
        output.mkdir(parents=True,exist_ok=False);record(output/'job.json',binding);write_bytes(output/'frozen-manifest.json',args.manifest.read_bytes())
    if args.endpoint=='sol' and not(output/'account-binding.json').exists():record(output/'account-binding.json',t.account_receipt(binding))
    for row in pending[:args.limit]:
        if (output/'STOP').exists():t.note_stop(output);return 3
        if args.endpoint=='grok' and not grok_contact_allowed(route):return 3
        state=collect_one(row,manifest,binding,root,output,subset,validator,receipts,helper,call_codex,broker)
        print(json.dumps({'ordinal':row['endpoint_ordinal'],'state':state}),flush=True)
        if state not in SETTLED:return 3
    return 0


if __name__=='__main__':raise SystemExit(main())
