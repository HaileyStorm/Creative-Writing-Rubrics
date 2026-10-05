import copy
import importlib.util
import json
from pathlib import Path

import pytest

PATH = Path(__file__).resolve().parents[1] / 'evaluation-results/hbq-census-native-f-v1/census.py'
spec = importlib.util.spec_from_file_location('native_census_f_test', PATH)
census = importlib.util.module_from_spec(spec)
spec.loader.exec_module(census)


def put(root, relative, value):
    raw = census.canonical(value)
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return {'path': 'C:/fixture/' + relative, 'sha256': census.sha(raw)}


def terminal_fixture(tmp_path):
    native = {'request_id_hash': 'a' * 64, 'session_id_hash': 'b' * 64}
    leaves = [{'question_id': 'q1', 'verdict': 'CANNOT_ASSESS'}, {'question_id': 'q2', 'verdict': 'NOT_APPLICABLE'}]
    output = {'verdicts': [{**x, 'note': 'private rationale'} for x in leaves]}
    terminal = {'ordinal': 1, 'state': 'completed', 'native_identity': native, 'native_envelope_sha256': 'c' * 64,
                'candidate_result': {'output': output, 'native_envelope_artifact': {'sha256': 'c' * 64}},
                'verdicts': output['verdicts']}
    pin = put(tmp_path, 'owner/attempts/request-0001/terminal.json', terminal)
    return terminal, {'root': 'C:/fixture/owner', 'native_identity': dict(native), 'native_envelope_sha256': 'c' * 64}, {'ordinal': 1, 'terminal_sha256': pin['sha256']}, leaves


def test_native_raw_states_preserve_uncertainty_and_ignore_rationale(tmp_path):
    terminal, owner, pin, leaves = terminal_fixture(tmp_path)
    proof = census.native_terminal(census.Inputs(tmp_path), owner, pin, ['q1', 'q2'], leaves, {'source_path_prefix': 'C:/fixture'})
    assert proof['raw_states_sha256'] == census.digest(leaves)
    terminal['candidate_result']['output']['verdicts'][0]['note'] = 'changed private rationale'
    pin['terminal_sha256'] = put(tmp_path, 'owner/attempts/request-0001/terminal.json', terminal)['sha256']
    changed = census.native_terminal(census.Inputs(tmp_path), owner, pin, ['q1', 'q2'], leaves, {'source_path_prefix': 'C:/fixture'})
    assert changed['raw_states_sha256'] == proof['raw_states_sha256']
    assert changed['terminal_sha256'] != proof['terminal_sha256']


@pytest.mark.parametrize('change', ['order', 'state', 'identity', 'pin'])
def test_native_source_and_normalization_errors_fail(tmp_path, change):
    terminal, owner, pin, leaves = terminal_fixture(tmp_path)
    if change == 'order':
        terminal['candidate_result']['output']['verdicts'].reverse()
    elif change == 'state':
        terminal['candidate_result']['output']['verdicts'][0]['verdict'] = 'NO'
    elif change == 'identity':
        terminal['native_identity']['session_id_hash'] = 'd' * 64
    if change != 'pin':
        pin['terminal_sha256'] = put(tmp_path, 'owner/attempts/request-0001/terminal.json', terminal)['sha256']
    else:
        pin['terminal_sha256'] = 'f' * 64
    with pytest.raises(ValueError):
        census.native_terminal(census.Inputs(tmp_path), owner, pin, ['q1', 'q2'], leaves, {'source_path_prefix': 'C:/fixture'})


