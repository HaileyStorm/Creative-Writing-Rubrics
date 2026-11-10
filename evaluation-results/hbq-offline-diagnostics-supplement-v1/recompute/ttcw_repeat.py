"""Aggregate-only offline stratification of two pinned, selected TTCW repeat banks."""
import argparse
from collections import Counter
from fractions import Fraction
import hashlib
import json
from pathlib import Path
PINS = {'initial_saved_view': ('initial_view', 26253882, 'cbf6192a025521990b17cb3c3f4d2c56e9443eb0ac3084a85eba8fcee9be96f4'), 'selected_repeat_saved_view': ('repeat_view', 961821, '3755acbab8cb8893563575e976e392b683a44474fac176d6b84cbe1a644104e1')}
STATES = ('YES', 'NO', 'NOT_APPLICABLE', 'CANNOT_ASSESS')
STRATA = ('stable', 'yes_no_flip', 'applicability_change', 'cannot_assess_change')

def require(value, message):
    if not value:
        raise RuntimeError(message)

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def evidence_set(row):
    return frozenset((json.dumps(item, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False) for item in row['evidence']))

def banks(view):
    result = {}
    for record in view['records']:
        if record['arm'] != 'hbq':
            continue
        require(record['semantic_acceptance']['accepted'] is True and (not record['semantic_acceptance']['errors']), 'Saved semantic acceptance')
        descriptor = record['condition_descriptor']
        rows = record['response']['verdicts']
        require([row['question_id'] for row in rows] == descriptor['question_ids'], 'Exact per-packet saved ID order')
        sid = descriptor['story_id']
        bank = result.setdefault(sid, {'records': {}, 'packets': []})
        for row in rows:
            qid = row['question_id']
            require(qid not in bank['records'] and row['verdict'] in STATES, 'Unique exact bank IDs and known states')
            bank['records'][qid] = row
        bank['packets'].append(descriptor)
    return result

def stratum(left, right):
    if left == right:
        return 'stable'
    if 'CANNOT_ASSESS' in (left, right):
        return 'cannot_assess_change'
    if set((left, right)) == {'YES', 'NO'}:
        return 'yes_no_flip'
    require('NOT_APPLICABLE' in (left, right), 'Exhaustive transition strata')
    return 'applicability_change'

def summarize(pairs):
    equal = nonempty_intersection = empty_union = 0
    jaccards = []
    for left, right in pairs:
        a, b = (evidence_set(left), evidence_set(right))
        equal += a == b
        intersection, union = (a & b, a | b)
        nonempty_intersection += bool(intersection)
        if union:
            jaccards.append(Fraction(len(intersection), len(union)))
        else:
            empty_union += 1
    mean = sum(jaccards, Fraction()) / len(jaccards) if jaccards else None
    return {'matched_leaf_pairs': len(pairs), 'exact_evidence_sets_equal': equal, 'exact_evidence_sets_unequal': len(pairs) - equal, 'nonempty_exact_evidence_intersection': nonempty_intersection, 'empty_evidence_unions': empty_union, 'jaccard_defined_pairs': len(jaccards), 'mean_exact_set_jaccard': float(mean) if mean is not None else None, 'mean_exact_set_jaccard_fraction': {'numerator': mean.numerator, 'denominator': mean.denominator} if mean is not None else None}

