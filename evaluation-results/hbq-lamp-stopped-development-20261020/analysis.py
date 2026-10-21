"""Retrospective ordinal development analysis of the retained LAMP 032 prefix."""
import argparse
import ast
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

PINS = {
    'manifest': '480aa86df271078e322ac85cf8cfe5fe6ed02344138e218900cfe03c069b6ab6',
    'profiles': 'aa6a9e809f53e6640497e7fa3d5efe6f583426b794a90f031832562cb7354a69',
    'records': '72ad3b80421137f29e36f85efab1d8b8314bc2d1a67dd550959befb0cb052325',
    'parent_report': 'f7e9601fd69ba0d2df534e4cef904599661abf37eb5c73cafb0f4c2dae10ad5e',
    'human_profile': 'cd90bc17ae1ea1e0f2113f7c2b497eb47c59962a8891a91c1883bb3865b121e5',
    'original_analysis': 'de4e20855e346232a0de7f7fbbc83b6f85b9982fc992821cfe962344e6c4d856',
}
ARMS = ('hbq', 'ttcw14', 'holistic', 'compact', 'oregon')


def require(ok, why):
    if not ok:
        raise ValueError(why)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False) + '\n').encode('utf-8')


def checked(path, pin, size=None):
    path = Path(path).absolute()
    for node in (path, *path.parents):
        require(not node.is_symlink() and not (node.stat().st_file_attributes & 0x400 if hasattr(node.stat(), 'st_file_attributes') else False), 'Unsafe input ancestry')
    raw = path.read_bytes()
    require(digest(raw) == pin and (size is None or len(raw) == size), 'Input commitment differs')
    return raw


def within(root, name):
    path = Path(root).absolute() / name
    require(not Path(name).is_absolute() and '..' not in Path(name).parts, 'Relative source path required')
    require(path.is_relative_to(Path(root).absolute()), 'Source path escaped root')
    return path


def load_ordinal_helpers(raw):
    # Reuse only pure lineage/rank decoders. The original study entrypoint and
    # its all-17808-terminal release gate remain unchanged and are never run.
    names = {'decode_rankings', 'load_human_orders', 'human_ballots'}
    tree = ast.parse(raw)
    functions = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
    require({node.name for node in functions} == names, 'Original ordinal helpers differ')
    c = SimpleNamespace(require=require, digest=digest, canonical=canonical,
                        p=SimpleNamespace(POLICY='matched_lamp_source_only_v1', checked=checked, within=within))
    c.pinned = lambda root, name, meta: checked(within(root, name), meta['sha256'], meta['bytes'])
    namespace = {'c': c, 'json': json, 'defaultdict': defaultdict}
    exec(compile(ast.Module(body=functions, type_ignores=[]), 'frozen_lamp_ordinal_helpers', 'exec'), namespace)
    return namespace


def direction(left, right):
    return (left > right) - (left < right)


