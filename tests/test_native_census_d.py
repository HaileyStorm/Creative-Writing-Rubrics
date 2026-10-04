from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('native_census_d', ROOT / 'evaluation-results/hbq-census-native-d-v1/census.py')
census = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(census)


def put(root, name, value):
    raw = census.canonical(value)
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return census.sha(raw)


def slot(ordinal, disposition='accepted', native=None):
    accepted = disposition in ('accepted', 'accepted_reconciled')
    return {'scope': 'panel', 'endpoint': 'grok', 'ordinal': ordinal, 'sample_sha256': str(ordinal),
            'source_sha256': 'same-work', 'native_identity_sha256': native or str(ordinal),
            'accepted': accepted, 'disposition': disposition, 'unknown_exit_preserved': disposition == 'accepted_reconciled',
            'leaves': [{'question_id': 'leaf', 'verdict': 'YES'}] if accepted else []}


def test_replacement_and_failed_dispositions_never_add_votes_or_studies():
    slots = [slot(1), slot(2, 'ambiguous'), slot(3, 'accepted_reconciled'), slot(4, 'unattempted_after_retained_stop')]
    result = census.aggregate(slots, [{'id': 'panel', 'replaces_census_a': 'lamp-development'}])
    assert result['native_leaf_rows'] == result['accepted_packets'] == 2
    assert result['planned_packet_slots'] == 4
    assert result['dispositions'] == {'accepted': 1, 'ambiguous': 1, 'accepted_reconciled': 1, 'unattempted_after_retained_stop': 1}
    assert result['scopes'][0]['replaces_census_a_declaration'] == 'lamp-development'
    assert result['scopes'][0]['endpoints'][0]['distinct_source_hashes'] == 1
    assert result['independent_work_count'] is result['physical_provider_contact_count'] is None


def test_original_suffix_overlap_and_duplicate_native_are_rejected():
    with pytest.raises(ValueError, match='Overlapping'):
        census.validate_slots([slot(1), slot(1)])
    with pytest.raises(ValueError, match='Duplicate accepted native'):
        census.validate_slots([slot(1, native='native'), slot(2, native='native')])
    other = slot(2)
    other['sample_sha256'] = '1'
    with pytest.raises(ValueError, match='Duplicate leaf'):
        census.validate_slots([slot(1), other])


def test_hash_size_and_root_bound_fail_before_reading_foreign_inputs(tmp_path):
    pin = put(tmp_path, 'metadata.json', {'state': 'accepted'})
    inputs = census.Inputs(tmp_path)
    with pytest.raises(ValueError, match='Source hash differs'):
        inputs.raw('metadata.json', '0' * 64)
    with pytest.raises(ValueError, match='byte count'):
        inputs.raw('metadata.json', pin, 999)
    with pytest.raises(ValueError, match='leaves retained'):
        inputs.raw('../foreign.json')


def test_wave_order_and_intent_hash_are_required(tmp_path):
    intent = {'ordinals': [1, 2], 'manifest_sha256': 'manifest', 'endpoint': 'grok'}
    pin = put(tmp_path, 'root/waves/grok-wave-0001.intent.json', intent)
    result = {'ordinals': [1, 2], 'intent_sha256': pin,
              'terminals': [{'ordinal': n, 'state': 'ambiguous', 'terminal_sha256': str(n)} for n in (1, 2)]}
    put(tmp_path, 'root/waves/grok-wave-0001.result.json', result)
    lineage = {'endpoint': 'grok', 'wave_starts': [1, 1, 2], 'wave_size': 2, 'wave_end': 2,
               'wave_pattern': 'waves/{endpoint}-wave-{start:04d}'}
    root, receipts = census.packet_receipts(census.Inputs(tmp_path), lineage, 'root/manifest.json', 'manifest')
    assert root == 'root' and [r['ordinal'] for r in receipts] == [1, 2]
    result['terminals'].reverse()
    put(tmp_path, 'root/waves/grok-wave-0001.result.json', result)
    with pytest.raises(ValueError, match='Wave order'):
        census.packet_receipts(census.Inputs(tmp_path), lineage, 'root/manifest.json', 'manifest')


