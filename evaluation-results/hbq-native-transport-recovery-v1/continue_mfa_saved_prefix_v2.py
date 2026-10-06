"""Reserve the stopped MFA Grok prefix; dispatch only original slots307..434."""
from copy import deepcopy
import argparse
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import continue_saved_decode as old

f, r = old.f, old.r
canonical, digest, require, meta, write = old.canonical, old.digest, old.require, old.meta, old.write
POLICY = 'mfa_saved_prefix_untouched_suffix_v2'
PROGRAM = Path(r'C:\Users\Haile\Documents\cwr-resume-control-20260919-r1\successor-program-20261004')
BASE = PROGRAM / 'mfa-canary'
FROZEN = BASE / 'frozen-001'
SOURCE = BASE / 'judging-grok-saved-decode-001'
PLAN_ROOT = BASE / 'saved-prefix-v2-001'
PARENT = BASE / 'saved-decode-grok-plan-001/plan.json'
PARENT_SHA = '82fcfaffbb35a65158d3d22f775db9e4a669961d58fbc5e6531e4fd7fdb683f5'
MANIFEST_SHA = 'ce8a735c40a18c676c82cc0585b36f91cbb6a9faa98ac2289f86fdfb52cadd80'
JOB_SHA = '29ddbc6ca1391176e3803d4e28a9b4e7f7be4becaaad20ad68fec33aeaa9463c'
OUTER = BASE / 'saved-decode-grok-lifecycle-001/terminal.json'
OUTER_SHA = 'd13e32e80083f81a089ae61c3613bc82a225ac55ea8a0e39032ea92b17938d34'
RELEASE = PROGRAM / 'semantic-crossform/saved-prefix-v2-lifecycle/grok-001/invocation.json'
RELEASE_SHA = '6bb17b3141ef91836dbe2b2c3101d6e715c054b4e1e9595a167db7bab0a508d9'
INVENTORY_SHA = '505068a78d29d49011cc54a512066642c4508781d31e1f268199dbd2ba0156cf'
TOOLS = Path(r'C:\Users\Haile\.codex\tools')
CODE = {
    'old': ('continue_saved_decode.py', '993ef94ac1f032fd44d880fc953238a4653d6777f9fba964bbb73aa1c12ff7d2'),
    'failed': ('continue_failed_transport.py', 'c9079969a868f0800ef22e681d4304424af9c738ed514755f3a3aaf968fa243e'),
    'decode': ('reconcile_failed_suffix.py', 'f285d228607c26cca0009d17626e7d6915f3d715e3b29f02784a25c682f4be68'),
    'generic': ('reconcile.py', 'fbedc8e50d08de7dff0547483f26c9fd081a8b4c9e62f0713609ce043e0fb34c'),
    'context': ('../hbq-matched-mfa-v1/context_reconciliation.py', '39ee7b9d54a16fa2384c68466c181a2e23d8f645f2ed09d17edd2e377bc54e35'),
    'collector': ('../hbq-matched-mfa-v1/collector.py', 'a4a7073ff5d24875fcc1d866b727792ebdafa4ad70df327691a72e17cbcacc94'),
    'metadata': ('../hbq-matched-hanna-20261004/prepare.py', '2d82e4959c3296ccaa6e6521adb46f85588427d429a544b36a2891ebaea8c7b0')}
PREFIX_SPEC = [{key: True for key in ('endpoint', 'endpoint_ordinal', 'logical_sample_id', 'request_sha256', 'native_identity', 'state')}]
ROW_SPEC = [{key: True for key in ('endpoint', 'endpoint_ordinal', 'logical_sample_id', 'request_sha256', 'prompt_sha256', 'schema_sha256')}]
RELEASE_SPEC = {'source_release': {
    'source': True, 'source_job_sha256': True, 'outer_terminal_sha256': True, 'outer_exit_code': True,
    'plan_sha256': True, 'source_outcomes_admitted': True, 'ambiguous_observations_resent': True,
    'started_terminal_inventory': [{key: True for key in ('native_identity', 'ordinal', 'retained_artifacts', 'state', 'terminal_sha256')}]}}


def pinned(path, sha):
    raw = path.read_bytes()
    require((meta(raw) == sha if isinstance(sha, dict) else digest(raw) == sha),
            'Exact MFA saved-prefix source differs: ' + path.name)
    return raw


def metadata_reader():
    relative, sha = CODE['metadata']
    pinned(HERE / relative, sha)
    return r.load('mfa_saved_prefix_private_metadata', HERE / relative).project_json


