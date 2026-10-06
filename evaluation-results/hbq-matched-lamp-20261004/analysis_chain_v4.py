"""Named LAMP004 full17808 analysis; metadata mode never opens native outcomes.

The pinned historical chain supplies the first400 Grok observations once.
Only401..8904 may replace its untouched entries after every owning return.
"""
from __future__ import annotations

import ast
from collections import Counter
import json
from pathlib import Path
import re
import sys
from types import FunctionType

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
PREDECESSOR_SHA = '790f0f7dcc5fff2d3bff402697c4686e2d0a633059405c34375ba71f7046e60b'
POLICY = 'matched_lamp_full17808_native_chain_analysis_v4'
COLLECTOR_SHA = '2b7f60e1f51bcdc1b610f6c577f163b928fc69020668868f1075c0b7100781db'
LAUNCHER_SHA = 'fdaaf0a2578db78b53931a97a30fa92ec28abdf8e98b36f5d5baffeeabc28177'
FROZEN_SHA = '2b9d3b625e0c7f2a82e4fba1c88615a6801bb540ed805e86557e6d5cc42fd379'
INVOCATION_SHA = '22621920debcb904764c2187685bee1b1c32985e19e51fc87088443ceaed34e8'
JOB_SHA = '122346f10322e83ec8b9cb86577633a0d17cf4b938ce208540b06bb2e374817f'
RETURN_READER_SHA = 'ec51197c5beccc7e5214f9887d934822556683f63805385a2b98ad4991cf0219'
RETURN_SHA = 'a7abefd69c8d5af62e595865f5842202a6a29685f665f5dee28421d295a4feaa'
HISTORICAL_JOB_SHA = '2e0d777d88b5e7c4acbf86ed479d9622ce105baf01f663a95faff1aca92f0c90'
HISTORICAL_OUTER_SHA = '8324824750f6e128aa588ae26e98f1777cb81bffba7d9200cf929336368aff6e'
HISTORICAL_INVOCATION_SHA = '33e2b9b3216fdd8723ed708f63e4a7cf244b214dadadbadbfd76b4badc63a7c2'
HISTORICAL_DISPATCH_SHA = '69a44fda3ae59758fd641f8edd6e1d7312512e6bfe4c0bb92ebc95a588d89471'
CURRENT = {'collector': ('continue_lamp_untouched_suffix_v5_001.py', COLLECTOR_SHA),
    'launcher': ('launch_lamp_grok_suffix_004_001.py', LAUNCHER_SHA),
    'policy': 'lamp_untouched400_strict_native_once_execution_v5', 'freeze': FROZEN_SHA,
    'output': 'judging-grok-untouched-suffix-v5-001', 'through': 400}
CURRENT_LIFECYCLE_PINS = {'invocation': INVOCATION_SHA,
    'handle': '9738f97d61c666651422934e89074a84864fca8a5e687050096f69f83f6decd9',
    'native_handle': '93b1a70c8a9849b5d0c198b326c1bdde9d2c476e0c7ab9c760e6ae64251f9e01',
    'run_started': '647bbed69e34e7aa1f28bf44f6a4acefdd6019e83e4dfce6d07fedcaf21c6543'}


def predecessor():
    import hashlib
    import importlib.util
    path = HERE / 'analysis_chain_v3.py'
    require(hashlib.sha256(path.read_bytes()).hexdigest() == PREDECESSOR_SHA, 'Pinned historical LAMP analysis differs')
    spec = importlib.util.spec_from_file_location('lamp004_private_historical_analysis', path)
    value = importlib.util.module_from_spec(spec); spec.loader.exec_module(value)
    return value


def require(condition, message):
    if not condition:
        raise ValueError(message)


