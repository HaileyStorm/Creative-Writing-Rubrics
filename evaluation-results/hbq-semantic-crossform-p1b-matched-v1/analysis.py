"""Provider-free descriptive analysis; no oracle labels or candidate inference."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from itertools import combinations
import json
from pathlib import Path
import statistics
import sys

HERE = Path(__file__).resolve().parent
import importlib.util

_spec = importlib.util.spec_from_file_location('descriptive_p1b_analysis_collector', HERE / 'collector.py')
c = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(c)
POLICY = 'descriptive_crossform_analysis_v1'
MANIFEST_SHA = '4e139dc1ef859be838cbe9ee8c579285845074032c6a00867a1b03859fdec2ff'
TOKEN_FIELDS = ('input_tokens', 'cached_input_tokens', 'output_tokens')


def fraction(numerator, denominator):
    return numerator / denominator if denominator else None


def mean(values):
    return statistics.mean(values) if values else None


def agreement(left, right, expected):
    c.require(len(left) == len(right), 'Agreement requires paired observations')
    n = len(left)
    observed = fraction(sum(a == b for a, b in zip(left, right)), n)
    lc, rc = Counter(left), Counter(right)
    chance = sum(lc[k] * rc[k] for k in lc.keys() | rc.keys()) / (n * n) if n else None
    kappa = (observed - chance) / (1 - chance) if chance is not None and chance < 1 else None
    return {'planned_paired_units': expected, 'paired_observed_units': n, 'missing_pairs': expected - n,
            'raw_agreement': observed, 'cohen_kappa': kappa,
            'kappa_limit': 'Unavailable with no paired observations or degenerate chance agreement; descriptive only'}


def scalar_differences(left, right, expected):
    deltas = [b - a for a, b in zip(left, right)]
    return {'planned_pairs': expected, 'observed_pairs': len(deltas), 'missing_pairs': expected - len(deltas),
            'mean_signed_right_minus_left': mean(deltas), 'mean_absolute_native_difference': mean([abs(d) for d in deltas]),
            'exact_agreement': fraction(sum(d == 0 for d in deltas), len(deltas))}


def native_metrics(sample, row, terminal):
    result = {**{field: None for field in TOKEN_FIELDS}, 'latency_seconds': None,
              'basis': 'Native latency not attested; tokens unavailable unless own completed-turn usage is replayed'}
    # Only this verified native event contract exposes sample-scoped token fields.
    # Adapter wall time, campaign clocks and opaque Grok usage are not native latency/tokens.
    if row['endpoint'] == 'sol' and terminal['state'] in c.SETTLED:
        provider = json.loads((sample / 'native-result.json').read_bytes())
        metadata = provider['provider_artifacts']['codex_events']
        raw = c.pinned(sample, metadata['path'], metadata)
        rows = [json.loads(line) for line in raw.splitlines() if line.strip()]
        completed = [r for r in rows if r.get('type') == 'turn.completed']
        if len(completed) == 1:
            usage = completed[0].get('usage', {})
            for field in TOKEN_FIELDS:
                value = usage.get(field)
                if type(value) is int and value >= 0:
                    result[field] = value
            result['basis'] = 'Own native completed-turn event usage after collector receipt replay; latency unavailable'
    return result


def collect_evidence(manifest, manifest_sha, root, results, tools, subset, validator, receipts):
    admitted, inventory, commitments = [], [], []
    for endpoint in c.ENDPOINTS:
        output = results[endpoint]
        binding = None
        binding_valid = True
        if output.exists():
            try:
                binding = c.verify_job_binding(output, manifest, root, manifest_sha, endpoint, tools)
            except (ValueError, OSError, KeyError, TypeError):
                binding_valid = False
        for row in (r for r in manifest['requests'] if r['endpoint'] == endpoint):
            sample = c.sample_path(output, row)
            item = {'request': row, 'state': 'untouched', 'native_metrics': {field: None for field in (*TOKEN_FIELDS, 'latency_seconds')}}
            if not binding_valid:
                item['state'] = 'job_unadmitted'
            elif not sample.exists():
                pass
            elif not (sample / 'terminal.json').is_file():
                item['state'] = 'started_unresolved'
            else:
                try:
                    terminal, answer = c.replay(sample, row, manifest, binding, root, receipts, subset, validator)
                    item['state'] = terminal['state']
                    item['native_metrics'] = native_metrics(sample, row, terminal)
                    commitments.append({'endpoint': endpoint, 'logical_sample_id': row['logical_sample_id'],
                                        'terminal_sha256': c.digest((sample / 'terminal.json').read_bytes())})
                    if answer is not None:
                        admitted.append({'request': row, 'response': answer})
                except (ValueError, OSError, KeyError, TypeError):
                    item['state'] = 'replay_unadmitted'
            inventory.append(item)
    c.require(len(inventory) == len(manifest['requests']), 'Every planned slot must receive a disposition')
    return admitted, inventory, commitments


def load_hbq(manifest, root):
    sys.path.insert(0, str(c.REPO / 'src'))
    from hbqrs import core, runner, scoring_v2
    for module, name in [(core, 'core.py'), (runner, 'runner.py'), (scoring_v2, 'scoring_v2.py')]:
        c.require(c.digest(Path(module.__file__).read_bytes()) == manifest['artifacts']['implementation/' + name]['sha256'],
                  'Frozen scoring implementation differs')
    modules = core.load_modules(root / 'registry/all_modules.yaml')
    bundles = core.load_bundles(root / 'bundles/all_bundles.yaml')
    return {'core': core, 'runner': runner, 'scorer': scoring_v2, 'modules': modules,
            'bundles': {bid: core.resolve_bundle(bundles, bid) for bid in manifest['bank_counts']}}


def score_bank(planned, admitted, hbq, root, manifest):
    row = planned[0]
    form, bundle_id = row['form'], row['bundle_id']
    frozen = json.loads(c.pinned(root, 'compiled/' + bundle_id + '.json', manifest['artifacts']['compiled/' + bundle_id + '.json']))
    expected = [q['question']['id'] for q in hbq['core'].compiled_questions(frozen)]
    planned_ids = [qid for r in sorted(planned, key=lambda r: r['batch']) for qid in r['question_ids']]
    leaves = [v for item in admitted for v in item['response']['verdicts']]
    states = Counter(v['verdict'] for v in leaves)
    coverage = {'planned_packets': len(planned), 'admitted_packets': len(admitted), 'expected_leaves': len(expected),
                'observed_native_leaves': len(leaves), 'native_states': dict(states),
                'assessed_binary': states['YES'] + states['NO'], 'observed_applicable': len(leaves) - states['NOT_APPLICABLE']}
    coverage['assessed_over_observed_applicable'] = fraction(coverage['assessed_binary'], coverage['observed_applicable'])
    base = {'score': None, 'scale': [0, 100], 'increment': 5, 'native_coverage': coverage,
            'leaf_states': {v['question_id']: v['verdict'] for v in leaves}, 'dimensions': {}}
    _, required_leaves, required_packets = c.FORMS[form]
    admitted_ids = Counter(x['request']['request_sha256'] for x in admitted)
    if (len(planned) != required_packets or len(expected) != required_leaves or len(set(expected)) != required_leaves
            or planned_ids != expected or admitted_ids != Counter(r['request_sha256'] for r in planned)
            or len(leaves) != required_leaves or Counter(v['question_id'] for v in leaves) != Counter(expected)):
        return {**base, 'state': 'incomplete_or_nonunique_full_bank_no_scalar', 'weighted_coverage': None, 'sensitivity_bounds': None}
    contract_meta = row['task_contracts'][0]
    contract = json.loads(c.pinned(root, contract_meta['path'], manifest['artifacts'][contract_meta['path']]))
    compiled = hbq['core'].compile_bundle(hbq['modules'], hbq['bundles'][bundle_id], task_contract=contract)
    c.require(hbq['core'].compiled_questions(compiled) == hbq['core'].compiled_questions(frozen), 'Context-aware compiled bank differs')
    try:
        normalized = []
        for item in sorted(admitted, key=lambda item: item['request']['batch']):
            request = item['request']
            _, _, texts, context = c.inputs(root, manifest, request)
            normalized.extend(hbq['runner']._normalize_batch(item['response'], expected_ids=request['question_ids'],
                artifact_id=row['artifact_id'], bundle_id=bundle_id, judge_id=row['endpoint'],
                run_id=request['logical_sample_id'], artifact_text=texts[row['artifact_id']], context_texts=[context]))
        report = hbq['scorer'].score_bundle(hbq['modules'], hbq['bundles'][bundle_id], normalized,
            artifact_id=row['artifact_id'], task_contract=contract, admission_policy='strict_import_v1')
    except ValueError:
        return {**base, 'state': 'strict_import_unadmitted_no_scalar', 'weighted_coverage': None, 'sensitivity_bounds': None}
    penalties = [{k: p[k] for k in ('module_id', 'coverage')} for p in report['penalties']]
    return {**base, 'score': report['final_score']['observed'] if report['status'] == 'SCORED' else None,
            'state': report['status'], 'weighted_coverage': report['coverage'], 'penalty_coverage': penalties,
            'sensitivity_bounds': {k: report['final_score'][k] for k in ('lower', 'upper')},
            'uncertainty_width': None if report['final_score']['lower'] is None else report['final_score']['upper'] - report['final_score']['lower'],
            'hard_gate_status': report['hard_gate_status']}


def missing_dimensions(arm, schema):
    if arm == 'poemetric':
        return {'item_' + str(i): {'value': None, 'scale': [1, 5], 'increment': 1, 'absence_zero': i in (7, 8)} for i in range(1, 9)}
    if arm not in ('compact', 'oregon'): return {}
    field, id_field, scale = ('dimensions', 'dimension_id', [1, 5]) if arm == 'compact' else ('traits', 'trait_id', [1, 6])
    ids = schema['properties']['result']['properties'][field]['items']['properties'][id_field]['enum']
    return {i: {'value': None, 'scale': scale, 'increment': 1, 'absence_zero': False} for i in ids}


def scalar_profile(arm, response):
    if arm == 'ttcw14':
        leaves = response['verdicts']
        complete = len(leaves) == 14 and all(v['verdict'] in ('YES', 'NO') for v in leaves)
        return {'score': sum(v['verdict'] == 'YES' for v in leaves) / 14 if complete else None,
                'state': 'assessed' if complete else 'partial_abstention_no_complete_score', 'scale': [0, 1], 'increment': 1 / 14,
                'leaf_states': {v['test_id']: v['verdict'] for v in leaves}, 'dimensions': {},
                'primary_basis': 'Derived YES fraction of all fourteen tests; no scalar with any unassessed test'}
    scales = {'holistic': [1, 7], 'compact': [1, 5], 'oregon': [6, 36], 'poemetric': [1, 5]}
    base = {'score': None, 'scale': scales[arm], 'increment': 1, 'leaf_states': {}, 'dimensions': {}}
    if response['status'] == 'CANNOT_ASSESS':
        return {**base, 'state': 'explicit_abstention'}
    result = response['result']
    if arm == 'poemetric':
        dimensions = {'item_' + str(r['item_id']): {'value': r['score'], 'scale': [1, 5], 'increment': 1,
                                                   'absence_zero': r['item_id'] in (7, 8)} for r in result['diagnostics']}
        return {**base, 'state': 'assessed', 'score': result['overall_quality']['score'], 'dimensions': dimensions,
                'primary_basis': 'POEMetric item 10 whole-poem quality only; diagnostics and absence are not aggregated'}
    field = {'holistic': 'score', 'compact': 'overall_score', 'oregon': 'total_score'}[arm]
    dimensions = {}
    if arm == 'compact':
        dimensions = {r['dimension_id']: {'value': r['score'], 'scale': [1, 5], 'increment': 1, 'absence_zero': False}
                      for r in result['dimensions']}
    if arm == 'oregon':
        dimensions = {r['trait_id']: {'value': r['score'], 'scale': [1, 6], 'increment': 1, 'absence_zero': False}
                      for r in result['traits']}
    return {**base, 'state': 'assessed', 'score': result[field], 'dimensions': dimensions}


def profiles(manifest, records, hbq, root):
    planned, admitted = defaultdict(list), defaultdict(list)
    key = lambda r: (r['endpoint'], r['form'], r['arm'], r['artifact_id'], r['repeat'])
    for row in manifest['requests']:
        if row['arm'] != 'pairwise': planned[key(row)].append(row)
    for record in records:
        if record['request']['arm'] != 'pairwise': admitted[key(record['request'])].append(record)
    output = {}
    for identity, rows in planned.items():
        items = admitted[identity]
        if identity[2] == 'hbq':
            output[identity] = score_bank(rows, items, hbq, root, manifest)
        elif len(items) != 1:
            output[identity] = {'score': None, 'state': 'missing_unadmitted_no_scalar', 'leaf_states': {}, 'dimensions': {}}
        else:
            output[identity] = scalar_profile(identity[2], items[0]['response'])
        if identity[2] != 'hbq':
            schema = json.loads(c.pinned(root, rows[0]['schema_path'], manifest['artifacts'][rows[0]['schema_path']]))
            output[identity]['dimensions'] = {**missing_dimensions(identity[2], schema), **output[identity]['dimensions']}
    return output


def distribution(values, scale, increment, planned, absence_zero=False):
    present = [v for v in values if v is not None]
    absence = sum(v == 0 for v in present) if absence_zero else 0
    scores = [v for v in present if not (absence_zero and v == 0)]
    low, high = scale
    return {'planned_items': planned, 'reported_values': len(present), 'missing_or_abstained': planned - len(present),
            'absence_zero': absence if absence_zero else None, 'assessed_nonabsence': len(scores),
            'native_scale': scale, 'near_threshold_increment': increment, 'mean': mean(scores),
            'minimum': min(scores) if scores else None, 'maximum': max(scores) if scores else None,
            'exact_floor': sum(v == low for v in scores), 'exact_ceiling': sum(v == high for v in scores),
            'near_floor_inclusive': sum(v <= low + increment for v in scores),
            'near_ceiling_inclusive': sum(v >= high - increment for v in scores)}


def scalar_diagnostics(item_profiles):
    grouped = defaultdict(list)
    for (endpoint, form, arm, artifact, cycle), profile in item_profiles.items():
        grouped[(endpoint, form, arm, cycle)].append((artifact, profile))
    output = []
    for identity, items in sorted(grouped.items()):
        arm = identity[2]
        scale = {'hbq': [0, 100], 'holistic': [1, 7], 'compact': [1, 5], 'oregon': [6, 36], 'poemetric': [1, 5], 'ttcw14': [0, 1]}[arm]
        increment = 5 if arm == 'hbq' else 1 / 14 if arm == 'ttcw14' else 1
        dimensions = sorted({d for _, p in items for d in p.get('dimensions', {})})
        dimensions_output = {}
        for dimension in dimensions:
            sample = next(p['dimensions'][dimension] for _, p in items if dimension in p.get('dimensions', {}))
            values = [p.get('dimensions', {}).get(dimension, {}).get('value') for _, p in items]
            dimensions_output[dimension] = distribution(values, sample['scale'], sample['increment'], len(items), sample['absence_zero'])
        output.append({'endpoint': identity[0], 'form': identity[1], 'arm': arm, 'cycle': identity[3],
                       'primary': distribution([p['score'] for _, p in items], scale, increment, len(items)),
                       'states': dict(Counter(p['state'] for _, p in items)), 'dimensions': dimensions_output})
    return output


def repeat_diagnostics(item_profiles):
    groups = defaultdict(list)
    for endpoint, form, arm, artifact, cycle in item_profiles:
        if cycle == 2: groups[(endpoint, form, arm)].append(artifact)
    output = []
    for (endpoint, form, arm), artifacts in sorted(groups.items()):
        triples = [all(item_profiles[(endpoint, form, arm, artifact, cycle)]['score'] is not None for cycle in range(3)) for artifact in artifacts]
        pairs = []
        for left_cycle, right_cycle in combinations(range(3), 2):
            scalar_left, scalar_right, native_left, native_right = [], [], [], []
            dimensions = defaultdict(lambda: {'left': [], 'right': [], 'native_left': [], 'native_right': []})
            leaf_expected = 0
            for artifact in artifacts:
                left = item_profiles[(endpoint, form, arm, artifact, left_cycle)]
                right = item_profiles[(endpoint, form, arm, artifact, right_cycle)]
                if left['score'] is not None and right['score'] is not None:
                    scalar_left.append(left['score']); scalar_right.append(right['score'])
                for dimension in left['dimensions'].keys() | right['dimensions'].keys():
                    a, b = left['dimensions'].get(dimension), right['dimensions'].get(dimension)
                    if a and b and a['value'] is not None and b['value'] is not None:
                        dimensions[dimension]['native_left'].append(a['value']); dimensions[dimension]['native_right'].append(b['value'])
                        if not (a['absence_zero'] and 0 in (a['value'], b['value'])):
                            dimensions[dimension]['left'].append(a['value']); dimensions[dimension]['right'].append(b['value'])
                    else:
                        dimensions[dimension]
                leaf_expected += c.FORMS[form][1] if arm == 'hbq' else 14 if arm == 'ttcw14' else 0
                common = left['leaf_states'].keys() & right['leaf_states'].keys()
                for qid in sorted(common):
                    native_left.append(left['leaf_states'][qid]); native_right.append(right['leaf_states'][qid])
            pairs.append({'cycles': [left_cycle, right_cycle], 'primary_native_difference': scalar_differences(scalar_left, scalar_right, len(artifacts)),
                          'native_leaf_state_agreement': agreement(native_left, native_right, leaf_expected) if leaf_expected else None,
                          'dimensions': {d: {'native_nonabsence_difference': scalar_differences(v['left'], v['right'], len(artifacts)),
                                             'native_category_agreement_including_absence': agreement(v['native_left'], v['native_right'], len(artifacts))}
                                         for d, v in sorted(dimensions.items())}})
        output.append({'endpoint': endpoint, 'form': form, 'arm': arm, 'planned_three_cycle_items': len(artifacts),
                       'complete_three_cycle_scalars': sum(triples), 'cycle_pairs': pairs})
    return output


def pairwise_diagnostics(manifest, records):
    planned = {key: r for r in manifest['requests'] if r['arm'] == 'pairwise'
               for key in [(r['endpoint'], r['form'], r['pair_id'], r['repeat'], r['orientation'])]}
    orders = {}
    for item in records:
        row, answer = item['request'], item['response']
        if row['arm'] != 'pairwise': continue
        winner = answer['winner']
        chosen = winner if winner in ('TIE', 'CANNOT_ASSESS') else next(s['id'] for s in row['sources'] if s['side'] == winner)
        orders[(row['endpoint'], row['form'], row['pair_id'], row['repeat'], row['orientation'])] = chosen
    grouped = defaultdict(list)
    for endpoint, form, pair, cycle, orientation in planned:
        if orientation == 'AB': grouped[(endpoint, form, cycle)].append(pair)
    summaries, decisions = [], {}
    for (endpoint, form, cycle), pairs in sorted(grouped.items()):
        states = Counter()
        matches = 0
        assessable = 0
        for pair in pairs:
            left, right = [orders.get((endpoint, form, pair, cycle, orientation)) for orientation in ('AB', 'BA')]
            if left is None or right is None:
                states['missing_orientation'] += 1
            elif 'CANNOT_ASSESS' in (left, right):
                states['explicit_abstention'] += 1
            else:
                assessable += 1
                matches += left == right
                states['consistent_tie' if left == right == 'TIE' else 'consistent_selection' if left == right else 'orientation_conflict'] += 1
                if left == right: decisions[(endpoint, form, pair, cycle)] = left
        summaries.append({'endpoint': endpoint, 'form': form, 'cycle': cycle, 'planned_pairs': len(pairs),
                          'planned_orientations': 2 * len(pairs), 'native_decision_counts': dict(Counter(
                              orders.get((endpoint, form, pair, cycle, orientation), 'MISSING')
                              if orders.get((endpoint, form, pair, cycle, orientation)) in ('TIE', 'CANNOT_ASSESS', None) else 'SELECTED'
                              for pair in pairs for orientation in ('AB', 'BA'))),
                          'states': dict(states), 'assessed_both_orientations': assessable,
                          'orientation_consistency': fraction(matches, assessable)})
    repeat = []
    for endpoint in c.ENDPOINTS:
        for form in c.FORMS:
            pairs = [pair for ep, f, pair, cycle, orientation in planned if ep == endpoint and f == form and cycle == 2 and orientation == 'AB']
            if not pairs: continue
            cycle_pairs = []
            for a, b in combinations(range(3), 2):
                left, right = [], []
                for pair in pairs:
                    l, r = decisions.get((endpoint, form, pair, a)), decisions.get((endpoint, form, pair, b))
                    canonical_left = planned[(endpoint, form, pair, a, 'AB')]['sources'][0]['id']
                    if l is not None and r is not None:
                        label = lambda value: 'TIE' if value == 'TIE' else 'LEFT' if value == canonical_left else 'RIGHT'
                        left.append(label(l)); right.append(label(r))
                cycle_pairs.append({'cycles': [a, b], **agreement(left, right, len(pairs))})
            repeat.append({'endpoint': endpoint, 'form': form, 'planned_three_cycle_pairs': len(pairs),
                           'complete_three_cycle_consistent_decisions': sum(all((endpoint, form, p, cycle) in decisions for cycle in range(3)) for p in pairs),
                           'cycle_pairs': cycle_pairs})
    return {'order': summaries, 'repeat': repeat}, decisions


def matched_contrasts(manifest, item_profiles, decisions):
    interendpoint = []
    groups = defaultdict(list)
    for endpoint, form, arm, artifact, cycle in item_profiles:
        if endpoint == 'sol': groups[(form, arm, cycle)].append(artifact)
    for (form, arm, cycle), artifacts in sorted(groups.items()):
        left, right, ls, rs = [], [], [], []
        dimensions = defaultdict(lambda: {'left': [], 'right': []})
        leaf_expected = 0
        for artifact in artifacts:
            a = item_profiles.get(('grok', form, arm, artifact, cycle))
            b = item_profiles[('sol', form, arm, artifact, cycle)]
            if a is None: continue
            if a['score'] is not None and b['score'] is not None: left.append(a['score']); right.append(b['score'])
            for dimension in a['dimensions'].keys() | b['dimensions'].keys():
                av, bv = a['dimensions'].get(dimension), b['dimensions'].get(dimension)
                if av and bv and av['value'] is not None and bv['value'] is not None and not (av['absence_zero'] and 0 in (av['value'], bv['value'])):
                    dimensions[dimension]['left'].append(av['value']); dimensions[dimension]['right'].append(bv['value'])
                else:
                    dimensions[dimension]
            leaf_expected += c.FORMS[form][1] if arm == 'hbq' else 14 if arm == 'ttcw14' else 0
            for qid in sorted(a['leaf_states'].keys() & b['leaf_states'].keys()): ls.append(a['leaf_states'][qid]); rs.append(b['leaf_states'][qid])
        interendpoint.append({'form': form, 'arm': arm, 'cycle': cycle, 'right_minus_left': 'Sol minus Grok',
                              'scalar': scalar_differences(left, right, len(artifacts)),
                              'dimensions_nonabsence': {d: scalar_differences(v['left'], v['right'], len(artifacts)) for d, v in sorted(dimensions.items())},
                              'native_leaf_state_agreement': agreement(ls, rs, leaf_expected) if leaf_expected else None})
    # Arm comparisons use directions on exact shared pairs, never subtract unlike scales.
    pairs = {}
    for row in manifest['requests']:
        if row['arm'] == 'pairwise' and row['orientation'] == 'AB':
            pairs[(row['form'], row['pair_id'])] = [s['id'] for s in row['sources']]
    contrasts = []
    for endpoint in c.ENDPOINTS:
        for form in c.FORMS:
            scoped = {p: ids for (f, p), ids in pairs.items() if f == form}
            arms = sorted({arm for ep, f, arm, artifact, cycle in item_profiles if ep == endpoint and f == form and cycle == 0} | {'pairwise'})
            directions = {}
            for pair, ids in scoped.items():
                direct = decisions.get((endpoint, form, pair, 0))
                if direct is not None: directions[('pairwise', pair)] = 'TIE' if direct == 'TIE' else 'LEFT' if direct == ids[0] else 'RIGHT'
                for arm in arms:
                    values = [item_profiles.get((endpoint, form, arm, artifact, 0), {}).get('score') for artifact in ids]
                    if all(v is not None for v in values):
                        directions[(arm, pair)] = 'TIE' if values[0] == values[1] else 'LEFT' if values[0] > values[1] else 'RIGHT'
            for a, b in combinations(arms, 2):
                common = [p for p in scoped if (a, p) in directions and (b, p) in directions]
                contrasts.append({'endpoint': endpoint, 'form': form, 'arms': [a, b], 'cycle': 0,
                                  **agreement([directions[(a, p)] for p in common], [directions[(b, p)] for p in common], len(scoped))})
    pair_interendpoint = []
    for form in c.FORMS:
        scoped = [p for f, p in pairs if f == form]
        common = [p for p in scoped if ('grok', form, p, 0) in decisions and ('sol', form, p, 0) in decisions]
        label = lambda ep, pair: 'TIE' if decisions[(ep, form, pair, 0)] == 'TIE' else 'LEFT' if decisions[(ep, form, pair, 0)] == pairs[(form, pair)][0] else 'RIGHT'
        pair_interendpoint.append({'form': form, 'cycle': 0, **agreement([label('grok', p) for p in common], [label('sol', p) for p in common], len(scoped))})
    return {'interendpoint_scalars': interendpoint, 'interendpoint_pairwise': pair_interendpoint,
            'initial_matched_arm_pair_directions': contrasts,
            'basis': 'Exact same texts, form and cycle; unlike native scales are never subtracted; no oracle direction is assigned'}


def inventory_summary(inventory):
    groups = defaultdict(list)
    for item in inventory:
        r = item['request']; groups[(r['endpoint'], r['form'], r['arm'], r['repeat'])].append(item)
    output = []
    for identity, items in sorted(groups.items()):
        metrics = {}
        for field in (*TOKEN_FIELDS, 'latency_seconds'):
            reported = [item['native_metrics'].get(field) for item in items if item['native_metrics'].get(field) is not None]
            metrics[field] = {'planned_requests': len(items), 'reported_requests': len(reported),
                              'unavailable_requests': len(items) - len(reported), 'sum_native_reported': sum(reported) if reported else None,
                              'mean_native_reported': mean(reported)}
        output.append({'endpoint': identity[0], 'form': identity[1], 'arm': identity[2], 'cycle': identity[3],
                       'planned_requests': len(items), 'states': dict(Counter(i['state'] for i in items)), 'native_metrics': metrics})
    return output


def analyze(manifest, records, inventory, hbq, root):
    c.require(len(inventory) == len(manifest['requests']) and Counter(i['request']['request_sha256'] for i in inventory)
              == Counter(r['request_sha256'] for r in manifest['requests']), 'All planned denominators must be preserved exactly')
    expected = {r['request_sha256']: r for r in manifest['requests']}
    ids = [item['request']['request_sha256'] for item in records]
    accepted = {i['request']['request_sha256'] for i in inventory if i['state'] == 'accepted'}
    c.require(len(ids) == len(set(ids)) and set(ids) == accepted
              and all(item['request'] == expected[item['request']['request_sha256']] for item in records), 'Admitted request inventory differs')
    item_profiles = profiles(manifest, records, hbq, root)
    pair_summary, decisions = pairwise_diagnostics(manifest, records)
    public_profiles = []
    for identity, profile in sorted(item_profiles.items()):
        public_profiles.append({'endpoint': identity[0], 'form': identity[1], 'arm': identity[2], 'artifact_id': identity[3], 'cycle': identity[4],
                                **{k: v for k, v in profile.items() if k != 'leaf_states'}})
    return {'schema_version': 1, 'analysis_policy': POLICY, 'study_id': manifest['study_id'], 'evidence_class': 'descriptive_ai_synthetic_stimuli',
            'candidate': None, 'oracle_accepted': False, 'fixed_synthetic_labels': False, 'labels_opened': False,
            'intended_defect_success_rate_eligible': False, 'human_alignment_claim': False, 'candidate_gain_claim': False,
            'first_review_uncertainty_preserved': True, 'planned': manifest['counts'], 'admitted_requests': len(records),
            'terminal_states': dict(Counter(i['state'] for i in inventory)), 'request_inventory': inventory_summary(inventory),
            'item_profiles': public_profiles, 'scalar_diagnostics': scalar_diagnostics(item_profiles),
            'repeat_diagnostics': repeat_diagnostics(item_profiles), 'pairwise': pair_summary,
            'matched_contrasts': matched_contrasts(manifest, item_profiles, decisions),
            'limitations': ['Twenty-four AI stimuli in eight source families; no human labels or accepted aesthetic oracle.',
                'Native scalar descriptions and within-pair directions only; no intended-transform correctness or candidate inference.',
                'Incomplete/unadmitted banks have no scalar or weighted coverage/bounds; CA/N/A remain native states.',
                'HBQ bounds are rubric-sensitivity bounds, not statistical confidence intervals.',
                'POEMetric item 10 is primary; absence codes 7/8 are diagnostic categories; fixed-form-to-free-verse transfer is unvalidated.',
                'Raw agreement/kappa are descriptive; sparse form-balanced sentinels do not establish population reliability.',
                'Reported token coverage is native completed-turn usage only; latency, unreported tokens, cost/cache and physical contact count remain unavailable.']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', required=True, type=Path)
    parser.add_argument('--manifest-sha256', required=True)
    parser.add_argument('--tools-root', required=True, type=Path)
    parser.add_argument('--grok-results', required=True, type=Path)
    parser.add_argument('--sol-results', required=True, type=Path)
    args = parser.parse_args()
    c.require(args.manifest_sha256 == MANIFEST_SHA, 'Named analysis requires the exact matched freeze')
    manifest, root, subset, validator = c.load_manifest(args.manifest, args.manifest_sha256, args.tools_root.resolve())
    hbq = load_hbq(manifest, root)
    from hbqrs import codex_receipts
    records, inventory, commitments = collect_evidence(manifest, args.manifest_sha256, root,
        {'sol': args.sol_results.resolve(), 'grok': args.grok_results.resolve()}, args.tools_root.resolve(), subset, validator, codex_receipts)
    report = analyze(manifest, records, inventory, hbq, root)
    report.update(manifest_sha256=args.manifest_sha256, analysis_sha256=c.digest(Path(__file__).read_bytes()),
                  collector_sha256=c.digest(Path(c.__file__).read_bytes()), review_file_commitments=manifest['review_file_commitments'],
                  replayed_terminal_commitment_sha256=c.digest(c.canonical(sorted(commitments, key=lambda r: (r['endpoint'], r['logical_sample_id'])))))
    print(json.dumps(report, sort_keys=True, allow_nan=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
