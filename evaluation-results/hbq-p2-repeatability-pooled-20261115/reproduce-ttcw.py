"""Reproduce pooled TTCW adaptation summaries from private derived projections.

The two inputs remain private. This verifies their digests, recalculates
agreement and kappa from pooled matrices, and checks summary consistency; it
does not regenerate raw-to-derived provenance or emit individual identifiers.
"""
import argparse
from fractions import Fraction
import hashlib
import json
from pathlib import Path

PINS = {
    'scores': '7bdf5acefceca48cde78770f5a99b906bf987461665f152ce2f7f7c5bd06ec5a',
    'parity': 'cbf53dfae74be08cfea7aa2ae6401e79aa8512588b0478884d85aad2ae16ad18',
}


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def load(path, digest):
    raw = Path(path).read_bytes()
    require(hashlib.sha256(raw).hexdigest() == digest, 'private projection digest differs')
    result = json.loads(raw)
    require(type(result) is dict, 'projection shape differs')
    return result


def measure(record):
    matrix = record['transition_matrix_yes_no']
    require(type(matrix) is list and len(matrix) == 2 and
            all(type(row) is list and len(row) == 2 and
                all(type(n) is int and n >= 0 for n in row) for row in matrix), 'matrix differs')
    n = sum(map(sum, matrix))
    agree = matrix[0][0] + matrix[1][1]
    chance = sum(sum(matrix[i]) * sum(row[i] for row in matrix) for i in range(2))
    denominator = n * n - chance
    kappa = Fraction(n * agree - chance, denominator) if denominator else None
    exact = None if kappa is None else [kappa.numerator, kappa.denominator]
    require((n, agree, exact) == (record['pairs'], record['agreements'], record['cohen_kappa_exact']),
            'kappa summary differs')
    return {'pairs': n, 'agreements': agree, 'cohen_kappa_exact': exact}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scores', type=Path, required=True)
    parser.add_argument('--parity', type=Path, required=True)
    args = parser.parse_args()
    source = load(args.scores, PINS['scores'])
    parity = load(args.parity, PINS['parity'])
    require(source['index_sha256'] == parity['index_sha256'] and
            parity['stories_with_matching_source_binding_and_bytes'] == source['stories'] == 3,
            'cross-arm source scope differs')
    require(source['cycles'] == 3 and source['tests_per_bank'] == 14 and source['accepted_banks'] == 9,
            'planned geometry differs')
    records = source['cycle_pair_results']
    require(set(records) == {'0-1', '0-2', '1-2'}, 'cycle groups differ')
    groups = {key: measure(records[key]) for key in ('0-1', '0-2', '1-2')}
    groups['pooled'] = measure(source['pooled_pairs'])
    matrices = [records[key]['transition_matrix_yes_no'] for key in ('0-1', '0-2', '1-2')]
    require(all(source['pooled_pairs']['transition_matrix_yes_no'][i][j] == sum(m[i][j] for m in matrices)
                for i in range(2) for j in range(2)), 'pooled matrix differs')
    score = source['score_summary']
    require(score['native_range'] == [0, 1] and score['paired_score_comparisons'] == 9 and
            sum(score['story_pair_direction_counts'].values()) == 9, 'score summary differs')
    result = {'study': 'selected-p2-short-story-ttcw14-repeatability',
              'method': source['method'], 'stories': source['stories'], 'cycles': source['cycles'],
              'tests_per_bank': source['tests_per_bank'], 'accepted_banks': source['accepted_banks'],
              'cross_arm_matching_source_stories': parity['stories_with_matching_source_binding_and_bytes'],
              'groups': groups, 'score_summary': score,
              'input_projection_sha256': PINS}
    print(json.dumps(result, sort_keys=True, indent=2, allow_nan=False))


if __name__ == '__main__':
    main()
