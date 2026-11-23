"""Analyze pairwise rank agreement in the exposed EduPo score table."""
from __future__ import annotations

import argparse
import csv
from decimal import Decimal, InvalidOperation
import hashlib
import io
import json
import math
from collections import Counter
from itertools import combinations
from pathlib import Path

SOURCE_SHA256 = 'f438b60c4fe1ad6aee1eba09400b10387cc55ea889720a7e36a40ba443572eb2'
SOURCE_GIT = 'a196f9124590f9dbf144ed86746045b80713b22a'
DIMENSIONS = {'semantics': ('Human-Semantics', 'ChatGPT-Semantics'),
              'syntax': ('Human-Syntax', 'ChatGPT-Syntax'),
              'rhyming': ('Human-Rhyming', 'ChatGPT-Rhyming'),
              'metre': ('Human-Metre', 'ChatGPT-Metre')}


def pair_counts(pairs):
    counts = dict.fromkeys(('concordant', 'discordant', 'human_tie_only',
                            'model_tie_only', 'both_tied'), 0)
    for (h1, m1), (h2, m2) in pairs:
        h = (h1 > h2) - (h1 < h2)
        m = (m1 > m2) - (m1 < m2)
        key = ('both_tied' if not h and not m else 'human_tie_only' if not h else
               'model_tie_only' if not m else 'concordant' if h == m else 'discordant')
        counts[key] += 1
    c, d, ht, mt = (counts[k] for k in ('concordant', 'discordant', 'human_tie_only', 'model_tie_only'))
    den = math.sqrt((c + d + ht) * (c + d + mt))
    return {**counts, 'pairs': sum(counts.values()),
            'kendall_tau_b': (c - d) / den if den else None,
            'agreement_when_both_strict': c / (c + d) if c + d else None}


def analyze(raw: bytes):
    if hashlib.sha256(raw).hexdigest() != SOURCE_SHA256:
        raise ValueError('source SHA-256 mismatch')
    blob = hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()
    if blob != SOURCE_GIT:
        raise ValueError('source Git blob mismatch')
    reader = csv.DictReader(io.StringIO(raw.decode('utf-8'), newline=''), delimiter='\t', strict=True)
    if not reader.fieldnames or len(reader.fieldnames) != 18 or len(set(reader.fieldnames)) != 18:
        raise ValueError('unexpected columns')
    records = list(reader)
    if len(records) != 100 or any(None in row or None in row.values() for row in records):
        raise ValueError('unexpected row count or shape')
    if len({row['filename'] for row in records}) != 100:
        raise ValueError('duplicate filenames')
    groups = Counter(row['system'] for row in records)
    if len(groups) != 5 or sorted(groups.values()) != [20] * 5:
        raise ValueError('unexpected source groups')
    output = {}
    for dimension, (human_col, model_col) in DIMENSIONS.items():
        try:
            values = [(row['system'], Decimal(row[human_col]), Decimal(row[model_col])) for row in records]
        except (InvalidOperation, KeyError) as exc:
            raise ValueError('invalid score') from exc
        if any(not h.is_finite() or not m.is_finite() or not 0 <= h <= 10 or not 0 <= m <= 1
               for _, h, m in values):
            raise ValueError('score outside stated ranges')
        all_pairs = list(combinations(values, 2))
        select = lambda ps: [((a[1], a[2]), (b[1], b[2])) for a, b in ps]
        same = [(a, b) for a, b in all_pairs if a[0] == b[0]]
        cross = [(a, b) for a, b in all_pairs if a[0] != b[0]]
        output[dimension] = {
            'n': len(values),
            'human_at_min_0': sum(h == 0 for _, h, _ in values),
            'human_at_max_10': sum(h == 10 for _, h, _ in values),
            'model_at_min_0': sum(m == 0 for _, _, m in values),
            'model_at_max_1': sum(m == 1 for _, _, m in values),
            'human_distinct_scores': len({h for _, h, _ in values}),
            'model_distinct_scores': len({m for _, _, m in values}),
            'all_pairs': pair_counts(select(all_pairs)),
            'within_source_groups': pair_counts(select(same)),
            'between_source_groups': pair_counts(select(cross)),
            'per_source_group': {group: pair_counts(select([(a, b) for a, b in same if a[0] == group]))
                                 for group in sorted(groups)},
        }
    return {'schema': 'edupo-exposed-pairrank-v1', 'source_sha256': SOURCE_SHA256,
            'source_git_blob': SOURCE_GIT, 'rows': len(records), 'group_sizes': dict(sorted(groups.items())),
            'dimensions': output}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('table', type=Path)
    args = parser.parse_args()
    print(json.dumps(analyze(args.table.read_bytes()), sort_keys=True, indent=2, allow_nan=False))


if __name__ == '__main__':
    main()
