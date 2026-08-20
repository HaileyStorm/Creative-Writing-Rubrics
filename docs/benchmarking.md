# Benchmarking with HBQ-RS

Use the stack as a *structured* judge, not as a single scalar disguised as truth.

## Report the control fields

Every published score should include:

- `bundle_id` and bundle version
- `hard_gate_status` (`VALID` / `INVALID` / `UNRESOLVED`)
- `coverage` and `minimum_coverage`
- `status` (`SCORED` / `PROVISIONAL` / `INELIGIBLE` / `UNRESOLVED`)
- `final_score.lower` / `observed` / `upper`
- judge identity, prompt hashes, and whether order-swapped pairwise was used

A leaderboard that drops hard-gate failures into the quality average is lying about both eligibility and craft.

## Recommended protocol

1. Freeze the bundle and any dynamic task module before candidates are visible.
2. Grade independently. Do not condition later leaves on a desired ranking.
3. For close finalists, run `prompts/judge/PAIRWISE_FINALIST_PROMPT.md` twice with swapped order. Disagreement is a tie or an escalation, not a coin flip.
4. Attach judge meta-rubrics when you are measuring the *judge*:
   - `meta.judge_bias_and_calibration_control`
   - `op.select.judge_confidence_and_evidence_quality`
   - `op.select.rubric_application_quality`
5. For long work, follow `prompts/judge/LONG_FORM_PROTOCOL.md`. Never publish the mean of chapter scores as a manuscript score.

## Intervals and coverage

`CANNOT_ASSESS` widens the interval. If coverage is below the bundle threshold, the result is `PROVISIONAL` and must not drive unattended acceptance. Missing modalities (no audio for an audio leaf) are `CANNOT_ASSESS`, not `NO`.

## Bias controls

Hide author and model identity. Shuffle candidate order. Do not reward length or rhetorical confidence unless a leaf asks for it. Keep user-taste overlays out of the craft total.

## What this is not

HBQ-RS does not claim human-agreement proof from syntax checks or a single uncalibrated model. Calibrate against a labeled set before treating deltas as significant.
