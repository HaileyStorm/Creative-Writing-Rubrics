"""Provider-free prediction diagnostics for the full matched LAMP triplet study."""
from collections import Counter, defaultdict
import argparse
import importlib.util
import json
import math
from pathlib import Path
import random
import statistics
import sys

HERE = Path(__file__).resolve().parent
COLLECTOR_SHA = 'd5a146f0ab615994792f422ef7dc01bac5f7dca9e38ac6c0a4a085c5b8ceb698'
raw_collector = (HERE / 'collector.py').read_bytes()
import hashlib
if hashlib.sha256(raw_collector).hexdigest() != COLLECTOR_SHA:
    raise ValueError('Retained LAMP collector differs')
spec = importlib.util.spec_from_file_location('lamp_analysis_native_collection', HERE / 'collector.py')
c = importlib.util.module_from_spec(spec); spec.loader.exec_module(c)
RANGES = {'hbq': (0, 100), 'ttcw14': (0, 1), 'holistic': (1, 7), 'compact': (1, 5), 'oregon': (6, 36)}
STATES = ('YES', 'NO', 'NOT_APPLICABLE', 'CANNOT_ASSESS')
HUMAN_PROFILE_SHA = 'cd90bc17ae1ea1e0f2113f7c2b497eb47c59962a8891a91c1883bb3865b121e5'


def fraction(a, b):
    return a / b if b else None


def load_manifest(path, expected_sha, tools):
    raw = path.read_bytes(); root = path.resolve().parent; manifest = json.loads(raw)
    c.require(c.digest(raw) == expected_sha == c.MANIFEST_SHA, 'Exact frozen manifest differs')
    c.require(c.digest(c.canonical({k: v for k, v in manifest.items() if k != 'manifest_content_sha256'}))
              == manifest['manifest_content_sha256'], 'Manifest content commitment differs')
    # Sealed lineage and source bytes are committed without interpreting roles, labels or prose.
    for name, meta in manifest['artifacts'].items(): c.pinned(root, name, meta)
    sys.path.insert(0, str(c.p.REPO / 'src'))
    c.validate_design(manifest, {'compiled.json': c.pinned(root, 'compiled.json', manifest['artifacts']['compiled.json'])})
    source = c.source_settings(manifest, root)
    c.require(tools.resolve() == Path(source['external_pins']['tools_root_local_only']).resolve(), 'Tools root differs')
    c.p.checked(tools / 'adaptive_settings/account_probe.py', source['external_pins']['account_probe_sha256'])
    sys.path.insert(0, str(tools))
    for current, frozen in [(HERE / 'prepare.py', 'implementation/prepare.py'),
            (c.p.REPO / 'src/hbqrs/core.py', 'implementation/core.py'),
            (c.p.REPO / 'src/hbqrs/runner.py', 'implementation/runner.py'),
            (c.p.REPO / 'src/hbqrs/scoring_v2.py', 'implementation/scoring_v2.py'),
            (c.p.REPO / 'src/hbqrs/codex_receipts.py', 'implementation/codex_receipts.py'),
            (tools / 'model_work_queue/broker.py', 'implementation/broker.py'),
            (tools / 'model_work_queue/adapters/grok_exec.py', 'implementation/grok_exec.py'),
            (c.p.REPO / 'schema/hbq_verdict.schema.json', 'schema/hbq_verdict.schema.json'),
            (c.p.REPO / 'schema/hbq_judge_response.schema.json', 'schema/hbq_judge_response.schema.json')]:
        c.p.checked(current, manifest['artifacts'][frozen]['sha256'])
    subset = c.p.load('lamp_analysis_frozen_subset', root / 'implementation/schema_subset.py')
    validator = c.p.load('lamp_analysis_frozen_admission', root / 'implementation/validate_response.py')
    receipts = c.p.load('lamp_analysis_frozen_receipts', root / 'implementation/codex_receipts.py')
    for name in {row['schema_path'] for row in manifest['requests']}:
        subset.validate_schema(json.loads(c.pinned(root, name, manifest['artifacts'][name])))
    from hbqrs import core, runner, scoring_v2
    modules = core.load_modules(root / 'registry/all_modules.yaml')
    bundle = core.resolve_bundle(core.load_bundles(root / 'bundles/all_bundles.yaml'), 'prose.short_form')
    hbq = {'core': core, 'runner': runner, 'scorer': scoring_v2, 'modules': modules, 'bundle': bundle,
           'ids': [q['question']['id'] for q in core.compiled_questions(json.loads((root / 'compiled.json').read_bytes()))]}
    return manifest, root, subset, validator, receipts, hbq


def collect_evidence(manifest, manifest_sha, root, tools, outputs, subset, validator, receipts):
    records = []; statuses = {}; identities = set()
    for endpoint in c.p.ENDPOINTS:
        output = outputs[endpoint]; states = Counter(); binding = None
        if output.exists(): binding = c.verify_job_binding(output, manifest, root, manifest_sha, endpoint, tools)
        for row in (r for r in manifest['requests'] if r['endpoint'] == endpoint):
            sample = c.sample_path(output, row)
            if not sample.exists(): states['untouched'] += 1; continue
            if not (sample / 'terminal.json').exists():
                if (sample / 'condition.json').exists():
                    c.require(json.loads((sample / 'condition.json').read_bytes()) == row, 'Reserved condition differs')
                states['started_unresolved' if (sample / 'attempt-started.json').exists() else 'reserved_unresolved'] += 1
                continue
            terminal, answer = c.replay(sample, row, manifest, binding, root, receipts, subset, validator)
            states[terminal['state']] += 1
            identity = terminal.get('native_thread_id')
            if identity:
                c.require(identity not in identities, 'Native identity reused across logical samples'); identities.add(identity)
            if answer is not None: records.append({'request': row, 'response': answer})
        c.require(sum(states.values()) == 8904, 'Endpoint denominator differs')
        statuses[endpoint] = {'planned': 8904, 'states': dict(states),
            'verified_terminal': sum(n for state, n in states.items() if state in c.TERMINAL_STATES),
            'accepted': states['accepted'], 'pending_or_unresolved': states['untouched'] + states['started_unresolved'] + states['reserved_unresolved']}
    return records, statuses


