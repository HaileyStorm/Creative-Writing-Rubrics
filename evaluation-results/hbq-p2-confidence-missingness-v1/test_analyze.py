import importlib.util
from fractions import Fraction
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('p2_missingness', Path(__file__).with_name('analyze.py'))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

def test_small_case_enumerates_missing_assignments():
    # Enumerate the status of each missing item, independently of the analysis algorithm.
    from itertools import product
    differences = []
    for choices in product(('omit', 'low_same', 'low_flip', 'high_same', 'high_flip'), repeat=2):
        low_added = sum(x.startswith('low_') for x in choices)
        high_added = sum(x.startswith('high_') for x in choices)
        differences.append(Fraction(1 + choices.count('low_flip'), 2 + low_added)
                           - Fraction(choices.count('high_flip'), 2 + high_added))
    assert module.envelope(1, 2, 0, 2, 2) == (min(differences), max(differences))

def test_real_count_bounds_and_source_pin():
    assert module.envelope(18, 126, 5, 332, 24)[0] == Fraction(153, 2492)
    assert module.envelope(16, 126, 8, 332, 24)[0] == Fraction(208, 5607)
    with pytest.raises(ValueError, match='hash mismatch'):
        module.project(b'{}')
