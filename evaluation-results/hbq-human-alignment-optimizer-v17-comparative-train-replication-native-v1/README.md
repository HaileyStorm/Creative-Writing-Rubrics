# V17 native endpoint execution

This package is the provider-capable counterpart to the frozen V17 TRAIN-only
replication source.  It prepares 48 fresh calls per endpoint (38 individual
direct and 10 two-order ten-story comparative batches), then independently
admits those receipts before combining them with 12 exact V15 historical direct
measurements from the same endpoint.  It never pools Grok and Sol.

V17 source is pinned to commit `3715be8` and SHA-256
`3e0dee255b2631249c76fcc70baf99c5842be17550baafbe18e270ac9d52a827`.
The lower native lifecycle is pinned to V16 executor commit `3c1bec6` and
SHA-256 `554c6ab1e70a74a89c9b7cefab7c15ea66146a44aea7a8d38293ae6c2d4956db`.
Both are checked against their live Git blobs before use.

`prepare_all` is provider-free and writes one immutable prepared root per
endpoint.  It requires an acknowledgement and validated current route proof,
but reports zero provider calls and process launches.  `execute_one` and
`execute_wave` require explicit `allow_remote=True`; the inherited reviewed
lifecycle keeps tools, web, and subagents disabled, gates current route
evidence, limits concurrency to ten, and makes post-contact ambiguity terminal
rather than automatically resending a cell.

`report` rederives the V17 schedule from frozen inputs, re-admits all fresh
native receipts and the selected V15 receipt evidence, checks endpoint and
receipt identities, and supplies cell/payload/endpoint provenance to the V17
analyzer.  It does not prove native endpoint contact cardinality, provider
attestation, generalization, confirmation, selection, promotion, runtime use,
or any public-performance claim.  Grok remains the primary development route;
Sol uses identical frozen payload bytes as an independent endpoint check.

No provider was contacted by creation of this package.  A future execution
requires a fresh, reviewed no-liability route proof and explicit disclosure at
the caller before its prepared output root is created.
