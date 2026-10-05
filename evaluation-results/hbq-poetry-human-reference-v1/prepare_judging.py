"""Prospective 960-request presented-poetry plan; sealed human targets stay closed."""
from __future__ import annotations

from collections import Counter,defaultdict
import argparse
import importlib.util
import json
from pathlib import Path
import re
import sys

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[1]
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module

generation=load('poetry_judging_runtime_generation',HERE.parent/'hbq-semantic-crossform-p1b-v1/collect.py')
base=generation.prepare
mfa=load('poetry_judging_schema_projection',HERE.parent/'hbq-matched-mfa-v1/prepare.py')
canonical,digest,require=base.canonical,base.digest,base.require
POLICY='study2_presented_poetry_matched_v1'
REFERENCE_SHA='f58a41dffdefb19fa61a45f39c6b0e2b0b51e93533f0fef7f55700324b0536f2'
PROJECTOR_SHA='1bee226769292c9e889621f942c81357728244965ad19c1fd03902b9380d9a1f'
RUNTIME_SHA='45c7ad4ea2eee0d8acecd877d8a1f9f27854c2d537b53fd9b27a0da7956cbb68'
SECONDARY_ACCOUNT_SHA='a283be8dc909b7f172c1a348c38883deb00394b66de29023cbe45de4bbc37d3d'
BUNDLE='poetry.general'
BANK_COUNTS={'domain_questions':66,'hard_gates':0,'penalty_questions':18,'supplemental_questions':11}
ENDPOINTS=('grok','sol')
ARM_COUNTS={'hbq':360,'holistic':30,'compact':30,'poemetric':30,'pairwise':30}
DIMENSIONS=['poetic_architecture','image_relations','language_voice','rhythm_lineation','emotional_reader_effect','meaning_resonance']
CONTEXT={'artifact_kind':'poetry','declared_scope':'poem','completion_status':'unknown','background':[],
    'constraints':['Assess only the presented poetic artifact. Original full-work boundaries, author brief, intended audience and origin are unavailable.',
        'Poetic form is unspecified. Assess visible execution on its own terms; do not require fixed rhyme, meter, linear narrative, closure or novelty without a supplied requirement.'],
    'audience':[]}
SOURCE_POLICY=('SOURCE ORIGIN POLICY: Origin information is unavailable and deliberately excluded. '
    'The default AI-origin assumption does not apply. Do not infer author, human/AI origin, reputation, human ratings or other-arm judgments. '
    'Evaluate only the exact presented text and common context.\n')
HUMAN_GATE={'policy':'all_planned_verified_terminals_plus_explicit_postprediction_release_v1',
    'requests_required':960,'endpoints':list(ENDPOINTS),'explicit_release_flag_required':True,
    'verified_terminal_replay_required':True,'untouched_or_inflight_blocks_release':True,
    'semantic_rejections_remain_missing':True,'preparation_opens_human_targets':False,
    'preparation_grants_judging_authority':False}


def metadata(path,raw):return {'path':path,'sha256':digest(raw),'bytes':len(raw)}


def pinned(root,name,meta):
    path=(root/name).resolve();require(path.is_relative_to(root.resolve()),'Input path leaves its source root')
    raw=path.read_bytes();require(digest(raw)==meta['sha256'] and len(raw)==meta['bytes'],'Frozen input differs')
    return raw


def read_reference(path):
    raw=path.read_bytes();require(digest(raw)==REFERENCE_SHA,'Exact source-reference manifest differs')
    manifest=json.loads(raw);root=path.resolve().parent
    require(manifest['policy']=='study2_outcome_blind_poetry_source_v1' and manifest['targets_sealed'] is True
        and manifest['prediction_release_authorized'] is False,'Sealed reference contract differs')
    projector=pinned(root,'implementation/prepare_sources.py',manifest['artifacts']['implementation/prepare_sources.py'])
    require(digest(projector)==PROJECTOR_SHA,'Source projection implementation differs')
    texts={}
    for name,meta in manifest['artifacts'].items():
        match=re.fullmatch(r'sealed/texts/(poem-[a-f0-9]{24})\.qsf\.txt',name)
        if match:
            value=pinned(root,name,meta);value.decode('utf-8')
            texts[match[1]]={'raw':value,'source_path':name,'sha256':digest(value),'bytes':len(value)}
    require(len(texts)==10 and len({v['sha256'] for v in texts.values()})==10,'Ten unique QSF projections required')
    return texts,{'private/reference-manifest.json':raw,'implementation/source-projector.py':projector},manifest


