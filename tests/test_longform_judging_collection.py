"""Mock transport witnesses prove orchestration/source admission, not native reading."""
from copy import deepcopy
from datetime import timedelta
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import uuid

import pytest

ROOT = Path(__file__).resolve().parents[1]
def load(name,path):
    spec = importlib.util.spec_from_file_location(name,path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module); return module

c = load('test_p4_judging_collector',ROOT/'evaluation-results/hbq-longform-dependency-pilot-v1/collector.py')
fixtures = load('p4_judging_preparation_fixtures',ROOT/'tests/test_longform_dependency_preparation.py')


@pytest.fixture(scope='module')
def frozen(tmp_path_factory):
    root = tmp_path_factory.mktemp('p4-frozen')
    sources = fixtures.sources.__wrapped__(); summary_plan = fixtures.summary_plan.__wrapped__(sources)
    wrapper,receipts,_,_ = fixtures.saved_summaries.__wrapped__(root,summary_plan,sources)
    summaries,lineage = c.p.read_summaries(wrapper,*summary_plan,sources[-1],receipts)
    works,cases,files,runtime,runtime_files,subset = sources
    manifest,raw = c.p.judging_plan(works,cases,files,runtime,runtime_files,subset,summaries,lineage)
    freeze = root/'judging-frozen'
    for name,data in raw.items(): c.write_bytes(freeze/name,data)
    sha = c.digest(raw['manifest.json']); code_sha = c.digest(Path(c.__file__).read_bytes())
    tools = Path(runtime['external_pins']['tools_root_local_only'])
    return {'root':freeze,'manifest':manifest,'files':raw,'sha':sha,'code_sha':code_sha,'tools':tools,'sources':sources,
            'subset':subset,'validator':c.p.load('p4_test_admission',freeze/'implementation/validate_response.py')}


class Receipts:
    reject = False
    def verify(self,sample,provider,**kwargs):
        if self.reject: raise ValueError('Synthetic receipt failure')
        assert kwargs['model'] == 'gpt-6.1-sol' and kwargs['reasoning'] == 'high'
        assert provider['receipt_policy'] == 'codex_native_rollout_v1'
        for item in provider['provider_artifacts'].values(): c.pinned(sample,item['path'],item)
    def event_identity(self,events,final): return json.loads(events)['thread_id'],[]


def response(row,quote=None):
    return {'verdicts':[{'question_id':q,'verdict':'CANNOT_ASSESS' if quote is None else 'YES','confidence':1,
        'note':'Mechanical witness only.','evidence':[{'kind':'summary','reference':'declared representation access',
            'exact_quote':None,'summary':'Available evidence leaves this criterion unresolved.'}] if quote is None else [{'kind':'exact_quote','reference':'declared available source',
            'exact_quote':quote,'summary':None}]} for q in row['question_ids']]}


@pytest.fixture
def job(tmp_path,frozen):
    output = tmp_path/'results'; output.mkdir()
    binding = c.job_binding(frozen['manifest'],frozen['root'],frozen['sha'],'sol',frozen['tools'],collector_sha=frozen['code_sha'])
    c.record(output/'job.json',binding); c.record(output/'account-binding.json',c.t.account_receipt(binding))
    c.write_bytes(output/'frozen-manifest.json',frozen['files']['manifest.json'])
    state = {'contacts':0,'quote':None,'failure':False,'duplicate':False,'stop_after':False,'malformed':False}
    receipts = Receipts()
    def call(**kwargs):
        assert kwargs['timeout'] == 900 and kwargs['attempt_number'] == 1 and kwargs['reasoning'] == 'high'
        assert kwargs['codex_receipt_policy'] == 'codex_native_rollout_v1'
        kwargs['before_provider_attempt'](); state['contacts'] += 1
        sample = kwargs['output_dir']; row = json.loads((sample/'condition.json').read_bytes())
        if state['failure']:
            (sample/'failure.txt').write_bytes(b'synthetic transport failure'); raise TimeoutError('Mock timeout')
        answer = response(row,state['quote']); final = b'completed but not JSON' if state['malformed'] else c.canonical(answer)
        events = c.canonical({'thread_id':str(uuid.uuid5(uuid.NAMESPACE_URL,'duplicate' if state['duplicate'] else row['logical_sample_id']))})
        artifacts = {}
        for name,path,raw in [('codex_message','native-final.json',final),('codex_events','events.json',events)]:
            c.write_bytes(sample/path,raw); artifacts[name] = c.p.metadata(path,raw)
        if state['stop_after']: (output/'STOP').write_bytes(b'stop after current call')
        return final.decode(),{'receipt_policy':'codex_native_rollout_v1','provider_artifacts':artifacts}
    rows = [r for r in frozen['manifest']['requests'] if r['endpoint'] == 'sol' and r['arm'] == 'hbq']
    return {**frozen,'output':output,'binding':binding,'state':state,'receipts':receipts,'call':call,'rows':rows,
            'helper':SimpleNamespace(CLI=Path('never-executed-synthetic.exe'))}


def collect(job,row):
    return c.collect_one(row,job['manifest'],job['binding'],job['root'],job['output'],job['subset'],job['validator'],
        job['receipts'],job['helper'],job['call'])


