"""Reserve an exact Sol job chain, including native failures, without new contact.

Historical continue_sol.py remains the verifier for admitted native completions.
Failed transport evidence is reserved here; completion recovery and admission are
separate descendants and never change this suffix selection or add prefix votes.
"""
from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
import json
from pathlib import Path
import re

from analysis import validate_continuation
from collector_v2 import POLICY
from continue_chain import _manifest
from continue_manifest import fresh_private_output
import continue_sol as predecessor
from prepare import canonical, checked, digest, within

HERE = Path(__file__).resolve().parent
CHAIN_POLICY = 'untouched_sol_suffix_after_reserved_chain_v1'


def failure_receipt(results: Path, row: dict, artifacts: dict[str, bytes], job: dict) -> tuple[dict, str | None, str | None]:
    sample = results / f"{row['endpoint_ordinal']:04d}-{row['logical_sample_id'][:12]}"
    names = ('condition.json', 'terminal.json', 'native-identity.json', 'attempt-started.json', 'schema.json')
    raw = {name: (sample / name).read_bytes() for name in names}
    condition, terminal, identity, started = (json.loads(raw[name]) for name in names[:4])
    if (job.get('collector_policy') != POLICY or condition != row
            or terminal.get('state') != 'unadmitted_no_resend' or terminal.get('accepted') is not False
            or terminal.get('error_class') != '_ProviderAttemptFailure' or terminal.get('no_resend') is not True
            or raw['schema.json'] != artifacts[row['schema_path']]
            or identity.get('logical_sample_id') != row['logical_sample_id']
            or identity.get('session_id') is not None or started.get('session_id') is not None
            or started.get('state') != 'before_contact' or started.get('no_resend') is not True):
        raise ValueError('Sol failure condition, started receipt or terminal binding differs; no resend')
    provider = terminal.get('provider_record') or {}
    pins = provider.get('provider_artifacts', {})
    if 'codex_events' not in pins:
        raise ValueError('Sol native failure lacks pinned transport events; no resend')
    for pin in pins.values():
        raw[pin['path']] = checked(within(sample, pin['path']), pin['sha256'], pin['bytes'])
    event_rows, unreadable = [], 0
    for line in raw[pins['codex_events']['path']].splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except (ValueError, UnicodeDecodeError):
            unreadable += 1
            continue
        if not isinstance(event, dict):
            unreadable += 1
            continue
        event_rows.append(event)
    threads = [r.get('thread_id') for r in event_rows if r.get('type') == 'thread.started']
    turns = {r['turn_id'] for r in event_rows if isinstance(r.get('turn_id'), str) and r['turn_id']}
    if len(threads) > 1 or any(not isinstance(t, str) or not t for t in threads) or len(turns) > 1:
        raise ValueError('Sol failed transport contains conflicting native identities')
    thread, turn = (threads[0] if threads else None), (next(iter(turns)) if turns else None)
    # Preserve every retained file, including partial responses, without admitting a final.
    for path in sorted(sample.rglob('*')):
        if path.is_file():
            raw[path.relative_to(sample).as_posix()] = path.read_bytes()
    receipt = {
        'endpoint_ordinal': row['endpoint_ordinal'], 'logical_sample_id': row['logical_sample_id'],
        'request_sha256': row['request_sha256'], 'condition_sha256': digest(raw['condition.json']),
        'terminal_sha256': digest(raw['terminal.json']), 'terminal_state': 'unadmitted_no_resend',
        'native_state': 'failed_transport_reserved_unadmitted', 'no_resend': True,
        'native_thread_id_sha256': digest(thread.encode()) if thread else None,
        'native_turn_id_sha256': digest(turn.encode()) if turn else None,
        'native_identity_missing': thread is None, 'new_votes': 0, 'accepted_vote': False,
        'event_counts': dict(sorted(Counter(r.get('type', 'unknown') for r in event_rows).items())),
        'unreadable_event_lines': unreadable, 'completion_inferred': False,
        'artifacts': {name: {'sha256': digest(payload), 'bytes': len(payload)} for name, payload in sorted(raw.items())},
    }
    return receipt, thread, turn


