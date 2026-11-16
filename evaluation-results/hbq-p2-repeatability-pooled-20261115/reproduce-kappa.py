"""Recompute pooled P2 kappa summaries from one private derived projection.

The input is not published. This script checks its byte commitment, recomputes
agreement and unweighted Cohen kappa from its matrices, and emits pooled
summary counts only. It does not regenerate the projection from native records.
"""
import argparse
from fractions import Fraction
import hashlib
import json
from pathlib import Path

SOURCE_SHA256 = '3a9da5d6b53e519111087b8a44ffd799b0091aac60416a7f7da1dc952b6bc999'
STATES = ['YES', 'NO', 'NOT_APPLICABLE', 'CANNOT_ASSESS']


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def calculate(record):
    matrix = record['confusion_matrix']
    require(type(matrix) is list and len(matrix) == 4 and
            all(type(row) is list and len(row) == 4 and
                all(type(x) is int and x >= 0 for x in row) for row in matrix), 'matrix shape differs')
    n = sum(map(sum, matrix))
    diagonal = sum(matrix[i][i] for i in range(4))
    rows = [sum(row) for row in matrix]
    cols = [sum(row[i] for row in matrix) for i in range(4)]
    expected_numerator = sum(a * b for a, b in zip(rows, cols))
    denominator = n * n - expected_numerator
    kappa = Fraction(n * diagonal - expected_numerator, denominator) if denominator else None
    exact = None if kappa is None else [kappa.numerator, kappa.denominator]
    require((n, diagonal, exact) == (record['pairs'], record['agreements'], record['cohen_kappa_exact']),
            'matrix and saved summary differ')
    return {'pairs': n, 'agreements': diagonal, 'cohen_kappa_exact': exact}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True, help='retained private derived projection')
    raw = parser.parse_args().input.read_bytes()
    require(hashlib.sha256(raw).hexdigest() == SOURCE_SHA256, 'private projection digest differs')
    source = json.loads(raw)
    require(source['state_order'] == STATES, 'state order differs')
    require(set(source['groups']) == {'0-1', '0-2', '1-2', 'pooled'}, 'cycle groups differ')
    groups = {}
    for label in ('0-1', '0-2', '1-2', 'pooled'):
        original = source['groups'][label]
        require(set(original) == {'all_four_states', 'excluding_cannot_assess'}, 'inclusion rules differ')
        groups[label] = {name: calculate(original[name]) for name in ('all_four_states', 'excluding_cannot_assess')}
        full, excluded = original['all_four_states']['confusion_matrix'], original['excluding_cannot_assess']['confusion_matrix']
        require(all(excluded[i][j] == (full[i][j] if i != 3 and j != 3 else 0)
                    for i in range(4) for j in range(4)), 'exclusion matrix differs')
    for variant in ('all_four_states', 'excluding_cannot_assess'):
        pooled = source['groups']['pooled'][variant]['confusion_matrix']
        require(all(pooled[i][j] == sum(source['groups'][cycle][variant]['confusion_matrix'][i][j]
                                        for cycle in ('0-1', '0-2', '1-2'))
                    for i in range(4) for j in range(4)), 'pooled matrix differs')
    print(json.dumps({'study': 'selected-p2-short-story-hbq-repeatability-kappa',
                      'private_projection_sha256': SOURCE_SHA256, 'groups': groups},
                     sort_keys=True, indent=2, allow_nan=False))


if __name__ == '__main__':
    main()
