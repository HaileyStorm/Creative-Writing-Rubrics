"""Project already-public WPB development aggregates into six matrix rows."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import re

MODEL = 'evaluation-results/hbq-human-alignment-wpb-sol-completed-result-v1/aggregate.v1.json'
LENGTH = 'evaluation-results/hbq-wpb-length-baseline-dev-v1/README.md'
PINS = {MODEL: 'cc48b45dfd49c73230e57e47d7d39eef40b1baa170ee316497def8cfa52aadde',
        LENGTH: 'ce6b7da68ed77843cbba85a458019f21f3506b3e2027c2b95ade856133d2a622'}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    sources = {}
    for name, pin in PINS.items():
        raw = (args.repo_root / name).read_bytes()
        if sha256(raw).hexdigest() != pin:
            raise ValueError('published source digest differs')
        sources[name] = raw
    model = json.loads(sources[MODEL])
    match = re.search(r'(\d+) of (\d+) TRAIN pairs and (\d+) of (\d+) DEV pairs', sources[LENGTH].decode('utf-8'))
    if not match:
        raise ValueError('published length counts missing')
    tw, tn, dw, dn = map(int, match.groups())
    lengths = {'train': (tw, tn), 'dev': (dw, dn)}
    if lengths != {'train': (84, 105), 'dev': (17, 24)} or model['full_hbq'] is not False:
        raise ValueError('source scope differs')
    rows = []
    for partition in ('train', 'dev'):
        for arm in ('length', 'grok_compact_proxy', 'sol_compact_proxy'):
            if arm == 'length':
                wins, pairs = lengths[partition]
                ties = 0
                source = LENGTH
                categories = 35 if partition == 'train' else 8
            else:
                branch = 'frozen_grok_choice' if arm == 'grok_compact_proxy' else 'matched_sol'
                m = model[branch]['partition_metrics'][partition]
                wins, pairs, ties, categories = m['wins'], m['pairs'], m['ties'], m['categories']
                if wins + m['losses'] + ties != pairs or categories * 3 != pairs:
                    raise ValueError('source geometry differs')
                source = MODEL
            if pairs != lengths[partition][1]:
                raise ValueError('denominators differ')
            rows.append({'dataset': 'WritingPreferenceBench', 'partition': partition,
                         'population': 'published preference reference; credentials not established here',
                         'arm': arm, 'pairs': pairs, 'categories': categories,
                         'wins': wins, 'ties': ties, 'ties_are_wins': False,
                         'metric': 'preferred-side win proportion', 'value': wins / pairs,
                         'source': source, 'source_sha256': PINS[source],
                         'scope': 'selected development; not full HBQ or confirmation'})
    raw = ''.join(json.dumps(row, sort_keys=True, separators=(',', ':')) + '\n' for row in rows).encode()
    with args.output.open('xb') as f:
        f.write(raw)
    print(sha256(raw).hexdigest())

if __name__ == '__main__':
    main()
