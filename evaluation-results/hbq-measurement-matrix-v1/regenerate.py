"""Regenerate a portable matrix from three public aggregates and safe metadata."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re

KEY = ('dataset', 'population', 'form', 'endpoint', 'arm', 'reference_axis',
       'cohort_view', 'metric', 'unit')


def require(ok, message):
    if not ok:
        raise ValueError(message)


def pointer(parts):
    return '/'+('/'.join(str(part).replace('~', '~0').replace('/', '~1') for part in parts))


def at(document, parts):
    for part in parts:
        document = document[part]
    return document


def take(source, names):
    return {name: source[name] for name in names if name in source}


def bootstrap(source, field, kind, interval_field):
    if field not in source:
        return {'status': 'not_reported', 'value': None}
    saved = source[field]
    return {'kind': kind, 'status': saved.get('state',
            'reported' if saved.get(interval_field) is not None else 'null_in_source'),
            'value': saved.get(interval_field), 'source_interval_field': interval_field,
            'estimation_metadata': saved}


def reader_aliases(public, extension):
    dryad = public['dryad']; kyoto = public['kyoto_qsf12']
    contrasts = {}
    for name, item in dryad['pairwise_availability_conditioned_contrasts'].items():
        extra = extension['dryad']['contrast_results'][name]
        contrasts[name] = {**item, **take(extra, ('full_planned_missing_outcome_bounds', 'missing_bounds_type')),
            'conditional_story_bootstrap': {**item['conditional_story_bootstrap'],
                                            **extra['conditional_story_bootstrap']}}
    differences = {}
    for family in ('hbq_ttcw_primary_differences', 'ladder_primary_differences'):
        differences[family] = {name: {**item, **extension['kyoto_qsf12'][family][name]}
                               for name, item in kyoto[family].items()}
    return {'dryad': {'planned': dryad['planned_stories'],
        'common_five': dryad['fixed_all_five_numeric_common_stories'],
        'arms': dryad['arms'], 'common_distributions': dryad['fixed_all_five_common_distributions'],
        'common_rhos': dryad['fixed_all_five_common_rhos'], 'contrast_results': contrasts,
        'limits': dryad['limits']},
        'kyoto_qsf12': {'methods': kyoto['methods'], 'primary_rhos': kyoto['primary_fixed12_rhos'],
                         **differences, 'limits': kyoto['limits']}}


def reader_source(parts):
    mapped = list(parts)
    aliases = {'common_distributions': 'fixed_all_five_common_distributions',
               'common_rhos': 'fixed_all_five_common_rhos',
               'contrast_results': 'pairwise_availability_conditioned_contrasts',
               'primary_rhos': 'primary_fixed12_rhos'}
    if len(mapped) > 1:
        mapped[1] = aliases.get(mapped[1], mapped[1])
    return pointer(mapped)


def build(inputs, metadata, metadata_ref):
    rows = []; pins = metadata['effective_public_inputs']; t = inputs['ttcw_initial']
    for field in ('ttcw_initial_and_selected_repeats', 'dryad', 'kyoto'):
        require(metadata['axis_bindings'][field]['form'] == 'prose.short_story',
                'Exact declared CWR task-scope metadata required')

    def emit(family, parts, dataset, population, arm, axis, view, metric, unit,
             *, denominators, point=None, interval=None, bounds=None, status=None, limits=()):
        source = at(inputs[family], parts)
        axis_family = ('dryad' if dataset == 'Dryad_DEV30' else 'kyoto' if dataset == 'Kyoto_QSF12'
                       else 'ttcw_initial_and_selected_repeats')
        binding = {**metadata['axis_bindings'][axis_family], 'source_commitments': metadata['axis_source_commitments'],
            'metadata_pointer': '/axis_bindings/'+axis_family, 'scope': metadata['axis_scope'],
            'per_attempt_field_attestation': 'unresolved_not_replayed_by_this_projection'}
        if family == 'ttcw_repeats':
            binding['observed_summary'] = {'value': inputs[family]['provenance']['observed_native_controls'],
                'source_pointer': '/provenance/observed_native_controls', 'basis': 'source-declared observed summary'}
        if dataset == 'Kyoto_QSF12' and arm in ('constant_zero', 'lexical_token_count', 'raw_type_token_ratio'):
            binding = {**binding, 'model': 'not_applicable', 'reasoning': 'not_applicable',
                       'endpoint': 'not_applicable', 'scope': 'Source-only diagnostic control; no native judge call'}
        row = {'dataset': dataset, 'population': population, 'form': binding['form'],
            'endpoint': binding['endpoint'], 'model': binding['model'], 'reasoning': binding['reasoning'],
            'arm': arm, 'reference_axis': axis, 'cohort_view': view, 'metric': metric, 'unit': unit,
            'source_ref': pins[family], 'source_pointer': reader_source(parts) if family == 'reader' else pointer(parts),
            'source_subtree': None if metric == 'efficiency' and status == 'not_reported' else source,
            'source_subtree_basis': 'Explicit public-field aliases plus supplement' if family == 'reader' else 'Original public aggregate subtree',
            'original_input_commitment': metadata['original_input_commitments'][family],
            'original_source_pointer': pointer(parts), 'axis_binding': binding,
            'denominators': denominators, 'point': point,
            'interval': interval if interval is not None else {'status': 'not_reported', 'value': None},
            'missing_outcome_bounds': bounds,
            'status': status if status is not None else
                (source.get('state', 'reported_source_subtree') if isinstance(source, dict) else 'reported_source_value'),
            'limitations': list(limits)}
        if metric == 'efficiency' and status == 'not_reported':
            row['source_context_pointer'] = row['source_pointer']
        if family == 'reader' and len(parts) > 2 and parts[1] in (
                'contrast_results', 'hbq_ttcw_primary_differences', 'ladder_primary_differences'):
            row['supplement_ref'] = metadata_ref
            row['supplement_pointer'] = pointer(['reader_extensions', *parts[:3]])
        rows.append(row)

    population = 'existing_expert_reference_development'
    expert = 'mean_14_binary_creativity_tests_three_expert_ballots_per_story'
    tlimits = metadata['limitations']['ttcw_initial']
    emit('ttcw_initial', ['coverage'], 'TTCW', population, 'all_five', expert, 'planned_and_available',
         'coverage', 'story_and_plot', denominators=t['coverage'], point=t['coverage'], limits=tlimits)
    for arm, saved in t['available_method_results_different_denominators'].items():
        base = ['available_method_results_different_denominators', arm]
        for field, metric, unit, point_field, denominator_fields in (
            ('association', 'signed_spearman', 'story', 'rho', ('works', 'expected_works', 'missing_works')),
            ('distribution', 'score_distribution', 'story', None, ('n',)),
            ('within_plot_expert_derived_pair_agreement', 'expert_derived_pair_agreement',
             'within_plot_unordered_story_pair', 'fraction',
             ('assessed_denominator', 'expected_denominator', 'unassessed', 'unordered_pairs', 'expert_ties_excluded'))):
            item = saved[field]
            emit('ttcw_initial', base+[field], 'TTCW', population, arm, expert, 'method_specific_available',
                 metric, unit, denominators={**take(item, denominator_fields),
                     'represented_plot_clusters': saved['represented_plot_clusters']},
                 point=item.get(point_field) if point_field else item,
                 interval=bootstrap(item, 'bootstrap', 'plot_cluster_percentile_95', 'percentile_95'),
                 bounds=take(item, ('unobserved_outcome_bounds', 'full_denominator_bounds')), limits=tlimits)
    for arm, item in t['same_28_score_distributions'].items():
        emit('ttcw_initial', ['same_28_score_distributions', arm], 'TTCW', population, arm, expert,
             'all_five_exact_common28', 'score_distribution', 'story', denominators=take(item, ('works',)),
             point=item, limits=tlimits)
    for family in ('hbq_pair_specific_associations', 'other_pair_specific_associations'):
        for pair, item in t[family].items():
            emit('ttcw_initial', [family, pair], 'TTCW', population,
                 'hbq__'+pair if family.startswith('hbq_') else pair, expert,
                 'pair_specific_numeric_intersection', 'paired_delta_spearman', 'story',
                 denominators=take(item, ('works', 'expected_works', 'missing_works')),
                 point=take(item, ('delta_rho', 'left_rho_same_works', 'right_rho_same_works')),
                 interval=bootstrap(item, 'bootstrap', 'plot_cluster_percentile_95', 'percentile_95'),
                 bounds=take(item, ('unobserved_outcome_bounds',)), limits=tlimits)
    pair = t['pairwise_expert_derived_agreement']
    for field in ('each_order_against_expert', 'order_averaged_within_plot_agreement', 'repeat_same_order_agreement'):
        item = pair[field]
        emit('ttcw_initial', ['pairwise_expert_derived_agreement', field], 'TTCW', population,
             'pairwise', expert, field, 'expert_derived_pair_agreement',
             'ordered_pair' if field == 'each_order_against_expert' else 'unordered_pair',
             denominators=take(item, ('assessed_denominator', 'expected_denominator', 'unassessed', 'expert_ties_excluded')),
             point=item['fraction'], interval=bootstrap(item, 'bootstrap', 'plot_cluster_percentile_95', 'percentile_95'),
             bounds=take(item, ('full_denominator_bounds',)), limits=tlimits)
    emit('ttcw_initial', ['pairwise_expert_derived_agreement'], 'TTCW', population, 'pairwise', expert,
         'initial_reverse_order_diagnostic', 'order_consistency', 'unordered_pair',
         denominators=take(pair, ('initial_assessed_orders', 'initial_expected_orders', 'paired_order_complete_pairs', 'unordered_pairs')),
         point=take(pair, ('paired_order_disagreements', 'paired_order_opposite_direction_pairs',
                          'mean_absolute_canonical_order_gap', 'global_rho', 'global_rho_reason')), limits=tlimits)
    tests = t['ttcw14_expert_test_agreement']
    for field in ('expert_majority', 'individual_ballots'):
        item = tests[field]
        emit('ttcw_initial', ['ttcw14_expert_test_agreement', field], 'TTCW', population, 'ttcw14', field,
             'all_reported_test_cells', 'test_agreement', 'story_test_cell' if field == 'expert_majority' else 'expert_ballot',
             denominators=take(item, ('assessed_denominator', 'expected_denominator', 'unassessed')),
             point=item['fraction'], interval=bootstrap(item, 'bootstrap', 'plot_cluster_percentile_95', 'percentile_95'),
             bounds=take(item, ('full_denominator_bounds',)), limits=tlimits)
    for test, saved in tests['by_test'].items():
        for field, item in saved.items():
            emit('ttcw_initial', ['ttcw14_expert_test_agreement', 'by_test', test, field], 'TTCW', population,
                 'ttcw14', field+'/test_'+test, 'test_specific', 'test_agreement',
                 'story_test_cell' if field == 'majority' else 'expert_ballot',
                 denominators=take(item, ('assessed_denominator', 'expected_denominator', 'unassessed')),
                 point=item['fraction'], bounds=take(item, ('full_denominator_bounds',)), limits=tlimits)
    operations = t['accepted_request_operations']
    for group, saved, path in [('all_accepted', operations['all_accepted'], ['all_accepted'])]+[
            (arm, saved, ['by_arm', arm]) for arm, saved in operations['by_arm'].items()]:
        for metric, item in saved['metrics'].items():
            emit('ttcw_initial', ['accepted_request_operations', *path, 'metrics', metric], 'TTCW',
                 'accepted_requests_only', group, 'not_applicable', 'accepted_only_operations', metric,
                 'milliseconds' if metric.endswith('_ms') else 'tokens',
                 denominators={**take(item, ('observed', 'missing')),
                               'accepted_requests_in_group': saved['accepted_requests_in_group']},
                 point=take(item, ('sum', 'mean', 'median', 'p90_nearest_rank', 'minimum', 'maximum')),
                 limits=operations['limits'])

    reader = inputs['reader']; dryad = reader['dryad']; kyoto = reader['kyoto_qsf12']
    for dataset, section, reference_population in (
            ('Dryad_DEV30', 'dryad', 'pooled_reader_means'),
            ('Kyoto_QSF12', 'kyoto_qsf12', 'equal_response_reader_means')):
        saved = reader[section]; limits = saved['limits']
        for arm, item in saved['arms' if section == 'dryad' else 'methods'].items():
            fields = ('planned_packets', 'received_packets', 'request_complete_stories') if section == 'dryad' else (
                'admitted_parent_packets', 'additional_native_packets', 'complete_original_request_banks')
            base = [section, 'arms' if section == 'dryad' else 'methods', arm]
            emit('reader', base, dataset, reference_population, arm, 'not_applicable', 'method_specific_available',
                 'packet_and_score_availability', 'packet_and_story', denominators=take(item, fields),
                 point=take(item, (*fields, 'states')), limits=limits)
            distribution = item['distribution']
            emit('reader', base+['distribution'], dataset, reference_population, arm, 'not_applicable',
                 'method_specific_available', 'score_distribution', 'story',
                 denominators=take(distribution, ('available', 'planned', 'missing', 'numeric_stories',
                                                 'planned_stories', 'missing_stories', 'available_unordered_pairs')),
                 point=distribution, limits=limits)
        emit('reader', [section], dataset, reference_population, 'all_methods', 'not_applicable',
             'reported_aggregate_scope', 'efficiency', 'request_operations', denominators={},
             status='not_reported', limits=[*limits, 'No reader efficiency aggregate supplied; missing is not zero'])
    for arm, item in dryad['common_distributions'].items():
        emit('reader', ['dryad', 'common_distributions', arm], 'Dryad_DEV30', 'pooled_reader_means', arm,
             'not_applicable', 'all_five_exact_common27', 'score_distribution', 'story',
             denominators=take(item, ('available', 'planned', 'missing', 'available_unordered_pairs')),
             point=item, limits=dryad['limits'])
    for name, point in dryad['common_rhos'].items():
        _view, arm, axis = name.split('/')
        emit('reader', ['dryad', 'common_rhos', name], 'Dryad_DEV30', 'pooled_reader_means', arm, axis,
             'all_five_exact_common27', 'signed_spearman', 'story',
             denominators={'common_five': dryad['common_five'], 'planned': dryad['planned']},
             point=point, limits=dryad['limits'])
    for name, item in dryad['contrast_results'].items():
        emit('reader', ['dryad', 'contrast_results', name], 'Dryad_DEV30', 'pooled_reader_means',
             'hbq__'+item['arm'], item['axis'], 'pair_specific_numeric_intersection', 'paired_delta_spearman', 'story',
             denominators=take(item, ('available', 'planned', 'missing')),
             point=take(item, ('point', 'HBQ_rho_on_common_set', 'comparator_rho_on_common_set')),
             interval=bootstrap(item, 'conditional_story_bootstrap', 'conditional_story_percentile_95', 'interval95'),
             bounds=take(item, ('full_planned_missing_outcome_bounds', 'missing_bounds_type')),
             status=item['interpretation'], limits=[*dryad['limits'], *item['inconclusive_reasons']])
    for name, item in kyoto['primary_rhos'].items():
        _kind, arm, axis = name.split('/')
        emit('reader', ['kyoto_qsf12', 'primary_rhos', name], 'Kyoto_QSF12', 'equal_response_reader_means',
             arm, axis, 'primary_fixed12', 'signed_spearman', 'story',
             denominators=take(item, ('complete_values', 'planned')), point=item['point'],
             interval={'status': 'not_estimated', 'value': None}, limits=kyoto['limits'])
    for field in ('hbq_ttcw_primary_differences', 'ladder_primary_differences'):
        for name, item in kyoto[field].items():
            _kind, left, right, axis = name.split('/')
            for view in ('primary_fixed12', 'secondary_exact_common_diagnostic'):
                stat = item[view]
                emit('reader', ['kyoto_qsf12', field, name, view], 'Kyoto_QSF12', 'equal_response_reader_means',
                     left+'__'+right, axis, view, 'paired_delta_spearman', 'story',
                     denominators=take(stat, ('complete_values', 'planned', 'works', 'missing_of_planned12')),
                     point=stat['point'], interval={'status': 'not_estimated', 'value': None,
                         'interval_estimated': item['interval_estimated']},
                     bounds=take(item, ('full12_missing_outcome_bounds', 'bounds_are_confidence_intervals')),
                     limits=[*kyoto['limits'], 'Secondary common-set diagnostic never replaces primary_fixed12'])

    repeats = inputs['ttcw_repeats']; limits = repeats['limitations']
    specs = (
        ('HBQ_raw_leaf_agreement', 'hbq', 'raw_four_state_leaf_agreement', 'matched_leaf_pair',
         ('matched_leaf_pairs', 'joint_binary_pairs')),
        ('HBQ_order_comparison', 'hbq', 'bank_order_comparison', 'bank_pair', ('available_bank_pairs',)),
        ('comparator_scalars', 'all_comparators', 'repeat_scalar_agreement', 'available_scalar_comparison', ('available',)),
        ('pair_judgments', 'pairwise', 'repeat_orientation_agreement', 'ordered_pair_comparison',
         ('available_pair_groups', 'available_same_orientation_comparisons', 'complete_assessed_reverse_orientation_pairs',
          'incomplete_reverse_orientation_pairs')),
        ('evidence_set_overlap', 'hbq', 'exact_saved_evidence_set_overlap', 'matched_leaf_pair', ('matched_leaf_pairs',)),
    )
    for field, arm, metric, unit, denominator_fields in specs:
        item = repeats[field]
        emit('ttcw_repeats', [field], 'TTCW', 'selected_model_repeat_comparisons', arm, 'model_initial_vs_cycle2',
             'selected_ancestry_eligible_cycle2', metric, unit, denominators=take(item, denominator_fields), point=item,
             interval={'status': 'not_estimated', 'value': None,
                       'confidence_intervals_estimated': repeats['confidence_intervals_estimated']}, limits=limits)
    for index, item in enumerate(repeats['HBQ_banks']):
        emit('ttcw_repeats', ['HBQ_banks', index], 'TTCW', 'selected_model_repeat_comparisons', 'hbq',
             'model_initial_vs_cycle2', item['bank_label'], 'bank_repeat_agreement', 'matched_leaf_pair',
             denominators=take(item, ('leaves', 'packets')), point=item,
             interval={'status': 'not_estimated', 'value': None}, limits=limits)
    for index, item in enumerate(repeats['comparator_scalars']['by_arm']):
        emit('ttcw_repeats', ['comparator_scalars', 'by_arm', index], 'TTCW', 'selected_model_repeat_comparisons',
             item['arm'], 'model_initial_vs_cycle2', 'available_repeat_comparisons', 'repeat_scalar_agreement',
             'scalar_comparison', denominators=take(item, ('available_comparisons',)), point=item,
             interval={'status': 'not_estimated', 'value': None}, limits=limits)
    emit('ttcw_repeats', ['scope'], 'TTCW', 'selected_model_repeat_comparisons', 'all_arms', 'not_applicable',
         'selected_ancestry_eligible_cycle2', 'efficiency', 'request_operations', denominators={},
         status='not_reported', limits=[*limits, 'No selected-repeat efficiency aggregate supplied; missing is not zero'])
    require(len({tuple(row[key] for key in KEY) for row in rows}) == len(rows), 'Unique typed matrix keys required')
    require(len(rows) == metadata['expected_row_coverage']['total'], 'Original metric-family row coverage differs')
    return rows


def checked(root, reference):
    path = (root/reference['path']).resolve()
    require(not Path(reference['path']).is_absolute() and path.is_relative_to(root), 'Repository-relative public input required')
    raw = path.read_bytes()
    require(len(raw) == reference['bytes'] and hashlib.sha256(raw).hexdigest() == reference['sha256'],
            'Exact public aggregate bytes required')
    return json.loads(raw)


def encode(value):
    text = json.dumps(value, sort_keys=True, ensure_ascii=True, allow_nan=False)
    require(not re.search(r'(?i)([a-z]:[\\/]|[\w.+-]+@[\w.-]+|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})', text),
            'Private operational marker in public projection')
    return (text+'\n').encode('utf-8')


def regenerate(repo_root, output):
    root = Path(repo_root).resolve()
    metadata_path = Path(__file__).resolve().with_name('source-metadata.json')
    raw = metadata_path.read_bytes(); metadata = json.loads(raw)
    require(metadata['policy'] == 'portable_existing_measurements_aggregate_projection_v1', 'Exact metadata policy required')
    metadata_ref = {'path': 'evaluation-results/hbq-measurement-matrix-v1/source-metadata.json',
                    'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}
    inputs = {name: checked(root, item) for name, item in metadata['effective_public_inputs'].items()}
    inputs['reader'] = reader_aliases(inputs['reader'], metadata['reader_extensions'])
    rows = build(inputs, metadata, metadata_ref)
    payload = b''.join(encode(row) for row in rows)
    with Path(output).open('xb') as stream:
        stream.write(payload)
    require(Path(output).read_bytes() == payload, 'Output readback differs')
    return {'rows': len(rows), 'sha256': hashlib.sha256(payload).hexdigest(), 'bytes': len(payload),
            'new_statistics': False, 'private_input_required': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(regenerate(args.repo_root, args.output), sort_keys=True))


if __name__ == '__main__':
    main()
