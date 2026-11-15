# HF32 length-adjusted rank sensitivity

This post-result sensitivity check asks how the previously reported model–human
associations change after a linear adjustment for word-count rank. It uses the
same selected HF32 development works and human references as the
[length-baseline report](../hbq-hf32-length-baseline-v1/README.md). It adds no
model calls, human ratings or labels.

For each reference axis, the same 19 works have a complete HBQ score, TTCW14
score and human reference. The expert and reader references are different
constructs, and their matched cohorts need not be identical. The original
32-work plan, attrition and target definitions are described in the
[HF32 pilot report](../hbq-hf32-frozen708-human-reference-v1/README.md).

| Reference | Method | Unadjusted Spearman rho | Length-adjusted rank correlation |
| --- | --- | ---: | ---: |
| Expert mean | HBQ | 0.293140 | 0.233022 |
| Expert mean | TTCW14 | 0.232532 | 0.200521 |
| Reader median | HBQ | 0.390412 | 0.422324 |
| Reader median | TTCW14 | 0.364687 | 0.377443 |

The calculation assigns midranks within each cohort, linearly residualizes
the model-score ranks and human-reference ranks against an intercept and
word-count ranks, then takes the Pearson correlation of those residuals. The
two model associations remain positive in this selected dataset after that
specific adjustment. This is not a within-length Spearman correlation and does
not establish a causal effect, eliminate other confounding, prove independent
observations, or establish method superiority. It is not a population confidence
interval, confirmation study or candidate-promotion result.

## Reproduction

Run `python analyze.py` from this directory or any working directory. The script
reads the adjacent public length-baseline aggregate, checks its canonical JSON
SHA-256 `65eee601772e6fd3d949611a8200a7f2c0ba6a2cd1217597a0592d2dda9c5e72`,
and prints the adjusted aggregate. An alternative file can be supplied with
`--input`. Canonical JSON means UTF-8 encoding of recursively key-sorted JSON
using separators `,` and `:`, without ASCII escaping or non-finite numbers.
[aggregate.json](aggregate.json) records the results at full precision.

An independent local check reconstructed all four correlations from the
original pinned records using exact fractional midranks and confirmed the
residuals' orthogonality. That independent check requires private source inputs;
the calculation in this report can be reproduced from the public aggregate.
These checks verify the arithmetic, not the generality or causal meaning of the
result. No individual texts or ratings are published here.
