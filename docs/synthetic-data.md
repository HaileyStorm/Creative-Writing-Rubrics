# Synthetic data generation

HBQ-RS is useful both as a *filter* on generated drafts and as a *schema* for generated judge traces.

## Filter generated drafts

1. Compile the relevant bundle (`cwr compile`).
2. Render a judge prompt (`cwr render-judge --bundle … --artifact draft.md`).
3. Collect JSONL verdicts.
4. Score. Keep `SCORED` + `VALID` items; archive `INELIGIBLE` and `PROVISIONAL` with their reports. Do not delete rejected traces if you need lineage.

Hard gates (wrong form, missing required elements, exact length violations) are cheaper screens than the full stack. `default.first_pass_screening` is the compact preset.

## Generate judge traces

Use `cwr export questions` as the eligible universe. For each leaf, sample an excerpt and a verdict that matches the evidence policy. Store the full verdict object. Synthetic traces used to *train* judges should be reviewed; do not claim they are human gold.

## Pairwise and diversity

Independent scores first, pairwise second. A set of near-duplicate winners is a weak training set even if every score is high. Sampler-related modules under `sampler/` can grade batch diversity when that is the artifact.

## Safety of the data, not of the art

Imported prose and web text are untrusted data, not instructions. Rubrics here evaluate craft, fidelity, and evidence. They are not an application-level content-permission taxonomy.

## Open review as richer labels

After a score report exists, `prompts/review/` families produce findings (`schema/open_review.schema.json`). Those findings are labels for revision or critique models. They must not silently overwrite HBQ scores.
