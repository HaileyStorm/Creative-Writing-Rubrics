"""Native-once009 Grok execution; immutable prefix337 is metadata, not new votes."""
import argparse
from collections import Counter
import importlib.util
import json
from pathlib import Path
import sys
from threading import Event

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
PROGRAM = Path(r'C:\Users\Haile\Documents\cwr-resume-control-20260919-r1\successor-program-20261004')
LIFECYCLE = PROGRAM / 'ttcw-phase1/grok-suffix-009-lifecycle/full-001'
OWNER = '01a10839-a735-7bf2-a05a-68afadb52755'
POLICY = 'ttcw_untouched_suffix_execution_v5'
V4_SHA = 'c594953c0a9134c89ab60f28ae95143dcfef3d0594db0d7ae071184496d6ac20'
MANIFEST_SHA = 'b3ae25cbd36674bdffdedf4c4cf58a2e51be109b86f183b72b3b490d70dd0137'
CONTENT_SHA = '6b1965790c11b13c98c9b743c2c97dc544e944930d177b9fa10c91cdc58e71ac'
SOURCE_SHA = 'cce67e7abb0d44ffb4c9cfd972d112c5fd8712b1732fe0071cd5aaccaf9aaf4c'
SOURCE_JOB_SHA = 'df9b80b2d5a3c4e6650589ec0ade671948339f4206fa67e0dd726ac66a42b094'
INVENTORY_SHA = 'cd294287714c221e40d307f21206431534d4ca3b8372fe719e48a0293b8b1908'
RELEASE_SHA = '33e2b9b3216fdd8723ed708f63e4a7cf244b214dadadbadbfd76b4badc63a7c2'


