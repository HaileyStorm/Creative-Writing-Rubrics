"""Project exact reviewed aggregates into the concise supplement; no scientific recomputation."""
import argparse
import hashlib
import json
from pathlib import Path

PINS={'ttcw_repeat':'2d17e51f0c79e1058f65ba79c44a02f3134a6443d29440e7ac6cf64cf0b118bd',
      'poetry_order':'e19a2fbca91ff574f2c7a36ed2b54fd2dbbfd86ddbad74bd85fdb36f632f8a05',
      'ttcw_partial':'743aa2e79d33a4acde2f818db7faccf46ff7cbde4eb7619fa013b026cd52c823',
      'dryad_influence':'d56438f6fd3d0edc23930dbb115ae78a93a91e8e465b5d5d121710487aaccd3b'}
def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package-dir',type=Path,default=Path(__file__).resolve().parent)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists(): raise ValueError('Create-only output file')
    data={}; originals={}
    for name,pin in PINS.items():
        path=args.package_dir/'reviewed_aggregates'/f'{name}.json'
        raw=path.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=pin: raise ValueError('Reviewed aggregate pin mismatch')
        originals[path]=raw; data[name]=json.loads(raw)
    repeat=data['ttcw_repeat']; poetry=data['poetry_order']; partial=data['ttcw_partial']; dryad=data['dryad_influence']
    report={'state':'DESCRIPTIVE_OFFLINE_FOUR_DIAGNOSTIC_SUPPLEMENT',
        'ttcw_repeat':{'work_pairs':2,'leaf_pairs':356,'changes_by_anonymous_bank':[x['state_changes'] for x in repeat['banks']],
            'question_recurrence':repeat['question_recurrence'],'state_conditioned_exact_evidence':repeat['combined']['strata']},
        'poetry_scalar_order':{'families':poetry['families'],'variants_per_family':poetry['variants_per_family'],
            'cycles':poetry['cycles'],'arms':{name:item['overall'] for name,item in poetry['arms'].items()}},
        'ttcw_partial_rank':{'formula':partial['formula'],'cohorts':{name:{'role':item['role'],'works':item['works'],
            'unadjusted_rho':item['saved_HBQ_expert_rho'],
            'single_controls':{control:value['approximate_value'] for control,value in item['single_controls'].items()}}
            for name,item in partial['cohorts'].items()}},
        'dryad_delete_one':{'axes':{name:{key:item[key] for key in ('baseline_stories','stories_each_deletion','baseline_rho','planned_deletions','defined_deletions','undefined_deletions','minimum_delete_one_rho','maximum_delete_one_rho','maximum_absolute_shift','coefficient_sign_counts')} for name,item in dryad['axes'].items()}},
        'reviewed_aggregate_sha256':PINS,
        'limits':{'ttcw_repeat':repeat['limits'],'poetry_scalar_order':poetry['limits'],'ttcw_partial_rank':partial['limits'],'dryad_delete_one':dryad['limits']},
        'candidate_promoted':False,'human_validity_established':False,'prospective_validation_established':False,
        'new_provider_calls':0,'new_human_labels':0,'projection_is_scientific_recomputation':False}
    encoded=(json.dumps(report,indent=2,sort_keys=True,allow_nan=False)+'\n').encode()
    for path,raw in originals.items():
        if path.read_bytes()!=raw: raise ValueError('Input changed during projection')
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open('xb') as handle: handle.write(encoded)
    print(json.dumps({'state':'AGGREGATE_PROJECTION_COMPLETE','bytes':len(encoded),'sha256':hashlib.sha256(encoded).hexdigest()},sort_keys=True))
if __name__=='__main__': main()
