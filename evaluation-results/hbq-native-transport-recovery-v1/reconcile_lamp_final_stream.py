"""Fixed-slot zero-call projection of LAMP's canonical saved final stream."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
PROGRAM = Path(r'C:\Users\Haile\Documents\cwr-resume-control-20260919-r1\successor-program-20261004')
SOURCE = PROGRAM / 'lamp-reference/judging-grok-parallel-001'
FROZEN = PROGRAM / 'lamp-reference/frozen-001'
SLOT = '0005-0f2b32c29a39'
SESSION = 'b3db6f5d-3b07-44e5-9dea-dac6c19ccd63'
SESSION_ROOT = Path(r'C:\Users\Haile\.grok\sessions\C%3A%5CUsers%5CHaile%5C.codex%5Cstate%5Cmodel-work-queue-cwr-placeholder-r31%5Cgrok-exec-ppsh6yun') / SESSION
ROUTE_ROOT = Path(r'C:\Users\Haile\.codex\state\model-work-queue-cwr-placeholder-r31')
POLICY = 'saved_canonical_final_stream_projection_v1'
EARLY_SHA = '5562d5d9425b81c5aaefdd003e284ebfc0e3b4b3fcd4f10e5bdd8a8b1c60665a'
FINAL_SHA = 'c1bf6d5e6eb5373efa0a4ebc28569d574cc9c515095cb0f402eeca219d78e7f8'
EARLY_BYTES, FINAL_BYTES = 586, 6127
CODE = {
    'decode': ('reconcile_failed_suffix.py', 'f285d228607c26cca0009d17626e7d6915f3d715e3b29f02784a25c682f4be68'),
    'generic': ('reconcile.py', 'fbedc8e50d08de7dff0547483f26c9fd081a8b4c9e62f0713609ce043e0fb34c'),
    'history': ('../hbq-matched-ttcw-20261004/reconcile_history.py', 'a9e27d3c5da5ff341f0f7172d7dfffd6c139fe8f569b2655e55fbf7279c676ed'),
    'source_project': ('../hbq-matched-lamp-20261004/collector_decode.py', 'f9bd97b14220e50c174930d0938f540e4f566022be786a4f3a4f24d0b568e30a'),
    'collector': ('../hbq-matched-lamp-20261004/collector.py', 'd5a146f0ab615994792f422ef7dc01bac5f7dca9e38ac6c0a4a085c5b8ceb698'),
    'prepare': ('../hbq-matched-lamp-20261004/prepare.py', '1e0cad075cefe4408eb48e4e8b6b2b65f1e541be807683a275537ba8248e4d62'),
    'runner': ('../../src/hbqrs/runner.py', '04a87edb728701afa6a43233a775c032473c82d0f189f209713051025d86f1f7'),
    'receipts': ('../../src/hbqrs/codex_receipts.py', '5d1c7af681e881a77201dee7cece4a14fa11cadc86d119714766492e547e1116'),
}
MANIFEST_SHA = '480aa86df271078e322ac85cf8cfe5fe6ed02344138e218900cfe03c069b6ab6'
JOB_SHA = 'b2699b2a39b2cbd38dc684ed52ecdb87e34ed25a2593eb97101f07f5d7a8bc71'
SOURCE_PINS = {
    'condition.json': '1dea07020d184755b08b036a9498bece16be3a122dc48c282e24a104072e5f84',
    'attempt-started.json': 'a860caf2439b61ae0263f7b327db9a976b854dea760aeccb735c6f75b5761cd4',
    'native-identity.json': 'e46117f129d58a6c1329faad62b9a03e9b59bdc9dfaef2232bf940e16205de8b',
    'native-result.json': 'dc6565defcb63ebfa63c1ef5e999577e208056ab643bdf416a95009b9b03742d',
    'prompt.txt': '9d63cd8a4219c4e12ac618d817f32b35935e11cb772afe879d12679b330ae7ab',
    'schema.json': '38c32cfd67f521d809b98d640b54601483a1e553ee806a87624ce343d8ecd6aa',
    'task-context.json': 'df39d23094f1bdee17be8c3869457c2fda76074ad5ea826796a4cb2b0b469316',
    'terminal.json': '543c6fb1a5d345c3e7f9ac4470ee2670dbbee74b51075d23a9dd25c419610543',
}
NATIVE_PINS = {
    'summary': '9a9a0ea43b8941c3f37479ca36473f70c05ad20d3b21a99c7c21abe3b9c44e69',
    'updates': '0cdefdde351534b4e1fcf6d70ede605e239934679eb82f55dd2db2289d8e32df',
    'chat': '7bbabec8d17423db22cc361d028bc9d0c2bb1e6a1659ca3e358f69bf905c1b23',
    'events': '3239a2546abaf04fa2e4cd0c6f63e5725b3098fc4b76b40719d2cd9afaa33133',
    'signals': '5a2c72c5d94dd83c857e4a5cccb696b771ac49567c2e770d1d3b9b43bad0cc11',
    'prompt_history': 'ce77b10d73267f70f1913cea6731f88ec439215dcac359f04bf861f7bc13e929',
    'tool_definitions': '4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945',
    'usage': '47005ca6c0cbc981f1149db8a7ea9b3dceaf60a003e4c38294e701bcbaf1a2c5',
    'prompt_context': 'c44ac07d9dcfbe842163dd9153254fdb810605a7f9974e3f1aeff6916653c101',
    'system_prompt': 'd8711efa61dbbc48826ea2aa504cb3850f00ffd0ba693b59c4a9bf8a04517405',
}


def digest(raw): return hashlib.sha256(raw).hexdigest()
def canonical(value): return (json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False) + '\n').encode()
def require(ok, message):
    if not ok: raise ValueError(message)


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec); sys.modules[name] = module
    spec.loader.exec_module(module); return module


def final_stream_projection(original, observed, updates, summary, session, prompt, chat):
    _, diagnostics = observed(original, updates, summary, session, prompt)
    require([v['params']['update']['sessionUpdate'] for v in updates] ==
            ['user_message_chunk', 'agent_thought_chunk', 'retry_state', 'agent_message_chunk',
             'retry_state', 'agent_thought_chunk', 'agent_message_chunk', 'turn_completed'], 'Not the fixed two-stream lifecycle')
    require([v['attempt'] for v in diagnostics] == [1, 2], 'Not the two observed decode diagnostics')
    pairs = [(updates[1], updates[3]), (updates[5], updates[6])]
    metadata = [[v['params']['_meta'] for v in pair] for pair in pairs]
    require(all(a['streamStartMs'] == b['streamStartMs'] and a['turnStartMs'] == b['turnStartMs']
                and a['promptId'] == b['promptId'] == summary['request_id']
                and a['agentTimestampMs'] <= b['agentTimestampMs'] for a, b in metadata)
            and metadata[0][0]['streamStartMs'] < metadata[1][0]['streamStartMs']
            and metadata[0][0]['turnStartMs'] == metadata[1][0]['turnStartMs'], 'Own distinct final stream binding differs')
    early, final = [pair[1]['params']['update']['content']['text'].encode() for pair in pairs]
    require(len(early) == EARLY_BYTES and digest(early) == EARLY_SHA
            and len(final) == FINAL_BYTES and digest(final) == FINAL_SHA, 'Exact saved stream bytes differ')
    try: json.loads(early)
    except json.JSONDecodeError: pass
    else: raise ValueError('Earlier stream is a complete alternative; final projection is ineligible')
    require(isinstance(json.loads(final), dict), 'Canonical final is not one structured answer')
    assistants = [v for v in chat if v.get('type') == 'assistant']
    require(len(assistants) == 1 and assistants[0]['content'].encode() == final, 'Canonical saved final is missing or ambiguous')
    return [updates[0], updates[5], updates[6], updates[7]], diagnostics


def reconcile(*, snapshot=None, commitments=None):
    for relative, sha in CODE.values(): require(digest((HERE / relative).read_bytes()) == sha, 'Frozen source implementation differs')
    decode = load('lamp_final_private_decode', HERE / CODE['decode'][0])
    generic = load('lamp_final_private_generic', HERE / CODE['generic'][0])
    source_project = load('lamp_final_private_source_project', HERE / CODE['source_project'][0])
    c = source_project.c
    class Reads(generic.ReadSet):
        def raw(self, name, path):
            require(self.snapshot is None or name in self.expected, 'Frozen snapshot commitment missing')
            if self.snapshot is None and name == 'source/manifest':
                require(path.stat().st_size == 40062500, 'Exact frozen manifest byte bound differs')
                value = path.read_bytes(); self.raws[name], self.paths[name] = value, str(path)
                return value
            return super().raw(name, path)
    reads = Reads(snapshot, commitments)
    def raw(name, path, sha):
        value = reads.raw(name, path); require(digest(value) == sha, 'Pinned source differs: ' + name); return value
    for key, (relative, sha) in CODE.items(): raw('implementation/' + key, HERE / relative, sha)
    job = json.loads(raw('source/job', SOURCE / 'job.json', JOB_SHA))
    manifest_raw = raw('source/manifest', FROZEN / 'manifest.json', MANIFEST_SHA)
    require((SOURCE / 'frozen-manifest.json').read_bytes() == manifest_raw, 'Original job raw manifest differs')
    manifest = json.loads(manifest_raw)
    require(manifest['labels_read'] is False and manifest['counts']['requests_per_endpoint'] == 8904
            and manifest['counts']['requests_total'] == len(manifest['requests']) == 17808, 'Source geometry/label boundary differs')
    require(c.verify_job_binding(SOURCE, manifest, FROZEN, MANIFEST_SHA, 'grok', Path(job['tools_root_local_only'])) == job,
            'Exact original source execution binding differs')
    sample = SOURCE / SLOT
    for name, sha in SOURCE_PINS.items(): raw('source/sample/' + name, sample / name, sha)
    row = json.loads(reads.raws['source/sample/condition.json'])
    require(row in manifest['requests'] and row['endpoint'] == 'grok' and row['endpoint_ordinal'] == 5
            and c.sample_path(SOURCE, row) == sample
            and digest(canonical({k: v for k, v in row.items() if k != 'request_sha256'})) == row['request_sha256'], 'Fixed source condition differs')
    started = json.loads(reads.raws['source/sample/attempt-started.json'])
    invocation = started['execution_invocation']
    raw('source/invocation', SOURCE / invocation['path'], invocation['sha256'])
    input_names = {row['prompt_path'], row['schema_path'], row['retained_schema_path'], row['task_context']['path'],
                   row['shared_work_context']['path'], *(v['input_path'] for v in row['sources']), *(v['path'] for v in row['task_contracts'])}
    for name in input_names: raw('frozen/input/' + name, FROZEN / name, manifest['artifacts'][name]['sha256'])
    for item in row['sources']: raw('source/sample/sources/' + item['id'], sample / 'sources' / (item['id'] + '.txt'), item['sha256'])
    for name in ('schema_subset.py', 'validate_response.py', 'mfa-admission.py', 'ttcw-admission.py', 'runner.py', 'codex_receipts.py'):
        raw('frozen/implementation/' + name, FROZEN / 'implementation' / name, manifest['artifacts']['implementation/' + name]['sha256'])
    subset = load('lamp_final_frozen_subset', FROZEN / 'implementation/schema_subset.py')
    validator = load('lamp_final_frozen_validator', FROZEN / 'implementation/validate_response.py')
    def exact_session(session, route_root):
        require(session == SESSION and route_root.resolve() == ROUTE_ROOT.resolve(), 'Fixed own native session differs')
        return SESSION_ROOT
    source_project.session_directory = exact_session
    source_project.POLICY = POLICY
    proof = {}
    def completion(selected_sample, prompt, selected_session, selected_started, selected_job, **kwargs):
        require(selected_sample.resolve() == sample.resolve() and selected_session.resolve() == SESSION_ROOT.resolve()
                and selected_started == started and selected_job == job, 'Fixed native recipient binding differs')
        class NativeReads(generic.ReadSet):
            def raw(self, name, path):
                value = raw('native/' + name, path, NATIVE_PINS[name])
                self.raws[name], self.paths[name] = value, str(path); return value
        native_reads = NativeReads()
        chat = [json.loads(v) for v in native_reads.raw('chat', SESSION_ROOT / 'chat_history.jsonl').splitlines()]
        original = generic.grok_projection
        generic.grok_projection = lambda updates, summary, session, text: final_stream_projection(
            original, decode.observed_decode_stream_projection, updates, summary, session, text, chat)
        answer, native = generic.recover_grok(native_reads, sample, prompt.decode(), SESSION_ROOT, started, job)
        projection = native_reads.raws['updates_projection']
        native_reads.paths['updates_projection'] = 'derived:' + POLICY
        reads.raws['native/updates_projection'], reads.paths['native/updates_projection'] = projection, 'derived:' + POLICY
        updates = [json.loads(v) for v in native_reads.raws['updates'].splitlines()]
        proof.update(earlier_stream_sha256=EARLY_SHA, earlier_stream_bytes=EARLY_BYTES, earlier_stream_invalid_json=True,
            canonical_final_sha256=FINAL_SHA, canonical_final_bytes=FINAL_BYTES,
            discarded_rows=[{'position': n, 'record_sha256': digest(canonical(updates[n]))} for n in (1, 2, 3, 4)],
            original_projection_error='Saved stream lacks exact completed assistant response',
            canonical_terminal_has_stream_id=False, terminal_to_stream_identity_attested=False,
            final_stream_contact_attribution_verified=False)
        native.update(policy=POLICY, original_strict_v5_admission_satisfied=False, final_stream_projection=proof)
        return answer, native, native_reads
    receipt, native_reads = source_project.project(sample, row, manifest, job, FROZEN, subset, validator,
        SimpleNamespace(saved_completion=completion, LAMP_POLICY=POLICY), ROUTE_ROOT)
    require(receipt['native']['saved_history']['session_id'] == SESSION and receipt['native']['saved_history']['assistant_sha256'] == FINAL_SHA,
            'Canonical saved answer identity differs')
    receipt.update(schema_version=1, implementation_sha256=digest(Path(__file__).read_bytes()), source_commitments=reads.commitments(),
        projection=proof, original_state='ambiguous', original_strict_v5_admission_satisfied=False,
        same_original_observation_only=True, provider_calls_made=0, new_votes=0, no_resend=True,
        full_planned_denominators={'grok': 8904, 'sol': 8904, 'matched': 17808},
        human_labels_opened=False, human_release_eligible=False)
    response = [json.loads(v) for v in native_reads.raws['chat'].splitlines() if json.loads(v).get('type') == 'assistant'][0]['content'].encode()
    return receipt, reads, response, canonical(receipt['acceptance'])


def fresh_output(output):
    output = output.resolve()
    require(not output.exists() and all(not output.is_relative_to(root.resolve()) and not root.resolve().is_relative_to(output)
            for root in (REPO, SOURCE, FROZEN, SESSION_ROOT.parent)), 'Private output must be fresh and outside retained inputs')
    return output


def verify(path, expected_sha):
    saved_raw = path.read_bytes(); require(digest(saved_raw) == expected_sha, 'Saved descendant receipt differs')
    saved = json.loads(saved_raw)
    require(digest((path.parent / Path(__file__).name).read_bytes()) == saved['implementation_sha256'], 'Saved implementation differs')
    for pin in saved['source_commitments'].values():
        value = (path.parent / pin['snapshot']).read_bytes()
        require(digest(value) == pin['sha256'] and len(value) == pin['bytes'], 'Saved raw/projection snapshot differs')
        if not pin['source_locator_local_only'].startswith('derived:'):
            require(Path(pin['source_locator_local_only']).read_bytes() == value, 'Original source bytes changed')
    actual, _, response, acceptance = reconcile(snapshot=path.parent, commitments=saved['source_commitments'])
    require(actual == saved and (path.parent / 'response.json').read_bytes() == response
            and (path.parent / 'acceptance.json').read_bytes() == acceptance, 'Saved admission/provenance replay differs')
    return actual


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--output-root', required=True, type=Path); parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args(); output = fresh_output(args.output_root)
    receipt, reads, response, acceptance = reconcile(); result = canonical(receipt)
    if not args.dry_run:
        output.mkdir(parents=True, exist_ok=False)
        for name, value in reads.raws.items():
            pin = receipt['source_commitments'][name]
            if not pin['source_locator_local_only'].startswith('derived:'):
                require(Path(pin['source_locator_local_only']).read_bytes() == value, 'Original source changed before snapshot')
            path = output / pin['snapshot']; path.parent.mkdir(parents=True, exist_ok=True)
            with path.open('xb') as handle: handle.write(value)
        for name, value in [('response.json', response), ('acceptance.json', acceptance), (Path(__file__).name, Path(__file__).read_bytes()),
                            ('reconciliation.json', result), ('terminal.json', canonical({'policy': POLICY, 'state': receipt['effective_terminal']['state'],
                                'receipt_sha256': digest(result), 'no_resend': True}))]:
            with (output / name).open('xb') as handle: handle.write(value)
    print(json.dumps({'policy': POLICY, 'slot': SLOT, 'accepted': receipt['acceptance']['accepted'],
        'semantic_error_count': len(receipt['acceptance']['errors']), 'receipt_sha256': digest(result), 'snapshot_files': len(reads.raws),
        'provider_calls': 0, 'new_votes': 0, 'human_labels_opened': False, 'output_written': not args.dry_run}, sort_keys=True))


if __name__ == '__main__': raise SystemExit(main())
