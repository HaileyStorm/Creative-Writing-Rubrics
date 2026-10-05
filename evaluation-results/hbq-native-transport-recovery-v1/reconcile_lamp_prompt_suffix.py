"""Two qualified saved representations; original outbound bytes remain unproven."""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
BASE_SHA = 'fe04fb5b85b41ba236bdf577deeaf4c8862f4df54bffe00369a57410a64fc055'
base_path = HERE / 'reconcile_lamp_final_stream.py'
import hashlib
if hashlib.sha256(base_path.read_bytes()).hexdigest() != BASE_SHA: raise ValueError('Frozen source utility differs')
spec = importlib.util.spec_from_file_location('lamp_suffix_private_source_utility', base_path)
base = importlib.util.module_from_spec(spec); sys.modules[spec.name] = base; spec.loader.exec_module(base)
load, require, digest, canonical = base.load, base.require, base.digest, base.canonical
PROGRAM, FROZEN, REPO, ROUTE_ROOT = base.PROGRAM, base.FROZEN, base.REPO, base.ROUTE_ROOT
SOURCE = PROGRAM / 'lamp-reference/judging-grok-decode-continuation-001'
JOB_SHA = '1c32c40d6bfbbe5323823e2a99171ea23eb0667ab812b2add5c61635847c3d9c'
POLICY = 'saved_terminal_space_lf_omission_qualified_representation_v1'
CODE = {**base.CODE, 'base': ('reconcile_lamp_final_stream.py', BASE_SHA)}
OBSERVATIONS = (
    {'slot': '0120-70323a9369e3', 'session': 'a2bfcfb6-b505-4984-a640-9e693df3e22b', 'leaf': 'grok-exec-gc1i1qs6',
     'condition.json': '0921fb72dae95c9f8e6025304d7f0d792c57bbaa2f7671e64c16d0e2b7924a40',
     'attempt-started.json': '3fbbfe47f85a5d6d09c07f9657a5d6b641d915d011f050449875377a0cbd6fc3',
     'native-identity.json': '726f40c1d5066956bd47c8273a1f6632a0cbf14a41f37ccbfcb7852e52f284bb',
     'terminal.json': 'bafc4cbad6c032ca5cfbf3e66ea2dc44620701d9aadfccd9b52a80d93dd2344b',
     'prompt.txt': 'c2e908fda167f12183027ef656a79608591203dd88cdf7c97162548774fee9ea',
     'schema.json': 'a726404eef267d32ab5af1e847c8c376d3ce522d0226663f5efaf72d18ce02bd',
     'saved_prompt_sha256': 'c49e23d1506785b5c915408d6339f675c8d944f7ee2b289e6e047e6215caafff',
     'native': {'updates': '906a17fc106d4b1b8a41b3ba26964df928a1d6241791f854ed1af31e8d2807c0',
        'summary': '3c8c7e43dcc995edbdbe68ffc81e31c60ccb51122396bf87ac2b758db3234f2a',
        'chat': '75439ff802f43fb6c0daa8f3e92e6a0665e9962d7d6e82fa9498354a6a3d4614',
        'events': 'ac2059e1f97d0400bc318a5e8a1a0d7e8aca851cb873d3b84a11ef50e0d41d7a',
        'signals': '668f1f87cea5ff104e8f5bbd60fb5e753c0fc66ea1aca0908918480a979c4adf',
        'prompt_history': 'b5742bf164efff0089d9544fdce7158a11907932f00b58f62bf242fda12c7310',
        'prompt_context': '64be48bebabdc013c30a1bd4ff87f6c7380a5640b5f968fde20cb21bf5e1e8ec',
        'usage': '1b1b82300cbc89800889337226b7f7059ae1aba481e73571655d7f97f2e3d28f'}},
    {'slot': '0121-9bd43d4216e3', 'session': '4a5e787c-f1f6-4bf5-955c-cbf0735aaae9', 'leaf': 'grok-exec-cp24e87t',
     'condition.json': 'f7989aab1de30fe82f7585a4796fe2e5076ad3bf77f98011e876cfdcc23a51a8',
     'attempt-started.json': '08ed6600c8ed7c428c8b5813d1b89e2f1951c3ed361bfacd9c301bbd011b6566',
     'native-identity.json': 'de85dc95baf1b76a606d03e4b587ee66b4b56177656884431842a56cf1db0441',
     'terminal.json': 'd06f217e3a3d05302e550e88605025e640e4fda0b12b39bba97018bb397142a3',
     'prompt.txt': '8d6baff9d1521ebf7fa49f7de38f0603b789535f26aa5cedcdf3c4c5461b5ebe',
     'schema.json': 'f600b151916ae6e44e584f71159b0633d5eb5f3d0b3a04d4873c480a6d0a61cd',
     'saved_prompt_sha256': '3009651155c603cda66656968a501f69a0908abdbb035d9919898f56e52cc97d',
     'native': {'updates': '75e43bc53094b54a8864cf3e0e051d0f8b78ba79f7a47cadce1472eb93c8c893',
        'summary': '15cb2820dfc56f6d7b3e6aacd98a75a57fc57cc319df87d7ff167bc82a37b48d',
        'chat': '63b0de4655098fb01e184248bd19516dc685af824dc841993cb1f23636effbe9',
        'events': '6c6b6f1e7930a2538d73eecff50abbb48a1a94217ac0857c192d688a33c5eaab',
        'signals': '2fc95a806b0100f10f9fd67501f839db5748271ed21c60bbb3b99002480047b3',
        'prompt_history': '9061b5216dccb4cc9806b40233d6a12d05130df05dc8866546cd5d82ea072fd9',
        'prompt_context': '58041685da18c8f9b4aaaaba34aab1e6745d9c3823c4941b3f76223055299865',
        'usage': '3879f5027ec0c9ada89472e5b9bd56e08ad6550c00f5bd27a5709be77265e7b1'}},
)


