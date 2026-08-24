# S2 disjoint passage-status holdout: aggregate result v1

This is the aggregate-only public projection of the settled
`hbq-nonpoetry-scope-disjoint-holdout-v1-execution-v1` execution. It does not
copy its external execution root, fixtures, carriers, labels, prompts,
responses, evidence, individual outcomes, session metadata, or private
controller material.

All 48 planned singleton slots completed. Each settled slot records one
accepted provider call and one batch attempt; there were zero post-response
retries. Both baseline and candidate arms passed all four control cells. Across
the eight cells in each arm, baseline passed five and candidate passed six. The
candidate passed both explicit material-failure cells (2/2), where baseline
passed neither (0/2). It passed neither missing-required-evidence cell (0/2),
where baseline passed one (1/2), and therefore did not reach 3/3 in all eight
candidate cells.

The frozen outcome is `NO_GO`; no wording, rubric, leaf, ownership, split, or
weight change is promoted. The candidate failed this frozen comparison, but
the result does not establish that its wording is substantively invalid. The
missing-required-evidence difference is a semantic/oracle dispute about a
silent disposition being `YES` versus
`CANNOT_ASSESS`, not an independently resolved causal diagnosis. It is negative
development evidence about this frozen comparison, not a claim that the
underlying scope distinction is invalid or abandoned. A separately frozen
successor is required before another evaluation; DSPy was not used in this
execution.

`public-result.json` contains only aggregate counts and SHA-256 commitments to
the immutable execution claim, settlement, and public aggregate projection.
