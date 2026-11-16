"""Reconstruct LAMP human-disagreement strata from public aggregate totals."""
import argparse
from fractions import Fraction
from hashlib import sha256
import json
from pathlib import Path

SOURCE = 'evaluation-results/hbq-lamp-stopped-development-20261020/results.json'
SOURCE_SHA256 = '6258147e5bbb4e4ffea5b1ae681e47af3ac50c43c49118d41fd854c634c85b1d'


def integer(x, name):
    if type(x) is not int or x < 0:
        raise ValueError(name + ' must be a nonnegative integer')
    return x


def credit(x, name):
    if type(x) not in (int, float):
        raise ValueError(name + ' must be numeric')
    v = Fraction(str(x))
    if v < 0 or (2 * v).denominator != 1:
        raise ValueError(name + ' must be nonnegative half-credit')
    return v


def build(repo):
    raw = (repo / SOURCE).read_bytes()
    if sha256(raw).hexdigest() != SOURCE_SHA256:
        raise ValueError('public source digest differs')
    source = json.loads(raw)
    method = source['methods']['pairwise_each_order']
    consensus = source['methods']['pairwise_consensus']
    orders = integer(method['observed_pairs'], 'orders')
    unanimous = integer(method['observed_pairs_with_unanimous_humans'], 'unanimous orders')
    ballots = integer(method['individual_correlated_ballots'], 'ballots')
    majority = credit(method['majority_half_credit_total'], 'majority credit')
    ballot_credit = credit(method['individual_half_credit_total'], 'individual credit')
    repeats = integer(source['complete_AB_BA_pairs'], 'reversed pairs')
    if (orders, unanimous, ballots, repeats) != (93, 70, 279, 4) or ballots != 3 * orders:
        raise ValueError('published geometry differs')
    if consensus['observed_pairs'] != repeats or consensus['observed_pairs_with_unanimous_humans'] != repeats:
        raise ValueError('reversed-pair unanimity differs')
    split = orders - unanimous
    # For unanimous ballots, individual credit is three times majority credit.
    # For a 2-to-1 split, individual credit is majority credit plus one per order.
    majority_unanimous = (ballot_credit - majority - split) / 2
    majority_split = majority - majority_unanimous
    individual_unanimous = 3 * majority_unanimous
    individual_split = majority_split + split
    if not (0 <= majority_unanimous <= unanimous and 0 <= majority_split <= split and
            (2 * majority_unanimous).denominator == 1 and (2 * majority_split).denominator == 1 and
            individual_unanimous + individual_split == ballot_credit):
        raise ValueError('reconstructed credits invalid')
    def row(name, n, pairs, m, b, majority_ballot_credit):
        return {'human_votes': name, 'orders': n, 'distinct_pairs': pairs,
                'model_majority_half_credit': float(m), 'majority_order_denominator': n,
                'model_individual_half_credit': float(b), 'individual_ballot_order_denominator': 3 * n,
                'same_ballot_majority_rule_credit': majority_ballot_credit}
    return {'state': 'RETROSPECTIVE_PUBLIC_AGGREGATE_RECONSTRUCTION', 'source': SOURCE,
            'source_sha256': SOURCE_SHA256, 'orders': orders, 'distinct_pairs': orders - repeats,
            'reversed_order_pairs': repeats,
            'strata': [row('unanimous', unanimous, unanimous - repeats, majority_unanimous,
                           individual_unanimous, 3 * unanimous),
                       row('two_to_one_split', split, split, majority_split,
                           individual_split, 2 * split)],
            'limits': ['All numbers are algebraically derived from the already-public aggregate, not new human data.',
                       'The same ballots are reused for reversed orders; passages, groups and assessors are dependent.',
                       'Strata contain different availability-selected items and cannot identify a causal effect or method winner.',
                       'The majority-rule quantity is an in-sample arithmetic maximum for binary decisions on those same ballots, not an external reliability or population ceiling.',
                       'No new provider call, scoring, admission, human label, validation, confirmation or promotion.']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    raw = (json.dumps(build(args.repo_root), sort_keys=True, indent=2, allow_nan=False) + '\n').encode()
    with args.output.open('xb') as stream:
        stream.write(raw)
    print(sha256(raw).hexdigest())


if __name__ == '__main__':
    main()
