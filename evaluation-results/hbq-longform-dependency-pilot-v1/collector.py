"""Source-bound P4 collection; dependency diagnostics never yield whole-work scores."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import sys
import uuid
import importlib.util

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('p4_judging_prepare', HERE / 'prepare.py')
p = importlib.util.module_from_spec(spec); spec.loader.exec_module(p)
# This retained predecessor supplies native transport admission, not P1 study policy.
TRANSPORT_PATH = HERE.parent / 'hbq-semantic-crossform-p1b-matched-v1/collector.py'
TRANSPORT_SHA = '71e4a5e1a21ff45338796b060fadde638367067da922786e0a810eec42e8feaa'
t = p.load('p4_native_receipt_predecessor', TRANSPORT_PATH)
POLICY = 'longform_source_bound_judging_once_v1'
SETTLED = {'accepted', 'semantic_rejected'}
TERMINAL_STATES = SETTLED | {'unadmitted_no_resend', 'ambiguous', 'definitely_not_contacted', 'unavailable'}
CUTOFF = datetime(2026, 10, 16, 5, 40, tzinfo=timezone.utc)
canonical, digest, require, pinned = p.canonical, p.digest, p.require, t.pinned
record, write_bytes, within = t.record, t.write_bytes, t.within


def grok_contact_allowed(route, at_time=None):
    now = at_time or datetime.now(timezone.utc)
    expiry = datetime.fromisoformat(route['cost_evidence']['expires_at'].replace('Z', '+00:00'))
    return now + timedelta(seconds=900) < min(CUTOFF, expiry)


def source_settings(manifest, root):
    raw = pinned(root, 'private/source-generation-manifest.json', manifest['artifacts']['private/source-generation-manifest.json'])
    require(digest(raw) == manifest['source_generation_manifest_file_sha256'] == p.RUNTIME_SHA, 'Prior runtime manifest differs')
    source = json.loads(raw); p.generation.verify_external_pins(source)
    require(manifest['external_pins'] == source['external_pins']
            and all(manifest['runtime'][k] == v for k,v in source['runtime'].items() if k != 'outbound_artifacts'), 'Native source runtime differs')
    require(source['runtime']['model'] == 'gpt-6.1-sol' and source['runtime']['reasoning'] == 'high'
            and source['runtime']['receipt_policy'] == 'codex_native_rollout_v1'
            and source['runtime']['timeout_seconds'] == 900 and source['runtime']['workers'] == 1
            and source['runtime']['automatic_retries'] == 0 and source['runtime']['attempts_per_logical_sample'] == 1,
            'One-worker Sol/high receipt contract differs')
    return source


def inputs(root, manifest, row):
    prompt = pinned(root, row['prompt_path'], manifest['artifacts'][row['prompt_path']])
    schema = pinned(root, row['schema_path'], manifest['artifacts'][row['schema_path']])
    require(digest(prompt) == row['prompt_sha256'] and len(prompt) == row['prompt_bytes']
            and digest(schema) == row['schema_sha256'] and len(schema) == row['schema_bytes'], 'Request prompt/schema differs')
    require(len(row['sources']) == 1 and row['sources'][0]['id'] == row['work_id'] == row['artifact_id'], 'Source identity differs')
    source = row['sources'][0]
    raw = pinned(root, source['input_path'], source)
    require(raw == pinned(root, source['input_path'], manifest['artifacts'][source['input_path']]), 'Available representation commitment differs')
    context = pinned(root, row['task_context']['path'], row['task_context'])
    require(context == pinned(root, row['task_context']['path'], manifest['artifacts'][row['task_context']['path']])
            and raw in prompt and context in prompt, 'Declared available representation/context absent from prompt')
    original = pinned(root, row['target_original']['path'], row['target_original'])
    require(original == pinned(root, row['target_original']['path'], manifest['artifacts'][row['target_original']['path']]), 'Original source commitment differs')
    require(row['context_arm'] in ('raw_full','anchored_map','summary_only'), 'Unknown representation access')
    if row['context_arm'] == 'raw_full': require(raw == original, 'Raw full representation must be exact original narrative')
    return prompt, schema, {source['id']: raw.decode('utf-8')}, context.decode('utf-8')


def validate_geometry(manifest, root):
    from hbqrs import core, runner
    compiled_raw = pinned(root, 'compiled/prose.novella.json', manifest['artifacts']['compiled/prose.novella.json'])
    compiled = json.loads(compiled_raw)
    ids = [q['question']['id'] for q in core.compiled_questions(compiled)]
    require(len(ids) == len(set(ids)) == 219, 'Canonical novella bank differs')
    require(manifest['counts'] == {'works':2,'cases':6,'case_leaf_instances':18,'unique_case_leaves':10,'cycles':3,
        'diagnostic_requests':216,'whole_work_requests':248,'requests_total':464,'requests_per_endpoint':232,
        'whole_bank_leaves':219,'whole_bank_packets':28,'summary_generation_calls_separate':2}, 'P4 planned denominators differ')
    require(len(manifest['requests']) == 464 and [r['ordinal'] for r in manifest['requests']] == list(range(1,465)), 'Global inventory differs')
    endpoint_logicals = []
    sentinel = manifest['whole_bank_sentinel']['work_id']
    originals = {}
    for row in manifest['requests']: originals[row['work_id']] = row['target_original']['sha256']
    handoff = json.loads(pinned(root,'source-index/agent-handoff.json',manifest['artifacts']['source-index/agent-handoff.json']))
    case_work = {c['id']:Path(c['source']).stem for c in handoff['case_proposals']}
    require(set(originals) == {'pg43','pg209'} and sentinel == min(originals, key=lambda w: digest(canonical(
        [p.POLICY, 'whole_bank_sentinel_metadata_v1', w, originals[w]]))), 'Metadata-only bank sentinel differs')
    for endpoint in p.ENDPOINTS:
        rows = [r for r in manifest['requests'] if r['endpoint'] == endpoint]
        require(len(rows) == 232 and [r['endpoint_ordinal'] for r in rows] == list(range(1,233))
                and len({r['logical_sample_id'] for r in rows}) == 232, 'Endpoint request inventory differs')
        endpoint_logicals.append({r['logical_sample_id'] for r in rows})
        require(Counter((r['contract'],r['arm']) for r in rows) == Counter({
            ('unscored_dependency_diagnostic','hbq'):54,('unscored_dependency_diagnostic','holistic'):54,
            ('whole_work_baseline','hbq'):112,('whole_work_baseline','holistic'):6,('whole_work_baseline','compact'):6}), 'Contract/arm denominators differ')
        banks, diagnostics, comparators = defaultdict(list), set(), set()
        for row in rows:
            diagnostic = row['contract'] == 'unscored_dependency_diagnostic'
            require(row['contract'] in ('unscored_dependency_diagnostic','whole_work_baseline')
                    and row['work_id'] in originals and row['repeat'] in (0,1,2)
                    and row['bundle_id'] == 'prose.novella' and row['compiled_sha256'] == digest(compiled_raw)
                    and row['whole_work_artistic_score'] == (not diagnostic)
                    and row['full_bank_score_eligible'] == (not diagnostic and row['arm'] == 'hbq')
                    and row['prompt_policy'] == 'human_authored_source_override_v1', 'Scope/scoring eligibility differs')
            require(row['rendering_policy'] == ('exact_source_body_splice_v1' if row['arm'] == 'hbq' else 'exact_source_concat_v1'), 'Source rendering policy differs')
            if diagnostic:
                require(row['case_id'] in p.CASE_LEAVES and row['work_id'] == case_work[row['case_id']] and row['batch'] == 1
                        and row['question_ids'] == (p.CASE_LEAVES[row['case_id']] if row['arm'] == 'hbq' else []), 'Diagnostic leaf packet differs')
                key = (row['case_id'],row['context_arm'],row['repeat'],row['arm'])
                require(key not in diagnostics, 'Duplicate diagnostic condition'); diagnostics.add(key)
            else:
                require(row['context_arm'] == 'raw_full' and 'case_id' not in row, 'Whole-work scope must have full original only')
                if row['arm'] == 'hbq': banks[(row['work_id'],row['repeat'])].append(row)
                else:
                    key = (row['work_id'],row['repeat'],row['arm'])
                    require(key not in comparators and row['question_ids'] == [] and row['batch'] == 1, 'Duplicate whole-work comparator'); comparators.add(key)
            contracts = row['task_contracts']; require(len(contracts) == 1 and contracts[0]['artifact_id'] == row['work_id'], 'Task target differs')
            task = contracts[0]; raw = pinned(root, task['path'], manifest['artifacts'][task['path']]); contract = json.loads(raw)
            require(digest(raw) == task['sha256'] and contract == p.task_contract(row['work_id'], diagnostic), 'Canonical task contract differs')
            projection = json.dumps(runner._task_contract_judge_context(contract), ensure_ascii=False, indent=2).encode('utf-8')
            require(pinned(root, row['task_context']['path'], row['task_context']) == projection, 'Exact rendered task-context projection differs')
        require(len(diagnostics) == 108 and len(comparators) == 12
                and set(banks) == {(w,c) for w in originals for c in range(3) if c == 0 or w == sentinel}, 'Bank/repeat geometry differs')
        for group in banks.values():
            group.sort(key=lambda r:r['batch'])
            require([r['batch'] for r in group] == list(range(1,29))
                    and [q for r in group for q in r['question_ids']] == ids, 'Full bank is incomplete, duplicated or reordered')
    require(endpoint_logicals[0] == endpoint_logicals[1], 'Endpoints must share exact logical conditions')


def load_manifest(path, expected_sha, collector_sha, tools):
    raw = path.read_bytes(); root = path.resolve().parent; manifest = json.loads(raw)
    require(digest(raw) == expected_sha and digest(Path(__file__).read_bytes()) == collector_sha
            and digest(TRANSPORT_PATH.read_bytes()) == TRANSPORT_SHA, 'Exact manifest/collector/retained transport pin differs')
    require(manifest['study_id'] == p.POLICY and manifest['stage'] == 'matched_judging_preparation'
            and manifest['candidate'] is None and manifest['oracle_accepted'] is False and manifest['human_labels_supplied'] == 0
            and manifest['human_alignment_claim'] is False and manifest['execution_authority'] is False, 'Only descriptive P4 judging contract is eligible')
    for relative, meta in manifest['artifacts'].items(): pinned(root, relative, meta)
    source = source_settings(manifest, root)
    require(tools.resolve() == Path(source['external_pins']['tools_root_local_only']).resolve(), 'Native tools root differs')
    for current, frozen in [(HERE/'prepare.py','implementation/prepare.py'), (HERE/'arms/validate_response.py','implementation/validate_response.py'),
            (HERE.parent/'hbq-matched-mfa-v1/validate_response.py','implementation/mfa-admission.py'),
            (p.REPO/'src/hbqrs/core.py','implementation/core.py'), (p.REPO/'src/hbqrs/scoring_v2.py','implementation/scoring_v2.py')]:
        require(digest(current.read_bytes()) == manifest['artifacts'][frozen]['sha256'], 'Frozen preparation/scoring/admission implementation differs')
    require(manifest['source_index_commitments'] == p.SOURCE_PINS, 'Source index commitments differ')
    for relative, sha in p.SOURCE_PINS.items(): require(manifest['artifacts']['source-index/'+relative]['sha256'] == sha, 'Source index binding differs')
    require('private/summary-wrapper.json' in manifest['artifacts'] and 'private/summary-generation-manifest.json' in manifest['artifacts'], 'Independent source summary lineage required')
    subset = p.load('p4_judging_frozen_subset', root/'implementation/schema_subset.py')
    validator = p.load('p4_judging_frozen_admission', root/'implementation/validate_response.py')
    receipts = p.load('p4_judging_frozen_receipts', root/'implementation/codex_receipts.py')
    sys.path.insert(0, str(p.REPO/'src')); validate_geometry(manifest, root)
    for row in manifest['requests']:
        require(digest(canonical({k:v for k,v in row.items() if k != 'request_sha256'})) == row['request_sha256']
                and digest(canonical({k:v for k,v in row.items() if k not in ('request_sha256','logical_sample_id','endpoint','endpoint_ordinal','ordinal')})) == row['logical_sample_id'], 'Logical request commitment differs')
        _, schema, _, _ = inputs(root, manifest, row); subset.validate_schema(json.loads(schema))
        retained = pinned(root, row['retained_schema_path'], manifest['artifacts'][row['retained_schema_path']])
        require(digest(retained) == row['retained_schema_sha256'], 'Original retained schema differs')
    return manifest, root, subset, validator, receipts


def job_binding(manifest, root, manifest_sha, endpoint, tools, route=None, collector_sha=None, payload_classification='public_synthetic'):
    require(endpoint in p.ENDPOINTS and payload_classification == 'public_synthetic', 'Reviewed public-text disclosure classification differs')
    source = source_settings(manifest, root)
    runtime = {'model':'grok-4.7','reasoning':'high'} if endpoint == 'grok' else dict(manifest['runtime'])
    if endpoint == 'sol': runtime.update(secondary_home_sha256=runtime['codex_home_sha256'], codex_receipt_policy='codex_native_rollout_v1')
    binding = {'schema_version':1, 'policy':POLICY, 'manifest_sha256':manifest_sha, 'endpoint':endpoint,
        'collector_sha256':collector_sha or digest(Path(__file__).read_bytes()), 'retained_native_transport_sha256':TRANSPORT_SHA,
        'runtime':runtime, 'timeout_seconds':900, 'workers':1, 'automatic_retries':0, 'no_ambiguous_resend':True,
        'source_generation_manifest_sha256':manifest['source_generation_manifest_file_sha256'],
        'artifacts_commitment_sha256':digest(canonical(manifest['artifacts'])), 'payload_classification':payload_classification,
        'outbound_artifacts':manifest['runtime']['outbound_artifacts'], 'diagnostic_scalar_eligible':False,
        'provider_contact_cardinality_proven':False, 'model_read_whole_body_proven':False,
        'source_helper_sha256':source['artifacts']['implementation/secondary-helper.py']['sha256'], 'cli_sha256':source['external_pins']['cli_sha256'],
        'runner_sha256':manifest['artifacts']['implementation/runner.py']['sha256'], 'receipt_reader_sha256':manifest['artifacts']['implementation/codex_receipts.py']['sha256'],
        'admission_sha256':manifest['artifacts']['implementation/validate_response.py']['sha256'],
        'account_probe_sha256':digest((tools/'adaptive_settings/account_probe.py').read_bytes()),
        'broker_sha256':digest((tools/'model_work_queue/broker.py').read_bytes()),
        'grok_adapter_sha256':digest((tools/'model_work_queue/adapters/grok_exec.py').read_bytes())}
    if endpoint == 'grok':
        require(route is not None and route['name'] == 'grok-build-grok-4.7' and route['model'] == 'grok-4.7'
                and route['reasoning_effort'] == 'high' and route['timeout_seconds'] == 900
                and payload_classification in route['allowed_payload_classes'], 'Exact reviewed Grok route differs')
        binding.update(route=route,route_sha256=digest(canonical(route).rstrip(b'\n')),
            campaign_deadline=CUTOFF.isoformat(),deadline_margin_seconds=900)
    return binding


def sample_path(output, row): return output/f"{row['endpoint_ordinal']:04d}-{row['logical_sample_id'][:12]}"


def native_answer(sample, row, binding, prompt, schema, receipts):
    parseable = True
    if row['endpoint'] == 'sol':
        native = json.loads((sample/'native-result.json').read_bytes())
        final = within(sample,native['provider_artifacts']['codex_message']['path']).read_bytes()
        receipts.verify(sample,native,prompt=prompt.decode('utf-8'),model=binding['runtime']['model'],reasoning='high',final_raw=final)
        events = within(sample,native['provider_artifacts']['codex_events']['path']).read_bytes()
        identity, _ = receipts.event_identity(events,final)
        try: answer = json.loads(final)
        except json.JSONDecodeError: answer,parseable = None,False
    else:
        answer = t.validate_native(sample,row,binding,prompt,schema,receipts)
        identity = json.loads((sample/'native-identity.json').read_bytes())['session_id']
    require(str(uuid.UUID(identity)) == identity, 'Own native UUID unavailable')
    return answer, identity, parseable


def replay(sample,row,manifest,binding,root,receipts,subset,validator):
    require((sample/'terminal.json').is_file(), 'Occupied slot is unresolved; no resend')
    terminal = json.loads((sample/'terminal.json').read_bytes())
    require(terminal['no_resend'] is True and terminal['manifest_sha256'] == binding['manifest_sha256']
            and terminal['logical_sample_id'] == row['logical_sample_id'] and terminal['job_sha256'] == digest((sample.parent/'job.json').read_bytes())
            and json.loads((sample/'condition.json').read_bytes()) == row, 'Terminal condition/job identity differs')
    require(terminal['state'] in TERMINAL_STATES, 'Unknown terminal state')
    if terminal['state'] not in SETTLED:
        for relative, meta in terminal['retained_artifacts'].items(): pinned(sample,relative,meta)
        return terminal,None
    for relative, sha in terminal['artifact_sha256s'].items(): require(digest(within(sample,relative).read_bytes()) == sha, 'Settled own artifact differs')
    started = json.loads((sample/'attempt-started.json').read_bytes())
    require(started['manifest_sha256'] == binding['manifest_sha256'] and started['logical_sample_id'] == row['logical_sample_id']
            and started['attempt_id'] == terminal['attempt_id'] and started['attempt'] == 1 and started['no_resend'] is True
            and started['job_sha256'] == terminal['job_sha256'] and started['prompt_sha256'] == row['prompt_sha256']
            and started['schema_sha256'] == row['schema_sha256'], 'Own attempt binding differs')
    datetime.fromisoformat(started['time'])
    if row['endpoint'] == 'sol':
        account = (sample.parent/'account-binding.json').read_bytes()
        require(digest(account) == started['account_binding_sha256'] and json.loads(account) == t.account_receipt(binding), 'Own account receipt differs')
    prompt,schema,texts,context = inputs(root,manifest,row)
    require((sample/'prompt.txt').read_bytes() == prompt and (sample/'schema.json').read_bytes() == schema
            and (sample/'available-source.txt').read_bytes() == texts[row['work_id']].encode('utf-8')
            and (sample/'task-context.json').read_bytes() == context.encode('utf-8'), 'Own typed source/context snapshots differ')
    answer,identity,parseable = native_answer(sample,row,binding,prompt,schema,receipts)
    require(identity == terminal['native_thread_id'] and answer == json.loads((sample/'response.json').read_bytes()), 'Own native/derived identity differs')
    require(json.loads((sample/'native-final-parse.json').read_bytes()) == {'json_parseable':parseable}, 'Own final parse disposition differs')
    admission = validator.semantic_validate(row['arm'],answer,row,texts,subset,context=context,schema=json.loads(schema))
    require(admission == json.loads((sample/'acceptance.json').read_bytes())
            and admission['accepted'] == terminal['accepted'] == (terminal['state'] == 'accepted'), 'Source-bound admission differs')
    return terminal,answer if admission['accepted'] else None


def collect_one(row,manifest,binding,root,output,subset,validator,receipts,helper=None,call_codex=None,broker=None):
    sample = sample_path(output,row); sample.mkdir(exist_ok=False); record(sample/'condition.json',row)
    prompt,schema,texts,context = inputs(root,manifest,row)
    for name,raw in [('prompt.txt',prompt),('schema.json',schema),('available-source.txt',texts[row['work_id']].encode('utf-8')),('task-context.json',context.encode('utf-8'))]: write_bytes(sample/name,raw)
    session = str(uuid.uuid4()) if row['endpoint'] == 'grok' else None
    record(sample/'native-identity.json',{'session_id':session,'logical_sample_id':row['logical_sample_id']})
    terminal = {'manifest_sha256':binding['manifest_sha256'],'logical_sample_id':row['logical_sample_id'],'no_resend':True,
        'job_sha256':digest((output/'job.json').read_bytes()),'accepted':False,'diagnostic_scalar_eligible':False,
        'representation_access':row['context_arm'],'contract':row['contract'],'model_read_whole_body_proven':False}
    def before():
        require(not (output/'STOP').exists(), 'STOP prevents new contact')
        require(row['endpoint'] != 'grok' or grok_contact_allowed(binding['route']), 'Route expiry/campaign deadline prevents contact')
        terminal['attempt_id'] = str(uuid.uuid4())
        record(sample/'attempt-started.json',{'time':datetime.now(timezone.utc).isoformat(),'attempt_id':terminal['attempt_id'],
            'attempt':1,'no_resend':True,'manifest_sha256':binding['manifest_sha256'],'logical_sample_id':row['logical_sample_id'],
            'job_sha256':terminal['job_sha256'],'prompt_sha256':row['prompt_sha256'],'schema_sha256':row['schema_sha256'],
            'session_id':session,'account_binding_sha256':digest((output/'account-binding.json').read_bytes()) if row['endpoint'] == 'sol' else None})
    try:
        if row['endpoint'] == 'sol':
            content,native = call_codex(executable=str(helper.CLI),model=binding['runtime']['model'],reasoning='high',
                prompt=prompt.decode('utf-8'),output_dir=sample,response_schema=sample/'schema.json',batch_number=1,attempt_number=1,timeout=900,
                before_provider_attempt=before,codex_receipt_policy='codex_native_rollout_v1')
        else:
            native = broker.run_grok_native_request(binding['route']['name'],{'prompt':prompt.decode('utf-8')},
                output_schema=json.loads(schema),nonvisual_max_turns=1,session_id=session,before_contact=before,expected_route_sha256=binding['route_sha256'])
        record(sample/'native-result.json',native)
        if row['endpoint'] == 'grok':
            if native['state'] != 'completed':
                terminal['state'] = native['state'] if native['state'] in TERMINAL_STATES-SETTLED else 'unadmitted_no_resend'
                raise RuntimeError('Native Grok attempt did not complete')
            write_bytes(sample/'native-envelope.json',broker.read_grok_native_envelope(native['result']['native_envelope_artifact']))
        answer,identity,parseable = native_answer(sample,row,binding,prompt,schema,receipts)
        require((sample/'attempt-started.json').is_file(), 'Own contact-start receipt missing')
        if row['endpoint'] == 'sol':
            if parseable: require(answer == json.loads(content), 'Returned content differs from own native final')
            else:
                final = within(sample,native['provider_artifacts']['codex_message']['path']).read_bytes().decode('utf-8')
                require(content == final.replace('\r\n','\n').replace('\r','\n'), 'Returned malformed content differs from native final')
        for other in output.glob('*/terminal.json'):
            require(json.loads(other.read_bytes()).get('native_thread_id') != identity, 'Duplicate native request UUID')
        terminal['native_thread_id'] = identity; record(sample/'response.json',answer)
        record(sample/'native-final-parse.json',{'json_parseable':parseable})
        acceptance = validator.semantic_validate(row['arm'],answer,row,texts,subset,context=context,schema=json.loads(schema))
        record(sample/'acceptance.json',acceptance)
        terminal.update(state='accepted' if acceptance['accepted'] else 'semantic_rejected',accepted=acceptance['accepted'],abstention=acceptance['abstention'])
        terminal['artifact_sha256s'] = {x.name:digest(x.read_bytes()) for x in sample.iterdir() if x.is_file()}
    except BaseException as error:
        if terminal.get('state') in SETTLED: terminal.update(state='unadmitted_no_resend',accepted=False)
        terminal.setdefault('state','unadmitted_no_resend'); terminal['error_class'] = type(error).__name__
        if hasattr(error,'provider_record'): terminal['provider_record'] = error.provider_record
        terminal['retained_artifacts'] = {x.relative_to(sample).as_posix():p.metadata(x.relative_to(sample).as_posix(),x.read_bytes()) for x in sample.rglob('*') if x.is_file()}
        record(sample/'terminal.json',terminal)
        if (output/'STOP').exists(): t.note_stop(output)
        if not isinstance(error,Exception): raise
        return terminal['state']
    record(sample/'terminal.json',terminal)
    if (output/'STOP').exists(): t.note_stop(output)
    return terminal['state']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('manifest','results-dir','tools-root'): parser.add_argument('--'+name,type=Path,required=True)
    for name in ('manifest-sha256','collector-sha256'): parser.add_argument('--'+name,required=True)
    parser.add_argument('--endpoint',choices=p.ENDPOINTS,required=True)
    parser.add_argument('--route-root',type=Path); parser.add_argument('--route-sha256')
    parser.add_argument('--payload-classification',choices=['public_synthetic'],default='public_synthetic')
    parser.add_argument('--limit',type=int); parser.add_argument('--validate-only',action='store_true'); args = parser.parse_args()
    require(args.limit is None or args.limit > 0,'Limit must be positive')
    manifest,root,subset,validator,receipts = load_manifest(args.manifest,args.manifest_sha256,args.collector_sha256,args.tools_root)
    output = args.results_dir.resolve(); p.generation.output_preflight(output,root)
    route = None
    if args.endpoint == 'grok':
        require(args.route_root is not None and args.route_sha256 is not None,'Grok requires exact reviewed route')
        route = next(r for r in json.loads((args.route_root/'routes.json').read_bytes())['routes'] if r['name'] == 'grok-build-grok-4.7')
        require(digest(canonical(route).rstrip(b'\n')) == args.route_sha256,'Reviewed Grok route pin differs')
    binding = job_binding(manifest,root,args.manifest_sha256,args.endpoint,args.tools_root,route,args.collector_sha256,args.payload_classification)
    if output.exists():
        require(json.loads((output/'job.json').read_bytes()) == binding and (output/'frozen-manifest.json').read_bytes() == args.manifest.read_bytes(),'Existing job/raw manifest binding differs')
        if args.endpoint == 'sol': require(json.loads((output/'account-binding.json').read_bytes()) == t.account_receipt(binding),'Existing secondary account binding differs')
    rows = [r for r in manifest['requests'] if r['endpoint'] == args.endpoint]; pending,states,native_ids = [],[],set()
    for row in rows:
        sample = sample_path(output,row)
        if not sample.exists(): pending.append(row); continue
        terminal,_ = replay(sample,row,manifest,binding,root,receipts,subset,validator); states.append(terminal['state'])
        if terminal.get('native_thread_id'):
            require(terminal['native_thread_id'] not in native_ids,'Duplicate native UUID'); native_ids.add(terminal['native_thread_id'])
    if args.validate_only:
        print(json.dumps({'state':'provider_free_validated','manifest_sha256':args.manifest_sha256,'endpoint':args.endpoint,
            'planned':232,'untouched':len(pending),'terminal_states':dict(Counter(states)),'provider_calls':0,
            'diagnostic_scalar_eligible':False,'model_read_whole_body_proven':False})); return 0
    require(all(state in SETTLED for state in states),'Incomplete occupied native attempt requires reconciliation; no resend')
    if (output/'STOP').exists(): t.note_stop(output); return 3
    if not pending: return 0
    helper = call_codex = broker = None
    if args.endpoint == 'sol':
        source = source_settings(manifest,root)
        helper = p.load('p4_judging_secondary_helper',Path(source['external_pins']['secondary_helper_path_local_only']))
        env = t.secondary_binding(source,helper); os.environ.clear(); os.environ.update(env)
        sys.path.insert(0,str(args.tools_root)); from adaptive_settings.account_probe import probe
        from hbqrs import runner
        t.secondary_binding(source,helper,probe(helper.CLI)); call_codex = runner._call_codex
    else:
        require(grok_contact_allowed(route),'Route expiry/campaign deadline prevents new contact')
        sys.path.insert(0,str(args.tools_root)); from model_work_queue.broker import Broker
        broker = Broker(args.route_root.resolve())
    if not output.exists():
        output.mkdir(parents=True,exist_ok=False); record(output/'job.json',binding); write_bytes(output/'frozen-manifest.json',args.manifest.read_bytes())
    if args.endpoint == 'sol':
        expected = t.account_receipt(binding)
        if (output/'account-binding.json').exists(): require(json.loads((output/'account-binding.json').read_bytes()) == expected,'Retained account receipt differs')
        else: record(output/'account-binding.json',expected)
    for row in pending[:args.limit]:
        if (output/'STOP').exists(): t.note_stop(output); return 3
        if args.endpoint == 'grok' and not grok_contact_allowed(route): return 3
        state = collect_one(row,manifest,binding,root,output,subset,validator,receipts,helper,call_codex,broker)
        print(json.dumps({'ordinal':row['endpoint_ordinal'],'state':state,'contract':row['contract']}),flush=True)
        if state not in SETTLED: return 3
    return 0


if __name__ == '__main__': raise SystemExit(main())
