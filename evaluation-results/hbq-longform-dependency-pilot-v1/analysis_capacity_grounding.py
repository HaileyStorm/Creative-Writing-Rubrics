"""Provider-free capacity-prefix binding for the retained P4 CRLF span policy."""
from collections import Counter, defaultdict
from types import SimpleNamespace
import argparse
import json
from pathlib import Path

import importlib.util

HERE = Path(__file__).resolve().parent


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ag = load('p4_capacity_retained_grounding', HERE / 'analysis_grounding.py')
cc = load('p4_capacity_retained_continuation', HERE.parent / 'hbq-native-transport-recovery-v1/continue_capacity.py')
c, g, a = ag.c, ag.g, ag.a
POLICY = 'p4_capacity_prefix_crlf_span_grounding_v1'
PLAN_SHA = 'e94d44e6854837cece048258432d849d2919b4a8bbe9e0498030c19d29b861fd'
JOB_SHA = '197d2f18e97a16041ebfe6c8983c328d4f5890c756044fd2e847640f1bb63ac4'
CONTINUATION_SHA = 'ed1db65b99275615cec36bb6a545cf284b1d2e4f085dfde26d8c1e7046493982'
GROUNDING_SHA = '3f2896d10a0a15b01fa603090483798fd77d9135bdeacee708fbed1a1931bf52'
GROUNDING_ANALYSIS_SHA = 'e0abb42a3a6e8d908db9801d8552c99912b2ca1b79dfb088f1ef42e5ed356de6'


def validate_membership(plan, manifest):
    rows = sorted((r for r in manifest['requests'] if r['endpoint'] == 'sol'), key=lambda r:r['endpoint_ordinal'])
    c.require(len(manifest['requests']) == plan['full_planned_denominator'] == 464 and len(rows) == plan['endpoint_denominator'] == 232,
              'Full original denominators differ')
    c.require([r['endpoint_ordinal'] for r in rows] == list(range(1, 233))
              and len({r['request_sha256'] for r in rows}) == 232, 'Original Sol slot identities differ')
    reserved = plan['reserved_through']
    c.require(reserved == 97 and len(plan['prefix']) == reserved, 'Reserved capacity prefix differs')
    c.require([(r['endpoint_ordinal'], r['logical_sample_id'], r['request_sha256']) for r in rows[:reserved]] ==
              [(r['endpoint_ordinal'], r['logical_sample_id'], r['request_sha256']) for r in plan['prefix']],
              'Reserved prefix membership differs')
    c.require([r['request_sha256'] for r in rows[reserved:]] == plan['untouched_request_sha256s'],
              'Untouched suffix membership/order differs')
    c.require(plan['capacity_failure_admitted'] is False and plan['failure_counts_as_missing'] is True
              and plan['prefix'][-1]['state'] == 'unadmitted_no_resend', 'Reserved failure cannot be admitted')
    return rows


def verify_capacity(plan_path, output):
    for path, pin in ((Path(cc.__file__), CONTINUATION_SHA), (Path(g.__file__), GROUNDING_SHA),
                      (Path(ag.__file__), GROUNDING_ANALYSIS_SHA), (HERE/'analysis.py', ag.ANALYSIS_SHA),
                      (a.UTILITY_PATH, a.UTILITY_SHA)):
        c.require(c.digest(path.read_bytes()) == pin, 'Retained implementation pin differs')
    # This owning verifier replays the frozen original prefix and its capacity proof.
    plan, ctx = cc.verify_plan(plan_path, PLAN_SHA)
    c.require(plan['config']['study'] == 'p4' and plan['original_manifest_sha256'] == a.MANIFEST_SHA
              and ctx['source']['collector_sha256'] == a.COLLECTOR_SHA, 'Capacity study/source differs')
    validate_membership(plan, ctx['manifest'])
    binding = cc.job_binding(plan, PLAN_SHA)
    raw = (output/'job.json').read_bytes()
    c.require(c.digest(raw) == JOB_SHA and json.loads(raw) == binding, 'Exact capacity continuation job differs')
    c.require(json.loads((output/'account-binding.json').read_bytes()) == c.t.account_receipt(binding),
              'Own capacity secondary account differs')
    expected = {c.sample_path(output,row).name for row in cc.suffix_rows(plan,ctx)}
    c.require({p.name for p in output.iterdir() if p.is_dir()} <= expected, 'Capacity output includes reserved/unknown slot')
    return plan, ctx, binding


