"""Provider-free poetry prediction replay and explicitly gated descriptive human joins."""
from collections import Counter, defaultdict
import argparse
import csv
from decimal import Decimal, InvalidOperation
import hashlib
import importlib.util
import io
import json
import math
from pathlib import Path
import statistics
import sys

HERE = Path(__file__).resolve().parent
POLICY = 'study2_poetry_prediction_replay_and_gated_alignment_v1'
GATE_POLICY = 'study2_poetry_analysis_once_replay_equivalent_terminal_gate_v1'
COLLECTOR_SHA = 'e06cc12c339d6eadadd8f7baa445d93b1777a43d21a57f33edc48b0d69573dd7'
PROFILE_SHA = '4a71da2ecd04810349b1f7395f61bba79b599dfb76ed11815dae31897550652e'
METADATA_SHA = '9dddd5b4468deda9da5204b2607830e7e1d4e12560d8fee87caad838bfc9ed1d'
ENDPOINTS = ('sol', 'grok')
SCALES = {'hbq': (0, 100), 'holistic': (1, 7), 'compact': (1, 5), 'poemetric': (1, 5)}
COMPACT_DIMENSIONS = ('poetic_architecture', 'image_relations', 'language_voice', 'rhythm_lineation',
                      'emotional_reader_effect', 'meaning_resonance')


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode() + b'\n'


def checked(path, digest):
    raw = Path(path).read_bytes()
    require(sha(raw) == digest, 'Exact input commitment differs')
    return raw


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def human_profile():
    raw = (HERE / 'human_profile.json').read_bytes()
    require(sha(raw) == PROFILE_SHA, 'Frozen human analysis profile differs')
    profile = json.loads(raw)
    require(profile['policy'] == 'study2_poetry_descriptive_human_alignment_v1'
            and profile['primary_condition'] == 'nothing' and profile['primary_target'] == 'overall_quality'
            and profile['rating_scale'] == [1, 7] and len(set(profile['rating_fields'])) == 14,
            'Human analysis profile differs')
    return profile, sha(raw)


def outer_bindings(specs, manifest_sha):
    require(set(specs) == set(ENDPOINTS) and all(all(s.get(k) is not None for k in
        ('output', 'job_sha', 'terminal', 'terminal_sha', 'handle', 'handle_sha', 'invocation', 'invocation_sha'))
        for s in specs.values()), 'Both exact outer/job/path/hash bindings required before attempt reads')
    bindings, proofs = {}, {}
    for endpoint, s in specs.items():
        output = Path(s['output']).resolve()
        binding = json.loads(checked(output / 'job.json', s['job_sha']))
        terminal = json.loads(checked(s['terminal'], s['terminal_sha']))
        handle = json.loads(checked(s['handle'], s['handle_sha']))
        invocation = json.loads(checked(s['invocation'], s['invocation_sha']))
        argv = invocation['argv']
        require(binding['endpoint'] == endpoint and binding['manifest_sha256'] == manifest_sha
            and binding['collector_sha256'] == COLLECTOR_SHA and binding['workers'] == 1
            and binding['planned_endpoint_requests'] == 480 and binding['planned_study_requests'] == 960,
            'Selected native job differs from original poetry contract')
        require(Path(s['terminal']).name == 'terminal.json' and terminal['no_resend'] is True
            and type(terminal['exit_code']) is int and terminal['exit_code'] in (0, 3) and terminal['time']
            and handle['endpoint'] == endpoint and handle['workers'] == 1
            and Path(handle['native_job']).resolve() == output / 'job.json'
            and terminal['invocation_sha256'] == handle['invocation_sha256'] == s['invocation_sha']
            and argv.count('--results-dir') == 1
            and Path(argv[argv.index('--results-dir') + 1]).resolve() == output
            and invocation['collector_sha256'] == COLLECTOR_SHA and invocation['manifest_sha256'] == manifest_sha,
            'Actual outer terminal/handle/invocation does not bind selected job')
        require('--workers' not in argv or (argv.count('--workers') == 1 and argv[argv.index('--workers') + 1] == '1'),
                'Outer worker setting differs')
        bindings[endpoint] = binding
        proofs[endpoint] = {k: s[k] for k in ('job_sha', 'terminal_sha', 'handle_sha', 'invocation_sha')}
        proofs[endpoint].update(outer_exit_code=terminal['exit_code'], native_child_quiescence_proven=False,
                                provider_quiescence_proven=False)
    return bindings, proofs


