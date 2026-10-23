"""Private development analysis of explicit-ID TTCW profiles and saved results.

Uses already-open development references. Never dispatches, scores a bank, trains
a judge, promotes a candidate or opens an unused confirmation reference.
"""
from __future__ import annotations

import argparse
import ast
from collections import Counter, defaultdict
from itertools import combinations
import json
import math
from pathlib import Path
import random
import statistics
from types import SimpleNamespace
from typing import Any, Callable

from completion_order import encoded, require, sha
from ordered_profiles import ANALYSIS_SHA, CONDITION_SHA, RANGES, SOURCE_PINS
from ordered_results import SCALAR, join, read, value

FREEZE_SHA = 'd7395eeca3bb513b68418589a9496074cce2b093cf96db614451fd7c06dfe035'
LABEL_SHA = '1916ec27eaa8810a8427ed7000e2aefa3535fd2a33b2ae1d372cccdab3fc6516'
ORIGINAL_SHA = 'b1868f8b6dee6daba3125b73628e6276b34f7049fad049f17262cbe3c859b7b7'


def functions(repo):
    path = repo / 'evaluation-results/hbq-matched-ttcw-20261004/analysis.py'
    raw = read(path, ANALYSIS_SHA)
    names = {'fraction', 'ranks', 'rho', 'percentile', 'cluster_bootstrap', 'bounded_agreement', 'distribution', 'association', 'direction', 'within_plot', 'load_labels', 'ttcw_agreement', 'pairwise_analysis'}
    nodes = [n for n in ast.parse(raw).body if isinstance(n, ast.FunctionDef) and n.name in names]
    require({n.name for n in nodes} == names, 'Frozen analysis API differs')
    scope = {'json': json, 'Counter': Counter, 'defaultdict': defaultdict, 'statistics': statistics, 'math': math, 'random': random, 'Any': Any, 'Callable': Callable, 'Path': Path, 'RANGES': RANGES, 'LABEL_SHA': LABEL_SHA, 'BOOTSTRAP_SEED': 20261004, 'prepare': SimpleNamespace(checked=read)}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), 'exec'), scope)
    original = scope['cluster_bootstrap']
    resampling = {'executed_calls': 0, 'suppressed_calls': 0}
    def guarded_bootstrap(rows, statistic, reps=2000, seed=20261004):
        if len(rows) < 33:
            resampling['suppressed_calls'] += 1
            return {'state': 'not_estimated', 'reason': 'Frozen stopped-prefix rule: below33 numeric works; no resampling executed', 'replicates': 0}
        result = original(rows, statistic, reps=reps, seed=seed)
        resampling['executed_calls'] += int(result.get('replicates', 0) > 0)
        return result
    scope['cluster_bootstrap'] = guarded_bootstrap
    return scope, resampling


def bound_scores(profile_payload, view, requests, condition):
    summary = profile_payload['summary']
    require(summary['condition_sha256'] == CONDITION_SHA and summary['analysis_source_sha256'] == ANALYSIS_SHA and summary['scoring_source_sha256'] == SOURCE_PINS, 'Numeric producer source binding differs')
    require(summary['compiled_bundle_sha256'] == condition['runtime']['compiled_bundle_sha256'] and summary['question_payload_sha256'] == condition['runtime']['question_payload_sha256'], 'Numeric producer compilation differs')
    require(profile_payload['saved_result_summary'] == view['summary'], 'Profiles and current explicit result view differ')
    records = {r['endpoint_ordinal']: r for r in view['records']}
    cohort = {r['id'] for r in condition['cohort']}
    profiles = {(r['arm'], r['story_id']): r for r in profile_payload['profiles']}
    require(len(profiles) == len(profile_payload['profiles']) == 180 and set(profiles) == {(arm, story) for arm in SCALAR for story in cohort}, 'Numeric profile coverage differs')
    scores = {arm: {} for arm in SCALAR}
    for (arm, story), profile in profiles.items():
        bank = sorted((r for r in requests.values() if r['arm'] == arm and r.get('story_id') == story), key=lambda row: row['batch'] if arm == 'hbq' else row['endpoint_ordinal'])
        selected = [r['endpoint_ordinal'] for r in bank if r['endpoint_ordinal'] in records]
        missing = [r['endpoint_ordinal'] for r in bank if r['endpoint_ordinal'] not in records]
        require(profile['endpoint_ordinals'] == selected and profile['missing_packet_ordinals'] == missing and profile['complete_request_bank'] is (not missing), 'Numeric profile request membership differs')
        require(profile['source_record_set_sha256'] == sha(encoded([records[n] for n in selected])), 'Numeric profile producer input differs')
        score = profile['score']
        if score is not None:
            require(not missing and profile['state'] == ('SCORED' if arm == 'hbq' else 'assessed'), 'Incomplete or unassessed numeric result')
            require(type(score) in (int, float) and math.isfinite(score) and RANGES[arm][0] <= score <= RANGES[arm][1], 'Invalid numeric score')
            scores[arm][story] = score
    return scores


