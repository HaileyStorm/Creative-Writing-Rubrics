"""Paired group sensitivity from an already published HANNA aggregate."""
from __future__ import annotations

import argparse
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path
import subprocess

SOURCE_COMMIT = '16a3a725a7fcfea8adb6ca90d370ca2d8f46de8d'
SOURCE_PATH = 'evaluation-results/hbq-human-alignment-optimizer-v5-f20-broader-development-sol-result-v1/result.json'
SOURCE_SHA256 = '34441a265fbf4d654b2de4e89acfcc4b436029f0ff8c7cca47c9759ffc922fa3'
BASELINE = 'candidate-102cc7f06c9a99a7'
PARENT = 'normalized-nextwave-08-conservative-hybrid'
DESCENDANT = 'broader-nextwave-13-missing_evidence_not_no'


def require(ok, message):
    if not ok:
        raise ValueError(message)


def six(value):
    return format(value.quantize(Decimal('0.000001')), 'f')


def paired(left, right):
    require(set(left) == set(right) and len(left) >= 2, 'paired groups differ or are insufficient')
    for value in list(left.values()) + list(right.values()):
        require(isinstance(value, Decimal) and value.is_finite() and value >= 0, 'invalid group error')
    delta = [right[k] - left[k] for k in sorted(left)]
    total = sum(delta, Decimal(0))
    leave_one_out = [(total - x) / (len(delta) - 1) for x in delta]
    return {'groups': len(delta), 'lower_error': sum(x < 0 for x in delta),
            'higher_error': sum(x > 0 for x in delta), 'equal_error': sum(x == 0 for x in delta),
            'mean_change': six(total / len(delta)),
            'leave_one_group_out_mean_change_min': six(min(leave_one_out)),
            'leave_one_group_out_mean_change_max': six(max(leave_one_out))}


def analyze(raw):
    require(sha256(raw).hexdigest() == SOURCE_SHA256, 'source hash differs')
    source = json.loads(raw, parse_float=Decimal, parse_int=Decimal)
    rows = source['metrics']
    require(type(rows) is list and len(rows) == 3, 'unexpected metric rows')
    by_id = {row['candidate_id']: row for row in rows}
    require(set(by_id) == {BASELINE, PARENT, DESCENDANT}, 'unexpected or duplicate candidate IDs')
    groups = {name: by_id[name]['group_mae'] for name in by_id}
    require(all(type(x) is dict and len(x) == 7 for x in groups.values()), 'unexpected group geometry')
    require(all(by_id[name]['cells'] == 7 for name in by_id), 'unexpected cell count')
    for name, values in groups.items():
        require(all(isinstance(v, Decimal) and v.is_finite() and v >= 0 for v in values.values()),
                'invalid group error')
        require(abs(sum(values.values(), Decimal(0)) / 7 - by_id[name]['equal_group_mae']) < Decimal('1e-12'),
                'reported equal-group mean differs')
    return {'schema': 'hanna-seven-group-sensitivity-v1', 'source_commit': SOURCE_COMMIT,
            'source_sha256': SOURCE_SHA256, 'direction': 'right_minus_left_lower_is_better',
            'comparisons': {'baseline_to_parent': paired(groups[BASELINE], groups[PARENT]),
                            'baseline_to_descendant': paired(groups[BASELINE], groups[DESCENDANT]),
                            'parent_to_descendant': paired(groups[PARENT], groups[DESCENDANT])}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--verify', type=Path)
    args = parser.parse_args()
    require(not (args.output and args.verify), 'choose output or verify')
    raw = subprocess.run(['git', '-C', str(args.repo), 'show', SOURCE_COMMIT + ':' + SOURCE_PATH],
                         check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout
    data = (json.dumps(analyze(raw), sort_keys=True, indent=2, allow_nan=False) + '\n').encode('utf-8')
    if args.verify:
        require(args.verify.read_bytes().replace(b'\r\n', b'\n') == data, 'aggregate differs')
        print('Saved aggregate reproduced')
    elif args.output:
        with args.output.open('xb') as handle:
            handle.write(data)
        print('Saved aggregate created')
    else:
        print(data.decode('utf-8'), end='')


if __name__ == '__main__':
    main()
