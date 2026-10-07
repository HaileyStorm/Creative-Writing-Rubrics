"""Fixed-panel global Worker-ID omissions on the opened historical HANNA slice."""
from __future__ import annotations
import argparse
from collections import defaultdict
from fractions import Fraction
import hashlib
import importlib.util
import json
from pathlib import Path
import statistics

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[1]
FLOOR=HERE.parent/'hbq-multisample-floor-discrimination-v1'
LEXER=HERE.parent/'hbq-human-agreement-story-bootstrap-v1/source.py'
PROFILE_SHA='91c1751d2d6070b795990db9c7278d22bb68eaae3d9239478f009055210d451b'
HBQ='hbq_short_story_batch32'

def require(condition,message):
    if not condition: raise ValueError(message)
def sha(raw): return hashlib.sha256(raw).hexdigest()
def canonical(value): return (json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n').encode()
def checked(path,pin):
    raw=path.read_bytes()
    require(sha(raw)==pin,'Pinned input differs: '+path.name)
    return raw
def load_module(path,pin,name):
    checked(path,pin)
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module

def collect_selected(raw,stories,axes,lexer,identity_rows):
    iterator=iter(lexer.csv_spans(raw))
    header=[lexer.decode_field(raw,span) for span in next(iterator)]
    positions={name:index for index,name in enumerate(header)}
    require(len(header)==len(positions) and {'Story ID','Worker ID','Assignment ID','Story','Prompt','Name',*axes}<=set(header),
            'HANNA header differs')
    rows={story:[] for story in stories}
    accounting={'selected_rows':0,'unselected_rows_metadata_only':0,'rating_fields_decoded':0,
                'unselected_rating_fields_decoded':0,'story_prompt_Name_fields_decoded':0}
    for source_row,spans in enumerate(iterator,1):
        require(len(spans)==len(header),'CSV row width differs')
        story=lexer.decode_field(raw,spans[positions['Story ID']])
        if story not in rows:
            accounting['unselected_rows_metadata_only']+=1
            continue
        position=len(rows[story])
        worker=lexer.decode_field(raw,spans[positions['Worker ID']])
        assignment=lexer.decode_field(raw,spans[positions['Assignment ID']])
        require(position<len(identity_rows[story]),'Extra selected source row')
        require(identity_rows[story][position]=={'source_row':source_row,'within_story_position':position,
                                               'worker_id':worker,'assignment_id':assignment},'Identity/source-order drift')
        values=[int(lexer.decode_field(raw,spans[positions[axis]])) for axis in axes]
        require(all(1<=value<=5 for value in values),'Selected rating range differs')
        rows[story].append({'worker_id':worker,'assignment_id':assignment,'values':values})
        accounting['selected_rows']+=1; accounting['rating_fields_decoded']+=len(axes)
    require(all(len(values)==3 and len({v['worker_id'] for v in values})==3 and
                all(v['worker_id'].strip() and v['assignment_id'].strip() for v in values) for values in rows.values()),
            'Selected three-worker coverage differs')
    return rows,accounting

def targets(rows,omitted=None):
    output={}; counts={}
    for story,annotations in rows.items():
        remaining=[row for row in annotations if row['worker_id']!=omitted]
        require(len(remaining)>=2 and all(len(row['values'])==6 for row in remaining),'Omission coverage differs')
        output['hanna-'+story]=Fraction(sum(sum(row['values']) for row in remaining),6*len(remaining))
        counts['hanna-'+story]=len(remaining)
    return output,counts

def sign(value): return (value>0)-(value<0)
def difference(value,reference): return None if value is None or reference is None else value-reference
def summarize(values):
    defined=[value for value in values if value is not None]
    return {'planned':len(values),'defined':len(defined),'undefined':len(values)-len(defined),
            'minimum':min(defined) if defined else None,'maximum':max(defined) if defined else None}

def calculate(rows,panel,cohorts,legacy,correlation):
    workers=sorted({row['worker_id'] for annotations in rows.values() for row in annotations})
    require(len(workers)==7,'Frozen worker-ID set differs')
    exact,original_counts=targets(rows)
    means={arm:{item:sum(values,Fraction(0))/len(values) for item,values in items.items()} for arm,items in panel.items()}
    require(all(set(items)==set(exact) for items in means.values()),'Model/reference item join differs')
    baseline=[]; omissions=[]; output=[]; contrasts=[]; tie_rows=[]
    for cohort,items in cohorts.items():
        require(set(items)<=set(exact),'Cohort join differs')
        base={arm:correlation([scores[item] for item in items],[exact[item] for item in items]) for arm,scores in means.items()}
        pairs=[(left,right) for i,left in enumerate(items) for right in items[i+1:]]
        tie_rows.append({'cohort':cohort,'pairs':len(pairs),
                         'exact_tied_pairs':sum(exact[a]==exact[b] for a,b in pairs),
                         'legacy_float_tied_pairs':sum(legacy[a]==legacy[b] for a,b in pairs),
                         'tie_partition_disagreements':sum((exact[a]==exact[b])!=(legacy[a]==legacy[b]) for a,b in pairs),
                         'strict_direction_reversals':sum(sign(exact[a]-exact[b])*sign(legacy[a]-legacy[b])==-1 for a,b in pairs)})
        states=[]
        for number,worker in enumerate(workers,1):
            reference,counts=targets(rows,worker)
            values={arm:correlation([scores[item] for item in items],[reference[item] for item in items]) for arm,scores in means.items()}
            states.append(values)
            omissions.append({'cohort':cohort,'worker_label':f'worker-{number:03d}',
                              'affected_stories':sum(counts[item]!=original_counts[item] for item in items),
                              'surviving_annotations':sum(counts[item] for item in items),
                              'retained_stories':len(items),'spearman_by_arm':values})
        for arm,scores in means.items():
            legacy_rho=correlation([scores[item] for item in items],[legacy[item] for item in items])
            baseline.append({'cohort':cohort,'arm':arm,'items':len(items),'spearman_exact_targets':base[arm],
                             'spearman_frozen_float_targets_same_exact_model_means':legacy_rho})
            output.append({'cohort':cohort,'arm':arm,'items':len(items),'baseline':base[arm],
                           'worker_id_omission_sensitivity':summarize([state[arm] for state in states])})
            if arm!=HBQ:
                values=[difference(state[arm],state[HBQ]) for state in states]
                contrasts.append({'cohort':cohort,'comparator':arm,'baseline_delta':difference(base[arm],base[HBQ]),
                                  'worker_id_omission_delta_sensitivity':summarize(values)})
    return {'baselines':baseline,'omission_states':omissions,'rows':output,'paired_contrasts':contrasts,'target_tie_comparison':tie_rows}

def run(csv_path,frozen_path,identity_path,source_root):
    profile=json.loads(checked(HERE/'profile.json',PROFILE_SHA))
    lexer=load_module(LEXER,profile['lexer_source_sha256'],'hanna_rater_pinned_csv')
    floor=load_module(FLOOR/'analyze.py',profile['floor_source_sha256'],'hanna_rater_pinned_panel')
    floor_profile=json.loads(checked(FLOOR/'profile.json',profile['floor_profile_sha256']))
    source_raw={name:floor.checked(source_root,pin) for name,pin in floor_profile['source_pins'].items()}
    repository_raw={name:floor.checked(REPO,pin) for name,pin in floor_profile['repository_pins'].items()}
    panel,prompts,cohorts=floor.preflight(source_root,floor_profile,repository_raw,source_raw)
    frozen=lexer.metadata_projector()(checked(frozen_path,profile['frozen11_sha256']),{
        'samples':[{'item_id':True,'story_id':True,'human_overall':True}]})['samples']
    require([row['story_id'] for row in frozen]==profile['sample_story_ids'] and
            all(row['item_id']=='hanna-'+row['story_id'] for row in frozen),'Frozen eleven-item membership differs')
    identity=json.loads(checked(identity_path,profile['identity_rows_sha256']))
    rows,accounting=collect_selected(checked(csv_path,profile['csv_sha256']),profile['sample_story_ids'],profile['axes'],lexer,identity)
    legacy={row['item_id']:row['human_overall'] for row in frozen}
    exact,_=targets(rows)
    for story,annotations in rows.items():
        nested=statistics.fmean(statistics.fmean(row['values'][axis] for row in annotations) for axis in range(6))
        require(nested==legacy['hanna-'+story] and abs(float(exact['hanna-'+story])-nested)<=1e-12,
                'Original human scalar reconstruction differs')
    parent=lexer.parent_module({'parent_source_sha256':'de21884862ac28dbeba840b28aede1ba38ab9245f9557b11a47ad93d22e730fd'})
    result=calculate(rows,panel,cohorts,legacy,parent.spearman_average_ties)
    report={'schema_version':1,'policy':profile['policy'],'profile_sha256':PROFILE_SHA,'source_sha256':sha(Path(__file__).read_bytes()),
            'source_bindings':{key:profile[key] for key in ('csv_sha256','frozen11_sha256','identity_rows_sha256','floor_source_sha256','floor_profile_sha256','lexer_source_sha256')},
            'panel_source_pins':floor_profile['source_pins'],'panel_repository_pins':floor_profile['repository_pins'],
            'geometry':{'stories':11,'prompt_clusters':len(set(prompts.values())),'original_items':6,'later_items':5,
                        'arms':6,'model_repetitions':5,'model_scalar_values':330,'human_annotations':33,'worker_ids':7,'omission_states_per_cohort':7},
            'legacy_human_scalar_reconstructed_exactly':True,'field_accounting':accounting,
            'method':profile['omission'],'target_tie_semantics':profile['target_ties'],'interpretation':profile['interpretation'],
            'scope':profile['scope'],'timing':profile['timing'],'non_claims':profile['non_claims'],**result}
    return report,rows

def main():
    parser=argparse.ArgumentParser()
    for flag in ('csv','frozen11','identities','source-root','output'): parser.add_argument('--'+flag,required=True,type=Path)
    args=parser.parse_args(); output=args.output.resolve()
    input_roots=(args.csv.parent,args.frozen11.parent,args.identities.parent,args.source_root)
    require(not output.exists() and not output.is_relative_to(REPO) and not REPO.is_relative_to(output) and
            all(not output.is_relative_to(path.resolve()) and not path.resolve().is_relative_to(output) for path in input_roots),
            'Fresh private output outside repository and retained inputs required')
    report,rows=run(args.csv,args.frozen11,args.identities,args.source_root)
    output.mkdir()
    for name,value in [('report.json',report),('private-selected-annotations.json',rows)]:
        with (output/name).open('xb') as stream: stream.write(canonical(value))
    print(json.dumps({'report_sha256':sha(canonical(report)),'rows':len(report['rows']),
                      'paired_contrasts':len(report['paired_contrasts']),'field_accounting':report['field_accounting']}))

if __name__=='__main__': main()
