# Dryad human internal agreement, fixed split

This aggregate-only result measures agreement between two deterministic halves of the same human evaluator pool. It is not model alignment, a human ceiling, an HBQ-RS mapping, or a pooled result with HANNA/WPB.

The protocol pins the audited 12-axis ratings CSV and source-only split manifest by SHA-256. It hashes all 600 opaque evaluator indices with one fixed seed, assigns 300 to each half, averages each half's ratings within a story, requires at least two ratings per story per half, and computes tie-aware Spearman correlations across eligible stories. TRAIN has 175 eligible stories (one excluded for coverage); DEV has 60 eligible stories.

| Axis | TRAIN | DEV |
| --- | ---: | ---: |
| Novel | 0.501 | 0.348 |
| Original | 0.438 | 0.339 |
| Rare | 0.540 | 0.364 |
| Appropriate | 0.454 | 0.492 |
| Feasible | 0.491 | 0.417 |
| Publishable | 0.486 | 0.505 |
| Well-written | 0.564 | 0.540 |
| Enjoyed | 0.435 | 0.469 |
| Boring | 0.466 | 0.346 |
| Funny | 0.352 | -0.061 |
| Twist | 0.623 | 0.539 |
| Future | 0.158 | 0.106 |

`future` denotes the source dimension concerning changed expectations of future stories; the full survey prompt is not available in the source package. `boring` is reported in its direct source orientation. Reversing that orientation in both evaluator halves would leave this rank-agreement statistic unchanged.

No bootstrap or confidence interval was run, so finite one-split sensitivity is unquantified. Confirmation outcomes are filtered before rating-axis parsing and are absent from this package. The historical parent aggregate SHA-256 is `050c810f58314116725f7ac34fc3cff6b4dcfe38dbb6d85132648b86fd021fe7`; this published descendant reproduces its 24 aggregate rows exactly.

For a portable replay, provide the local audited files explicitly; the command refuses to overwrite output or can check an existing aggregate without writing:

```text
python source.py --ratings PATH_TO_AUDITED_V2.csv --split-manifest PATH_TO_SPLIT.jsonl --output fresh-result.json
python source.py --ratings PATH_TO_AUDITED_V2.csv --split-manifest PATH_TO_SPLIT.jsonl --check-result result.json
```
