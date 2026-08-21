# Changelog

## 1.1.0 — 2026-08-20

- Added hash-bound v2 score descendants with optional effective-leaf confidence diagnostics by rubric role; retained immutable v1 score parents and legacy domain-point `report.confidence` compatibility.
- Added strict task contracts that keep weighted author goals separate from objective binding requirements.
- Added `cwr longform` for deterministic segmentation, constrained route selection, mapping, complete-source scoring, complete scope-correct local diagnostics by default, explicit WIP handling and opt-in sampling, bounded parallel workers, resumable reports, and accessible SVG/HTML output.
- Added optional hierarchical score profiles, a manuscript-bound profile generator, and offline full-report and embeddable-scorecard output with disclosed custom weights.
- Added optional offline setup, weight, report, scorecard, and status pages. They are CLI-generated helpers with no server, telemetry, template editor, or theme system.
- Added multi-sample batch manifests for independent automatic routing, one-sample shared routing, and plan-first per-sample review.
- Added bundle and task-contract overrides for controlled draft comparisons, plus a selected-question diagnostic report that prevents partial bundle runs from producing composite scores.
- Added `applies_when` and source references to judge packets, plus task-contract support across compile, score, render, and judge commands.
- Reframed the Gray Blood comparison as two matched six-chapter evaluations with valid whole-work scores and complete scope-correct chapter diagnostics.
- Published a complete short story and a frozen five-run repeatability study comparing batched HBQ, single-batch HBQ, compact analytic, and holistic judging.
- Added typed judge evidence: source-exact quotations are verified against the supplied artifact or context, while non-verbatim support is labeled as a summary; historical verdict files remain readable.
- Added bounded automatic retries for rejected binary batches, with every rejected provider response preserved outside the accepted checkpoint chain.
- Added an optional, tool-disabled Grok Build CLI provider with strict envelope validation and explicit disclosure when the CLI cannot attest the requested reasoning effort.
- Added the optional Windows Nous tool-free bridge provider, restricted to the declared DeepSeek V4 Flash and V4 Pro fallback models at `max`; unattested provider reasoning requires an explicit provisional opt-in.
- Kept all stable registry, bundle, criterion, and question IDs unchanged.

## 1.0.0 — 2026-08-20

- Public extract of HBQ-RS 1.0.0: 277 modules, 2,139 binary leaves, 85 bundles.
- Deterministic compile/score library and `cwr` CLI (validate, compile, score, list, show, pack, export, render-judge).
- Resumable `cwr judge` runner for OpenAI-compatible endpoints and Codex CLI, with explicit remote-send disclosure and a strict response schema.
- Quote-free long-form case-study groundwork with score reports, state maps, and comparative synthesis from two private six-chapter drafts.
- Judge protocols plus generalized open-review families.
- Neutralized two-role display wording; stable module, question, bundle, and criterion IDs unchanged.
- Apache-2.0 license for this original synthesis. Bibliographic sources remain separately licensed.