def session_root(observation):
    return Path(r'C:\Users\Haile\.grok\sessions') / (
        'C%3A%5CUsers%5CHaile%5C.codex%5Cstate%5Cmodel-work-queue-cwr-placeholder-r31%5C' + observation['leaf']) / observation['session']


def qualified_prompt(frozen, updates, histories, session):
    require(frozen.endswith(b' \n') and [v['params']['update']['sessionUpdate'] for v in updates] ==
            ['user_message_chunk', 'agent_thought_chunk', 'agent_message_chunk', 'turn_completed'], 'Not the exact ordinary completion/suffix profile')
    native = updates[0]['params']['update']['content']['text'].encode()
    require(native == frozen[:-2] and updates[0]['params']['sessionId'] == session
            and len(histories) == 1 and histories[0]['session_id'] == session and histories[0]['prompt'].encode() == native,
            'Saved prompt is not the exact own terminal SPACE+LF omission')
    return native


def reconcile(*, snapshot=None, commitments=None):
    for relative, sha in CODE.values(): require(digest((HERE / relative).read_bytes()) == sha, 'Frozen source implementation differs')
    generic = load('lamp_suffix_private_generic', HERE / CODE['generic'][0])
    history = load('lamp_suffix_private_history', HERE / CODE['history'][0])
    project = load('lamp_suffix_private_source_project', HERE / CODE['source_project'][0]); c = project.c
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
    manifest_raw = raw('source/manifest', FROZEN / 'manifest.json', base.MANIFEST_SHA)
    require((SOURCE / 'frozen-manifest.json').read_bytes() == manifest_raw, 'Original job raw manifest differs')
    manifest = json.loads(manifest_raw)
    require(manifest['labels_read'] is False and manifest['counts']['requests_per_endpoint'] == 8904
            and manifest['counts']['requests_total'] == len(manifest['requests']) == 17808
            and job['collector_sha256'] == CODE['source_project'][1] and job['saved_completion_reader_sha256'] == CODE['decode'][1],
            'Source geometry/reader/label boundary differs')
    subset = load('lamp_suffix_frozen_subset', FROZEN / 'implementation/schema_subset.py')
    validator = load('lamp_suffix_frozen_validator', FROZEN / 'implementation/validate_response.py')
    for name in ('schema_subset.py', 'validate_response.py', 'mfa-admission.py', 'ttcw-admission.py', 'runner.py', 'codex_receipts.py'):
        raw('frozen/implementation/' + name, FROZEN / 'implementation' / name, manifest['artifacts']['implementation/' + name]['sha256'])
    entries, responses, acceptances = [], {}, {}
    project.POLICY = POLICY
    for observation in OBSERVATIONS:
        slot = observation['slot']; sample = SOURCE / slot; prefix = slot + '/'; selected_session = session_root(observation)
        for name in ('condition.json', 'attempt-started.json', 'native-identity.json', 'terminal.json', 'prompt.txt', 'schema.json'):
            raw(prefix + 'source/' + name, sample / name, observation[name])
        raw(prefix + 'source/native-result.json', sample / 'native-result.json', base.SOURCE_PINS['native-result.json'])
        row = json.loads(reads.raws[prefix + 'source/condition.json'])
        require(row in manifest['requests'] and row['endpoint'] == 'grok' and row['endpoint_ordinal'] in (120, 121)
                and c.sample_path(SOURCE, row) == sample
                and digest(canonical({k: v for k, v in row.items() if k != 'request_sha256'})) == row['request_sha256'], 'Fixed source condition differs')
        started = json.loads(reads.raws[prefix + 'source/attempt-started.json'])
        invocation = started['execution_invocation']; raw(prefix + 'source/invocation', SOURCE / invocation['path'], invocation['sha256'])
        for name in {row['prompt_path'], row['schema_path'], row['retained_schema_path'], row['task_context']['path'], row['shared_work_context']['path'],
                     *(v['input_path'] for v in row['sources']), *(v['path'] for v in row['task_contracts'])}:
            raw('frozen/input/' + name, FROZEN / name, manifest['artifacts'][name]['sha256'])
        for item in row['sources']: raw(prefix + 'source/sources/' + item['id'], sample / 'sources' / (item['id'] + '.txt'), item['sha256'])
        context_raw = (sample / 'task-context.json').read_bytes()
        raw(prefix + 'source/task-context', sample / 'task-context.json', digest(context_raw))
        def exact_session(session, route_root):
            require(session == observation['session'] and route_root.resolve() == ROUTE_ROOT.resolve(), 'Fixed own native session differs')
            return selected_session
        project.session_directory = exact_session
        def completion(own_sample, frozen_prompt, own_session, own_started, own_job, **kwargs):
            require(own_sample.resolve() == sample.resolve() and own_session.resolve() == selected_session.resolve()
                    and own_started == started and own_job == job, 'Fixed native recipient binding differs')
            class NativeReads(generic.ReadSet):
                def raw(self, name, path):
                    pin = observation['native'].get(name, base.NATIVE_PINS.get(name))
                    require(pin is not None, 'Unpinned native source')
                    value = raw(prefix + 'native/' + name, path, pin); self.raws[name], self.paths[name] = value, str(path); return value
                def json(self, name, path): return json.loads(self.raw(name, path))
                def lines(self, name, path): return [json.loads(v) for v in self.raw(name, path).splitlines()]
            native_reads = NativeReads()
            updates = native_reads.lines('updates', selected_session / 'updates.jsonl')
            histories = native_reads.lines('prompt_history', selected_session.parent / 'prompt_history.jsonl')
            saved_prompt = qualified_prompt(frozen_prompt, updates, histories, observation['session'])
            require(digest(saved_prompt) == observation['saved_prompt_sha256'], 'Exact saved representation differs')
            summary = native_reads.json('summary', selected_session / 'summary.json')
            try: generic.grok_projection(updates, summary, observation['session'], saved_prompt.decode())
            except ValueError as error: require(str(error) == 'No demonstrated Grok DNS recovery', 'Ordinary native field validation failed')
            else: raise ValueError('Unexpected recovery diagnostics in ordinary saved representation')
            response, native = history.history_response(native_reads, selected_session,
                {'session_id': observation['session']}, started,
                {'model': 'grok-4.7', 'route': job['route'], 'cutoff': job['campaign_deadline']}, saved_prompt)
            require(native['prompt_projection'] == 'exact', 'Saved representation itself is not byte-exact')
            native['prompt_projection'] = 'exact_saved_representation_not_attested_original_outbound'
            reads.raws[prefix + 'native/saved_prompt_projection'] = saved_prompt
            reads.paths[prefix + 'native/saved_prompt_projection'] = 'derived:' + POLICY
            proof = {'policy': POLICY, 'saved_history': native, 'history_reader_sha256': CODE['history'][1],
                'qualification': {'omitted_terminal_bytes_hex': '200a', 'original_frozen_prompt_sha256': digest(frozen_prompt),
                    'original_frozen_prompt_bytes': len(frozen_prompt), 'saved_prompt_sha256': digest(saved_prompt), 'saved_prompt_bytes': len(saved_prompt),
                    'all_preceding_bytes_exact': True, 'native_user_equals_prompt_history': True,
                    'exact_original_outbound_bytes_proven': False, 'original_strict_v5_admission_satisfied': False},
                'original_native_envelope_reconstructed': False, 'physical_contact_cardinality_proven': False}
            responses[slot] = response
            return json.loads(response), proof, native_reads
        entry, _ = project.project(sample, row, manifest, job, FROZEN, subset, validator,
            SimpleNamespace(saved_completion=completion, LAMP_POLICY=POLICY), ROUTE_ROOT)
        entry.update(original_state='ambiguous', same_original_observation_only=True, new_votes=0, no_resend=True,
                     original_strict_v5_admission_satisfied=False, exact_original_outbound_bytes_proven=False)
        entries.append(entry); acceptances[slot] = canonical(entry['acceptance'])
    require(len(entries) == len({v['request_sha256'] for v in entries}) == len({v['native']['saved_history']['session_id'] for v in entries}) == 2,
            'Duplicate or widened fixed observation set')
    receipt = {'schema_version': 1, 'policy': POLICY, 'implementation_sha256': digest(Path(__file__).read_bytes()),
        'observations': entries, 'source_commitments': reads.commitments(), 'full_planned_denominators': {'grok': 8904, 'sol': 8904, 'matched': 17808},
        'provider_calls': 0, 'new_votes': 0, 'human_labels_opened': False, 'human_release_eligible': False,
        'exact_original_outbound_bytes_proven': False, 'original_strict_v5_admission_satisfied': False,
        'original_native_envelopes_reconstructed': False, 'physical_contact_cardinality_proven': False}
    return receipt, reads, responses, acceptances


