# Dryad fixed-half human agreement: conditional story intervals

This retrospective extension adds story-resampling uncertainty to the immutable
[one-split human agreement aggregate](../hbq-human-alignment-dryad-human-agreement-v1/README.md).
All 24 original point estimates replayed exactly before the new calculation.
It does not establish model alignment, a human ceiling or a rubric improvement.

The unchanged 600-evaluator pool is split into two fixed groups of 300. Each
axis correlates arithmetic half-means across eligible stories with average-tie
Spearman: 175 TRAIN stories (one excluded for insufficient half coverage) and
60 DEV stories. The frozen profile resamples stories 5,000 times within each
partition, carrying both halves and all twelve axes together. Each duplicate
story retains its multiplicity and ranks are recomputed for every draw.

The table gives the original correlation and a pointwise conditional 95%
percentile interval, using linear quantiles. All 120,000 axis/draw values were
defined. DEV funny and future include zero; no multiplicity-adjusted significance
or superiority claim is made.

| Axis | TRAIN correlation [interval] | DEV correlation [interval] |
|---|---|---|
| novel | 0.501 [0.380, 0.602] | 0.348 [0.091, 0.571] |
| original | 0.438 [0.319, 0.546] | 0.339 [0.084, 0.555] |
| rare | 0.540 [0.425, 0.639] | 0.364 [0.106, 0.581] |
| appropriate | 0.454 [0.324, 0.571] | 0.492 [0.252, 0.680] |
| feasible | 0.491 [0.363, 0.607] | 0.417 [0.168, 0.627] |
| publishable | 0.486 [0.358, 0.600] | 0.505 [0.270, 0.680] |
| well_written | 0.564 [0.446, 0.663] | 0.540 [0.290, 0.728] |
| enjoyed | 0.435 [0.313, 0.549] | 0.469 [0.249, 0.654] |
| boring | 0.466 [0.341, 0.582] | 0.346 [0.084, 0.573] |
| funny | 0.352 [0.216, 0.472] | -0.061 [-0.312, 0.195] |
| twist | 0.623 [0.517, 0.710] | 0.539 [0.328, 0.707] |
| future | 0.158 [0.005, 0.306] | 0.106 [-0.161, 0.372] |

These are descriptive conditional intervals for the observed rating field and
fixed evaluator split. Story exchangeability is assumed, not verified. Shared
raters across stories, topic/condition clustering, evaluator-population sampling,
alternate splits and simultaneous family coverage are not modeled. The
percentile method is a simple exploratory choice rather than a demonstrated
coverage guarantee; [SciPy's bootstrap documentation](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.bootstrap.html)
describes paired resampling and the limitations of percentile intervals. This
profile was frozen before these new draws, after the parent points were already
public. It is not a prospective confirmation protocol. Boring retains its source
orientation; the parent's missing future survey-prompt limitation remains.

`source.py`, `profile.json` and `result.json` bind the exact parent code, protocol,
aggregate and private inputs. The source-only split manifest is projected to
story identity and partition. A byte-level CSV lexer scans delimiters without
decoding story prose; confirmation rows contribute evaluator IDs only and are
excluded before any rating-field decoding. Actual accounting: 2,836 open rows,
34,032 open rating fields, 683 confirmation metadata rows, zero decoded
confirmation rating fields and zero decoded story-text fields. Lexical byte
access is not a claim that confirmation bytes were never read.

Private raw inputs, IDs, half-means and bootstrap distributions are not published.
The saved private distribution commitment is
`04e98e5ba2b13ae7e00cadaa9907f1a3a13a639ec08a113ef1dc67a6a98c16dc`.
The aggregate result is
`d432350a0fb80dabdab80189a42586a12a95ef28078b896dbb360667bb9ed227`.
`execution.json` records the actual runtime and acceptance. Three focused guards
pass: duplicated-story average ties versus the independent Fraction parent,
closed/prose field decoding, and retention of undefined draws. Root readback
verified all 24 parent rows, every distribution hash/count/range and every
endpoint using independent standard-library inclusive quantiles. No provider
calls, new human labels, judge fitting, candidate changes or promotion occurred.

Replay with the recorded CPython version and original hash-bound inputs; output
must be a fresh private directory outside the repository:

```text
python -B source.py --ratings <private-ratings.csv> --split-manifest <source-only-split.jsonl> --output <fresh-private-output>
python -B test_source.py
```

This addresses the fixed-split human-reference interval gap for this source.
The full P2 matrix, other datasets, matched endpoint comparisons, repeatability,
revision utility and prospective release gates remain incomplete.
