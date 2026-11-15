# HF32: expert and reader references on shared works

This post-result analysis compares the already-open expert and reader
references on the same available works in the HF32 development pilot. It adds
no model calls, ratings or labels. The [original report](../hbq-hf32-frozen708-human-reference-v1/README.md)
describes the cohort and the [length baseline](../hbq-hf32-length-baseline-v1/README.md)
describes the earlier 19-work comparisons.

The expert reference is the mean of two finite expert creativity ratings; the
reader reference is the median of available finite nonexpert creativity
ratings. Of 27 complete HBQ banks, 21 works have both references, four have
only the expert reference, and two only the reader reference. Availability of
both method scores narrows the comparison to 17 works. The two separately
matched comparisons have 19 works each.

| Reference | Word count rho | Historical HBQ rho | TTCW14 rho |
| --- | ---: | ---: | ---: |
| Expert mean | -0.401467 | 0.315155 | 0.270009 |
| Reader median | 0.235642 | 0.393332 | 0.385712 |

On the same 17 works the expert-versus-reader Spearman correlation is 0.014878.
Among their 136 unordered pairs, 48 have matching reference directions and 46
opposing directions; 22 tie only on the expert reference, 16 tie only on the
reader reference, and four tie on both. These pairs reuse works and are not
independent observations. Word count uses whitespace-separated tokens from the
pinned source story, excluding prompt and context.

The opposite signs for length persist within this selected common subset;
this is not evidence that length causes ratings or that the expert and reader
populations differ. The small, availability-selected cohort and its different
reference aggregates limit interpretation. No uncertainty interval, new
confirmation, method superiority or candidate promotion follows. The five
incomplete HBQ banks and other unavailable method or reference values remain
outside this complete-case analysis; it does not correct missingness.

## Reproduction

`analyze.py` produces [aggregate.json](aggregate.json) using four private
inputs: the source analysis result (SHA-256
`e8bfc8cb83c91f4f26c4f901bc0f9fef9e993072b509c175baccafcddaad9fe7`),
request manifest (`ab4adf5943e0eb12dd5e750e05ea63c5c99cafd3f2ec37c351d4bd05a62e9268`),
grouped-completion result (`469806acefd2f4cc92908f6b31e3c5f0afae3b4e8c15b9061892f89293994a0c`),
and prepared-root directory referenced by that manifest. Supply these through
`--source`, `--requests`, `--cases` and `--prepared-root`. The script checks
input commitments, artifact membership and the pinned adjacent length-baseline
helper. Authorized access to private inputs is required; the public aggregate
does not include stories or individual ratings. An independent local check used
the comparator source references and pair-count midranks to reproduce all
seven correlations and the five pair categories.
