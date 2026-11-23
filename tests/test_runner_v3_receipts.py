import json

import pytest

from hbqrs import codex_receipts_v2, codex_receipts_v3, runner
from hbqrs.core import HBQError
from test_runner import _native_codex_process, _native_run


def test_classified_capture_and_resume_bind_policy_and_readers(tmp_path, monkeypatch):
    calls = _native_codex_process(monkeypatch, tmp_path / 'home')
    assert _native_run(tmp_path, codex_receipt_policy=codex_receipts_v3.POLICY)['verdicts'] == 1
    config = json.loads((tmp_path / 'run' / 'run.json').read_text(encoding='utf-8'))['configuration']['codex_receipt']
    assert all(config[k] == v for k, v in codex_receipts_v3.binding().items())
    assert _native_run(tmp_path, resume=True, codex_receipt_policy=codex_receipts_v3.POLICY)['verdicts'] == 1
    with pytest.raises(HBQError, match='provider settings changed'):
        _native_run(tmp_path, resume=True, codex_receipt_policy=codex_receipts_v2.POLICY)
    assert len(calls) == 1


def test_unclassifiable_rollout_is_retained_and_not_resent(tmp_path, monkeypatch):
    home = tmp_path / 'home'
    calls = _native_codex_process(monkeypatch, home)
    original = runner.subprocess.run

    def incomplete(*args, **kwargs):
        result = original(*args, **kwargs)
        paths = list(home.rglob('rollout-*.jsonl'))
        assert len(paths) == 1
        raw = paths[0].read_bytes()
        marker = b'{"type":"event_msg","payload":{"type":"item_started"}}\n'
        first, rest = raw.split(b'\n', 1)
        paths[0].write_bytes(first + b'\n' + marker + rest)
        return result

    monkeypatch.setattr(runner.subprocess, 'run', incomplete)
    with pytest.raises(HBQError, match='not retryable'):
        _native_run(tmp_path, codex_receipt_policy=codex_receipts_v3.POLICY)
    assert list((tmp_path / 'run' / 'responses').glob('*.rollout.jsonl'))
    with pytest.raises(HBQError, match='terminal nonretryable'):
        _native_run(tmp_path, resume=True, codex_receipt_policy=codex_receipts_v3.POLICY)
    assert len(calls) == 1