def replay(job,row):
    return c.replay(c.sample_path(job['output'],row),row,job['manifest'],job['binding'],job['root'],job['receipts'],job['subset'],job['validator'])


def test_complete_contracts_banks_and_readonly_cli(frozen,tmp_path,monkeypatch,capsys):
    before = deepcopy(frozen['manifest'])
    manifest,_,_,_,_ = c.load_manifest(frozen['root']/'manifest.json',frozen['sha'],frozen['code_sha'],frozen['tools'])
    assert manifest == before and manifest['counts']['diagnostic_requests'] == 216 and manifest['counts']['whole_work_requests'] == 248
    output = tmp_path/'fresh'
    original = c.p.load
    def readonly(name,path):
        assert Path(path).name != 'secondary-helper.py'; return original(name,path)
    monkeypatch.setattr(c.p,'load',readonly)
    monkeypatch.setattr('sys.argv',['collector.py','--manifest',str(frozen['root']/'manifest.json'),'--manifest-sha256',frozen['sha'],
        '--collector-sha256',frozen['code_sha'],'--results-dir',str(output),'--tools-root',str(frozen['tools']),'--endpoint','sol','--validate-only'])
    assert c.main() == 0
    report = json.loads(capsys.readouterr().out)
    assert report['planned'] == report['untouched'] == 232 and report['provider_calls'] == 0 and not output.exists()
    assert not report['diagnostic_scalar_eligible'] and not report['model_read_whole_body_proven']


@pytest.mark.parametrize('kind',['duplicate_leaf','missing_bank','diagnostic_scalar','duplicate_logical','changed_context'])
def test_geometry_and_exact_context_failure(frozen,kind):
    manifest = deepcopy(frozen['manifest'])
    row = next(r for r in manifest['requests'] if r['endpoint'] == 'sol' and r['full_bank_score_eligible'])
    if kind == 'duplicate_leaf': row['question_ids'][1] = row['question_ids'][0]
    if kind == 'missing_bank': manifest['requests'].remove(row)
    if kind == 'diagnostic_scalar': next(r for r in manifest['requests'] if r['contract']=='unscored_dependency_diagnostic')['full_bank_score_eligible'] = True
    if kind == 'duplicate_logical':
        rows = [r for r in manifest['requests'] if r['endpoint']=='sol']; rows[1]['logical_sample_id'] = rows[0]['logical_sample_id']
    if kind == 'changed_context': row['task_context']['sha256'] = '0'*64
    with pytest.raises(ValueError): c.validate_geometry(manifest,frozen['root'])


def test_semantic_rejection_keeps_missing_and_next_untouched_collects(job):
    first,second = job['rows'][:2]; job['state']['quote'] = 'Unavailable invented source quote.'
    assert collect(job,first) == 'semantic_rejected' and replay(job,first)[1] is None
    job['state']['quote'] = None
    assert collect(job,second) == 'accepted' and job['state']['contacts'] == 2
    terminal,answer = replay(job,second)
    assert terminal['no_resend'] and answer and not terminal['diagnostic_scalar_eligible']
    with pytest.raises(FileExistsError): collect(job,first)
    assert job['state']['contacts'] == 2


def test_receipt_verified_malformed_final_is_semantic_missingness(job):
    row = job['rows'][0]; job['state']['malformed'] = True
    assert collect(job,row) == 'semantic_rejected' and replay(job,row)[1] is None
    sample = c.sample_path(job['output'],row)
    assert (sample/'native-final.json').read_bytes() == b'completed but not JSON'
    assert json.loads((sample/'native-final-parse.json').read_bytes()) == {'json_parseable':False}
    job['state']['malformed'] = False
    assert collect(job,job['rows'][1]) == 'accepted' and job['state']['contacts'] == 2


@pytest.mark.parametrize('kind',['native','receipt','duplicate'])
def test_incomplete_failures_stop_no_resend(job,kind):
    first,second = job['rows'][:2]
    if kind == 'native': job['state']['failure'] = True
    if kind == 'receipt': job['receipts'].reject = True
    if kind == 'duplicate': job['state']['duplicate'] = True; assert collect(job,first) == 'accepted'; first = second
    assert collect(job,first) == 'unadmitted_no_resend' and replay(job,first)[1] is None
    with pytest.raises(FileExistsError): collect(job,first)
    assert len(list(job['output'].glob('*/terminal.json'))) == (2 if kind == 'duplicate' else 1)


def test_summary_only_no_unavailable_original_or_rubric_context(job):
    row = next(r for r in job['rows'] if r['context_arm']=='summary_only')
    source = job['sources'][0][row['work_id']]['index']['anchors'][0]['quote']
    job['state']['quote'] = source
    assert collect(job,row) == 'semantic_rejected' and replay(job,row)[1] is None
    other = next(r for r in job['rows'] if r['context_arm']=='summary_only' and r['logical_sample_id']!=row['logical_sample_id'])
    job['state']['quote'] = '"audience": []'
    assert collect(job,other) == 'accepted'
    third = next(r for r in job['rows'] if r['context_arm']=='summary_only' and r['logical_sample_id'] not in {row['logical_sample_id'],other['logical_sample_id']})
    job['state']['quote'] = third['question_ids'][0]
    assert collect(job,third) == 'semantic_rejected'


