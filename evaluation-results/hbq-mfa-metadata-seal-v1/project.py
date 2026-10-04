"""Seal pinned research sources and emit only outcome-blind cohort metadata."""
from __future__ import annotations
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
from urllib.request import Request, urlopen

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[1]
REVISION='d7e4925307ebe354a376ca7f38d8bd014775b6f2'
REPOSITORY='tuhinjubcse/Author-Style-Personalization'

def canonical(value):
    return (json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False)+'\n').encode('utf-8')

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def identity(value):
    return sha(canonical(value))

def git_blob(raw):
    return hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()

def project(data, filename):
    """Whitelist fields; never return winner, preference, rationale or excerpt text."""
    if not isinstance(data,dict):
        raise ValueError('Unexpected source root structure')
    task,condition,panel=Path(filename).name.split('_')[:3]
    rows=[]
    for target,authors in data.items():
        if not isinstance(target,str) or not isinstance(authors,dict):
            raise ValueError('Unexpected target grouping')
        for writer,judgments in authors.items():
            if not isinstance(writer,str) or not isinstance(judgments,list):
                raise ValueError('Unexpected writer grouping')
            for index,judgment in enumerate(judgments):
                if not isinstance(judgment,list) or len(judgment) not in (2,3):
                    raise ValueError('Unexpected judgment structure')
                record=judgment[-1]
                if not isinstance(record,dict):
                    raise ValueError('Unexpected judgment record')
                judge=judgment[1] if len(judgment)==3 else record.get('user')
                if not isinstance(judge,(str,int)) or isinstance(judge,bool) or judge=='':
                    raise ValueError('Missing rater identity; no inferred participant')
                excerpts=[record.get('Excerpt1'),record.get('Excerpt2')]
                if not all(isinstance(text,str) and text for text in excerpts):
                    raise ValueError('Missing source excerpt; no inferred artifact')
                hashes=[sha(text.encode('utf-8')) for text in excerpts]
                target_hash,writer_hash=identity(target),identity(writer)
                rows.append({'task':task,'condition':condition,'panel':panel,
                    'target_hash':target_hash,'writer_hash':writer_hash,'rater_hash':identity(judge),
                    'source_position':index,'excerpt_hashes':hashes,
                    'excerpt_bytes':[len(text.encode('utf-8')) for text in excerpts],
                    'pair_hash':identity({'target':target_hash,'condition':condition,'excerpts':sorted(hashes)}),
                    'judgment_identity_hash':identity(record.get('id')),
                    'metadata_record_hash':identity({'target':target_hash,'writer':writer_hash,'index':index,
                        'rater':identity(judge),'excerpts':hashes})})
    return rows

def aggregate(rows):
    counts=Counter((row['task'],row['condition'],row['panel']) for row in rows)
    by_task=[]
    for (task,condition,panel),count in sorted(counts.items()):
        selected=[row for row in rows if (row['task'],row['condition'],row['panel'])==(task,condition,panel)]
        by_task.append({'task':task,'condition':condition,'panel':panel,'judgments':count,
            'pairs':len({r['pair_hash'] for r in selected}),
            'target_clusters':len({r['target_hash'] for r in selected}),
            'writer_clusters':len({r['writer_hash'] for r in selected}),
            'rater_identifiers':len({r['rater_hash'] for r in selected}),
            'distinct_exact_excerpts':len({h for r in selected for h in r['excerpt_hashes']})})
    return {'judgment_rows':len(rows),'by_task':by_task,
        'distinct_target_clusters':len({r['target_hash'] for r in rows}),
        'distinct_writer_clusters':len({r['writer_hash'] for r in rows}),
        'distinct_rater_identifiers':len({r['rater_hash'] for r in rows}),
        'distinct_exact_excerpts':len({h for r in rows for h in r['excerpt_hashes']}),
        'distinct_pairs_across_tasks':len({r['pair_hash'] for r in rows}),
        'metadata_commitment_sha256':sha(canonical(rows))}

def write(path,raw):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('xb') as handle:
        handle.write(raw)

