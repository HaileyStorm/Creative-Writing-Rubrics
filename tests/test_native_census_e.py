from __future__ import annotations

import gzip
import importlib.util
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('native_census_e', ROOT / 'evaluation-results/hbq-census-native-e-v1/census.py')
census = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(census)


def put(root, name, value, raw=False):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    data = value if raw else census.pretty(value)
    path.write_bytes(data)
    return [name, census.sha(data), len(data)]


def response(result, identity, config_hash='configuration', prompt_hash='prompt', schema_hash='schema'):
    content = json.dumps(result)
    return {'format_version': 1, 'config_sha256': config_hash, 'prompt_sha256': prompt_hash,
            'schema_sha256': schema_hash, 'content': content, 'content_sha256': census.sha(content.encode()),
            'result_sha256': census.sha(census.pretty(result)),
            'provider': {'reported': {'session_id': identity}}}


def fixture(tmp_path):
    prefix = str(tmp_path).replace('\\', '/')
    original = prefix + '/original'
    schema = {'type': 'object', 'properties': {'value': {'type': 'integer'}}, 'required': ['value']}
    schema_path = 'evaluation-results/hbq-multisample-repeatability-v1/fixture.schema.json'
    schema_pin = put(tmp_path, 'repository/' + schema_path, schema)
    source_pins = {}
    for name in ('source.md', 'prompt.md', 'task-contract.json'):
        pin = put(tmp_path, 'original/inputs/item/' + name, b'private-source' if name != 'task-contract.json' else b'{}', raw=True)
        source_pins[name] = {'bytes': pin[2], 'sha256': pin[1], 'path': name}
    schedule = [{'item_id': 'item', 'arm_id': 'arm', 'repetition': 1, 'position': 1}]
    frozen = {'study_id': 'study', 'schedule': schedule, 'schedule_sha256': census.digest(schedule),
              'samples': [{'item_id': 'item', 'inputs': source_pins}],
              'runtime_files': [{'path': schema_path, 'sha256': schema_pin[1], 'bytes': schema_pin[2]}],
              'contract': {'arms': [{'arm_id': 'arm', 'kind': 'native', 'schema': 'fixture.schema.json'}]}}
    frozen_pin = put(tmp_path, 'original/frozen-run-contract.json', frozen)
    base = 'original/runs/item/arm/run-01'
    prompt = b'private-prompt'
    config = {'name': 'item-arm-run-01', 'provider': 'codex', 'model': 'model', 'reasoning': 'high',
              'prompt_sha256': census.sha(prompt), 'schema_sha256': census.sha(census.pretty(schema))}
    manifest = {'format_version': 1, 'configuration': config, 'config_sha256': census.sha(census.pretty(config))}
    manifest_pin = put(tmp_path, base + '/pass.json', manifest)
    result = {'value': 1}
    record = response(result, 'accepted', manifest['config_sha256'], config['prompt_sha256'], config['schema_sha256'])
    response_pin = put(tmp_path, base + '/response.json', record)
    put(tmp_path, base + '/result.json', result)
    put(tmp_path, base + '/request.prompt.txt.gz', gzip.compress(prompt), raw=True)
    put(tmp_path, base + '/response.schema.json', schema)
    cell = {'sequence': 1, 'item_id': 'item', 'arm_id': 'arm', 'repetition': 1, 'source_kind': 'original',
            'source_root': original, 'run_binding_path': prefix + '/' + manifest_pin[0],
            'run_binding_sha256': manifest_pin[1], 'session_ids': ['accepted'], 'artifact_commitments': [response_pin[1]]}
    historical = {'source_record_count': 1, 'session_id_record_count': 1, 'unique_observed_session_count': 1,
                  'unavailable_record_count': 0, 'artifact_commitment_count': 1,
                  'observed_session_sha256': census.sha(b'accepted'), 'artifact_commitments_sha256': census.sha(response_pin[1].encode())}
    failed_base = 'original/failed'
    failed_files = []
    for n in range(1, 4):
        name = f'attempts/rejected-{n:04d}.json'
        p = put(tmp_path, failed_base + '/' + name, {'format_version': 1, 'reason': 'private-rationale',
            'response': response(result, f'failed-{n}'), 'result': result})
        failed_files.append({'path': name, 'bytes': p[2], 'sha256': p[1]})
    provenance = {'study_id': 'study', 'cells': [cell], 'source_kind_counts': {'original': 1},
                  'frozen_contract': {'sha256': frozen_pin[1]}}
    assets = {'frozen': frozen_pin, 'provenance': put(tmp_path, 'consolidation/provenance.json', provenance),
              'summary': put(tmp_path, 'consolidation/summary.json', {'study_id': 'study', 'fresh_session_commitment': historical}),
              'predecessor': put(tmp_path, 'successor/predecessor.json', {'frozen_contract_sha256': frozen_pin[1],
                  'sequence77_failure': {'accepted': False, 'artifact_list': {'files': failed_files}}}),
              'unresolved': put(tmp_path, 'unresolved/claim.json', {'pid': 0})}
    recipe = {'scope': 'fixture', 'common_census_sha256': census.sha(census.COMMON_PATH.read_bytes()),
              'source_path_prefix': prefix, 'original_root': original, 'repository_root': prefix + '/repository',
              'assets': assets, 'source_kind_counts': {'original': 1}, 'reported_model': 'model', 'reported_reasoning': 'high',
              'rejected_sequences': [], 'physical_retry_sequences': [], 'failed_prefix_root': failed_base,
              'unresolved': [{'scope': 'missing-terminal', 'asset': 'unresolved'}],
              'expected_counts': {'accepted_logical_cells': 1, 'accepted_units': 1, 'rejected_attempts': 3,
                                  'unique_observed_sessions_bounded_lineage': 4},
              'input_roots': [original, prefix + '/consolidation', prefix + '/successor', prefix + '/unresolved']}
    return recipe


