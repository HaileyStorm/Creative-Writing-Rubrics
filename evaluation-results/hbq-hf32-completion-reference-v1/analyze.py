"""Reproduce the aggregate from the two retained private inputs; no network use."""
import argparse
from collections import Counter
import hashlib
from itertools import combinations
import json
import math
from pathlib import Path
SOURCE_SHA = 'e8bfc8cb83c91f4f26c4f901bc0f9fef9e993072b509c175baccafcddaad9fe7'
MANIFEST_SHA = '469806acefd2f4cc92908f6b31e3c5f0afae3b4e8c15b9061892f89293994a0c'

def require(condition, message):
    if not condition:
        raise ValueError(message)

def read_pinned(path, expected):
    data = path.read_bytes()
    require(hashlib.sha256(data).hexdigest() == expected, 'input digest differs')
    return data

def finite(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)

def ranks(values):
    order = sorted(range(len(values)), key=lambda i: values[i])
    result = [None] * len(values)
    start = 0
    while start < len(values):
        end = start + 1
        while end < len(values) and values[order[end]] == values[order[start]]:
            end += 1
        midrank = (start + 1 + end) / 2
        for i in order[start:end]:
            result[i] = midrank
        start = end
    return result

def spearman(x, y):
    if len(x) < 3:
        return None
    a, b = ranks(x), ranks(y)
    am, bm = sum(a) / len(a), sum(b) / len(b)
    numerator = sum((u - am) * (v - bm) for u, v in zip(a, b))
    aa, bb = sum((u - am) ** 2 for u in a), sum((v - bm) ** 2 for v in b)
    return numerator / math.sqrt(aa * bb) if aa and bb else None

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True, type=Path, help='Private frozen HF32 analysis result')
    parser.add_argument('--manifest', required=True, type=Path, help='Private grouped-completion result')
    args = parser.parse_args()
    source = json.loads(read_pinned(args.source, SOURCE_SHA))
    manifest = json.loads(read_pinned(args.manifest, MANIFEST_SHA))
    identities = {hashlib.sha256(k.encode()).hexdigest(): k for k in source['paired_scores']}
    require(len(identities) == 32 and set(source['paired_scores']) == set(source['projected_targets']), 'source identities differ')
    rows = []
    seen = set()
    for case in manifest['results']:
        digest = case['artifact_id_sha256']
        require(digest in identities and digest not in seen, 'case source missing or duplicated')
        seen.add(digest)
        ident = identities[digest]
        arms = source['paired_scores'][ident]
        target = source['projected_targets'][ident]
        e = case['grouped_bounds']
        require(case['saved_bounds']['observed'] == arms['historical']['score'], 'score identity differs')
        require((e['lower'], e['upper']) == (case['saved_bounds']['lower'], case['saved_bounds']['upper']), 'saved interval differs')
        require(arms['candidate']['score'] == arms['historical']['score'], 'candidate differs')
        require(all(target[k] is None or finite(target[k]) for k in ('expert_mean2', 'nonexpert_median')), 'reference nonfinite')
        ttcw = arms['ttcw14']['score']
        require(ttcw is None or finite(ttcw), 'comparator nonfinite')
        rows.append({'hbq': arms['historical']['score'], 'ttcw': ttcw,
                     'expert': target['expert_mean2'], 'reader': target['nonexpert_median'],
                     'bounds': {'lower': e['lower'], 'upper': e['upper']}})
    require(len(rows) == len(manifest['results']) == 27, 'case count differs')
    results = {}
    for axis in ('expert', 'reader'):
        common = [r for r in rows if r[axis] is not None and r['ttcw'] is not None]
        pair_counts = {'disjoint': Counter(), 'overlap_or_touch': Counter()}
        for a, b in combinations(common, 2):
            bound_a, bound_b = a['bounds'], b['bounds']
            stratum = 'disjoint' if bound_a['lower'] > bound_b['upper'] or bound_b['lower'] > bound_a['upper'] else 'overlap_or_touch'
            c = pair_counts[stratum]
            c['pairs'] += 1
            if a[axis] == b[axis]:
                c['reference_tie'] += 1
                continue
            for method in ('hbq', 'ttcw'):
                if a[method] == b[method]:
                    c[method + '_tie'] += 1
                else:
                    c[method + ('_concordant' if (a[method] > b[method]) == (a[axis] > b[axis]) else '_discordant')] += 1
        results[axis] = {'matched_works': len(common),
                         'spearman_hbq': spearman([r['hbq'] for r in common], [r[axis] for r in common]),
                         'spearman_ttcw': spearman([r['ttcw'] for r in common], [r[axis] for r in common]),
                         'pair_counts': {k: dict(v) for k, v in pair_counts.items()}}
    print(json.dumps({'source_sha256': SOURCE_SHA, 'case_manifest_sha256': MANIFEST_SHA,
                      'guarded_envelope_works': 27, 'results': results, 'provider_calls': 0, 'new_human_labels': 0,
                      'limits': ['Post-result complete-case development subset; exact shared cohort within each axis only. Seventeen ranges also have full enumeration; ten rely on guarded grouping and direct witnesses.',
                                 'Expert and reader references measure different constructs; works and raters may be dependent.',
                                 'Intervals are scorer substitutions, not confidence or prediction intervals; pair counts reuse works.',
                                 'No population, causal, method-superiority or candidate-promotion inference follows.']}, sort_keys=True, indent=2, allow_nan=False))

if __name__ == '__main__':
    main()
