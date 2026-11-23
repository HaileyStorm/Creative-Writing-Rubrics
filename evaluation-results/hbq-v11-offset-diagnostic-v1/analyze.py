"""Retrospective fixed-offset diagnostic on published matched V11 scores."""
import argparse
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path
import subprocess

COMMIT='f28270f6bd0971baa33504c7c682c8da7bce74c3'
HASHES={'grok':'6366de64754c365c4d91a9117d8c174f771ad50062ef342f11996cddfa78c58e',
        'sol':'eef0c259a86a4a9fb5e465bfa03fa93bc4e862ad1bdd15abe0a71ebc2efaaa82'}
DIMS={'Coherence','Complexity','Empathy','Engagement','Relevance','Surprise'}


def read(repo,endpoint):
    path=f'evaluation-results/hbq-human-alignment-optimizer-v11-train-{endpoint}-result-v1/result.json'
    data=subprocess.run(['git','-C',str(repo),'show',COMMIT+':'+path],check=True,stdout=subprocess.PIPE).stdout
    if sha256(data).hexdigest()!=HASHES[endpoint]:raise ValueError('source changed')
    return json.loads(data,parse_float=Decimal,parse_int=Decimal)


def analyze(data):
    rows=data['cells']; comparison=data['comparison']
    base=comparison['baseline_candidate_id']; child=comparison['child_candidate_id']
    if len(rows)!=8 or base==child:raise ValueError('unexpected geometry')
    mapped={}
    for row in rows:
        key=(row['prompt_group_id'],row['candidate_id'])
        if key in mapped or row['candidate_id'] not in (base,child):raise ValueError('duplicate or unknown cell')
        if set(row['scores'])!=DIMS or set(row['target'])!=DIMS:raise ValueError('dimension mismatch')
        for x in list(row['scores'].values())+list(row['target'].values()):
            if not isinstance(x,Decimal) or not x.is_finite():raise ValueError('invalid numeric value')
        if any(not 1<=x<=5 for x in row['target'].values()):raise ValueError('invalid reference scale')
        mapped[key]=row
    groups=sorted({g for g,_ in mapped})
    if len(groups)!=4 or len(mapped)!=8:raise ValueError('unexpected groups')
    methods={k:[] for k in ('baseline','child20','shifted_clipped','shifted_unclipped','fixed_three')};clipped=0;below_scale=0
    for g in groups:
        a=mapped[g,base]; b=mapped[g,child]
        if a['target']!=b['target']:raise ValueError('unpaired references')
        target=a['target']; values=a['scores']; other=b['scores']
        clipped+=sum(values[d]+1>5 for d in DIMS)
        below_scale+=sum(values[d]<1 for d in DIMS)
        predictions={'baseline':values,'child20':other,'shifted_clipped':{d:max(Decimal(1),min(Decimal(5),values[d]+1)) for d in DIMS},
                     'shifted_unclipped':{d:values[d]+1 for d in DIMS},'fixed_three':{d:Decimal(3) for d in DIMS}}
        for k,p in predictions.items():methods[k].append(sum(abs(p[d]-target[d]) for d in DIMS)/6)
    mean={k:sum(v)/4 for k,v in methods.items()}
    published={v['candidate_id']:v['equal_group_mae'] for v in data['metrics']}
    if set(published)!={base,child} or any(abs(mean[k]-published[c])>Decimal('1e-12') for k,c in (('baseline',base),('child20',child))):
        raise ValueError('published means differ')
    delta=[a-b for a,b in zip(methods['shifted_clipped'],methods['child20'])]
    return {'groups':4,'dimensions':6,'mae':{k:format(v.quantize(Decimal('.000001')),'f') for k,v in mean.items()},
            'clipped_dimension_count':clipped,'baseline_below_reference_scale_count':below_scale,
            'shifted_vs_child_group_counts':{'lower':sum(x<0 for x in delta),'equal':sum(x==0 for x in delta),'higher':sum(x>0 for x in delta)}}


def main():
    p=argparse.ArgumentParser();p.add_argument('--repo',type=Path,required=True);p.add_argument('--verify',type=Path);args=p.parse_args()
    result={'schema':'v11_fixed_offset_diagnostic_v1','source_commit':COMMIT,'source_sha256':HASHES,
            'definition':'baseline + 1, clipped to [1,5]; unclipped and fixed-3 shown separately',
            'selection':'post-hoc, not a trained mapping or frozen comparator',
            'results':{e:analyze(read(args.repo,e)) for e in ('grok','sol')}}
    raw=(json.dumps(result,sort_keys=True,indent=2)+'\n').encode()
    if args.verify:
        if args.verify.read_bytes().replace(b'\r\n',b'\n')!=raw:raise ValueError('saved result differs')
        print('Aggregate reproduced')
    else:print(raw.decode(),end='')

if __name__=='__main__':main()
