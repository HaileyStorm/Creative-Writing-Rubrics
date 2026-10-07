"""Retrospective matched scalar calibration with entire-prompt cross-fitting."""
from __future__ import annotations
import argparse,hashlib,importlib.util,json,os
from collections import Counter,defaultdict
from fractions import Fraction
from pathlib import Path

HERE=Path(__file__).resolve().parent;REPO=HERE.parents[1]
PROFILE_SHA='784f61c5889b5d95a13b363ba680887bd7ff980e9f2db6c0c47c59ae0f752e69'
FLOOR=HERE.parent/'hbq-multisample-floor-discrimination-v1'
LEXER=HERE.parent/'hbq-human-agreement-story-bootstrap-v1/source.py'
PARENT_REPORT=HERE.parent/'hbq-historical-annotator-sensitivity-v1/result.json'
METHODS=('isotonic','training_median','training_mean','native_affine')
def require(condition,message):
    if not condition:raise ValueError(message)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def checked(path,pin):
    raw=path.read_bytes();require(sha(raw)==pin,'Pinned input differs: '+path.name);return raw
def fraction_json(value):
    if isinstance(value,Fraction):return {'n':value.numerator,'d':value.denominator}
    raise TypeError(type(value).__name__)
def canonical(value):return (json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False,default=fraction_json)+'\n').encode()
def load(path,pin,name):
    checked(path,pin);spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
def pava(points):
    require(bool(points) and all(w>0 for _,_,w in points),'Positive training weights required')
    grouped=defaultdict(lambda:[Fraction(0),Fraction(0)])
    for x,y,w in points:grouped[x][0]+=w*y;grouped[x][1]+=w
    xs=sorted(grouped);blocks=[]
    for i,x in enumerate(xs):
        wy,w=grouped[x];blocks.append(([i],wy,w))
        while len(blocks)>1 and blocks[-2][1]/blocks[-2][2]>blocks[-1][1]/blocks[-1][2]:
            right=blocks.pop();left=blocks.pop()
            blocks.append((left[0]+right[0],left[1]+right[1],left[2]+right[2]))
    values={i:wy/w for indices,wy,w in blocks for i in indices}
    return [(x,values[i]) for i,x in enumerate(xs)]
def predict(knots,x):
    require(bool(knots),'Empty fit')
    if x<=knots[0][0]:return knots[0][1],('clamped_lower' if x<knots[0][0] else 'exact_training_score')
    if x>=knots[-1][0]:return knots[-1][1],('clamped_upper' if x>knots[-1][0] else 'exact_training_score')
    for (a,ya),(b,yb) in zip(knots,knots[1:]):
        if a<x<=b:return (yb,'exact_training_score') if x==b else (ya+(yb-ya)*(x-a)/(b-a),'interpolated')
    raise ValueError('Training knots not ordered')
def weighted_median(values):
    ordered=sorted(values);half=sum((w for _,w in ordered),Fraction(0))/2;total=Fraction(0)
    for i,(value,weight) in enumerate(ordered):
        total+=weight
        if total>half:return value
        if total==half:return (value+ordered[i+1][0])/2
    raise ValueError('Empty median')
def fold_predictions(train,held,scores,targets,prompts,bounds):
    require(train and held and set(train).isdisjoint(held) and
            {prompts[i] for i in train}.isdisjoint({prompts[i] for i in held}),'Prompt-disjoint fold required')
    counts=Counter(prompts[i] for i in train);weights={i:Fraction(1,counts[prompts[i]]) for i in train}
    points=[(scores[i],targets[i],weights[i]) for i in train];knots=pava(points)
    median=weighted_median([(targets[i],weights[i]) for i in train])
    mean=sum((targets[i]*weights[i] for i in train),Fraction(0))/sum(weights.values(),Fraction(0))
    forecasts={method:{} for method in METHODS};modes=Counter()
    for i in held:
        fitted,mode=predict(knots,scores[i]);modes[mode]+=1
        for method,value in [('isotonic',fitted),('training_median',median),('training_mean',mean),
                             ('native_affine',1+4*(scores[i]-bounds[0])/(bounds[1]-bounds[0]))]:
            require(1<=value<=5,'Predicted reference scale differs');forecasts[method][i]=value
    return forecasts,{'knots':knots,'training_weights':weights,'training_median':median,'training_mean':mean,
                      'training_items':len(train),'training_prompts':len(counts),'unique_training_scores':len(knots),
                      'fitted_plateaus':len({y for _,y in knots}),'prediction_modes':dict(modes)}
