# Grok Build broker comparison v1

Four completed, public-synthetic advisory runs through the zero-charge Grok
Build broker. They are useful comparison input for the HBQ-RS repair plan, not
judge scores, causal evidence, or a model promotion.

| Run | Narrow use | Product-useful take |
| --- | --- | --- |
| `overlap-repair-ladder` | Rank repair hypotheses | Start with frozen-output/rollup checks, then vary one factor at a time. |
| `smallest-falsifiable-matrix` | Bound the next experiment | Compare singleton with 24 first; use intermediate sizes only as diagnostics and 178 only as stress. |
| `repeat-slot-contract` | Specify multi-run aggregation | A repeat is a stable `(leaf, repeat_index)` slot; repair replaces the slot and reduction happens before rubric weighting. |
| `small-product-bakeoff` | Bound four-arm comparison | Use a sparse 3 stories × 3 repeats × 4 arms development baseline; expand only for an unresolved decision. |

All four runs requested `grok-4.6` at `high`; the CLI reported
`grok-4.6-build`. The CLI did not attest that reasoning effort was honored.
Each used an isolated, one-turn, read-only session. The telemetry is included
weekly-allowance accounting on the owner-attested zero-charge saved-session
route; it is not evidence of an incremental paid evaluation.

The latter two runs were the successful concurrency canary: both started at
`2026-08-22T23:31:29Z`, under the route's `max_concurrency=2`, and completed
one second apart (`23:32:22Z` and `23:32:23Z`). This proves two bounded broker
calls can overlap on this route; it does not establish a throughput guarantee
or model-quality result.

## What the evidence supports

- Keep the full 2,145-leaf registry for product coverage; report any
  HANNA-oriented slice beside it rather than shrinking the product profile.
- First isolate reporting/aggregation from leaf behavior using frozen verdicts.
- Then test batch size, polarity, and wording separately on relevant overlap
  leaves, with development reuse followed by a small frozen holdout.
- Model `repeat_count` as full passes over a frozen leaf set: each accepted
  slot is keyed by `(leaf, repeat_index)`, a repair is not an extra vote, and
  each leaf is reduced before its deterministic rubric weight is applied.
- Use the sparse 3 × 3 × 4 comparison as a development design input, not a
  completed bakeoff or fixed production threshold.
- Treat the existing 96% retry agreement, 92% exact-quote support, one-story
  polarity pilot, and generated-only HANNA macro as directional diagnostics,
  not promotion evidence.

## Corrections and limits

The first response incorrectly described 2,145 leaves as a possible batch
shape and overstated that existing retry data makes leaf noise unlikely. The
registry count is not a batch-size observation, and one-story retry evidence
cannot rule out stable-but-wrong verdicts. The second response supplies the
usable staged matrix: singleton versus 24 first; sizes below 24 only if the
comparison or product constraints warrant them; 178 as capacity stress only.
It is advisory design input, not causal evidence, and does not require all
2,145 leaves in every targeted experiment.

`summary.json` exposes the compact conclusions; `manifest.json` binds the two
earlier and two concurrent private broker records without publishing their
prompts, raw conversation material, filesystem paths, or session identifiers.

The small-product-bakeoff response has three deliberate limits: a tied arm is
not automatically decided by cost or length without product-quality tradeoffs;
quote and coverage metrics remain protocol-aware, though a separately defined
uniform evidence wrapper may be compared later; and suggested kill/promote
thresholds are heuristics to preregister, not universal facts.