def agreement(ballots, predictions, planned=282):
    credit2 = ballot_credit2 = ties = unanimous = 0
    for pid, prediction in predictions.items():
        require(prediction in (-1, 0, 1), 'Invalid predicted direction')
        votes = [value for _, value in ballots[pid]]
        preferred = 1 if sum(votes) > 0 else -1
        credit2 += 1 if prediction == 0 else 2 * (prediction == preferred)
        ballot_credit2 += sum(1 if prediction == 0 else 2 * (prediction == vote) for vote in votes)
        ties += prediction == 0
        unanimous += len(set(votes)) == 1
    n = len(predictions)
    require(n <= planned, 'Observed direction denominator exceeds plan')
    return {
        'observed_pairs': n, 'planned_pairs': planned, 'missing_pairs': planned - n,
        'model_ties': ties, 'tie_credit': 0.5,
        'majority_half_credit_total': credit2 / 2,
        'majority_agreement': credit2 / (2 * n) if n else None,
        'majority_arithmetic_full_denominator_bounds': [credit2 / (2 * planned), (credit2 / 2 + planned - n) / planned],
        'individual_correlated_ballots': 3 * n,
        'individual_half_credit_total': ballot_credit2 / 2,
        'individual_agreement': ballot_credit2 / (6 * n) if n else None,
        'individual_arithmetic_full_denominator_bounds': [ballot_credit2 / (6 * planned), (ballot_credit2 / 2 + 3 * (planned - n)) / (3 * planned)],
        'observed_pairs_with_unanimous_humans': unanimous,
        'state': 'INCONCLUSIVE_PARTIAL_RETROSPECTIVE_DEVELOPMENT',
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('frozen', 'prefix', 'human-profile', 'original-analysis', 'control', 'freeze', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    source_sha = digest(Path(__file__).read_bytes())
    freeze_raw = args.freeze.read_bytes()
    freeze = json.loads(freeze_raw)
    require(freeze['analysis_source_sha256'] == source_sha and freeze['inputs'] == PINS, 'Descendant analysis freeze differs')
    require(freeze['state'] == 'RETROSPECTIVE_DEVELOPMENT_DESCENDANT_FROZEN_BEFORE_LOCAL_TARGET_DECODE', 'Wrong descendant contract')
    manifest = json.loads(checked(args.frozen/'manifest.json', PINS['manifest']))
    parent = json.loads(checked(args.prefix/'report.json', PINS['parent_report']))
    profiles = json.loads(checked(args.prefix/'private-bank-profiles.json', PINS['profiles']))
    records = json.loads(checked(args.prefix/'private-admitted-records.json', PINS['records']))
    human_profile = json.loads(checked(args.human_profile, PINS['human_profile']))
    helpers = load_ordinal_helpers(checked(args.original_analysis, PINS['original_analysis']))
    require(human_profile['all_strata_already_development'] and human_profile['human_scalar_scale'] is None,
            'Only already-development ordinal references are in scope')
    require(human_profile['manifest_sha256'] == PINS['manifest'] and parent['manifest_sha256'] == PINS['manifest'], 'Study source mismatch')
    require(parent['admitted_records'] == len(records) == 1149 and parent['source_states'] == {'accepted':1149,'semantic_rejected':4,'empty_terminal':2}, 'Prefix count differs')
    requests = {(r['endpoint'], r['endpoint_ordinal']):r for r in manifest['requests']}
    require(len(requests) == 17808, 'Original request geometry differs')
    seen = set()
    for record in records:
        row = record['request']; key = (row['endpoint'], row['endpoint_ordinal'])
        require(row['endpoint'] == 'sol' and key not in seen and row == requests[key]
                and record['native_and_semantic_admitted'], 'Admitted prediction join differs')
        seen.add(key)
    pairs = {row['pair_id']: row for row in manifest['selection']['pairs']}
    groups = {row['id']: row for row in manifest['selection']['groups']}
    require(len(groups) == 94 and len(pairs) == 282, 'Ordinal pair geometry differs')
    banks = {tuple(row['key']):row['profile'] for row in profiles}
    require(len(banks) == len(profiles), 'Duplicate saved profile identity')
    predictions = {}
    numeric = {}
    for arm in ARMS:
        numeric[arm] = {key[2]:p['score'] for key,p in banks.items()
                        if key[0:2] == ('sol',arm) and key[3] == 0 and p.get('score') is not None}
        if arm == 'hbq':
            require(len(numeric[arm]) == 38 and all(banks[('sol',arm,aid,0)]['state'] == 'SCORED'
                    and len(banks[('sol',arm,aid,0)]['leaves']) == 170 for aid in numeric[arm]), 'Complete HBQ bank inclusion differs')
        predictions[arm] = {pid:direction(numeric[arm][p['left']], numeric[arm][p['right']])
                            for pid,p in pairs.items() if p['left'] in numeric[arm] and p['right'] in numeric[arm]}
    orders = {}
    order_states = Counter()
    for record in records:
        row,answer = record['request'],record['response']
        if row['arm'] != 'pairwise' or row['repeat'] != 0:
            continue
        pid = row['pair_id']; key = (pid,row['orientation']); pair = pairs[pid]
        require(key not in orders and row['orientation'] in ('AB','BA'), 'Duplicate or unknown pair order')
        require({s['id'] for s in row['sources']} == {pair['left'],pair['right']}, 'Pair orientation membership differs')
        winner = answer['winner']; order_states[winner] += 1
        require(winner in ('A','B','TIE','CANNOT_ASSESS'), 'Unknown pair winner')
        chosen = next((s['id'] for s in row['sources'] if s['side'] == winner), None)
        require(winner in ('TIE','CANNOT_ASSESS') or chosen in (pair['left'],pair['right']), 'Unknown selected story side')
        orders[key] = None if winner == 'CANNOT_ASSESS' else 0 if winner == 'TIE' else 1 if chosen == pair['left'] else -1
    consensus = {}; order_conflicts = 0
    for pid in pairs:
        left,right = orders.get((pid,'AB')), orders.get((pid,'BA'))
        if left is None or right is None:
            continue
        consensus[pid] = direction(left+right,0)
        order_conflicts += left != right
    predictions['pairwise_consensus'] = consensus
    # This durable intent and all exact prediction inputs precede target decoding.
    args.output.mkdir(parents=False, exist_ok=False)
    intent = {'schema_version':1,'state':'OPEN_ALREADY_DEVELOPMENT_ORDINAL_REFERENCES_UNDER_DESCENDANT',
              'analysis_freeze_sha256':digest(freeze_raw),'prediction_sha256':{k:PINS[k] for k in ('profiles','records','parent_report','manifest')},
              'unused_or_blinded_claim':False,'original_gate_pass_claim':False,
              'human_target_sha256':[row['sha256'] for row in human_profile['targets']]}
    with (args.output/'target-opening-intent.json').open('xb') as stream:
        stream.write((json.dumps(intent,indent=2)+'\n').encode())
    human_orders = helpers['load_human_orders'](manifest,args.frozen,args.control,human_profile)
    ballots = helpers['human_ballots'](manifest,human_orders)
    require(len(human_orders) == 282 and len(ballots) == 282 and sum(map(len,ballots.values())) == 846, 'Human reference counts differ')
    results = {}
    for arm,directions in predictions.items():
        r = agreement(ballots,directions)
        group_counts = Counter(pairs[pid]['group_id'] for pid in directions)
        r.update({'numeric_paragraphs':len(numeric[arm]) if arm in numeric else None,
                  'expected_paragraphs':282 if arm in numeric else None,
                  'represented_triplets':len(group_counts),'complete_triplets':sum(v == 3 for v in group_counts.values()),
                  'planned_triplets':94})
        results[arm] = r
    per_order = []
    for (pid,orientation),value in orders.items():
        if value is not None:
            per_order.append((pid,orientation,value))
    # Prefix the repeated pair IDs for order-level bookkeeping only; human votes
    # remain the same three correlated ballots under both presentations.
    order_ballots = {pid+':'+orientation:ballots[pid] for pid,orientation,_ in per_order}
    results['pairwise_each_order'] = agreement(order_ballots,{pid+':'+orientation:v for pid,orientation,v in per_order},564)
    results['pairwise_each_order']['orders_repeat_existing_pair_ballots'] = True
    contrasts = {}
    for arm in (*ARMS[1:],'pairwise_consensus'):
        shared = set(predictions['hbq']) & set(predictions[arm]); deltas = []
        for pid in shared:
            preferred = 1 if sum(v for _,v in ballots[pid]) > 0 else -1
            credit = lambda d:0.5 if d == 0 else float(d == preferred)
            deltas.append(credit(predictions[arm][pid])-credit(predictions['hbq'][pid]))
        contrasts[arm+'_minus_hbq'] = {'shared_pairs':len(shared),'mean_half_credit_agreement_difference':sum(deltas)/len(deltas) if deltas else None,
                                      'state':'INCONCLUSIVE_PARTIAL_RETROSPECTIVE_DEVELOPMENT','confidence_interval':None}
    result = {'schema_version':1,'study':'lamp-retained-prefix-ordinal-development-20261020',
              'state':'INCONCLUSIVE_PARTIAL_RETROSPECTIVE_DEVELOPMENT','input_sha256':PINS,
              'analysis_source_sha256':source_sha,'analysis_freeze_sha256':digest(freeze_raw),
              'source_assessor_ids':11,'verified_independent_people':False,'rank_orders':282,'correlated_pair_ballots':846,
              'human_scalar_scale':None,'global_rank_correlation':None,'all_strata_already_development':True,
              'original_all17808_gate_met':False,'original_gate_changed':False,'historical_tools_off_eligible_records':0,
              'methods':results,'paired_contrasts':contrasts,'accepted_initial_pair_orders':len(orders),'native_order_states':dict(order_states),
              'complete_AB_BA_pairs':len(consensus),'AB_BA_order_conflicts':order_conflicts,
              'provider_calls':0,'scorer_calls':0,'native_or_semantic_replays':0,'bootstrap_resamples':0,
              'new_human_labels':0,'human_targets_decoded_this_execution':True,'candidate_promoted':False,'full_goal_complete':False,
              'limitations':freeze['limitations']}
    private = {'schema_version':1,'analysis_freeze_sha256':digest(freeze_raw),'pairs':[
        {'pair_id':pid,'group_id':p['group_id'],'human_directions':[v for _,v in ballots[pid]],
         'model_directions':{arm:directions[pid] for arm,directions in predictions.items() if pid in directions},
         'order_directions':{o:orders[(pid,o)] for o in ('AB','BA') if (pid,o) in orders}}
        for pid,p in pairs.items() if any(pid in directions for directions in predictions.values()) or any((pid,o) in orders for o in ('AB','BA'))]}
    for name,document in [('results.json',result),('private-pair-reconciliation.json',private)]:
        with (args.output/name).open('xb') as stream:
            stream.write((json.dumps(document,indent=2,sort_keys=True)+'\n').encode())
    print(json.dumps({'state':result['state'],'methods':{arm:{k:r[k] for k in ('observed_pairs','model_ties','majority_agreement','individual_agreement')} for arm,r in results.items()},
                      'complete_AB_BA_pairs':len(consensus),'order_conflicts':order_conflicts,'paired_contrasts':contrasts}))


if __name__ == '__main__':
    main()
