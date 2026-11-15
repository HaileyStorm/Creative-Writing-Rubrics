# HF32: sensitivity to ties and individual works

This post-result analysis revisits the same 17 availability-selected works in
the [expert and reader overlap report](../hbq-hf32-reference-overlap-v1/README.md).
It uses already-open development results and adds no model calls or human
labels. The expert reference is the mean of two expert creativity ratings;
the reader reference is the median of available nonexpert creativity ratings.
TTCW14 is the retained concise-evidence adaptation, not a native administration
of the original instrument.

For each pair with a non-tied human reference, we compare whether the method
orders the works in the same direction. The table shows HBQ minus TTCW14 in
percentage points under three symmetric conventions for scoring method ties:
zero, half or full credit. These are sensitivity conventions, not a claim that
a tie is correct. HBQ had no model ties on the eligible pairs; TTCW14 had 20
expert-reference and 22 reader-reference ties.

| Human reference | Zero tie credit | Half tie credit | Full tie credit |
| --- | ---: | ---: | ---: |
| Expert | +10.00 | +0.91 | -8.18 |
| Reader | +12.07 | +2.59 | -6.90 |

With half tie credit, removing each work in turn gives differences from -6.19
to +5.73 points for the expert reference and -1.50 to +8.25 for the reader
reference. The expert difference is negative for five of the 17 removals;
the reader difference is negative for three. Each deletion changes the set
and denominator of eligible pairs. The pairs share works: these deletion ranges
are neither confidence intervals nor significance tests.

The result is selected and retrospective. It does not establish a winner,
population performance, human validation, a causal mechanism or promotion of a
candidate. Missing banks, method scores and references remain outside this
complete-case cohort, which does not correct selection bias. Expert and reader
references are different aggregates and may share dependencies.

## Reproduction

`analyze.py` prints [aggregate.json](aggregate.json) from three retained private
inputs: the source analysis result (SHA-256
`e8bfc8cb83c91f4f26c4f901bc0f9fef9e993072b509c175baccafcddaad9fe7`),
request manifest (`ab4adf5943e0eb12dd5e750e05ea63c5c99cafd3f2ec37c351d4bd05a62e9268`),
and grouped-completion result (`469806acefd2f4cc92908f6b31e3c5f0afae3b4e8c15b9061892f89293994a0c`).
Supply them through `--source`, `--requests` and `--cases`. The script checks
their digests, the saved membership and score bindings, and emits aggregate
values only. Authorized access to private inputs is required; no story,
individual rating, work identifier or response is included here. An independent
local calculation reconstructed both reference axes and all 102 combinations
of reference, tie convention and single-work deletion from the same pinned
inputs. It does not establish independence, native provenance or wider validity.
