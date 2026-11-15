"""Post-result, provider-free overlap analysis of previously opened HF32 data.

Print aggregate statistics only; no stories or individual scores are emitted.
The shared cohort is an availability-selected development subset, not a new
human-reference evaluation or a provider request.
"""
from collections import Counter
from itertools import combinations
import hashlib
import json
from pathlib import Path

import argparse
import importlib.util

HELPER_SHA = 'fdb7a2cbe9a3505179b22dab79ed9cd9e1bef7e86ac9e26f892e1cb3c1826dc7'
helper = Path(__file__).resolve().parent.parent / 'hbq-hf32-length-baseline-v1' / 'analyze.py'
if hashlib.sha256(helper.read_bytes()).hexdigest() != HELPER_SHA:
    raise ValueError('length-baseline helper differs')
spec = importlib.util.spec_from_file_location('pinned_length_baseline', helper)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
read_pinned, require, finite, spearman = module.read_pinned, module.require, module.finite, module.spearman
SOURCE_SHA, REQUEST_MANIFEST_SHA, CASE_MANIFEST_SHA = module.SOURCE_SHA, module.REQUEST_MANIFEST_SHA, module.CASE_MANIFEST_SHA


def paired_directions(rows):
    result = Counter()
    for left, right in combinations(rows, 2):
        result['pairs'] += 1
        de = left['expert'] - right['expert']
        dr = left['reader'] - right['reader']
        if de == 0 and dr == 0:
            result['both_tie'] += 1
        elif de == 0:
            result['expert_only_tie'] += 1
        elif dr == 0:
            result['reader_only_tie'] += 1
        elif (de > 0) == (dr > 0):
            result['same_direction'] += 1
        else:
            result['opposite_direction'] += 1
    return {k: result[k] for k in ('pairs', 'both_tie', 'expert_only_tie',
                                    'reader_only_tie', 'same_direction', 'opposite_direction')}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True, type=Path)
    parser.add_argument('--requests', required=True, type=Path)
    parser.add_argument('--cases', required=True, type=Path)
    parser.add_argument('--prepared-root', required=True, type=Path)
    args = parser.parse_args()
    source = json.loads(read_pinned(args.source, SOURCE_SHA))
    cases = json.loads(read_pinned(args.cases, CASE_MANIFEST_SHA))
    refs = [r['manifest721'] for r in source['authoritative_replays'].values()]
    require(refs and all(x == refs[0] for x in refs) and refs[0]['sha256'] == REQUEST_MANIFEST_SHA,
            'manifest reference differs')
    manifest = json.loads(read_pinned(args.requests, REQUEST_MANIFEST_SHA))
    require(len(manifest['requests']) == 736, 'request count differs')
    source_refs = {}
    arms = Counter()
    for request in manifest['requests']:
        require(len(request['sources']) == 1 and request['sources'][0]['id'] == request['artifact_id'],
                'request source differs')
        aid, ref = request['artifact_id'], request['sources'][0]
        require(aid not in source_refs or source_refs[aid] == ref, 'conflicting source bytes')
        source_refs[aid] = ref
        arms[request['arm']] += 1
    require(len(source_refs) == 32 and arms == {'hbq': 704, 'ttcw14': 32}, 'request membership differs')
    require(set(source_refs) == set(source['paired_scores']) == set(source['projected_targets']), 'source membership differs')
    hashed = {hashlib.sha256(k.encode()).hexdigest(): k for k in source_refs}
    require(len(hashed) == 32, 'ID hash collision')
    rows, seen = [], set()
    for case in cases['results']:
        key = case['artifact_id_sha256']
        require(key in hashed and key not in seen, 'case membership differs')
        seen.add(key)
        aid = hashed[key]
        ref = source_refs[aid]
        rel = Path(ref['input_path'])
        require(not rel.is_absolute() and '..' not in rel.parts, 'unsafe input path')
        story = read_pinned(args.prepared_root / rel, ref['sha256'], ref['bytes']).decode('utf-8-sig')
        scores, targets = source['paired_scores'][aid], source['projected_targets'][aid]
        hbq, ttcw = scores['historical']['score'], scores['ttcw14']['score']
        require(hbq == case['saved_bounds']['observed'] == scores['candidate']['score'], 'saved score differs')
        row = {'length': len(story.split()), 'hbq': hbq, 'ttcw': ttcw,
               'expert': targets['expert_mean2'], 'reader': targets['nonexpert_median']}
        require(all(v is None or finite(v) for v in row.values()) and row['length'] > 0, 'invalid data')
        rows.append(row)
    require(len(rows) == 27, 'complete-bank count differs')
    membership = Counter(('expert' if r['expert'] is not None else 'no_expert',
                          'reader' if r['reader'] is not None else 'no_reader') for r in rows)
    selected = [r for r in rows if all(r[k] is not None for k in ('expert', 'reader', 'hbq', 'ttcw'))]
    expert = [r for r in rows if r['expert'] is not None and r['hbq'] is not None and r['ttcw'] is not None]
    reader = [r for r in rows if r['reader'] is not None and r['hbq'] is not None and r['ttcw'] is not None]
    require(len(expert) == len(reader) == 19 and len(selected) >= 3, 'cohort changed')
    correlations = {axis: {method: spearman([r[method] for r in selected], [r[axis] for r in selected])
                           for method in ('length', 'hbq', 'ttcw')}
                    for axis in ('expert', 'reader')}
    print(json.dumps({'state': 'HF32_POST_RESULT_SHARED_REFERENCE_OVERLAP',
        'source_sha256': SOURCE_SHA, 'request_manifest_sha256': REQUEST_MANIFEST_SHA,
        'case_manifest_sha256': CASE_MANIFEST_SHA, 'planned_works': 32, 'complete_hbq_banks': 27,
        'reference_availability_among_complete_banks': {
            'both': membership[('expert', 'reader')], 'expert_only': membership[('expert', 'no_reader')],
            'reader_only': membership[('no_expert', 'reader')], 'neither': membership[('no_expert', 'no_reader')]},
        'expert_matched_cohort': len(expert), 'reader_matched_cohort': len(reader),
        'common_reference_and_method_cohort': len(selected), 'correlations_spearman': correlations,
        'expert_reader_spearman': spearman([r['expert'] for r in selected], [r['reader'] for r in selected]),
        'expert_reader_pair_directions': paired_directions(selected),
        'provider_calls': 0, 'new_human_labels': 0,
        'limits': ['Selected previously opened development works; not an independent sample or prospective confirmation.',
                   'The common subset is selected on availability and does not address missingness or prove the populations differ.',
                   'Expert and reader references use distinct aggregates; shared work does not establish independent raters.',
                   'Pairs reuse works; no confidence interval, causation, superiority or candidate promotion is established.']},
        sort_keys=True, indent=2, allow_nan=False))


if __name__ == '__main__':
    main()
