"""Provider-free pinned Dryad Grok collection metadata and retained-terminal census."""
from __future__ import annotations

import argparse
from collections import Counter
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPOSITORY = HERE.parent.parent
COMMON_PATH = HERE.parent / 'hbq-evidence-census-pass-c-v1' / 'census.py'
_spec = importlib.util.spec_from_file_location('native_census_f_common', COMMON_PATH)
_common = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_common)
require, sha, canonical, digest, VERDICTS = (_common.require, _common.sha, _common.canonical, _common.digest, _common.VERDICTS)


class Inputs(_common.Inputs):
    def raw(self, locator, expected=None, size=None):
        path = self.path(locator)
        require(path.stat().st_size <= 32 * 1024 * 1024, 'Named census input exceeds bounded size')
        raw = path.read_bytes()
        require(expected is not None and sha(raw) == expected, 'Pinned source hash differs: ' + locator)
        require(size is None or len(raw) == size, 'Pinned source size differs: ' + locator)
        self.artifacts[locator] = {'source_locator': locator, 'source_sha256': sha(raw), 'source_bytes': len(raw)}
        return raw


def locator(path, recipe):
    prefix = recipe['source_path_prefix'].replace('\\', '/').rstrip('/') + '/'
    value = str(path).replace('\\', '/')
    require(value.startswith(prefix), 'Historical locator leaves pinned Documents prefix')
    return value[len(prefix):]


def read_pin(inputs, pin, recipe):
    return inputs.raw(locator(pin['path'], recipe), pin['sha256'], pin.get('bytes'))


def states(value, questions):
    require(isinstance(value, list) and len(value) == len(questions), 'Native leaf count differs')
    rows = [{'question_id': x['question_id'], 'verdict': x['verdict']} for x in value]
    require([x['question_id'] for x in rows] == questions, 'Native criterion order differs')
    require(all(x['verdict'] in VERDICTS for x in rows), 'Native four-state verdict differs')
    return rows


def identity(value):
    result = {k: value[k] for k in ('request_id_hash', 'session_id_hash')}
    require(all(isinstance(x, str) and len(x) == 64 and set(x) <= set('0123456789abcdef')
                for x in result.values()), 'Native identity hash differs')
    return result


def unique_identities(values):
    projected = [identity(x) for x in values]
    require(all(len({x[k] for x in projected}) == len(projected) for k in ('request_id_hash', 'session_id_hash')),
            'Duplicate native request/session identity')
    return projected


