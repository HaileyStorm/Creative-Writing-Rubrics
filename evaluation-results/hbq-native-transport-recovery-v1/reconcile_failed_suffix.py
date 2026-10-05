"""Zero-call saved decode-retry descendants for three exact failed Grok suffix slots."""
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
SESSIONS = Path(r'C:\Users\Haile\.grok\sessions')
POLICY = 'saved_grok_decode_retry_completed_projection_v1'
LAMP_POLICY = 'saved_grok_observed_decode_stream_completed_projection_v1'
DECODE = 'reqwest error stream: Transport error: error decoding response body'
CODE = {
    'generic': ('reconcile.py', 'fbedc8e50d08de7dff0547483f26c9fd081a8b4c9e62f0713609ce043e0fb34c'),
    'suffix': ('continue_failed_transport.py', 'c9079969a868f0800ef22e681d4304424af9c738ed514755f3a3aaf968fa243e'),
    'history': ('../hbq-matched-ttcw-20261004/reconcile_history.py', 'a9e27d3c5da5ff341f0f7172d7dfffd6c139fe8f569b2655e55fbf7279c676ed'),
    'p1': ('../hbq-semantic-crossform-p1b-matched-v1/collector.py', '71e4a5e1a21ff45338796b060fadde638367067da922786e0a810eec42e8feaa'),
    'mfa': ('../hbq-matched-mfa-v1/collector.py', 'a4a7073ff5d24875fcc1d866b727792ebdafa4ad70df327691a72e17cbcacc94'),
    'context': ('../hbq-matched-mfa-v1/context_reconciliation.py', '39ee7b9d54a16fa2384c68466c181a2e23d8f645f2ed09d17edd2e377bc54e35'),
}
STUDIES = {
    'semantic-crossform': {'manifest': 'matched-frozen-002', 'manifest_sha': '4e139dc1ef859be838cbe9ee8c579285845074032c6a00867a1b03859fdec2ff',
        'plan_sha': '1d8b0b917aab8ceda558445e4a87a35c44b2d69ad027a125f543bbe6f45b063f',
        'job_sha': 'c3b0f80a3a945efb364ab9c7a12494f592ff33e5d68f0d11feec1ed8c42c2a3f', 'denominator': 1584},
    'mfa-canary': {'manifest': 'frozen-001', 'manifest_sha': 'ce8a735c40a18c676c82cc0585b36f91cbb6a9faa98ac2289f86fdfb52cadd80',
        'plan_sha': '3ea8e9d5ffaf7fed58bf71304460ca70c69338883807efbc88df937ef25645ff',
        'job_sha': 'c1180d6ccb9f2b1d24229bc8bd92c2cb40f4c58606975e22c37a24f32fd1013e', 'denominator': 868},
}
OBSERVATIONS = (
    {'study': 'semantic-crossform', 'slot': '0175-91472977f77f', 'session': 'ed05080f-66eb-4444-bc08-8a79290fed43', 'leaf': 'grok-exec-5y1lmaqr',
     'updates': '12d735aa83f2be5b03b2f705f5d9576ec854e667741b1717ddd28793bb68a101', 'summary': '2c7e63a3d3d86aaefefccb7afe0bc3c4b9a326e846e978ff1bc4e09b29e68f91',
     'signals': '7e703da84306f7b8617b2aa32fb5d2373b5c4674588abeb839b259dd85de8758', 'terminal': '8bfd1f002ba6a5310b255722bb011933e03bd7092d7c5c36521052d508daef83',
     'response': 'aa33a20d5ff3eee57110f56f7c144a7e87ab96c930ef4baa9c0826ba0ec5d1f6', 'projection': 'e45f503ac686c7fa43634cbe7a537425c79b883c9202155dff6f13069d4abe41',
     'condition': 'cfb420b0fa0b715e982d58bb404aef0ee496567cc0f1c226353aa379ce759813', 'started': 'f99d0521349bbb8c713bd89603ecb3f7ca02fbaab41d44131b3619547c3d9938',
     'identity': 'c43017c6dde704810d3af2d5375e900731c19bd665cf9fc0a3cfdd74ae25b2ba', 'native-result': 'dc6565defcb63ebfa63c1ef5e999577e208056ab643bdf416a95009b9b03742d'},
    {'study': 'semantic-crossform', 'slot': '0176-1bbaa1e8b076', 'session': '804902e1-16de-4f9d-89df-4d0ec3c43874', 'leaf': 'grok-exec-453bvtwj',
     'updates': 'b54b9a8f41a43714392791bb455b5f016f09a4a65c100f5f0da4e0aeb2541bd9', 'summary': 'dfd68d2c76f2938a98165b7db6dcb5f11ba9900e76d7eebae554b1e6e58b076f',
     'signals': 'fa91cb954bccfd5e87cfb3aa558bd4cd47c8a76d5d0024174b73e1618f51a7b8', 'terminal': 'abd188e4512a0d4e79abace0c4bfb232c6b208bdc3e09a6737d25fd45cf54186',
     'response': '3a2969a06ef2765ded9f5936ccda4604d65f1a38bbf65de3c21cb0ae0e2ade38', 'projection': 'ba50fd9e9930aa40e7fc1f01f542e9da98acd5e1c60dcc48192313c6d576ef3d',
     'condition': '6663be1cc7a33df52951e64655af9adce734f687b9dcbaad3d42d6721896f9ff', 'started': '0b211b060784e01761d3144a3cc3e6c24b424a200eca8155fbdb168045a779f5',
     'identity': 'ec19f62402da7cf0e31f6c0b696d7ae90f1633a4e60c3abdd3bebc22c8a5d61e', 'native-result': 'dc6565defcb63ebfa63c1ef5e999577e208056ab643bdf416a95009b9b03742d'},
    {'study': 'mfa-canary', 'slot': '0142-85e9052865ea', 'session': 'c65f3feb-a22f-4596-ae32-d9e90e9690f4', 'leaf': 'grok-exec-176egcy5',
     'updates': 'e4e6bc64902a3f093845f2109cacf46432fd472168c0831bcb5de19d6386aa79', 'summary': '7bd70e6646437272e2eb0532cac42709923362a43d92eaac7fd6434e9428fc32',
     'signals': '01902b2894a2e2f50dd6eba1071fb923cf5d995bb4771686c504eff283abbbe7', 'terminal': '7e841884e6dc14b5fe7343bfd8b9166dff198a7780fd485107b524c97c560207',
     'response': '2b3da2e9b4222be2a4640fd3b42641f12c60c0afd36abb573f0179ff4c6ebdce', 'projection': '346b2c226e1ee8511e3b83c2eb9b16462eb1a3fd5a4b034ab5325154d9ae36db',
     'condition': '891ef824a93977cbf8f63f964a03ff8c9de11f970c03b69636416ae94236cbb9', 'started': '182c57728336251a8249293f1a3d04006d221835a06ff89b359cd29f98ceec6c',
     'identity': '0a8d68a0cbb7d288bdabf5becf2ebd5862e7e854c52b7cf105b945b4c4d1d59b', 'native-result': 'ccf48ff7a508db048959ee50ca2c4852f5f3a8eee37e9683d7316a3755f555d7'},
)


