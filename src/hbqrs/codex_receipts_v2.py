"""Opt-in strict offline projection of already-retained Codex receipts.

This policy rejects ambiguous JSON before invoking the unchanged v1 reader.
It is not wired into live collection, authenticates no provider, and cannot
establish the effective tool inventory or prevent pre-dispatch tool exposure.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from . import codex_receipts as legacy

POLICY = 'codex_native_rollout_unique_json_v2'


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


def _validate_json_lines(raw: bytes) -> None:
    if not isinstance(raw, bytes) or not raw or len(raw) > legacy.MAX_BYTES or not raw.endswith(b'\n'):
        raise ValueError('Native receipt is missing, truncated or exceeds its byte bound')
    for line in raw.splitlines():
        if not line or len(line) > legacy.MAX_LINE_BYTES:
            raise ValueError('Native receipt line is empty or exceeds its byte bound')
        try:
            value = json.loads(line.decode('utf-8'), object_pairs_hook=_unique_object,
                               parse_constant=_invalid_constant, parse_float=_finite_float)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError('Native receipt line must be strict UTF-8 JSON') from exc
        if not isinstance(value, dict):
            raise ValueError('Native receipt record is not an object')


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
