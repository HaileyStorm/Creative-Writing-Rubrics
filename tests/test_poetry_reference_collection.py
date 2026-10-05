"""Provider-free orchestration/replay witnesses; mocks do not establish native proof."""
from copy import deepcopy
from datetime import timedelta
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import uuid

import pytest

ROOT=Path(__file__).resolve().parents[1]
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module);return module
c=load('test_poetry_collection',ROOT/'evaluation-results/hbq-poetry-human-reference-v1/collector.py')
fixtures=load('poetry_collection_preparation_fixtures',ROOT/'tests/test_poetry_reference_judging.py')


@pytest.fixture(scope='module')
def frozen(tmp_path_factory):
    runtime=fixtures.runtime.__wrapped__();manifest,files=fixtures.design.__wrapped__(runtime)
    root=tmp_path_factory.mktemp('poetry-collection-frozen')
    for name,raw in files.items():c.write_bytes(root/name,raw)
    return {'root':root,'manifest':manifest,'files':files,'sha':c.digest(files['manifest.json']),
        'code_sha':c.digest(Path(c.__file__).read_bytes()),'tools':Path(runtime[0]['external_pins']['tools_root_local_only']),
        'subset':runtime[2],'validator':c.p.load('poetry_collection_test_admission',root/'implementation/validate_response.py')}


class Receipts:
    reject=False
    def verify(self,sample,native,**kwargs):
        if self.reject:raise ValueError('Synthetic native receipt rejected')
        assert kwargs['model']=='gpt-6.1-sol' and kwargs['reasoning']=='high'
        assert kwargs['prompt']==(sample/'prompt.txt').read_bytes().decode()
        assert native['receipt_policy']=='codex_native_rollout_v1'
        for meta in native['provider_artifacts'].values():c.pinned(sample,meta['path'],meta)
    def event_identity(self,events,final):return json.loads(events)['thread_id'],[]


def answer(row):
    return {'verdicts':[{'question_id':qid,'verdict':'CANNOT_ASSESS','confidence':1,'note':'Fixture-only uncertainty.',
        'evidence':[{'kind':'summary','reference':'available source','exact_quote':None,'summary':'Mechanical uncertainty witness.'}]} for qid in row['question_ids']]}


@pytest.fixture
def job(tmp_path,frozen):
    output=tmp_path/'results';output.mkdir()
    binding=c.job_binding(frozen['manifest'],frozen['root'],frozen['sha'],'sol',frozen['tools'])
    c.record(output/'job.json',binding);c.record(output/'account-binding.json',c.t.account_receipt(binding))
    c.write_bytes(output/'frozen-manifest.json',frozen['files']['manifest.json'])
    state={'contacts':0,'invalid':False,'malformed':False,'fail':False,'duplicate':False,'stop_after':False}
    def call(**kwargs):
        assert kwargs['timeout']==900 and kwargs['attempt_number']==1 and kwargs['reasoning']=='high'
        assert kwargs['codex_receipt_policy']=='codex_native_rollout_v1'
        kwargs['before_provider_attempt']();state['contacts']+=1
        sample=kwargs['output_dir'];row=json.loads((sample/'condition.json').read_bytes())
        if state['fail']:
            c.write_bytes(sample/'failure.txt',b'fixture transport failure');raise TimeoutError('Synthetic timeout')
        response=answer(row)
        if state['invalid']:response['verdicts'][-1]['question_id']=response['verdicts'][0]['question_id']
        final=b'completed non-JSON' if state['malformed'] else c.canonical(response)
        identity=str(uuid.uuid5(uuid.NAMESPACE_URL,'duplicate' if state['duplicate'] else row['logical_sample_id']))
        events=c.canonical({'thread_id':identity});artifacts={}
        for key,path,raw in [('codex_message','native-final.json',final),('codex_events','events.json',events)]:
            c.write_bytes(sample/path,raw);artifacts[key]=c.p.metadata(path,raw)
        if state['stop_after']:c.write_bytes(output/'STOP',b'stop')
        return final.decode(),{'receipt_policy':'codex_native_rollout_v1','provider_artifacts':artifacts}
    return {**frozen,'output':output,'binding':binding,'state':state,'call':call,'receipts':Receipts(),
        'helper':SimpleNamespace(CLI=Path('fixture-not-executed.exe')),
        'rows':[r for r in frozen['manifest']['requests'] if r['endpoint']=='sol' and r['arm']=='hbq']}


def collect(job,row):
    return c.collect_one(row,job['manifest'],job['binding'],job['root'],job['output'],job['subset'],job['validator'],
        job['receipts'],job['helper'],job['call'])


def replay(job,row):
    return c.replay(c.sample_path(job['output'],row),row,job['manifest'],job['binding'],job['root'],job['receipts'],job['subset'],job['validator'])


def cli(job):
    return ['collector','--manifest',str(job['root']/'manifest.json'),'--manifest-sha256',job['sha'],
        '--collector-sha256',job['code_sha'],'--tools-root',str(job['tools']),'--results-dir',str(job['output']),'--endpoint','sol']


