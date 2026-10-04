"""Reserve a verified settled Sol prefix and freeze its untouched original suffix."""
from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
import json
from pathlib import Path
import re
import sys

from collector_v2 import POLICY
from continue_chain import _manifest
from continue_manifest import fresh_private_output
from prepare import canonical, checked, digest, within, REPO

sys.path.insert(0, str(REPO / 'src'))
from hbqrs import codex_receipts

HERE = Path(__file__).resolve().parent
ACCOUNT_SHA256 = digest(canonical({'type': 'chatgpt', 'email': 'hailey2collet@gmail.com'})[:-1])
FILES = ('condition.json', 'terminal.json', 'native-result.json', 'native-identity.json',
         'attempt-started.json', 'schema.json', 'response.json', 'acceptance.json')


def source_job(results: Path, manifest: dict, raw_manifest: bytes, helper: Path) -> tuple[dict, bytes]:
    raw = (results / 'job.json').read_bytes()
    job = json.loads(raw)
    expected = {'endpoint': 'sol', 'manifest_sha256': digest(raw_manifest), 'model': 'gpt-6.1-sol',
                'reasoning': 'high', 'zero_charge_only': True, 'automatic_retries': 0,
                'account_identity_sha256': ACCOUNT_SHA256,
                'helper_sha256': digest(helper.read_bytes()),
                'runner_sha256': digest((REPO / 'src/hbqrs/runner.py').read_bytes()),
                'receipt_reader_sha256': codex_receipts.binding()['reader_sha256'],
                'validator_sha256': manifest['implementation']['semantic_validator_sha256'],
                'destination': 'OpenAI ChatGPT subscription via native Codex exec',
                'payload_classification': 'public_repo',
                'sampler': 'native defaults; requested high; temperature unsupported'}
    if any(job.get(key) != value for key, value in expected.items()):
        raise ValueError('Source Sol job manifest, account, helper, runtime or admission binding differs')
    policy = job.get('collector_policy')
    if policy not in {None, POLICY}:
        raise ValueError('Source Sol collector policy differs')
    collector = HERE / ('collector.py' if policy is None else 'collector_v2.py')
    if job.get('collector_sha256') != digest(collector.read_bytes()):
        raise ValueError('Source Sol collector bytes differ')
    if manifest.get('collection_policy') is not None and manifest['collection_policy'] != {
            'name': policy, 'collector_sha256': job['collector_sha256']}:
        raise ValueError('Source frozen collection policy differs')
    if expected['validator_sha256'] != digest((HERE / 'validate_response.py').read_bytes()):
        raise ValueError('Frozen semantic admission implementation differs')
    sys.path.insert(0, str(Path(r'C:\Users\Haile\.codex\tools')))
    from model_work_queue.adapters import json_schema_subset
    if manifest['implementation']['schema_subset_sha256'] != digest(Path(json_schema_subset.__file__).read_bytes()):
        raise ValueError('Frozen schema admission implementation differs')
    return job, raw


def prefix_receipt(results: Path, row: dict, artifacts: dict[str, bytes], job: dict) -> tuple[dict, str, str]:
    sample = results / f"{row['endpoint_ordinal']:04d}-{row['logical_sample_id'][:12]}"
    raw = {name: (sample / name).read_bytes() for name in FILES}
    condition, terminal, native, identity, started = (json.loads(raw[name]) for name in FILES[:5])
    state = terminal.get('state')
    if state not in {'accepted', 'semantic_rejected'} or terminal.get('accepted') is not (state == 'accepted'):
        raise ValueError('Sol prefix contains an unresolved or conflicting terminal state; no resend')
    if (condition != row or raw['schema.json'] != artifacts[row['schema_path']]
            or identity.get('logical_sample_id') != row['logical_sample_id']
            or identity.get('session_id') is not None or started.get('session_id') is not None
            or started.get('state') != 'before_contact' or started.get('no_resend') is not True
            or terminal.get('no_resend') is not True):
        raise ValueError('Sol prefix condition, schema or no-resend identity differs')
    for key, filename in [('native_result_sha256', 'native-result.json'),
                          ('response_sha256', 'response.json'), ('acceptance_sha256', 'acceptance.json')]:
        if terminal.get(key) != digest(raw[filename]):
            raise ValueError('Sol terminal artifact commitment differs')
    response, acceptance = json.loads(raw['response.json']), json.loads(raw['acceptance.json'])
    if acceptance.get('accepted') is not (state == 'accepted') or terminal.get('abstention') != acceptance.get('abstention'):
        raise ValueError('Sol retained semantic admission state differs')
    prompt = artifacts[row['prompt_path']].decode('utf-8')
    codex_receipts.verify(sample, native, prompt=prompt, model=job['model'], reasoning=job['reasoning'])
    retained = {}
    for name, pin in native['provider_artifacts'].items():
        payload = checked(within(sample, pin['path']), pin['sha256'], pin['bytes'])
        retained[name] = payload
        raw[pin['path']] = payload
    if json.loads(retained['codex_message']) != response:
        raise ValueError('Sol native final response differs from retained response')
    # verify() reprojects the exact own rollout; only then use its native identity.
    thread, _ = codex_receipts.event_identity(retained['codex_events'], retained['codex_message'])
    projected = json.loads(retained['codex_receipt'])
    if thread != projected['thread_id'] or thread != native['reported']['session_id']:
        raise ValueError('Sol own-thread native identity differs')
    command = native.get('command', [])
    try:
        schema_arg = command[command.index('--output-schema') + 1]
        cwd_arg = command[command.index('--cd') + 1]
    except (ValueError, IndexError):
        raise ValueError('Sol native command lacks schema or working-directory binding') from None
    if Path(schema_arg).resolve() != (sample / 'schema.json').resolve() or Path(cwd_arg).resolve() != sample.resolve():
        raise ValueError('Sol native command schema or working directory differs')
    receipt = {'endpoint_ordinal': row['endpoint_ordinal'], 'logical_sample_id': row['logical_sample_id'],
               'request_sha256': row['request_sha256'], 'condition_sha256': digest(raw['condition.json']),
               'terminal_sha256': digest(raw['terminal.json']), 'terminal_state': state,
               'native_state': 'completed_own_turn_verified', 'no_resend': True,
               'native_thread_id_sha256': digest(thread.encode()),
               'native_turn_id_sha256': digest(projected['turn_id'].encode()),
               'artifacts': {name: {'sha256': digest(payload), 'bytes': len(payload)} for name, payload in sorted(raw.items())}}
    return receipt, thread, projected['turn_id']