def score_bank(planned, admitted, hbq, root, manifest):
    ordered = sorted(planned, key=lambda r: r['batch'])
    leaves = [v for item in admitted for v in item['response']['verdicts']]
    states = Counter(v['verdict'] for v in leaves)
    coverage = {'planned_packets': len(planned), 'accepted_packets': len(admitted), 'expected_leaves': 170,
        'native_leaves': len(leaves), 'states': dict(states), 'assessed_binary': states['YES'] + states['NO'],
        'applicable_observed': len(leaves) - states['NOT_APPLICABLE']}
    coverage['assessed_over_observed_applicable'] = fraction(coverage['assessed_binary'], coverage['applicable_observed'])
    safe_leaves = {v['question_id']: v['verdict'] for v in leaves}
    base = {'score': None, 'coverage': coverage, 'leaves': safe_leaves}
    if (len(ordered) != 22 or [r['batch'] for r in ordered] != list(range(1, 23))
            or [qid for r in ordered for qid in r['question_ids']] != hbq['ids']
            or len(set(hbq['ids'])) != 170 or len(admitted) != 22 or len(leaves) != 170
            or Counter(v['question_id'] for v in leaves) != Counter(hbq['ids'])
            or Counter(item['request']['logical_sample_id'] for item in admitted) != Counter(r['logical_sample_id'] for r in ordered)):
        return {**base, 'state': 'incomplete_or_duplicate_full_bank_no_scalar'}
    row = ordered[0]; contract_ref = row['task_contracts'][0]
    contract = json.loads(c.pinned(root, contract_ref['path'], manifest['artifacts'][contract_ref['path']]))
    compiled = hbq['core'].compile_bundle(hbq['modules'], hbq['bundle'], task_contract=contract)
    c.require(row['compiled_sha256'] == manifest['artifacts']['compiled.json']['sha256']
              and [q['question']['id'] for q in hbq['core'].compiled_questions(compiled)] == hbq['ids'], 'Scoring compiler/task differs from frozen bank')
    try:
        normalized = []
        for item in sorted(admitted, key=lambda item: item['request']['batch']):
            r = item['request']; _, _, texts, context = c.inputs(root, manifest, r)
            normalized.extend(hbq['runner']._normalize_batch(item['response'], expected_ids=r['question_ids'],
                artifact_id=r['artifact_id'], bundle_id=r['bundle_id'], judge_id=r['endpoint'], run_id=r['logical_sample_id'],
                artifact_text=texts[r['sources'][0]['id']], context_texts=[context]))
        report = hbq['scorer'].score_bundle(hbq['modules'], hbq['bundle'], normalized, artifact_id=row['artifact_id'],
            task_contract=contract, admission_policy='strict_import_v1')
    except ValueError:
        return {**base, 'state': 'strict_import_unadmitted_no_scalar'}
    return {**base, 'score': report['final_score']['observed'] if report['status'] == 'SCORED' else None,
        'state': report['status'], 'weighted_coverage': report['coverage'], 'uncertainty_bounds': report['final_score'],
        'penalty_deduction': report['penalty_deduction'], 'issue_count': len(report['issues']), 'report_version': report['report_version']}


def profiles(manifest, records, hbq, root):
    planned = defaultdict(list); admitted = defaultdict(list)
    key = lambda r: (r['endpoint'], r['arm'], r['artifact_id'], r['repeat'])
    for row in manifest['requests']:
        if row['arm'] != 'pairwise': planned[key(row)].append(row)
    for item in records:
        if item['request']['arm'] != 'pairwise': admitted[key(item['request'])].append(item)
    out = {}
    for identity, rows in planned.items():
        items = admitted[identity]; arm = identity[1]
        if arm == 'hbq': out[identity] = score_bank(rows, items, hbq, root, manifest)
        elif not items: out[identity] = {'score': None, 'state': 'missing_unadmitted_no_scalar', 'leaves': {}}
        else:
            c.require(len(items) == 1, 'Duplicate scalar observation')
            answer = items[0]['response']
            if arm == 'ttcw14':
                leaves = {v['test_id']: v['verdict'] for v in answer['verdicts']}
                assessed = sum(v in ('YES', 'NO') for v in leaves.values())
                out[identity] = {'score': sum(v == 'YES' for v in leaves.values()) / 14 if assessed == len(leaves) == 14 else None,
                    'state': 'assessed' if assessed == len(leaves) == 14 else 'partial_abstention_no_scalar', 'leaves': leaves,
                    'coverage': {'expected_leaves': 14, 'native_leaves': len(leaves), 'assessed_binary': assessed, 'states': dict(Counter(leaves.values()))}}
            else:
                abstained = answer['status'] == 'CANNOT_ASSESS'
                out[identity] = {'score': None if abstained else answer['result'][{'holistic': 'score', 'compact': 'overall_score', 'oregon': 'total_score'}[arm]],
                                 'state': 'explicit_abstention' if abstained else 'assessed', 'leaves': {}}
    return out


