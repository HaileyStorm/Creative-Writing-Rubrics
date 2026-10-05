"""Recover one pinned Grok saved-history response without contacting a provider.

Creates a fresh private saved_history_reconciliation_v1 descendant. This is
not reconstruction of the original native envelope or full runtime contract.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from urllib.parse import unquote

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
TOOLS = Path(r'C:\Users\Haile\.codex\tools')
PINNED_SLOT = '0077-17c45dba71a4'
PINNED_INPUTS = {
    'manifest': ('8789835ceef5d507d1d5662a0fbccf34ad8ea9528cd80e2c801e9df6815fec19', 2357824),
    'job': ('6fb3d16f5d96556e2b7e0ffd9c425fdfc5b61a05c3327b0cd51ce90e32d08f65', 4429),
    'condition': ('3666a978adfd78b3db641ebdc84b8bd191273c8c05871915cefc84a704ee45e7', 1498),
    'identity': ('ff37edf9eba37ab7c1d9c9f675dcf10756c554042c0338d49a3fe76c837fff3c', 150),
    'started': ('92fc01b9e43c9a1af9c2c1689cce4316724f6202da831656cc7b1efba3d37c23', 155),
    'terminal': ('710e15b5ed0dd23f1dcd6153a59a9aa851a017905cb1a50afbdc503cc32ce8da', 69),
    'ambiguous': ('261864f98269417d3a1b40ea36fe1aed1073a3df116dcd78b5b7c55cc46b9fae', 602),
    'summary': ('e03afbf785b79ad8ee6c6b4d076e67deb829cad3b1b7b925992850aa9fa88546', 931),
    'chat': ('aeded68c8f355a11f275c7f3cecfd2d46381ed394ae8a48024e850846661ad12', 265013),
    'updates': ('b01a525fe62e9b453dae7bf5939e30e3eeae9fa82f79352b812f78de1e032624', 84309),
    'events': ('4cdbb8269606c366576353347b3f182baeef302ecb244d5d4c280a4883f49b88', 357427),
    'prompt_history': ('34581d98bf191089892dfd03a03943b3e9a5cc00954906bb93a86f99abe76f79', 17227),
    'tool_definitions': ('4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945', 2),
    'system_prompt': ('d8711efa61dbbc48826ea2aa504cb3850f00ffd0ba693b59c4a9bf8a04517405', 99),
    'signals': ('5fd5d60a5bd653c8343397543ee353c069d579f13a964e917fd351818b626501', 1512),
    'usage': ('7abcd7486d44cb85287157c726b3c7059d03529a87ae598e71a67e58238aef2d', 1466),
    'prompt_context': ('1be553bb39aac0469b67cd2154805112b40819043eb0b24d18a58dec8832488c', 721),
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode('utf-8')


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def timestamp(value):
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, timezone.utc)
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    require(result.tzinfo is not None, 'Native timestamp lacks timezone')
    return result


class Inputs:
    def __init__(self, pins):
        self.pins, self.raws, self.paths = pins, {}, {}

    def raw(self, name, path, pin=None, size=None):
        raw = path.read_bytes()
        require(len(raw) <= 16 * 1024 * 1024, 'Retained file exceeds bounded input limit')
        expected, count = self.pins.get(name, (pin, size))
        require(expected is None or sha(raw) == expected, f'Source hash differs: {name}')
        require(count is None or len(raw) == count, f'Source size differs: {name}')
        require(name not in self.raws or self.raws[name] == raw, 'Input changed during reconciliation')
        self.raws[name], self.paths[name] = raw, path
        return raw

    def json(self, name, path, pin=None, size=None):
        return json.loads(self.raw(name, path, pin, size))

    def lines(self, name, path):
        return [json.loads(row) for row in self.raw(name, path).splitlines() if row.strip()]

    def commitments(self):
        return {name: {'source_locator': str(self.paths[name]), 'sha256': sha(raw), 'bytes': len(raw)}
                for name, raw in sorted(self.raws.items())}


def frozen(inputs, root, manifest, name, relative, pin, size=None):
    path = (root / relative).resolve()
    require(path.is_relative_to(root) and path != root, 'Frozen source path escapes manifest root')
    metadata = manifest['artifacts'][relative]
    require(metadata['sha256'] == pin and (size is None or metadata['bytes'] == size), 'Frozen artifact descriptor differs')
    return inputs.raw(name, path, pin, metadata['bytes'])


def admission_implementation(inputs, implementation):
    subset_path = TOOLS / 'model_work_queue/adapters/json_schema_subset.py'
    validator_path = HERE / 'validate_response.py'
    inputs.raw('schema_subset_implementation', subset_path, implementation['schema_subset_sha256'])
    inputs.raw('semantic_validator_implementation', validator_path, implementation['semantic_validator_sha256'])
    def load(name, path):
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    return load('ttcw_saved_history_subset', subset_path), load('ttcw_saved_history_validator', validator_path)


def history_response(inputs, session_root, identity, started, job, prompt):
    session = identity['session_id']
    require(session_root.name == session and started['session_id'] == session, 'Saved session identity differs')
    summary = inputs.json('summary', session_root / 'summary.json')
    chat = inputs.lines('chat', session_root / 'chat_history.jsonl')
    updates = inputs.lines('updates', session_root / 'updates.jsonl')
    events = inputs.lines('events', session_root / 'events.jsonl')
    histories = inputs.lines('prompt_history', session_root.parent / 'prompt_history.jsonl')
    tools = inputs.json('tool_definitions', session_root / 'tool_definitions.json')
    signals = inputs.json('signals', session_root / 'signals.json')
    inputs.json('usage', session_root / 'usage.json')
    inputs.json('prompt_context', session_root / 'prompt_context.json')
    system = inputs.raw('system_prompt', session_root / 'system_prompt.txt')
    require(system == b'Act as an isolated structured-output evaluator. Do not use memory, tools, web, plans, or subagents.',
            'Saved system instruction differs')
    require(summary['info']['id'] == session and summary['info']['cwd'] == unquote(session_root.parent.name)
            and summary['current_model_id'] == job['model']
            and isinstance(summary['request_id'], str) and summary['request_id'], 'Saved model/request identity differs')
    start, created, finished = timestamp(started['time']), timestamp(summary['created_at']), timestamp(summary['updated_at'])
    require(start - timedelta(seconds=120) <= created <= finished
            and finished <= timestamp(job['cutoff']), 'Saved session time binding differs')
    require(len(histories) == 1 and histories[0]['session_id'] == session and histories[0]['is_bash'] is False,
            'Saved prompt/session cardinality differs')
    saved = histories[0]['prompt'].encode('utf-8')
    exact, projected = saved == prompt, prompt.endswith(b'\n') and saved == prompt[:-1]
    require(exact or projected, 'Saved prompt differs from frozen source')
    require(created - timedelta(seconds=120) <= timestamp(histories[0]['timestamp']) <= finished,
            'Saved prompt timestamp differs')
    require(tools == [] and all(signals.get(key) == 0 for key in
            ('toolCallCount', 'toolFailureCount', 'errorCount', 'cancellationCount', 'inferenceIdleTimeouts'))
            and signals['assistantMessageCount'] == signals['turnCount'] == 1,
            'Saved history contains tools/errors/partial turn')
    assistants = [row for row in chat if row.get('type') == 'assistant']
    require(len(assistants) == 1 and chat[-1] == assistants[0]
            and all(row.get('type') in {'system', 'user', 'reasoning', 'assistant'} for row in chat),
            'Saved chat is partial or has tool state')
    message = assistants[0]
    require(message['model_id'] == job['route']['reported_model'] and isinstance(message['content'], str),
            'Saved assistant reported model/content differs')
    chunks, terminals, previous = [], [], None
    for wrapper in updates:
        params, time = wrapper['params'], timestamp(wrapper['timestamp'])
        require(params['sessionId'] == session and created - timedelta(seconds=120) <= time <= finished + timedelta(seconds=120)
                and (previous is None or previous <= time), 'Saved update identity/time differs')
        previous = time
        update = params['update']
        kind = update['sessionUpdate']
        require(kind in {'user_message_chunk', 'agent_thought_chunk', 'agent_message_chunk', 'turn_completed'},
                'Saved update contains unsupported/tool state')
        if kind == 'agent_message_chunk':
            require(update['content']['type'] == 'text', 'Saved assistant stream is not text')
            chunks.append(update['content']['text'])
        if kind == 'turn_completed':
            terminals.append(update)
    require(len(terminals) == 1 and updates[-1]['params']['update'] == terminals[0]
            and terminals[0]['stop_reason'] == 'end_turn' and terminals[0]['prompt_id'] == summary['request_id']
            and ''.join(chunks) == message['content'], 'Saved stream lacks exact completed assistant response')
    ended = [event for event in events if event.get('type') == 'turn_ended']
    require(len(ended) == 1 and events[-1] == ended[0] and ended[0]['outcome'] == 'completed'
            and all('tool' not in event['type'] and 'error' not in event['type'] for event in events),
            'Saved event terminal/tool state differs')
    require(abs((timestamp(ended[0]['ts']) - finished).total_seconds()) <= 120, 'Saved completed event timestamp differs')
    raw = message['content'].encode('utf-8')
    return raw, {'session_id': session, 'session_id_sha256': sha(session.encode()),
                 'request_id': summary['request_id'], 'request_id_sha256': sha(summary['request_id'].encode()),
                 'requested_model': job['model'], 'reported_model': message['model_id'], 'completed_at': summary['updated_at'],
                 'prompt_projection': 'exact' if exact else 'single_terminal_lf_omission',
                 'assistant_bytes': len(raw), 'assistant_sha256': sha(raw)}


def reconcile(manifest_path, results_root, slot, session_root, pins):
    inputs = Inputs(pins)
    root = manifest_path.resolve().parent
    manifest = inputs.json('manifest', manifest_path)
    body = {k: v for k, v in manifest.items() if k != 'manifest_content_sha256'}
    require(sha(canonical(body) + b'\n') == manifest['manifest_content_sha256'], 'Manifest content commitment differs')
    job = inputs.json('job', results_root / 'job.json')
    require(job['manifest_sha256'] == sha(inputs.raws['manifest']) and job['endpoint'] == 'grok'
            and job['automatic_retries'] == 0 and job['zero_charge_only'] is True
            and job['route_sha256'] == sha(canonical(job['route']))
            and job['route']['model'] == job['model'], 'Original job/route binding differs')
    policy = manifest['collection_policy']
    require(job['collector_policy'] == policy['name'] and job['collector_sha256'] == policy['collector_sha256']
            and job['validator_sha256'] == manifest['implementation']['semantic_validator_sha256'], 'Frozen admission binding differs')
    inputs.raw('collector_implementation', HERE / 'collector_v2.py', job['collector_sha256'])
    require(Path(slot).name == slot and slot not in {'.', '..'}, 'Slot must be one retained directory name')
    sample = results_root / slot
    row = inputs.json('condition', sample / 'condition.json')
    matches = [r for r in manifest['requests'] if r['logical_sample_id'] == row['logical_sample_id'] and r['endpoint'] == 'grok']
    require(len(matches) == 1 and matches[0] == row
            and slot == f"{row['endpoint_ordinal']:04d}-{row['logical_sample_id'][:12]}"
            and row['request_sha256'] == sha(canonical({k: v for k, v in row.items() if k != 'request_sha256'}) + b'\n'),
            'Slot condition/request commitment differs')
    identity = inputs.json('identity', sample / 'native-identity.json')
    started = inputs.json('started', sample / 'attempt-started.json')
    terminal = inputs.json('terminal', sample / 'terminal.json')
    ambiguous = inputs.json('ambiguous', sample / 'native-result.json')
    require(identity['logical_sample_id'] == row['logical_sample_id'] and started['state'] == 'before_contact'
            and started['no_resend'] is True and terminal == {'accepted': False, 'no_resend': True, 'state': 'ambiguous'}
            and ambiguous['state'] == 'ambiguous' and ambiguous['result'] is None
            and ambiguous['failure']['code'] == 'unclassified_after_launch', 'Original ambiguity/attempt binding differs')
    prompt = frozen(inputs, root, manifest, 'frozen_prompt', row['prompt_path'], row['prompt_sha256'], row['prompt_bytes'])
    schema_raw = frozen(inputs, root, manifest, 'frozen_schema', row['schema_path'], row['schema_sha256'], row['schema_bytes'])
    require(inputs.raw('retained_schema', sample / 'schema.json') == schema_raw, 'Retained schema differs')
    context_meta = manifest['artifacts']['context.txt']
    context = frozen(inputs, root, manifest, 'frozen_context', 'context.txt', context_meta['sha256']).decode('utf-8')
    sources = {source['id']: frozen(inputs, root, manifest, 'source_' + str(index), source['input_path'], source['sha256']).decode('utf-8')
               for index, source in enumerate(row['sources'])}
    subset, validator = admission_implementation(inputs, manifest['implementation'])
    response_raw, native = history_response(inputs, session_root, identity, started, job, prompt)
    response = json.loads(response_raw)
    schema = json.loads(schema_raw)
    subset.validate_schema(schema)
    require(subset.matches_schema(response, schema), 'Completed saved response violates frozen schema')
    if row['arm'] == 'hbq':
        require([v['question_id'] for v in response['verdicts']] == row['question_ids'], 'Completed response question order differs')
    acceptance = validator.semantic_validate(row['arm'], response, row, sources, subset, context=context, schema=schema)
    receipt = {'schema_version': 1, 'evidence_class': 'saved_history_reconciliation_v1',
               'slot': slot, 'logical_sample_id': row['logical_sample_id'], 'endpoint': 'grok', 'arm': row['arm'],
               'state': 'completed_semantically_accepted' if acceptance['accepted'] else 'completed_semantically_rejected',
               'accepted': acceptance['accepted'], 'abstention': acceptance['abstention'], 'semantic_errors': acceptance['errors'],
               'original_terminal_preserved': 'ambiguous', 'no_resend': True, 'provider_calls_made': 0,
               'original_native_envelope_reconstructed': False, 'full_runtime_contract_attested': False,
               'native_identity': native, 'source_commitments': inputs.commitments(),
               'response_sha256': sha(response_raw), 'acceptance_sha256': sha(canonical(acceptance) + b'\n'),
               'implementation_sha256': sha(Path(__file__).read_bytes())}
    return receipt, response_raw, acceptance, inputs


def write_new(path, raw):
    with path.open('xb') as stream:
        stream.write(raw)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for flag in ('manifest', 'results-root', 'session-root', 'private-output'):
        parser.add_argument('--' + flag, type=Path, required=True)
    parser.add_argument('--slot', required=True)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    output = args.private_output.resolve()
    roots = [REPO, args.manifest.resolve().parent, args.results_root.resolve(), args.session_root.resolve().parent]
    require(not output.exists() and all(not output.is_relative_to(r) and not r.is_relative_to(output) for r in roots),
            'Private output must be fresh and outside retained input trees and repository')
    require(args.slot == PINNED_SLOT, 'CLI requires the pinned slot77 source contract')
    receipt, response, acceptance, inputs = reconcile(args.manifest.resolve(), args.results_root.resolve(),
                                                      args.slot, args.session_root.resolve(), PINNED_INPUTS)
    if not args.dry_run:
        output.mkdir(parents=True, exist_ok=False)
        write_new(output / 'invocation.json', canonical({'slot': args.slot, 'evidence_class': receipt['evidence_class'],
                  'implementation_sha256': receipt['implementation_sha256'], 'provider_calls_made': 0}) + b'\n')
        try:
            snapshot = output / 'snapshot'
            snapshot.mkdir()
            for name, raw in inputs.raws.items():
                require(inputs.paths[name].read_bytes() == raw, 'Input changed before private snapshot')
                write_new(snapshot / (name + '.bin'), raw)
            write_new(output / 'reconcile_history.py', Path(__file__).read_bytes())
            write_new(output / 'response.json', response)
            write_new(output / 'acceptance.json', canonical(acceptance) + b'\n')
            write_new(output / 'reconciliation.json', canonical(receipt) + b'\n')
            write_new(output / 'terminal.json', canonical({'state': receipt['state'], 'reconciliation_sha256': sha(canonical(receipt) + b'\n')}) + b'\n')
        except (OSError, ValueError):
            write_new(output / 'terminal.json', canonical({'state': 'failed_private_snapshot_pending', 'no_resend': True}) + b'\n')
            raise
    print(json.dumps({'dry_run': args.dry_run, 'evidence_class': receipt['evidence_class'], 'state': receipt['state'],
                      'accepted': receipt['accepted'], 'abstention': receipt['abstention'],
                      'semantic_error_count': len(receipt['semantic_errors']), 'verified_input_files': len(inputs.raws),
                      'response_sha256': receipt['response_sha256'], 'receipt_sha256': sha(canonical(receipt) + b'\n'),
                      'provider_calls_made': 0, 'no_resend': True}, sort_keys=True))
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise SystemExit(f'History reconciliation pending: {type(error).__name__}')
