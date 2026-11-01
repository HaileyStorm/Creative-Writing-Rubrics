"""Project one exact closed Poetry report to public aggregates; no replay or scoring."""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
import hashlib
import json
import math
from pathlib import Path
import re
import statistics
import sys

REPORT = {'sha256': '4fea1950e29aad7442d37ae0ce9dbdbfc091069e53131261e7455f2e85cc46d7', 'bytes': 5426453}
READBACK = {'sha256': 'a6ca8769a0ae5fe46c6cac8e36f53291d7363c7502877562220a37d0515193eb', 'bytes': 24867}
RECEIPT = {'sha256': '526bc1c16e9bac69a0806b67eb235d42573b36d3c74b901971e52512c8a90492', 'bytes': 1218}
FORMS = {'poetry.free_verse', 'poetry.sonnet.contemporary', 'poetry.sonnet.petrarchan', 'poetry.sonnet.shakespearean', 'poetry.sonnet.spenserian'}
ARMS = ('holistic', 'compact', 'poemetric')


def require(ok, message):
    if not ok:
        raise ValueError(message)


def checked(path, pin):
    path = path.absolute()
    for node in (path, *path.parents):
        require(not node.is_symlink() and not getattr(node.stat(), 'st_file_attributes', 0) & 1024, 'Reparse input refused')
    before = path.stat(); raw = path.read_bytes(); after = path.stat()
    require((before.st_ino, before.st_size, before.st_mtime_ns) == (after.st_ino, after.st_size, after.st_mtime_ns)
            and len(raw) == pin['bytes'] and hashlib.sha256(raw).hexdigest() == pin['sha256'], 'Exact closed input required')
    return raw


def project_json(raw, specification):
    """Decode only explicitly selected fields; skipped targets are never decoded."""
    text, decoder = raw.decode("utf-8"), json.JSONDecoder()

    def white(i):
        while i < len(text) and text[i].isspace():
            i += 1
        return i

    def skip(i):
        i = white(i)
        if text[i] == '"':
            i += 1
            while i < len(text):
                if text[i] == "\\":
                    i += 2
                elif text[i] == '"':
                    return i + 1
                else:
                    i += 1
        elif text[i] in "[{":
            close = "]" if text[i] == "[" else "}"
            i += 1
            while True:
                i = white(i)
                if text[i] == close:
                    return i + 1
                if text[i] in ",:":
                    i += 1
                else:
                    i = skip(i)
        else:
            end = i
            while end < len(text) and text[end] not in ",]} \r\n\t":
                end += 1
            return end
        raise ValueError("Unterminated source JSON")

    def parse(i, spec):
        i = white(i)
        if spec is True:
            return decoder.raw_decode(text, i)
        if isinstance(spec, list):
            require(text[i] == "[", "Expected source metadata array")
            result, i = [], white(i + 1)
            while text[i] != "]":
                value, i = parse(i, spec[0])
                result.append(value)
                i = white(i)
                if text[i] == ",":
                    i = white(i + 1)
                else:
                    require(text[i] == "]", "Invalid source array separator")
            return result, i + 1
        require(text[i] == "{", "Expected source metadata object")
        result, seen, i = {}, set(), white(i + 1)
        while text[i] != "}":
            key, i = decoder.raw_decode(text, i)
            require(isinstance(key, str) and key not in seen, "Duplicate source metadata key")
            seen.add(key)
            i = white(i)
            require(text[i] == ":", "Invalid source metadata separator")
            i = white(i + 1)
            if key in spec:
                result[key], i = parse(i, spec[key])
            else:
                i = skip(i)
            i = white(i)
            if text[i] == ",":
                i = white(i + 1)
            else:
                require(text[i] == "}", "Invalid source object separator")
        require(set(result) == set(spec), "Required source metadata absent")
        return result, i + 1

    value, end = parse(0, specification)
    require(white(end) == len(text), "Trailing source JSON")
    return value

