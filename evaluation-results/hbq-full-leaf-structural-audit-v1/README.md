# HBQ-RS full-leaf structural audit v1

This public, read-only package freezes a deterministic structural inventory of all 2,145 HBQ-RS leaves. It records ownership, provenance, routing, polarity, scope, evidence, materiality, and complete lexical pair candidates. It does not evaluate prose, call a model, or select a rubric remedy.

Run `python generate.py --check` to verify the frozen inputs and every generated output. The source inputs are hashed as UTF-8 with CRLF canonicalized to LF, and are compared to the exact Git blobs at the pinned parent revision; a Windows checkout cannot silently redefine the evidence. Running without `--check` regenerates `leaf-audit.jsonl`, `findings.jsonl`, `summary.json`, and `manifest.json` from those pinned public registry inputs.

The lexical scan examines every unordered leaf pair, without top-K truncation. NFKC/lower/punctuation folding, boilerplate tokens, thresholds, and threshold sensitivity are frozen in `audit-contract.json`. A lexical candidate is not semantic-duplication proof. Scope-binding candidates mean only that nonlocal wording coexists with a current-artifact/zero-neighbor default; that default does not prove local-only evidence. Static scope and surface-polarity candidates are review queues only: none assigns a first remedy, changes leaf ownership, splits a leaf, rewrites wording, or reweights a module.

The audit explicitly preserves the current ownership boundary: `core.freshness_and_non_genericness.no_default_metaphors` remains the stockness owner, while `penalty.purple_prose.proportion` and `penalty.purple_prose.fatigue` remain density owners. A later human or Sol review may use `sol-review.schema.json`, but it must bind every frozen input hash, an existing generated finding, and declared immutable empirical evidence before proposing any change. This static package declares no empirical evidence records, so it cannot itself support a proposal.

The source-inventory map covers 203 legacy-source modules and 1,594 leaves. A null `source_inventory_entry` for later modules is an explicit provenance state, not an audit error. All present rows report canonical positive YES pass orientation, material severity, and an evidence minimum of one; that is frozen registry state, not a defect conclusion.

The package contains only public registry metadata and generated candidates. It intentionally excludes private prose, local absolute paths, provider output, and empirical judgments.
