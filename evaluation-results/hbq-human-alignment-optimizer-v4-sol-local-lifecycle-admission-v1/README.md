# HANNA v4 Sol local-lifecycle admission v1

This provider-free adapter verifies an immutable exec-v3 Sol root by replaying its
pinned verifier against its own persisted route evidence, then creates a disjoint
exact artifact clone plus an admission result/proof. It makes no provider call.

The admitted evidence is `local_lifecycle_verified`. It is **not** native endpoint
evidence: provider attestation is false and native endpoint contact cardinality is
unproven. Downstream consumers must deduplicate on the proof’s full key and retain
that ceiling. The CLI accepts repeatable `--prior-proof` arguments and authenticates
each prior proof before rejecting a duplicate key.