def replay_once(c, manifest, root, bindings, outputs, receipts, subset, validator, explicit_release=False):
    observations, counts, identities = {}, {ep: Counter() for ep in ENDPOINTS}, set()
    for row in manifest['requests']:
        key = row['request_sha256']
        require(key not in observations, 'Duplicate planned request')
        sample = c.sample_path(outputs[row['endpoint']], row)
        if not sample.exists():
            state, answer = 'untouched', None
        elif not (sample / 'terminal.json').is_file():
            state, answer = 'occupied_unresolved_no_vote', None
        else:
            terminal, answer = c.replay(sample, row, manifest, bindings[row['endpoint']], root, receipts, subset, validator)
            state = terminal['state']
            identity = terminal.get('native_thread_id')
            if identity:
                require(identity not in identities, 'Native UUID reused across planned observations')
                identities.add(identity)
        counts[row['endpoint']][state] += 1
        observations[key] = {'request': row, 'state': state, 'response': answer}
    require(len(observations) == 960 and all(sum(v.values()) == 480 for v in counts.values()), 'Full planned denominator differs')
    verified = sum(n for values in counts.values() for state, n in values.items() if state in c.TERMINAL_STATES)
    ready = verified == 960
    gate = {'policy': GATE_POLICY, 'delegated_contract': manifest['human_label_gate']['policy'],
        'basis': 'One unchanged collector.replay per occupied terminal; same all960 terminal predicate as collector.label_release_gate; no monkeypatch',
        'planned': 960, 'verified_terminal': verified, 'endpoints': {ep: dict(v) for ep, v in counts.items()},
        'all_planned_verified_terminal': ready, 'explicit_postprediction_release': explicit_release,
        'human_release_eligible': ready and explicit_release, 'human_targets_opened': False}
    return observations, gate


def scoring_context(c, root, manifest):
    sys.path.insert(0, str(c.p.REPO / 'src'))
    from hbqrs import core, runner, scoring_v2
    modules = core.load_modules(root / 'registry/all_modules.yaml')
    bundle = core.resolve_bundle(core.load_bundles(root / 'bundles/all_bundles.yaml'), 'poetry.general')
    compiled = json.loads(c.pinned(root, 'compiled/poetry.general.json', manifest['artifacts']['compiled/poetry.general.json']))
    ids = [q['question']['id'] for q in core.compiled_questions(compiled)]
    require(len(ids) == len(set(ids)) == 95, 'Frozen generic poetry bank differs')
    return {'core': core, 'runner': runner, 'scorer': scoring_v2, 'modules': modules, 'bundle': bundle, 'ids': ids}