def average(values):return sum(values,Fraction(0))/len(values)
def curve_bins(items,forecasts,targets,prompts):
    ordered=sorted(items,key=lambda i:(forecasts[i],i));n=len(ordered)
    cuts=[i for i in range(2,n-1) if forecasts[ordered[i-1]]<forecasts[ordered[i]]]
    cut=min(cuts,key=lambda i:(abs(2*i-n),i)) if cuts else None
    bins=[ordered] if cut is None else [ordered[:cut],ordered[cut:]]
    counts=Counter(prompts[i] for i in items);result=[]
    for members in bins:
        require(len(members)>=2,'Private individual target would enter public curve')
        weights={i:Fraction(1,counts[prompts[i]]) for i in members};total=sum(weights.values(),Fraction(0))
        result.append({'items':len(members),'prompt_groups':len({prompts[i] for i in members}),
                       'predicted_mean':float(sum((weights[i]*forecasts[i] for i in members),Fraction(0))/total),
                       'human_mean':float(sum((weights[i]*targets[i] for i in members),Fraction(0))/total)})
    return result
def calculate(panel,prompts,cohorts,targets,ranges,correlation):
    require(set(targets)==set(prompts),'Reference/prompt membership differs')
    means={arm:{i:average(values) for i,values in scores.items()} for arm,scores in panel.items()}
    rows=[];private=[]
    for cohort,items in cohorts.items():
        groups=sorted({prompts[i] for i in items})
        for arm,scores in means.items():
            forecasts={method:{} for method in METHODS};folds=[];modes=Counter()
            for number,group in enumerate(groups,1):
                train=[i for i in items if prompts[i]!=group];held=[i for i in items if prompts[i]==group]
                values,fit=fold_predictions(train,held,scores,targets,prompts,ranges[arm])
                for method in METHODS:
                    require(set(values[method]).isdisjoint(forecasts[method]),'Duplicate held-out forecast')
                    forecasts[method].update(values[method])
                modes.update(fit['prediction_modes']);folds.append({'fold':number,'prompt_hash':group,'train_ids':train,'held_ids':held,**fit})
            require(all(set(values)==set(items) for values in forecasts.values()),'Missing held-out forecast')
            group_mae={};group_mse={}
            for method,values in forecasts.items():
                group_mae[method]=[average([abs(values[i]-targets[i]) for i in items if prompts[i]==group]) for group in groups]
                group_mse[method]=[average([(values[i]-targets[i])**2 for i in items if prompts[i]==group]) for group in groups]
            paired_mae=[a-b for a,b in zip(group_mae['isotonic'],group_mae['training_median'])]
            paired_mse=[a-b for a,b in zip(group_mse['isotonic'],group_mse['training_mean'])]
            rows.append({'cohort':cohort,'arm':arm,'items':len(items),'prompt_groups':len(groups),'folds':len(folds),
                         'training_items_min':min(f['training_items'] for f in folds),'training_items_max':max(f['training_items'] for f in folds),
                         'training_prompts':len(groups)-1,'prediction_modes':dict(modes),
                         'group_equal_mae':{m:float(average(v)) for m,v in group_mae.items()},
                         'group_equal_mse':{m:float(average(v)) for m,v in group_mse.items()},
                         'isotonic_minus_training_median_mae':float(average(paired_mae)),
                         'isotonic_minus_training_mean_mse':float(average(paired_mse)),
                         'paired_mae_groups':{'lower_error':sum(v<0 for v in paired_mae),'equal_error':sum(v==0 for v in paired_mae),'higher_error':sum(v>0 for v in paired_mae)},
                         'raw_score_spearman':correlation([scores[i] for i in items],[targets[i] for i in items]),
                         'out_of_fold_spearman':{m:correlation([forecasts[m][i] for i in items],[targets[i] for i in items]) for m in METHODS},
                         'isotonic_prediction_curve':curve_bins(items,forecasts['isotonic'],targets,prompts)})
            private.append({'cohort':cohort,'arm':arm,'items':items,'prompt_hashes':{i:prompts[i] for i in items},
                            'references':{i:targets[i] for i in items},'model_means':{i:scores[i] for i in items},'forecasts':forecasts,
                            'folds':folds,'group_mae':group_mae,'group_mse':group_mse,'paired_mae':paired_mae,'paired_mse':paired_mse})
    return rows,private
