"""Fixed P1 Grok209 ordinary saved completion; zero contacts and zero new votes."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
PROGRAM = Path(r'C:\Users\Haile\Documents\cwr-resume-control-20260919-r1\successor-program-20261004')
BASE = PROGRAM / 'semantic-crossform'
SOURCE = BASE / 'judging-grok-saved-decode-001'
FROZEN = BASE / 'matched-frozen-002'
PLAN = BASE / 'saved-decode-grok-plan-001/plan.json'
LIFECYCLE = BASE / 'saved-decode-grok-lifecycle-001/terminal.json'
OUTPUT = BASE / 'slot209-ordinary-completion-reconciliation-001'
SLOT = '0209-a76bd1eec6bf'
SESSION = '40f1d5ba-d36b-4c22-8316-614017f315d3'
SESSION_ROOT = Path(r'C:\Users\Haile\.grok\sessions\C%3A%5CUsers%5CHaile%5C.codex%5Cstate%5Cmodel-work-queue-cwr-placeholder-r31%5Cgrok-exec-pmiant77') / SESSION
POLICY = 'fixed_p1_grok209_ordinary_completed_history_v1'
MANIFEST_SHA = '4e139dc1ef859be838cbe9ee8c579285845074032c6a00867a1b03859fdec2ff'
PLAN_SHA = '417c211cd33e56a730ec57bad4a99d83aa4465c6c7afda7149abcbec641beffa'
JOB_SHA = 'b667fa6c7a5dd1893cc5e7b73b647a427945a3665c685064960d6dffda5da58b'
LIFECYCLE_SHA = '7d226e3867e5a134f2f37eff42907d6d64ea9cc832e67b9cd08aa0c184521409'
REQUEST_SHA = '83aa9dc38a9976feca2d97ec0a924933ccad53b48b96513bcf1448475d66da59'
LOGICAL = 'a76bd1eec6bfe42548b4e292787b22e8f254f6879a08ac1cdf534898bd95ae11'
RESPONSE_SHA = '98fdae19580bd77b0b11fe93115cec40a201a14464e6f9cfcca792ae8e74bb3d'
CODE = {
    'generic': ('reconcile.py', 'fbedc8e50d08de7dff0547483f26c9fd081a8b4c9e62f0713609ce043e0fb34c'),
    'history': ('../hbq-matched-ttcw-20261004/reconcile_history.py', 'a9e27d3c5da5ff341f0f7172d7dfffd6c139fe8f569b2655e55fbf7279c676ed'),
    'continuation': ('continue_saved_decode.py', '993ef94ac1f032fd44d880fc953238a4653d6777f9fba964bbb73aa1c12ff7d2'),
    'collector': ('../hbq-semantic-crossform-p1b-matched-v1/collector.py', '71e4a5e1a21ff45338796b060fadde638367067da922786e0a810eec42e8feaa')}
SOURCE_PINS = {
    'attempt-started.json': '02df809f0549e29108fc11e43e3e0fd4284db7b8def84e6b2a326a5f44f65894',
    'condition.json': '7e5186e3335a696b317eace719158cfbe58a037c4f1565d7e956ace9015ab941',
    'native-identity.json': '14783777fee124b93bb790c9a65663ea318c1d9d13abfbf9444626cda7019959',
    'native-result.json': 'ccf48ff7a508db048959ee50ca2c4852f5f3a8eee37e9683d7316a3755f555d7',
    'prompt.txt': '61809a098f19f4f15ce3adeae99246c8f2beaee25d710134fca8cae49772b75b',
    'schema.json': 'dee0567f0ac0830351b8d272c67f3440acf92fa5f48e9cc373c4513547ec2e96',
    'terminal.json': 'c3b9bed8ad817b7bbd7ebd8e3fe966a23c79b0575e62d921b0429808e9b4f1f2'}
NATIVE_PINS = {
    'summary': '777ad66b72dd44d9a640036bd3002c8547dfc925b2db58bc6cf911996047e593',
    'updates': '89fa5e89df4f8bb888eac7a517b4c4ae0e9a6171f4ca04efffca3b179bc25123',
    'chat': 'c065aa96419e1dcaf362f007840b40846c11c535ffbc1478b8c2690ed062a6f4',
    'events': '2fa411a58588e59a275b554ff4192d6ccb7ebc015e6db34ffb59643fb1c8e7cd',
    'signals': '29ff06d6d71cb6387d9a06674697f704212410d1f594e33f357c99b03856b002',
    'prompt_history': '3f6f0cca0af9018d95109fb28ededd0e16cfc8f77b3710548ea7da0d166afed3',
    'tool_definitions': '4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945',
    'usage': 'd442b98415512ed8908f8833de423b7032251810410413a4105d11da57837757',
    'prompt_context': '61154e505bdd694888da0d3a084c18f04867b7c6d6e73efdda47baa34f272ddf',
    'system_prompt': 'd8711efa61dbbc48826ea2aa504cb3850f00ffd0ba693b59c4a9bf8a04517405'}


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False) + '\n').encode()


def require(ok, message):
    if not ok:
        raise ValueError(message)


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def exact_native_prompt(prompt, history_text, update_text):
    require(isinstance(prompt, bytes) and prompt.endswith(b'\n')
            and isinstance(history_text, str) and isinstance(update_text, str)
            and history_text.encode('utf-8') == update_text.encode('utf-8') == prompt[:-1],
            'Only the fixed final-LF omission is supported; native history/user bytes must match')


def ordinary_records(generic, updates, summary, session, prompt, history_text, assistant):
    require([row['params']['update']['sessionUpdate'] for row in updates] ==
            ['user_message_chunk', 'agent_thought_chunk', 'agent_message_chunk', 'turn_completed'],
            'Only the four ordinary completed records are supported')
    exact_native_prompt(prompt, history_text, updates[0]['params']['update']['content']['text'])
    require(summary['current_model_id'] == 'grok-4.7' and summary['reasoning_effort'] == 'high'
            and assistant['model_id'] == 'grok-4.7-build' and assistant['reasoning_effort'] == 'high',
            'Own requested/reported model or effort differs')
    # The unchanged generic checker validates every record, then requires a DNS diagnostic.
    # This named ordinary policy retains all four records and permits no diagnostic.
    try:
        generic.grok_projection(updates, summary, session, prompt.decode('utf-8'))
    except ValueError as error:
        require(str(error) == 'No demonstrated Grok DNS recovery', 'Ordinary native field/lifecycle validation failed')
    else:
        raise ValueError('Ordinary recipient cannot adopt a diagnostic projection')


def observation(row, started, native, raw_response, acceptance):
    require(row['endpoint'] == 'grok' and row['endpoint_ordinal'] == 209
            and row['logical_sample_id'] == LOGICAL and row['request_sha256'] == REQUEST_SHA
            and started['session_id'] == native['session_id'] == SESSION
            and started['job_sha256'] == JOB_SHA, 'Fixed original request/native provenance differs')
    require(type(acceptance.get('accepted')) is bool and isinstance(json.loads(raw_response), dict),
            'Saved semantic disposition/response is unresolved')
    return {'endpoint': 'grok', 'endpoint_ordinal': 209, 'slot': SLOT, 'logical_sample_id': LOGICAL,
            'request_sha256': REQUEST_SHA, 'source_job_sha256': JOB_SHA,
            'source_terminal_sha256': SOURCE_PINS['terminal.json'], 'original_state': 'ambiguous',
            'state': 'accepted' if acceptance['accepted'] else 'semantic_rejected',
            'response_sha256': digest(raw_response), 'response_bytes': len(raw_response),
            'acceptance_sha256': digest(canonical(acceptance)), 'admission': acceptance,
            'native': {'policy': POLICY, 'saved_history': native, 'original_strict_v5_admission_satisfied': False},
            'same_original_observation_only': True, 'new_votes': 0, 'no_resend': True}


def reconcile(*, snapshot=None, commitments=None):
    for relative, sha in CODE.values():
        require(digest((HERE / relative).read_bytes()) == sha, 'Frozen source implementation differs')
    generic = load('p1_ordinary_private_generic', HERE / CODE['generic'][0])
    continuation = load('p1_ordinary_private_continuation', HERE / CODE['continuation'][0])
    history = load('p1_ordinary_private_history', HERE / CODE['history'][0])
    c = load('p1_ordinary_private_collector', HERE / CODE['collector'][0])
    class Reads(generic.ReadSet):
        def raw(self, name, path):
            require(self.snapshot is None or name in self.expected, 'Snapshot commitment missing')
            return super().raw(name, path)
    reads = Reads(snapshot, commitments)
    def raw(name, path, sha):
        value = reads.raw(name, path)
        require(digest(value) == sha, 'Pinned source differs: ' + name)
        return value
    own_code = Path(__file__).read_bytes()
    raw('implementation/recipient', Path(__file__), digest(own_code))
    for key, (relative, sha) in CODE.items():
        raw('implementation/' + key, HERE / relative, sha)
    manifest = json.loads(raw('source/manifest', FROZEN / 'manifest.json', MANIFEST_SHA))
    require(len(manifest['requests']) == manifest['counts']['requests_total'] == 1584
            and manifest['human_alignment_claim'] is False and manifest['fixed_synthetic_labels'] is False
            and manifest['evidence_class'] == 'descriptive_ai_synthetic_stimuli', 'Full P1 source/label boundary differs')
    plan = json.loads(raw('source/plan', PLAN, PLAN_SHA))
    job = json.loads(raw('source/job', SOURCE / 'job.json', JOB_SHA))
    require(job == continuation.job_binding(plan, PLAN_SHA, job['workers'], job['route'], job['execution_route_sha256']),
            'Exact source runtime/account/route binding differs')
    lifecycle = json.loads(raw('source/lifecycle', LIFECYCLE, LIFECYCLE_SHA))
    require(lifecycle['exit_code'] == 3, 'Own collector lifecycle is not the frozen terminal')
    sample = SOURCE / SLOT
    require({p.relative_to(sample).as_posix() for p in sample.rglob('*') if p.is_file()} == set(SOURCE_PINS),
            'Original source inventory changed or has an envelope/descendant')
    for name, sha in SOURCE_PINS.items():
        raw('source/sample/' + name, sample / name, sha)
    row = json.loads(reads.raws['source/sample/condition.json'])
    require(row in manifest['requests'] and c.sample_path(SOURCE, row) == sample
            and digest(canonical({k: v for k, v in row.items() if k != 'request_sha256'})) == row['request_sha256'],
            'Original committed condition differs')
    terminal = json.loads(reads.raws['source/sample/terminal.json'])
    failure = json.loads(reads.raws['source/sample/native-result.json'])
    require(terminal['state'] == failure['state'] == 'ambiguous' and terminal['accepted'] is False
            and terminal['no_resend'] is True and terminal['error_class'] == 'RuntimeError'
            and failure['result'] is None and failure['failure']['code'] == 'unclassified_after_launch'
            and failure['failure']['provider_error_type'] == 'GrokBuildTransportFailure', 'Exact original failure differs')
    identity = json.loads(reads.raws['source/sample/native-identity.json'])
    require(identity == {'logical_sample_id': LOGICAL, 'session_id': SESSION}, 'Fixed native UUID differs')
    inputs = {row['prompt_path'], row['schema_path'], row['task_context']['path'], row['shared_work_context']['path'],
              *(item['input_path'] for item in row['sources']), *(item['path'] for item in row['task_contracts'])}
    for name in sorted(inputs):
        raw('frozen/input/' + name, FROZEN / name, manifest['artifacts'][name]['sha256'])
    for name in ('schema_subset.py', 'validate_response.py', 'runner.py', 'codex_receipts.py'):
        raw('frozen/implementation/' + name, FROZEN / 'implementation' / name, manifest['artifacts']['implementation/' + name]['sha256'])
    subset = load('p1_ordinary_frozen_subset', FROZEN / 'implementation/schema_subset.py')
    validator = load('p1_ordinary_frozen_validator', FROZEN / 'implementation/validate_response.py')
    original, answer = c.replay(sample, row, manifest, job, FROZEN, generic.codex_receipts, subset, validator)
    require(original == terminal and answer is None, 'Original failure acquired an admitted response')
    started, prompt, schema, texts, context = generic.validate_started(c, sample, row, job, MANIFEST_SHA, FROZEN, manifest)
    require(len(prompt) == 23444 and prompt == reads.raws['source/sample/prompt.txt'], 'Exact original prompt bytes differ')
    class NativeInputs:
        def raw(self, name, path):
            return raw('native/' + name, path, NATIVE_PINS[name])
        def json(self, name, path):
            return json.loads(self.raw(name, path))
        def lines(self, name, path):
            return [json.loads(line) for line in self.raw(name, path).splitlines()]
    native_inputs = NativeInputs()
    summary = native_inputs.json('summary', SESSION_ROOT / 'summary.json')
    updates = native_inputs.lines('updates', SESSION_ROOT / 'updates.jsonl')
    histories = native_inputs.lines('prompt_history', SESSION_ROOT.parent / 'prompt_history.jsonl')
    chat = native_inputs.lines('chat', SESSION_ROOT / 'chat_history.jsonl')
    assistants = [item for item in chat if item.get('type') == 'assistant']
    require(len(histories) == len(assistants) == 1, 'Saved native request/answer is not unique')
    ordinary_records(generic, updates, summary, SESSION, prompt, histories[0]['prompt'], assistants[0])
    response, native = history.history_response(native_inputs, SESSION_ROOT, identity, started,
        {'model': job['route']['model'], 'route': job['route'], 'cutoff': job['campaign_deadline']}, prompt)
    require(len(response) == 10430 and digest(response) == RESPONSE_SHA, 'Fixed saved final bytes differ')
    subset.validate_schema(json.loads(schema))
    acceptance = validator.semantic_validate(row['arm'], json.loads(response), row, texts, subset, context=context, schema=json.loads(schema))
    receipt = observation(row, started, native, response, acceptance)
    receipt.update(schema_version=1, policy=POLICY, implementation_sha256=digest(own_code),
                   manifest_sha256=MANIFEST_SHA, plan_sha256=PLAN_SHA, source_lifecycle_sha256=LIFECYCLE_SHA,
                   source_commitments=reads.commitments(), provider_calls=0, human_labels_opened=False,
                   human_release_eligible=False, full_planned_denominators={'sol': 792, 'grok': 792, 'matched': 1584},
                   original_failure_preserved=True, original_strict_v5_admission_satisfied=False,
                   original_native_envelopes_reconstructed=False, original_outbound_bytes_preserved=True,
                   prompt_projection='fixed_single_terminal_lf_omission', native_records_filtered=0,
                   physical_contact_cardinality_proven=False, cost_tokens_latency_attested=False)
    return receipt, reads, response, canonical(acceptance)


def verify(receipt_path, expected_sha256):
    raw = receipt_path.read_bytes()
    require(digest(raw) == expected_sha256, 'Exact ordinary recipient receipt differs')
    saved = json.loads(raw)
    actual, _, response, acceptance = reconcile(snapshot=receipt_path.parent, commitments=saved['source_commitments'])
    require(actual == saved, 'Ordinary snapshot/native/admission replay differs')
    require((receipt_path.parent / 'response.json').read_bytes() == response
            and (receipt_path.parent / 'acceptance.json').read_bytes() == acceptance, 'Saved response/admission artifact differs')
    for pin in saved['source_commitments'].values():
        current = Path(pin['source_locator_local_only']).read_bytes()
        require(digest(current) == pin['sha256'] and len(current) == pin['bytes'], 'Original retained source bytes changed')
    return actual


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--output-root', type=Path)
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--verify', type=Path)
    parser.add_argument('--expected-sha256')
    args = parser.parse_args()
    if args.verify:
        require(args.expected_sha256 and not args.output_root and not args.dry_run, 'Verification needs only exact receipt SHA')
        receipt = verify(args.verify, args.expected_sha256)
        print(json.dumps({'state': 'verified', 'policy': POLICY, 'receipt_sha256': args.expected_sha256,
                          'accepted': receipt['admission']['accepted'], 'provider_calls': 0, 'new_votes': 0, 'human_labels_opened': False}))
        return 0
    require(args.output_root and not args.expected_sha256, 'Fresh fixed private output root required')
    output = args.output_root.resolve()
    require(output == OUTPUT.resolve() and not output.exists(), 'Only the fresh named private recipient output is supported')
    receipt, reads, response, acceptance = reconcile()
    payload = canonical(receipt)
    if not args.dry_run:
        output.mkdir(parents=True, exist_ok=False)
        files = {pin['snapshot']: reads.raws[name] for name, pin in receipt['source_commitments'].items()}
        files.update({'reconciliation.json': payload, 'response.json': response, 'acceptance.json': acceptance})
        for relative, data in files.items():
            path = output / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open('xb') as stream:
                stream.write(data)
    print(json.dumps({'state': 'ordinary_completion_dry_run' if args.dry_run else 'saved_ordinary_completion',
                      'policy': POLICY, 'receipt_sha256': digest(payload), 'accepted': receipt['admission']['accepted'],
                      'semantic_errors': len(receipt['admission'].get('errors', [])), 'snapshots': len(reads.raws),
                      'full_planned_denominator': 1584, 'provider_calls': 0, 'new_votes': 0,
                      'human_labels_opened': False, 'output_written': not args.dry_run}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
