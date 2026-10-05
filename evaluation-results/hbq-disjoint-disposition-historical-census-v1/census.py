"""Three pinned historical roots: selective metadata, immutable hash-only inventory."""
import argparse
from collections import Counter
import hashlib
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
POLICY = 'disjoint_disposition_historical_metadata_census_v1'
LEAF_STATES = {'YES', 'NO', 'NOT_APPLICABLE', 'CANNOT_ASSESS'}
FAMILIES = ('nonpoetry', 'poetry-disjoint', 'poetry-treatment')
LEXICAL_READER = REPO / 'evaluation-results/hbq-matched-hanna-20261004/prepare.py'
LEXICAL_READER_SHA = '2d82e4959c3296ccaa6e6521adb46f85588427d429a544b36a2891ebaea8c7b0'
_lexical_reader = None


def project_source(family, name, raw):
    """Skipped JSON values remain lexical source bytes, including quotes and targets."""
    global _lexical_reader
    if _lexical_reader is None:
        require(file_pin(LEXICAL_READER)['sha256'] == LEXICAL_READER_SHA, 'Pinned lexical metadata reader differs')
        spec = importlib.util.spec_from_file_location('disjoint_census_private_lexical_reader', LEXICAL_READER)
        _lexical_reader = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(_lexical_reader)
    fields = lambda *keys: dict.fromkeys(keys, True)
    slot = fields('slot_id', 'logical_sample_id', 'leaf_id', 'repeat')
    leaf = fields('run_id', 'question_id', 'verdict')
    specification = None
    if family == 'nonpoetry' and name in {'study-manifest.json', 'runtime-schedule.json'}:
        specification = {'slots': [slot]}
    elif family == 'poetry-treatment' and name == 'study-manifest.json':
        specification = {'planned_slots': True, 'slots': [fields('opaque_slot_id')]}
    elif family == 'poetry-disjoint' and name == 'frozen-input-snapshot/dry-manifest.v2.json':
        specification = fields('planned_slots', 'rendered_slots', 'rendered_prompt_sha256')
    elif name == 'execution-terminal.v1.json':
        specification = {'completed_slots': True} if family == 'nonpoetry' else {
            'planned_slots': True, 'completed_slots': True, 'records': [{}]}
    elif name.startswith('runs/') and name.endswith('/run.json'):
        specification = {'config_sha256': True, 'run_id': True, 'configuration': {'question_ids': True}}
    elif name.startswith('runs/') and name.endswith('/responses/batch-0001.json'):
        specification = {'question_ids': True, 'batch': True, 'accepted_attempt': True,
                         'normalized_verdicts': [leaf if family == 'nonpoetry' else fields('run_id', 'question_id')],
                         'response_artifact': fields('bytes', 'path', 'sha256')}
    elif family == 'nonpoetry' and name.startswith('runs/'):
        if name.endswith('/verdicts.jsonl'):
            return [_lexical_reader.project_json(line, leaf) for line in raw.splitlines()]
        if name.endswith(('/responses/batch-0001.attempt-0001.message.json',
                          '/responses/batch-0001.accepted-0001.message.txt')):
            specification = {'verdicts': [fields('question_id', 'verdict')]}
        elif name.endswith('/responses/attempt-lifecycle/batch-0001/attempt-0001.start.json'):
            specification = fields('attempt', 'batch', 'state', 'config_sha256')
        elif name.endswith('/responses/attempt-lifecycle/batch-0001/attempt-0001.settled.json'):
            specification = {**fields('attempt', 'batch', 'state', 'outcome', 'start_sha256'),
                             'evidence': fields('kind', 'path', 'sha256')}
    require(specification is not None, 'No lexical metadata projection exists for this source')
    return _lexical_reader.project_json(raw, specification)


def require(ok, message):
    if not ok:
        raise ValueError(message)


def canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False) + '\n').encode()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def file_pin(path):
    digest, size = hashlib.sha256(), 0
    with path.open('rb') as stream:
        while chunk := stream.read(1024 * 1024):
            size += len(chunk)
            digest.update(chunk)
    return {'bytes': size, 'sha256': digest.hexdigest()}


def inventory(root, excluded):
    return [{'path': path.relative_to(root).as_posix(), **file_pin(path)}
            for path in sorted(root.rglob('*')) if path.is_file()
            and not any(name in path.relative_to(root).parts for name in excluded)]


def leaf_projection(rows, question_id):
    require(len(rows) == 1 and rows[0]['question_id'] == question_id
            and rows[0]['verdict'] in LEAF_STATES, 'Retained singleton leaf/state differs')
    return {'question_id': question_id, 'state': rows[0]['verdict']}


