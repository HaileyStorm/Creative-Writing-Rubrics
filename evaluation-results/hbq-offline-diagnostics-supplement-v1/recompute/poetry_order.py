"""Private post-hoc scalar ordering transitions in four saved poetry families."""
import argparse
from collections import Counter
from fractions import Fraction
import hashlib
from itertools import combinations
import json
from pathlib import Path
REPORT_SHA = '4fea1950e29aad7442d37ae0ce9dbdbfc091069e53131261e7455f2e85cc46d7'
ANALYSIS_SHA = '3683a689c7a7d63d069067faf75ded1f1ded1a95856493ff5d944d78a34a501c'
ARMS = ('hbq', 'holistic', 'compact', 'poemetric')
KINDS = ('missing', 'stable_strict', 'stable_tie', 'strict_reversal', 'tie_entry', 'tie_exit')

def require(ok, message):
    if not ok:
        raise RuntimeError(message)

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def summary(items):
    counts = Counter(items)
    return {'planned': len(items), 'observed': len(items) - counts['missing'], **{key: counts[key] for key in KINDS}, 'tie_change': counts['tie_entry'] + counts['tie_exit']}

def sign(value):
    return (value > 0) - (value < 0)

def classify(scores):
    if any((value is None for value in scores)):
        return 'missing'
    a, b, c, d = (Fraction(str(value)) for value in scores)
    old, new = (sign(a - b), sign(c - d))
    if old == new:
        return 'stable_tie' if old == 0 else 'stable_strict'
    if old == 0:
        return 'tie_exit'
    if new == 0:
        return 'tie_entry'
    return 'strict_reversal'

def analyze(report):
    profiles = report['full_bank_profiles']
    families = {}
    hbq = {}
    for row in profiles:
        require(row['scope'] == 'full_bank', 'Only full banks')
        require((row['status'] == 'SCORED') == (row['eligible_scalar'] is not None), 'Saved scalar eligibility')
        if row['status'] == 'SCORED':
            require(row['complete_original_bank'], 'Scored whole bank')
            require(row['eligible_scalar'] == row['full_report']['final_score']['observed'], 'Saved observed scalar')
        item = families.setdefault(row['family_id'], {'ids': set(), 'forms': set()})
        item['ids'].add(row['artifact_id'])
        item['forms'].add(row['bundle_id'])
        key = (row['artifact_id'], row['repeat'])
        require(key not in hbq, 'Unique bank/cycle')
        hbq[key] = row['eligible_scalar']
    require(len(profiles) == 36 and len(families) == 4, 'Frozen four-family sentinel population')
    lookup = {'hbq': hbq}
    for arm in ARMS[1:]:
        rows = [r for r in report['native_comparator_profiles'] if r['arm'] == arm]
        values = {}
        for row in rows:
            require((row['state'] == 'assessed') == (row['score'] is not None), 'Saved comparator eligibility')
            key = (row['artifact_id'], row['repeat'])
            require(key not in values, 'Unique comparator/cycle')
            values[key] = row['score']
        lookup[arm] = values
    transitions = {arm: [] for arm in ARMS}
    form_counts = Counter()
    for family in families.values():
        require(len(family['ids']) == 3 and len(family['forms']) == 1, 'Three variants with one fixed form')
        form = next(iter(family['forms']))
        form_counts[form] += 1
        for left, right in combinations(sorted(family['ids']), 2):
            for old, new in combinations(range(3), 2):
                for arm in ARMS:
                    values = lookup[arm]
                    keys = ((left, old), (right, old), (left, new), (right, new))
                    require(all((key in values for key in keys)), 'All planned profile rows present; missing scores explicit')
                    kind = classify([values[key] for key in keys])
                    transitions[arm].append((form, f'{old}-{new}', kind))
    arms = {}
    for arm, rows in transitions.items():
        require(len(rows) == 36, '36 planned pair-cycle contrasts')
        arms[arm] = {'overall': summary([x[2] for x in rows]), 'by_cycle_contrast': {key: summary([x[2] for x in rows if x[1] == key]) for key in ('0-1', '0-2', '1-2')}, 'by_form': {form: summary([x[2] for x in rows if x[0] == form]) for form in sorted(form_counts)}, 'by_form_and_cycle_contrast': {form: {key: summary([x[2] for x in rows if x[:2] == (form, key)]) for key in ('0-1', '0-2', '1-2')} for form in sorted(form_counts)}}
    return {'state': 'POST_HOC_OFFLINE_SELECTED_POETRY_SCALAR_ORDER_DIAGNOSTIC', 'families': 4, 'variants_per_family': 3, 'cycles': [0, 1, 2], 'family_counts_by_form': dict(sorted(form_counts.items())), 'arms': arms, 'definitions': {'population': 'Exactly the four families represented by saved full_bank_profiles; comparator-only families excluded.', 'comparison': 'Unordered variant pair within a family, contrasted over two cycles. Both pair members must have eligible scores in both cycles.', 'score': 'Saved eligible_scalar for SCORED complete HBQ banks; saved score for assessed comparator rows. Fraction(str(value)) preserves the serialized numeric value.', 'strict_reversal': 'Both cycles have unequal pair scores and their signs differ.', 'tie_entry': 'Earlier cycle strict ordering becomes an exact tie.', 'tie_exit': 'Earlier cycle exact tie becomes strict ordering.', 'missing': 'At least one of the four required eligible saved scores is null; never imputed.'}, 'limits': ['Four selected synthetic families, shared artifacts and dependent cycle contrasts; not population reliability.', 'Unequal availability and tied score compression prevent arm-winner or equivalence claims.', 'Scalar-induced ordering is distinct from direct pairwise judgments and from literary correctness.', 'Creator variant roles provide no quality oracle; no human alignment, causal improvement or promotion established.', 'Historical report qualifications remain; no new current-account, sampler or native-runtime qualification.'], 'provider_calls': 0, 'scorer_calls': 0, 'native_replays': 0, 'held_out_target_reads': 0, 'promotion': 'none'}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report',type=Path,required=True)
    parser.add_argument('--eligibility-analysis',type=Path,required=True)
    parser.add_argument('--output-dir',type=Path,required=True)
    args=parser.parse_args()
    paths={'report':args.report,'eligibility_analysis':args.eligibility_analysis}
    originals={key:path.read_bytes() for key,path in paths.items()}
    require(len(originals['report'])==5426453 and sha(originals['report'])==REPORT_SHA,'Pinned report')
    require(sha(originals['eligibility_analysis'])==ANALYSIS_SHA,'Pinned eligibility source')
    result=analyze(json.loads(originals['report']))
    result['sources']={key:{'sha256':sha(raw),'bytes':len(raw)} for key,raw in originals.items()}
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
