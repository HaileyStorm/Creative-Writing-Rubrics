"""Conservative pairwise agreement bounds for explicitly missing scores.

This offline diagnostic does not admit evidence or determine a study protocol.
"""
from __future__ import annotations

from collections import Counter
from fractions import Fraction
from itertools import combinations
import math
from typing import Any

from .core import HBQError


def _valid_number(value: Any) -> bool:
    return type(value) in (int, Fraction) or (type(value) is float and math.isfinite(value))


def pairwise_agreement_bounds(rows: list[dict[str, Any]], *, within_groups: bool = False) -> dict[str, Any]:
    """Bound directional agreement over available, unequal reference pairs.

    Each row has unique nonempty string ``id``, nonempty string ``group``, and
    numeric or null ``reference`` and ``score``. Null score means unresolved;
    null reference excludes its pairs. The caller must independently establish
    the provenance, eligibility, scoring direction and missingness of inputs.
    """
    if type(rows) is not list or type(within_groups) is not bool:
        raise HBQError('rows must be a list and within_groups must be boolean')
    ids: set[str] = set()
    for row in rows:
        if type(row) is not dict or set(row) != {'id', 'group', 'reference', 'score'}:
            raise HBQError('each row must contain id, group, reference and score')
        if type(row['id']) is not str or not row['id'] or row['id'] in ids:
            raise HBQError('row IDs must be unique nonempty strings')
        if type(row['group']) is not str or not row['group']:
            raise HBQError('group must be a nonempty string')
        for field in ('reference', 'score'):
            if row[field] is not None and not _valid_number(row[field]):
                raise HBQError(f'{field} must be a finite number or null')
        ids.add(row['id'])
    counts: Counter[str] = Counter()
    for a, b in combinations(rows, 2):
        if within_groups and a['group'] != b['group']:
            continue
        counts['considered_pairs'] += 1
        if a['reference'] is None or b['reference'] is None:
            counts['missing_reference_pairs'] += 1
        elif a['reference'] == b['reference']:
            counts['reference_ties'] += 1
        elif a['score'] is None or b['score'] is None:
            counts['unresolved_score_pairs'] += 1
        elif a['score'] == b['score']:
            counts['observed_score_ties'] += 1
        elif (a['reference'] > b['reference']) == (a['score'] > b['score']):
            counts['observed_concordant'] += 1
        else:
            counts['observed_discordant'] += 1
    eligible = (counts['unresolved_score_pairs'] + counts['observed_score_ties'] +
                counts['observed_concordant'] + counts['observed_discordant'])
    credit_twice = 2 * counts['observed_concordant'] + counts['observed_score_ties']
    return {
        'policy': 'reference_conditioned_pairwise_outer_bounds_v1',
        'within_groups': within_groups,
        'considered_pairs': counts['considered_pairs'],
        'missing_reference_pairs': counts['missing_reference_pairs'],
        'reference_ties': counts['reference_ties'],
        'eligible_pairs': eligible,
        'observed_concordant': counts['observed_concordant'],
        'observed_discordant': counts['observed_discordant'],
        'observed_score_ties': counts['observed_score_ties'],
        'unresolved_score_pairs': counts['unresolved_score_pairs'],
        'observed_credit_twice': credit_twice,
        'lower': float(Fraction(credit_twice, 2 * eligible)) if eligible else None,
        'upper': float(Fraction(credit_twice + 2 * counts['unresolved_score_pairs'], 2 * eligible)) if eligible else None,
    }
