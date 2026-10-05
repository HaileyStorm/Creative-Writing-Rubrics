"""Study2 metadata and analysis readiness; no prediction or human-target reads."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPOSITORY = HERE.parents[1]
SELECTIVE = HERE.parent / 'hbq-matched-hanna-20261004/prepare.py'
SELECTIVE_SHA = '2d82e4959c3296ccaa6e6521adb46f85588427d429a544b36a2891ebaea8c7b0'
POLICY = 'study2_poetry_metadata_analysis_readiness_v1'
STUDY = 'study2_presented_poetry_matched_v1'
ARMS = {'hbq': 360, 'holistic': 30, 'compact': 30, 'poemetric': 30, 'pairwise': 30}
COUNTS = {'texts': 10, 'cycles': 3, 'bank_leaves': 95, 'bank_packets': 12, 'banks_per_endpoint': 30,
          'disjoint_pairs': 5, 'requests_per_endpoint': 480, 'requests_total': 960, 'arms_per_endpoint': ARMS}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')


def require(condition, message):
    if not condition:
        raise ValueError(message)


require(sha(SELECTIVE.read_bytes()) == SELECTIVE_SHA, 'Pinned selective metadata reader differs')
spec = importlib.util.spec_from_file_location('poetry_analysis_metadata_reader', SELECTIVE)
selective = importlib.util.module_from_spec(spec)
spec.loader.exec_module(selective)
project_json = selective.project_json


def pinned(path, expected, size=None):
    raw = Path(path).read_bytes()
    require(sha(raw) == expected and (size is None or len(raw) == size), 'Metadata artifact commitment differs')
    return raw


def relative(root, locator):
    path = (root / locator).resolve()
    require(path.is_relative_to(root.resolve()), 'Metadata locator leaves frozen root')
    return path


def metadata_view(manifest_path, manifest_sha, reference_path, explicit_release=False):
    # Check release before any source read; this surface never opens job/target trees.
    require(not explicit_release, 'Metadata-only analysis cannot release labels; true outer proof and full960 collector replay are required')
    manifest_path, reference_path = Path(manifest_path), Path(reference_path)
    raw = pinned(manifest_path, manifest_sha)
    manifest = project_json(raw, {key: True for key in (
        'study_id', 'stage', 'candidate', 'oracle_accepted', 'human_labels_supplied', 'human_alignment_claim',
        'execution_authority', 'reference_manifest_file_sha256', 'source_projection_sha256', 'source_projection_contract_sha256',
        'human_label_gate', 'counts', 'bank_ids', 'artifacts')})
    require(manifest['study_id'] == STUDY and manifest['stage'] == 'prospective_judging_preparation_only'
            and manifest['candidate'] is None and manifest['oracle_accepted'] is False
            and manifest['human_labels_supplied'] == 0 and manifest['human_alignment_claim'] is False
            and manifest['execution_authority'] is False and manifest['counts'] == COUNTS
            and len(manifest['bank_ids']) == len(set(manifest['bank_ids'])) == 10,
            'Frozen presented-poetry plan metadata differs')
    gate = manifest['human_label_gate']
    require(gate['policy'] == 'all_planned_verified_terminals_plus_explicit_postprediction_release_v1'
            and gate['requests_required'] == 960 and set(gate['endpoints']) == {'sol', 'grok'}
            and all(gate[key] is True for key in ('explicit_release_flag_required', 'verified_terminal_replay_required',
                                                'untouched_or_inflight_blocks_release', 'semantic_rejections_remain_missing')),
            'Frozen human label gate differs')
    root = manifest_path.resolve().parent
    embedded_meta = manifest['artifacts']['private/reference-manifest.json']
    embedded = pinned(relative(root, 'private/reference-manifest.json'), embedded_meta['sha256'], embedded_meta['bytes'])
    reference_raw = pinned(reference_path, manifest['reference_manifest_file_sha256'])
    require(reference_raw == embedded, 'Original/embedded source-reference manifests differ')
    reference = project_json(reference_raw, {'policy': True, 'contract_sha256': True, 'artifacts': True,
                                            'targets_sealed': True, 'prediction_release_authorized': True})
    require(reference['policy'] == 'study2_outcome_blind_poetry_source_v1' and reference['targets_sealed'] is True
            and reference['prediction_release_authorized'] is False
            and reference['contract_sha256'] == manifest['source_projection_contract_sha256'],
            'Sealed source-reference metadata differs')
    summary_meta = reference['artifacts']['summary.json']
    summary_raw = pinned(relative(reference_path.resolve().parent, 'summary.json'), summary_meta['sha256'], summary_meta['bytes'])
    summary = project_json(summary_raw, {'rows': True, 'targets': True, 'unique_response_ids': True, 'source_files': True})
    require(summary['targets'] == 10 and summary['rows'] == 6960 and summary['unique_response_ids'] == 696,
            'Inherited Study2 structural count metadata differs')
    text_pins = []
    for tid in manifest['bank_ids']:
        source = reference['artifacts']['sealed/texts/' + tid + '.qsf.txt']
        presented = manifest['artifacts']['inputs/' + tid + '.txt']
        require((source['sha256'], source['bytes']) == (presented['sha256'], presented['bytes']),
                'Presented text/source projection metadata differs')
        text_pins.append({'opaque_text_id': tid, 'sha256': source['sha256'], 'bytes': source['bytes']})
    require(len({p['sha256'] for p in text_pins}) == 10, 'Presented text metadata is not unique')
    predictions = {'state': 'unavailable_until_verified_native_replay', 'endpoint_terminal_counts': None,
                   'missing_rejected_omitted_or_inflight_counts': None, 'coverage': None, 'hbq_scalars_and_bounds': None,
                   'native_floors_ceilings': None, 'within_item_repeats': None, 'pair_orientation_consistency': None}
    report = {'schema_version': 1, 'policy': POLICY, 'view': 'metadata_only_analysis_readiness',
        'implementation_sha256': sha(Path(__file__).read_bytes()), 'selective_reader_sha256': SELECTIVE_SHA,
        'manifest_file_sha256': manifest_sha, 'reference_manifest_file_sha256': sha(reference_raw),
        'reference_summary_file_sha256': sha(summary_raw), 'source_projection_sha256': manifest['source_projection_sha256'],
        'planned': {'requests_total': 960, 'endpoints': {ep: {'requests': 480, 'arms': ARMS} for ep in ('sol', 'grok')},
                    'presented_poems': 10, 'bank_unique_leaves': 95, 'bank_packets': 12, 'cycles': 3,
                    'full_bank_required_for_scalar': True, 'scope': 'presented_poetic_artifact_original_completion_unknown'},
        'inherited_structural_declarations': {'assessor_response_ids': summary['unique_response_ids'],
            'poem_rating_rows': summary['rows'], 'basis': 'Pinned source-projector summary; raw CSV targets and metadata are not reread',
            'raw_source_files_manifest_declared': summary['source_files'], 'raw_source_files_read': False},
        'presented_text_pins_manifest_declared': text_pins, 'presented_text_bytes_read': False,
        'prediction_diagnostics': predictions,
        'native_scale_contracts': {'hbq': {'scale': [0, 100], 'requirement': 'Complete unique admitted95-leaf/12-packet context-aware bank; positive/penalty completeness and sensitivity bounds separate'},
            'holistic': {'scale': [1, 7]}, 'compact': {'overall_scale': [1, 5], 'dimensions': 6},
            'poemetric': {'primary_item': 10, 'primary_scale': [1, 5], 'aggregate': None,
                          'items_1_2': 'CANNOT_ASSESS/null', 'absence_zero_diagnostics_only': [7, 8],
                          'scope': 'Named unspecified-form adaptation; original fixed-form construct-transfer caveat'},
            'pairwise': {'outcomes': ['A', 'B', 'TIE', 'CANNOT_ASSESS'], 'orientations': ['AB', 'BA'],
                         'design': 'Five disjoint metadata pairs; matched contrasts, not ranking graph'}},
        'human_label_gate': {'policy': gate['policy'], 'all_planned_verified_terminal': False,
            'completion_evidence_state': 'not_inspected_no_true_outer_proof_supplied', 'explicit_postprediction_release': False,
            'human_release_eligible': False, 'human_targets_opened': False,
            'future_requirements': ['Actual outer terminal/handle/invocation bound to each selected native job',
                'Existing collector full960 verified-terminal gate', 'Explicit postprediction human release',
                'Separately implemented and verified source-to-human-target join']},
        'human_alignment': {'state': 'unimplemented_and_unverified', 'metrics': None},
        'native_jobs_or_attempt_trees_opened': False, 'labels_read': False, 'human_targets_opened': False,
        'provider_calls': 0, 'candidate': None,
        'limitations': ['Metadata commitments are verified; source text and target bytes are not opened or rehashed.',
            'Interrupted old jobs have no supplied true outer proof; prediction metrics remain unavailable, not zero.',
            'This module implements metadata readiness only; no native replay or human-alignment adapter is advertised.',
            'All ten items are descriptive presented stimuli; no whole-author-work, origin, unused-data, rights, population or human-alignment claim.',
            'Native scales remain separate; no cross-scale subtraction or POEMetric diagnostic aggregate.']}
    return report


def output_path(path, inputs):
    path = Path(path).resolve()
    require(not path.exists() and not path.is_relative_to(REPOSITORY), 'Output must be fresh and outside repository')
    require(all(not path.is_relative_to(Path(source).resolve().parent) for source in inputs), 'Output overlaps frozen inputs')
    return path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--manifest-sha256', required=True)
    parser.add_argument('--reference-manifest', type=Path, required=True)
    parser.add_argument('--output-root', type=Path, required=True)
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--explicit-postprediction-release', action='store_true')
    args = parser.parse_args(argv)
    output = output_path(args.output_root, (args.manifest, args.reference_manifest))
    report = metadata_view(args.manifest, args.manifest_sha256, args.reference_manifest, args.explicit_postprediction_release)
    raw = canonical(report) + b'\n'
    receipt = {key: report[key] for key in ('policy', 'implementation_sha256', 'manifest_file_sha256',
        'reference_manifest_file_sha256', 'reference_summary_file_sha256', 'planned')}
    receipt.update(report_sha256=sha(raw), dry_run=args.dry_run, human_targets_opened=False, labels_read=False,
                   native_jobs_or_attempt_trees_opened=False, human_release_eligible=False, provider_calls=0)
    if not args.dry_run:
        output.mkdir(parents=True, exist_ok=False)
        for name, content in {'analysis.py': Path(__file__).read_bytes(), 'analysis.json': raw,
            'invocation.json': canonical({'manifest_path_local_only': str(args.manifest.resolve()),
                'reference_manifest_path_local_only': str(args.reference_manifest.resolve()),
                'view': 'metadata_only'}) + b'\n',
            'terminal.json': canonical({**receipt, 'state': 'completed_metadata_only'}) + b'\n'}.items():
            with (output / name).open('xb') as stream:
                stream.write(content)
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