def score_bank(planned, admitted, hbq, c, root, manifest):
    ordered = sorted(planned, key=lambda r: r['batch'])
    leaves = [v for item in admitted for v in item['response']['verdicts']]
    states = Counter(v['verdict'] for v in leaves)
    base = {'score': None, 'leaf_states': {v['question_id']: v['verdict'] for v in leaves},
        'coverage': {'planned_packets': 12, 'accepted_packets': len(admitted), 'expected_leaves': 95,
                     'observed_leaves': len(leaves), 'states': dict(states)}}
    if (len(ordered) != 12 or [r['batch'] for r in ordered] != list(range(1, 13))
        or [qid for r in ordered for qid in r['question_ids']] != hbq['ids']
        or len(admitted) != 12 or len(leaves) != 95
        or Counter(v['question_id'] for v in leaves) != Counter(hbq['ids'])
        or Counter(x['request']['request_sha256'] for x in admitted) != Counter(r['request_sha256'] for r in ordered)):
        return {**base, 'state': 'incomplete_or_duplicate_bank_no_scalar'}
    row = ordered[0]
    contract_ref = row['task_contracts'][0]
    contract = json.loads(c.pinned(root, contract_ref['path'], manifest['artifacts'][contract_ref['path']]))
    compiled = hbq['core'].compile_bundle(hbq['modules'], hbq['bundle'], task_contract=contract)
    require([q['question']['id'] for q in hbq['core'].compiled_questions(compiled)] == hbq['ids']
        and all(r['compiled_sha256'] == manifest['artifacts']['compiled/poetry.general.json']['sha256']
                and r['task_contracts'] == row['task_contracts'] and r['task_context'] == row['task_context'] for r in ordered),
        'Bank compiled/task context differs')
    normalized = []
    try:
        for item in sorted(admitted, key=lambda x: x['request']['batch']):
            r = item['request']; _, _, texts, context = c.inputs(root, manifest, r)
            normalized.extend(hbq['runner']._normalize_batch(item['response'], expected_ids=r['question_ids'],
                artifact_id=r['artifact_id'], bundle_id=r['bundle_id'], judge_id=r['endpoint'], run_id=r['logical_sample_id'],
                artifact_text=texts[r['sources'][0]['id']], context_texts=[context]))
        report = hbq['scorer'].score_bundle(hbq['modules'], hbq['bundle'], normalized, artifact_id=row['artifact_id'],
                                          task_contract=contract, admission_policy='strict_import_v1')
    except ValueError:
        return {**base, 'state': 'strict_import_unadmitted_no_scalar'}
    native_states = base['leaf_states']
    positive_ids = [q['question']['id'] for q in compiled['domain_questions']]
    penalty_ids = [q['question']['id'] for group in compiled['penalty_groups'] for q in group['questions']]
    role_completeness = {role: {'states': dict(Counter(native_states[q] for q in ids)),
        'complete_native_assessment': all(native_states[q] in ('YES', 'NO', 'NOT_APPLICABLE') for q in ids)}
        for role, ids in (('positive', positive_ids), ('penalty', penalty_ids))}
    return {**base, 'score': report['final_score']['observed'] if report['status'] == 'SCORED' else None,
        'state': report['status'], 'weighted_coverage': report['coverage'], 'sensitivity_bounds': report['final_score'],
        'penalty_deduction': report['penalty_deduction'], 'native_role_completeness': role_completeness,
        'issues_count': len(report['issues'])}


def profiles(observations, hbq, c, root, manifest):
    planned, accepted = defaultdict(list), defaultdict(list)
    pair_orders = {}
    pair_lookup = {p['pair_id']: p for p in manifest['pairs']}
    for item in observations.values():
        r, answer = item['request'], item['response']
        if r['arm'] == 'pairwise':
            value = None
            if answer is not None and answer['winner'] != 'CANNOT_ASSESS':
                chosen = next((s['id'] for s in r['sources'] if s['side'] == answer['winner']), None)
                value = 0 if answer['winner'] == 'TIE' else 1 if chosen == pair_lookup[r['pair_id']]['left'] else -1
            pair_orders[(r['endpoint'], r['pair_id'], r['repeat'], r['orientation'])] = value
            continue
        key = (r['endpoint'], r['arm'], r['artifact_id'], r['repeat'])
        planned[key].append(r)
        if answer is not None:
            accepted[key].append(item)
    result = {}
    for key, rows in planned.items():
        items, arm = accepted[key], key[1]
        if arm == 'hbq':
            result[key] = score_bank(rows, items, hbq, c, root, manifest)
        elif not items:
            result[key] = {'score': None, 'state': 'missing_unadmitted_no_scalar'}
        else:
            require(len(items) == 1, 'Duplicate comparator observation')
            answer = items[0]['response']
            if answer['status'] == 'CANNOT_ASSESS':
                result[key] = {'score': None, 'state': 'explicit_abstention'}
            else:
                value = answer['result']
                score = value['score'] if arm == 'holistic' else value['overall_score'] if arm == 'compact' else value['overall_quality']['score']
                entry = {'score': score, 'state': 'SCORED'}
                if arm == 'compact': entry['dimensions'] = {d['dimension_id']: d['score'] for d in value['dimensions']}
                if arm == 'poemetric': entry['diagnostics'] = {str(d['item_id']): {'status': d['status'], 'score': d['score']} for d in value['diagnostics']}
                result[key] = entry
    return result, pair_orders


def fraction(a, b):
    return a / b if b else None


def mean(values):
    return statistics.mean(values) if values else None