def native_terminal(inputs, owner, terminal_pin, questions, expected, recipe):
    original = owner.get('original_terminal')
    if isinstance(original, dict):
        require(original['sha256'] == terminal_pin['terminal_sha256'], 'Original terminal pin differs')
        path = locator(original['path'], recipe)
    else:
        path = locator(owner['root'], recipe) + f"/attempts/request-{terminal_pin['ordinal']:04d}/terminal.json"
    raw = inputs.raw(path, terminal_pin['terminal_sha256'])
    terminal = json.loads(raw)
    original_state = terminal.get('state', terminal.get('status'))
    recovery = None
    if owner.get('kind') == 'standing_v6_runtime_data_recovered_native':
        adoption = owner['recovery_adoption']
        require(adoption['decision'] == 'approved_native_279_runtime_data_recovery'
                and adoption['automatic_resend_authorized'] is False, 'Runtime data recovery adoption differs')
        recovery = json.loads(read_pin(inputs, adoption['recovery_record'], recipe))
        require(recovery['original_terminal'] == original and recovery['original_terminal_state'] == original_state
                and recovery['ordinal'] == terminal_pin['ordinal'] and recovery['provider_calls_made'] == 0
                and recovery['automatic_resend_authorized'] is False and recovery['original_evidence_modified'] is False,
                'Runtime recovery altered original disposition or authorizes a new contact')
    require(terminal.get('ordinal') == terminal_pin['ordinal'] and (original_state == 'completed' or recovery is not None),
            'Native terminal is not completed or explicitly recovered')
    retained = states((recovery or terminal)['verdicts'], questions)
    require(retained == expected, 'Retained terminal normalization differs from collection')
    raw_states = None
    result = terminal.get('candidate_result')
    if isinstance(result, dict):
        raw_states = states(result['output']['verdicts'], questions)
        descriptor = result['native_envelope_artifact']
        require(descriptor['sha256'] == terminal.get('native_envelope_sha256', descriptor['sha256'])
                and owner.get('native_envelope_sha256', descriptor['sha256']) == descriptor['sha256'],
                'Native envelope commitment differs')
        require(recovery is None or recovery['native_envelope'] == descriptor, 'Recovered native envelope descriptor differs')
    elif isinstance(terminal.get('raw_response'), str):
        response = terminal['raw_response']
        require(sha(response.encode('utf-8')) == terminal['raw_response_sha256'], 'Raw response commitment differs')
        parsed = response.strip()
        if parsed.startswith('```'):
            lines = parsed.splitlines()
            require(lines[-1] == '```', 'Unclosed retained response fence')
            parsed = '\n'.join(lines[1:-1])
        raw_states = states(json.loads(parsed)['verdicts'], questions)
    require(raw_states == retained, 'Raw/normalized four-state projection differs')
    value = terminal.get('native_identity')
    if value is None:
        metadata = terminal.get('provider_metadata', {})
        value = {'request_id_hash': metadata.get('request_id_sha256'), 'session_id_hash': metadata.get('session_id_sha256')}
    native = identity(value)
    require(owner.get('native_identity', native) == native, 'Owner native identity differs')
    require(recovery is None or identity(recovery['native_identity']) == native, 'Runtime recovery native identity differs')
    return {'terminal_sha256': sha(raw), 'raw_states_sha256': digest(raw_states),
            'normalized_states_sha256': digest(retained), 'native_identity': native,
            'native_envelope_sha256': result['native_envelope_artifact']['sha256'] if isinstance(result, dict) else None,
            'original_terminal_state': original_state, 'runtime_data_recovery_sha256': digest(recovery) if recovery is not None else None,
            'native_envelope_bytes_replayed': False}


def adopted_projection(inputs, collection, ordinal, questions, expected, recipe):
    if ordinal == 254:
        pins = collection['local_recovery_protected_paths']
        selected = {k: pins[k] for k in ('adoption', 'local_projection', 'proposal', 'independent_review', 'standing_authority')}
        projected_key = 'local_projection'
        adoption_identity = collection['local_recovery_identity']
        require(collection['local_recovery_provenance']['ordinary_native_admission'] is False
                and collection['local_recovery_provenance']['new_provider_attempts_authorized'] == 0,
                'Local recovery claims ordinary admission/new attempts')
    else:
        recovery = next(x for x in collection['parallel_local_recoveries'] if x['ordinal'] == ordinal)
        require(recovery['ordinary_native_admission'] is False, 'Parallel recovery claims ordinary admission')
        selected = recovery['protected_paths']
        projected_key = 'projected_message'
        adoption_identity = recovery['local_identity']
    receipts = {k: sha(read_pin(inputs, pin, recipe)) for k, pin in selected.items()}
    projected = json.loads(read_pin(inputs, selected[projected_key], recipe))
    require(states(projected['verdicts'], questions) == expected, 'Adopted projection state/order differs')
    return {'adoption_identity_sha256': digest(adoption_identity), 'protected_file_commitments': receipts,
            'raw_states_sha256': digest(expected), 'normalized_states_sha256': digest(expected),
            'ordinary_native_admission': False, 'new_votes_added': 0}


