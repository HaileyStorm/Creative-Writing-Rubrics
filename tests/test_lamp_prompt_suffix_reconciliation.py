"""Exact qualified representation and immutable negative-admission replay boundaries."""
from copy import deepcopy
import importlib.util
from pathlib import Path
import sys

import pytest

REPO = Path(__file__).resolve().parents[1]
path = REPO / 'evaluation-results/hbq-native-transport-recovery-v1/reconcile_lamp_prompt_suffix.py'
spec = importlib.util.spec_from_file_location('test_lamp_prompt_suffix', path)
m = importlib.util.module_from_spec(spec); sys.modules[spec.name] = m; spec.loader.exec_module(m)


def fixture():
    rows = [{'params': {'sessionId': 'own', 'update': {'sessionUpdate': kind}}}
            for kind in ('user_message_chunk', 'agent_thought_chunk', 'agent_message_chunk', 'turn_completed')]
    rows[0]['params']['update']['content'] = {'type': 'text', 'text': 'literal source and context'}
    return rows, [{'session_id': 'own', 'prompt': 'literal source and context'}]


def test_only_exact_terminal_space_lf_omission_preserves_original_and_identity():
    rows, histories = fixture(); source = b'literal source and context \n'; raw = m.canonical(rows)
    assert m.qualified_prompt(source, rows, histories, 'own') == source[:-2]
    assert source == b'literal source and context \n' and m.canonical(rows) == raw
    for suffix in (b'\n', b'\r\n', b'\t\n', b'  \n'):
        with pytest.raises(ValueError): m.qualified_prompt(b'literal source and context' + suffix, rows, histories, 'own')
    bad = deepcopy(rows); bad[0]['params']['update']['content']['text'] = 'altered source and context'
    with pytest.raises(ValueError): m.qualified_prompt(source, bad, histories, 'own')
    bad = deepcopy(rows); bad[0]['params']['sessionId'] = 'foreign'
    with pytest.raises(ValueError): m.qualified_prompt(source, bad, histories, 'own')
    with pytest.raises(ValueError): m.qualified_prompt(source, rows, histories * 2, 'own')
    bad = deepcopy(rows); bad.insert(1, {'params': {'update': {'sessionUpdate': 'retry_state'}}})
    with pytest.raises(ValueError): m.qualified_prompt(source, bad, histories, 'own')


def test_readback_preserves_rejection_and_checks_snapshot_source_and_no_overwrite(tmp_path, monkeypatch):
    subset = m.load('suffix_test_frozen_subset', m.FROZEN / 'implementation/schema_subset.py')
    validator = m.load('suffix_test_frozen_admission', m.FROZEN / 'implementation/validate_response.py')
    candidate = {'winner': 'A', 'abstention_reason': None, 'tradeoff': 'Synthetic comparison', 'evidence': [
        {'side': 'A', 'quote': 'absent quotation', 'explanation': 'Synthetic'},
        {'side': 'B', 'quote': 'literal B', 'explanation': 'Synthetic'}]}
    admission = validator.semantic_validate('pairwise', candidate,
        {'sources': [{'id': 'a', 'side': 'A'}, {'id': 'b', 'side': 'B'}]}, {'a': 'literal A', 'b': 'literal B'}, subset, schema={'type': 'object'})
    assert admission['accepted'] is False and 'Pair quote is not on the declared side' in admission['errors']
    output = tmp_path / 'descendant'; assert m.fresh_output(output) == output.resolve()
    with pytest.raises(ValueError, match='outside retained'): m.fresh_output(m.SOURCE / 'new')
    output.mkdir()
    with pytest.raises(ValueError, match='fresh'): m.fresh_output(output)
    original = tmp_path / 'original'; original.write_bytes(b'original')
    acceptance = m.canonical(admission)
    saved = {'implementation_sha256': m.digest(b'fixture'), 'observations': [{'acceptance': {'accepted': False},
        'effective_terminal': {'state': 'semantic_rejected'}}], 'human_release_eligible': False, 'new_votes': 0,
        'source_commitments': {'raw': {'source_locator_local_only': str(original), 'sha256': m.digest(b'original'), 'bytes': 8, 'snapshot': 'raw.bin'}}}
    raw = m.canonical(saved); receipt = output / 'reconciliation.json'; receipt.write_bytes(raw)
    (output / Path(m.__file__).name).write_bytes(b'fixture'); (output / 'raw.bin').write_bytes(b'original')
    slot = '0120-70323a9369e3'; (output / slot).mkdir(); (output / slot / 'response.json').write_bytes(b'{}')
    (output / slot / 'acceptance.json').write_bytes(acceptance)
    monkeypatch.setattr(m, 'reconcile', lambda **kwargs: (saved, None, {slot: b'{}'}, {slot: acceptance}))
    verified = m.verify(receipt, m.digest(raw))
    assert verified['observations'][0]['effective_terminal']['state'] == 'semantic_rejected'
    assert verified['observations'][0]['acceptance']['accepted'] is False and verified['new_votes'] == 0
    (output / 'raw.bin').write_bytes(b'corrupt!')
    with pytest.raises(ValueError, match='snapshot differs'): m.verify(receipt, m.digest(raw))
    (output / 'raw.bin').write_bytes(b'original'); original.write_bytes(b'changed!')
    with pytest.raises(ValueError, match='Original source bytes changed'): m.verify(receipt, m.digest(raw))
    assert original.read_bytes() == b'changed!'