def reserve_once(prefix, rows, inventory):
    require(len(rows) == 434 and [row['endpoint_ordinal'] for row in rows] == list(range(1, 435)), 'Full434 original Grok geometry differs')
    require(len({row['logical_sample_id'] for row in rows}) == 434
            and len({row['request_sha256'] for row in rows}) == 434, 'Duplicate original request identity')
    require([entry['endpoint_ordinal'] for entry in prefix] == list(range(1, 148)), 'Frozen ancestor must reserve1..147')
    require([entry['ordinal'] for entry in inventory] == list(range(148, 307)), 'Stopped source must reserve148..306')
    result = deepcopy(prefix)
    for entry, row in zip(result, rows):
        require(entry['endpoint'] == row['endpoint'] == 'grok' and entry['logical_sample_id'] == row['logical_sample_id']
                and entry['request_sha256'] == row['request_sha256'], 'Ancestor original identity differs')
        entry.update(no_resend=True, new_votes=0, source_admission_replayed=False)
    for entry, row in zip(inventory, rows[147:306]):
        require(entry['state'] in {'accepted', 'semantic_rejected', 'ambiguous'}, 'Unknown source disposition')
        result.append(dict(row, state=entry['state'], native_identity=entry['native_identity'],
                           source_root_local_only=str(SOURCE), source_job_sha256=JOB_SHA,
                           source_terminal_sha256=entry['terminal_sha256'], source_inventory=deepcopy(entry['retained_artifacts']),
                           no_resend=True, new_votes=0, source_admission_replayed=False))
    require(len({entry['logical_sample_id'] for entry in result}) == 306
            and len({entry['request_sha256'] for entry in result}) == 306
            and len({entry['native_identity'] for entry in result}) == 306, 'Duplicate reserved original identity')
    require([entry['endpoint_ordinal'] for entry in result if entry['state'] == 'ambiguous'] == [131, 267, 301, 302, 303], 'Frozen unresolved source membership differs')
    return result