def grok_fixture(tmp_path, accepted):
    base = 'root/attempts/request-0001'
    started = {'ordinal': 1, 'attempt_number': 1, 'session_id': 'synthetic-session', 'manifest_sha256': 'manifest',
               'plan_sha256': 'plan', 'prompt_sha256': 'prompt', 'schema_sha256': 'schema'}
    put(tmp_path, base + '/attempt-start.json', started)
    put(tmp_path, base + '/contact-admission.json', {'ordinal': 1, 'session_id': 'synthetic-session',
        'disclosure_sha256': 'disclosure', 'route_sha256': 'route'})
    value = {'question_id': 'leaf', 'verdict': 'YES', 'artifact_id': 'sample', 'bundle_id': 'prose.short_form',
             'note': 'private-rationale', 'evidence': [{'exact_quote': 'private-prose'}]}
    native = {'session_id_hash': census.sha(b'synthetic-session'), 'request_id_hash': 'native-request', 'observed_turns': 1}
    runtime = {**native, 'envelope_hash': 'envelope', 'execution_contract': {'staged_prompt_sha256': 'prompt'}}
    outcome = {'state': 'completed' if accepted else 'ambiguous', 'failure': None,
               'result': {'runtime': runtime, 'native_envelope_artifact': {'sha256': 'envelope'},
                          'output': {'verdicts': [value]}} if accepted else None}
    outcome_pin = put(tmp_path, base + '/broker-outcome.json', outcome)
    terminal = {'ordinal': 1, 'session_id': 'synthetic-session', 'manifest_sha256': 'manifest', 'plan_sha256': 'plan',
                'state': 'accepted' if accepted else 'ambiguous', 'broker_outcome_sha256': outcome_pin}
    if accepted:
        terminal.update(native_identity=native, native_envelope_sha256='envelope', verdicts=[value])
    terminal_pin = put(tmp_path, base + '/terminal.json', terminal)
    row = {'ordinal': 1, 'sample_id': 'sample', 'prompt_sha256': 'prompt', 'schema_sha256': 'schema', 'question_ids': ['leaf']}
    lineage = {'endpoint': 'grok', 'attempt_pattern': 'attempts/request-{ordinal:04d}', 'ambiguous': [] if accepted else [1]}
    receipt = {'state': terminal['state'], 'terminal_sha256': terminal_pin, 'wave_result_sha256': 'wave', 'wave_intent_sha256': 'intent'}
    return row, lineage, receipt


@pytest.mark.parametrize('accepted', [False, True])
def test_packet_projection_preserves_ambiguity_without_leaking_text(tmp_path, accepted):
    row, lineage, receipt = grok_fixture(tmp_path, accepted)
    result = census.project_packet(census.Inputs(tmp_path), 'panel', row, {'source_sha256': 'source'}, lineage,
        'root', receipt, {'disclosure_sha256': 'disclosure', 'route_sha256': 'route'}, 'manifest', 'plan')
    assert result['accepted'] is accepted
    assert len(result['leaves']) == int(accepted)
    assert result['no_resend'] is True
    assert result['native_identity_sha256'] == ('native-request' if accepted else None)
    assert 'private-rationale' not in json.dumps(result)
    assert 'private-prose' not in json.dumps(result)


