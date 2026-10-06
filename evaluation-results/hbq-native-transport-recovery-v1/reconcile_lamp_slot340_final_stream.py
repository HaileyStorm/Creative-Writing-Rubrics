"""Fixed-slot340 zero-call descendant of the canonical saved final stream."""
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
SOURCE = PROGRAM / 'lamp-reference/judging-grok-saved-prefix-v2-001'
FROZEN = PROGRAM / 'lamp-reference/frozen-001'
OUTPUT = PROGRAM / 'lamp-reference/slot340-final-stream-reconciliation-001'
LIFECYCLE = PROGRAM / 'lamp-reference/saved-prefix-v2-lifecycle/grok-001'
SLOT = '0340-b7bedd962ccf'
SESSION = '66175d87-fa6d-4871-8765-511a1c5efb59'
SESSION_ROOT = Path(r'C:\Users\Haile\.grok\sessions\C%3A%5CUsers%5CHaile%5C.codex%5Cstate%5Cmodel-work-queue-cwr-placeholder-r31%5Cgrok-exec-ygm6bx75') / SESSION
ROUTE_ROOT = Path(r'C:\Users\Haile\.codex\state\model-work-queue-cwr-placeholder-r31')
POLICY = 'saved_lamp_slot340_canonical_final_stream_projection_v1'
EARLY_SHA = '7b50cbb16757f8df21557a835989b2816a76e18264f795a201775a1493387015'
FINAL_SHA = '48a384d43983f4623254b0ee7d99f8e851f4145f62e743737b41272c2a3e3c12'
EARLY_BYTES, FINAL_BYTES = 4434, 5662
DECODE = 'reqwest error stream: Transport error: error decoding response body'
MANIFEST_SHA = '480aa86df271078e322ac85cf8cfe5fe6ed02344138e218900cfe03c069b6ab6'
PREFIX_SHA = 'f3d3473263e1c3310186f0803b8f52593b1c855f01ff6eec3797ca651e4f2f9c'
JOB_SHA = 'fac974ba29adc5fe8aefd3bda35397f2f26076b47f6737af5b7507069bfbb527'
OUTER_SHA = '9f966188428b875c53f679dd1a6219cae881b55ee69694db46ee61b470394b51'
OUTER_INVOCATION_SHA = '5319fb314f10314ad8f53cffd73f2c193de6a29e65d79d1f947dfd75a59f9b14'
CODE = {
    'generic': ('reconcile.py', 'fbedc8e50d08de7dff0547483f26c9fd081a8b4c9e62f0713609ce043e0fb34c'),
    'history': ('../hbq-matched-ttcw-20261004/reconcile_history.py', 'a9e27d3c5da5ff341f0f7172d7dfffd6c139fe8f569b2655e55fbf7279c676ed'),
    'source_project': ('../hbq-matched-lamp-20261004/collector_decode.py', 'f9bd97b14220e50c174930d0938f540e4f566022be786a4f3a4f24d0b568e30a'),
    'v2': ('../hbq-matched-lamp-20261004/collector_saved_prefix_v2.py', '6ece7e7f867ec87c3d47bd2daee7e437335cca07c82ada0d7d8ae4111d9e6d76'),
    'collector': ('../hbq-matched-lamp-20261004/collector.py', 'd5a146f0ab615994792f422ef7dc01bac5f7dca9e38ac6c0a4a085c5b8ceb698'),
    'prepare': ('../hbq-matched-lamp-20261004/prepare.py', '1e0cad075cefe4408eb48e4e8b6b2b65f1e541be807683a275537ba8248e4d62'),
    'runner': ('../../src/hbqrs/runner.py', '04a87edb728701afa6a43233a775c032473c82d0f189f209713051025d86f1f7'),
    'receipts': ('../../src/hbqrs/codex_receipts.py', '5d1c7af681e881a77201dee7cece4a14fa11cadc86d119714766492e547e1116'),
}
SOURCE_PINS = {
    'condition.json': '566d7b79e5f8aebdb7c1f14ab3d817aa464cad8e75e9714e1827804b339bd830',
    'attempt-started.json': '2e948a43bb236dd89ea209460dc0dad65e0d3c238ac2a0999891866df0c5077c',
    'native-identity.json': '26dc01757f521cd55254b35d32888aa346f6af95a57a6d8da840d6e9fe895df7',
    'native-result.json': 'dc6565defcb63ebfa63c1ef5e999577e208056ab643bdf416a95009b9b03742d',
    'prompt.txt': 'f94c39a4d0196b828c656ba25d088ea197d38acd4f9d00fe47f731cab1713d5a',
    'schema.json': 'b9783df972fa1a6eaaa9b4a8c140ad4453ed32216245429aa162271c04e94b96',
    'task-context.json': '8aeedc034cd240a037bd0763d58ed48d22def0309586289d17d45f65f41559a2',
    'terminal.json': 'ffbdf9b02490ac2a657d787e15a3620bb17efe25649cc336152b1385a010920d',
}
NATIVE_PINS = {
    'summary': '14724584762db6ef2f9407a26e77b4a9b11cf3f82bfa7798d370bc71793eab05',
    'updates': '341a52108838f7b5b969035320e4a7cb9fc90f2d1dacc729cfe70246c370081f',
    'chat': '75559c4e86eb525b8c5f6602192b0fdb41220fe54482fdc29051be8ed4fe1587',
    'events': 'f83c33f9b99697a8563c0020f6f2642eea031e9d2acaa99c4e8d556d8ef64727',
    'signals': 'a1d31b57222b9bdc8cae21a57f8c41b90cc43eb39f555a80b3f33bf163bb239f',
    'prompt_history': '3ed2452b6eae3403fa7215414dab4f4b06eba29bda434111efe952e1bc778218',
    'tool_definitions': '4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945',
    'usage': '540ec9ee3db67fb5c225bbbbe424350687cecbc3941435ee82d1bf9b96f7d2f5',
    'prompt_context': '0a4901d986f2f050e867fd9bbc850cdf74109826f33585e35f3a3fb135bac685',
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


def final_stream_projection(original, updates, summary, session, prompt, chat):
    require(session == SESSION and [v['params']['update']['sessionUpdate'] for v in updates] ==
            ['user_message_chunk', 'agent_thought_chunk', 'retry_state', 'agent_message_chunk',
             'agent_thought_chunk', 'agent_message_chunk', 'turn_completed'], 'Not the fixed slot340 two-stream lifecycle')
    retry = updates[2]
    require(retry['params']['update'] == {'sessionUpdate': 'retry_state', 'type': 'retrying', 'attempt': 1,
            'max_retries': 15, 'reason': DECODE, 'error_type': 'http'}, 'Not the exact slot340 decode diagnostic')
    for rows in ([v for v in updates if v is not retry], [updates[0], retry]):
        try: original(rows, summary, session, prompt)
        except ValueError as error:
            require(str(error) == 'No demonstrated Grok DNS recovery', 'Fixed stream rejected generic native validation')
        else: raise ValueError('Fixed stream cannot adopt another recovery profile')
    ids = [v['params']['_meta']['eventId'] for v in updates]
    times = [original.__globals__['timestamp'](v['timestamp']) for v in updates]
    require(len(ids) == len(set(ids)) and times == sorted(times), 'Fixed stream cross-subsequence identity/time differs')
    user = updates[0]['params']['update']['content']['text']
    require(prompt.endswith('\n') and user == prompt[:-1], 'Not the exact slot340 terminal LF representation')
    pairs = [(updates[1], updates[3]), (updates[4], updates[5])]
    metadata = [[v['params']['_meta'] for v in pair] for pair in pairs]
    require(all(a['streamStartMs'] == b['streamStartMs'] and a['turnStartMs'] == b['turnStartMs']
                and a['promptId'] == b['promptId'] == summary['request_id']
                and a['agentTimestampMs'] <= b['agentTimestampMs'] for a, b in metadata)
            and metadata[0][0]['streamStartMs'] < metadata[1][0]['streamStartMs']
            and metadata[0][0]['turnStartMs'] == metadata[1][0]['turnStartMs'], 'Own distinct final stream binding differs')
    early, final = [pair[1]['params']['update']['content']['text'].encode() for pair in pairs]
    require(len(early) == EARLY_BYTES and digest(early) == EARLY_SHA
            and len(final) == FINAL_BYTES and digest(final) == FINAL_SHA, 'Exact saved slot340 stream bytes differ')
    try: json.loads(early)
    except json.JSONDecodeError: pass
    else: raise ValueError('Earlier stream is a complete alternative; final projection is ineligible')
    require(isinstance(json.loads(final), dict), 'Canonical final is not one structured answer')
    assistants = [v for v in chat if v.get('type') == 'assistant']
    require(len(assistants) == 1 and assistants[0]['content'].encode() == final, 'Canonical saved final is missing or ambiguous')
    return [updates[0], updates[4], updates[5], updates[6]], [
        {'record_sha256': digest(canonical(retry)), 'reason': DECODE, 'attempt': 1}]


def reconcile(*, snapshot=None, commitments=None):
    for relative, sha in CODE.values(): require(digest((HERE / relative).read_bytes()) == sha, 'Frozen source implementation differs')
    generic = load('lamp_slot340_private_generic', HERE / CODE['generic'][0])
    source_project = load('lamp_slot340_private_source_project', HERE / CODE['source_project'][0])
    v2 = load('lamp_slot340_private_v2', HERE / CODE['v2'][0]); c = source_project.c
    class Reads(generic.ReadSet):
        def raw(self, name, path):
            require(self.snapshot is None or name in self.expected, 'Frozen snapshot commitment missing')
            if self.snapshot is None and name == 'source/manifest':
                require(path.stat().st_size == 40062500, 'Exact frozen manifest byte bound differs')
                value = path.read_bytes(); self.raws[name], self.paths[name] = value, str(path); return value
            return super().raw(name, path)
    reads = Reads(snapshot, commitments)
    def raw(name, path, sha):
        value = reads.raw(name, path); require(digest(value) == sha, 'Pinned source differs: ' + name); return value
    for key, (relative, sha) in CODE.items(): raw('implementation/' + key, HERE / relative, sha)
    job = json.loads(raw('source/job', SOURCE / 'job.json', JOB_SHA))
    manifest_raw = raw('source/manifest', FROZEN / 'manifest.json', MANIFEST_SHA); manifest = json.loads(manifest_raw)
    require((SOURCE / 'frozen-manifest.json').read_bytes() == manifest_raw and manifest['labels_read'] is False
            and manifest['counts']['requests_per_endpoint'] == 8904
            and manifest['counts']['requests_total'] == len(manifest['requests']) == 17808, 'Source geometry/label boundary differs')
    raw('source/prefix', SOURCE / 'frozen-prefix.json', PREFIX_SHA)
    require(job == v2.job_binding(manifest, job['route'], job['workers'], PREFIX_SHA, CODE['v2'][1]), 'Exact source v2 execution binding differs')
    outer = json.loads(raw('source/outer_terminal', LIFECYCLE / 'terminal.json', OUTER_SHA))
    outer_invocation = json.loads(raw('source/outer_invocation', LIFECYCLE / 'invocation.json', OUTER_INVOCATION_SHA))
    require(outer['exit_code'] == 1 and outer['no_resend'] is True and outer['invocation_sha256'] == OUTER_INVOCATION_SHA
            and outer_invocation['collector_sha256'] == CODE['v2'][1]
            and outer_invocation['prefix_sha256'] == PREFIX_SHA and outer_invocation['manifest_sha256'] == MANIFEST_SHA,
            'Exact true outer source terminal/invocation differs')
    sample = SOURCE / SLOT
    for name, sha in SOURCE_PINS.items(): raw('source/sample/' + name, sample / name, sha)
    row = json.loads(reads.raws['source/sample/condition.json'])
    require(row in manifest['requests'] and row['endpoint'] == 'grok' and row['endpoint_ordinal'] == 340
            and c.sample_path(SOURCE, row) == sample
            and digest(canonical({k: v for k, v in row.items() if k != 'request_sha256'})) == row['request_sha256'], 'Fixed source condition differs')
    started = json.loads(reads.raws['source/sample/attempt-started.json']); invocation = started['execution_invocation']
    raw('source/invocation', SOURCE / invocation['path'], invocation['sha256'])
    input_names = {row['prompt_path'], row['schema_path'], row['retained_schema_path'], row['task_context']['path'],
                   row['shared_work_context']['path'], *(v['input_path'] for v in row['sources']), *(v['path'] for v in row['task_contracts'])}
    for name in input_names: raw('frozen/input/' + name, FROZEN / name, manifest['artifacts'][name]['sha256'])
    for item in row['sources']: raw('source/sample/sources/' + item['id'], sample / 'sources' / (item['id'] + '.txt'), item['sha256'])
    for name in ('schema_subset.py', 'validate_response.py', 'mfa-admission.py', 'ttcw-admission.py', 'runner.py', 'codex_receipts.py'):
        raw('frozen/implementation/' + name, FROZEN / 'implementation' / name, manifest['artifacts']['implementation/' + name]['sha256'])
    subset = load('lamp_slot340_frozen_subset', FROZEN / 'implementation/schema_subset.py')
    validator = load('lamp_slot340_frozen_validator', FROZEN / 'implementation/validate_response.py')
    def exact_session(session, route_root):
        require(session == SESSION and route_root.resolve() == ROUTE_ROOT.resolve(), 'Fixed own native session differs'); return SESSION_ROOT
    source_project.session_directory = exact_session; source_project.POLICY = POLICY
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
        histories = [json.loads(v) for v in native_reads.raw('prompt_history', SESSION_ROOT.parent / 'prompt_history.jsonl').splitlines()]
        require(len(histories) == 1 and histories[0]['session_id'] == SESSION
                and histories[0]['prompt'].encode() == prompt[:-1], 'Exact own slot340 saved prompt representation differs')
        original = generic.grok_projection
        generic.grok_projection = lambda updates, summary, session, text: final_stream_projection(original, updates, summary, session, text, chat)
        answer, native = generic.recover_grok(native_reads, sample, prompt.decode(), SESSION_ROOT, started, job)
        require(native['saved_history']['prompt_projection'] == 'single_terminal_lf_omission', 'Fixed prompt representation differs')
        projection = native_reads.raws['updates_projection']
        reads.raws['native/updates_projection'], reads.paths['native/updates_projection'] = projection, 'derived:' + POLICY
        updates = [json.loads(v) for v in native_reads.raws['updates'].splitlines()]
        proof.update(earlier_stream_sha256=EARLY_SHA, earlier_stream_bytes=EARLY_BYTES, earlier_stream_invalid_json=True,
            canonical_final_sha256=FINAL_SHA, canonical_final_bytes=FINAL_BYTES,
            discarded_rows=[{'position': n, 'record_sha256': digest(canonical(updates[n]))} for n in (1, 2, 3)],
            original_projection_error='Unobserved decode stream lifecycle', saved_prompt_projection='single_terminal_lf_omission',
            canonical_terminal_has_stream_id=False, terminal_to_stream_identity_attested=False,
            final_stream_contact_attribution_verified=False, exact_original_outbound_bytes_proven=False)
        native.update(policy=POLICY, original_strict_v5_admission_satisfied=False, final_stream_projection=proof)
        return answer, native, native_reads
    receipt, native_reads = source_project.project(sample, row, manifest, job, FROZEN, subset, validator,
        SimpleNamespace(saved_completion=completion, LAMP_POLICY=POLICY), ROUTE_ROOT)
    require(receipt['native']['saved_history']['session_id'] == SESSION
            and receipt['native']['saved_history']['assistant_sha256'] == FINAL_SHA, 'Canonical saved answer identity differs')
    receipt.update(schema_version=1, implementation_sha256=digest(Path(__file__).read_bytes()), source_commitments=reads.commitments(),
        projection=proof, original_state='ambiguous', original_strict_v5_admission_satisfied=False,
        exact_original_outbound_bytes_proven=False, same_original_observation_only=True, provider_calls_made=0, new_votes=0, no_resend=True,
        full_planned_denominators={'grok': 8904, 'sol': 8904, 'matched': 17808}, human_labels_opened=False, human_release_eligible=False)
    response = [json.loads(v) for v in native_reads.raws['chat'].splitlines() if json.loads(v).get('type') == 'assistant'][0]['content'].encode()
    return receipt, reads, response, canonical(receipt['acceptance'])


def verify(path, expected_sha):
    saved_raw = path.read_bytes(); require(digest(saved_raw) == expected_sha, 'Saved descendant receipt differs'); saved = json.loads(saved_raw)
    require(digest((path.parent / Path(__file__).name).read_bytes()) == saved['implementation_sha256'], 'Saved implementation differs')
    for pin in saved['source_commitments'].values():
        value = (path.parent / pin['snapshot']).read_bytes()
        require(digest(value) == pin['sha256'] and len(value) == pin['bytes'], 'Saved raw/projection snapshot differs')
        if not pin['source_locator_local_only'].startswith('derived:'):
            require(Path(pin['source_locator_local_only']).read_bytes() == value, 'Original source bytes changed')
    actual, _, response, acceptance = reconcile(snapshot=path.parent, commitments=saved['source_commitments'])
    require(actual == saved and (path.parent / 'response.json').read_bytes() == response
            and (path.parent / 'acceptance.json').read_bytes() == acceptance, 'Saved admission/provenance replay differs'); return actual


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--output-root', required=True, type=Path); parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args(); output = args.output_root.resolve()
    require(output == OUTPUT.resolve() and not output.exists(), 'Named private output must be fresh')
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
    print(json.dumps({'policy': POLICY, 'slot': SLOT, 'proposed_state': receipt['effective_terminal']['state'],
        'accepted': receipt['acceptance']['accepted'], 'semantic_error_count': len(receipt['acceptance']['errors']),
        'receipt_sha256': digest(result), 'snapshot_files': len(reads.raws), 'provider_calls': 0, 'new_votes': 0,
        'human_labels_opened': False, 'output_written': not args.dry_run}, sort_keys=True))


if __name__ == '__main__': main()