def build_plan():
    files = {'implementation/continue_mfa_saved_prefix_v2.py': Path(__file__).read_bytes()}
    for key, (relative, sha) in CODE.items():
        files['implementation/' + key + '.py'] = pinned(HERE / relative, sha)
    project = metadata_reader()
    parent_raw = pinned(PARENT, PARENT_SHA)
    parent = project(parent_raw, {'reserved_through': True, 'original_manifest_sha256': True,
                                 'endpoint_denominator': True, 'full_planned_denominator': True,
                                 'artifacts': True, 'prefix': PREFIX_SPEC})
    require(parent['reserved_through'] == 147 and parent['original_manifest_sha256'] == MANIFEST_SHA
            and parent['endpoint_denominator'] == 434 and parent['full_planned_denominator'] == 868, 'Ancestor contract differs')
    for name, pin in parent['artifacts'].items():
        require(meta((PARENT.parent / name).read_bytes()) == pin, 'Frozen ancestor artifact differs')
    manifest_raw = pinned(FROZEN / 'manifest.json', MANIFEST_SHA)
    manifest = project(manifest_raw, {'requests': ROW_SPEC, 'artifacts': True})
    require(len(manifest['requests']) == 868, 'Full868 matched geometry differs')
    for name, pin in manifest['artifacts'].items():
        require(meta((FROZEN / name).read_bytes()) == pin, 'Frozen source/prompt/schema/context artifact differs')
    rows = [row for row in manifest['requests'] if row['endpoint'] == 'grok']
    job_raw = pinned(SOURCE / 'job.json', JOB_SHA)
    job = json.loads(job_raw)
    require(job['manifest_sha256'] == MANIFEST_SHA and job['saved_decode_plan_sha256'] == PARENT_SHA
            and job['collector_sha256'] == CODE['old'][1] and job['policy'] == old.POLICY
            and job['reserved_prefix'] == 147 and job['timeout_seconds'] == 900 and job['automatic_retries'] == 0
            and job['payload_classification'] == 'public_repo' and job['full_planned_denominator'] == 868,
            'Stopped source execution binding differs')
    for key, relative in [('broker_sha256', 'model_work_queue/broker.py'),
                          ('account_probe_sha256', 'adaptive_settings/account_probe.py')]:
        pinned(TOOLS / relative, job[key])
    outer_raw = pinned(OUTER, OUTER_SHA)
    require(project(outer_raw, {'exit_code': True})['exit_code'] == 3, 'True source outer lifecycle is not terminal')
    release = project(pinned(RELEASE, RELEASE_SHA), RELEASE_SPEC)['source_release']
    inventory = release['started_terminal_inventory']
    require(digest(canonical(inventory)) == INVENTORY_SHA and release['source'] == 'mfa'
            and release['source_job_sha256'] == JOB_SHA and release['outer_terminal_sha256'] == OUTER_SHA
            and release['plan_sha256'] == PARENT_SHA and release['outer_exit_code'] == 3
            and release['source_outcomes_admitted'] is False and release['ambiguous_observations_resent'] is False,
            'Reviewed source release differs')
    expected = {f"{row['endpoint_ordinal']:04d}-{row['logical_sample_id'][:12]}" for row in rows[147:306]}
    require({path.name for path in SOURCE.iterdir() if path.is_dir()} == expected, 'Stopped source slot inventory differs')
    for entry, row in zip(inventory, rows[147:306]):
        sample = SOURCE / f"{row['endpoint_ordinal']:04d}-{row['logical_sample_id'][:12]}"
        pinned(sample / 'terminal.json', entry['terminal_sha256'])
        for name, sha in entry['retained_artifacts'].items():
            pinned(sample / name, sha)
        pinned(sample / 'prompt.txt', row['prompt_sha256'])
        pinned(sample / 'schema.json', row['schema_sha256'])
        started = project((sample / 'attempt-started.json').read_bytes(), {key: True for key in
                          ('manifest_sha256', 'logical_sample_id', 'prompt_sha256', 'schema_sha256', 'job_sha256', 'session_id', 'no_resend', 'attempt')})
        require(started == dict(manifest_sha256=MANIFEST_SHA, logical_sample_id=row['logical_sample_id'],
                               prompt_sha256=row['prompt_sha256'], schema_sha256=row['schema_sha256'], job_sha256=JOB_SHA,
                               session_id=entry['native_identity'], no_resend=True, attempt=1), 'Source started request/native binding differs')
        identity = project((sample / 'native-identity.json').read_bytes(), {'session_id': True, 'logical_sample_id': True})
        require(identity == {'session_id': entry['native_identity'], 'logical_sample_id': row['logical_sample_id']}, 'Source native identity differs')
    prefix = reserve_once(parent['prefix'], rows, inventory)
    files.update({'parent-plan.json': parent_raw, 'source-job.json': job_raw, 'source-lifecycle-terminal.json': outer_raw,
                  'source-release.json': canonical(release), 'original-manifest.json': manifest_raw})
    plan = {'schema_version': 1, 'policy': POLICY, 'study': 'mfa', 'endpoint': 'grok',
            'collector_sha256': digest(Path(__file__).read_bytes()), 'original_manifest_sha256': MANIFEST_SHA,
            'parent_plan_sha256': PARENT_SHA, 'source_job_sha256': JOB_SHA, 'source_lifecycle_sha256': OUTER_SHA,
            'source_release_invocation_sha256': RELEASE_SHA, 'source_release_inventory_sha256': INVENTORY_SHA,
            'reserved_through': 306, 'prefix': prefix, 'source_binding': job,
            'untouched_request_sha256s': [row['request_sha256'] for row in rows[306:]],
            'endpoint_denominator': 434, 'full_planned_denominator': 868,
            'timeout_seconds': 900, 'attempts_per_logical_sample': 1, 'automatic_retries': 0,
            'allowed_workers': [1, 10], 'project_endpoint_concurrency_limit': 10,
            'prospective_saved_completion_policy': 'saved_grok_observed_decode_stream_completed_projection_v1',
            'human_label_gate': 'all_original_planned_slots_verified_terminal_plus_explicit_postprediction_release_v1',
            'source_admissions_replayed': False, 'human_targets_opened': False, 'provider_calls': 0, 'new_votes': 0,
            'original_native_envelopes_reconstructed': False, 'physical_contact_cardinality_proven': False,
            'artifacts': {name: meta(raw) for name, raw in files.items()}}
    files['plan.json'] = canonical(plan)
    return plan, files


def verify_plan(path, sha):
    saved = json.loads(pinned(path, sha))
    for name, pin in saved['artifacts'].items():
        require(meta((path.parent / name).read_bytes()) == pin, 'Frozen MFA continuation artifact differs')
    actual, _ = build_plan()
    require(actual == saved, 'MFA prefix/source/runtime commitments differ')
    return saved