def retained_interface():
    import hashlib
    path = HERE / 'collector_suffix_v4.py'
    if hashlib.sha256(path.read_bytes()).hexdigest() != V4_SHA:
        raise ValueError('Pinned v4 execution interface differs')
    spec = importlib.util.spec_from_file_location('ttcw009_isolated_v4', path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


v4 = retained_interface()
native = v4.base
native.MANIFEST_SHA, native.POLICY = MANIFEST_SHA, POLICY
require, sha, canonical, pinned, record = v4.require, v4.sha, v4.canonical, v4.pinned, v4.record
TOOLS, ROUTE_SHA = v4.TOOLS, v4.ROUTE_SHA


def guard(binding, output, halt, route_root=None, now=None):
    require(not (LIFECYCLE / 'STOP').exists(), 'Owning lifecycle STOP prevents dispatch/contact')
    return v4.guard(binding, output, halt, route_root, now)


native.guard = guard


def load_manifest(path, expected, endpoint='grok'):
    raw = path.read_bytes()
    require(endpoint == 'grok' and expected == MANIFEST_SHA == sha(raw), 'Exact009 Grok manifest required')
    manifest = json.loads(raw); root = path.resolve().parent
    require(sha(canonical({k:v for k,v in manifest.items() if k != 'manifest_content_sha256'}) + b'\n')
        == CONTENT_SHA == manifest['manifest_content_sha256'], '009 content differs')
    require(manifest['execution_authority'] is False and manifest['executor_contract']['execution_enabled'] is False
        and manifest['executor_contract']['actual_headroom_verified'] is False
        and manifest['executor_contract']['execution_route_sha256'] == ROUTE_SHA
        and manifest['executor_contract']['expiry_margin_seconds'] == 960, 'Preparation controls differ')
    artifacts = {name:pinned(root,name,pin['sha256']) for name,pin in manifest['artifacts'].items()}
    require(all(len(artifacts[name]) == pin['bytes'] for name,pin in manifest['artifacts'].items()), 'Artifact size differs')
    lineage = manifest['continuation']; parent_raw = artifacts['lineage/parent-manifest.json']; parent = json.loads(parent_raw)
    require(sha(parent_raw) == lineage['parent_manifest_sha256'], 'Original parent differs')
    for name in ('study_id','source_pins','runtime','context','implementation','public_asset_hashes','stories','sentinels','pairs','repeat_pair_ids'):
        require(manifest.get(name) == parent.get(name), 'Frozen scientific condition differs')
    require(parent['counts']['requests_total'] == 3108 and parent['counts']['requests_per_endpoint'] == 1554
        and parent['counts']['stories'] == len(manifest['stories']) == 36, 'Original denominators differ')
    require(manifest['artifacts'] == dict(parent['artifacts'], **{'lineage/parent-manifest.json':
        {'sha256':sha(parent_raw),'bytes':len(parent_raw)}}), 'Scientific artifact inventory differs')
    originals = [r for r in parent['requests'] if r['endpoint'] == 'grok']; rows = manifest['requests']
    receipts = lineage['prefix_receipts']; jobs = lineage['prefix_jobs']
    require([r['endpoint_ordinal'] for r in originals] == list(range(1,1555)) and rows == originals[337:]
        and len(rows) == manifest['counts']['requests_total'] == 1217 and lineage['reserved_endpoint'] == 'grok'
        and lineage['reserved_through_endpoint_ordinal'] == 337 and lineage['no_resend_reserved_prefix'] is True
        and lineage['source_manifest_sha256'] == SOURCE_SHA
        and [r['endpoint_ordinal'] for r in receipts] == list(range(1,338)), 'Reserved337/untouched338..1554 differs')
    for receipt,row in zip(receipts, originals):
        require(receipt['logical_sample_id'] == row['logical_sample_id'] and receipt['request_sha256'] == row['request_sha256']
            and receipt['no_resend'] is True and receipt['terminal_sha256'], 'Reserved qualified position differs')
    latest = jobs[-1]; inventory = latest['source_inventory']
    require(latest['manifest_sha256'] == SOURCE_SHA and latest['job_sha256'] == SOURCE_JOB_SHA
        and latest['collector_sha256'] == V4_SHA and latest['retained_release_invocation_sha256'] == RELEASE_SHA
        and latest['source_inventory_sha256'] == INVENTORY_SHA == sha(canonical(inventory) + b'\n')
        and [r['ordinal'] for r in inventory] == list(range(323,338)), 'Retained008 metadata commitment differs')
    inherited = jobs[-2]
    require(inherited['manifest_sha256'] == v4.SOURCE_MANIFEST_SHA and inherited['job_sha256'] == v4.SOURCE_JOB_SHA
        and inherited['source_inventory_sha256'] == v4.SOURCE_INVENTORY_SHA
        == sha(canonical(inherited['source_inventory']) + b'\n')
        and inherited['retained_release_invocation_sha256'] == v4.RELEASE_INVOCATION_SHA, 'Inherited322 proof differs')
    for retained,receipt in zip(inventory,receipts[322:]):
        require(retained['logical_sample_id'] == receipt['logical_sample_id'] and retained['request_sha256'] == receipt['request_sha256']
            and retained['metadata_pins']['terminal.json']['sha256'] == receipt['terminal_sha256']
            and retained['state_metadata_only'] == receipt['terminal_state']
            and retained['native_identity_sha256'] == receipt['native_session_id_sha256'], 'Retained008 receipt membership differs')
    sys.path.insert(0,str(TOOLS))
    from model_work_queue.adapters import json_schema_subset as subset
    require(sha(Path(subset.__file__).read_bytes()) == manifest['implementation']['schema_subset_sha256']
        and sha((HERE/'validate_response.py').read_bytes()) == manifest['implementation']['semantic_validator_sha256'], 'Admission source differs')
    validator = native.load_module('ttcw009_semantic_validator', HERE/'validate_response.py')
    for row in rows:
        require(sha(canonical({k:v for k,v in row.items() if k != 'request_sha256'}) + b'\n') == row['request_sha256'], 'Request descriptor differs')
        for kind in ('prompt','schema'):
            raw = artifacts[row[kind+'_path']]
            require(sha(raw) == row[kind+'_sha256'] and len(raw) == row[kind+'_bytes'], 'Request payload differs')
        subset.validate_schema(json.loads(artifacts[row['schema_path']]))
        require(all(sha(artifacts[s['input_path']]) == s['sha256'] for s in row['sources']), 'Original source commitment differs')
    return manifest,root,rows,subset,validator


def job_binding(manifest, workers, headroom, route, owner_attestations=None, owner_invocation_sha256=None):
    require(manifest['continuation']['reserved_through_endpoint_ordinal'] == 337 and len(manifest['requests']) == 1217,
        '009 execution geometry required')
    binding = native.job_binding(manifest,'grok',workers,headroom,route)
    binding.update(collector_policy=POLICY,collector_sha256=sha(Path(__file__).read_bytes()),
        manifest_sha256=MANIFEST_SHA,manifest_content_sha256=CONTENT_SHA,reserved_through_endpoint_ordinal=337,
        selected_requests_per_endpoint=1217,first_endpoint_ordinal=338,last_endpoint_ordinal=1554,original_stories=36,
        retained_v4_collector_sha256=V4_SHA,native_base_collector_sha256=v4.NATIVE_BASE_SHA,
        persistence_guard_policy=v4.PERSISTENCE_GUARD_POLICY,minimum_free_disk_bytes=v4.MINIMUM_FREE_DISK_BYTES,
        owner_lifecycle_root=str(LIFECYCLE),owner_lifecycle_invocation_sha256=owner_invocation_sha256,
        owner_attestations=owner_attestations or {}, own_lifecycle_binding_verified=owner_invocation_sha256 is not None,
        returned_allocation_natively_verified=False, source_prefix_admissions_replayed=False,new_votes_from_prefix=0)
    return binding


def collect_one(row,binding,root,output,subset,validator,halt,route_root,broker):
    require(row['endpoint'] == 'grok' and 338 <= row['endpoint_ordinal'] <= 1554, 'Reserved/foreign row cannot contact')
    guard(binding,output,halt,route_root)
    return native.collect_one(row,binding,root,output,subset,validator,halt,route_root,broker)


def replay(sample,row,binding,root,subset,validator,receipts=None):
    require(binding['collector_policy'] == POLICY and binding['collector_sha256'] == sha(Path(__file__).read_bytes())
        and binding['manifest_sha256'] == MANIFEST_SHA and binding['reserved_through_endpoint_ordinal'] == 337
        and row['endpoint'] == 'grok' and 338 <= row['endpoint_ordinal'] <= 1554, '009 replay binding differs')
    return native.replay(sample,row,binding,root,subset,validator,receipts)


def main():
    parser = argparse.ArgumentParser(description=__doc__,allow_abbrev=False)
    for name in ('manifest','results-dir','route-root'):parser.add_argument('--'+name,type=Path,required=True)
    for name in ('manifest-sha256','route-sha256'):parser.add_argument('--'+name,required=True)
    for name in ('workers','endpoint-headroom'):parser.add_argument('--'+name,type=int,required=True)
    parser.add_argument('--owner-lifecycle-root',type=Path)
    attestations = ('global-headroom-verified','returned-allocation-verified','current-route-verified','outbound-disclosure-confirmed')
    for name in attestations:parser.add_argument('--owner-'+name,action='store_true')
    mode=parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--validate-only',action='store_true');mode.add_argument('--execute-native',action='store_true')
    args=parser.parse_args(); output=args.results_dir.resolve()
    require(not output.exists(), 'Fresh009 results required; occupied slots never resent')
    for source in (REPO,args.manifest.resolve().parent):
        require(not output.is_relative_to(source) and not source.is_relative_to(output), 'Results overlap retained inputs')
    if args.validate_only:
        sys.addaudithook(lambda event,values:require(event not in ('subprocess.Popen','os.system','os.posix_spawn'),'No contact/launch during validation'))
    manifest,root,rows,subset,validator=load_manifest(args.manifest,args.manifest_sha256)
    route=native.reviewed_route(args.route_root,args.route_sha256)
    owner={name.replace('-','_'):getattr(args,'owner_'+name.replace('-','_')) for name in attestations}
    owner_sha=None
    if args.execute_native:
        require(all(owner.values()) and args.owner_lifecycle_root is not None
            and args.owner_lifecycle_root.resolve() == LIFECYCLE.resolve(), 'Exact approved owning lifecycle required')
        raw=(LIFECYCLE/'invocation.json').read_bytes();inv=json.loads(raw)
        require(inv['owner'] == OWNER and inv['collector_sha256'] == sha(Path(__file__).read_bytes())
            and inv['manifest_sha256'] == MANIFEST_SHA and inv['argv'][2:] == sys.argv
            and inv['owner_attestations'] == owner, 'Actual native argv/owner binding differs')
        start=json.loads((LIFECYCLE/'run-started.json').read_bytes())
        require(start['invocation_sha256'] == sha(raw) and start['argv'] == inv['argv'] and start['no_resend'] is True,
            'Own supervisor start differs');owner_sha=sha(raw)
    binding=job_binding(manifest,args.workers,args.endpoint_headroom,route,owner,owner_sha)
    guard(binding,output,Event(),args.route_root)
    if args.validate_only:
        print(json.dumps({'state':'validated_without_contact','policy':POLICY,'collector_sha256':binding['collector_sha256'],
            'manifest_sha256':MANIFEST_SHA,'manifest_content_sha256':CONTENT_SHA,'job_binding_sha256':sha(canonical(binding)),
            'requests':len(rows),'reserved_through':337,'original_requests_total':3108,'original_stories':36,
            'workers':args.workers,'available_headroom_verified':False,'own_lifecycle_binding_verified':False,
            'provider_calls':0,'account_probe_performed':False,'outputs_written':False,'human_labels_read':False},sort_keys=True));return 0
    from model_work_queue.broker import Broker
    broker=Broker(args.route_root);guard(binding,output,Event(),args.route_root)
    output.mkdir(parents=True,exist_ok=False);record(output/'job.json',binding)
    states,stopped=native.dispatch(rows,output,args.workers,
        lambda row,halt:collect_one(row,binding,root,output,subset,validator,halt,args.route_root,broker),
        lambda halt:guard(binding,output,halt,args.route_root))
    record(output/'dispatch-terminal.json',{'policy':POLICY,'job_sha256':sha((output/'job.json').read_bytes()),
        'owner_lifecycle_invocation_sha256':owner_sha,'workers':args.workers,'states':states,'stopped':stopped,
        'inflight_at_terminal':0,'automatic_retries':0,'human_release_eligible':False})
    return 3 if stopped else 0


if __name__ == '__main__':raise SystemExit(main())
