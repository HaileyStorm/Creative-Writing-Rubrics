"""Join a saved V13 TRAIN metadata census to the immutable v7 registry.

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
POLICY = 'historical_disposition_coverage_registry_v8'
TARGET = 'hbq-human-alignment-optimizer-v13-train-expansion-result-v1'
CENSUS = 'v13_train_receipt_metadata'
V7_SHA = 'c858d5081c33b22a79c45bb2963427e661392860dec8ca34df42dbab771b254b'
V13_SHA = '7d1fabc5dbceb7ab2d1e82e5577e822eff3a809b8e1c947a8c327d009c7cff1f'


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
    previous, binding = recipe['predecessor'], recipe['v13']
    require(set(previous) == set(binding) == {'report', 'receipt', 'recipe', 'implementation', 'private_ledger'},
            'Saved proof file roles differ')
    old = {k: checked(p, roots) for k, p in previous.items()}
    saved = {k: checked(p, roots) for k, p in binding.items()}
    report, terminal = json.loads(old['report']), json.loads(old['receipt'])
    census, receipt, census_recipe = json.loads(saved['report']), json.loads(saved['receipt']), json.loads(saved['recipe'])
    require(previous['implementation']['sha256'] == V7_SHA and binding['implementation']['sha256'] == V13_SHA,
            'Qualified implementations differ')
    require(report['policy'] == terminal['policy'] == 'historical_disposition_coverage_registry_v7' and
            terminal['state'] == 'completed' and terminal['dry_run'] is False and
            terminal['inventory'] == report['inventory'], 'Saved v7 completion differs')
    for key, name in [('report_sha256', 'report'), ('recipe_file_sha256', 'recipe'),
                      ('implementation_sha256', 'implementation'), ('private_ledger_sha256', 'private_ledger')]:
        require(terminal[key] == sha(old[name]), 'Saved v7 receipt commitment differs')
        if name != 'report':
            require(report[key] == terminal[key], 'Saved v7 report commitment differs')
    require(receipt['state'] == 'completed' and receipt['output_written'] is True and
            census['policy'] == receipt['policy'] == census_recipe['policy'] == 'historical_v13_train_receipt_metadata_v1',
            'Saved V13 completion differs')
    for key, name in [('report_sha256', 'report'), ('recipe_sha256', 'recipe'),
                      ('implementation_sha256', 'implementation'), ('private_ledger_sha256', 'private_ledger')]:
        require(receipt[key] == sha(saved[name]), 'Saved V13 receipt commitment differs')
        if name != 'report':
            require(census[key] == receipt[key], 'Saved V13 report commitment differs')
    require(census['partition'] == 'train' and census['planned_cells'] == receipt['planned_cells'] == 88 and
            census['items'] == 44 and census['groups'] == 22 and census['candidates'] == 2 and
            all(census[k] == 0 for k in ('provider_calls', 'new_votes', 'native_admission_replays',
                'semantic_admission_replays', 'scoring_calls', 'compiler_calls', 'tools_off_eligible_records', 'capacity_released')) and
            all(census[k] is False for k in ('labels_opened', 'score_projections_opened', 'confirmation_opened',
                'candidate_promoted', 'full_goal_complete', 'semantic_schedule_hash_recomputed')) and
            census['physical_contact_cardinality'] is None, 'V13 evidence scope differs')
    require(receipt['provider_calls'] == receipt['new_votes'] == 0 and
            terminal['provider_calls_made'] == terminal['new_provider_votes'] == 0 and
            report['provider_calls_made'] == report['new_provider_votes'] == 0, 'Nonvoting scope differs')
    require(set(census['endpoints']) == set(census_recipe['endpoints']) == {'grok'}, 'V13 endpoint set differs')
    for endpoint in ('grok',):
        counts = census['endpoints'][endpoint]
        require(counts['planned_cells'] == counts['receipt_backed_metadata_cells'] == counts['distinct_identity_pairs'] == 88 and
                counts['control_metadata_mismatch_cells'] == 0 and sorted(counts['candidate_cells'].values()) == [44, 44],
                'V13 endpoint membership differs')
    # This saved private ledger contains only whitelisted metadata, never labels or response prose.
    private = json.loads(saved['private_ledger'])
    declared = list(census_recipe['sources'].values())
    declared.extend(pin for endpoint in census_recipe['endpoints'].values()
                    for pins in endpoint['cells'].values() for pin in pins.values())
    require(private['policy'] == census['policy'] and len(private['rows']) == 88 and
            len(private['artifact_ledger']) == census['source_commitments_checked'] == len(declared) and
            sha(canonical(private['artifact_ledger'])) == census['input_commitment_sha256'] and
            census['source_pins'] == census_recipe['sources'] and
            Counter(canonical(p) for p in private['artifact_ledger']) == Counter(canonical(p) for p in declared),
            'Saved V13 private commitments differ')
    input_pins = [*previous.values(), *binding.values(), *private['artifact_ledger']]
    for pin in private['artifact_ledger']:
        checked(pin, roots)
    packages = [p for p in report['declaration_packages'] if p['id'] == TARGET]
    require(len(packages) == 1 and all(census['source_pins'][role] in packages[0]['artifact_commitments']
            for role in ('public_result', 'public_provenance')) and
            census['source_pins']['registry_v7'] == previous['report'], 'Public/private declaration binding differs')
    old_edges = [e for e in report['coverage_edges'] if e['source_type'] == 'declaration_package' and e['source'] == TARGET]
    require(len(old_edges) == 1 and old_edges[0]['relationship'] == 'unresolved_locator' and
            old_edges[0]['census'] is None and all(c['id'] != CENSUS for c in report['completed_censuses']),
            'Expected one unresolved declaration and fresh census namespace')
    inv = report['inventory']
    require([inv[k] for k in ('declaration_packages', 'coverage_edges', 'completed_censuses',
            'metadata_only_qualified_packages', 'unresolved_declaration_packages')] == [76, 115, 10, 7, 56],
            'Saved v7 inventory differs')
    counts = {'receipt_metadata_cells': 88, 'grok_cells': 88, 'sol_cells': 0, 'train_items': 44,
              'prompt_groups': 22, 'candidates': 2, 'control_metadata_mismatches': 0}
    replacement = {'source_type': 'declaration_package', 'source': TARGET, 'relationship': 'metadata_membership_only',
        'census': CENSUS, 'census_namespace': 'completed_census', 'basis': 'saved_v13_receipt_metadata_source_commitment_join_only',
        'metadata_counts': counts, 'fresh_observations': 0, 'new_provider_votes': 0,
        'observed_leaf_coverage': 'not_established', 'native_admission': 'not_replayed', 'scoring': 'not_replayed',
        'physical_contact_cardinality': None, 'tools_off_eligible_records': 0, 'capacity_released': 0}
    report['coverage_edges'] = [replacement if edge == old_edges[0] else edge for edge in report['coverage_edges']]
    report['completed_censuses'].append({'id': CENSUS, 'recipe': binding['recipe'], 'report': binding['report'],
        'receipt': binding['receipt'], 'receipt_kind': 'completed_terminal',
        'basis': 'saved_metadata_only_proof_hash_binding_not_reexecuted', 'observed_leaf_coverage': 'not_established'})
    report.update(schema_version=8, policy=POLICY, historical_predecessor_v7={'pins': previous,
        'superseded_locator_edges': old_edges, 'input_commitment_sha256': report['input_commitment_sha256'],
        'private_ledger_sha256': report['private_ledger_sha256']},
        qualified_v13_train_metadata_binding={'id': CENSUS, 'pins': binding, 'counts': counts, 'fresh_observations': 0})
    report['inventory'] = {**inv, 'completed_censuses': 11, 'metadata_only_qualified_packages': 8,
        'unresolved_declaration_packages': 55, 'relationships': dict(sorted(Counter(e['relationship'] for e in report['coverage_edges']).items()))}
    report['limitations'] = [line.replace('V13 and pilot declarations remain separate and unresolved.', 'At the historical v7 snapshot V13 and pilot declarations remained unresolved; v8 qualifies V13 metadata only, and pilots remain unresolved.') for line in report['limitations']]
    report['limitations'].append('V13 joins 88 historical TRAIN Grok receipt metadata cells over 44 overlapping items; it adds no native votes, current tools-disabled qualification, scores, unique human references or independently established physical contacts. Original Sol schedule count is zero; pilot declarations remain unresolved.')
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
    for pin in [*recipe['predecessor'].values(), *recipe['v13'].values()]:
        path = path_for(pin, roots)
        require(not output.is_relative_to(path.parent) and not path.is_relative_to(output), 'Output overlaps proof input')
    require(not args.recipe.resolve().is_relative_to(output), 'Output overlaps recipe')
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
    terminal = {'policy': POLICY, 'state': 'verified' if args.dry_run else 'completed', 'dry_run': args.dry_run,
        'report_sha256': sha(report_raw), 'recipe_file_sha256': sha(recipe_raw), 'implementation_sha256': sha(implementation),
        'private_ledger_sha256': sha(private_raw), 'inventory': report['inventory'], 'provider_calls_made': 0, 'new_provider_votes': 0}
    if not args.dry_run:
        output.mkdir(parents=True, exist_ok=False)
        for name, raw in [('registry.json', report_raw), ('private-ledger.json', private_raw),
                          ('registry-v8.recipe.json', recipe_raw), ('registry_v8.py', implementation), ('terminal.json', canonical(terminal))]:
            with (output/name).open('xb') as stream:
                stream.write(raw)
    print(json.dumps(terminal, sort_keys=True))


if __name__ == '__main__':
    main()