def test_frozen_geometry_no_write_validation_and_binding(frozen,tmp_path,monkeypatch,capsys):
    monkeypatch.setattr(c,'MANIFEST_SHA',frozen['sha'])
    source=frozen['root']/'manifest.json';before=source.read_bytes()
    loaded=c.load_manifest(source,frozen['sha'],frozen['code_sha'],frozen['tools'])
    assert loaded[0]==frozen['manifest'] and source.read_bytes()==before
    output=tmp_path/'fresh';args={**frozen,'output':output}
    original=c.p.load
    def guarded(name,path):
        assert Path(path).name!='secondary-helper.py';return original(name,path)
    monkeypatch.setattr(c.p,'load',guarded);monkeypatch.setattr('sys.argv',cli(args)+['--validate-only'])
    assert c.main()==0 and not output.exists()
    report=json.loads(capsys.readouterr().out);assert report['planned']==report['untouched']==480 and report['study_planned']==960
    assert report['provider_calls']==0 and not report['human_targets_opened']
    with pytest.raises(ValueError,match='pin differs'):c.load_manifest(source,frozen['sha'],'0'*64,frozen['tools'])
    binding=c.job_binding(frozen['manifest'],frozen['root'],frozen['sha'],'sol',frozen['tools'])
    assert binding['workers']==binding['attempts_per_logical_sample']==1 and binding['automatic_retries']==0
    assert binding['timeout_seconds']==900 and binding['runtime']['codex_receipt_policy']=='codex_native_rollout_v1'
    assert binding['payload_classification']=='public_repo' and 'no synthetic-origin claim' in binding['payload_description']


def test_semantic_cardinality_and_malformed_native_final_missing_no_resend(job):
    first,second,third=job['rows'][:3];job['state']['invalid']=True
    assert collect(job,first)=='semantic_rejected' and replay(job,first)[1] is None
    job['state'].update(invalid=False,malformed=True)
    assert collect(job,second)=='semantic_rejected' and replay(job,second)[1] is None
    assert (c.sample_path(job['output'],second)/'native-final.json').read_bytes()==b'completed non-JSON'
    job['state']['malformed']=False
    assert collect(job,third)=='accepted' and replay(job,third)[1]
    with pytest.raises(FileExistsError):collect(job,first)
    assert job['state']['contacts']==3


def test_native_failures_stop_resume_and_occupied_slots_cannot_resend(job,monkeypatch):
    first=job['rows'][0];job['state']['fail']=True
    assert collect(job,first)=='unadmitted_no_resend' and replay(job,first)[1] is None
    with pytest.raises(FileExistsError):collect(job,first)
    monkeypatch.setattr(c,'MANIFEST_SHA',job['sha']);monkeypatch.setattr('sys.argv',cli(job))
    with pytest.raises(ValueError,match='reconciliation; no resend'):c.main()
    assert job['state']['contacts']==1
    unresolved=c.sample_path(job['output'],job['rows'][1]);unresolved.mkdir()
    with pytest.raises(ValueError,match='unresolved; no resend'):c.main()
    assert job['state']['contacts']==1


def test_receipt_source_account_and_job_are_bound_before_admission(job):
    row=job['rows'][0];assert collect(job,row)=='accepted'
    sample=c.sample_path(job['output'],row)
    for path in [sample/'native-final.json',sample/'sources'/f"{row['sources'][0]['id']}.txt",
        sample/'task-context.json',job['output']/'account-binding.json',job['output']/'job.json']:
        raw=path.read_bytes();path.write_bytes(raw+b'changed')
        with pytest.raises((ValueError,json.JSONDecodeError)):replay(job,row)
        path.write_bytes(raw)
    job['receipts'].reject=True
    assert collect(job,job['rows'][1])=='unadmitted_no_resend'


def test_duplicate_native_uuid_and_late_hash_failure_cannot_advance(job,monkeypatch):
    job['state']['duplicate']=True
    assert collect(job,job['rows'][0])=='accepted'
    assert collect(job,job['rows'][1])=='unadmitted_no_resend'
    job['state']['duplicate']=False;row=job['rows'][2];original=c.digest;final=c.canonical(answer(row));injected=[]
    def late_hash(raw):
        if raw==final and not injected:injected.append(True);raise OSError('Synthetic late evidence hash failure')
        return original(raw)
    monkeypatch.setattr(c,'digest',late_hash)
    assert collect(job,row)=='unadmitted_no_resend'
    terminal,admitted=replay(job,row)
    assert injected and terminal['accepted'] is False and admitted is None
    with pytest.raises(FileExistsError):collect(job,row)
    assert job['state']['contacts']==3


def test_stop_before_contact_and_current_attempt_settles(job):
    c.write_bytes(job['output']/'STOP',b'stop')
    assert collect(job,job['rows'][0])=='unadmitted_no_resend' and job['state']['contacts']==0
    (job['output']/'STOP').unlink();job['state']['stop_after']=True
    assert collect(job,job['rows'][1])=='accepted'
    assert (job['output']/'stop-observed.json').exists() and job['state']['contacts']==1