def failed_terminal(sample, row, job, c, project):
    """Retain failed bytes without decoding provider bodies or manufacturing votes."""
    fields = dict.fromkeys('state accepted logical_sample_id manifest_sha256 job_sha256 no_resend retained_artifacts'.split(), True)
    raw = (sample / 'terminal.json').read_bytes()
    terminal = project(raw, fields)
    terminal.update(identity.optional(project, raw, ('attempt_id', 'native_thread_id', 'error_class')))
    require(terminal['state'] in c.TERMINAL_STATES - c.SETTLED and terminal['accepted'] is False
            and terminal['no_resend'] is True and terminal['manifest_sha256'] == job['manifest_sha256']
            and terminal['job_sha256'] == c.digest((sample.parent / 'job.json').read_bytes())
            and terminal['logical_sample_id'] == row['logical_sample_id']
            and project((sample / 'condition.json').read_bytes(), True) == row, 'Failed original metadata binding differs')
    pins = terminal['retained_artifacts']
    require(set(pins) == {p.relative_to(sample).as_posix() for p in sample.rglob('*')
                        if p.is_file() and p.relative_to(sample).as_posix() != 'terminal.json'}, 'Failed original artifact inventory differs')
    for name, pin in pins.items():
        c.pinned(sample, name, pin)
    for kind in ('prompt', 'schema'):
        raw = (sample / (kind + ('.txt' if kind == 'prompt' else '.json'))).read_bytes()
        require(c.digest(raw) == row[kind + '_sha256'] and len(raw) == row[kind + '_bytes'], 'Failed original payload differs')
    return terminal, None


def dispatcher(source, job, prior, observed=None):
    pin = source['lifecycle'].get('dispatch_terminal')
    require(pin is not None, 'Own UUID dispatcher receipt required')
    path, root = Path(pin['path']), Path(source['results_root'])
    require(path.parent.resolve() == root.resolve()
            and re.fullmatch(r'dispatch-terminal-[0-9a-f-]{36}\.json', path.name), 'Own UUID dispatcher path differs')
    require({p.resolve() for p in root.glob('dispatch-terminal-*.json')} == {path.resolve()}, 'Own dispatcher membership differs')
    value = json.loads(prior.checked(path, pin['sha256']))
    require(value['policy'] == job['policy'] and value['workers'] == job['workers'] == 2
            and type(value['inflight_at_terminal']) is int and value['inflight_at_terminal'] == 0
            and value['automatic_retries'] == 0 and value['human_release_eligible'] is False
            and type(value['stopped']) is bool, 'Own joined dispatcher contract differs')
    execution_pin = value['execution_invocation']
    require(re.fullmatch(r'execution-invocation-[0-9a-f-]{36}\.json', execution_pin['path']), 'Own execution receipt path differs')
    raw = prior.checked(root / execution_pin['path'], execution_pin['sha256'])
    execution = json.loads(raw)
    inv = json.loads(prior.checked(source['lifecycle']['invocation']['path'], source['lifecycle']['invocation']['sha256']))
    require(execution_pin['bytes'] == len(raw) and execution['argv'] == inv['argv'][2:]
            and execution['workers'] == 2 and execution['job_sha256'] == source['job_sha256']
            and execution['owner_global_headroom_confirmation'] is True and execution['owner_declared_endpoint_headroom'] == 2
            and prior.time(inv['time']) <= prior.time(execution['time']) <= prior.time(json.loads(prior.checked(
                source['lifecycle']['outer_terminal']['path'], source['lifecycle']['outer_terminal']['sha256']))['time']),
            'Own dispatcher execution/invocation binding differs')
    states = value['states']
    require(set(states) <= {'accepted', 'semantic_rejected', 'ambiguous', 'unadmitted_no_resend'}
            and all(type(n) is int and n >= 0 for n in states.values())
            and value['settled_this_execution'] == sum(states.values()), 'Own dispatcher count differs')
    if observed is not None:
        require(dict(Counter(observed)) == states, 'Dispatcher/replayed terminal counts differ')
    return value


