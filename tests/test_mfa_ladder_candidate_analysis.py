from copy import deepcopy
import importlib.util
from pathlib import Path

import pytest

from hbqrs import core, ladder_uncertainty, scoring_v2
from test_scoring import _full_verdicts


HERE = Path(__file__).resolve().parents[1] / 'evaluation-results/hbq-matched-mfa-v1'
spec = importlib.util.spec_from_file_location('mfa_ladder_preparation_test', HERE / 'analysis_ladder_candidate.py')
a = importlib.util.module_from_spec(spec)
spec.loader.exec_module(a)


def test_complete_original_admission_once_immutable_and_incomplete_or_changed_profile_fails(modules, bundle_by_id, monkeypatch, tmp_path):
    bundle = bundle_by_id['prose.short_form']
    compiled, records = _full_verdicts(modules, bundle)
    for record in records:
        record['bundle_id'] = bundle['bundle_id']
        for evidence in record['evidence']:
            evidence['summary'] = evidence.pop('quote')
    ids = [r['question']['id'] for r in core.compiled_questions(compiled)]
    bank = {'artifact_id': 'test-artifact', 'endpoint': 'sol', 'repeat': 0,
        'manifest_sha256': a.verified_profile()['cohorts']['mfa_quality_development_manifest_sha256'],
        'native_replay_receipt_sha256': 'a'*64, 'frozen_source_context_verified': True,
        'raw_normalized_verdicts_sha256': ladder_uncertainty.canonical_json_sha256(records),
        'packets': [{'batch': i+1, 'question_ids': ids[i*8:(i+1)*8], 'request_sha256': a.sha(str(i).encode()),
                     'accepted': True, 'native_replay_verified': True} for i in range(22)]}
    before = deepcopy((modules, bundle, records, bank))
    original = scoring_v2.validate_import_admission
    policies = []

    def admission(*args, **kwargs):
        policies.append(kwargs['admission_policy'])
        return original(*args, **kwargs)

    monkeypatch.setattr(scoring_v2, 'validate_import_admission', admission)
    result = a.project_complete_bank(modules, bundle, records, artifact_id='test-artifact', task_contract=None, verified_bank=bank)
    assert policies == ['strict_import_v1', 'historical_permissive_v1']
    assert result['provenance']['original_import_admission_count'] == 1
    assert result['provenance']['native_replay_independently_verified_here'] is False
    assert (modules, bundle, records, bank) == before
    policies.clear()
    with pytest.raises(ValueError, match='Complete unique'):
        a.project_complete_bank(modules, bundle, records[:-1], artifact_id='test-artifact', task_contract=None, verified_bank=bank)
    assert policies == []
    wrong_profile = tmp_path / 'profile.json'
    wrong_profile.write_bytes(a.PROFILE_PATH.read_bytes() + b' ')
    monkeypatch.setattr(a, 'PROFILE_PATH', wrong_profile)
    with pytest.raises(ValueError, match='commitment differs'):
        a.project_complete_bank(modules, bundle, records, artifact_id='test-artifact', task_contract=None, verified_bank=bank)
    assert policies == []


def test_initial_only_and_all_planned_guard_prevents_selective_abstention_gain():
    def projection(tid, repeat, historical, candidate):
        def report(score):
            return {'hard_gate_status': 'VALID', 'status': 'SCORED', 'final_score': {'observed': score}}
        return {'provenance': {'complete_bank': True, 'artifact_id': tid, 'endpoint': 'sol', 'repeat': repeat, 'profile_sha256': a.PROFILE_SHA},
                'historical_report': report(historical), 'candidate_report': report(candidate)}
    pairs = [{'pair_id': pid, 'target_hash': 'target', 'condition': 'fewshot', 'panel': 'expert', 'fine_variant': 'exact-source-variant',
              'task': 'quality', 'left': left, 'right': right, 'membership_verified': True,
              'planned_ballot_ids': ['0', '2'] if pid == 'p1' else ['1']}
             for pid, left, right in [('p1', 'a', 'b'), ('p2', 'c', 'd')]]
    projections = {('sol', 'a', 0): projection('a', 0, 80, 70), ('sol', 'b', 0): projection('b', 0, 70, 70),
                   ('sol', 'c', 0): projection('c', 0, 60, 60), ('sol', 'd', 0): projection('d', 0, 70, 70),
                   ('sol', 'a', 1): projection('a', 1, 1, 1), ('sol', 'b', 1): projection('b', 1, 100, 100)}
    decisions = a.initial_pair_decisions(pairs, projections, endpoint='sol')
    assert decisions[0]['historical']['decision'] == 'LEFT'
    assert decisions[0]['candidate']['state'] == 'TIE'
    stratum = decisions[0]['stratum']
    ballots = [{'stratum': stratum, 'target_hash': 'target', 'ballot_id': str(i), 'pair_id': pid, 'human_state': state, 'winner': winner}
               for i, (pid, state, winner) in enumerate([('p1', 'BINARY', 'RIGHT'), ('p2', 'BINARY', 'RIGHT'), ('p1', 'UNKNOWN', None)])]
    with pytest.raises(ValueError, match='released ballots required'):
        a.aggregate_all_planned(decisions, ballots)
    with pytest.raises(ValueError, match='All registered planned ballot IDs'):
        a.aggregate_all_planned(decisions, ballots[:-1], caller_ballots_verified_and_released=True)
    result = a.aggregate_all_planned(decisions, ballots, caller_ballots_verified_and_released=True)['strata'][0]
    assert result['historical']['complete_case_binary_accuracy'] == .5
    assert result['candidate']['complete_case_binary_accuracy'] == 1
    assert result['historical']['all_planned_accuracy'] == result['candidate']['all_planned_accuracy'] == 1/3
    assert result['candidate']['source_human_states']['UNKNOWN'] == 1
    assert result['coverage_guard_pass'] is False and result['expert_5pp_point_guard_pass'] is False
    assert result['improvement_claim_established'] is False
    del projections[('sol', 'a', 0)]
    missing = a.initial_pair_decisions(pairs, projections, endpoint='sol')[0]
    assert missing['historical']['state'] == missing['candidate']['state'] == 'MISSING_INITIAL_BANK'
