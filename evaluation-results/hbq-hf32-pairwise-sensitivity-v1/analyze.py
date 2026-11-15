"""Reproduce an aggregate sensitivity report from retained private HF32 inputs."""
import argparse
from collections import Counter
from fractions import Fraction
import hashlib
from itertools import combinations
import json
import math
from pathlib import Path

SOURCE_SHA = 'e8bfc8cb83c91f4f26c4f901bc0f9fef9e993072b509c175baccafcddaad9fe7'
REQUEST_SHA = 'ab4adf5943e0eb12dd5e750e05ea63c5c99cafd3f2ec37c351d4bd05a62e9268'
CASES_SHA = '469806acefd2f4cc92908f6b31e3c5f0afae3b4e8c15b9061892f89293994a0c'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read(path, expected):
    raw = path.read_bytes()
    require(hashlib.sha256(raw).hexdigest() == expected, 'input digest differs')
    return json.loads(raw)


def load_rows(source_path, requests_path, cases_path):
    source = read(source_path, SOURCE_SHA)
    manifest = read(requests_path, REQUEST_SHA)
    cases = read(cases_path, CASES_SHA)
    refs = [r['manifest721'] for r in source['authoritative_replays'].values()]
    require(refs and all(r == refs[0] for r in refs) and refs[0]['sha256'] == REQUEST_SHA,
            'request binding differs')
    require(len(manifest['requests']) == 736, 'request count differs')
    ids = {r['artifact_id'] for r in manifest['requests']}
    require(len(ids) == 32 and ids == set(source['paired_scores']) == set(source['projected_targets']),
            'artifact membership differs')
    hashed = {hashlib.sha256(aid.encode()).hexdigest(): aid for aid in ids}
    require(len(hashed) == 32, 'identifier collision')
    rows, seen = [], set()
    for case in cases['results']:
        key = case['artifact_id_sha256']
        require(key in hashed and key not in seen, 'case membership differs')
        seen.add(key)
        aid = hashed[key]
        scores, target = source['paired_scores'][aid], source['projected_targets'][aid]
        hbq, ttcw = scores['historical']['score'], scores['ttcw14']['score']
        require(hbq == case['saved_bounds']['observed'] == scores['candidate']['score'], 'score binding differs')
        row = {'hbq': hbq, 'ttcw': ttcw, 'expert': target['expert_mean2'], 'reader': target['nonexpert_median']}
        require(all(v is None or (type(v) in (int, float) and math.isfinite(v)) for v in row.values()), 'invalid value')
        rows.append(row)
    require(len(rows) == 27, 'complete-bank cohort differs')
    common = [r for r in rows if all(r[k] is not None for k in ('hbq', 'ttcw', 'expert', 'reader'))]
    require(len(common) == 17, 'matched cohort differs')
    return common


def difference(rows, reference, tie_credit):
    delta = Fraction(0)
    count = 0
    for a, b in combinations(rows, 2):
        human = (a[reference] > b[reference]) - (a[reference] < b[reference])
        if not human:
            continue
        count += 1
        points = []
        for method in ('hbq', 'ttcw'):
            direction = (a[method] > b[method]) - (a[method] < b[method])
            points.append(tie_credit if not direction else Fraction(int(direction == human)))
        delta += points[0] - points[1]
    require(count > 0, 'no non-tied reference pairs')
    return 100 * delta / count


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--requests', type=Path, required=True)
    parser.add_argument('--cases', type=Path, required=True)
    args = parser.parse_args()
    rows = load_rows(args.source, args.requests, args.cases)
    analysis = {}
    for reference in ('expert', 'reader'):
        tie_differences = {str(c): round(float(difference(rows, reference, c)), 2)
                           for c in (Fraction(0), Fraction(1, 2), Fraction(1))}
        deleted = [difference(rows[:i] + rows[i+1:], reference, Fraction(1, 2)) for i in range(len(rows))]
        signs = Counter('positive' if x > 0 else 'negative' if x < 0 else 'zero' for x in deleted)
        analysis[reference] = {'full_difference_pp_by_tie_credit': tie_differences,
            'half_credit_leave_one_out_min_pp': round(float(min(deleted)), 2),
            'half_credit_leave_one_out_max_pp': round(float(max(deleted)), 2),
            'half_credit_leave_one_out_signs': {k: signs[k] for k in ('negative', 'zero', 'positive')}}
    print(json.dumps({'state': 'HF32_POST_RESULT_WORK_DELETION_SENSITIVITY',
        'source_sha256': SOURCE_SHA, 'request_manifest_sha256': REQUEST_SHA, 'case_manifest_sha256': CASES_SHA,
        'works': len(rows), 'analysis': analysis, 'provider_calls': 0, 'new_human_labels': 0,
        'limits': ['Availability-selected post-result development subset, not prospective confirmation.',
                   'Pairs share works; deletion ranges are not confidence intervals or significance tests.',
                   'Tie credits are sensitivity conventions, not additional correct predictions.',
                   'No population inference, method superiority or promotion follows.']}, sort_keys=True, indent=2))


if __name__ == '__main__':
    main()
