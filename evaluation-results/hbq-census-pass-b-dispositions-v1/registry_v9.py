"""Join saved V14 pilot metadata to the immutable v8 registry.

This is a saved-proof projection. It never runs prior readers or collectors,
opens targets, admits native votes, recomputes scores or releases capacity.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
POLICY = 'historical_disposition_coverage_registry_v9'
TARGET = 'hbq-human-alignment-optimizer-v14-dspy-train-pilot-result-v1'
CENSUS = 'v14_pilot_receipt_preparation_metadata'
V8_SHA = '1ba96283fcba0719a49e5b91b3f801ffcf42b7e34fa46591e960b9e0e44ad141'
PILOT_SHA = 'f6b950aac977d1e875e733623c7358a794d4287030123967e20b3b3604e76c8b'


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return (json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False)+'\n').encode()


def plain(path):
    require(path.resolve() == path, 'Canonical path required')
    for part in (path, *path.parents):
        if part.exists():
            require(not getattr(part.lstat(), 'st_file_attributes', 0) & 0x400 and not part.is_symlink(), 'Reparse/link path refused')


def path_for(pin, roots):
    rel = Path(pin['locator'])
    root = roots[pin['root']]
    require(not rel.is_absolute() and '..' not in rel.parts, 'Plain relative source required')
    path = root / rel
    plain(path)
    require(path.is_relative_to(root), 'Pin leaves declared root')
    return path


def checked(pin, roots):
    raw = path_for(pin, roots).read_bytes()
    require(len(raw) == pin['bytes'] and sha(raw) == pin['sha256'], 'Saved proof bytes differ')
    return raw


def run(recipe, roots):
    require(recipe['policy'] == POLICY, 'Wrong registry recipe')
    previous, binding = recipe['predecessor'], recipe['pilot']
    require(set(previous) == set(binding) == {'report', 'receipt', 'recipe', 'implementation', 'private_ledger'},
            'Saved proof file roles differ')
    old = {k: checked(p, roots) for k, p in previous.items()}
    saved = {k: checked(p, roots) for k, p in binding.items()}
    report, terminal = json.loads(old['report']), json.loads(old['receipt'])
    census, receipt, census_recipe = json.loads(saved['report']), json.loads(saved['receipt']), json.loads(saved['recipe'])
    require(previous['implementation']['sha256'] == V8_SHA and binding['implementation']['sha256'] == PILOT_SHA,
            'Qualified implementations differ')
    require(report['policy'] == terminal['policy'] == 'historical_disposition_coverage_registry_v8' and
            terminal['state'] == 'completed' and terminal['dry_run'] is False and
            terminal['inventory'] == report['inventory'], 'Saved v8 completion differs')
    for key, name in [('report_sha256', 'report'), ('recipe_file_sha256', 'recipe'),
                      ('implementation_sha256', 'implementation'), ('private_ledger_sha256', 'private_ledger')]:
        require(terminal[key] == sha(old[name]), 'Saved v8 receipt commitment differs')
        if name != 'report':
            require(report[key] == terminal[key], 'Saved v8 report commitment differs')
    require(receipt['state'] == 'completed' and receipt['output_written'] is True and
            census['policy'] == receipt['policy'] == census_recipe['policy'] == 'historical_v14_pilot_receipt_preparation_metadata_v1',
            'Saved pilot completion differs')
    for key, name in [('report_sha256', 'report'), ('recipe_sha256', 'recipe'),
                      ('implementation_sha256', 'implementation'), ('private_ledger_sha256', 'private_ledger')]:
        require(receipt[key] == sha(saved[name]), 'Saved pilot receipt commitment differs')
        if name != 'report':
            require(census[key] == receipt[key], 'Saved pilot report commitment differs')
    require(census['partition'] == 'train' and census['planned_cells'] == receipt['planned_cells'] == 16 and
            census['preparation_only_cells'] == receipt['preparation_only_cells'] == 8 and
            census['scope_metadata_rows'] == 24 and census['logical_candidate_item_conditions'] == 8 and
            census['items'] == census['groups'] == 4 and census['candidates'] == 2 and
            all(census[k] == 0 for k in ('provider_calls', 'new_votes', 'native_admission_replays',
                'semantic_admission_replays', 'scoring_calls', 'compiler_calls', 'tools_off_eligible_records', 'capacity_released')) and
            all(census[k] is False for k in ('labels_opened', 'score_projections_opened', 'confirmation_opened',
                'candidate_promoted', 'full_goal_complete', 'semantic_schedule_hash_recomputed',
                'published_aggregate_inventory_reconstructed')) and
            census['physical_contact_cardinality'] is None, 'Pilot evidence scope differs')
    require(receipt['provider_calls'] == receipt['new_votes'] == 0 and
            terminal['provider_calls_made'] == terminal['new_provider_votes'] == 0 and
            report['provider_calls_made'] == report['new_provider_votes'] == 0, 'Nonvoting scope differs')
    scope_roles = {'grok_receipts': ('grok', 'receipt_backed'), 'sol_receipts': ('sol', 'receipt_backed'),
                   'sol_preparations': ('sol', 'preparation_only')}
    require(set(census['scopes']) == set(census_recipe['scopes']) == set(scope_roles), 'Pilot scope set differs')
    for name, (endpoint, kind) in scope_roles.items():
        c = census['scopes'][name]
        expected_receipts = 8 if kind == 'receipt_backed' else 0
        require((c['endpoint'], c['kind']) == (endpoint, kind) and c['prepared_metadata_cells'] == 8 and
                c['receipt_backed_metadata_cells'] == c['distinct_declared_identity_pairs'] == expected_receipts and
                c['control_metadata_mismatch_cells'] == 0 and sorted(c['candidate_cells'].values()) == [4, 4],
                'Pilot scope membership differs')
    require(census['cross_scope_preparation_join']['matching_logical_cells'] == 8 and
            census['cross_scope_preparation_join']['identical_prepared_raw_hashes'] +
            census['cross_scope_preparation_join']['different_prepared_raw_hashes'] == 8 and
            census['cross_scope_preparation_join']['retry_authority'] is False and
            census['cross_scope_preparation_join']['physical_contact_relationship'] == 'unproven',
            'Cross-scope preparation authority differs')
    # Saved private ledger contains whitelisted metadata only; preparations remain nonvoting.
    private = json.loads(saved['private_ledger'])
    declared = list(census_recipe['sources'].values())
    declared.extend(pin for scope in census_recipe['scopes'].values()
                    for pins in scope['cells'].values() for pin in pins.values())
    require(private['policy'] == census['policy'] and len(private['rows']) == 24 and
            Counter(row['scope'] for row in private['rows']) == {name: 8 for name in scope_roles} and
            all(row['receipt'] is row['settings'] is None and
                row['disposition'] == 'preparation_metadata_only_contact_unknown'
                for row in private['rows'] if row['scope'] == 'sol_preparations') and
            len(private['artifact_ledger']) == census['source_commitments_checked'] == len(declared) == 106 and
            sha(canonical(private['artifact_ledger'])) == census['input_commitment_sha256'] and
            census['source_pins'] == census_recipe['sources'] and
            Counter(canonical(p) for p in private['artifact_ledger']) == Counter(canonical(p) for p in declared),
            'Saved pilot private commitments differ')
    input_pins = [*previous.values(), *binding.values(), *private['artifact_ledger']]
    for pin in private['artifact_ledger']:
        checked(pin, roots)
    packages = [p for p in report['declaration_packages'] if p['id'] == TARGET]
    require(len(packages) == 1 and all(census['source_pins'][role] in packages[0]['artifact_commitments']
            for role in ('public_result', 'public_provenance')) and
            census['source_pins']['registry_v8'] == previous['report'], 'Public/private declaration binding differs')
    old_edges = [e for e in report['coverage_edges'] if e['source_type'] == 'declaration_package' and e['source'] == TARGET]
    require(len(old_edges) == 1 and old_edges[0]['relationship'] == 'unresolved_locator' and
            old_edges[0]['census'] is None and all(c['id'] != CENSUS for c in report['completed_censuses']),
            'Expected one unresolved declaration and fresh census namespace')
    inv = report['inventory']
    require([inv[k] for k in ('declaration_packages', 'coverage_edges', 'completed_censuses',
            'metadata_only_qualified_packages', 'unresolved_declaration_packages')] == [76, 115, 11, 8, 55],
            'Saved v8 inventory differs')
    counts = {'receipt_metadata_cells': 16, 'grok_cells': 8, 'sol_cells': 8, 'preparation_only_cells': 8,
              'train_items': 4, 'prompt_groups': 4, 'candidates': 2, 'control_metadata_mismatches': 0}
    replacement = {'source_type': 'declaration_package', 'source': TARGET, 'relationship': 'metadata_membership_only',
        'census': CENSUS, 'census_namespace': 'completed_census', 'basis': 'saved_v14_pilot_receipt_preparation_metadata_source_commitment_join_only',
        'metadata_counts': counts, 'fresh_observations': 0, 'new_provider_votes': 0,
        'observed_leaf_coverage': 'not_established', 'native_admission': 'not_replayed', 'scoring': 'not_replayed',
        'physical_contact_cardinality': None, 'tools_off_eligible_records': 0, 'capacity_released': 0}
    report['coverage_edges'] = [replacement if edge == old_edges[0] else edge for edge in report['coverage_edges']]
    report['completed_censuses'].append({'id': CENSUS, 'recipe': binding['recipe'], 'report': binding['report'],
        'receipt': binding['receipt'], 'receipt_kind': 'completed_terminal',
        'basis': 'saved_metadata_only_proof_hash_binding_not_reexecuted', 'observed_leaf_coverage': 'not_established'})
    report.update(schema_version=9, policy=POLICY, historical_predecessor_v8={'pins': previous,
        'superseded_locator_edges': old_edges, 'input_commitment_sha256': report['input_commitment_sha256'],
        'private_ledger_sha256': report['private_ledger_sha256']},
        qualified_v14_pilot_metadata_binding={'id': CENSUS, 'pins': binding, 'counts': counts, 'fresh_observations': 0})
    report['inventory'] = {**inv, 'completed_censuses': 12, 'metadata_only_qualified_packages': 9,
        'unresolved_declaration_packages': 54, 'relationships': dict(sorted(Counter(e['relationship'] for e in report['coverage_edges']).items()))}
    # Preserve previous limitations as historical statements while making current pilot status explicit.
    report['limitations'] = [
        'Historical predecessor limitation: ' + line + ' Current v9 qualifies the pilot metadata only.'
        if 'pilots remain unresolved' in line.lower() else line for line in report['limitations']]
    report['limitations'].append('V14 pilot joins sixteen historical TRAIN receipt metadata cells, eight per endpoint, plus eight separately retained Sol preparation records over four items. Preparation absence never authorizes retry. No votes, admission, scores, new humans, unused confirmation, current tools-disabled qualification or physical contacts are established; aggregate report inventories remain unreconstructed.')
    private_out = {'policy': POLICY, 'artifact_ledger': input_pins}
    report.update(input_commitment_sha256=sha(canonical(input_pins)), private_ledger_sha256=sha(canonical(private_out)))
    return report, private_out


def main():
    import sys
    sys.dont_write_bytecode = True
    require(not sys.flags.optimize, 'Non-optimized execution required')
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    for name in ('documents-root', 'control-root', 'recipe', 'output-root'):
        parser.add_argument('--'+name, type=Path, required=True)
    parser.add_argument('--recipe-sha256', required=True)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    roots = {'repository': REPO, 'documents': args.documents_root.resolve(), 'control': args.control_root.resolve()}
    recipe_raw, implementation = args.recipe.read_bytes(), Path(__file__).read_bytes()
    require(sha(recipe_raw) == args.recipe_sha256, 'Recipe digest differs')
    recipe = json.loads(recipe_raw)
    output = args.output_root.absolute()
    plain(output)
    require(not output.exists() and output == args.output_root.absolute() and
            output.is_relative_to(roots['control']) and not output.is_relative_to(REPO), 'Fresh private output required')
    for pin in [*recipe['predecessor'].values(), *recipe['pilot'].values()]:
        path = path_for(pin, roots)
        require(not output.is_relative_to(path.parent) and not path.is_relative_to(output), 'Output overlaps proof input')
    require(not args.recipe.resolve().is_relative_to(output), 'Output overlaps recipe')
    pilot_recipe = json.loads(checked(recipe['pilot']['recipe'], roots))
    retained_roots = [path_for(scope['root'], roots) for scope in pilot_recipe['scopes'].values()]
    for retained in retained_roots:
        require(retained.is_dir() and not output.is_relative_to(retained) and not retained.is_relative_to(output),
                'Output overlaps retained pilot scope')
    report, private = run(recipe, roots)
    report.update(recipe_file_sha256=sha(recipe_raw), implementation_sha256=sha(implementation))
    report_raw, private_raw = canonical(report), canonical(private)
    for pin in private['artifact_ledger']:
        require(not output.is_relative_to(path_for(pin, roots).parent), 'Output overlaps original source')
        checked(pin, roots)
    require(args.recipe.read_bytes() == recipe_raw and Path(__file__).read_bytes() == implementation and
            args.output_root.resolve() == output == args.output_root.absolute() and
            not output.exists(), 'Publication snapshot changed')
    plain(output)
    for retained in retained_roots:
        plain(retained)
        require(retained.is_dir() and not output.is_relative_to(retained) and not retained.is_relative_to(output),
                'Retained pilot scope changed before publication')
    terminal = {'policy': POLICY, 'state': 'verified' if args.dry_run else 'completed', 'dry_run': args.dry_run,
        'report_sha256': sha(report_raw), 'recipe_file_sha256': sha(recipe_raw), 'implementation_sha256': sha(implementation),
        'private_ledger_sha256': sha(private_raw), 'inventory': report['inventory'], 'provider_calls_made': 0, 'new_provider_votes': 0}
    if not args.dry_run:
        output.mkdir(parents=True, exist_ok=False)
        for name, raw in [('registry.json', report_raw), ('private-ledger.json', private_raw),
                          ('registry-v9.recipe.json', recipe_raw), ('registry_v9.py', implementation), ('terminal.json', canonical(terminal))]:
            with (output/name).open('xb') as stream:
                stream.write(raw)
    print(json.dumps(terminal, sort_keys=True))


if __name__ == '__main__':
    main()
