"""Prospective contracts and exact grounding; no human ratings or native calls."""
from collections import Counter
import copy
import importlib.util
import json
from pathlib import Path
import sys

import pytest

ROOT=Path(__file__).resolve().parents[1]
PROGRAM=Path(r'C:\Users\Haile\Documents\cwr-resume-control-20260919-r1\successor-program-20261004')
spec=importlib.util.spec_from_file_location('test_poetry_judging_prepare',ROOT/'evaluation-results/hbq-poetry-human-reference-v1/prepare_judging.py')
p=importlib.util.module_from_spec(spec);spec.loader.exec_module(p)
admission=p.load('test_poetry_judging_admission',p.HERE/'arms/validate_response.py')


@pytest.fixture(scope='module')
def runtime():
    path=PROGRAM/'semantic-crossform/frozen-001/manifest.json'
    if not path.exists():pytest.skip('Pinned local runtime metadata unavailable')
    return p.runtime_inputs(path)


@pytest.fixture(scope='module')
def design(runtime):
    texts={}
    for i in range(10):
        raw=f'  Lantern {i} waits.\r\nA copper river answers.\r\n'.encode()
        texts['poem-'+f'{i:024x}']={'raw':raw,'source_path':f'fixture/{i}.txt','sha256':p.digest(raw),'bytes':len(raw)}
    before=copy.deepcopy(texts)
    manifest,files=p.build_design(texts,{}, {'contract_sha256':'fixture-source-contract'},*runtime)
    assert before==texts
    return manifest,files


def row(design,arm):return next(r for r in design[0]['requests'] if r['arm']==arm)


def check(design,r,answer,runtime):
    files=design[1];texts={s['id']:files[s['input_path']].decode() for s in r['sources']}
    return admission.semantic_validate(r['arm'],answer,r,texts,runtime[2],
        context=files[r['task_context']['path']].decode(),schema=json.loads(files[r['schema_path']]))


def poemetric_answer():
    ev={'quote':'Lantern','explanation':'A visible image.'}
    return {'status':'SCORED','abstention_reason':None,'result':{
        'method':'poemetric_unspecified_form_descendant_v1',
        'diagnostics':[{'item_id':i,'status':'CANNOT_ASSESS' if i<3 else 'SCORED',
            'score':None if i<3 else 0 if i in (7,8) else 3,
            'rationale':'Unprovided instruction.' if i<3 else 'Local judgment.',
            'evidence':[] if i<3 or i in (7,8) else [copy.deepcopy(ev)]} for i in range(1,9)],
        'overall_quality':{'item_id':10,'score':4,'rationale':'Independent overall judgment.',
            'evidence':[copy.deepcopy(ev),{'quote':'copper river','explanation':'A second observation.'}]},
        'literary_devices_comment':{'comment':'No devices identified.','evidence':[]},
        'quality_comment':{'comment':'Local overall observation.','evidence':[copy.deepcopy(ev)]}}}


def test_full_geometry_and_same_contract_repetition(design):
    manifest,files=design
    assert len(manifest['requests'])==960
    assert manifest['candidate'] is None and not manifest['execution_authority']
    assert manifest['human_label_gate']==p.HUMAN_GATE
    assert manifest['counts']['banks_per_endpoint']==30
    for endpoint in p.ENDPOINTS:
        rows=[r for r in manifest['requests'] if r['endpoint']==endpoint]
        assert Counter(r['arm'] for r in rows)==p.ARM_COUNTS
        for tid in manifest['bank_ids']:
            banks=[[r for r in rows if r['arm']=='hbq' and r['artifact_id']==tid and r['repeat']==cycle] for cycle in range(3)]
            ordered=[sorted(bank,key=lambda r:r['batch']) for bank in banks]
            assert all(sum(len(r['question_ids']) for r in bank)==95 for bank in ordered)
            assert all([r['question_ids'] for r in ordered[0]]==[r['question_ids'] for r in bank] for bank in ordered)
            assert all([r['prompt_sha256'] for r in ordered[0]]==[r['prompt_sha256'] for r in bank] for bank in ordered)
    assert all(r['bundle_id']=='poetry.general' for r in manifest['requests'])
    assert not any(name.startswith(('sealed/targets/','private/source-linkage')) for name in files)


def test_exact_source_bytes_unknown_scope_and_common_pretty_context(design):
    manifest,files=design
    contexts={r['task_context']['sha256'] for r in manifest['requests']}
    assert len(contexts)==1
    for r in manifest['requests']:
        prompt=files[r['prompt_path']];context=files[r['task_context']['path']]
        assert b'"audience": []' in context and context in prompt
        assert r['completion_status']=='unknown' and not r['whole_original_author_work_score_eligible']
        assert r['form']=='unspecified' and b'The default AI-origin assumption does not apply' in prompt
        for source in r['sources']:
            assert files[source['input_path']].startswith(b'  Lantern')
            assert files[source['input_path']] in prompt and b'\r\n' in files[source['input_path']]
        assert all(marker not in prompt for marker in (b'PRIVATE HUMAN RATING',b'CSV TARGET'))


