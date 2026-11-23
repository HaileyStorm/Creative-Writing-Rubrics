"""Provider-free census of historical V14 pilot receipt and preparation metadata.

Whitelisted JSON projection skips targets, scores, prompts, commands, payload
values and response bodies. Three retained scopes stay separate; absence never
makes a historical request safe to resend. No original study is executed.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
HELPER = HERE / 'census_train_v14_metadata.py'
HELPER_SHA = 'b07a1899ac2b75e9eb3a229a0c151f546f13e8a5ff7541c77c7c577ca8684975'
POLICY = 'historical_v14_pilot_receipt_preparation_metadata_v1'
STUDY = 'hbq-human-alignment-optimizer-v14-dspy-train-pilot-v1'
SOL_STUDY = 'hbq-human-alignment-optimizer-v14-dspy-train-pilot-sol-v1'
GROK_SHA = '4446c2b3e1472039b2aa0c607cfe84656aa5504d3fe37ae428945a1f7b62fc3f'
SOL_SHA = 'ac84ce7af8797b7e19feb79ec4026a4e68ae7f973e70e7e851cb70d9886c27b2'
CONTRACT_SHA = 'd92013a659f494547053d2737459a7715247894b113f60669b2fdf761ff2e8b3'
SCOPES = {'grok_receipts': ('grok', 'receipt_backed'), 'sol_receipts': ('sol', 'receipt_backed'),
          'sol_preparations': ('sol', 'preparation_only')}
PREPARATION_FILES = ('prepared.json', 'response-schema.json')
ABSENT_FILES = ('execution-receipt.json', 'effective-settings.json', 'launch-intent.json')
SOURCE_ROLES = {'schedule', 'grok_code', 'sol_code', 'study_contract', 'public_provenance',
                'public_result', 'public_readme', 'registry_v8', 'shared_metadata_helper', 'lexical_projector'}

def require(ok, message):
    if not ok:
        raise ValueError(message)

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def canonical(value):
    return (json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False)+'\n').encode()

def plain(path):
    require(path.resolve() == path, 'Canonical source/output path required')
    for p in (path, *path.parents):
        if p.exists():
            require(not getattr(p.lstat(), 'st_file_attributes', 0) & 0x400 and not p.is_symlink(), 'Reparse/link path refused')

def path_for(pin, roots):
    rel = Path(pin['locator'])
    require(not rel.is_absolute() and '..' not in rel.parts, 'Plain root-relative descriptor required')
    path = roots[pin['root']] / rel
    plain(path)
    require(path.is_relative_to(roots[pin['root']]), 'Source leaves declared root')
    return path

def checked(pin, roots):
    raw = path_for(pin, roots).read_bytes()
    require(len(raw) == pin['bytes'] and sha(raw) == pin['sha256'], 'Frozen source bytes differ')
    return raw

def shared():
    raw = HELPER.read_bytes()
    require(sha(raw) == HELPER_SHA, 'Pinned metadata helper differs')
    scope = {'__file__': str(HELPER), '__name__': 'pilot_metadata_helpers'}
    exec(compile(raw, str(HELPER), 'exec'), scope)
    return SimpleNamespace(**scope)

def schemas(base, endpoint):
    p, r, s = base.schemas(endpoint)
    if endpoint == 'sol':
        p['source'] = {k: True for k in ('v14_study_sha256', 'v14_schedule_sha256', 'recovered_descendant_sha256',
                                        'sol_role', 'endpoint_pooling', 'selection', 'promotion', 'generalization')}
    return p, r, s

def cell_id(candidate, item):
    return 'v14-train-' + sha(canonical({'candidate': candidate, 'item': item}))[:20]

def sol_id(source):
    return 'v14-train-sol-' + sha(canonical({'source_cell_id': source}))[:20]

def membership(recipe, roots):
    base = shared()
    for name, binding in recipe['scopes'].items():
        require(name in SCOPES and (binding['endpoint'], binding['kind']) == SCOPES[name], 'Scope roles differ')
        root = path_for(binding['root'], roots)
        require(root.is_dir() and {p.name for p in root.iterdir() if p.is_dir() and p.name != '.claims'} == set(binding['cells']),
                'Finite root membership differs')
        files = base.FILES if binding['kind'] == 'receipt_backed' else PREPARATION_FILES
        require(set(binding['absent_files']) == (set() if binding['kind'] == 'receipt_backed' else set(ABSENT_FILES)),
                'Frozen absence contract differs')
        for name, pins in binding['cells'].items():
            require(set(pins) == set(files), 'Finite file roles differ')
            for filename, pin in pins.items():
                require(path_for(pin, roots) == root / name / filename, 'Cell descriptor differs')
                checked(pin, roots)
            for filename in binding['absent_files']:
                path = root / name / filename
                plain(path)
                require(not path.exists(), 'Preparation-only receipt absence changed')
    return base

def run(recipe, roots):
    require(recipe['policy'] == POLICY and set(recipe['scopes']) == set(SCOPES) and
            set(recipe['sources']) == SOURCE_ROLES, 'Exact pilot recipe required')
    base = membership(recipe, roots)
    project = base.projector()
    sources = {k: checked(pin, roots) for k, pin in recipe['sources'].items()}
    for role, digest in [('grok_code', GROK_SHA), ('sol_code', SOL_SHA), ('study_contract', CONTRACT_SHA),
                         ('shared_metadata_helper', HELPER_SHA), ('lexical_projector', base.PROJECTOR_SHA)]:
        require(recipe['sources'][role]['sha256'] == digest, 'Original source/helper binding differs')
    public = json.loads(sources['public_provenance'])
    contract = json.loads(sources['study_contract'])
    require(public['study_id'] == STUDY.replace('-pilot-v1', '-pilot-result-v1') and
            public['source_commitments']['grok']['study_sha256'] == GROK_SHA and
            public['source_commitments']['sol']['study_sha256'] == SOL_SHA and
            contract['study_id'] == STUDY, 'Publication source binding differs')
    schedule = project(sources['schedule'], base.SCHEDULE)
    require(schedule['study_id'] == STUDY and schedule['endpoint'] == 'grok_primary' and
            schedule['schedule_sha256'] == recipe['semantic_schedule_sha256'] and
            schedule['geometry'] == contract['geometry'] == {'candidates': 2, 'grok_cells': 8, 'groups': 4,
                'items': 4, 'max_concurrency': 10, 'sol_cells': 0}, 'Schedule identity/geometry differs')
    cells = schedule['cells']
    groups = {g['prompt_group_id'] for g in schedule['groups']}
    require(len(cells) == 8 and [c['ordinal'] for c in cells] == list(range(1, 9)) and
            len({c['cell_id'] for c in cells}) == 8 and all(c['partition'] == 'train' for c in cells) and
            len(schedule['groups']) == len(groups) == 4 and all(g['partition'] == 'train' for g in schedule['groups']),
            'Frozen TRAIN membership differs')
    candidates = sorted({c['candidate_id'] for c in cells})
    item_sets = [{c['item_id'] for c in cells if c['candidate_id'] == k} for k in candidates]
    require(len(candidates) == 2 and item_sets[0] == item_sets[1] and len(item_sets[0]) == 4 and
            {c['prompt_group_id'] for c in cells} == groups and all(
                c['cell_id'] == cell_id(c['candidate_id'], c['item_id']) and
                c['endpoint_payload_sha256s'] == {'grok_primary': c['payload_sha256'], 'sol_later': c['payload_sha256']}
                for c in cells), 'Candidate/item/parity metadata differs')
    descendant = contract['recovered_descendant']
    descendant_cells = [c for c in cells if c['candidate_id'] == descendant['candidate_id']]
    require(len(descendant_cells) == 4 and all(c['candidate_profile_sha256'] ==
            public['candidate_lineage']['shared_profile_sha256'] == descendant['profile_sha256'] for c in cells) and
            all(c['candidate_sha256'] == descendant['candidate_sha256'] == public['candidate_lineage']['descendant_candidate_sha256'] and
                c['candidate_instruction_sha256'] == descendant['instruction_sha256'] ==
                public['candidate_lineage']['descendant_instruction_sha256'] for c in descendant_cells),
            'Published descendant/profile metadata differs')
    rows, ledger, identities, counts = [], [], {}, {}
    for scope_name, binding in sorted(recipe['scopes'].items()):
        endpoint, kind = SCOPES[scope_name]
        planned = {c['cell_id'] if endpoint == 'grok' else sol_id(c['cell_id']) for c in cells}
        require(set(binding['cells']) == planned, 'Scope schedule membership differs')
        p_spec, r_spec, s_spec = schemas(base, endpoint)
        identities[scope_name] = set()
        scope_rows = []
        for source in cells:
            name = source['cell_id'] if endpoint == 'grok' else sol_id(source['cell_id'])
            pins = binding['cells'][name]
            raw = {k: checked(pin, roots) for k, pin in pins.items()}
            ledger.extend(pins.values())
            prepared = project(raw['prepared.json'], p_spec)
            expected = {k: source[k] for k in base.CELL}
            expected['cell_id'] = name
            if endpoint == 'sol':
                expected.update(source_cell_id=source['cell_id'], payload_parity='v14_grok_schedule_exact_payload_bytes')
            expected_study = STUDY if endpoint == 'grok' else SOL_STUDY
            require(prepared['cell'] == expected and prepared['study_id'] == binding['study_id'] == expected_study and
                    prepared['process_launches'] == prepared['provider_calls_made'] == 0 and
                    prepared['response_schema_sha256'] == pins['response-schema.json']['sha256'] == recipe['response_schema_sha256'],
                    'Preparation/schema commitment differs')
            if endpoint == 'grok':
                require(prepared['schedule_sha256'] == schedule['schedule_sha256'] and
                        prepared['outbound_payload_sha256'] == source['payload_sha256'], 'Grok source schedule differs')
            else:
                require(prepared['source'] == {'v14_study_sha256': GROK_SHA,
                    'v14_schedule_sha256': schedule['schedule_sha256'],
                    'recovered_descendant_sha256': contract['recovered_descendant']['source_sha256'],
                    'sol_role': 'matched_train_measurement_on_v14_frozen_schedule', 'endpoint_pooling': 'forbidden',
                    'selection': 'none', 'promotion': 'none', 'generalization': 'none'} and
                    prepared['task_payload_sha256'] == source['payload_sha256'], 'Sol source/parity metadata differs')
            row = {'scope': scope_name, 'endpoint': endpoint, 'source_cell_id': source['cell_id'], 'cell_id': name,
                   'prepared': prepared, 'pins': pins, 'absent_files': binding['absent_files']}
            if kind == 'preparation_only':
                row.update(disposition='preparation_metadata_only_contact_unknown', receipt=None, settings=None,
                           identity_commitment_sha256=None, control_metadata_mismatches=[])
            else:
                receipt, settings = project(raw['execution-receipt.json'], r_spec), project(raw['effective-settings.json'], s_spec)
                require(receipt['cell'] == expected and receipt['study_id'] == expected_study and
                        receipt['process_launches'] == 1 and
                        receipt['effective_settings_sha256'] == pins['effective-settings.json']['sha256'] and
                        receipt['launch_intent_sha256'] == pins['launch-intent.json']['sha256'], 'Receipt cell/control hashes differ')
                identity_sha = sha(canonical(receipt['identity']))
                if endpoint == 'grok':
                    require(receipt['prepared_sha256'] == pins['prepared.json']['sha256'] and
                            receipt['payload_sha256'] == source['payload_sha256'] and
                            receipt['identity_sha256'] == identity_sha, 'Grok receipt binding differs')
                    keys = ('request_id', 'session_id')
                else:
                    require(receipt['response_schema_sha256'] == pins['response-schema.json']['sha256'] and
                            receipt['request_sha256'] == source['payload_sha256'], 'Sol receipt request/schema differs')
                    keys = ('thread_id', 'session_id')
                identity = tuple(receipt['identity'][k] for k in keys)
                require(all(isinstance(v, str) and v for v in identity) and identity not in identities[scope_name],
                        'Declared endpoint identity duplicate/missing')
                identities[scope_name].add(identity)
                controls = {'requested_model': receipt['identity']['requested_model'] == settings['requested_model'],
                            'prepared_tools': prepared['tools_enabled'] == settings['tools_enabled']}
                if endpoint == 'grok':
                    controls.update(reported_model=receipt['identity']['reported_model'] == settings['reported_model'],
                                    identity_tools=receipt['identity']['tools_enabled'] == settings['tools_enabled'])
                else:
                    controls.update(requested_effort=receipt['identity']['requested_reasoning_effort'] == settings['requested_reasoning_effort'],
                                    effective_model=receipt['identity']['effective_model'] == settings['local_effective_model'])
                mismatches = sorted(k for k, good in controls.items() if not good)
                row.update(receipt=receipt, settings=settings, identity_commitment_sha256=identity_sha,
                           control_metadata_mismatches=mismatches,
                           disposition='receipt_backed_metadata_control_mismatch' if mismatches else 'receipt_backed_metadata_only')
            rows.append(row)
            scope_rows.append(row)
        if kind == 'receipt_backed':
            require(all(len({v[i] for v in identities[scope_name]}) == 8 for i in (0, 1)), 'Endpoint identity reuse differs')
        counts[scope_name] = {'endpoint': endpoint, 'kind': kind, 'prepared_metadata_cells': 8,
            'receipt_backed_metadata_cells': 8 if kind == 'receipt_backed' else 0,
            'distinct_declared_identity_pairs': len(identities[scope_name]),
            'candidate_cells': dict(Counter(r['prepared']['cell']['candidate_id'] for r in scope_rows)),
            'control_metadata_mismatch_cells': sum(bool(r['control_metadata_mismatches']) for r in scope_rows)}
    by_scope = {name: {r['cell_id']: r for r in rows if r['scope'] == name} for name in SCOPES}
    # Compare every retained preparation binding; no request or response is executed.
    matching, raw_equal = 0, 0
    for name, prepared_row in by_scope['sol_preparations'].items():
        receipt_row = by_scope['sol_receipts'][name]
        require(prepared_row['prepared']['cell'] == receipt_row['prepared']['cell'] and
                prepared_row['prepared']['source'] == receipt_row['prepared']['source'], 'Cross-scope Sol logical membership differs')
        matching += 1
        raw_equal += prepared_row['pins']['prepared.json']['sha256'] == receipt_row['pins']['prepared.json']['sha256']
    ledger.extend(recipe['sources'].values())
    report = {'policy': POLICY, 'status': 'completed_metadata_only_census', 'partition': 'train',
        'items': 4, 'groups': 4, 'candidates': 2, 'planned_cells': 16, 'preparation_only_cells': 8,
        'logical_candidate_item_conditions': 8, 'scope_metadata_rows': 24, 'scopes': counts,
        'cross_scope_preparation_join': {'matching_logical_cells': matching, 'identical_prepared_raw_hashes': raw_equal,
            'different_prepared_raw_hashes': 8-raw_equal, 'retry_authority': False, 'physical_contact_relationship': 'unproven'},
        'source_pins': recipe['sources'], 'semantic_schedule_sha256': schedule['schedule_sha256'],
        'semantic_schedule_hash_recomputed': False, 'source_commitments_checked': len(ledger),
        'input_commitment_sha256': sha(canonical(ledger)), 'provider_calls': 0, 'new_votes': 0,
        'native_admission_replays': 0, 'semantic_admission_replays': 0, 'scoring_calls': 0, 'compiler_calls': 0,
        'tools_off_eligible_records': 0, 'capacity_released': 0, 'physical_contact_cardinality': None,
        'labels_opened': False, 'score_projections_opened': False, 'confirmation_opened': False,
        'candidate_promoted': False, 'full_goal_complete': False, 'published_aggregate_inventory_reconstructed': False,
        'limitations': ['Sixteen historical receipt metadata rows and eight separate preparation rows; no admitted or independent votes.',
            'Preparation-only receipt absence does not prove no contact, untouched work, safe retry or capacity release.',
            'Raw UTF8 JSON is scanned lexically, but excluded target/payload/response/score values are not decoded.',
            'Semantic schedule hash is joined, not recomputed; published original report/inventory serialization is not reconstructed.',
            'Historical identity and tool flags establish no physical-contact cardinality, current tools-disabled qualification or promotion.',
            'TRAIN pilot uses overlapping historical human-reference namespaces; no new humans or unused confirmation claim.']}
    return report, {'policy': POLICY, 'rows': rows, 'artifact_ledger': ledger}

def main(argv=None):
    sys.dont_write_bytecode = True
    require(not sys.flags.optimize, 'Non-optimized execution required')
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    for name in ('documents-root', 'control-root', 'recipe', 'output-root'):
        parser.add_argument('--'+name, type=Path, required=True)
    parser.add_argument('--recipe-sha256', required=True)
    args = parser.parse_args(argv)
    implementation = Path(__file__).read_bytes()
    roots = {'repository': REPO, 'documents': args.documents_root.absolute(), 'control': args.control_root.absolute()}
    for path in roots.values():
        plain(path)
    recipe_raw = args.recipe.read_bytes()
    require(sha(recipe_raw) == args.recipe_sha256, 'Recipe digest differs')
    recipe = json.loads(recipe_raw)
    output = args.output_root.absolute()
    plain(output)
    require(not output.exists() and output.is_relative_to(roots['control']) and not output.is_relative_to(REPO), 'Fresh private output required')
    paths = [path_for(p, roots) for p in recipe['sources'].values()]
    paths.extend(path_for(e['root'], roots) for e in recipe['scopes'].values())
    require(all(not output.is_relative_to(p if p.is_dir() else p.parent) and not p.is_relative_to(output) for p in paths)
            and not args.recipe.resolve().is_relative_to(output), 'Output overlaps source')
    report, private = run(recipe, roots)
    membership(recipe, roots)
    for pin in recipe['sources'].values():
        checked(pin, roots)
    require(args.recipe.read_bytes() == recipe_raw and Path(__file__).read_bytes() == implementation,
            'Recipe/implementation snapshot changed')
    plain(output)
    require(not output.exists(), 'Create-only destination changed')
    private_raw = canonical(private)
    report.update(implementation_sha256=sha(implementation), recipe_sha256=sha(recipe_raw), private_ledger_sha256=sha(private_raw))
    report_raw = canonical(report)
    terminal = {'policy': POLICY, 'state': 'completed', 'output_written': True, 'report_sha256': sha(report_raw),
        'private_ledger_sha256': sha(private_raw), 'implementation_sha256': sha(implementation), 'recipe_sha256': sha(recipe_raw),
        'planned_cells': 16, 'preparation_only_cells': 8, 'provider_calls': 0, 'new_votes': 0}
    output.mkdir(parents=True, exist_ok=False)
    for name, raw in [('report.json', report_raw), ('private-metadata-ledger.json', private_raw),
                      ('recipe.json', recipe_raw), ('census_v14_pilot_metadata.py', implementation), ('terminal.json', canonical(terminal))]:
        with (output/name).open('xb') as stream:
            stream.write(raw)
    print(json.dumps(terminal, sort_keys=True))

if __name__ == '__main__':
    main()
