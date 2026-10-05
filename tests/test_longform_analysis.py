"""Bounded descriptions and replay boundaries; no provider or literary proof."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
def load(name,path):
    spec = importlib.util.spec_from_file_location(name,path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module); return module

a = load('test_longform_analysis',ROOT/'evaluation-results/hbq-longform-dependency-pilot-v1/analysis.py')
fixtures = load('p4_analysis_collection_fixtures',ROOT/'tests/test_longform_judging_collection.py')


@pytest.fixture(scope='module')
def frozen(tmp_path_factory):
    result = fixtures.frozen.__wrapped__(tmp_path_factory)
    return {**result,'hbq':a.load_hbq(result['manifest'],result['root'])}


def bank(frozen,work='pg43',cycle=0,endpoint='sol',penalties_ca=False,gate='YES'):
    rows = sorted([r for r in frozen['manifest']['requests'] if r['contract']=='whole_work_baseline' and r['arm']=='hbq'
        and r['work_id']==work and r['repeat']==cycle and r['endpoint']==endpoint],key=lambda r:r['batch'])
    compiled = json.loads(frozen['files']['compiled/prose.novella.json'])
    penalties = {q['question']['id'] for g in compiled['penalty_groups'] for q in g['questions']}
    gates = {q['question']['id'] for q in compiled['hard_gates']}
    records = []
    for row in rows:
        leaves = [{'question_id':qid,'verdict':gate if qid in gates else 'CANNOT_ASSESS' if penalties_ca and qid in penalties else 'YES',
            'confidence':1,'note':'Mechanical exact-context witness.',
            'evidence':[{'kind':'exact_quote','reference':'declared task context','exact_quote':'"audience": []','summary':None}]} for qid in row['question_ids']]
        records.append({'request':row,'response':{'verdicts':leaves}})
    return rows,records


def inventory(manifest,records=()):
    accepted = {r['request']['request_sha256'] for r in records}
    return [{'request':r,'state':'accepted' if r['request_sha256'] in accepted else 'untouched','native_metrics':{}}
        for r in manifest['requests']]


def test_complete_actual_canonical_bank_role_counts_and_penalty_uncertainty(frozen):
    rows,records = bank(frozen); before = deepcopy(records)
    result = a.score_bank(rows,records,frozen['hbq'],frozen['root'],frozen['manifest'])
    assert result['value']==100 and result['state']=='SCORED' and result['fully_assessed_point_score']
    assert result['sensitivity_bounds']=={'lower':100,'upper':100} and result['weighted_coverage']==1
    assert {k:v['planned_leaves'] for k,v in result['roles'].items()}=={'domain':175,'hard_gate':1,'penalty':18,'supplemental':25}
    assert records==before
    rows,records = bank(frozen,penalties_ca=True)
    result = a.score_bank(rows,records,frozen['hbq'],frozen['root'],frozen['manifest'])
    assert result['value']==100 and result['weighted_coverage']==1 and not result['fully_assessed_point_score']
    assert result['sensitivity_bounds']=={'lower':79,'upper':100} and result['uncertainty_width']==21
    assert all(p['coverage']==0 for p in result['penalties'])


@pytest.mark.parametrize('kind',['missing_packet','duplicate_packet','missing_leaf','duplicate_leaf','unsupported_scope'])
def test_incomplete_or_unsupported_bank_never_calls_scalar_scorer(frozen,monkeypatch,kind):
    rows,records = bank(frozen); rows,records = deepcopy((rows,records))
    if kind=='missing_packet': records.pop()
    if kind=='duplicate_packet': records[-1]=deepcopy(records[0])
    if kind=='missing_leaf': records[0]['response']['verdicts'].pop()
    if kind=='duplicate_leaf': records[0]['response']['verdicts'][-1]=deepcopy(records[0]['response']['verdicts'][0])
    if kind=='unsupported_scope': rows[0]['full_bank_score_eligible']=False
    monkeypatch.setattr(frozen['hbq']['scorer'],'score_bundle',lambda *args,**kwargs:pytest.fail('Incomplete/unsupported bank reached scoring'))
    result = a.score_bank(rows,records,frozen['hbq'],frozen['root'],frozen['manifest'])
    assert result['value'] is None and result['weighted_coverage'] is None and result['sensitivity_bounds'] is None


@pytest.mark.parametrize('gate',['NO','CANNOT_ASSESS'])
def test_gate_ineligibility_or_uncertainty_is_not_scalar(frozen,gate):
    rows,records = bank(frozen,gate=gate)
    result = a.score_bank(rows,records,frozen['hbq'],frozen['root'],frozen['manifest'])
    assert result['value'] is None and not result['fully_assessed_point_score']
    assert result['hard_gate_status']==('INVALID' if gate=='NO' else 'UNRESOLVED')


def test_unavailable_grounding_never_scores(frozen):
    rows,records = bank(frozen); records = deepcopy(records)
    records[0]['response']['verdicts'][0]['evidence'][0]['exact_quote']='Invented unavailable quote.'
    result = a.score_bank(rows,records,frozen['hbq'],frozen['root'],frozen['manifest'])
    assert result['state']=='strict_import_unadmitted_no_scalar' and result['value'] is None


def test_zero_results_all464_and_exact_native_scales(frozen,tmp_path):
    records,items,_ = a.collect_evidence(frozen['manifest'],frozen['sha'],frozen['root'],{'sol':tmp_path/'absent-sol','grok':tmp_path/'absent-grok'},
        frozen['tools'],frozen['subset'],frozen['validator'],fixtures.Receipts())
    report = a.analyze(frozen['manifest'],records,items,frozen['hbq'],frozen['root'])
    assert report['states']=={'untouched':464} and report['admitted_requests']==0
    assert sum(r['planned_requests'] for r in report['request_inventory'])==464
    assert sum(r['planned_requests'] for r in report['request_inventory'] if r['contract']=='unscored_dependency_diagnostic')==216
    assert all(p['value'] is None for p in report['profiles']) and report['candidate'] is None
    assert not report['oracle_accepted'] and not report['human_alignment_claim'] and not report['bootstrap_eligible']
    assert {tuple(p['native_scale']) for p in report['profiles'] if p['arm']=='compact'}=={(1,5)}
    assert {tuple(p['native_scale']) for p in report['profiles'] if p['arm']=='holistic'}=={(1,7)}
    assert all(m['sum_native_reported'] is None for item in report['request_inventory'] for m in item['native_metrics'].values())
    assert not (tmp_path/'absent-sol').exists() and not (tmp_path/'absent-grok').exists()


def test_diagnostic_three_leaves_keep_ca_na_and_representation_changes(frozen):
    rows = [r for r in frozen['manifest']['requests'] if r['contract']=='unscored_dependency_diagnostic' and r['endpoint']=='sol'
        and r['arm']=='hbq' and r['case_id']=='j_event_revelation' and r['repeat']==0]
    records = []
    for row in rows:
        answer = fixtures.response(row)
        states = ['YES','CANNOT_ASSESS','NOT_APPLICABLE'] if row['context_arm']=='raw_full' else ['NO','YES','NOT_APPLICABLE']
        for v,state in zip(answer['verdicts'],states): v['verdict']=state
        records.append({'request':row,'response':answer})
    profiles = a.profiles(frozen['manifest'],records,frozen['hbq'],frozen['root'])
    raw = profiles[a.identity(next(r for r in rows if r['context_arm']=='raw_full'))]
    assert raw['value'] is None and raw['whole_work_quality_scalar'] is None
    assert raw['native_coverage']['native_states']=={'YES':1,'CANNOT_ASSESS':1,'NOT_APPLICABLE':1}
    assert raw['native_coverage']['assessed_over_observed_applicable']==.5
    item = next(x for x in a.comparisons(profiles) if x['comparison']==['representation_access','unscored_dependency_diagnostic','sol','hbq','raw_full','anchored_map'])
    assert item['native_leaf_agreement']['planned_paired_units']==54 and item['native_leaf_agreement']['paired_observed_units']==3
    assert item['native_rating_difference']['observed_pairs']==0
    assert {'left':'CANNOT_ASSESS','right':'YES','count':1} in item['native_state_transitions']


def test_three_cycle_whole_bank_sentinel_and_two_endpoint_pairs(frozen):
    records = []
    for endpoint in ('sol','grok'):
        for cycle in range(3): records.extend(bank(frozen,endpoint=endpoint,cycle=cycle)[1])
    report = a.analyze(frozen['manifest'],records,inventory(frozen['manifest'],records),frozen['hbq'],frozen['root'])
    triples = [r for r in report['three_cycle_inventory'] if r['contract']=='whole_work_baseline' and r['arm']=='hbq']
    assert len(triples)==2 and all(r['planned_three_cycle_units']==r['complete_native_rating_triples']==1 for r in triples)
    pair = next(x for x in report['matched_comparisons'] if x['comparison']==['cross_endpoint','whole_work_baseline','hbq','raw_full',0,'grok','sol'])
    assert pair['planned_paired_items']==2 and pair['native_rating_difference']['observed_pairs']==1
    assert pair['native_leaf_agreement']['planned_paired_units']==438 and pair['native_leaf_agreement']['paired_observed_units']==219
    repeat = next(x for x in report['matched_comparisons'] if x['comparison']==['repeat_cycle','whole_work_baseline','sol','hbq','raw_full',0,2])
    assert repeat['native_rating_difference']['exact_agreement']==1 and repeat['native_leaf_agreement']['raw_agreement']==1


def test_planned_denominators_and_duplicate_admitted_requests_fail(frozen):
    rows,records = bank(frozen)
    with pytest.raises(ValueError): a.analyze(frozen['manifest'],[],inventory(frozen['manifest'])[:-1],frozen['hbq'],frozen['root'])
    with pytest.raises(ValueError): a.analyze(frozen['manifest'],records+[records[0]],inventory(frozen['manifest'],records),frozen['hbq'],frozen['root'])


def test_native_comparator_ceilings_and_dimensions_remain_on_distinct_scales(frozen):
    records = []
    for arm in ('compact','holistic'):
        row = next(r for r in frozen['manifest']['requests'] if r['contract']=='whole_work_baseline' and r['endpoint']=='sol'
            and r['arm']==arm and r['work_id']=='pg43' and r['repeat']==0)
        schema = json.loads(frozen['files'][row['schema_path']])
        result = {'method':schema['properties']['result']['properties']['method']['enum'][0]}
        evidence = [{'quote':'The','explanation':'Synthetic evidence only.'}]
        if arm=='compact':
            dims = schema['properties']['result']['properties']['dimensions']['items']['properties']['dimension_id']['enum']
            result.update(overall_score=5,overall_rationale='Mechanical witness.',dimensions=[{'dimension_id':dim,'score':5,
                'rationale':'Mechanical witness.','evidence':evidence} for dim in dims])
        else: result.update(score=7,rationale='Mechanical witness.',strengths=['One','Two'],limitations=[],evidence=evidence*2)
        records.append({'request':row,'response':{'status':'SCORED','abstention_reason':None,'result':result}})
    report = a.analyze(frozen['manifest'],records,inventory(frozen['manifest'],records),frozen['hbq'],frozen['root'])
    primary = {r['arm']:r for r in report['native_distributions'] if r['endpoint']=='sol' and r['contract']=='whole_work_baseline' and r['dimension']=='primary' and r['arm']!='hbq'}
    assert primary['compact']['native_scale']==[1,5] and primary['holistic']['native_scale']==[1,7]
    assert all(r['exact_ceiling']==1 and r['reported_values']==1 and r['near_threshold_increment']==1 for r in primary.values())
    profiles = [r for r in report['profiles'] if r['work_id']=='pg43' and r['cycle']==0 and r['endpoint']=='sol' and r['arm'] in primary and r['contract']=='whole_work_baseline']
    assert {r['arm']:r['whole_work_quality_scalar'] for r in profiles}=={'compact':5,'holistic':7}
    assert len(next(r for r in profiles if r['arm']=='compact')['dimensions'])==6


def test_replay_tamper_started_and_bad_job_have_no_votes(frozen,tmp_path):
    job = fixtures.job.__wrapped__(tmp_path,frozen); row = job['rows'][0]
    assert fixtures.collect(job,row)=='accepted'
    sample = a.c.sample_path(job['output'],row)
    (sample/'available-source.txt').write_bytes(b'changed')
    records,items,_ = a.collect_evidence(frozen['manifest'],frozen['sha'],frozen['root'],{'sol':job['output'],'grok':tmp_path/'absent'},
        frozen['tools'],frozen['subset'],frozen['validator'],job['receipts'])
    assert not records and CounterStates(items).get('replay_unadmitted')==1
    a.c.sample_path(job['output'],job['rows'][1]).mkdir()
    records,items,_ = a.collect_evidence(frozen['manifest'],frozen['sha'],frozen['root'],{'sol':job['output'],'grok':tmp_path/'absent'},
        frozen['tools'],frozen['subset'],frozen['validator'],job['receipts'])
    assert not records and CounterStates(items).get('started_unresolved')==1
    (job['output']/'job.json').write_bytes(b'{}')
    records,items,_ = a.collect_evidence(frozen['manifest'],frozen['sha'],frozen['root'],{'sol':job['output'],'grok':tmp_path/'absent'},
        frozen['tools'],frozen['subset'],frozen['validator'],job['receipts'])
    assert not records and CounterStates(items).get('job_unadmitted')==232


def CounterStates(items):
    from collections import Counter
    return Counter(i['state'] for i in items)


def test_native_usage_zero_distinct_unavailable_no_provider_latency(tmp_path):
    events = b'{"type":"turn.completed","usage":{"input_tokens":0,"output_tokens":9}}\n'
    (tmp_path/'events.jsonl').write_bytes(events)
    (tmp_path/'native-result.json').write_bytes(a.c.canonical({'provider_artifacts':{'codex_events':a.c.p.metadata('events.jsonl',events)}}))
    # This isolated arithmetic witness assumes prior receipt replay, as collect_evidence requires.
    sol = a.d.native_metrics(tmp_path,{'endpoint':'sol'},{'state':'accepted'})
    grok = a.d.native_metrics(tmp_path,{'endpoint':'grok'},{'state':'accepted'})
    assert sol['input_tokens']==0 and sol['output_tokens']==9 and sol['cached_input_tokens'] is None and sol['latency_seconds'] is None
    assert grok['input_tokens'] is None and grok['output_tokens'] is None