def test_unknown_exit_reconciles_native_message_without_manufacturing_process_success(tmp_path):
    response = {'verdicts': [{'question_id': 'leaf', 'verdict': 'YES'}]}
    final = census.canonical(response)
    events = [{'type': 'thread.started', 'thread_id': 'native-thread'}, {'type': 'turn.started'},
              {'type': 'item.completed', 'item': {'type': 'agent_message', 'text': final.decode()}}, {'type': 'turn.completed'}]
    event_raw = b'\n'.join(census.canonical(e) for e in events)
    base = tmp_path / 'root'
    base.mkdir()
    (base / 'events.jsonl').write_bytes(event_raw)
    (base / 'final.json').write_bytes(final)
    completion = {'event_sha256': census.sha(event_raw), 'event_bytes': len(event_raw), 'final_sha256': census.sha(final),
                  'final_bytes': len(final), 'state': 'timeout_unknown_exit', 'exit_code': None}
    completion_pin = put(tmp_path, 'root/process-completion.json', completion)
    evidence = {'process_completion_sha256': completion_pin, 'final_sha256': census.sha(final),
                'events_sha256': census.sha(event_raw), 'original_process_exit_state': 'timeout_unknown_exit',
                'provider_calls_by_reconciliation': 0,
                'native_identity': {'thread_id': 'native-thread', 'turn_completed': True, 'tool_events': 0, 'native_event_count': 4}}
    _, actual, proof = census.native_sol(census.Inputs(tmp_path), 'root', evidence, True)
    assert actual == response
    assert proof['process_state'] == 'timeout_unknown_exit' and proof['process_exit_code'] is None
    with pytest.raises(ValueError, match='process completion'):
        census.native_sol(census.Inputs(tmp_path), 'root', evidence, False)


def test_cli_dry_run_creates_nothing_and_existing_outputs_fail(tmp_path, monkeypatch, capsys):
    control, here = tmp_path / 'control', tmp_path / 'code'
    control.mkdir(); here.mkdir()
    put(here, 'recipe.json', {'scope': 'synthetic'})
    output = tmp_path / 'output'
    report = {'observed': {}, 'nonempirical_dispositions': [], 'verified_artifact_count': 0, 'status': 'partial'}
    monkeypatch.setattr(census, 'HERE', here)
    monkeypatch.setattr(census, 'build_census', lambda *args: (report, {}))
    monkeypatch.setattr(sys, 'argv', ['census.py', '--control-root', str(control), '--output-root', str(output), '--dry-run'])
    assert census.main() == 0
    assert not output.exists()
    assert json.loads(capsys.readouterr().out)['dry_run'] is True
    output.mkdir()
    with pytest.raises(ValueError, match='fresh'):
        census.main()


def test_stopped_remainder_requires_explicit_nonaccepted_terminal_wave():
    terminal = {'endpoints': [{'endpoint': 'grok', 'state': 'stopped_nonaccepted_wave', 'wave_start': 25}]}
    lineage = {'endpoint': 'grok', 'wave_starts': [1, 25, 8]}
    receipts = [{'ordinal': 28, 'state': 'ambiguous'}, {'ordinal': 32, 'state': 'accepted'}]
    census.stopped_lineage(terminal, lineage, receipts)
    with pytest.raises(ValueError, match='Stopped lineage'):
        census.stopped_lineage(terminal, lineage, [{'ordinal': 32, 'state': 'accepted'}])
    terminal['endpoints'][0]['wave_start'] = 17
    with pytest.raises(ValueError, match='Stopped lineage'):
        census.stopped_lineage(terminal, lineage, receipts)


def test_suffix_contact_disclosure_stays_distinct_from_preparation_disclosure(tmp_path):
    row, lineage, receipt = grok_fixture(tmp_path, True)
    manifest = {'disclosure_sha256': 'suffix-preparation-disclosure', 'route_sha256': 'route'}
    with pytest.raises(ValueError, match='Contact admission'):
        census.project_packet(census.Inputs(tmp_path), 'fiction', row, {'source_sha256': 'source'}, lineage,
                              'root', receipt, manifest, 'manifest', 'plan')
    lineage['contact_disclosure_sha256'] = 'disclosure'
    slot = census.project_packet(census.Inputs(tmp_path), 'fiction', row, {'source_sha256': 'source'}, lineage,
                                 'root', receipt, manifest, 'manifest', 'plan')
    assert slot['lineage']['contact_disclosure_sha256'] == 'disclosure'
    assert slot['lineage']['manifest_disclosure_sha256'] == 'suffix-preparation-disclosure'
