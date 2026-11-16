"""Check P2 repeatability aggregates against retained local source records.

This read-only verifier requires the original private index, manifest, snapshot
and accepted-record tree. It hashes and decodes accepted responses, which may
contain private quotations, but emits only aggregate counts. It does not open
held terminal or response files, contact a provider, or adjudicate judgments.
"""
import argparse
from collections import Counter, defaultdict
from fractions import Fraction
import hashlib
from itertools import combinations
import json
from pathlib import Path

INDEX = '2beee17892f90c44bf9f0014ad07cf6a3adbfc053951a32a8139a4f93e91aab5'
MANIFEST = 'fce6c47f99b3492fbcaa86a94056b3c8d68169687c0274faa0ace9ee523f776e'
SNAPSHOT = '75155efd2385f3e5b7750d71c82ed014dd155fd7e86d7225c85464a2ff1d12aa'
STATES = ('YES', 'NO', 'NOT_APPLICABLE', 'CANNOT_ASSESS')
HERE = Path(__file__).resolve().parent


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read_pinned(path, digest, size=None):
    path = Path(path).absolute()
    for part in (path, *path.parents):
        stat = part.stat()
        require(not part.is_symlink() and not getattr(stat, 'st_file_attributes', 0) & 1024,
                'source ancestry contains a symlink or reparse point')
    before = path.stat()
    raw = path.read_bytes()
    after = path.stat()
    require((before.st_size, before.st_mtime_ns, before.st_ino) ==
            (after.st_size, after.st_mtime_ns, after.st_ino), 'source changed during read')
    require(hashlib.sha256(raw).hexdigest() == digest and (size is None or len(raw) == size),
            'source digest or size differs')
    return raw


def pinned_json(path, digest, size=None):
    value = json.loads(read_pinned(path, digest, size))
    require(type(value) is dict, 'source object shape differs')
    return value


def rooted_relative(root, value):
    relative = Path(value)
    require(not relative.is_absolute() and '..' not in relative.parts, 'unsafe source-relative path')
    path = root / relative
    require(path.resolve().is_relative_to(root.resolve()), 'source path escapes root')
    return path


def accepted_ref(root, ref):
    path = Path(ref['path'])
    require(path.is_absolute() and path.resolve().is_relative_to(root.resolve()), 'record outside owner root')
    return path