def runtime_inputs(path):
    manifest,root,sha=base.read_manifest(path)
    require(sha==RUNTIME_SHA,'Designated native runtime source differs');generation.verify_external_pins(manifest)
    runtime=manifest['runtime']
    require(runtime['model']=='gpt-6.1-sol' and runtime['reasoning']=='high' and runtime['timeout_seconds']==900
        and runtime['workers']==runtime['attempts_per_logical_sample']==1 and runtime['automatic_retries']==0
        and runtime['receipt_policy']=='codex_native_rollout_v1' and runtime['account_identity_sha256']==SECONDARY_ACCOUNT_SHA,
        'Expected secondary native runtime differs')
    files={'private/source-generation-manifest.json':path.read_bytes()}
    for name in ('secondary-helper.py','runner.py','codex_receipts.py','schema_subset.py'):
        files['implementation/'+name]=pinned(root,'implementation/'+name,manifest['artifacts']['implementation/'+name])
    for name in ('prepare.py','collect.py'):
        files['implementation/generation-'+name]=pinned(root,'implementation/'+name,manifest['artifacts']['implementation/'+name])
    return manifest,files,load('poetry_frozen_schema_subset',root/'implementation/schema_subset.py')


def task_contract(artifact_id):
    return {'contract_version':1,'contract_id':POLICY,'artifact_id':artifact_id,'context':CONTEXT,
        'preferences':[],'priorities':[],'weighted_goals':[],'binding_requirements':[]}


def arm_assets(files):
    assets={}
    for arm in ('holistic','compact','pairwise','poemetric'):
        prompt=(HERE/'arms'/f'{arm}.prompt.md').read_bytes()
        source=(HERE/'arms/poemetric.schema.json') if arm=='poemetric' else HERE.parent/'hbq-matched-mfa-v1/arms'/f'{arm}.schema.json'
        raw=source.read_bytes();schema=json.loads(raw)
        if arm!='poemetric':
            properties=schema['properties'] if arm=='pairwise' else schema['properties']['result']['properties']
            properties['method']['enum']=['study2_presented_poem_'+arm+'_v1']
            if arm=='compact':properties['dimensions']['items']['properties']['dimension_id']['enum']=DIMENSIONS
        files[f'arms/{arm}.prompt.md']=prompt;files[f'arms/{arm}.original.schema.json']=raw
        files[f'arms/{arm}.retained.schema.json']=canonical(schema)
        assets[arm]=(prompt.decode('utf-8'),schema)
    return assets


def selection(texts):
    ordered=sorted(texts,key=lambda tid:digest(canonical([POLICY,'disjoint_pair_order_v1',tid])))
    return [{'pair_id':'pair-'+digest(canonical([POLICY,'pair_v1',sorted(ordered[i:i+2])]))[:24],
        'left':ordered[i],'right':ordered[i+1]} for i in range(0,10,2)]