@pytest.mark.parametrize('kind',['final','context','source','account','condition'])
def test_own_artifacts_and_account_tamper_fail(job,kind):
    row = job['rows'][0]; assert collect(job,row) == 'accepted'
    sample = c.sample_path(job['output'],row)
    paths = {'final':sample/'native-final.json','context':sample/'task-context.json','source':sample/'available-source.txt',
             'account':job['output']/'account-binding.json','condition':sample/'condition.json'}
    paths[kind].write_bytes(paths[kind].read_bytes()+b'changed')
    with pytest.raises(ValueError): replay(job,row)


def test_stop_before_contact_and_current_settles(job):
    row = job['rows'][0]; (job['output']/'STOP').write_bytes(b'stop')
    assert collect(job,row) == 'unadmitted_no_resend' and job['state']['contacts']==0
    (job['output']/'STOP').unlink(); job['state']['stop_after'] = True
    assert collect(job,job['rows'][1]) == 'accepted' and (job['output']/'stop-observed.json').exists()


def test_grok_expiry_and_campaign_boundaries_and_job_pins(frozen):
    route = {'name':'grok-build-grok-4.7','model':'grok-4.7','reasoning_effort':'high','timeout_seconds':900,
        'allowed_payload_classes':['public_synthetic'],'reported_model':'grok-4.7','cost_evidence':{'expires_at':c.CUTOFF.isoformat()}}
    boundary = c.CUTOFF-timedelta(seconds=900)
    assert c.grok_contact_allowed(route,boundary-timedelta(microseconds=1))
    assert not c.grok_contact_allowed(route,boundary)
    expiry = boundary-timedelta(days=10); route['cost_evidence']['expires_at'] = expiry.isoformat()
    assert not c.grok_contact_allowed(route,expiry-timedelta(seconds=899))
    binding = c.job_binding(frozen['manifest'],frozen['root'],frozen['sha'],'grok',frozen['tools'],route)
    assert binding['deadline_margin_seconds']==900 and binding['runtime']=={'model':'grok-4.7','reasoning':'high'}
    assert binding['retained_native_transport_sha256']==c.TRANSPORT_SHA
    route['timeout_seconds']=300
    with pytest.raises(ValueError): c.job_binding(frozen['manifest'],frozen['root'],frozen['sha'],'grok',frozen['tools'],route)


def test_wrong_exact_manifest_collector_and_output_fail(frozen):
    with pytest.raises(ValueError,match='pin differs'): c.load_manifest(frozen['root']/'manifest.json','0'*64,frozen['code_sha'],frozen['tools'])
    with pytest.raises(ValueError,match='pin differs'): c.load_manifest(frozen['root']/'manifest.json',frozen['sha'],'0'*64,frozen['tools'])
    with pytest.raises(ValueError): c.p.generation.output_preflight(c.HERE/'results',frozen['root'])
    with pytest.raises(ValueError): c.p.generation.output_preflight(frozen['root']/'results',frozen['root'])


def test_occupied_unresolved_fails_before_dispatch(job,monkeypatch):
    c.sample_path(job['output'],job['rows'][0]).mkdir()
    monkeypatch.setattr('sys.argv',['collector.py','--manifest',str(job['root']/'manifest.json'),'--manifest-sha256',job['sha'],
        '--collector-sha256',job['code_sha'],'--results-dir',str(job['output']),'--tools-root',str(job['tools']),'--endpoint','sol'])
    with pytest.raises(ValueError,match='unresolved; no resend'): c.main()
    assert job['state']['contacts']==0


def test_late_evidence_hash_failure_demotes_and_stops_before_next_contact(job,monkeypatch):
    row = job['rows'][0]; final = c.canonical(response(row)); original = c.digest
    injected = []
    def late_hash(raw):
        if raw == final and not injected:
            injected.append(True); raise OSError('Synthetic late evidence hash failure')
        return original(raw)
    monkeypatch.setattr(c,'digest',late_hash)
    assert collect(job,row) == 'unadmitted_no_resend'
    terminal,answer = replay(job,row)
    assert injected and terminal['accepted'] is False and terminal['no_resend'] and answer is None
    assert terminal['error_class']=='OSError' and job['state']['contacts']==1
    assert json.loads((c.sample_path(job['output'],row)/'acceptance.json').read_bytes())['accepted'] is True
    with pytest.raises(FileExistsError): collect(job,row)
    monkeypatch.setattr('sys.argv',['collector.py','--manifest',str(job['root']/'manifest.json'),'--manifest-sha256',job['sha'],
        '--collector-sha256',job['code_sha'],'--results-dir',str(job['output']),'--tools-root',str(job['tools']),'--endpoint','sol'])
    with pytest.raises(ValueError,match='Incomplete occupied native attempt'): c.main()
    assert job['state']['contacts']==1
    assert not c.sample_path(job['output'],job['rows'][1]).exists()