def summary(pairs, categories):
    n = len(pairs)
    agreement = sum(a == b for a, b in pairs)
    left, right = Counter(a for a, _ in pairs), Counter(b for _, b in pairs)
    chance = sum(left[s] * right[s] for s in categories)
    den = n * n - chance
    kappa = Fraction(n * agreement - chance, den) if den else None
    return {'pairs': n, 'agreements': agreement,
            'cohen_kappa_exact': None if kappa is None else [kappa.numerator, kappa.denominator]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--index', type=Path, required=True)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--snapshot', type=Path, required=True)
    parser.add_argument('--owner-root', type=Path, required=True,
                        help='original absolute root containing the accepted record paths')
    args = parser.parse_args()
    owner = args.owner_root.resolve(strict=True)
    require(owner.is_dir(), 'owner root is not a directory')
    index = pinned_json(args.index, INDEX)
    manifest = pinned_json(args.manifest, MANIFEST)
    snapshot = pinned_json(args.snapshot, SNAPSHOT)
    require(index['manifest_sha256'] == MANIFEST and index['snapshot_sha256'] == SNAPSHOT, 'index bindings differ')
    require(len(index['artifacts']) == len(manifest['artifacts']) == 100, 'artifact count differs')
    require(len({item['path'] for item in index['artifacts']}) == 100 and
            {item['path'] for item in index['artifacts']} == set(manifest['artifacts']), 'artifact membership differs')
    for item in index['artifacts']:
        expected = manifest['artifacts'][item['path']]
        require((item['sha256'], item['bytes']) == (expected['sha256'], expected['bytes']), 'artifact binding differs')
        read_pinned(rooted_relative(args.manifest.parent, item['path']), item['sha256'], item['bytes'])

    planned = {row['logical_id']: row for row in manifest['requests']}
    requests = {row['logical_id']: row for row in index['requests']}
    require(len(planned) == len(manifest['requests']) == len(requests) == len(index['requests']) == 216 and
            set(planned) == set(requests), 'request identities differ')
    snapshot_refs = {ref['path']: ref for ref in snapshot['accepted_terminal_refs']}
    require(len(snapshot_refs) == len(snapshot['accepted_terminal_refs']) == 213, 'snapshot terminals differ')
    indexed_leaves = defaultdict(dict)
    for leaf in index['leaves']:
        qid, logical = leaf['question_id'], leaf['logical_id']
        require(qid not in indexed_leaves[logical] and logical in requests, 'duplicate or unknown leaf')
        indexed_leaves[logical][qid] = leaf
    require(sum(map(len, indexed_leaves.values())) == 1602, 'planned HBQ leaf count differs')
    hbq, ttcw = defaultdict(dict), {}
    source_bindings = defaultdict(lambda: defaultdict(set))
    accepted = held = 0
    for logical, request in requests.items():
        row = planned[logical]
        require(all(request[k] == row[k] for k in ('story_id', 'cycle', 'arm', 'batch_number', 'packet_index')),
                'request geometry differs')
        for key in ('source', 'prompt', 'schema'):
            path = row[key + '_path']
            require(request[key] == {'path': path, **manifest['artifacts'][path]}, 'input binding differs')
        source = request['source']
        source_bindings[row['story_id']][row['arm']].add((source['path'], source['sha256'], source['bytes']))
        leaves = indexed_leaves[logical]
        require(set(leaves) == set(row['question_ids']) and request['planned_question_count'] == len(leaves),
                'planned leaf binding differs')
        terminal_ref = request['terminal']
        if terminal_ref['state'] == 'unadmitted_no_resend':
            held += 1
            require(terminal_ref['no_resend'] is True and request['response'] is None and
                    all(x['terminal_state'] == 'unadmitted_no_resend' and x['observed_verdict'] is None
                        for x in leaves.values()), 'held record differs')
            # Keep held files unopened and states unknown.
            for qid, leaf in leaves.items():
                require(leaf['story_id'] == row['story_id'] and leaf['cycle'] == row['cycle'], 'held leaf binding differs')
                bank = hbq[(row['story_id'], row['cycle'])]
                require(qid not in bank, 'held packet overlaps another packet')
                bank[qid] = None
            continue
        accepted += 1
        require(terminal_ref['state'] == 'accepted' and terminal_ref['no_resend'] is True and
                terminal_ref['path'] in snapshot_refs, 'accepted terminal missing from snapshot')
        require(all(terminal_ref[k] == snapshot_refs[terminal_ref['path']][k] for k in ('path', 'sha256', 'bytes')),
                'snapshot terminal binding differs')
        terminal_path = accepted_ref(owner, terminal_ref)
        require(terminal_path.name == 'terminal.json' and terminal_path.parent.name == logical, 'terminal path differs')
        terminal = pinned_json(terminal_path, terminal_ref['sha256'], terminal_ref['bytes'])
        require(terminal['logical_id'] == logical and terminal['state'] == 'accepted' and terminal['no_resend'] is True,
                'accepted terminal differs')
        evidence = terminal.get('evidence', terminal)
        for name in ('attempt', 'admission', 'native_result', 'response'):
            ref = request[name]
            terminal_entry = terminal['attempt'] if name == 'attempt' else evidence[name]
            require(all(ref[k] == terminal_entry[k] for k in ('path', 'sha256', 'bytes')), 'record binding differs')
            path = accepted_ref(owner, ref)
            require(path.parent == terminal_path.parent, 'record parent differs')
            raw = read_pinned(path, ref['sha256'], ref['bytes'])
            if name == 'attempt':
                attempt = json.loads(raw)
                require(attempt['logical_id'] == logical and attempt['no_resend'] is True, 'attempt differs')
            elif name == 'admission':
                admission = json.loads(raw)
                require(admission['accepted'] is True and admission['errors'] == [], 'admission differs')
            elif name == 'response':
                response = json.loads(raw)
        verdicts = response['verdicts']
        if row['arm'] == 'hbq':
            values = {v['question_id']: v['verdict'] for v in verdicts}
            require(len(values) == len(verdicts) and set(values) == set(leaves) and set(values.values()) <= set(STATES),
                    'HBQ response differs')
            for qid, value in values.items():
                leaf = leaves[qid]
                require(leaf['observed_verdict'] == value and leaf['terminal_state'] == 'accepted' and
                        leaf['story_id'] == row['story_id'] and leaf['cycle'] == row['cycle'], 'leaf binding differs')
                bank = hbq[(row['story_id'], row['cycle'])]
                require(qid not in bank, 'HBQ packet overlap')
                bank[qid] = value
        else:
            require(row['arm'] == 'ttcw14' and not leaves and response['method'] == 'ttcw14_concise_evidence_v1',
                    'comparator method differs')
            values = {v['test_id']: v['verdict'] for v in verdicts}
            require(len(values) == len(verdicts) == 14 and set(values) == {f'ttcw-{i:02d}' for i in range(1, 15)}
                    and set(values.values()) <= {'YES', 'NO'}, 'comparator response differs')
            key = (row['story_id'], row['cycle'])
            require(key not in ttcw, 'duplicate comparator bank')
            ttcw[key] = values
    require((accepted, held) == (213, 3), 'accepted/held partition differs')
    require(len(source_bindings) == 3 and all(set(v) == {'hbq', 'ttcw14'} and len(v['hbq']) == 1 and
            v['hbq'] == v['ttcw14'] for v in source_bindings.values()), 'cross-arm sources differ')
    stories = sorted(source_bindings)
    require(set(hbq) == set(ttcw) == {(s, c) for s in stories for c in (0, 1, 2)}, 'bank geometry differs')
    for story in stories:
        universe = set(hbq[(story, 0)])
        require(len(universe) == 178 and all(set(hbq[(story, c)]) == universe for c in (1, 2)),
                'HBQ leaf universe differs')

    hbq_groups, ttcw_groups = {}, {}
    missing_cells = 0
    for story in stories:
        a, b, c = (hbq[(story, cycle)] for cycle in (0, 1, 2))
        for qid in a:
            if a[qid] is None:
                missing_cells += 1
                require(b[qid] is not None and b[qid] == c[qid], 'missing-cell later states differ')
    for a, b in ((0, 1), (0, 2), (1, 2)):
        key = f'{a}-{b}'
        hbq_groups[key] = [(hbq[(s, a)][q], hbq[(s, b)][q]) for s in stories for q in hbq[(s, a)]
                           if hbq[(s, a)][q] is not None and hbq[(s, b)][q] is not None]
        ttcw_groups[key] = [(ttcw[(s, a)][q], ttcw[(s, b)][q]) for s in stories for q in ttcw[(s, a)]]
    for groups in (hbq_groups, ttcw_groups):
        groups['pooled'] = [pair for key in ('0-1', '0-2', '1-2') for pair in groups[key]]
    hbq_expected = pinned_json(HERE / 'aggregate-kappa.json',
                               '2fd74a1c127858818f78a7fa1f6d3f3d15989851a204dc9c2b4bb4f9cad9fef4')
    ttcw_expected = pinned_json(HERE / 'aggregate-ttcw.json',
                                'd50c0dc2d63a162a515c19778ba462880f647d13cca4e9e0750fef72aea807c6')
    for key in ('0-1', '0-2', '1-2', 'pooled'):
        pairs = hbq_groups[key]
        require(summary(pairs, STATES) == hbq_expected['groups'][key]['all_four_states'], 'HBQ agreement differs')
        filtered = [p for p in pairs if 'CANNOT_ASSESS' not in p]
        require(summary(filtered, STATES) == hbq_expected['groups'][key]['excluding_cannot_assess'],
                'HBQ exclusion sensitivity differs')
        require(summary(ttcw_groups[key], ('YES', 'NO')) == ttcw_expected['groups'][key],
                'comparator agreement differs')
    pooled = hbq_groups['pooled']
    base = pinned_json(HERE / 'aggregate.json',
                       '9a5aff14e1e1dd51ab0be912aea6552cde037719ac108e8ec1f86d993e9f0e9c')
    matches = sum(a == b for a, b in pooled)
    require((len(pooled), matches, missing_cells) ==
            (base['observed_leaf_pairs'], base['observed_agreements'], base['unobserved_cycle_zero_leaves']) and
            sum(a == b == 'CANNOT_ASSESS' for a, b in pooled) == base['observed_joint_cannot_assess_agreements'] and
            (accepted, accepted + held) == (base['all_arm_accepted_requests'], base['all_arm_planned_requests']) and
            (len(hbq_groups['1-2']), sum(a == b for a, b in hbq_groups['1-2'])) ==
            (base['complete_later_cycle_pairs'], base['complete_later_cycle_agreements']) and
            base['full_plan_agreement_bounds'] == {'minimum_agreements': matches,
                                                    'maximum_agreements': matches + 2 * missing_cells,
                                                    'denominator': 1602}, 'missing-state bounds differ')
    scores = {key: Fraction(sum(v == 'YES' for v in values.values()), 14) for key, values in ttcw.items()}
    changes = [abs(scores[(s, a)] - scores[(s, b)]) for a, b in ((0, 1), (0, 2), (1, 2)) for s in stories]
    directions = Counter()
    for a, b in ((0, 1), (0, 2), (1, 2)):
        for x, y in combinations(stories, 2):
            left, right = scores[(x, a)] - scores[(y, a)], scores[(x, b)] - scores[(y, b)]
            directions['at_least_one_tie' if left == 0 or right == 0 else
                       'same_direction' if (left > 0) == (right > 0) else 'reversal'] += 1
    score_summary = {'native_range': [0, 1], 'distinct_scores': len(set(scores.values())),
                     'exact_floor': sum(x == 0 for x in scores.values()),
                     'exact_ceiling': sum(x == 1 for x in scores.values()),
                     'near_floor_le_0_1': sum(x <= Fraction(1, 10) for x in scores.values()),
                     'near_ceiling_ge_0_9': sum(x >= Fraction(9, 10) for x in scores.values()),
                     'paired_score_comparisons': len(changes),
                     'unchanged_score_comparisons': sum(x == 0 for x in changes),
                     'max_absolute_change_exact': [max(changes).numerator, max(changes).denominator],
                     'story_pair_direction_counts': {k: directions[k] for k in
                                                     ('same_direction', 'reversal', 'at_least_one_tie')}}
    require(score_summary == ttcw_expected['score_summary'], 'comparator score summary differs')
    print(json.dumps({'state': 'P2_PUBLIC_AGGREGATES_MATCH_RETAINED_ACCEPTED_RECORDS',
                      'artifact_commitments': 100, 'accepted_requests': accepted, 'held_requests_unopened': held,
                      'hbq_observed_pairs': len(pooled), 'hbq_agreements': matches,
                      'ttcw_observed_pairs': len(ttcw_groups['pooled']),
                      'provider_calls': 0, 'human_targets_read': False}, sort_keys=True, indent=2))


if __name__ == '__main__':
    main()