def project_collection(collection, schedule, plan, inputs, recipe):
    native = unique_identities(collection['native_identities'])
    excluded = unique_identities(collection['historical_excluded_native_identities'])
    require(digest(native) == collection['native_identity_commitment_sha256'] == recipe['native_identity_sha256'],
            'Native identity commitment differs')
    for key in ('request_id_hash', 'session_id_hash'):
        require(not {x[key] for x in native} & {x[key] for x in excluded}, 'Historical exclusion became an accepted vote')
    require(collection['recovered_ordinals'] == recipe['recovered_ordinals'], 'Recovery ordinal set differs')
    requests = {x['ordinal']: x for x in plan['requests']}
    passes = {x['pass_id']: x for x in plan['passes']}
    require(len(requests) == len(plan['requests']) and len(passes) == len(plan['passes']), 'Duplicate plan identity')
    require(len(set(schedule['question_ids'])) == len(schedule['question_ids']), 'Duplicate frozen criterion identity')
    rows = collection['rows']
    require([x['pass_id'] for x in rows] == [x['pass_id'] for x in schedule['selected_passes']], 'Selected pass order differs')
    owners = collection['root_chain_ordinal_owners']
    positions, projected_rows, normalized, witnesses, seen = [], [], [], [], set()
    for row, selected in zip(rows, schedule['selected_passes']):
        planned = passes[row['pass_id']]
        require(row['opaque_story_id'] == planned['opaque_story_id'] and row['partition'] == selected['partition'] == planned['partition']
                and row['ordinals'] == selected['request_ordinals'], 'Source/pass/partition/ordinal join differs')
        require(row['source'] == {'bytes': planned['source_bytes'], 'sha256': planned['source_sha256']}, 'Story source commitment differs')
        base = recipe['plan_root']
        inputs.raw(base + '/' + planned['input_path'], planned['source_sha256'], planned['source_bytes'])
        verdicts = states(row['verdict_rows'], schedule['question_ids'])
        require(digest(verdicts) == row['verdicts_sha256'], 'Pass verdict commitment differs')
        normalized.extend({'opaque_story_id': row['opaque_story_id'], 'pass_id': row['pass_id'], **x} for x in verdicts)
        offset = 0
        terminals = {x['ordinal']: x for x in row['replay_input_commitments'].get('terminals', [])}
        for ordinal in row['ordinals']:
            require(ordinal not in seen, 'Duplicate logical position')
            seen.add(ordinal)
            request = requests[ordinal]
            require(request['pass_id'] == row['pass_id'] and request['logical_sample_id'] == selected['logical_sample_id'], 'Request pass identity differs')
            questions = request['question_ids']
            batch = verdicts[offset:offset + len(questions)]
            require([x['question_id'] for x in batch] == questions, 'Frozen request criterion order differs')
            offset += len(questions)
            for name in ('prompt', 'schema'):
                inputs.raw(base + '/' + request[name + '_path'], request[name + '_sha256'], request[name + '_bytes'])
            owner = owners.get(str(ordinal))
            proof = None
            if owner is not None:
                pin = terminals.get(ordinal)
                require(pin is not None and pin.get('owner') == owner, 'Owner/terminal membership differs')
                if ordinal in (254, 370):
                    proof = adopted_projection(inputs, collection, ordinal, questions, batch, recipe)
                    disposition = 'adopted_projection_no_extra_vote'
                else:
                    proof = native_terminal(inputs, owner, pin, questions, batch, recipe)
                    witnesses.append(proof['native_identity'])
                    disposition = ('adopted_native_runtime_data_recovery_no_extra_vote'
                                   if proof['runtime_data_recovery_sha256'] else 'retained_terminal_raw_state_join')
            else:
                disposition = 'static_prefix_or_replacement_commitment_native_join_pending'
            positions.append({'ordinal': ordinal, 'pass_id_sha256': digest(row['pass_id']), 'source_sha256': row['source']['sha256'],
                              'question_ids': questions, 'leaves': batch, 'prompt_sha256': request['prompt_sha256'],
                              'schema_sha256': request['schema_sha256'], 'disposition': disposition,
                              'recovered': ordinal in collection['recovered_ordinals'], 'owner': owner, 'proof': proof,
                              'historical_replay_input_commitments_sha256': digest(row['replay_input_commitments'])})
        require(offset == len(verdicts), 'Pass leaf coverage differs')
        projected_rows.append({'pass_id_sha256': digest(row['pass_id']), 'source': row['source'], 'partition': row['partition'],
                               'ordinals': row['ordinals'], 'verdicts_sha256': digest(verdicts), 'provenance_sha256': digest(row['provenance'])})
    require([x['ordinal'] for x in positions] == schedule['selected_request_ordinals'], 'Frozen selected ordinal order differs')
    require(normalized == collection['normalized_verdict_rows'], 'Collection normalized row projection differs')
    require(set(owners) == {str(x['ordinal']) for x in positions if x['owner'] is not None}, 'Unjoined owner entries')
    witnesses = unique_identities(witnesses)
    require(all(x in native for x in witnesses), 'Terminal identity absent from admitted identity commitment')
    observed = {'story_pass_pairs': len(rows), 'logical_positions': len(positions), 'ordinary_native_identities': len(native),
                'criterion_leaves': len(normalized), 'historical_excluded_native_identities': len(excluded),
                'recovered_positions': len(collection['recovered_ordinals']), 'owner_entries': len(owners),
                'direct_native_terminal_witnesses': len(witnesses),
                'adopted_projections_directly_joined': sum(x['disposition'] == 'adopted_projection_no_extra_vote' for x in positions),
                'adopted_native_runtime_data_recoveries': sum(x['disposition'] == 'adopted_native_runtime_data_recovery_no_extra_vote' for x in positions),
                'static_native_position_joins_pending': sum(x['proof'] is None for x in positions),
                'parallel_prefix_descriptors': len(collection['parallel_source_epoch']['retained_parallel_prefixes']),
                'historical_analysis_excluded_passes': len(collection['coverage_failures']),
                'native_state_counts': dict(sorted(Counter(x['verdict'] for x in normalized).items())),
                'owner_kind_counts': dict(sorted(Counter(x['kind'] for x in owners.values()).items()))}
    require(all(observed[k] == value for k, value in recipe['expected_counts'].items()), 'Pinned census aggregate differs')
    return observed, {'positions': positions, 'passes': projected_rows, 'ordinary_native_identities': native,
                      'historical_excluded_native_identities': excluded, 'recovered_ordinals': collection['recovered_ordinals']}