def test_complete_bank_and_changed_text_fail_closed(design):
    manifest,files=design
    broken=copy.deepcopy(manifest)
    broken['requests'].remove(next(r for r in broken['requests'] if r['arm']=='hbq' and r['endpoint']=='sol'))
    with pytest.raises(ValueError):p.validate_design(broken,files)
    changed=dict(files);source=row(design,'hbq')['sources'][0]['input_path'];changed[source]+=b'altered'
    with pytest.raises(ValueError,match='commitment'):p.validate_design(manifest,changed)


def test_disjoint_pairs_reverse_exact_sides(design):
    manifest,_=design
    assert len({tid for pair in manifest['pairs'] for tid in (pair['left'],pair['right'])})==10
    for pair in manifest['pairs']:
        rows=[r for r in manifest['requests'] if r['arm']=='pairwise' and r['endpoint']=='sol' and r['pair_id']==pair['pair_id']]
        assert len(rows)==6
        for cycle in range(3):
            ab=next(r for r in rows if r['repeat']==cycle and r['orientation']=='AB')
            ba=next(r for r in rows if r['repeat']==cycle and r['orientation']=='BA')
            assert [s['id'] for s in ab['sources']]==[s['id'] for s in ba['sources']][::-1]
            assert [s['side'] for s in ab['sources']]==[s['side'] for s in ba['sources']]==['A','B']


def test_hbq_context_quote_is_grounded_but_instruction_is_not(design,runtime):
    r=row(design,'hbq')
    answer={'verdicts':[{'question_id':qid,'verdict':'YES','confidence':0.8,'note':'Context evidence.',
        'evidence':[{'kind':'exact_quote','reference':'common context','exact_quote':'"audience": []','summary':None}]} for qid in r['question_ids']]}
    assert check(design,r,answer,runtime)['accepted']
    answer['verdicts'][0]['evidence'][0]['exact_quote']='SOURCE ORIGIN POLICY'
    assert not check(design,r,answer,runtime)['accepted']


def test_pair_tie_and_abstention_are_distinct(design,runtime):
    r=row(design,'pairwise');files=design[1]
    answer={'method':'study2_presented_poem_pairwise_v1','winner':'TIE','tradeoff':'Balanced local effects.',
        'abstention_reason':None,'evidence':[{'side':s['side'],'quote':files[s['input_path']].decode().split('\r\n')[0],
            'explanation':'Visible local text.'} for s in r['sources']]}
    result=check(design,r,answer,runtime);assert result['accepted'] and not result['abstention']
    answer.update(winner='CANNOT_ASSESS',abstention_reason='Insufficient basis.',evidence=[])
    result=check(design,r,answer,runtime);assert result['accepted'] and result['abstention']
    answer.update(winner='TIE',abstention_reason=None)
    assert not check(design,r,answer,runtime)['accepted']


@pytest.mark.parametrize('arm,ceiling',[('holistic',7),('compact',5)])
def test_native_scales_and_abstention_preserved(design,runtime,arm,ceiling):
    ev={'quote':'Lantern','explanation':'Local visible choice.'}
    if arm=='holistic':
        result={'method':'study2_presented_poem_holistic_v1','score':ceiling,'rationale':'Overall local judgment.',
            'strengths':['Image relation.','Sound relation.'],'limitations':[],
            'evidence':[ev,{'quote':'copper river','explanation':'Second local choice.'}]}
        score_field='score'
    else:
        result={'method':'study2_presented_poem_compact_v1','overall_score':ceiling,'overall_rationale':'Independent overall judgment.',
            'dimensions':[{'dimension_id':dim,'score':3,'rationale':'Local dimension judgment.','evidence':[ev]} for dim in p.DIMENSIONS]}
        score_field='overall_score'
    r=row(design,arm);answer={'status':'SCORED','result':result,'abstention_reason':None}
    assert check(design,r,answer,runtime)['accepted']
    result[score_field]=ceiling+1
    assert not check(design,r,answer,runtime)['accepted']
    answer={'status':'CANNOT_ASSESS','result':None,'abstention_reason':'Supplied text is insufficient.'}
    assert check(design,r,answer,runtime)['accepted'] and check(design,r,answer,runtime)['abstention']


