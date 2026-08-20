# Changelog

## 1.1.0 — 2026-08-20

- Added strict task contracts that keep weighted author goals separate from objective binding requirements.
- Added `cwr longform`: deterministic segmentation, constrained route selection, mapping, complete-source scoring, scope-correct complete-by-default local diagnostics, explicit WIP rules, bounded parallel workers, opt-in sampling, resumable reports, and accessible SVG/HTML output.
- Added strict optional hierarchical score profiles, a manuscript-bound profile generator, and an offline full report plus embeddable scorecard with disclosed custom weights.
- Added optional offline setup, weight, report, scorecard, and status pages; they remain CLI-generated helpers with no server, telemetry, template editor, or theme system.
- Added strict multi-sample batch manifests with independent automatic routing, one-sample shared routing, and plan-first per-sample review policies.
- Added explicit bundle and task-contract overrides for controlled draft comparisons.
- Added a strict selected-question diagnostic report; partial bundle runs no longer produce misleading composite scores.
- Added `applies_when` and source references to judge packets, plus task-contract support in compile, score, render, and judge commands.
- Reframed the Gray Blood comparison as two matched six-chapter evaluations with valid whole-work scores and fixed-subset chapter diagnostics.
- Published a complete short story and a frozen five-run repeatability study comparing batched HBQ, single-batch HBQ, compact analytic, and holistic judging.
- Added typed judge evidence: source-exact quotations are verified against the supplied artifact or context, while non-verbatim support is labeled as a summary; historical verdict files remain readable.
- Kept all stable registry, bundle, criterion, and question IDs unchanged.

## 1.0.0 — 2026-08-20

- Public extract of HBQ-RS 1.0.0: 277 modules, 2,139 binary leaves, 85 bundles.
- Deterministic compile/score library and `cwr` CLI (validate, compile, score, list, show, pack, export, render-judge).
- Resumable `cwr judge` runner for OpenAI-compatible endpoints and Codex CLI, with explicit remote-send disclosure and a strict response schema.
- Quote-free long-form case-study groundwork with score reports, state maps, and comparative synthesis from two private six-chapter drafts.
- Judge protocols plus generalized open-review families.
- Neutralized two-role display wording; stable module, question, bundle, and criterion IDs unchanged.
- Apache-2.0 license for this original synthesis. Bibliographic sources remain separately licensed.