def digest(raw): return hashlib.sha256(raw).hexdigest()
def canonical(value): return (json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False) + '\n').encode()
def require(ok, message):
    if not ok: raise ValueError(message)


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec); sys.modules[name] = module
    spec.loader.exec_module(module); return module


def decode_projection(original, updates, summary, session, prompt):
    try:
        original(updates, summary, session, prompt)
    except ValueError as error:
        require(str(error) == 'No demonstrated Grok DNS recovery', 'Decode projection rejected generic field/lifecycle validation')
    else: raise ValueError('Decode-only projection cannot adopt generic DNS recovery')
    require(len(updates) == 5 and [row['params']['update']['sessionUpdate'] for row in updates]
            == ['user_message_chunk', 'retry_state', 'agent_thought_chunk', 'agent_message_chunk', 'turn_completed'],
            'Decode projection needs the exact five-record lifecycle')
    diagnostic = updates[1]
    require(diagnostic['params']['update'] == {'sessionUpdate': 'retry_state', 'type': 'retrying', 'attempt': 1,
            'max_retries': 15, 'reason': DECODE, 'error_type': 'http'}, 'Not the exact single decode retry diagnostic')
    return [updates[0], *updates[2:]], [{'record_sha256': digest(canonical(diagnostic)), 'reason': DECODE, 'attempt': 1}]


