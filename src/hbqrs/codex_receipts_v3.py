"""Opt-in classified rollout-item admission for new Codex receipts.

This is an additional syntactic and semantic admission guard, not native
authentication, proof of enabled tools, or pre-dispatch attestation.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from . import codex_receipts as v1, codex_receipts_v2 as v2

POLICY = 'codex_native_rollout_classified_items_v3'
_ITEM_TYPES = frozenset({'UserMessage', 'AgentMessage', 'Reasoning', 'AgentReasoning'})


def binding() -> dict[str, str]:
    return {'policy': POLICY, 'reader_sha256': v1.sha(Path(__file__).read_bytes()),
            'v2_reader_sha256': v2.binding()['reader_sha256'],
            'v1_reader_sha256': v1.binding()['reader_sha256']}


def project(rollout_raw: bytes, events_raw: bytes, final_raw: bytes, *, prompt: str,
            model: str, reasoning: str, cwd: Path) -> dict[str, Any]:
    """Require classifiable supported item events, then retain the v2 result."""
    v2._validate_json_lines(rollout_raw)
    for line in rollout_raw.splitlines():
        row = v2._parse_object(line)
        payload = row.get('payload')
        if row.get('type') != 'event_msg' or not isinstance(payload, dict):
            continue  # The v2/v1 projector independently checks record shapes.
        event_type = payload.get('type')
        if not isinstance(event_type, str):
            raise ValueError('Native rollout event type is unclassifiable')
        if event_type == 'item_updated':
            raise ValueError('Unsupported native rollout item update')
        if event_type in {'item_started', 'item_completed'}:
            item = payload.get('item')
            if (not isinstance(item, dict) or not isinstance(item.get('type'), str)
                    or item['type'] not in _ITEM_TYPES):
                raise ValueError('Native rollout item event is unclassifiable or unsupported')
    previous = v2.project(rollout_raw, events_raw, final_raw, prompt=prompt,
                          model=model, reasoning=reasoning, cwd=cwd)
    return {'policy': POLICY, 'reader_sha256': v1.sha(Path(__file__).read_bytes()),
            'v2_projection': previous, 'rollout_item_classification': 'supported_non_tool_items_only',
            'native_source_authenticated': False, 'effective_tool_inventory_attested': False,
            'pre_dispatch_tool_disable_attested': False}


def capture(output_dir: Path, stem: str, *, events_path: Path, message_path: Path,
            prompt: str, model: str, reasoning: str, codex_home: Path,
            started_at: datetime, rollout_path: Path | None = None) -> tuple[dict, dict]:
    events_raw, final_raw = v1.read_bounded(events_path), v1.read_bounded(message_path)
    v2._validate_json_lines(events_raw)
    thread_id, _ = v1.event_identity(events_raw, final_raw)
    original = rollout_path if rollout_path is not None else v1.locate(codex_home, thread_id, started_at=started_at)
    raw = v1.read_bounded(original)
    raw_path = output_dir / 'responses' / f'{stem}.rollout.jsonl'
    with raw_path.open('xb') as out:
        out.write(raw)
    receipt = project(raw, events_raw, final_raw, prompt=prompt, model=model,
                      reasoning=reasoning, cwd=output_dir)
    receipt_path = output_dir / 'responses' / f'{stem}.receipt.json'
    with receipt_path.open('x', encoding='utf-8', newline='\n') as out:
        json.dump(receipt, out, sort_keys=True, indent=2, allow_nan=False)
        out.write('\n')
    artifacts = {}
    for name, path in (('codex_events', events_path), ('codex_message', message_path),
                       ('codex_rollout', raw_path), ('codex_receipt', receipt_path)):
        data = v1.read_bounded(path)
        artifacts[name] = {'path': path.relative_to(output_dir).as_posix(), 'bytes': len(data), 'sha256': v1.sha(data)}
    return receipt, artifacts


def verify(output_dir: Path, provider: dict, *, prompt: str, model: str, reasoning: str,
           final_raw: bytes | None = None) -> None:
    if provider.get('receipt_policy') != POLICY:
        raise ValueError('Classified native receipt policy is missing')
    artifacts = provider.get('provider_artifacts', {})
    if set(artifacts) != {'codex_events', 'codex_message', 'codex_rollout', 'codex_receipt'}:
        raise ValueError('Native receipt artifact inventory differs')
    raw = {}
    for name, item in artifacts.items():
        path = (output_dir / item['path']).resolve()
        if not path.is_relative_to(output_dir.resolve()):
            raise ValueError('Native receipt path escapes the run')
        raw[name] = v1.read_bounded(path)
        if len(raw[name]) != item['bytes'] or v1.sha(raw[name]) != item['sha256']:
            raise ValueError('Native receipt artifact is not bound')
    if final_raw is not None and final_raw != raw['codex_message']:
        raise ValueError('Native final message differs from the accepted response')
    expected = project(raw['codex_rollout'], raw['codex_events'], raw['codex_message'],
                       prompt=prompt, model=model, reasoning=reasoning, cwd=output_dir)
    retained = v2._parse_object(raw['codex_receipt'])
    if (v2._canonical(retained) != v2._canonical(expected)
            or v2._canonical(provider.get('reported')) != v2._canonical(expected['v2_projection']['v1_projection']['reported'])):
        raise ValueError('Classified native execution receipt is not replayable')