def build_census(source_root, recipe):
    require(sha(COMMON_PATH.read_bytes()) == recipe['common_census_sha256'], 'Common census source drift')
    inputs = Inputs(source_root)
    assets = {k: inputs.raw(v['locator'], v['sha256'], v['bytes']) for k, v in recipe['assets'].items()}
    collection = json.loads(assets['train'])['freeze']['admission']['record']['collection_record']
    require(digest(collection) == recipe['embedded_collection_sha256'], 'Embedded collection projection differs')
    observed, ledger = project_collection(collection, json.loads(assets['schedule']), json.loads(assets['plan']), inputs, recipe)
    prefixes = collection['parallel_source_epoch']['retained_parallel_prefixes']
    for prefix in prefixes:
        inputs.raw(locator(prefix['manifest_path'], recipe), prefix['manifest_sha256'])
        read_pin(inputs, prefix['replay_receipt'], recipe)
    artifacts = sorted(inputs.artifacts.values(), key=lambda x: x['source_locator'])
    report = {'schema_version': 1, 'scope': recipe['scope'], 'status': 'partial_program_census', 'provider_calls_made': 0,
              'new_provider_votes': 0, 'replaces': 'Census A Dryad Grok projection', 'observed': observed,
              'recipe_sha256': digest(recipe), 'implementation_sha256': sha(Path(__file__).read_bytes()),
              'common_census_sha256': recipe['common_census_sha256'], 'historical_declared_collection_sha256': recipe['historical_declared_collection_sha256'],
              'embedded_collection_sha256': digest(collection),
              'declared_and_embedded_collection_hash_match': recipe['historical_declared_collection_sha256'] == digest(collection),
              'native_identity_sha256': digest(ledger['ordinary_native_identities']), 'native_join_sha256': digest(ledger),
              'verified_artifact_count': len(artifacts), 'verified_artifact_bytes': sum(x['source_bytes'] for x in artifacts),
              'verified_artifact_index_sha256': digest(artifacts),
              'source_commitments_sha256': digest(collection['source_commitments']), 'input_commitments_sha256': digest(collection['input_commitments']),
              'parallel_prefix_descriptors_sha256': digest(prefixes),
              'source_locators': [v['locator'] for v in recipe['assets'].values()],
              'limitations': recipe['limitations']}
    ledger.update({'schema_version': 1, 'private_task_local_only': True, 'report_sha256': digest(report), 'artifacts': artifacts,
                   'parallel_prefix_descriptors': prefixes})
    return report, ledger