def distribution(values, arm):
    low, high = RANGES[arm]; counts = Counter(values)
    affine = [100 * (v - low) / (high - low) for v in values]
    return {'n': len(values), 'native_range': [low, high], 'minimum': min(values) if values else None,
        'maximum': max(values) if values else None, 'mean': statistics.mean(values) if values else None,
        'affine_range': [0, 100], 'affine_mean': statistics.mean(affine) if affine else None,
        'distinct_scores': len(counts), 'items_in_ties': sum(n for n in counts.values() if n > 1),
        'tied_unordered_pairs': sum(n*(n-1)//2 for n in counts.values()), 'floor': counts[low], 'ceiling': counts[high],
        'near_floor_10_percent_range': sum(v <= low + .1*(high-low) for v in values),
        'near_ceiling_10_percent_range': sum(v >= high - .1*(high-low) for v in values)}


def transitions(left, right, identities):
    counts = Counter(); binary = binary_matches = matches = flips = 0
    for identity in identities:
        a, b = left.get(identity, {}), right.get(identity, {})
        for qid in a.keys() & b.keys():
            counts[a[qid] + '->' + b[qid]] += 1; matches += a[qid] == b[qid]
            flips += (a[qid] == 'NOT_APPLICABLE') != (b[qid] == 'NOT_APPLICABLE')
            binary += a[qid] in ('YES', 'NO') and b[qid] in ('YES', 'NO')
            binary_matches += a[qid] == b[qid] and a[qid] in ('YES', 'NO')
    return {'observed_pairs': sum(counts.values()), 'four_state_counts': dict(counts), 'exact_matches': matches,
            'exact_agreement': fraction(matches, sum(counts.values())), 'paired_binary': binary,
            'binary_exact_matches': binary_matches, 'binary_agreement': fraction(binary_matches, binary), 'not_applicable_activation_flips': flips}


def scalar_diagnostics(manifest, bank_profiles):
    out = {}; sentinel_ids = {v for g in manifest['selection']['groups'] if g['id'] in manifest['selection']['sentinel_group_ids'] for v in g['variant_ids']}
    for endpoint in c.p.ENDPOINTS:
        for arm in RANGES:
            initial = {key[2]: value for key, value in bank_profiles.items() if key[0] == endpoint and key[1] == arm and key[3] == 0}
            scores = [p['score'] for p in initial.values() if p['score'] is not None]
            deltas = []; repeat_transitions = Counter(); transition_totals = Counter()
            for cycle in (1, 2):
                repeat = {aid: bank_profiles.get((endpoint, arm, aid, cycle), {}) for aid in sentinel_ids}
                for aid in sentinel_ids:
                    a, b = initial.get(aid, {}).get('score'), repeat[aid].get('score')
                    if a is not None and b is not None: deltas.append(abs(a-b))
                t = transitions({aid: initial.get(aid, {}).get('leaves', {}) for aid in sentinel_ids},
                    {aid: repeat[aid].get('leaves', {}) for aid in sentinel_ids}, sentinel_ids)
                repeat_transitions.update(t['four_state_counts'])
                transition_totals.update({k: t[k] for k in ('observed_pairs', 'exact_matches', 'paired_binary', 'binary_exact_matches', 'not_applicable_activation_flips')})
            entry = {'planned_initial_paragraphs': 282, 'missing_or_abstained_scalars': 282-len(scores),
                'profile_states': dict(Counter(p['state'] for p in initial.values())), 'distribution': distribution(scores, arm),
                'repeat': {'planned_scalar_comparisons': 36, 'observed_scalar_comparisons': len(deltas),
                    'exact_scalar_matches': sum(d == 0 for d in deltas), 'mean_absolute_native_delta': statistics.mean(deltas) if deltas else None,
                    'independent_triplets_added': 0}}
            if arm in ('hbq', 'ttcw14'):
                expected = 170 if arm == 'hbq' else 14
                entry['repeat']['leaf_transitions'] = {**dict(transition_totals), 'planned_pairs': 36*expected,
                    'four_state_counts': dict(repeat_transitions), 'exact_agreement': fraction(transition_totals['exact_matches'], transition_totals['observed_pairs']),
                    'binary_agreement': fraction(transition_totals['binary_exact_matches'], transition_totals['paired_binary'])}
                native = sum((Counter(p.get('coverage', {}).get('states', {})) for p in initial.values()), Counter())
                applicable = sum(native.values()) - native['NOT_APPLICABLE']
                entry['leaf_coverage'] = {'planned_initial_leaves': 282*expected, 'observed_initial_leaves': sum(native.values()),
                    'missing_native_leaves': 282*expected-sum(native.values()), 'observed_initial_states': dict(native),
                    'observed_applicable': applicable, 'assessed_over_observed_applicable': fraction(native['YES'] + native['NO'], applicable),
                    'complete_bank_profiles': sum(p['state'] not in ('incomplete_or_duplicate_full_bank_no_scalar', 'missing_unadmitted_no_scalar') for p in initial.values())}
            if arm == 'hbq':
                entry['hbq_weighted_coverage_mean'] = statistics.mean([p['weighted_coverage'] for p in initial.values() if 'weighted_coverage' in p]) if any('weighted_coverage' in p for p in initial.values()) else None
                penalties = [p['penalty_deduction']['observed'] for p in initial.values() if 'penalty_deduction' in p]
                entry['penalty_deduction'] = {'observations': len(penalties), 'mean': statistics.mean(penalties) if penalties else None,
                    'nonzero': sum(p > 0 for p in penalties), 'provisional_profiles': sum(p['state'] == 'PROVISIONAL' for p in initial.values())}
            out[endpoint + ':' + arm] = entry
    return out


def pair_diagnostics(manifest, records):
    pairs = {p['pair_id']: p for p in manifest['selection']['pairs']}; orders = {}; native_states = defaultdict(Counter)
    for item in records:
        r, answer = item['request'], item['response']
        if r['arm'] != 'pairwise': continue
        key = (r['endpoint'], r['pair_id'], r['repeat'], r['orientation'])
        c.require(key not in orders, 'Duplicate ordered pair observation')
        winner = answer['winner']; native_states[(r['endpoint'], r['repeat'])][winner] += 1
        chosen = next((s['id'] for s in r['sources'] if s['side'] == winner), None)
        orders[key] = None if winner == 'CANNOT_ASSESS' else .5 if winner == 'TIE' else float(chosen == pairs[r['pair_id']]['left'])
    def consensus(endpoint, pid, cycle):
        values = [orders.get((endpoint, pid, cycle, o)) for o in ('AB', 'BA')]
        return statistics.mean(values) if all(v is not None for v in values) else None
    out = {}
    for endpoint in c.p.ENDPOINTS:
        gaps = []; signed = []; consensus_values = []; repeats = []
        for pid, pair in pairs.items():
            values = [orders.get((endpoint, pid, 0, o)) for o in ('AB', 'BA')]
            base = consensus(endpoint, pid, 0)
            if base is not None: consensus_values.append(base); gaps.append(abs(values[0]-values[1])); signed.append(values[0]-values[1])
            if pair['group_id'] in manifest['selection']['sentinel_group_ids']:
                for cycle in (1, 2):
                    repeat = consensus(endpoint, pid, cycle)
                    if base is not None and repeat is not None: repeats.append(abs(base-repeat))
        out[endpoint] = {'planned_initial_pairs': 282, 'planned_initial_ordered_requests': 564, 'complete_AB_BA_pairs': len(gaps),
            'native_initial_winner_states': dict(native_states[(endpoint, 0)]), 'consensus_ties_including_order_conflicts': sum(v == .5 for v in consensus_values),
            'order_disagreements': sum(v > 0 for v in gaps), 'mean_absolute_order_gap': statistics.mean(gaps) if gaps else None,
            'mean_AB_minus_BA_canonical_left_preference': statistics.mean(signed) if signed else None,
            'repeat_planned_consensus_comparisons': 36, 'repeat_observed_consensus_comparisons': len(repeats),
            'repeat_exact_consensus_matches': sum(v == 0 for v in repeats), 'repeat_mean_absolute_consensus_delta': statistics.mean(repeats) if repeats else None,
            'global_pair_graph_ranking': False}
    matched_orders = []; matched_consensus = []; native_ties = Counter(); consensus_kinds = Counter()
    for pid, pair in pairs.items():
        cycles = (0, 1, 2) if pair['group_id'] in manifest['selection']['sentinel_group_ids'] else (0,)
        for cycle in cycles:
            for orientation in ('AB', 'BA'):
                s, g = [orders.get((ep, pid, cycle, orientation)) for ep in ('sol', 'grok')]
                if s is not None and g is not None:
                    matched_orders.append((s, g))
                    native_ties['both_native_ties'] += s == g == .5
                    native_ties['one_native_tie'] += (s == .5) != (g == .5)
            s, g = [consensus(ep, pid, cycle) for ep in ('sol', 'grok')]
            if s is not None and g is not None:
                matched_consensus.append((s, g))
                values = [[orders[(ep, pid, cycle, o)] for o in ('AB', 'BA')] for ep in ('sol', 'grok')]
                conflict = any(v[0] != v[1] for v in values)
                consensus_kinds['comparisons_with_any_order_conflict'] += conflict
                consensus_kinds['equal_consensus_with_any_order_conflict'] += s == g and conflict
                consensus_kinds['both_endpoints_two_native_ties'] += all(v == [.5, .5] for v in values)
    out['cross_endpoint'] = {'same_order': {**preference_comparison(matched_orders, 636), **dict(native_ties)},
        'AB_BA_consensus': {**preference_comparison(matched_consensus, 318), **dict(consensus_kinds),
            'interpretation': 'Arithmetic canonical-left preference; equal .5 may be an order conflict, not a native tie.'},
        'independent_triplets': 94, 'repeats_add_independent_triplets': 0, 'global_pair_graph_ranking': False}
    return out


def preference_comparison(comparisons, planned):
    matches = sum(s == g for s, g in comparisons); observed = len(comparisons); missing = planned-observed
    c.require(0 <= matches <= observed <= planned, 'Matched preference denominator differs')
    return {'planned_comparisons': planned, 'observed_comparisons': observed, 'unresolved_comparisons': missing,
        'exact_agreements': matches, 'disagreements': observed-matches, 'complete_case_agreement': fraction(matches, observed),
        'full_denominator_agreement_bounds': [fraction(matches, planned), fraction(matches+missing, planned)],
        'mean_absolute_canonical_preference_delta': statistics.mean(abs(s-g) for s, g in comparisons) if comparisons else None}


def within_triplet_rank(manifest, bank_profiles, arm):
    counts = Counter(); represented = set(); observed = 0
    for pair in manifest['selection']['pairs']:
        directions = []
        for endpoint in ('sol', 'grok'):
            left, right = [bank_profiles.get((endpoint, arm, pair[side], 0), {}).get('score') for side in ('left', 'right')]
            if left is None or right is None: break
            directions.append((left > right)-(left < right))
        if len(directions) != 2: continue
        s, g = directions; observed += 1; represented.add(pair['group_id'])
        counts['concordant_non_tied'] += s == g and s != 0
        counts['discordant_non_tied'] += s*g == -1
        counts['sol_only_tie'] += s == 0 and g != 0
        counts['grok_only_tie'] += g == 0 and s != 0
        counts['both_ties'] += s == g == 0
    concordant, discordant = counts['concordant_non_tied'], counts['discordant_non_tied']
    matches = concordant + counts['both_ties']; missing = 282-observed
    c.require(0 <= observed <= 282, 'Within-triplet rank denominator differs')
    denominator = math.sqrt((concordant+discordant+counts['sol_only_tie'])*(concordant+discordant+counts['grok_only_tie']))
    return {'planned_within_triplet_pairs': 282, 'observed_pairs': observed, 'unresolved_pairs': missing,
        'clusters_with_observed_pairs': len(represented), 'planned_clusters': 94, 'direction_counts': dict(counts),
        'complete_case_exact_direction_agreement': fraction(matches, observed),
        'non_tied_direction_agreement': fraction(concordant, concordant+discordant),
        'full_denominator_exact_direction_agreement_bounds': [matches/282, (matches+missing)/282],
        'within_triplet_kendall_tau_b': (concordant-discordant)/denominator if denominator else None,
        'unobserved_tau_bounds': [-1, 1] if missing else None,
        'rank_scope': 'Only the three canonical pairs per triplet; no cross-triplet ordering or human target.',
        'state': 'descriptive_complete_prediction_cohort' if not missing else 'descriptive_partial_prediction_cohort'}


def percentile(values, probability):
    ordered = sorted(values); location = probability*(len(ordered)-1); lo, hi = math.floor(location), math.ceil(location)
    return ordered[lo] + (ordered[hi]-ordered[lo])*(location-lo)


def triplet_bootstrap(values, planned_groups, reps=2000):
    """TTCW cluster-percentile method adapted to the 94 prospective LAMP triplets."""
    c.require(1 <= reps <= 2000 and len(planned_groups) == len(set(planned_groups)) == 94, 'Finite bootstrap or full triplet denominator differs')
    if set(values) != set(planned_groups):
        return {'state': 'not_estimated', 'reason': 'Incomplete paired triplet cohort', 'represented_clusters': len(values), 'planned_clusters': 94}
    rng = random.Random(20261004); groups = sorted(planned_groups)
    samples = [statistics.mean(values[g] for g in rng.choices(groups, k=94)) for _ in range(reps)]
    return {'state': 'descriptive_paired_triplet_sensitivity', 'planned_clusters': 94, 'replicates': reps, 'seed': 20261004,
            'percentile_95': [percentile(samples, .025), percentile(samples, .975)], 'human_alignment': False}


def endpoint_diagnostics(manifest, bank_profiles, reps):
    out = {}; groups = manifest['selection']['groups']; ids = {v for g in groups for v in g['variant_ids']}
    for arm, (low, high) in RANGES.items():
        differences = {}; by_group = {}; strata = Counter()
        for aid in ids:
            s, g = [bank_profiles.get((ep, arm, aid, 0), {}).get('score') for ep in ('sol', 'grok')]
            if s is not None and g is not None: differences[aid] = 100*(s-g)/(high-low)
        for group in groups:
            values = [differences.get(aid) for aid in group['variant_ids']]
            if all(v is not None for v in values): by_group[group['id']] = statistics.mean(values); strata[group['stratum']] += 1
        entry = {'planned_paired_paragraphs': 282, 'paired_paragraphs': len(differences), 'complete_triplets': len(by_group),
            'complete_triplets_by_stratum': dict(strata), 'mean_affine_sol_minus_grok': statistics.mean(differences.values()) if differences else None,
            'mean_absolute_affine_endpoint_delta': statistics.mean(abs(v) for v in differences.values()) if differences else None,
            'triplet_equal_weight_mean_affine_sol_minus_grok': statistics.mean(by_group.values()) if by_group else None,
            'bootstrap': triplet_bootstrap(by_group, [g['id'] for g in groups], reps),
            'within_triplet_rank_agreement': within_triplet_rank(manifest, bank_profiles, arm)}
        if arm in ('hbq', 'ttcw14'):
            entry['leaf_transitions_sol_to_grok'] = {**transitions(
                {aid: bank_profiles.get(('sol', arm, aid, 0), {}).get('leaves', {}) for aid in ids},
                {aid: bank_profiles.get(('grok', arm, aid, 0), {}).get('leaves', {}) for aid in ids}, ids),
                'planned_pairs': 282*(170 if arm == 'hbq' else 14)}
        out[arm] = entry
    return out


def load_human_profile(manifest):
    profile = json.loads(c.p.checked(HERE / 'human_profile.json', HUMAN_PROFILE_SHA))
    c.require(profile['schema_version'] == 1 and profile['manifest_sha256'] == c.MANIFEST_SHA
              and profile['locator_packet_sha256'] == manifest['locator_packet_sha256'], 'Human profile source binding differs')
    c.require([r['groups'] for r in profile['targets']] == [8, 13, 14, 11, 23, 25]
              and [r['stratum'] for r in profile['targets']] == list(range(6))
              and profile['admitted_groups'] == 94 and profile['paragraphs'] == 282
              and profile['assessor_orders'] == 282 and profile['correlated_pair_ballots'] == 846
              and profile['source_assessor_ids'] == 11 and not profile['verified_independent_people']
              and profile['earlier_order_position_is_preferred'] and not profile['human_ties']
              and profile['human_scalar_scale'] is None, 'Human ordinal profile differs')
    for row in profile['targets']:
        for path, pin in ((row['source_freeze'], row['source_freeze_sha256']),
                          (row['membership'], row['membership_sha256'])):
            c.require(manifest['source_pins'].get(path) == pin, 'Human membership/freeze is outside frozen sources')
    return profile


def decode_rankings(document, receipt, admitted):
    """Post-gate ordinal decoder; source roles never determine a preference."""
    c.require(document['schema_version'] == 1, 'Unsupported retained ranking schema')
    groups = document[receipt['groups_key']]
    c.require(len(groups) == receipt['groups'] == len(admitted), 'Human admitted group count differs')
    seen = set(); orders = []
    for group in groups:
        gid = group['id']
        c.require(gid in admitted and gid not in seen, 'Human group is duplicate or outside admitted membership')
        seen.add(gid); bridge = admitted[gid]; variants = bridge['variants']
        assessors = group['assessors']
        c.require(isinstance(assessors, dict) and len(assessors) == 3, 'Expected exactly three source assessor orders')
        for source_id, record in assessors.items():
            c.require(isinstance(source_id, str) and bool(source_id)
                      and set(record) == {'instruction_id_local_only', 'ordered_variant_ids_local_only'}
                      and type(record['instruction_id_local_only']) is int, 'Unsupported retained assessor record')
            ranked = record['ordered_variant_ids_local_only']
            c.require(isinstance(ranked, list) and len(ranked) == 3 and all(isinstance(v, str) for v in ranked)
                      and len(set(ranked)) == 3 and set(ranked) == set(variants), 'Rank order is not the admitted triplet permutation')
            orders.append({'group_id': bridge['id'], 'source_assessor_id': source_id,
                           'order': [variants[v] for v in ranked]})
    c.require(seen == set(admitted) and len(orders) == receipt['assessor_orders'], 'Human order inventory differs')
    return orders


def load_human_orders(manifest, root, control, profile):
    # This function is reachable only after the unchanged native collector release gate.
    lineage = json.loads(c.pinned(root, 'private/source-lineage.json', manifest['artifacts']['private/source-lineage.json']))
    selected = {g['id']: g for g in manifest['selection']['groups']}; by_stratum = defaultdict(dict); all_paragraphs = set()
    c.require(len(lineage) == len(selected) == 94, 'Human lineage group geometry differs')
    seen = set()
    for group in lineage:
        source_gid, gid = group['source_group_id'], group['id']; stratum = group['stratum']
        c.require(gid in selected and gid not in seen and stratum == selected[gid]['stratum']
                  and gid == 'lg-' + c.digest(c.canonical([c.p.POLICY, source_gid]))[:24]
                  and source_gid not in by_stratum[stratum], 'Human original/new group bridge differs')
        seen.add(gid); variants = {}
        for variant in group['variants']:
            source_vid, aid = variant['source_variant_id'], variant['id']
            c.require(source_vid not in variants and aid not in all_paragraphs
                      and aid == 'lp-' + c.digest(c.canonical([c.p.POLICY, source_gid, source_vid]))[:24], 'Human paragraph bridge differs')
            meta = manifest['artifacts']['inputs/' + aid + '.txt']
            c.require(meta['sha256'] == variant['source_sha256'] and meta['bytes'] == variant['source_bytes'], 'Human source paragraph commitment differs')
            variants[source_vid] = aid; all_paragraphs.add(aid)
        c.require(len(variants) == 3 and set(variants.values()) == set(selected[gid]['variant_ids']), 'Human admitted variant membership differs')
        by_stratum[stratum][source_gid] = {'id': gid, 'variants': variants}
    c.require(seen == set(selected) and len(all_paragraphs) == 282 and set(by_stratum) == set(range(6)), 'Human full admitted lineage differs')
    for source in profile['decoder_sources']:
        c.p.checked(c.p.within(control, source['path']), source['sha256'])
    orders = []
    for index, row in enumerate(profile['targets']):
        raw = c.p.checked(c.p.within(control, row['path']), row['sha256'], row['bytes'])
        document = json.loads(raw)
        metadata = {key: document[key] for key in ('source_revision', 'source_freeze_sha256',
                    'pretarget_predictions_sha256', 'ranking_source_pins')}
        c.require(c.digest(c.canonical(metadata)) == row['receipt_metadata_sha256']
                  and document['source_revision'] == profile['source_revision']
                  and document['source_freeze_sha256'] == row['source_freeze_sha256']
                  and document['pretarget_predictions_sha256'] == row['pretarget_predictions_sha256']
                  and c.digest(c.canonical(document['ranking_source_pins'])) == row['ranking_source_pins_sha256'], 'Human retained extraction receipt differs')
        orders.extend(decode_rankings(document, row, by_stratum[index]))
    c.require(len(orders) == 282 and len({r['source_assessor_id'] for r in orders}) == 11, 'Human source assessor inventory differs')
    return orders


def human_ballots(manifest, orders):
    by_group = defaultdict(list)
    for order in orders: by_group[order['group_id']].append(order)
    ballots = {}
    for pair in manifest['selection']['pairs']:
        group_orders = by_group[pair['group_id']]
        c.require(len(group_orders) == 3 and len({o['source_assessor_id'] for o in group_orders}) == 3,
                  'Human group requires three distinct source orders')
        votes = []
        for order in group_orders:
            c.require(len(order['order']) == len(set(order['order'])) == 3
                      and pair['left'] in order['order'] and pair['right'] in order['order'], 'Human pair/order join differs')
            votes.append((order['source_assessor_id'], 1 if order['order'].index(pair['left']) < order['order'].index(pair['right']) else -1))
        c.require(pair['pair_id'] not in ballots, 'Duplicate human canonical pair')
        ballots[pair['pair_id']] = votes
    return ballots


def human_direction_metrics(manifest, ballots, directions, reps):
    majority = []; individual = []; by_group = defaultdict(list); by_source = defaultdict(list); ties = 0
    for pair in manifest['selection']['pairs']:
        direction = directions.get(pair['pair_id'])
        if direction is None: continue
        c.require(direction in (-1, 0, 1), 'Invalid model preference direction')
        votes = ballots[pair['pair_id']]; preferred = 1 if sum(v for _, v in votes) > 0 else -1
        credit = .5 if direction == 0 else float(direction == preferred)
        majority.append(credit); ties += direction == 0
        credits = [.5 if direction == 0 else float(direction == vote) for _, vote in votes]
        individual.extend(credits); by_group[pair['group_id']].append((credit, statistics.mean(credits)))
        for (sid, _), value in zip(votes, credits): by_source[sid].append(value)
    def measure(values, denominator):
        total = sum(values); missing = denominator-len(values)
        c.require(0 <= len(values) <= denominator, 'Human agreement denominator differs')
        return {'planned': denominator, 'observed': len(values), 'missing': missing,
                'complete_case_half_tie_credit_agreement': fraction(total, len(values)),
                'all_planned_agreement_bounds': [total/denominator, (total+missing)/denominator]}
    groups = [g['id'] for g in manifest['selection']['groups']]
    complete = {gid: statistics.mean(v[0] for v in values) for gid, values in by_group.items() if len(values) == 3}
    individual_complete = {gid: statistics.mean(v[1] for v in values) for gid, values in by_group.items() if len(values) == 3}
    loss = 94-len(complete); leave_one_out = []
    for excluded in {sid for votes in ballots.values() for sid, _ in votes}:
        values = [v for sid, scores in by_source.items() if sid != excluded for v in scores]
        if values: leave_one_out.append(statistics.mean(values))
    bootstrap = triplet_bootstrap(complete, groups, reps); bootstrap['human_alignment'] = True
    report = {'majority_pairs': measure(majority, 282), 'individual_correlated_pair_ballots': measure(individual, 846),
        'model_zero_directions': ties, 'tie_credit': .5, 'complete_triplets': len(complete), 'planned_triplets': 94,
        'source_group_loss_fraction': loss/94, 'state': 'inconclusive_source_group_loss' if loss/94 > .1 else 'descriptive_development_alignment',
        'triplet_bootstrap': bootstrap,
        'crossed_source_assessor_sensitivity': {'method': 'Leave one reused source assessor ID out; no independent-person claim',
            'source_ids': 11, 'represented_source_ids': len(by_source), 'verified_independent_people': False,
            'individual_agreement_range': [min(leave_one_out), max(leave_one_out)] if leave_one_out else None}}
    return report, complete, individual_complete


def human_metrics(manifest, orders, banks, records, reps):
    ballots = human_ballots(manifest, orders); ordered_pairs = {}
    for item in records:
        row, answer = item['request'], item['response']
        if row['arm'] != 'pairwise' or row['repeat'] != 0: continue
        pair = next(p for p in manifest['selection']['pairs'] if p['pair_id'] == row['pair_id'])
        winner = answer['winner']; chosen = next((s['id'] for s in row['sources'] if s['side'] == winner), None)
        key = (row['endpoint'], row['pair_id'], row['orientation'])
        c.require(key not in ordered_pairs, 'Duplicate initial native pair order')
        ordered_pairs[key] = None if winner == 'CANNOT_ASSESS' else 0 if winner == 'TIE' else 1 if chosen == pair['left'] else -1
    out = {}; cluster_values = {}; groups = [g['id'] for g in manifest['selection']['groups']]
    for endpoint in c.p.ENDPOINTS:
        for arm in (*RANGES, 'pairwise'):
            directions = {}; kinds = Counter()
            for pair in manifest['selection']['pairs']:
                pid = pair['pair_id']
                if arm == 'pairwise':
                    values = [ordered_pairs.get((endpoint, pid, orientation)) for orientation in ('AB', 'BA')]
                    if any(v is None for v in values): continue
                    total = sum(values); directions[pid] = (total > 0)-(total < 0)
                    kinds['two_native_ties'] += values == [0, 0]
                    kinds['AB_BA_order_conflicts'] += values[0] != values[1]
                    kinds['zero_consensus_with_order_conflict'] += total == 0 and values[0] != values[1]
                else:
                    values = [banks.get((endpoint, arm, pair[side], 0), {}).get('score') for side in ('left', 'right')]
                    if any(v is None for v in values): continue
                    directions[pid] = (values[0] > values[1])-(values[0] < values[1])
            report, majority, individual = human_direction_metrics(manifest, ballots, directions, reps)
            if arm == 'pairwise': report['native_order_consensus_kinds'] = dict(kinds)
            out[endpoint + ':' + arm] = report; cluster_values[(endpoint, arm)] = (majority, individual)
        base = cluster_values[(endpoint, 'hbq')][0]
        for arm in (*RANGES, 'pairwise'):
            if arm == 'hbq': continue
            alternative = cluster_values[(endpoint, arm)][0]
            shared = set(base) & set(alternative)
            paired = triplet_bootstrap({gid: alternative[gid]-base[gid] for gid in shared}, groups, reps)
            paired['human_alignment'] = True
            paired['arm_dependent_complete_triplet_attrition'] = set(base) != set(alternative)
            out[endpoint + ':' + arm]['paired_majority_agreement_minus_hbq'] = paired
    c.require(len(ballots) == 282 and sum(len(v) for v in ballots.values()) == 846, 'Full human ballot denominator differs')
    return {'arms': out, 'rank_orders': 282, 'correlated_pair_ballots': 846, 'majority_pairs': 282,
            'unanimous_human_pairs': sum(abs(sum(v for _, v in votes)) == 3 for votes in ballots.values()),
            'human_ties': False, 'human_scalar_scale': None, 'source_assessor_ids': 11,
            'verified_independent_people': False, 'global_pair_graph_ranking': False}


def human_alignment(manifest, root, manifest_sha, tools, outputs, receipts, subset, validator, explicit_release,
                    *, control=None, banks=None, records=None, reps=2000):
    if not explicit_release:
        return {'state': 'sealed_skipped_before_decode', 'human_targets_opened': False, 'explicit_postprediction_release': False,
                'human_profile_sha256': HUMAN_PROFILE_SHA, 'actual_human_id_joins_and_metrics_verified': False}
    gate = c.label_release_gate(manifest, root, manifest_sha, tools, outputs, receipts, subset, validator, True)
    c.require(gate['human_release_eligible'], 'Unchanged collector gate requires all17808 verified original terminals before label decode')
    c.require(control is not None and banks is not None and records is not None, 'Postprediction release requires exact control root and replayed predictions')
    profile = load_human_profile(manifest)
    orders = load_human_orders(manifest, root, control.resolve(), profile)
    return {'state': 'descriptive_development_alignment', 'gate': gate, 'human_targets_opened': True,
            'explicit_postprediction_release': True, 'human_profile_sha256': HUMAN_PROFILE_SHA,
            'target_receipt_sha256': [r['sha256'] for r in profile['targets']],
            'actual_human_id_joins_and_metrics_verified': True, **human_metrics(manifest, orders, banks, records, reps)}


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--manifest', type=Path, required=True); parser.add_argument('--manifest-sha256', required=True)
    parser.add_argument('--tools-root', type=Path, required=True)
    parser.add_argument('--control-root', type=Path, help='Required only after explicit successful label release')
    parser.add_argument('--human-profile-only', action='store_true', help='Check pinned metadata readiness without opening results, lineage or human targets')
    parser.add_argument('--sol-results-dir', type=Path); parser.add_argument('--grok-results-dir', type=Path)
    parser.add_argument('--bootstrap-reps', type=int, default=2000)
    parser.add_argument('--explicit-postprediction-release', action='store_true')
    args = parser.parse_args(); c.require(1 <= args.bootstrap_reps <= 2000, 'Finite bootstrap repetitions must be 1..2000')
    if args.human_profile_only:
        c.require(not args.explicit_postprediction_release, 'Metadata-only check cannot release human ranks')
        manifest = json.loads(c.p.checked(args.manifest, args.manifest_sha256))
        c.require(args.manifest_sha256 == c.MANIFEST_SHA
                  and c.digest(c.canonical({k: v for k, v in manifest.items() if k != 'manifest_content_sha256'}))
                  == manifest['manifest_content_sha256'], 'Frozen manifest metadata commitment differs')
        load_human_profile(manifest)
        print(json.dumps({'policy': 'matched_lamp_human_profile_metadata_only_v1', 'manifest_sha256': args.manifest_sha256,
            'human_profile_sha256': HUMAN_PROFILE_SHA, 'planned_requests': 17808, 'admitted_groups': 94,
            'prospective_rank_orders': 282, 'prospective_correlated_pair_ballots': 846,
            'human_targets_opened': False, 'labels_read': False, 'provider_calls': 0,
            'actual_human_id_joins_and_metrics_verified': False}, sort_keys=True)); return 0
    manifest, root, subset, validator, receipts, hbq = load_manifest(args.manifest, args.manifest_sha256, args.tools_root)
    load_human_profile(manifest)
    outputs = {ep: (getattr(args, ep + '_results_dir') or root.parent / (ep + '-001')).resolve() for ep in c.p.ENDPOINTS}
    for output in outputs.values(): c.output_preflight(output, root)
    records, states = collect_evidence(manifest, args.manifest_sha256, root, args.tools_root, outputs, subset, validator, receipts)
    banks = profiles(manifest, records, hbq, root)
    alignment = human_alignment(manifest, root, args.manifest_sha256, args.tools_root, outputs, receipts, subset, validator,
        args.explicit_postprediction_release, control=args.control_root, banks=banks, records=records, reps=args.bootstrap_reps)
    report = {'policy': 'matched_lamp_triplet_analysis_with_gated_human_ranks_v1', 'manifest_sha256': args.manifest_sha256,
        'analysis_sha256': c.digest(Path(__file__).read_bytes()), 'collector_sha256': COLLECTOR_SHA,
        'score_report_v2_schema_sha256': c.digest((c.p.REPO / 'schema/hbq_score_report.v2.schema.json').read_bytes()),
        'counts': manifest['counts'], 'planned_requests': 17808, 'endpoint_states': states,
        'scalars': scalar_diagnostics(manifest, banks), 'pairwise': pair_diagnostics(manifest, records),
        'paired_endpoints': endpoint_diagnostics(manifest, banks, args.bootstrap_reps),
        'human_alignment': alignment,
        'provider_calls': 0, 'human_targets_opened': alignment['human_targets_opened'], 'labels_read': alignment['human_targets_opened'],
        'limits': ['Already development-exposed 94 triplets; no unused or general expert claim.',
                   'Scalar profiles require complete admitted native banks; provisional reports remain provisional.',
                   'Affine transforms preserve native scale endpoints and do not establish construct equivalence.',
                   'Repeats add no independent works; pairwise comparisons stay within triplets.']}
    print(json.dumps(report, ensure_ascii=False, sort_keys=True, allow_nan=False)); return 0


if __name__ == '__main__': raise SystemExit(main())
