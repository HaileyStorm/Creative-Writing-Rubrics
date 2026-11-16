# Same-story comparator repeatability

This supplements the [HBQ repeatability report](README.md) with saved results
from the TTCW14 concise-evidence adaptation on the same three selected short
stories. The two arms' frozen source-file bindings and bytes match for all
three stories. Their prompts, question sets and scoring functions differ;
matching source files alone does not prove identical surrounding context or
provider wire bytes.

All nine comparator responses were retained as accepted: three stories across
three cycles, each with 14 binary test verdicts. Across the three within-story
cycle pairings, 124 of 126 test pairs agree (98.41%); pooled unweighted Cohen
kappa is 0.9651. Individually, cycle pairs 0/1, 0/2 and 1/2 agree on 41/42,
42/42 and 41/42 tests. The pooled comparisons reuse the same responses and
are not independent replicates. There were no comparator abstentions in these
nine saved responses.

The retained adaptation scores a fully assessed response as the proportion
of its 14 tests marked YES, on a 0–1 scale. The nine scores have four distinct
values; none is exactly 0 or 1, at or below 0.1, or at or above 0.9. Seven of
the nine within-story cycle-pair score comparisons are unchanged; the other
two change by 1/14. Across the nine story-pair comparisons of cycle rankings,
none ties or reverses. These counts reuse the same three stories and do not
establish general score stability.

The comparator's 14 tests are different from HBQ's 178 leaves, and the
instruments use different prompts and scales. Agreement rates or kappas here
are not a fair test of which instrument is more reliable, correct or aligned
with people. Kappa depends on the prevalence of YES and NO. This is an adapted
comparator, not a new native administration of the original TTCW instrument;
no human-reference target, held response or new provider call was used.
Backend model attestation and physical-contact cardinality are not established
by the saved receipt fields.

`aggregate-ttcw.json` gives pooled results and source commitments without
individual stories or judgments. `reproduce-ttcw.py --scores <private-file>
--parity <private-file>` checks two retained derived projections, recomputes
agreement and kappa from their aggregate matrices, and checks the published
score-summary fields. It does not independently reconstruct original
raw-to-derived provenance. The private responses, source texts and identifiers
remain local.