def test_native_join_preserves_failed_prefix_and_unresolved_scope_without_votes_or_text(tmp_path):
    recipe = fixture(tmp_path)
    report, ledger = census.build_census(tmp_path, recipe)
    assert report['observed']['accepted_logical_cells'] == report['observed']['accepted_units'] == 1
    assert report['observed']['rejected_attempts'] == 3
    assert report['observed']['unique_observed_sessions_bounded_lineage'] == 4
    assert report['observed']['historical_analysis_projection']['source_record_count'] == 1
    assert report['observed']['physical_provider_contact_count'] is None
    assert report['unresolved_dispositions'][0]['provider_contact_count'] is None
    assert all(not a['accepted'] and not a['leaves'] for a in ledger['failed_prefix_attempts'])
    assert 'private-source' not in json.dumps(ledger)
    assert 'private-prompt' not in json.dumps(report)
    assert 'private-rationale' not in json.dumps(ledger)


@pytest.mark.parametrize('failure', ['missing_manifest', 'changed_source', 'changed_result', 'wrong_schedule', 'wrong_projection'])
def test_missing_or_changed_pins_and_identity_cannot_silently_reduce_denominator(tmp_path, failure):
    recipe = fixture(tmp_path)
    if failure == 'missing_manifest':
        (tmp_path / 'original/runs/item/arm/run-01/pass.json').unlink()
    elif failure == 'changed_source':
        (tmp_path / 'original/inputs/item/source.md').write_bytes(b'changed')
    elif failure == 'changed_result':
        put(tmp_path, 'original/runs/item/arm/run-01/result.json', {'value': 2})
    else:
        p = tmp_path / recipe['assets']['provenance'][0]
        d = json.loads(p.read_bytes())
        if failure == 'wrong_schedule':
            d['cells'][0]['repetition'] = 2
        else:
            d['cells'][0]['artifact_commitments'] = ['wrong']
        recipe['assets']['provenance'] = put(tmp_path, recipe['assets']['provenance'][0], d)
    with pytest.raises(ValueError):
        census.build_census(tmp_path, recipe)


def test_adoption_is_one_cell_and_duplicate_adoption_fails():
    event = {'item_id': 'item', 'arm_id': 'arm', 'repetition': 1}
    cell = {**event, 'sequence': 1, 'source_kind': 'adopted'}
    census.validate_cells([cell], [event], 'study')
    with pytest.raises(ValueError, match='Duplicate'):
        census.validate_cells([cell, cell], [event, event], 'study')


