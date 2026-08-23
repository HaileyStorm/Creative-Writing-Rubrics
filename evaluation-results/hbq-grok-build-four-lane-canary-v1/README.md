# Grok Build four-lane canary v1

This packet preserves four completed public-synthetic broker results. All four
started at `2026-08-23T00:14:33Z`; they finished between `00:15:27Z` and
`00:16:19Z`, with one attempt each and four delivered results. The route was
healthy and armed at a host-wide cap of four.

| Output | Provisional use |
| --- | --- |
| `preface-ablation-2x2.json` | A held-out 2x2 test for separating origin wording from strictness wording. |
| `sparse-human-reference-portfolio.json` | A small, separated portfolio for overlap repair, expert edits, and non-overlap benefits. |
| `batch-breakpoint-hunt.json` | A gated, progressive batch-size search rather than an exhaustive grid. |
| `mature-fiction-measurement-contrast.json` | A compact contrast of refusal, schema/quote failure, and existing-label suitability. |

These are design suggestions, not decisions, judge scores, causal findings,
human-alignment evidence, model promotion, or paid evaluation. They may inform
later preregistration and review only.

The broker requested `grok-4.6` at `high`; Grok Build reported
`grok-4.6-build`. Reasoning effort was requested but not attested. The route
used isolated, one-turn, read-only calls. Its `costUSD` fields are retained as
included weekly-allowance usage telemetry for the zero-charge saved-session
route, not as an incremental paid evaluation.

What this canary establishes is narrow: four bounded broker calls overlapped
and completed under the reviewed host-wide cap of four. It does not establish a
general throughput guarantee, capacity beyond four, model quality, or the
correctness of any suggestion in the result files.

Run `python validate.py` from this directory to verify the copied result hashes,
shared runtime identity, timings, result envelope shape, and the safe broker
snapshot. That snapshot binds the route/gate cap, 4/4 completed-and-delivered
status, one completed attempt per item, evidence hashes, and usage telemetry.
The manifest does not publish prompts, source queue paths, owner attestation,
or session IDs.
