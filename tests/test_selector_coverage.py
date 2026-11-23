"""Opt-in selector coverage: real consumer admission with synthetic inputs."""
import json
from copy import deepcopy

import pytest

from hbqrs import core, runner
from hbqrs.selector_integrity import COVERAGE, EXACT, HISTORICAL, admit_bundle_selectors, resolve_selector_policy
from test_longform_runner import _catalog
from test_response_validation import ResponseBankValidationTests


def test_selector_coverage_requires_each_explicit_question_but_preserves_v1():
    modules = [{'module_id': 'invented', 'tree': [
        {'id': 'first', 'type': 'group', 'children': [{'id': 'one', 'type': 'question'}]},
        {'id': 'second', 'type': 'group', 'children': [{'id': 'two', 'type': 'question'}]},
    ]}]
    component = {'module_id': 'invented', 'include_question_ids': ['one', 'two'], 'include_group_ids': ['first']}
    bundle = {'bundle_id': 'invented', 'domains': [{'domain_id': 'one', 'components': [component]}]}
    for policy in (HISTORICAL, EXACT):
        admit_bundle_selectors(modules, bundle, policy)
    with pytest.raises(core.HBQError, match='explicit questions excluded by group filter: two'):
        admit_bundle_selectors(modules, bundle, COVERAGE)
    component['include_group_ids'].append('second')
    admit_bundle_selectors(modules, bundle, COVERAGE)
    assert [leaf['id'] for leaf, _, _ in core.select_leaves(modules[0], component)] == ['one', 'two']
    component['include_group_ids'] = []  # historical empty group selector is unrestricted
    admit_bundle_selectors(modules, bundle, COVERAGE)
    assert resolve_selector_policy(None, {}) == (HISTORICAL, False)
    assert resolve_selector_policy(None, {'selector_policy': EXACT}) == (EXACT, True)
    with pytest.raises(core.HBQError, match='selector policy changed'):
        resolve_selector_policy(COVERAGE, {'selector_policy': EXACT})


def test_new_coverage_policy_rejects_before_runner_dispatch(tmp_path, monkeypatch):
    registry, bundles = _catalog(tmp_path)
    modules = json.loads(registry.read_bytes())
    first = modules[0]['tree'][0]
    second = deepcopy(first); second['id'] = first['id'] + '.second'
    modules[0]['tree'] = [
        {'id': 'group.first', 'type': 'group', 'title': 'First', 'score_mode': 'weighted_mean', 'weight': 1, 'children': [first]},
        {'id': 'group.second', 'type': 'group', 'title': 'Second', 'score_mode': 'weighted_mean', 'weight': 1, 'children': [second]},
    ]
    registry.write_text(json.dumps(modules), encoding='utf-8')
    catalog = json.loads(bundles.read_bytes())
    component = catalog[0]['domains'][0]['components'][0]
    component['include_question_ids'] = [first['id'], second['id']]
    component['include_group_ids'] = ['group.first']
    bundles.write_text(json.dumps(catalog), encoding='utf-8')
    artifact = tmp_path / 'story.txt'; artifact.write_text('An invented scene.', encoding='utf-8')
    def forbidden(*args, **kwargs):
        pytest.fail('Provider boundary reached')
    for name in ('_call_codex', '_call_openai', '_call_grok', '_call_nous'):
        monkeypatch.setattr(runner, name, forbidden)
    with pytest.raises(core.HBQError, match='explicit questions excluded by group filter'):
        runner.run_judge(artifact_path=artifact, artifact_id='invented', bundle_id='prose.synthetic',
                         registry=registry, bundles=bundles, output_dir=tmp_path / 'run',
                         provider='codex', model='gpt-6.1-sol', reasoning='high', batch_size=32,
                         batch_attempts=1, allow_remote=True, selector_policy=COVERAGE)
    assert not (tmp_path / 'run' / 'run.json').exists()
    component['include_group_ids'].append('group.second')
    bundles.write_text(json.dumps(catalog), encoding='utf-8')
    calls = []
    from test_longform_runner import _questions
    def synthetic(**kwargs):
        ids = [row['question_id'] for row in _questions(kwargs['prompt'])]
        calls.append(ids)
        return json.dumps({'verdicts': [{'question_id': qid, 'verdict': 'YES', 'confidence': 0.8,
            'evidence': [{'kind': 'exact_quote', 'reference': 'synthetic', 'exact_quote': 'invented scene', 'summary': None}],
            'note': 'Synthetic.'} for qid in ids]}), {'reported': {'provider': 'openai', 'model': 'gpt-6.1-sol',
            'reasoning_effort': 'high', 'session_id': 'synthetic-selector-session'}}
    monkeypatch.setattr(runner, '_call_codex', synthetic)
    opts = dict(artifact_path=artifact, artifact_id='invented', bundle_id='prose.synthetic', registry=registry,
                bundles=bundles, output_dir=tmp_path / 'run', provider='codex', model='gpt-6.1-sol',
                reasoning='high', batch_size=32, batch_attempts=1, allow_remote=True)
    runner.run_judge(**opts, selector_policy=COVERAGE)
    manifest_path = tmp_path / 'run' / 'run.json'; prior = manifest_path.read_bytes()
    assert json.loads(prior)['configuration']['selector_policy'] == COVERAGE
    assert calls == [[first['id'], second['id']]]
    monkeypatch.setattr(runner, '_call_codex', forbidden)
    runner.run_judge(**opts, resume=True)
    with pytest.raises(core.HBQError, match='selector policy changed'):
        runner.run_judge(**opts, resume=True, selector_policy=EXACT)
    assert manifest_path.read_bytes() == prior


