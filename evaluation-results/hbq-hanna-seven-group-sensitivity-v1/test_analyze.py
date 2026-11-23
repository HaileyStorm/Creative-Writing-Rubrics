from decimal import Decimal

import pytest

from analyze import paired


def test_paired_counts_and_leave_one_group_out():
    a = {'a': Decimal('2'), 'b': Decimal('2'), 'c': Decimal('2')}
    b = {'c': Decimal('2'), 'a': Decimal('1'), 'b': Decimal('3')}
    result = paired(a, b)
    assert (result['lower_error'], result['higher_error'], result['equal_error']) == (1, 1, 1)
    assert result['mean_change'] == '0.000000'
    assert result['leave_one_group_out_mean_change_min'] == '-0.500000'
    assert result['leave_one_group_out_mean_change_max'] == '0.500000'


def test_group_membership_and_invalid_numbers_fail():
    with pytest.raises(ValueError, match='groups differ'):
        paired({'a': Decimal(1), 'b': Decimal(2)}, {'a': Decimal(1), 'c': Decimal(2)})
    with pytest.raises(ValueError, match='invalid group error'):
        paired({'a': Decimal('NaN'), 'b': Decimal(2)}, {'a': Decimal(1), 'b': Decimal(2)})
