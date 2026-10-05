"""CRLF source proofs and same-observation admission; no provider/human proof."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
def load(name,path):
    spec = importlib.util.spec_from_file_location(name,path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module); return module
ag = load('test_p4_grounding_analysis',ROOT/'evaluation-results/hbq-longform-dependency-pilot-v1/analysis_grounding.py')
g,c = ag.g,ag.c
fixtures = load('p4_grounding_collection_fixtures',ROOT/'tests/test_longform_judging_collection.py')
analysis_fixtures = load('p4_grounding_analysis_fixtures',ROOT/'tests/test_longform_analysis.py')


@pytest.fixture(scope='module')
def frozen(tmp_path_factory):
    result = fixtures.frozen.__wrapped__(tmp_path_factory)
    return {**result,'hbq':ag.a.load_hbq(result['manifest'],result['root'])}


@pytest.fixture
def job(tmp_path,frozen): return fixtures.job.__wrapped__(tmp_path,frozen)


@pytest.mark.parametrize('quote',['α\nβ','α β'])
def test_supported_exact_inverse_char_and_utf8_spans(quote):
    text = 'start α\r\nβ finish'
    result = g.SpanSources({'available':{'text':text,'path':'narrative.txt',
        'original_coordinates':{'path':'original.txt','sha256':'x','char_start':10,'byte_start':20}}}).prove(quote)
    assert result['state']=='projected_exact_span' and result['native_quote']==quote
    assert result['exact_source_quote']=='α\r\nβ'
    location = result['locations'][0]
    assert location['source_char']==[6,10] and location['source_utf8_byte']==[6,12]
    assert location['original_source']['char']==[16,20] and location['original_source']['utf8_byte']==[26,32]
    assert result['native_quote_sha256']==g.digest(quote.encode())
    assert location['span_sha256']==g.digest('α\r\nβ'.encode())


def test_repeated_identical_spans_keep_all_locations_and_distinct_spans_fail():
    source = lambda text:g.SpanSources({'available':{'text':text,'path':'source.txt'}})
    repeated = source('a\r\nb and a\r\nb').prove('a b')
    assert repeated['state']=='projected_exact_span' and repeated['ambiguous_locations'] and len(repeated['locations'])==2
    ambiguous = source('a\r\nb c and a b\r\nc').prove('a b c')
    assert ambiguous['state']=='ambiguous_distinct_spans' and ambiguous['exact_source_quote'] is None
    assert len(ambiguous['candidate_span_sha256s'])==2
    exact = source('a b c and a\r\nb c').prove('a b c')
    assert exact['state']=='exact_inherited' and exact['exact_source_quote']=='a b c'


@pytest.mark.parametrize('text,quote',[
    ('a\nb','a b'),('a\rb','a b'),('a\t b','a b'),('a\r\n  b','a b'),
    ('Alpha\r\nBeta','alpha beta'),('a—\r\nb','a- b'),('é\r\nb','e\u0301 b'),('a\r\nb','a…b'),('a\r\nb','   ')])
def test_no_general_whitespace_or_lexical_repair(text,quote):
    result = g.SpanSources({'available':{'text':text,'path':'source.txt'}}).prove(quote)
    assert result['exact_source_quote'] is None


def normalized_quote(job,row):
    text = c.inputs(job['root'],job['manifest'],row)[2][row['work_id']]
    at = text.index('\r\n',100)
    start,end = max(0,at-25),min(len(text),at+30)
    return text[start:end].replace('\r\n',' ')


def evidence(job):
    return ag.collect_descendants(job['manifest'],job['sha'],job['root'],
        {'sol':job['output'],'grok':job['output'].parent/'absent-grok'},job['tools'],job['subset'],job['validator'],job['receipts'])


def test_native_replay_then_quote_only_descendant_same_vote_strict_history(job):
    row = next(r for r in job['rows'] if r['context_arm']=='raw_full')
    job['state']['quote']=normalized_quote(job,row)
    assert fixtures.collect(job,row)=='semantic_rejected'
    sample = c.sample_path(job['output'],row)
    before = {path.name:path.read_bytes() for path in sample.iterdir() if path.is_file()}
    records,inventory,ledger = evidence(job)
    assert len(records)==1 and len(inventory)==464
    assert sum(i['state']=='accepted' for i in inventory)==1
    item = next(i for i in inventory if i['request']==row)
    assert item['strict_state']=='semantic_rejected' and item['grounding_state']=='projected_accepted'
    original = json.loads(before['response.json']); descendant = records[0]['response']
    for old,new in zip(original['verdicts'],descendant['verdicts']):
        assert {k:v for k,v in old.items() if k!='evidence'}=={k:v for k,v in new.items() if k!='evidence'}
        assert old['evidence'][0]['exact_quote']!=new['evidence'][0]['exact_quote']
    certificate = ledger[0]['certificate']
    assert certificate['original_admission']['accepted'] is False and certificate['descendant_admission']['accepted']
    assert all(q['locations'][0]['original_source'] for q in certificate['quotes'])
    assert {path.name:path.read_bytes() for path in sample.iterdir() if path.is_file()}==before
    assert job['state']['contacts']==1


def test_changed_native_receipt_no_projection_and_incomplete_no_vote(job):
    row = next(r for r in job['rows'] if r['context_arm']=='raw_full')
    job['state']['quote']=normalized_quote(job,row); fixtures.collect(job,row)
    sample = c.sample_path(job['output'],row); (sample/'events.json').write_bytes(b'changed raw receipt')
    records,inventory,ledger = evidence(job)
    assert not records and not ledger
    assert next(i for i in inventory if i['request']==row)['state']=='replay_unadmitted'
    other = next(r for r in job['rows'] if r['logical_sample_id']!=row['logical_sample_id'])
    c.sample_path(job['output'],other).mkdir()
    assert next(i for i in evidence(job)[1] if i['request']==other)['state']=='started_unresolved'


def test_available_representation_bounds_and_context_only_for_hbq(job):
    row = next(r for r in job['rows'] if r['context_arm']=='summary_only')
    raw_row = next(r for r in job['rows'] if r['context_arm']=='raw_full' and r['work_id']==row['work_id'])
    job['state']['quote']=normalized_quote(job,raw_row); fixtures.collect(job,row)
    records,inventory,ledger=evidence(job)
    assert not records and ledger[0]['grounding_state']=='descendant_rejected'
    sources,context,schema = ag.available_sources(job['root'],job['manifest'],row)
    assert 'original_coordinates' not in sources['available']
    source = {'available':{'text':'available','path':'source'},'task_context':{'text':'a\r\nb','path':'context'}}
    answer = fixtures.response(row,'a b')
    result = g.derive(answer,row,source,'a\r\nb',schema,job['subset'],job['validator'])
    assert result['state']=='projected_accepted'
    assert result['quotes'][0]['locations'][0]['source_id']=='task_context'
    holistic = next(r for r in job['manifest']['requests'] if r['arm']=='holistic')
    _,_,hol_schema = ag.available_sources(job['root'],job['manifest'],holistic)
    response={'status':'SCORED','abstention_reason':None,'result':{'score':4,'rationale':'Reason',
        'strengths':['One','Two'],'limitations':[], 'evidence':[{'quote':'a b','explanation':'Reason'}]*2}}
    properties=hol_schema['properties']['result']['properties']
    response['result']['method']=properties['method']['enum'][0]
    assert job['subset'].matches_schema(response,hol_schema)
    result=g.derive(response,holistic,source,'a\r\nb',hol_schema,job['subset'],job['validator'])
    assert result['response'] is None and result['state']=='descendant_rejected'
    source['available']['text']='a\r\nb'
    result=g.derive(response,holistic,source,'unavailable context',hol_schema,job['subset'],job['validator'])
    assert result['state']=='projected_accepted' and result['response']['result']['score']==4


def test_original_semantic_failure_and_recovered_schema_limit_stay_rejected(job):
    row=job['rows'][0]; _,_,schema=ag.available_sources(job['root'],job['manifest'],row)
    source={'available':{'text':'a\r\nb','path':'source'}}
    answer=fixtures.response(row,'a b')
    answer['verdicts'][0].update(verdict='CANNOT_ASSESS',note=' ')
    result=g.derive(answer,row,source,'',schema,job['subset'],job['validator'])
    assert result['state']=='descendant_rejected' and result['response'] is None
    quote='a '*249+'bb'; source['available']['text']='a\r\n'*249+'bb'
    answer=fixtures.response(row,quote)
    assert len(quote)==500 and job['subset'].matches_schema(answer,schema)
    result=g.derive(answer,row,source,'',schema,job['subset'],job['validator'])
    assert result['changed_quote_fields']==len(row['question_ids']) and result['state']=='descendant_rejected'
    assert result['descendant_admission']['errors']==['Response violates frozen schema']


def test_inherited_and_projected_are_one_observation_each_fullbank_only(job,frozen):
    first,second = [r for r in job['rows'] if r['context_arm']=='raw_full'][:2]
    job['state']['quote']=None; fixtures.collect(job,first)
    job['state']['quote']=normalized_quote(job,second); fixtures.collect(job,second)
    records,inventory,ledger=evidence(job)
    report=ag.describe(job['manifest'],records,inventory,frozen['hbq'],job['root'])
    assert report['admitted_requests']==report['logical_observations']==2
    assert report['strict_accepted_inherited']==report['projected_accepted']==1
    assert report['provider_calls']==report['new_votes']==0 and report['candidate'] is None
    assert all(p['value'] is None for p in report['profiles'] if p['arm']=='hbq')
    rows,bank=analysis_fixtures.bank(frozen)
    result=ag.a.score_bank(rows,bank,frozen['hbq'],frozen['root'],frozen['manifest'])
    assert result['value']==100 and result['native_coverage']['planned_leaves']==219
    assert ag.a.score_bank(rows,bank[:-1],frozen['hbq'],frozen['root'],frozen['manifest'])['value'] is None


def test_exact_controller_commitment_and_fresh_output(tmp_path):
    decision=tmp_path/'decision.json'; decision.write_bytes(b'{}')
    with pytest.raises(ValueError): ag.decision_input(decision)
    retained=tmp_path/'retained'; retained.mkdir()
    with pytest.raises(ValueError): c.p.base.output_preflight(retained)
    with pytest.raises(ValueError): c.p.base.output_preflight(retained/'new',(retained,))
    fresh=tmp_path/'fresh'; c.p.base.output_preflight(fresh,(retained,))
    assert not fresh.exists()
