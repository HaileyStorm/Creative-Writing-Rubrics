from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('fixture_intent_review', ROOT / 'evaluation-results/hbq-semantic-crossform-p1b-intent-v1/prepare_review.py')
reviewer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(reviewer)
SPEC_GENERATION = importlib.util.spec_from_file_location('intent_mock_generation', ROOT / 'tests/test_semantic_fixture_generation.py')
fixture_generation = importlib.util.module_from_spec(SPEC_GENERATION)
SPEC_GENERATION.loader.exec_module(fixture_generation)


@pytest.fixture(scope='module')
def prepared_generation():
    cls = fixture_generation.SemanticFixtureGenerationTests
    cls.setUpClass()
    yield cls
    cls.doClassCleanups()


@pytest.fixture
def accepted_prefix(prepared_generation, monkeypatch):
    test = prepared_generation()
    test.setUp()
    for row in test.manifest['requests'][:2]:
        test.row = row
        answer = fixture_generation.synthetic_answer(row['family'])
        for i, role in enumerate(reviewer.prepare.VARIANTS):
            answer['variants'][role]['text'] = answer['variants'][role]['text'].replace(role, ('amber', 'copper', 'violet')[i])
            answer['variants'][role]['proposed_intent_note'] = 'PRIVATE INTENT NOTE NEVER REVEAL'
        answer['proposed_review_notes'] = 'PRIVATE GENERATOR REVIEW NOTES NEVER REVEAL'
        assert test.run_one(answer)
    fixture_generation.collect.record(test.output / 'job.json', fixture_generation.collect.job_binding(test.manifest, test.manifest_sha))
    original_load = reviewer.prepare.load_module
    def mock_receipt_loader(name, path):
        return test.receipts if Path(path).name == 'codex_receipts.py' else original_load(name, path)
    monkeypatch.setattr(reviewer.prepare, 'load_module', mock_receipt_loader)
    yield test
    test.doCleanups()


def build(test, through=2):
    return reviewer.build(test.frozen / 'manifest.json', test.output, through_family=through, manifest_sha256=test.manifest_sha)


def test_explicit_accepted_prefix_and_role_blinding_preserve_source_map(accepted_prefix):
    test = accepted_prefix
    summary, files = build(test)
    assert summary['selected_families'] == 2 and summary['total_prospective_families'] == 8
    assert summary['families_outside_selected_prefix'] == 6
    assert not summary['oracle_accepted'] and not summary['eligible_for_scoring']
    visible = files['reviewer/packet.json'] + files['reviewer/packet.md']
    for secret in (b'target_defect', b'legitimate_style', b'PRIVATE INTENT NOTE', b'PRIVATE GENERATOR REVIEW NOTES', b'p1b-f01.original'):
        assert secret not in visible
    packet = json.loads(files['reviewer/packet.json']); mapping = json.loads(files['private/role-map.json'])
    assert mapping['review_packet_sha256'] == reviewer.digest(files['reviewer/packet.json'])
    for family, private in zip(packet['families'], mapping['families']):
        assert set(private['variants']) == {v['variant_id'] for v in family['variants']}
        assert {v['role'] for v in private['variants'].values()} == set(reviewer.prepare.VARIANTS)
        for v in family['variants']:
            assert reviewer.digest(v['text'].encode()) == private['variants'][v['variant_id']]['text_sha256']
    assert build(test)[1] == files
    smaller = json.loads(build(test, 1)[1]['reviewer/packet.json'])
    assert smaller['families'][0] == packet['families'][0]
    with pytest.raises(ValueError, match='unresolved'): build(test, 3)
    with pytest.raises(ValueError, match='Explicit'): build(test, 0)


@pytest.mark.parametrize('damage', ['native_message', 'response', 'derived_text', 'source_semantics', 'receipt_rejection'])
def test_reuses_generation_source_and_own_receipt_tamper_checks(accepted_prefix, damage):
    test = accepted_prefix
    row = test.manifest['requests'][0]
    sample = fixture_generation.collect.sample_path(test.output, row)
    if damage == 'receipt_rejection': test.receipts.reject = True
    elif damage == 'source_semantics':
        path = test.frozen / row['semantics_path']; before = path.read_bytes(); path.write_bytes(b'changed')
    else:
        path = {'native_message': sample / 'responses/message.json', 'response': sample / 'response.json',
                'derived_text': sample / 'variants/original.txt'}[damage]
        path.write_bytes(b'changed')
    try:
        with pytest.raises(ValueError): build(test)
    finally:
        if damage == 'source_semantics': path.write_bytes(before)


