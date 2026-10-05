import importlib.util
import json
from pathlib import Path

import pytest


MODULE = Path(__file__).resolve().parents[1] / 'evaluation-results/hbq-poetry-human-reference-v1/analysis.py'
spec = importlib.util.spec_from_file_location('poetry_reference_analysis', MODULE)
analysis = importlib.util.module_from_spec(spec)
spec.loader.exec_module(analysis)


def test_metadata_view_never_opens_targets_text_or_jobs_and_cannot_release(tmp_path, monkeypatch):
    judging, reference = tmp_path / 'judging', tmp_path / 'reference'
    (judging / 'private').mkdir(parents=True)
    reference.mkdir()

    def store(path, value):
        raw = json.dumps(value).encode()
        path.write_bytes(raw)
        return {'sha256': analysis.sha(raw), 'bytes': len(raw)}

    summary_path = reference / 'summary.json'
    # Excluded values cannot even be decoded by the metadata reader.
    summary_raw = b'{"rows":6960,"targets":10,"unique_response_ids":696,"source_files":{},"sealed_ratings":"\\q","poem_text":"\\q"}'
    summary_path.write_bytes(summary_raw)
    artifacts = {'summary.json': {'sha256': analysis.sha(summary_raw), 'bytes': len(summary_raw)}}
    presented = {}
    ids = ['opaque-' + str(i) for i in range(10)]
    for tid in ids:
        pin = {'sha256': analysis.sha(tid.encode()), 'bytes': 42}
        artifacts['sealed/texts/' + tid + '.qsf.txt'] = pin
        presented['inputs/' + tid + '.txt'] = pin
    reference_path = reference / 'manifest.json'
    reference_pin = store(reference_path, {'policy': 'study2_outcome_blind_poetry_source_v1',
        'contract_sha256': 'contract', 'targets_sealed': True, 'prediction_release_authorized': False,
        'artifacts': artifacts})
    embedded_path = judging / 'private/reference-manifest.json'
    embedded_path.write_bytes(reference_path.read_bytes())
    presented['private/reference-manifest.json'] = reference_pin
    manifest_path = judging / 'manifest.json'
    manifest_pin = store(manifest_path, {'study_id': analysis.STUDY,
        'stage': 'prospective_judging_preparation_only', 'candidate': None, 'oracle_accepted': False,
        'human_labels_supplied': 0, 'human_alignment_claim': False, 'execution_authority': False,
        'counts': analysis.COUNTS, 'bank_ids': ids, 'artifacts': presented,
        'reference_manifest_file_sha256': reference_pin['sha256'], 'source_projection_sha256': 'projector',
        'source_projection_contract_sha256': 'contract', 'human_label_gate': {
            'policy': 'all_planned_verified_terminals_plus_explicit_postprediction_release_v1',
            'requests_required': 960, 'endpoints': ['sol', 'grok'], 'explicit_release_flag_required': True,
            'verified_terminal_replay_required': True, 'untouched_or_inflight_blocks_release': True,
            'semantic_rejections_remain_missing': True}})
    allowed = {manifest_path.resolve(), reference_path.resolve(), embedded_path.resolve(),
               summary_path.resolve(), MODULE.resolve()}
    original = Path.read_bytes
    reads = []

    def guarded_read(path):
        assert path.resolve() in allowed, 'Attempted sealed text/target or mutable job read'
        reads.append(path.resolve())
        return original(path)

    monkeypatch.setattr(Path, 'read_bytes', guarded_read)
    report = analysis.metadata_view(manifest_path, manifest_pin['sha256'], reference_path)
    assert set(reads) == allowed
    assert report['planned']['requests_total'] == 960
    assert report['inherited_structural_declarations']['poem_rating_rows'] == 6960
    assert report['prediction_diagnostics']['coverage'] is None
    assert report['prediction_diagnostics']['hbq_scalars_and_bounds'] is None
    assert report['human_alignment']['state'] == 'unimplemented_and_unverified'
    assert not report['human_label_gate']['human_release_eligible']
    assert not report['labels_read'] and not report['native_jobs_or_attempt_trees_opened']
    reads.clear()
    with pytest.raises(ValueError, match='cannot release labels'):
        analysis.metadata_view(manifest_path, manifest_pin['sha256'], reference_path, explicit_release=True)
    assert reads == []