def observed_decode_stream_projection(original, updates, summary, session, prompt):
    """Validate original subsequences without changing any native row or diagnostic."""
    kinds = [row['params']['update']['sessionUpdate'] for row in updates]
    supported = [['user_message_chunk', *(['retry_state'] * n), 'agent_thought_chunk', 'agent_message_chunk', 'turn_completed']
                 for n in (1, 2, 3)]
    supported.append(['user_message_chunk', 'agent_thought_chunk', 'retry_state', 'agent_message_chunk',
                      'retry_state', 'agent_thought_chunk', 'agent_message_chunk', 'turn_completed'])
    require(kinds in supported, 'Unobserved decode stream lifecycle')
    retry = [row for row in updates if row['params']['update']['sessionUpdate'] == 'retry_state']
    kept = [row for row in updates if row['params']['update']['sessionUpdate'] != 'retry_state']
    for rows in (kept, [updates[0], *retry]):
        try: original(rows, summary, session, prompt)
        except ValueError as error:
            require(str(error) == 'No demonstrated Grok DNS recovery', 'Observed stream rejected generic field/lifecycle validation')
        else: raise ValueError('Observed decode stream cannot adopt generic DNS recovery')
    diagnostics = []
    for n, row in enumerate(retry, 1):
        require(row['params']['update'] == {'sessionUpdate': 'retry_state', 'type': 'retrying', 'attempt': n,
                'max_retries': 15, 'reason': DECODE, 'error_type': 'http'}, 'Unknown observed decode stream retry')
        diagnostics.append({'record_sha256': digest(canonical(row)), 'reason': DECODE, 'attempt': n})
    ids = [row['params']['_meta']['eventId'] for row in updates]
    require(len(ids) == len(set(ids)), 'Duplicate event across saved stream subsequences')
    times = [original.__globals__['timestamp'](row['timestamp']) for row in updates]
    require(times == sorted(times), 'Saved stream cross-subsequence order differs')
    return kept, diagnostics


def saved_completion(sample, prompt, session_root, started, job, *, snapshot=None, commitments=None, profile=POLICY):
    """Read one explicit own saved session; the caller binds source and semantic admission."""
    require(isinstance(prompt, bytes), 'Exact frozen prompt must be bytes')
    for key in ('generic', 'history'):
        relative, sha = CODE[key]
        require(digest((HERE / relative).read_bytes()) == sha, 'Frozen native reader differs')
    r = load('decode_saved_completion_private_generic', HERE / CODE['generic'][0])
    original = r.grok_projection
    require(profile in {POLICY, LAMP_POLICY}, 'Unknown saved decode recipient policy')
    project = decode_projection if profile == POLICY else observed_decode_stream_projection
    r.grok_projection = lambda updates, summary, session, text: project(original, updates, summary, session, text)
    class Reads(r.ReadSet):
        def raw(self, name, path):
            require(self.snapshot is None or name in self.expected, 'Frozen snapshot commitment missing')
            return super().raw(name, path)
    reads = Reads(snapshot, commitments)
    response, native = r.recover_grok(reads, sample, prompt.decode('utf-8'), session_root, started, job)
    reads.paths['updates_projection'] = 'derived:' + profile
    if snapshot is not None:
        pin = reads.expected.get('updates_projection')
        require(pin is not None and digest(reads.raws['updates_projection']) == pin['sha256']
                and len(reads.raws['updates_projection']) == pin['bytes']
                and (snapshot / pin['snapshot']).read_bytes() == reads.raws['updates_projection'],
                'Saved decode projection commitment differs')
    native.update(policy=profile, original_strict_v5_admission_satisfied=False)
    return response, native, reads


