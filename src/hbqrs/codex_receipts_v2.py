"""Opt-in strict projection, capture and replay of Codex receipts.

This policy rejects ambiguous JSON before invoking the unchanged v1 reader.
It authenticates no provider and cannot establish the effective tool inventory
or prevent pre-dispatch tool exposure.
"""
from __future__ import annotations

import json
import math
from datetime import datetime
from pathlib import Path
from typing import Any

from . import codex_receipts as legacy

POLICY = 'codex_native_rollout_unique_json_v2'


def binding() -> dict[str, str]:
    return {'policy': POLICY, 'reader_sha256': legacy.sha(Path(__file__).read_bytes()),
            'v1_reader_sha256': legacy.binding()['reader_sha256']}


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Native receipt JSON contains duplicate object keys')
        result[key] = value
    return result


def _finite_float(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed):
        raise ValueError('Native receipt JSON contains a non-finite number')
    return parsed


def _invalid_constant(value: str) -> None:
    raise ValueError('Native receipt JSON contains a non-finite number')


def _parse_object(raw: bytes) -> dict[str, Any]:
    try:
        value = json.loads(raw.decode('utf-8'), object_pairs_hook=_unique_object,
                           parse_constant=_invalid_constant, parse_float=_finite_float)
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ValueError('Native receipt must be strict UTF-8 JSON') from exc
    if not isinstance(value, dict):
        raise ValueError('Native receipt record is not an object')
    return value


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'),
                      allow_nan=False).encode('utf-8')


def _validate_json_lines(raw: bytes) -> None:
    if not isinstance(raw, bytes) or not raw or len(raw) > legacy.MAX_BYTES or not raw.endswith(b'\n'):
        raise ValueError('Native receipt is missing, truncated or exceeds its byte bound')
    for line in raw.splitlines():
        if not line or len(line) > legacy.MAX_LINE_BYTES:
            raise ValueError('Native receipt line is empty or exceeds its byte bound')
        _parse_object(line)


def project(rollout_raw: bytes, events_raw: bytes, final_raw: bytes, *, prompt: str,
            model: str, reasoning: str, cwd: Path) -> dict[str, Any]:
    """Validate unique-key native records, then apply the historical projector.

    The returned v1 projection is nested and explicitly identified. It is not a
    v1 capture receipt and must not be substituted into existing checkpoints.
    """
    _validate_json_lines(rollout_raw)
    _validate_json_lines(events_raw)
    prior = legacy.project(rollout_raw, events_raw, final_raw, prompt=prompt,
                           model=model, reasoning=reasoning, cwd=cwd)
    return {'policy': POLICY, 'syntax': 'unique_keys_finite_numbers_utf8_jsonl',
            'v1_reader_sha256': legacy.binding()['reader_sha256'],
            'v2_reader_sha256': legacy.sha(Path(__file__).read_bytes()),
            'v1_projection': prior,
            'native_source_authenticated': False,
            'effective_tool_inventory_attested': False,
            'pre_dispatch_tool_disable_attested': False}


def capture(output_dir: Path, stem: str, *, events_path: Path, message_path: Path,
            prompt: str, model: str, reasoning: str, codex_home: Path,
            started_at: datetime, rollout_path: Path | None = None) -> tuple[dict, dict]:
    """Capture fresh raw bytes before v2 admission; never replace a v1 receipt."""
    events_raw, final_raw = legacy.read_bounded(events_path), legacy.read_bounded(message_path)
    _validate_json_lines(events_raw)
    thread_id, _ = legacy.event_identity(events_raw, final_raw)
    original = rollout_path if rollout_path is not None else legacy.locate(codex_home, thread_id, started_at=started_at)
    raw = legacy.read_bounded(original)
    raw_path = output_dir / 'responses' / f'{stem}.rollout.jsonl'
    with raw_path.open('xb') as out:
        out.write(raw)
    receipt = project(raw, events_raw, final_raw, prompt=prompt, model=model, reasoning=reasoning, cwd=output_dir)
    receipt_path = output_dir / 'responses' / f'{stem}.receipt.json'
    with receipt_path.open('x', encoding='utf-8', newline='\n') as out:
        json.dump(receipt, out, sort_keys=True, indent=2, allow_nan=False)
        out.write('\n')
    artifacts = {}
    for name, path in (('codex_events', events_path), ('codex_message', message_path),
                       ('codex_rollout', raw_path), ('codex_receipt', receipt_path)):
        data = legacy.read_bounded(path)
        artifacts[name] = {'path': path.relative_to(output_dir).as_posix(), 'bytes': len(data), 'sha256': legacy.sha(data)}
    return receipt, artifacts


def verify(output_dir: Path, provider: dict, *, prompt: str, model: str, reasoning: str,
           final_raw: bytes | None = None) -> None:
    """Replay only v2 artifacts using the current exact v1 and v2 readers."""
    if provider.get('receipt_policy') != POLICY:
        raise ValueError('Strict native receipt policy is missing')
    artifacts = provider.get('provider_artifacts', {})
    if set(artifacts) != {'codex_events', 'codex_message', 'codex_rollout', 'codex_receipt'}:
        raise ValueError('Native receipt artifact inventory differs')
    raw = {}
    for name, item in artifacts.items():
        path = (output_dir / item['path']).resolve()
        if not path.is_relative_to(output_dir.resolve()):
            raise ValueError('Native receipt path escapes the run')
        raw[name] = legacy.read_bounded(path)
        if len(raw[name]) != item['bytes'] or legacy.sha(raw[name]) != item['sha256']:
            raise ValueError('Native receipt artifact is not bound')
    if final_raw is not None and final_raw != raw['codex_message']:
        raise ValueError('Native final message differs from the accepted response')
    expected = project(raw['codex_rollout'], raw['codex_events'], raw['codex_message'],
                       prompt=prompt, model=model, reasoning=reasoning, cwd=output_dir)
    retained = _parse_object(raw['codex_receipt'])
    if (_canonical(retained) != _canonical(expected)
            or _canonical(provider.get('reported')) != _canonical(expected['v1_projection']['reported'])):
        raise ValueError('Strict native execution receipt is not replayable')