def affine_bands(values, low, high, planned):
    normalized = [100 * (v-low) / (high-low) for v in values]
    return {'mapping': {'native_range': [low, high], 'normalized_range': [0, 100],
                        'formula': '100*(value-native_min)/(native_max-native_min)'},
            'planned': planned, 'observed': len(values), 'unmapped_or_missing': planned-len(values),
            'normalized_at_or_below_10': sum(v <= 10 for v in normalized),
            'normalized_at_or_above_90': sum(v >= 90 for v in normalized),
            'cross_scale_subtraction_or_aggregation': False}


def categorical_agreement(pairs, planned):
    left, right = Counter(a for a, _ in pairs), Counter(b for _, b in pairs)
    n = len(pairs); exact = sum(a == b for a, b in pairs)
    observed = fraction(exact, n)
    expected = sum(left[k]*right[k] for k in left.keys() | right.keys()) / (n*n) if n else None
    return {'planned_pairs': planned, 'observed_pairs': n, 'unobserved_pairs': planned-n,
            'exact_matches': exact, 'raw_agreement': observed, 'chance_expected_agreement': expected,
            'cohen_kappa': (observed-expected)/(1-expected) if expected is not None and expected < 1 else None,
            'left_state_counts': dict(left), 'right_state_counts': dict(right),
            'left_prevalence': {k: v/n for k, v in left.items()}, 'right_prevalence': {k: v/n for k, v in right.items()},
            'transitions': dict(Counter(a + '->' + b for a, b in pairs)),
            'basis': 'Observed matched native leaf states; repeated leaf positions are descriptive, not independent poems'}


