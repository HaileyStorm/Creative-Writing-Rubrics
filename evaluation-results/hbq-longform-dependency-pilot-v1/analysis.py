"""Provider-free P4 descriptions; source-access diagnostics are not whole-work scores."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from itertools import combinations
import importlib.util
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('p4_analysis_collector',HERE/'collector.py')
c = importlib.util.module_from_spec(spec); spec.loader.exec_module(c)
UTILITY_PATH = HERE.parent/'hbq-semantic-crossform-p1b-matched-v1/analysis.py'
UTILITY_SHA = 'e158e278b29a0a2ade3aeae4691a86ba70d1a9f1f618b3a94a2d33d43ee5fd04'
d = c.p.load('p4_descriptive_arithmetic',UTILITY_PATH)
POLICY = 'longform_source_access_descriptive_analysis_v1'
MANIFEST_SHA = 'd0cb6589924a4900b123206f40595035a6d792c623bac1c8303de9d95bac1ac4'
COLLECTOR_SHA = '0425421d9cdcbcc706c69e5eae16724079ddd05d0d670962707105724721525f'
TOKEN_FIELDS = d.TOKEN_FIELDS


def collect_evidence(manifest,manifest_sha,root,results,tools,subset,validator,receipts):
    candidates,inventory,commitments = [],[],[]
    native_items = defaultdict(list)
    for endpoint in c.p.ENDPOINTS:
        output = results[endpoint]; binding,valid = None,True
        if output.exists():
            try:
                binding = json.loads((output/'job.json').read_bytes())
                c.require(binding == c.job_binding(manifest,root,manifest_sha,endpoint,tools,binding.get('route'),COLLECTOR_SHA)
                    and c.digest((output/'frozen-manifest.json').read_bytes()) == manifest_sha,'Job/raw manifest differs')
                if endpoint == 'sol': c.require(json.loads((output/'account-binding.json').read_bytes()) == c.t.account_receipt(binding),'Own account differs')
            except (ValueError,OSError,KeyError,TypeError): valid = False
        for row in (r for r in manifest['requests'] if r['endpoint']==endpoint):
            sample = c.sample_path(output,row)
            item = {'request':row,'state':'untouched','native_metrics':{f:None for f in (*TOKEN_FIELDS,'latency_seconds')}}
            if not valid: item['state'] = 'job_unadmitted'
            elif not sample.exists(): pass
            elif not (sample/'terminal.json').is_file(): item['state'] = 'started_unresolved'
            else:
                try:
                    terminal,answer = c.replay(sample,row,manifest,binding,root,receipts,subset,validator)
                    item['state'] = terminal['state']; item['native_metrics'] = d.native_metrics(sample,row,terminal)
                    commitments.append({'endpoint':endpoint,'logical_sample_id':row['logical_sample_id'],'terminal_sha256':c.digest((sample/'terminal.json').read_bytes())})
                    if terminal.get('native_thread_id'): native_items[(endpoint,terminal['native_thread_id'])].append(item)
                    if answer is not None: candidates.append({'request':row,'response':answer})
                except (ValueError,OSError,KeyError,TypeError): item['state'] = 'replay_unadmitted'
            inventory.append(item)
    duplicate_ids = set()
    for items in native_items.values():
        if len(items)>1:
            for item in items:
                item['state'] = 'duplicate_native_unadmitted'; duplicate_ids.add(item['request']['request_sha256'])
    return [r for r in candidates if r['request']['request_sha256'] not in duplicate_ids],inventory,commitments


def load_hbq(manifest,root):
    sys.path.insert(0,str(c.p.REPO/'src'))
    from hbqrs import core,runner,scoring_v2
    for module,name in [(core,'core.py'),(runner,'runner.py'),(scoring_v2,'scoring_v2.py')]:
        c.require(c.digest(Path(module.__file__).read_bytes()) == manifest['artifacts']['implementation/'+name]['sha256'],'Frozen canonical scoring code differs')
    modules = core.load_modules(root/'registry/all_modules.yaml')
    bundle = core.resolve_bundle(core.load_bundles(root/'bundles/all_bundles.yaml'),'prose.novella')
    schemas = {name:c.digest((c.p.REPO/'schema'/name).read_bytes()) for name in ('hbq_verdict.schema.json','hbq_score_report.v2.schema.json')}
    return {'core':core,'runner':runner,'scorer':scoring_v2,'modules':modules,'bundle':bundle,'analysis_time_schema_sha256':schemas}


def native_coverage(leaves,expected):
    states = Counter(v['verdict'] for v in leaves)
    applicable = len(leaves)-states['NOT_APPLICABLE']; assessed = states['YES']+states['NO']
    return {'planned_leaves':expected,'observed_admitted_leaves':len(leaves),'missing_leaves':expected-len(leaves),
        'native_states':dict(states),'assessed_binary':assessed,'observed_applicable':applicable,
        'assessed_over_observed_applicable':d.fraction(assessed,applicable)}


def score_bank(planned,admitted,hbq,root,manifest):
    row = planned[0]; frozen = json.loads(c.pinned(root,'compiled/prose.novella.json',manifest['artifacts']['compiled/prose.novella.json']))
    questions = hbq['core'].compiled_questions(frozen); ids = [q['question']['id'] for q in questions]
    leaves = [v for item in admitted for v in item['response']['verdicts']]
    states = {v['question_id']:v['verdict'] for v in leaves}
    role_ids = {role:{q['question']['id'] for q in questions if q['role']==role} for role in ('domain','hard_gate','penalty','supplemental')}
    base = {'value':None,'native_scale':[0,100],'near_threshold_increment':5,'state':'incomplete_or_nonunique_full_bank_no_scalar',
        'native_coverage':native_coverage(leaves,219),'leaf_states':states,'dimensions':{},'weighted_coverage':None,
        'sensitivity_bounds':None,'hard_gate_status':None,'fully_assessed_point_score':False,
        'roles':{role:native_coverage([v for v in leaves if v['question_id'] in qids],len(qids)) for role,qids in role_ids.items()}}
    if (len(planned)!=28 or not (len(ids)==len(set(ids))==219)
        or [q for r in sorted(planned,key=lambda r:r['batch']) for q in r['question_ids']]!=ids
        or Counter(r['request_sha256'] for r in planned)!=Counter(item['request']['request_sha256'] for item in admitted)
        or len(leaves)!=219 or Counter(v['question_id'] for v in leaves)!=Counter(ids)):
        return base
    if any(r['contract']!='whole_work_baseline' or r['context_arm']!='raw_full' or r['arm']!='hbq'
        or r['full_bank_score_eligible'] is not True or r['whole_work_artistic_score'] is not True for r in planned):
        return {**base,'state':'unsupported_scope_no_scalar'}
    try:
        contract_meta = row['task_contracts'][0]
        contract = json.loads(c.pinned(root,contract_meta['path'],manifest['artifacts'][contract_meta['path']]))
        c.require(contract == c.p.task_contract(row['work_id'],False),'Whole-work task contract differs')
        compiled = hbq['core'].compile_bundle(hbq['modules'],hbq['bundle'],task_contract=contract)
        c.require(hbq['core'].compiled_questions(compiled)==questions,'Context-aware full bank differs')
        normalized = []
        for item in sorted(admitted,key=lambda item:item['request']['batch']):
            request = item['request']; _,_,texts,context = c.inputs(root,manifest,request)
            c.require(request['work_id']==row['work_id'] and request['task_context']==row['task_context']
                and request['target_original']==row['target_original'],'Whole-bank frozen source/context differs')
            normalized.extend(hbq['runner']._normalize_batch(item['response'],expected_ids=request['question_ids'],
                artifact_id=row['artifact_id'],bundle_id='prose.novella',judge_id=row['endpoint'],run_id=request['logical_sample_id'],
                artifact_text=texts[row['work_id']],context_texts=[context]))
        report = hbq['scorer'].score_bundle(hbq['modules'],hbq['bundle'],normalized,artifact_id=row['artifact_id'],
            task_contract=contract,admission_policy='strict_import_v1')
    except (ValueError,KeyError,TypeError): return {**base,'state':'strict_import_unadmitted_no_scalar'}
    final = report['final_score']; value = final['observed'] if report['status']=='SCORED' else None
    point = (value is not None and report['hard_gate_status']=='VALID' and report['coverage']==1
        and all(p['coverage']==1 for p in report['penalties']) and final['lower']==final['upper'])
    return {**base,'value':value,'state':report['status'],'weighted_coverage':report['coverage'],
        'base_score':report['base_score'],'penalty_deduction':report['penalty_deduction'],
        'sensitivity_bounds':{'lower':final['lower'],'upper':final['upper']},
        'uncertainty_width':None if final['lower'] is None else final['upper']-final['lower'],
        'hard_gate_status':report['hard_gate_status'],'fully_assessed_point_score':point,
        'hard_gates':[{'question_id':g['question_id'],'verdict':g['verdict']} for g in report['hard_gates']],
        'domains':[{k:r[k] for k in ('domain_id','nominal_points','active','weights','coverage','score')} for r in report['domains']],
        'penalties':[{k:r[k] for k in ('module_id','cap_points','weights','coverage','deduction')} for r in report['penalties']],
        'supplemental_effective_states':dict(Counter(r['verdict'] for r in report['supplemental'])),
        'scoring_policy':'frozen_canonical_scoring_v2_with_historical_cumulative_enforcement'}


def identity(row):
    return (row['contract'],row['endpoint'],row['work_id'],row.get('case_id',''),row['context_arm'],row['repeat'],row['arm'])


def profiles(manifest,records,hbq,root):
    planned,admitted = defaultdict(list),defaultdict(list)
    for row in manifest['requests']: planned[identity(row)].append(row)
    for record in records: admitted[identity(record['request'])].append(record)
    output = {}
    for key,rows in planned.items():
        items = admitted[key]; row = rows[0]; diagnostic = key[0]=='unscored_dependency_diagnostic'
        if row['arm']=='hbq' and not diagnostic: output[key] = score_bank(rows,items,hbq,root,manifest); continue
        base = {'value':None,'state':'missing_unadmitted','dimensions':{},'leaf_states':{},'whole_work_quality_scalar':None}
        if row['arm']=='hbq':
            leaves = [v for item in items for v in item['response']['verdicts']]
            output[key] = {**base,'state':'native_leaf_diagnostic' if len(items)==1 else 'missing_unadmitted',
                'native_scale':None,'near_threshold_increment':None,'native_coverage':native_coverage(leaves,3),
                'leaf_states':{v['question_id']:v['verdict'] for v in leaves}}
        else:
            schema = json.loads(c.pinned(root,row['schema_path'],manifest['artifacts'][row['schema_path']]))
            dims = d.missing_dimensions(row['arm'],schema)
            native = d.scalar_profile(row['arm'],items[0]['response']) if len(items)==1 else None
            output[key] = {**base,'native_scale':[1,7] if row['arm']=='holistic' else [1,5],'near_threshold_increment':1,
                'dimensions':dims,'rating_scope':'declared_dependency_only' if diagnostic else 'whole_original_novella'}
            if native:
                output[key].update(value=native['score'],state=native['state'],dimensions={**dims,**native['dimensions']})
                if not diagnostic: output[key]['whole_work_quality_scalar'] = native['score']
    return output


def contrast(pairs,kind):
    left,right,native_left,native_right,binary_left,binary_right = [],[],[],[],[],[]
    dims = defaultdict(lambda:([ ],[ ])); expected_leaves = 0; transitions = Counter()
    for a,b in pairs:
        if a['value'] is not None and b['value'] is not None: left.append(a['value']); right.append(b['value'])
        expected_leaves += a.get('native_coverage',{}).get('planned_leaves',0)
        for qid in a['leaf_states'].keys() & b['leaf_states'].keys():
            x,y = a['leaf_states'][qid],b['leaf_states'][qid]; native_left.append(x); native_right.append(y); transitions[(x,y)] += 1
            if x in ('YES','NO') and y in ('YES','NO'): binary_left.append(x); binary_right.append(y)
        for dim in a['dimensions'].keys() | b['dimensions'].keys():
            x,y = a['dimensions'].get(dim,{}).get('value'),b['dimensions'].get(dim,{}).get('value')
            if x is not None and y is not None: dims[dim][0].append(x); dims[dim][1].append(y)
            else: dims[dim]
    return {'planned_paired_items':len(pairs),'native_rating_difference':d.scalar_differences(left,right,len(pairs)),
        'rating_interpretation':'Scoped dependency ratings only; no whole-work scalar' if kind=='unscored_dependency_diagnostic' else 'Same native arm/scale only',
        'native_leaf_agreement':d.agreement(native_left,native_right,expected_leaves) if expected_leaves else None,
        'binary_leaf_agreement':d.agreement(binary_left,binary_right,expected_leaves) if expected_leaves else None,
        'native_state_transitions':[{'left':x,'right':y,'count':n} for (x,y),n in sorted(transitions.items())],
        'dimensions':{dim:d.scalar_differences(x,y,len(pairs)) for dim,(x,y) in sorted(dims.items())}}


def comparisons(item_profiles):
    groups = defaultdict(list)
    for key,a in item_profiles.items():
        contract,endpoint,work,case,context,cycle,arm = key
        if endpoint=='grok':
            other = (contract,'sol',work,case,context,cycle,arm)
            groups[('cross_endpoint',contract,arm,context,cycle,'grok','sol')].append((a,item_profiles[other]))
        for other_cycle in range(cycle+1,3):
            other = (contract,endpoint,work,case,context,other_cycle,arm)
            if other in item_profiles: groups[('repeat_cycle',contract,endpoint,arm,context,cycle,other_cycle)].append((a,item_profiles[other]))
        if contract=='unscored_dependency_diagnostic':
            for left_context,right_context in combinations(('raw_full','anchored_map','summary_only'),2):
                if context!=left_context: continue
                other = (contract,endpoint,work,case,right_context,cycle,arm)
                groups[('representation_access',contract,endpoint,arm,left_context,right_context)].append((a,item_profiles[other]))
    return [{'comparison':list(key),**contrast(pairs,key[1])} for key,pairs in sorted(groups.items(),key=lambda x:str(x[0]))]


def three_cycles(item_profiles):
    groups = defaultdict(list)
    for key in item_profiles:
        if key[5]!=2: continue
        unit = key[:5]+key[6:]; profiles3 = [item_profiles[key[:5]+(cycle,)+key[6:]] for cycle in range(3)]
        groups[(key[0],key[1],key[4],key[6])].append(profiles3)
    return [{'contract':key[0],'endpoint':key[1],'context_arm':key[2],'arm':key[3],'planned_three_cycle_units':len(items),
        'complete_native_rating_triples':sum(all(p['value'] is not None for p in ps) for ps in items),
        'complete_native_leaf_triples':sum(all(len(p['leaf_states'])==p.get('native_coverage',{}).get('planned_leaves',0)>0 for p in ps) for ps in items)}
        for key,items in sorted(groups.items())]


def inventory_summary(inventory):
    groups = defaultdict(list)
    for item in inventory:
        r = item['request']; groups[(r['contract'],r['endpoint'],r['arm'],r['context_arm'],r['repeat'])].append(item)
    output = []
    for key,items in sorted(groups.items()):
        metrics = {}
        for field in (*TOKEN_FIELDS,'latency_seconds'):
            values = [i['native_metrics'].get(field) for i in items if i['native_metrics'].get(field) is not None]
            metrics[field] = {'reported_requests':len(values),'unavailable_requests':len(items)-len(values),
                'sum_native_reported':sum(values) if values else None,'mean_native_reported':d.mean(values)}
        output.append({'contract':key[0],'endpoint':key[1],'arm':key[2],'context_arm':key[3],'cycle':key[4],
            'planned_requests':len(items),'states':dict(Counter(i['state'] for i in items)),'native_metrics':metrics})
    return output


def analyze(manifest,records,inventory,hbq,root):
    c.require(len(inventory)==464 and Counter(i['request']['request_sha256'] for i in inventory)==Counter(r['request_sha256'] for r in manifest['requests']),'All planned denominators required')
    ids = [r['request']['request_sha256'] for r in records]; expected = {r['request_sha256']:r for r in manifest['requests']}
    c.require(len(ids)==len(set(ids)) and set(ids)=={i['request']['request_sha256'] for i in inventory if i['state']=='accepted'}
        and all(r['request']==expected[r['request']['request_sha256']] for r in records),'Only unique replay-admitted requests may vote')
    items = profiles(manifest,records,hbq,root); public = []
    scalar_groups = defaultdict(list)
    for key,profile in sorted(items.items()):
        contract,endpoint,work,case,context,cycle,arm = key
        public.append({'contract':contract,'endpoint':endpoint,'work_id':work,'case_id':case or None,'context_arm':context,'cycle':cycle,'arm':arm,
            **{k:v for k,v in profile.items() if k!='leaf_states'}})
        if profile['native_scale'] is not None: scalar_groups[(contract,endpoint,arm,'primary')].append((profile['value'],profile['native_scale'],profile['near_threshold_increment']))
        for dim,value in profile['dimensions'].items(): scalar_groups[(contract,endpoint,arm,dim)].append((value['value'],value['scale'],1))
    distributions = [{'contract':key[0],'endpoint':key[1],'arm':key[2],'dimension':key[3],
        **d.distribution([v for v,_,_ in values],values[0][1],values[0][2],len(values))} for key,values in sorted(scalar_groups.items())]
    return {'schema_version':1,'analysis_policy':POLICY,'study_id':manifest['study_id'],'candidate':None,'oracle_accepted':False,
        'human_labels_supplied':0,'human_alignment_claim':False,'interpretation_oracle_claim':False,'population_generalization':False,
        'bootstrap_eligible':False,'planned':manifest['counts'],'admitted_requests':len(records),'states':dict(Counter(i['state'] for i in inventory)),
        'request_inventory':inventory_summary(inventory),'profiles':public,'native_distributions':distributions,
        'matched_comparisons':comparisons(items),'three_cycle_inventory':three_cycles(items),
        'analysis_time_schema_sha256':hbq['analysis_time_schema_sha256'],
        'limitations':['Two pre-existing human-authored novellas; model familiarity and prior case knowledge remain possible.',
            'AI summary/map representations and factual review are proposed aids, not interpretation or aesthetic oracles.',
            'Diagnostic native leaves and scoped1–7 ratings are not whole-work scalar scores; CA and N/A remain distinct.',
            'Only complete unique admitted219-leaf raw-full banks use canonical scoring_v2 and historical cumulative enforcement.',
            'HBQ bounds are rubric-sensitivity bounds, not statistical confidence intervals. Scalar completeness excludes supplemental questions.',
            'Holistic1–7, compact1–5 and HBQ0–100 remain separate; no cross-scale subtraction or human-alignment inference.',
            'Agreement/kappa and two-work contrasts are descriptive; no population bootstrap or generalization.',
            'Own native prompt binding attests submitted bytes, not that the model read the whole body or avoided truncation.',
            'Tokens require replayed own completed-turn usage; native latency, billing/cache claims and physical contact cardinality remain unavailable.',
            'Verdict/report schemas are recorded at analysis time; these two schema hashes were not explicit prospective preparation artifacts.']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('manifest','tools-root','grok-results','sol-results'): parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--manifest-sha256',required=True); args = parser.parse_args()
    c.require(args.manifest_sha256==MANIFEST_SHA and c.digest(UTILITY_PATH.read_bytes())==UTILITY_SHA,'Named analysis input/utility pin differs')
    manifest,root,subset,validator,receipts = c.load_manifest(args.manifest,args.manifest_sha256,COLLECTOR_SHA,args.tools_root.resolve())
    hbq = load_hbq(manifest,root)
    records,inventory,commitments = collect_evidence(manifest,args.manifest_sha256,root,{'grok':args.grok_results.resolve(),'sol':args.sol_results.resolve()},
        args.tools_root.resolve(),subset,validator,receipts)
    report = analyze(manifest,records,inventory,hbq,root)
    report.update(manifest_sha256=args.manifest_sha256,analysis_sha256=c.digest(Path(__file__).read_bytes()),collector_sha256=COLLECTOR_SHA,
        descriptive_utility_sha256=UTILITY_SHA,replayed_terminal_commitment_sha256=c.digest(c.canonical(sorted(commitments,key=lambda r:(r['endpoint'],r['logical_sample_id'])))))
    print(json.dumps(report,sort_keys=True,allow_nan=False)); return 0


if __name__ == '__main__': raise SystemExit(main())
