# Batch curve live v1

This is a transport-agnostic callback mechanism beside the frozen batch-curve v2 protocol. It has no provider adapter, contains no results, and makes no size recommendation.

The adapter verifies the parent contract and its projection before every run. It takes question order only from that frozen contract, renders each request through the canonical binary prompt renderer, and records only parsed verdicts plus hashes and provider receipts. It never writes a credential, request text, or raw provider response body.

An operator supplies a fresh-session callback outside this package. That callback is a transport boundary only: no concrete Codex, Grok, or Nous adapter is implemented or verified here, and this package makes no live-provider usability claim. Per-cell atomic checkpoints make an interrupted external work directory resumable. A completed 39-cell callback screen is mechanism output only: v2's deep exact-stack validation still controls any recommendation, so this adapter cannot recommend a size above 24—or any size—until that evidence exists.
