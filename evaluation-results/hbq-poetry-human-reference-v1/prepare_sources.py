"""Outcome-blind Study 2 source projection; human targets remain sealed source bytes."""
from __future__ import annotations

import argparse
from collections import Counter,defaultdict
import csv
import hashlib
from html.parser import HTMLParser
import io
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET
import zipfile

REPO = Path(__file__).resolve().parents[2]
POLICY = 'study2_outcome_blind_poetry_source_v1'
PINS = {
    'study2.csv':(1848967,'4c0442ace467845c06633d36e9b7f1afc55a6985e3e978d59005b902521d70de'),
    'study2.qsf':(148003,'ce46f10ef87723414d6962cfd1c402c067a6c24bf1cf8ef9648e54c7cf0b0c02'),
    'assessment-poems.docx':(10989,'1744de5d8e380f0987de74ddad8f54858cc3bdabbe3680c0fac88881acac83b6'),
    'parser.Rmd':(53580,'fa154a5c7956a30752e6e5c6ba9b2a54d940c2a1b18b0feb4d8fe9f7a1ed349a'),
}
RATINGS = ('beautiful','imagery','inspiring','lyrical','meaningful','mood_emotion','moving','original',
    'overall_quality','profound','rhythm','sound','theme','witty')
COLUMNS = ('ResponseId','Poet','condition','beautiful','imagery','inspiring','lyrical','meaningful','mood_emotion',
    'moving','original','overall_quality','profound','rhyme','rhythm','sound','theme','witty','poem_ID','word_count',
    'line_count','stanzas','four_line_stanzas','rhymes_binary','all_lines_rhyme','first_person','Frequency',
    'Like poetry','College Major','Background in poetry','Age','Gender','Authorship','Discrimination Response','correct')
STRUCTURAL = ('word_count','line_count','stanzas','four_line_stanzas','rhymes_binary','all_lines_rhyme','first_person')
CONDITIONS = ('nothing','human','AI')
CONTRACT = {'policy':POLICY,'primary_condition':'nothing','ratings':list(RATINGS),'rating_scale':[1,7],
    'rhyme':'separate_categorical_source_field; not a quality rating',
    'target_key':'paste(Poet,poem_ID,sep="_")','human_target_values':'sealed_original_CSV_only_until_prediction_release',
    'QSF_text_policy':'HTML_normal_flow_ASCII_layout_whitespace; BR_LF; paragraph_boundaries; preserve_NBSP_and_Unicode',
    'DOCX_text_policy':'document_XML_t_text_tab_and_break; LF_between_paragraphs; retain_blank_paragraphs',
    'catalogue_alias_policy':'unique_casefold_alphanumeric_metadata_match; record_original_strings_and_mismatches',
    'linkage':'unique_QSF_loop_catalogue_or_exact_DOCX_body; independent_bases_must_agree; no_fuzzy_text',
    'form':'unknown; no inference from structural counts','scope':'presented_survey_poem; original_complete_work_not_attested',
    'proposed_bundle':'poetry.general/default.general_poem; pending_scope_review',
    'unused_data_certification':False,'provider_calls':0,'judging_authorized':False,'prediction_release_authorized':False}


def require(condition,message):
    if not condition: raise ValueError(message)
