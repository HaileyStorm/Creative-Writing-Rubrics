from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('mfa_metadata_v2', ROOT / 'evaluation-results/hbq-mfa-metadata-seal-v2/project.py')
projector = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(projector)
PATH = 'data/style_finetuned_expert_anon.json'


def data():
    return {'target': {'writer': [['private-choice', 'source-rater', {
        'id': 17, 'Excerpt1': 'left prose', 'Excerpt2': 'right prose', 'Original': 'reference prose',
        'Preference': 'private-preference', 'Rationale': 'private-rationale', 'unknown': 'private-other'}]]}}


def synthetic_recipe(raw, second_raw=None):
    second_raw = raw if second_raw is None else second_raw
    return {'terms': 'Synthetic provider-free tests', 'releases': [
        {'release': name, 'repository': f'test/{name}', 'revision': 'test-only',
         'sources': [[PATH, projector.git_blob(value), len(value), 'outcomes']]}
        for name, value in [('left', raw), ('right', second_raw)]]}


def test_label_and_unknown_changes_do_not_affect_released_metadata():
    source = data()
    snapshot = copy.deepcopy(source)
    before = projector.project(source, PATH, 'author-style')
    changed = copy.deepcopy(source)
    judgment = changed['target']['writer'][0]
    judgment[0] = 'changed-label'
    judgment[-1].update(Preference='new', Rationale='new', unknown='new')
    assert before == projector.project(changed, PATH, 'author-style')
    assert source == snapshot
    serialized = json.dumps(before)
    for secret in ('private-choice', 'private-preference', 'private-rationale', 'private-other',
                   'left prose', 'right prose', 'reference prose', 'source-rater'):
        assert secret not in serialized


def test_variant_geometry_preserves_exact_text_order_and_v1_pair_identity():
    source = data()
    source['target']['other-writer'] = copy.deepcopy(source['target']['writer'])
    variant = copy.deepcopy(source['target']['writer'][0])
    variant[-1]['Excerpt2'] += ' '
    source['target']['writer'].append(variant)
    rows = projector.project(source, PATH, 'author-style')
    geometry = projector.count_geometry(rows)
    assert geometry['nominal_target_writer_groups'] == 2
    assert geometry['target_writer_pair_memberships'] == 3
    assert geometry['pairs'] == 2
    assert geometry['groups_with_multiple_exact_pairs'] == 1
    assert rows[0]['pair_hash'] == rows[2]['pair_hash']
    old = projector._v1.project(data(), PATH)
    assert rows[0]['pair_hash'] == old[0]['pair_hash']
    swapped = data()
    record = swapped['target']['writer'][0][-1]
    record['Excerpt1'], record['Excerpt2'] = record['Excerpt2'], record['Excerpt1']
    reverse = projector.project(swapped, PATH, 'author-style')[0]
    assert reverse['pair_hash'] == rows[0]['pair_hash']
    assert reverse['ordered_pair_hash'] != rows[0]['ordered_pair_hash']
    assert reverse['excerpt_hashes'] == list(reversed(rows[0]['excerpt_hashes']))


def test_cross_release_duplicates_preserve_missingness_without_independence():
    source = data()
    record = source['target']['writer'][0][-1]
    source['target']['writer'][0][1] = ''
    del record['id']
    del record['Original']
    left = projector.project(source, PATH, 'left')
    right = projector.project(source, PATH, 'right')
    assert left[0]['rater_hash'] is None
    assert left[0]['judgment_identity_hash'] is None
    summary = projector.aggregate(left + right, [], ['left', 'right'])
    assert summary['cross_release']['all_rows']['metadata_record_hash']['shared_distinct'] == 1
    assert summary['cross_release']['all_rows']['rater_hash']['shared_distinct'] == 0
    assert summary['independent_work_count'] is None
    for group in summary['by_release_task_condition_panel']:
        assert group['missing_rater_rows'] == group['missing_record_identity_rows'] == group['missing_original_rows'] == 1
    assert summary['references'][0]['reference_identity_links'] == 'unverified'


def test_catalogue_only_explicit_original_fields_and_no_inferred_writer():
    references = projector.project_references({'unknown-author': [{'Original': 'reference prose', 'Generated': 'secret'}]}, 'left', 'catalogue')
    assert len(references) == 1
    assert references[0]['original_hash'] == projector.sha(b'reference prose')
    assert references[0]['writer_hash'] is None
    assert references[0]['writer_identity_basis'] == 'unverified'
    assert references[0]['source_original_field'] == 'Original'
    assert references[0]['original_field_basis'] == 'uppercase_compatibility'
    assert 'reference prose' not in json.dumps(references)
    assert projector.project_references({'unrecognized': ['prose']}, 'left', 'catalogue') == []


