from pathlib import Path

import pytest

from hbqrs import codex_receipts as legacy, codex_receipts_v2 as strict
from test_codex_receipts import native_fixture, raw


def invoke(reader, cwd: Path, rollout: bytes, events: bytes, final: bytes):
    return reader.project(rollout, events, final, prompt='Judge this synthetic passage.',
                          model='gpt-6.1-sol', reasoning='high', cwd=cwd)


def test_unique_json_projection_matches_legacy_on_valid_receipt(tmp_path):
    rollout, events, final = native_fixture(tmp_path)
    old = invoke(legacy, tmp_path, raw(rollout), raw(events), final)
    result = invoke(strict, tmp_path, raw(rollout), raw(events), final)
    assert result['v1_projection'] == old
    assert result['policy'] == strict.POLICY
    assert not result['effective_tool_inventory_attested']
    assert not result['pre_dispatch_tool_disable_attested']


@pytest.mark.parametrize('part,old_type,new_type', [
    ('events', b'"type":"agent_message"', b'"type":"tool_call","type":"agent_message"'),
    ('rollout', b'"type":"UserMessage"', b'"type":"CommandExecution","type":"UserMessage"'),
])
def test_ambiguous_item_type_rejected_without_changing_legacy(tmp_path, part, old_type, new_type):
    rollout, events, final = native_fixture(tmp_path)
    data = {'rollout': raw(rollout), 'events': raw(events)}
    assert old_type in data[part]
    data[part] = data[part].replace(old_type, new_type, 1)
    assert invoke(legacy, tmp_path, data['rollout'], data['events'], final)['zero_tool_activity_observed']
    with pytest.raises(ValueError, match='duplicate'):
        invoke(strict, tmp_path, data['rollout'], data['events'], final)


@pytest.mark.parametrize('value', [b'NaN', b'Infinity', b'1e400'])
def test_rejects_nonfinite_json_even_in_ignored_fields(tmp_path, value):
    rollout, events, final = native_fixture(tmp_path)
    events_raw = raw(events).replace(b'"usage":{', b'"extra":' + value + b',"usage":{', 1)
    with pytest.raises(ValueError, match='non-finite'):
        invoke(strict, tmp_path, raw(rollout), events_raw, final)