def test_retry_messages_do_not_become_sessions_or_accepted_units():
    accepted = {'reported_session_sha256': 'accepted'}
    rejected = {'reported_session_sha256': 'rejected', 'accepted': False, 'leaves': [],
                'physical_messages': [{'sha256': 'message1'}, {'sha256': 'message2'}]}
    cell = {'kind': 'native', 'source_kind': 'adopted', 'accepted_units': [accepted], 'rejected_attempts': [rejected], 'leaves': []}
    result = census.aggregate([cell], [], [], {'source_record_count': 2, 'artifact_commitment_count': 4})
    assert result['accepted_units'] == 1 and result['rejected_attempts'] == 1
    assert result['retry_physical_message_commitments'] == result['unique_observed_sessions_bounded_lineage'] == 2
    assert result['physical_provider_contact_count'] is None
    with pytest.raises(ValueError, match='Duplicate reported session'):
        census.aggregate([cell, cell], [], [], {})


def test_retry_archive_embedded_rejection_and_two_physical_messages_reproduce_projection(tmp_path):
    recipe = fixture(tmp_path)
    base = 'original/runs/item/arm/run-01'
    manifest = json.loads((tmp_path / base / 'pass.json').read_bytes())
    accepted_result = {'value': 1}
    rejected_result = {'value': 2}
    rejected_response = response(rejected_result, 'retry-first', manifest['config_sha256'],
                                 manifest['configuration']['prompt_sha256'], manifest['configuration']['schema_sha256'])
    rejected_pin = put(tmp_path, base + '/attempts/rejected-0001.json', {'format_version': 1,
        'reason': 'private-semantic-rejection', 'response': rejected_response, 'result': rejected_result})
    for name in ('pass.json', 'request.prompt.txt.gz', 'response.schema.json'):
        put(tmp_path, base + '/retry-attempts/attempt-0001/' + name, (tmp_path / base / name).read_bytes(), raw=True)
    first = put(tmp_path, base + '/responses/batch-0001.attempt-0001.message.json', rejected_result)
    second = put(tmp_path, base + '/retry-attempts/attempt-0002/responses/batch-0001.attempt-0001.message.json', accepted_result)
    recipe['rejected_sequences'] = recipe['physical_retry_sequences'] = [1]
    path = recipe['assets']['provenance'][0]
    provenance = json.loads((tmp_path / path).read_bytes())
    c = provenance['cells'][0]
    c['session_ids'].append('retry-first')
    c['artifact_commitments'].extend([rejected_pin[1], first[1], second[1]])
    recipe['assets']['provenance'] = put(tmp_path, path, provenance)
    path = recipe['assets']['summary'][0]
    summary = json.loads((tmp_path / path).read_bytes())
    h = summary['fresh_session_commitment']
    h.update(source_record_count=2, session_id_record_count=2, unique_observed_session_count=2,
             artifact_commitment_count=4, observed_session_sha256=census.sha(b'accepted\nretry-first'),
             artifact_commitments_sha256=census.sha('\n'.join(sorted(c['artifact_commitments'])).encode()))
    recipe['assets']['summary'] = put(tmp_path, path, summary)
    recipe['expected_counts'].update(rejected_attempts=4, unique_observed_sessions_bounded_lineage=5)
    report, _ = census.build_census(tmp_path, recipe)
    assert report['observed']['accepted_units'] == 1
    assert report['observed']['retry_physical_message_commitments'] == 2
    assert report['observed']['historical_analysis_projection']['artifact_commitment_count'] == 4
    put(tmp_path, base + '/retry-attempts/attempt-0002/responses/batch-0001.attempt-0001.message.json', rejected_result)
    with pytest.raises(ValueError, match='physical message differs'):
        census.build_census(tmp_path, recipe)