def test_adopted_recovery_has_one_state_projection_and_no_extra_vote(tmp_path):
    leaves = [{'question_id': 'q', 'verdict': 'YES'}]
    pins = {k: put(tmp_path, k + '.json', {'verdicts': leaves} if k == 'local_projection' else {'receipt': k})
            for k in ('adoption', 'local_projection', 'proposal', 'independent_review', 'standing_authority')}
    collection = {'local_recovery_protected_paths': pins, 'local_recovery_identity': {'ordinal': 254, 'projection_sha256': pins['local_projection']['sha256']},
                  'local_recovery_provenance': {'ordinary_native_admission': False, 'new_provider_attempts_authorized': 0}}
    proof = census.adopted_projection(census.Inputs(tmp_path), collection, 254, ['q'], leaves, {'source_path_prefix': 'C:/fixture'})
    assert proof['new_votes_added'] == 0 and proof['ordinary_native_admission'] is False
    assert proof['raw_states_sha256'] == census.digest(leaves)
    collection['local_recovery_provenance']['new_provider_attempts_authorized'] = 1
    with pytest.raises(ValueError):
        census.adopted_projection(census.Inputs(tmp_path), collection, 254, ['q'], leaves, {'source_path_prefix': 'C:/fixture'})


def test_native_runtime_recovery_preserves_ambiguous_original_and_adds_no_contact(tmp_path):
    terminal, owner, pin, leaves = terminal_fixture(tmp_path)
    terminal['state'] = 'ambiguous'
    terminal.pop('verdicts')
    original = put(tmp_path, 'owner/attempts/request-0001/terminal.json', terminal)
    pin['terminal_sha256'] = original['sha256']
    record = {'ordinal': 1, 'verdicts': leaves, 'native_identity': terminal['native_identity'],
              'native_envelope': terminal['candidate_result']['native_envelope_artifact'], 'original_terminal': original,
              'original_terminal_state': 'ambiguous', 'provider_calls_made': 0, 'automatic_resend_authorized': False,
              'original_evidence_modified': False}
    owner.update({'kind': 'standing_v6_runtime_data_recovered_native', 'original_terminal': original,
                  'recovery_adoption': {'decision': 'approved_native_279_runtime_data_recovery', 'automatic_resend_authorized': False,
                                        'recovery_record': put(tmp_path, 'recovery.json', record)}})
    proof = census.native_terminal(census.Inputs(tmp_path), owner, pin, ['q1', 'q2'], leaves, {'source_path_prefix': 'C:/fixture'})
    assert proof['original_terminal_state'] == 'ambiguous'
    assert proof['runtime_data_recovery_sha256'] == census.digest(record)
    assert proof['native_identity'] == owner['native_identity']
    record['provider_calls_made'] = 1
    owner['recovery_adoption']['recovery_record'] = put(tmp_path, 'recovery.json', record)
    with pytest.raises(ValueError):
        census.native_terminal(census.Inputs(tmp_path), owner, pin, ['q1', 'q2'], leaves, {'source_path_prefix': 'C:/fixture'})


def static_fixture(tmp_path):
    native = [{'request_id_hash': 'a' * 64, 'session_id_hash': 'b' * 64}]
    excluded = [{'request_id_hash': 'c' * 64, 'session_id_hash': 'd' * 64}]
    leaves = [{'question_id': 'q', 'verdict': 'NO'}]
    source = b'private source'
    (tmp_path / 'plan').mkdir()
    (tmp_path / 'plan/source.txt').write_bytes(source)
    for name in ('prompt', 'schema'):
        (tmp_path / ('plan/' + name)).write_bytes(name.encode())
    row = {'pass_id': 'p', 'opaque_story_id': 's', 'partition': 'TRAIN', 'ordinals': [70], 'source': {'bytes': len(source), 'sha256': census.sha(source)},
           'verdict_rows': leaves, 'verdicts_sha256': census.digest(leaves), 'provenance': {'kind': 'historical_replacement'}, 'replay_input_commitments': {'prefix': 'e' * 64}}
    collection = {'native_identities': native, 'historical_excluded_native_identities': excluded, 'native_identity_commitment_sha256': census.digest(native),
                  'recovered_ordinals': [70], 'rows': [row], 'root_chain_ordinal_owners': {}, 'normalized_verdict_rows': [{'pass_id': 'p', 'opaque_story_id': 's', **leaves[0]}],
                  'parallel_source_epoch': {'retained_parallel_prefixes': []}, 'coverage_failures': []}
    schedule = {'selected_passes': [{'pass_id': 'p', 'partition': 'TRAIN', 'logical_sample_id': 'l', 'request_ordinals': [70]}], 'selected_request_ordinals': [70], 'question_ids': ['q']}
    request = {'ordinal': 70, 'pass_id': 'p', 'logical_sample_id': 'l', 'question_ids': ['q']}
    for name in ('prompt', 'schema'):
        request.update({name + '_path': name, name + '_bytes': len(name), name + '_sha256': census.sha(name.encode())})
    plan = {'passes': [{'pass_id': 'p', 'opaque_story_id': 's', 'partition': 'TRAIN', 'input_path': 'source.txt', 'source_bytes': len(source), 'source_sha256': census.sha(source)}], 'requests': [request]}
    recipe = {'native_identity_sha256': census.digest(native), 'recovered_ordinals': [70], 'plan_root': 'plan', 'expected_counts': {}}
    return collection, schedule, plan, recipe


