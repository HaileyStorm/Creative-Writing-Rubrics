"""Fixture proofs of source linkage and sealed outcomes; no human-rating inspection."""
from copy import deepcopy
import csv
import importlib.util
import io
import json
from pathlib import Path
import zipfile

import pytest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('test_poetry_reference_prepare',ROOT/'evaluation-results/hbq-poetry-human-reference-v1/prepare_sources.py')
p=importlib.util.module_from_spec(spec); spec.loader.exec_module(p)
POEM_SENTINEL='SEALED_CREATIVE_TEXT'
TARGET_SENTINEL='SEALED_HUMAN_TARGET'
DEMO_SENTINEL='SEALED_DEMOGRAPHIC'


@pytest.fixture
def sources():
    stream=io.StringIO(newline=''); writer=csv.DictWriter(stream,fieldnames=p.COLUMNS); writer.writeheader()
    for condition in p.CONDITIONS:
        for at in range(1,11):
            row={k:'' for k in p.COLUMNS}; row.update(ResponseId='person-'+condition,Poet='Writer '+str(at),poem_ID=str(at),
                condition=condition,Authorship='AI' if at<=5 else 'human',word_count='4',line_count='2',Age=DEMO_SENTINEL)
            for name in (*p.RATINGS,'rhyme'): row[name]=TARGET_SENTINEL
            writer.writerow(row)
    block_id='BL_poems'; elements=[]
    for at in range(1,11):
        html=POEM_SENTINEL+str(at)+'<br>\nsecond line'
        elements.append({'Element':'SQ','PrimaryAttribute':'QID'+str(at),'Payload':{'QuestionType':'DB','QuestionText':html,
            'DisplayLogic':{'0':{'0':{'LeftOperand':block_id+','+str(at),'RightOperand':'lm://CurrentLoop',
                'LogicType':'LoopAndMerge','Operator':'EqualTo'}}}}})
    block={'ID':block_id,'Type':'Standard','BlockElements':[{'QuestionID':'QID'+str(at)} for at in range(1,11)],
        'Options':{'LoopingOptions':{'Static':{str(at):{'1':'Writer '+str(at)} for at in range(1,11)}}}}
    elements += [{'Element':'BL','Payload':{'1':block}},{'Element':'FL','Payload':{'Flow':[{'ID':block_id},
        *[{'EmbeddedData':[{'Field':'condition','Value':name}]} for name in p.CONDITIONS]]}}]
    xml=['<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>']
    for at in range(1,11):
        for text in ['Writer '+str(at)+' '+str(at)+': '+('AI' if at<=5 else 'human'),POEM_SENTINEL+str(at),'second line','']:
            xml.append('<w:p><w:r><w:t>'+text+'</w:t></w:r></w:p>')
    xml.append('</w:body></w:document>'); document=io.BytesIO()
    with zipfile.ZipFile(document,'w') as archive: archive.writestr('word/document.xml',''.join(xml).encode())
    lines=['']*1031
    lines[72]='assessment_data$condition <- factor(assessment_data$condition, levels=c("nothing", "human", "AI"), ordered=FALSE)'
    lines[137]='assessment_data$poem <- paste(assessment_data$Poet, assessment_data$poem_ID, sep = "_")'
    lines[1030]='nothing <- merged_data %>% filter(condition == "nothing")'
    return {'study2.csv':stream.getvalue().encode(),'study2.qsf':p.canonical({'SurveyElements':elements}),
        'assessment-poems.docx':document.getvalue(),'parser.Rmd':'\n'.join(lines).encode()}


def mutate_qsf(sources,change):
    qsf=json.loads(sources['study2.qsf']); change(qsf); sources['study2.qsf']=p.canonical(qsf)


def test_blind_metadata_and_separate_exact_sealed_artifacts(sources):
    before=deepcopy(sources); summary,files=p.project(sources,{})
    public=p.canonical(summary).decode()
    assert TARGET_SENTINEL not in public and POEM_SENTINEL not in public and DEMO_SENTINEL not in public
    assert summary['rows']==30 and summary['targets']==10 and summary['conditions']==dict.fromkeys(p.CONDITIONS,10)
    assert summary['unique_response_ids']==3 and summary['response_id_repetition_histogram']=={10:3}
    assert summary['exact_QSF_DOCX_matches']==10 and summary['contract']['prediction_release_authorized'] is False
    assert files['sealed/targets/study2.csv']==sources['study2.csv']
    assert all(name.startswith(('sealed/','private/')) or name=='summary.json' for name in files)
    assert sources==before
    ledger=json.loads(files['private/source-linkage.json'])
    assert all(item['form']=='unknown' and item['scope_review']=='pending' for item in ledger)
    assert all(set(item['linkage_basis'])=={'unique_catalogue_metadata','exact_DOCX_body'} for item in ledger)


def test_html_BR_paragraph_entity_and_DOCX_break_fidelity():
    primary,literal=p.extract_html('<p>first&nbsp;line<br>\nsecond</p><p>third</p>')
    assert primary=='first\u00a0line\nsecond\nthird\n'
    assert literal=='first\u00a0line\n\nsecond\nthird\n'
    with pytest.raises(ValueError):p.extract_html('<pre>unknown rendering</pre>')