def test_lowercase_catalogue_matches_outcome_target_and_preserves_missing_variants():
    catalogue = {'unknown-root': [
        {'writer': 'target', 'original': 'reference prose', 'generated': 'sealed'},
        {'writer': 'target', 'original': 'reference prose '},
        {'writer': 'writer', 'original': 'reference prose'},
        {'original': 'reference prose'},
        {'writer': 'empty-target'}]}
    snapshot = copy.deepcopy(catalogue)
    refs = projector.project_references(catalogue, 'left', 'catalogue')
    assert catalogue == snapshot
    assert len(refs) == 5
    assert refs[0]['source_original_field'] == 'original'
    assert refs[0]['original_field_basis'] == 'pinned_source_parser'
    assert refs[0]['original_hash'] != refs[1]['original_hash']
    source = data()
    variant = copy.deepcopy(source['target']['writer'][0])
    variant[-1]['Original'] = 'reference prose?'
    source['target']['writer'].append(variant)
    source['unmatched-target'] = copy.deepcopy(data()['target'])
    rows = projector.project(source, PATH, 'left')
    summary = projector.aggregate(rows, refs, ['left', 'right'])['references'][0]
    links = summary['writer_target_links']
    assert summary['missing_writer_identity_records'] == summary['missing_original_text_records'] == 1
    assert summary['source_original_field_counts'] == {'original': 5}
    assert links['shared_writer_target_identifier_hashes'] == 1
    assert links['catalogue_writer_identifiers_without_outcome_target_match'] == 2
    assert links['outcome_target_identifiers_without_catalogue_writer_match'] == 1
    assert links['outcome_rows_with_target_identifier_match'] == 2
    assert links['outcome_rows_with_exact_target_and_original_match'] == links['distinct_exact_target_original_links'] == 1
    assert links['outcome_rows_with_target_match_but_unmatched_original_hash'] == 1
    assert links['catalogue_writer_identifiers_with_multiple_original_hashes'] == 1
    assert links['outcome_target_identifiers_with_multiple_original_hashes'] == 1
    assert links['exact_matched_rows_with_multiple_catalogue_original_variants'] == 1
    assert summary['reference_identity_links'] == 'exact_writer_target_and_original_hash_matches_observed'
    serialized = json.dumps({'references': refs, 'summary': summary})
    assert 'reference prose' not in serialized
    assert 'sealed' not in serialized


def test_exact_blob_replay_reuses_bytes_but_retains_source_provenance(tmp_path, monkeypatch):
    raw = projector.canonical(data())
    recipe = synthetic_recipe(raw)
    source = tmp_path / 'source'
    path = source / PATH
    path.parent.mkdir(parents=True)
    path.write_bytes(raw)
    monkeypatch.setattr(projector, 'fetch', lambda *args: pytest.fail('Replay attempted provider contact'))
    output = tmp_path / 'output'
    summary = projector.run(output, source, recipe=recipe)
    assert len(summary['source_receipts']) == 2
    assert summary['source_receipts'][1]['retrieval_mode'] == 'same_run_exact_blob_reuse'
    assert summary['source_receipts'][0]['release'] != summary['source_receipts'][1]['release']
    assert summary['cohort']['cross_release']['all_rows']['metadata_record_hash']['shared_distinct'] == 1
    terminal = json.loads((output / 'terminal.json').read_bytes())
    assert terminal['state'] == 'completed_blinded_projection'
    assert terminal['summary_sha256'] == projector.sha((output / 'summary.json').read_bytes())
    assert terminal['private_metadata_sha256'] == projector.sha((output / 'private-metadata.json').read_bytes())
    for name in ('left', 'right'):
        assert (output / 'sealed-source' / name / PATH).read_bytes() == raw
    assert 'retrieval_origin' not in summary['source_receipts'][0]
    with pytest.raises(ValueError, match='fresh private'):
        projector.run(output, source, recipe=recipe)


def test_failed_second_source_preserves_completed_prefix_and_never_retries(tmp_path, monkeypatch):
    raw, second_raw = projector.canonical(data()), projector.canonical({'other': data()['target']})
    recipe = synthetic_recipe(raw, second_raw)
    calls = []
    def fake_fetch(url, size):
        calls.append(url)
        return raw if len(calls) == 1 else b'bad source'
    monkeypatch.setattr(projector, 'fetch', fake_fetch)
    output = tmp_path / 'failed'
    with pytest.raises(ValueError, match='frozen Git blob/size'):
        projector.run(output, recipe=recipe)
    assert len(calls) == 2
    assert (output / 'receipts/000.json').is_file()
    assert (output / 'metadata-parts/000.json').is_file()
    assert (output / 'requests/001.json').is_file()
    assert (output / 'sealed-source/right' / PATH).read_bytes() == b'bad source'
    assert json.loads((output / 'received/001.json').read_bytes())['received_bytes'] == 10
    assert not (output / 'summary.json').exists()
    terminal = json.loads((output / 'terminal.json').read_bytes())
    assert terminal['state'] == 'failed_preserved'
    assert terminal['completed_sources'] == 1
    assert 'bad source' not in json.dumps(terminal)


def test_replay_missing_bytes_and_output_input_overlap_fail_locally(tmp_path, monkeypatch):
    raw = projector.canonical(data())
    recipe = synthetic_recipe(raw)
    source = tmp_path / 'source'
    source.mkdir()
    monkeypatch.setattr(projector, 'fetch', lambda *args: pytest.fail('Missing replay source attempted provider contact'))
    with pytest.raises(ValueError, match='fresh private'):
        projector.run(source / 'inside', source, recipe=recipe)
    with pytest.raises(ValueError, match='missing exact pinned'):
        projector.run(tmp_path / 'failed', source, recipe=recipe)
    assert json.loads((tmp_path / 'failed/terminal.json').read_bytes())['state'] == 'failed_preserved'


def test_frozen_recipe_and_sha_checks_reject_drift(tmp_path, monkeypatch):
    _, recipe = projector.load_recipe()
    assert len(recipe['releases']) == 2
    assert all(len(release['sources']) == 9 for release in recipe['releases'])
    raw = projector.canonical(data())
    blob = projector.git_blob(raw)
    monkeypatch.setitem(projector.KNOWN_SHA256, blob, '0' * 64)
    with pytest.raises(ValueError, match='SHA256'):
        projector.validate_source(raw, blob, len(raw))
    recipe['releases'][0]['revision'] = 'drift'
    altered = tmp_path / 'recipe.json'
    altered.write_bytes(projector.canonical(recipe))
    monkeypatch.setattr(projector, 'RECIPE', altered)
    with pytest.raises(ValueError, match='recipe digest mismatch'):
        projector.load_recipe()
