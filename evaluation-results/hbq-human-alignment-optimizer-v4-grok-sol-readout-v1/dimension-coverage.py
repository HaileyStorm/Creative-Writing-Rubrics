"""Descriptive coverage and discrepancies for the published 33 matched pairs."""
import hashlib
import json
import math
from pathlib import Path

root = Path(__file__).resolve().parents[2]
source = root / 'evaluation-results/hbq-human-alignment-optimizer-v4-grok-sol-readout-v1/result-33-pairs.json'
raw = source.read_bytes()
assert hashlib.sha256(raw).hexdigest() == '3ef7ea2ff8f95484d925f439e0b8e123f2c671d2d4835577bc049abc1bb301ba'
data = json.loads(raw)
rows = data['pairs']
assert len(rows) == 33
dimensions = sorted(rows[0]['absolute_difference'])
assert len(dimensions) == 6
groups = {d: [] for d in dimensions}
missing = {d: 0 for d in dimensions}
items = {}
complete = 0
for row in rows:
    assert set(row['absolute_difference']) == set(dimensions)
    excluded = set(row['uncovered_dimensions'])
    assert excluded <= set(dimensions) and len(excluded) == len(row['uncovered_dimensions'])
    complete += not excluded
    item = items.setdefault(row['item_id'], [])
    for dimension in dimensions:
        value = row['absolute_difference'][dimension]
        assert isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0
        if dimension in excluded:
            missing[dimension] += 1
        else:
            groups[dimension].append(value)
            item.append(value)
assert len(items) == 7 and sum(map(len, groups.values())) == 172 and sum(missing.values()) == 26
assert all(groups.values()) and all(items.values())
result = {
    'source_sha256': hashlib.sha256(raw).hexdigest(),
    'pairs': len(rows), 'item_clusters': len(items), 'pair_dimensions': len(rows) * len(dimensions),
    'complete_pairs': complete,
    'complete_pair_mean_absolute_difference': {d: sum(row['absolute_difference'][d] for row in rows if not row['uncovered_dimensions']) / complete for d in dimensions},
    'dimensions': {d: {'covered': len(groups[d]), 'missing': missing[d],
                       'covered_mean_absolute_difference': sum(groups[d])/len(groups[d]),
                       'covered_zero_recorded_difference': sum(v == 0 for v in groups[d]),
                       'covered_maximum_absolute_difference': max(groups[d])} for d in dimensions},
    'item_covered_mean_absolute_difference_range': [min(sum(v)/len(v) for v in items.values()),
                                                     max(sum(v)/len(v) for v in items.values())],
    'limitations': 'Descriptive post-result summaries of selected historical pairs. Uncovered dimensions are excluded, not imputed; item/candidate dimensions are dependent. Absolute differences cannot recover signed bias, score ranks or pair-order disagreement. No human alignment, reliability, provider ranking, generalization or native contact cardinality is established.'
}
print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))
