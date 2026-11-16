"""Add target-only cross-validation baselines to the opened V13 TRAIN study."""
import argparse
from collections import Counter, defaultdict
from fractions import Fraction
from hashlib import sha256
import json
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--schedule', type=Path, required=True)
parser.add_argument('--calibration', type=Path, required=True)
parser.add_argument('--public-result', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
SCHEDULE, CAL, PUBLIC = args.schedule, args.calibration, args.public_result
PINS = {'schedule': '2d66a311912e82f5cc1e4bb411e94493a22e6b0761da43ee6d580972a5d589db',
        'calibration': 'e3900856addc8a4385f0dc578de87ecf88ab921e20a0ab9998bfa653d430caa8',
        'public_result': 'd039289ef0054ad1448bb3d852f505e6362a182ce3adae9610a407d34f912800'}
DIMS = ('Relevance', 'Coherence', 'Empathy', 'Surprise', 'Engagement', 'Complexity')
CHILD = 'broader-nextwave-20-missing_evidence_not_no-referent-evidence'

def load(path, name):
    raw = path.read_bytes()
    if sha256(raw).hexdigest() != PINS[name]:
        raise ValueError('source digest mismatch')
    return json.loads(raw)

def canonical(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False) + '\n').encode()

schedule, saved, public = load(SCHEDULE, 'schedule'), load(CAL, 'calibration'), load(PUBLIC, 'public_result')
commit = schedule['schedule_sha256']
if sha256(canonical({k:v for k,v in schedule.items() if k != 'schedule_sha256'})).hexdigest() != commit:
    raise ValueError('schedule commitment mismatch')
if saved['input_report_sha256'] != public['source']['v13_canonical_report_sha256'] or public['source']['calibration_output_sha256'] != PINS['calibration']:
    raise ValueError('public calibration provenance mismatch')
cells = schedule['cells']
if len(cells) != 88 or any(c['partition'] != 'train' for c in cells):
    raise ValueError('schedule is not exact TRAIN-only geometry')
child = {c['cell_id']: c for c in cells if c['candidate_id'] == CHILD}
if len(child) != 44 or len({c['item_id'] for c in child.values()}) != 44:
    raise ValueError('child inventory mismatch')
for c in cells:
    if sha256(canonical(c['target'])).hexdigest() != c['target_sha256']:
        raise ValueError('target commitment mismatch')
by_group = defaultdict(list)
for cell in child.values():
    if set(cell['target']) != set(DIMS):
        raise ValueError('target dimensions differ')
    by_group[cell['prompt_group_id']].append(cell)
if len(by_group) != 22 or any(not v for v in by_group.values()):
    raise ValueError('expected 22 nonempty prompt groups')
folds = {f['heldout_prompt_group_id']: f for f in saved['folds']}
if len(folds) != 22 or set(folds) != set(by_group):
    raise ValueError('fold inventory mismatch')
maes = defaultdict(dict)
for group, held in by_group.items():
    fold = folds[group]
    training_groups = set(by_group) - {group}
    if set(fold['fit_prompt_group_ids']) != training_groups:
        raise ValueError('fold training groups mismatch')
    predictions = {p['cell_id']: p['scores'] for p in fold['heldout_predictions']}
    if set(predictions) != {c['cell_id'] for c in held}:
        raise ValueError('held-out prediction mismatch')
    baselines = {}
    for dim in DIMS:
        values = sorted((Fraction(str(c['target'][dim])), Fraction(1, len(by_group[g])))
                        for g in training_groups for c in by_group[g])
        if sum((weight for _, weight in values), Fraction()) != 21:
            raise ValueError('training group weights mismatch')
        weighted_sum = sum((value * weight for value, weight in values), Fraction())
        cumulative = Fraction()
        median = None
        for i, (value, weight) in enumerate(values):
            cumulative += weight
            if cumulative > Fraction(21, 2):
                median = value
                break
            if cumulative == Fraction(21, 2):
                median = (value + values[i+1][0]) / 2
                break
        if median is None:
            raise ValueError('weighted median undefined')
        baselines[dim] = {'mean': weighted_sum / 21, 'median': median}
    for method in ('calibrated', 'train_mean', 'train_median'):
        absolute = []
        for cell in held:
            for dim in DIMS:
                target = Fraction(str(cell['target'][dim]))
                pred = (Fraction(str(predictions[cell['cell_id']][dim])) if method == 'calibrated' else
                        baselines[dim]['mean' if method == 'train_mean' else 'median'])
                absolute.append(abs(pred - target))
        maes[method][group] = sum(absolute, Fraction()) / len(absolute)

metrics = {method: float(sum(groups.values(), Fraction()) / 22) for method, groups in maes.items()}
expected = public['metrics']['out_of_fold_calibrated_child20_equal_group_mean_item_mae']
if abs(metrics['calibrated'] - expected) > 1e-12:
    raise ValueError('saved calibrated result could not be reconstructed')
comparison = {}
for baseline in ('train_mean', 'train_median'):
    signs = Counter('lower' if maes['calibrated'][g] < maes[baseline][g] else
                    'higher' if maes['calibrated'][g] > maes[baseline][g] else 'equal' for g in by_group)
    comparison[baseline] = {'calibrated_minus_baseline_mae': metrics['calibrated'] - metrics[baseline],
                            'calibrated_group_loss_comparison': dict(signs)}
result = {'source_sha256': PINS, 'schedule_commitment': commit, 'groups': 22, 'items': 44,
          'dimensions': 6, 'training_groups_per_fold': 21,
          'heldout_group_size_histogram': dict(sorted(Counter(len(v) for v in by_group.values()).items())),
          'out_of_fold_equal_group_mae': metrics, 'comparison': comparison,
          'baseline_definitions': {'train_mean': 'dimension-wise mean across the 21 remaining prompt groups',
                                   'train_median': 'dimension-wise weighted median with each of 21 remaining groups given weight one'},
          'limitations': ['Post-result TRAIN-only comparator; not confirmation, population inference, or a preselected primary arm.',
                          'Saved model scores and held-out calibration predictions were not newly replayed or generated.',
                          'Fold training sets overlap and all items and six dimensions share annotation dependencies.',
                          'The target-only baselines use no model scores; calibrated predictions use the saved historical endpoint evidence.'],
          'new_provider_calls': 0, 'new_human_labels': 0}
output = (json.dumps(result, sort_keys=True, indent=2) + '\n').encode()
with args.output.open('xb') as f:
    f.write(output)
print(json.dumps({'sha256': sha256(output).hexdigest(), 'metrics': metrics, 'comparison': comparison}))
