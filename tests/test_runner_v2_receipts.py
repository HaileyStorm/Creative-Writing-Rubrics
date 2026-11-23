import json
import hashlib
from datetime import datetime, timezone
from pathlib import Path
import subprocess

import pytest

from hbqrs import codex_receipts_v2, runner
from hbqrs.core import HBQError
from test_runner import _native_codex_process, _native_run
from test_codex_receipts import native_fixture, raw


def test_strict_capture_resume_and_policy_binding(tmp_path, monkeypatch):
    home = tmp_path / 'home'
    calls = _native_codex_process(monkeypatch, home)
    assert _native_run(tmp_path, codex_receipt_policy=codex_receipts_v2.POLICY)['verdicts'] == 1
    config = json.loads((tmp_path / 'run' / 'run.json').read_text(encoding='utf-8'))['configuration']['codex_receipt']
    assert all(config[k] == v for k, v in codex_receipts_v2.binding().items())
    checkpoint = json.loads((tmp_path / 'run' / 'responses' / 'batch-0001.json').read_text(encoding='utf-8'))
    assert checkpoint['provider']['receipt_policy'] == codex_receipts_v2.POLICY
    receipt_path = tmp_path / 'run' / checkpoint['provider']['provider_artifacts']['codex_receipt']['path']
    receipt = json.loads(receipt_path.read_text(encoding='utf-8'))
    assert receipt['policy'] == codex_receipts_v2.POLICY
    assert not receipt['pre_dispatch_tool_disable_attested']
    assert _native_run(tmp_path, resume=True, codex_receipt_policy=codex_receipts_v2.POLICY)['verdicts'] == 1
    assert len(calls) == 1
    with pytest.raises(HBQError, match='provider settings changed'):
        _native_run(tmp_path, resume=True, codex_receipt_policy=runner.codex_receipts.POLICY)
    assert len(calls) == 1


def test_duplicate_events_fail_closed_and_are_not_resent(tmp_path, monkeypatch):
    calls = _native_codex_process(monkeypatch, tmp_path / 'home')
    original = runner.subprocess.run

    def ambiguous(*args, **kwargs):
        result = original(*args, **kwargs)
        altered = result.stdout.replace(b'"type":"agent_message"',
                                        b'"type":"tool_call","type":"agent_message"', 1)
        assert altered != result.stdout
        return subprocess.CompletedProcess(result.args, result.returncode, stdout=altered, stderr=result.stderr)

    monkeypatch.setattr(runner.subprocess, 'run', ambiguous)
    with pytest.raises(HBQError, match='not retryable'):
        _native_run(tmp_path, codex_receipt_policy=codex_receipts_v2.POLICY)
    assert list((tmp_path / 'run' / 'responses').glob('*.events.jsonl'))
    assert not (tmp_path / 'run' / 'responses' / 'batch-0001.json').exists()
    with pytest.raises(HBQError, match='terminal nonretryable'):
        _native_run(tmp_path, resume=True, codex_receipt_policy=codex_receipts_v2.POLICY)
    assert len(calls) == 1


def test_duplicate_rollout_is_retained_and_not_resent(tmp_path, monkeypatch):
    home = tmp_path / 'home'
    calls = _native_codex_process(monkeypatch, home)
    original = runner.subprocess.run

    def ambiguous(*args, **kwargs):
        result = original(*args, **kwargs)
        paths = list(home.rglob('rollout-*.jsonl'))
        assert len(paths) == 1
        prior = paths[0].read_bytes()
        altered = prior.replace(b'"type":"UserMessage"',
                                b'"type":"CommandExecution","type":"UserMessage"', 1)
        assert altered != prior
        paths[0].write_bytes(altered)
        return result

    monkeypatch.setattr(runner.subprocess, 'run', ambiguous)
    with pytest.raises(HBQError, match='not retryable'):
        _native_run(tmp_path, codex_receipt_policy=codex_receipts_v2.POLICY)
    assert list((tmp_path / 'run' / 'responses').glob('*.rollout.jsonl'))
    with pytest.raises(HBQError, match='terminal nonretryable'):
        _native_run(tmp_path, resume=True, codex_receipt_policy=codex_receipts_v2.POLICY)
    assert len(calls) == 1