def hbq_fixture(tmp_path):
    ids = ['leaf1', 'leaf2']
    sample = {'item_id': 'item', 'question_count': 2, 'question_id_sequence_sha256': census.digest(ids),
              'inputs': {name: {'sha256': name, 'bytes': 1} for name in ('source.md', 'prompt.md', 'task-contract.json')}}
    arm = {'bundle_id': 'bundle', 'batch_size': 1, 'question_count': 2}
    config = {'artifact_id': 'item', 'bundle_id': 'bundle', 'question_ids': ids, 'batch_size': 1, 'strict_ai': True,
              'retry_semantics': 'cumulative_batch_attempts_v1', 'evidence_normalization_policy': 'normalization',
              'validation_feedback_policy': 'feedback', 'compiled_bundle_sha256': 'bundle-pin', 'questions_sha256': 'questions-pin',
              'artifact': sample['inputs']['source.md'], 'task_contract': sample['inputs']['task-contract.json'],
              'contexts': [sample['inputs']['prompt.md']]}
    manifest = {'format_version': 3, 'configuration': config, 'config_sha256': census.sha(census.pretty(config))}
    put(tmp_path, 'run/response.schema.json', {'type': 'object'})
    values = []
    previous = None
    for number, state in enumerate(['CANNOT_ASSESS', 'NOT_APPLICABLE'], 1):
        native = {'question_id': ids[number - 1], 'verdict': state, 'note': 'private-note'}
        value = {**native, 'artifact_id': 'item', 'bundle_id': 'bundle'}
        values.append(value)
        response_pin = put(tmp_path, f'run/responses/accepted-{number}.json', {'verdicts': [native]})
        checkpoint = {'format_version': 4, 'batch': number, 'question_ids': [ids[number - 1]],
            'previous_checkpoint_sha256': previous, 'accepted_attempt': 1, 'rejected_chain': {'count': 0, 'head_sha256': None},
            'normalization_policy': 'normalization', 'validation_feedback_policy': 'feedback',
            'response_artifact': {'path': f'responses/accepted-{number}.json', 'sha256': response_pin[1], 'bytes': response_pin[2]},
            'response_sha256': response_pin[1], 'normalized_verdicts': [value], 'verdicts_sha256': census.sha(census.verdict_bytes(values)),
            'normalization_audit': [], 'prompt_sha256': 'prompt', 'base_prompt_sha256': 'base', 'effective_prompt_sha256': 'effective',
            'provider': {'reported': {'session_id': f'batch-{number}'}}}
        previous = put(tmp_path, f'run/responses/batch-{number:04d}.json', checkpoint)[1]
    put(tmp_path, 'run/verdicts.jsonl', census.verdict_bytes(values), raw=True)
    return manifest, sample, arm


def test_hbq_preserves_four_state_order_and_cumulative_checkpoint_chain(tmp_path):
    manifest, sample, arm = hbq_fixture(tmp_path)
    leaves, units, _, _, _, _ = census.project_hbq(census.Inputs(tmp_path), 'run', manifest, sample, arm)
    assert [v['verdict'] for v in leaves] == ['CANNOT_ASSESS', 'NOT_APPLICABLE']
    assert len(units) == 2 and 'private-note' not in json.dumps(leaves)
    p = tmp_path / 'run/responses/batch-0002.json'
    checkpoint = json.loads(p.read_bytes())
    checkpoint['previous_checkpoint_sha256'] = 'wrong'
    put(tmp_path, 'run/responses/batch-0002.json', checkpoint)
    with pytest.raises(ValueError, match='chain'):
        census.project_hbq(census.Inputs(tmp_path), 'run', manifest, sample, arm)


