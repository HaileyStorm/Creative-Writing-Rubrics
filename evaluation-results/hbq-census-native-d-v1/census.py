"""Provider-free native request/leaf join for pre-batch35 LAMP lineages."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPOSITORY = HERE.parent.parent
COMMON_PATH = HERE.parent / 'hbq-evidence-census-pass-c-v1' / 'census.py'
_spec = importlib.util.spec_from_file_location('native_census_d_common', COMMON_PATH)
_common = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_common)
Inputs, require, sha, canonical, digest = (_common.Inputs, _common.require, _common.sha, _common.canonical, _common.digest)
VERDICTS = _common.VERDICTS


def unique(rows, key):
    result = {row[key]: row for row in rows}
    require(len(rows) == len(result), 'Duplicate retained identity')
    return result


def source_artifacts(inputs, freeze, prefix, selected_hashes):
    variants = [variant for entry in freeze['selected'] for variant in entry.get('variants', [entry])]
    known = set()
    for variant in variants:
        source_hash = variant['artifact_sha256']
        if source_hash in selected_hashes:
            inputs.raw(prefix + '/' + variant['artifact_path'], source_hash, variant['artifact_bytes'])
            known.add(source_hash)
    require(known == selected_hashes, 'Planned source missing from frozen artifacts')


def packet_receipts(inputs, lineage, manifest_path, manifest_sha):
    root = str(Path(manifest_path).parent).replace('\\', '/')
    first, last, step = lineage['wave_starts']
    receipts = []
    seen = set()
    for start in range(first, last + 1, step):
        base = lineage.get('wave_root', root) + '/' + lineage['wave_pattern'].format(endpoint=lineage['endpoint'], start=start)
        result_raw = inputs.raw(base + '.result.json')
        result = json.loads(result_raw)
        intent = inputs.read(base + '.intent.json', result['intent_sha256'])
        numbers = list(range(start, min(start + lineage['wave_size'], lineage['wave_end'] + 1)))
        require(intent['ordinals'] == numbers and [r['ordinal'] for r in result['terminals']] == numbers
                and intent['manifest_sha256'] == lineage.get('wave_manifest_sha256', manifest_sha)
                and ('ordinals' not in result or result['ordinals'] == numbers)
                and ('endpoint' not in intent or intent['endpoint'] == lineage['endpoint']),
                'Wave order/condition commitment differs')
        for receipt in result['terminals']:
            require(receipt['ordinal'] not in seen and isinstance(receipt.get('terminal_sha256'), str),
                    'Duplicate or missing retained packet terminal')
            seen.add(receipt['ordinal'])
            receipts.append({**receipt, 'wave_result_sha256': sha(result_raw), 'wave_intent_sha256': result['intent_sha256']})
    return root, receipts


def stopped_lineage(terminal, lineage, receipts):
    endpoint = terminal.get(lineage['endpoint'])
    if endpoint is None:
        endpoint = unique(terminal['endpoints'], 'endpoint')[lineage['endpoint']]
    require(endpoint['state'] == 'stopped_nonaccepted_wave'
            and endpoint['wave_start'] == lineage['wave_starts'][1]
            and any(r['state'] != 'accepted' for r in receipts
                    if r['ordinal'] >= endpoint['wave_start']),
            'Stopped lineage disposition/wave differs')


def native_sol(inputs, base, evidence, reconciled):
    completion = inputs.read(base + '/process-completion.json', evidence['process_completion_sha256'])
    event_hash = completion.get('events_sha256', completion.get('event_sha256'))
    event_bytes = completion.get('events_bytes', completion.get('event_bytes'))
    require(isinstance(event_hash, str) and isinstance(event_bytes, int), 'Missing native event commitment')
    raw = inputs.raw(base + '/events.jsonl', event_hash, event_bytes)
    events = [json.loads(line) for line in raw.splitlines() if line.strip()]
    threads = [event.get('thread_id') for event in events if event.get('type') == 'thread.started']
    native = evidence['native_identity']
    require(len(threads) == 1 and isinstance(threads[0], str) and threads[0]
            and native['thread_id'] == threads[0] and native['turn_completed'] is True
            and native['tool_events'] == 0 and native['native_event_count'] == len(events)
            and sum(event.get('type') == 'turn.completed' for event in events) == 1,
            'Native Sol identity/completion differs')
    final = inputs.raw(base + '/final.json', completion['final_sha256'], completion['final_bytes'])
    require(sha(final) == evidence['final_sha256'], 'Native final commitment differs')
    messages = [e['item']['text'] for e in events if e.get('type') == 'item.completed'
                and e.get('item', {}).get('type') == 'agent_message']
    require(len(messages) == 1 and messages[0].rstrip('\r\n') == final.decode('utf-8').rstrip('\r\n'),
            'Native event/final response differs')
    if reconciled:
        require(completion['state'] == evidence['original_process_exit_state']
                and completion['exit_code'] is None and evidence['events_sha256'] == event_hash
                and evidence['provider_calls_by_reconciliation'] == 0,
                'Unknown-exit reconciliation differs')
    else:
        require(completion['state'] == 'exited' and completion['exit_code'] == 0, 'Native process completion differs')
    return sha(threads[0].encode('utf-8')), json.loads(final), {
        'native_events_sha256': event_hash, 'native_final_sha256': sha(final),
        'process_completion_sha256': evidence['process_completion_sha256'],
        'process_state': completion['state'], 'process_exit_code': completion['exit_code']}


def native_grok(inputs, base, evidence, started, row, accepted):
    outcome = inputs.read(base + '/broker-outcome.json', evidence['broker_outcome_sha256'])
    if not accepted:
        require(outcome['state'] == 'ambiguous' and outcome['result'] is None,
                'Ambiguous broker disposition conflicts with result')
        return None, None, {'broker_outcome_sha256': evidence['broker_outcome_sha256']}
    require(outcome['state'] == 'completed' and outcome['failure'] is None, 'Accepted broker disposition differs')
    result = outcome['result']
    native, runtime, envelope = evidence['native_identity'], result['runtime'], result['native_envelope_artifact']
    require(native['session_id_hash'] == sha(started['session_id'].encode('utf-8')) == runtime['session_id_hash']
            and native['request_id_hash'] == runtime['request_id_hash']
            and native['observed_turns'] == runtime['observed_turns']
            and envelope['sha256'] == evidence['native_envelope_sha256'] == runtime['envelope_hash']
            and runtime['execution_contract']['staged_prompt_sha256'] == row['prompt_sha256'],
            'Grok native identity/envelope/prompt differs')
    if 'prompt_bytes' in row:
        require(runtime['execution_contract']['staged_prompt_byte_length'] == row['prompt_bytes'],
                'Grok staged prompt size differs')
    return native['request_id_hash'], result['output'], {
        'broker_outcome_sha256': evidence['broker_outcome_sha256'],
        'native_envelope_sha256': envelope['sha256'], 'native_envelope_materialized_here': False,
        'retained_runtime_sha256': digest(runtime)}


def project_packet(inputs, scope, row, passed, lineage, root, receipt, manifest, manifest_sha, plan_sha):
    ordinal, endpoint = row['ordinal'], lineage['endpoint']
    base = root + '/' + lineage['attempt_pattern'].format(endpoint=endpoint, ordinal=ordinal)
    terminal = inputs.read(base + '/terminal.json', receipt['terminal_sha256'])
    start_raw = inputs.raw(base + '/attempt-start.json')
    started = json.loads(start_raw)
    require(started['ordinal'] == terminal['ordinal'] == ordinal and started['attempt_number'] == 1
            and terminal['state'] == receipt['state'] and started['session_id'] == terminal['session_id']
            and started['manifest_sha256'] == terminal['manifest_sha256'] == manifest_sha
            and started['plan_sha256'] == terminal['plan_sha256'] == plan_sha
            and started['prompt_sha256'] == row['prompt_sha256'] and started['schema_sha256'] == row['schema_sha256'],
            f'Packet attempt/condition/terminal differs: {scope}/{endpoint}/{ordinal}')
    contact = inputs.read(base + '/contact-admission.json')
    require(contact['ordinal'] == ordinal and contact['session_id'] == started['session_id']
            and (contact.get('disclosure_sha256') == lineage.get('contact_disclosure_sha256', manifest['disclosure_sha256'])
                 or ('disclosure_sha256' not in contact and contact.get('manifest_sha256') == manifest_sha)),
            f'Contact admission differs: {scope}/{endpoint}/{ordinal}')
    evidence, reconciled = terminal, False
    if 'reconciliations' in lineage and lineage['reconciliations'][0] <= ordinal <= lineage['reconciliations'][1]:
        evidence = inputs.read(base + '/reconciliation.json')
        require(terminal['state'] == 'unknown_exit_requires_reconciliation' and evidence['state'] == 'accepted'
                and evidence['ordinal'] == ordinal and evidence['plan_sha256'] == plan_sha
                and evidence['manifest_sha256'] == manifest_sha and evidence['terminal_sha256'] == receipt['terminal_sha256']
                and evidence['attempt_start_sha256'] == sha(start_raw), 'Reconciliation predecessor differs')
        reconciled = True
    accepted = evidence['state'] == 'accepted'
    require(accepted or terminal['state'] == 'ambiguous', 'Unsupported retained disposition remains pending')
    if 'ambiguous' in lineage:
        require((ordinal in lineage['ambiguous']) == (not accepted), 'Pinned ambiguity inventory differs')
    if endpoint == 'sol':
        require(started['model'] == contact['model'] == 'gpt-6-sol'
                and started['effort'] == contact['effort'] == 'xhigh', 'Retained Sol requested settings differ')
        identity, response, native_lineage = native_sol(inputs, base, evidence, reconciled)
        inputs.raw(base + '/prompt.txt', row['prompt_sha256'], row.get('prompt_bytes'))
        inputs.raw(base + '/schema.json', row['schema_sha256'], row.get('schema_bytes'))
    else:
        route = manifest.get('grok_route_sha256', manifest.get('route_sha256'))
        require(contact['route_sha256'] == route, 'Grok contact route differs')
        identity, response, native_lineage = native_grok(inputs, base, evidence, started, row, accepted)
    leaves = []
    if accepted:
        values, native_values = evidence['verdicts'], response['verdicts']
        require([v['question_id'] for v in values] == row['question_ids']
                and [(v['question_id'], v['verdict']) for v in values]
                == [(v['question_id'], v['verdict']) for v in native_values], 'Native leaf order/state differs')
        for position, value in enumerate(values):
            require(value['artifact_id'] == row['sample_id'] and value['bundle_id'] == 'prose.short_form'
                    and value['verdict'] in VERDICTS, 'Normalized leaf identity/state differs')
            leaves.append({'position': position, 'question_id': value['question_id'], 'verdict': value['verdict'],
                           'native_row_sha256': digest(native_values[position]), 'normalized_row_sha256': digest(value)})
    proof = {**native_lineage, 'root_name': root, 'manifest_sha256': manifest_sha,
             'terminal_sha256': receipt['terminal_sha256'], 'original_terminal_state': terminal['state'],
             'attempt_start_sha256': sha(start_raw), 'contact_admission_sha256': inputs.artifacts[base + '/contact-admission.json']['source_sha256'],
             'contact_disclosure_directly_attested': 'disclosure_sha256' in contact,
             'contact_disclosure_sha256': contact.get('disclosure_sha256'),
             'manifest_disclosure_sha256': manifest['disclosure_sha256'],
             'wave_result_sha256': receipt['wave_result_sha256'], 'wave_intent_sha256': receipt['wave_intent_sha256'],
             'reconciliation_sha256': inputs.artifacts[base + '/reconciliation.json']['source_sha256'] if reconciled else None,
             'response_sha256': digest(response) if accepted else None,
             'normalized_verdicts_sha256': digest(evidence['verdicts']) if accepted else None}
    return {'scope': scope, 'endpoint': endpoint, 'ordinal': ordinal,
            'sample_sha256': digest(row['sample_id']), 'group_sha256': digest(passed.get('group_id_local_only')),
            'source_sha256': passed['source_sha256'], 'repeat_index': passed.get('repeat_index_local_only'),
            'prompt_sha256': row['prompt_sha256'], 'schema_sha256': row['schema_sha256'],
            'planned_schema_sha256': row.get('original_schema_sha256', row['schema_sha256']),
            'planned_question_ids_sha256': digest(row['question_ids']), 'planned_question_count': len(row['question_ids']),
            'client_session_sha256': sha(started['session_id'].encode('utf-8')), 'native_identity_sha256': identity,
            'accepted': accepted, 'disposition': 'accepted_reconciled' if reconciled else terminal['state'],
            'unknown_exit_preserved': reconciled, 'no_resend': True, 'leaves': leaves,
            'lineage': proof, 'lineage_sha256': digest(proof)}


def validate_slots(slots):
    keys, native, leaf_keys = set(), set(), set()
    for slot in slots:
        key = (slot['scope'], slot['endpoint'], slot['ordinal'])
        require(key not in keys, 'Overlapping original/suffix logical packet; duplicate votes forbidden')
        keys.add(key)
        if slot['accepted']:
            require(slot['native_identity_sha256'] not in native, 'Duplicate accepted native identity')
            native.add(slot['native_identity_sha256'])
            for leaf in slot['leaves']:
                key = (slot['scope'], slot['endpoint'], slot['sample_sha256'], leaf['question_id'])
                require(key not in leaf_keys, 'Duplicate leaf in one pass')
                leaf_keys.add(key)


def aggregate(slots, scopes):
    result = []
    for scope in scopes:
        selected = [s for s in slots if s['scope'] == scope['id']]
        endpoints = []
        for endpoint in sorted({s['endpoint'] for s in selected}):
            rows = [s for s in selected if s['endpoint'] == endpoint]
            leaves = [v for s in rows for v in s['leaves']]
            endpoints.append({'endpoint': endpoint, 'planned_packets': len(rows),
                              'accepted_packets': sum(s['accepted'] for s in rows), 'dispositions': dict(Counter(s['disposition'] for s in rows)),
                              'native_leaf_rows': len(leaves), 'leaf_states': dict(Counter(v['verdict'] for v in leaves)),
                              'unknown_exit_reconciled_packets': sum(s.get('unknown_exit_preserved', False) for s in rows),
                              'accepted_native_identifiers': len({s['native_identity_sha256'] for s in rows if s['accepted']}),
                              'accepted_sample_identifiers': len({s['sample_sha256'] for s in rows if s['accepted']}),
                              'distinct_source_hashes': len({s['source_sha256'] for s in rows})})
        result.append({'scope': scope['id'], 'replaces_census_a_declaration': scope.get('replaces_census_a'),
                       'counting_rule': 'replace earlier declaration with joined evidence; never append a duplicate study',
                       'declared_confirmation_not_attempted': scope.get('declared_confirmation_not_attempted', 0), 'endpoints': endpoints})
    return {'scopes': result, 'native_leaf_rows': sum(len(s['leaves']) for s in slots),
            'accepted_packets': sum(s['accepted'] for s in slots), 'planned_packet_slots': len(slots),
            'dispositions': dict(Counter(s['disposition'] for s in slots)),
            'independent_work_count': None, 'physical_provider_contact_count': None}


def build_census(control_root, recipe):
    require(sha(COMMON_PATH.read_bytes()) == recipe['common_census_sha256'], 'Common census utility pin differs')
    inputs = Inputs(Path(control_root))
    for path, pin, size in recipe.get('metadata_schema_basis', []):
        inputs.raw(path, pin, size)
    data = {name: json.loads(inputs.raw(path, pin, size)) for name, (path, pin, size) in recipe['assets'].items()}
    slots, contexts = [], []
    for scope in recipe['scopes']:
        plan, freeze = data[scope['plan']], data[scope['source']]
        plan_path, plan_sha, _ = recipe['assets'][scope['plan']]
        require(plan['source_freeze_sha256'] == recipe['assets'][scope['source']][1], 'Source/plan freeze binding differs')
        requests, passes = unique(plan['requests'], 'ordinal'), unique(plan['passes'], 'sample_id')
        first, last = scope['selected_ordinals']
        require(set(range(first, last + 1)) <= requests.keys(), 'Selected planned ordinal missing')
        selected_sources = {passes[requests[n]['sample_id']]['source_sha256'] for n in range(first, last + 1)}
        source_prefix = str(Path(recipe['assets'][scope['source']][0]).parent).replace('\\', '/')
        source_artifacts(inputs, freeze, source_prefix, selected_sources)
        if 'selection' in scope:
            selection_sha = recipe['assets'][scope['selection']][1]
            require(plan['selection_sha256'] == selection_sha, 'Selection condition binding differs')
        condition = {key: plan.get(key) for key in ('bundle_id', 'artifact_kind', 'declared_scope', 'completion_status',
                     'brief', 'selected_modules', 'question_ids', 'runtime_pins', 'source_freeze_sha256', 'selection_sha256')}
        contexts.append({'scope': scope['id'], 'plan_sha256': plan_sha, 'condition_commitment_sha256': digest(condition),
                         'runtime_pins_sha256': digest(plan['runtime_pins']), 'current_runtime_equivalence_verified': False})
        seen = defaultdict(set)
        for lineage in scope['lineages']:
            manifest = data[lineage['manifest']]
            manifest_path, manifest_sha, _ = recipe['assets'][lineage['manifest']]
            require(manifest.get('plan_sha256', manifest.get('confirmation_plan_sha256')) == plan_sha, 'Manifest plan binding differs')
            if lineage.get('wave_manifest'):
                continuation = data[lineage['wave_manifest']]
                continuation_path, continuation_sha, _ = recipe['assets'][lineage['wave_manifest']]
                prior = continuation['predecessor'][lineage['endpoint']]
                prefix_slots = [s for s in slots if s['scope'] == scope['id'] and s['endpoint'] == lineage['endpoint']]
                require(continuation['source_plan_sha256'] == plan_sha
                        and prior['manifest_sha256'] == manifest_sha
                        and prior['collector_sha256'] == manifest['runner_sha256']
                        and prior['terminal_chain_sha256'] == sha(canonical([s['lineage']['terminal_sha256'] for s in prefix_slots]) + b'\n')
                        and prior['reconciliation_chain_sha256'] == sha(canonical([s['lineage']['reconciliation_sha256'] for s in prefix_slots
                                                                                   if s['unknown_exit_preserved']]) + b'\n')
                        and continuation[lineage['endpoint'] + '_suffix'] == [lineage['wave_starts'][0], last]
                        and continuation['retry_or_resend_authority'] is False, 'Panel continuation predecessor differs')
                continuation_terminal = data[lineage['wave_terminal']]
                require(continuation_terminal['manifest_sha256'] == continuation_sha
                        and unique(continuation_terminal['endpoints'], 'endpoint')[lineage['endpoint']]['state'] == 'all_suffix_attempted',
                        'Panel continuation terminal differs')
                lineage = {**lineage, 'wave_root': str(Path(continuation_path).parent).replace('\\', '/'),
                           'wave_manifest_sha256': continuation_sha}
            if lineage.get('predecessor_manifest'):
                require(manifest['original_manifest_sha256'] == recipe['assets'][lineage['predecessor_manifest']][1]
                        and manifest['original_terminal_sha256'] == recipe['assets'][lineage['predecessor_terminal']][1],
                        'Suffix predecessor binding differs')
            if lineage.get('contact_manifest'):
                contact_manifest = data[lineage['contact_manifest']]
                require(manifest['original_manifest_sha256'] == recipe['assets'][lineage['contact_manifest']][1]
                        and manifest['disclosure_sha256'] == recipe['assets'][lineage['manifest_disclosure']][1]
                        and contact_manifest['disclosure_sha256'] == recipe['assets'][lineage['contact_disclosure']][1],
                        'Original-contact/suffix-preparation disclosure binding differs')
                lineage = {**lineage, 'contact_disclosure_sha256': contact_manifest['disclosure_sha256']}
            if lineage.get('root_terminal'):
                terminal = data[lineage['root_terminal']]
                require(terminal['manifest_sha256'] == manifest_sha, 'Root terminal manifest binding differs')
                if scope.get('declared_confirmation_not_attempted'):
                    require(terminal['confirmation_requests_attempted'] == 0, 'Confirmation disposition declaration differs')
                if lineage.get('predecessor_terminal'):
                    require(terminal['original_terminal_sha256'] == recipe['assets'][lineage['predecessor_terminal']][1]
                            and terminal['ordinal_28_resend_attempted'] is False, 'Suffix stop/predecessor differs')
            root, receipts = packet_receipts(inputs, lineage, manifest_path, manifest_sha)
            if scope.get('declared_confirmation_not_attempted'):
                stopped_lineage(terminal, lineage, receipts)
            for receipt in receipts:
                ordinal = receipt['ordinal']
                require(first <= ordinal <= last and ordinal not in seen[lineage['endpoint']], 'Original/suffix ordinal overlap')
                seen[lineage['endpoint']].add(ordinal)
                row = requests[ordinal]
                inputs.raw(str(Path(plan_path).parent / row['prompt_path']).replace('\\', '/'), row['prompt_sha256'], row.get('prompt_bytes'))
                inputs.raw(str(Path(plan_path).parent / row['schema_path']).replace('\\', '/'), row['schema_sha256'], row.get('schema_bytes'))
                if scope.get('schema_projection'):
                    projection = data[scope['schema_projection']]
                    projection_path, projection_sha, _ = recipe['assets'][scope['schema_projection']]
                    projected = unique(projection['records'], 'ordinal')[ordinal]
                    require(projection['source_plan_sha256'] == plan_sha and manifest['schema_projection_sha256'] == projection_sha
                            and projected['original_sha256'] == row['schema_sha256']
                            and projected['question_ids'] == row['question_ids'], 'Endpoint schema projection binding differs')
                    inputs.raw(str(Path(projection_path).parent / projected['path']).replace('\\', '/'), projected['projected_sha256'])
                    row = {**row, 'original_schema_sha256': row['schema_sha256'], 'schema_sha256': projected['projected_sha256']}
                slots.append(project_packet(inputs, scope['id'], row, passes[row['sample_id']], lineage, root,
                                            receipt, manifest, manifest_sha, plan_sha))
        for endpoint, observed in seen.items():
            missing = set(range(first, last + 1)) - observed
            require(not missing or scope.get('declared_confirmation_not_attempted'), 'Missing packet without stopped-lineage disposition')
            if missing:
                require(missing == set(range(max(observed) + 1, last + 1)), 'Stopped lineage has an internal gap')
            for ordinal in sorted(missing):
                row, passed = requests[ordinal], passes[requests[ordinal]['sample_id']]
                slots.append({'scope': scope['id'], 'endpoint': endpoint, 'ordinal': ordinal,
                              'sample_sha256': digest(row['sample_id']), 'source_sha256': passed['source_sha256'],
                              'accepted': False, 'disposition': 'unattempted_after_retained_stop', 'leaves': [], 'no_resend': True,
                              'native_identity_sha256': None, 'stop_basis': 'pinned root terminal and exact contiguous wave inventory'})
    validate_slots(slots)
    metadata = []
    repo_inputs = Inputs(REPOSITORY)
    for path, pin, size, disposition in recipe.get('repository_metadata', []):
        value = json.loads(repo_inputs.raw(path, pin, size))
        if disposition == 'qpc24_pending_freeze':
            require(value['status'] == 'FROZEN_PROVIDER_FREE_PENDING_INDEPENDENT_REVIEW'
                    and value['privacy']['provider_calls_made'] == 0, 'QPC24 pending-freeze status differs')
            metadata.append({'source_locator': path, 'source_sha256': pin, 'disposition': disposition,
                             'declared_positions': value['first_pass']['positions'], 'empirical_denominator_added': 0})
        else:
            metadata.append({'source_locator': path, 'source_sha256': pin, 'disposition': disposition,
                             'consolidation_provenance_sha256': value['completed_analysis_commitments']['consolidation_provenance_sha256'],
                             'empirical_denominator_added': 0})
    artifacts = sorted(inputs.artifacts.values(), key=lambda r: r['source_locator'])
    report = {'schema_version': 1, 'scope': recipe['scope'], 'status': 'partial_program_census',
              'provider_calls_made': 0, 'new_provider_votes': 0, 'recipe_sha256': digest(recipe),
              'implementation_sha256': sha(Path(__file__).read_bytes()), 'common_census_sha256': recipe['common_census_sha256'],
              'observed': aggregate(slots, recipe['scopes']), 'conditions': contexts, 'nonempirical_dispositions': metadata,
              'verified_artifact_count': len(artifacts), 'verified_artifact_bytes': sum(r['source_bytes'] for r in artifacts),
              'native_request_leaf_join_sha256': digest(slots), 'verified_artifact_index_sha256': digest(artifacts),
              'limitations': ['This join replaces panel/batch2 A declarations; source/pass/endpoint labels are not independent studies',
                              'Native identity and retained envelope commitments do not establish complete physical-contact counts or modern full-contract attestation',
                              'Confirmation collection, batch4/batch6, other LAMP pilots, multisample native roots and historical failed-predecessor contacts remain pending',
                              'QPC24 freeze contributes no empirical rows; raw prose, rationales and human preferences are not exported']}
    ledger = {'schema_version': 1, 'private_task_local_only': True, 'report_sha256': digest(report),
              'slots': slots, 'artifacts': artifacts, 'repository_metadata_artifacts': list(repo_inputs.artifacts.values())}
    return report, ledger


def write(path, value):
    with path.open('xb') as handle:
        handle.write(canonical(value) + b'\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--control-root', type=Path, required=True)
    parser.add_argument('--output-root', type=Path, required=True)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    output, control = args.output_root.resolve(), args.control_root.resolve()
    require(not output.exists() and not output.is_relative_to(REPOSITORY) and not REPOSITORY.is_relative_to(output)
            and not output.is_relative_to(control) and not control.is_relative_to(output),
            'Census output must be fresh and outside repository and retained control inputs')
    recipe_raw = (HERE / 'recipe.json').read_bytes()
    recipe = json.loads(recipe_raw)
    if not args.dry_run:
        output.mkdir(parents=True, exist_ok=False)
        with (output / 'recipe.json').open('xb') as handle:
            handle.write(recipe_raw)
        with (output / 'census.py').open('xb') as handle:
            handle.write(Path(__file__).read_bytes())
        with (output / 'common-census.py').open('xb') as handle:
            handle.write(COMMON_PATH.read_bytes())
        write(output / 'invocation.json', {'scope': recipe['scope'], 'recipe_file_sha256': sha(recipe_raw),
              'implementation_sha256': sha(Path(__file__).read_bytes()), 'provider_calls_made': 0})
    try:
        report, ledger = build_census(control, recipe)
        if not args.dry_run:
            write(output / 'census.json', report)
            write(output / 'private-slots.json', ledger)
            write(output / 'terminal.json', {'state': 'completed_provider_free_join', 'report_sha256': digest(report), 'private_ledger_sha256': digest(ledger)})
        print(json.dumps({'dry_run': args.dry_run, 'report_sha256': digest(report), 'private_ledger_sha256': digest(ledger),
                          'observed': report['observed'], 'nonempirical_dispositions': report['nonempirical_dispositions'],
                          'verified_artifact_count': report['verified_artifact_count'], 'status': report['status']}, sort_keys=True))
        return 0
    except (OSError, ValueError, KeyError, TypeError) as error:
        if not args.dry_run:
            write(output / 'terminal.json', {'state': 'failed_join_pending', 'error_class': type(error).__name__})
        parser.exit(1, f'Census D pending: {type(error).__name__}: {error}\n')


if __name__ == '__main__':
    raise SystemExit(main())