def fresh_output(output, protected):
    output = output.resolve()
    require(not output.exists() and all(not output.is_relative_to(path.resolve()) and not path.resolve().is_relative_to(output)
            for path in protected), 'Private descendant output must be fresh and outside retained inputs')
    return output


def reconcile(program, sessions, *, snapshot=None, commitments=None):
    require(program.resolve() == PROGRAM.resolve() and sessions.resolve() == SESSIONS.resolve(), 'Only the three fixed source observations are supported')
    for relative, sha in CODE.values(): require(digest((HERE / relative).read_bytes()) == sha, 'Frozen source implementation differs')
    r = load('decode_suffix_private_generic', HERE / CODE['generic'][0])
    original = r.grok_projection
    r.grok_projection = lambda updates, summary, session, prompt: decode_projection(original, updates, summary, session, prompt)
    suffix = load('decode_suffix_private_executor', HERE / CODE['suffix'][0])
    class Reads(r.ReadSet):
        def raw(self, name, path):
            require(self.snapshot is None or name in self.expected, 'Frozen snapshot commitment missing')
            return super().raw(name, path)
    reads = Reads(snapshot, commitments)
    def raw(name, path, sha=None):
        data = reads.raw(name, path); require(sha is None or digest(data) == sha, 'Pinned source differs: ' + name); return data
    entries = []; responses = {}; acceptances = {}
    for study, pin in STUDIES.items():
        prefix = study + '/'; source = program / study / 'judging-grok-failed-transport-001'; root = program / study / pin['manifest']
        job = json.loads(raw(prefix + 'job', source / 'job.json', pin['job_sha']))
        plan = json.loads(raw(prefix + 'plan', program / study / 'failed-transport-grok-plan-001/plan.json', pin['plan_sha']))
        require(job == suffix.job_binding(plan, pin['plan_sha'], job['workers'], job['route'], job['execution_route_sha256']), 'Exact suffix execution binding differs')
        manifest = json.loads(raw(prefix + 'manifest', root / 'manifest.json', pin['manifest_sha']))
        require(len(manifest['requests']) == pin['denominator'] and
                (manifest['labels_read'] is False if study == 'mfa-canary' else
                 manifest['human_alignment_claim'] is False and manifest['fixed_synthetic_labels'] is False),
                'Full source denominator/label boundary differs')
        module = load('decode_suffix_private_p1', HERE / CODE['p1'][0]) if study == 'semantic-crossform' else None
        context = None
        if module is None:
            context = load('decode_suffix_private_mfa_context', HERE / CODE['context'][0]); module = context.old
        for name in ('schema_subset.py', 'validate_response.py', 'runner.py'):
            raw(prefix + 'implementation/' + name, root / 'implementation' / name,
                manifest['artifacts']['implementation/' + name]['sha256'])
        subset = load('decode_suffix_subset_' + study, root / 'implementation/schema_subset.py')
        validator = load('decode_suffix_validator_' + study, root / 'implementation/validate_response.py')
        if context: validator = context.admission(root, manifest, validator, context.frozen_runner(root, manifest))
        for observation in (v for v in OBSERVATIONS if v['study'] == study):
            sample = source / observation['slot']; key = study + '/' + observation['slot'] + '/'
            row = json.loads(raw(key + 'condition', sample / 'condition.json', observation['condition']))
            require(row in manifest['requests'] and module.sample_path(source, row) == sample
                    and row['endpoint'] == 'grok' and row['endpoint_ordinal'] > plan['reserved_through']
                    and digest(canonical({k: v for k, v in row.items() if k != 'request_sha256'})) == row['request_sha256'], 'Exact original source condition differs')
            terminal = json.loads(raw(key + 'terminal', sample / 'terminal.json', observation['terminal']))
            failure = json.loads(raw(key + 'native-result', sample / 'native-result.json', observation['native-result']))
            require(terminal['state'] == failure['state'] == 'ambiguous' and failure['result'] is None and terminal['no_resend'] is True
                    and terminal['logical_sample_id'] == row['logical_sample_id'] and terminal['manifest_sha256'] == pin['manifest_sha']
                    and not (sample / 'native-envelope.json').exists(), 'Original source ambiguity/envelope boundary differs')
            require(failure['failure']['code'] == ('validation_tool_policy_attestation' if study == 'semantic-crossform' else 'unclassified_after_launch'),
                    'Source failure is outside the fixed observation contract')
            started = json.loads(raw(key + 'started', sample / 'attempt-started.json', observation['started']))
            identity = json.loads(raw(key + 'identity', sample / 'native-identity.json', observation['identity']))
            require(identity == {'logical_sample_id': row['logical_sample_id'], 'session_id': observation['session']}
                    and started['session_id'] == observation['session'], 'Exact own native identity differs')
            _, prompt, schema, texts, task_context = r.validate_started(module, sample, row, job, pin['manifest_sha'], root, manifest)
            for name in ('prompt.txt', 'schema.json'):
                raw(key + name, sample / name, row['prompt_sha256'] if name == 'prompt.txt' else row['schema_sha256'])
            for name in {row['prompt_path'], row['schema_path'], *(item['input_path'] for item in row['sources']),
                         *([row['task_context']['path']] if 'task_context' in row else ['context.txt']),
                         *([row['shared_work_context']['path']] if 'shared_work_context' in row else []),
                         *([row['task_contract_path']] if 'task_contract_path' in row else [])}:
                raw(prefix + 'input/' + name, root / name, manifest['artifacts'][name]['sha256'])
            encoded = 'C%3A%5CUsers%5CHaile%5C.codex%5Cstate%5Cmodel-work-queue-cwr-placeholder-r31%5C' + observation['leaf']
            session_root = sessions / encoded / observation['session']
            class NativeReads:
                def raw(self, name, path): return raw(key + 'native/' + name, path, observation.get(name))
                @property
                def raws(self): return local.raws
                @property
                def paths(self): return local.paths
            local = r.ReadSet()
            # The generic reader keeps its local names; all actual raw reads remain in the shared pinned snapshot.
            native_reads = NativeReads()
            response, native = r.recover_grok(native_reads, sample, prompt.decode(), session_root, started, job)
            projection = local.raws['updates_projection']
            require(digest(projection) == observation['projection'], 'Exact decode projection differs')
            chat = [json.loads(v) for v in reads.raws[key + 'native/chat'].splitlines()]
            assistants = [v for v in chat if v.get('type') == 'assistant']; require(len(assistants) == 1, 'Duplicate saved assistant')
            response_raw = assistants[0]['content'].encode(); require(digest(response_raw) == observation['response'] and json.loads(response_raw) == response, 'Exact saved final differs')
            reads.raws[key + 'native/updates_projection'] = projection
            reads.paths[key + 'native/updates_projection'] = 'derived:validated_single_decode_retry_completed_projection_v1'
            native.update(policy=POLICY, source_failure_preserved=True, original_strict_v5_admission_satisfied=False)
            subset.validate_schema(json.loads(schema))
            accepted = validator.semantic_validate(row['arm'], response, row, texts, subset, context=task_context, schema=json.loads(schema))
            responses[key] = response_raw; acceptances[key] = canonical(accepted)
            entries.append({'study': study, 'slot': observation['slot'], 'endpoint': 'grok', 'endpoint_ordinal': row['endpoint_ordinal'],
                'logical_sample_id': row['logical_sample_id'], 'request_sha256': row['request_sha256'], 'source_job_sha256': pin['job_sha'],
                'source_terminal_sha256': observation['terminal'], 'original_state': 'ambiguous', 'native': native,
                'state': 'accepted' if accepted['accepted'] else 'semantic_rejected', 'admission': accepted,
                'response_sha256': digest(response_raw), 'acceptance_sha256': digest(canonical(accepted)),
                'same_original_observation_only': True, 'new_votes': 0, 'no_resend': True})
    require(len(entries) == len({(v['study'], v['logical_sample_id']) for v in entries}) == 3, 'Duplicate or widened observation set')
    receipt = {'schema_version': 1, 'policy': POLICY, 'implementation_sha256': digest(Path(__file__).read_bytes()),
        'program_root_local_only': str(program.resolve()), 'sessions_root_local_only': str(sessions.resolve()), 'observations': entries,
        'source_commitments': reads.commitments(), 'full_planned_denominators': {'semantic-crossform': 1584, 'mfa-canary': 868},
        'provider_calls': 0, 'new_votes': 0, 'human_labels_opened': False, 'human_release_eligible': False,
        'original_native_envelopes_reconstructed': False, 'physical_contact_cardinality_proven': False}
    return receipt, reads, responses, acceptances


