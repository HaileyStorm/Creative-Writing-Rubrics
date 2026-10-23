"""Build private numeric profiles from explicit-ID saved TTCW results.

Uses the frozen analysis/scorer without human references or provider contact.
Missing packets stay missing; complete banks may still yield no numeric score.
"""
from __future__ import annotations

import argparse
import ast
from collections import Counter, defaultdict
from itertools import combinations
import json
from pathlib import Path
import statistics
import sys
from types import SimpleNamespace
from typing import Any

from completion_order import PINS, encoded, require, sha
from ordered_results import SCALAR, child, join, read, value

CONDITION_SHA = '219d1388e13bd796d13b93a7511ed7ee55d0cf120479783debf022a622d83dde'
ANALYSIS_SHA = 'c843cb8bfb54a3cc27955c911c1a8e5aa053d6a2f25a9f4dd3b67479fa22ae19'
RANGES = {'hbq': (0, 100), 'ttcw14': (0, 1), 'holistic': (1, 7), 'compact': (1, 5), 'oregon': (6, 36)}
SOURCE_PINS = {
    'src/hbqrs/core.py': '70b4cd16bd536f2f6ddb8e066f801090a037a39605652b14d6c7f6ff312446cb',
    'src/hbqrs/runner.py': '04a87edb728701afa6a43233a775c032473c82d0f189f209713051025d86f1f7',
    'src/hbqrs/scoring_v2.py': '1305f444aaa45a0f47cc38cab207e847ae2ca04142637e6ee765edc3f06960d6',
    'src/hbqrs/weights.py': '6893e8cdbb7ae5de1bb732f6004df558c73838c80bb75d1b2cadb651cc37f139',
    'src/hbqrs/paths.py': 'dedadb6d9f8e3cf700c16012b29e1a590a2b1175c8ead0cf17c44aa6417b8266',
    'src/hbqrs/__init__.py': 'bd80d26dfe93422ca407f3692a227f3070954115df61eeea9b7efd4ec22617ac',
    'registry/all_modules.json': '43a33ee015310097f79c8a04bb7c3a8782813e758d523b1db08ae2b14d51f66f',
    'bundles/all_bundles.json': '012af060e8630b8980661465b368e129ddeec82dfa7b48e13e7a35a473eb95a8',
    'schema/hbq_verdict.schema.json': '2d176506edab164c71d42a73661bcd526e4331dbdce659dfae56168b708a4f19',
    'schema/hbq_judge_response.schema.json': '8896aabcd8f8a503f171d95d70117535da22ceff90400ff8698ee8b3f607edd8',
}


def runtime(repo, condition):
    captured = {name: read(repo / name, pin) for name, pin in SOURCE_PINS.items()}
    source = repo / 'evaluation-results/hbq-matched-ttcw-20261004/analysis.py'
    raw = read(source, ANALYSIS_SHA)
    names = {'fraction', 'distribution', 'score_story', 'load_hbq'}
    nodes = [n for n in ast.parse(raw).body if isinstance(n, ast.FunctionDef) and n.name in names]
    require({n.name for n in nodes} == names, 'Frozen scoring API differs')
    scope = {'Any': Any, 'Counter': Counter, 'statistics': statistics, 'RANGES': RANGES, 'REPO': repo, 'sys': sys, 'prepare': SimpleNamespace(digest=sha)}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(source), 'exec'), scope)
    hbq = scope['load_hbq'](condition)
    for key, name in (('core', 'core.py'), ('runner', 'runner.py'), ('strict', 'scoring_v2.py')):
        require(Path(hbq[key].__file__).resolve() == repo / 'src/hbqrs' / name, 'Loaded scoring module belongs to another checkout')
    require(hbq["runner"].schema_dir().resolve() == repo / "schema" and hbq["strict"].schema_dir().resolve() == repo / "schema", "Effective schema root differs from pinned checkout")
    require(all(read(repo / name) == raw for name, raw in captured.items()), 'Scoring source changed while loading')
    return scope, hbq


