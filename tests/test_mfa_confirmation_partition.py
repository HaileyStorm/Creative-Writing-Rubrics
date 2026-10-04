from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('mfa_partition', ROOT / 'evaluation-results/hbq-mfa-confirmation-plan-v1/partition.py')
partition = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(partition)


def h(value):
    return partition.sha(value.encode())


def row(target, *, release='author-style', task='style', condition='finetuned', pair=None, original=None):
    source = {target: {'writer': [['sealed-label', 'rater', {
        'id': 1, 'Excerpt1': (pair or (target+'a', target+'b'))[0],
        'Excerpt2': (pair or (target+'a', target+'b'))[1]}]]}}
    if original is not None:
        source[target]['writer'][0][-1]['Original'] = original
    return partition.seal.project(source, f'data/{task}_{condition}_expert_anon.json', release)[0]


def small(metadata, **kwargs):
    return partition.design(metadata, development_targets=1, confirmation_targets=2,
                            development_fine_targets=1, confirmation_fine_targets=2, **kwargs)


def metadata():
    return {'rows': [row(t, original=t+'ref') for t in ('a', 'b', 'c')], 'references': []}


@pytest.mark.parametrize('link', ['candidate', 'row_reference', 'catalogue_reference', 'candidate_to_reference'])
def test_shared_text_connects_targets_across_all_scopes(link):
    data = metadata()
    a, b = data['rows'][:2]
    b.update(release='good-writing', task='quality', panel='lay', condition='fewshot')
    if link == 'candidate':
        b['excerpt_hashes'][0] = a['excerpt_hashes'][0]
    elif link == 'row_reference':
        b['original_hash'] = a['original_hash']
    elif link == 'candidate_to_reference':
        b['original_hash'] = a['excerpt_hashes'][0]
    else:
        data['references'] = [{'writer_hash': r['target_hash'], 'original_hash': h('shared'), 'release': r['release']} for r in (a, b)]
    summary, ledger = partition.design(data, development_targets=1, confirmation_targets=2,
                                      development_fine_targets=1, confirmation_fine_targets=1)
    assert summary['component_count'] == 2
    joined = next(c for c in ledger['components'] if len(c['target_hashes']) == 2)
    assert a['target_hash'] in joined['target_hashes'] and b['target_hash'] in joined['target_hashes']
    assert summary['crosspartition_checks'] == {'target_crosspartition_count': 0, 'text_crosspartition_count': 0, 'candidate_pair_crosspartition_count': 0}


def test_exposed_component_is_development_and_empty_audit_stays_incomplete():
    data = metadata()
    snapshot = copy.deepcopy(data)
    exposure = {'text_hashes': [data['rows'][0]['original_hash']], 'audit_complete': True}
    summary, ledger = small(data, exposure=exposure)
    assert next(c for c in ledger['components'] if data['rows'][0]['target_hash'] in c['target_hashes'])['partition'] == 'development'
    assert summary['exposure_audit']['status'] == 'supplied_complete'
    assert summary['exposure_audit']['unused_data_certified'] is False
    assert small(data, exposure={'audit_complete': True})[0]['exposure_audit']['status'] == 'incomplete'
    assert data == snapshot


def test_impossible_forced_component_and_nominal_geometry_are_pending():
    data = metadata()
    data['rows'][1]['excerpt_hashes'][0] = data['rows'][0]['excerpt_hashes'][0]
    summary, ledger = small(data, exposure={'target_hashes': [data['rows'][0]['target_hash']]})
    assert summary['state'] == 'pending_design_decision'
    assert all(c['partition'] == 'unassigned' for c in ledger['components'])
    assert all(v is None for v in summary['crosspartition_checks'].values())
    assert partition.design(data)[0]['state'] == 'pending_design_decision'


def test_assignment_is_stable_under_metadata_row_order():
    data = metadata()
    summary, ledger = small(data)
    reversed_data = {'rows': list(reversed(data['rows'])), 'references': []}
    other_summary, other_ledger = small(reversed_data)
    assert ledger['components'] == other_ledger['components']
    assert summary['partition_target_counts'] == other_summary['partition_target_counts'] == {
        'development': 1, 'confirmation': 2, 'unassigned': 0}


