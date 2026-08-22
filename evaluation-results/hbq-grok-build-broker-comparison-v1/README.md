# Grok Build broker comparison v1

Two completed, public-synthetic advisory runs through the zero-charge Grok Build
broker. They are useful comparison input for the HBQ-RS repair plan, not judge
scores, causal evidence, or a model promotion.

| Run | Narrow use | Product-useful take |
| --- | --- | --- |
| `overlap-repair-ladder` | Rank repair hypotheses | Start with frozen-output/rollup checks, then vary one factor at a time. |
| `smallest-falsifiable-matrix` | Bound the next experiment | Compare singleton with 24 first; use intermediate sizes only as diagnostics and 178 only as stress. |

Both runs requested `grok-4.6` at `high`; the CLI reported
`grok-4.6-build`. The CLI did not attest that reasoning effort was honored.
Each used an isolated, one-turn, read-only session. The telemetry is included
weekly-allowance accounting on the owner-attested zero-charge saved-session
route; it is not evidence of an incremental paid evaluation.

## What the evidence supports

- Keep the full 2,145-leaf registry for product coverage; report any
  HANNA-oriented slice beside it rather than shrinking the product profile.
- First isolate reporting/aggregation from leaf behavior using frozen verdicts.
- Then test batch size, polarity, and wording separately on relevant overlap
  leaves, with development reuse followed by a small frozen holdout.
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
private broker records without publishing their prompts, raw conversation
material, filesystem paths, or session identifiers.
