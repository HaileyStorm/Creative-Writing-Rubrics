import csv
import importlib.util
import io
import json
from pathlib import Path
from types import SimpleNamespace

import pytest


HERE = Path(__file__).resolve().parents[1] / 'evaluation-results/hbq-poetry-human-reference-v1'
spec = importlib.util.spec_from_file_location('poetry_prediction_analysis_test', HERE / 'analysis_predictions.py')
a = importlib.util.module_from_spec(spec)
spec.loader.exec_module(a)


def test_missing_outer_or_closed_gate_fails_before_any_attempt_or_label_read(monkeypatch):
    def forbidden(path):
        pytest.fail('Read attempted before authoritative gate')
    monkeypatch.setattr(Path, 'read_bytes', forbidden)
    with pytest.raises(ValueError, match='Both exact outer'):
        a.outer_bindings({'sol': {'output': Path('live-sol')}, 'grok': {'output': Path('live-grok')}}, 'manifest')
    with pytest.raises(ValueError, match='Full960'):
        a.decode_humans(Path('sealed/manifest.json'), {'human_release_eligible': False}, {}, {})


def test_partial_duplicate_banks_have_no_scalar_and_native_absence_and_order_conflicts_stay_separate():
    ids = ['q' + str(i) for i in range(95)]
    rows = [{'batch': i+1, 'question_ids': ids[i*8:(i+1)*8], 'request_sha256': str(i)} for i in range(12)]
    admitted = [{'request': r, 'response': {'verdicts': [{'question_id': q, 'verdict': 'YES'} for q in r['question_ids']]}} for r in rows]
    hbq = {'ids': ids}
    assert a.score_bank(rows, admitted[:-1], hbq, None, None, {})['score'] is None
    duplicate = [*admitted[:-1], admitted[0]]
    assert a.score_bank(rows, duplicate, hbq, None, None, {})['state'] == 'incomplete_or_duplicate_bank_no_scalar'
    tids = ['t' + str(i) for i in range(10)]
    manifest = {'bank_ids': tids, 'pairs': [{'pair_id': str(i), 'left': tids[i*2], 'right': tids[i*2+1]} for i in range(5)]}
    profiles = {}
    for ep in a.ENDPOINTS:
        for arm in a.SCALES:
            for tid in tids:
                for cy in range(3):
                    entry = {'score': 5, 'state': 'SCORED'}
                    if arm == 'hbq': entry.update(leaf_states={}, coverage={'states': {}})
                    if arm == 'poemetric': entry['diagnostics'] = {'1': {'status': 'CANNOT_ASSESS', 'score': None}, '7': {'status': 'SCORED', 'score': 0}}
                    profiles[(ep, arm, tid, cy)] = entry
    orders = {(ep, p['pair_id'], cy, o): 1 if o == 'AB' else -1 for ep in a.ENDPOINTS for p in manifest['pairs'] for cy in range(3) for o in ('AB', 'BA')}
    report = a.prediction_diagnostics(manifest, profiles, orders)
    poemetric = report['native_profiles']['sol:poemetric']
    assert poemetric['floor'] == 0 and poemetric['ceiling'] == 30
    assert poemetric['separate_diagnostics']['7']['absence_zero'] == 30
    assert poemetric['separate_diagnostics']['1']['unavailable'] == 30
    assert report['pair_orientations']['sol']['order_conflicts'] == 15
    assert report['pair_orientations']['sol']['both_native_ties'] == 0
    assert poemetric['separate_diagnostics']['7']['affine_normalized_bands']['observed'] == 0
    assert poemetric['separate_diagnostics']['7']['affine_normalized_bands']['absence_zero_excluded'] == 30