def test_original_schema_and_strict_poem_grounding_both_apply(frozen):
    row=next(r for r in frozen['manifest']['requests'] if r['arm']=='poemetric')
    prompt,schema,texts,context=c.inputs(frozen['root'],frozen['manifest'],row)
    response=fixtures.poemetric_answer();before=deepcopy(response)
    def admit():return c.admission(frozen['root'],row,frozen['manifest'],response,schema,texts,context,frozen['subset'],frozen['validator'])
    assert admit()['accepted'] and response==before
    response['result']['diagnostics'].append(deepcopy(response['result']['diagnostics'][-1]))
    assert admit()['errors']==['Response violates original retained schema']
    response=deepcopy(before);response['result']['quality_comment']['evidence'][0]['quote']='SOURCE ORIGIN POLICY'
    assert not admit()['accepted']
    response=deepcopy(before);response['result']['diagnostics'][0].update(status='SCORED',score=3)
    assert not admit()['accepted']


def test_grok_route_expiry_deadline_disclosure_and_own_envelope(frozen,tmp_path):
    route={'name':'grok-build-grok-4.7','model':'grok-4.7','reported_model':'grok-4.7','reasoning_effort':'high',
        'timeout_seconds':900,'allowed_payload_classes':['public_repo'],'cost_evidence':{'expires_at':c.CUTOFF.isoformat()}}
    boundary=c.CUTOFF-timedelta(seconds=900)
    assert c.grok_contact_allowed(route,boundary-timedelta(microseconds=1)) and not c.grok_contact_allowed(route,boundary)
    expiry=boundary-timedelta(days=1);route['cost_evidence']['expires_at']=expiry.isoformat()
    assert not c.grok_contact_allowed(route,expiry-timedelta(seconds=899))
    binding=c.job_binding(frozen['manifest'],frozen['root'],frozen['sha'],'grok',frozen['tools'],route)
    assert binding['deadline_margin_seconds']==900
    row=next(r for r in frozen['manifest']['requests'] if r['endpoint']=='grok' and r['arm']=='hbq')
    prompt,schema,_,_=c.inputs(frozen['root'],frozen['manifest'],row);response=answer(row);session=str(uuid.uuid4())
    envelope=c.canonical({'sessionId':session,'structuredOutput':response});compact=lambda v:c.canonical(v).rstrip(b'\n')
    native={'state':'completed','result':{'runtime':{'session_id_hash':c.digest(session.encode()),'requested_model':'grok-4.7',
        'requested_reasoning_effort':'high','reported_model':'grok-4.7','execution_contract':{'output_schema_hash':c.digest(compact(json.loads(schema))) }},
        'request_hash':c.digest(compact({'prompt':prompt.decode()})),'output_hash':c.digest(compact(response)),'output':response,
        'native_envelope_artifact':{'sha256':c.digest(envelope),'byte_length':len(envelope)}}}
    sample=tmp_path/'grok';sample.mkdir();c.record(sample/'native-result.json',native)
    c.record(sample/'native-identity.json',{'session_id':session});c.write_bytes(sample/'native-envelope.json',envelope)
    assert c.native_answer(sample,row,binding,prompt,schema,None)[0]==response
    native['result']['runtime']['requested_reasoning_effort']='low';(sample/'native-result.json').write_bytes(c.canonical(native))
    with pytest.raises(ValueError,match='binding differs'):c.native_answer(sample,row,binding,prompt,schema,None)
    route['timeout_seconds']=300
    with pytest.raises(ValueError):c.job_binding(frozen['manifest'],frozen['root'],frozen['sha'],'grok',frozen['tools'],route)


def test_label_release_requires_two_full_verified_inventories_and_explicit_flag(frozen,tmp_path,monkeypatch):
    outputs={e:tmp_path/e for e in c.p.ENDPOINTS}
    for output in outputs.values():output.mkdir()
    # Gate arithmetic is isolated; own terminal replay is exercised above.
    monkeypatch.setattr(c,'verify_job_binding',lambda output,m,r,sha,e,tools:{'endpoint':e})
    partial={'enabled':False,'unresolved':False}
    def inventory(m,b,r,o,*args):
        if partial['unresolved']:raise ValueError('Occupied slot is unresolved; no resend')
        missing=1 if partial['enabled'] and b['endpoint']=='sol' else 0
        return [{}]*missing,['accepted']*(479-missing)+['semantic_rejected'],set()
    monkeypatch.setattr(c,'inventory',inventory)
    def gate(flag):return c.label_release_gate(frozen['manifest'],frozen['root'],frozen['sha'],frozen['tools'],outputs,None,None,None,flag)
    assert gate(False)['all_planned_verified_terminal'] and not gate(False)['human_release_eligible']
    assert gate(True)['human_release_eligible'] and not gate(True)['human_targets_opened']
    partial['enabled']=True;assert not gate(True)['human_release_eligible']
    partial['unresolved']=True
    with pytest.raises(ValueError,match='unresolved'):gate(True)
