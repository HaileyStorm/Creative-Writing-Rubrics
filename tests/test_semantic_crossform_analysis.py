"""Bounded descriptive mechanics, not native-provider or literary-validity proof."""
from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


a = load('test_p1b_descriptive_analysis', ROOT / 'evaluation-results/hbq-semantic-crossform-p1b-matched-v1/analysis.py')
fixtures = load('analysis_preparation_fixtures', ROOT / 'tests/test_semantic_crossform_matched.py')


@pytest.fixture(scope='module')
def frozen(tmp_path_factory):
    cls = fixtures.fixtures.SemanticFixtureGenerationTests
    cls.setUpClass()
    try:
        tests = [{'ttcw_idx': i, 'torrance_dimension': 'mock', 'category': 'mock', 'question': 'A fixture criterion?',
                  'full_prompt': 'Fixture definition.\n\nGiven the story apply it.'} for i in range(1, 15)]
        manifest, files = fixtures.matched.build_design(cls.manifest, fixtures.answers(cls.manifest),
            {'sources/ttcw-tests.json': fixtures.matched.canonical(tests)}, cls.subset)
        root = tmp_path_factory.mktemp('descriptive-frozen')
        for name, raw in files.items():
            path = root / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(raw)
        yield manifest, files, root, a.load_hbq(manifest, root)
    finally:
        cls.doClassCleanups()


def bank(frozen, form='short_narrative', endpoint='sol', cycle=0, penalties_ca=False, context_quote=False):
    manifest, files, root, hbq = frozen
    rows = [r for r in manifest['requests'] if r['arm'] == 'hbq' and r['form'] == form and r['endpoint'] == endpoint and r['repeat'] == cycle]
    artifact = rows[0]['artifact_id']
    rows = sorted([r for r in rows if r['artifact_id'] == artifact], key=lambda r: r['batch'])
    compiled = json.loads(files['compiled/' + rows[0]['bundle_id'] + '.json'])
    penalty_ids = {q['question']['id'] for g in compiled['penalty_groups'] for q in g['questions']}
    quote = '"audience": []' if context_quote else files[rows[0]['sources'][0]['input_path']].decode().split()[0]
    records = []
    for row in rows:
        verdicts = [{'question_id': qid, 'verdict': 'CANNOT_ASSESS' if penalties_ca and qid in penalty_ids else 'YES',
                     'confidence': 1, 'note': 'Synthetic evidence witness.',
                     'evidence': [{'kind': 'exact_quote', 'reference': 'fixture',
                         'exact_quote': quote, 'summary': None}]} for qid in row['question_ids']]
        records.append({'request': row, 'response': {'verdicts': verdicts}})
    return rows, records


def test_complete_context_aware_passage_and_penalty_uncertainty(frozen):
    manifest, _, root, hbq = frozen
    rows, records = bank(frozen, form='novel_work_segment', context_quote=True)
    before = copy.deepcopy(records)
    result = a.score_bank(rows, records, hbq, root, manifest)
    assert result['score'] == 100 and result['state'] == 'SCORED'
    assert result['weighted_coverage'] == 1 and result['sensitivity_bounds'] == {'lower': 100, 'upper': 100}
    assert records == before
    rows, records = bank(frozen, penalties_ca=True)
    result = a.score_bank(rows, records, hbq, root, manifest)
    assert result['score'] == 100 and result['weighted_coverage'] == 1
    assert result['sensitivity_bounds'] == {'lower': 82, 'upper': 100} and result['uncertainty_width'] == 18
    assert all(p['coverage'] == 0 for p in result['penalty_coverage'])


@pytest.mark.parametrize('failure', ['missing_packet', 'duplicate_packet', 'missing_leaf', 'duplicate_leaf'])
def test_partial_or_nonunique_bank_never_scores(frozen, monkeypatch, failure):
    manifest, _, root, hbq = frozen
    rows, records = bank(frozen)
    records = copy.deepcopy(records)
    if failure == 'missing_packet': records.pop()
    if failure == 'duplicate_packet': records[-1] = copy.deepcopy(records[0])
    if failure == 'missing_leaf': records[0]['response']['verdicts'].pop()
    if failure == 'duplicate_leaf': records[0]['response']['verdicts'][-1] = copy.deepcopy(records[0]['response']['verdicts'][0])
    def forbidden(*args, **kwargs): raise AssertionError('Incomplete bank reached scalar scorer')
    monkeypatch.setattr(hbq['scorer'], 'score_bundle', forbidden)
    result = a.score_bank(rows, records, hbq, root, manifest)
    assert result['score'] is None and result['weighted_coverage'] is None and result['sensitivity_bounds'] is None


def test_strict_import_unadmitted_bank_no_scalar(frozen):
    manifest, _, root, hbq = frozen
    rows, records = bank(frozen)
    records = copy.deepcopy(records)
    records[0]['response']['verdicts'][0]['evidence'][0]['exact_quote'] = 'not in artifact or context'
    result = a.score_bank(rows, records, hbq, root, manifest)
    assert result['state'] == 'strict_import_unadmitted_no_scalar' and result['score'] is None


