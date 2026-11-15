"""Opt-in, guarded scorer-only completion extrema for fully supplied verdict banks.

Raises ValueError unless the fixed-activity, dependency and work guards hold.
Not a new judgment, human validation, or a statistical confidence interval.
"""
from collections import defaultdict
import copy
import hashlib
import itertools
import json
import math
from pathlib import Path
from . import core, scoring_v2

CORE_SHA256 = '8c6022efc005f45e40df2ca9e7f8d508c50af6ae7197384b5798773ea968162a'
MAX_GROUP_ASSIGNMENTS = 531441
MAX_WORK_UNITS = 50000000
STATES = ('NO', 'YES', 'NOT_APPLICABLE')

def require(value, message):
    if not value:
        raise ValueError(message)

def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode('utf-8')).hexdigest()

def grouped_completion_envelope(modules, bundle, verdicts, artifact, contract):
    if hashlib.sha256(Path(core.__file__).read_bytes()).hexdigest() != CORE_SHA256:
        raise ValueError('unsupported core implementation')
    before = _digest((modules, bundle, verdicts, artifact, contract))
    scoring_v2.validate_import_admission(modules, bundle, verdicts, artifact_id=artifact,
                                         task_contract=contract, admission_policy='strict_import_v2')
    compiled = core.compile_bundle(modules, bundle, task_contract=contract)
    selected = core.compiled_questions(compiled)
    ids = [r['question']['id'] for r in selected]
    require(len(ids) == len(set(ids)) == len(verdicts), 'duplicate or omitted selected question')
    base = {r['question_id']: r['verdict'] for r in verdicts}
    require(set(base) == set(ids), 'verdict membership differs')
    baseline = core.score_bundle(modules, bundle, verdicts, artifact_id=artifact, task_contract=contract)
    require(baseline['hard_gate_status'] == 'VALID', 'gate not fixed valid')
    require(all(base[r['question']['id']] != 'CANNOT_ASSESS' for r in compiled['hard_gates']), 'unknown gate')
    domains = defaultdict(list)
    ladder_domains = defaultdict(set)
    for r in compiled['domain_questions']:
        domains[str(r['domain_id'])].append(r)
        if r['question'].get('question_type') == 'subjective_threshold':
            ladder_domains[r['module_id']].add(str(r['domain_id']))
    require(all(len(v) == 1 for v in ladder_domains.values()), 'ladder crosses domains')
    meta = {str(x['domain_id']): x for x in bundle['domains']}
    require(set(domains) == set(meta), 'empty or missing domain')
    points = [float(meta[k]['points']) for k in meta]
    require(all(math.isfinite(x) and x >= 0 for x in points) and 0 < sum(points) < 1e100, 'unsupported domain points')
    require(math.isfinite(100.0 / sum(points)), 'unsupported normalization')
    groups = []
    for domain, rows in domains.items():
        # A fixed assessed question keeps this domain active and assessed for
        # every completion, including all-N/A substitutions elsewhere.
        require(any(base[r['question']['id']] in ('YES', 'NO') for r in rows), 'domain could become inactive')
        groups.append(('domain', domain, float(meta[domain]['points']), rows))
    penalties = compiled['penalty_groups']
    require(len({r['module_id'] for r in penalties}) == len(penalties), 'duplicate penalty groups')
    groups.extend(('penalty', r['module_id'], float(r['cap_points']), r['questions']) for r in penalties)
    require(all(math.isfinite(cap) and cap >= 0 for _, _, cap, _ in groups), 'unsupported group weight')
    estimated = sum(3 ** sum(base[r['question']['id']] == 'CANNOT_ASSESS' for r in rows) for _, _, _, rows in groups)
    require(estimated <= MAX_GROUP_ASSIGNMENTS and estimated * len(selected) <= MAX_WORK_UNITS,
            'grouped calculation exceeds work limit')
    extrema, group_work, all_unknown = [], 0, set()
    for kind, group_id, amount, rows in groups:
        unknown = [r['question']['id'] for r in rows if base[r['question']['id']] == 'CANNOT_ASSESS']
        require(not (set(unknown) & all_unknown), 'unknown spans scoring groups')
        all_unknown.update(unknown)
        require(len(unknown) <= 12, 'group exceeds bounded local search')
        low = high = None
        for assignment in itertools.product(STATES, repeat=len(unknown)):
            effective = dict(base)
            effective.update(zip(unknown, assignment))
            core._enforce_subjective_ladders(compiled, effective, [])
            passed = failed = 0.0
            for r in rows:
                weight = float(r['effective_weight'])
                require(math.isfinite(weight) and 0 < weight < 1e100, 'unsupported effective weight')
                state = effective[r['question']['id']]
                if state == 'YES': passed += weight
                elif state == 'NO': failed += weight
                elif state != 'NOT_APPLICABLE':
                    raise ValueError('scoring group remains unresolved')
            assessed = passed + failed
            if kind == 'domain':
                require(assessed > 0, 'domain lost assessment')
                contribution = core._weighted_share(amount, passed, assessed)
            else:
                contribution = core._weighted_share(amount, failed, assessed) if assessed else 0.0
            require(math.isfinite(contribution), 'nonfinite group contribution')
            if low is None or contribution < low[0]: low = (contribution, assignment)
            if high is None or contribution > high[0]: high = (contribution, assignment)
        group_work += 3 ** len(unknown)
        # A larger penalty reduces final score; domains act in the other direction.
        extrema.append((unknown, low[1] if kind == 'domain' else high[1],
                        high[1] if kind == 'domain' else low[1]))
    scored = {r['question']['id'] for r in selected if r['role'] != 'supplemental'}
    require(all_unknown == {q for q in scored if base[q] == 'CANNOT_ASSESS'}, 'scored unknown omitted')
    bounds = []
    for side in (1, 2):
        candidate = copy.deepcopy(verdicts)
        by_id = {r['question_id']: r for r in candidate}
        for unknown, low, high in extrema:
            for qid, state in zip(unknown, (low, high)[side-1]):
                by_id[qid]['verdict'] = state
        report = core.score_bundle(modules, bundle, candidate, artifact_id=artifact, task_contract=contract)
        require(report['status'] == 'SCORED' and report['hard_gate_status'] == 'VALID', 'extremum not scored')
        bounds.append(report['final_score']['observed'])
    require(bounds[0] <= bounds[1], 'extrema inverted')
    require(before == _digest((modules, bundle, verdicts, artifact, contract)), 'input mutation detected')
    return {'policy': 'guarded_grouped_completion_v1', 'core_sha256': CORE_SHA256, 'input_sha256': before,
            'historical_status': baseline['status'], 'historical_final_score': baseline['final_score'],
            'lower': bounds[0], 'upper': bounds[1], 'score_unknowns': len(all_unknown),
            'group_assignments_checked': group_work, 'estimated_work_units': estimated * len(selected),
            'maximum_work_units': MAX_WORK_UNITS, 'full_assignments': 3 ** len(all_unknown),
            'fixed_domain_assessment': True, 'fixed_valid_gates': True, 'cross_domain_ladders': False}
