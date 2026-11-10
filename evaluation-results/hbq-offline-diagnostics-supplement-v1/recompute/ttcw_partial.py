"""Post-hoc single-control partial correlations from pinned saved rank coefficients."""
import argparse
from decimal import Decimal, localcontext
import hashlib
import json
from pathlib import Path
PIN = 'f7a2665ef961cc048947ab780271d709e980ddd19aa5035ab3647e7be893d11b'
COHORTS = (('all_five_28', 28, 'primary'), ('HBQ_numeric_29', 29, 'dependent_secondary'))
CONTROLS = ('lexical_token_count', 'raw_type_token_ratio')

def require(ok, message):
    if not ok:
        raise RuntimeError(message)

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def calculate(report):
    require(report['state'] == 'DESCRIPTIVE_TTCW_SOURCE_CONTROLS_ON_FIXED401', 'Exact saved source state')
    require(report['statistic'].startswith('Equal-story average-tie Spearman'), 'Rank coefficient semantics')
    require(report['unused_confirmation_opened'] is False and report['new_human_labels'] == 0, 'Saved evidence scope')
    results = {}
    for name, n, role in COHORTS:
        cohort = report['cohorts'][name]
        require(cohort['works'] == n and cohort['planned_original_works'] == 36 and (cohort['missing_original_works'] == 36 - n), 'Fixed reported cohort')
        require(cohort['represented_plot_groups'] == 12 and cohort['state'] == 'INCONCLUSIVE_REGISTERED_SHARED33_RULE_UNMET', 'Original selection gate remains unmet')
        method = cohort['method_points']['hbq']
        require(method['available'] == n and method['planned_cohort'] == n and (method['calculation'] == 'exact_membership_cached401'), 'Saved exact-membership HBQ binding')
        xy = cohort['cached_HBQ_expert_rho']
        require(method['rho'] == xy and method['saved_statistic_pointer'] == cohort['cached_HBQ_pointer'], 'Same saved HBQ/expert coefficient')
        values = {}
        for control in CONTROLS:
            feature = cohort['controls'][control]
            require(feature['works'] == n and feature['feature_available'] == n and (feature['undefined_reason'] is None), 'Same complete reported control cohort')
            xz, yz = (feature['rho_with_HBQ_score'], feature['rho_with_expert_mean'])
            require(all((abs(v) < 1 for v in (xy, xz, yz))), 'Finite nondegenerate reported correlations')
            residual_x, residual_y = (1 - xz * xz, 1 - yz * yz)
            denominator = (residual_x * residual_y).sqrt()
            require(denominator > 0, 'Positive partial-rank denominator')
            numerator = xy - xz * yz
            determinant = 1 + 2 * xy * xz * yz - xy * xy - xz * xz - yz * yz
            require(determinant >= 0, 'Reported triple is positive semidefinite')
            partial = numerator / denominator
            require(abs(partial) <= 1, 'Valid reported-coefficient partial correlation')
            values[control] = {'input_coefficients': {'HBQ_expert': str(xy), 'HBQ_control': str(xz), 'expert_control': str(yz)}, 'residual_rank_variance_factors': {'HBQ': str(residual_x), 'expert': str(residual_y)}, 'numerator': str(numerator), 'denominator': str(denominator), 'correlation_matrix_determinant': str(determinant), 'partial_rank_correlation_from_saved_coefficients': str(partial), 'approximate_value': float(partial)}
        constant = cohort['controls']['constant_zero']
        require(constant['rho_with_HBQ_score'] is None and constant['rho_with_expert_mean'] is None and (constant['undefined_reason'] == 'constant_vector'), 'Undefined constant control preserved')
        results[name] = {'role': role, 'works': n, 'reported_plot_groups': 12, 'original_required_shared_works': 33, 'original_shared_work_rule_met': False, 'saved_HBQ_expert_rho': str(xy), 'single_controls': values, 'constant_control_partial': None, 'constant_control_reason': 'Undefined source correlations; constant has no rank variance.'}
    return {'state': 'POST_HOC_PARTIAL_RANK_FROM_SAVED_ROUNDED_COEFFICIENTS', 'cohorts': results, 'formula': '(r_XY-r_XZ*r_YZ)/sqrt((1-r_XZ^2)*(1-r_YZ^2)); X=HBQ ranks, Y=expert-mean ranks, Z=one control rank vector.', 'interpretation': 'Pearson correlation of standardized average-tie rank residuals after one linear rank control at a time; no reranking of residuals.', 'source_commitments': report['source_commitments'], 'source_freeze_sha256': report['freeze_sha256'], 'membership_evidence': 'Reported exact-membership source coefficients and pointers checked; raw individual memberships are not reopened or independently reconstructed.', 'limits': ['Inputs are saved JSON coefficients rounded by the earlier computation; high-precision arithmetic cannot restore lost precision. No raw-rank recomputation.', 'Post-hoc descriptive analysis; primary shared28 and dependent HBQ29 are selected available subsets, not independent replications.', 'Original shared33 rule remains unmet; seven/eight missing works, plot dependence and selection remain.', 'One control at a time; lexical length and raw TTR are related and are not jointly controlled. No nonlinear, latent or plot/condition confounding adjustment.', 'No causal explanation, significance test, confidence interval, human-validity gain or candidate promotion follows.', 'No adjusted competitor correlations are available here; unadjusted method points must not be compared as adjusted competitors.'], 'new_human_labels': 0, 'provider_calls': 0, 'scorer_calls': 0, 'native_replays': 0, 'held_out_target_reads': 0, 'promotion': 'none'}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report',type=Path,required=True)
    parser.add_argument('--output-dir',type=Path,required=True)
    args=parser.parse_args()
    paths={'report':args.report}; originals={'report':args.report.read_bytes()}
    require(len(originals['report'])==9402 and sha(originals['report'])==PIN,'Pinned source-control report')
    with localcontext() as ctx:
        ctx.prec=60
        result=calculate(json.loads(originals['report'],parse_float=Decimal))
    result['input']={'sha256':PIN,'bytes':9402}
    publish(args.output_dir,result,paths,originals)

def publish(directory,result,paths,originals):
    if directory.exists():
        raise ValueError('Use an unused create-only output directory')
    for key,path in paths.items():
        if path.read_bytes()!=originals[key]:
            raise ValueError('Input bytes changed during analysis')
    raw=(json.dumps(result,indent=2,sort_keys=True,ensure_ascii=False,allow_nan=False)+'\n').encode()
    directory.mkdir(parents=True,exist_ok=False)
    with (directory/'aggregate.json').open('xb') as handle: handle.write(raw)
    receipt={'state':'RECOMPUTED_FROM_EXPLICIT_PINNED_INPUTS','aggregate':{'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)},
             'adapter_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
             'inputs':{key:{'sha256':hashlib.sha256(value).hexdigest(),'bytes':len(value)} for key,value in originals.items()},
             'input_bytes_rechecked':True}
    with (directory/'receipt.json').open('x',encoding='utf-8') as handle:
        handle.write(json.dumps(receipt,indent=2,sort_keys=True)+'\n')

if __name__=='__main__':
    main()
