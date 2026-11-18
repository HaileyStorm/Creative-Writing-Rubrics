"""Versioned prohibition guidance and schema selection preserve v1 behavior."""
import copy
import hashlib
import json

import pytest
from jsonschema import Draft202012Validator

from hbqrs import core, scoring_v2, scoring_completion_envelope, scoring_grouped_completion
from hbqrs.paths import schema_dir


def contract(version):
    return {'contract_version': version, 'contract_id': 'synthetic', 'artifact_id': 'synthetic',
            'context': {'artifact_kind': 'prose', 'declared_scope': 'story', 'completion_status': 'complete',
                        'background': [], 'constraints': [], 'audience': []},
            'preferences': [], 'priorities': [], 'weighted_goals': [],
            'binding_requirements': [{'requirement_id': 'prohibition', 'atomic_question': 'Is the term absent?',
                'objective': True, 'non_negotiable': True,
                'source': {'kind': 'explicit_user_requirement', 'reference': 'synthetic', 'exact_excerpt': 'No forbidden term.'},
                'applies_to': ['work'], 'verification': {'method': 'absence', 'expected': 'forbidden term'}}]}


def gate(modules, bundle, task):
    return next(row['question'] for row in core.compiled_questions(core.compile_bundle(modules, bundle, task_contract=task))
                if row['role'] == 'hard_gate' and row['question']['id'].endswith('.prohibition'))


def test_v2_absence_and_legacy_schema_receipt(modules, bundles):
    bundle = core.resolve_bundle(bundles, 'prose.short_story')
    old, new = contract(1), contract(2)
    old_gate, new_gate = gate(modules, bundle, old), gate(modules, bundle, new)
    assert 'return NOT_APPLICABLE' in old_gate['applies_when']
    assert 'Return YES when the prohibited condition is absent' in new_gate['applies_when']
    assert 'NO when it is present' in new_gate['applies_when']
    assert 'Absence alone does not justify NOT_APPLICABLE' in new_gate['applies_when']
    a, b = copy.deepcopy(old_gate), copy.deepcopy(new_gate)
    del a['applies_when']; del b['applies_when']
    assert a == b
    for task in (old, new):
        schema_path = schema_dir() / core.task_contract_schema_name(task)
        assert not list(Draft202012Validator(json.loads(schema_path.read_bytes())).iter_errors(task))
        admission = scoring_v2.validate_import_admission(modules, bundle, [], artifact_id='synthetic',
                                                         task_contract=task, admission_policy='strict_import_v3')
        assert admission['task_contract_schema_sha256'] == hashlib.sha256(schema_path.read_bytes()).hexdigest()
    assert (schema_dir() / core.task_contract_schema_name(old)).name == 'hbq_task_contract.schema.json'
    assert gate(modules, bundle, dict(old, contract_version=1.0)) == old_gate
    assert gate(modules, bundle, {k: v for k, v in old.items() if k != 'contract_version'}) == old_gate


@pytest.mark.parametrize('version', [True, False, None, '2', 0, 3, 2.5, float('nan')])
def test_invalid_version_preserves_permissive_compile_but_fails_strict(modules, bundles, version):
    bundle = core.resolve_bundle(bundles, 'prose.short_story')
    assert gate(modules, bundle, contract(version)) == gate(modules, bundle, contract(1))
    with pytest.raises(core.HBQError, match='Unsupported task contract version'):
        scoring_v2.validate_import_admission(modules, bundle, [], artifact_id='synthetic',
                                             task_contract=contract(version), admission_policy='strict_import_v3')


def test_numeric_v2_and_route_schema():
    value = contract(2.0)
    assert core.task_contract_version(value) == 2
    assert core.route_selection_schema_name(value) == 'hbq_route_selection.v2.schema.json'
    schema = json.loads((schema_dir() / core.route_selection_schema_name(value)).read_bytes())
    nested = {'$defs': schema['$defs'], '$ref': '#/$defs/task_contract'}
    assert not list(Draft202012Validator(nested).iter_errors(value))


def test_v2_completion_guards_and_extrema(modules, bundles):
    bundle = core.resolve_bundle(bundles, 'prose.short_story')
    task = contract(2)
    task['weighted_goals'] = [{'goal_id': 'synthetic_goal', 'atomic_question': 'Is a lantern present?',
        'weight': 1.0, 'source': {'kind': 'driving_prompt', 'reference': 'synthetic', 'exact_excerpt': 'A lantern.'},
        'applies_to': ['work'], 'rationale': 'Synthetic goal.'}]
    rows = core.compiled_questions(core.compile_bundle(modules, bundle, task_contract=task))
    records = [{'artifact_id': 'synthetic', 'bundle_id': bundle['bundle_id'],
                'question_id': row['question']['id'], 'verdict': 'YES', 'confidence': 1.0,
                'evidence': [{'reference': str(i), 'summary': 'Synthetic evidence.'} for i in
                             range(max(1, int(row['question'].get('evidence_policy', {}).get('minimum_references', 0))))]}
               for row in rows]
    goal = next(r for r in records if r['question_id'].endswith('.synthetic_goal'))
    supplement_id = next(row['question']['id'] for row in rows if row['role'] == 'supplemental')
    supplement = next(r for r in records if r['question_id'] == supplement_id)
    goal['verdict'] = supplement['verdict'] = 'CANNOT_ASSESS'
    before = copy.deepcopy((modules, bundle, task, records))
    grouped = scoring_grouped_completion.grouped_completion_envelope(modules, bundle, records, 'synthetic', task,
                                                                       admission_policy='strict_import_v3')
    exhaustive = scoring_completion_envelope.completion_envelope(modules, bundle, records, artifact_id='synthetic',
                                                                  task_contract=task, admission_policy='strict_import_v3')
    assert (grouped['lower'], grouped['upper']) == (exhaustive['numeric_completion_bounds']['lower'],
                                                   exhaustive['numeric_completion_bounds']['upper'])
    assert exhaustive['supplemental_unassessed'] == 1 and grouped['score_unknowns'] == 1
    assert (modules, bundle, task, records) == before
    unknown_gate = copy.deepcopy(records)
    next(r for r in unknown_gate if r['question_id'].endswith('.prohibition'))['verdict'] = 'CANNOT_ASSESS'
    with pytest.raises(ValueError, match='gate not fixed valid'):
        scoring_grouped_completion.grouped_completion_envelope(modules, bundle, unknown_gate, 'synthetic', task,
                                                                admission_policy='strict_import_v3')
    unresolved = scoring_completion_envelope.completion_envelope(modules, bundle, unknown_gate, artifact_id='synthetic',
                                                                  task_contract=task, admission_policy='strict_import_v3')
    assert unresolved['numeric_completion_bounds'] is None


def test_v2_longform_contract_and_route_validation():
    from hbqrs import longform
    from test_longform import TEXT, _catalog, _contract, _route
    segmentation = longform.segment_longform(TEXT, artifact_id='synthetic-story')
    task = _contract()
    task['contract_version'] = 2
    units = [unit['unit_id'] for unit in segmentation['units']]
    assert longform.validate_task_contract(task, artifact_id='synthetic-story', unit_ids=units) == task
    route = _route(segmentation, contract=task)
    modules, bundles = _catalog()
    checked = longform.validate_route_selection(route, segmentation=segmentation, modules=modules,
                                                 bundles=bundles, binding_contract_approved=True)
    assert checked['task_contract']['contract_version'] == 2
