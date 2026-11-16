"""Reconstruct aggregate author-model score distributions from public data."""
import argparse
from collections import Counter, defaultdict
import csv
from decimal import Decimal, InvalidOperation
import hashlib
import io
from itertools import combinations
import json
from pathlib import Path

TABLE_SHA256 = '0c6deb17a57ed5d04f7a0c42388ada259924e85ba0112829571df16f84f06f37'
SOURCE = ('https://github.com/ku-nlp/creativity-evaluation-artifact/blob/'
          '120c47958bd4941e8d6abd6995dc858b53515788/study1_human/data/llm_ratings.csv')


def fail(message):
    raise ValueError(message)


def score(raw):
    try:
        value = Decimal(raw.strip())
    except (InvalidOperation, AttributeError):
        return None
    return int(value) if value.is_finite() and value == value.to_integral_value() and 1 <= value <= 7 else None


def build(raw):
    if hashlib.sha256(raw).hexdigest() != TABLE_SHA256:
        fail('Author source hash differs')
    reader = csv.DictReader(io.StringIO(raw.decode('utf-8-sig'), newline=''))
    if reader.fieldnames is None or not {'model_label', 'model_id', 'story_id', 'topic', 'IC'} <= set(reader.fieldnames):
        fail('Author source columns differ')
    groups, topics = defaultdict(dict), {}
    for row in reader:
        condition, case, topic = (row['model_label'], row['model_id']), row['story_id'], row['topic']
        if not all(condition) or not case or not topic or case in groups[condition] or (case in topics and topics[case] != topic):
            fail('Duplicate or conflicting identity')
        topics[case] = topic
        groups[condition][case] = score(row['IC'])
    if len(groups) != 20 or len(topics) != 12 or sorted(Counter(topics.values()).values()) != [4, 4, 4] or any(set(g) != set(topics) for g in groups.values()):
        fail('Planned study geometry differs')
    hist = Counter()
    for group in groups.values():
        values = [v for v in group.values() if v is not None]
        hist['valid'] += len(values)
        hist['unavailable'] += 12 - len(values)
        hist['minimum_1'] += values.count(1)
        hist['maximum_7'] += values.count(7)
        hist['all_pair_ties'] += sum(a == b for a, b in combinations(values, 2))
        hist['all_available_pairs'] += len(values) * (len(values) - 1) // 2
        for a, b in combinations(sorted(topics), 2):
            if topics[a] == topics[b] and group[a] is not None and group[b] is not None:
                hist['within_topic_available_pairs'] += 1
                hist['within_topic_ties'] += group[a] == group[b]
    comparison = {name: Counter() for name in ('same_model_id', 'different_model_id')}
    story_pairs = list(combinations(sorted(topics), 2))
    for left, right in combinations(sorted(groups), 2):
        counts = comparison['same_model_id' if left[1] == right[1] else 'different_model_id']
        a, b = groups[left], groups[right]
        counts['condition_pairs'] += 1
        for case in topics:
            if a[case] is None or b[case] is None:
                counts['unavailable_story_comparisons'] += 1
            else:
                counts['available_story_comparisons'] += 1
                counts['same_score' if a[case] == b[case] else 'different_score'] += 1
        for x, y in story_pairs:
            scopes = ['all'] + (['within_topic'] if topics[x] == topics[y] else [])
            if any(v is None for v in (a[x], a[y], b[x], b[y])):
                for scope in scopes:
                    counts[scope + '_unavailable'] += 1
                continue
            d1 = (a[x] > a[y]) - (a[x] < a[y])
            d2 = (b[x] > b[y]) - (b[x] < b[y])
            category = ('both_tie' if d1 == d2 == 0 else 'one_tie' if d1 == 0 or d2 == 0 else
                        'same_strict' if d1 == d2 else 'opposite_strict')
            for scope in scopes:
                counts[scope + '_available'] += 1
                counts[scope + '_' + category] += 1
    return {'source': SOURCE, 'source_sha256': TABLE_SHA256, 'conditions': len(groups),
            'stories': len(topics), 'topic_groups': 3, 'native_scale': [1, 7],
            'distribution': dict(sorted(hist.items())),
            'condition_pair_agreement': {k: dict(sorted(v.items())) for k, v in comparison.items()},
            'limitations': ['Author-model scores only; no human-reference or CWR alignment.',
                            'Shared stories, topics and model families make comparisons dependent.',
                            'Source and prompt equivalence to survey rendering is not established.',
                            'Different recorded model IDs do not establish independent runtime or model families.']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    encoded = (json.dumps(build(args.input.read_bytes()), sort_keys=True, indent=2) + '\n').encode('utf-8')
    with args.output.open('xb') as out:
        out.write(encoded)
    print(hashlib.sha256(encoded).hexdigest())


if __name__ == '__main__':
    main()
