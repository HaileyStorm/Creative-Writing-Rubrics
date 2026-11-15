"""Reproduce the aggregate from retained private inputs; no network access."""
import argparse
from collections import Counter
import hashlib
from itertools import combinations
import json
import math
from pathlib import Path

SOURCE_SHA = 'e8bfc8cb83c91f4f26c4f901bc0f9fef9e993072b509c175baccafcddaad9fe7'
REQUEST_MANIFEST_SHA = 'ab4adf5943e0eb12dd5e750e05ea63c5c99cafd3f2ec37c351d4bd05a62e9268'
CASE_MANIFEST_SHA = '469806acefd2f4cc92908f6b31e3c5f0afae3b4e8c15b9061892f89293994a0c'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read_pinned(path, expected, size=None):
    data = path.read_bytes()
    require(hashlib.sha256(data).hexdigest() == expected, 'input digest differs')
    require(size is None or len(data) == size, 'input size differs')
    return data


def finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def ranks(values):
    order = sorted(range(len(values)), key=lambda i: values[i])
    result = [None] * len(values)
    start = 0
    while start < len(values):
        end = start + 1
        while end < len(values) and values[order[end]] == values[order[start]]:
            end += 1
        for index in order[start:end]:
            result[index] = (start + 1 + end) / 2
        start = end
    return result


def spearman(x, y):
    if len(x) < 3:
        return None
    a, b = ranks(x), ranks(y)
    am, bm = sum(a) / len(a), sum(b) / len(b)
    xy = sum((u - am) * (v - bm) for u, v in zip(a, b))
    aa, bb = sum((u - am) ** 2 for u in a), sum((v - bm) ** 2 for v in b)
    return xy / math.sqrt(aa * bb) if aa and bb else None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True, type=Path, help='Private HF32 analysis result')
    parser.add_argument('--requests', required=True, type=Path, help='Private frozen request manifest')
    parser.add_argument('--cases', required=True, type=Path, help='Private grouped-completion result')
    parser.add_argument('--prepared-root', required=True, type=Path, help='Directory containing pinned source files')
    args = parser.parse_args()
    source = json.loads(read_pinned(args.source, SOURCE_SHA))
    case_manifest = json.loads(read_pinned(args.cases, CASE_MANIFEST_SHA))
    references = [r['manifest721'] for r in source['authoritative_replays'].values()]
    require(references and all(r == references[0] for r in references), 'request references differ')
    require(references[0]['sha256'] == REQUEST_MANIFEST_SHA, 'request manifest commitment differs')
    manifest = json.loads(read_pinned(args.requests, REQUEST_MANIFEST_SHA))
    require(len(manifest['requests']) == 736, 'request geometry differs')
    artifact_sources = {}
    request_counts = Counter()
    for request in manifest['requests']:
        require(len(request['sources']) == 1, 'unexpected source cardinality')
        ref = request['sources'][0]
        require(ref['id'] == request['artifact_id'], 'source identity differs')
        artifact = request['artifact_id']
        if artifact in artifact_sources:
            require(artifact_sources[artifact] == ref, 'source bytes differ between requests')
        artifact_sources[artifact] = ref
        request_counts[request['arm']] += 1
    require(len(artifact_sources) == 32 and request_counts == {'hbq': 704, 'ttcw14': 32}, 'source geometry differs')
    require(set(artifact_sources) == set(source['paired_scores']) == set(source['projected_targets']), 'artifact membership differs')
    lengths = {}
    for artifact, ref in artifact_sources.items():
        relative = Path(ref['input_path'])
        require(not relative.is_absolute() and '..' not in relative.parts, 'source path differs')
        path = args.prepared_root / relative
        raw = read_pinned(path, ref['sha256'], ref['bytes'])
        text = raw.decode('utf-8-sig')
        lengths[artifact] = len(text.split())
        require(lengths[artifact] > 0, 'empty source text')
    lookup = {hashlib.sha256(key.encode()).hexdigest(): key for key in artifact_sources}
    require(len(lookup) == 32, 'hashed IDs collide')
    seen, rows = set(), []
    for case in case_manifest['results']:
        digest = case['artifact_id_sha256']
        require(digest in lookup and digest not in seen, 'case missing or duplicated')
        seen.add(digest)
        artifact = lookup[digest]
        scores, targets = source['paired_scores'][artifact], source['projected_targets'][artifact]
        hbq, ttcw = scores['historical']['score'], scores['ttcw14']['score']
        require(hbq == case['saved_bounds']['observed'] == scores['candidate']['score'], 'score differs')
        row = {'length': lengths[artifact], 'hbq': hbq, 'ttcw': ttcw,
               'expert': targets['expert_mean2'], 'reader': targets['nonexpert_median']}
        require(all(x is None or finite(x) for x in row.values()), 'nonfinite value')
        rows.append(row)
    require(len(rows) == 27, 'complete case count differs')
    result = {}
    for axis in ('expert', 'reader'):
        group = [x for x in rows if x[axis] is not None and x['hbq'] is not None and x['ttcw'] is not None]
        require(len(group) == 19, 'matched cohort differs')
        pair = Counter()
        for left, right in combinations(group, 2):
            pair['pairs'] += 1
            if left[axis] == right[axis]:
                pair['reference_tie'] += 1
            elif left['length'] == right['length']:
                pair['length_tie'] += 1
            elif (left['length'] > right['length']) == (left[axis] > right[axis]):
                pair['concordant'] += 1
            else:
                pair['discordant'] += 1
        result[axis] = {
            'matched_works': len(group),
            'word_count_range': [min(x['length'] for x in group), max(x['length'] for x in group)],
            'distinct_word_counts': len({x['length'] for x in group}),
            'spearman_length_reference': spearman([x['length'] for x in group], [x[axis] for x in group]),
            'spearman_hbq_reference': spearman([x['hbq'] for x in group], [x[axis] for x in group]),
            'spearman_ttcw_reference': spearman([x['ttcw'] for x in group], [x[axis] for x in group]),
            'spearman_length_hbq': spearman([x['length'] for x in group], [x['hbq'] for x in group]),
            'spearman_length_ttcw': spearman([x['length'] for x in group], [x['ttcw'] for x in group]),
            'length_pair_counts': dict(sorted(pair.items())),
        }
    print(json.dumps({'state': 'HF32_POST_RESULT_LENGTH_BASELINE',
        'source_sha256': SOURCE_SHA, 'request_manifest_sha256': REQUEST_MANIFEST_SHA,
        'case_manifest_sha256': CASE_MANIFEST_SHA,
        'word_count_definition': 'Python whitespace split on pinned UTF-8 source text; no prompt or task context included',
        'planned_works': 32, 'complete_hbq_banks': 27, 'matched_results': result,
        'provider_calls': 0, 'new_human_labels': 0,
        'limits': ['Post-result selected development cohorts, not confirmation; only the same 19 works per reference axis are compared.',
                   'Length is an association baseline, not a mechanism, quality rule, causal explanation or calibrated judge.',
                   'Expert and reader constructs differ; works, raters and pair counts are not necessarily independent.',
                   'No population inference, method superiority or candidate promotion follows.']},
        sort_keys=True, indent=2, allow_nan=False))


if __name__ == '__main__':
    main()