def singleton_observation(slot, run_id, representations, pins, *, scheduled_logical=None):
    require(slot['leaf_id'] == 'scope.passage.status' and isinstance(run_id, str) and run_id,
            'Only the frozen singleton scope leaf is eligible')
    projected = [leaf_projection(rows, slot['leaf_id']) for rows in representations]
    require(len(projected) == 4 and all(value == projected[0] for value in projected),
            'Checkpoint/message/verdict representations disagree')
    return {'kind': 'retained_singleton_leaf', 'slot_identity_sha256': sha(canonical(slot['slot_id'])),
            'logical_sample_identity_sha256': sha(canonical(slot['logical_sample_id'])),
            'runtime_schedule_logical_sample_identity_sha256': sha(canonical(scheduled_logical)) if scheduled_logical is not None else None,
            'manifest_runtime_logical_identity_matches': slot['logical_sample_id'] == scheduled_logical if scheduled_logical is not None else None,
            'run_identity_sha256': sha(canonical(run_id)), 'repeat': slot['repeat'],
            'observation_identity_sha256': sha(canonical([slot['logical_sample_id'], slot['slot_id'], run_id])),
            **projected[0], 'representation_count': 4, 'artifact_commitments': pins,
            'current_admission_verified': False, 'native_session_identity': None,
            'physical_contact_cardinality_proven': False, 'new_votes': 0}


def declared_population(slot_ids, output_ids, declaration):
    require(len(slot_ids) == len(set(slot_ids)) == declaration['planned_slots']
            and len(output_ids) == len(set(output_ids)) and set(output_ids) <= set(slot_ids),
            'Declared planned/output identities differ')
    outputs = declaration.get('historical_nonvoting_output_dispositions', declaration.get('retained_output_dispositions'))
    require(outputs == len(output_ids) and declaration['completed_slots'] == 0
            and declaration['untouched_slots'] == len(slot_ids) - len(output_ids),
            'Historical nonvoting/untouched declarations differ')
    return [{'kind': 'historical_output_disposition' if slot in output_ids else 'inherited_untouched_declaration',
             'slot_identity_sha256': sha(canonical(slot)),
             'disposition': 'historical_nonvoting_semantic_output' if slot in output_ids else 'declared_untouched',
             'current_admission_verified': False, 'voting_leaf_observations': 0, 'native_session_identity': None,
             'native_contact_disposition': 'unresolved', 'new_votes': 0} for slot in slot_ids]


def nonpoetry(source_json, source_raw, family):
    manifest = source_json('study-manifest.json')
    schedule = source_json('runtime-schedule.json')
    terminal = source_json('execution-terminal.v1.json')
    slots = manifest['slots']
    require(len(slots) == len(schedule['slots']) == terminal['completed_slots'] == 6,
            'Exact six-slot retained geometry differs')
    require([slot['slot_id'] for slot in slots] == [slot['slot_id'] for slot in schedule['slots']]
            and len({slot['slot_id'] for slot in slots}) == 6, 'Frozen schedule membership differs')
    observations = []
    for slot, scheduled in zip(slots, schedule['slots']):
        require(all(slot[key] == scheduled[key] for key in ('slot_id', 'leaf_id', 'repeat')),
                'Frozen singleton scope/independent repeat identity differs')
        base = 'runs/' + slot['slot_id']
        run = source_json(base + '/run.json')
        checkpoint_name = base + '/responses/batch-0001.json'
        checkpoint = source_json(checkpoint_name)
        require(run['configuration']['question_ids'] == checkpoint['question_ids'] == ['scope.passage.status']
                and checkpoint['batch'] == checkpoint['accepted_attempt'] == 1,
                'Singleton checkpoint metadata differs')
        normalized = checkpoint['normalized_verdicts']
        verdicts = source_json(base + '/verdicts.jsonl')
        require(all(row['run_id'] == run['run_id'] for row in normalized + verdicts), 'Retained run/checkpoint identity differs')
        attempt_name = base + '/responses/batch-0001.attempt-0001.message.json'
        accepted_name = base + '/responses/batch-0001.accepted-0001.message.txt'
        artifact = checkpoint['response_artifact']
        require(artifact['path'] == 'responses/batch-0001.accepted-0001.message.txt'
                and family['source_pins'][accepted_name] == {'bytes': artifact['bytes'], 'sha256': artifact['sha256']},
                'Accepted message byte commitment differs')
        start_name = base + '/responses/attempt-lifecycle/batch-0001/attempt-0001.start.json'
        settled_name = base + '/responses/attempt-lifecycle/batch-0001/attempt-0001.settled.json'
        start, settled = source_json(start_name), source_json(settled_name)
        require(start['attempt'] == start['batch'] == settled['attempt'] == settled['batch'] == 1
                and start['state'] == 'started' and settled['state'] == 'settled' and settled['outcome'] == 'accepted'
                and start['config_sha256'] == run['config_sha256']
                and settled['start_sha256'] == family['source_pins'][start_name]['sha256']
                and settled['evidence'] == {'kind': 'accepted_checkpoint', 'path': 'responses/batch-0001.json',
                                           'sha256': family['source_pins'][checkpoint_name]['sha256']},
                'Retained lifecycle/checkpoint commitments differ')
        pins = {name.rsplit('/', 1)[-1]: family['source_pins'][name] for name in
                [checkpoint_name, attempt_name, accepted_name, base + '/verdicts.jsonl', start_name, settled_name]}
        item = singleton_observation(slot, run['run_id'],
            [normalized, verdicts, source_json(attempt_name)['verdicts'], source_json(accepted_name)['verdicts']], pins,
            scheduled_logical=scheduled['logical_sample_id'])
        item['run_artifact_sha256'] = family['source_pins'][base + '/run.json']['sha256']
        observations.append(item)
    require(len({item['run_identity_sha256'] for item in observations}) == 6
            and len({item['observation_identity_sha256'] for item in observations}) == 6,
            'Duplicate run/message observation across planned repeats')
    return observations, {'planned_slots_from_manifest': 6, 'retained_leaf_observations': 6,
                          'leaf_states': dict(Counter(item['state'] for item in observations)),
                          'representation_rows': 24, 'duplicate_representations_not_extra_observations': 18,
                          'manifest_runtime_logical_identity_mismatches': sum(not item['manifest_runtime_logical_identity_matches'] for item in observations),
                          'retained_checkpoint_accepted_dispositions': 6, 'terminal_declared_completed_slots': 6}


