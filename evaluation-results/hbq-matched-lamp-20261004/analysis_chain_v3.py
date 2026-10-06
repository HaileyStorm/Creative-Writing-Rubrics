"""Explicit full LAMP chain replay; metadata mode opens code, never outcomes.

Historical scoring and rank decoding remain the pinned predecessor's methods.
Saved completions qualify their original observations; they add no new votes.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
PROGRAM = Path.home() / 'Documents/cwr-resume-control-20260919-r1/successor-program-20261004'
POLICY = 'matched_lamp_full17808_native_chain_analysis_v3'
OWNER = '01a10839-a735-7bf2-a05a-68afadb52755'
MANIFEST_SHA = '480aa86df271078e322ac85cf8cfe5fe6ed02344138e218900cfe03c069b6ab6'
ANALYSIS_SHA = 'de4e20855e346232a0de7f7fbbc83b6f85b9982fc992821cfe962344e6c4d856'
IDENTITY_SHA = '5c8997c439298c15d3f5619ed42e04927e90f0b0553bbeeae18fd5b96d5f22ba'
GAP_SHA = '6770d434646e3147ea720943b54baee8c4d63b87cace3508eefbbde1433fef3b'
GAP_RECEIPT = 'f7c55334ad10992a73ce805bb6f46b448aee7dcd0ddd868f13f1c7b1b5da48bd'
FIXED340_SHA = '13047d0ea1979934fba861f0cc493dc59631db73329d7e51eabbe5604b2bdde4'
FIXED340_RECEIPT = '7b4dfe778985a41497d30a28aa1f31b22182d5b56931cf6b5bbd6e62de9a6d22'
SOL_FREEZE = '166c7372df38f87ab31aa95dd35a0c2b3523d0ff135fe978d579fa6f8219420a'
GROK_FREEZE = '3526472e3e02cb648100725b784d5626a70501bd7893a377e39d9dd203ee6798'
ORIGINAL = {
    'sol': {'job': '28c0d9a9979a607d4c19fab543f11a5a17d6f3531d07bd3aea3d422ed511a5c7',
        'outer': '78652ea92b9015a5dd40f8a9b508a088caf0d59bc83748da82e13711ead4dc0a',
        'launcher': ('launch_sol_parallel_001.py', '7d0d631983272084a8cfa6f320479eb7698e80b6f5482688c4560f78360c0e1e'),
        'output': 'judging-sol-parallel-001', 'through': 1155, 'exit': 3},
    'grok': {'job': 'fac974ba29adc5fe8aefd3bda35397f2f26076b47f6737af5b7507069bfbb527',
        'outer': '9f966188428b875c53f679dd1a6219cae881b55ee69694db46ee61b470394b51',
        'launcher': ('launch_saved_prefix_v2_001.py', '2f4d3b15947bf8edcc74da8b6982d370597bf784ff54f03532c31387158ceb48'),
        'output': 'judging-grok-saved-prefix-v2-001', 'through': 343, 'exit': 1},
}
SUFFIXES = {'grok': {
    'collector': ('continue_lamp_untouched_suffix_v4_001.py', '2fd621267b6d78eb4c93fec1474de72032d8a233326710c23c9688b04c7df64e'),
    'launcher': ('launch_lamp_grok_suffix_003_001.py', '32627bdf06ed2abd2e6c89cf3466163c1f4499a4338e217a75e215e549760f36'),
    'policy': 'lamp_untouched343_strict_native_once_execution_v4', 'freeze': GROK_FREEZE,
    'output': 'judging-grok-untouched-suffix-v4-001', 'through': 343,
}, 'sol': {
    'collector': ('continue_lamp_sol_suffix_v2_001.py', '8dcd8d68e681f4c9b009939b50f5d1727c5155c733d5187b63082b5df77e445d'),
    'launcher': ('launch_lamp_sol_suffix_002_001.py', '08d8976be6bc40cf8d2faa098868512f64a5c1b73eb62f3da38e842f709fc500'),
    'policy': 'lamp_sol_untouched1155_strict_native_once_execution_v2', 'freeze': SOL_FREEZE,
    'output': 'judging-sol-suffix-v2-001', 'through': 1155,
}}
sys.dont_write_bytecode = True


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False) + '\n').encode()


def checked(path, pin):
    raw = Path(path).read_bytes()
    require(sha(raw) == pin, 'Exact retained source differs')
    return raw


def module(name, path, pin):
    checked(path, pin)
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def predecessor():
    return module('lamp_chain_v3_private_analysis', HERE / 'analysis.py', ANALYSIS_SHA)


def identity_reader():
    return module('lamp_chain_v3_metadata_identity', HERE.parent / 'hbq-mfa-conditional-benchmark-v1/analysis_chain_v2.py', IDENTITY_SHA)


def argument(argv, name):
    require(argv.count(name) == 1 and argv.index(name) + 1 < len(argv), 'Own argv argument missing/duplicated')
    return argv[argv.index(name) + 1]


def time(value):
    result = datetime.fromisoformat(value)
    require(result.tzinfo is not None, 'Owning chronology requires timezone')
    return result


def lifecycle(source, job):
    endpoint, kind = source['endpoint'], source['kind']
    require(endpoint in ORIGINAL and kind in {'original', 'suffix'}, 'Unknown chain source')
    pins = source['lifecycle']
    original = kind == 'original'
    spec = ORIGINAL[endpoint] if original else SUFFIXES[endpoint]
    names = {'outer_terminal', 'invocation', 'launcher', 'run_started', 'handle'}
    if not original or endpoint == 'grok':
        names.add('native_handle')
    require(set(pins) == names, 'Exact owning lifecycle files required')
    read = lambda name: json.loads(checked(pins[name]['path'], pins[name]['sha256']))
    # This gate precedes all attempt/response reads, including saved projections.
    outer = read('outer_terminal')
    if original:
        require(pins['outer_terminal']['sha256'] == spec['outer'] and outer['exit_code'] == spec['exit'], 'Original owning terminal differs')
    else:
        require(outer['exit_code'] in (0, 3) and outer.get('native_exit_confirmed') is True,
                'Suffix requires its owning child wait/return')
    require(outer['no_resend'] is True, 'Owning return must preserve no-resend')
    launcher = PROGRAM / 'lamp-reference' / spec['launcher'][0]
    require(Path(pins['launcher']['path']).resolve() == launcher.resolve()
            and pins['launcher']['sha256'] == spec['launcher'][1], 'Unpinned owning launcher')
    checked(launcher, spec['launcher'][1])
    inv, started, handle = (read(n) for n in ('invocation', 'run_started', 'handle'))
    rawpin = pins['invocation']['sha256']
    argv = inv['native_argv'] if not original and endpoint == 'sol' else inv['argv']
    require(inv['launcher_sha256'] == spec['launcher'][1] and inv['owner'] == OWNER
            and inv['workers'] == handle['workers'] == job['workers'] == 2
            and inv['collector_sha256'] == job['collector_sha256']
            and inv['manifest_sha256'] == job['manifest_sha256'] == source['manifest_sha256']
            and started['invocation_sha256'] == rawpin
            and time(inv['time']) <= time(started['time']) <= time(outer['time'])
            and started['no_resend'] is True
            and Path(handle['native_job']).resolve() == Path(source['results_root']).resolve() / 'job.json'
            and Path(handle['lifecycle']).resolve() == Path(pins['outer_terminal']['path']).resolve().parent,
            'Own invocation/job/start/handle differs')
    require('--validate-only' not in argv
            and int(argument(argv, '--workers')) == 2 and '--owner-global-headroom-verified' in argv,
            'Owning scientific argv differs')
    if original or endpoint == 'grok':
        require(Path(argument(argv, '--results-dir')).resolve() == Path(source['results_root']).resolve(), 'Own scientific output differs')
    if original:
        command_source = module('lamp_chain_v3_original_' + endpoint + '_owning_command', launcher, spec['launcher'][1])
        require(argv == command_source.command()
                and Path(source['manifest_path']).resolve() == (PROGRAM / 'lamp-reference/frozen-001/manifest.json').resolve(),
                'Exact original owning command/science differs')
    else:
        require(argument(argv, '--manifest-sha256') == source['manifest_sha256'], 'Suffix scientific pin differs')
    if original and endpoint == 'sol':
        require(handle['invocation_sha256'] == rawpin and started['pid'] == handle['pid'], 'Original runpy owning identity differs')
        proof_basis = 'pinned_own_runpy_return_and_threadpool_join'
    else:
        native = read('native_handle')
        require(started['argv'] == native['argv'] == argv and native['no_resend'] is True
                and native['pid'] != handle['pid'] and Path(native['cwd']).resolve() == REPO.resolve()
                and outer['invocation_sha256'] == rawpin, 'Owning child/native argv differs')
        proof_basis = 'pinned_own_child_wait_and_threadpool_join'
    if not original:
        suffix_lifecycle(source, job, pins, inv, started, handle, native, outer, spec)
    return {'endpoint': endpoint, 'kind': kind, 'verified': True, 'job_sha256': source['job_sha256'],
        'lifecycle_sha256': {key: value['sha256'] for key, value in pins.items()}, 'proof_basis': proof_basis,
        'native_process_creation_verified': not original, 'remote_or_billing_quiescence_proven': False}


def suffix_lifecycle(source, job, pins, inv, started, handle, native, outer, spec):
    launcher = PROGRAM / 'lamp-reference' / spec['launcher'][0]
    if spec['policy'] == 'lamp_sol_untouched1155_strict_native_once_execution_v2':
        sol_suffix_lifecycle(source, job, pins, inv, started, handle, native, outer, spec)
        return
    argv = inv['argv']; rawpin = pins['invocation']['sha256']
    require(handle['argv'] == [str(REPO / '.venv/Scripts/python.exe'), '-B', str(launcher), '--run', '--invocation-sha256', rawpin]
            and argv[:3] == [str(REPO / '.venv/Scripts/python.exe'), '-B', str(PROGRAM / 'lamp-reference' / spec['collector'][0])]
            and argument(argv, '--adapter-sha256') == spec['collector'][1]
            and argument(argv, '--owning-invocation') == pins['invocation']['path']
            and '--execute-native' in argv and argument(argv, '--endpoint-headroom') == '2'
            and inv['route_sha256'] == job['route_sha256']
            and inv['persistence_guard_policy'] == job['persistence_guard_policy'] == 'free_disk_before_native_contact_v1'
            and inv['minimum_free_disk_bytes'] == job['minimum_free_disk_bytes'] == 268435456
            and set(inv['owner_attestations']) == {'global_headroom_verified', 'returned_allocation_verified',
                'current_route_verified', 'outbound_disclosure_confirmed'}
            and all(value is True for value in inv['owner_attestations'].values()), 'Exact executed suffix owner/persistence contract differs')
    require(job['owning_invocation_binding_verified'] is True and job['execution_opt_in'] is True
            and job['owner_global_headroom_confirmation'] is True
            and job['owning_invocation'] == {'path': pins['invocation']['path'], 'sha256': rawpin,
                'bytes': len(checked(pins['invocation']['path'], rawpin)), 'launcher_sha256': spec['launcher'][1],
                'source_outer_sha256': inv['source_release']['source_outer_sha256'],
                'source_inventory_sha256': inv['source_release']['inventory_sha256']}
            and outer['native_job'] == {'path': str(Path(source['results_root']) / 'job.json'),
                'sha256': source['job_sha256'], 'bytes': len(checked(Path(source['results_root']) / 'job.json', source['job_sha256']))},
            'Executed own job/outer commitment differs')
    require(handle['creation_time_basis'] == native['creation_time_basis'] == 'Windows GetProcessTimes on owned Popen handle'
            and handle['creationflags'] == 134218240 and native['creationflags'] == 134217728
            and time(inv['time']) <= time(handle['process_creation_utc']) <= time(started['time'])
            <= time(native['process_creation_utc']) <= time(outer['time']), 'Exact own creation/return chronology differs')


def sol_suffix_lifecycle(source, job, pins, inv, started, handle, native, outer, spec):
    launcher = PROGRAM / 'lamp-reference' / spec['launcher'][0]
    command_source = module('lamp_chain_v3_sol_owning_command', launcher, spec['launcher'][1])
    rawpin = pins['invocation']['sha256']; argv = inv['native_argv']
    require(argv == command_source.native_command()
            and handle['argv'] == [str(REPO / '.venv/Scripts/python.exe'), '-B', str(launcher), '--run']
            and argument(argv, '--owner-lifecycle-root') == str(Path(pins['invocation']['path']).parent)
            and '--execute-native' in argv and argument(argv, '--endpoint-headroom') == '2'
            and set(inv['owner_attestations']) == {'global_headroom_verified', 'current_conditional_sol2_released', 'outbound_disclosure_acknowledged'}
            and all(v is True for v in inv['owner_attestations'].values())
            and job['execution_opt_in'] is True and job['owner_lifecycle_invocation_sha256'] == rawpin
            and job['runtime_augmentation'] == {'policy': 'lamp_sol_disk_stop_before_contact_v1',
                'source_sha256': spec['collector'][1], 'min_launch_free_bytes': 1073741824,
                'min_contact_free_bytes': 268435456, 'original_durable_callback_preserved': True}
            and started['source_release_sha256'] == sha(canonical(inv['source_release'])), 'Executed Sol owning/runtime contract differs')
    require(handle['creation_time_basis'] == native['creation_time_basis'] == 'Windows GetProcessTimes on owned Popen handle'
            and handle['creationflags'] == 134218240 and native['creationflags'] == 134217728
            and time(inv['time']) <= time(handle['process_creation_utc']) <= time(started['time'])
            <= time(native['process_creation_utc']) <= time(outer['time']), 'Sol own creation/return chronology differs')


def merge(joined, records, seen, row, terminal, answer, identities, provenance, attempted):
    key = (row['endpoint'], row['endpoint_ordinal'])
    require(key not in joined, 'Original observation occupied twice')
    require(len(set(identities)) == len(identities) and not seen.intersection(identities), 'Native identity reused across original observations')
    require(answer is None or terminal['state'] == 'accepted' and terminal['accepted'] is True,
            'Rejected or failed response cannot supply a vote')
    require(terminal['state'] in {'accepted', 'semantic_rejected', 'ambiguous', 'unadmitted_no_resend'}, 'Unknown terminal disposition')
    seen.update(identities)
    entry = {'endpoint': row['endpoint'], 'endpoint_ordinal': row['endpoint_ordinal'],
        'descriptor_sha256': sha(canonical(row)), 'state': terminal['state'], 'terminal_verified': True, 'attempted_verified': attempted,
        'native_identity_commitments': [list(i) for i in identities], 'provenance': provenance}
    joined[key] = entry
    if answer is not None:
        records.append({'request': row, 'response': answer})


def label_gate(manifest, ledger, proofs, explicit_release):
    planned = {(r['endpoint'], r['endpoint_ordinal']): sha(canonical(r)) for r in manifest['requests']}
    require(len(planned) == len(manifest['requests']) == 17808
            and Counter(ep for ep, _ in planned) == {'sol': 8904, 'grok': 8904}, 'Full scientific denominator differs')
    require(len(ledger) == 17808 and set(ledger) == set(planned)
            and all(e['descriptor_sha256'] == planned[key] for key, e in ledger.items()), 'Original descriptor ledger differs')
    require({(p['endpoint'], p['kind']) for p in proofs} == {(e, k) for e in ORIGINAL for k in ('original', 'suffix')}
            and len(proofs) == 4 and all(p['verified'] is True for p in proofs), 'Every named owning return required')
    ready = all(e.get('terminal_verified') is True and e.get('attempted_verified') is True
                and e['state'] in {'accepted', 'semantic_rejected', 'ambiguous', 'unadmitted_no_resend'}
                and (e['state'] not in {'accepted', 'semantic_rejected'} or e['native_identity_commitments']) for e in ledger.values())
    return {'policy': POLICY + '_all17808_explicit_rank_release', 'planned': 17808,
        'all_planned_verified_attempted_terminal_dispositions': ready, 'explicit_postprediction_release': explicit_release,
        'human_release_eligible': ready and explicit_release is True, 'human_targets_opened': False}


def gap_terminal(sample, row, job, c):
    require(row['endpoint'] == 'sol' and row['endpoint_ordinal'] in (1153, 1155), 'Unknown empty terminal gap')
    reader = module('lamp_chain_v3_fixed_gap', PROGRAM / 'ttcw-phase1/recover_disk_full_gaps_001.py', GAP_SHA)
    raw, provenance = reader.resolve_terminal(sample / 'terminal.json', GAP_RECEIPT)
    terminal = json.loads(raw)
    require(provenance['projection_applied'] is True and terminal['state'] == 'ambiguous'
            and terminal['accepted'] is False and terminal['logical_sample_id'] == row['logical_sample_id']
            and terminal['job_sha256'] == sha((sample.parent / 'job.json').read_bytes())
            and terminal['manifest_sha256'] == job['manifest_sha256'] and terminal['no_resend'] is True
            and json.loads((sample / 'condition.json').read_bytes()) == row, 'Gap missing-observation binding differs')
    for name, pin in terminal['retained_artifacts'].items():
        c.pinned(sample, name, pin)
    return terminal, None, provenance


def replay_suffix(adapter, c, sample, row, manifest, job, receipts, subset, validator):
    state = json.loads((sample / 'terminal.json').read_bytes())['state']
    if state in c.SETTLED:
        return adapter.replay(c, sample, row, manifest, job, receipts, subset, validator)
    # The historical execution replay intentionally rejects failed slots for
    # resumption. Analysis retains that verified disposition without a vote.
    require(state in c.TERMINAL_STATES, 'Unknown suffix terminal disposition')
    if row['endpoint'] == 'sol':
        return adapter.replay(c, sample, row, manifest, job, receipts, subset, validator)
    terminal, answer = c.replay(sample, row, manifest, job, adapter.base['FROZEN'], receipts, subset, validator)
    require(answer is None and terminal['accepted'] is False and not terminal.get('retention_errors'), 'Failed suffix evidence is unretained/admitted')
    return terminal, None


def fixed340(row, original, answer, sample):
    require(row['endpoint_ordinal'] == 340 and original['state'] == 'ambiguous' and answer is None, 'Fixed340 requires original missing observation')
    reader = module('lamp_chain_v3_fixed340', HERE.parent / 'hbq-native-transport-recovery-v1/reconcile_lamp_slot340_final_stream.py', FIXED340_SHA)
    overlay = reader.verify(PROGRAM / 'lamp-reference/slot340-final-stream-reconciliation-001/reconciliation.json', FIXED340_RECEIPT)
    terminal = overlay['effective_terminal']
    session = json.loads((sample / 'native-identity.json').read_bytes())['session_id']
    require(overlay['same_original_observation_only'] is True and overlay['new_votes'] == 0
            and overlay['request_sha256'] == row['request_sha256']
            and Path(overlay['source_sample_local_only']).resolve() == sample.resolve()
            and overlay['source_job_sha256'] == original['job_sha256']
            and terminal['logical_sample_id'] == original['logical_sample_id'] == row['logical_sample_id']
            and terminal['native_thread_id'] == session and original.get('native_thread_id', session) == session
            and terminal['attempt_id'] == original['attempt_id']
            and terminal['manifest_sha256'] == original['manifest_sha256']
            and terminal['accepted'] == overlay['acceptance']['accepted']
            and terminal['state'] in {'accepted', 'semantic_rejected'}
            and terminal['no_resend'] is True and overlay['original_strict_v5_admission_satisfied'] is False,
            'Fixed340 changes original request/native/admission identity')
    return terminal, overlay['response'] if terminal['accepted'] else None


def build(config):
    require(config['manifest_sha256'] == MANIFEST_SHA and config['policy'] == POLICY, 'Named original scientific config required')
    old = predecessor(); c = old.c; identity = identity_reader(); project = identity.lexical_reader()
    sources = config['sources']
    require(len(sources) == 4 and {(s['endpoint'], s['kind']) for s in sources}
            == {(e, k) for e in ORIGINAL for k in ('original', 'suffix')}, 'Exactly four named chain sources required')
    require(len({Path(s['results_root']).resolve() for s in sources}) == 4, 'Duplicate source output')
    jobs, proofs = {}, []
    for source in sources:
        key = (source['endpoint'], source['kind'])
        spec = ORIGINAL[key[0]] if key[1] == 'original' else SUFFIXES[key[0]]
        require(Path(source['results_root']).resolve() == (PROGRAM / 'lamp-reference' / spec['output']).resolve(), 'Named result root differs')
        if key[1] == 'original':
            require(source['job_sha256'] == spec['job'] and source['manifest_sha256'] == MANIFEST_SHA, 'Original source pins differ')
        else:
            require(source['manifest_sha256'] == spec['freeze'], 'Suffix source manifest differs')
        # A missing owning outer fails before any native job/attempt is opened.
        outer_pin = source['lifecycle']['outer_terminal']
        checked(outer_pin['path'], outer_pin['sha256'])
        jobs[key] = json.loads(checked(Path(source['results_root']) / 'job.json', source['job_sha256']))
        proofs.append(lifecycle(source, jobs[key]))
    manifest, root, subset, validator, receipts, hbq = old.load_manifest(Path(config['manifest_path']), MANIFEST_SHA, Path(config['tools_root']))
    old.load_human_profile(manifest)
    source_by = {(s['endpoint'], s['kind']): s for s in sources}
    original_outputs = {e: Path(source_by[(e, 'original')]['results_root']) for e in ORIGINAL}
    sol_job = c.verify_job_binding(original_outputs['sol'], manifest, root, MANIFEST_SHA, 'sol', Path(config['tools_root']))
    require(sol_job == jobs[('sol', 'original')], 'Original Sol job reconstruction differs')
    # Only this private analysis instance substitutes already-verified owning
    # returns for the predecessor's limited EXIT0/3 outer interface.
    prior_outer = old.outer_terminal_binding
    proof_by = {p['endpoint']: p for p in proofs if p['kind'] == 'original'}
    def verified_outer(output, endpoint, binding, path, pin):
        source = source_by[(endpoint, 'original')]
        require(output == original_outputs[endpoint] and binding == jobs[(endpoint, 'original')]
                and Path(path) == Path(source['lifecycle']['outer_terminal']['path'])
                and pin == source['lifecycle']['outer_terminal']['sha256'], 'Verified original owning return substituted incorrectly')
        return proof_by[endpoint]
    old.outer_terminal_binding = verified_outer
    try:
        adoption = old.load_saved_v2_adoption(manifest, root, Path(config['tools_root']), original_outputs, subset, validator, receipts,
            prefix_root=PROGRAM / 'lamp-reference/saved-prefix-v2-001', prefix_sha=old.SAVED_V2_PREFIX_SHA,
            job_sha=old.SAVED_V2_JOB_SHA, sol_job_sha=old.SOL_JOB_SHA,
            route_root=Path(config['route_root']), route_sha=config['original_grok_route_sha256'],
            outer_pins={e: (Path(source_by[(e, 'original')]['lifecycle']['outer_terminal']['path']),
                source_by[(e, 'original')]['lifecycle']['outer_terminal']['sha256']) for e in ORIGINAL})
    finally:
        old.outer_terminal_binding = prior_outer
    joined, records, seen = {}, [], set()
    def observe(row, terminal, answer, sample, provenance):
        ids = identity.native_ids(sample, row, terminal, c, project)
        terminal_id = terminal.get('native_thread_id')
        if terminal_id:
            item = ('sol_thread' if row['endpoint'] == 'sol' else 'grok_session', sha(terminal_id.encode()))
            require(item in ids, 'Effective terminal and original native metadata disagree')
        started_path = sample / 'attempt-started.json'
        attempted = started_path.is_file()
        if attempted:
            fields = {'attempt': True, 'no_resend': True, 'logical_sample_id': True, 'manifest_sha256': True,
                'job_sha256': True, 'prompt_sha256': True, 'schema_sha256': True, 'attempt_id': True, 'time': True,
                'execution_invocation': True}
            started = project(started_path.read_bytes(), fields)
            require(started['attempt'] == 1 and started['no_resend'] is True
                    and started['logical_sample_id'] == terminal['logical_sample_id'] == row['logical_sample_id']
                    and started['manifest_sha256'] == terminal['manifest_sha256']
                    and started['job_sha256'] == terminal['job_sha256'] == sha((sample.parent / 'job.json').read_bytes())
                    and started['prompt_sha256'] == row['prompt_sha256'] and started['schema_sha256'] == row['schema_sha256'],
                    'Original attempted missing/native binding differs')
            require(started['attempt_id'] == terminal.get('attempt_id', terminal.get('recovery', {}).get('native_metadata', {}).get('attempt_id')),
                    'Own attempt identity differs')
            time(started['time'])
            execution = project(c.pinned(sample.parent, started['execution_invocation']['path'], started['execution_invocation']),
                {'argv': True, 'workers': True, 'job_sha256': True, 'time': True})
            source_workers = project((sample.parent / 'job.json').read_bytes(), {'workers': True})['workers']
            require(execution['job_sha256'] == started['job_sha256'] and execution['workers'] == source_workers
                    and c.execution_workers(execution['argv']) == source_workers
                    and '--owner-global-headroom-verified' in execution['argv']
                    and time(execution['time']) <= time(started['time']), 'Original durable callback/execution binding differs')
            provenance['original_attempt_started_sha256'] = sha(started_path.read_bytes())
        require(answer is None or attempted, 'Accepted observation lacks original durable attempt')
        merge(joined, records, seen, row, terminal, answer, ids, provenance, attempted)
    for endpoint in ORIGINAL:
        output = original_outputs[endpoint]; job = jobs[(endpoint, 'original')]
        rows = [r for r in manifest['requests'] if r['endpoint'] == endpoint][:ORIGINAL[endpoint]['through']]
        expected = {c.sample_path(output, r).name for r in rows if endpoint != 'grok' or r['endpoint_ordinal'] > 122}
        require({p.name for p in output.iterdir() if p.is_dir() and re.match(r'\d{4}-', p.name)} == expected,
                'Original occupied membership differs from its frozen reservation')
        for row in rows:
            sample = c.sample_path(output, row); ordinal = row['endpoint_ordinal']
            if endpoint == 'grok' and ordinal <= 122:
                terminal, answer = old.saved_v2_replay(sample, row, adoption, manifest, root, receipts, subset, validator, output)
                entry = adoption['prefix']['entries'][ordinal - 1]
                sample = Path(entry['source_sample_local_only'])
                provenance = {'policy': old.SAVED_V2_ADOPTION_POLICY, 'prefix_sha256': old.SAVED_V2_PREFIX_SHA,
                    'source_artifacts': entry['source_artifacts'], 'same_original_observation_only': True, 'new_votes': 0}
            elif endpoint == 'sol' and ordinal in (1153, 1155):
                terminal, answer, provenance = gap_terminal(sample, row, job, c)
            else:
                raw = (sample / 'terminal.json').read_bytes()
                terminal, answer = (old.saved_v2_replay(sample, row, adoption, manifest, root, receipts, subset, validator, output)
                    if endpoint == 'grok' and ordinal != 340 else c.replay(sample, row, manifest, job, root, receipts, subset, validator))
                provenance = {'original_terminal_sha256': sha(raw), 'original_terminal_state': json.loads(raw)['state'],
                    'qualified_representation': terminal.get('admission_basis'), 'new_votes': 0}
                if endpoint == 'grok' and ordinal == 340:
                    terminal, answer = fixed340(row, terminal, answer, sample)
                    provenance.update(qualified_representation='saved_lamp_slot340_canonical_final_stream_projection_v1',
                        receipt_sha256=FIXED340_RECEIPT, original_strict_v5_admission_satisfied=False)
                require((sample / 'terminal.json').read_bytes() == raw and not terminal.get('retention_errors'), 'Original terminal changed/unretained')
            observe(row, terminal, answer, sample, provenance)
    for endpoint in ORIGINAL:
        source = source_by[(endpoint, 'suffix')]; spec = SUFFIXES[endpoint]; job = jobs[(endpoint, 'suffix')]
        adapter = module('lamp_chain_v3_' + endpoint + '_native_suffix', PROGRAM / 'lamp-reference' / spec['collector'][0], spec['collector'][1])
        context = adapter.qualification_context()
        if endpoint == 'sol':
            p, own_c, own, rows, modules = context
        else:
            p, own_c, own, rows, reserved_ids, modules = context
        require(rows == [r for r in manifest['requests'] if r['endpoint'] == endpoint][spec['through']:]
                and all(own['artifacts'][k] == v for k, v in manifest['artifacts'].items()), 'Suffix changes original science/artifacts')
        invpin = source['lifecycle']['invocation']; invraw = checked(invpin['path'], invpin['sha256']); inv = json.loads(invraw)
        if endpoint == 'sol':
            expected_job = adapter.job_binding(p, own_c, own, 2, 2, invpin['sha256'], True)
        else:
            adapter.owning_pin = {'path': invpin['path'], 'sha256': invpin['sha256'], 'bytes': len(invraw),
                'launcher_sha256': spec['launcher'][1], 'source_outer_sha256': inv['source_release']['source_outer_sha256'],
                'source_inventory_sha256': inv['source_release']['inventory_sha256']}
            expected_job = adapter.job_binding(p, own_c, own, job.get('route'), 2, 2, True, True)
        require(job == expected_job, 'Exact executed native suffix job differs')
        output = Path(source['results_root']); allowed = {c.sample_path(output, row).name: row for row in rows}
        require(all(d.name in allowed for d in output.iterdir() if d.is_dir() and re.match(r'\d{4}-', d.name)), 'Suffix reoccupies reserved/foreign slot')
        own_subset, own_validator, own_receipts = modules
        for row in rows:
            sample = c.sample_path(output, row)
            if not sample.exists():
                key = (endpoint, row['endpoint_ordinal'])
                require(key not in joined, 'Untouched suffix duplicates original observation')
                joined[key] = {'endpoint': endpoint, 'endpoint_ordinal': row['endpoint_ordinal'],
                    'descriptor_sha256': sha(canonical(row)), 'state': 'untouched', 'terminal_verified': False,
                    'native_identity_commitments': []}
                continue
            require((sample / 'terminal.json').is_file(), 'Returned suffix retains an unresolved occupied slot; no resend')
            raw = (sample / 'terminal.json').read_bytes()
            terminal, answer = replay_suffix(adapter, own_c, sample, row, own, job, own_receipts, own_subset, own_validator)
            require((sample / 'terminal.json').read_bytes() == raw, 'Own native terminal changed')
            observe(row, terminal, answer, sample, {'collector_sha256': spec['collector'][1],
                'original_terminal_sha256': sha(raw), 'strict_native_verified': terminal['state'] in c.SETTLED})
    require(len(joined) == 17808, 'Full original chain denominator differs')
    return old, manifest, root, hbq, joined, records, proofs


def analyze(config, explicit_release=False, control=None, reps=2000):
    old, manifest, root, hbq, ledger, records, proofs = build(config)
    gate = label_gate(manifest, ledger, proofs, explicit_release)
    banks = old.profiles(manifest, records, hbq, root)
    alignment = {'state': 'sealed_skipped_before_decode', 'human_targets_opened': False}
    if explicit_release:
        require(gate['human_release_eligible'] and control is not None, 'All verified original terminals and explicit rank release required')
        profile = old.load_human_profile(manifest)
        orders = old.load_human_orders(manifest, root, control.resolve(), profile)
        alignment = {'state': 'descriptive_development_alignment', 'human_targets_opened': True,
            **old.human_metrics(manifest, orders, banks, records, reps)}
    return {'policy': POLICY, 'manifest_sha256': MANIFEST_SHA, 'analysis_sha256': sha(Path(__file__).read_bytes()),
        'planned_requests': 17808, 'endpoint_states': {ep: dict(Counter(e['state'] for e in ledger.values() if e['endpoint'] == ep)) for ep in ORIGINAL},
        'ledger_sha256': sha(canonical(list(ledger.values()))), 'owning_returns': proofs, 'label_gate': gate,
        'scalars': old.scalar_diagnostics(manifest, banks), 'pairwise': old.pair_diagnostics(manifest, records),
        'paired_endpoints': old.endpoint_diagnostics(manifest, banks, reps), 'human_alignment': alignment,
        'labels_read': alignment['human_targets_opened'], 'provider_calls': 0, 'new_votes_from_projections': 0,
        'limits': ['Qualified historical observations do not manufacture strict-v5 envelopes or contact cardinality.',
            'Unknown tokens/latency remain unavailable; planned repeats are correlated observations.',
            'Already development-exposed triplets; no global disconnected ranking or independent-person claim.']}


def metadata():
    old = predecessor()
    old.c.p.checked(HERE / 'human_profile.json', old.HUMAN_PROFILE_SHA)
    identity = identity_reader()
    identity.lexical_reader()
    for spec in ORIGINAL.values():
        checked(PROGRAM / 'lamp-reference' / spec['launcher'][0], spec['launcher'][1])
    for spec in SUFFIXES.values():
        checked(PROGRAM / 'lamp-reference' / spec['collector'][0], spec['collector'][1])
        checked(PROGRAM / 'lamp-reference' / spec['launcher'][0], spec['launcher'][1])
    return {'policy': POLICY, 'analysis_sha256': sha(Path(__file__).read_bytes()), 'predecessor_sha256': ANALYSIS_SHA,
        'scientific_manifest_sha256': MANIFEST_SHA, 'human_profile_sha256': old.HUMAN_PROFILE_SHA,
        'planned': 17808, 'endpoint_planned': {'sol': 8904, 'grok': 8904},
        'reserved': {'sol': 1155, 'grok': 343}, 'untouched_suffix': {'sol': 7749, 'grok': 8561},
        'suffix_contracts': SUFFIXES, 'source_jobs_read': 0, 'source_attempts_read': 0, 'source_answers_read': 0,
        'human_targets_opened': False, 'human_release_eligible': False, 'provider_calls': 0,
        'runtime_full_chain_verified': False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--metadata-only', action='store_true')
    parser.add_argument('--config', type=Path)
    parser.add_argument('--config-sha256')
    parser.add_argument('--explicit-postprediction-release', action='store_true')
    parser.add_argument('--control-root', type=Path)
    parser.add_argument('--bootstrap-reps', type=int, default=2000)
    args = parser.parse_args(argv)
    if args.metadata_only:
        require(args.config is None and args.config_sha256 is None and not args.explicit_postprediction_release
                and args.control_root is None, 'Metadata mode cannot open sources or ranks')
        print(json.dumps(metadata(), sort_keys=True)); return 0
    require(args.config is not None and args.config_sha256 is not None, 'Exact pinned chain config required')
    require(1 <= args.bootstrap_reps <= 2000, 'Finite bootstrap repetitions required')
    config = json.loads(checked(args.config, args.config_sha256))
    report = analyze(config, args.explicit_postprediction_release, args.control_root, args.bootstrap_reps)
    print(json.dumps(report, ensure_ascii=False, sort_keys=True, allow_nan=False)); return 0


if __name__ == '__main__':
    raise SystemExit(main())