def test_deep_json_is_recorded_nonretryable_and_not_resent(tmp_path, monkeypatch):
    calls = _native_codex_process(monkeypatch, tmp_path / 'home')
    original = runner.subprocess.run

    def deep(*args, **kwargs):
        result = original(*args, **kwargs)
        nested = b'[' * 50000 + b'0' + b']' * 50000
        altered = result.stdout.replace(b'"usage":{', b'"extra":' + nested + b',"usage":{', 1)
        assert altered != result.stdout
        return subprocess.CompletedProcess(result.args, result.returncode, stdout=altered, stderr=result.stderr)

    monkeypatch.setattr(runner.subprocess, 'run', deep)
    with pytest.raises(HBQError, match='not retryable'):
        _native_run(tmp_path, codex_receipt_policy=codex_receipts_v2.POLICY)
    assert list((tmp_path / 'run' / 'responses').glob('*.events.jsonl'))
    with pytest.raises(HBQError, match='terminal nonretryable'):
        _native_run(tmp_path, resume=True, codex_receipt_policy=codex_receipts_v2.POLICY)
    assert len(calls) == 1


def test_replay_rejects_duplicate_receipt_even_with_rebound_hash(tmp_path):
    rollout, events, final = native_fixture(tmp_path)
    (tmp_path / 'responses').mkdir()
    events_path, message_path, source_path = (tmp_path / 'responses' / 'events.jsonl',
                                              tmp_path / 'responses' / 'message.json',
                                              tmp_path / 'source.jsonl')
    events_path.write_bytes(raw(events)); message_path.write_bytes(final); source_path.write_bytes(raw(rollout))
    receipt, artifacts = codex_receipts_v2.capture(
        tmp_path, 'attempt', events_path=events_path, message_path=message_path,
        prompt='Judge this synthetic passage.', model='gpt-6.1-sol', reasoning='high',
        codex_home=tmp_path, started_at=datetime.now(timezone.utc), rollout_path=source_path)
    provider = {'receipt_policy': codex_receipts_v2.POLICY, 'provider_artifacts': artifacts,
                'reported': receipt['v1_projection']['reported']}
    receipt_path = tmp_path / artifacts['codex_receipt']['path']
    modified = receipt_path.read_bytes().replace(b'{\n', b'{\n  "policy": "other",\n', 1)
    receipt_path.write_bytes(modified)
    artifacts['codex_receipt']['sha256'] = hashlib.sha256(modified).hexdigest()
    artifacts['codex_receipt']['bytes'] = len(modified)
    with pytest.raises(ValueError, match='duplicate'):
        codex_receipts_v2.verify(tmp_path, provider, prompt='Judge this synthetic passage.',
                                 model='gpt-6.1-sol', reasoning='high', final_raw=final)


def test_replay_rejects_boolean_changed_to_zero_even_with_rebound_hash(tmp_path):
    rollout, events, final = native_fixture(tmp_path)
    (tmp_path / 'responses').mkdir()
    events_path, message_path, source_path = (tmp_path / 'responses' / 'events.jsonl',
                                              tmp_path / 'responses' / 'message.json',
                                              tmp_path / 'source.jsonl')
    events_path.write_bytes(raw(events)); message_path.write_bytes(final); source_path.write_bytes(raw(rollout))
    receipt, artifacts = codex_receipts_v2.capture(
        tmp_path, 'attempt', events_path=events_path, message_path=message_path,
        prompt='Judge this synthetic passage.', model='gpt-6.1-sol', reasoning='high',
        codex_home=tmp_path, started_at=datetime.now(timezone.utc), rollout_path=source_path)
    provider = {'receipt_policy': codex_receipts_v2.POLICY, 'provider_artifacts': artifacts,
                'reported': receipt['v1_projection']['reported']}
    receipt_path = tmp_path / artifacts['codex_receipt']['path']
    parsed = json.loads(receipt_path.read_bytes())
    assert parsed['pre_dispatch_tool_disable_attested'] is False
    parsed['pre_dispatch_tool_disable_attested'] = 0
    modified = (json.dumps(parsed, sort_keys=True) + '\n').encode()
    receipt_path.write_bytes(modified)
    artifacts['codex_receipt']['sha256'] = hashlib.sha256(modified).hexdigest()
    artifacts['codex_receipt']['bytes'] = len(modified)
    with pytest.raises(ValueError, match='not replayable'):
        codex_receipts_v2.verify(tmp_path, provider, prompt='Judge this synthetic passage.',
                                 model='gpt-6.1-sol', reasoning='high', final_raw=final)
