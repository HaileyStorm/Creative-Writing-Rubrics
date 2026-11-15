"""Partial correlations of globally midranked HF32 variables, adjusting length."""
import argparse
import hashlib
import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
INPUT_CANONICAL_SHA = '65eee601772e6fd3d949611a8200a7f2c0ba6a2cd1217597a0592d2dda9c5e72'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path,
                        default=HERE.parent / 'hbq-hf32-length-baseline-v1' / 'aggregate.json')
    args = parser.parse_args()
    source = json.loads(args.input.read_text(encoding='utf-8-sig'))
    canonical = json.dumps(source, sort_keys=True, separators=(',', ':'),
                           ensure_ascii=False, allow_nan=False).encode('utf-8')
    if hashlib.sha256(canonical).hexdigest() != INPUT_CANONICAL_SHA:
        raise ValueError('baseline aggregate differs')
    results = {}
    for axis, row in source['matched_results'].items():
        if axis not in ('expert', 'reader') or row['matched_works'] != 19:
            raise ValueError('reference axis differs')
        length_reference = row['spearman_length_reference']
        out = {'matched_works': 19, 'length_reference_spearman': length_reference}
        for arm in ('hbq', 'ttcw'):
            raw_r = row['spearman_' + arm + '_reference']
            arm_length = row['spearman_length_' + arm]
            denominator = math.sqrt((1 - arm_length * arm_length) * (1 - length_reference * length_reference))
            if not denominator:
                raise ValueError('constant rank residual')
            out[arm] = {'unadjusted_spearman': raw_r,
                        'length_adjusted_rank_correlation': (raw_r - arm_length * length_reference) / denominator}
        results[axis] = out
    if set(results) != {'expert', 'reader'}:
        raise ValueError('reference axes incomplete')
    print(json.dumps({'state': 'HF32_POST_RESULT_LENGTH_ADJUSTED_RANK_SENSITIVITY',
                      'baseline_aggregate_canonical_sha256': INPUT_CANONICAL_SHA, 'axes': results,
                      'method': 'Pearson correlations between midranks, residualizing score and reference ranks linearly on an intercept and word-count rank',
                      'provider_calls': 0, 'new_human_labels': 0,
                      'limits': ['Post-result selected development cohorts; expert and reader axes are distinct.',
                                 'Rank residualization is not within-length Spearman and does not identify causal effects or eliminate all confounding.',
                                 'Works and raters may be dependent; no confidence interval, method-superiority or promotion claim follows.']},
                     indent=2, sort_keys=True, allow_nan=False))


if __name__ == '__main__':
    main()
