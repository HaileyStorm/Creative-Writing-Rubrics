# Selected short-story repeatability: pooled saved-state results

This descriptive analysis uses three selected short stories, 178 HBQ leaves
per story and three planned cycles. A later retained snapshot recorded 213 of
216 planned requests accepted across HBQ and a separate comparator arm; the
remaining three HBQ packets are held. The figures below concern HBQ leaves
only. This is a partial, selected development study, not a population sample.

Across the 1,554 observed within-story leaf/cycle pairs, 1,480 agree
(95.24%). Six of those agreements are `CANNOT_ASSESS` in both cycles; those
matches do not represent successful assessment. On the fully observed later
two cycles alone, 511 of 534 leaf pairs agree (95.69%). These latter pairs
are included in the first total, not additional observations.

The missing first-cycle packets leave 24 leaf states unknown and therefore
48 of the 1,602 planned pair comparisons unobserved. For each of those 24
leaves, the two saved later-cycle states agree. If a missing state is allowed
to take any of the four verdict states independently, it can match neither or
both later states. The resulting descriptive full-plan agreement bounds are
1,480–1,528 out of 1,602 (92.38%–95.38%). These are logical bounds under the
stated assignment space, not confidence intervals or probabilities. They do
not impute the missing states or establish that each assignment is a valid
literary judgment.

The comparisons share stories, leaves and cycle outputs; they are dependent.
Agreement is sensitive to the mix of verdict states and does not establish
correctness, human alignment, general reliability, model equivalence, or
superiority over the comparator. Saved receipt fields report the requested
model and settings, but backend model attestation and physical-contact
cardinality were not independently established. No held request was retried or
released for this analysis, and no human target was read for it.

## Reproduction and scope

`aggregate.json` contains pooled counts and opaque source commitments only.
`reproduce.py --observed <private-file> --unstable <private-file> --bounds
<private-file>` regenerates it from three retained, digest-pinned **derived**
projections. It checks the cycle totals, transition totals, missing-cell
condition, and agreement bounds; it does not regenerate those projections
from original records. The private projections, underlying source texts,
individual responses, case/leaf identifiers, and held records are not
published here. A source-level audit of those records and their local hashes
is retained separately; the public aggregate alone cannot independently prove
native admission, provider identity, or the source-to-projection derivation.