def analyze(initial, repeated):
    before, after = (banks(initial), banks(repeated))
    common = sorted(set(before) & set(after))
    require(len(common) == len(after) == 2, 'Exactly two selected common HBQ works')
    output = []
    changed_sets = []
    pooled = {key: [] for key in STRATA}
    pooled_stable_states = {key: [] for key in STATES}
    common_questions = None
    for ordinal, sid in enumerate(common, 1):
        a, b = (before[sid], after[sid])
        require(len(a['packets']) == len(b['packets']) == 23, '23 packets per selected saved bank')
        require(set(a['records']) == set(b['records']) and len(a['records']) == 178, 'Exactly 178 matched bank question IDs')
        qids = set(a['records'])
        if common_questions is None:
            common_questions = qids
        require(qids == common_questions, 'Same 178 question identities across the two works')
        initial_packets = {frozenset(p['question_ids']): p for p in a['packets']}
        repeat_packets = {frozenset(p['question_ids']): p for p in b['packets']}
        require(len(initial_packets) == len(repeat_packets) == 23 and initial_packets.keys() == repeat_packets.keys(), 'Same packet membership')
        for members, packet in initial_packets.items():
            peer = repeat_packets[members]
            require(all((packet[key] == peer[key] for key in ('prompt_sha256', 'schema_sha256', 'question_ids', 'bundle_id', 'sources'))), 'Saved prompt/schema/source descriptors match across each repeat')
        strata = {key: [] for key in STRATA}
        stable_states = {key: [] for key in STATES}
        changed = set()
        for qid in qids:
            left, right = (a['records'][qid], b['records'][qid])
            key = stratum(left['verdict'], right['verdict'])
            strata[key].append((left, right))
            pooled[key].append((left, right))
            if key == 'stable':
                stable_states[left['verdict']].append((left, right))
                pooled_stable_states[left['verdict']].append((left, right))
            else:
                changed.add(qid)
        changed_sets.append(changed)
        output.append({'bank': f'bank_{ordinal:02d}', 'matched_packets': 23, 'matched_leaf_pairs': 178, 'state_changes': len(changed), 'strata': {key: summarize(strata[key]) for key in STRATA}, 'stable_by_state': {key: summarize(stable_states[key]) for key in STATES}})
    require([row['state_changes'] for row in output] == [8, 10], 'Reproduce saved 8/10 changes')
    recurrence = Counter((sum((qid in changed for changed in changed_sets)) for qid in common_questions))
    require(sum(recurrence.values()) == 178, 'Complete recurrence denominator')
    all_pairs = [pair for pairs in pooled.values() for pair in pairs]
    require(summarize(all_pairs)['exact_evidence_sets_equal'] == 9, 'Reproduce 9/356 overall evidence equality')
    return {'state': 'POST_HOC_OFFLINE_SELECTED_REPEAT_DIAGNOSTIC', 'banks': output, 'combined': {'matched_leaf_pairs': 356, 'strata': {key: summarize(pooled[key]) for key in STRATA}, 'stable_by_state': {key: summarize(pooled_stable_states[key]) for key in STATES}, 'all_pairs': summarize(all_pairs)}, 'question_recurrence': {'matched_question_identities': 178, 'changed_in_neither_work_pair': recurrence[0], 'changed_in_exactly_one_work_pair': recurrence[1], 'changed_in_both_work_pairs': recurrence[2], 'distinct_questions_changed': recurrence[1] + recurrence[2]}, 'definitions': {'evidence_set': 'Unordered set of exact canonical JSON evidence objects; all fields retained, item order and duplicates ignored; no text normalization.', 'jaccard': 'Exact evidence-object intersection size / union size. Empty union is undefined/null and excluded from the mean; zero-pair strata have null means.', 'bank_order': 'Lexical ordering of private selected work IDs, used only to reproduce the saved anonymous bank order.', 'applicability_change': 'Any unequal state pair containing NOT_APPLICABLE and no CANNOT_ASSESS.', 'cannot_assess_change': 'Any unequal state pair containing CANNOT_ASSESS.'}, 'limits': ['Two selected works; leaves and repeated question identities are dependent, not population replicates.', 'Post-hoc stratification and question recurrence add to prior unconditional equality/Jaccard summaries; no new preregistration.', 'Exact evidence-object turnover is not semantic reasoning turnover, validity, support quality or causality. A reference or summary edit makes an object unequal.', 'The one recurrently changed question is not by itself evidence of a general rubric defect.', 'Saved descriptor equality is not fresh native validation, current-account equivalence or sampler/backend attestation.'], 'provider_calls': 0, 'native_replays': 0, 'semantic_validations': 0, 'score_calls': 0, 'human_target_reads': 0, 'promotion': 'none'}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--initial-view',type=Path,required=True)
    parser.add_argument('--repeat-view',type=Path,required=True)
    parser.add_argument('--output-dir',type=Path,required=True)
    args=parser.parse_args()
    paths={'initial_saved_view':args.initial_view,'selected_repeat_saved_view':args.repeat_view}
    originals={key:path.read_bytes() for key,path in paths.items()}
    for key,raw in originals.items():
        _,size,pin=PINS[key]
        require(len(raw)==size and sha(raw)==pin,'Exact saved-view input required')
    result=analyze(json.loads(originals['initial_saved_view']),json.loads(originals['selected_repeat_saved_view']))
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