def fetch(url,bound):
    with urlopen(Request(url,headers={'User-Agent':'CWR-outcome-blind-source-audit/1'}),timeout=45) as response:
        if response.status!=200:
            raise ValueError('Source retrieval did not return HTTP200')
        raw=response.read(bound+1)
    if len(raw)>bound:
        raise ValueError('Source exceeds frozen byte bound')
    return raw

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--metadata',type=Path,required=True)
    parser.add_argument('--private-output',type=Path,required=True)
    parser.add_argument('--source-root',type=Path,help='Provider-free replay of already sealed source bytes')
    args=parser.parse_args()
    output=args.private_output.resolve()
    inputs=[REPO,args.metadata.resolve()]
    if args.source_root:
        inputs.append(args.source_root.resolve())
    if output.exists() or any(output.is_relative_to(p) or p.is_relative_to(output) for p in inputs):
        raise ValueError('Use a fresh private destination outside repository and inputs')
    metadata_raw=args.metadata.read_bytes()
    metadata=json.loads(metadata_raw)
    source=next(r for r in metadata['repositories'] if r['repository']==REPOSITORY)
    if source['revision']!=REVISION:
        raise ValueError('Source revision differs from registered metadata')
    blobs=source['expert_blobs']
    if len(blobs)!=4 or {Path(p).name for p,_,_ in blobs}!={f'{task}_{condition}_expert_anon.json' for task in ('quality','style') for condition in ('fewshot','finetuned')}:
        raise ValueError('Unexpected frozen expert source set')
    if any(not p.startswith('data/') or '..' in Path(p).parts or not 0<size<=4*1024*1024 for p,_,size in blobs):
        raise ValueError('Unexpected source path or byte bound')
    output.mkdir(parents=True,exist_ok=False)
    invocation={'policy':'mfa_outcome_blind_metadata_v1','metadata_sha256':sha(metadata_raw),
        'projector_sha256':sha(Path(__file__).read_bytes()),'repository':REPOSITORY,'revision':REVISION,
        'blobs':blobs,'fields_released':'hashes/counts/lengths/structural positions only',
        'target_values_released':False,'rationales_released':False,'excerpts_released':False,
        'purpose':'Owner-authorized private non-commercial confirmation design research; no excerpt/raw-outcome publication',
        'source_mode':'local_replay' if args.source_root else 'bounded_exact_pinned_raw_files',
        'automatic_network_retries':0}
    write(output/'invocation.json',canonical(invocation))
    rows=[]
    receipts=[]
    try:
        for path,blob_id,size in blobs:
            raw=(args.source_root/path).read_bytes() if args.source_root else fetch(f'https://raw.githubusercontent.com/{REPOSITORY}/{REVISION}/{path}',size)
            if len(raw)!=size or git_blob(raw)!=blob_id:
                raise ValueError('Source bytes differ from frozen Git blob/size')
            write(output/'sealed-source'/path,raw)
            projected=project(json.loads(raw),path)
            rows.extend(projected)
            receipts.append({'path':path,'git_blob_sha1':blob_id,'sha256':sha(raw),'bytes':size,
                'metadata_rows':len(projected),'metadata_sha256':sha(canonical(projected))})
        summary={'policy':'mfa_outcome_blind_metadata_v1','repository':REPOSITORY,'revision':REVISION,
            'source_receipts':receipts,'cohort':aggregate(rows),'target_values_released':False,
            'rationales_released':False,'excerpts_released':False,'human_alignment_results':None,
            'limitations':['Hashed identifier counts do not establish independently verified participants',
                'Pair/excerpt reuse remains in the ledger; rows are not independent works',
                'Only expert release geometry is projected; lay and cross-release row joins remain open',
                'Candidate, condition, target partition and confirmation plan are not frozen by this audit']}
        write(output/'private-metadata.json',canonical(rows))
        write(output/'summary.json',canonical(summary))
        write(output/'terminal.json',canonical({'state':'completed_blinded_projection','summary_sha256':sha(canonical(summary)),
            'private_metadata_sha256':sha(canonical(rows)),'target_opening_authorized':False}))
        print(json.dumps(summary,sort_keys=True))
        return 0
    except Exception as exc:
        write(output/'terminal.json',canonical({'state':'failed_preserved','error_class':type(exc).__name__,'error':str(exc)}))
        raise

if __name__=='__main__':
    raise SystemExit(main())
