import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('pairrank', Path(__file__).with_name('analyze.py'))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_ties_are_not_counted_as_agreement():
    pair = lambda x, y: (x, y)
    counts = module.pair_counts([
        pair((1, 1), (2, 2)), pair((1, 2), (2, 1)),
        pair((1, 1), (1, 2)), pair((1, 1), (2, 1)),
        pair((1, 1), (1, 1)),
    ])
    assert [counts[k] for k in ('concordant', 'discordant', 'human_tie_only',
                                 'model_tie_only', 'both_tied')] == [1, 1, 1, 1, 1]
    assert counts['agreement_when_both_strict'] == 0.5
    assert counts['kendall_tau_b'] == 0
    assert module.pair_counts([pair((1, 1), (1, 1))])['kendall_tau_b'] is None


def test_rejects_changed_source_before_analysis():
    with pytest.raises(ValueError, match='SHA-256'):
        module.analyze(b'filename\tsystem\n')
