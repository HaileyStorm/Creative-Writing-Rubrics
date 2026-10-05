"""Provider-free P4 CRLF span descendants, separately committed from strict history."""
from __future__ import annotations

import argparse
from collections import Counter,defaultdict
import json
from pathlib import Path
import importlib.util

HERE = Path(__file__).resolve().parent
def load(name,path):
    spec = importlib.util.spec_from_file_location(name,path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module); return module
a = load('p4_grounding_retained_analysis',HERE/'analysis.py')
g = load('p4_grounding_span_policy',HERE/'grounding.py')
c = a.c
ANALYSIS_SHA = '08b551ceaa864af7927a78986a2d7e96ac73916591077eda553190a1b4732e5a'


def decision_input(path):
    raw = path.read_bytes(); decision = json.loads(raw)
    c.require(c.digest(raw)==g.DECISION_SHA and decision['policy']==g.POLICY
        and decision['manifest_sha256']==a.MANIFEST_SHA and decision['prefix_informed'] is True,
        'Exact post-prefix controller decision differs')
    return raw,decision


def available_sources(root,manifest,row):
    _,schema,texts,context = c.inputs(root,manifest,row)
    source = row['sources'][0]
    sources = {'available':{'text':texts[row['work_id']],'path':source['input_path']},
        'task_context':{'text':context,'path':row['task_context']['path']}}
    if row['context_arm']=='raw_full':
        index_path = 'source-index/indexes/'+row['work_id']+'.json'
        index = json.loads(c.pinned(root,index_path,manifest['artifacts'][index_path]))
        original_path = 'source-fetch/'+index['source_file']
        raw = c.pinned(root,original_path,manifest['artifacts'][original_path])
        text = sources['available']['text']
        c.require(raw[index['source_byte'][0]:index['source_byte'][1]]==text.encode('utf-8')
            and raw.decode('utf-8-sig')[index['source_char'][0]:index['source_char'][1]]==text,
            'Original narrative source coordinates differ')
        sources['available']['original_coordinates'] = {'path':original_path,'sha256':c.digest(raw),
            'char_start':index['source_char'][0],'byte_start':index['source_byte'][0]}
    return sources,context,json.loads(schema)


def collect_descendants(manifest,manifest_sha,root,results,tools,subset,validator,receipts):
    records,inventory,ledger = [],[],[]; identities = defaultdict(list)
    for endpoint in c.p.ENDPOINTS:
        output = results[endpoint]; binding,valid = None,True
        if output.exists():
            try:
                binding = json.loads((output/'job.json').read_bytes())
                c.require(binding==c.job_binding(manifest,root,manifest_sha,endpoint,tools,binding.get('route'),a.COLLECTOR_SHA)
                    and c.digest((output/'frozen-manifest.json').read_bytes())==manifest_sha,'Own job/raw manifest differs')
                if endpoint=='sol': c.require(json.loads((output/'account-binding.json').read_bytes())==c.t.account_receipt(binding),'Own account differs')
            except (ValueError,OSError,KeyError,TypeError): valid=False
        for row in (r for r in manifest['requests'] if r['endpoint']==endpoint):
            sample = c.sample_path(output,row)
            item = {'request':row,'state':'untouched','strict_state':'untouched','grounding_state':'not_completed',
                'native_metrics':{field:None for field in (*a.TOKEN_FIELDS,'latency_seconds')}}
            entry = None
            if not valid: item.update(state='job_unadmitted',strict_state='job_unadmitted')
            elif not sample.exists(): pass
            elif not (sample/'terminal.json').is_file(): item.update(state='started_unresolved',strict_state='started_unresolved')
            else:
                try:
                    terminal,answer = c.replay(sample,row,manifest,binding,root,receipts,subset,validator)
                    item.update(state=terminal['state'],strict_state=terminal['state'],native_metrics=a.d.native_metrics(sample,row,terminal))
                    if terminal.get('native_thread_id'): identities[(endpoint,terminal['native_thread_id'])].append(item)
                    entry = {'endpoint':endpoint,'logical_sample_id':row['logical_sample_id'],'request_sha256':row['request_sha256'],
                        'original_sample_path':str(sample),'job_sha256':c.digest((output/'job.json').read_bytes()),
                        'strict_terminal_sha256':c.digest((sample/'terminal.json').read_bytes()),'strict_terminal':terminal,
                        'condition':row,'grounding_state':'nonsettled_unadmitted','response':None}
                    if terminal['state'] in c.SETTLED:
                        response_raw = (sample/'response.json').read_bytes()
                        original = json.loads(response_raw)
                        sources,context,schema = available_sources(root,manifest,row)
                        derived = g.derive(original,row,sources,context,schema,subset,validator)
                        c.require(derived['original_admission']==json.loads((sample/'acceptance.json').read_bytes()),'Original admission differs after replay')
                        entry.update(original_response=original,original_response_file_sha256=c.digest(response_raw),
                            source_commitments={key:{k:v for k,v in value.items() if k!='text'}|{'sha256':c.digest(value['text'].encode('utf-8'))} for key,value in sources.items()},
                            certificate={k:v for k,v in derived.items() if k!='response'},response=derived['response'],grounding_state=derived['state'])
                        item['grounding_state'] = derived['state']
                        if derived['response'] is not None:
                            item['state']='accepted'; records.append({'request':row,'response':derived['response']})
                    ledger.append(entry)
                except (ValueError,OSError,KeyError,TypeError):
                    item.update(state='replay_unadmitted',strict_state='replay_unadmitted',grounding_state='replay_unadmitted')
            inventory.append(item)
    duplicates = set()
    for items in identities.values():
        if len(items)>1:
            for item in items:
                item.update(state='duplicate_native_unadmitted',grounding_state='duplicate_native_unadmitted')
                duplicates.add(item['request']['request_sha256'])
    for entry in ledger:
        if entry['request_sha256'] in duplicates: entry.update(grounding_state='duplicate_native_unadmitted',response=None)
    return [r for r in records if r['request']['request_sha256'] not in duplicates],inventory,ledger


