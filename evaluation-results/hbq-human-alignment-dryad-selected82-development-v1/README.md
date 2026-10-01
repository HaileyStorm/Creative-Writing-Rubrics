# Dryad selected-82 development aggregate

This is an aggregate-only, private-source-derived development result. Its
public-redaction and provenance audit was completed on 2026-10-01. It contains
no story text, raw human
ratings, evaluator identities, individual targets, or model responses. The
three exact local source-report hashes and machine-readable aggregate are in
[summary.json](summary.json); the private reports are not included here.

The immutable 100-story collection was retained. The owner designated 18
low-coverage DEV stories for exclusion from this analysis, leaving 70 TRAIN
and 12 DEV. This does **not** admit the original 100-story study. The frozen
TRAIN fit was tested on the 12 selected DEV stories on Grok and then on Sol
without refitting or further provider calls. The Dryad human targets reflect
regular-reader judgments, not publishing-expert judgments.

| Endpoint | Baseline novelty/usefulness rho | Candidate novelty/usefulness rho | Paired-bootstrap 2.5% lower bound | Retained? |
| --- | ---: | ---: | ---: | --- |
| Grok | 0.5245 / 0.4266 | 0.6224 / 0.5524 | 0.0000 | No |
| Sol | 0.4476 / 0.3636 | 0.5664 / 0.5804 | 0.0000 | No |

The frozen rule required a **strictly positive** lower bound from 2,000
paired bootstrap replicates. Positive point estimates on twelve stories do
not pass it. The candidate is neither a runtime default nor a promoted rubric.

The same identities show one Grok score at or below 10, no Grok score at or
above 90, no Sol score at or below 10, and one Sol score at or above 90 under
each profile. Mean absolute Grok–Sol score distance increased from 20.38 to
22.15, though the maximum decreased from 30.70 to 26.75. These are score-range
and cross-endpoint descriptions, **not** within-endpoint repeatability, and
the candidate cannot be characterized as a uniform improvement.

The audit matched the three exact private source-report hashes in
`summary.json` to their retained TRAIN, DEV, and Sol files and checked this
package for story text, individual ratings, assessor identities, request or
session IDs, and model responses. No source or annotation bytes are published
by this package. Aggregate publication is not product release; independent
confirmation and the other release criteria remain outstanding.
