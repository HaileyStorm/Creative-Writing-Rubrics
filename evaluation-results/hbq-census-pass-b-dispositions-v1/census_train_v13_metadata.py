"""Provider-free, metadata-only census of historical V13 remaining-TRAIN Grok.

Targets, scores, prompt/payload and native response containers are not decoded.
Reuse pinned lexical/metadata helpers; never execute the original study code.
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
POLICY = 'historical_v13_train_receipt_metadata_v1'
STUDY = 'hbq-human-alignment-optimizer-v13-train-expansion-v1'
CODE_SHA = 'f2b5a4c178cf2a7919b5dfd8c5ddde7bf5c1e0e9aa81a2f2f4d0bdd9b97c8261'
CONTRACT_SHA = 'f4868f88e001d07a02c5cf35b12b923c9fa8c53a0ce6010151b1142ad87495a9'
SCHEDULE_SHA = '2d66a311912e82f5cc1e4bb411e94493a22e6b0761da43ee6d580972a5d589db'

def require(ok, message):
    if not ok:
        raise ValueError(message)

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def canonical(value):
    return (json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False) + '\n').encode()

def shared():
    raw = HELPER.read_bytes()
    require(sha(raw) == HELPER_SHA, 'Pinned shared metadata helper differs')
    scope = {'__file__': str(HELPER), '__name__': 'v13_shared_metadata_helpers'}
    exec(compile(raw, str(HELPER), 'exec'), scope)
    return SimpleNamespace(**scope)

def plain(path):
    require(path.resolve() == path, 'Canonical source/output path required')
    for p in (path, *path.parents):
        if p.exists():
            require(not getattr(p.lstat(), 'st_file_attributes', 0) & 0x400 and not p.is_symlink(), 'Reparse/link path refused')

def path_for(pin, roots):
    locator = Path(pin['locator'])
    require(not locator.is_absolute() and '..' not in locator.parts, 'Plain root-relative descriptor required')
    path = roots[pin['root']] / locator
    plain(path)
    require(path.is_relative_to(roots[pin['root']]), 'Source leaves declared root')
    return path

def checked(pin, roots):
    raw = path_for(pin, roots).read_bytes()
    require(len(raw) == pin['bytes'] and sha(raw) == pin['sha256'], 'Pinned source bytes differ')
    return raw

def run(recipe, roots):
    require(recipe['policy'] == POLICY and set(recipe['endpoints']) == {'grok'}, 'Exact V13 endpoint policy required')
    base = shared()
    project = base.projector()
    sources = {name: checked(pin, roots) for name, pin in recipe['sources'].items()}
    require(recipe['sources']['study_code']['sha256'] == CODE_SHA and
            recipe['sources']['study_contract']['sha256'] == CONTRACT_SHA and
            recipe['sources']['schedule']['sha256'] == SCHEDULE_SHA, 'Original V13 source binding differs')
    require(recipe['sources']['shared_metadata_helper']['sha256'] == HELPER_SHA and
            recipe['sources']['lexical_projector']['sha256'] == base.PROJECTOR_SHA, 'Metadata helper binding differs')
    public = json.loads(sources['public_provenance'])
    require(public['source_study']['study_sha256'] == CODE_SHA and
            public['source_study']['study_contract_sha256'] == CONTRACT_SHA and
            public['source_study']['study_id'] == STUDY and
            public['receipt_replay']['schedule_raw_sha256'] == SCHEDULE_SHA, 'Publication source commitment differs')
    spec = dict(base.SCHEDULE)
    spec['geometry'] = {k: True for k in ('candidates', 'grok_cells', 'grok_max_concurrent_cells', 'sol_cells', 'train_groups', 'train_items')}
    schedule = project(sources['schedule'], spec)
    require(schedule['study_id'] == STUDY and schedule['endpoint'] == 'grok_primary' and
            schedule['schedule_sha256'] == recipe['semantic_schedule_sha256'], 'Declared schedule differs')
    require(schedule['geometry'] == {'candidates': 2, 'grok_cells': 88, 'grok_max_concurrent_cells': 10,
            'sol_cells': 0, 'train_groups': 22, 'train_items': 44}, 'V13 schedule geometry differs')
    cells = schedule['cells']
    require(len(cells) == 88 and [c['ordinal'] for c in cells] == list(range(1, 89)) and
            len({c['cell_id'] for c in cells}) == 88 and all(c['partition'] == 'train' for c in cells), 'Schedule membership differs')
    groups = {g['prompt_group_id'] for g in schedule['groups']}
    require(len(groups) == len(schedule['groups']) == 22 and all(g['partition'] == 'train' for g in schedule['groups']), 'TRAIN groups differ')
    candidates = sorted({c['candidate_id'] for c in cells})
    item_sets = [{c['item_id'] for c in cells if c['candidate_id'] == k} for k in candidates]
    require(len(candidates) == 2 and item_sets[0] == item_sets[1] and len(item_sets[0]) == 44 and
            {c['prompt_group_id'] for c in cells} == groups and all(
                c['cell_id'] == 'v13-train-' + sha(canonical({'candidate': c['candidate_id'], 'item': c['item_id']}))[:20]
                and c['endpoint_payload_sha256s'] == {'grok_primary': c['payload_sha256'], 'sol_later': c['payload_sha256']}
                for c in cells), 'Frozen candidate/item identity differs')
    binding = recipe['endpoints']['grok']
    root = path_for(binding['root'], roots)
    require(root.is_dir() and binding['study_id'] == STUDY, 'Original endpoint root differs')
    names = {c['cell_id'] for c in cells}
    require({p.name for p in root.iterdir() if p.is_dir() and p.name != '.claims'} == names == set(binding['cells']), 'Finite directory membership differs')
    p_spec, r_spec, s_spec = base.schemas('grok')
    rows, identities, ledger = [], set(), []
    for source in cells:
        name = source['cell_id']
        pins = binding['cells'][name]
        require(set(pins) == set(base.FILES), 'Finite metadata file roles differ')
        raw = {}
        for filename, pin in pins.items():
            require(path_for(pin, roots) == root / name / filename, 'Cell descriptor path differs')
            raw[filename] = checked(pin, roots)
            ledger.append(pin)
        prepared = project(raw['prepared.json'], p_spec)
        receipt = project(raw['execution-receipt.json'], r_spec)
        settings = project(raw['effective-settings.json'], s_spec)
        expected = {key: source[key] for key in base.CELL}
        require(prepared['cell'] == receipt['cell'] == expected and
                prepared['study_id'] == receipt['study_id'] == STUDY, 'Receipt cell join differs')
        require(prepared['process_launches'] == prepared['provider_calls_made'] == 0 and
                receipt['process_launches'] == 1, 'Preparation/execution declarations differ')
        require(receipt['effective_settings_sha256'] == pins['effective-settings.json']['sha256'] and
                receipt['launch_intent_sha256'] == pins['launch-intent.json']['sha256'] and
                prepared['response_schema_sha256'] == pins['response-schema.json']['sha256'] == recipe['response_schema_sha256'] and
                prepared['schedule_sha256'] == schedule['schedule_sha256'] and
                prepared['outbound_payload_sha256'] == source['payload_sha256'] and
                receipt['prepared_sha256'] == pins['prepared.json']['sha256'] and
                receipt['payload_sha256'] == source['payload_sha256'] and
                receipt['identity_sha256'] == sha(canonical(receipt['identity'])), 'Receipt commitment join differs')
        identity = tuple(receipt['identity'][key] for key in ('request_id', 'session_id'))
        require(all(isinstance(v, str) and v for v in identity) and identity not in identities, 'Declared identity reuse/missing field')
        identities.add(identity)
        controls = {'requested_model': receipt['identity']['requested_model'] == settings['requested_model'],
                    'reported_model': receipt['identity']['reported_model'] == settings['reported_model'],
                    'prepared_tools': prepared['tools_enabled'] == settings['tools_enabled'],
                    'identity_tools': receipt['identity']['tools_enabled'] == settings['tools_enabled']}
        mismatches = sorted(k for k, consistent in controls.items() if not consistent)
        rows.append({'endpoint': 'grok', 'source_cell_id': name, 'cell_id': name,
                     'disposition': 'receipt_backed_metadata_control_mismatch' if mismatches else 'receipt_backed_metadata_only',
                     'control_metadata_mismatches': mismatches, 'prepared': prepared, 'receipt': receipt, 'settings': settings, 'pins': pins})
    require(all(len({v[i] for v in identities}) == 88 for i in (0, 1)), 'Endpoint identity reuse differs')
    ledger.extend(recipe['sources'].values())
    counts = {'planned_cells': 88, 'receipt_backed_metadata_cells': 88, 'distinct_identity_pairs': len(identities),
              'candidate_cells': dict(Counter(r['prepared']['cell']['candidate_id'] for r in rows)),
              'control_metadata_mismatch_cells': sum(bool(r['control_metadata_mismatches']) for r in rows),
              'settings_tool_flags': dict(Counter(str(r['settings']['tools_enabled']) for r in rows)),
              'receipt_provider_call_declarations': dict(Counter(str(r['receipt']['provider_calls_made']) for r in rows))}
    report = {'policy': POLICY, 'status': 'completed_metadata_only_census', 'partition': 'train', 'items': 44, 'groups': 22,
              'candidates': 2, 'planned_cells': 88, 'endpoints': {'grok': counts}, 'source_pins': recipe['sources'],
              'semantic_schedule_sha256': schedule['schedule_sha256'], 'semantic_schedule_hash_recomputed': False,
              'source_commitments_checked': len(ledger), 'input_commitment_sha256': sha(canonical(ledger)),
              'shared_metadata_helper_sha256': HELPER_SHA, 'provider_calls': 0, 'new_votes': 0, 'native_admission_replays': 0,
              'semantic_admission_replays': 0, 'scoring_calls': 0, 'compiler_calls': 0, 'tools_off_eligible_records': 0,
              'capacity_released': 0, 'physical_contact_cardinality': None, 'labels_opened': False, 'score_projections_opened': False,
              'confirmation_opened': False, 'candidate_promoted': False, 'full_goal_complete': False,
              'limitations': ['Receipt metadata only; not native/semantic admission, leaf/score validation or current tools-disabled qualification.',
                'Declared identities/process launches do not prove physical contacts, provider attestation or billing quiescence.',
                'Excluded targets/payloads prevent semantic schedule-hash recomputation and original metric/report reconstruction.',
                'TRAIN overlaps other historical expansions; metadata rows are not additional unique human references or independent votes.',
                'Original Sol schedule count is zero; this census establishes no Sol result, capacity release or candidate promotion.']}
    return report, {'policy': POLICY, 'rows': rows, 'artifact_ledger': ledger}

def recheck(recipe, roots):
    shared()
    for pin in recipe['sources'].values():
        checked(pin, roots)
    for binding in recipe['endpoints'].values():
        root = path_for(binding['root'], roots)
        require({p.name for p in root.iterdir() if p.is_dir() and p.name != '.claims'} == set(binding['cells']), 'Endpoint snapshot changed')
        for pins in binding['cells'].values():
            for pin in pins.values():
                checked(pin, roots)

def main(argv=None):
    sys.dont_write_bytecode = True
    require(not sys.flags.optimize, 'Non-optimized execution required')
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    for name in ('documents-root', 'control-root', 'recipe', 'output-root'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--recipe-sha256', required=True)
    args = parser.parse_args(argv)
    implementation = Path(__file__).read_bytes()
    roots = {'repository': REPO, 'documents': args.documents_root.absolute(), 'control': args.control_root.absolute()}
    for path in roots.values():
        plain(path)
    raw = args.recipe.read_bytes()
    require(sha(raw) == args.recipe_sha256, 'Recipe digest differs')
    recipe = json.loads(raw)
    output = args.output_root.absolute()
    plain(output)
    require(not output.exists() and output.is_relative_to(roots['control']) and not output.is_relative_to(REPO), 'Fresh private output required')
    paths = [path_for(p, roots) for p in recipe['sources'].values()]
    paths.extend(path_for(e['root'], roots) for e in recipe['endpoints'].values())
    require(all(not output.is_relative_to(p if p.is_dir() else p.parent) and not p.is_relative_to(output) for p in paths)
            and not args.recipe.resolve().is_relative_to(output), 'Output overlaps source')
    report, private = run(recipe, roots)
    recheck(recipe, roots)
    require(args.recipe.read_bytes() == raw and Path(__file__).read_bytes() == implementation, 'Recipe/implementation snapshot changed')
    require(not output.exists(), 'Create-only destination changed')
    plain(output)
    private_raw = canonical(private)
    report.update(implementation_sha256=sha(implementation), recipe_sha256=sha(raw), private_ledger_sha256=sha(private_raw))
    report_raw = canonical(report)
    receipt = {'policy': POLICY, 'state': 'completed', 'output_written': True, 'report_sha256': sha(report_raw),
               'private_ledger_sha256': sha(private_raw), 'implementation_sha256': sha(implementation), 'recipe_sha256': sha(raw),
               'planned_cells': 88, 'provider_calls': 0, 'new_votes': 0}
    output.mkdir(parents=True, exist_ok=False)
    for name, value in [('report.json', report_raw), ('private-metadata-ledger.json', private_raw), ('recipe.json', raw),
                        ('census_train_v13_metadata.py', implementation), ('terminal.json', canonical(receipt))]:
        with (output / name).open('xb') as stream:
            stream.write(value)
    print(json.dumps(receipt, sort_keys=True))
    return receipt

if __name__ == '__main__':
    main()
