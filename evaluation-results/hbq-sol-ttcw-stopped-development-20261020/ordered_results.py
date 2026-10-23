"""Read saved TTCW results by explicit identity, without prefix inference.

Returns the immutable parent record objects plus locally verified continuation
records. Does not dispatch, reserve, score, read human targets or authorize reuse.
The caller owns serialization and reconciliation across other attempt roots.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import importlib.util
import json
from pathlib import Path

from completion_order import PINS, encoded, require, sha
from ordered_progress import OrderedProgress, PLAN_SHA

PARENT_SHA = '8ea0af717bd5351b3a0f9b727c24420ea7f3da0ddbdf78967e958d1e8702b87f'
READER_SHA = 'd1bcadff4472c8171b3ab08b07d609b48623189814a49375bd32966a1df4e6e7'
SCALAR = ('hbq', 'ttcw14', 'holistic', 'compact', 'oregon')


def plain(path):
    require(path == path.resolve(), 'Canonical path required')
    for item in (path, *path.parents):
        if item.exists():
            require(not item.is_symlink() and not getattr(item.lstat(), 'st_file_attributes', 0) & 1024, 'Reparse source refused')


def read(path, expected=None):
    plain(path)
    raw = path.read_bytes()
    require(expected is None or sha(raw) == expected, 'Saved source changed: ' + path.name)
    return raw


def value(path, expected=None):
    return json.loads(read(path, expected))


def child(root, relative):
    result = root / relative
    plain(result)
    require(result.is_relative_to(root) and result != root, 'Saved artifact escapes its root')
    return result


def native_reader(repo):
    path = repo / 'src/hbqrs/codex_receipts.py'
    read(path, READER_SHA)
    spec = importlib.util.spec_from_file_location('ordered_results_native_reader', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def join(*, parent_cache, manifest, census, plan, run_dir=None, repo=None):
    read(plan, PLAN_SHA)
    manifest_value = value(manifest, PINS['manifest'])
    rows = {r['endpoint_ordinal']: r for r in manifest_value['requests']}
    census_value = value(census, PINS['census'])
    parent_ids = {r['ordinal'] for r in census_value if r['state'] == 'accepted_saved_prediction'}
    occupied_parent = {r['ordinal'] for r in census_value if r['state'] == 'occupied_unadmitted_no_resend'}
    parent = value(parent_cache, PARENT_SHA)
    for name, commitment in parent['files'].items():
        raw = read(child(parent_cache.parent, name), commitment['sha256'])
        require(len(raw) == commitment['bytes'], 'Parent file length changed')
    records = value(parent_cache.parent / 'qualified-predictions.json')['records']
    require(len(records) == len(parent_ids) == 328 and {r['endpoint_ordinal'] for r in records} == parent_ids, 'Parent accepted identities differ')
    for record in records:
        row = rows[record['endpoint_ordinal']]
        require(record['endpoint'] == 'sol' and record['no_resend'] is True, 'Parent endpoint/no-resend differs')
        require(all(record[k] == row[k] for k in ('logical_sample_id', 'request_sha256', 'scientific_condition_sha256', 'arm')), 'Parent request identity differs')
    parent_objects_sha = sha(encoded(records))
    identities = [tuple(identity) for record in records for identity in record['enumerated_native_identities']]
    require(len(identities) == len(set(identities)) == 656, 'Parent native identities differ')
    added = []
    status = None
    if run_dir is not None:
        plain(run_dir)
        progress = OrderedProgress(plan, manifest, census, run_dir, purpose='collector_progress')
        status = progress.inspect()
        require(repo is not None, 'Native receipt source repository required')
        reader = native_reader(repo)
        for entry in progress.entries:
            if entry['source_ordinal'] not in status['accepted_ordinals']:
                continue
            sample = progress.sample(entry)
            row = progress.rows[entry['source_ordinal']]
            require(value(sample / 'condition.json') == row, 'Continuation frozen request differs')
            terminal = value(sample / 'terminal.json')
            identity = value(sample / 'native-identity.json')
            require(identity['logical_sample_id'] == row['logical_sample_id'] and identity['session_id'] is None, 'Native identity differs')
            require(all(identity[k] == terminal[k] for k in ('progress_binding', 'attempt_marker_sha256')), 'Producer identity binding differs')
            native = value(sample / 'native-result.json')
            response = value(sample / 'response.json')
            admission = value(sample / 'acceptance.json')
            require(admission['accepted'] is terminal['accepted'] is True, 'Admission differs')
            frozen = Path(manifest_value['payload_reuse']['root']).resolve()
            prompt = read(child(frozen, row['prompt_path']), row['prompt_sha256']).decode('utf-8')
            schema = read(child(frozen, row['schema_path']), row['schema_sha256'])
            require(read(sample / 'schema.json') == schema, 'Attempt schema differs')
            for artifact in native['provider_artifacts'].values():
                child(sample, artifact['path'])
            reader.verify(sample, native, prompt=prompt, model='gpt-6.1-sol', reasoning='high')
            artifacts = native['provider_artifacts']
            require(value(child(sample, artifacts['codex_message']['path'])) == response, 'Saved native final differs from admitted response')
            receipt = value(child(sample, artifacts['codex_receipt']['path']))
            new_ids = [('sol_thread', sha(receipt['thread_id'].encode())), ('sol_turn', sha(receipt['turn_id'].encode()))]
            require(not set(new_ids) & set(identities), 'Repeated native thread/turn identity')
            identities.extend(new_ids)
            added.append({'endpoint': 'sol', 'endpoint_ordinal': row['endpoint_ordinal'], 'logical_sample_id': row['logical_sample_id'], 'request_sha256': row['request_sha256'], 'scientific_condition_sha256': row['scientific_condition_sha256'], 'arm': row['arm'], 'state': 'accepted_ordered_continuation_saved_native_and_semantic_receipts', 'response': response, 'semantic_acceptance': admission, 'condition_descriptor': row, 'enumerated_native_identities': new_ids, 'execution_condition': progress.plan['execution_condition'], 'execution_condition_sha256': progress.plan['execution_condition_sha256'], 'progress_binding': terminal['progress_binding'], 'attempt_marker_sha256': terminal['attempt_marker_sha256'], 'native_reported': native['reported'], 'native_receipt_reader_sha256': READER_SHA, 'native_receipt_replayed_locally': True, 'semantic_validation_reexecuted': False, 'no_resend': True, 'source_artifacts': {name: {'path': str(sample / name), 'sha256': sha(read(sample / name))} for name in ('condition.json', 'native-identity.json', 'attempt-started.json', 'terminal.json', 'native-result.json', 'response.json', 'acceptance.json')}})
    combined = [*records, *added]
    accepted = {r['endpoint_ordinal'] for r in combined}
    require(len(accepted) == len(combined) and not accepted & occupied_parent, 'Duplicate or occupied accepted identity')
    require(len({r['logical_sample_id'] for r in combined}) == len(combined), 'Duplicate logical sample')
    require(sha(encoded(combined[:len(records)])) == parent_objects_sha, 'Parent record objects changed')
    groups = {arm: defaultdict(set) for arm in SCALAR}
    for n, row in rows.items():
        if row['arm'] in groups:
            groups[row['arm']][row['story_id']].add(n)
    complete = {arm: {story for story, expected in works.items() if expected <= accepted} for arm, works in groups.items()}
    attempted = set(status['attempted_ordinals']) if status else set()
    unattempted = set(range(1, 1045)) - parent_ids - occupied_parent - attempted
    summary = {'schema_version': 1, 'state': 'EXPLICIT_ID_SAVED_RESULT_VIEW', 'plan_sha256': PLAN_SHA, 'parent_cache_sha256': PARENT_SHA, 'parent_record_objects_sha256': parent_objects_sha, 'parent_record_objects_unchanged': True, 'parent_accepted': len(records), 'new_accepted': len(added), 'total_accepted': len(combined), 'accepted_ordinals': sorted(accepted), 'occupied_parent_no_resend_ordinals': sorted(occupied_parent), 'new_attempted_ordinals': sorted(attempted), 'new_semantic_rejected_ordinals': status['semantic_rejected_ordinals'] if status else [], 'new_unresolved_ordinals': status['unresolved_ordinals'] if status else [], 'new_stopped_no_resend_ordinals': status['stopped_no_resend_ordinals'] if status else [], 'remaining_unattempted_ordinals': sorted(unattempted), 'continuation_supplied': status is not None, 'continuation_state': status['state'] if status else 'NOT_SUPPLIED', 'next_entry': status['next_entry'] if status else None, 'request_complete_works': {arm: len(ids) for arm, ids in complete.items()}, 'all_five_request_complete_works': len(set.intersection(*complete.values())), 'provider_contact_authority': False, 'provider_calls': 0, 'scorer_calls': 0, 'human_targets_read': False, 'new_native_receipts_replayed': len(added), 'qualification_limits': 'Parent qualification fields unchanged. Continuation proves saved native model/effort and zero observed tool activity, not AUX/wire/account/backend/sampler equivalence. Membership is not numeric scoring or human validation.'}
    return {'records': combined, 'summary': summary}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('parent-cache', 'manifest', 'census', 'plan'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--run-dir', type=Path)
    parser.add_argument('--repo', type=Path)
    parser.add_argument('--output', type=Path, help='Create a private combined records/summary JSON; contains retained research responses.')
    args = parser.parse_args()
    paths = {name: getattr(args, name).resolve() if getattr(args, name) is not None else None for name in ('parent_cache', 'manifest', 'census', 'plan', 'run_dir', 'repo')}
    try:
        result = join(**paths)
        if args.output:
            plain(args.output.resolve())
            with args.output.open('xb') as stream:
                stream.write(encoded(result))
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(2, f'ordered results: {error}\n')
    print(json.dumps(result['summary'], indent=2, allow_nan=False))


if __name__ == '__main__':
    main()