def test_exact_row_references_variants_missingness_and_release_assignment():
    data = metadata()
    variant = copy.deepcopy(data['rows'][0])
    variant['original_hash'] = h('different-row-reference')
    missing = copy.deepcopy(variant)
    missing.update(original_hash=None, original_present=False, original_is_text=False)
    other_release = copy.deepcopy(data['rows'][0]); other_release['release'] = 'good-writing'
    pair_variant = row('a', pair=('aa', 'new-candidate'), original='aref')
    data['rows'] += [variant, missing, other_release, pair_variant]
    data['references'] = [{'release': 'author-style', 'writer_hash': data['rows'][0]['target_hash'], 'original_hash': h('catalogue-only')}]
    summary, ledger = small(data)
    units = [u for u in ledger['evaluation_units'] if u['target_hash'] == data['rows'][0]['target_hash']]
    assert len(units) == 5
    assert sum(not u['eligible'] for u in units) == 1
    assert all(not u['catalogue_reference_match'] for u in units)
    assert len({u['partition'] for u in units}) == 1
    group = next(d for d in summary['denominators'] if d['release'] == 'author-style')
    assert group['groups_with_multiple_exact_pairs'] == 1
    assert sum(u['rows'] for u in ledger['evaluation_units']) == len(data['rows'])
    assert all(len(u['row_memberships']) == u['rows'] for u in units)


def sealed(tmp_path, monkeypatch):
    source = tmp_path / 'input'; source.mkdir()
    data = metadata()
    recipe = {'releases': [{'release': r, 'repository': 'test', 'revision': 'pinned',
                            'sources': [[data['rows'][0]['source_path'], 'blob', 12, 'outcomes']]}
                           for r in ('author-style', 'good-writing')]}
    raw_recipe = json.dumps(recipe, indent=2).encode()
    monkeypatch.setattr(partition.seal, 'RECIPE_SHA256', partition.sha(partition.canonical(recipe)))
    receipts = []
    for release in recipe['releases']:
        path, blob, size, kind = release['sources'][0]
        rows = [r for r in data['rows'] if r['release'] == release['release']]
        receipts.append({'release': release['release'], 'repository': 'test', 'revision': 'pinned',
                         'path': path, 'git_blob_sha1': blob, 'bytes': size, 'kind': kind,
                         'metadata_rows': len(rows), 'metadata_sha256': partition.sha(partition.canonical(rows))})
    summary = {'policy': partition.seal.POLICY, 'recipe_sha256': partition.sha(raw_recipe),
               'cohort': partition.seal.aggregate(data['rows'], [], ['author-style', 'good-writing']),
               'source_receipts': receipts, 'target_values_released': False, 'rationales_released': False, 'excerpts_released': False}
    for name, raw in [('source-recipe.json', raw_recipe), ('private-metadata.json', partition.canonical(data)), ('summary.json', partition.canonical(summary))]:
        (source / name).write_bytes(raw)
    return source


def test_input_commitments_dryrun_and_immutable_fresh_output(tmp_path, monkeypatch):
    source = sealed(tmp_path, monkeypatch)
    output = tmp_path / 'output'
    summary = partition.run(source, output, dry_run=True, development_targets=1, confirmation_targets=2,
                            development_fine_targets=1, confirmation_fine_targets=2)
    assert not output.exists()
    assert summary['source_commitments']['source_recipe_file_sha256'] != summary['source_commitments']['recipe_canonical_json_lf_sha256']
    written = partition.run(source, output, development_targets=1, confirmation_targets=2,
                            development_fine_targets=1, confirmation_fine_targets=2)
    assert partition.sha((output / 'private-membership.json').read_bytes()) == written['private_membership_ledger_sha256']
    public = (output / 'summary.json').read_text()
    assert metadata()['rows'][0]['target_hash'] not in public
    assert set(p.name for p in output.iterdir()) == {'summary.json', 'private-membership.json'}
    with pytest.raises(ValueError, match='must not exist'):
        partition.run(source, output)
    with pytest.raises(ValueError, match='outside'):
        partition.run(source, source / 'child', dry_run=True)


@pytest.mark.parametrize('change', ['metadata', 'receipt', 'recipe', 'missing'])
def test_missing_or_mismatched_metadata_fails(tmp_path, monkeypatch, change):
    source = sealed(tmp_path, monkeypatch)
    if change == 'missing':
        (source / 'private-metadata.json').unlink()
    elif change == 'metadata':
        value = json.loads((source / 'private-metadata.json').read_bytes()); value['rows'].pop()
        (source / 'private-metadata.json').write_bytes(partition.canonical(value))
    else:
        value = json.loads((source / 'summary.json').read_bytes())
        if change == 'receipt': value['source_receipts'][0]['metadata_sha256'] = h('wrong')
        else: value['recipe_sha256'] = h('wrong')
        (source / 'summary.json').write_bytes(partition.canonical(value))
    with pytest.raises((ValueError, FileNotFoundError)):
        partition.run(source, tmp_path / 'output', dry_run=True)
