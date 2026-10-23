"""Reproduce the fixed compact-dimension development diagnostic.

Reads retained private inputs and writes aggregates only. No model is called.
The native overall comparator is retained; the six-dimension mean is post hoc.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from fractions import Fraction
import json
from pathlib import Path

from completion_order import PINS, encoded, require, sha
from ordered_analysis import FREEZE_SHA, LABEL_SHA, ORIGINAL_SHA, functions
from ordered_results import read, value

VIEW_SHA = '387a39c7c4bf7c11276853fd32fa10b9c7adacb7c6c5c67b9c740f7e9fd13e86'
DIMENSIONS = ('narrative_architecture', 'character_relationships', 'worldbuilding_integration', 'prose_voice', 'emotional_reader_effect', 'thematic_complexity')


def analyze(*, joined, manifest_path, freeze_path, labels, repo):
    view_bytes = read(joined, VIEW_SHA)
    view = json.loads(view_bytes)
    manifest = value(manifest_path, PINS['manifest'])
    freeze = value(freeze_path, FREEZE_SHA)
    read(labels, LABEL_SHA)
    require(freeze['development_only'] is True and freeze['promotion_authorized'] is False, 'Development scope required')
    requests = {r['endpoint_ordinal']: r for r in manifest['requests']}
    expected = {r['id'] for r in freeze['cohort']}
    groups = {r['id']: r['plot'] for r in freeze['cohort']}
    require(len(expected) == 36, 'Frozen cohort differs')
    original_scores, mean_scores = {}, {}
    frequencies = defaultdict(Counter)
    all_means_round_to_overall = True
    two_dimension_order_equivalent = True
    for record in view['records']:
        if record['arm'] != 'compact':
            continue
        row = requests[record['endpoint_ordinal']]
        require(record['semantic_acceptance']['accepted'] is True and record['response']['status'] == 'SCORED', 'Accepted scored compact result required')
        require(all(record[k] == row[k] for k in ('arm', 'logical_sample_id', 'request_sha256', 'scientific_condition_sha256')), 'Frozen request identity differs')
        result = record['response']['result']
        dimensions = result['dimensions']
        scores = {d['dimension_id']: d['score'] for d in dimensions}
        require(len(dimensions) == len(scores) == 6 and set(scores) == set(DIMENSIONS), 'Six unique original dimensions required')
        require(all(type(v) is int and 1 <= v <= 5 for v in scores.values()), 'Native dimension score differs')
        overall = result['overall_score']
        require(type(overall) is int and 1 <= overall <= 5, 'Native overall score differs')
        story = row['story_id']
        require(story in expected and story not in mean_scores, 'Duplicate or unknown work')
        mean = Fraction(sum(scores.values()), 6)
        mean_scores[story] = float(mean)
        original_scores[story] = overall
        all_means_round_to_overall &= round(mean) == overall
        two_dimension_order_equivalent &= mean == Fraction(scores['narrative_architecture'] + scores['worldbuilding_integration'] + 8, 6)
        for dimension, score in scores.items():
            frequencies[dimension][score] += 1
    require(len(mean_scores) == 17 and set(mean_scores) == set(original_scores), 'Fixed matched subset differs')
    original = value(Path(manifest['payload_reuse']['root']).resolve() / 'manifest.json', ORIGINAL_SHA)
    scope, resampling = functions(repo)
    targets, _ = scope['load_labels'](labels, original)
    require(set(mean_scores) <= set(targets), 'Missing reference for observed work')
    methods = {name: {'distribution': scope['distribution'](scores, 'compact'), 'association': scope['association'](scores, targets, groups, 2000)} for name, scores in (('original_overall', original_scores), ('equal_dimension_mean', mean_scores))}
    return {
        'schema_version': 1, 'state': 'POST_HOC_DEVELOPMENT_DIAGNOSTIC',
        'diagnostic': 'compact_equal_dimension_mean_v1',
        'rule': 'Unweighted arithmetic mean of exactly six native integer dimension scores; no fitting or imputation.',
        'source_commitments': {'joined_sha256': sha(view_bytes), 'manifest_sha256': PINS['manifest'], 'freeze_sha256': FREEZE_SHA, 'labels_sha256': LABEL_SHA},
        'accepted_view_records': len(view['records']), 'matched_works': len(mean_scores), 'expected_works': 36,
        'represented_plot_clusters': len({groups[s] for s in mean_scores}),
        'methods': methods, 'dimension_frequencies': dict(frequencies),
        'constant_dimensions': [d for d in DIMENSIONS if len(frequencies[d]) == 1],
        'all_dimension_means_round_to_native_overall': all_means_round_to_overall,
        'ranking_equivalent_to_architecture_plus_worldbuilding': two_dimension_order_equivalent,
        'resampling': resampling, 'provider_calls': 0, 'new_human_labels': 0,
        'baseline_unchanged': True, 'candidate_promoted': False, 'unused_confirmation': False,
        'full_goal_complete': False,
        'limits': [
            'Post-hoc after score-distribution inspection and access to already-open development references; no prospective confirmation.',
            'Availability-selected17of36works in10plots; estimates do not establish generalized improvement.',
            'The original constant rank vector has undefined correlation, not zero correlation.',
            'All derived means round to2, so integer quantization can explain the native overall category.',
            'Four dimensions are constant; this ordering comes only from narrative architecture and worldbuilding.',
            'Equal weighting and spacing of ordinal ratings are operational assumptions, not proven measurement properties.',
            'Different available subsets cannot support a direct comparison with HBQ or another comparator.',
            'Raw stories, native responses, work identities, reference ballots and account details are excluded from this aggregate output.',
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('joined', 'manifest', 'freeze', 'labels', 'repo', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    try:
        report = analyze(joined=args.joined.resolve(), manifest_path=args.manifest.resolve(), freeze_path=args.freeze.resolve(), labels=args.labels.resolve(), repo=args.repo.resolve())
        with args.output.open('xb') as stream:
            stream.write(encoded(report))
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(2, f'compact dimension mean: {error}\n')
    print(json.dumps({'state': report['state'], 'matched_works': report['matched_works'], 'methods': report['methods'], 'provider_calls': 0}, allow_nan=False))


if __name__ == '__main__':
    main()
