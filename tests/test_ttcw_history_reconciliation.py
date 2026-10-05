from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / 'evaluation-results/hbq-matched-ttcw-20261004'
SPEC = importlib.util.spec_from_file_location('ttcw_history_reconciliation', HERE / 'reconcile_history.py')
history = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(history)


def put(path, value, lines=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = b'\n'.join(history.canonical(x) for x in value) + b'\n' if lines else history.canonical(value) + b'\n'
    path.write_bytes(raw)
    return raw


def fixture(tmp_path, quote='Synthetic source'):
    frozen, results = tmp_path / 'frozen', tmp_path / 'results'
    slot = '0001-abcdefghijkl'
    session_id = 'synthetic-session'
    session = tmp_path / 'saved' / 'synthetic-cwd' / session_id
    sample = results / slot
    evidence = {'type': 'object', 'properties': {'kind': {'type': 'string'}, 'reference': {'type': 'string'},
        'exact_quote': {'type': ['string', 'null']}, 'summary': {'type': ['string', 'null']}},
        'required': ['kind', 'reference', 'exact_quote', 'summary'], 'additionalProperties': False}
    schema = {'type': 'object', 'properties': {'verdicts': {'type': 'array', 'items': {'type': 'object',
        'properties': {'question_id': {'type': 'string'}, 'verdict': {'type': 'string'}, 'note': {'type': ['string', 'null']},
                       'evidence': {'type': 'array', 'items': evidence}},
        'required': ['question_id', 'verdict', 'note', 'evidence'], 'additionalProperties': False}}},
        'required': ['verdicts'], 'additionalProperties': False}
    frozen.mkdir()
    (frozen / 'prompt.txt').write_bytes(b'Synthetic frozen request\n')
    (frozen / 'story.txt').write_bytes(b'Synthetic source text.')
    (frozen / 'context.txt').write_bytes(b'Synthetic context.')
    schema_raw = put(frozen / 'schema.json', schema)
    artifacts = {p.name: {'sha256': history.sha(p.read_bytes()), 'bytes': len(p.read_bytes())} for p in frozen.iterdir()}
    row = {'endpoint': 'grok', 'endpoint_ordinal': 1, 'logical_sample_id': 'abcdefghijkl-more', 'arm': 'hbq',
        'question_ids': ['leaf'], 'prompt_path': 'prompt.txt', 'prompt_sha256': artifacts['prompt.txt']['sha256'],
        'prompt_bytes': artifacts['prompt.txt']['bytes'], 'schema_path': 'schema.json', 'schema_sha256': artifacts['schema.json']['sha256'],
        'schema_bytes': len(schema_raw), 'sources': [{'id': 'story', 'input_path': 'story.txt', 'sha256': artifacts['story.txt']['sha256']}]}
    row['request_sha256'] = history.sha(history.canonical(row) + b'\n')
    implementation = {'schema_subset_sha256': history.sha((history.TOOLS / 'model_work_queue/adapters/json_schema_subset.py').read_bytes()),
                      'semantic_validator_sha256': history.sha((HERE / 'validate_response.py').read_bytes())}
    collector_hash = history.sha((HERE / 'collector_v2.py').read_bytes())
    manifest = {'requests': [row], 'artifacts': artifacts, 'implementation': implementation,
                'collection_policy': {'name': 'semantic_reject_continue_v2', 'collector_sha256': collector_hash}}
    manifest['manifest_content_sha256'] = history.sha(history.canonical(manifest) + b'\n')
    manifest_raw = put(frozen / 'manifest.json', manifest)
    route = {'model': 'grok-4.7', 'reported_model': 'grok-4.7-build'}
    job = {'manifest_sha256': history.sha(manifest_raw), 'endpoint': 'grok', 'model': 'grok-4.7', 'automatic_retries': 0,
           'zero_charge_only': True, 'route': route, 'route_sha256': history.sha(history.canonical(route)),
           'collector_policy': 'semantic_reject_continue_v2', 'collector_sha256': collector_hash,
           'validator_sha256': implementation['semantic_validator_sha256'], 'cutoff': '2026-10-16T00:00:00Z'}
    put(results / 'job.json', job)
    put(sample / 'condition.json', row)
    put(sample / 'native-identity.json', {'logical_sample_id': row['logical_sample_id'], 'session_id': session_id})
    put(sample / 'attempt-started.json', {'session_id': session_id, 'state': 'before_contact', 'time': '2026-10-04T23:00:00Z', 'no_resend': True})
    put(sample / 'terminal.json', {'state': 'ambiguous', 'accepted': False, 'no_resend': True})
    put(sample / 'native-result.json', {'state': 'ambiguous', 'result': None, 'failure': {'code': 'unclassified_after_launch'}})
    (sample / 'schema.json').write_bytes(schema_raw)
    put(session / 'summary.json', {'info': {'id': session_id, 'cwd': 'synthetic-cwd'}, 'current_model_id': 'grok-4.7',
         'request_id': 'native-request', 'created_at': '2026-10-04T23:00:01Z', 'updated_at': '2026-10-04T23:00:10Z'})
    answer = {'verdicts': [{'question_id': 'leaf', 'verdict': 'YES', 'note': None,
        'evidence': [{'kind': 'exact_quote', 'reference': 'story', 'exact_quote': quote, 'summary': None}]}]}
    text = history.canonical(answer).decode()
    put(session / 'chat_history.jsonl', [{'type': 'user', 'content': 'Synthetic frozen request'},
        {'type': 'assistant', 'model_id': 'grok-4.7-build', 'content': text}], lines=True)
    def update(kind, **values):
        return {'timestamp': '2026-10-04T23:00:10Z', 'params': {'sessionId': session_id, 'update': {'sessionUpdate': kind, **values}}}
    put(session / 'updates.jsonl', [update('user_message_chunk'), update('agent_message_chunk', content={'type': 'text', 'text': text}),
        update('turn_completed', stop_reason='end_turn', prompt_id='native-request')], lines=True)
    put(session / 'events.jsonl', [{'ts': '2026-10-04T23:00:01Z', 'type': 'turn_started'},
        {'ts': '2026-10-04T23:00:10Z', 'type': 'turn_ended', 'outcome': 'completed'}], lines=True)
    put(session.parent / 'prompt_history.jsonl', [{'timestamp': '2026-10-04T23:00:02Z', 'session_id': session_id,
        'prompt': 'Synthetic frozen request', 'is_bash': False}], lines=True)
    put(session / 'tool_definitions.json', [])
    put(session / 'signals.json', {'toolCallCount': 0, 'toolFailureCount': 0, 'errorCount': 0, 'cancellationCount': 0,
                                  'inferenceIdleTimeouts': 0, 'assistantMessageCount': 1, 'turnCount': 1})
    put(session / 'usage.json', {})
    put(session / 'prompt_context.json', {})
    (session / 'system_prompt.txt').write_bytes(b'Act as an isolated structured-output evaluator. Do not use memory, tools, web, plans, or subagents.')
    return frozen / 'manifest.json', results, slot, session


def run(paths, pins=None):
    return history.reconcile(*paths, {} if pins is None else pins)


def mutate(path, change, lines=False):
    value = [json.loads(x) for x in path.read_bytes().splitlines()] if lines else json.loads(path.read_bytes())
    change(value)
    put(path, value, lines)


def test_complete_history_admits_exact_response_without_replacing_ambiguity(tmp_path):
    paths = fixture(tmp_path)
    terminal = (paths[1] / paths[2] / 'terminal.json').read_bytes()
    receipt, response, acceptance, _ = run(paths)
    assert acceptance == {'accepted': True, 'abstention': False, 'errors': []}
    assert receipt['evidence_class'] == 'saved_history_reconciliation_v1'
    assert receipt['native_identity']['prompt_projection'] == 'single_terminal_lf_omission'
    assert receipt['provider_calls_made'] == 0 and receipt['no_resend']
    assert not receipt['original_native_envelope_reconstructed'] and not receipt['full_runtime_contract_attested']
    assert receipt['response_sha256'] == history.sha(response)
    assert (paths[1] / paths[2] / 'terminal.json').read_bytes() == terminal


@pytest.mark.parametrize('damage', ['prompt', 'session', 'partial', 'tool', 'request', 'stream'])
def test_wrong_binding_partial_or_tool_history_fails(tmp_path, damage):
    paths = fixture(tmp_path)
    session = paths[3]
    if damage == 'prompt':
        mutate(session.parent / 'prompt_history.jsonl', lambda rows: rows[0].update(prompt='Different request'), True)
    elif damage == 'session':
        mutate(session / 'summary.json', lambda row: row['info'].update(id='different-session'))
    elif damage == 'partial':
        mutate(session / 'updates.jsonl', lambda rows: rows.pop(), True)
    elif damage == 'tool':
        mutate(session / 'signals.json', lambda row: row.update(toolCallCount=1))
    elif damage == 'request':
        mutate(session / 'summary.json', lambda row: row.update(request_id='different-request'))
    else:
        mutate(session / 'updates.jsonl', lambda rows: rows[1]['params']['update']['content'].update(text='Different response'), True)
    with pytest.raises(ValueError):
        run(paths)


def test_completed_invalid_quote_retains_rejection_and_all_errors(tmp_path):
    paths = fixture(tmp_path, quote='Not in the source or context')
    receipt, _, acceptance, _ = run(paths)
    assert receipt['state'] == 'completed_semantically_rejected'
    assert not receipt['accepted'] and not acceptance['accepted']
    assert receipt['semantic_errors'] == acceptance['errors'] == ['HBQ exact quote does not match artifact/context']


def test_source_pin_mismatch_fails_before_history_admission(tmp_path):
    paths = fixture(tmp_path)
    with pytest.raises(ValueError, match='Source hash differs: condition'):
        run(paths, {'condition': ('0' * 64, None)})


def test_cli_dry_run_writes_nothing_and_fresh_output_is_required(tmp_path, monkeypatch, capsys):
    paths = fixture(tmp_path)
    output = tmp_path / 'reconciliation'
    monkeypatch.setattr(history, 'PINNED_SLOT', paths[2])
    monkeypatch.setattr(history, 'PINNED_INPUTS', {})
    monkeypatch.setattr(sys, 'argv', ['reconcile_history.py', '--manifest', str(paths[0]), '--results-root', str(paths[1]),
        '--slot', paths[2], '--session-root', str(paths[3]), '--private-output', str(output), '--dry-run'])
    assert history.main() == 0
    assert not output.exists() and json.loads(capsys.readouterr().out)['accepted'] is True
    output.mkdir()
    with pytest.raises(ValueError, match='fresh'):
        history.main()


def test_private_descendant_preserves_exact_bytes_and_original_ambiguity(tmp_path, monkeypatch, capsys):
    paths = fixture(tmp_path)
    output = tmp_path / 'reconciliation'
    original = (paths[1] / paths[2] / 'terminal.json').read_bytes()
    monkeypatch.setattr(history, 'PINNED_SLOT', paths[2])
    monkeypatch.setattr(history, 'PINNED_INPUTS', {})
    monkeypatch.setattr(sys, 'argv', ['reconcile_history.py', '--manifest', str(paths[0]), '--results-root', str(paths[1]),
        '--slot', paths[2], '--session-root', str(paths[3]), '--private-output', str(output)])
    assert history.main() == 0
    summary = json.loads(capsys.readouterr().out)
    receipt_raw = (output / 'reconciliation.json').read_bytes()
    receipt = json.loads(receipt_raw)
    assert history.sha(receipt_raw) == summary['receipt_sha256']
    assert history.sha((output / 'response.json').read_bytes()) == receipt['response_sha256']
    assert history.sha((output / 'acceptance.json').read_bytes()) == receipt['acceptance_sha256']
    for name, commitment in receipt['source_commitments'].items():
        assert history.sha((output / 'snapshot' / (name + '.bin')).read_bytes()) == commitment['sha256']
    assert (paths[1] / paths[2] / 'terminal.json').read_bytes() == original
    with pytest.raises(ValueError, match='fresh'):
        history.main()
