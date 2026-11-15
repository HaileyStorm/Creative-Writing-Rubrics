# HF32 development comparison with a length baseline

This post-result analysis adds a simple word-count baseline to the previously
reported HF32 matched comparison. It uses the same retained works, scores and
human references; it adds no model calls, ratings or labels. The result is
descriptive development evidence, not a new confirmation study or a quality
rule. The [original HF32 report](../hbq-hf32-frozen708-human-reference-v1/README.md)
describes the cohort, target definitions, attrition and historical execution.

## Same-data comparison

Word count is the number of whitespace-separated tokens in each pinned UTF-8
source text, excluding the task prompt and context. Within each reference axis,
the table uses the same 19 works with a complete HBQ score, TTCW14 score and
available human reference. The expert reference is the mean of exactly two
finite expert creativity ratings; the reader reference is the median of
available finite nonexpert creativity ratings. These axes measure different
constructs and their 19-work cohorts need not be identical.

| Reference | Word count rho | Historical HBQ rho | TTCW14 rho |
| --- | ---: | ---: | ---: |
| Expert mean | -0.406487 | 0.293140 | 0.232532 |
| Reader median | 0.173742 | 0.390412 | 0.364687 |

The signed association for word count differs between these two cohorts; this
does not establish that length causes a rating or that shorter or longer text is
preferable. Choosing an inverse-length scoring rule after observing these data
would be post-result selection. Correlation magnitudes alone do not establish a
winner or statistically meaningful difference.

For completeness, the expert cohort's word counts range from 44 to 198, with
17 distinct values; the reader cohort ranges from 67 to 198, with 18 distinct
values. Among each cohort's 171 unordered work pairs, the length ordering agrees
with the expert reference on 43 and disagrees on 93, with 34 reference ties and
one length tie among non-tied references. For the reader reference, the counts
are 83 agree, 61 disagree, 26 reference ties and one length tie. Pairs reuse
works and are not independent observations. [aggregate.json](aggregate.json)
also records correlations between length and each model score.

## Limits and reproduction

The original 32-work plan yielded 27 complete HBQ banks; the same-data
three-way comparisons have 19 works per reference axis. These are selected,
already-open development cohorts with possible dependence among works and
raters. They do not establish population reliability, causal confounding,
superiority, human validation, or candidate promotion. No confidence intervals
or independent replications are added here.

`analyze.py` reproduces the aggregate given four private local inputs:

- `--source`: the retained HF32 analysis result, SHA-256
  `e8bfc8cb83c91f4f26c4f901bc0f9fef9e993072b509c175baccafcddaad9fe7`;
- `--requests`: the frozen request manifest, SHA-256
  `ab4adf5943e0eb12dd5e750e05ea63c5c99cafd3f2ec37c351d4bd05a62e9268`;
- `--cases`: the grouped completion result, SHA-256
  `469806acefd2f4cc92908f6b31e3c5f0afae3b4e8c15b9061892f89293994a0c`;
- `--prepared-root`: the directory containing the source files referenced by
  the request manifest.

The script checks these commitments, the per-file sizes and hashes, request
and artifact membership, and the matched score joins. It prints aggregate JSON
without story text or individual ratings. The inputs remain private, so public
readers need authorized access to reproduce the result. An independent local
check used the TTCW source references, regular-expression word counting and
pair-count midranks; it reproduced all ten reported correlations and both
pair-count strata.