def build(manifest_path: Path, prefix_jobs: list[tuple[Path, Path]], *, secondary_helper: Path) -> tuple[dict, dict[str, bytes]]:
    if not prefix_jobs:
        raise ValueError('An ordered source-job prefix chain is required')
    original, original_raw = _manifest(manifest_path)
    root = manifest_path.resolve().parent
    artifacts = {name: checked(within(root, name), pin['sha256'], pin['bytes']) for name, pin in original['artifacts'].items()}
    if 'lineage/parent-manifest.json' in artifacts:
        raise ValueError('--manifest must identify the original frozen study')
    originals = [row for row in original['requests'] if row['endpoint'] == 'sol']
    if ([row['endpoint_ordinal'] for row in originals] != list(range(1, len(originals) + 1))
            or len({row['logical_sample_id'] for row in originals}) != len(originals)):
        raise ValueError('Original Sol order or logical identities differ')
    for row in original['requests']:
        if digest(canonical({k: v for k, v in row.items() if k != 'request_sha256'})) != row['request_sha256']:
            raise ValueError('Original request descriptor commitment differs')
        for path_key, sha_key, size_key in [('prompt_path', 'prompt_sha256', 'prompt_bytes'), ('schema_path', 'schema_sha256', 'schema_bytes')]:
            payload = artifacts[row[path_key]]
            if digest(payload) != row[sha_key] or len(payload) != row[size_key]:
                raise ValueError('Original request artifact pin differs')
        for source in row['sources']:
            if digest(artifacts[source['input_path']]) != source['sha256']:
                raise ValueError('Original source artifact pin differs')
    receipts, commitments = [], []
    threads, turns, result_roots = set(), set(), set()
    for source_path, results in prefix_jobs:
        source_path, results = source_path.resolve(), results.resolve()
        if results in result_roots:
            raise ValueError('Duplicate source-job result root')
        result_roots.add(results)
        source, raw_source = _manifest(source_path)
        validate_continuation(source, original, 'sol', base_raw=original_raw, derived_root=source_path.parent)
        for name, pin in source['artifacts'].items():
            checked(within(source_path.parent, name), pin['sha256'], pin['bytes'])
        job, raw_job = predecessor.source_job(results, source, raw_source, secondary_helper)
        allowed = {f"{row['endpoint_ordinal']:04d}-{row['logical_sample_id'][:12]}": row for row in source['requests'] if row['endpoint'] == 'sol'}
        attempted = [path for path in results.iterdir() if path.is_dir() and re.match(r'\d{4}-', path.name)]
        if not attempted or any(path.name not in allowed for path in attempted):
            raise ValueError('Source attempts absent or outside their own frozen descriptors')
        attempted.sort(key=lambda path: allowed[path.name]['endpoint_ordinal'])
        first = len(receipts) + 1
        for sample in attempted:
            row = allowed[sample.name]
            if row['endpoint_ordinal'] != len(receipts) + 1:
                raise ValueError('Attempted Sol chain is duplicate or noncontiguous')
            state = json.loads((sample / 'terminal.json').read_bytes()).get('state')
            if state in {'accepted', 'semantic_rejected'}:
                receipt, thread, turn = predecessor.prefix_receipt(results, row, artifacts, job)
                receipt.update(accepted_vote=state == 'accepted', new_votes=0)
            else:
                receipt, thread, turn = failure_receipt(results, row, artifacts, job)
            if thread is not None and thread in threads or turn is not None and turn in turns:
                raise ValueError('Duplicate Sol native thread or turn identity in chain')
            if thread is not None:
                threads.add(thread)
            if turn is not None:
                turns.add(turn)
            receipt['source_job_index'] = len(commitments)
            receipts.append(receipt)
        commitments.append({
            'manifest_sha256': digest(raw_source), 'manifest_content_sha256': source['manifest_content_sha256'],
            'job_sha256': digest(raw_job), 'source_job_binding': job,
            'collector_sha256': job['collector_sha256'], 'collector_policy': job.get('collector_policy'),
            'first_endpoint_ordinal': first, 'last_endpoint_ordinal': len(receipts),
            'receipt_commitment_sha256': digest(canonical(receipts[first - 1:])),
            'runtime_timeout_attestation': None,
        })
    through = len(receipts)
    suffix = originals[through:]
    if not suffix:
        raise ValueError('No untouched Sol suffix remains')
    descendant = deepcopy(original)
    descendant.pop('manifest_content_sha256')
    descendant['historical_registration'] = {'counts': original['counts'], 'bytes': original['bytes'], 'manifest_content_sha256': original['manifest_content_sha256']}
    descendant['continuation'] = {
        'policy': CHAIN_POLICY, 'preparer_sha256': digest(Path(__file__).read_bytes()),
        'receipt_verifier_sha256': digest((HERE / 'continue_sol.py').read_bytes()),
        'parent_manifest_sha256': digest(original_raw), 'prefix_jobs': commitments,
        'reserved_endpoint': 'sol', 'reserved_through_endpoint_ordinal': through,
        'selection': 'Every original Sol request after the entire reserved prefix, independent of all prefix outcomes',
        'prefix_receipts': receipts, 'prefix_receipt_commitment_sha256': digest(canonical(receipts)),
        'no_resend_reserved_prefix': True, 'new_votes': 0,
        'runtime_timeout_attestation': None, 'collector_v2_execution_timeout_seconds': 300,
        'runtime_authority': 'Unchanged collector_v2 executes at 300 seconds; preparation grants no execution authority or timeout override',
    }
    descendant['collection_policy'] = {'name': POLICY, 'collector_sha256': digest((HERE / 'collector_v2.py').read_bytes())}
    descendant['requests'] = suffix
    initial = [row for row in suffix if row['repeat'] == 0]
    descendant['counts'] = {
        'reserved_prefix_requests': through, 'requests_per_endpoint': len(suffix), 'requests_total': len(suffix),
        'initial_requests_per_endpoint': len(initial), 'repeat_requests_per_endpoint': len(suffix) - len(initial),
        'by_arm_per_endpoint': dict(sorted(Counter(row['arm'] for row in suffix).items())),
        'hbq_initial_verdict_positions_per_endpoint': sum(len(row['question_ids']) for row in initial if row['arm'] == 'hbq'),
        'ttcw14_initial_test_positions_per_endpoint': 14 * sum(row['arm'] == 'ttcw14' for row in initial),
    }
    artifacts['lineage/parent-manifest.json'] = original_raw
    descendant['artifacts'] = {name: {'sha256': digest(raw), 'bytes': len(raw)} for name, raw in sorted(artifacts.items())}
    prompt_bytes = sum(row['prompt_bytes'] for row in suffix)
    descendant['bytes'] = {'prompt_transmission_per_endpoint': prompt_bytes, 'prompt_transmission_total': prompt_bytes,
                           'schema_transmission_total': sum(row['schema_bytes'] for row in suffix), 'unique_artifacts_total': sum(map(len, artifacts.values()))}
    descendant['manifest_content_sha256'] = digest(canonical(descendant))
    artifacts['manifest.json'] = canonical(descendant)
    return descendant, artifacts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--prefix-job', action='append', required=True, metavar='MANIFEST=RESULTROOT')
    parser.add_argument('--secondary-helper', type=Path, required=True)
    parser.add_argument('--private-output', type=Path, required=True)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    jobs = []
    for item in args.prefix_job:
        manifest, separator, results = item.partition('=')
        if not separator or not manifest or not results:
            parser.error('--prefix-job requires MANIFEST=RESULTROOT')
        jobs.append((Path(manifest), Path(results)))
    output = fresh_private_output(args.private_output, args.manifest.resolve().parent, args.secondary_helper,
                                  *(path for job in jobs for path in (job[0].resolve().parent, job[1])))
    manifest, artifacts = build(args.manifest, jobs, secondary_helper=args.secondary_helper)
    if not args.dry_run:
        output.mkdir(parents=True, exist_ok=False)
        for name, raw in artifacts.items():
            path = within(output, name)
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open('xb') as handle:
                handle.write(raw)
    print(json.dumps({
        'state': 'dry_run_without_contact' if args.dry_run else 'prepared_without_contact',
        'manifest_sha256': digest(artifacts['manifest.json']), 'manifest_content_sha256': manifest['manifest_content_sha256'],
        'parent_manifest_sha256': manifest['continuation']['parent_manifest_sha256'],
        'counts': manifest['counts'], 'historical_counts': manifest['historical_registration']['counts'],
        'reserved_prefix_states': dict(Counter(row['terminal_state'] for row in manifest['continuation']['prefix_receipts'])),
        'source_jobs': [{k: v for k, v in j.items() if k != 'source_job_binding'} for j in manifest['continuation']['prefix_jobs']],
        'collector_v2_execution_timeout_seconds': 300, 'provider_calls_made': 0,
    }, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