def build(manifest_path: Path, results: Path, *, secondary_helper: Path) -> tuple[dict, dict[str, bytes]]:
    original, original_raw = _manifest(manifest_path)
    root, results = manifest_path.resolve().parent, results.resolve()
    artifacts = {name: checked(within(root, name), pin['sha256'], pin['bytes']) for name, pin in original['artifacts'].items()}
    if 'lineage/parent-manifest.json' in artifacts:
        raise ValueError('Manifest must identify the original frozen study')
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
                raise ValueError('Original source pin differs')
    job, raw_job = source_job(results, original, original_raw, secondary_helper)
    allowed = {f"{row['endpoint_ordinal']:04d}-{row['logical_sample_id'][:12]}": row for row in originals}
    attempted = [path for path in results.iterdir() if path.is_dir() and re.match(r'\d{4}-', path.name)]
    if not attempted or any(path.name not in allowed for path in attempted):
        raise ValueError('Sol attempts absent or outside original frozen descriptors')
    attempted.sort(key=lambda path: allowed[path.name]['endpoint_ordinal'])
    receipts, threads, turns = [], set(), set()
    for sample in attempted:
        row = allowed[sample.name]
        if row['endpoint_ordinal'] != len(receipts) + 1:
            raise ValueError('Attempted Sol prefix is noncontiguous')
        receipt, thread, turn = prefix_receipt(results, row, artifacts, job)
        if thread in threads or turn in turns:
            raise ValueError('Duplicate Sol native thread or turn identity')
        threads.add(thread); turns.add(turn); receipts.append(receipt)
    through = len(receipts)
    suffix = originals[through:]
    if not suffix:
        raise ValueError('No untouched Sol suffix remains')
    descendant = deepcopy(original)
    descendant.pop('manifest_content_sha256')
    descendant['historical_registration'] = {'counts': original['counts'], 'bytes': original['bytes'],
                                              'manifest_content_sha256': original['manifest_content_sha256']}
    descendant['continuation'] = {
        'policy': 'untouched_sol_suffix_after_settled_native_prefix_v1', 'preparer_sha256': digest(Path(__file__).read_bytes()),
        'parent_manifest_sha256': digest(original_raw), 'prefix_job_sha256': digest(raw_job),
        'source_job_binding': job, 'reserved_endpoint': 'sol', 'reserved_through_endpoint_ordinal': through,
        'selection': 'Every original Sol request after the entire settled prefix, independent of prefix outcomes',
        'prefix_receipts': receipts, 'prefix_receipt_commitment_sha256': digest(canonical(receipts)),
        'no_resend_reserved_prefix': True, 'runtime_timeout_attestation': None,
        'runtime_authority': 'Source job does not attest call timeout; preparation grants no execution authority',
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
                           'schema_transmission_total': sum(row['schema_bytes'] for row in suffix),
                           'unique_artifacts_total': sum(map(len, artifacts.values()))}
    descendant['manifest_content_sha256'] = digest(canonical(descendant))
    artifacts['manifest.json'] = canonical(descendant)
    return descendant, artifacts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--prefix-results', type=Path, required=True)
    parser.add_argument('--secondary-helper', type=Path, required=True)
    parser.add_argument('--private-output', type=Path, required=True)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    output = fresh_private_output(args.private_output, args.manifest.resolve().parent, args.prefix_results, args.secondary_helper)
    manifest, artifacts = build(args.manifest, args.prefix_results, secondary_helper=args.secondary_helper)
    if not args.dry_run:
        output.mkdir(parents=True, exist_ok=False)
        for name, raw in artifacts.items():
            path = within(output, name)
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open('xb') as handle:
                handle.write(raw)
    print(json.dumps({'state': 'dry_run_without_contact' if args.dry_run else 'prepared_without_contact',
                      'manifest_sha256': digest(artifacts['manifest.json']), 'manifest_content_sha256': manifest['manifest_content_sha256'],
                      'parent_manifest_sha256': manifest['continuation']['parent_manifest_sha256'],
                      'source_job_sha256': manifest['continuation']['prefix_job_sha256'],
                      'counts': manifest['counts'], 'historical_counts': manifest['historical_registration']['counts'],
                      'reserved_prefix_states': dict(Counter(r['terminal_state'] for r in manifest['continuation']['prefix_receipts'])),
                      'provider_calls_made': 0}, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
