"""Declared-scale affine bands for the pinned descriptive P1 item profiles."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from fractions import Fraction
import hashlib
import importlib.util
import json
from pathlib import Path

POLICY = 'descriptive_p1_declared_affine_bands_v1'
SOURCE_SHA = '9f3c5dec6177694c8053a680fdeb716d34008a9dc289c124323480f874f0e0df'
SOURCE_POLICY = 'descriptive_p1_saved_decode_chain_analysis_v1'
READER_SHA = '2d82e4959c3296ccaa6e6521adb46f85588427d429a544b36a2891ebaea8c7b0'
REPO = Path(__file__).resolve().parents[2]
READER = REPO / 'evaluation-results/hbq-matched-hanna-20261004/prepare.py'
SCALES = {'hbq': ([0, 100], 5), 'ttcw14': ([0, 1], 1 / 14),
          'holistic': ([1, 7], 1), 'compact': ([1, 5], 1),
          'oregon': ([6, 36], 1), 'poemetric': ([1, 5], 1)}
PROFILE_FIELDS = {k: True for k in ('endpoint', 'form', 'arm', 'artifact_id', 'cycle', 'score', 'dimensions')}
DIMENSION_FIELDS = {'value', 'scale', 'increment', 'absence_zero'}


def require(value, message):
    if not value:
        raise ValueError(message)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return (json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(',', ':')) + '\n').encode()


def reader():
    require(digest(READER.read_bytes()) == READER_SHA, 'Lexical boundary reader bytes differ')
    spec = importlib.util.spec_from_file_location('p1_affine_lexical_boundary', READER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def project(raw):
    require(digest(raw) == SOURCE_SHA, 'Completed analysis source bytes differ')
    # Dimensions are the pinned report's closed numeric metadata objects, not responses.
    data = reader().project_json(raw, {'analysis_policy': True, 'item_profiles': [PROFILE_FIELDS]})
    require(data['analysis_policy'] == SOURCE_POLICY, 'Source analysis policy differs')
    return data['item_profiles']


def distribution(values, scale, increment, absence_zero=False):
    require(len(scale) == 2 and scale[0] < scale[1], 'Invalid declared scale')
    low, high = map(lambda x: Fraction(str(x)), scale)
    scores, absence = [], 0
    for value in values:
        if value is None:
            continue
        require(isinstance(value, (int, float)) and not isinstance(value, bool), 'Nonnumeric scalar')
        v = Fraction(str(value))
        if absence_zero and v == 0:
            absence += 1
            continue
        require(low <= v <= high, 'Scalar outside declared quality scale')
        scores.append(v)
    frequency = Counter(scores)
    normalized = [100 * (v - low) / (high - low) for v in scores]
    return {'planned_items': len(values), 'reported_values': sum(v is not None for v in values),
            'missing_or_abstained': sum(v is None for v in values), 'absence_zero_count': absence,
            'absence_zero_supported': absence_zero, 'assessed_nonabsence': len(scores),
            'native_scale': scale, 'native_increment': increment,
            'exact_floor': sum(v == low for v in scores), 'exact_ceiling': sum(v == high for v in scores),
            'affine_floor_le_10': sum(v <= 10 for v in normalized),
            'affine_ceiling_ge_90': sum(v >= 90 for v in normalized),
            'distinct_scores': len(frequency), 'tied_score_values': sum(n > 1 for n in frequency.values()),
            'tied_observations': sum(n for n in frequency.values() if n > 1),
            'tied_pairs': sum(n * (n - 1) // 2 for n in frequency.values()),
            'native_minimum': float(min(scores)) if scores else None,
            'native_maximum': float(max(scores)) if scores else None,
            'affine_minimum': float(min(normalized)) if normalized else None,
            'affine_maximum': float(max(normalized)) if normalized else None}


def analyze(profiles):
    grouped, seen = defaultdict(list), set()
    for row in profiles:
        require(set(row) == set(PROFILE_FIELDS), 'Unexpected projected item fields')
        identity = tuple(row[k] for k in ('endpoint', 'form', 'arm', 'artifact_id', 'cycle'))
        require(identity not in seen, 'Duplicate logical item profile')
        seen.add(identity)
        require(row['arm'] in SCALES, 'No scalar policy for this arm; pairwise has no scalar')
        require(isinstance(row['dimensions'], dict), 'Invalid dimension metadata')
        for name, dim in row['dimensions'].items():
            require(set(dim) == DIMENSION_FIELDS, 'Unexpected dimension fields')
            expected_absence = row['arm'] == 'poemetric' and name in ('item_7', 'item_8')
            require(dim['absence_zero'] is expected_absence, 'Absence category differs')
            expected_scale = [1, 6] if row['arm'] == 'oregon' else [1, 5]
            require(dim['scale'] == expected_scale and dim['increment'] == 1, 'Dimension scale differs')
        grouped[(row['endpoint'], row['form'], row['arm'], row['cycle'])].append(row)
    groups = []
    for (endpoint, form, arm, cycle), rows in sorted(grouped.items()):
        scale, increment = SCALES[arm]
        dimensions = {}
        for name in sorted({name for row in rows for name in row['dimensions']}):
            exemplar = next(row['dimensions'][name] for row in rows if name in row['dimensions'])
            dimensions[name] = distribution([row['dimensions'].get(name, {}).get('value') for row in rows],
                                            exemplar['scale'], exemplar['increment'], exemplar['absence_zero'])
        groups.append({'endpoint': endpoint, 'form': form, 'arm': arm, 'cycle': cycle,
                       'primary': distribution([row['score'] for row in rows], scale, increment),
                       'dimensions': dimensions})
    return {'policy': POLICY, 'normalization': '100*(x-low)/(high-low); inclusive bands <=10 and >=90',
            'planned_item_profiles': len(profiles), 'groups': groups, 'native_pairwise_scalar_projection': None,
            'new_calls': 0, 'new_votes': 0, 'labels_opened': False, 'rescore': False,
            'candidate_claim': False, 'human_quality_claim': False,
            'limitations': ['Denominators are all retained planned item profiles, not request packets or pairwise observations.',
                           'Affine bands describe declared scales; they do not establish comparable quality across arms.',
                           'Missing profiles retain missing scalars; no leaf states or strict-import decisions are reconstructed.',
                           'POEMetric 7/8 zero is absence, excluded from quality bands and ties.']}


def prepare(source, output_root):
    source, output_root = source.resolve(), output_root.resolve()
    require(not output_root.exists(), 'Output must be fresh')
    require(not output_root.is_relative_to(REPO) and not REPO.is_relative_to(output_root), 'Output overlaps repository')
    require(not output_root.is_relative_to(source.parent) and not source.parent.is_relative_to(output_root), 'Output overlaps source')
    raw = source.read_bytes()
    report = analyze(project(raw))
    receipt = {'policy': POLICY, 'source_path': str(source), 'source_bytes': len(raw), 'source_sha256': digest(raw),
               'source_analysis_policy': SOURCE_POLICY, 'admission_replayed': False,
               'source_basis': 'retained_descriptive_item_profiles_not_new_admission', 'lexical_reader_sha256': READER_SHA,
               'implementation_sha256': digest(Path(__file__).read_bytes()), 'report_sha256': digest(canonical(report)),
               'planned_item_profiles': report['planned_item_profiles'], 'group_count': len(report['groups']),
               'rescore': False, 'labels_opened': False, 'new_votes': 0, 'new_calls': 0}
    return report, receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output-root', type=Path, required=True)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    report, receipt = prepare(args.source, args.output_root)
    if not args.dry_run:
        args.output_root.mkdir(parents=True, exist_ok=False)
        for name, value in [('report.json', report), ('receipt.json', receipt),
                            ('invocation.json', {'source': str(args.source.resolve()), 'output_root': str(args.output_root.resolve()),
                                                 'dry_run': False, 'implementation_sha256': receipt['implementation_sha256']})]:
            with (args.output_root / name).open('xb') as stream:
                stream.write(canonical(value))
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
