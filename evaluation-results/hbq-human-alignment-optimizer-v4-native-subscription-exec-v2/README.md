# HANNA v4 native subscription exec v2

This versioned successor changes only the Codex startup feature flags used by the Sol validation route. It explicitly disables `code_mode` and no longer disables the stable `code_mode_host` support feature. Its default launcher loads the exact pinned shared runner through a localized seam that requires and replaces exactly one `code_mode_host` argument token before compilation. The remaining exec-v1 and runner behavior is loaded from exact pinned bytes, so the strict JSONL lifecycle parser, read-only ephemeral execution, ignored user configuration, tool/web/plugin/subagent disablement, and terminal post-launch reconciliation/no-resend behavior are unchanged.

The change addresses the excluded exec-v1 diagnostic run whose startup emitted a `code_mode_host` error before the otherwise coherent lifecycle. It does not relabel or retry that run, attest native endpoint contact cardinality, or make an alignment claim.

DSPy and Optuna remain development-only dependencies of the separate optimizer. This execution package does not import either library.
