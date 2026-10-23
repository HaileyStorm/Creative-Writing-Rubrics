"""Portable reproduction of the separate retrospective Sol DEV30 baseline.
The original private source/profile were frozen before the new associations.
No native reader, scorer, model, fit or confirmation reference is invoked.
"""
import argparse
from collections import Counter
from fractions import Fraction
import hashlib,json,math,random,statistics,sys
from pathlib import Path

INPUT_SHA={'replay': 'fc70eb43be0608e787eeb877b0d42bb81cc08efe47646c8759f69c5f3c57613f', 'schedule': '2836a81d26836274440318338b395a04dad51a80f7d339ca0612f8135dc0e82f', 'target_provenance': '499735faeeb24219dacbc32c4bbedb588aec30eb5ea72730028d5e3a8e10941b', 'targets': 'd9071d48465faf7beb37b249b5120e33645a3bc0925aec7856402d75fc2d35b5'}
AXES=('novel', 'original', 'rare', 'appropriate', 'feasible', 'publishable', 'well_written', 'enjoyed', 'boring', 'funny', 'twist', 'future')
PRIMARY=('well_written', 'enjoyed')
FROZEN_PROFILE_SHA='0559fd0b537cdfbbfe18f1fd662557808b3e02cba1c6425f61b3bb94e7944a7d'
FROZEN_SOURCE_SHA='8b5e51eee19a014a9c55e1c7b01b50266a4a51d34718c746090f96561a328cdb'
PUBLIC_PROFILE_SHA='2a1be320fceb6d164684f99d093a82bf20723314b4262911b91e15982348d066'

def sha(b):return hashlib.sha256(b).hexdigest()

def encoded(v):return (json.dumps(v,sort_keys=True,indent=2,allow_nan=False)+'\n').encode()

def ranks(values):
    order=sorted(range(len(values)),key=values.__getitem__);result=[None]*len(values);i=0
    while i<len(order):
        j=i+1
        while j<len(order) and values[order[j]]==values[order[i]]:j+=1
        average=Fraction(i+1+j,2)
        for k in order[i:j]:result[k]=average
        i=j
    return result

def rho(left,right):
    assert len(left)==len(right)
    if len(left)<2:return None
    a,b=ranks(left),ranks(right);ma=sum(a)/len(a);mb=sum(b)/len(b)
    aa=sum((v-ma)**2 for v in a);bb=sum((v-mb)**2 for v in b)
    return None if not aa or not bb else float(sum((x-ma)*(y-mb) for x,y in zip(a,b)))/math.sqrt(float(aa*bb))

def fraction(v):
    assert set(v)=={'numerator','denominator'} and type(v['numerator']) is type(v['denominator']) is int and v['denominator']>0
    result=Fraction(v['numerator'],v['denominator']);assert 1<=result<=9;return result