def owning_return(source, job, prior):
    current = source['kind'] == 'suffix004'
    spec = CURRENT if current else prior.SUFFIXES['grok']
    expected_job = JOB_SHA if current else HISTORICAL_JOB_SHA
    require(source['endpoint'] == 'grok' and source['job_sha256'] == expected_job
            and source['manifest_sha256'] == spec['freeze']
            and Path(source['results_root']).resolve() == (prior.PROGRAM / 'lamp-reference' / spec['output']).resolve(),
            'Exact named Grok suffix binding differs')
    pins = source['lifecycle']
    require('dispatch_terminal' in pins, 'Own dispatcher commitment absent')
    life = prior.PROGRAM / 'lamp-reference' / ('untouched-suffix-v5-lifecycle/grok-001' if current else 'untouched-suffix-v4-lifecycle/grok-001')
    for name, filename in {'outer_terminal': 'terminal.json', 'invocation': 'invocation.json', 'run_started': 'run-started.json',
                           'handle': 'handle.json', 'native_handle': 'native-handle.json'}.items():
        require(Path(pins[name]['path']).resolve() == (life / filename).resolve(), 'Own lifecycle path differs')
    expected_pins = CURRENT_LIFECYCLE_PINS if current else {'invocation': HISTORICAL_INVOCATION_SHA,
        'outer_terminal': HISTORICAL_OUTER_SHA, 'dispatch_terminal': HISTORICAL_DISPATCH_SHA}
    require(all(pins[name]['sha256'] == pin for name, pin in expected_pins.items()), 'Actual own lifecycle commitment differs')
    scope = dict(vars(prior), SUFFIXES={**prior.SUFFIXES, 'grok': spec})
    lifecycle = FunctionType(prior.lifecycle.__code__, scope)
    normalized = {**source, 'kind': 'suffix', 'lifecycle': {k: v for k, v in pins.items() if k != 'dispatch_terminal'}}
    proof = lifecycle(normalized, job)
    require(job['policy'] == spec['policy'] and job['collector_sha256'] == spec['collector'][1], 'Own executed collector differs')
    if current:
        native = json.loads(prior.checked(pins['native_handle']['path'], pins['native_handle']['sha256']))
        handle = json.loads(prior.checked(pins['handle']['path'], pins['handle']['sha256']))
        require(native['pid'] == 11560 and handle['pid'] == 33776
                and native['process_creation_utc'] == '2026-10-06T07:57:34.827126+00:00', 'Actual own native birth differs')
        reader = prior.module('lamp004_saved_source_return', prior.PROGRAM / 'lamp-reference/readback_lamp_suffix003_return_001.py', RETURN_READER_SHA)
        receipt, _ = reader.saved_receipt(RETURN_SHA)
        inv = json.loads(prior.checked(pins['invocation']['path'], INVOCATION_SHA))
        require(inv['source_release'] == {**receipt, 'source_return_receipt_sha256': RETURN_SHA}
                and inv['reserved_allocation'] == {'old_interrupted_grok': 3, 'hanna_interrupted_grok': 3, 'ttcw009_untouched_grok': 2, 'new_lamp_grok': 2},
                'Own saved source-return/allocation differs')
    dispatcher(source, job, prior)
    proof.update(kind=source['kind'], code_backed_joined_local_drain=True, inflight_zero_natively_measured=False,
                 dispatch_terminal_sha256=pins['dispatch_terminal']['sha256'])
    return proof


def label_gate(manifest, ledger, proofs, explicit_release):
    prior = predecessor()
    historical = [p for p in proofs if p['kind'] != 'suffix004']
    gate = prior.label_gate(manifest, ledger, historical, False)
    require(len(proofs) == 5 and sum(p['endpoint'] == 'grok' and p['kind'] == 'suffix004' and p['verified'] is True
                                   for p in proofs) == 1, 'All five owning returns required')
    gate.update(policy=POLICY + '_all17808_explicit_rank_release', explicit_postprediction_release=explicit_release,
                human_release_eligible=gate['all_planned_verified_attempted_terminal_dispositions'] and explicit_release is True)
    return gate