def poetry_disjoint(source_json, family):
    manifest = source_json('frozen-input-snapshot/dry-manifest.v2.json')
    terminal = source_json('execution-terminal.v1.json')
    ids = sorted(manifest['rendered_prompt_sha256'])
    require(manifest['planned_slots'] == manifest['rendered_slots'] == terminal['planned_slots'] == 12
            and terminal['completed_slots'] == 0 and terminal['records'] == [], 'Historical zero-completed terminal differs')
    base = 'runs/q-46ac81'
    checkpoint = source_json(base + '/responses/batch-0001.json')
    run = source_json(base + '/run.json')
    require(checkpoint['batch'] == checkpoint['accepted_attempt'] == 1
            and checkpoint['question_ids'] == run['configuration']['question_ids']
            and len(checkpoint['question_ids']) == len(checkpoint['normalized_verdicts']) == 1
            and checkpoint['normalized_verdicts'][0]['run_id'] == run['run_id'], 'Pinned historical output metadata differs')
    artifact = checkpoint['response_artifact']
    require(artifact['path'] == 'responses/batch-0001.accepted-0001.message.txt'
            and family['source_pins'][base + '/' + artifact['path']] == {'bytes': artifact['bytes'], 'sha256': artifact['sha256']},
            'Historical accepted-named message commitment differs')
    observations = declared_population(ids, ['q-46ac81'], family['inherited_declaration'])
    occupied = next(item for item in observations if item['kind'] == 'historical_output_disposition')
    occupied.update(run_identity_sha256=sha(canonical(run['run_id'])),
                    checkpoint_sha256=family['source_pins'][base + '/responses/batch-0001.json']['sha256'],
                    message_sha256=artifact['sha256'], checkpoint_accepted_attempt_metadata=1,
                    voting_admission_inferred_from_filename=False)
    return observations, {'planned_slots_from_frozen_metadata': 12, 'terminal_declared_completed_slots': 0,
                          'retained_historical_nonvoting_output_dispositions': 1,
                          'inherited_untouched_declarations': 11, 'retained_leaf_observations': 0,
                          'historical_response_leaf_states_decoded': False}


def poetry_treatment(source_json, family):
    manifest = source_json('study-manifest.json')
    require(manifest['planned_slots'] == len(manifest['slots']) == 12, 'Frozen treatment planned geometry differs')
    ids = [slot['opaque_slot_id'] for slot in manifest['slots']]
    observations = declared_population(ids, [], family['inherited_declaration'])
    return observations, {'planned_slots_from_manifest': 12, 'retained_output_dispositions': 0,
                          'inherited_untouched_declarations': 12, 'retained_leaf_observations': 0,
                          'contact_absence_inferred_from_filesystem': False}


