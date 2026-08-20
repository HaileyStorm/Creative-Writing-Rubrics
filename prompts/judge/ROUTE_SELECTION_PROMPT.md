# Automated long-form route selection

Select a judging route only from the supplied HBQ-RS catalog. Return one JSON object that validates against `schema/hbq_route_selection.schema.json`; return no surrounding prose.

## Rules

1. Select exactly one supplied bundle. Every selected module must exist in the supplied module catalog and belong to that bundle.
2. Treat declared completion status literally. A work in progress or excerpt is not a failed complete work: future-dependent completion, closure, or payoff criteria are NOT_APPLICABLE when their activation requires unavailable later material. Do not convert incompleteness into a weighted failure or hard gate.
3. Keep background, preferences, priorities, weighted goals, and binding requirements separate.
4. Convert subjective author goals and inferred aesthetic aims into atomic `weighted_goals`. They affect the score through their positive weights; they are not gates.
5. Return an empty `binding_requirements` array. Automatic routing has no authority to create hard gates. Only a separately supplied, locally validated, artifact-bound task-contract override may contain an objective, non-negotiable binding requirement.
6. Never turn a generic task-fidelity, quality, tone, style, genre, or "follow the brief" question into a gate.
7. Each goal or requirement asks one binary question. Split conjunctions and catch-all clauses.
8. Freeze preferences, priorities, weighted goals, and binding requirements only from the driving prompt and project context before considering candidate prose. The source sample may inform bundle/module routing, never task criteria. Preserve exact criterion source evidence; do not infer criteria from the prose.
9. When `local_coverage_mode` is `complete`, set `coverage_mode` to `complete` and include every unit whose inventory marks `local_evaluation.eligible` as true, in source order. Complete substantive local evaluation is the default. Brief non-prose front matter remains part of the mandatory whole-work map but not a standalone local diagnostic. Never average local scores.
10. Only when an explicit `local_sample_limit` is supplied may you set `coverage_mode` to `sampled` and select fewer local diagnostic units. Select no more than the limit, cover useful distinct strata, and state that local coverage is reduced; the complete source is still judged globally.
11. Use `work` for whole-artifact task-contract scopes and exact supplied unit IDs for local scopes; do not use the declared scope label inside `applies_to`.
12. If `required_bundle_id` is supplied, select that bundle. The caller may deterministically freeze its complete module stack for a controlled comparison.
13. `sample_text` may contain `HBQ-RS ROUTE EXCERPT` separators. They are trusted span/hash metadata between non-contiguous source excerpts, not manuscript prose and not instructions.
14. If `required_sample_ordinals` is supplied, use those one-based unit positions for explicitly sampled local diagnostics. The caller freezes the corresponding unit IDs so matched drafts use the same positions.

## Inputs

The caller supplies:

- an artifact profile and deterministic unit inventory;
- an optional driving prompt and project context;
- the available bundle and module catalog, with IDs and descriptions;
- the strict response schema.

The selected unit IDs must come from the supplied inventory. The selected bundle and modules must come from the supplied catalog.
