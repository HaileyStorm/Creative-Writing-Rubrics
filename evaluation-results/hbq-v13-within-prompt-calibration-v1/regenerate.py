"""Add target-only cross-validation baselines to the opened V13 TRAIN study."""
import argparse
import itertools
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
groups, dims = by_group, DIMS

all_counts, group_means = Counter(), []
multi_groups = 0
for gid, cells in groups.items():
    if len(cells) < 2:
        continue
    multi_groups += 1
    predictions = {x['cell_id']: x['scores'] for x in folds[gid]['heldout_predictions']}
    if set(predictions) != {x['cell_id'] for x in cells}:
        raise ValueError('heldout predictions changed')
    group = Counter()
    for left, right in itertools.combinations(cells, 2):
        for dim in dims:
            a, b = Fraction(str(left['target'][dim])), Fraction(str(right['target'][dim]))
            x = Fraction(str(predictions[left['cell_id']][dim]))
            y = Fraction(str(predictions[right['cell_id']][dim]))
            if a == b:
                outcome = 'reference_tie'
            elif x == y:
                outcome = 'prediction_tie'
            elif (a > b) == (x > y):
                outcome = 'concordant'
            else:
                outcome = 'discordant'
            group[outcome] += 1
            all_counts[outcome] += 1
    n = group['concordant'] + group['discordant'] + group['prediction_tie']
    if n:
        group_means.append(Fraction(2 * group['concordant'] + group['prediction_tie'], 2*n))

if multi_groups != 10 or sum(all_counts.values()) != 240:
    raise ValueError('within-prompt geometry changed')
n = all_counts['concordant'] + all_counts['discordant'] + all_counts['prediction_tie']
out = {'source_sha256': PINS,
       'cohort': {'planned_works': 44, 'prompt_groups': 22, 'multi_item_groups': multi_groups,
                  'within_prompt_work_pairs': 40, 'dimensions': 6, 'pair_dimension_cells': 240},
       'counts': dict(all_counts),
       'calibrated_direction_agreement_half_for_prediction_ties': float(Fraction(2*all_counts['concordant'] + all_counts['prediction_tie'], 2*n)) if n else None,
       'constant_baseline_direction_agreement_half_for_prediction_ties': 0.5 if n else None,
       'eligible_reference_nontied_pair_dimension_cells': n,
       'equal_multi_item_group_mean_agreement': float(sum(group_means, Fraction()) / len(group_means)) if group_means else None,
       'groups_with_nontied_reference_cells': len(group_means),
       'limits': ['Post-result TRAIN analysis of saved held-out predictions; not confirmation or a preselected estimand.',
                  'Target-only baselines are constant within each prompt and dimension, so their pair predictions tie.',
                  'Pair/dimension cells share stories, prompts, dimensions, raters and overlapping training folds.',
                  'Human reference ties are excluded from directional accuracy and prediction ties get half credit.',
                  'These ranks do not establish human validation, practical utility, population generalization or improvement.'],
       'provider_calls': 0, 'new_human_labels': 0}
encoded = (json.dumps(out, sort_keys=True, indent=2) + '\n').encode()
with args.output.open('xb') as f:
    f.write(encoded)
print(json.dumps({'sha256': sha256(encoded).hexdigest(), 'counts': out['counts'],
                  'agreement': out['calibrated_direction_agreement_half_for_prediction_ties'],
                  'equal_group_agreement': out['equal_multi_item_group_mean_agreement']}))
