"""Synthetic offline acceptance for the experimental pair completion bridge."""
import json
from pathlib import Path
from unittest.mock import patch

import pytest
import _run_verify_fixture
from hbqrs import completion_readiness, core
from test_verified_pair_comparison import make_run
from hbqrs.verified_pair_completion import compare_verified_completion_runs as compare


def unknown_run(root, source, aid):
    inputs = root / 'inputs'
    inputs.mkdir(parents=True)
    for name in ('source.md', 'prompt.md', 'task.json'):
        data = (source / name).read_text(encoding='utf-8')
        if name == 'task.json':
            value = json.loads(data)
            value['artifact_id'] = aid
            data = json.dumps(value)
        (inputs / name).write_text(data, encoding='utf-8')

    class Proxy:
        changed = False
        def __getattr__(self, name):
            return getattr(json, name)
        def dumps(self, value, **kwargs):
            if isinstance(value, dict) and set(value) == {'verdicts'}:
                for verdict in value['verdicts']:
                    if verdict['question_id'] == 'core.holistic_artistic_success.threshold_1_functional':
                        verdict['verdict'] = 'CANNOT_ASSESS'
                        self.changed = True
            return json.dumps(value, **kwargs)
    proxy = Proxy()
    with patch.object(_run_verify_fixture, 'json', proxy):
        result = _run_verify_fixture.build_fixture(root, artifact_id=aid,
            provider_session_prefix=aid,
            input_paths=(inputs / 'source.md', inputs / 'prompt.md', inputs / 'task.json'))
    if not proxy.changed:
        raise RuntimeError('Synthetic unknown was not introduced')
    return result


def test_unknown_and_work_limit(tmp_path):
    reference, reference_frozen = make_run(tmp_path / 'reference', 'right')
    uncertain, uncertain_frozen = unknown_run(tmp_path / 'uncertain', tmp_path / 'reference/inputs', 'left')
    capped = compare(uncertain, uncertain_frozen, reference, reference_frozen, max_cases=2)
    assert capped['completion']['relation'] == 'UNAVAILABLE'
    assert capped['completion']['left_envelope']['required_completions'] == 3
    result = compare(uncertain, uncertain_frozen, reference, reference_frozen, max_cases=3)
    assert result['completion']['relation'] == 'INCONCLUSIVE'
    assert result['completion']['left']['bounds'] == {'lower': 92.0, 'upper': 100.0}
    assert result['completion']['right']['bounds'] == {'lower': 100.0, 'upper': 100.0}
    assert result['historical']['relation'] == 'RIGHT'


def test_mismatched_tasks_and_invalid_caps(tmp_path):
    left, lf = make_run(tmp_path / 'left', 'left')
    right, rf = make_run(tmp_path / 'right', 'right', goal='Does it reject the prompt?')
    result = compare(left, lf, right, rf)
    assert (result['completion']['relation'], result['completion']['reason']) == ('INCOMPARABLE', 'task_differs')
    for cap in (True, 0, 19684):
        with pytest.raises(ValueError):
            compare(left, lf, right, rf, max_cases=cap)


def test_verdict_change_during_analysis_fails_closed(tmp_path):
    left, lf = make_run(tmp_path / 'left', 'left')
    right, rf = make_run(tmp_path / 'right', 'right')
    actual = completion_readiness.readiness
    def change_after_read(*args, **kwargs):
        result = actual(*args, **kwargs)
        path = Path(left) / 'verdicts.jsonl'
        path.write_bytes(path.read_bytes() + b'\n')
        return result
    with patch.object(completion_readiness, 'readiness', change_after_read):
        with pytest.raises(core.HBQError, match='changed during completion analysis'):
            compare(left, lf, right, rf, max_cases=1)
