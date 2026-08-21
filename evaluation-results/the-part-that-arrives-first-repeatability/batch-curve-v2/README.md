# Batch curve v2: frozen executable protocol

This package contains no provider output, score, coverage, recommendation, or claim that any size is validated. It contains an offline fake-endpoint execution path that proves only the local schedule, journal, exact-question coverage, analysis formulas, and verifier semantics.

The screen fixes thirteen sizes—1, 2, 4, 8, 12, 16, 24, 32, 48, 64, 96, 128, and all-in-one—and runs each exactly three times in the frozen order. Every cell binds the same source bytes, compiled **178-leaf** sequence (domain, hard-gate, supplemental, and penalty leaves), model stack, and retry policy. `all-in-one` is exactly the frozen full sequence, never a domain-only shortcut.

## Execution and privacy boundary

`batch_curve_harness.py` has no live provider client. Its only executable runner takes an injected offline fake endpoint. It writes a planned/accepted/completed journal and rejects reordered, incomplete, duplicated, or projection-mutated records. A future real adapter is separately authorized work: before its first call the exact destination, outbound payload, existing-session authorization, local retention, and provider-identity mapping in `study-contract.json` must be reviewed. Credentials and provider-response bodies are not study artifacts; immutable local provenance contains only the permitted redacted receipts and hashes.

## Recommendation rule

There is no default size. A stack-specific recommendation may name only the largest size with successful completed empirical deep validation on the same full exact stack. Its cap is derived from journal-backed accepted calls whose ordered question IDs reconstruct the requested full batch; a declared number cannot raise a cap. Offline mechanism support, derived manual evidence, another format, or a diagnostic experiment is not a recommendation and can never exceed that stack's largest validated successful size.

## Deterministic measures and bracket

The harness implements the three-repeat leaf-agreement, modal-label, nominal-alpha, score-deviation, schema, quote-grounding, confidence-secondary, and position formulas named in the contract. Canonical HBQ score, coverage, bounds, and status are unchanged. Confidence diagnostics are explicitly secondary: assessed-confidence mass is not called coverage and confidence-weighted score sensitivity is not called score.

Every ladder member is screened first. The deterministic state machine records success or failure for every member, then emits only observed adjacent transitions for deep bracket validation. It never infers an unexecuted member's result. The deeper eleven-item HANNA gate remains required before any recommendation.

## Offline mechanism evidence

[offline-mechanism-matrix.json](offline-mechanism-matrix.json) is generated from the current 85-bundle catalog by `generated_matrix_document`. It binds each derived row to its full compiled-question projection/hash, every frozen batch partition shape and remainder, local fixture score reconstruction, and secondary confidence extraction. The eight representative format stacks are independently derived selections with their own selection hashes and findings. They are never evidence that a batch size works in production.

The complete frozen projection, provider disclosure, formulas, state transitions, and cross-format protocol are in [study-contract.json](study-contract.json). Its complete canonical projection is independently pinned in [study-contract.projection.sha256](study-contract.projection.sha256); the harness rejects a contract whose bytes no longer produce that digest. The manual format-stack checks are separately fixed in [manual-stack-fixtures.json](manual-stack-fixtures.json) and are verified through direct core compilation, not by regenerating the matrix.