SELECTION = {'state': True, 'form_summary': True, 'within_form_scalar_concordance': True, 'recorded_states': True, 'denominators': True, 'native_replay_calls': True, 'requalification_calls': True, 'new_model_requests': True, 'cached_packets_reused': True, 'cached_packets_requalified_or_rescored': True, 'full_bank_profiles': [{'repeat': True, 'bundle_id': True, 'status': True, 'complete_original_bank': True, 'weighted_coverage': True, 'unchanged_score_reused': True}], 'scalar_repeat_differences': [{'arm': True, 'artifact_id': True, 'left_repeat': True, 'right_repeat': True, 'planned_pairs': True, 'observed_pairs': True, 'missing_pairs': True, 'mean_absolute_native_difference': True, 'mean_signed_right_minus_left': True, 'exact_agreement': True}], 'native_comparator_profiles': [{'artifact_id': True, 'bundle_id': True, 'arm': True}], 'per_artifact_hbq_repeatability': [{'form': True, 'left_repeat': True, 'right_repeat': True, 'native_states': True, 'eligible_scalar_delta': True, 'contract_and_configuration': True, 'left_status': True, 'right_status': True}], 'original_synthetic_family_profiles': [{'family_id': True, 'repeat': True}], 'source_packet1396': {'sha256': True, 'bytes': True}, 'original_failure': {'sha256': True, 'bytes': True}, 'original_terminal': {'sha256': True, 'bytes': True}, 'saved_qualification': {'sha256': True, 'bytes': True}, 'saved_amended_strict_replay': {'sha256': True, 'bytes': True}, 'actual_closed_lineage': {'sha256': True, 'bytes': True}, 'new_closed_input_guard': {'sha256': True, 'bytes': True}, 'old_failed_analysis_represented_as_success': True}

def summarize(values):
    require(all(type(v) in (int, float) and math.isfinite(v) for v in values), 'Finite saved descriptive values')
    return {'observed': len(values), 'minimum': min(values) if values else None,
            'maximum': max(values) if values else None, 'mean': statistics.mean(values) if values else None}


