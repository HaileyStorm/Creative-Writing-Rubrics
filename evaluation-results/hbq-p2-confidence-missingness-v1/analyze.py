"""Conservative missing-state sensitivity of a retained P2 aggregate."""
from __future__ import annotations

import argparse
from fractions import Fraction
import hashlib
import json
from pathlib import Path

SOURCE_SHA256 = '8fb7c1a4ad3327b6bdee7958df8ad46ed39780f4bd4c88fa315d6d531732d522'
LOW = '[0.75,0.9)'
HIGH = '[0.9,1]'


def envelope(low_flips: int, low_n: int, high_flips: int, high_n: int, missing: int):
    """Exact relaxed extrema for low minus high binary flip rates.

    Each missing item may be omitted or enter either bin as a flip or nonflip.
    This deliberately ignores constraints from the retained later states.
    """
    if (any(type(v) is not int for v in (low_flips, low_n, high_flips, high_n, missing))
            or low_n <= 0 or high_n <= 0 or missing < 0
            or not 0 <= low_flips <= low_n or not 0 <= high_flips <= high_n):
        raise ValueError('invalid binary counts')
    minima, maxima = [], []
    for low_added in range(missing + 1):
        for high_added in range(missing - low_added + 1):
            minima.append(Fraction(low_flips, low_n + low_added)
                          - Fraction(high_flips + high_added, high_n + high_added))
            maxima.append(Fraction(low_flips + low_added, low_n + low_added)
                          - Fraction(high_flips, high_n + high_added))
    return min(minima), max(maxima)


def fraction(value: Fraction):
    return {'numerator': value.numerator, 'denominator': value.denominator}


def project(raw: bytes):
    if hashlib.sha256(raw).hexdigest() != SOURCE_SHA256:
        raise ValueError('source aggregate hash mismatch')
    data = json.loads(raw)
    if data['stories'] != 3 or data['confidence_bins_exclude_missing_predictor'] is not True:
        raise ValueError('unexpected source cohort or confidence policy')
    results = []
    for row in data['by_horizon']:
        counts = row['all_pairs']['counts']
        if (counts['planned_pairs'], counts['observed_pairs'], counts['missing_cycle0_only'],
                counts['missing_repeat_only'], counts['both_missing']) != (534, 510, 24, 0, 0):
            raise ValueError('unexpected observed or missing cohort')
        bins = {entry['bin']: entry['binary_flip_rate'] for entry in row['confidence_bins']}
        low, high = bins[LOW], bins[HIGH]
        lf, ln = low['numerator'], low['denominator']
        hf, hn = high['numerator'], high['denominator']
        if (ln, hn, lf + hf) != (126, 332, counts['binary_flips']):
            raise ValueError('unexpected binary denominators or flip totals')
        minimum, maximum = envelope(lf, ln, hf, hn, 24)
        results.append({
            'repeat_cycle': row['repeat_cycle'],
            'low_bin': {'flips': lf, 'binary_pairs': ln},
            'high_bin': {'flips': hf, 'binary_pairs': hn},
            'observed_low_minus_high': fraction(Fraction(lf, ln) - Fraction(hf, hn)),
            'relaxed_lower_bound': fraction(minimum),
            'relaxed_upper_bound': fraction(maximum),
        })
    if sorted(x['repeat_cycle'] for x in results) != [1, 2]:
        raise ValueError('unexpected repeat cycles')
    return {
        'schema': 'p2-confidence-missingness-v1', 'source_aggregate_sha256': SOURCE_SHA256,
        'stories': 3, 'planned_pairs_per_horizon': 534, 'missing_first_cycle_states': 24,
        'lower_confidence_bin': LOW, 'higher_confidence_bin': HIGH,
        'bounds': 'relaxed per-horizon allocation; exact rational difference in flip rates',
        'same_missing_states_across_horizons': True, 'results': results,
        'source_to_aggregate_independent_recount_established': False,
        'new_model_or_provider_calls': 0, 'new_human_labels': 0,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path, help='Exact private retained aggregate')
    args = parser.parse_args()
    print(json.dumps(project(args.source.read_bytes()), sort_keys=True, indent=2, allow_nan=False))


if __name__ == '__main__':
    main()