def test_affine_bands_chance_agreement_signed_offset_and_shared_poem_ranks():
    assert a.affine_bands([6], 1, 7, 3)['normalized_at_or_above_90'] == 0
    assert a.affine_bands([4], 1, 5, 3)['normalized_at_or_above_90'] == 0
    assert a.affine_bands([92], 0, 100, 3)['normalized_at_or_above_90'] == 1
    agreement = a.categorical_agreement([('YES', 'YES'), ('YES', 'NO'), ('NO', 'NO'), ('NO', 'YES')], 6)
    assert agreement['raw_agreement'] == .5 and agreement['cohen_kappa'] == 0
    assert agreement['left_prevalence'] == {'YES': .5, 'NO': .5}
    assert agreement['unobserved_pairs'] == 2
    assert a.categorical_agreement([('YES', 'YES')], 1)['cohen_kappa'] is None
    tids = ['t'+str(i) for i in range(10)]
    manifest = {'bank_ids': tids, 'pairs': []}
    profiles = {}
    for ep in a.ENDPOINTS:
        for arm in a.SCALES:
            for i, tid in enumerate(tids):
                for cy in range(3):
                    score = (10+i if ep == 'sol' else 9+i) if arm == 'hbq' else (4 if ep == 'sol' else 3)
                    entry = {'score': score, 'state': 'SCORED'}
                    if arm == 'hbq': entry.update(leaf_states={}, coverage={'states': {}})
                    profiles[(ep, arm, tid, cy)] = entry
    cross = a.prediction_diagnostics(manifest, profiles, {})['same_arm_cross_endpoint']['hbq']
    assert cross['mean_signed_native_offset_sol_minus_grok'] == 1
    assert cross['shared_poem_rank_agreement']['by_cycle'][0]['spearman'] == 1
    assert cross['shared_poem_rank_agreement']['three_cycle_means']['shared_complete_poems'] == 10
    assert a.spearman([(1, 2), (1, 3)]) is None


def test_released_exact_row_join_keeps_missing_cells_and_rejects_unknown_values_and_changed_ids(tmp_path):
    projector_raw = (HERE / 'prepare_sources.py').read_bytes()
    source = a.load('poetry_fixture_projector', HERE / 'prepare_sources.py')
    (tmp_path / 'implementation').mkdir()
    (tmp_path / 'implementation/prepare_sources.py').write_bytes(projector_raw)
    profile, _ = a.human_profile()
    artifacts = {}

    def save(name, raw):
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        artifacts[name] = {'sha256': a.sha(raw), 'bytes': len(raw)}

    pins, links = [], []
    targets = {}
    for i in range(10):
        key = 'Author' + str(i) + '_' + str(i)
        tid = source.opaque('poem', key)
        text_hash = a.sha(('synthetic text ' + str(i)).encode())
        targets[i] = tid
        pins.append({'opaque_text_id': tid, 'sha256': text_hash, 'bytes': 42})
        links.append({'target_id': tid, 'CSV_key': {'Poet': 'Author'+str(i), 'poem_ID': str(i), 'commitment_sha256': a.sha(key.encode())},
                      'primary_text': {'sha256': text_hash, 'bytes': 42}})
    rows, csv_rows = [], []
    for assessor in range(696):
        rid = source.opaque('response', str(assessor))
        for i in range(10):
            rows.append({'source_record_index': len(rows), 'response_id': rid, 'target_id': targets[i], 'condition': 'nothing'})
            row = {f: '' for f in source.COLUMNS}
            row.update(ResponseId=str(assessor), Poet='Author'+str(i), poem_ID=str(i), condition='nothing')
            row.update({f: '4.0' for f in source.RATINGS})
            csv_rows.append(row)
    csv_rows[0]['overall_quality'] = ''
    rows[1]['condition'] = csv_rows[1]['condition'] = 'human'
    for field in source.RATINGS: csv_rows[1][field] = 'unused framing is not numeric'
    save('private/row-metadata.json', a.canonical(rows))
    save('private/source-linkage.json', a.canonical(links))
    gate = {'human_release_eligible': True, 'all_planned_verified_terminal': True, 'explicit_postprediction_release': True}

    def decode():
        stream = io.StringIO(newline='')
        writer = csv.DictWriter(stream, fieldnames=source.COLUMNS)
        writer.writeheader(); writer.writerows(csv_rows)
        save('sealed/targets/study2.csv', stream.getvalue().encode())
        manifest = a.canonical({'artifacts': artifacts})
        (tmp_path / 'manifest.json').write_bytes(manifest)
        metadata = {'reference_manifest_file_sha256': a.sha(manifest), 'source_projection_sha256': a.sha(projector_raw),
                    'presented_text_pins_manifest_declared': pins}
        return a.decode_humans(tmp_path / 'manifest.json', gate, profile, metadata)

    humans = decode()
    assert humans['public']['missing_rating_cells']['overall_quality'] == 1
    assert len(humans['ballots']) == 6959 and humans['public']['raw_human_values_in_report'] is False
    assert humans['public']['condition_rows'] == {'nothing': 6959, 'human': 1}
    assert humans['means'][targets[0]]['overall_quality'] == 4
    csv_rows[0]['overall_quality'] = '8'
    with pytest.raises(ValueError, match='Unknown human rating'):
        decode()
    csv_rows[0]['overall_quality'] = '4'
    csv_rows[0]['ResponseId'] = 'changed-source-id'
    with pytest.raises(ValueError, match='join differs'):
        decode()