def test_catalogue_typo_exact_body_basis_and_distinct_text_variant(sources):
    def change(qsf):
        block=next(e['Payload']['1'] for e in qsf['SurveyElements'] if e['Element']=='BL')
        block['Options']['LoopingOptions']['Static']['1']['1']='Catalogue Typo'
        qsf['SurveyElements'][1]['Payload']['QuestionText']=POEM_SENTINEL+'2<br>second&nbsp;line'
    mutate_qsf(sources,change)
    summary,files=p.project(sources,{})
    assert summary['catalogue_QSF_CSV_mismatches']==1 and summary['exact_QSF_DOCX_matches']==9
    ledger=json.loads(files['private/source-linkage.json'])
    typo=next(t for t in ledger if t['CSV_key']['poem_ID']=='1')
    assert typo['linkage_basis']==['exact_DOCX_body'] and typo['QSF']['catalogue_name']=='Catalogue Typo'
    different=next(t for t in ledger if t['CSV_key']['poem_ID']=='2')
    assert different['linkage_basis']==['unique_catalogue_metadata'] and not different['QSF_DOCX_exact_text_equal']
    assert different['primary_text']['sha256']!=different['DOCX_text']['sha256']


@pytest.mark.parametrize('kind',['ambiguous_catalogue','conflicting_bases','unlinked','inactive_block','missing_stimulus'])
def test_linkage_fails_without_silent_guessing(sources,kind):
    def change(qsf):
        block=next(e['Payload']['1'] for e in qsf['SurveyElements'] if e['Element']=='BL')
        if kind=='ambiguous_catalogue':block['Options']['LoopingOptions']['Static']['1']['1']='Writer 2'
        if kind=='conflicting_bases':qsf['SurveyElements'][0]['Payload']['QuestionText']=qsf['SurveyElements'][1]['Payload']['QuestionText']+' '
        if kind=='unlinked':
            block['Options']['LoopingOptions']['Static']['1']['1']='Unknown catalogue'
            qsf['SurveyElements'][0]['Payload']['QuestionText']='Unmatched creative text'
        if kind=='inactive_block':qsf['SurveyElements'][-1]['Payload']['Flow'][0]['ID']='BL_other'
        if kind=='missing_stimulus':block['BlockElements'].pop()
    mutate_qsf(sources,change)
    with pytest.raises(ValueError):p.project(sources,{})


def test_raw_source_string_and_row_metadata_commitments(sources):
    summary,files=p.project(sources,{})
    ledger=json.loads(files['private/source-linkage.json']); qsf=sources['study2.qsf']
    for item in ledger:
        for location in item['QSF']['question_text_raw_JSON_spans']:
            start,end=location['byte']; assert p.digest(qsf[start:end])==location['sha256']
    rows=json.loads(files['private/row-metadata.json'])
    assert all(set(row)=={'source_record_index','response_id','target_id','condition','Authorship'} for row in rows)
    assert TARGET_SENTINEL not in files['private/row-metadata.json'].decode() and DEMO_SENTINEL not in files['private/row-metadata.json'].decode()


def test_missingness_is_not_rating_decoding_or_quality_selection(sources):
    text=sources['study2.csv'].decode(); text=text.replace(TARGET_SENTINEL+',',',',1); sources['study2.csv']=text.encode()
    summary,files=p.project(sources,{})
    assert summary['target_field_missingness']['beautiful']==1 and summary['targets']==10
    assert files['sealed/targets/study2.csv']==sources['study2.csv']


def saved_fetch(root,sources):
    root.mkdir(); pins={name:(len(raw),p.digest(raw)) for name,raw in sources.items()}; receipts=[]
    for name,raw in sources.items():
        (root/name).write_bytes(raw); receipt={'name':name,'bytes':len(raw),'sha256':p.digest(raw),'status':200}
        (root/(name+'.http.json')).write_bytes(p.canonical(receipt)); receipts.append(receipt)
    terminal={'state':'completed_sealed_source_fetch','human_targets_opened_by_model':False,'poem_text_displayed':False,
        'provider_judging_calls':0,'files':receipts}; (root/'terminal.json').write_bytes(p.canonical(terminal))
    return pins


@pytest.mark.parametrize('kind',['source_bytes','receipt','terminal'])
def test_source_and_fetch_receipts_fail_closed(sources,tmp_path,kind):
    root=tmp_path/'fetch'; pins=saved_fetch(root,sources)
    assert p.source_files(root,pins)[0]==sources
    if kind=='source_bytes':(root/'study2.csv').write_bytes(b'changed source')
    if kind=='receipt':
        receipt=json.loads((root/'study2.qsf.http.json').read_bytes());receipt['sha256']='0'*64
        (root/'study2.qsf.http.json').write_bytes(p.canonical(receipt))
    if kind=='terminal':
        terminal=json.loads((root/'terminal.json').read_bytes());terminal['human_targets_opened_by_model']=True
        (root/'terminal.json').write_bytes(p.canonical(terminal))
    with pytest.raises(ValueError):p.source_files(root,pins)


def test_dry_run_whitelist_and_fresh_output(sources,tmp_path,monkeypatch,capsys):
    root=tmp_path/'source';root.mkdir(); output=tmp_path/'fresh'
    monkeypatch.setattr(p,'source_files',lambda path:(sources,{}))
    monkeypatch.setattr('sys.argv',['prepare_sources.py','--source-root',str(root),'--output-root',str(output),'--dry-run'])
    assert p.main()==0; raw=capsys.readouterr().out; report=json.loads(raw)
    assert not output.exists() and report['dry_run'] and not report['output_written']
    assert all(secret not in raw for secret in (POEM_SENTINEL,TARGET_SENTINEL,DEMO_SENTINEL,'Writer'))
    output.mkdir()
    with pytest.raises(ValueError):p.output_preflight(output,root)
    with pytest.raises(ValueError):p.output_preflight(root/'new',root)
    with pytest.raises(ValueError):p.output_preflight(ROOT/'new-private',root)
