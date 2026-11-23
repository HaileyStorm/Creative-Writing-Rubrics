# Missingness sensitivity of saved confidence and repeat flips

This retrospective, provider-free supplement uses the previously saved P2
confidence aggregate for three selected short stories and 178 leaves each. It
compares binary YES/NO verdict changes from the first cycle to each later cycle,
separately for first-cycle confidence `[0.75, 0.9)` and `[0.9, 1]`. It does
not assess whether either verdict is correct.

| Comparison | Lower confidence flips / binary pairs | Higher confidence flips / binary pairs | Observed rate difference | Relaxed minimum difference |
| --- | ---: | ---: | ---: | ---: |
| First to second cycle | 18 / 126 | 5 / 332 | 12.78 percentage points | 6.14 points |
| First to third cycle | 16 / 126 | 8 / 332 | 10.29 percentage points | 3.71 points |

There are 534 planned leaf pairs per comparison, 510 observed, and 24 missing
first-cycle states. Each missing item is allowed to be excluded or placed in
either reported confidence bin with a binary flip or nonflip. Exact rational
enumeration produces the minimum and maximum lower-minus-higher flip-rate
differences over that relaxed assignment space. For each reported minimum,
the relaxation puts all 24 missing items in the higher-confidence bin as flips.
This assignment is hypothetical; it is not an imputation or a claim about the
missing verdicts. It even ignores constraints from the retained later states,
so the bounds can be wider than the actual feasible range. The same 24 missing
first-cycle states occur in both comparisons; they are not 48 distinct losses.

The pattern is descriptive and was examined after the data were available.
The stories, leaves and cycles are dependent; these are logical bounds, not
confidence intervals or probabilities. They do not establish calibration,
human alignment, causation, a confidence threshold, or population reliability.
A retained worklog entry reports that a separate-method source recount finished
and matched the aggregate's counts; it used the same reviewed input guard. A
separate read-only review confirmed that the saved aggregate and that entry
both name 204 accepted packets, 1,578 leaf outcomes and input-inventory SHA-256
`76070192abe1bf62a24940786f066039c6f60ff868ee97a9efb25ed6401bac4b`.
This corroborates the association but does not authenticate the recount's
execution. A later entry describes a recount as running without identifying
an attempt, so its relationship to the completed recount is unclear. The
original terminal evidence has not been independently recovered. These
calculations authenticate the aggregate's bytes and arithmetic, not its native
admission or model identity.

`python analyze.py <private-retained-aggregate.json>` prints the output in
`aggregate.json` after checking its source hash. The source stays private; no
story text, individual verdicts, identifiers, human labels or responses are
published here. This report makes no provider calls and adds no votes.