def analyze(*, view, profiles_path, profiles_sha256, manifest_path, condition_path, freeze_path, labels, repo):
    profile_bytes = read(profiles_path, profiles_sha256)
    profile_payload = json.loads(profile_bytes)
    freeze = value(freeze_path, FREEZE_SHA)
    condition = value(condition_path, CONDITION_SHA)
    require(freeze['development_only'] is True and freeze['promotion_authorized'] is False, 'Frozen development scope differs')
    manifest = value(manifest_path, freeze['request_manifest']['sha256'])
    requests = {r['endpoint_ordinal']: r for r in manifest['requests']}
    original = value(Path(manifest['payload_reuse']['root']).resolve() / 'manifest.json', ORIGINAL_SHA)
    groups = {r['id']: r['plot'] for r in freeze['cohort']}
    require(len(groups) == 36 and {r['id']: r['plot'] for r in condition['cohort']} == groups == {r['id']: r['plot'] for r in original['stories']}, 'Original source/plot cohort differs')
    require(set(original['repeat_pair_ids']) == set(freeze['original_registration_unchanged']['repeat_pair_ids']), 'Original pair sentinels differ')
    scores = bound_scores(profile_payload, view, requests, condition)
    scope, resampling = functions(repo)
    # This exact reference was opened in the retained stopped-development study.
    # The immutable profile digest and explicit request joins are checked first.
    targets, ballots = scope['load_labels'](labels, original)
    methods = {}
    private_ids = {}
    for arm in SCALAR:
        selected = sorted(set(scores[arm]) & set(targets))
        private_ids[arm] = selected
        methods[arm] = {'association': scope['association'](scores[arm], targets, groups, 2000), 'represented_plot_clusters': len({groups[s] for s in selected}), 'distribution': scope['distribution'](scores[arm], arm), 'within_plot_expert_derived_pair_agreement': scope['within_plot'](scores[arm], targets, original['pairs'], 2000)}
    paired = {}
    paired_ids = {}
    for left, right in combinations(SCALAR, 2):
        selected = sorted(set(scores[left]) & set(scores[right]) & set(targets))
        key = left + '__' + right
        paired_ids[key] = selected
        left_rho = scope['rho']([scores[left][s] for s in selected], [targets[s] for s in selected])
        right_rho = scope['rho']([scores[right][s] for s in selected], [targets[s] for s in selected])
        complete = len(selected) >= 33
        rows = [(groups[s], scores[left][s], scores[right][s], targets[s]) for s in selected]
        def delta(sample):
            a = scope['rho']([r[1] for r in sample], [r[3] for r in sample])
            b = scope['rho']([r[2] for r in sample], [r[3] for r in sample])
            return None if a is None or b is None else a - b
        paired[key] = {'works': len(selected), 'expected_works': 36, 'left_rho_same_works': left_rho, 'right_rho_same_works': right_rho, 'delta_rho': None if left_rho is None or right_rho is None else left_rho - right_rho, 'state': 'descriptive_development' if complete else 'inconclusive_missing_over_10_percent', 'bootstrap': scope['cluster_bootstrap'](rows, delta, 2000) if complete else {'state': 'not_estimated', 'replicates': 0, 'reason': 'Incomplete shared denominator'}, 'unobserved_outcome_bounds': [-2, 2] if len(selected) < 36 else None, 'undefined_reason': 'Too few paired works or constant rank vector' if left_rho is None or right_rho is None else None}
    records = view['records']
    ttcw_records = {requests[r['endpoint_ordinal']]['story_id']: {'leaves': r['response']['verdicts']} for r in records if r['arm'] == 'ttcw14'}
    accepted = {r['logical_sample_id']: {'request': requests[r['endpoint_ordinal']], 'response': r['response']} for r in records}
    shared = set.intersection(*(set(v) for v in scores.values()))
    test_agreement = scope['ttcw_agreement'](ttcw_records, ballots, groups, 2000)
    pairwise = scope['pairwise_analysis'](accepted, original, targets, 2000)
    report = {'schema_version': 1, 'state': 'EXPLICIT_ID_DEVELOPMENT_COMPARISON', 'analysis_id': freeze['analysis_id'], 'profiles_sha256': sha(profile_bytes), 'analysis_freeze_sha256': FREEZE_SHA, 'analysis_source_sha256': ANALYSIS_SHA, 'labels_sha256': LABEL_SHA, 'methods': methods, 'paired_method_comparisons': paired, 'all_five_shared_numeric_works': len(shared), 'ttcw14_expert_test_agreement': test_agreement, 'pairwise_expert_derived_agreement': pairwise, 'private_paired_ids': {'methods': private_ids, 'method_comparisons': paired_ids, 'all_five': sorted(shared)}, 'registered_primary_coverage_met': len(shared) >= 33, 'resampling': resampling, 'saved_result_summary': view['summary'], 'provider_calls': 0, 'canonical_scorer_calls': 0, 'native_or_semantic_reexecuted': False, 'new_human_labels': 0, 'already_opened_development_reference_read': True, 'unused_confirmation': False, 'candidate_promoted': False, 'full_goal_complete': False, 'limits': ['Numeric results are hash-bound producer profiles, not independently rescored by this analysis.', 'Exact per-method and paired intersections are retained privately; availability-selected subsets do not support a winning-method claim.', 'Expert pair directions derive from existing mean expert scores, not direct preference ballots.', 'Original33-work and12-plot uncertainty rules retained; missing outcome bounds are not confidence intervals.', 'Further continuation is development, not unused confirmation; native/backend/order qualification limits remain inherited.']}
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('parent-cache', 'manifest', 'census', 'plan', 'condition', 'repo', 'profiles', 'freeze', 'labels'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--profiles-sha256', required=True)
    parser.add_argument('--run-dir', type=Path)
    parser.add_argument('--output', type=Path, required=True, help='Create-only private report with exact analysis intersections.')
    args = parser.parse_args()
    try:
        paths = {name: getattr(args, name).resolve() if getattr(args, name) is not None else None for name in ('parent_cache', 'manifest', 'census', 'plan', 'run_dir', 'repo')}
        view = join(**paths)
        report = analyze(view=view, profiles_path=args.profiles.resolve(), profiles_sha256=args.profiles_sha256, manifest_path=paths['manifest'], condition_path=args.condition.resolve(), freeze_path=args.freeze.resolve(), labels=args.labels.resolve(), repo=paths['repo'])
        with args.output.open('xb') as stream:
            stream.write(encoded(report))
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(2, f'ordered analysis: {error}\n')
    print(json.dumps({'state': report['state'], 'methods': {a: {'n': v['association']['works'], 'rho': v['association']['rho']} for a, v in report['methods'].items()}, 'all_five_shared_numeric_works': report['all_five_shared_numeric_works'], 'registered_primary_coverage_met': report['registered_primary_coverage_met'], 'resampling': report['resampling'], 'provider_calls': 0, 'canonical_scorer_calls': 0, 'unused_confirmation': False}, indent=2))


if __name__ == '__main__':
    main()