def test_poemetric_absence_is_diagnostic_not_primary_quality(design,runtime):
    r=row(design,'poemetric');answer=poemetric_answer()
    assert check(design,r,answer,runtime)['accepted']
    assert answer['result']['overall_quality']['score']==4
    assert answer['result']['diagnostics'][6]['score']==answer['result']['diagnostics'][7]['score']==0
    answer['result']['overall_quality']['score']=0
    assert not check(design,r,answer,runtime)['accepted']


@pytest.mark.parametrize('change',['form_score','theme_score','nonabsence_zero','duplicate_item','comment_quote','whitespace_quote','origin_field'])
def test_poemetric_contract_or_grounding_errors_rejected(design,runtime,change):
    answer=poemetric_answer();result=answer['result']
    if change in ('form_score','theme_score'):
        result['diagnostics'][0 if change=='form_score' else 1].update(status='SCORED',score=3)
    elif change=='nonabsence_zero':result['diagnostics'][2]['score']=0
    elif change=='duplicate_item':result['diagnostics'][-1]['item_id']=7
    elif change=='comment_quote':result['quality_comment']['evidence'][0]['quote']='SOURCE ORIGIN POLICY'
    elif change=='whitespace_quote':
        r=row(design,'poemetric')
        result['overall_quality']['evidence'][0]['quote']=design[1][r['sources'][0]['input_path']].decode().replace('\r\n','\n')
    else:result['inferred_authorship']='human'
    assert not check(design,row(design,'poemetric'),answer,runtime)['accepted']


def reference_fixture(tmp_path,monkeypatch):
    files={'implementation/prepare_sources.py':b'fixture projector', 'sealed/targets/study2.csv':b'PRIVATE HUMAN RATING',
        'private/source-linkage.json':b'PRIVATE CATALOGUE'}
    files.update({f'sealed/texts/poem-{i:024x}.qsf.txt':f'Fixture {i}.'.encode() for i in range(10)})
    for name,raw in files.items():
        path=tmp_path/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
    manifest={'policy':'study2_outcome_blind_poetry_source_v1','targets_sealed':True,'prediction_release_authorized':False,
        'artifacts':{name:p.metadata(name,raw) for name,raw in files.items()}}
    raw=p.canonical(manifest);path=tmp_path/'manifest.json';path.write_bytes(raw)
    monkeypatch.setattr(p,'REFERENCE_SHA',p.digest(raw));monkeypatch.setattr(p,'PROJECTOR_SHA',p.digest(files['implementation/prepare_sources.py']))
    return path


def test_reference_reader_never_opens_targets_or_catalogue(tmp_path,monkeypatch):
    path=reference_fixture(tmp_path,monkeypatch);original=Path.read_bytes
    def guarded(self):
        assert self.name not in ('study2.csv','source-linkage.json')
        return original(self)
    monkeypatch.setattr(Path,'read_bytes',guarded)
    texts,_,_=p.read_reference(path);assert len(texts)==10
    poem=tmp_path/'sealed/texts/poem-000000000000000000000000.qsf.txt';poem.write_bytes(b'changed')
    with pytest.raises(ValueError,match='differs'):p.read_reference(path)


def test_exact_reference_and_projector_pins_required(tmp_path,monkeypatch):
    path=reference_fixture(tmp_path,monkeypatch)
    raw=path.read_bytes();path.write_bytes(raw+b' ')
    with pytest.raises(ValueError,match='manifest differs'):p.read_reference(path)
    path.write_bytes(raw);(tmp_path/'implementation/prepare_sources.py').write_bytes(b'changed')
    with pytest.raises(ValueError,match='differs'):p.read_reference(path)


def test_fresh_output_and_no_write_dry_run(tmp_path,monkeypatch,design,runtime,capsys):
    source=tmp_path/'source';source.mkdir();out=tmp_path/'fresh'
    p.base.output_preflight(out,(source,))
    with pytest.raises(ValueError):p.base.output_preflight(source,(source,))
    monkeypatch.setattr(p,'read_reference',lambda path:({}, {}, {}))
    monkeypatch.setattr(p,'runtime_inputs',lambda path:runtime)
    monkeypatch.setattr(p,'build_design',lambda *args:design)
    monkeypatch.setattr(sys,'argv',['prepare_judging','--reference-manifest',str(source/'reference.json'),
        '--runtime-manifest',str(source/'runtime.json'),'--output-root',str(out),'--dry-run'])
    assert p.main()==0 and not out.exists()
    stdout=capsys.readouterr().out;report=json.loads(stdout)
    assert report['human_label_gate_closed'] and not report['human_values_opened'] and report['provider_calls']==0
    assert not any(word in stdout for word in ('Lantern','copper river','PRIVATE HUMAN'))