def digest(raw): return hashlib.sha256(raw).hexdigest()
def canonical(value): return (json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n').encode('utf-8')
def meta(raw): return {'bytes':len(raw),'sha256':digest(raw)}
def opaque(kind,value): return kind+'-'+digest(canonical({'study2_source':PINS['study2.csv'][1],'kind':kind,'value':value}))[:24]
def catalogue(value): return ''.join(c for c in value.casefold() if c.isalnum())


class SurveyHTML(HTMLParser):
    def __init__(self): super().__init__(convert_charrefs=True); self.parts=[]; self.literal=[]
    def handle_starttag(self,tag,attrs):
        require(tag in ('br','p','div','span','b','strong','i','em','u','font'),'Unsupported stimulus HTML element')
        if tag=='br': self.parts.append('\n'); self.literal.append('\n')
        elif tag in ('p','div') and self.parts and not self.parts[-1].endswith('\n'):
            self.parts.append('\n'); self.literal.append('\n')
    def handle_endtag(self,tag):
        if tag in ('p','div'): self.parts.append('\n'); self.literal.append('\n')
    def handle_data(self,data):
        self.literal.append(data); self.parts.append(re.sub(r'[ \t\r\n\f]+',' ',data))
    def result(self):
        # Normal-flow HTML discards collapsible spaces at line edges; NBSP remains literal.
        return re.sub(r' *\n *','\n',''.join(self.parts)).strip(' '),''.join(self.literal)


def extract_html(html):
    parser=SurveyHTML(); parser.feed(html); parser.close(); return parser.result()


def dict_nodes(value):
    if isinstance(value,dict):
        yield value
        for item in value.values(): yield from dict_nodes(item)
    elif isinstance(value,list):
        for item in value: yield from dict_nodes(item)


def qsf_stimuli(raw):
    qsf=json.loads(raw); elements=qsf['SurveyElements']
    blocks=[block for e in elements if e['Element']=='BL' for block in e['Payload'].values()
        if block.get('Type')!='Trash' and 'Static' in block.get('Options',{}).get('LoopingOptions',{})]
    require(len(blocks)==1,'Exactly one active static poem block required'); block=blocks[0]
    flow=next(e['Payload'] for e in elements if e['Element']=='FL')
    require(any(n.get('ID')==block['ID'] for n in dict_nodes(flow)),'Poem block absent from active flow')
    conditions={n['Value'] for n in dict_nodes(flow) if n.get('Field')=='condition' and 'Value' in n}
    require(conditions==set(CONDITIONS),'Source framing conditions differ')
    qids={v['QuestionID'] for v in block['BlockElements'] if 'QuestionID' in v}
    static=block['Options']['LoopingOptions']['Static']; poems=[]; framing=[]
    for element in elements:
        if element['Element']!='SQ' or element['PrimaryAttribute'] not in qids: continue
        payload=element['Payload']
        if payload.get('QuestionType')!='DB': continue
        links=[node for node in dict_nodes(payload.get('DisplayLogic',{}))
            if str(node.get('LeftOperand','')).startswith(block['ID']+',')]
        if not links:
            declared=[node['RightOperand'] for node in dict_nodes(payload.get('DisplayLogic',{}))
                if node.get('LeftOperand')=='condition' and node.get('RightOperand') in CONDITIONS]
            if declared:
                require(len(declared)==1,'Ambiguous framing display metadata')
                framing.append({'qid':element['PrimaryAttribute'],'condition':declared[0],
                    'question_text_sha256':digest(payload['QuestionText'].encode())})
            continue
        require(len(links)==1 and links[0]['LogicType']=='LoopAndMerge' and links[0]['Operator']=='EqualTo'
            and links[0]['RightOperand']=='lm://CurrentLoop','Unsupported poem loop linkage')
        slot=links[0]['LeftOperand'].split(',')[-1]
        require(slot in static and set(static[slot])=={'1'},'Missing static author metadata')
        html=payload['QuestionText']; text,literal=extract_html(html)
        spans=[]
        for match in re.finditer(rb'"QuestionText"\s*:\s*("(?:\\.|[^"\\])*")',raw):
            if json.loads(match[1])==html:
                spans.append({'byte':[match.start(1),match.end(1)],'sha256':digest(match[1])})
        require(bool(text.strip()) and spans,'Stimulus source string unavailable')
        poems.append({'qid':element['PrimaryAttribute'],'slot':slot,'catalogue_name':static[slot]['1'],
            'html':html,'text':text,'literal_text':literal,'question_text_raw_JSON_spans':spans,
            'question_text_sha256':digest(html.encode()),'question_text_UTF8_bytes':len(html.encode())})
    require(len(poems)==len(static)==10 and len({p['slot'] for p in poems})==10
        and len({digest(p['text'].encode()) for p in poems})==10,'Ten unique linked stimuli required')
    return poems,{'block_id':block['ID'],'flow_sha256':digest(canonical(flow)),
        'block_sha256':digest(canonical(block)),'framing_questions':framing}


def docx_sections(raw):
    with zipfile.ZipFile(io.BytesIO(raw)) as archive: xml=archive.read('word/document.xml')
    root=ET.fromstring(xml); ns='{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
    paragraphs=[]
    for paragraph in root.findall('.//'+ns+'body/'+ns+'p'):
        parts=[]
        for node in paragraph.iter():
            if node.tag==ns+'t': parts.append(node.text or '')
            elif node.tag==ns+'tab': parts.append('\t')
            elif node.tag in (ns+'br',ns+'cr'): parts.append('\n')
        paragraphs.append(''.join(parts))
    headings=[]
    for index,text in enumerate(paragraphs):
        match=re.fullmatch(r'(.+?)\s+(\d+):\s*(.+)',text)
        if match: headings.append((index,match[1],match[2],match[3]))
    require(len(headings)==10 and len({h[2] for h in headings})==10,'Ten unique DOCX poem headings required')
    sections={}
    for at,(start,name,poem_id,label) in enumerate(headings):
        end=headings[at+1][0] if at+1<len(headings) else len(paragraphs)
        body=paragraphs[start+1:end]; exact='\n'.join(body)
        # Keep the complete section too; only empty section-boundary paragraphs are excluded from the comparison body.
        first,last=0,len(body)
        while first<last and body[first]=='': first+=1
        while last>first and body[last-1]=='': last-=1
        text='\n'.join(body[first:last])
        sections[poem_id]={'catalogue_name':name,'source_label':label,'heading':paragraphs[start],
            'paragraph_span':[start+1,end],'body_paragraph_span':[start+1+first,start+1+last],
            'section_text':exact,'text':text,'document_xml_sha256':digest(xml),'boundary_empty_paragraphs':[first,len(body)-last]}
    return sections,meta(xml)


def csv_metadata(raw):
    reader=csv.DictReader(io.StringIO(raw.decode('utf-8-sig'),newline=''))
    require(tuple(reader.fieldnames)==COLUMNS,'Pinned 35-column assessment schema differs')
    targets={}; metadata=[]; responses=Counter(); missing=Counter(); framing=Counter(); pairs=Counter()
    for index,row in enumerate(reader):
        require(None not in row and all(row[k] for k in ('ResponseId','Poet','poem_ID','condition','Authorship')),'Required metadata missing')
        require(row['condition'] in CONDITIONS and row['Authorship'] in ('human','AI'),'Unknown source metadata category')
        key=row['Poet']+'_'+row['poem_ID']; target_id=opaque('poem',key); response_id=opaque('response',row['ResponseId'])
        target=targets.setdefault(key,{'target_id':target_id,'Poet':row['Poet'],'poem_ID':row['poem_ID'],
            'Authorship':row['Authorship'],'rows':0,'conditions':Counter(),'structural':defaultdict(set)})
        require(target['Authorship']==row['Authorship'],'Authorship metadata inconsistent within target')
        target['rows']+=1; target['conditions'][row['condition']]+=1
        for column in STRUCTURAL: target['structural'][column].add(row[column])
        # Outcomes are inspected only for absence; no numeric decoding, summaries, thresholds or selection.
        for column in (*RATINGS,'rhyme'): missing[column]+=int(row[column] is None or not row[column].strip())
        responses[response_id]+=1; framing[(row['condition'],row['Authorship'])]+=1; pairs[(response_id,target_id)]+=1
        metadata.append({'source_record_index':index,'response_id':response_id,'target_id':target_id,
            'condition':row['condition'],'Authorship':row['Authorship']})
    require(len(targets)==10 and len({t['poem_ID'] for t in targets.values()})==10,'Ten unique CSV poem IDs required')
    header=raw[:raw.index(b'\n')+1]
    summary={'rows':len(metadata),'columns':len(COLUMNS),'header':meta(header),'targets':len(targets),
        'conditions':{name:sum(n for (condition,_),n in framing.items() if condition==name) for name in CONDITIONS},
        'framing_denominators':[{'condition':condition,'Authorship':authorship,'rows':n} for (condition,authorship),n in sorted(framing.items())],
        'unique_response_ids':len(responses),'response_id_repetition_histogram':dict(sorted(Counter(responses.values()).items())),
        'repeated_response_target_pairs':sum(n>1 for n in pairs.values()),'target_field_missingness':dict(missing),
        'cross_study_response_overlap':'unknown; Study1 not loaded'}
    return targets,metadata,summary


def source_files(source_root,pins=PINS):
    files={name:(source_root/name).read_bytes() for name in pins}
    for name,raw in files.items(): require((len(raw),digest(raw))==pins[name],'Pinned source differs: '+name)
    terminal_raw=(source_root/'terminal.json').read_bytes(); terminal=json.loads(terminal_raw)
    require(terminal['state']=='completed_sealed_source_fetch' and terminal['human_targets_opened_by_model'] is False
        and terminal['poem_text_displayed'] is False and terminal['provider_judging_calls']==0,'Source sealed-fetch disposition differs')
    receipts={}
    for name,raw in files.items():
        receipt_raw=(source_root/(name+'.http.json')).read_bytes(); receipt=json.loads(receipt_raw)
        require(receipt['name']==name and receipt['status']==200 and (receipt['bytes'],receipt['sha256'])==pins[name]
            and sum(item==receipt for item in terminal['files'])==1,'Source HTTP/terminal commitment differs')
        receipts[name+'.http.json']=receipt_raw
    receipts['terminal.json']=terminal_raw
    if (source_root/'invocation.json').is_file(): receipts['invocation.json']=(source_root/'invocation.json').read_bytes()
    return files,receipts


def project(files,receipts):
    targets,rows,summary=csv_metadata(files['study2.csv']); poems,qsf_lineage=qsf_stimuli(files['study2.qsf'])
    sections,xml_meta=docx_sections(files['assessment-poems.docx'])
    rmd=files['parser.Rmd'].decode('utf-8'); schema_lines={}
    for number,fragment in [(73,'levels=c("nothing", "human", "AI")'),(138,'paste(assessment_data$Poet, assessment_data$poem_ID, sep = "_")'),
        (1031,'filter(condition == "nothing")')]:
        line=rmd.splitlines()[number-1]; require(fragment in line,'Source parser contract differs')
        schema_lines[str(number)]={'sha256':digest(line.encode()),'source':'parser.Rmd'}
    by_id={target['poem_ID']:target for target in targets.values()}; require(set(by_id)==set(sections),'DOCX/CSV poem IDs differ')
    output={'sealed/targets/study2.csv':files['study2.csv']}; ledger=[]; linked=set()
    for poem in sorted(poems,key=lambda p:p['qid']):
        catalogue_matches=[t for t in targets.values() if catalogue(t['Poet'])==catalogue(poem['catalogue_name'])]
        text_matches=[by_id[key] for key,section in sections.items() if poem['text']==section['text']]
        require(len(catalogue_matches)<=1 and len(text_matches)<=1,'Ambiguous source linkage')
        require(catalogue_matches or text_matches,'Unlinked QSF source; owner decision required')
        if catalogue_matches and text_matches: require(catalogue_matches[0]['target_id']==text_matches[0]['target_id'],'Metadata/text source linkage disagrees')
        target=(catalogue_matches or text_matches)[0]; tid=target['target_id']; section=sections[target['poem_ID']]
        require(tid not in linked,'Duplicate target source linkage'); linked.add(tid)
        base='sealed/texts/'+tid
        for suffix,text in [('.qsf.txt',poem['text']),('.qsf-literal-nodes.txt',poem['literal_text']),('.qsf.html',poem['html']),
            ('.docx.txt',section['text']),('.docx-section.txt',section['section_text'])]: output[base+suffix]=text.encode('utf-8')
        ledger.append({'target_id':tid,'CSV_key':{'Poet':target['Poet'],'poem_ID':target['poem_ID'],
                'commitment_sha256':digest((target['Poet']+'_'+target['poem_ID']).encode())},
            'Authorship':target['Authorship'],'rows':target['rows'],'conditions':dict(target['conditions']),
            'structural_source_values':{k:sorted(v) for k,v in target['structural'].items()},
            'QSF':{k:v for k,v in poem.items() if k not in ('text','literal_text','html')},
            'DOCX':{k:v for k,v in section.items() if k not in ('text','section_text')},
            'linkage_basis':['unique_catalogue_metadata']*bool(catalogue_matches)+['exact_DOCX_body']*bool(text_matches),
            'catalogue_exact_QSF_CSV':poem['catalogue_name']==target['Poet'],
            'catalogue_exact_DOCX_CSV':section['catalogue_name']==target['Poet'],
            'QSF_DOCX_exact_text_equal':poem['text']==section['text'],'form':'unknown','scope_review':'pending',
            'primary_text':meta(poem['text'].encode()),'DOCX_text':meta(section['text'].encode())})
    require(len(linked)==10,'Complete source linkage required')
    public_targets=[{'target_id':t['target_id'],'key_commitment_sha256':t['CSV_key']['commitment_sha256'],
        'primary_text_sha256':t['primary_text']['sha256'],'primary_text_bytes':t['primary_text']['bytes'],
        'Authorship':t['Authorship'],'rows':t['rows'],'conditions':t['conditions'],
        'QSF_DOCX_exact_text_equal':t['QSF_DOCX_exact_text_equal'],'form':'unknown','scope_review':'pending'} for t in ledger]
    summary.update({'policy':POLICY,'contract':CONTRACT,'source_files':{name:meta(raw) for name,raw in files.items()},
        'fetch_receipt_files':len(receipts),'source_parser_contract':schema_lines,'QSF_structure':qsf_lineage,
        'document_xml':xml_meta,'target_inventory':public_targets,
        'exact_QSF_DOCX_matches':sum(t['QSF_DOCX_exact_text_equal'] for t in ledger),
        'catalogue_QSF_CSV_mismatches':sum(not t['catalogue_exact_QSF_CSV'] for t in ledger),
        'catalogue_DOCX_CSV_mismatches':sum(not t['catalogue_exact_DOCX_CSV'] for t in ledger),
        'human_target_values_displayed':False,'poem_text_displayed':False,'candidate':None,
        'limitations':['Ten presented poems support a descriptive existing-reference baseline only.',
            'Public showcase and published aggregate exposure exist; unused-data certification unavailable.',
            'Rights and later-upload byte equivalence remain unresolved.',
            'Form, generic poetry scope and prediction release require separate review; no invented author brief.',
            'QSF and DOCX variants remain separately committed; no fuzzy text repair or catalogue equivalence claim.',
            'Original human ratings/rhyme stay in sealed source CSV; no outcome decoding or analysis performed.']})
    for name,raw in files.items():
        if name!='study2.csv': output['sealed/source/'+name]=raw
    for name,raw in receipts.items(): output['private/fetch-provenance/'+name]=raw
    output['private/source-linkage.json']=canonical(ledger); output['private/row-metadata.json']=canonical(rows)
    output['summary.json']=canonical(summary)
    return summary,output


def output_preflight(output,source):
    output,source=output.resolve(),source.resolve()
    require(not output.exists(),'Output must be fresh and nonexistent')
    for retained in (REPO,source): require(not output.is_relative_to(retained) and not retained.is_relative_to(output),'Output overlaps repository or source')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root',type=Path,required=True); parser.add_argument('--output-root',type=Path,required=True)
    parser.add_argument('--dry-run',action='store_true'); args=parser.parse_args()
    output_preflight(args.output_root,args.source_root)
    files,receipts=source_files(args.source_root); summary,artifacts=project(files,receipts)
    artifacts['implementation/prepare_sources.py']=Path(__file__).read_bytes()
    manifest={'schema_version':1,'policy':POLICY,'contract_sha256':digest(canonical(CONTRACT)),
        'source_root_local_only':str(args.source_root.resolve()),'source_files':{k:meta(v) for k,v in files.items()},
        'artifacts':{k:meta(v) for k,v in artifacts.items()},'targets_sealed':True,'prediction_release_authorized':False}
    artifacts['manifest.json']=canonical(manifest)
    if not args.dry_run:
        for name,raw in artifacts.items():
            path=args.output_root/name; path.parent.mkdir(parents=True,exist_ok=True)
            with path.open('xb') as file: file.write(raw)
    # This explicit whitelist excludes private catalogues, poem text, target values and demographic/free responses.
    print(json.dumps({key:summary[key] for key in ('policy','rows','columns','targets','conditions','framing_denominators',
        'unique_response_ids','response_id_repetition_histogram','repeated_response_target_pairs','target_field_missingness',
        'cross_study_response_overlap','fetch_receipt_files','exact_QSF_DOCX_matches','catalogue_QSF_CSV_mismatches',
        'catalogue_DOCX_CSV_mismatches','human_target_values_displayed','poem_text_displayed')}|{
        'dry_run':args.dry_run,'output_written':not args.dry_run,'manifest':meta(artifacts['manifest.json']),
        'source_files':summary['source_files'],'artifact_count':len(artifacts),'artifact_bytes':sum(map(len,artifacts.values()))},sort_keys=True))
    return 0


if __name__=='__main__': raise SystemExit(main())
