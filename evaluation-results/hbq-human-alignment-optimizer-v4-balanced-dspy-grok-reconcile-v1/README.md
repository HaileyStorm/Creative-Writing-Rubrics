# Balanced DSPy Grok terminal reconciliation (v1)

This provider-free descendant reads ten immutable, terminal v2 roots and writes a fresh reconciliation manifest. It neither imports nor invokes adapters, queues, DSPy, Optuna, or remote execution.

It preserves raw controls and model output hashes, verifies native completed-control evidence using the adapter's no-trailing-newline JSON domain, and creates an explicitly derived project-canonical profile. The derivation audits any ASCII base64 whitespace removal and repairs only the profile's internal `instruction_sha256`; factors remain opaque model-supplied content. The source roots are never modified or retried.
