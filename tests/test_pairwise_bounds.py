from copy import deepcopy
from fractions import Fraction
from itertools import product

import pytest

from hbqrs.core import HBQError
from hbqrs.pairwise_bounds import pairwise_agreement_bounds


def test_bounds_contain_actual_completions_and_preserve_exact_references():
    rows = [
        {'id': 'a', 'group': 'x', 'reference': Fraction(2**54 + 1, 2**54), 'score': 0},
        {'id': 'b', 'group': 'x', 'reference': 1.0, 'score': 1},
        {'id': 'c', 'group': 'x', 'reference': 2, 'score': None},
        {'id': 'd', 'group': 'y', 'reference': None, 'score': 3},
    ]
    before = deepcopy(rows)
    bound = pairwise_agreement_bounds(rows, within_groups=True)
    assert bound['eligible_pairs'] == 3 and bound['observed_discordant'] == 1
    assert bound['unresolved_score_pairs'] == 2 and bound['reference_ties'] == 0
    for (score,) in product((0, 1, 2, 3), repeat=1):
        completed = deepcopy(rows)
        completed[2]['score'] = score
        exact = pairwise_agreement_bounds(completed, within_groups=True)
        assert exact['lower'] == exact['upper']
        assert bound['lower'] <= exact['lower'] <= bound['upper']
    assert pairwise_agreement_bounds(rows)['missing_reference_pairs'] == 3
    assert rows == before


def test_ties_empty_and_invalid_input():
    rows = [{'id': 'a', 'group': 'x', 'reference': 1, 'score': 4},
            {'id': 'b', 'group': 'x', 'reference': 2, 'score': 4}]
    tied = pairwise_agreement_bounds(rows)
    assert tied['lower'] == tied['upper'] == 0.5 and tied['observed_score_ties'] == 1
    rows[1]['reference'] = 1
    assert pairwise_agreement_bounds(rows)['lower'] is None
    rows[1]['id'] = 'a'
    with pytest.raises(HBQError, match='unique'):
        pairwise_agreement_bounds(rows)
    rows[1]['id'], rows[1]['reference'] = 'b', float('nan')
    with pytest.raises(HBQError, match='finite'):
        pairwise_agreement_bounds(rows)
