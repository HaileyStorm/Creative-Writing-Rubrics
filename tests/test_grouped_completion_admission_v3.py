"""Behavioral boundary for grouped completion's opt-in contract validation."""
import copy

import pytest

from hbqrs import core, scoring_completion_envelope, scoring_grouped_completion


def test_grouped_v3_contract_admission_and_historical_compatibility(modules, bundles):
    bundle = core.resolve_bundle(bundles, 'prose.scene')
    contract = {'contract_version': 1, 'contract_id': 'synthetic', 'artifact_id': 'synthetic',
                'context': {'artifact_kind': 'prose', 'declared_scope': 'scene', 'completion_status': 'excerpt',
                            'background': [], 'constraints': [], 'audience': []},
                'preferences': [], 'priorities': [], 'weighted_goals': [], 'binding_requirements': []}
    records = []
    for row in core.compiled_questions(core.compile_bundle(modules, bundle, task_contract=contract)):
        question = row['question']
        count = max(1, int(question.get('evidence_policy', {}).get('minimum_references', 0)))
        records.append({'artifact_id': 'synthetic', 'bundle_id': bundle['bundle_id'],
                        'question_id': question['id'], 'verdict': 'YES', 'confidence': 1.0,
                        'evidence': [{'reference': str(i), 'summary': 'Synthetic evidence.'}
                                     for i in range(count)]})
    next(r for r in records if r['question_id'] in {
        row['question']['id'] for row in core.compiled_questions(core.compile_bundle(modules, bundle))
        if row['role'] == 'domain'})['verdict'] = 'CANNOT_ASSESS'
    before = copy.deepcopy((modules, bundle, records, contract))
    legacy = scoring_grouped_completion.grouped_completion_envelope(modules, bundle, records, 'synthetic', contract)
    explicit = scoring_grouped_completion.grouped_completion_envelope(
        modules, bundle, records, 'synthetic', contract, admission_policy='strict_import_v2')
    strict = scoring_grouped_completion.grouped_completion_envelope(
        modules, bundle, records, 'synthetic', contract, admission_policy='strict_import_v3')
    admission = strict.pop('admission')
    assert legacy == explicit == strict
    exhaustive = scoring_completion_envelope.completion_envelope(
        modules, bundle, records, artifact_id='synthetic', task_contract=contract,
        admission_policy='strict_import_v3')
    assert (strict['lower'], strict['upper']) == (
        exhaustive['numeric_completion_bounds']['lower'], exhaustive['numeric_completion_bounds']['upper'])
    assert admission['policy'] == 'strict_import_v3'
    assert len(admission['task_contract_schema_sha256']) == 64
    assert (modules, bundle, records, contract) == before

    invalid = dict(contract, unexpected=True)
    scoring_grouped_completion.grouped_completion_envelope(modules, bundle, records, 'synthetic', invalid)
    with pytest.raises(core.HBQError, match='task contract violates schema'):
        scoring_grouped_completion.grouped_completion_envelope(
            modules, bundle, records, 'synthetic', invalid, admission_policy='strict_import_v3')
    with pytest.raises(ValueError, match='unsupported admission policy'):
        scoring_grouped_completion.grouped_completion_envelope(
            modules, bundle, records, 'synthetic', contract, admission_policy='historical_permissive_v1')
