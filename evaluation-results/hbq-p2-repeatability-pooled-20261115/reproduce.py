"""Reproduce pooled figures from three retained private derived projections.

Pass --observed, --unstable and --bounds paths. No individual identifiers,
creative text or response bodies are printed. The three inputs are private;
this script checks their byte commitments and aggregate consistency. It does
not independently regenerate their original raw-to-derived provenance.
"""
import argparse
import hashlib
import json
from pathlib import Path

PINNED = {
    'observed': 'f406670bc3391a3074fb48048ae6bc926f9d9908f2fa36aab3d7c46e1ab28c1f',
    'unstable': '4deedc0cbe93a0b06aa9837713a2749a68568210fffbeff1c481234d97c7e0d1',
    'bounds': '9edaa3d4ea2c14b8a2ae3636974baa48ff9714aa8ea044eb3300a13a52551b76',
}
STATES = {'YES', 'NO', 'NOT_APPLICABLE', 'CANNOT_ASSESS'}


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def load(path, expected):
    raw = Path(path).read_bytes()
    require(hashlib.sha256(raw).hexdigest() == expected, 'private projection digest differs')
    value = json.loads(raw)
    require(type(value) is dict, 'private projection shape differs')
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in PINNED:
        parser.add_argument('--' + name, required=True, type=Path)
    args = parser.parse_args()
    observed, unstable, bounds = (load(getattr(args, name), digest) for name, digest in PINNED.items())
    stories = observed['per_story']
    require(len(stories) == 3, 'selected story count differs')
    pairs = matches = complete_pairs = complete_matches = 0
    for story in stories:
        cycles = {tuple(row['cycles']): row for row in story['cycles']}
        require(set(cycles) == {(0, 1), (0, 2), (1, 2)}, 'cycle set differs')
        require([cycles[key]['observed'] for key in ((0, 1), (0, 2), (1, 2))] == [170, 170, 178],
                'planned pair coverage differs')
        for row in cycles.values():
            require(type(row['matches']) is int and 0 <= row['matches'] <= row['observed'], 'invalid pair count')
            pairs += row['observed']
            matches += row['matches']
        complete_pairs += cycles[(1, 2)]['observed']
        complete_matches += cycles[(1, 2)]['matches']
    bins = observed['unordered_transition_counts']
    require(all(len(row['states']) == 2 and set(row['states']) <= STATES and
                type(row['pairs']) is int and row['pairs'] >= 0 for row in bins), 'transition bins differ')
    require(len({tuple(row['states']) for row in bins}) == len(bins), 'duplicate transition bin')
    require(sum(row['pairs'] for row in bins) == pairs and
            sum(row['pairs'] for row in bins if row['states'][0] == row['states'][1]) == matches,
            'transition counts differ')
    cannot = sum(row['pairs'] for row in bins if row['states'] == ['CANNOT_ASSESS', 'CANNOT_ASSESS'])
    missing_cells = unstable['partial_leaf_story_cells']
    require(missing_cells == 24 and len(unstable['unstable']) == unstable['unstable_cells'], 'partial count differs')
    require(not any(None in row['cycles'] for row in unstable['unstable']), 'a partial cell has differing later states')
    planned_pairs = len(stories) * 178 * 3
    require(pairs + 2 * missing_cells == planned_pairs == observed['planned_pairs'], 'planned pair count differs')
    # The two retained later states agree for each partial cell. With four
    # states available, each missing state can match neither or both.
    lower, upper = matches, matches + 2 * missing_cells
    require((pairs, matches, complete_pairs, complete_matches, cannot) ==
            (bounds['observed_pairs'], bounds['observed_matches'], bounds['complete_later_cycle_pairs'],
             bounds['complete_later_cycle_matches'], bounds['observed_both_cannot_assess']),
            'independent projection differs')
    require(bounds['missing_cells_with_disagreeing_later_states'] == 0 and
            bounds['bounds']['lower_matches'] == lower and bounds['bounds']['upper_matches'] == upper,
            'missing-state bounds differ')
    result = {'study': 'selected-p2-short-story-hbq-repeatability',
              'story_count': len(stories), 'leaves_per_story': 178, 'cycles_per_story': 3,
              'all_arm_planned_requests': bounds['planned_requests_all_arms'],
              'all_arm_accepted_requests': bounds['accepted_requests'],
              'observed_leaf_pairs': pairs, 'observed_agreements': matches,
              'observed_joint_cannot_assess_agreements': cannot,
              'complete_later_cycle_pairs': complete_pairs, 'complete_later_cycle_agreements': complete_matches,
              'unobserved_cycle_zero_leaves': missing_cells, 'unobserved_leaf_pairs': 2 * missing_cells,
              'planned_leaf_pairs': planned_pairs,
              'full_plan_agreement_bounds': {'minimum_agreements': lower, 'maximum_agreements': upper,
                                             'denominator': planned_pairs},
              'provider_calls_for_analysis': 0, 'human_targets_read_for_analysis': False,
              'input_projection_sha256': PINNED}
    print(json.dumps(result, sort_keys=True, indent=2, allow_nan=False))


if __name__ == '__main__':
    main()
