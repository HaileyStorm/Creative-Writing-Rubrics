"""Offline behavioral checks; fixture provider and review records are invented."""
from copy import deepcopy
import json
from unittest.mock import patch

import pytest

from hbqrs import core
from hbqrs.verified_pair_comparison import compare_verified_binary_runs
import _run_verify_fixture
from _run_verify_fixture import build_fixture


def make_run(root, aid, *, prompt='Write an invented lantern story.',
             goal='Does it respond to the prompt?', session_prefix=None, scope_reason=None, inapplicable=False):
    inputs = root / 'inputs'
    inputs.mkdir(parents=True)
    source, context, task = inputs / 'source.md', inputs / 'prompt.md', inputs / 'task.json'
    source.write_text(f'The lantern glowed for {aid}.', encoding='utf-8')
    context.write_text(prompt, encoding='utf-8')
    contract = {'contract_version': 1, 'contract_id': 'invented-pair', 'artifact_id': aid,
                'context': {'artifact_kind': 'short prose fiction', 'declared_scope': 'complete short story',
                            'completion_status': 'complete', 'background': [], 'constraints': [], 'audience': []},
                'preferences': [], 'priorities': [],
                'weighted_goals': [{'goal_id': 'prompt_response', 'atomic_question': goal, 'weight': 1.0,
                                    'source': {'kind': 'driving_prompt', 'reference': 'invented',
                                               'exact_excerpt': 'Write an invented lantern story.'},
                                    'applies_to': ['whole artifact'], 'rationale': 'Invented fixture.'}],
                'binding_requirements': []}
    task.write_text(json.dumps(contract), encoding='utf-8')
    original_write = _run_verify_fixture.write_json
    def write_fixture(path, value):
        if scope_reason is not None and path.name == 'scope-compatibility.json':
            value = dict(value, reason=scope_reason)
        original_write(path, value)
    class FixtureJson:
        changed = False
        def __getattr__(self, name):
            return getattr(json, name)
        def dumps(self, value, **kwargs):
            if inapplicable and not self.changed and isinstance(value, dict) and set(value) == {'verdicts'}:
                value['verdicts'][0]['verdict'] = 'NOT_APPLICABLE'
                self.changed = True
            return json.dumps(value, **kwargs)
    fixture_json = FixtureJson()
    with patch.object(_run_verify_fixture, 'write_json', write_fixture), patch.object(_run_verify_fixture, 'json', fixture_json):
        result = build_fixture(root, artifact_id=aid, provider_session_prefix=session_prefix or aid,
                               input_paths=(source, context, task))
    assert fixture_json.changed == inapplicable
    return result


def test_matching_verified_runs_and_tampering(tmp_path):
    left, lf = make_run(tmp_path / 'left', 'synthetic-left')
    right, rf = make_run(tmp_path / 'right', 'synthetic-right')
    result = compare_verified_binary_runs(left, lf, right, rf)
    assert result['relation'] == 'TIE'
    assert result['reason'] == 'observed_point_order'
    assert result['provider_identity_authenticated'] is False
    assert result['human_review_authenticated'] is False
    assert result['context_origin_authenticated'] is False
    assert result['interval_bounds_kind'] == 'historical_scorer_bounds'
    assert result['interval_completion_envelope_guaranteed'] is False
    assert len(result['shared_context_sha256']) == 64
    bad = deepcopy(rf)
    bad['execution']['reasoning'] = 'different'
    with pytest.raises(core.HBQError):
        compare_verified_binary_runs(left, lf, right, bad)


@pytest.mark.parametrize(('difference', 'expected'), [
    ('task', 'task_differs'), ('context', 'configuration_differs'), ('scope', 'scope_differs'),
    ('session', 'provider_session_reused'), ('applicability', 'report_scoring_context_differs')])
def test_mismatched_runs_are_incomparable(tmp_path, difference, expected):
    left, lf = make_run(tmp_path / 'left', 'synthetic-left', session_prefix='same')
    options = {'session_prefix': 'same' if difference == 'session' else 'different'}
    if difference == 'task':
        options['goal'] = 'Does it reject the prompt?'
    if difference == 'context':
        options['prompt'] = 'Write a different invented story.'
    if difference == 'scope':
        options['scope_reason'] = 'A different invented scope decision.'
    if difference == 'applicability':
        options['inapplicable'] = True
    right, rf = make_run(tmp_path / 'right', 'synthetic-right', **options)
    result = compare_verified_binary_runs(left, lf, right, rf)
    assert (result['relation'], result['reason']) == ('INCOMPARABLE', expected)
