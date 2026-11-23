from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import pytest

from hbqrs import codex_receipts as v1, codex_receipts_v2 as v2, codex_receipts_v3 as v3
from test_codex_receipts import native_fixture, raw


def project(reader, cwd: Path, rollout, events, final):
    return reader.project(raw(rollout), raw(events), final, prompt='Judge this synthetic passage.',
                          model='gpt-6.1-sol', reasoning='high', cwd=cwd)


def test_classified_policy_preserves_nested_v2_projection(tmp_path):
    rollout, events, final = native_fixture(tmp_path)
    result = project(v3, tmp_path, rollout, events, final)
    assert result['v2_projection'] == project(v2, tmp_path, rollout, events, final)
    assert result['policy'] == v3.POLICY
    assert result['effective_tool_inventory_attested'] is False
    assert result['pre_dispatch_tool_disable_attested'] is False


@pytest.mark.parametrize('event_type', ['item_started', 'item_completed'])
@pytest.mark.parametrize('item', [None, {}, {'type': 'CommandExecution'}, {'type': 'Other'}])
def test_unclassifiable_rollout_items_rejected(tmp_path, event_type, item):
    rollout, events, final = native_fixture(tmp_path)
    payload = {'type': event_type}
    if item is not None:
        payload['item'] = item
    rollout.insert(8, {'type': 'event_msg', 'payload': payload})
    if item is None:
        assert project(v1, tmp_path, rollout, events, final)['zero_tool_activity_observed'] is True
        assert project(v2, tmp_path, rollout, events, final)['v1_projection']['zero_tool_activity_observed'] is True
    with pytest.raises(ValueError, match='unclassifiable or unsupported'):
        project(v3, tmp_path, rollout, events, final)


def test_unqualified_item_update_is_rejected(tmp_path):
    rollout, events, final = native_fixture(tmp_path)
    rollout.insert(8, {'type': 'event_msg', 'payload': {'type': 'item_updated', 'item': {'type': 'UserMessage'}}})
    with pytest.raises(ValueError, match='Unsupported native rollout item update'):
        project(v3, tmp_path, rollout, events, final)


def test_v2_json_uniqueness_is_still_required(tmp_path):
    rollout, events, final = native_fixture(tmp_path)
    ambiguous = raw(events).replace(b'"type":"agent_message"', b'"type":"tool_call","type":"agent_message"', 1)
    with pytest.raises(ValueError, match='duplicate'):
        v3.project(raw(rollout), ambiguous, final, prompt='Judge this synthetic passage.',
                   model='gpt-6.1-sol', reasoning='high', cwd=tmp_path)


def test_replay_rejects_changed_receipt_even_when_artifact_hash_is_rebound(tmp_path):
    rollout, events, final = native_fixture(tmp_path)
    (tmp_path / 'responses').mkdir()
    events_path = tmp_path / 'responses' / 'events.jsonl'
    final_path = tmp_path / 'responses' / 'message.json'
    rollout_path = tmp_path / 'source.jsonl'
    events_path.write_bytes(raw(events))
    final_path.write_bytes(final)
    rollout_path.write_bytes(raw(rollout))
    receipt, artifacts = v3.capture(tmp_path, 'attempt', events_path=events_path, message_path=final_path,
        prompt='Judge this synthetic passage.', model='gpt-6.1-sol', reasoning='high', codex_home=tmp_path,
        started_at=datetime.now(timezone.utc), rollout_path=rollout_path)
    provider = {'receipt_policy': v3.POLICY, 'provider_artifacts': artifacts,
                'reported': receipt['v2_projection']['v1_projection']['reported']}
    v3.verify(tmp_path, provider, prompt='Judge this synthetic passage.', model='gpt-6.1-sol',
              reasoning='high', final_raw=final)
    receipt_path = tmp_path / artifacts['codex_receipt']['path']
    altered = json.loads(receipt_path.read_bytes())
    altered['pre_dispatch_tool_disable_attested'] = 0
    encoded = (json.dumps(altered, sort_keys=True) + '\n').encode()
    receipt_path.write_bytes(encoded)
    artifacts['codex_receipt']['sha256'] = hashlib.sha256(encoded).hexdigest()
    artifacts['codex_receipt']['bytes'] = len(encoded)
    with pytest.raises(ValueError, match='not replayable'):
        v3.verify(tmp_path, provider, prompt='Judge this synthetic passage.', model='gpt-6.1-sol',
                  reasoning='high', final_raw=final)