def build(view, manifest_path, condition_path, repo):
    manifest = value(manifest_path, PINS['manifest'])
    condition = value(condition_path, CONDITION_SHA)
    scope, hbq = runtime(repo, condition)
    rows = {r['endpoint_ordinal']: r for r in manifest['requests']}
    records = {r['endpoint_ordinal']: r for r in view['records']}
    require(len(records) == len(view['records']), 'Duplicate accepted identity')
    cohort = [r['id'] for r in condition['cohort']]
    require(len(cohort) == len(set(cohort)) == 36, 'Frozen cohort differs')
    expected = {arm: defaultdict(list) for arm in SCALAR}
    for row in rows.values():
        if row['arm'] in expected:
            require(row['repeat'] == 0 and row['story_id'] in cohort and row['scientific_condition_sha256'] == CONDITION_SHA, 'Frozen initial request differs')
            expected[row['arm']][row['story_id']].append(row)
    frozen = Path(manifest['payload_reuse']['root']).resolve()
    context_ref = condition['common_context']
    context = read(child(frozen, context_ref['path']), context_ref['sha256']).decode('utf-8')
    profiles = []
    scores = {arm: {} for arm in SCALAR}
    full_banks_submitted = 0
    for arm in SCALAR:
        for story in cohort:
            bank = sorted(expected[arm][story], key=lambda row: row['batch'] if arm == 'hbq' else row['endpoint_ordinal'])
            require(len(bank) == (23 if arm == 'hbq' else 1), 'Frozen bank geometry differs')
            selected = [row for row in bank if row['endpoint_ordinal'] in records]
            packed = []
            for row in selected:
                record = records[row['endpoint_ordinal']]
                require(record['semantic_acceptance']['accepted'] is True and record['no_resend'] is True, 'Unadmitted record supplied to scorer')
                require(all(record[k] == row[k] for k in ('arm', 'logical_sample_id', 'request_sha256', 'scientific_condition_sha256')), 'Profile request identity differs')
                item = {'request': row, 'response': record['response']}
                if arm == 'hbq' and len(selected) == len(bank):
                    require(len(row['sources']) == 1 and row['sources'][0]['id'] == story, 'HBQ source identity differs')
                    source = row['sources'][0]
                    item.update(source_text=read(child(frozen, source['input_path']), source['sha256']).decode('utf-8'), context_text=context)
                packed.append(item)
            if arm == 'hbq' and len(selected) == 23:
                full_banks_submitted += 1
            result = scope['score_story'](arm, packed, hbq)
            score = result['score']
            require(score is None or RANGES[arm][0] <= score <= RANGES[arm][1], 'Score outside frozen native scale')
            if score is not None:
                scores[arm][story] = score
            profiles.append({'arm': arm, 'story_id': story, 'endpoint_ordinals': [r['endpoint_ordinal'] for r in selected], 'missing_packet_ordinals': [r['endpoint_ordinal'] for r in bank if r['endpoint_ordinal'] not in records], 'complete_request_bank': len(selected) == len(bank), 'source_record_set_sha256': sha(encoded([records[r['endpoint_ordinal']] for r in selected])), **{k: v for k, v in result.items() if k != 'leaves'}})
    arms = {}
    for arm in SCALAR:
        selected = [p for p in profiles if p['arm'] == arm]
        arms[arm] = {'expected_works': 36, 'request_complete_works': sum(p['complete_request_bank'] for p in selected), 'received_records': sum(len(p['endpoint_ordinals']) for p in selected), 'numeric_works': len(scores[arm]), 'states': dict(Counter(p['state'] for p in selected)), 'distribution': scope['distribution'](scores[arm], arm)}
    shared = {a + '__' + b: len(set(scores[a]) & set(scores[b])) for a, b in combinations(SCALAR, 2)}
    summary = {'schema_version': 1, 'state': 'EXPLICIT_ID_NUMERIC_PROFILES_WITHOUT_HUMAN_TARGETS', 'condition_sha256': CONDITION_SHA, 'analysis_source_sha256': ANALYSIS_SHA, 'scoring_source_sha256': SOURCE_PINS, 'compiled_bundle_sha256': condition['runtime']['compiled_bundle_sha256'], 'question_payload_sha256': condition['runtime']['question_payload_sha256'], 'accepted_records': len(records), 'arms': arms, 'shared_numeric_work_denominators': shared, 'all_five_shared_numeric_works': len(set.intersection(*(set(s) for s in scores.values()))), 'full_hbq_banks_submitted_to_frozen_scoring_path': full_banks_submitted, 'pairwise_records_retained_in_view': sum(r['arm'] == 'pairwise' for r in records.values()), 'provider_calls': 0, 'human_targets_read': False, 'human_alignment_measured': False, 'native_or_semantic_reexecuted': False, 'candidate_promoted': False, 'full_goal_complete': False, 'limits': ['Request membership and numeric availability remain distinct.', 'Original full-bank admission, native scales, scorer and missingness behavior retained.', 'Local normalization checks exact source/context quotations; cached producer admission and native qualification limits remain inherited.', 'Incomplete availability-selected development coverage does not establish a winning method or prospective confirmation.']}
    return {'summary': summary, 'profiles': profiles, 'saved_result_summary': view['summary']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('parent-cache', 'manifest', 'census', 'plan', 'condition', 'repo'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--run-dir', type=Path)
    parser.add_argument('--output', type=Path, required=True, help='Create-only private numeric profiles and provenance.')
    args = parser.parse_args()
    try:
        paths = {name: getattr(args, name).resolve() if getattr(args, name) is not None else None for name in ('parent_cache', 'manifest', 'census', 'plan', 'run_dir', 'repo')}
        view = join(**paths)
        result = build(view, paths['manifest'], args.condition.resolve(), paths['repo'])
        with args.output.open('xb') as stream:
            stream.write(encoded(result))
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(2, f'ordered profiles: {error}\n')
    print(json.dumps(result['summary'], indent=2, allow_nan=False))


if __name__ == '__main__':
    main()
