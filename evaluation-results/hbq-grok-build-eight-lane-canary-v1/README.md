# Grok Build eight-lane canary v1

This packet preserves eight completed public-synthetic broker results. The
queue records all eight attempts starting at `2026-08-23T01:38:40Z`; result
envelopes record launch at `:40` or `:41`, and finish between `01:39:23Z` and
`01:40:31Z`. Each had one attempt and a delivered result. The route and
matching host gate were healthy at a reviewed host-wide cap of eight.

The results cover aggregation, confidence, HANNA repair, integration,
paired-polarity, preface-ablation, repair-protocol, and expert-edit pilot
design. Each is a provisional design input only—not a decision, judge score,
causal result, human-alignment finding, model promotion, or paid evaluation.

The broker requested `grok-4.6` at `high`; Grok Build reported
`grok-4.6-build`. Reasoning effort was requested but not attested. Calls were
isolated, one-turn, and read-only. The recorded `costUSD` fields are included
weekly-allowance usage telemetry for a zero-charge saved-session route, not an
incremental paid evaluation.

This canary establishes only that eight bounded calls overlapped and completed
under the reviewed cap. It does not establish general throughput, capacity
beyond eight, model quality, or correctness of the advisory outputs.

Run `python validate.py` from this directory to check result hashes, shared
runtime identity, timing, envelope shape, and the credential-safe broker
snapshot. The packet excludes prompts, queue paths, owner attestation,
credentials, raw route commands, and session identifiers.
