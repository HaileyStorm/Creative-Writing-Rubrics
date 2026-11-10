"""Delete-one-story descriptive influence for the already-opened Dryad DEV30."""
from __future__ import annotations
from fractions import Fraction
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import sys
PINS = {'panel': 'cbfc8eea8c5855b1e3cd0c30e5c14c3d53db42869ade3faf6e3b84b99c6f7b6c', 'analysis': '0c91ec3f2c31f40599d74fb250df5a4cbc12b3174ab89b6e743db7f6d1836c28', 'published_aggregate': '43bc7afc5ec7ab389d1dddb965c83ad49d312727e0780dc6eecca4b6881ea505'}
AXES = ('well_written', 'enjoyed')

def checked(path, digest):
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != digest:
        raise ValueError('Source hash mismatch: ' + path.name)
    return raw

def encoded(value):
    return (json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, indent=2) + '\n').encode()

def sign_counts(values):
    return {'positive': sum((v is not None and v > 0 for v in values)), 'zero': sum((v == 0 for v in values)), 'negative': sum((v is not None and v < 0 for v in values)), 'undefined': sum((v is None for v in values))}

def calculate():
    if sys.flags.optimize:
        raise ValueError('Run without optimization')
    panel = json.loads(checked(PANEL, PINS['panel']))
    source = checked(PUBLISHED / 'analysis.py', PINS['analysis'])
    published = json.loads(checked(PUBLISHED / 'aggregates.json', PINS['published_aggregate']))
    spec = importlib.util.spec_from_file_location('dryad_pinned_published_analysis', PUBLISHED / 'analysis.py')
    analysis = importlib.util.module_from_spec(spec)
    exec(compile(source, str(PUBLISHED / 'analysis.py'), 'exec'), analysis.__dict__)
    assert len(panel) == 30 and len({r['pass_id'] for r in panel}) == 30
    assert len({r['opaque_story_id'] for r in panel}) == 30
    assert all((type(r['score']) in (int, float) and math.isfinite(r['score']) and (0 <= r['score'] <= 100) for r in panel))
    model = [Fraction(str(row['score'])) for row in panel]
    targets = {axis: [analysis.fraction(row['axis_means'][axis]) for row in panel] for axis in AXES}
    baselines = {axis: analysis.rho(model, targets[axis]) for axis in AXES}
    assert all((baselines[axis] == published['associations'][axis]['rho'] for axis in AXES))
    report = {}
    for axis in AXES:
        values = [analysis.rho(model[:i] + model[i + 1:], targets[axis][:i] + targets[axis][i + 1:]) for i in range(30)]
        defined = [value for value in values if value is not None]
        shifts = [None if value is None else value - baselines[axis] for value in values]
        defined_shifts = [value for value in shifts if value is not None]
        report[axis] = {'baseline_stories': 30, 'stories_each_deletion': 29, 'baseline_rho': baselines[axis], 'published_baseline_reproduced_exactly': True, 'planned_deletions': 30, 'defined_deletions': len(defined), 'undefined_deletions': 30 - len(defined), 'minimum_delete_one_rho': min(defined) if defined else None, 'maximum_delete_one_rho': max(defined) if defined else None, 'maximum_absolute_shift': max(map(abs, defined_shifts)) if defined_shifts else None, 'minimum_signed_shift': min(defined_shifts) if defined_shifts else None, 'maximum_signed_shift': max(defined_shifts) if defined_shifts else None, 'coefficient_sign_counts': sign_counts(values), 'shift_sign_counts': sign_counts(shifts), 'delete_one_rho_sorted': sorted(defined) + [None] * (30 - len(defined))}
    result = {'state': 'RETROSPECTIVE_DEV30_DELETE_ONE_STORY_INFLUENCE', 'source_sha256': PINS, 'axes': report, 'rank_rule': 'Pinned published Fraction targets and Fraction(str(score)); average tied ranks; Pearson correlation of ranks; rerank each29-story subset.', 'distribution_order': 'Separate ascending numeric distributions per axis; no deletion identities or cross-axis deletion mapping.', 'provider_calls': 0, 'new_human_labels': 0, 'confirmation_opened': False, 'candidate_promoted': False, 'canonical_scorer_calls': 0, 'limits': ['Observational sensitivity of a previously selected, already-opened30-story development cohort; no held-out or prospective claim.', 'One deletion measures local influence only. It does not establish generalization, causal effect, significance or a population confidence interval.', 'Story observations and mean human targets may share evaluators, topics and conditions; deletion does not model crossed-rater or cluster dependence.', 'The original100-story reduction followed partial model observation; selection and original unmet study/coverage/native-provenance gates remain unchanged.', 'No candidate, comparator or winner was selected or promoted. Historical account/model/receipt limitations remain.']}
    raw = encoded(result)
    for row in panel:
        assert row['pass_id'].encode() not in raw and row['opaque_story_id'].encode() not in raw
    return result

import argparse
def main():
    global PANEL,PUBLISHED
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--private-panel',type=Path,required=True)
    parser.add_argument('--published-dryad-dir',type=Path,required=True)
    parser.add_argument('--output-dir',type=Path,required=True)
    args=parser.parse_args()
    PANEL=args.private_panel; PUBLISHED=args.published_dryad_dir
    paths={'panel':PANEL,'analysis':PUBLISHED/'analysis.py','published_aggregate':PUBLISHED/'aggregates.json'}
    originals={key:checked(path,PINS[key]) for key,path in paths.items()}
    result=calculate()
    publish(args.output_dir,result,paths,originals)

def publish(directory,result,paths,originals):
    if directory.exists():
        raise ValueError('Use an unused create-only output directory')
    for key,path in paths.items():
        if path.read_bytes()!=originals[key]:
            raise ValueError('Input bytes changed during analysis')
    raw=(json.dumps(result,indent=2,sort_keys=True,ensure_ascii=False,allow_nan=False)+'\n').encode()
    directory.mkdir(parents=True,exist_ok=False)
    with (directory/'aggregate.json').open('xb') as handle: handle.write(raw)
    receipt={'state':'RECOMPUTED_FROM_EXPLICIT_PINNED_INPUTS','aggregate':{'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)},
             'adapter_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
             'inputs':{key:{'sha256':hashlib.sha256(value).hexdigest(),'bytes':len(value)} for key,value in originals.items()},
             'input_bytes_rechecked':True}
    with (directory/'receipt.json').open('x',encoding='utf-8') as handle:
        handle.write(json.dumps(receipt,indent=2,sort_keys=True)+'\n')

if __name__=='__main__':
    main()
