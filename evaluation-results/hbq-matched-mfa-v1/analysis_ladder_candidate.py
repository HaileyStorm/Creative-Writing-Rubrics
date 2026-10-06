"""Prospective ladder projection preparation; no native driver or label release."""
from collections import Counter, defaultdict
import argparse
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
PROFILE_PATH = HERE / 'ladder-candidate-profile.json'
PROFILE_SHA = 'd526fbba30d9e864f71e198c6a179a7ce360f21118ca393d49189f290e07a1b6'
SELECTIVE_PATH = HERE.parent / 'hbq-matched-hanna-20261004/prepare.py'
SELECTIVE_SHA = '2d82e4959c3296ccaa6e6521adb46f85588427d429a544b36a2891ebaea8c7b0'
POLICY = 'mfa_ladder_candidate_preparation_v1'
ARMS = ('historical', 'candidate')


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def checked(path, digest):
    raw = Path(path).read_bytes()
    require(sha(raw) == digest, 'Frozen profile/source commitment differs: ' + str(path))
    return raw


def verified_profile():
    profile = json.loads(checked(PROFILE_PATH, PROFILE_SHA))
    for locator, digest in profile['source_files_sha256'].items():
        checked(REPO / locator, digest)
    return profile


def runtime():
    profile = verified_profile()
    sys.path.insert(0, str(REPO / 'src'))
    from hbqrs import core, ladder_uncertainty, decision_readiness
    return profile, core, ladder_uncertainty, decision_readiness


def is_digest(value):
    return isinstance(value, str) and len(value) == 64 and all(c in '0123456789abcdef' for c in value)


def project_complete_bank(modules, bundle, verdicts, *, artifact_id, task_contract, verified_bank):
    """Project caller-replayed originals; verify completeness, not native receipts.

    The caller must establish frozen source/context and native/schema admission.
    Its receipt commitment is retained, not opened or independently replayed here.
    Strict original import admission occurs inside the pinned ladder API once.
    """
    profile, core, ladder, readiness = runtime()
    compiled = core.compile_bundle(modules, bundle, task_contract=task_contract)
    expected = [q['question']['id'] for q in core.compiled_questions(compiled)]
    packets = verified_bank['packets']
    ordered = sorted(packets, key=lambda p: p['batch'])
    require(bundle['bundle_id'] == 'prose.short_form' and len(expected) == len(set(expected)) == 170
        and len(ordered) == 22 and [p['batch'] for p in ordered] == list(range(1, 23))
        and [q for p in ordered for q in p['question_ids']] == expected
        and all(p['question_ids'] == expected[(p['batch']-1)*8:p['batch']*8] for p in ordered)
        and all(p['accepted'] is True and p['native_replay_verified'] is True and is_digest(p['request_sha256']) for p in ordered)
        and len({p['request_sha256'] for p in ordered}) == 22
        and len(verdicts) == 170 and Counter(v['question_id'] for v in verdicts) == Counter(expected),
        'Complete unique admitted170-leaf/22-packet bank required before projection')
    require(verified_bank['artifact_id'] == artifact_id and verified_bank['endpoint'] in ('sol', 'grok')
        and type(verified_bank['repeat']) is int and verified_bank['repeat'] in (0, 1, 2)
        and verified_bank['manifest_sha256'] == profile['cohorts']['mfa_quality_development_manifest_sha256']
        and is_digest(verified_bank['native_replay_receipt_sha256'])
        and verified_bank['frozen_source_context_verified'] is True
        and verified_bank['raw_normalized_verdicts_sha256'] == ladder.canonical_json_sha256(list(verdicts)),
        'Caller verified-bank identity/context/original commitment differs')
    reports = ladder.score_bundle(modules, bundle, verdicts, artifact_id=artifact_id,
                                 task_contract=task_contract, admission_policy='strict_import_v1')
    changes = reports['candidate_report']['ladder_projection']['changes']
    return {**reports, 'historical_readiness': readiness.decision_readiness(reports['historical_report']),
        'candidate_readiness': readiness.decision_readiness(reports['candidate_report']),
        'changed_states': dict(Counter(c['raw_state'] + '->' + c['effective_state'] for c in changes)),
        'change_count': len(changes), 'provenance': {'policy': POLICY, 'profile_sha256': PROFILE_SHA,
            'source_files_sha256': profile['source_files_sha256'], 'complete_bank': True,
            'artifact_id': artifact_id, 'endpoint': verified_bank['endpoint'], 'repeat': verified_bank['repeat'],
            'manifest_sha256': verified_bank['manifest_sha256'], 'caller_bank_receipt_sha256': sha(canonical(verified_bank)),
            'native_replay_receipt_sha256': verified_bank['native_replay_receipt_sha256'],
            'native_replay_independently_verified_here': False,
            'frozen_modules_content_sha256': ladder.canonical_json_sha256(modules),
            'frozen_bundle_content_sha256': ladder.canonical_json_sha256(bundle),
            'compiled_content_sha256': ladder.canonical_json_sha256(compiled),
            'raw_verdicts_sha256': reports['candidate_report']['ladder_projection']['raw_verdicts_sha256'],
            'historical_report_sha256': ladder.canonical_json_sha256(reports['historical_report']),
            'candidate_report_sha256': ladder.canonical_json_sha256(reports['candidate_report']),
            'original_import_admission_count': 1, 'new_semantic_admissions': 0, 'new_native_votes': 0,
            'provider_calls': 0}}