def synthetic_review(packet, mapping):
    entries = []
    for family, private in zip(packet['families'], mapping['families']):
        for variant in family['variants']:
            defect = private['variants'][variant['variant_id']]['role'] == 'target_defect'
            evidence = [{'source': 'variant', 'quote': variant['text'].split()[0]}]
            def assessment(status): return {'status': status, 'evidence': copy.deepcopy(evidence), 'why': 'Synthetic source-supported assessment.'}
            anchors = [{**assessment('not_supported' if defect and i == 0 else 'supported'), 'anchor_id': anchor['anchor_id']}
                       for i, anchor in enumerate(family['proposed_preservation_anchors'])]
            entries.append({'family_id': family['family_id'], 'variant_id': variant['variant_id'],
                            'criterion': assessment('not_supported' if defect else 'supported'),
                            'quality_suitability': assessment('supported'), 'brief_suitability': assessment('supported'),
                            'anchors': anchors, 'local_issue': {'identified': defect,
                                'affected_anchor_ids': [anchors[0]['anchor_id']] if defect else [],
                                'evidence': copy.deepcopy(evidence) if defect else [], 'why': 'Synthetic local issue assessment.'}})
    return {'schema_version': 1, 'packet_sha256': reviewer.digest(reviewer.canonical(packet)),
            'reviewer_declaration': {'kind': 'independent_ai_intent_review', 'identity': 'synthetic reviewer', 'independent_of_generator': True},
            'variants': entries, 'unresolved_disagreements': []}


@pytest.fixture
def review_inputs(accepted_prefix):
    _, files = build(accepted_prefix)
    packet, mapping = json.loads(files['reviewer/packet.json']), json.loads(files['private/role-map.json'])
    return packet, mapping, synthetic_review(packet, mapping), accepted_prefix.subset


def test_unblinding_candidate_retains_ai_limits_and_does_not_promote(review_inputs):
    packet, mapping, review, subset = review_inputs
    snapshot = copy.deepcopy((packet, mapping, review))
    result = reviewer.validate_review(packet, mapping, review, subset)
    assert all(f['oracle_admission_candidate'] for f in result['families'])
    assert not result['oracle_accepted'] and not result['eligible_for_scoring'] and not result['ai_review_is_human_label']
    assert (packet, mapping, review) == snapshot


@pytest.mark.parametrize('damage', ['foreign_quote', 'duplicate', 'missing', 'missing_anchor', 'map_hash', 'anchor_hash'])
def test_schema_inventory_and_exact_source_evidence_failures(review_inputs, damage):
    packet, mapping, review, subset = review_inputs
    if damage == 'foreign_quote': review['variants'][0]['criterion']['evidence'][0]['quote'] = 'NOT IN THIS TEXT'
    elif damage == 'duplicate': review['variants'].append(copy.deepcopy(review['variants'][0]))
    elif damage == 'missing': review['variants'].pop()
    elif damage == 'missing_anchor': review['variants'][0]['anchors'].pop()
    elif damage == 'anchor_hash': mapping['families'][0]['anchor_metadata_lineage'][0]['review_proposal_utf8_sha256'] = 'wrong'
    else: mapping['families'][0]['variants'][review['variants'][0]['variant_id']]['text_sha256'] = 'wrong'
    with pytest.raises(ValueError): reviewer.validate_review(packet, mapping, review, subset)


@pytest.mark.parametrize('block', ['uncertain_control', 'failed_control', 'unlocalized_defect', 'uncertain_defect', 'disagreement', 'not_independent'])
def test_uncertainty_disagreement_and_unrealized_intent_block_admission(review_inputs, block):
    packet, mapping, review, subset = review_inputs
    roles = {key: value['role'] for family in mapping['families'] for key, value in family['variants'].items()}
    control = next(e for e in review['variants'] if roles[e['variant_id']] == 'legitimate_style')
    defect = next(e for e in review['variants'] if roles[e['variant_id']] == 'target_defect')
    if block == 'uncertain_control': control['criterion']['status'] = 'uncertain'
    elif block == 'failed_control': control['quality_suitability']['status'] = 'not_supported'
    elif block == 'unlocalized_defect': defect['local_issue'].update(identified=False, affected_anchor_ids=[])
    elif block == 'uncertain_defect': defect['brief_suitability']['status'] = 'uncertain'
    elif block == 'disagreement': review['unresolved_disagreements'] = ['Preserved synthetic disagreement']
    else: review['reviewer_declaration']['independent_of_generator'] = False
    result = reviewer.validate_review(packet, mapping, review, subset)
    assert not all(f['oracle_admission_candidate'] for f in result['families'])
    assert result['unresolved_disagreements'] == review['unresolved_disagreements']


def test_explicit_generation_role_marker_prevents_packet_not_redaction(accepted_prefix):
    test = accepted_prefix
    row = test.manifest['requests'][0]
    answer = fixture_generation.synthetic_answer(row['family'])
    semantics = json.loads(test.files[row['semantics_path']])
    with pytest.raises(ValueError, match='role marker'):
        reviewer.blinded_packet([(row, answer, semantics, {})], test.manifest_sha, 8)


