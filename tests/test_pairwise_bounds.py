from copy import deepcopy
from fractions import Fraction
from itertools import product

import pytest

from hbqrs.core import HBQError
from hbqrs.pairwise_bounds import POLICY_V1, POLICY_V2, pairwise_agreement_bounds


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
        value = Fraction(exact['observed_credit_twice'], 2 * exact['eligible_pairs'])
        assert Fraction.from_float(exact['lower']) <= value <= Fraction.from_float(exact['upper'])
        assert Fraction.from_float(bound['lower']) <= value <= Fraction.from_float(bound['upper'])
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


def test_float_endpoints_do_not_exclude_exact_rational_bounds():
    def pairs(n, concordant, unresolved=0):
        return [
            {'id': f'{i}-{j}', 'group': str(i), 'reference': j,
             'score': None if i >= n - unresolved and j == 1 else
                      j if i < concordant else 1 - j}
            for i in range(n) for j in range(2)
        ]

    for n, concordant, unresolved in ((5, 2, 0), (3, 1, 0), (5, 2, 1)):
        result = pairwise_agreement_bounds(pairs(n, concordant, unresolved), within_groups=True)
        lower = Fraction(concordant, n)
        upper = Fraction(concordant + unresolved, n)
        assert Fraction.from_float(result['lower']) <= lower
        assert Fraction.from_float(result['upper']) >= upper
        assert 0 <= result['lower'] <= result['upper'] <= 1
        assert result['policy'] == POLICY_V2
        historical = pairwise_agreement_bounds(pairs(n, concordant, unresolved), within_groups=True, policy=POLICY_V1)
        assert historical['policy'] == POLICY_V1
        assert historical['lower'] == float(lower) and historical['upper'] == float(upper)
    with pytest.raises(HBQError, match='policy'):
        pairwise_agreement_bounds([], policy=[])