def initial_pair_decisions(registered_pairs, projections, *, endpoint):
    """Use only caller-verified source pairs and initial banks, never repeats."""
    verified_profile()
    require(endpoint in ('sol', 'grok'), 'Unsupported endpoint')
    result, seen = [], set()
    for pair in registered_pairs:
        require(pair['membership_verified'] is True and pair['task'] == 'quality'
            and pair['panel'] in ('expert', 'lay') and pair['left'] != pair['right']
            and all(isinstance(pair[k], str) and pair[k] for k in ('pair_id', 'target_hash', 'condition', 'fine_variant'))
            and isinstance(pair['planned_ballot_ids'], list) and pair['planned_ballot_ids']
            and all(isinstance(v, str) and v for v in pair['planned_ballot_ids'])
            and len(pair['planned_ballot_ids']) == len(set(pair['planned_ballot_ids'])),
            'Verified registered quality pair/stratum required')
        stratum = (endpoint, pair['task'], pair['condition'], pair['panel'], pair['fine_variant'])
        identity = (*stratum, pair['pair_id'])
        require(identity not in seen, 'Duplicate registered pair/stratum')
        seen.add(identity)
        row = {'stratum': stratum, 'pair_id': pair['pair_id'], 'target_hash': pair['target_hash'], 'primary_repeat': 0,
               'planned_ballot_ids': list(pair['planned_ballot_ids'])}
        for arm in ARMS:
            scores, categories = [], []
            for tid in (pair['left'], pair['right']):
                projection = projections.get((endpoint, tid, 0))
                if projection is None:
                    categories.append('MISSING_INITIAL_BANK'); continue
                provenance = projection['provenance']
                require(provenance['complete_bank'] is True and provenance['artifact_id'] == tid
                    and provenance['endpoint'] == endpoint and provenance['repeat'] == 0
                    and provenance['profile_sha256'] == PROFILE_SHA, 'Initial bank projection identity differs')
                report = projection[arm + '_report']
                if report['hard_gate_status'] != 'VALID': categories.append('INVALID_OR_UNRESOLVED_GATE')
                elif report['status'] != 'SCORED': categories.append('UNAVAILABLE_STATUS')
                elif report['final_score']['observed'] is None: categories.append('UNAVAILABLE_SCALAR')
                else: scores.append(report['final_score']['observed'])
            if categories:
                row[arm] = {'decision': None, 'state': categories[0], 'unavailable_reasons': sorted(set(categories))}
            else:
                require(len(scores) == 2 and all(isinstance(v, (int, float)) and math.isfinite(v) for v in scores), 'Usable observed scores required')
                direction = (scores[0] > scores[1]) - (scores[0] < scores[1])
                row[arm] = {'decision': 'LEFT' if direction > 0 else 'RIGHT' if direction < 0 else None,
                            'state': 'DIRECTIONAL' if direction else 'TIE'}
        result.append(row)
    return result


