"""Summarize retained LAMP leaf applicability; no scoring or provider calls."""
import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import io
import json
from pathlib import Path

PROFILE_SHA = 'aa6a9e809f53e6640497e7fa3d5efe6f583426b794a90f031832562cb7354a69'
COMPILED_SHA = 'fdb8d9f49bdc9183db0783c461f2e58d044fd088a7e3cfaea7bb95af501e93a4'
STATES = ('YES', 'NO', 'NOT_APPLICABLE', 'CANNOT_ASSESS')


def pinned_json(path, expected):
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError('Input differs from retained study bytes')
    return json.loads(raw)


def summarize(profiles, compiled):
    selected = [row for row in profiles if row['key'][:2] == ['sol', 'hbq']
                and row['profile']['state'] == 'SCORED']
    if len(selected) != 38 or len({tuple(row['key']) for row in selected}) != 38:
        raise ValueError('Expected 38 distinct saved scored banks')
    entries = compiled['domain_questions'] + compiled['supplemental_questions']
    entries += [q for group in compiled['penalty_groups'] for q in group['questions']]
    questions = {entry['question']['id']: entry for entry in entries}
    if len(entries) != len(questions) or len(questions) != 170:
        raise ValueError('Frozen question membership differs')
    counts = {qid: Counter({state: 0 for state in STATES}) for qid in questions}
    bank_counts = []
    for row in selected:
        profile = row['profile']
        if row['key'][3] != 0 or set(profile['leaves']) != set(questions):
            raise ValueError('Expected complete initial bank membership')
        if profile['coverage']['native_leaves'] != 170:
            raise ValueError('Saved bank native leaf count differs')
        bank = Counter({state: 0 for state in STATES})
        for qid, state in profile['leaves'].items():
            if state not in STATES:
                raise ValueError('Unknown saved leaf state')
            counts[qid][state] += 1
            bank[state] += 1
        bank_counts.append(bank)
    criteria = []
    modules = defaultdict(lambda: {'criteria': 0, **{state: 0 for state in STATES}})
    for qid, entry in sorted(questions.items()):
        c = counts[qid]
        if sum(c.values()) != 38:
            raise ValueError('Criterion denominator differs')
        criteria.append({'criterion_id': qid, 'module_id': entry['module_id'],
                         'role': entry['role'], 'text': entry['question']['text'],
                         'applies_when': entry['question']['applies_when'],
                         'counts': dict(c), 'assessed_binary': c['YES'] + c['NO']})
        module = modules[entry['module_id']]
        module['criteria'] += 1
        for state in STATES:
            module[state] += c[state]
    totals = {state: sum(c[state] for c in bank_counts) for state in STATES}
    if sum(totals.values()) != 6460:
        raise ValueError('Expected 38 times 170 leaf cells')
    coverage = [row['profile']['weighted_coverage'] for row in selected]
    return {
        'schema_version': 1, 'study': 'lamp-retained-applicability-development-20261020',
        'state': 'RETROSPECTIVE_AVAILABILITY_SELECTED_COVERAGE_DIAGNOSTIC',
        'input_sha256': {'profiles': PROFILE_SHA, 'compiled': COMPILED_SHA},
        'analysis_source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'selection': 'All 38 Sol HBQ SCORED initial banks in the retained 032 profile file; incomplete banks excluded.',
        'banks': 38, 'criteria': 170, 'leaf_cells': 6460, 'state_counts': totals,
        'always_not_applicable': [row['criterion_id'] for row in criteria if row['counts']['NOT_APPLICABLE'] == 38],
        'never_binary_assessed': [row['criterion_id'] for row in criteria if row['assessed_binary'] == 0],
        'criteria_with_cannot_assess': sum(row['counts']['CANNOT_ASSESS'] > 0 for row in criteria),
        'banks_with_cannot_assess': sum(bank['CANNOT_ASSESS'] > 0 for bank in bank_counts),
        'saved_canonical_weighted_coverage': {'minimum': min(coverage), 'maximum': max(coverage), 'mean': sum(coverage) / len(coverage)},
        'modules': dict(sorted(modules.items())), 'criterion_counts': criteria,
        'provider_calls': 0, 'scorer_calls': 0, 'semantic_or_native_replays': 0,
        'human_labels_opened': False, 'candidate_promoted': False,
        'limitations': [
            'Raw state counts are unweighted and are not canonical weighted coverage.',
            'Persistent NOT_APPLICABLE may correctly reflect passage scope; counts alone do not establish a rubric or judge defect.',
            'CANNOT_ASSESS identifies saved unassessability, not its cause or correctness.',
            'Banks are availability-selected, dependent initial paragraphs rather than a representative population or repeatability panel.',
            'Historical collection tool controls remain unqualified; do not pool with the contemporary tools-disabled Sol condition.',
            'No human alignment, ground-truth, semantic grounding, causal effect, current-model or full-system validity claim.'
        ]
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profiles', type=Path, required=True)
    parser.add_argument('--compiled', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True, help='New output directory')
    args = parser.parse_args()
    result = summarize(pinned_json(args.profiles, PROFILE_SHA), pinned_json(args.compiled, COMPILED_SHA))
    text = io.StringIO(newline='')
    writer = csv.writer(text, lineterminator='\n')
    writer.writerow(('criterion_id', 'module_id', 'role', 'YES', 'NO', 'NOT_APPLICABLE', 'CANNOT_ASSESS', 'assessed_binary', 'question'))
    for row in result['criterion_counts']:
        writer.writerow((row['criterion_id'], row['module_id'], row['role'], *(row['counts'][state] for state in STATES), row['assessed_binary'], row['text']))
    args.output.mkdir(parents=False, exist_ok=False)
    for name, content in [('results.json', json.dumps(result, indent=2, sort_keys=True) + '\n'), ('criteria.csv', text.getvalue())]:
        with (args.output/name).open('xb') as stream:
            stream.write(content.encode('utf-8'))
    print(json.dumps({key: result[key] for key in ('state', 'banks', 'criteria', 'leaf_cells', 'state_counts', 'always_not_applicable', 'never_binary_assessed', 'criteria_with_cannot_assess', 'banks_with_cannot_assess', 'saved_canonical_weighted_coverage')}))


if __name__ == '__main__':
    main()
