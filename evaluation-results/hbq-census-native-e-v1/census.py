"""Provider-free pinned multisample native metadata and failed-attempt census."""
from __future__ import annotations

import argparse
from collections import Counter
import gzip
import importlib.util
import json
from pathlib import Path

from jsonschema import Draft202012Validator

HERE = Path(__file__).resolve().parent
REPOSITORY = HERE.parent.parent
COMMON_PATH = HERE.parent / 'hbq-evidence-census-pass-c-v1' / 'census.py'
_spec = importlib.util.spec_from_file_location('native_census_e_common', COMMON_PATH)
_common = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_common)
Inputs, require, sha, canonical, digest = (_common.Inputs, _common.require, _common.sha, _common.canonical, _common.digest)
VERDICTS = _common.VERDICTS


def pretty(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode('utf-8')


def verdict_bytes(values):
    return ''.join(json.dumps(v, ensure_ascii=False, sort_keys=True) + '\n' for v in values).encode('utf-8')


def locator(path, recipe):
    prefix = recipe['source_path_prefix'].replace('\\', '/').rstrip('/') + '/'
    value = str(path).replace('\\', '/')
    require(value.startswith(prefix), 'Historical locator leaves pinned source prefix')
    return value[len(prefix):]


def session(record):
    value = record.get('provider', {}).get('reported', {}).get('session_id')
    require(isinstance(value, str) and bool(value), 'Missing reported session identity')
    return value


def parsed_content(text):
    value = text.strip()
    if value.startswith('```'):
        lines = value.splitlines()
        require(lines[-1] == '```', 'Unclosed native JSON fence')
        value = '\n'.join(lines[1:-1])
    return json.loads(value)


def source_conditions(inputs, frozen, recipe):
    original = locator(recipe['original_root'], recipe)
    samples = {}
    for sample in frozen['samples']:
        require(sample['item_id'] not in samples, 'Duplicate frozen item identity')
        samples[sample['item_id']] = sample
        for name in ('source.md', 'prompt.md', 'task-contract.json'):
            pin = sample['inputs'][name]
            inputs.raw(original + '/inputs/' + sample['item_id'] + '/' + name, pin['sha256'], pin['bytes'])
    return samples


def schema_for_arm(inputs, frozen, arm, recipe):
    path = (REPOSITORY / 'evaluation-results/hbq-multisample-repeatability-v1' / arm['schema']).resolve()
    relative = path.relative_to(REPOSITORY).as_posix()
    pins = [p for p in frozen['runtime_files'] if (REPOSITORY / p['path']).resolve() == path]
    require(len(pins) == 1, 'Native schema missing from frozen runtime fingerprints')
    pin = pins[0]
    historical = recipe['repository_root'].rstrip('/\\') + '/' + relative
    raw = inputs.raw(locator(historical, recipe), pin['sha256'], pin['bytes'])
    return json.loads(raw), sha(raw)


def validate_native_response(inputs, base, response, result, manifest, schema):
    config = manifest['configuration']
    require(manifest['format_version'] == 1 and manifest['config_sha256'] == sha(pretty(config)),
            'Native configuration commitment differs')
    prompt = gzip.decompress(inputs.raw(base + '/request.prompt.txt.gz'))
    projected_schema = inputs.raw(base + '/response.schema.json')
    require(sha(prompt) == config['prompt_sha256'] and config['schema_sha256'] == sha(pretty(schema)),
            'Native prompt/schema condition differs')
    require(response['format_version'] == 1 and response['config_sha256'] == manifest['config_sha256']
            and response['prompt_sha256'] == config['prompt_sha256']
            and response['schema_sha256'] == config['schema_sha256']
            and response['content_sha256'] == sha(response['content'].encode('utf-8'))
            and response['result_sha256'] == sha(pretty(result))
            and parsed_content(response['content']) == result, 'Native response/result commitment differs')
    require(not list(Draft202012Validator(schema).iter_errors(result)), 'Native result schema differs')
    return {'prompt_sha256': sha(prompt), 'projected_schema_sha256': sha(projected_schema),
            'result_sha256': sha(pretty(result)), 'content_sha256': response['content_sha256']}


def rejected_attempt(inputs, path, sequence, ordinal, namespace):
    raw = inputs.raw(path)
    record = json.loads(raw)
    require(record['format_version'] == 1 and isinstance(record.get('response'), dict)
            and isinstance(record.get('result'), dict) and isinstance(record.get('reason'), str),
            'Retained rejected-attempt shape differs')
    response = record['response']
    require(response['content_sha256'] == sha(response['content'].encode('utf-8'))
            and response['result_sha256'] == sha(pretty(record['result']))
            and parsed_content(response['content']) == record['result'], 'Rejected response commitment differs')
    return {'sequence': sequence, 'attempt': ordinal, 'namespace': namespace,
            'accepted': False, 'disposition': 'retained_semantic_rejection', 'leaves': [],
            'reported_session_sha256': sha(session(response).encode('utf-8')),
            'record_sha256': sha(raw), 'reason_sha256': digest(record['reason']),
            'response_sha256': digest(response), 'result_sha256': digest(record['result'])}, session(response)


def project_hbq(inputs, base, manifest, sample, arm, expected_version=3, recipe=None):
    config = manifest['configuration']
    require(manifest['format_version'] == expected_version and manifest['config_sha256'] == sha(pretty(config)),
            'HBQ configuration commitment differs')
    references = []
    if recipe is not None:
        for pin in [*config['prompts'], config['response_schema']]:
            reference = locator(pin['path'], recipe)
            exists = inputs.path(reference).is_file()
            raw = inputs.raw(reference) if exists else None
            matches = exists and sha(raw) == pin['sha256'] and len(raw) == pin['bytes']
            references.append({'source_locator': reference, 'expected_sha256': pin['sha256'], 'expected_bytes': pin['bytes'],
                               'observed_sha256': sha(raw) if exists else None, 'observed_bytes': len(raw) if exists else None,
                               'disposition': 'matches_historical_fingerprint' if matches else
                                              ('historical_locator_changed' if exists else 'historical_locator_unavailable')})
    ids = config['question_ids']
    require(len(ids) == sample['question_count'] == arm['question_count']
            and digest(ids) == sample['question_id_sequence_sha256'] and len(set(ids)) == len(ids),
            'Frozen ordered leaf identity differs')
    require(config['artifact_id'] == sample['item_id'] and config['bundle_id'] == arm['bundle_id']
            and config['batch_size'] == arm['batch_size'] and config['strict_ai'] is True
            and config['retry_semantics'] == 'cumulative_batch_attempts_v1', 'HBQ condition identity differs')
    for entry, name in [(config['artifact'], 'source.md'), (config['task_contract'], 'task-contract.json'),
                        (config['contexts'][0], 'prompt.md')]:
        pin = sample['inputs'][name]
        require(entry['sha256'] == pin['sha256'] and entry['bytes'] == pin['bytes'], 'HBQ source condition differs')
    schema_raw = inputs.raw(base + '/response.schema.json')
    provider_schema = json.loads(schema_raw)
    checkpoints = sorted(inputs.path(base + '/responses').glob('batch-[0-9][0-9][0-9][0-9].json'))
    expected_batches = (len(ids) + arm['batch_size'] - 1) // arm['batch_size']
    require(len(checkpoints) == expected_batches, 'Missing accepted HBQ checkpoint')
    values, leaves, units, sessions, commitments = [], [], [], [], []
    previous = None
    for number, path in enumerate(checkpoints, 1):
        checkpoint_path = base + '/responses/' + path.name
        raw = inputs.raw(checkpoint_path)
        checkpoint = json.loads(raw)
        chunk = ids[(number - 1) * arm['batch_size']:number * arm['batch_size']]
        require(path.name == f'batch-{number:04d}.json' and checkpoint['format_version'] == 4
                and checkpoint['batch'] == number and checkpoint['question_ids'] == chunk
                and checkpoint['previous_checkpoint_sha256'] == previous
                and checkpoint['accepted_attempt'] == 1
                and checkpoint['rejected_chain'] == {'count': 0, 'head_sha256': None}
                and checkpoint['normalization_policy'] == config['evidence_normalization_policy']
                and checkpoint['validation_feedback_policy'] == config['validation_feedback_policy'],
                'HBQ ordered checkpoint/normalization chain differs')
        artifact = checkpoint['response_artifact']
        native_raw = inputs.raw(base + '/' + artifact['path'], artifact['sha256'], artifact['bytes'])
        native = json.loads(native_raw)
        require(sha(native_raw) == checkpoint['response_sha256'], 'HBQ accepted raw commitment differs')
        require(not list(Draft202012Validator(provider_schema).iter_errors(native)), 'HBQ native response schema differs')
        normalized = checkpoint['normalized_verdicts']
        native_ids = [v['question_id'] for v in native['verdicts']]
        native_rows = {v['question_id']: (position, v) for position, v in enumerate(native['verdicts'])}
        require(len(native_rows) == len(native_ids) == len(chunk) and set(native_ids) == set(chunk)
                and [v['question_id'] for v in normalized] == chunk
                and all(native_rows[v['question_id']][1]['verdict'] == v['verdict'] for v in normalized),
                'HBQ raw/normalized leaf states differ')
        for row in normalized:
            native_position, native_row = native_rows[row['question_id']]
            require(row['artifact_id'] == sample['item_id'] and row['bundle_id'] == arm['bundle_id']
                    and row['verdict'] in VERDICTS, 'HBQ native four-state identity differs')
            leaves.append({'position': len(leaves), 'question_id': row['question_id'], 'verdict': row['verdict'],
                           'native_batch_position': native_position,
                           'native_row_sha256': digest(native_row), 'normalized_row_sha256': digest(row)})
        values.extend(normalized)
        require(checkpoint['verdicts_sha256'] == sha(verdict_bytes(values)), 'HBQ cumulative verdict commitment differs')
        observed = session(checkpoint)
        sessions.append(observed)
        commitments.append(sha(raw))
        units.append({'ordinal': number, 'accepted': True, 'reported_session_sha256': sha(observed.encode('utf-8')),
                      'checkpoint_sha256': sha(raw), 'raw_response_sha256': sha(native_raw),
                      'question_ids_sha256': digest(chunk), 'normalization_audit_sha256': digest(checkpoint['normalization_audit']),
                      'native_question_ids_sha256': digest(native_ids), 'native_order_differs': native_ids != chunk,
                      'prompt_sha256': checkpoint['prompt_sha256'], 'base_prompt_sha256': checkpoint['base_prompt_sha256'],
                      'effective_prompt_sha256': checkpoint['effective_prompt_sha256']})
        previous = sha(raw)
    verdict_raw = inputs.raw(base + '/verdicts.jsonl')
    require(verdict_raw == verdict_bytes(values), 'HBQ retained verdict stream differs')
    return leaves, units, [], sessions, commitments, {
        'verdicts_sha256': sha(verdict_raw), 'persisted_schema_sha256': sha(schema_raw),
        'compiled_bundle_sha256': config['compiled_bundle_sha256'], 'questions_sha256': config['questions_sha256'],
        'question_ids_sha256': digest(ids), 'normalization_policy': config['evidence_normalization_policy'],
        'historical_static_references': references,
        'normalization_reexecution': False}


def project_native(inputs, base, manifest, cell, schema, recipe):
    config = manifest['configuration']
    require(config['name'] == f"{cell['item_id']}-{cell['arm_id']}-run-{cell['repetition']:02d}",
            'Native item/arm/repetition differs')
    response_raw = inputs.raw(base + '/response.json')
    response = json.loads(response_raw)
    result = inputs.read(base + '/result.json')
    proof = validate_native_response(inputs, base, response, result, manifest, schema)
    sessions, commitments = [session(response)], [sha(response_raw)]
    units = [{'ordinal': 1, 'accepted': True, 'reported_session_sha256': sha(sessions[0].encode('utf-8')),
              'response_sha256': sha(response_raw), **proof}]
    attempts = []
    paths = sorted(inputs.path(base).glob('attempts/rejected-*.json'))
    require(not list(inputs.path(base).glob('attempts/failed-*.json')), 'New native failed-record disposition requires explicit recipe')
    for ordinal, path in enumerate(paths, 1):
        attempt, observed = rejected_attempt(inputs, base + '/attempts/' + path.name, cell['sequence'], ordinal, 'admitted_cell_retry')
        attempts.append(attempt)
        sessions.append(observed)
        commitments.append(attempt['record_sha256'])
    require(bool(paths) == (cell['sequence'] in recipe['rejected_sequences']), 'Pinned admitted retry inventory differs')
    if cell['sequence'] in recipe['physical_retry_sequences']:
        require(len(paths) == 1, 'Retry-native rejection count differs')
        archive = base + '/retry-attempts/attempt-0001'
        archived_manifest = inputs.read(archive + '/pass.json')
        first_attempt = inputs.read(base + '/attempts/rejected-0001.json')
        archived_response, archived_result = first_attempt['response'], first_attempt['result']
        validate_native_response(inputs, archive, archived_response, archived_result, archived_manifest, schema)
        for ordinal, root, expected in [(1, base, archived_result), (2, base + '/retry-attempts/attempt-0002', result)]:
            raw = inputs.raw(root + '/responses/batch-0001.attempt-0001.message.json')
            require(json.loads(raw) == expected, 'Retry physical message differs')
            commitments.append(sha(raw))
            attempts[0].setdefault('physical_messages', []).append({'attempt': ordinal, 'sha256': sha(raw)})
    return [], units, attempts, sessions, commitments, proof


def validate_cells(cells, schedule, study_id):
    require(len(cells) == len(schedule), 'Admitted logical cell geometry differs')
    seen = set()
    for position, (cell, event) in enumerate(zip(cells, schedule), 1):
        key = (study_id, cell['sequence'], cell['item_id'], cell['arm_id'], cell['repetition'])
        require(cell['sequence'] == position and key not in seen
                and all(cell[k] == event[k] for k in ('item_id', 'arm_id', 'repetition')),
                'Duplicate, reordered or mismatched adopted cell')
        seen.add(key)


def aggregate(cells, failed, unresolved, historical):
    attempts = [a for c in cells for a in c['rejected_attempts']] + failed
    units = [u for c in cells for u in c['accepted_units']]
    identities = [u['reported_session_sha256'] for u in units] + [a['reported_session_sha256'] for a in attempts]
    require(len(identities) == len(set(identities)), 'Duplicate reported session across bounded attempt lineage')
    leaves = [v for c in cells for v in c['leaves']]
    references = {digest(r): r for c in cells for r in c.get('commitments', {}).get('historical_static_references', [])}
    return {'accepted_logical_cells': len(cells), 'accepted_units': len(units),
            'hbq_passes': sum(c['kind'] == 'hbq' for c in cells),
            'native_passes': sum(c['kind'] == 'native' for c in cells),
            'native_leaf_rows': len(leaves), 'leaf_states': dict(Counter(v['verdict'] for v in leaves)),
            'rejected_attempts': len(attempts), 'failed_prefix_attempts': len(failed),
            'unique_observed_sessions_bounded_lineage': len(set(identities)),
            'retry_physical_message_commitments': sum(len(a.get('physical_messages', [])) for a in attempts),
            'hbq_raw_order_differs_batches': sum(u.get('native_order_differs', False) for u in units),
            'hbq_quality_cohort_counts': dict(Counter(c['hbq_quality_cohort'] for c in cells if c['kind'] == 'hbq')),
            'distinct_historical_static_reference_dispositions': dict(Counter(r['disposition'] for r in references.values())),
            'source_kind_counts': dict(Counter(c['source_kind'] for c in cells)),
            'historical_analysis_projection': historical, 'unresolved_controller_records': len(unresolved),
            'independent_work_count': None, 'physical_provider_contact_count': None,
            'replaces_prior_multisample_declaration': True}


def build_census(source_root, recipe):
    require(sha(COMMON_PATH.read_bytes()) == recipe['common_census_sha256'], 'Common census implementation differs')
    inputs = Inputs(source_root)
    assets = {k: json.loads(inputs.raw(*pin)) for k, pin in recipe['assets'].items()}
    for pin in recipe.get('journal_assets', []):
        for line in inputs.raw(*pin).splitlines():
            require(isinstance(json.loads(line), dict), 'Journal record shape differs')
    provenance, summary, frozen = assets['provenance'], assets['summary'], assets['frozen']
    require(provenance['study_id'] == summary['study_id'] == frozen['study_id'], 'Study identity differs')
    require(provenance['frozen_contract']['sha256'] == recipe['assets']['frozen'][1], 'Consolidation frozen contract differs')
    require(digest(frozen['schedule']) == frozen['schedule_sha256'], 'Frozen schedule commitment differs')
    cells = provenance['cells']
    validate_cells(cells, frozen['schedule'], frozen['study_id'])
    require(provenance['source_kind_counts'] == recipe['source_kind_counts'], 'Pinned source adoption geometry differs')
    if 'missing181_receipt' in assets:
        receipt = assets['missing181_receipt']
        require(receipt['binding_sha256'] == recipe['assets']['missing181_binding'][1]
                and receipt['event'] == assets['missing181_binding']['event']
                and receipt['event']['sequence'] == 181
                and receipt['output']['sha256'] == cells[180]['run_binding_sha256'],
                'Detached completion receipt differs')
    samples = source_conditions(inputs, frozen, recipe)
    arms = {a['arm_id']: a for a in frozen['contract']['arms']}
    schemas = {a['arm_id']: schema_for_arm(inputs, frozen, a, recipe)[0] for a in arms.values() if a['kind'] == 'native'}
    projected, observed_sessions, commitments = [], [], []
    for cell in cells:
        arm, sample = arms[cell['arm_id']], samples[cell['item_id']]
        root = locator(cell['source_root'], recipe)
        base = root + '/runs/' + cell['item_id'] + '/' + cell['arm_id'] + f"/run-{cell['repetition']:02d}"
        binding = base + ('/run.json' if arm['kind'] == 'hbq' else '/pass.json')
        require(locator(cell['run_binding_path'], recipe) == binding, 'Adopted native manifest path differs')
        manifest = inputs.read(binding, cell['run_binding_sha256'])
        config = manifest['configuration']
        require(config['provider'] == 'codex' and config['model'] == recipe['reported_model']
                and config['reasoning'] == recipe['reported_reasoning'], 'Retained requested condition differs')
        if arm['kind'] == 'hbq':
            version = 4 if cell['source_kind'] in ('missing181_detached_completion', 'v8_accepted_183_330') else 3
            leaves, units, rejected, sessions, hashes, proof = project_hbq(inputs, base, manifest, sample, arm, version, recipe)
        else:
            leaves, units, rejected, sessions, hashes, proof = project_native(inputs, base, manifest, cell, schemas[cell['arm_id']], recipe)
        require(sorted(sessions) == sorted(cell['session_ids']) and sorted(hashes) == sorted(cell['artifact_commitments']),
                'Published native session/artifact projection differs')
        observed_sessions.extend(sessions)
        commitments.extend(hashes)
        projected.append({'sequence': cell['sequence'], 'item_sha256': digest(cell['item_id']), 'arm_id': cell['arm_id'],
                          'repetition': cell['repetition'], 'source_kind': cell['source_kind'], 'kind': arm['kind'],
                          'manifest_sha256': cell['run_binding_sha256'], 'condition_sha256': digest(config),
                          'source_sha256': sample['inputs']['source.md']['sha256'], 'leaves': leaves,
                          'hbq_quality_cohort': ('original_1.0.0' if version == 3 else 'v8_1.2.1') if arm['kind'] == 'hbq' else None,
                          'accepted_units': units, 'rejected_attempts': rejected, 'commitments': proof})
    historical = summary['fresh_session_commitment']
    require(len(observed_sessions) == historical['source_record_count'] == historical['session_id_record_count']
            == len(set(observed_sessions)) == historical['unique_observed_session_count']
            and historical['unavailable_record_count'] == 0
            and sha('\n'.join(sorted(observed_sessions)).encode('utf-8')) == historical['observed_session_sha256']
            and len(commitments) == historical['artifact_commitment_count']
            and sha('\n'.join(sorted(commitments)).encode('utf-8')) == historical['artifact_commitments_sha256'],
            'Historical 609/613 projection differs')
    predecessor = assets['predecessor']
    failure = predecessor['sequence77_failure']
    require(failure['accepted'] is False and predecessor['frozen_contract_sha256'] == recipe['assets']['frozen'][1],
            'Failed predecessor acceptance/frozen binding differs')
    failed_base = recipe['failed_prefix_root']
    for entry in failure['artifact_list']['files']:
        inputs.raw(failed_base + '/' + entry['path'], entry['sha256'], entry['bytes'])
    failed = [rejected_attempt(inputs, failed_base + f'/attempts/rejected-{n:04d}.json', 77, n,
                               'original_failed_prefix')[0] for n in range(1, 4)]
    unresolved = [{'scope': entry['scope'], 'disposition': 'unresolved_historical_controller',
                   'source_sha256': recipe['assets'][entry['asset']][1], 'accepted_units_added': 0,
                   'provider_contact_count': None} for entry in recipe['unresolved']]
    observed = aggregate(projected, failed, unresolved, historical)
    require(all(observed[k] == v for k, v in recipe['expected_counts'].items()), 'Pinned census aggregate differs')
    artifacts = sorted(inputs.artifacts.values(), key=lambda r: r['source_locator'])
    report = {'schema_version': 1, 'scope': recipe['scope'], 'status': 'partial_program_census',
              'provider_calls_made': 0, 'new_provider_votes': 0, 'recipe_sha256': digest(recipe),
              'implementation_sha256': sha(Path(__file__).read_bytes()), 'common_census_sha256': recipe['common_census_sha256'],
              'observed': observed, 'unresolved_dispositions': unresolved,
              'verified_artifact_count': len(artifacts), 'verified_artifact_bytes': sum(a['source_bytes'] for a in artifacts),
              'native_join_sha256': digest(projected), 'verified_artifact_index_sha256': digest(artifacts),
              'limitations': ['Counts cover the pinned multisample lineage only; replacement and adoption never add independent studies',
                             'Reported sessions and physical messages are distinct; complete provider-contact counts remain unverified',
                             'V3 sequence178 and missing181 r1 remain unresolved; missing outputs or PIDs prove no contact conclusion',
                             'Provider/model/runtime attestation, modern strict import, semantic normalization reexecution and full-score replay remain unverified',
                             'Historical static schema/prompt fingerprints are retained; changed or unavailable current locators do not reconstruct their original bytes',
                             'Only counts, hashes and source locators are released; prose, rationales, native scores and human labels are excluded']}
    ledger = {'schema_version': 1, 'private_task_local_only': True, 'report_sha256': digest(report),
              'cells': projected, 'failed_prefix_attempts': failed, 'unresolved_dispositions': unresolved, 'artifacts': artifacts}
    return report, ledger


def write(path, value):
    with path.open('xb') as handle:
        handle.write(canonical(value) + b'\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--output-root', type=Path, required=True)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    output, source = args.output_root.resolve(), args.source_root.resolve()
    recipe_raw = (HERE / 'recipe.json').read_bytes()
    recipe = json.loads(recipe_raw)
    input_roots = [Inputs(source).path(locator(r, recipe)) for r in [*recipe['input_roots'], recipe['repository_root']]]
    require(not output.exists() and not output.is_relative_to(REPOSITORY) and not REPOSITORY.is_relative_to(output)
            and all(not output.is_relative_to(r) and not r.is_relative_to(output) for r in input_roots),
            'Census output must be fresh and outside repository and exact retained input roots')
    if not args.dry_run:
        output.mkdir(parents=True, exist_ok=False)
        for name, raw in [('recipe.json', recipe_raw), ('census.py', Path(__file__).read_bytes()), ('common-census.py', COMMON_PATH.read_bytes())]:
            with (output / name).open('xb') as handle:
                handle.write(raw)
        write(output / 'invocation.json', {'scope': recipe['scope'], 'recipe_file_sha256': sha(recipe_raw),
              'implementation_sha256': sha(Path(__file__).read_bytes()), 'source_root': str(source), 'provider_calls_made': 0})
    try:
        report, ledger = build_census(source, recipe)
        if not args.dry_run:
            write(output / 'census.json', report)
            write(output / 'private-slots.json', ledger)
            write(output / 'terminal.json', {'state': 'completed_provider_free_join', 'report_sha256': digest(report), 'private_ledger_sha256': digest(ledger)})
        print(json.dumps({'dry_run': args.dry_run, 'report_sha256': digest(report), 'private_ledger_sha256': digest(ledger),
                          'observed': report['observed'], 'verified_artifact_count': report['verified_artifact_count'], 'status': report['status']}, sort_keys=True))
        return 0
    except (OSError, ValueError, KeyError, TypeError) as error:
        if not args.dry_run:
            write(output / 'terminal.json', {'state': 'failed_join_pending', 'error_class': type(error).__name__})
        parser.exit(1, f'Census E pending: {type(error).__name__}: {error}\n')


if __name__ == '__main__':
    raise SystemExit(main())