def test_role_bearing_anchor_aside_is_private_and_entirely_filtered_anchor_blocks(accepted_prefix):
    test = accepted_prefix
    row = test.manifest['requests'][0]
    sample = fixture_generation.collect.sample_path(test.output, row)
    answer = json.loads((sample / 'response.json').read_bytes())
    anchor = 'A factual dependency remains available. Only target_defect may violate this causal dependency.'
    answer['preservation_anchors'][0] = anchor
    semantics = json.loads(test.files[row['semantics_path']])
    packet, mapping = reviewer.blinded_packet([(row, answer, semantics, {})], test.manifest_sha, 8)
    proposed = packet['families'][0]['proposed_preservation_anchors'][0]
    assert proposed['proposal'] == 'A factual dependency remains available.'
    assert proposed['proposal_available'] and proposed['source_metadata_filtered']
    lineage = mapping['families'][0]['anchor_metadata_lineage'][0]
    assert lineage['source_anchor'] == anchor
    assert lineage['removed_role_bearing_sentences'] == ['Only target_defect may violate this causal dependency.']
    assert lineage['source_anchor_utf8_sha256'] == reviewer.digest(anchor.encode())
    assert b'target_defect' not in reviewer.canonical(packet)
    answer['preservation_anchors'][0] = 'Only target_defect may violate this dependency.'
    packet, mapping = reviewer.blinded_packet([(row, answer, semantics, {})], test.manifest_sha, 8)
    proposed = packet['families'][0]['proposed_preservation_anchors'][0]
    assert proposed['proposal'] == '' and not proposed['proposal_available']
    result = reviewer.validate_review(packet, mapping, synthetic_review(packet, mapping), test.subset)
    assert not result['families'][0]['oracle_admission_candidate']
    assert all('filtered_anchor_missing_proposal' in v['blocking_reasons'] for v in result['families'][0]['variants'])


def test_creative_role_heading_fails_without_changing_source(accepted_prefix):
    test = accepted_prefix
    row = test.manifest['requests'][0]
    sample = fixture_generation.collect.sample_path(test.output, row)
    answer = json.loads((sample / 'response.json').read_bytes())
    answer['variants']['original']['text'] = '# Original\n' + answer['variants']['original']['text']
    snapshot = copy.deepcopy(answer)
    with pytest.raises(ValueError, match='role label'):
        reviewer.blinded_packet([(row, answer, json.loads(test.files[row['semantics_path']]), {})], test.manifest_sha, 8)
    assert answer == snapshot


@pytest.mark.parametrize('label', ['target defect', 'legitimate style'])
def test_space_separated_role_labels_filter_metadata_and_reject_creative_leaks(accepted_prefix, label):
    test = accepted_prefix
    row = test.manifest['requests'][0]
    sample = fixture_generation.collect.sample_path(test.output, row)
    answer = json.loads((sample / 'response.json').read_bytes())
    sentence = f'Only {label} may violate this causal dependency.'
    anchor = 'A factual dependency remains available. ' + sentence
    answer['preservation_anchors'][0] = anchor
    semantics = json.loads(test.files[row['semantics_path']])
    packet, mapping = reviewer.blinded_packet([(row, answer, semantics, {})], test.manifest_sha, 8)
    assert packet['families'][0]['proposed_preservation_anchors'][0]['proposal'] == 'A factual dependency remains available.'
    assert mapping['families'][0]['anchor_metadata_lineage'][0]['source_anchor'] == anchor
    assert mapping['families'][0]['anchor_metadata_lineage'][0]['removed_role_bearing_sentences'] == [sentence]
    answer['variants']['original']['text'] += '\nA ' + label + ' label leaks here.'
    snapshot = copy.deepcopy(answer)
    with pytest.raises(ValueError, match='role marker'):
        reviewer.blinded_packet([(row, answer, semantics, {})], test.manifest_sha, 8)
    assert answer == snapshot


@pytest.mark.parametrize('assessment', ['criterion', 'local_issue'])
def test_whitespace_only_exact_substring_cannot_be_review_evidence(review_inputs, assessment):
    packet, mapping, review, subset = review_inputs
    entry = next(e for e in review['variants'] if e['local_issue']['identified'])
    entry[assessment]['evidence'] = [{'source': 'variant', 'quote': ' '}]
    assert ' ' in next(v['text'] for f in packet['families'] for v in f['variants'] if v['variant_id'] == entry['variant_id'])
    with pytest.raises(ValueError, match='nonblank'):
        reviewer.validate_review(packet, mapping, review, subset)


def test_fresh_output_scope(accepted_prefix, tmp_path):
    for output in (accepted_prefix.frozen / 'child', accepted_prefix.output, ROOT / 'private-review'):
        with pytest.raises(ValueError): reviewer.prepare.output_preflight(output, (accepted_prefix.frozen, accepted_prefix.output))
    fresh = tmp_path / 'fresh'
    reviewer.prepare.output_preflight(fresh, (accepted_prefix.frozen, accepted_prefix.output))
    assert not fresh.exists()