def validate_output(output, plan_root=None):
    protected = [r.REPO, FROZEN, SOURCE, PARENT.parent, RELEASE.parent, TOOLS, old.reader().SESSIONS]
    if plan_root:
        protected.append(plan_root)
    require(output.parent == BASE.resolve() and all(not output.is_relative_to(path.resolve())
            and not path.resolve().is_relative_to(output) for path in protected), 'Private output overlaps retained inputs')


def runtime_context():
    # No ancestor outcome replay: the old prefix remains reserved and unadmitted.
    context_path = HERE / CODE['context'][0]
    sys.path.insert(0, str(context_path.resolve().parent))
    context = r.load('mfa_saved_prefix_private_context', context_path)
    module = context.old
    require(digest(Path(module.__file__).read_bytes()) == CODE['collector'][1], 'Native collector differs')
    manifest, root, subset, validator = module.load_manifest(FROZEN / 'manifest.json', MANIFEST_SHA, TOOLS)
    runner = context.frozen_runner(root, manifest)
    return {'module': module, 'manifest': manifest, 'root': root, 'subset': subset,
            'validator': context.admission(root, manifest, validator, runner), 'tools': TOOLS,
            'saved_decode_reader': old.reader()}


def job_binding(plan, sha, workers, route, route_sha):
    binding = old.job_binding(plan, sha, workers, route, route_sha)
    binding.update(policy=POLICY, collector_sha256=digest(Path(__file__).read_bytes()),
                   mfa_saved_prefix_v2_plan_sha256=sha, source_release_inventory_sha256=INVENTORY_SHA,
                   source_release_invocation_sha256=RELEASE_SHA, source_lifecycle_sha256=OUTER_SHA,
                   source_admissions_replayed=False)
    return binding


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    sub = parser.add_subparsers(dest='mode', required=True)
    prep = sub.add_parser('prepare')
    prep.add_argument('--output-root', type=Path, required=True)
    prep.add_argument('--dry-run', action='store_true')
    run = sub.add_parser('collect')
    for name in ('plan', 'results-dir', 'route-root'):
        run.add_argument('--' + name, type=Path, required=True)
    run.add_argument('--plan-sha256', required=True)
    run.add_argument('--execution-route-sha256', required=True)
    run.add_argument('--workers', type=int, default=1)
    run.add_argument('--limit', type=int)
    action = run.add_mutually_exclusive_group(required=True)
    action.add_argument('--validate-only', action='store_true')
    action.add_argument('--execute-native', action='store_true')
    run.add_argument('--owner-global-headroom-verified', action='store_true')
    run.add_argument('--owner-current-route-verified', action='store_true')
    args = parser.parse_args()
    if args.mode == 'prepare':
        output = args.output_root.resolve()
        require(output == PLAN_ROOT.resolve() and not output.exists(), 'Only the fresh named MFAv2 plan is supported')
        validate_output(output)
        plan, files = build_plan()
        if not args.dry_run:
            for name, raw in files.items():
                write(output / name, raw)
        print(json.dumps({'state': 'provider_free_mfa_saved_prefix_v2', 'plan_sha256': digest(files['plan.json']),
                          'reserved_through': 306, 'untouched': 128, 'endpoint_planned': 434, 'planned': 868,
                          'reserved_ambiguous': [131, 267, 301, 302, 303], 'source_admissions_replayed': False,
                          'human_release_eligible': False, 'human_targets_opened': False, 'provider_calls': 0,
                          'new_votes': 0, 'output_written': not args.dry_run}))
        return 0
    require(args.limit is None or args.limit > 0, 'Positive contact limit required')
    plan = verify_plan(args.plan.resolve(), args.plan_sha256)
    output = args.results_dir.resolve()
    validate_output(output, args.plan.parent)
    route = f.select_execution_route(plan, args.route_root, args.execution_route_sha256)
    binding = job_binding(plan, args.plan_sha256, args.workers, route, args.execution_route_sha256)
    f.reviewed_route(binding, args.route_root)
    ctx = runtime_context()
    if args.validate_only:
        pending, states = old.inventory(plan, ctx, output, binding)
        print(json.dumps({'state': 'provider_free_validated', 'source_admissions_replayed': False,
                          **old.label_gate(plan, states, pending)}))
        return 0
    return old.collect(plan, ctx, output, binding, args.route_root, execute_native=args.execute_native,
                       headroom=args.owner_global_headroom_verified, route_confirmed=args.owner_current_route_verified,
                       limit=args.limit)


if __name__ == '__main__':
    raise SystemExit(main())
