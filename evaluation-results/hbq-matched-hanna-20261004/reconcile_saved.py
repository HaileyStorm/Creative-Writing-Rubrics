"""Explicit zero-call HANNA descendants for two pinned completed DNS-transport failures."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
PROGRAM = Path(r'C:\Users\Haile\Documents\cwr-resume-control-20260919-r1\successor-program-20261004')
RESULTS = PROGRAM / 'hanna-reference/judging-sol-parallel-001'
HOME = Path(r'C:\Users\Haile\.codex\collection-accounts\cwr-sol-secondary')
POLICY = 'matched_hanna_saved_sol_transport_reconciliation_v1'
COLLECTOR_SHA = '327bfa1deeed417f7a558914d650297fda3c0999adccd2c2a8b0a661b182cf83'
TRANSPORT_SHA = 'fbedc8e50d08de7dff0547483f26c9fd081a8b4c9e62f0713609ce043e0fb34c'
READER_SHA = '5d1c7af681e881a77201dee7cece4a14fa11cadc86d119714766492e547e1116'
VALIDATOR_SHA = 'a41915877b6f7e21a05f0b34d3c31c788f7f23070ab674ecfc514d93391e270e'
COMMON = {
    'manifest': ('d4f8c8c7847b7715d97ccb9d0a46fdc0651e79777f17309019fc2e75ad02bedc', 15542284),
    'job': ('ae211908de20c69438d29a726b6f6cc9e64e6af232e5aa2d3ed06ba520457927', None),
    'account': ('40edd086c88f8b2770cabdfac9776d647fdba5bd1bf1e11dbd0b6e58972c5a57', None),
}
SLOTS = {
    '0007-cc2135de14f3': {
        'condition': ('18f2de05863c1cbeabaf33933e1b99e0360386c2b4fa55eeed16bcd145ada387', 2237),
        'started': ('465fb04944be50cf0f8db30d722d5eb7e45ce7ea0fe46e2afc439708c7a69521', 838),
        'identity': ('1a03cfb67dc5c233e909e698499190041da18d427fccdaad8bf6c75f6b2f5a12', 107),
        'terminal': ('cd6be63bec20c4476c3b333b2166a3f4d0fd890d1befc5b893dc7cf1f8b3b57b', 1710),
        'events': ('e90f405117190e023ef483e7c26c5534e03f7203c09b52774ca67a2f73e9f0ad', 8726),
        'final': ('e0b4a537ca4625c916c1814af6a673c00d8c47108b464b2400e38967bc762a64', 6741),
        'rollout': ('6ed1b75dfa249d4533ac214fcbe8b5b0b8e2d5e80b4da988d5ee0f0d87711f0f', 86648),
        'projection': '5cbff8aa0e9b5a45edf5fe81453f688556b88174b1d39d04cc6459e49571a972',
        'reader_receipt': '5a50e53227ba7757eb0583b695a50045e7cb4ee863ddc3ad6b58656e404528ef',
        'thread': '01a10d3b-59e3-7d23-bd05-2b48c53999ec',
        'rollout_name': 'rollout-2026-10-05T12-02-35-01a10d3b-59e3-7d23-bd05-2b48c53999ec.jsonl',
    },
    '0008-9a27a33af88d': {
        'condition': ('b72c1f148c64788813454adac644a5475744565a56f27dd5a484fd68b24d707e', 2305),
        'started': ('bf7f0c7f8c7c8943c9114fd7f2d8fdaff8bfa5f2d83d7e574e51845d7c966732', 838),
        'identity': ('3acaf1e5330e9c411441d0e40e007dce985c60c1c991d8d756514a4aa27908c4', 107),
        'terminal': ('d039849ae656492f8fea60233dfc02a59e677a18229e4aa8c26cb24bde6d790b', 1710),
        'events': ('cf240e834575d3a9ad57a80b08e71e5f7f6e449a0cef666d3dfc25bfd679c69a', 7187),
        'final': ('6f18c13f01e89ae7125278b3d118bed6517e43559b332874d6aa161b1675813f', 5282),
        'rollout': ('991265aaba87c19aa8ecf9e83a0b14fc8e28b5bb50d5ebcde1ad021e52750922', 82689),
        'projection': '7f0532e8fd662f1c352b8a565d8c8e7c070a07df846f7fe57f4b615d19528c14',
        'reader_receipt': '31d0b4c9a02e28ac8d876c524a40e24d1d58a13034540a351e77807fcba53002',
        'thread': '01a10d3b-6282-75e3-af9f-2d613464fd83',
        'rollout_name': 'rollout-2026-10-05T12-02-38-01a10d3b-6282-75e3-af9f-2d613464fd83.jsonl',
    },
}


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec); sys.modules[name] = module
    spec.loader.exec_module(module); return module


def digest(raw): return hashlib.sha256(raw).hexdigest()
def canonical(value): return (json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False) + '\n').encode()
def require(ok, message):
    if not ok: raise ValueError(message)


def bind_attempt(slot, row, manifest, job, started, identity, terminal):
    require(slot in SLOTS and row in manifest['requests'] and row['endpoint'] == 'sol'
            and f"{row['endpoint_ordinal']:04d}-{row['logical_sample_id'][:12]}" == slot, 'Exact original observation differs')
    require(digest(canonical({k: v for k, v in row.items() if k != 'request_sha256'})) == row['request_sha256'], 'Frozen condition commitment differs')
    require(job['policy'] == 'matched_hanna_native_parallel_owner_amendment_v1' and job['collector_sha256'] == COLLECTOR_SHA
            and job['manifest_sha256'] == COMMON['manifest'][0] and job['receipt_reader_sha256'] == READER_SHA
            and job['admission_sha256'] == VALIDATOR_SHA and job['planned_study_requests'] == 6864
            and job['runtime']['model'] == 'gpt-6.1-sol' and job['runtime']['reasoning'] == 'high', 'Frozen source job/runtime differs')
    require(started['manifest_sha256'] == COMMON['manifest'][0] and started['job_sha256'] == COMMON['job'][0]
            and started['logical_sample_id'] == row['logical_sample_id'] and started['attempt'] == 1 and started['no_resend'] is True
            and started['prompt_sha256'] == row['prompt_sha256'] and started['schema_sha256'] == row['schema_sha256']
            and started['session_id'] is None and identity == {'session_id': None, 'logical_sample_id': row['logical_sample_id']}, 'Own started identity differs')
    require(terminal['state'] == 'unadmitted_no_resend' and terminal['accepted'] is False and terminal['no_resend'] is True
            and terminal['logical_sample_id'] == row['logical_sample_id'] and terminal['job_sha256'] == COMMON['job'][0]
            and terminal['manifest_sha256'] == COMMON['manifest'][0] and terminal['error_class'] == '_ProviderAttemptFailure', 'Original strict failure differs')


def reconcile(manifest_path, results, slot, home, rollout, *, snapshot=None, commitments=None):
    require(slot in SLOTS and results.resolve() == RESULTS.resolve() and home.resolve() == HOME.resolve()
            and rollout.resolve() == HOME / 'sessions/2026/10/05' / SLOTS[slot]['rollout_name'], 'Exact source job/slot/own rollout locator differs')
    pins = {**COMMON, **{k: v for k, v in SLOTS[slot].items() if isinstance(v, tuple)}}
    collector_path = HERE / 'collector.py'; transport_path = HERE.parent / 'hbq-native-transport-recovery-v1/reconcile.py'
    require(digest(collector_path.read_bytes()) == COLLECTOR_SHA and digest(transport_path.read_bytes()) == TRANSPORT_SHA, 'Retained implementation pin differs')
    c = load('hanna_saved_collection', collector_path); transport = load('hanna_saved_transport', transport_path)
    class Reads(transport.ReadSet):
        def raw(self, name, path):
            require(self.snapshot is None or name in self.expected, 'Snapshot commitment missing: ' + name)
            raw = super().raw(name, path)
            if name in pins:
                sha, size = pins[name]
                require(digest(raw) == sha and (size is None or len(raw) == size), 'Pinned source differs: ' + name)
            return raw
    reads = Reads(snapshot, commitments); sample = results / slot
    paths = {'manifest': manifest_path, 'job': results / 'job.json', 'account': results / 'account-binding.json',
        'condition': sample / 'condition.json', 'started': sample / 'attempt-started.json',
        'identity': sample / 'native-identity.json', 'terminal': sample / 'terminal.json'}
    values = {name: json.loads(reads.raw(name, path)) for name, path in paths.items()}
    manifest, job, row, started = (values[k] for k in ('manifest', 'job', 'condition', 'started'))
    root = manifest_path.parent
    require(manifest['study_id'] == c.p.STUDY and manifest['counts']['requests_total'] == 6864
            and manifest['labels_read'] is False and manifest['labels_released'] is False, 'Frozen full denominator/label boundary differs')
    tools = Path(manifest['external_pins']['tools_root_local_only'])
    require(c.verify_job_binding(results, manifest, root, COMMON['manifest'][0], 'sol', tools) == job, 'Original job binding differs')
    bind_attempt(slot, row, manifest, job, started, values['identity'], values['terminal'])
    require(values['account'] == c.t.account_receipt(job) and started['account_binding_sha256'] == digest(reads.raws['account']), 'Original own account differs')
    invocation = json.loads(reads.raw('invocation', c.within(results, started['execution_invocation']['path'])))
    require(digest(reads.raws['invocation']) == started['execution_invocation']['sha256']
            and len(reads.raws['invocation']) == started['execution_invocation']['bytes']
            and invocation['job_sha256'] == COMMON['job'][0] and invocation['workers'] == job['workers']
            and c.execution_workers(invocation['argv']) == job['workers'] and '--owner-global-headroom-verified' in invocation['argv'], 'Original execution argv differs')
    names = {row['prompt_path'], row['schema_path'], row['retained_schema_path'], row['task_context']['path'],
             row['originating_prompt']['path'], row['task_contract_path'], row['compiled_path'], *(s['input_path'] for s in row['sources'])}
    names.update({'implementation/schema_subset.py', 'implementation/validate_response.py', 'implementation/runner.py',
                  'implementation/codex_receipts.py', 'implementation/core.py', 'implementation/prepare.py'})
    for index, name in enumerate(sorted(names)):
        raw = reads.raw('frozen_' + str(index), c.within(root, name)); meta = manifest['artifacts'][name]
        require(digest(raw) == meta['sha256'] and len(raw) == meta['bytes'], 'Frozen source/admission artifact differs')
    for index, (name, meta) in enumerate(sorted(values['terminal']['retained_artifacts'].items())):
        raw = reads.raw('original_retained_' + str(index), c.within(sample, name))
        require(digest(raw) == meta['sha256'] and len(raw) == meta['bytes'], 'Original retained artifact differs')
    for name, path, pin in [('collector_implementation', collector_path, COLLECTOR_SHA),
            ('transport_implementation', transport_path, TRANSPORT_SHA), ('reader_implementation', REPO / 'src/hbqrs/codex_receipts.py', READER_SHA),
            ('validator_implementation', root / 'implementation/validate_response.py', VALIDATOR_SHA)]:
        require(digest(reads.raw(name, path)) == pin, 'Named implementation differs')
    for name in ('runner.py', 'core.py', 'prepare.py'):
        current = HERE / name if name == 'prepare.py' else REPO / 'src/hbqrs' / name
        require(digest(current.read_bytes()) == manifest['artifacts']['implementation/' + name]['sha256'], 'Exact context reader differs')
    prompt, schema, texts, context = c.inputs(root, manifest, row)
    require((sample / 'prompt.txt').read_bytes() == prompt and (sample / 'schema.json').read_bytes() == schema
            and (sample / 'task-context.json').read_bytes() == context.encode()
            and all((sample / 'sources' / (tid + '.txt')).read_bytes() == text.encode() for tid, text in texts.items()), 'Own literal source/context snapshots differ')
    response, native = transport.recover_sol(reads, sample, prompt.decode(), home, started, rollout_path=rollout)
    native_receipt = native['native_reader_receipt']; expected = SLOTS[slot]
    require(native_receipt['thread_id'] == expected['thread'] and len(native['diagnostics']) == 7
            and native['filtered_events_sha256'] == expected['projection'] and digest(canonical(native_receipt)) == expected['reader_receipt'], 'Pinned own completed transport projection differs')
    if snapshot is not None: reads.raw('events_projection', Path('derived:validated_dns_transport_projection'))
    subset = load('hanna_saved_subset', root / 'implementation/schema_subset.py')
    validator = load('hanna_saved_validator', root / 'implementation/validate_response.py')
    acceptance = c.admission(root, row, manifest, response, schema, texts, context, subset, validator)
    recipe = {'manifest': str(manifest_path), 'results_root': str(results), 'slot': slot, 'own_home': str(home), 'rollout': str(rollout)}
    receipt = {'schema_version': 1, 'policy': POLICY, 'recipe': recipe, 'endpoint': 'sol', 'slot': slot,
        'logical_sample_id': row['logical_sample_id'], 'endpoint_ordinal': row['endpoint_ordinal'], 'request_sha256': row['request_sha256'],
        'state': 'completed_semantically_accepted' if acceptance['accepted'] else 'completed_semantically_rejected',
        'accepted': acceptance['accepted'], 'abstention': acceptance['abstention'], 'semantic_errors': acceptance['errors'],
        'original_terminal_preserved': 'unadmitted_no_resend', 'source_terminal_sha256': expected['terminal'][0],
        'same_original_observation_only': True, 'new_logical_votes': 0, 'provider_calls_made': 0, 'no_resend': True,
        'full_planned_denominator': 6864, 'human_labels_released': False, 'original_native_envelope_reconstructed': False,
        'original_strict_native_admission_satisfied': False, 'physical_contact_cardinality_proven': False,
        'native': native, 'response_sha256': digest(reads.raws['final']), 'acceptance_sha256': digest(canonical(acceptance)),
        'source_commitments': reads.commitments(), 'implementation_sha256': digest(Path(__file__).read_bytes())}
    return receipt, reads.raws['final'], acceptance, reads


def fresh_output(output, roots):
    output = output.resolve()
    require(not output.exists() and all(not output.is_relative_to(root.resolve()) and not root.resolve().is_relative_to(output)
                                       for root in roots), 'Output must be fresh and outside original source trees/repository')
    return output


def verify(receipt_path, expected_sha):
    raw = receipt_path.read_bytes(); require(digest(raw) == expected_sha, 'Exact saved descendant differs')
    saved = json.loads(raw); recipe = saved['recipe']
    actual, _, _, _ = reconcile(Path(recipe['manifest']), Path(recipe['results_root']), recipe['slot'],
        Path(recipe['own_home']), Path(recipe['rollout']), snapshot=receipt_path.parent, commitments=saved['source_commitments'])
    require(actual == saved, 'Saved descendant/source/admission replay differs')
    return actual


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    for name in ('manifest', 'results-root', 'own-home', 'rollout', 'output-root'): parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--slot', choices=tuple(SLOTS), required=True)
    parser.add_argument('--dry-run', '--validate-only', dest='dry_run', action='store_true')
    args = parser.parse_args()
    output = fresh_output(args.output_root, [REPO, args.manifest.parent, args.results_root, args.own_home])
    receipt, response, acceptance, reads = reconcile(args.manifest.resolve(), args.results_root.resolve(), args.slot, args.own_home.resolve(), args.rollout.resolve())
    raw = canonical(receipt)
    if not args.dry_run:
        output.mkdir(parents=True, exist_ok=False)
        try:
            for name, content in reads.raws.items():
                if name != 'events_projection': require(Path(reads.paths[name]).read_bytes() == content, 'Source changed before snapshot')
                path = output / 'native' / (name + '.bin'); path.parent.mkdir(parents=True, exist_ok=True)
                with path.open('xb') as handle: handle.write(content)
            for name, content in [('reconcile_saved.py', Path(__file__).read_bytes()), ('response.json', response),
                    ('acceptance.json', canonical(acceptance)), ('reconciliation.json', raw),
                    ('terminal.json', canonical({'state': receipt['state'], 'no_resend': True, 'reconciliation_sha256': digest(raw)}))]:
                with (output / name).open('xb') as handle: handle.write(content)
        except (OSError, ValueError):
            if not (output / 'terminal.json').exists():
                with (output / 'terminal.json').open('xb') as handle: handle.write(canonical({'state': 'failed_private_snapshot_pending', 'no_resend': True}))
            raise
    print(json.dumps({'policy': POLICY, 'dry_run': args.dry_run, 'slot': args.slot, 'accepted': receipt['accepted'],
        'semantic_error_count': len(receipt['semantic_errors']), 'diagnostics': len(receipt['native']['diagnostics']),
        'receipt_sha256': digest(raw), 'response_sha256': receipt['response_sha256'], 'acceptance_sha256': receipt['acceptance_sha256'],
        'verified_input_files': len(reads.raws), 'provider_calls_made': 0, 'new_logical_votes': 0,
        'human_labels_released': False, 'full_planned_denominator': 6864}, sort_keys=True))


if __name__ == '__main__':
    try: main()
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise SystemExit('HANNA saved reconciliation pending: ' + type(error).__name__) from None
