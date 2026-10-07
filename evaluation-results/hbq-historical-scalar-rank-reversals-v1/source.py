"""Exact within-input repeat pair order diagnostics; no target or inference use."""
from __future__ import annotations
import argparse,hashlib,importlib.util,json,os
from collections import Counter
from fractions import Fraction
from itertools import combinations
from pathlib import Path
HERE=Path(__file__).resolve().parent;REPO=HERE.parents[1]
PROFILE_SHA='24fc9488ba452c405d5efa429078ca4dffbdd74809009c7ad5378feb122fcd4b'
FLOOR=HERE.parent/'hbq-multisample-floor-discrimination-v1'
CATEGORIES=('strict_reversal','stable_strict','always_tied','tie_changing_no_reversal')
SIGNS=(-1,0,1)
def require(condition,message):
    if not condition:raise ValueError(message)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def checked(path,pin):
    raw=path.read_bytes();require(sha(raw)==pin,'Pinned input differs: '+path.name);return raw
def encode(value):
    if isinstance(value,Fraction):return {'numerator':value.numerator,'denominator':value.denominator}
    raise TypeError(type(value).__name__)
def canonical(value):return (json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False,default=encode)+'\n').encode()
def sign(value):return (value>0)-(value<0)
def category(signs):
    require(len(signs)==5 and all(type(v)is int and v in SIGNS for v in signs),'Five exact signs required')
    unique=set(signs)
    if -1 in unique and 1 in unique:return 'strict_reversal'
    if unique=={0}:return 'always_tied'
    if 0 in unique:return 'tie_changing_no_reversal'
    return 'stable_strict'
def ratio(n,d):return Fraction(n,d) if d else None
def summarize(pairs):
    counts={name:0 for name in CATEGORIES};matrix=[[0]*3 for _ in SIGNS]
    for pair in pairs:
        counts[category(pair['signs'])]+=1
        for a,b in combinations(pair['signs'],2):matrix[a+1][b+1]+=1
    n=len(pairs);den=n*10;require(sum(counts.values())==n and sum(map(sum,matrix))==den,'Pair counts differ')
    strict_flips=matrix[0][2]+matrix[2][0]
    tie_changes=matrix[0][1]+matrix[1][0]+matrix[1][2]+matrix[2][1]
    both_strict=matrix[0][0]+matrix[0][2]+matrix[2][0]+matrix[2][2]
    same_sign=sum(matrix[i][i] for i in range(3))
    require(strict_flips+tie_changes+same_sign==den,'Sign comparison partition differs')
    return {'item_pairs':n,'available_pairs':n,'missing_pairs':0,'pair_category_counts':counts,
      'pairs_with_any_tie':sum(0 in p['signs'] for p in pairs),'pair_strict_reversal_rate':ratio(counts['strict_reversal'],n),
      'repeat_index_pair_comparisons':den,'sign_cross_tab_order':['negative','tie','positive'],'sign_cross_tab':matrix,
      'strict_flip_comparisons':strict_flips,'tie_change_comparisons':tie_changes,'same_sign_comparisons':same_sign,
      'both_strict_comparisons':both_strict,'strict_flip_rate_all_comparisons':ratio(strict_flips,den),
      'strict_flip_rate_when_both_strict':ratio(strict_flips,both_strict)}
def calculate(panel,prompts,cohorts):
    require(len(panel)==6 and len(prompts)==11 and all(set(v)==set(prompts) for v in panel.values()),'Matched panel required')
    require(all(len(values)==5 for by_item in panel.values() for values in by_item.values()),'Five repeat values required')
    rows=[];private=[]
    for cohort,items in cohorts.items():
        items=sorted(items);require(len(items) in (5,6),'Frozen cohort size differs')
        for arm,by_item in panel.items():
            pairs=[]
            for left,right in combinations(items,2):
                signs=[sign(a-b) for a,b in zip(by_item[left],by_item[right],strict=True)]
                pairs.append({'left':left,'right':right,'same_prompt':prompts[left]==prompts[right],
                              'signs':signs,'category':category(signs)})
            same=[p for p in pairs if p['same_prompt']];different=[p for p in pairs if not p['same_prompt']]
            require(len(same)==(0 if len(items)==6 else 1),'Frozen within-prompt pairs differ')
            rows.append({'cohort':cohort,'arm':arm,'items':len(items),'prompt_groups':len({prompts[i] for i in items}),
              'repeats':5,'all_pairs':summarize(pairs),'same_prompt_pairs':summarize(same),'different_prompt_pairs':summarize(different)})
            private.append({'cohort':cohort,'arm':arm,'items':items,'prompt_hashes':{i:prompts[i] for i in items},
              'scores':{i:by_item[i] for i in items},'pairs':pairs})
    require(len(rows)==12 and sum(r['all_pairs']['item_pairs'] for r in rows)==150,'Planned pair geometry differs')
    return rows,private
def run(source_root):
    profile=json.loads(checked(HERE/'profile.json',PROFILE_SHA))
    checked(FLOOR/'analyze.py',profile['floor_source_sha256'])
    spec=importlib.util.spec_from_file_location('rank_reversal_pinned_floor',FLOOR/'analyze.py');floor=importlib.util.module_from_spec(spec);spec.loader.exec_module(floor)
    floor_profile=json.loads(checked(FLOOR/'profile.json',profile['floor_profile_sha256']))
    source_raw={name:floor.checked(source_root,pin) for name,pin in floor_profile['source_pins'].items()}
    repository_raw={name:floor.checked(REPO,pin) for name,pin in floor_profile['repository_pins'].items()}
    panel,prompts,cohorts=floor.preflight(source_root,floor_profile,repository_raw,source_raw)
    rows,private=calculate(panel,prompts,cohorts)
    report={'schema_version':1,'policy':profile['policy'],'source_sha256':sha(Path(__file__).read_bytes()),'profile_sha256':PROFILE_SHA,
      'floor_source_sha256':profile['floor_source_sha256'],'floor_profile_sha256':profile['floor_profile_sha256'],
      'panel_source_pins':floor_profile['source_pins'],'panel_repository_pins':floor_profile['repository_pins'],
      'cohort_commitments':floor_profile['cohorts'],'geometry':profile['planned'],
      'repeat_index':profile['repeat_index'],'pair_orientation':profile['pair_orientation'],'categories':profile['categories'],
      'metrics':profile['metrics'],'timing':profile['timing'],'scope':profile['inputs'],'interpretation':profile['interpretation'],
      'rows':rows,'provider_calls':0,'human_targets_materialized':False,'new_native_admission':False,
      'leaf_chance_adjusted_agreement_measured':False,'interendpoint_measured':False,'promotion':False}
    return report,private
def create(path,raw):
    with path.open('xb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
    require(path.read_bytes()==raw,'Output readback differs')
def main():
    parser=argparse.ArgumentParser()
    for flag in ('source-root','output'):parser.add_argument('--'+flag,required=True,type=Path)
    args=parser.parse_args();output=args.output.resolve()
    require(not output.exists() and all(not output.is_relative_to(root.resolve()) and not root.resolve().is_relative_to(output) for root in (REPO,args.source_root)),'Fresh private output outside repository and retained inputs required')
    report,private=run(args.source_root);output.mkdir()
    create(output/'report.json',canonical(report));create(output/'private-pairs.json',canonical(private))
    print(json.dumps({'report_sha256':sha(canonical(report)),'private_pairs_sha256':sha(canonical(private)),'rows':len(report['rows'])}))
if __name__=='__main__':main()