def test_unjoined_prefix_is_pending_and_replaces_without_extra_vote(tmp_path):
    collection, schedule, plan, recipe = static_fixture(tmp_path)
    observed, ledger = census.project_collection(collection, schedule, plan, census.Inputs(tmp_path), recipe)
    assert observed['logical_positions'] == observed['criterion_leaves'] == 1
    assert observed['static_native_position_joins_pending'] == 1
    assert observed['adopted_projections_directly_joined'] == 0
    assert ledger['positions'][0]['recovered'] is True
    assert ledger['positions'][0]['proof'] is None
    assert ledger['historical_excluded_native_identities'] == collection['historical_excluded_native_identities']


@pytest.mark.parametrize('change', ['exclusion', 'duplicate_position', 'missing_source'])
def test_exclusion_reuse_duplicate_vote_and_missing_pin_fail(tmp_path, change):
    collection, schedule, plan, recipe = static_fixture(tmp_path)
    if change == 'exclusion':
        collection['historical_excluded_native_identities'] = copy.deepcopy(collection['native_identities'])
    elif change == 'duplicate_position':
        collection['rows'][0]['ordinals'].append(70)
        schedule['selected_passes'][0]['request_ordinals'].append(70)
    else:
        (tmp_path / 'plan/source.txt').unlink()
    with pytest.raises((ValueError, FileNotFoundError)):
        census.project_collection(collection, schedule, plan, census.Inputs(tmp_path), recipe)


def test_output_must_be_fresh_outside_inputs_even_for_dry_run(tmp_path):
    with pytest.raises(ValueError):
        census.check_output(tmp_path, tmp_path, {'input_roots': []})
    with pytest.raises(ValueError):
        census.check_output(tmp_path / 'input/new', tmp_path, {'input_roots': ['input']})
    census.check_output(tmp_path / 'fresh', tmp_path, {'input_roots': ['input']})


def test_output_guard_includes_roots_derived_from_pinned_record(tmp_path):
    collection = {'root_chain_ordinal_owners': {'1': {'root': 'C:/fixture/retained-owner'}},
                  'parallel_source_epoch': {'retained_parallel_prefixes': []},
                  'local_recovery_protected_paths': {},
                  'parallel_successor_protected_paths': {'receipt': {'path': 'C:/fixture/control/receipt.json', 'sha256': 'a' * 64}},
                  'runtime_data_protected_paths': {}}
    value = {'freeze': {'admission': {'record': {'collection_record': collection}}}}
    pin = put(tmp_path, 'train.json', value)
    recipe = {'input_roots': [], 'source_path_prefix': 'C:/fixture',
              'assets': {'train': {'locator': 'train.json', 'sha256': pin['sha256'], 'bytes': (tmp_path / 'train.json').stat().st_size}}}
    with pytest.raises(ValueError):
        census.check_output(tmp_path / 'retained-owner/new', tmp_path, recipe)
    census.check_output(tmp_path / 'fresh', tmp_path, recipe)
    census.check_output(tmp_path / 'control/fresh', tmp_path, recipe)