def terminal_descendant(ctx, row, sample, terminal, job_sha):
    entry = {'endpoint':row['endpoint'], 'logical_sample_id':row['logical_sample_id'], 'request_sha256':row['request_sha256'],
             'original_sample_path':str(sample), 'job_sha256':job_sha,
             'strict_terminal_sha256':c.digest((sample/'terminal.json').read_bytes()), 'strict_terminal':terminal,
             'condition':row, 'grounding_state':'nonsettled_unadmitted', 'response':None, 'new_votes':0, 'no_resend':True}
    if terminal['state'] not in c.SETTLED:
        return entry
    response_raw = (sample/'response.json').read_bytes()
    original = json.loads(response_raw)
    sources, context, schema = ag.available_sources(ctx['root'],ctx['manifest'],row)
    derived = g.derive(original,row,sources,context,schema,ctx['subset'],ctx['validator'])
    c.require(derived['original_admission'] == json.loads((sample/'acceptance.json').read_bytes()),
              'Original admission differs after own replay')
    entry.update(original_response=original, original_response_file_sha256=c.digest(response_raw),
        source_commitments={key:{k:v for k,v in value.items() if k!='text'} |
                               {'sha256':c.digest(value['text'].encode())} for key,value in sources.items()},
        certificate={k:v for k,v in derived.items() if k!='response'},
        response=derived['response'], grounding_state=derived['state'])
    return entry