def describe(manifest,records,inventory,hbq,root,ledger=()):
    report = a.analyze(manifest,records,inventory,hbq,root)
    report.update(analysis_policy=g.POLICY,retained_descriptive_analysis_policy=a.POLICY,
        strict_states=dict(Counter(i['strict_state'] for i in inventory)),
        grounding_states=dict(Counter(i['grounding_state'] for i in inventory)),
        policy_contract=g.CONTRACT,policy_contract_sha256=g.CONTRACT_SHA,controller_decision_sha256=g.DECISION_SHA,
        post_prefix_exploratory=True,separate_human_approval_claim=False,provider_calls=0,new_votes=0,
        logical_observations=len(records),strict_accepted_inherited=sum(i['grounding_state']=='strict_accepted_inherited' for i in inventory),
        projected_accepted=sum(i['grounding_state']=='projected_accepted' for i in inventory))
    report['quote_proof_states']=dict(Counter(q['state'] for entry in ledger for q in entry.get('certificate',{}).get('quotes',[])))
    report['descendant_rejection_errors']=dict(Counter(error for entry in ledger if entry['grounding_state']=='descendant_rejected'
        for error in entry['certificate']['descendant_admission']['errors']))
    for profile in report['profiles']:
        profile['grounding_policy']=g.POLICY
        profile['grounding_context_commitment_sha256']=c.digest(c.canonical({'manifest_sha256':a.MANIFEST_SHA,
            'controller_decision_sha256':g.DECISION_SHA,'policy_contract_sha256':g.CONTRACT_SHA}))
    report['limitations'].extend(['Post-prefix exploratory source-grounding descendant; original exact-quotation compliance and strict terminals remain unchanged.',
        'Only CRLF-to-LF or CRLF-to-one-ASCII-space contiguous spans; differing recovered spans remain unadmitted.',
        'Recovered source spans establish quotation provenance, not literary correctness, interpretation, human alignment or promotion.'])
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('manifest','tools-root','grok-results','sol-results','controller-decision','output-root'):
        parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--manifest-sha256',required=True); parser.add_argument('--dry-run',action='store_true')
    args = parser.parse_args(); results = {'sol':args.sol_results.resolve(),'grok':args.grok_results.resolve()}
    c.p.base.output_preflight(args.output_root,(args.manifest.resolve().parent,*results.values(),args.controller_decision,args.tools_root))
    c.require(args.manifest_sha256==a.MANIFEST_SHA and c.digest((HERE/'analysis.py').read_bytes())==ANALYSIS_SHA
        and c.digest(a.UTILITY_PATH.read_bytes())==a.UTILITY_SHA,'Retained analysis/manifest/utility pin differs')
    decision_raw,_ = decision_input(args.controller_decision)
    manifest,root,subset,validator,receipts = c.load_manifest(args.manifest,args.manifest_sha256,a.COLLECTOR_SHA,args.tools_root.resolve())
    records,inventory,ledger = collect_descendants(manifest,args.manifest_sha256,root,results,args.tools_root.resolve(),subset,validator,receipts)
    report = describe(manifest,records,inventory,a.load_hbq(manifest,root),root,ledger)
    profile = {'policy':g.POLICY,'manifest_sha256':args.manifest_sha256,'controller_decision_sha256':g.DECISION_SHA,
        'policy_contract_sha256':g.CONTRACT_SHA,'grounding_sha256':c.digest((HERE/'grounding.py').read_bytes()),
        'analysis_grounding_sha256':c.digest(Path(__file__).read_bytes()),'retained_analysis_sha256':ANALYSIS_SHA,
        'collector_sha256':a.COLLECTOR_SHA,'source_artifacts_commitment_sha256':c.digest(c.canonical(manifest['artifacts'])),
        'private_ledger_sha256':c.digest(c.canonical(ledger)),'inventory_sha256':c.digest(c.canonical(inventory)),
        'report_sha256':c.digest(c.canonical(report)),'provider_calls':0,'new_votes':0}
    files = {'report.json':c.canonical(report),'profile.json':c.canonical(profile),'private/ledger.json':c.canonical(ledger),
        'private/inventory.json':c.canonical(inventory),'private/original-manifest.json':args.manifest.read_bytes(),
        'private/controller-decision.json':decision_raw,'implementation/grounding.py':(HERE/'grounding.py').read_bytes(),
        'implementation/analysis_grounding.py':Path(__file__).read_bytes()}
    if not args.dry_run:
        for name,raw in files.items(): c.p.base.write_new(c.within(args.output_root,name),raw)
    print(json.dumps({'dry_run':args.dry_run,'profile':profile,'planned':manifest['counts'],
        'strict_states':report['strict_states'],'grounding_states':report['grounding_states'],
        'quote_proof_states':report['quote_proof_states'],'descendant_rejection_errors':report['descendant_rejection_errors'],
        'admitted_requests':len(records),'full_bank_scalars':sum(p.get('value') is not None and p['arm']=='hbq' for p in report['profiles']),
        'artifact_bytes':sum(len(raw) for raw in files.values()),'output_written':not args.dry_run},sort_keys=True,allow_nan=False))
    return 0


if __name__=='__main__': raise SystemExit(main())
