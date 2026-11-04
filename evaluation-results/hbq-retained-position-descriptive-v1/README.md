# TTCW retained presentation-position description

This provider-free, post-hoc projection describes the 72 saved initial ordered
pair judgments from the opened TTCW expert-reference development collection.
The 36 pairs share 36 works across 12 plots. Presenting each pair in both orders
does not create independent works, and the 24 planned same-order repeat
comparisons remain unavailable.

The judge selected the first-presented story in 37 judgments and the second in
35. Across the 36 pairs, 33 selections remained on the same story when order
reversed; two selected the first position in both orders and one selected the
second position in both orders. Among the same pairs, the judgment matched the
expert-higher story 31/36 times when that story appeared first and 30/36 times
when it appeared second. The expert direction is derived from existing binary
creativity-test ratings; it is not a direct human preference ballot.

As an exploratory simple baseline, select the story with more whitespace-separated
words and abstain on ties. The longer story matches the expert-derived direction
in 10 of 35 pairs; one pair has equal word counts. On the same 35 pairs in both
orders, the saved judge matches that direction in 59 of 70 judgments and selects
the longer story in 19 of 70. The two orders reuse the same pairs and the pairs
share works and plots. These post-hoc counts are not independent confirmation or
evidence of general superiority over a length baseline.

On the separately fixed 28-story cohort shared by all five scoring methods,
whitespace word count has Spearman rho `-0.600` with the existing expert
reference. The corresponding length correlations are `-0.406` for Claude (10
stories), `-0.529` for GPT-3.5 (10), and `-0.286` for GPT-4 (8). Average ranks
handle ties. The same fixed data reproduce the published overall HBQ (`0.712`)
and TTCW14 (`0.423`) correlations. These exploratory associations do not show
that length caused expert or model scores, and the small generator groups share
plots. They use opened development data and have no estimated confidence interval.

Choosing shorter stories after seeing that negative association gives a
shorter-story rho of `0.600`; HBQ minus that baseline is `0.112` on the same 28
works. For a sensitivity check, 2,000 paired resamples of the 12 plots give a
2.5th–97.5th percentile range of `[-0.111, 0.374]` for that difference, with no
undefined draws. The rule's direction was selected on these data, the 28 works
are an incomplete availability-conditioned cohort, and the range is conditional
on the observed plots. It does not establish superiority or repair the original
missing-data gate.

Among those same 28 works, 22 unordered pairs have both stories in the same
plot, across 10 plots. The following counts compare each saved scalar ordering
with the direction derived from the existing expert ratings. A tie is reported
separately; it does not mean the method selected the expert-higher story.

| Rule | Matches | Mismatches | Ties |
| --- | ---: | ---: | ---: |
| HBQ | 20 | 2 | 0 |
| TTCW14 | 15 | 6 | 1 |
| Holistic | 2 | 0 | 20 |
| Compact | 0 | 0 | 22 |
| Oregon | 8 | 5 | 9 |
| Shorter story, chosen post hoc | 14 | 7 | 1 |

The direct pair judge agrees in 40 of the corresponding 44 ordered judgments.
Those orders repeat the same 22 pairs; the pairs also share works and plots.
These are descriptive, incomplete-cohort comparisons, not independent human
preference ballots, a superiority test or a measure of revision utility.

These are descriptive counts, not a causal position effect, statistical
significance, general model-bias claim, or proof of literary quality. Historical
clients include different versions and missing version fields; this is not a
new current-contract qualification. Original admission, reference and cohort
limitations remain in the [initial development report](../hbq-sol-ttcw-initial-development-20261026/README.md).
The complete alignment, repeatability and release program remains open.

`aggregate.json` contains no prose, per-work decisions, participant identities,
individual ratings, or private paths. It is regenerated directly from the
hash-pinned saved joined view, frozen manifest, fixed-cohort freeze, saved features
and already-opened reference ratings. The command also verifies each frozen prompt and both source texts
against their exact hashes and confirms the presented order. These inputs remain
private and are needed for reproduction. The command reuses saved admissions; it
does not replay native receipts or establish scientific validation.

```text
python -B regenerate.py --joined <saved-joined.json> --manifest <frozen-manifest.json> --labels <opened-labels.json> --frozen-root <frozen-input-root> --cohort-freeze <fixed-cohort-freeze.json> --features <saved-features.json> --output <new-aggregate.json>
```

The command creates a fresh output and checks exact input hashes, request and
source bindings, plot and pair membership, denominators and the recorded counts.
It makes no provider call, native replay, scoring call, new judgment, new human
label, or promotion.
