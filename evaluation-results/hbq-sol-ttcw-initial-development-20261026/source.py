"""Export aggregates from exact saved development inputs, without rescoring.

No native replay, reference-label read, correlation/bootstrap rerun or provider call.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

PINS = {
    'joined': 'cbf6192a025521990b17cb3c3f4d2c56e9443eb0ac3084a85eba8fcee9be96f4',
    'profiles': 'f1ac953b99bbddd96272eb9555e60eb80c9de6d5d30861e2ad7dd2e6fbecd388',
    'analysis': '230b9391bc060d375b529cd715f5442424d70f46ba3e27d3ff5292690366f903',
    'condition': '219d1388e13bd796d13b93a7511ed7ee55d0cf120479783debf022a622d83dde',
    'operations': '187fc5e2947470f93af8d5d242c2719e07c4d1307dc1bc39a777c5cb9dd00090',
}
ARMS = ('hbq', 'ttcw14', 'holistic', 'compact', 'oregon')


def checked(path, pin):
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != pin:
        raise ValueError('Saved input differs: ' + path.name)
    return json.loads(raw)


def export(joined, profiles, analysis, condition, operations):
    summary = joined['summary']
    shared = set(analysis['private_paired_ids']['all_five'])
    if (len(shared) != 28 or summary['total_accepted'] != 1035
            or summary['producer_total_accepted'] != 1034
            or summary['same_attempt_recovered_count'] != 1
            or len(summary['new_attempted_ordinals']) != 711
            or summary['new_unresolved_ordinals'] or summary['remaining_unattempted_ordinals']
            or profiles['saved_result_summary'] != summary
            or analysis['saved_result_summary'] != summary):
        raise ValueError('Saved completion/view binding differs')
    groups = {r['id']: r['plot'] for r in condition['cohort']}
    if len({groups[s] for s in shared}) != 12 or operations['fixed_view_sha256'] != PINS['joined']:
        raise ValueError('Cohort or operations binding differs')
    rows = {(r['arm'], r['story_id']): r for r in profiles['profiles']}
    matched_distributions = {}
    for arm in ARMS:
        values = [rows[arm, story]['score'] for story in sorted(shared)]
        counts = Counter(values)
        bounds = profiles['summary']['arms'][arm]['distribution']['native_range']
        matched_distributions[arm] = {
            'works': len(values), 'native_range': bounds,
            'minimum': min(values), 'maximum': max(values),
            'distinct_scores': len(counts),
            'tied_unordered_pairs': sum(n * (n - 1) // 2 for n in counts.values()),
            'exact_floor_count': sum(v == bounds[0] for v in values),
            'exact_ceiling_count': sum(v == bounds[1] for v in values),
        }
    pairs = {}
    for arm in ARMS[1:]:
        key = 'hbq__' + arm
        pair = analysis['paired_method_comparisons'][key]
        if len(analysis['private_paired_ids']['method_comparisons'][key]) != pair['works']:
            raise ValueError('Pair-specific denominator differs')
        pairs[arm] = pair
    # Only HBQ–TTCW uses exactly the all-five subset. Other correlations retain
    # their own explicit pair-specific denominator; none is relabeled as 28.
    if set(analysis['private_paired_ids']['method_comparisons']['hbq__ttcw14']) != shared:
        raise ValueError('HBQ–TTCW membership differs')
    return {
        'schema_version': 1,
        'state': 'INITIAL_COLLECTION_COMPLETE_DESCRIPTIVE_DEVELOPMENT',
        'private_input_sha256': PINS,
        'fixed_snapshot': {
            'producer_accepted': 1034, 'separate_same_attempt_saved_recovery': 1,
            'total_distinct_accepted': 1035, 'unchanged_parent_records': 328,
            'continuation_attempted': 711, 'continuation_unresolved': 0,
            'continuation_unattempted': 0,
            'continuation_semantic_rejects_retained_no_resend': 4,
            'parent_nonadmitted_retained_no_resend': 5,
            'complete_hbq_banks_scored': 29, 'profile_grid_rows': 180,
            'original_failed_no_resend_record_preserved': summary['original_producer_stopped_no_resend_preserved'],
        },
        'coverage': {
            'planned_works': 36, 'planned_plot_groups': 12,
            'numeric_works_by_method': {arm: profiles['summary']['arms'][arm]['numeric_works'] for arm in ARMS},
            'all_five_shared_numeric_works': 28, 'all_five_shared_plot_groups': 12,
            'works_without_all_five_numeric_scores': 8,
            'original_required_shared_numeric_works': 33,
            'registered_primary_coverage_met': analysis['registered_primary_coverage_met'],
        },
        'same_28_score_distributions': matched_distributions,
        'hbq_pair_specific_associations': pairs,
        'other_pair_specific_associations': {k: v for k, v in analysis['paired_method_comparisons'].items() if not k.startswith('hbq__')},
        'available_method_results_different_denominators': analysis['methods'],
        'pairwise_expert_derived_agreement': analysis['pairwise_expert_derived_agreement'],
        'ttcw14_expert_test_agreement': analysis['ttcw14_expert_test_agreement'],
        'accepted_request_operations': {k: operations[k] for k in ('accepted_requests', 'all_accepted', 'by_arm', 'limits')},
        'uncertainty': {
            'bootstrap_calls_executed': analysis['resampling']['executed_calls'],
            'bootstrap_calls_suppressed': analysis['resampling']['suppressed_calls'],
            'rules': 'Frozen per-statistic 33-work/12-plot or assessed-pair/cell coverage rules; undefined draws are not redrawn.',
            'hbq_method_comparison_intervals_estimated': False,
            'population_or_method_superiority_inference_supported': False,
        },
        'scope': {
            'already_opened_development_reference_used': analysis['already_opened_development_reference_read'],
            'unused_confirmation_used': analysis['unused_confirmation'],
            'new_human_labels': analysis['new_human_labels'],
            'candidate_promoted': analysis['candidate_promoted'],
            'full_goal_complete': analysis['full_goal_complete'],
            'export_provider_calls': 0, 'export_scorer_calls': 0,
            'export_correlations_recomputed': False,
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in (*PINS, 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    payload = export(**{name: checked(getattr(args, name), pin) for name, pin in PINS.items()})
    raw = (json.dumps(payload, sort_keys=True, indent=2, allow_nan=False) + '\n').encode()
    with args.output.open('xb') as stream:
        stream.write(raw)
    print(json.dumps({'state': payload['state'], 'sha256': hashlib.sha256(raw).hexdigest()}))


if __name__ == '__main__':
    main()