def census(documents, recipe_path=HERE / 'recipe.json'):
    raw_recipe = recipe_path.read_bytes()
    recipe = json.loads(raw_recipe)
    require(recipe['policy'] == POLICY and [family['id'] for family in recipe['families']] == list(FAMILIES),
            'Only the three named retained executions are supported')
    ledgers, slots, summaries, roots = [], [], [], []
    for family in recipe['families']:
        root = (documents / family['root_relative_to_documents']).resolve()
        require(root.is_relative_to(documents.resolve()), 'Source locator escapes the supplied Documents root')
        roots.append(root)
        artifacts = inventory(root, recipe['inventory_excluded_directory_names'])
        require(len(artifacts) == family['artifact_count'] and sha(canonical(artifacts)) == family['artifact_inventory_sha256'],
                'Exact retained artifact inventory differs')
        by_name = {item['path']: {'bytes': item['bytes'], 'sha256': item['sha256']} for item in artifacts}
        require(all(by_name.get(name) == pin for name, pin in family['source_pins'].items()), 'Selective source commitment differs')
        public = family['public_artifact']
        require(file_pin(REPO / public['path']) == {key: public[key] for key in ('bytes', 'sha256')}, 'Exact public hash-only commitment differs')
        def source_raw(name):
            require(name in family['source_pins'], 'Source is outside the pinned metadata projection allowlist')
            raw = (root / name).read_bytes()
            require({'bytes': len(raw), 'sha256': sha(raw)} == family['source_pins'][name], 'Source changed during projection')
            return raw
        def source_json(name):
            return project_source(family['id'], name, source_raw(name))
        project = {'nonpoetry': nonpoetry, 'poetry-disjoint': poetry_disjoint, 'poetry-treatment': poetry_treatment}[family['id']]
        observations, observed = project(source_json, source_raw, family) if family['id'] == 'nonpoetry' else project(source_json, family)
        for item in observations:
            item['family'] = family['id']
        slots.extend(observations)
        ledgers.extend({'family': family['id'], **item} for item in artifacts)
        ledgers.append({'family': family['id'], 'kind': 'public_hash_only', **public})
        summaries.append({'family': family['id'], 'public_artifact_commitment': public,
                          'source_root_locator': family['root_relative_to_documents'],
                          'artifact_inventory_sha256': family['artifact_inventory_sha256'], 'artifact_count': len(artifacts),
                          'inherited_declaration': family['inherited_declaration'], 'observed': observed,
                          'current_admission_verified': False, 'current_verified_admitted_votes': 0,
                          'native_request_session_join': 'unresolved', 'physical_contact_cardinality': None})
    report = {'schema_version': 1, 'policy': POLICY, 'implementation_sha256': sha(Path(__file__).read_bytes()),
              'lexical_projection_reader_sha256': LEXICAL_READER_SHA,
              'recipe_sha256': sha(raw_recipe), 'families': summaries,
              'artifact_ledger_sha256': sha(canonical(ledgers)), 'private_slot_ledger_sha256': sha(canonical(slots)),
              'provider_calls': 0, 'new_votes': 0, 'scoring_performed': False, 'human_labels_opened': False,
              'scope': 'exact_retained_roots_only_no_ancestor_request_sum',
              'remaining_gaps': ['Run/checkpoint/message IDs are not complete own native session/request/model receipts.',
                                 'Frozen manifest and runtime-schedule logical IDs are retained separately; slot/leaf/repeat matching does not resolve their differing identities.',
                                 'Historical accepted checkpoints do not establish current semantic/native admission.',
                                 'Untouched counts are inherited declarations; filesystem absence is not negative contact proof.',
                                 'Sealed outcomes, notes, prose and quoted evidence are hash-only; no label or oracle projection.']}
    return report, slots, ledgers, roots


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--documents-root', type=Path, required=True)
    parser.add_argument('--output-root', type=Path, required=True)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    output = args.output_root.resolve()
    require(not output.exists(), 'Census output must be a fresh immutable descendant')
    report, slots, artifacts, roots = census(args.documents_root.resolve())
    require(all(not output.is_relative_to(path.resolve()) and not path.resolve().is_relative_to(output)
                for path in [REPO, *roots]), 'Private census output overlaps source evidence or checkout')
    if not args.dry_run:
        output.mkdir(parents=True, exist_ok=False)
        for name, value in [('report.json', report), ('private-slots.json', slots), ('artifact-ledger.json', artifacts)]:
            with (output / name).open('xb') as stream:
                stream.write(canonical(value))
    print(json.dumps({'state': 'provider_free_historical_census', 'report_sha256': sha(canonical(report)),
                      'artifact_ledger_sha256': report['artifact_ledger_sha256'],
                      'private_slot_ledger_sha256': report['private_slot_ledger_sha256'],
                      'families': [{'family': item['family'], 'observed': item['observed']} for item in report['families']],
                      'provider_calls': 0, 'new_votes': 0, 'human_labels_opened': False, 'output_written': not args.dry_run}, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