def run(annotations,source_root):
    profile=json.loads(checked(HERE/'profile.json',PROFILE_SHA));checked(PARENT_REPORT,profile['selected_annotation_parent_report_sha256'])
    lexer=load(LEXER,profile['lexer_source_sha256'],'calibration_pinned_lexer')
    floor=load(FLOOR/'analyze.py',profile['floor_source_sha256'],'calibration_pinned_panel')
    floor_profile=json.loads(checked(FLOOR/'profile.json',profile['floor_profile_sha256']))
    source_raw={name:floor.checked(source_root,pin) for name,pin in floor_profile['source_pins'].items()}
    repository_raw={name:floor.checked(REPO,pin) for name,pin in floor_profile['repository_pins'].items()}
    panel,prompts,cohorts=floor.preflight(source_root,floor_profile,repository_raw,source_raw)
    projected=lexer.metadata_projector()(checked(annotations,profile['selected_annotations_sha256']),
        {story:[{'values':True}] for story in profile['sample_story_ids']})
    require(all(len(rows)==3 and all(len(row['values'])==6 and all(type(v)is int and 1<=v<=5 for v in row['values']) for row in rows) for rows in projected.values()),'Selected reference shape/range differs')
    targets={'hanna-'+story:Fraction(sum(sum(row['values']) for row in rows),18) for story,rows in projected.items()}
    parent=lexer.parent_module({'parent_source_sha256':profile['parent_spearman_source_sha256']})
    rows,private=calculate(panel,prompts,cohorts,targets,floor_profile['native_ranges'],parent.spearman_average_ties)
    report={'schema_version':1,'policy':profile['policy'],'profile_sha256':PROFILE_SHA,'source_sha256':sha(Path(__file__).read_bytes()),
            'bindings':{key:profile[key] for key in profile if key.endswith('_sha256')},'panel_source_pins':floor_profile['source_pins'],
            'panel_repository_pins':floor_profile['repository_pins'],'geometry':dict(stories=11,prompt_groups=10,arms=6,repeats=5,model_values=330,human_annotations=33,arm_cohort_rows=12,folds=60,held_out_item_arm_predictions=66),
            'fit':profile['fit'],'metrics':profile['metrics'],'timing':profile['timing'],'scope':profile['scope'],
            'interpretation':profile['interpretation'],'prior_work':profile['prior_work'],'non_claims':profile['non_claims'],'rows':rows}
    return report,private
def create(path,raw):
    with path.open('xb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
    require(path.read_bytes()==raw,'Output readback differs')
def main():
    parser=argparse.ArgumentParser()
    for flag in ('annotations','source-root','output'):parser.add_argument('--'+flag,required=True,type=Path)
    args=parser.parse_args();output=args.output.resolve()
    require(not output.exists() and all(not output.is_relative_to(root.resolve()) and not root.resolve().is_relative_to(output) for root in (REPO,args.annotations.parent,args.source_root)),'Fresh private output outside repository and retained inputs required')
    report,private=run(args.annotations,args.source_root);output.mkdir()
    create(output/'report.json',canonical(report));create(output/'private-folds.json',canonical(private))
    print(json.dumps({'report_sha256':sha(canonical(report)),'private_folds_sha256':sha(canonical(private)),'rows':len(report['rows'])}))
if __name__=='__main__':main()
