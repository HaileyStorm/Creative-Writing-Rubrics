"""Collect frozen matched requests once; retain every attempt and stop on failure."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import threading
import uuid

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
TOOLS = Path(r'C:\Users\Haile\.codex\tools')
CUTOFF = datetime(2026, 10, 16, 5, 55, tzinfo=timezone.utc)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode('utf-8')


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def write_new(path, value):
    with path.open('x', encoding='utf-8', newline='\n') as handle:
        json.dump(value, handle, sort_keys=True, indent=2, allow_nan=False)
        handle.write('\n')


def read_pinned(root, relative, expected):
    path = (root / relative).resolve()
    if not path.is_relative_to(root):
        raise ValueError('Frozen input escapes manifest directory')
    raw = path.read_bytes()
    if digest(raw) != expected:
        raise ValueError(f'Frozen input hash differs: {relative}')
    return raw


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--results-dir', type=Path, required=True)
    parser.add_argument('--endpoint', choices=['grok', 'sol'], required=True)
    parser.add_argument('--route-root', type=Path)
    parser.add_argument('--secondary-helper', type=Path)
    parser.add_argument('--workers', type=int, default=1)
    parser.add_argument('--limit', type=int)
    parser.add_argument('--validate-only', action='store_true')
    args = parser.parse_args()
    cap = 10 if args.endpoint == 'grok' else 4
    if not 1 <= args.workers <= cap or (args.limit is not None and args.limit < 1):
        parser.error('Invalid concurrency or request limit')
    root = args.manifest.resolve().parent
    output = args.results_dir.resolve()
    if (output.is_relative_to(REPO) or REPO.is_relative_to(output)
            or output.is_relative_to(root) or root.is_relative_to(output)):
        raise ValueError('Private evidence must be outside repository and frozen inputs')
    raw_manifest = args.manifest.read_bytes()
    manifest = json.loads(raw_manifest)
    manifest_body = {k:v for k,v in manifest.items() if k!='manifest_content_sha256'}
    if digest(canonical(manifest_body)+b'\n') != manifest['manifest_content_sha256']:
        raise ValueError('Manifest content hash differs')
    for relative, metadata in manifest['artifacts'].items():
        if len(read_pinned(root,relative,metadata['sha256'])) != metadata['bytes']:
            raise ValueError('Frozen artifact length differs')
    rows = [row for row in manifest['requests'] if row['endpoint'] == args.endpoint]
    if not rows or len({row['logical_sample_id'] for row in rows}) != len(rows):
        raise ValueError('Endpoint requests are absent or duplicated')
    sys.path.insert(0, str(TOOLS))
    sys.path.insert(0, str(REPO / 'src'))
    from model_work_queue.adapters import json_schema_subset as subset
    implementation = manifest['implementation']
    for path, expected in (
        (HERE/'validate_response.py', implementation['semantic_validator_sha256']),
        (Path(subset.__file__), implementation['schema_subset_sha256']),
    ):
        if digest(path.read_bytes())!=expected:
            raise ValueError('Frozen admission implementation differs')
    validator = load_module('ttcw_response_validator', HERE / 'validate_response.py')
    # Validate every frozen request before any contact or job reservation.
    for row in rows:
        descriptor = {k:v for k,v in row.items() if k!='request_sha256'}
        if digest(canonical(descriptor)+b'\n') != row['request_sha256']:
            raise ValueError('Request descriptor hash differs')
        read_pinned(root, row['prompt_path'], row['prompt_sha256']).decode('utf-8')
        subset.validate_schema(json.loads(read_pinned(root, row['schema_path'], row['schema_sha256'])))
        for source in row['sources']:
            read_pinned(root, source['input_path'], source['sha256']).decode('utf-8')
    if args.validate_only:
        print(json.dumps({'state':'validated_without_contact', 'endpoint':args.endpoint, 'requests':len(rows), 'manifest_sha256':digest(raw_manifest)}))
        return 0
    output.mkdir(parents=True, exist_ok=True)
    route = broker = helper = None
    binding = {'manifest_sha256':digest(raw_manifest),'endpoint':args.endpoint,
        'workers':args.workers,
        'collector_sha256':digest(Path(__file__).read_bytes()),'validator_sha256':digest((HERE/'validate_response.py').read_bytes()),
        'zero_charge_only':True,'automatic_retries':0,'sampler':'native defaults; requested high; temperature unsupported'}
    if args.endpoint == 'grok':
        if not args.route_root:
            parser.error('Grok requires reviewed route root')
        from model_work_queue.broker import Broker
        broker = Broker(args.route_root.resolve())
        registry = json.loads((args.route_root/'routes.json').read_bytes())
        route = next(r for r in registry['routes'] if r['name']=='grok-build-grok-4.7')
        binding.update(route_sha256=digest(canonical(route)), model=route['model'], route=route,
            destination=route['destination'], payload_classification='public_repo', cutoff=CUTOFF.isoformat())
    else:
        if not args.secondary_helper:
            parser.error('Sol requires designated isolated-account helper')
        helper = load_module('cwr_secondary_account', args.secondary_helper.resolve())
        env = helper.collection_environment()
        os.environ.clear()
        os.environ.update(env)
        from adaptive_settings.account_probe import probe
        from hbqrs import runner, codex_receipts
        account = probe(helper.CLI)
        if account.get('account_type')!='chatgpt' or account.get('email','').lower()!='hailey2collet@gmail.com' or not account.get('probe_exit_confirmed'):
            raise ValueError('Designated secondary subscription account is unavailable')
        binding.update(model='gpt-6.1-sol', reasoning='high', destination='OpenAI ChatGPT subscription via native Codex exec',
            payload_classification='public_repo', helper_sha256=digest(args.secondary_helper.read_bytes()),
            runner_sha256=digest((REPO/'src/hbqrs/runner.py').read_bytes()), receipt_reader_sha256=codex_receipts.binding()['reader_sha256'],
            account_identity_sha256=digest(canonical({'type':account['account_type'],'email':account['email']})))
    job = output/'job.json'
    if job.exists():
        if json.loads(job.read_bytes()) != binding:
            raise ValueError('Job binding changed; preserve old job and use a separately reviewed continuation')
    else:
        write_new(job, binding)
    stop = threading.Event()

    def collect(row):
        sample = output/f"{row['endpoint_ordinal']:04d}-{row['logical_sample_id'][:12]}"
        created = False
        try:
            sample.mkdir(exist_ok=False)
            created = True
            write_new(sample/'condition.json', row)
            prompt = read_pinned(root,row['prompt_path'],row['prompt_sha256']).decode('utf-8')
            schema_raw = read_pinned(root,row['schema_path'],row['schema_sha256'])
            schema_path = sample/'schema.json'
            schema_path.write_bytes(schema_raw)
            session = str(uuid.uuid4()) if args.endpoint=='grok' else None
            write_new(sample/'native-identity.json',{'session_id':session,'logical_sample_id':row['logical_sample_id']})
            def before():
                if stop.is_set() or (args.endpoint=='grok' and datetime.now(timezone.utc)>=CUTOFF):
                    raise RuntimeError('Collection stopped before contact')
                write_new(sample/'attempt-started.json',{'state':'before_contact','time':datetime.now(timezone.utc).isoformat(),
                    'session_id':session,'no_resend':True})
            if args.endpoint=='grok':
                native = broker.run_grok_native_request(route['name'],{'prompt':prompt},output_schema=json.loads(schema_raw),
                    nonvisual_max_turns=1,session_id=session,before_contact=before,expected_route_sha256=binding['route_sha256'])
                write_new(sample/'native-result.json',native)
                if native['state']!='completed':
                    stop.set()
                    write_new(sample/'terminal.json',{'state':native['state'],'no_resend':True,'accepted':False})
                    return False
                record = native['result']
                answer = record['output']
                (sample/'native-envelope.json').write_bytes(broker.read_grok_native_envelope(record['native_envelope_artifact']))
            else:
                content, record = runner._call_codex(executable=str(helper.CLI),model='gpt-6.1-sol',reasoning='high',prompt=prompt,
                    output_dir=sample,response_schema=schema_path,batch_number=1,timeout=300,before_provider_attempt=before,
                    codex_receipt_policy='codex_native_rollout_v1')
                write_new(sample/'native-result.json',record)
                answer = json.loads(content)
            write_new(sample/'response.json',answer)
            texts = {s['id']:read_pinned(root,s['input_path'],s['sha256']).decode('utf-8') for s in row['sources']}
            acceptance = validator.semantic_validate(row['arm'],answer,row,texts,subset,
                context=(root/'context.txt').read_text(encoding='utf-8'),schema=json.loads(schema_raw))
            write_new(sample/'acceptance.json',acceptance)
            if not acceptance['accepted']:
                stop.set()
            write_new(sample/'terminal.json',{'state':'accepted' if acceptance['accepted'] else 'semantic_rejected',
                'accepted':acceptance['accepted'],'abstention':acceptance['abstention'],'no_resend':True,
                'native_result_sha256':digest((sample/'native-result.json').read_bytes()),
                'response_sha256':digest((sample/'response.json').read_bytes()),'acceptance_sha256':digest((sample/'acceptance.json').read_bytes())})
            return acceptance['accepted']
        except Exception as exc:
            stop.set()
            details = {'state':'unadmitted_no_resend','accepted':False,'error_class':type(exc).__name__,'error':str(exc),'no_resend':True}
            if hasattr(exc,'provider_record'):
                details['provider_record'] = exc.provider_record
            if created and not (sample/'terminal.json').exists():
                write_new(sample/'terminal.json',details)
            print(json.dumps({'state':'local_failure_preserved','sample':row['logical_sample_id'],'error_class':type(exc).__name__}),flush=True)
            return False

    pending = []
    for row in rows:
        sample = output/f"{row['endpoint_ordinal']:04d}-{row['logical_sample_id'][:12]}"
        if sample.exists():
            terminal = sample/'terminal.json'
            if (not terminal.is_file() or json.loads(terminal.read_bytes()).get('state')!='accepted'
                    or json.loads((sample/'condition.json').read_bytes())!=row):
                raise ValueError('Existing unresolved/rejected attempt requires reconciliation; no resend')
            receipt = json.loads(terminal.read_bytes())
            for name in ('response','acceptance'):
                if digest((sample/f'{name}.json').read_bytes())!=receipt[f'{name}_sha256']:
                    raise ValueError('Accepted attempt evidence changed')
            if digest((sample/'native-result.json').read_bytes()) != receipt['native_result_sha256']:
                raise ValueError('Accepted native evidence changed')
            native = json.loads((sample/'native-result.json').read_bytes())
            if args.endpoint=='sol':
                codex_receipts.verify(sample,native,prompt=read_pinned(root,row['prompt_path'],row['prompt_sha256']).decode('utf-8'),
                    model='gpt-6.1-sol',reasoning='high')
            else:
                envelope = (sample/'native-envelope.json').read_bytes()
                if digest(envelope)!=native['result']['native_envelope_artifact']['sha256']:
                    raise ValueError('Accepted Grok envelope changed')
        else:
            pending.append(row)
    if args.limit is not None:
        pending = pending[:args.limit]
    iterator = iter(pending)
    completed = accepted = 0
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        live = set()
        for _ in range(args.workers):
            row = next(iterator,None)
            if row is not None:
                live.add(pool.submit(collect,row))
        while live:
            done, live = wait(live,return_when=FIRST_COMPLETED)
            for future in done:
                completed += 1
                accepted += bool(future.result())
            while len(live)<args.workers and not stop.is_set():
                row = next(iterator,None)
                if row is None:
                    break
                live.add(pool.submit(collect,row))
            print(json.dumps({'completed_this_invocation':completed,'accepted_this_invocation':accepted,'in_flight':len(live),'stopped':stop.is_set()}),flush=True)
    return 3 if stop.is_set() else 0


if __name__=='__main__':
    raise SystemExit(main())
