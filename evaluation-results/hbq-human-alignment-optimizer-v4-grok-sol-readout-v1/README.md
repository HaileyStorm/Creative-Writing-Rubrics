# Matched Grok versus Sol descriptive readout

This provider-free readout verifies the frozen set of 33 successful exact prompt/schema-matched pairs using the pinned exec-v3 Sol lifecycle verifier and the admitted Grok native-observation proofs. The two immutable terminal Sol cells and every failed or preparation-only root are excluded. Sol evidence remains explicitly limited to a verified local Codex lifecycle with native endpoint contact cardinality unproven. Historical route evidence is replayed from each root’s mutually bound prepared/proof/receipt artifacts; it is not presented as current route evidence.

The internal replay recomputes endpoint scores from native evidence. Across the 33 frozen pairs, the covered-only mean absolute difference is `0.4392` over `172` covered pair-by-dimension observations. This is a descriptive discrepancy for this sample, not an agreement or interchangeability estimate. The public result contains stable item/candidate/cell identifiers, prompt hashes, uncovered dimensions, per-pair absolute differences, exact aggregate denominators, and covered-only difference means. It omits endpoint score means because the compact public artifact does not duplicate per-pair endpoint scores. Dimensions not covered by a Grok observation remain visible for that pair but are excluded from every paired aggregate. Exact provider, requested/effective/reported model, requested reasoning, reasoning-attestation ceiling, route, transport, and identity-evidence fields are explicit.

The result binds the frozen-successor, HANNA CSV, analyzer, analyzer contract, and pinned executor/admission code and contract bytes by SHA-256. Publication recomputes aggregates and pair differences from the full verified readout, requires exact false claims and evidence ceilings, and rejects fabricated aggregates, provider/contact reuse, provider/session reuse, duplicate item/candidate pairs, and misassociated roots.

The artifact contains no story text or response-evidence prose and supports no selection, substitution, generalization, provider-quality, or model-ranking claim.

The [dimension coverage summary](dimension-coverage.json) adds covered-only
absolute differences and the same summaries restricted to the 22 pairs with all
six dimensions covered by Grok. **Coverage in that historical summary reflects
Grok only; it does not require Sol coverage.** A subsequent check of retained
Sol response coverage found that eight of the 172 Grok-covered dimensions were
uncovered by Sol (four empathy and four relevance), leaving 164 covered by both.
Only 16 pairs have all six dimensions covered by both. Treat the original
Grok-only summaries accordingly; their saved results remain unchanged.
Dimension-specific estimates otherwise use different subsets; missing Grok
dimensions are never imputed. The seven item clusters and
candidate/dimension observations are dependent, and these post-result summaries
do not establish agreement or generalize to new material. The published data
omit signed scores, so provider offsets, score ranks and ordering reversals cannot
be recovered. Regenerate the summary from the pinned public result with
`python evaluation-results/hbq-human-alignment-optimizer-v4-grok-sol-readout-v1/dimension-coverage.py`.

To reproduce the already disclosed both-endpoint coverage counts, run
`python evaluation-results/hbq-human-alignment-optimizer-v4-grok-sol-readout-v1/both-covered-counts.py`.
This requires the original local receipt, admission-proof and response directories;
the public package alone is insufficient. It verifies their retained hashes and
identity bindings but does not rerun full historical admission. Successful output
contains only aggregate counts and limitations, not scores or per-pair coverage.
Errors and tracebacks can contain local paths and identifiers; review them before
sharing logs.
