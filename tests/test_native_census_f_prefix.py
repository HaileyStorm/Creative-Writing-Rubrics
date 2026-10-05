import copy
import importlib.util
import json
from pathlib import Path

import pytest

PATH = Path(__file__).resolve().parents[1] / 'evaluation-results/hbq-census-native-f-v1/join_prefix.py'
spec = importlib.util.spec_from_file_location('native_census_f_prefix_test', PATH)
join = importlib.util.module_from_spec(spec)
spec.loader.exec_module(join)


def native_fixture(number=1):
    questions = ['q1', 'q2']
    leaves = [{'question_id': 'q1', 'verdict': 'CANNOT_ASSESS'}, {'question_id': 'q2', 'verdict': 'NOT_APPLICABLE'}]
    schema = join.canonical({'type': 'object'})
    prompt = 'private prompt'
    slot = {'question_ids': questions, 'leaves': leaves, 'prompt_sha256': join.sha(prompt.encode()), 'schema_sha256': join.sha(schema)}
    output = {'verdicts': [{**x, 'note': 'private rationale'} for x in leaves]}
    request = {'prompt': prompt}
    context = {'prompt_sha256': slot['prompt_sha256'], 'prompt_bytes': len(prompt), 'response_schema_sha256': slot['schema_sha256'],
               'response_schema_bytes': len(schema), 'question_ids': questions, 'attempt_number': 1, 'batch_number': number}
    envelope = {'text': json.dumps(output), 'structuredOutput': output, 'requestId': 'request-' + str(number),
                'sessionId': 'session-' + str(number), 'stopReason': 'end_turn', 'num_turns': 1}
    raw_env = join.canonical(envelope)
    result = {'output': output, 'output_hash': join.digest(output), 'request_hash': join.digest(request),
              'native_envelope_artifact': {'sha256': join.sha(raw_env), 'byte_length': len(raw_env)}}
    outcome = {'state': 'completed', 'failure': None, 'result': result}
    raws = {key: join.canonical(value) for key, value in {'request': request, 'context': context, 'outcome': outcome, 'envelope': envelope}.items()}
    receipt = {key + '_sha256': join.sha(raw) for key, raw in raws.items()}
    receipt.update({'result_sha256': join.digest(result), 'request_id_hash': join.sha(envelope['requestId'].encode()),
                    'session_id_hash': join.sha(envelope['sessionId'].encode()), 'schema_sha256': slot['schema_sha256'],
                    'route_sha256': 'a' * 64, 'source_sha256': 'b' * 64})
    raws['receipt'] = join.canonical(receipt)
    provider = {'evidence_sha256': join.sha(raws['receipt']), 'request_id_sha256': receipt['request_id_hash'], 'session_id_sha256': receipt['session_id_hash'], 'reasoning_attested': False}
    return raws, provider, slot, schema


def test_exact_native_identity_and_four_states_without_attestation_upgrade():
    raws, provider, slot, schema = native_fixture()
    proof = join.validate_native(raws, provider, slot, schema, batch=1)
    assert proof['raw_states_sha256'] == join.digest(slot['leaves'])
    assert proof['modern_native_attestation'] is False
    assert proof['reported_reasoning_attested'] is False
    assert proof['native_identity']['session_id_hash'] == provider['session_id_sha256']


@pytest.mark.parametrize('change', ['identity', 'request', 'order', 'state', 'schema'])
def test_native_binding_failures_remain_failures(change):
    raws, provider, slot, schema = native_fixture()
    if change == 'identity':
        provider['session_id_sha256'] = 'f' * 64
    elif change == 'request':
        raws['request'] = join.canonical({'prompt': 'different source prompt'})
    elif change == 'order':
        slot['question_ids'].reverse()
    elif change == 'state':
        slot['leaves'][0]['verdict'] = 'NO'
    else:
        schema = b'{}'
    with pytest.raises(ValueError):
        join.validate_native(raws, provider, slot, schema, batch=1)