def prediction_diagnostics(manifest, bank_profiles, pair_orders):
    out = {}
    for ep in ENDPOINTS:
        for arm, (low, high) in SCALES.items():
            items = [bank_profiles[(ep, arm, tid, cycle)] for tid in manifest['bank_ids'] for cycle in range(3)]
            values = [p['score'] for p in items if p['score'] is not None]
            repeat_pairs, leaf_pairs = [], []
            for tid in manifest['bank_ids']:
                for a, b in ((0, 1), (0, 2), (1, 2)):
                    left, right = [bank_profiles[(ep, arm, tid, cycle)] for cycle in (a, b)]
                    if left['score'] is not None and right['score'] is not None:
                        repeat_pairs.append((left['score'], right['score']))
                    if arm == 'hbq':
                        ls, rs = left.get('leaf_states', {}), right.get('leaf_states', {})
                        leaf_pairs.extend((ls[q], rs[q]) for q in ls.keys() & rs.keys())
            transitions = Counter(a + '->' + b for a, b in leaf_pairs)
            entry = {'planned_profiles': 30, 'usable_scalars': len(values), 'missing_or_abstained_scalars': 30-len(values),
                'profile_states': dict(Counter(p['state'] for p in items)), 'native_scale': [low, high],
                'floor': sum(v == low for v in values), 'ceiling': sum(v == high for v in values), 'mean': mean(values),
                'near_floor': sum(v <= (5 if arm == 'hbq' else low + 1) for v in values),
                'near_ceiling': sum(v >= (95 if arm == 'hbq' else high - 1) for v in values),
                'near_boundary_policy': 'HBQ<=5/>=95; other native scales one increment from endpoint',
                'affine_normalized_bands': affine_bands(values, low, high, 30),
                'repeat': {'planned_pairs': 30, 'observed_pairs': len(repeat_pairs),
                    'exact_agreement': fraction(sum(a == b for a, b in repeat_pairs), len(repeat_pairs)),
                    'mean_absolute_native_delta': mean([abs(a-b) for a, b in repeat_pairs]), 'independent_poems_added': 0}}
            if arm == 'hbq':
                entry['native_leaf_states'] = dict(sum((Counter(p['coverage']['states']) for p in items), Counter()))
                entry['planned_leaf_positions'] = 2850
                entry['repeat']['leaf_transitions'] = dict(transitions)
                entry['repeat']['planned_leaf_pairs'] = 2850
                entry['repeat']['observed_leaf_pairs'] = len(leaf_pairs)
                entry['repeat']['leaf_agreement'] = categorical_agreement(leaf_pairs, 2850)
            if arm in ('compact', 'poemetric'):
                field = 'dimensions' if arm == 'compact' else 'diagnostics'
                separated = defaultdict(list); unavailable = Counter()
                for p in items:
                    for dim, value in p.get(field, {}).items():
                        score = value if arm == 'compact' else value['score']
                        if score is None: unavailable[dim] += 1
                        else: separated[dim].append(score)
                entry['separate_diagnostics'] = {dim: {'planned': 30, 'observed': len(separated[dim]), 'unavailable': unavailable[dim],
                    'missing_or_overall_abstained': 30-len(separated[dim])-unavailable[dim],
                    'mean': mean(separated[dim]), 'absence_zero': sum(v == 0 for v in separated[dim]) if arm == 'poemetric' and dim in ('7', '8') else None}
                    for dim in (COMPACT_DIMENSIONS if arm == 'compact' else tuple(str(i) for i in range(1, 9)))}
                for dim, diagnostic in entry['separate_diagnostics'].items():
                    assessed = [v for v in separated[dim] if arm != 'poemetric' or v != 0]
                    diagnostic['affine_normalized_bands'] = affine_bands(assessed, 1, 5, 30)
                    diagnostic['affine_normalized_bands']['absence_zero_excluded'] = (
                        sum(v == 0 for v in separated[dim]) if arm == 'poemetric' and dim in ('7', '8') else 0)
                entry['diagnostics_aggregated_as_quality'] = False
            out[ep + ':' + arm] = entry
    pairs = {}
    for ep in ENDPOINTS:
        comparisons = [(pair_orders.get((ep, p['pair_id'], cy, 'AB')), pair_orders.get((ep, p['pair_id'], cy, 'BA')))
                       for p in manifest['pairs'] for cy in range(3)]
        observed = [(a, b) for a, b in comparisons if a is not None and b is not None]
        pairs[ep] = {'planned_AB_BA_comparisons': 15, 'observed': len(observed),
            'consistent': sum(a == b for a, b in observed), 'order_conflicts': sum(a != b for a, b in observed),
            'both_native_ties': sum(a == b == 0 for a, b in observed), 'abstained_or_missing': 15-len(observed),
            'conflicts_converted_to_ties': False, 'ranking_graph': False}
    cross = {}
    for arm in SCALES:
        paired = [(bank_profiles[('sol', arm, tid, cy)]['score'], bank_profiles[('grok', arm, tid, cy)]['score'])
                  for tid in manifest['bank_ids'] for cy in range(3)]
        observed = [(a, b) for a, b in paired if a is not None and b is not None]
        cross[arm] = {'planned_same_scale_pairs': 30, 'observed': len(observed),
            'mean_absolute_native_delta': mean([abs(a-b) for a, b in observed]),
            'mean_signed_native_offset_sol_minus_grok': mean([a-b for a, b in observed]),
            'exact_agreement': fraction(sum(a == b for a, b in observed), len(observed))}
        ranks_by_cycle = []
        for cycle in range(3):
            shared = [(bank_profiles[('sol', arm, tid, cycle)]['score'], bank_profiles[('grok', arm, tid, cycle)]['score'])
                      for tid in manifest['bank_ids']]
            complete = [(a, b) for a, b in shared if a is not None and b is not None]
            ranks_by_cycle.append({'cycle': cycle, 'planned_poems': 10, 'shared_usable_poems': len(complete),
                                  'spearman': spearman(complete)})
        means = []
        for tid in manifest['bank_ids']:
            sv, gv = [[bank_profiles[(ep, arm, tid, cy)]['score'] for cy in range(3)] for ep in ENDPOINTS]
            if all(v is not None for v in (*sv, *gv)): means.append((mean(sv), mean(gv)))
        cross[arm]['shared_poem_rank_agreement'] = {'by_cycle': ranks_by_cycle,
            'three_cycle_means': {'planned_poems': 10, 'shared_complete_poems': len(means), 'spearman': spearman(means)},
            'null_when_fewer_than_two_or_nonvarying': True, 'independent_poems_added_by_repeats': 0}
    return {'native_profiles': out, 'pair_orientations': pairs, 'same_arm_cross_endpoint': cross,
            'cross_scale_subtraction': False}