def project(report, readback, receipt):
    r = project_json(report, SELECTION)
    guard = project_json(readback, {k: True for k in ('state', 'old_final_guard_executed',
        'new_closed_input_and_source_guard_executed', 'canonical_global_state_reread')})
    rec = project_json(receipt, {'state': True, 'report': {'sha256': True, 'bytes': True},
        'closed_input_readback': {'sha256': True, 'bytes': True}, 'native_replay_calls': True,
        'requalification_calls': True, 'new_model_requests': True, 'targets_read': True})
    require(r['state'] == rec['state'] == 'ACTUAL_CLOSED_INPUT_POETRY_REPORT_RECOVERY1396_WITH_EXPLICIT_GAPS'
            and rec['report'] == REPORT and rec['closed_input_readback'] == READBACK, 'Closed receipt composition differs')
    require(guard == {'state': 'PASS', 'old_final_guard_executed': False,
            'new_closed_input_and_source_guard_executed': True, 'canonical_global_state_reread': False}, 'Keep original failed guard distinction')
    require(all(r[k] == rec[k] == 0 for k in ('native_replay_calls', 'requalification_calls', 'new_model_requests'))
            and rec['targets_read'] is False and r['old_failed_analysis_represented_as_success'] is False, 'Recovery is not new native qualification')
    require(r['cached_packets_reused'] == 57 and r['cached_packets_requalified_or_rescored'] == 0, 'Retain unchanged cache reuse')
    require(r['saved_amended_strict_replay'] == {'sha256': '50ff51fc01c46a878b74858b9f3f797c273d8be51889fb0a93ad3b34c0f85a2c', 'bytes': 496789}
            and r['source_packet1396'] == {'sha256': '594b04af45797a4b536276a86c108a0190f07ce663ce505c7e75990fde023964', 'bytes': 16053},
            'Inherited exact closed85-request strict-replay and recovery-source commitments')
    require(sum(r['recorded_states'].values()) == r['denominators']['original_sol_requests'] == 642
            and r['denominators']['held_grok_requests'] == 642, 'Original endpoint denominators')
    identities = {}
    for row in r['native_comparator_profiles']:
        sid, form = row['artifact_id'], row['bundle_id']
        require(form in FORMS and row['arm'] in ARMS and identities.get(sid, form) == form, 'Fixed form map')
        identities[sid] = form
    families = {row['family_id'] for row in r['original_synthetic_family_profiles']}
    require(len(identities) == 24 and len(families) == 8, 'Frozen AI poem/family coverage')
    summary = r['form_summary']
    require(all(row['form'] in FORMS for row in summary), 'Public form labels only')
    statuses = Counter()
    for row in summary:
        statuses.update(row['statuses'])
    planned = sum(row['planned_full_banks'] for row in summary)
    complete = sum(row['complete_full_banks'] for row in summary)
    require(planned == 36 and complete == 35 and dict(statuses) == {'SCORED': 29, 'UNAVAILABLE_COMPLETE_BANK': 1, 'INELIGIBLE': 6},
            'Complete bank is distinct from scalar eligibility')
    initial_banks = sum(row['planned_full_banks'] for row in summary if row['repeat'] == 0)
    require(initial_banks == 12, 'Prespecified full-bank sentinel cohort')
    coverage_groups = defaultdict(list)
    for row in r['full_bank_profiles']:
        require(row['bundle_id'] in FORMS, 'Public coverage form')
        coverage_groups[(row['bundle_id'], row['repeat'])].append(row)
    coverage = []
    for (form, repeat), rows in sorted(coverage_groups.items()):
        values = [row['weighted_coverage'] for row in rows if row['weighted_coverage'] is not None]
        coverage.append({'form': form, 'repeat': repeat, 'planned_banks': len(rows),
            'complete_banks': sum(row['complete_original_bank'] for row in rows),
            'weighted_coverage_across_available_banks': summarize(values),
            'eligibility_separate_from_coverage': True})
    comparator_groups = defaultdict(list)
    for row in r['scalar_repeat_differences']:
        comparator_groups[(identities[row['artifact_id']], row['arm'], row['left_repeat'], row['right_repeat'])].append(row)
    scalar_repeat = []
    for (form, arm, left, right), rows in sorted(comparator_groups.items()):
        require(all(row['planned_pairs'] == 1 and row['observed_pairs'] in (0, 1) for row in rows), 'One saved artifact pair per repeat contrast')
        observed = [row for row in rows if row['observed_pairs'] == 1]
        scalar_repeat.append({'form': form, 'arm': arm, 'left_repeat': left, 'right_repeat': right,
            'planned_artifact_pairs': len(rows), 'observed_artifact_pairs': len(observed),
            'missing_artifact_pairs': len(rows)-len(observed),
            'absolute_change': summarize([row['mean_absolute_native_difference'] for row in observed]),
            'signed_right_minus_left_change': summarize([row['mean_signed_right_minus_left'] for row in observed]),
            'unchanged_pairs': sum(row['exact_agreement'] == 1 for row in observed)})
    hbq_groups = defaultdict(list)
    for row in r['per_artifact_hbq_repeatability']:
        require(row['form'] in FORMS, 'Public repeat form')
        hbq_groups[(row['form'], row['left_repeat'], row['right_repeat'])].append(row)
    hbq_repeat = []
    for (form, left, right), rows in sorted(hbq_groups.items()):
        complete_rows = [row for row in rows if row['native_states']['paired_observed_units'] > 0]
        deltas = [row['eligible_scalar_delta'] for row in rows if row['eligible_scalar_delta'] is not None]
        same = sum(type(row['contract_and_configuration']) is dict
            and row['contract_and_configuration']['actual_configurations_equal']
            and not row['contract_and_configuration']['original_contract_differences'] for row in rows)
        interpretations = Counter(row['contract_and_configuration']['interpretation']
            if type(row['contract_and_configuration']) is dict else row['contract_and_configuration'] for row in rows)
        equal_configurations = Counter(str(row['contract_and_configuration']['actual_configurations_equal'])
            if type(row['contract_and_configuration']) is dict else 'unavailable' for row in rows)
        hbq_repeat.append({'form': form, 'left_repeat': left, 'right_repeat': right,
            'planned_artifact_pairs': len(rows), 'complete_bank_pairs': len(complete_rows),
            'missing_complete_bank_pairs': len(rows)-len(complete_rows), 'eligible_scalar_pairs': len(deltas),
            'eligible_scalar_signed_right_minus_left_change': summarize(deltas),
            'eligible_scalar_absolute_change': summarize([abs(v) for v in deltas]),
            'per_bank_raw_agreement': summarize([row['native_states']['raw_agreement'] for row in complete_rows]),
            'recorded_contract_configuration_interpretations': dict(interpretations),
            'recorded_configuration_equality': dict(equal_configurations),
            'same_contract_and_configuration_pairs': same,
            'other_or_unavailable_contract_configuration_pairs': len(rows)-same})
    return {'schema_version': 1, 'policy': 'closed_poetry_native_descriptive_aggregate1398_v1',
        'source_commitments': {'closed_report': REPORT, 'closed_input_readback': READBACK, 'recovery_receipt': RECEIPT,
            **{k: r[k] for k in ('source_packet1396', 'original_failure', 'original_terminal', 'saved_qualification',
                                  'saved_amended_strict_replay', 'actual_closed_lineage')}},
        'scope': {'AI_created_poems': len(identities), 'designed_families': len(families),
            'Sol_logical_request_slots': r['denominators']['original_sol_requests'],
            'Grok_held_logical_request_slots': r['denominators']['held_grok_requests'],
            'initial_HBQ_full_bank_sentinel_poems': initial_banks,
            'HBQ_targeted_subset_only_poems': len(identities)-initial_banks,
            'initial_comparator_poems': len(identities), 'comparator_slots_per_arm': r['denominators']['comparator_requests_per_arm']},
        'frozen_cohort_rule': 'Four prespecified sentinel families, three variants each: two free-verse families, one contemporary-sonnet family and one Petrarchan-sonnet family. These12 poems receive full HBQ banks in three cycles; the other12 receive targeted diagnostic-pool subsets, never full-bank scalars. Comparators cover all24 initially and the12 sentinels in cycles1/2. No scope overlay or gate was changed.',
        'qualification_categories': r['recorded_states'],
        'historical_native_boundary': {'native_headers': r['denominators']['current_lineage_requests'],
            'joined_job_tuples': 5, 'qualification': 'Inherited saved five-job450-header lineage; no fresh native replay, current-state guard or provider-quiescence assertion.'},
        'native_attestation_scope': {'current_tail_requests': 85, 'all_32_features_disabled_for_current_tail': True,
            'qualification': 'Inherited completed amended strict-replay commitment in the closed1396 report; not replayed here. Mixed historical qualification categories remain separate; no all642 current-tool attestation.'},
        'full_bank_eligibility': {'planned': planned, 'complete': complete, 'statuses': dict(statuses)},
        'form_summary': summary, 'within_form_same_data_scalar_concordance': r['within_form_scalar_concordance'],
        'coverage_by_form_and_repeat': coverage, 'scalar_repeat_summaries': scalar_repeat, 'HBQ_repeat_summaries': hbq_repeat,
        'aggregation_method': 'Copy existing form/scalar concordance summaries. Simple counts and unweighted min/max/arithmetic means over existing per-artifact saved repeat differences/agreements and bank coverage, separately by form/repeat pair; no new qualification, score or rho. Repeat contrasts sharing an artifact are dependent; no leaf pooling or independent-sample interpretation.',
        'report_recovery': {**guard, 'native_replay_calls': 0, 'requalification_calls': 0, 'new_model_requests': 0,
            'cached_packets_reused': r['cached_packets_reused'], 'cached_packets_requalified_or_rescored': r['cached_packets_requalified_or_rescored'],
            'family_lookup_fix': 'Exact075 opaque family key from design-family SHA256 prefix; original075/074 identities unchanged; original failed1378 analysis remains failed.'},
        'limits': ['24 AI poems/eight designed families; no human labels, accepted quality oracle, human alignment, method winner or candidate promotion.',
            'HBQ prespecified12 sentinel poems/36 full-bank profiles; other12 poems have targeted HBQ subsets. Comparators cover24 initial poems/48 slots per arm. Same-form marginal cohorts can differ. Zero-planned full-bank forms are not compilation failures: targeted diagnostics and comparators remain separate from unmeasured full-bank scalars.',
            'Concordance uses only same-form/same-repeat artifacts with both eligible HBQ and comparator scores; availability-selected cohorts differ by comparator/repeat. Minimum three pairs; null remains undefined, including possible ties.',
            'Complete full banks and weighted coverage do not imply eligible scalar scores. INELIGIBLE remains distinct from unavailable/missing. Assessment bounds concern missing rubric assessments, not sampling confidence intervals.',
            'Historical native qualifications, cached qualifications and current85 native acceptances remain different scopes. No fresh provider quiescence, historical tool equivalence or all642 current-runtime/tool attestation is claimed.',
            'Repeat contrasts share artifacts/families and may differ in contract/configuration; descriptive changes are not independent trials or controlled same-runtime population reliability.',
            'The original final analysis guard did not execute. The separate recovery closed-input/source guard passed; original failure and saved qualifications are retained without native replay/requalification.',
            'Private retained inputs are needed for regeneration. This aggregate projection does not reconstruct native envelopes, re-admit returns, repair source data or establish human validity. Full research Goal remains incomplete.'],
        'sampling_confidence_intervals': None, 'bootstrap_draws': 0, 'provider_calls': 0,
        'native_or_scientific_replays': 0, 'new_judge_votes': 0, 'human_alignment_claimed': False,
        'candidate_or_baseline_promoted': False, 'full_research_goal_complete': False}


