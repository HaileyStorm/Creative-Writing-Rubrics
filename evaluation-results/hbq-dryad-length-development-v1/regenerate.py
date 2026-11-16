"""Reproduce the development-only Dryad length comparison from pinned private inputs."""
import argparse
from collections import Counter
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import random
import re

PINS = {
    'panel': 'cbfc8eea8c5855b1e3cd0c30e5c14c3d53db42869ade3faf6e3b84b99c6f7b6c',
    'manifest': 'd95ccf315193a77575259fdedd280984442c62148f9917da6157cc57701f712e',
    'analysis': '0c91ec3f2c31f40599d74fb250df5a4cbc12b3174ab89b6e743db7f6d1836c28',
    'aggregate': '43bc7afc5ec7ab389d1dddb965c83ad49d312727e0780dc6eecca4b6881ea505',
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def checked(path, digest):
    raw = path.read_bytes()
    require(hashlib.sha256(raw).hexdigest() == digest, 'Input digest mismatch')
    return raw


def quantile(values, q):
    position = (len(values) - 1) * q
    low = int(position)
    high = min(low + 1, len(values) - 1)
    return values[low] + (position - low) * (values[high] - values[low])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--panel', type=Path, required=True)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--story-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    published = Path(__file__).resolve().parent.parent / 'hbq-dryad-sol-dev30-development-20261023'
    panel = json.loads(checked(args.panel, PINS['panel']))
    manifest = json.loads(checked(args.manifest, PINS['manifest']))
    previous = json.loads(checked(published / 'aggregates.json', PINS['aggregate']))
    analysis = {}
    exec(compile(checked(published / 'analysis.py', PINS['analysis']), 'pinned-analysis', 'exec'), analysis)
    rows = manifest['scientific_condition']['cohort']
    cohort = {row['original_pass_id']: row for row in rows}
    ids = [row['pass_id'] for row in panel]
    require(len(panel) == len(rows) == len(cohort) == len(set(ids)) == 30 and set(ids) == set(cohort), 'Panel mismatch')
    lengths = []
    for row in panel:
        story = cohort[row['pass_id']]
        require(re.fullmatch(r'dryad-[0-9a-f]+', story['id']) is not None, 'Invalid story identity')
        rel = 'inputs/' + story['id'] + '.txt'
        pin = manifest['file_inventory'][rel]
        require(pin['sha256'] == story['source_sha256'] and pin['bytes'] == story['source_bytes'], 'Story commitment mismatch')
        raw = checked(args.story_root / rel, pin['sha256'])
        require(len(raw) == pin['bytes'], 'Story byte count mismatch')
        lengths.append(len(raw.decode('utf-8')))
    scores = [Fraction(str(row['score'])) for row in panel]
    rho, fraction = analysis['rho'], analysis['fraction']
    targets = {a: [fraction(row['axis_means'][a]) for row in panel] for a in ('well_written', 'enjoyed')}
    axes = {}
    for axis, human in targets.items():
        hbq = rho(scores, human)
        require(hbq == previous['associations'][axis]['rho'], 'Published HBQ correlation mismatch')
        axes[axis] = {'hbq_rho': hbq, 'length_rho': rho(lengths, human)}
    draws = {axis: [] for axis in targets}
    rng = random.Random(20261114)
    for _ in range(2000):
        ix = [rng.randrange(30) for _ in range(30)]
        for axis, human in targets.items():
            h = [human[i] for i in ix]
            left = rho([scores[i] for i in ix], h)
            right = rho([lengths[i] for i in ix], h)
            draws[axis].append(None if left is None or right is None else left - right)
    for axis, values in draws.items():
        valid = sorted(v for v in values if v is not None)
        axes[axis]['hbq_minus_length_rho'] = axes[axis]['hbq_rho'] - axes[axis]['length_rho']
        axes[axis]['undefined_draws'] = len(values) - len(valid)
        axes[axis]['conditional_paired_95_interval'] = [quantile(valid, .025), quantile(valid, .975)] if len(valid) == len(values) else None
    counts = Counter(lengths)
    result = {
        'schema_version': 1, 'state': 'RETROSPECTIVE_SELECTED_DEVELOPMENT',
        'input_sha256': PINS, 'stories': 30, 'axes': axes,
        'length_rule': 'UTF-8 decoded raw Unicode code points without normalization',
        'distinct_lengths': len(counts), 'tied_length_pairs': sum(v * (v - 1) // 2 for v in counts.values()),
        'hbq_length_rho': rho(scores, lengths),
        'bootstrap': {'unit': 'story', 'replicates': 2000, 'seed': 20261114, 'quantiles': 'linear interpolation', 'chosen_after_result': True},
        'limits': ['Selected previously opened development panel; no prospective confirmation.',
                   'Story resampling conditions on the selected panel and pooled rater means; it does not model shared raters, topic or selection.',
                   'The intervals do not establish a winner, equivalence, causation or population performance.'],
        'new_provider_calls': 0, 'new_human_labels': 0, 'confirmation_opened': False,
    }
    raw = (json.dumps(result, sort_keys=True, indent=2, allow_nan=False) + '\n').encode()
    for row in panel:
        require(row['pass_id'].encode() not in raw and row['opaque_story_id'].encode() not in raw, 'Private identity in output')
    with args.output.open('xb') as stream:
        stream.write(raw)
    require(args.output.read_bytes() == raw, 'Output readback mismatch')
    print(json.dumps({'state': result['state'], 'sha256': hashlib.sha256(raw).hexdigest(), 'stories': 30}))


if __name__ == '__main__':
    main()
