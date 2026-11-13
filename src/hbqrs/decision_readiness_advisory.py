"""Experimental opt-in advisory over saved reports; does not change scoring."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Mapping

from . import decision_readiness

POLICY = 'historical_ladder_readiness_advisory_v1'
ISSUE = re.compile(r'^Subjective ladder (\S+) had (\S+)=YES after a lower threshold failed or was unassessed; normalized to NO$')
THRESHOLD = re.compile(r'\.threshold_(\d+)(?:_|$)')


def advisory(report: Mapping[str, Any]) -> dict[str, Any]:
    """Find a narrow risk signature; no match never establishes safety."""
    note = ('A match is a possible historical upper-bound limitation, not proof of a violation. '
            'No match cannot establish a valid envelope; original raw verdicts and compiled ladder metadata are not retained here.')
    def indeterminate(reason: str) -> dict[str, Any]:
        return {'status': 'INDETERMINATE', 'reason': reason, 'matches': [], 'additional_ambiguity_observed': True, 'limitation': note}

    standard = report.get('standard')
    if not isinstance(standard, Mapping) or standard.get('id') != 'HBQ-RS' or standard.get('version') != '1.2.1':
        return indeterminate('unsupported_standard')
    version = report.get('report_version', 1)
    if type(version) is not int or version not in (1, 2) or report.get('scoring_policy') is not None:
        return indeterminate('unsupported_report_or_scoring_policy')
    issues, domains = report.get('issues'), report.get('domains')
    if not isinstance(issues, list) or not all(isinstance(i, str) for i in issues) or not isinstance(domains, list):
        return indeterminate('missing_or_malformed_issue_or_domain_fields')
    questions: dict[str, list[dict[str, str]]] = {}
    identifiers: set[str] = set()
    for domain in domains:
        if not isinstance(domain, Mapping) or not isinstance(domain.get('questions'), list):
            return indeterminate('malformed_domain_questions')
        for row in domain['questions']:
            if not isinstance(row, Mapping):
                return indeterminate('malformed_question')
            module, qid, state = row.get('module_id'), row.get('question_id'), row.get('verdict')
            if (not all(isinstance(x, str) and x for x in (module, qid, state))
                    or state not in {'YES', 'NO', 'CANNOT_ASSESS', 'NOT_APPLICABLE'} or qid in identifiers):
                return indeterminate('missing_or_duplicate_question_identity')
            identifiers.add(qid)
            questions.setdefault(module, []).append({'question_id': qid, 'verdict': state})

    hits: list[dict[str, str]] = []
    uncertain = False
    for issue in issues:
        if not issue.startswith('Subjective ladder'):
            continue
        match = ISSUE.fullmatch(issue)
        if match is None:
            uncertain = True
            continue
        module, suppressed = match.groups()
        suppressed_order = THRESHOLD.search(suppressed)
        rows = questions.get(module, [])
        named = [row for row in rows if row['question_id'] == suppressed]
        if suppressed_order is None or suppressed.count('threshold_') != 1 or len(named) != 1 or named[0]['verdict'] != 'NO':
            uncertain = True
            continue
        orders: dict[int, int] = {}
        for row in rows:
            order = THRESHOLD.search(row['question_id'])
            if row['question_id'].count('threshold_') > 1:
                uncertain = True
            elif order:
                orders[int(order.group(1))] = orders.get(int(order.group(1)), 0) + 1
            elif row['verdict'] == 'CANNOT_ASSESS':
                uncertain = True
        if any(count != 1 for count in orders.values()):
            uncertain = True
            continue
        for row in rows:
            order = THRESHOLD.search(row['question_id'])
            if (row['verdict'] == 'CANNOT_ASSESS' and order and row['question_id'].count('threshold_') == 1
                    and int(order.group(1)) < int(suppressed_order.group(1))):
                hits.append({'module_id': module, 'unassessed_question_id': row['question_id'],
                             'suppressed_question_id': suppressed})
    if hits:
        return {'status': 'POTENTIAL_HISTORICAL_LADDER_LIMITATION', 'matches': hits,
                'additional_ambiguity_observed': uncertain, 'limitation': note}
    if uncertain:
        return indeterminate('ambiguous_ladder_metadata')
    return {'status': 'NO_MATCH_DETECTED', 'matches': [], 'additional_ambiguity_observed': False, 'limitation': note}


def project(raw: bytes, *, threshold: float | None = None, comparison_raw: bytes | None = None,
            comparison_context_sha256: str | None = None) -> dict[str, Any]:
    report = json.loads(raw)
    if not isinstance(report, Mapping):
        raise ValueError('score report must be an object')
    result = {'policy': POLICY, 'report_sha256': hashlib.sha256(raw).hexdigest(),
              'source_files_observed_after_import_sha256': {'projection': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                                                           'legacy_readiness': hashlib.sha256(Path(decision_readiness.__file__).read_bytes()).hexdigest()},
              'legacy_readiness': decision_readiness.decision_readiness(report, threshold=threshold),
              'ladder_advisory': advisory(report),
              'interpretation': 'The current legacy readiness and any legacy comparison are recomputed; input score-report bytes are unchanged. Observed file hashes do not independently prove the executed bytes or historical provenance. This advisory cannot establish a universal interval envelope.'}
    if comparison_raw is None:
        if comparison_context_sha256 is not None:
            raise ValueError('comparison context requires a comparison report')
        return result
    other = json.loads(comparison_raw)
    if not isinstance(other, Mapping):
        raise ValueError('comparison score report must be an object')
    other_advisory = advisory(other)
    statuses = {result['ladder_advisory']['status'], other_advisory['status']}
    combined = ('POTENTIAL_HISTORICAL_LADDER_LIMITATION' if 'POTENTIAL_HISTORICAL_LADDER_LIMITATION' in statuses
                else 'INDETERMINATE' if 'INDETERMINATE' in statuses else 'NO_MATCH_DETECTED')
    result['comparison'] = {
        'report_sha256': hashlib.sha256(comparison_raw).hexdigest(),
        'legacy_comparison': decision_readiness.interval_comparison(
            report, other, comparison_context_sha256=comparison_context_sha256),
        'other_ladder_advisory': other_advisory,
        'combined_ladder_advisory': combined,
        'additional_ambiguity_observed': any(a['status'] == 'INDETERMINATE' or a['additional_ambiguity_observed']
                                             for a in (result['ladder_advisory'], other_advisory)),
        'limitation': 'Neither a no-match result nor a separated legacy interval proves a universal envelope.',
    }
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('report', type=Path)
    parser.add_argument('--threshold', type=float)
    parser.add_argument('--compare', type=Path)
    parser.add_argument('--comparison-context-sha256')
    args = parser.parse_args()
    if args.comparison_context_sha256 and not args.compare:
        parser.error('--comparison-context-sha256 requires --compare')
    print(json.dumps(project(args.report.read_bytes(), threshold=args.threshold,
                             comparison_raw=args.compare.read_bytes() if args.compare else None,
                             comparison_context_sha256=args.comparison_context_sha256), indent=2, allow_nan=False))


if __name__ == '__main__':
    main()