def verify(path, expected_sha):
    saved = json.loads(raw := path.read_bytes()); require(digest(raw) == expected_sha, 'Exact saved descendant differs')
    require(digest((path.parent / 'reconcile_failed_suffix.py').read_bytes()) == saved['implementation_sha256'], 'Saved implementation differs')
    for pin in saved['source_commitments'].values():
        retained = (path.parent / pin['snapshot']).read_bytes()
        require(digest(retained) == pin['sha256'] and len(retained) == pin['bytes'], 'Saved raw/projection snapshot differs')
    actual, _, responses, acceptances = reconcile(Path(saved['program_root_local_only']), Path(saved['sessions_root_local_only']),
                                                 snapshot=path.parent, commitments=saved['source_commitments'])
    require(actual == saved, 'Saved projection/admission replay differs')
    for key, content in responses.items():
        require((path.parent / 'responses' / key / 'response.json').read_bytes() == content
                and (path.parent / 'responses' / key / 'acceptance.json').read_bytes() == acceptances[key], 'Saved response/admission differs')
    for name, pin in saved['source_commitments'].items():
        if not pin['source_locator_local_only'].startswith('derived:'):
            source = Path(pin['source_locator_local_only']).read_bytes()
            require(digest(source) == pin['sha256'] and len(source) == pin['bytes'], 'Original source bytes changed')
    return actual


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--program-root', type=Path, default=PROGRAM); parser.add_argument('--grok-sessions-root', type=Path, default=SESSIONS)
    parser.add_argument('--output-root', type=Path, required=True); parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    # The named recipient lives beside P1 evidence, while remaining outside every retained child input tree.
    protected = [REPO, args.grok_sessions_root, *(args.program_root / name / child for name in STUDIES
        for child in ('judging-grok-failed-transport-001', 'failed-transport-grok-plan-001', STUDIES[name]['manifest']))]
    output = fresh_output(args.output_root, protected)
    receipt, reads, responses, acceptances = reconcile(args.program_root, args.grok_sessions_root)
    result = canonical(receipt)
    if not args.dry_run:
        output.mkdir(parents=True, exist_ok=False)
        for name, content in reads.raws.items():
            pin = receipt['source_commitments'][name]
            if not pin['source_locator_local_only'].startswith('derived:'):
                require(Path(pin['source_locator_local_only']).read_bytes() == content, 'Original source changed before snapshot')
            path = output / pin['snapshot']; path.parent.mkdir(parents=True, exist_ok=True)
            with path.open('xb') as handle: handle.write(content)
        for key, content in responses.items():
            path = output / 'responses' / key / 'response.json'; path.parent.mkdir(parents=True, exist_ok=True)
            with path.open('xb') as handle: handle.write(content)
            with (path.parent / 'acceptance.json').open('xb') as handle: handle.write(acceptances[key])
        for name, content in [('reconcile_failed_suffix.py', Path(__file__).read_bytes()), ('reconciliation.json', result),
                              ('terminal.json', canonical({'state': 'completed_saved_projection', 'policy': POLICY, 'receipt_sha256': digest(result), 'no_resend': True}))]:
            with (output / name).open('xb') as handle: handle.write(content)
    print(json.dumps({'policy': POLICY, 'receipt_sha256': digest(result), 'observations': 3,
        'accepted': sum(v['admission']['accepted'] for v in receipt['observations']),
        'semantic_error_count': sum(len(v['admission'].get('errors', [])) for v in receipt['observations']),
        'snapshot_files': len(reads.raws), 'provider_calls': 0, 'new_votes': 0, 'human_labels_opened': False, 'output_written': not args.dry_run}, sort_keys=True))


if __name__ == '__main__': raise SystemExit(main())