def write(path, value):
    with path.open('xb') as handle:
        handle.write(canonical(value) + b'\n')


def check_output(output, source, recipe):
    roots = [source / x for x in recipe['input_roots']]
    if 'assets' in recipe:
        pin = recipe['assets']['train']
        raw = Inputs(source).raw(pin['locator'], pin['sha256'], pin['bytes'])
        collection = json.loads(raw)['freeze']['admission']['record']['collection_record']
        roots.extend(source / locator(x['root'], recipe) for x in collection['root_chain_ordinal_owners'].values())
        roots.extend(source / locator(x['root'], recipe) for x in collection['parallel_source_epoch']['retained_parallel_prefixes'])
        for field in ('local_recovery_protected_paths', 'parallel_successor_protected_paths', 'runtime_data_protected_paths'):
            for descriptor in collection[field].values():
                path = descriptor.get('path')
                if path is not None and str(path).replace('\\', '/').startswith(recipe['source_path_prefix'].rstrip('/') + '/'):
                    mapped = source / locator(path, recipe)
                    roots.append(mapped)
    require(not output.exists() and not output.is_relative_to(REPOSITORY) and not REPOSITORY.is_relative_to(output)
            and all(not output.is_relative_to(r) and not r.is_relative_to(output) for r in roots),
            'Census output must be fresh and outside repository and exact retained input roots')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--output-root', type=Path, required=True)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    source, output = args.source_root.resolve(), args.output_root.resolve()
    recipe_raw = (HERE / 'recipe.json').read_bytes()
    recipe = json.loads(recipe_raw)
    check_output(output, source, recipe)
    if not args.dry_run:
        output.mkdir(parents=True, exist_ok=False)
        for name, raw in [('recipe.json', recipe_raw), ('census.py', Path(__file__).read_bytes()), ('common-census.py', COMMON_PATH.read_bytes())]:
            with (output / name).open('xb') as handle:
                handle.write(raw)
        write(output / 'invocation.json', {'source_root': str(source), 'scope': recipe['scope'], 'provider_calls_made': 0,
              'recipe_file_sha256': sha(recipe_raw), 'implementation_sha256': sha(Path(__file__).read_bytes())})
    try:
        report, ledger = build_census(source, recipe)
        if not args.dry_run:
            write(output / 'census.json', report)
            write(output / 'private-slots.json', ledger)
            write(output / 'terminal.json', {'state': 'completed_provider_free_join', 'report_sha256': digest(report), 'private_ledger_sha256': digest(ledger)})
        print(json.dumps({'dry_run': args.dry_run, 'observed': report['observed'], 'status': report['status'],
                          'report_sha256': digest(report), 'private_ledger_sha256': digest(ledger),
                          'verified_artifact_count': report['verified_artifact_count']}, sort_keys=True))
        return 0
    except (OSError, ValueError, KeyError, TypeError) as error:
        if not args.dry_run:
            write(output / 'terminal.json', {'state': 'failed_join_pending', 'error_class': type(error).__name__})
        parser.exit(1, f'Census F pending: {type(error).__name__}: {error}\n')


if __name__ == '__main__':
    raise SystemExit(main())
