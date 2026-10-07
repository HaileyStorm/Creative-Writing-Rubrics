# Historical HANNA: global annotator-ID influence sensitivity

This retrospective extension asks how the already-opened eleven-story human
reference changes when one published Worker ID is omitted everywhere it occurs.
The original six-story HBQ v1.0.0 cohort and later five-story v1.2.1 cohort remain
separate, with unchanged stories and five-repeat model means for all six arms.
They do not support a causal rubric-version comparison or contemporary endpoint
acceptance. The prior scalar results and annotator coverage were known before
this profile was frozen; selected individual rating decoding and omission
measurement followed that freeze and independent source review.

The original source has three annotations per selected story: 33 annotations,
198 integer axis ratings and seven distinct Worker IDs. Five IDs recur across
stories, with total coverage of 1, 1, 2, 5, 7, 8 and 9 stories. Assignment ID
identifies an annotation, not the omission unit. These published identifiers
do not certify natural-person identity or annotator expertise.

Each of the seven IDs is removed globally, using the same omission for every
arm and both cohorts. Every story retains two or three complete annotations;
no story is dropped. Human overall is the exact arithmetic mean of all six
axes across surviving annotations. Model means are fixed exact decimal
Fractions. Spearman uses average ranks for exact ties. All fourteen omission
states, affected-story counts and surviving-annotation counts are retained in
`result.json`, including two explicit zero-effect cohort states. Undefined
correlations and paired contrasts remain null.

| Cohort | Arm | Baseline Spearman | Seven omission states, min to max |
|---|---|---:|---|
| Original, n=6 | Cambridge | 1.000 | 0.522 to 1.000 |
| Original, n=6 | Compact analytic | 0.655 | 0.655 to 0.664 |
| Original, n=6 | HBQ | 0.714 | 0.371 to 0.899 |
| Original, n=6 | Holistic anchored | 0.655 | 0.655 to 0.664 |
| Original, n=6 | NAPLAN | 0.943 | 0.657 to 0.943 |
| Original, n=6 | Oregon | 0.943 | 0.319 to 1.000 |
| Later, n=5 | Cambridge | 0.462 | -0.308 to 0.564 |
| Later, n=5 | Compact analytic | undefined | undefined (7/7) |
| Later, n=5 | HBQ | -0.872 | -0.975 to -0.564 |
| Later, n=5 | Holistic anchored | undefined | undefined (7/7) |
| Later, n=5 | NAPLAN | 0.600 | -0.200 to 0.700 |
| Later, n=5 | Oregon | -0.718 | -0.975 to -0.564 |

All five comparator-minus-HBQ omission ranges cross zero in the original
six-story cohort. In the later five-story cohort, HBQ remains negatively
correlated in every omission state; Cambridge and NAPLAN contrasts remain
positive, while Oregon's crosses zero. Compact analytic and holistic anchored
have constant later-cohort model scores, so all seven correlations and their
paired contrasts are undefined. There are 70 defined and 14 undefined arm
states; 56 defined and 14 undefined paired contrasts.

These overlapping omissions measure fixed-panel annotator influence. They are
not independent repetitions, confidence intervals, a population reliability
coefficient, a significance test, a human ceiling or evidence of improvement.
Unequal coverage changes how much each omission perturbs the target. The tiny
historical cohorts and known development outcomes limit generalization. No
candidate is changed or promoted.

The original nested floating-point human averages were reconstructed exactly
before omission metrics. Exact reference targets and frozen floating-point
targets have no pairwise tie-partition disagreements or strict reversals in
either cohort, and their baseline correlations agree when using the same
exact model means. This does not claim literal replay of every legacy
floating-point estimator detail.

`profile.json`, `source.py`, `result.json` and `execution.json` retain source,
cohort, code and runtime commitments. The frozen 330-model-score panel is
reused through its pinned preflight, without rerunning native scoring or the
earlier bootstrap. The source CSV was reacquired at its original frozen hash
from the [pinned HANNA commit](https://github.com/dig-team/hanna-benchmark-asg/tree/282f27536a5d05ad4ce14298abcd70c45668fed2).
HANNA copyright 2022 dig-team; its [MIT license](https://github.com/dig-team/hanna-benchmark-asg/blob/282f27536a5d05ad4ce14298abcd70c45668fed2/LICENSE)
is retained verbatim in `HANNA_LICENSE.txt`. Source prose is not published here.

Only the selected 33 rows' ratings are decoded after matching source order,
Worker ID and Assignment ID to the pinned private identity inventory. The
remaining 3,135 rows route out after Story ID metadata; no unselected ratings,
Story, Prompt or Name fields are decoded. Full-file hashing and lexical scans
still access bytes and are not a non-access claim. Raw identifiers, selected
rating vectors, source prose and contemporary target artifacts remain private.
Published worker labels are local opaque labels, not raw source IDs.

Two focused guards passed for cross-story omission despite changing row
positions/assignment IDs, opaque prose/unselected fields, and undefined-value
propagation. Root readback independently checked all saved state geometry,
zero-effect states, arm summaries, paired differences, undefined counts,
source snapshots and target-variant baseline agreement without rereading
ratings or rerunning measurement. No provider calls or new human votes occurred.

Replay requires the hash-bound original private inputs and recorded CPython:

```text
python -B source.py --csv <frozen-HANNA.csv> --frozen11 <original-contract.json> --identities <private-source-row-identities.json> --source-root <frozen-330-score-root> --output <fresh-private-directory>
python -B test_source.py
```

Output must be outside the repository and retained input roots. The full P2
matrix, contemporary endpoint collections, other forms, repeatability,
revision utility and prospective release gates remain incomplete.