def aggregate_all_planned(decisions, planned_ballots, *, caller_ballots_verified_and_released=False):
    """Pure point summaries; caller supplies already released, verified outcomes.

    No source reader or release authority is implemented. Clustered/crossed-rater
    inference remains pending, so point guards never establish a promotion claim.
    """
    profile = verified_profile()
    require(caller_ballots_verified_and_released is True, 'Caller-verified postprediction released ballots required')
    by_pair = {(*d['stratum'], d['pair_id']): d for d in decisions}
    require(len(by_pair) == len(decisions), 'Duplicate pair decisions')
    expected_ballots = [(*d['stratum'], bid) for d in decisions for bid in d['planned_ballot_ids']]
    require(len(expected_ballots) == len(set(expected_ballots)), 'Source ballot registered to multiple pairs in one stratum')
    groups, seen = defaultdict(list), set()
    for ballot in planned_ballots:
        key = (*ballot['stratum'], ballot['pair_id'])
        require(key in by_pair and ballot['target_hash'] == by_pair[key]['target_hash']
            and ballot['human_state'] in ('BINARY', 'TIE', 'UNKNOWN', 'MISSING')
            and (ballot['human_state'] != 'BINARY' or ballot['winner'] in ('LEFT', 'RIGHT')),
            'Registered ballot membership or source state differs')
        identity = (*ballot['stratum'], ballot['ballot_id'])
        require(identity not in seen and ballot['ballot_id'] in by_pair[key]['planned_ballot_ids'], 'Duplicate or unregistered planned ballot/stratum')
        seen.add(identity); groups[tuple(ballot['stratum'])].append(ballot)
    require(seen == set(expected_ballots), 'All registered planned ballot IDs required; missing labels must remain explicit')
    output = []
    for stratum in sorted({tuple(d['stratum']) for d in decisions}):
        ds = [d for d in decisions if tuple(d['stratum']) == stratum]; bs = groups[stratum]
        metrics = {}
        for arm in ARMS:
            states = Counter(d[arm]['state'] for d in ds)
            correct = unknown_directional = binary_directional = 0
            human_states = Counter(b['human_state'] for b in bs)
            majorities = defaultdict(Counter)
            for b in bs:
                prediction = by_pair[(*stratum, b['pair_id'])][arm]['decision']
                if b['human_state'] == 'BINARY':
                    majorities[b['pair_id']][b['winner']] += 1
                    binary_directional += prediction is not None
                    correct += prediction == b['winner']
                elif b['human_state'] in ('MISSING', 'UNKNOWN'):
                    unknown_directional += prediction is not None
            majority_correct = majority_known = majority_ties = 0
            for d in ds:
                votes = majorities[d['pair_id']]
                if not sum(votes.values()): continue
                if votes['LEFT'] == votes['RIGHT']: majority_ties += 1; continue
                majority_known += 1
                majority_correct += d[arm]['decision'] == ('LEFT' if votes['LEFT'] > votes['RIGHT'] else 'RIGHT')
            directional = states['DIRECTIONAL']
            metrics[arm] = {'planned_pairs': len(ds), 'directional_pairs': directional, 'pair_states': dict(states),
                'decision_coverage': directional/len(ds) if ds else None, 'planned_ballots': len(bs),
                'source_human_states': dict(human_states), 'correct_binary_decisions': correct,
                'all_planned_accuracy': correct/len(bs) if bs else None,
                'complete_case_binary_accuracy': correct/binary_directional if binary_directional else None,
                'all_planned_accuracy_bounds': [correct/len(bs), (correct+unknown_directional)/len(bs)] if bs else [None, None],
                'majority_pair_agreement_all_planned': majority_correct/len(ds) if ds else None,
                'majority_known_pairs': majority_known, 'majority_ties': majority_ties, 'model_ties_receive_half_credit': False}
        baseline, candidate = metrics['historical'], metrics['candidate']
        gain_count = candidate['correct_binary_decisions'] - baseline['correct_binary_decisions']
        gain = gain_count/len(bs) if bs else None
        coverage_pass = candidate['directional_pairs'] >= baseline['directional_pairs']
        output.append({'stratum': stratum, 'historical': baseline, 'candidate': candidate,
            'all_planned_point_gain': gain, 'coverage_guard_pass': coverage_pass,
            'expert_5pp_point_guard_pass': coverage_pass and bool(bs) and 20*gain_count >= len(bs) if stratum[3] == 'expert' else None,
            'source_target_clusters': len({d['target_hash'] for d in ds}),
            'improvement_claim_established': False, 'lay_noninferiority_claim_established': False,
            'remaining_claim_requirements': ['Supported complete native/source/label driver', 'Frozen confirmation membership and eligibility',
                profile['prospective_claim_rules']['resampling'], 'Clustered95-percent bounds, crossed-rater sensitivity and attrition checks']})
    return {'policy': POLICY, 'profile_sha256': PROFILE_SHA, 'strata': output, 'endpoint_averaging': False,
            'candidate_promoted': False, 'label_reader_implemented': False}


