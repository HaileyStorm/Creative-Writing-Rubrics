"""Describe retained same-prompt repeatability without new model calls."""
from collections import Counter, defaultdict
import argparse
import hashlib
from itertools import combinations
import json
from pathlib import Path
import re

INDEX_SHA = '346cbbc81b867bedc2411bd7d9c309d6ccc0fc595b652d18bd14516681cd2982'
SCHEDULE_SHA = '34a5769967816c465e788cc00ed2296bab81c781e9b114b4bcc2eab07b549724'
TERMINAL_SHA = 'fcdc6f3e278b431e5e99daec2ff3cf8f50a05684ac236f31192d3816830e3f00'
STATES = ('YES', 'NO', 'NOT_APPLICABLE', 'CANNOT_ASSESS')


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read_pinned(path, digest):
    raw = path.read_bytes()
    require(sha(raw) == digest, 'input digest differs')
    return raw


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--index', type=Path, required=True)
    parser.add_argument('--schedule', type=Path, required=True)
    parser.add_argument('--terminals', type=Path, required=True)
    parser.add_argument('--runs-root', type=Path, required=True)
    args = parser.parse_args()
    index = json.loads(read_pinned(args.index, INDEX_SHA))
    schedule = json.loads(read_pinned(args.schedule, SCHEDULE_SHA))['slots']
    terminals = json.loads(read_pinned(args.terminals, TERMINAL_SHA))
    idx = {x['slot_id_sha256']: x for x in index['records']}
    terms = {x['opaque_slot_id']: x for x in terminals}
    require(len(idx) == len(schedule) == len(terms) == 24, 'saved membership differs')
    groups = defaultdict(list)
    for slot in schedule:
        sid = slot['opaque_slot_id']
        require(isinstance(sid, str) and re.fullmatch(r'[A-Za-z0-9_-]+', sid) is not None, 'unsafe slot identifier')
        require(sha(sid.encode()) in idx and sid in terms, 'unknown slot')
        item = idx[sha(sid.encode())]
        terminal = terms[sid]
        require(terminal['accepted'] and terminal['terminal_lifecycle'] == 'accepted_no_semantic_retry', 'saved terminal differs')
        path = args.runs_root / sid / 'responses/batch-0001.json'
        checkpoint = json.loads(read_pinned(path, item['checkpoint_sha256']))
        require(item['checkpoint_sha256'] == terminal['receipt_sha256'], 'receipt differs')
        verdicts = checkpoint['normalized_verdicts']
        require(len(verdicts) == 1 and verdicts[0]['question_id'] == item['leaf_id'] and
                verdicts[0]['verdict'] == terminal['verdict'] and terminal['verdict'] in STATES, 'verdict binding differs')
        groups[item['saved_prompt_sha256']].append({'repeat': slot['repeat'], 'arm': slot['arm'], 'role': slot['role'],
            'verdict': terminal['verdict'], 'source': item['artifact_sha256'], 'contexts': tuple(item['context_sha256']),
            'leaf': item['leaf_id'], 'question': item['declared_question_sha256'], 'rubric': item['declared_rubric_sha256'],
            'model': item['declared_model'], 'reasoning': item['declared_reasoning'],
            'session': item['reported_session_sha256']})
    require(len(groups) == 8 and all(len(x) == 3 for x in groups.values()), 'prompt group geometry differs')
    pair_matrix = Counter()
    by_arm_role = defaultdict(lambda: Counter())
    group_pattern = Counter()
    for values in groups.values():
        values.sort(key=lambda r: r['repeat'])
        require([v['repeat'] for v in values] == [1, 2, 3], 'repeat labels differ')
        for field in ('arm', 'role', 'source', 'contexts', 'leaf', 'question', 'rubric', 'model', 'reasoning'):
            require(len({v[field] for v in values}) == 1, f'group {field} differs')
        require(len({v['session'] for v in values}) == 3 and all(v['session'] is not None for v in values), 'reported sessions differ')
        cat = f"{values[0]['arm']}_{values[0]['role']}"
        by_arm_role[cat]['groups'] += 1
        unique = len({v['verdict'] for v in values})
        group_pattern['unanimous' if unique == 1 else 'mixed'] += 1
        by_arm_role[cat]['unanimous_groups' if unique == 1 else 'mixed_groups'] += 1
        for first, second in combinations(values, 2):
            pair_matrix[first['verdict'], second['verdict']] += 1
            by_arm_role[cat]['pairs'] += 1
            by_arm_role[cat]['agreeing_pairs'] += first['verdict'] == second['verdict']
    matrix = {a: {b: pair_matrix[a, b] for b in STATES} for a in STATES}
    pairs = sum(pair_matrix.values())
    agree = sum(pair_matrix[s, s] for s in STATES)
    require(pairs == 24 and sum(group_pattern.values()) == 8, 'comparison count differs')
    result = {'state': 'POETRY_REPETITION_SAVED_PROMPT_REPEATABILITY', 'index_sha256': INDEX_SHA,
        'planned_requests': 24, 'accepted_saved_requests': 24, 'identical_prompt_groups': 8,
        'repeats_per_group': 3, 'pair_comparisons': pairs, 'agreeing_pairs': agree,
        'pair_matrix_by_repeat_order': matrix, 'group_patterns': dict(group_pattern),
        'by_arm_and_role': {k: {key: c[key] for key in ('groups', 'unanimous_groups', 'mixed_groups', 'pairs', 'agreeing_pairs')}
                            for k, c in sorted(by_arm_role.items())},
        'provider_calls': 0, 'new_human_labels': 0,
        'limits': ['Small selected synthetic poetry treatment, not a population reliability estimate or human alignment.',
                   'Three within-group pairs reuse the same outputs and are dependent.',
                   'Prompt bytes match within groups, but reported provider settings and session IDs are not independently authenticated.',
                   'Source, context and declared leaf/rubric identities match within groups; historical runtime equivalence and account identity remain unverified.',
                   'Expected verdicts and human targets were not used; this does not alter the original NO_GO decision.']}
    print(json.dumps(result, sort_keys=True, indent=2))


if __name__ == '__main__':
    main()