def decode_humans(reference_path, gate, profile, metadata):
    require(gate['human_release_eligible'] is True and gate['all_planned_verified_terminal'] is True
        and gate['explicit_postprediction_release'] is True, 'Full960 verified terminal gate and explicit release required before labels')
    raw = checked(reference_path, metadata['reference_manifest_file_sha256'])
    reference, root = json.loads(raw), Path(reference_path).resolve().parent
    def artifact(name):
        pin = reference['artifacts'][name]
        value = checked(metadata_module.relative(root, name), pin['sha256'])
        require(len(value) == pin['bytes'], 'Human-source artifact byte count differs')
        return value
    row_raw, linkage_raw = artifact('private/row-metadata.json'), artifact('private/source-linkage.json')
    rows = metadata_module.project_json(row_raw, [{'source_record_index': True, 'response_id': True, 'target_id': True, 'condition': True}])
    linkage = metadata_module.project_json(linkage_raw, [{'target_id': True, 'CSV_key': True, 'primary_text': True}])
    require(len(rows) == 6960 and [r['source_record_index'] for r in rows] == list(range(6960))
            and len({r['response_id'] for r in rows}) == 696 and len(linkage) == 10,
            'Source respondent/poem/row geometry differs')
    checked(root / 'implementation/prepare_sources.py', metadata['source_projection_sha256'])
    source = load('poetry_alignment_frozen_projector', root / 'implementation/prepare_sources.py')
    require(profile['rating_fields'] == list(source.RATINGS), 'Human target field contract differs')
    by_key, text_pins = {}, {p['opaque_text_id']: p for p in metadata['presented_text_pins_manifest_declared']}
    for item in linkage:
        key = item['CSV_key']['Poet'] + '_' + item['CSV_key']['poem_ID']
        require(key not in by_key and source.opaque('poem', key) == item['target_id']
            and sha(key.encode()) == item['CSV_key']['commitment_sha256']
            and item['target_id'] in text_pins and item['primary_text']['sha256'] == text_pins[item['target_id']]['sha256'],
            'Exact CSV key/QSF target commitment differs')
        by_key[key] = item['target_id']
    csv_raw = artifact('sealed/targets/study2.csv')
    reader = csv.DictReader(io.StringIO(csv_raw.decode('utf-8-sig'), newline=''))
    require(tuple(reader.fieldnames) == source.COLUMNS, 'Pinned CSV field contract differs')
    ballots, values, missing, rhyme = {}, defaultdict(lambda: defaultdict(list)), Counter(), Counter()
    framing = Counter(); cells = Counter()
    for i, row in enumerate(reader):
        require(i < len(rows) and None not in row and all(v is not None for v in row.values()), 'Malformed CSV row')
        joined = rows[i]; key = row['Poet'] + '_' + row['poem_ID']
        require(key in by_key and joined['target_id'] == by_key[key]
            and joined['response_id'] == source.opaque('response', row['ResponseId']) and joined['condition'] == row['condition']
            and row['condition'] in source.CONDITIONS, 'CSV row/source-metadata join differs')
        framing[row['condition']] += 1
        if row['condition'] != profile['primary_condition']: continue
        decoded = {}
        for field in profile['rating_fields']:
            text = row[field].strip()
            if not text:
                decoded[field] = None
                continue
            try: number = Decimal(text)
            except InvalidOperation: raise ValueError('Unknown human rating value') from None
            require(number.is_finite() and number == number.to_integral_value() and 1 <= number <= 7,
                    'Unknown human rating value')
            decoded[field] = int(number)
        for field, score in decoded.items():
            cells[field] += 1
            if score is None: missing[field] += 1
            else: values[joined['target_id']][field].append(score)
        rhyme[row['rhyme'].strip()] += 1
        identity = (joined['response_id'], joined['target_id'])
        require(identity not in ballots, 'Repeated assessor/target primary-condition row has no configured merge policy')
        ballots[identity] = decoded['overall_quality']
    require(sum(framing.values()) == 6960 and set(by_key.values()) == set(text_pins), 'Complete human source join differs')
    return {'ballots': ballots, 'means': {tid: {f: mean(v) for f, v in fields.items()} for tid, fields in values.items()},
        'public': {'state': 'released_descriptive_source_join', 'rows': 6960, 'source_response_ids': 696,
            'verified_independent_people': False, 'presented_poems': 10, 'condition_rows': dict(framing),
            'primary_condition': profile['primary_condition'], 'rating_cells': dict(cells), 'missing_rating_cells': dict(missing),
            'rhyme': {'categorical_not_quality': True, 'missing_rows': rhyme[''], 'distinct_nonblank_categories': len([v for v in rhyme if v])},
            'commitments': {'csv_sha256': sha(csv_raw), 'row_metadata_sha256': sha(row_raw), 'source_linkage_sha256': sha(linkage_raw)},
            'raw_human_values_in_report': False}}