def collect_capacity(plan, ctx, output, binding):
    manifest = ctx['manifest']
    original = ctx['source_root']
    prefix = {e['request_sha256']:e for e in plan['prefix']}
    records, inventory, ledger = [], [], []
    identities = defaultdict(list)
    job_sha = c.digest((output/'job.json').read_bytes())
    for row in manifest['requests']:
        item = {'request':row, 'state':'not_supplied', 'strict_state':'not_supplied', 'grounding_state':'not_completed',
                'native_metrics':{field:None for field in (*a.TOKEN_FIELDS,'latency_seconds')}}
        if row['endpoint'] != 'sol':
            inventory.append(item)
            continue
        prior = prefix.get(row['request_sha256'])
        sample = c.sample_path(original if prior else output,row)
        if not prior and not sample.exists():
            item.update(state='untouched',strict_state='untouched')
        elif not prior and not (sample/'terminal.json').is_file():
            c.require(json.loads((sample/'condition.json').read_bytes()) == row, 'Occupied suffix condition differs')
            if (sample/'attempt-started.json').is_file():
                reader = SimpleNamespace(inputs=c.inputs,account_receipt=c.t.account_receipt)
                cc.r.validate_started(reader,sample,row,binding,a.MANIFEST_SHA,ctx['root'],manifest)
                item.update(state='started_unresolved',strict_state='started_unresolved')
            else:
                item.update(state='occupied_unresolved',strict_state='occupied_unresolved')
        else:
            try:
                if prior:
                    # verify_plan already replayed these native receipts once. Recheck
                    # retained file commitments before consuming that verified prefix.
                    for relative, pin in prior['source_inventory'].items():
                        c.pinned(sample,relative,pin)
                    terminal = json.loads((sample/'terminal.json').read_bytes())
                    c.require(c.digest((sample/'terminal.json').read_bytes()) == prior['source_terminal_sha256']
                              and terminal['state'] == prior['state'], 'Verified prefix terminal differs')
                    source_job_sha = plan['source_job_sha256']
                else:
                    terminal, _ = c.replay(sample,row,manifest,binding,ctx['root'],ctx['receipts'],ctx['subset'],ctx['validator'])
                    source_job_sha = job_sha
                item.update(state=terminal['state'],strict_state=terminal['state'],native_metrics=a.d.native_metrics(sample,row,terminal))
                entry = terminal_descendant(ctx,row,sample,terminal,source_job_sha)
                item['grounding_state'] = entry['grounding_state']
                if entry['response'] is not None:
                    item['state'] = 'accepted'
                    records.append({'request':row,'response':entry['response']})
                if terminal.get('native_thread_id'):
                    identities[terminal['native_thread_id']].append(item)
                ledger.append(entry)
            except (ValueError,OSError,KeyError,TypeError):
                item.update(state='replay_unadmitted',strict_state='replay_unadmitted',grounding_state='replay_unadmitted')
        inventory.append(item)
    duplicates = set()
    for items in identities.values():
        if len(items)>1:
            for item in items:
                duplicates.add(item['request']['request_sha256'])
                item.update(state='duplicate_native_unadmitted',grounding_state='duplicate_native_unadmitted')
    for entry in ledger:
        if entry['request_sha256'] in duplicates:
            entry.update(grounding_state='duplicate_native_unadmitted',response=None)
    return [r for r in records if r['request']['request_sha256'] not in duplicates],inventory,ledger


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('capacity-plan','capacity-results','controller-decision','output-root'):
        parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--dry-run',action='store_true')
    args = parser.parse_args()
    plan,ctx,binding = verify_capacity(args.capacity_plan.resolve(),args.capacity_results.resolve())
    c.p.base.output_preflight(args.output_root,(ctx['root'],ctx['source_root'],args.capacity_plan.parent,args.capacity_results,args.controller_decision,ctx['tools']))
    decision_raw,_ = ag.decision_input(args.controller_decision)
    records,inventory,ledger = collect_capacity(plan,ctx,args.capacity_results.resolve(),binding)
    report = ag.describe(ctx['manifest'],records,inventory,a.load_hbq(ctx['manifest'],ctx['root']),ctx['root'],ledger)
    report.update(capacity_adapter_policy=POLICY,capacity_plan_sha256=PLAN_SHA,capacity_job_sha256=JOB_SHA,
                  reserved_capacity_failure_admitted=False,unexamined_endpoint='grok')
    suffix = [i for i in inventory if i['request']['endpoint']=='sol' and i['request']['endpoint_ordinal']>plan['reserved_through']]
    profile = {'policy':POLICY,'grounding_policy':g.POLICY,'manifest_sha256':a.MANIFEST_SHA,'capacity_plan_sha256':PLAN_SHA,
        'capacity_job_sha256':JOB_SHA,'source_job_sha256':plan['source_job_sha256'],'reserved_through':plan['reserved_through'],
        'full_planned_denominator':464,'controller_decision_sha256':g.DECISION_SHA,'policy_contract_sha256':g.CONTRACT_SHA,
        'adapter_sha256':c.digest(Path(__file__).read_bytes()),'grounding_sha256':GROUNDING_SHA,
        'analysis_grounding_sha256':GROUNDING_ANALYSIS_SHA,'continuation_sha256':CONTINUATION_SHA,
        'inventory_sha256':c.digest(c.canonical(inventory)),'private_ledger_sha256':c.digest(c.canonical(ledger)),
        'report_sha256':c.digest(c.canonical(report)),'provider_calls':0,'new_votes':0,'human_targets_opened':False}
    files = {'report.json':c.canonical(report),'profile.json':c.canonical(profile),'private/inventory.json':c.canonical(inventory),
        'private/ledger.json':c.canonical(ledger),'private/capacity-plan.json':args.capacity_plan.read_bytes(),
        'private/capacity-job.json':(args.capacity_results/'job.json').read_bytes(),'private/controller-decision.json':decision_raw,
        'implementation/analysis_capacity_grounding.py':Path(__file__).read_bytes()}
    if not args.dry_run:
        for name,raw in files.items():c.p.base.write_new(c.within(args.output_root,name),raw)
    print(json.dumps({'dry_run':args.dry_run,'profile':profile,'strict_states':report['strict_states'],
        'grounding_states':report['grounding_states'],'suffix_strict_states':dict(Counter(i['strict_state'] for i in suffix)),
        'suffix_grounding_states':dict(Counter(i['grounding_state'] for i in suffix)),
        'quote_proof_states':report['quote_proof_states'],'descendant_rejection_errors':report['descendant_rejection_errors'],
        'admitted_requests':len(records),'output_written':not args.dry_run},sort_keys=True,allow_nan=False))
    return 0


if __name__=='__main__':raise SystemExit(main())
