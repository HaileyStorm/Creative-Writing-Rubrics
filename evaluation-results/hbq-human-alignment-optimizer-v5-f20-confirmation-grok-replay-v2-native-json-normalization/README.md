# Confirmation Grok replay v2

V2 reads the complete V1 collector without contacting a provider. It preserves
each native response byte string and its SHA-256, but accepts valid JSON whose
whitespace or key order is not V1's canonical serialization. The parsed
envelope, request/session identities, structured-output schema, persisted
receipt, and exact raw bytes must still agree.

It reports confirmation-only, eight-group-weighted MAE for the frozen baseline
and descendant. It does not make a selection, promotion, runtime, Sol, or
cross-provider claim.