def ranks(values):
    ordered = sorted(enumerate(values), key=lambda p: p[1]); result = [0.] * len(values); i = 0
    while i < len(ordered):
        j = i + 1
        while j < len(ordered) and ordered[j][1] == ordered[i][1]: j += 1
        for index, _ in ordered[i:j]: result[index] = (i + 1 + j) / 2
        i = j
    return result


def spearman(pairs):
    if len(pairs) < 2: return None
    x, y = ranks([p[0] for p in pairs]), ranks([p[1] for p in pairs])
    mx, my = mean(x), mean(y)
    denominator = math.sqrt(sum((v-mx)**2 for v in x) * sum((v-my)**2 for v in y))
    return sum((a-mx)*(b-my) for a, b in zip(x, y)) / denominator if denominator else None


def human_alignment(manifest, bank_profiles, pair_orders, humans):
    result = {}
    for endpoint in ENDPOINTS:
        for arm in (*SCALES, 'pairwise'):
            predictions = {}
            if arm != 'pairwise':
                for tid in manifest['bank_ids']:
                    values = [bank_profiles[(endpoint, arm, tid, cycle)]['score'] for cycle in range(3)]
                    if all(v is not None for v in values): predictions[tid] = mean(values)
                paired = [(score, humans['means'][tid]['overall_quality']) for tid, score in predictions.items()
                          if humans['means'].get(tid, {}).get('overall_quality') is not None]
            else: paired = []
            agreement, planned, observed, human_ties, model_ties = 0, 0, 0, 0, 0
            for pair in manifest['pairs']:
                if arm == 'pairwise':
                    orders = [pair_orders.get((endpoint, pair['pair_id'], cy, o)) for cy in range(3) for o in ('AB', 'BA')]
                    direction = orders[0] if all(v is not None for v in orders) and len(set(orders)) == 1 else None
                else:
                    left, right = predictions.get(pair['left']), predictions.get(pair['right'])
                    direction = None if left is None or right is None else (left > right)-(left < right)
                respondents = {rid for rid, tid in humans['ballots'] if tid in (pair['left'], pair['right'])}
                for rid in respondents:
                    planned += 1
                    left, right = [humans['ballots'].get((rid, pair[side])) for side in ('left', 'right')]
                    if left is None or right is None or direction is None: continue
                    hd = (left > right)-(left < right); observed += 1
                    agreement += hd == direction; human_ties += hd == 0; model_ties += direction == 0
            result[endpoint + ':' + arm] = {'planned_poems': 10 if arm != 'pairwise' else None,
                'complete_three_cycle_matched_poems': len(paired) if arm != 'pairwise' else None,
                'descriptive_spearman': spearman(paired) if arm != 'pairwise' else None,
                'assessor_pair_slots': planned, 'observed_pair_directions': observed, 'unresolved': planned-observed,
                'exact_direction_agreement': fraction(agreement, observed), 'human_ties': human_ties, 'prediction_ties': model_ties,
                'full_denominator_agreement_bounds': [fraction(agreement, planned), fraction(agreement + planned-observed, planned)]}
    return {'source_join': humans['public'], 'primary_overall_quality': result, 'independent_poems': 10,
            'population_inference': False, 'other_dimensions_comparator_crosswalk': None, 'candidate': None}