def test_all_planned_denominators_and_missing_dimensions(frozen):
    manifest, _, root, hbq = frozen
    inventory = [{'request': r, 'state': 'untouched', 'native_metrics': {}} for r in manifest['requests']]
    report = a.analyze(manifest, [], inventory, hbq, root)
    assert report['terminal_states'] == {'untouched': 1584} and report['admitted_requests'] == 0
    assert report['candidate'] is None and not report['human_alignment_claim'] and not report['oracle_accepted']
    assert sum(g['planned_requests'] for g in report['request_inventory']) == 1584
    assert all(p['score'] is None for p in report['item_profiles'])
    compact = next(g for g in report['scalar_diagnostics'] if g['arm'] == 'compact' and g['form'] == 'poem' and g['cycle'] == 0)
    assert len(compact['dimensions']) == 6 and all(v['missing_or_abstained'] == 6 for v in compact['dimensions'].values())
    poemetric = next(g for g in report['scalar_diagnostics'] if g['arm'] == 'poemetric' and g['cycle'] == 0)
    assert len(poemetric['dimensions']) == 8 and poemetric['primary']['mean'] is None
    text = json.dumps(report)
    assert 'fixture fixture' not in text and 'PRIVATE INTENDED' not in text
    with pytest.raises(ValueError, match='denominators'): a.analyze(manifest, [], inventory[:-1], hbq, root)


def test_poemetric_absence_not_quality_floor_or_numeric_delta():
    response = fixtures.poemetric_response()
    profile = a.scalar_profile('poemetric', response)
    profiles = {('sol', 'poem', 'poemetric', 'variant-opaque', cycle): copy.deepcopy(profile) for cycle in range(3)}
    profiles[('sol', 'poem', 'poemetric', 'variant-opaque', 1)]['dimensions']['item_7']['value'] = 1
    output = a.scalar_diagnostics(profiles)
    initial = next(o for o in output if o['cycle'] == 0)
    assert initial['primary']['mean'] == 5 and initial['primary']['exact_floor'] == 0
    assert initial['dimensions']['item_7']['absence_zero'] == 1 and initial['dimensions']['item_7']['exact_floor'] == 0
    repeat = a.repeat_diagnostics(profiles)[0]['cycle_pairs'][0]['dimensions']['item_7']
    assert repeat['native_nonabsence_difference']['observed_pairs'] == 0
    assert repeat['native_category_agreement_including_absence']['raw_agreement'] == 0


def test_three_cycle_native_differences_and_degenerate_kappa():
    profiles = {('sol', 'poem', 'hbq', 'variant-opaque', cycle): {
        'score': value, 'leaf_states': {'q1': 'YES', 'q2': 'CANNOT_ASSESS'}, 'dimensions': {}}
        for cycle, value in enumerate([100, 96, 98])}
    report = a.repeat_diagnostics(profiles)[0]
    assert report['complete_three_cycle_scalars'] == 1
    assert [p['primary_native_difference']['mean_signed_right_minus_left'] for p in report['cycle_pairs']] == [-4, -2, 2]
    leaves = report['cycle_pairs'][0]['native_leaf_state_agreement']
    assert leaves['planned_paired_units'] == 89 and leaves['paired_observed_units'] == 2 and leaves['raw_agreement'] == 1
    degenerate = a.agreement(['YES'] * 3, ['YES'] * 3, 3)
    assert degenerate['cohen_kappa'] is None and degenerate['raw_agreement'] == 1
    assert a.agreement([], [], 3)['raw_agreement'] is None


def pair_fixture(winners):
    rows, records = [], []
    for cycle, choices in enumerate(winners):
        for orientation, winner in zip(('AB', 'BA'), choices):
            ids = ['variant-left', 'variant-right'] if orientation == 'AB' else ['variant-right', 'variant-left']
            row = {'endpoint': 'sol', 'form': 'poem', 'arm': 'pairwise', 'pair_id': 'pair-opaque', 'repeat': cycle,
                   'orientation': orientation, 'sources': [{'id': i, 'side': side} for i, side in zip(ids, 'AB')]}
            rows.append(row)
            if winner is not None: records.append({'request': row, 'response': {'winner': winner}})
    return {'requests': rows}, records


def test_bidirectional_tie_abstention_and_conflict_remain_distinct():
    manifest, records = pair_fixture([('A', 'B'), ('TIE', 'TIE'), ('CANNOT_ASSESS', 'A')])
    report, decisions = a.pairwise_diagnostics(manifest, records)
    assert decisions[('sol', 'poem', 'pair-opaque', 0)] == 'variant-left'
    assert decisions[('sol', 'poem', 'pair-opaque', 1)] == 'TIE'
    assert ('sol', 'poem', 'pair-opaque', 2) not in decisions
    assert report['order'][2]['states'] == {'explicit_abstention': 1}
    assert report['repeat'][0]['complete_three_cycle_consistent_decisions'] == 0
    assert report['repeat'][0]['cycle_pairs'][0]['raw_agreement'] == 0
    manifest, records = pair_fixture([('A', 'A')])
    report, decisions = a.pairwise_diagnostics(manifest, records)
    assert not decisions and report['order'][0]['states'] == {'orientation_conflict': 1}