def build_design(texts,source_files,reference,runtime,runtime_files,subset):
    sys.path.insert(0,str(REPO/'src'))
    from hbqrs import core,runner
    from jsonschema import Draft202012Validator
    files={**source_files,**runtime_files}
    paths={'registry/all_modules.yaml':REPO/'registry/all_modules.yaml','bundles/all_bundles.yaml':REPO/'bundles/all_bundles.yaml',
        'schema/hbq_task_contract.schema.json':REPO/'schema/hbq_task_contract.schema.json',
        'schema/hbq_judge_response.schema.json':REPO/'schema/hbq_judge_response.schema.json',
        'schema/hbq_verdict.schema.json':REPO/'schema/hbq_verdict.schema.json',
        'schema/hbq_score_report.v2.schema.json':REPO/'schema/hbq_score_report.v2.schema.json',
        'prompts/BINARY_EVALUATION_PROMPT.md':REPO/'prompts/judge/BINARY_EVALUATION_PROMPT.md',
        'implementation/core.py':REPO/'src/hbqrs/core.py','implementation/runner.py':REPO/'src/hbqrs/runner.py',
        'implementation/scoring_v2.py':REPO/'src/hbqrs/scoring_v2.py',
        'implementation/prepare_judging.py':HERE/'prepare_judging.py',
        'implementation/validate_response.py':HERE/'arms/validate_response.py',
        'implementation/mfa-admission.py':HERE.parent/'hbq-matched-mfa-v1/validate_response.py',
        'implementation/mfa-prepare.py':Path(mfa.__file__)}
    files.update({name:path.read_bytes() for name,path in paths.items()})
    modules=core.load_modules(paths['registry/all_modules.yaml']);bundles=core.load_bundles(paths['bundles/all_bundles.yaml'])
    compiled=core.compile_bundle(modules,core.resolve_bundle(bundles,BUNDLE));questions=core.compiled_questions(compiled)
    require(compiled['counts']==BANK_COUNTS and len(questions)==len({q['question']['id'] for q in questions})==95,'Generic poetry bank differs')
    alias=core.compile_bundle(modules,core.resolve_bundle(bundles,'default.general_poem'))
    require(core.compiled_questions(alias)==questions,'Generic poetry alias differs')
    files['compiled/'+BUNDLE+'.json']=canonical(compiled);compiled_sha=digest(files['compiled/'+BUNDLE+'.json'])
    assets=arm_assets(files);contracts={};common=None
    for tid,item in sorted(texts.items()):
        require(digest(item['raw'])==item['sha256'] and len(item['raw'])==item['bytes'],'Selected text differs')
        task=task_contract(tid);Draft202012Validator(json.loads(files['schema/hbq_task_contract.schema.json'])).validate(task)
        contextual=core.compile_bundle(modules,core.resolve_bundle(bundles,BUNDLE),task_contract=task)
        require(core.compiled_questions(contextual)==questions and contextual['counts']==BANK_COUNTS,'Context changed canonical bank')
        contracts[tid]=task;files['contracts/'+tid+'.json']=canonical(task);files['inputs/'+tid+'.txt']=item['raw']
        raw=json.dumps(runner._task_contract_judge_context(task),ensure_ascii=False,indent=2).encode('utf-8')
        require(common is None or common==raw,'Common task projection differs across texts');common=raw
    context_path='contexts/'+digest(common)+'.json';files[context_path]=common;context_meta=metadata(context_path,common)
    pairs=selection(texts);files['selection.json']=canonical({'policy':'salted_opaque_metadata_disjoint_pairs_v1','pairs':pairs,
        'bank_ids':sorted(texts),'cycles':[0,1,2],'uses_outcomes':False})
    units=[]
    for cycle in range(3):
        for tid in sorted(texts):
            units.extend({'arm':'hbq','repeat':cycle,'artifact_id':tid,'batch':batch} for batch in range(1,13))
            units.extend({'arm':arm,'repeat':cycle,'artifact_id':tid,'batch':1} for arm in ('holistic','compact','poemetric'))
        units.extend({'arm':'pairwise','repeat':cycle,'pair_id':pair['pair_id'],'orientation':orientation,'batch':1}
            for pair in pairs for orientation in ('AB','BA'))
    units.sort(key=lambda unit:(unit['repeat'],digest(canonical([POLICY,'dispatch_order_v1',unit]))))
    pair_lookup={p['pair_id']:p for p in pairs};requests=[];ordinals=Counter()
    for unit in units:
        arm=unit['arm'];ids=[unit['artifact_id']] if arm!='pairwise' else [pair_lookup[unit['pair_id']][side] for side in ('left','right')]
        if unit.get('orientation')=='BA':ids.reverse()
        packet=questions[(unit['batch']-1)*8:unit['batch']*8] if arm=='hbq' else []
        schema=runner._batch_response_schema([q['question']['id'] for q in packet]) if arm=='hbq' else assets[arm][1]
        retained=canonical(schema);portable=mfa.portable_schema(schema);subset.validate_schema(portable);schema_raw=canonical(portable)
        retained_path='retained-schemas/'+digest(retained)+'.json';schema_path='schemas/'+digest(schema_raw)+'.json'
        files[retained_path],files[schema_path]=retained,schema_raw
        if arm=='hbq':
            marker='__STUDY2_EXACT_POEM_SPLICE_V1__'
            raw_text=texts[ids[0]]['raw'].decode('utf-8');require(marker not in raw_text,'Source splice marker collides')
            prompt=runner._render_prompt(binary_prompt=SOURCE_POLICY+files['prompts/BINARY_EVALUATION_PROMPT.md'].decode(),
                artifact={'name':ids[0],'text':marker},contexts=[],bundle_id=BUNDLE,artifact_id=ids[0],questions=packet,
                task_contract_context=runner._task_contract_judge_context(contracts[ids[0]]))
            require(prompt.count(marker)==1,'Source splice renderer differs');prompt=prompt.replace(marker,raw_text,1)
        else:
            prompt=SOURCE_POLICY+assets[arm][0]+'\n## Exact common task context\n\n'+common.decode('utf-8')
            for at,tid in enumerate(ids):prompt+='\n## Artifact'+(' '+'AB'[at] if arm=='pairwise' else '')+'\n\n'+texts[tid]['raw'].decode('utf-8')+'\n'
        raw=prompt.encode('utf-8');require(common in raw and all(texts[tid]['raw'] in raw for tid in ids),'Exact declared source/context absent from prompt')
        prompt_path='prompts/'+digest(raw)+'.txt';files[prompt_path]=raw
        sources=[{'id':tid,'input_path':'inputs/'+tid+'.txt','reference_projection_path':texts[tid]['source_path'],
            'sha256':texts[tid]['sha256'],'bytes':texts[tid]['bytes'],
            **({'side':'AB'[at]} if arm=='pairwise' else {})} for at,tid in enumerate(ids)]
        condition={**unit,'contract':'presented_poem_baseline','form':'unspecified','bundle_id':BUNDLE,
            'question_ids':[q['question']['id'] for q in packet],'sources':sources,'task_context':context_meta,
            'task_contracts':[{'artifact_id':tid,'path':'contracts/'+tid+'.json','sha256':digest(files['contracts/'+tid+'.json'])} for tid in ids],
            'compiled_sha256':compiled_sha,'full_bank_score_eligible':arm=='hbq','presented_artifact_score':True,
            'whole_original_author_work_score_eligible':False,'completion_status':'unknown',
            'prompt_policy':'blinded_source_origin_unspecified_v1','rendering_policy':'exact_source_body_splice_v1' if arm=='hbq' else 'exact_source_concat_v1',
            'prompt_path':prompt_path,'prompt_sha256':digest(raw),'prompt_bytes':len(raw),
            'schema_path':schema_path,'schema_sha256':digest(schema_raw),'schema_bytes':len(schema_raw),
            'retained_schema_path':retained_path,'retained_schema_sha256':digest(retained)}
        logical=digest(canonical(condition));endpoints=ENDPOINTS if int(logical[-1],16)%2==0 else ENDPOINTS[::-1]
        for endpoint in endpoints:
            ordinals[endpoint]+=1;row={**condition,'logical_sample_id':logical,'endpoint':endpoint,
                'endpoint_ordinal':ordinals[endpoint],'ordinal':len(requests)+1};row['request_sha256']=digest(canonical(row));requests.append(row)
    tools=Path(runtime['external_pins']['tools_root_local_only'])
    fingerprints={name:digest((tools/path).read_bytes()) for name,path in {
        'account_probe':'adaptive_settings/account_probe.py','broker':'model_work_queue/broker.py',
        'grok_adapter':'model_work_queue/adapters/grok_exec.py'}.items()}
    manifest={'schema_version':1,'study_id':POLICY,'stage':'prospective_judging_preparation_only','candidate':None,
        'oracle_accepted':False,'human_labels_supplied':0,'human_alignment_claim':False,'execution_authority':False,
        'provider_calls_by_preparation':0,'unused_data_certification':False,'rights_claim':False,
        'reference_manifest_file_sha256':REFERENCE_SHA,'source_projection_sha256':PROJECTOR_SHA,
        'source_projection_contract_sha256':reference['contract_sha256'],'source_generation_manifest_file_sha256':RUNTIME_SHA,
        'runtime':{**runtime['runtime'],'outbound_artifacts':'Exact presented QSF text projections, common task context, canonical questions/adapted comparator criteria and response schemas only; no human values, source catalogues or authorship metadata.',
            'secondary_account_expectation_only':True,'native_execution_proven':False},
        'external_pins':runtime['external_pins'],'route_compatibility_fingerprints':fingerprints,
        'endpoint_plan':{'sol':{'model':'gpt-6.1-sol','reasoning':'high','timeout_seconds':900,'workers':1},
            'grok':{'model':'grok-4.7','reasoning':'high','timeout_seconds':900,'workers':1,
                'reviewed_route_binding_required_at_launch':True,'cutoff_utc':'2026-10-16T05:40:00Z','deadline_margin_seconds':900,
                'earlier_route_expiry_remains_binding':True}},
        'human_label_gate':HUMAN_GATE,'requests':requests,'pairs':pairs,'bank_ids':sorted(texts),
        'counts':{'texts':10,'cycles':3,'bank_leaves':95,'bank_packets':12,'banks_per_endpoint':30,
            'disjoint_pairs':5,'requests_per_endpoint':480,'requests_total':960,'arms_per_endpoint':ARM_COUNTS},
        'order_policy':'Salted opaque metadata shuffle within cycle; canonical packet membership and question order fixed across repeats; no question-order causal test.',
        'pair_policy':'Five metadata-hash-disjoint pairs covering all ten texts; AB/BA in three cycles; matched contrasts, not a ranking graph.',
        'poemetric_policy':'poemetric_unspecified_form_descendant_v1; original fixed-form scope caveat; items1/2 CA/null, item10 independent primary1–5, no aggregate, absence0 only7/8; comments9/11 structured local evidence.',
        'poemetric_source':{'url':'https://arxiv.org/pdf/2604.03695v1','revision':'v1','date':'2026-04-04',
            'location':'Appendix C, printed pages21–23; fixed-form study scope in section7',
            'criteria':'Paraphrased descendant; unspecified-form abstention, exact quotations, structured comments and schema are adaptations.'},
        'score_contract':'Complete unique admitted95-leaf/12-packet bank before canonical scoring; positive/penalty completeness and sensitivity bounds remain separate; presented stimulus only.',
        'limitations':['Ten public pre-existing stimuli; familiarity and prior public showcase/aggregate exposure remain possible.',
            'Original full-author-work boundaries, forms, briefs and audiences are unavailable; no invented brief or fixed-form designation.',
            'Comparator prompts are named adaptations; POEMetric construct transfer is not validated for this source scope.',
            'Native scales stay separate; no cross-arm mean, inferred authorship, human-alignment or population-generalization claim.',
            'Preparation grants no provider contact, human-label opening, scoring-candidate promotion or rights certification.'],
        'artifacts':{name:metadata(name,raw) for name,raw in sorted(files.items())}}
    validate_design(manifest,files);files['manifest.json']=canonical(manifest);return manifest,files