def encode(value):
    raw = (json.dumps(value, sort_keys=True, ensure_ascii=False, indent=2, allow_nan=False)+'\n').encode()
    forbidden = {'path', 'artifact_id', 'family_id', 'question_id', 'judge_id', 'owner', 'thread_id', 'native_identity', 'request_ordinals'}
    def scan(node):
        if type(node) is dict:
            require(not (set(node) & forbidden), 'Private identity/path key in public output')
            for value in node.values(): scan(value)
        elif type(node) is list:
            for value in node: scan(value)
        elif type(node) is str:
            require(not re.search(r'(?i)([a-z]:[\\/]|@gmail\.com|artifact-[a-z0-9]|family-[a-z0-9]|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})', node), 'Private operational marker')
    scan(value)
    return raw


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--readback', type=Path, required=True)
    parser.add_argument('--receipt', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    require(sys.version_info[:2] == (3, 12) and __debug__, 'Python3.12 with assertions required')
    result = project(checked(args.report, REPORT), checked(args.readback, READBACK), checked(args.receipt, RECEIPT))
    raw = encode(result)
    require(not args.output.exists(), 'Create-only output; preserve existing outputs and partials')
    with args.output.open('xb') as handle:
        handle.write(raw)
    print(json.dumps({'state': 'CLOSED_POETRY_AGGREGATES_PROJECTED', 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest(), 'new_scoring_or_replay_or_provider_calls': 0}))


if __name__ == '__main__':
    main()
