# Historical scalar ranks across five repeats

This retrospective extension reports exact item-pair ordering changes in the
already-opened matched six-arm, eleven-item panel. Existing MAPD, rank
correlations, floors/ties, rater influence and calibration results were known.
The profile and source were frozen and independently reviewed before the
single new count execution. The original six-item/six-prompt HBQ v1.0.0 cohort
and later five-item/four-prompt v1.2.1 cohort remain separate for every arm.
The frozen projection records requested Sol/high; this diagnostic does not
newly attest native controls, current model behavior or tools-disabled collection.

For each item pair, compare the exact decimal-derived Fraction scores at each
of the five registered repeat positions. No means, rounding, epsilon,
normalization or clipping is used. Orient pairs by sorted item IDs; changing
that orientation swaps positive/negative signs but preserves reversals and
ties. Four categories are mutually exclusive and exhaustive:

- Strict reversal: both positive and negative differences occur, with or without ties.
- Stable strict: all five differences have the same nonzero sign.
- Always tied: all five differences are zero.
- Tie changing without reversal: ties occur alongside only one strict direction.

There are 15 original or 10 later item pairs per arm. Each pair supplies five
signs and ten repeat-index comparisons: 150 original or 100 later comparisons
per arm, 750 signs and 1,500 comparisons overall. These counts are derived from
330 existing scores; they are not new judgments or independent trials. The
three-by-three negative/tie/positive cross-tab uses earlier registered index
as row and later index as column. It is not a temporal causal or packet-order
perturbation result; repeat positions do not imply synchronized judging.

| Cohort | Arm | Strict reversal | Stable strict | Always tied | Tie changing, no reversal | Strict flips / all repeat comparisons | Strict flips / both-strict comparisons |
|---|---|---:|---:|---:|---:|---:|---:|
| Original n=6, g=6 | Cambridge | 3/15 | 11 | 0 | 1 | 8/150 | 8/132 |
| Original n=6, g=6 | Compact analytic | 0/15 | 5 | 10 | 0 | 0/150 | 0/50 |
| Original n=6, g=6 | HBQ | 7/15 | 8 | 0 | 0 | 31/150 | 31/146 |
| Original n=6, g=6 | Holistic anchored | 0/15 | 5 | 10 | 0 | 0/150 | 0/50 |
| Original n=6, g=6 | NAPLAN | 2/15 | 13 | 0 | 0 | 10/150 | 10/146 |
| Original n=6, g=6 | Oregon | 0/15 | 13 | 0 | 2 | 0/150 | 0/136 |
| Later n=5, g=4 | Cambridge | 3/10 | 3 | 0 | 4 | 10/100 | 10/77 |
| Later n=5, g=4 | Compact analytic | 0/10 | 0 | 10 | 0 | 0/100 | 0/0 (undefined) |
| Later n=5, g=4 | HBQ | 1/10 | 4 | 1 | 4 | 4/100 | 4/62 |
| Later n=5, g=4 | Holistic anchored | 0/10 | 0 | 10 | 0 | 0/100 | 0/0 (undefined) |
| Later n=5, g=4 | NAPLAN | 3/10 | 6 | 0 | 1 | 9/100 | 9/85 |
| Later n=5, g=4 | Oregon | 5/10 | 4 | 0 | 1 | 14/100 | 14/61 |

Original HBQ reverses strictly for 7/15 item pairs and 31/150 repeat-index
comparisons. Later HBQ reverses for 1/10 pairs and 4/100 comparisons, while
four other pairs change between ties and one strict direction and one remains
tied throughout. Different items and rubric versions prevent a causal version
improvement claim. These are historical repeat-order diagnostics, not quality
or human-alignment results.

Compact analytic and holistic have no strict reversals because they retain
coarse ordering: 10/15 original pairs and all 10/10 later pairs are always tied.
Their later conditional flip rate is undefined because no comparison has two
nonzero signs. A zero unconditional flip count or perfectly stable tie is not
evidence of useful discrimination. Original Oregon has no strict reversals but
two tie-changing pairs; later Oregon reverses for 5/10 pairs, including the
single same-prompt pair. No winner or population stability claim follows.

`result.json` also separates same-prompt and different-prompt pairs. Original
has zero same-prompt pairs, so those rates are null. Later has one same-prompt
pair per arm, which is a descriptive inventory, not a replicable sample size.
Different-prompt score order is not a validated quality ordering. Prompt and
item reuse, shared scores and overlapping repeat-index comparisons remain
dependent. No CI, significance or independent-pair inference is supplied.

This scalar projection cannot reconstruct four-state leaf transitions,
label marginal frequencies or chance-adjusted leaf agreement. It also cannot
supply absent matched observations from another endpoint. Existing raw HBQ
leaf agreement remains separate in the [completed aggregate](../hbq-multisample-repeatability-v1-completed-result-v1/README.md).
No new leaf, interendpoint or human metric is asserted.

The pinned [floor preflight](../hbq-multisample-floor-discrimination-v1/README.md)
verifies source/public/cohort bindings and the full rectangular scalar panel.
Its measurement/bootstrap functions are not called. Scalar-only lexical
projection does not materialize human targets, prose, rationales, responses or
native receipts. Hashing and lexical scans access full bytes; this is not a
byte-nonaccess claim. Exact pair membership, score vectors and sign sequences
remain private. Public outputs contain aggregate counts and commitments only.

One behavioral guard checked strict reversal versus changing/constant ties,
an independently enumerated three-by-three sign cross-tab, orientation symmetry,
nonzero tiny exact decimal signs, and undefined zero
denominators. Root readback independently checked every saved score difference,
pair/category, all cross-tabs/rates and prompt strata without rereading inputs
or rerunning collection/analysis. Exact source snapshots, original runtime,
terminal and private pair ledger are retained; source and aggregate review
accepted the stated scope. No provider calls, fitting, native scoring, bootstrap,
human labels, candidate changes or promotion occurred.

Replay needs the hash-bound retained score root and recorded CPython, with a
fresh private output outside the repository and retained sources:

```text
python -B source.py --source-root <frozen-330-score-root> --output <fresh-private-directory>
python -B test_source.py
```

The full current-contract multi-dataset matrix, interendpoint evidence,
cross-form collections, revision utility and prospective release gates remain
incomplete. Canonical baseline and frozen candidates remain unpromoted.
