# Six-cell Sol validation

Provider-free preparation and local-lifecycle receipt projection for the baseline and normalized nextwave-08 candidate across the frozen three development groups. Preparation requires explicit normalized/materialization/frozen-target inputs plus the completed 33-cell Grok execution root, collector, and published result; their committed identities and hashes are rechecked before a six-cell schedule is derived. Execution requires an exact fresh zero-charge Sol proof and acknowledgement, with `execute-wave` enforcing two in-process lanes and exclusive per-cell claims. Projection never re-arms a route: it replays persisted disclosures, acknowledgements, proofs, targets, launch intent, records, raw events/stderr, settings, receipts, and lifecycle identities.

This is descriptive Sol validation only: it never pools Grok and Sol, opens confirmation, selects a candidate, claims generalization, promotes a prompt, or supplies runtime behavior.