def metadata_view(manifest_path):
    profile = verified_profile()
    checked(SELECTIVE_PATH, SELECTIVE_SHA)
    spec = importlib.util.spec_from_file_location('mfa_ladder_selective_metadata', SELECTIVE_PATH)
    reader = importlib.util.module_from_spec(spec); spec.loader.exec_module(reader)
    raw = checked(manifest_path, profile['cohorts']['mfa_quality_development_manifest_sha256'])
    manifest = reader.project_json(raw, {'counts': True, 'scoring': True, 'selection_sha256': True, 'artifacts': True,
        'requests': [{'arm': True, 'artifact_id': True, 'endpoint': True, 'repeat': True, 'batch': True,
                      'question_ids': True, 'task': True, 'bundle_id': True}]})
    root = Path(manifest_path).resolve().parent
    selection_pin = manifest['artifacts']['selection.json']
    selection_raw = checked(root / 'selection.json', selection_pin['sha256'])
    require(len(selection_raw) == selection_pin['bytes'], 'Selection byte commitment differs')
    selection = reader.project_json(selection_raw, {'pairs': [{'pair_id': True, 'excerpt_hashes': True, 'metadata_row_sha256s': True}],
        'evaluation_units': [{'panel': True, 'condition': True, 'target_hash': True,
                             'row_memberships': [{'metadata_row_sha256': True, 'writer_hash': True}]}],
        'bank_sentinel_ids': True, 'pair_sentinel_ids': True})
    rows = manifest['requests']; banks = defaultdict(list)
    require(len(rows) == 868 and all(r['task'] == 'quality' and r['bundle_id'] == 'prose.short_form' for r in rows)
        and manifest['scoring']['candidate'] is None, 'Frozen development plan differs')
    for row in rows:
        if row['arm'] == 'hbq': banks[(row['endpoint'], row['artifact_id'], row['repeat'])].append(row)
    for packets in banks.values():
        ordered = sorted(packets, key=lambda r: r['batch']); ids = [q for p in ordered for q in p['question_ids']]
        require(len(ordered) == 22 and [p['batch'] for p in ordered] == list(range(1, 23))
                and len(ids) == len(set(ids)) == 170, 'Registered bank packet/leaf geometry differs')
    require(len(banks) == 34 and len(selection['pairs']) == 9 and len(selection['bank_sentinel_ids']) == len(selection['pair_sentinel_ids']) == 2,
            'Initial/sentinel geometry differs')
    for pair in selection['pairs']:
        require(all((ep, 'mfa-'+h, 0) in banks for ep in ('sol', 'grok') for h in pair['excerpt_hashes']), 'Pair lacks registered initial banks')
    return {'policy': POLICY, 'profile_sha256': PROFILE_SHA, 'implementation_sha256': sha(Path(__file__).read_bytes()),
        'manifest_sha256': sha(raw), 'selection_file_sha256': sha(selection_raw), 'selection_content_sha256_declared': manifest['selection_sha256'],
        'source_files_sha256': profile['source_files_sha256'], 'selective_reader_sha256': SELECTIVE_SHA,
        'planned_requests': 868, 'requests_per_endpoint': 434, 'canonical_leaves': 170, 'canonical_packets': 22,
        'initial_artifacts_per_endpoint': 13, 'endpoint_artifact_cycle_banks': 34, 'primary_repeat': 0,
        'registered_bank_cycles_per_endpoint': {ep: dict(Counter(cy for endpoint, tid, cy in banks if endpoint == ep)) for ep in ('sol', 'grok')},
        'primary_pairs': 9, 'bank_sentinels': 2, 'pair_sentinels': 2, 'registered_row_memberships': sum(len(u['row_memberships']) for u in selection['evaluation_units']),
        'panel_condition_units': dict(Counter(u['panel']+':'+u['condition'] for u in selection['evaluation_units'])),
        'threshold_ids': sorted({q for packets in banks.values() for p in packets for q in p['question_ids'] if 'threshold_' in q}),
        'scoring_pins_manifest_declared': {name: manifest['artifacts'][name] for name in ('compiled.json', 'registry/all_modules.yaml', 'bundles/all_bundles.yaml')},
        'fine_variant_assignment': 'Caller must preserve exact source fine variants; this metadata view does not certify their membership',
        'candidate_projection_executed': False, 'native_or_human_acceptance_claimed': False, 'native_driver_implemented': False,
        'human_label_release_authority': False, 'human_labels_opened': False, 'tasks_prose_or_native_attempts_opened': False,
        'confirmation_membership_or_unused_eligibility_verified': False, 'provider_calls': 0,
        'limitations': ['Pure projection requires caller-verified complete admitted banks and frozen context; no native receipt driver is implemented.',
            'Primary is initial repeat0; sentinel repeats are diagnostic only, never imputed or averaged.',
            'Point aggregates do not implement clustered/crossed-rater inference or establish expert/lay claim gates.',
            'Readiness is descriptive; strict interval context incompatibility is preserved.',
            'Profile freezes a mechanism, not confirmation membership, label release, unused status or promotion.']}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--output-root', type=Path, required=True)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args(argv)
    output, inputs = args.output_root.resolve(), args.manifest.resolve().parent
    require(not output.exists() and not output.is_relative_to(REPO) and not output.is_relative_to(inputs), 'Fresh output outside repository and input root required')
    report = metadata_view(args.manifest)
    raw = canonical(report) + b'\n'
    receipt = {'policy': POLICY, 'profile_sha256': PROFILE_SHA, 'implementation_sha256': report['implementation_sha256'],
        'manifest_sha256': report['manifest_sha256'], 'selection_file_sha256': report['selection_file_sha256'],
        'report_sha256': sha(raw), 'planned_requests': 868, 'candidate_projection_executed': False,
        'human_labels_opened': False, 'provider_calls': 0, 'dry_run': args.dry_run}
    if not args.dry_run:
        output.mkdir(parents=True, exist_ok=False)
        for name, value in {'report.json': raw, 'terminal.json': canonical(receipt)+b'\n',
            'analysis_ladder_candidate.py': Path(__file__).read_bytes(), 'ladder-candidate-profile.json': PROFILE_PATH.read_bytes()}.items():
            with (output/name).open('xb') as stream: stream.write(value)
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
