# Dryad human agreement: sensitivity to evaluator splits

The previously published [human-agreement report](../hbq-human-alignment-dryad-human-agreement-v1/README.md)
used one fixed division of the 600 evaluator indices into two equally sized
groups. This retrospective analysis reuses the same opened TRAIN and DEV
ratings to ask how the result changes across 20 other deterministic balanced
divisions. The original 24 axis/partition estimates were reproduced before
calculating the alternate splits. No model requests or new human labels were
made.

Each split assigns evaluator indices globally, so an evaluator is placed in
the same half for all stories. For each story and axis, each half's ratings
are averaged; a story needs at least two ratings in each half. Spearman
correlation with average ranks for ties compares the half-means across eligible
stories. Eligibility changes with the split: 172–176 TRAIN and 57–60 DEV
stories were eligible in the alternate divisions.

| DEV dimension | Original split | Minimum–maximum across 20 alternate splits |
| --- | ---: | ---: |
| Appropriate | 0.492 | 0.166–0.379 |
| Well-written | 0.540 | 0.475–0.633 |
| Funny | −0.061 | 0.003–0.331 |
| Future | 0.106 | −0.123–0.252 |

The earlier original split was selected before this sensitivity analysis; the
alternate seed schedule was specified before this calculation, after the
original results were known. A separate calculation applied the same splits to
the original source's novelty index (the mean of novel, original and rare) and
usefulness index (appropriate, feasible and publishable). On DEV, the original
values were 0.398 and 0.502; the alternate ranges were 0.276–0.538 and
0.333–0.581, respectively. These indices do not establish an HBQ mapping.

These are observed ranges of 20 correlated rearrangements of the same evaluator
pool, not confidence intervals or estimates of population reliability. Changing
story eligibility can contribute to variation. The analysis does not establish
a human ceiling, model alignment, causation, superiority or candidate promotion.
The original dataset's future-axis survey wording remains unavailable. The
separate [fixed-split story-bootstrap report](../hbq-human-agreement-story-bootstrap-v1/README.md)
addresses a different conditional uncertainty question and does not include
these alternate splits.

[axes.json](axes.json) contains all 24 axis/partition summaries and
[indices.json](indices.json) contains four index/partition summaries. They are
the unchanged aggregate outputs from the earlier analyses. Independent checks
reconstructed split assignments and tie-aware ranks on selected cases, and a
separate check reproduced both index summaries across all 21 splits.

## Reproduction

With the exact private inputs described by the parent protocol:

```text
python -B reproduce.py --ratings PATH_TO_AUDITED_V2.csv --split-manifest PATH_TO_SPLIT.jsonl
```

The script checks input and aggregate hashes, replays the parent split, and
compares every published axis and index summary. It makes no network or provider
calls and writes no output files. Its parent CSV reader parses complete rows as
strings; confirmation rows are excluded before rating values are converted or
used, but their bytes and fields pass through the parser. Story text, individual
ratings, evaluator identifiers and private paths are not emitted or published.
The split manifest is read for source identifiers and partition membership.