def distribution(values):
    c=Counter(values);return {'n':len(values),'minimum':min(values),'maximum':max(values),'mean':statistics.mean(values),'distinct_scores':len(c),'tied_unordered_pairs':sum(n*(n-1)//2 for n in c.values()),'floor_count':sum(v==0 for v in values),'ceiling_count':sum(v==100 for v in values),'at_or_below10':sum(v<=10 for v in values),'at_or_above90':sum(v>=90 for v in values),'native_range':[0,100]}

def percentile(values,p):
    ordered=sorted(values);position=(len(ordered)-1)*p;lo=math.floor(position);hi=math.ceil(position)
    return ordered[lo]+(ordered[hi]-ordered[lo])*(position-lo)

def analyze(*, replay_path, schedule_path, targets_path, provenance_path, profile_path):
    assert not sys.flags.optimize, 'Normal Python execution required'
    profile_bytes=profile_path.read_bytes();assert sha(profile_bytes)==PUBLIC_PROFILE_SHA
    profile=json.loads(profile_bytes);inputs={}
    for name,path in (('replay',replay_path),('schedule',schedule_path),('targets',targets_path),('target_provenance',provenance_path)):
        raw=path.read_bytes();assert sha(raw)==INPUT_SHA[name];inputs[name]=json.loads(raw)
    replay,schedule=inputs['replay'],inputs['schedule'];targets=inputs['targets']
    assert replay['full_study_admitted'] is False and replay['selected_requests']==2300 and replay['canonical_verdicts']==17800
    assert len(replay['accepted_native_thread_ids'])==len(set(replay['accepted_native_thread_ids']))==2300 and len(replay['unknown_exit_commitments'])==26
    rows=replay['endpoint_sol_rows'];assert len(rows)==100 and Counter(r['partition'] for r in rows)=={'TRAIN':70,'DEV':30}
    failures=[r for r in rows if r['coverage']<.88];assert len(failures)==2 and all(r['partition']=='TRAIN' for r in failures)
    assert sorted(r['coverage'] for r in failures)==[.8607,.8648]
    dev=[r for r in rows if r['partition']=='DEV'];ids={r['pass_id'] for r in dev}
    assert len(ids)==len(dev)==30 and ids==set(schedule['selected_dev_ids'])=={r['pass_id'] for r in schedule['selected_passes'] if r['partition']=='DEV'}
    assert len(targets)==60 and all(r['partition']=='DEV' for r in targets)
    lookup={r['opaque_story_id']:r for r in targets};assert len(lookup)==60
    panel=[]
    for r in sorted(dev,key=lambda r:r['pass_id']):
        assert type(r['score']) in (int,float) and math.isfinite(r['score']) and 0<=r['score']<=100 and .88<=r['coverage']<=1
        target=lookup[r['original_opaque_story_id']];assert set(target)=={'opaque_story_id','partition','rating_count','axis_means','indices'} and set(target['axis_means'])==set(AXES)
        assert type(target['rating_count']) is int and 9<=target['rating_count']<=14
        panel.append({'pass_id':r['pass_id'],'opaque_story_id':r['original_opaque_story_id'],'score':r['score'],'coverage':r['coverage'],'rating_count':target['rating_count'],'axis_means':target['axis_means']})
    assert len({r['opaque_story_id'] for r in panel})==30
    model=[Fraction(str(r['score'])) for r in panel];human={a:[fraction(r['axis_means'][a]) for r in panel] for a in AXES}
    associations={a:{'works':30,'rho':rho(model,human[a]),'target_orientation':'raw_source_negative_association_has_favorable_direction' if a=='boring' else 'raw_source_no_universal_quality_direction','role':'descendant_primary' if a in PRIMARY else 'exploratory'} for a in AXES}
    rng=random.Random(20261023);draws={a:[] for a in PRIMARY}
    for _ in range(2000):
        chosen=[rng.randrange(30) for _ in range(30)];x=[model[i] for i in chosen]
        for a in PRIMARY:draws[a].append(rho(x,[human[a][i] for i in chosen]))
    for a in PRIMARY:
        undefined=sum(v is None for v in draws[a]);associations[a]['conditional_story_bootstrap']={'replicates':2000,'seed':20261023,'undefined_draws':undefined,'interval95':None if undefined else [percentile(draws[a],.025),percentile(draws[a],.975)],'distribution_sha256':sha(encoded(draws[a])),'interpretation':'Pointwise conditional on selected stories and observed human means; shared evaluators, topic/condition clusters and selection not modeled.'}
    full_scores=[r['score'] for r in panel]
    report={'study_id':profile['study_id'],'state':'RETROSPECTIVE_SOL_ONLY_DEV30_BASELINE','frozen_profile_sha256':FROZEN_PROFILE_SHA,'frozen_source_sha256':FROZEN_SOURCE_SHA,'input_sha256':INPUT_SHA,'original_collection':{'stories':100,'TRAIN':70,'DEV':30,'requests':2300,'verdicts':17800,'distinct_local_thread_identities':2300,'unknown_exit_commitments':26,'process_success_proven_for_unknown_exits':False,'full_study_admitted':False,'TRAIN_coverage_failures_retained':[{'coverage':r['coverage'],'reason':'coverage_below_0.88'} for r in failures]},'analyzed':{'DEV_stories':30,'selected_DEV_stories':30,'missing_selected_DEV_stories':0,'prepared_DEV_story_mean_rows_decoded':60,'selected_DEV_rating_rows':sum(r['rating_count'] for r in panel),'per_story_rating_count_range':[min(r['rating_count'] for r in panel),max(r['rating_count'] for r in panel)],'coverage_range':[min(r['coverage'] for r in panel),max(r['coverage'] for r in panel)],'shared_evaluator_IDs_available':False},'score_distribution':distribution(full_scores),'associations':associations,'provider_calls':0,'canonical_scorer_calls':0,'new_human_labels':0,'Grok_fit_or_selection_reexecuted':False,'candidate_promoted':False,'confirmation_opened':False,'full_goal_complete':False,'limits':['Separate descriptive descendant; original selected100 sequencing, Grok winner and coverage gates remain unchanged and unmet.','The100story reduction followed partial model observation; selected30results do not establish generalization.','No contemporary native model/account/tools qualification or process-success proof is conferred on historical outputs.','Two primary axes chosen for this descendant; original co-primary novelty/usefulness unchanged. No twelve-axis composite.','Human targets are pooled per-story means; evaluator dependence and exact survey wording limitations remain.','Conditional story intervals are exploratory, pointwise and unadjusted; they are not population/crossed-rater confidence or a human ceiling.','No fitted candidate, matched competitor, causal improvement or prospective confirmation claim.']}
    return report

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('replay','schedule','targets','target-provenance','profile','output'):
        parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args()
    try:
        report=analyze(replay_path=args.replay.resolve(),schedule_path=args.schedule.resolve(),targets_path=args.targets.resolve(),provenance_path=args.target_provenance.resolve(),profile_path=args.profile.resolve())
        with args.output.open('xb') as stream:stream.write(encoded(report))
    except (OSError,ValueError,KeyError,TypeError,AssertionError) as error:
        parser.exit(2,'Dryad baseline: '+str(error)+'\n')
    print(json.dumps({'state':report['state'],'DEV_stories':report['analyzed']['DEV_stories'],'primary':{a:report['associations'][a] for a in PRIMARY},'provider_calls':0}))
if __name__=='__main__':main()
