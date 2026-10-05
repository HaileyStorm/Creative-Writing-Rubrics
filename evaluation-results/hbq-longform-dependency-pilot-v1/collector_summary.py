"""One-attempt secondary Sol summaries; receipt admission is not a factual oracle."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import uuid
import importlib.util

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('p4_summary_prepare', HERE / 'prepare.py')
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)
POLICY = 'longform_native_source_summary_once_v1'
SETTLED = 'accepted_generation'


def now():
    return datetime.now(timezone.utc).isoformat()


def record(path, value):
    p.base.write_new(path, p.canonical(value))


def pinned(root, relative, meta):
    raw = p.base.within(root, relative).read_bytes()
    p.require(len(raw) == meta['bytes'] and p.digest(raw) == meta['sha256'], 'Frozen artifact commitment differs')
    return raw


def load_manifest(path, manifest_sha, collector_sha):
    raw = path.read_bytes(); manifest = json.loads(raw); root = path.resolve().parent
    p.require(p.digest(raw) == manifest_sha and p.digest(Path(__file__).read_bytes()) == collector_sha, 'Exact manifest/collector pin differs')
    p.require(manifest['study_id'] == p.POLICY and manifest['stage'] == 'source_summary_generation'
              and manifest['summary_policy'] == p.SUMMARY_POLICY and manifest['candidate'] is None
              and manifest['oracle_accepted'] is False and manifest['execution_authority'] is False
              and manifest['human_labels_supplied'] == 0 and manifest['counts'] == {'works': 2, 'summary_generation_calls': 2, 'judging_requests_planned': 464},
              'Only the exact two-source unscored summary contract is eligible')
    for relative, meta in manifest['artifacts'].items(): pinned(root, relative, meta)
    runtime = manifest['runtime']
    p.require(runtime['model'] == 'gpt-6.1-sol' and runtime['reasoning'] == 'high'
              and runtime['receipt_policy'] == 'codex_native_rollout_v1' and runtime['timeout_seconds'] == 900
              and runtime['workers'] == runtime['attempts_per_logical_sample'] == 1 and runtime['automatic_retries'] == 0
              and runtime['account_identity_sha256'] == p.base.SECONDARY_ACCOUNT_SHA256, 'Frozen Sol/high one-attempt runtime differs')
    prior_raw = pinned(root, 'private/source-generation-manifest.json', manifest['artifacts']['private/source-generation-manifest.json'])
    p.require(p.digest(prior_raw) == manifest['source_generation_manifest_file_sha256'] == p.RUNTIME_SHA, 'Prior native runtime source differs')
    prior = json.loads(prior_raw)
    p.generation.verify_external_pins(prior)
    p.require(manifest['external_pins'] == prior['external_pins'] and all(runtime[k] == v for k,v in prior['runtime'].items() if k != 'outbound_artifacts'),
              'Secondary helper/account/runtime was changed')
    for path_current, relative in [(HERE / 'prepare.py', 'implementation/prepare.py'),
            (p.REPO / 'src/hbqrs/core.py', 'implementation/core.py'),
            (p.REPO / 'src/hbqrs/scoring_v2.py', 'implementation/scoring_v2.py')]:
        p.require(p.digest(path_current.read_bytes()) == manifest['artifacts'][relative]['sha256'], 'Frozen preparation/scoring code differs')
    p.require(manifest['source_index_commitments'] == p.SOURCE_PINS, 'Source index pins differ')
    for relative, sha in p.SOURCE_PINS.items():
        p.require(manifest['artifacts']['source-index/' + relative]['sha256'] == sha, 'Exact source index commitment differs')
    subset = p.load('p4_summary_frozen_subset', root / 'implementation/schema_subset.py')
    receipts = p.load('p4_summary_frozen_receipts', root / 'implementation/codex_receipts.py')
    rows = manifest['requests']
    p.require(len(rows) == 2 and {r['work_id'] for r in rows} == {'pg43','pg209'}
              and [r['ordinal'] for r in rows] == [1,2] and len({r['logical_sample_id'] for r in rows}) == 2, 'Summary request inventory differs')
    for row in rows:
        condition = {k:v for k,v in row.items() if k not in ('endpoint','ordinal','endpoint_ordinal','logical_sample_id','request_sha256')}
        p.require(row['endpoint'] == 'sol' and row['endpoint_ordinal'] == row['ordinal']
                  and row['stage'] == 'summary_generation' and row['summary_policy'] == p.SUMMARY_POLICY
                  and p.digest(p.canonical(condition)) == row['logical_sample_id']
                  and p.digest(p.canonical({k:v for k,v in row.items() if k != 'request_sha256'})) == row['request_sha256'], 'Summary request identity differs')
        prompt, schema, source, units = inputs(root, manifest, row)
        subset.validate_schema(json.loads(schema))
        p.require(source in prompt and p.canonical(units) in prompt, 'Exact source/unit projection absent from frozen prompt')
    return manifest, root, subset, receipts


def inputs(root, manifest, row):
    prompt = pinned(root, row['prompt_path'], manifest['artifacts'][row['prompt_path']])
    schema = pinned(root, row['schema_path'], manifest['artifacts'][row['schema_path']])
    source = pinned(root, row['source']['path'], row['source'])
    p.require(p.digest(prompt) == row['prompt_sha256'] and len(prompt) == row['prompt_bytes']
              and p.digest(schema) == row['schema_sha256'] and len(schema) == row['schema_bytes'], 'Request prompt/schema pin differs')
    index_path = 'source-index/indexes/' + row['work_id'] + '.json'
    index_raw = pinned(root, index_path, manifest['artifacts'][index_path]); index = json.loads(index_raw)
    p.require(p.digest(index_raw) == row['unit_index_sha256'] and index['narrative_sha256'] == row['source']['sha256'], 'Source-to-unit-index identity differs')
    units = [{k:u[k] for k in ('id','kind','heading','source_char','narrative_char')} for u in index['units']]
    return prompt, schema, source, units


def collector_binding(manifest, manifest_sha, collector_sha):
    return {'schema_version': 1, 'policy': POLICY, 'collector_sha256': collector_sha,
        'generation_manifest_file_sha256': manifest_sha, 'summary_job_sha256': p.digest(p.canonical(p.summary_job_binding(manifest, manifest_sha))),
        'prior_runtime_manifest_file_sha256': manifest['source_generation_manifest_file_sha256'],
        'input_artifact_commitment_sha256': p.digest(p.canonical(manifest['artifacts'])),
        'account_identity_sha256': manifest['runtime']['account_identity_sha256'], 'codex_home_sha256': manifest['runtime']['codex_home_sha256'],
        'helper_sha256': manifest['artifacts']['implementation/secondary-helper.py']['sha256'],
        'runner_sha256': manifest['artifacts']['implementation/runner.py']['sha256'],
        'receipt_reader_sha256': manifest['artifacts']['implementation/codex_receipts.py']['sha256'],
        'cli_sha256': manifest['external_pins']['cli_sha256'], 'timeout_seconds': 900, 'workers': 1,
        'automatic_retries': 0, 'no_ambiguous_resend': True, 'receipt_policy': 'codex_native_rollout_v1',
        'summary_semantically_verified': False, 'oracle_accepted': False, 'provider_contact_cardinality_proven': False}


def sample_path(output, row):
    return output / f"{row['ordinal']:04d}-{row['work_id']}-{row['logical_sample_id'][:12]}"


def verify_job(output, manifest, manifest_sha, collector_sha, raw_manifest):
    p.require(json.loads((output / 'job.json').read_bytes()) == p.summary_job_binding(manifest, manifest_sha)
              and json.loads((output / 'collector-binding.json').read_bytes()) == collector_binding(manifest, manifest_sha, collector_sha)
              and (output / 'frozen-manifest.json').read_bytes() == raw_manifest, 'Existing summary collector job binding differs')
    p.require(json.loads((output / 'account-binding.json').read_bytes()) == p.generation.expected_account_binding(manifest), 'Secondary account binding differs')


def verify_sample(sample, row, manifest, manifest_sha, frozen, subset, receipts, binding):
    p.require((sample / 'terminal.json').is_file(), 'Occupied summary attempt is unresolved; no resend')
    terminal_raw = (sample / 'terminal.json').read_bytes(); terminal = json.loads(terminal_raw)
    p.require(terminal['manifest_sha256'] == manifest_sha and terminal['logical_sample_id'] == row['logical_sample_id']
              and terminal['no_resend'] is True and terminal['collector_binding_sha256'] == p.digest(p.canonical(binding)), 'Terminal summary identity differs')
    if terminal['state'] == 'unadmitted_no_resend':
        for relative, meta in terminal['retained_artifacts'].items(): pinned(sample, relative, meta)
        return terminal, None
    p.require(terminal['state'] in ('accepted_generation', 'generation_rejected'), 'Unknown summary terminal state; no resend')
    raw_records = {n: (sample / (n + '.json')).read_bytes() for n in ('condition','attempt-started','native-result','response','validation')}
    p.require(all(p.digest(v) == terminal[n + '_sha256'] for n,v in raw_records.items()) and json.loads(raw_records['condition']) == row, 'Settled summary evidence differs')
    started = json.loads(raw_records['attempt-started'])
    p.require(started['attempt'] == 1 and started['no_resend'] is True and started['attempt_id'] == terminal['attempt_id']
              and started['manifest_sha256'] == manifest_sha and started['logical_sample_id'] == row['logical_sample_id']
              and started['prompt_sha256'] == row['prompt_sha256'] and started['schema_sha256'] == row['schema_sha256']
              and started['collector_binding_sha256'] == terminal['collector_binding_sha256'], 'Summary attempt identity differs')
    account_raw = (sample.parent / 'account-binding.json').read_bytes()
    p.require(p.digest(account_raw) == started['account_binding_sha256']
              and json.loads(account_raw) == p.generation.expected_account_binding(manifest), 'Summary attempt account differs')
    prompt, schema, source, units = inputs(frozen, manifest, row)
    p.require((sample / 'prompt.txt').read_bytes() == prompt and (sample / 'schema.json').read_bytes() == schema
              and (sample / 'source.txt').read_bytes() == source and (sample / 'source-units.json').read_bytes() == p.canonical(units), 'Exact summary source/prompt/schema snapshots differ')
    provider = json.loads(raw_records['native-result'])
    final_raw = p.base.within(sample, provider['provider_artifacts']['codex_message']['path']).read_bytes()
    receipts.verify(sample, provider, prompt=prompt.decode('utf-8'), model=manifest['runtime']['model'], reasoning=manifest['runtime']['reasoning'], final_raw=final_raw)
    events = p.base.within(sample, provider['provider_artifacts']['codex_events']['path']).read_bytes()
    native_id, _ = receipts.event_identity(events, final_raw)
    p.require(native_id == terminal['native_thread_id'], 'Own native summary identity differs')
    answer = json.loads(raw_records['response']); p.require(answer == json.loads(final_raw), 'Summary response differs from native final')
    try:
        validation = p.validate_summary(row, answer, json.loads(schema), subset)
    except ValueError as error:
        p.require(terminal['state'] == 'generation_rejected' and json.loads(raw_records['validation']) == rejected_validation(error), 'Summary rejection admission differs')
        return terminal, None
    p.require(terminal['state'] == SETTLED and json.loads(raw_records['validation']) == validation, 'Summary generation admission differs')
    derived = terminal['derived_summary']
    p.require(pinned(sample, derived['path'], derived) == answer['summary_text'].encode('utf-8'), 'Derived summary text differs')
    return terminal, answer


def rejected_validation(error):
    return {'accepted_generation': False, 'oracle_accepted': False, 'summary_semantically_verified': False,
            'reason': str(error)}


def note_stop(output, row=None):
    path = output / 'stop-observed.json'
    if not path.exists(): record(path, {'observed_at': now(), 'work_id': row['work_id'] if row else None,
                                       'behavior': 'prevent_new_contact; current bounded attempt settles'})


def collect_one(row, manifest, manifest_sha, frozen, output, call_codex, subset, receipts, binding):
    sample = sample_path(output, row); sample.mkdir(exist_ok=False)
    prompt, schema, source, units = inputs(frozen, manifest, row)
    record(sample / 'condition.json', row)
    for name, raw in [('prompt.txt', prompt), ('schema.json', schema), ('source.txt', source), ('source-units.json', p.canonical(units))]:
        p.base.write_new(sample / name, raw)
    attempt_id = str(uuid.uuid4())
    terminal = {'schema_version': 1, 'manifest_sha256': manifest_sha, 'logical_sample_id': row['logical_sample_id'],
        'attempt_id': attempt_id, 'no_resend': True, 'collector_binding_sha256': p.digest(p.canonical(binding)),
        'oracle_accepted': False, 'summary_semantically_verified': False}
    def before_contact():
        if (output / 'STOP').exists():
            note_stop(output, row); raise RuntimeError('Stop observed before native dispatch')
        record(sample / 'attempt-started.json', {'started_at': now(), 'attempt': 1, 'attempt_id': attempt_id,
            'manifest_sha256': manifest_sha, 'logical_sample_id': row['logical_sample_id'], 'no_resend': True,
            'prompt_sha256': row['prompt_sha256'], 'schema_sha256': row['schema_sha256'],
            'collector_binding_sha256': terminal['collector_binding_sha256'],
            'account_binding_sha256': p.digest((output / 'account-binding.json').read_bytes()), 'physical_contact_proven': False})
    try:
        content, provider = call_codex(executable=manifest['external_pins']['cli_path_local_only'], model=manifest['runtime']['model'],
            reasoning=manifest['runtime']['reasoning'], prompt=prompt.decode('utf-8'), output_dir=sample, response_schema=sample / 'schema.json',
            batch_number=1, attempt_number=1, timeout=900, before_provider_attempt=before_contact, codex_receipt_policy='codex_native_rollout_v1')
        record(sample / 'native-result.json', provider)
        final_raw = p.base.within(sample, provider['provider_artifacts']['codex_message']['path']).read_bytes()
        receipts.verify(sample, provider, prompt=prompt.decode('utf-8'), model=manifest['runtime']['model'], reasoning=manifest['runtime']['reasoning'], final_raw=final_raw)
        events = p.base.within(sample, provider['provider_artifacts']['codex_events']['path']).read_bytes()
        native_id, _ = receipts.event_identity(events, final_raw); terminal['native_thread_id'] = native_id
        for previous in output.glob('*/terminal.json'):
            p.require(json.loads(previous.read_bytes()).get('native_thread_id') != native_id, 'Duplicate own native summary identity')
        answer = json.loads(final_raw); p.require(answer == json.loads(content), 'Returned content differs from own native final')
        record(sample / 'response.json', answer)
        try:
            validation = p.validate_summary(row, answer, json.loads(schema), subset)
        except ValueError as error:
            validation = rejected_validation(error)
        record(sample / 'validation.json', validation)
        terminal['state'] = SETTLED if validation['accepted_generation'] else 'generation_rejected'
        if validation['accepted_generation']:
            summary_raw = answer['summary_text'].encode('utf-8'); p.base.write_new(sample / 'summary.txt', summary_raw)
            terminal['derived_summary'] = p.metadata('summary.txt', summary_raw)
        for name in ('condition','attempt-started','native-result','response','validation'):
            terminal[name + '_sha256'] = p.digest((sample / (name + '.json')).read_bytes())
    except BaseException as error:
        terminal.update(state='unadmitted_no_resend', error_class=type(error).__name__, started=(sample / 'attempt-started.json').exists())
        if getattr(error, 'provider_record', None) is not None: terminal['provider_record'] = error.provider_record
        terminal['retained_artifacts'] = {path.relative_to(sample).as_posix(): p.metadata(path.relative_to(sample).as_posix(), path.read_bytes())
                                          for path in sample.rglob('*') if path.is_file()}
        record(sample / 'terminal.json', terminal)
        if (output / 'STOP').exists(): note_stop(output, row)
        if not isinstance(error, Exception): raise
        return False
    record(sample / 'terminal.json', terminal)
    if (output / 'STOP').exists(): note_stop(output, row)
    return terminal['state'] == SETTLED


def receipt_wrapper(manifest_path, output, manifest, manifest_sha, frozen, subset, receipts, binding):
    entries, native_ids = [], set()
    for row in manifest['requests']:
        sample = sample_path(output, row)
        terminal, answer = verify_sample(sample, row, manifest, manifest_sha, frozen, subset, receipts, binding)
        p.require(answer is not None and terminal['state'] == SETTLED, 'Both source summaries must be accepted before wrapper emission')
        p.require(terminal['native_thread_id'] not in native_ids, 'Duplicate native source summary identity'); native_ids.add(terminal['native_thread_id'])
        entries.append({'work_id': row['work_id'], 'logical_sample_id': row['logical_sample_id'], 'sample_path': str(sample.resolve()),
            'source_narrative_sha256': row['source']['sha256'], 'native_thread_id': terminal['native_thread_id'],
            'summary': terminal['derived_summary'], 'terminal_sha256': p.digest((sample / 'terminal.json').read_bytes()),
            'native_result_sha256': terminal['native-result_sha256'], 'response_sha256': terminal['response_sha256']})
    return {'schema_version': 1, 'policy': 'longform_source_summary_receipts_v1',
            'generation_manifest': {'path': str(manifest_path.resolve()), 'sha256': manifest_sha},
            'prior_runtime_manifest_file_sha256': manifest['source_generation_manifest_file_sha256'],
            'generation_manifest_snapshot': p.metadata('frozen-manifest.json', (output / 'frozen-manifest.json').read_bytes()),
            'prior_runtime_manifest': p.metadata(str((frozen / 'private/source-generation-manifest.json').resolve()),
                                               (frozen / 'private/source-generation-manifest.json').read_bytes()),
            'collector_binding': p.metadata('collector-binding.json', (output / 'collector-binding.json').read_bytes()),
            'job': p.metadata('job.json', (output / 'job.json').read_bytes()),
            'account_binding': p.metadata('account-binding.json', (output / 'account-binding.json').read_bytes()),
            'collector_policy': POLICY, 'collector_sha256': binding['collector_sha256'],
            'summary_semantically_verified': False, 'oracle_accepted': False, 'summaries': entries}


def publish_wrapper(path, value):
    raw = p.canonical(value)
    if path.exists(): p.require(path.read_bytes() == raw, 'Existing summary receipt wrapper differs')
    else: p.base.write_new(path, raw)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--manifest-sha256', required=True)
    parser.add_argument('--collector-sha256', required=True)
    parser.add_argument('--results-dir', type=Path, required=True)
    parser.add_argument('--validate-only', action='store_true')
    args = parser.parse_args()
    manifest, frozen, subset, receipts = load_manifest(args.manifest, args.manifest_sha256, args.collector_sha256)
    output = args.results_dir.resolve(); p.generation.output_preflight(output, frozen)
    raw_manifest = args.manifest.read_bytes(); binding = collector_binding(manifest, args.manifest_sha256, args.collector_sha256)
    pending, states, native_ids = [], [], set()
    if output.exists(): verify_job(output, manifest, args.manifest_sha256, args.collector_sha256, raw_manifest)
    for row in manifest['requests']:
        sample = sample_path(output, row)
        if not sample.exists(): pending.append(row); continue
        terminal, _ = verify_sample(sample, row, manifest, args.manifest_sha256, frozen, subset, receipts, binding)
        states.append(terminal['state'])
        if terminal.get('native_thread_id') is not None:
            p.require(terminal['native_thread_id'] not in native_ids, 'Duplicate native summary identity'); native_ids.add(terminal['native_thread_id'])
    if args.validate_only:
        print(json.dumps({'state': 'provider_free_validated', 'manifest_sha256': args.manifest_sha256,
            'planned': 2, 'untouched': len(pending), 'terminal_states': states, 'provider_calls': 0,
            'summary_semantically_verified': False, 'oracle_accepted': False}, sort_keys=True)); return 0
    p.require(all(state == SETTLED for state in states), 'Unadmitted/rejected occupied summary slot requires reconciliation; no resend')
    if pending:
        if (output / 'STOP').exists(): note_stop(output); return 3
        helper = p.load('p4_summary_secondary_helper', Path(manifest['external_pins']['secondary_helper_path_local_only']))
        env = p.generation.secondary_environment(manifest, helper); os.environ.clear(); os.environ.update(env)
        sys.path.insert(0, manifest['external_pins']['tools_root_local_only'])
        from adaptive_settings.account_probe import probe
        sys.path.insert(0, str(p.REPO / 'src'))
        from hbqrs import runner
        _, account = p.generation.secondary_binding(manifest, helper, probe(helper.CLI))
        if not output.exists():
            output.mkdir(parents=True, exist_ok=False)
            record(output / 'job.json', p.summary_job_binding(manifest, args.manifest_sha256))
            record(output / 'collector-binding.json', binding)
            p.base.write_new(output / 'frozen-manifest.json', raw_manifest)
            record(output / 'account-binding.json', account)
        else: p.require(json.loads((output / 'account-binding.json').read_bytes()) == account, 'Live secondary account changed')
        for row in pending:
            if (output / 'STOP').exists(): note_stop(output, row); return 3
            if not collect_one(row, manifest, args.manifest_sha256, frozen, output, runner._call_codex, subset, receipts, binding):
                print(json.dumps({'state': 'summary_stopped_no_resend', 'work_id': row['work_id']}), flush=True); return 3
            print(json.dumps({'state': SETTLED, 'work_id': row['work_id'], 'summary_semantically_verified': False}), flush=True)
    wrapper = receipt_wrapper(args.manifest, output, manifest, args.manifest_sha256, frozen, subset, receipts, binding)
    publish_wrapper(output / 'summary-receipts.json', wrapper)
    print(json.dumps({'state': 'two_source_summaries_receipt_bound', 'accepted_generation': 2,
                      'oracle_accepted': False, 'summary_semantically_verified': False})); return 0


if __name__ == '__main__':
    raise SystemExit(main())