checked(HERE / 'analysis.py', METADATA_SHA)
metadata_module = load('poetry_predictions_metadata_only', HERE / 'analysis.py')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    for name in ('manifest', 'reference-manifest', 'output-root', 'tools-root'):
        parser.add_argument('--' + name, type=Path, required=name != 'tools-root')
    parser.add_argument('--manifest-sha256', required=True)
    parser.add_argument('--metadata-only', action='store_true')
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--explicit-postprediction-release', action='store_true')
    for ep in ENDPOINTS:
        for name in ('results-dir', 'outer-terminal', 'handle', 'invocation'):
            parser.add_argument('--' + ep + '-' + name, type=Path)
        for name in ('job-sha256', 'outer-terminal-sha256', 'handle-sha256', 'invocation-sha256'):
            parser.add_argument('--' + ep + '-' + name)
    args = parser.parse_args(argv)
    inputs = [args.manifest, args.reference_manifest] + [getattr(args, ep + '_results_dir') / 'job.json' for ep in ENDPOINTS if getattr(args, ep + '_results_dir') is not None]
    output = metadata_module.output_path(args.output_root, inputs)
    profile, profile_sha = human_profile()
    metadata = metadata_module.metadata_view(args.manifest, args.manifest_sha256, args.reference_manifest)
    report = {'policy': POLICY, 'implementation_sha256': sha(Path(__file__).read_bytes()), 'human_profile_sha256': profile_sha,
              'metadata': metadata, 'provider_calls': 0, 'human_targets_opened': False, 'candidate': None}
    if args.metadata_only:
        require(not args.explicit_postprediction_release, 'Metadata-only mode cannot release labels')
        report.update(state='metadata_only_no_native_replay', human_alignment='sealed_unopened')
    else:
        require(args.tools_root is not None, 'Frozen tools root required')
        specs = {ep: {'output': getattr(args, ep + '_results_dir'), 'job_sha': getattr(args, ep + '_job_sha256'),
            'terminal': getattr(args, ep + '_outer_terminal'), 'terminal_sha': getattr(args, ep + '_outer_terminal_sha256'),
            'handle': getattr(args, ep + '_handle'), 'handle_sha': getattr(args, ep + '_handle_sha256'),
            'invocation': getattr(args, ep + '_invocation'), 'invocation_sha': getattr(args, ep + '_invocation_sha256')} for ep in ENDPOINTS}
        bindings, outer = outer_bindings(specs, args.manifest_sha256)
        require(sha((HERE / 'collector.py').read_bytes()) == COLLECTOR_SHA, 'Frozen poetry collector differs')
        c = load('poetry_predictions_frozen_collector', HERE / 'collector.py')
        manifest, root, subset, validator, receipts = c.load_manifest(args.manifest, args.manifest_sha256, COLLECTOR_SHA, args.tools_root)
        outputs = {ep: Path(specs[ep]['output']).resolve() for ep in ENDPOINTS}
        for ep in ENDPOINTS:
            require(c.verify_job_binding(outputs[ep], manifest, root, args.manifest_sha256, ep, args.tools_root) == bindings[ep], 'Original selected job binding differs')
        observations, gate = replay_once(c, manifest, root, bindings, outputs, receipts, subset, validator, args.explicit_postprediction_release)
        hbq = scoring_context(c, root, manifest)
        bank_profiles, pair_orders = profiles(observations, hbq, c, root, manifest)
        report.update(state='verified_native_prediction_replay', outer_bindings=outer, label_gate=gate,
            predictions=prediction_diagnostics(manifest, bank_profiles, pair_orders),
            opaque_profiles=[{'endpoint': ep, 'arm': arm, 'opaque_text_id': tid, 'cycle': cy, **value}
                for (ep, arm, tid, cy), value in sorted(bank_profiles.items())], human_alignment='sealed_unopened')
        if args.explicit_postprediction_release:
            humans = decode_humans(args.reference_manifest, gate, profile, metadata)
            report.update(human_targets_opened=True, human_alignment=human_alignment(manifest, bank_profiles, pair_orders, humans))
    raw = canonical(report)
    receipt = {'policy': POLICY, 'state': report['state'], 'implementation_sha256': report['implementation_sha256'],
        'human_profile_sha256': profile_sha, 'report_sha256': sha(raw), 'planned': 960, 'provider_calls': 0,
        'human_targets_opened': report['human_targets_opened'], 'dry_run': args.dry_run}
    if not args.dry_run:
        output.mkdir(parents=True, exist_ok=False)
        for name, value in {'analysis.json': raw, 'terminal.json': canonical(receipt),
            'analysis_predictions.py': Path(__file__).read_bytes(), 'human_profile.json': (HERE / 'human_profile.json').read_bytes()}.items():
            with (output / name).open('xb') as stream: stream.write(value)
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
