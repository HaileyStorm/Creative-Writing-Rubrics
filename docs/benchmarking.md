# Benchmarking with HBQ-RS

Use the stack as a *structured* judge, not as a single scalar disguised as truth.

## Read a score report

- **Canonical score:** the deterministic result for the artifact at the scope actually judged. A manuscript score is not reconstructed from chapter or scene scores; those remain diagnostic children unless a separately saved composite profile is explicitly reported.
- **Controls:** `hard_gate_status` reports objective eligibility separately from quality. `VALID` means every applicable binding requirement passed; author preferences and weighted goals can affect score but not this status.
- **Coverage:** the weighted share of applicable point-bearing criteria resolved `YES` or `NO`. `NOT_APPLICABLE` leaves are excluded; `CANNOT_ASSESS` leaves reduce coverage rather than counting as failures.
- **Observed score:** the deterministic score from assessed applicable criteria after capped penalties. Report it with coverage and controls, never alone.
- **Bounds:** `lower` and `upper` are the results if unresolved `CANNOT_ASSESS` criteria resolve adversely or favorably. They are not confidence intervals or error bars.

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

## Name the judge condition precisely

A model name is not a reproducible judge. Record the exact checkpoint or revision, quantization, serving runtime, prompt and schema versions, sampler settings, role, batch size, and polarity. Two roles using the same checkpoint are useful repeated conditions, but they are not an independent-model ensemble. Treat a later fine-tune or specialized checkpoint as a new condition.

Sampler settings belong to the task. A sampler that helps drafting may hurt grading or exact evidence transfer, so do not carry a creative-generation profile into judging without a separate calibration result. Model confidence is also diagnostic until it is calibrated against repeated decisions and external labels; it does not change canonical score or coverage by default.

## Confidence diagnostics

`report.confidence` remains for compatibility. It is the legacy domain-point-weighted mean across assessed domains, not an effective-leaf calculation.

Versioned score reports carry the optional `confidence_diagnostics` field. Unversioned `score.json` files remain v1 evidence; current runner surfaces leave those parents untouched and atomically write a hash-bound `score.v2.json` descendant. V2 reports secondary role diagnostics for `domain`, `hard_gate`, `penalty`, and `supplemental` leaves using effective leaf weights. They never change the canonical score, coverage, penalties, gates, bounds, or status. An empty or wholly unassessed role has `null` ratios and is rendered as **Not observed**.

The `cwr score` command emits v2 by default. Use `--report-version 1` only to independently reconstruct the semantics of an immutable runner-owned `score.json` parent; the explicit v1 path restores the same materialized weight-profile audit and does not claim byte-identical serialization or reinterpret v2 evidence as v1.

## Intervals and coverage

`CANNOT_ASSESS` widens the interval. If coverage is below the bundle threshold, the result is `PROVISIONAL` and must not drive unattended acceptance. Missing modalities (no audio for an audio leaf) are `CANNOT_ASSESS`, not `NO`.

For worked public examples, see the [established-rubric repeatability study](../evaluation-results/the-part-that-arrives-first-repeatability/established-v4/), its [authorized source story](../evaluation-results/the-part-that-arrives-first-repeatability/source.md), and the sanitized [Gray Blood long-form comparison](../evaluation-results/gray-blood-ch1-6/).

## Bias controls

Hide author and model identity. Shuffle candidate order. Do not reward length or rhetorical confidence unless a leaf asks for it. Keep user-taste overlays out of the craft total.

## What this is not

HBQ-RS does not claim human-agreement proof from syntax checks or a single uncalibrated model. Calibrate against a labeled set before treating deltas as significant.