def build(config):
    prior = predecessor()
    require(config['policy'] == POLICY and len(config['sources']) == 5, 'Named five-source LAMP004 config required')
    current = [s for s in config['sources'] if s['kind'] == 'suffix004']
    require(len(current) == 1 and current[0]['endpoint'] == 'grok', 'Exactly one named LAMP004 source required')
    source = current[0]
    # Gate every owning return before any historical or current attempt/response read.
    for item in config['sources']:
        pin = item['lifecycle']['outer_terminal']; prior.checked(pin['path'], pin['sha256'])
    job = json.loads(prior.checked(Path(source['results_root']) / 'job.json', source['job_sha256']))
    proof = owning_return(source, job, prior)
    historical = [s for s in config['sources'] if s['kind'] != 'suffix004']
    grok003 = next(s for s in historical if s['endpoint'] == 'grok' and s['kind'] == 'suffix')
    historical_job = json.loads(prior.checked(Path(grok003['results_root']) / 'job.json', grok003['job_sha256']))
    historic_proof = owning_return(grok003, historical_job, prior)
    historical = [{**s, 'lifecycle': {k: v for k, v in s['lifecycle'].items() if k != 'dispatch_terminal'}} for s in historical]
    project = prior.identity_reader().lexical_reader()
    original_predecessor = prior.predecessor
    def selective_predecessor():
        old = original_predecessor(); c = old.c; replay = c.replay
        def selective(sample, row, manifest, binding, root, receipts, subset, validator):
            state = project((sample / 'terminal.json').read_bytes(), {'state': True})['state']
            return (failed_terminal(sample, row, binding, c, project) if state not in c.SETTLED
                    else replay(sample, row, manifest, binding, root, receipts, subset, validator))
        c.replay = selective
        return old
    prior.predecessor = selective_predecessor
    def replay_suffix(adapter, c, sample, row, manifest, binding, receipts, subset, validator):
        state = project((sample / 'terminal.json').read_bytes(), {'state': True})['state']
        return (failed_terminal(sample, row, binding, c, project) if state not in c.SETTLED else
                adapter.replay(c, sample, row, manifest, binding, receipts, subset, validator))
    prior.replay_suffix = replay_suffix
    text = prior.checked(HERE / 'analysis_chain_v3.py', PREDECESSOR_SHA).decode()
    function = next(n for n in ast.parse(text).body if isinstance(n, ast.FunctionDef) and n.name == 'build')
    body = ast.get_source_segment(text, function)
    require(body.count("json.loads(raw)['state']") == 1, 'Historical selective terminal derivation differs')
    body = body.replace("json.loads(raw)['state']", "project(raw, {'state': True})['state']")
    scope = dict(vars(prior)); exec(compile(body, 'pinned_lamp004_historical_build', 'exec'), scope)
    old, manifest, root, hbq, joined, records, proofs = scope['build']({**config, 'policy': prior.POLICY, 'sources': historical})
    proofs = [historic_proof if p['endpoint'] == 'grok' and p['kind'] == 'suffix' else p for p in proofs] + [proof]
    dispatcher(grok003, historical_job, prior, [joined[('grok', n)]['state'] for n in range(344, 401)])
    adapter = prior.module('lamp004_own_native_suffix', prior.PROGRAM / 'lamp-reference' / CURRENT['collector'][0], COLLECTOR_SHA)
    p, c, own, rows, reserved_ids, modules = adapter.qualification_context()
    require(rows == [r for r in manifest['requests'] if r['endpoint'] == 'grok'][400:]
            and all(own['artifacts'][k] == v for k, v in manifest['artifacts'].items()), 'LAMP004 changes original science')
    invpin = source['lifecycle']['invocation']; invraw = prior.checked(invpin['path'], invpin['sha256']); inv = json.loads(invraw)
    adapter.previous['owning_pin'] = {'path': invpin['path'], 'sha256': invpin['sha256'], 'bytes': len(invraw),
        'launcher_sha256': LAUNCHER_SHA, 'source_outer_sha256': inv['source_release']['source_outer_sha256'],
        'source_inventory_sha256': inv['source_release']['inventory_sha256']}
    require(adapter.job_binding(p, c, own, job.get('route'), 2, 2, True, True) == job, 'Actual LAMP004 job reconstruction differs')
    seen = {tuple(i) for entry in joined.values() for i in entry['native_identity_commitments']}
    require({('grok_session', prior.sha(i.encode())) for i in reserved_ids}
            == {i for i in seen if i[0] == 'grok_session'}, 'Frozen400/native identity join differs')
    output = Path(source['results_root']); allowed = {c.sample_path(output, r).name for r in rows}
    require(all(d.name in allowed for d in output.iterdir() if d.is_dir() and re.match(r'\d{4}-', d.name)), 'LAMP004 reoccupies prefix/foreign slot')
    observe = next(n for n in ast.walk(function) if isinstance(n, ast.FunctionDef) and n.name == 'observe')
    observe_scope = dict(vars(prior), c=c, project=project, identity=prior.identity_reader(), joined=joined, records=records, seen=seen)
    exec(compile(ast.fix_missing_locations(ast.Module(body=[observe], type_ignores=[])), 'pinned_lamp004_observe', 'exec'), observe_scope)
    subset, validator, receipts = modules; states = []
    dispatch = dispatcher(source, job, prior)
    for row in rows:
        key = ('grok', row['endpoint_ordinal'])
        require(joined[key]['state'] == 'untouched' and not joined[key]['terminal_verified'], 'LAMP004 position already occupied')
        sample = c.sample_path(output, row)
        if not sample.exists():
            continue
        raw = (sample / 'terminal.json').read_bytes()
        terminal, answer = replay_suffix(adapter, c, sample, row, own, job, receipts, subset, validator)
        states.append(terminal['state'])
        started_path = sample / 'attempt-started.json'
        if started_path.is_file():
            started = project(started_path.read_bytes(), {'execution_invocation': True, 'time': True})
            require(started['execution_invocation'] == dispatch['execution_invocation']
                    and prior.time(started['time']) <= prior.time(json.loads(prior.checked(
                        source['lifecycle']['outer_terminal']['path'], source['lifecycle']['outer_terminal']['sha256']))['time']),
                    'Own LAMP004 attempt dispatcher/return differs')
        require((sample / 'terminal.json').read_bytes() == raw, 'Own original terminal changed')
        del joined[key]
        observe_scope['observe'](row, terminal, answer, sample, {'collector_sha256': COLLECTOR_SHA,
            'original_terminal_sha256': prior.sha(raw), 'new_votes_from_prefix': 0, 'failed_body_decoded': False})
    dispatcher(source, job, prior, states)
    require(len(joined) == 17808, 'Full original cohort differs')
    return old, manifest, root, hbq, joined, records, proofs


def metadata():
    prior = predecessor(); result = prior.metadata()
    for kind in ('collector', 'launcher'):
        prior.checked(prior.PROGRAM / 'lamp-reference' / CURRENT[kind][0], CURRENT[kind][1])
    result.update(policy=POLICY, analysis_sha256=prior.sha(Path(__file__).read_bytes()), predecessor_sha256=PREDECESSOR_SHA,
        reserved={'sol': 1155, 'grok': 400}, untouched_suffix={'sol': 7749, 'grok': 8504},
        current_grok_suffix_contract=CURRENT, current_grok_job_sha256=JOB_SHA, current_grok_invocation_sha256=INVOCATION_SHA,
        required_owning_returns=5, full_chain_verified=False)
    return result


prior = predecessor()
identity = prior.identity_reader()
scope = dict(vars(prior), __file__=str(Path(__file__).resolve()), POLICY=POLICY, build=build, label_gate=label_gate, metadata=metadata)
analyze = FunctionType(prior.analyze.__code__, scope, argdefs=prior.analyze.__defaults__)
scope['analyze'] = analyze
main = FunctionType(prior.main.__code__, scope, argdefs=prior.main.__defaults__)


if __name__ == '__main__':
    raise SystemExit(main())