def test_response_policy_distinguishes_coverage_from_legacy_receipts():
    T = ResponseBankValidationTests
    T.setUpClass()
    case = T('test_complete_dynamic_bank_retains_abstentions_without_provenance')
    case.setUp()
    try:
        batches = case.batches(size=31)
        args = dict(artifact_id='invented-artifact', artifact_text=case.artifact,
                    context_texts=case.contexts, task_contract=case.task)
        from hbqrs.response_validation import validate_response_bank
        old = validate_response_bank(case.modules, case.bundle, batches, selector_policy=EXACT, **args)
        new = validate_response_bank(case.modules, case.bundle, batches, selector_policy=COVERAGE, **args)
        assert old['policy'] == 'supplied_complete_response_bank_v2'
        assert new['policy'] == 'supplied_complete_response_bank_v3'
        assert old['membership_complete'] and new['membership_complete']
        assert old['normalized_verdicts'] == new['normalized_verdicts']
        assert old['supplied_inputs_sha256'] != new['supplied_inputs_sha256']
        from hbqrs.paths import bundles_path
        from hbqrs.response_validation import ResponseBankValidationError
        bundle = deepcopy(core.resolve_bundle(core.load_bundles(bundles_path()), 'default.general_poem'))
        domain = next(d for d in bundle['domains'] if d['domain_id'] == 'image')
        component = next(c for c in domain['components'] if c['module_id'] == 'form.poetry.general_poetry')
        component['include_question_ids'] = ['form.poetry.general_poetry.image_concrete', 'form.poetry.general_poetry.rhythm']
        component['include_group_ids'] = ['form.poetry.general_poetry.image_language']
        domain['components'] = [component]; bundle['domains'] = [domain]
        with pytest.raises(ResponseBankValidationError) as rejected:
            validate_response_bank(case.modules, bundle, [], artifact_id='invented', artifact_text=case.artifact, selector_policy=COVERAGE)
        assert rejected.value.failure_type == 'BANK_DEFINITION_OR_TASK'
    finally:
        case.doCleanups()


def test_cli_validation_uses_coverage_policy(monkeypatch):
    from argparse import Namespace
    from hbqrs import cli
    modules = [{'module_id': 'm', 'tree': [
        {'id': 'a', 'type': 'group', 'children': [{'id': 'q1', 'type': 'question'}]},
        {'id': 'b', 'type': 'group', 'children': [{'id': 'q2', 'type': 'question'}]}]}]
    bundles = [{'bundle_id': 'b', 'domains': [{'domain_id': 'd', 'components': [
        {'module_id': 'm', 'include_question_ids': ['q1', 'q2'], 'include_group_ids': ['a']}]}]}]
    saved = []
    monkeypatch.setattr(cli, '_load_registry', lambda args: (modules, bundles))
    monkeypatch.setattr(cli, 'validate_registry', lambda *args, **kwargs: [])
    monkeypatch.setattr(cli, 'write_data', lambda output, report, fmt: saved.append(report))
    args = Namespace(module_schema=None, bundle_schema=None, selector_policy=COVERAGE, output=None, format='json')
    assert cli._cmd_validate(args) == 1
    assert any('explicit questions excluded' in error for error in saved[-1]['errors'])
    args.selector_policy = EXACT
    assert cli._cmd_validate(args) == 0