def validate_design(manifest,files):
    require(manifest['counts']['requests_total']==len(manifest['requests'])==960 and manifest['human_label_gate']==HUMAN_GATE,'Planned denominator or label gate differs')
    for name,meta in manifest['artifacts'].items():
        require(name in files and digest(files[name])==meta['sha256'] and len(files[name])==meta['bytes'],'Frozen artifact commitment differs')
    compiled=json.loads(files['compiled/'+BUNDLE+'.json'])
    from hbqrs import core
    ids=[q['question']['id'] for q in core.compiled_questions(compiled)]
    require(compiled['counts']==BANK_COUNTS and len(ids)==len(set(ids))==95,'Canonical bank differs')
    banks_expected={(tid,cycle) for tid in manifest['bank_ids'] for cycle in range(3)}
    require(len(manifest['bank_ids'])==len(set(manifest['bank_ids']))==10 and len(manifest['pairs'])==5
        and Counter(tid for pair in manifest['pairs'] for tid in (pair['left'],pair['right']))==Counter(manifest['bank_ids']), 'Source or disjoint pair geometry differs')
    for endpoint in ENDPOINTS:
        rows=[r for r in manifest['requests'] if r['endpoint']==endpoint]
        require(len(rows)==480 and [r['endpoint_ordinal'] for r in rows]==list(range(1,481))
            and Counter(r['arm'] for r in rows)==Counter(ARM_COUNTS)
            and len({r['logical_sample_id'] for r in rows})==480,'Endpoint inventory differs')
        banks=defaultdict(list);native=Counter();pair_units=Counter()
        for row in rows:
            require(row['completion_status']=='unknown' and row['whole_original_author_work_score_eligible'] is False
                and row['full_bank_score_eligible']==(row['arm']=='hbq') and row['form']=='unspecified'
                and row['bundle_id']==BUNDLE,'Scope/scoring flags differ')
            require(digest(canonical({k:v for k,v in row.items() if k!='request_sha256'}))==row['request_sha256']
                and digest(canonical({k:v for k,v in row.items() if k not in ('logical_sample_id','endpoint','endpoint_ordinal','ordinal','request_sha256')}))==row['logical_sample_id'], 'Request/logical commitment differs')
            for name in ('prompt','schema'):
                raw=files[row[name+'_path']];require(digest(raw)==row[name+'_sha256'] and len(raw)==row[name+'_bytes'],'Exact request payload differs')
            require(digest(files[row['retained_schema_path']])==row['retained_schema_sha256']
                and digest(files['compiled/'+BUNDLE+'.json'])==row['compiled_sha256']
                and metadata(row['task_context']['path'],files[row['task_context']['path']])==row['task_context']
                and all(digest(files[task['path']])==task['sha256'] for task in row['task_contracts']), 'Schema/compiler/context commitment differs')
            require(files[row['task_context']['path']] in files[row['prompt_path']]
                and all(files[s['input_path']] in files[row['prompt_path']] and digest(files[s['input_path']])==s['sha256']
                    and len(files[s['input_path']])==s['bytes'] for s in row['sources']), 'Declared source/context binding differs')
            if row['arm']=='hbq':banks[(row['artifact_id'],row['repeat'])].append(row)
            elif row['arm']=='pairwise':pair_units[(row['pair_id'],row['repeat'],row['orientation'])]+=1
            else:native[(row['artifact_id'],row['repeat'],row['arm'])]+=1
        require(set(banks)==banks_expected and all(len(bank)==12 and [qid for row in sorted(bank,key=lambda r:r['batch']) for qid in row['question_ids']]==ids for bank in banks.values()),'Full unique canonical banks required')
        require(native==Counter({(tid,cycle,arm):1 for tid in manifest['bank_ids'] for cycle in range(3) for arm in ('holistic','compact','poemetric')}), 'Native repetition inventory differs')
        require(pair_units==Counter({(p['pair_id'],cycle,orientation):1 for p in manifest['pairs'] for cycle in range(3) for orientation in ('AB','BA')}),'Pair orientation/repetition differs')
    require({r['logical_sample_id'] for r in manifest['requests'] if r['endpoint']=='sol'}=={r['logical_sample_id'] for r in manifest['requests'] if r['endpoint']=='grok'},'Matched endpoint inventory differs')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('reference-manifest','runtime-manifest','output-root'):parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--dry-run',action='store_true');args=parser.parse_args()
    base.output_preflight(args.output_root,(args.reference_manifest.resolve().parent,args.runtime_manifest.resolve().parent))
    texts,source_files,reference=read_reference(args.reference_manifest)
    runtime,runtime_files,subset=runtime_inputs(args.runtime_manifest)
    manifest,files=build_design(texts,source_files,reference,runtime,runtime_files,subset)
    if not args.dry_run:
        for name,raw in files.items():base.write_new(args.output_root/name,raw)
    print(json.dumps({'dry_run':args.dry_run,'counts':manifest['counts'],'manifest_file_sha256':digest(files['manifest.json']),
        'reference_manifest_file_sha256':REFERENCE_SHA,'source_projection_sha256':PROJECTOR_SHA,
        'prepare_judging_sha256':digest(Path(__file__).read_bytes()),'artifact_bytes':sum(map(len,files.values())),
        'prompt_bytes':sum(row['prompt_bytes'] for row in manifest['requests']),
        'human_label_gate_closed':True,'human_values_opened':False,'provider_calls':0,'execution_authority':False,
        'output_written':not args.dry_run},sort_keys=True));return 0


if __name__=='__main__':raise SystemExit(main())