def test_raw_order_is_preserved_when_checkpoint_reorders_by_exact_leaf_identity(tmp_path):
    manifest, sample, arm = hbq_fixture(tmp_path)
    manifest['configuration']['batch_size'] = arm['batch_size'] = 2
    manifest['config_sha256'] = census.sha(census.pretty(manifest['configuration']))
    first = json.loads((tmp_path / 'run/responses/batch-0001.json').read_bytes())
    second = json.loads((tmp_path / 'run/responses/batch-0002.json').read_bytes())
    native1 = json.loads((tmp_path / 'run/responses/accepted-1.json').read_bytes())['verdicts'][0]
    native2 = json.loads((tmp_path / 'run/responses/accepted-2.json').read_bytes())['verdicts'][0]
    pin = put(tmp_path, 'run/responses/accepted-1.json', {'verdicts': [native2, native1]})
    first.update(question_ids=['leaf1', 'leaf2'], normalized_verdicts=first['normalized_verdicts'] + second['normalized_verdicts'],
                 response_sha256=pin[1], verdicts_sha256=second['verdicts_sha256'])
    first['response_artifact'].update(sha256=pin[1], bytes=pin[2])
    put(tmp_path, 'run/responses/batch-0001.json', first)
    (tmp_path / 'run/responses/batch-0002.json').unlink()
    leaves, units, _, _, _, _ = census.project_hbq(census.Inputs(tmp_path), 'run', manifest, sample, arm)
    assert [v['native_batch_position'] for v in leaves] == [1, 0]
    assert units[0]['native_order_differs'] is True
    native2['verdict'] = 'YES'
    pin = put(tmp_path, 'run/responses/accepted-1.json', {'verdicts': [native2, native1]})
    first['response_artifact'].update(sha256=pin[1], bytes=pin[2])
    first['response_sha256'] = pin[1]
    put(tmp_path, 'run/responses/batch-0001.json', first)
    with pytest.raises(ValueError, match='leaf states differ'):
        census.project_hbq(census.Inputs(tmp_path), 'run', manifest, sample, arm)


def test_changed_historical_static_schema_is_explicit_without_erasing_pinned_native_leaves(tmp_path):
    manifest, sample, arm = hbq_fixture(tmp_path)
    pin = put(tmp_path, 'repository/old-schema.json', {'type': 'object'})
    manifest['configuration']['prompts'] = []
    manifest['configuration']['response_schema'] = {'path': str(tmp_path / pin[0]), 'sha256': pin[1], 'bytes': pin[2]}
    manifest['config_sha256'] = census.sha(census.pretty(manifest['configuration']))
    put(tmp_path, 'repository/old-schema.json', {'type': 'string'})
    leaves, _, _, _, _, proof = census.project_hbq(census.Inputs(tmp_path), 'run', manifest, sample, arm,
        recipe={'source_path_prefix': str(tmp_path)})
    assert len(leaves) == 2
    reference = proof['historical_static_references'][0]
    assert reference['disposition'] == 'historical_locator_changed'
    assert reference['expected_sha256'] == pin[1] != reference['observed_sha256']
    assert proof['normalization_reexecution'] is False


def test_dry_run_creates_nothing_and_fresh_output_preserves_existing_receipts(tmp_path, monkeypatch, capsys):
    source = tmp_path / 'source'
    source.mkdir()
    recipe = fixture(source)
    here = tmp_path / 'code'
    put(here, 'recipe.json', recipe)
    monkeypatch.setattr(census, 'HERE', here)
    output = tmp_path / 'output'
    monkeypatch.setattr(sys, 'argv', ['census.py', '--source-root', str(source), '--output-root', str(output), '--dry-run'])
    assert census.main() == 0 and not output.exists()
    assert json.loads(capsys.readouterr().out)['dry_run'] is True
    output.mkdir()
    (output / 'terminal.json').write_bytes(b'original-receipt')
    with pytest.raises(ValueError, match='fresh'):
        census.main()
    assert (output / 'terminal.json').read_bytes() == b'original-receipt'


def test_failed_actual_fixture_retains_immutable_invocation_and_pending_terminal(tmp_path, monkeypatch):
    source = tmp_path / 'source'
    source.mkdir()
    recipe = fixture(source)
    here = tmp_path / 'code'
    put(here, 'recipe.json', recipe)
    monkeypatch.setattr(census, 'HERE', here)
    output = tmp_path / 'output'
    (source / 'original/runs/item/arm/run-01/result.json').unlink()
    monkeypatch.setattr(sys, 'argv', ['census.py', '--source-root', str(source), '--output-root', str(output)])
    with pytest.raises(SystemExit) as failure:
        census.main()
    assert failure.value.code == 1
    assert json.loads((output / 'terminal.json').read_bytes())['state'] == 'failed_join_pending'
    assert json.loads((output / 'invocation.json').read_bytes())['provider_calls_made'] == 0
    assert not (output / 'census.json').exists()
