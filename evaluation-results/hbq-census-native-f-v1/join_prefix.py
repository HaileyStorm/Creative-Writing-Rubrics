"""Separate provider-free descendant joining Census F's retained prefix evidence."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPOSITORY = HERE.parent.parent
BASE_CODE_SHA = 'ea4af5aed3641d15886c701aa06adc832af8f20317d775fdd96c333173de2637'
if hashlib.sha256((HERE / 'census.py').read_bytes()).hexdigest() != BASE_CODE_SHA:
    raise ValueError('Published F implementation changed')
_spec = importlib.util.spec_from_file_location('native_census_f_prefix_base', HERE / 'census.py')
_base = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_base)
Inputs, require, sha, canonical, digest, states, identity = (_base.Inputs, _base.require, _base.sha, _base.canonical, _base.digest, _base.states, _base.identity)

PROGRAM = 'cwr-resume-control-20260919-r1/successor-program-20261004/census-f'
DISCOVERY = PROGRAM + '/prefix-discovery-001'
BASE = PROGRAM + '/run-001'
EPOCH = 'cwr-dryad-grok-selected100-v5-20260910-r1/epoch'
RECIPE = {'source_path_prefix': 'C:/Users/Haile/Documents'}
PINS = {
    'recipe': (DISCOVERY + '/recipe.txt', '6135ff0068d36b4931fd7da93b5b1244be73a96720caa553dc0d07f2a6701c6a', 7128),
    'provenance': (DISCOVERY + '/provenance.json', '7544cd16c9b16c88acc6d6a1f7f518d481004aa66b2aaa2837589a9bd7907b06', 654),
    'report': (BASE + '/census.json', '08fc01e9f1d456f7870b06ef11932514d1b09d9405f6862a6ab918eaa73f5581', 3960),
    'ledger': (BASE + '/private-slots.json', '082e7c336aa5702acc208d4fc30155c85906d781edfc0b1bebaa98fadd1a0593', 8571344),
    'terminal': (BASE + '/terminal.json', '8df6c54c871f4df2a9e04e026aff8bedbb8923a70d0786c0c41aaaae02147a46', 215),
    'epoch': (EPOCH + '/suffix-epoch.json', '74012a612915137c43e35eff5bb64b413be0b2dabbdc3aa52ceb4b88d1a245d6', 199019),
    'train': ('cwr-resume-control-20260919-r1/dryad-final-analysis-r25/train.json', '059bf0959d6abfc74106fd07f9caaaf13ba9303ba8fdedd6f2e564c3c246945d', 18210523),
}
NATIVE_ORDINALS = [*range(1, 70), *range(71, 88), 89, 90, 91]


def locator(path):
    return _base.locator(path, RECIPE)


def pretty(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode('utf-8')


def verdict_hash(value):
    return sha(''.join(json.dumps(x, ensure_ascii=False, sort_keys=True) + '\n' for x in value).encode('utf-8'))


def content(value):
    text = value.strip()
    if text.startswith('```'):
        lines = text.splitlines()
        require(lines[-1] == '```', 'Retained response fence incomplete')
        text = '\n'.join(lines[1:-1])
    return json.loads(text)


def inventory_file(inputs, root, inventory, relative, descriptor=None):
    require(relative in inventory, 'Named file absent from pinned inventory: ' + relative)
    expected = inventory[relative]
    if descriptor is not None:
        require(descriptor['path'] == relative and descriptor['sha256'] == expected, 'Descriptor/inventory pin differs')
    return inputs.raw(root + '/' + relative, expected, descriptor.get('bytes') if descriptor else None)


def validate_native(raws, provider, slot, schema_raw, run=None, batch=None):
    values = {key: json.loads(raw) for key, raw in raws.items()}
    request, context, outcome, envelope, receipt = (values[k] for k in ('request', 'context', 'outcome', 'envelope', 'receipt'))
    require(provider['evidence_sha256'] == sha(raws['receipt']), 'Provider receipt commitment differs')
    for key in ('request', 'context', 'outcome', 'envelope'):
        require(receipt[key + '_sha256'] == sha(raws[key]), 'Native receipt file binding differs')
    require(outcome['state'] == 'completed' and outcome['failure'] is None, 'Native outcome is not completed')
    result = outcome['result']
    require(receipt['result_sha256'] == digest(result) and result['request_hash'] == digest(request)
            and result['output_hash'] == digest(result['output']), 'Native result/request/output commitment differs')
    descriptor = result['native_envelope_artifact']
    require(descriptor['sha256'] == sha(raws['envelope']) and descriptor['byte_length'] == len(raws['envelope']), 'Native envelope descriptor differs')
    native = identity({'request_id_hash': provider['request_id_sha256'], 'session_id_hash': provider['session_id_sha256']})
    require(native == identity(receipt), 'Native receipt/provider identity differs')
    for field, key in (('requestId', 'request_id_hash'), ('sessionId', 'session_id_hash')):
        require(isinstance(envelope[field], str) and envelope[field] and sha(envelope[field].encode('utf-8')) == native[key],
                'Native envelope identity differs')
    require(envelope['stopReason'] == 'end_turn' and envelope['num_turns'] == 1, 'Native completion metadata differs')
    require(envelope['structuredOutput'] == result['output'] and content(envelope['text']) == result['output'], 'Native envelope/output projection differs')
    prompt = request['prompt'].encode('utf-8')
    require(sha(prompt) == context['prompt_sha256'] == slot['prompt_sha256'] and len(prompt) == context['prompt_bytes'], 'Native prompt binding differs')
    require(context['response_schema_sha256'] == slot['schema_sha256'] == receipt['schema_sha256'] == sha(schema_raw)
            and context['response_schema_bytes'] == len(schema_raw) and context['question_ids'] == slot['question_ids'], 'Native schema/question condition differs')
    contract = context.get('execution_contract')
    if contract is not None:
        require(contract['staged_prompt_sha256'] == sha(prompt) and contract['staged_prompt_byte_length'] == len(prompt)
                and contract['output_schema_hash'] == digest(json.loads(schema_raw)) and contract['max_turns'] == 1,
                'Declared execution condition differs')
    if run is not None:
        require(context['run'] == {'config_sha256': run['config_sha256'], 'run_id': run['run_id']}, 'Native run binding differs')
    if batch is not None:
        require(context['attempt_number'] == 1 and context['batch_number'] == batch, 'Native batch/attempt differs')
    raw_states = states(result['output']['verdicts'], slot['question_ids'])
    require(raw_states == slot['leaves'], 'Native ordered raw states differ from F ledger')
    return {'native_identity': native, 'raw_states_sha256': digest(raw_states),
            'request_sha256': sha(raws['request']), 'context_sha256': sha(raws['context']),
            'receipt_sha256': sha(raws['receipt']), 'envelope_sha256': sha(raws['envelope']),
            'outcome_sha256': sha(raws['outcome']), 'schema_sha256': sha(schema_raw),
            'source_transport_sha256': receipt['source_sha256'], 'route_sha256': receipt['route_sha256'],
            'reported_reasoning_attested': provider.get('reasoning_attested'), 'modern_native_attestation': False}


def join_prefix_run(inputs, root, inventory, rows, slots, batches, commitments, nonnative70=False):
    run_raw = inventory_file(inputs, root, inventory, 'run.json')
    run = json.loads(run_raw)
    require(sha(run_raw) == commitments['run_manifest_sha256'], 'Prefix run commitment differs')
    require(sha(pretty(run['configuration'])) == run['config_sha256'], 'Prefix run configuration commitment differs')
    require(run['configuration']['artifact']['sha256'] == rows['source']['sha256']
            and run['configuration']['artifact']['bytes'] == rows['source']['bytes'], 'Prefix source condition differs')
    previous = None
    cumulative = []
    joined = []
    for batch, ordinal in batches:
        relative = f'responses/batch-{batch:04d}.json'
        raw = inventory_file(inputs, root, inventory, relative)
        checkpoint = json.loads(raw)
        require(checkpoint['batch'] == batch and checkpoint['accepted_attempt'] == 1
                and checkpoint['previous_checkpoint_sha256'] == previous, 'Prefix checkpoint chain/accepted attempt differs')
        slot = slots[ordinal]
        require(slot['pass_id_sha256'] == digest(rows['pass_id']) and slot['source_sha256'] == rows['source']['sha256']
                and slot['historical_replay_input_commitments_sha256'] == digest(rows['replay_input_commitments']),
                'Prefix source/pass/replay commitment differs from base F')
        require(checkpoint['question_ids'] == slot['question_ids'] and checkpoint['base_prompt_sha256'] == checkpoint['effective_prompt_sha256']
                == checkpoint['prompt_sha256'] == slot['prompt_sha256'], 'Prefix prompt/question condition differs')
        normalized = checkpoint['normalized_verdicts']
        cumulative.extend(normalized)
        require(verdict_hash(cumulative) == checkpoint['verdicts_sha256']
                and states(normalized, slot['question_ids']) == slot['leaves'], 'Prefix normalized state projection differs')
        message = inventory_file(inputs, root, inventory, checkpoint['response_artifact']['path'], checkpoint['response_artifact'])
        require(sha(message) == checkpoint['response_sha256'] and states(content(message.decode('utf-8'))['verdicts'], slot['question_ids']) == slot['leaves'],
                'Accepted response state projection differs')
        schema_pin = run['configuration']['batch_response_schemas'][batch - 1]
        schema = inventory_file(inputs, root, inventory, schema_pin['path'], schema_pin)
        prompt = gzip.decompress(inventory_file(inputs, root, inventory, f'responses/batch-{batch:04d}.prompt.txt.gz'))
        require(sha(prompt) == slot['prompt_sha256'] and sha(schema) == slot['schema_sha256'], 'Retained prompt/schema differs from F slot')
        if ordinal == 70:
            require(nonnative70, 'Unexpected nonnative projection')
            proof = {'native_identity': None, 'raw_states_sha256': digest(slot['leaves']), 'new_votes_added': 0,
                     'disposition': 'adopted_projection_without_native_identity', 'checkpoint_sha256': sha(raw)}
        else:
            provider = checkpoint['provider']
            raws = {key: inventory_file(inputs, root, inventory, pin['path'], pin) for key, pin in provider['provider_artifacts'].items()}
            proof = validate_native(raws, provider, slot, schema, run, batch)
            start_raw = inventory_file(inputs, root, inventory, f'responses/attempt-lifecycle/batch-{batch:04d}/attempt-0001.start.json')
            settled_raw = inventory_file(inputs, root, inventory, f'responses/attempt-lifecycle/batch-{batch:04d}/attempt-0001.settled.json')
            start, settled = json.loads(start_raw), json.loads(settled_raw)
            require(start['state'] == 'started' and start['batch'] == batch and start['attempt'] == 1 and start['config_sha256'] == run['config_sha256']
                    and start['base_prompt_sha256'] == start['effective_prompt_sha256'] == slot['prompt_sha256'], 'Prefix lifecycle start differs')
            require(settled['state'] == 'settled' and settled['outcome'] == 'accepted' and settled['batch'] == batch and settled['attempt'] == 1
                    and settled['start_sha256'] == sha(start_raw) and settled['evidence'] == {'kind': 'accepted_checkpoint', 'path': relative, 'sha256': sha(raw)},
                    'Prefix lifecycle settlement differs')
            proof.update({'checkpoint_sha256': sha(raw), 'start_sha256': sha(start_raw), 'settled_sha256': sha(settled_raw), 'disposition': 'retained_native_prefix_state_join'})
        joined.append({'ordinal': ordinal, 'pass_id_sha256': slot['pass_id_sha256'], 'source_sha256': slot['source_sha256'],
                       'historical_replay_input_commitments_sha256': slot['historical_replay_input_commitments_sha256'],
                       'question_ids': slot['question_ids'], 'leaves': slot['leaves'], 'proof': proof})
        previous = sha(raw)
    require(previous == commitments['checkpoint_head_sha256'], 'Prefix final checkpoint head differs')
    return joined


def membership(base, joined):
    slots = {x['ordinal']: x for x in base['positions']}
    require(len(slots) == len(base['positions']), 'Duplicate base ordinal')
    require(sorted(x['ordinal'] for x in joined) == [*range(1, 88), 89, 90, 91], 'Prefix replacement set differs; 88/92 must remain deduplicated')
    require(all(slots[x['ordinal']]['proof'] is None for x in joined), 'Attempt to add a second vote to an already joined position')
    new = [identity(x['proof']['native_identity']) for x in joined if x['proof']['native_identity'] is not None]
    existing = [identity(x['proof']['native_identity']) for x in base['positions'] if x['proof'] and x['proof'].get('native_identity')]
    all_native = _base.unique_identities(existing + new)
    require(len(new) == 89 and len(all_native) == 2297, 'Native witness count differs')
    require({tuple(sorted(x.items())) for x in all_native} == {tuple(sorted(identity(x).items())) for x in base['ordinary_native_identities']},
            'Native identity pair not exactly in admitted F membership')
    for key in ('request_id_hash', 'session_id_hash'):
        require(not {x[key] for x in all_native} & {x[key] for x in base['historical_excluded_native_identities']}, 'Excluded identity became an extra accepted vote')
    require(next(x for x in joined if x['ordinal'] == 70)['proof']['native_identity'] is None, 'Ordinal70 manufactured native identity')
    return all_native


def build(source_root):
    inputs = Inputs(source_root)
    assets = {k: inputs.raw(*pin) for k, pin in PINS.items()}
    provenance, report, base, terminal, epoch = (json.loads(assets[k]) for k in ('provenance', 'report', 'ledger', 'terminal', 'epoch'))
    require(provenance['recipe_sha256'] == PINS['recipe'][1] and provenance['new_provider_calls'] == provenance['new_votes'] == 0, 'Discovery receipt differs')
    require(base['report_sha256'] == terminal['report_sha256'] == digest(report) and terminal['private_ledger_sha256'] == digest(base), 'Base F terminal/report/ledger binding differs')
    collection = json.loads(assets['train'])['freeze']['admission']['record']['collection_record']
    require(digest(collection) == report['embedded_collection_sha256'], 'Train/base collection projection differs')
    for field in ('old_execution_inventory', 'old_prefix_run_inventory'):
        require(digest(epoch[field]) == epoch[field + '_sha256'], 'Epoch inventory commitment differs')
    slots = {x['ordinal']: x for x in base['positions']}
    joined = []
    execution_root, prefix_root = locator(epoch['old_execution_root']), locator(epoch['old_prefix_run_root'])
    for row in collection['rows'][:3]:
        root = execution_root + '/runs/' + row['pass_id']
        prefix = 'runs/' + row['pass_id'] + '/'
        inventory = {k[len(prefix):]: v for k, v in epoch['old_execution_inventory'].items() if k.startswith(prefix)}
        joined.extend(join_prefix_run(inputs, root, inventory, row, slots, list(enumerate(row['ordinals'], 1)), row['replay_input_commitments']))
    row = collection['rows'][3]
    commits = row['replay_input_commitments']
    joined.extend(join_prefix_run(inputs, prefix_root, epoch['old_prefix_run_inventory'], row, slots,
                                 [(b, 69 + b) for b in range(1, 12)],
                                 {'run_manifest_sha256': commits['prefix_run_manifest_sha256'], 'checkpoint_head_sha256': commits['prefix_checkpoint_head_sha256']}, True))
    recovered_pin = epoch['recovered_study_manifest']
    recovered = json.loads(inputs.raw(locator(recovered_pin['path']), recovered_pin['sha256'], recovered_pin['bytes']))
    require(recovered['logical_request_ordinal'] == 70 and recovered['native_identity_claimed'] is False
            and recovered['provider_calls'] == 0 and recovered['resend_authority'] is False
            and recovered_pin['sha256'] == commits['recovered_manifest_sha256'], 'Ordinal70 adoption/no-resend binding differs')
    next(x for x in joined if x['ordinal'] == 70)['proof'].update({'adoption_manifest_sha256': recovered_pin['sha256'],
                                                               'provider_calls': 0, 'resend_authority': False})
    terminal_pins = {x['ordinal']: x for x in commits['terminals']}
    for ordinal in [*range(81, 88), 89, 90, 91]:
        pin = terminal_pins[ordinal]
        raw = inputs.raw(EPOCH + f'/attempts/request-{ordinal:04d}/terminal.json', pin['terminal_sha256'])
        value = json.loads(raw)
        slot = slots[ordinal]
        require(value['ordinal'] == ordinal and value['status'] == 'completed' and value['epoch_sha256'] == PINS['epoch'][1], 'Old-v5 terminal condition differs')
        require(states(value['verdicts'], slot['question_ids']) == slot['leaves'] and digest(value['verdicts']) == value['verdicts_sha256'], 'Old-v5 normalization differs')
        response = value['raw_response'].encode('utf-8')
        require(sha(response) == value['raw_response_sha256'] and states(content(value['raw_response'])['verdicts'], slot['question_ids']) == slot['leaves'], 'Old-v5 raw state projection differs')
        root = EPOCH + '/passes/' + row['pass_id'] + f'/requests/request-{ordinal:04d}'
        provider = value['provider_metadata']
        require(digest(provider) == value['provider_metadata_sha256'], 'Old-v5 provider metadata commitment differs')
        raws = {key: inventory_file(inputs, root, value['provider_evidence_inventory'], descriptor['path'], descriptor)
                for key, descriptor in provider['provider_artifacts'].items()}
        schema_pin = {'path': f'responses/schemas/batch-{ordinal - 69:04d}.json', 'sha256': slot['schema_sha256']}
        schema = inventory_file(inputs, prefix_root, epoch['old_prefix_run_inventory'], schema_pin['path'], schema_pin)
        proof = validate_native(raws, provider, slot, schema, batch=ordinal - 69)
        proof.update({'terminal_sha256': sha(raw), 'disposition': 'retained_old_v5_native_state_join'})
        joined.append({'ordinal': ordinal, 'pass_id_sha256': slot['pass_id_sha256'], 'source_sha256': slot['source_sha256'],
                       'historical_replay_input_commitments_sha256': slot['historical_replay_input_commitments_sha256'],
                       'question_ids': slot['question_ids'], 'leaves': slot['leaves'], 'proof': proof})
    all_native = membership(base, joined)
    artifacts = sorted(inputs.artifacts.values(), key=lambda x: x['source_locator'])
    summary = {'schema_version': 1, 'scope': 'retained_native_prefix_descendant_v1', 'base_report_sha256': digest(report),
               'base_private_ledger_sha256': digest(base), 'implementation_sha256': sha(Path(__file__).read_bytes()),
               'recipe_source_sha256': PINS['recipe'][1], 'provider_calls_made': 0, 'new_votes_added': 0,
               'observed': {'existing_positions_joined': 90, 'native_prefix_positions': 79, 'native_old_v5_positions': 10,
                            'nonnative_adopted_positions': 1, 'ordered_native_leaves': sum(len(x['leaves']) for x in joined if x['ordinal'] != 70),
                            'ordered_adopted_leaves': len(slots[70]['leaves']), 'total_native_witnesses_after_join': len(all_native),
                            'total_positions_unchanged': len(base['positions']), 'total_leaves_unchanged': report['observed']['criterion_leaves'],
                            'historical_exclusions_unchanged': len(base['historical_excluded_native_identities']), 'remaining_static_position_joins': 0},
               'verified_artifact_count': len(artifacts), 'verified_artifact_index_sha256': digest(artifacts), 'prefix_join_sha256': digest(joined),
               'limitations': ['Separate descendant; published Census F files and output remain immutable',
                              'Exact retained identity/state bindings do not establish modern native attestation, provider/model/runtime provenance or full physical-contact dispositions',
                              'Historical evidence/quote normalization is not reexecuted; full modern semantic admission and score replay remain unverified',
                              'Ordinal70 is an adopted nonnative projection; no fabricated request identity, new contact, vote or independent work',
                              'Discovery previously displayed model verdict/recovery text; this lineage is not claimed outcome-blind; no human labels or semantic authority used']}
    private = {'schema_version': 1, 'private_task_local_only': True, 'report_sha256': digest(summary), 'positions': joined, 'artifacts': artifacts}
    return summary, private, assets, (execution_root, prefix_root)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--output-root', type=Path, required=True)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    source, output = args.source_root.resolve(), args.output_root.resolve()
    require(not output.exists() and not output.is_relative_to(REPOSITORY) and not REPOSITORY.is_relative_to(output), 'Output must be fresh outside repository')
    epoch = json.loads(Inputs(source).raw(*PINS['epoch']))
    roots = [source / root for root in (BASE, DISCOVERY, EPOCH, locator(epoch['old_execution_root']), locator(epoch['old_prefix_run_root']))]
    require(all(not output.is_relative_to(root) and not root.is_relative_to(output) for root in roots), 'Output overlaps retained prefix inputs')
    if not args.dry_run:
        output.mkdir(parents=True, exist_ok=False)
        with (output / 'join_prefix.py').open('xb') as handle:
            handle.write(Path(__file__).read_bytes())
        _base.write(output / 'invocation.json', {'scope': 'retained_native_prefix_descendant_v1', 'source_root': str(source), 'input_pins': PINS,
                    'implementation_sha256': sha(Path(__file__).read_bytes()), 'provider_calls_made': 0})
    try:
        report, ledger, assets, _ = build(source)
        if not args.dry_run:
            for key in ('recipe', 'provenance'):
                with (output / ('recipe.txt' if key == 'recipe' else 'discovery-provenance.json')).open('xb') as handle:
                    handle.write(assets[key])
            _base.write(output / 'census.json', report)
            _base.write(output / 'private-slots.json', ledger)
            _base.write(output / 'terminal.json', {'state': 'completed_provider_free_prefix_join', 'report_sha256': digest(report), 'private_ledger_sha256': digest(ledger)})
        print(json.dumps({'dry_run': args.dry_run, 'observed': report['observed'], 'verified_artifact_count': report['verified_artifact_count'],
                          'report_sha256': digest(report), 'private_ledger_sha256': digest(ledger)}, sort_keys=True))
        return 0
    except (OSError, ValueError, KeyError, TypeError) as error:
        if not args.dry_run:
            _base.write(output / 'terminal.json', {'state': 'failed_prefix_join_pending', 'error_class': type(error).__name__})
        parser.exit(1, f'F prefix pending: {type(error).__name__}: {error}\n')


if __name__ == '__main__':
    raise SystemExit(main())