def fresh_output(output):
    output = output.resolve()
    require(not output.exists() and all(not output.is_relative_to(root.resolve()) and not root.resolve().is_relative_to(output)
            for root in (REPO, SOURCE, FROZEN, *(session_root(v).parent for v in OBSERVATIONS))), 'Private output must be fresh and outside retained inputs')
    return output


def verify(path, expected_sha):
    saved_raw = path.read_bytes(); require(digest(saved_raw) == expected_sha, 'Saved descendant receipt differs')
    saved = json.loads(saved_raw)
    require(digest((path.parent / Path(__file__).name).read_bytes()) == saved['implementation_sha256'], 'Saved implementation differs')
    for pin in saved['source_commitments'].values():
        value = (path.parent / pin['snapshot']).read_bytes()
        require(digest(value) == pin['sha256'] and len(value) == pin['bytes'], 'Saved raw/projection snapshot differs')
        if not pin['source_locator_local_only'].startswith('derived:'): require(Path(pin['source_locator_local_only']).read_bytes() == value, 'Original source bytes changed')
    actual, _, responses, acceptances = reconcile(snapshot=path.parent, commitments=saved['source_commitments'])
    require(actual == saved, 'Saved admission/provenance replay differs')
    for slot, response in responses.items():
        require((path.parent / slot / 'response.json').read_bytes() == response and (path.parent / slot / 'acceptance.json').read_bytes() == acceptances[slot],
                'Saved response/admission differs')
    return actual


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--output-root', required=True, type=Path); parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args(); output = fresh_output(args.output_root)
    receipt, reads, responses, acceptances = reconcile(); result = canonical(receipt)
    if not args.dry_run:
        output.mkdir(parents=True, exist_ok=False)
        for name, value in reads.raws.items():
            pin = receipt['source_commitments'][name]
            if not pin['source_locator_local_only'].startswith('derived:'): require(Path(pin['source_locator_local_only']).read_bytes() == value, 'Original source changed before snapshot')
            path = output / pin['snapshot']; path.parent.mkdir(parents=True, exist_ok=True)
            with path.open('xb') as handle: handle.write(value)
        for slot, response in responses.items():
            target = output / slot; target.mkdir()
            with (target / 'response.json').open('xb') as handle: handle.write(response)
            with (target / 'acceptance.json').open('xb') as handle: handle.write(acceptances[slot])
        for name, value in [(Path(__file__).name, Path(__file__).read_bytes()), ('reconciliation.json', result),
                            ('terminal.json', canonical({'policy': POLICY, 'state': 'completed_qualified_representation', 'receipt_sha256': digest(result), 'no_resend': True}))]:
            with (output / name).open('xb') as handle: handle.write(value)
    print(json.dumps({'policy': POLICY, 'observations': 2, 'accepted': sum(v['acceptance']['accepted'] for v in receipt['observations']),
        'semantic_error_count': sum(len(v['acceptance']['errors']) for v in receipt['observations']), 'receipt_sha256': digest(result),
        'snapshot_files': len(reads.raws), 'provider_calls': 0, 'new_votes': 0, 'human_labels_opened': False, 'output_written': not args.dry_run}, sort_keys=True))


if __name__ == '__main__': raise SystemExit(main())