def test_matched_arm_directions_do_not_subtract_unlike_scales():
    manifest, _ = pair_fixture([('A', 'B')])
    profiles = {}
    for endpoint in ('grok', 'sol'):
        for arm, values in [('holistic', [6, 5]), ('compact', [1, 5])]:
            for artifact, value in zip(['variant-left', 'variant-right'], values):
                profiles[(endpoint, 'poem', arm, artifact, 0)] = {'score': value, 'leaf_states': {}, 'dimensions': {}}
    decisions = {(endpoint, 'poem', 'pair-opaque', 0): 'variant-left' for endpoint in ('grok', 'sol')}
    report = a.matched_contrasts(manifest, profiles, decisions)
    row = next(r for r in report['initial_matched_arm_pair_directions'] if r['endpoint'] == 'sol' and r['arms'] == ['compact', 'holistic'])
    assert row['paired_observed_units'] == 1 and row['raw_agreement'] == 0
    assert all(r['scalar']['mean_signed_right_minus_left'] == 0 for r in report['interendpoint_scalars'])


def test_native_reported_zero_distinct_from_unavailable(tmp_path):
    events = b'{"type":"turn.completed","usage":{"input_tokens":0,"output_tokens":4}}\n'
    (tmp_path / 'events.jsonl').write_bytes(events)
    metadata = {'path': 'events.jsonl', 'bytes': len(events), 'sha256': a.c.digest(events)}
    (tmp_path / 'native-result.json').write_text(json.dumps({'provider_artifacts': {'codex_events': metadata}}), encoding='utf-8')
    metrics = a.native_metrics(tmp_path, {'endpoint': 'sol'}, {'state': 'accepted'})
    assert metrics['input_tokens'] == 0 and metrics['cached_input_tokens'] is None and metrics['latency_seconds'] is None
    summary = a.inventory_summary([{'request': {'endpoint': 'sol', 'form': 'poem', 'arm': 'holistic', 'repeat': 0},
                                    'state': 'accepted', 'native_metrics': metrics}])[0]['native_metrics']
    assert summary['input_tokens']['sum_native_reported'] == 0 and summary['cached_input_tokens']['sum_native_reported'] is None


def test_collect_missing_and_unresolved_occupancy_preserves_slots(tmp_path, monkeypatch):
    rows = [{'endpoint': endpoint, 'endpoint_ordinal': 1, 'logical_sample_id': 'a' * 64,
             'request_sha256': endpoint} for endpoint in ('grok', 'sol')]
    results = {endpoint: tmp_path / endpoint for endpoint in ('grok', 'sol')}
    results['sol'].mkdir()
    sample = a.c.sample_path(results['sol'], rows[1]); sample.mkdir()
    monkeypatch.setattr(a.c, 'verify_job_binding', lambda *args: {})
    records, inventory, commitments = a.collect_evidence({'requests': rows}, 'pin', tmp_path, results, tmp_path, None, None, None)
    assert not records and not commitments
    assert [i['state'] for i in inventory] == ['untouched', 'started_unresolved']


def test_settled_rejection_and_replay_failure_never_become_votes(tmp_path, monkeypatch):
    rows = [{'endpoint': 'grok', 'endpoint_ordinal': i, 'logical_sample_id': str(i) * 64,
             'request_sha256': str(i)} for i in range(1, 4)]
    results = {'grok': tmp_path / 'grok', 'sol': tmp_path / 'sol'}
    results['grok'].mkdir()
    for row in rows:
        sample = a.c.sample_path(results['grok'], row); sample.mkdir()
        (sample / 'terminal.json').write_bytes(b'{}')
    monkeypatch.setattr(a.c, 'verify_job_binding', lambda *args: {})
    monkeypatch.setattr(a, 'native_metrics', lambda *args: {})
    def replay(sample, row, *args):
        if row['endpoint_ordinal'] == 1: return {'state': 'accepted'}, {'fixture_response': True}
        if row['endpoint_ordinal'] == 2: return {'state': 'semantic_rejected'}, None
        raise ValueError('Retained receipt differs')
    monkeypatch.setattr(a.c, 'replay', replay)
    records, inventory, commitments = a.collect_evidence({'requests': rows}, 'pin', tmp_path, results, tmp_path, None, None, None)
    assert [i['state'] for i in inventory] == ['accepted', 'semantic_rejected', 'replay_unadmitted']
    assert len(inventory) == 3 and len(records) == 1 and records[0]['request'] == rows[0]
    assert len(commitments) == 2
