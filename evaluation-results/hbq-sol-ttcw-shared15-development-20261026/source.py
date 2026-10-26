"""Export aggregate-only interim results from three exact saved private inputs.

This consumer copies existing associations; it does not join the live journal,
read reference labels, score banks, recompute correlations or contact a model.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

PINS = {
    'joined': 'c249ff84ef4debfd40052daa9a21e851f1324023268276d2140e5a32698bd50f',
    'profiles': '2d9fe47ce2acfae924bef63134e894b1654dc3de779bf3b6c20b5ffc000c32d2',
    'analysis': '6e43a8b0b22c43a2fdf3cc58a38d74b442c8d66089e7d5dfe8c9bea304cff795',
}
ARMS = ('hbq', 'ttcw14', 'oregon', 'holistic', 'compact')


def checked(path, pin):
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != pin:
        raise ValueError('Saved input differs: ' + path.name)
    return json.loads(raw)


def export(joined, profiles, analysis):
    shared = set(analysis['private_paired_ids']['all_five'])
    if len(shared) != 15 or profiles['saved_result_summary'] != joined['summary'] or analysis['saved_result_summary'] != joined['summary']:
        raise ValueError('Saved view binding differs')
    summary = joined['summary']
    if summary['total_accepted'] != 568 or summary['producer_total_accepted'] != 567 or summary['same_attempt_recovered_count'] != 1:
        raise ValueError('Saved acceptance counts differ')
    rows = {(r['arm'], r['story_id']): r for r in profiles['profiles']}
    methods = {}
    for arm in ARMS:
        pair = analysis['paired_method_comparisons']['hbq__' + ('ttcw14' if arm == 'hbq' else arm)]
        key = 'hbq__' + ('ttcw14' if arm == 'hbq' else arm)
        if set(analysis['private_paired_ids']['method_comparisons'][key]) != shared:
            raise ValueError('Matched membership differs')
        values = [rows[arm, story]['score'] for story in sorted(shared)]
        counts = Counter(values)
        bounds = profiles['summary']['arms'][arm]['distribution']['native_range']
        methods[arm] = {
            'works': len(values),
            'rho_vs_expert_reference': pair['left_rho_same_works'] if arm == 'hbq' else pair['right_rho_same_works'],
            'undefined_reason': 'Constant score vector on the matched works' if len(counts) == 1 else None,
            'native_range': bounds,
            'minimum': min(values), 'maximum': max(values),
            'distinct_scores': len(counts),
            'tied_unordered_pairs': sum(n * (n - 1) // 2 for n in counts.values()),
            'exact_floor_count': sum(v == bounds[0] for v in values),
            'exact_ceiling_count': sum(v == bounds[1] for v in values),
        }
    return {
        'schema_version': 1,
        'state': 'INCOMPLETE_AVAILABILITY_SELECTED_DEVELOPMENT',
        'private_input_sha256': PINS,
        'fixed_snapshot': {
            'producer_accepted': 567, 'separate_same_attempt_saved_recovery': 1,
            'total_distinct_accepted': 568, 'unchanged_parent_records': 328,
            'profile_grid_rows': len(profiles['profiles']),
            'continuation_attempted': len(summary['new_attempted_ordinals']),
            'continuation_unresolved': len(summary['new_unresolved_ordinals']),
            'continuation_unattempted': len(summary['remaining_unattempted_ordinals']),
            'complete_hbq_banks_scored': profiles['summary']['full_hbq_banks_submitted_to_frozen_scoring_path'],
            'original_failed_no_resend_record_preserved': summary['original_producer_stopped_no_resend_preserved'],
            'collector_stopped_for_snapshot': False,
        },
        'coverage': {
            'planned_works': 36, 'planned_plot_groups': 12,
            'numeric_works_by_method': {arm: profiles['summary']['arms'][arm]['numeric_works'] for arm in ARMS},
            'all_five_shared_numeric_works': 15,
            'shared_plot_groups': analysis['methods']['hbq']['represented_plot_clusters'],
            'works_without_all_five_numeric_scores': 21,
            'original_required_shared_numeric_works': 33,
            'registered_primary_coverage_met': analysis['registered_primary_coverage_met'],
        },
        'same_fifteen_works': methods,
        'hbq_minus_comparator_rho_same_fifteen_works': {
            arm: analysis['paired_method_comparisons']['hbq__' + arm]['delta_rho'] for arm in ARMS if arm != 'hbq'
        },
        'uncertainty': {
            'state': 'INCONCLUSIVE_UNDER_MISSINGNESS',
            'bootstrap_draws': analysis['resampling']['executed_calls'],
            'confidence_intervals_estimated': False,
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
    inputs = {name: checked(getattr(args, name), pin) for name, pin in PINS.items()}
    payload = export(**inputs)
    raw = (json.dumps(payload, sort_keys=True, indent=2, allow_nan=False) + '\n').encode()
    with args.output.open('xb') as stream:
        stream.write(raw)
    print(json.dumps({'state': payload['state'], 'sha256': hashlib.sha256(raw).hexdigest()}))


if __name__ == '__main__':
    main()