def prefix_fixture(tmp_path):
    root = tmp_path / 'retained'
    root.mkdir()
    inventory = {}

    def put(path, raw):
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
        inventory[path] = join.sha(raw)
        return {'path': path, 'sha256': join.sha(raw), 'bytes': len(raw)}

    fixtures = [native_fixture(n) for n in (1, 2)]
    source = {'sha256': 'c' * 64, 'bytes': 10}
    configuration = {'artifact': source, 'batch_response_schemas': [put(f'schemas/{n}.json', fixture[3]) for n, fixture in enumerate(fixtures, 1)]}
    run = {'configuration': configuration, 'config_sha256': join.sha(join.pretty(configuration)), 'run_id': 'fixture-run'}
    run_pin = put('run.json', join.pretty(run))
    slots, cumulative, previous = {}, [], None
    for n, (raws, provider, slot, schema) in enumerate(fixtures, 1):
        context = json.loads(raws['context'])
        context['run'] = {'config_sha256': run['config_sha256'], 'run_id': run['run_id']}
        raws['context'] = join.canonical(context)
        receipt = json.loads(raws['receipt'])
        receipt['context_sha256'] = join.sha(raws['context'])
        raws['receipt'] = join.canonical(receipt)
        provider['evidence_sha256'] = join.sha(raws['receipt'])
        provider['provider_artifacts'] = {k: put(f'broker/{n}/{k}.json', raw) for k, raw in raws.items()}
        output = json.loads(raws['outcome'])['result']['output']
        message = put(f'accepted/{n}.txt', join.canonical(output))
        import gzip
        put(f'responses/batch-{n:04d}.prompt.txt.gz', gzip.compress(b'private prompt'))
        cumulative.extend(output['verdicts'])
        cp = {'batch': n, 'accepted_attempt': 1, 'previous_checkpoint_sha256': previous, 'question_ids': slot['question_ids'],
              'base_prompt_sha256': slot['prompt_sha256'], 'effective_prompt_sha256': slot['prompt_sha256'], 'prompt_sha256': slot['prompt_sha256'],
              'normalized_verdicts': output['verdicts'], 'verdicts_sha256': join.verdict_hash(cumulative), 'response_artifact': message,
              'response_sha256': message['sha256'], 'provider': provider}
        relative = f'responses/batch-{n:04d}.json'
        cp_pin = put(relative, join.canonical(cp))
        previous = cp_pin['sha256']
        start = {'state': 'started', 'batch': n, 'attempt': 1, 'config_sha256': run['config_sha256'],
                 'base_prompt_sha256': slot['prompt_sha256'], 'effective_prompt_sha256': slot['prompt_sha256']}
        start_pin = put(f'responses/attempt-lifecycle/batch-{n:04d}/attempt-0001.start.json', join.canonical(start))
        settled = {'state': 'settled', 'outcome': 'accepted', 'batch': n, 'attempt': 1, 'start_sha256': start_pin['sha256'],
                   'evidence': {'kind': 'accepted_checkpoint', 'path': relative, 'sha256': previous}}
        put(f'responses/attempt-lifecycle/batch-{n:04d}/attempt-0001.settled.json', join.canonical(settled))
        slots[n] = {**slot, 'pass_id_sha256': join.digest('p'), 'source_sha256': source['sha256'], 'historical_replay_input_commitments_sha256': join.digest({'prefix': 'e' * 64})}
    return root, inventory, slots, {'pass_id': 'p', 'source': source, 'replay_input_commitments': {'prefix': 'e' * 64}}, {'run_manifest_sha256': run_pin['sha256'], 'checkpoint_head_sha256': previous}, put


@pytest.mark.parametrize('change', ['checkpoint', 'pass', 'replay'])
def test_checkpoint_cumulative_commitment_and_predecessor_chain(tmp_path, change):
    root, inventory, slots, row, commits, put = prefix_fixture(tmp_path)
    proofs = join.join_prefix_run(join.Inputs(tmp_path), 'retained', inventory, row, slots, [(1, 1), (2, 2)], commits)
    assert len(proofs) == 2 and proofs[0]['proof']['native_identity'] != proofs[1]['proof']['native_identity']
    if change == 'checkpoint':
        cp = json.loads((root / 'responses/batch-0002.json').read_bytes())
        cp['previous_checkpoint_sha256'] = 'f' * 64
        put('responses/batch-0002.json', join.canonical(cp))
    elif change == 'pass':
        slots[1]['pass_id_sha256'] = 'f' * 64
    else:
        slots[1]['historical_replay_input_commitments_sha256'] = 'f' * 64
    with pytest.raises(ValueError):
        join.join_prefix_run(join.Inputs(tmp_path), 'retained', inventory, row, slots, [(1, 1), (2, 2)], commits)


def test_inventory_pin_mismatch_fails(tmp_path):
    root, inventory, slots, row, commits, put = prefix_fixture(tmp_path)
    (root / 'run.json').write_bytes(b'{}')
    with pytest.raises(ValueError, match='hash'):
        join.join_prefix_run(join.Inputs(tmp_path), 'retained', inventory, row, slots, [(1, 1), (2, 2)], commits)


def membership_fixture():
    pairs = [{'request_id_hash': join.sha(('r' + str(n)).encode()), 'session_id_hash': join.sha(('s' + str(n)).encode())} for n in range(2297)]
    joined = []
    counter = 0
    for ordinal in [*range(1, 88), 89, 90, 91]:
        native = None if ordinal == 70 else pairs[counter]
        counter += ordinal != 70
        joined.append({'ordinal': ordinal, 'proof': {'native_identity': native}})
    positions = [{'ordinal': x['ordinal'], 'proof': None} for x in joined]
    positions.extend({'ordinal': 88 if n == 0 else 10000 + n, 'proof': {'native_identity': value}} for n, value in enumerate(pairs[89:]))
    base = {'positions': positions, 'ordinary_native_identities': pairs,
            'historical_excluded_native_identities': [{'request_id_hash': 'a' * 64, 'session_id_hash': 'b' * 64}]}
    return base, joined


def test_existing_admission_membership_once_and_non_native70():
    base, joined = membership_fixture()
    assert len(join.membership(base, joined)) == 2297
    changed = copy.deepcopy(joined)
    changed[0]['ordinal'] = 88
    with pytest.raises(ValueError, match='deduplicated'):
        join.membership(base, changed)


@pytest.mark.parametrize('change', ['excluded', 'reused', 'unknown', 'manufactured70'])
def test_membership_does_not_add_rejected_or_duplicate_native_vote(change):
    base, joined = membership_fixture()
    if change == 'excluded':
        base['historical_excluded_native_identities'] = [joined[0]['proof']['native_identity']]
    elif change == 'reused':
        joined[0]['proof']['native_identity'] = base['positions'][-1]['proof']['native_identity']
    elif change == 'unknown':
        joined[0]['proof']['native_identity'] = {'request_id_hash': 'c' * 64, 'session_id_hash': 'd' * 64}
    else:
        next(x for x in joined if x['ordinal'] == 70)['proof']['native_identity'] = base['ordinary_native_identities'][0]
    with pytest.raises(ValueError):
        join.membership(base, joined)
