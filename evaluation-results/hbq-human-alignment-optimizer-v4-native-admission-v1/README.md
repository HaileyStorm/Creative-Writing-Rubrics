# HANNA v4 completed-Grok admission v1

This provider-free package admits one completed, independently verified
historical exec-v1 Grok cell per fresh destination into a predecessor-shaped
settled-cell root. It never launches a process or provider. It has admitted 20
mandatory-development cells across the first four items and all five frozen
candidates. Every cell has exactly one tool-free, zero-new-spend Grok Build
subscription process launch, proven native envelope/contact, and provider-free
admission proof; every source root remains untouched. Cells 16–20 are
`v4-cell-aff3e9e452578781`, `v4-cell-7b3adfd63809c14b`,
`v4-cell-0e0f71d03712b0aa`, `v4-cell-4e60777e232aa526`, and
`v4-cell-e3c472eea3d119c4`.

`admit.py --admit-completed-grok` pins the exec-v1 executor at
`5d2bd6871fe2013b8af5e166d89eeb020ff98889ce30494dd8889f7bee2d942f` and
pins the v4 native-subscription predecessor executor and contract. It
stable-reads the source inventory, freshly derives the mandatory row and
payload, then applies an independent historical verifier over pinned exec-v1
bytes and frozen source artifacts. It never consults a current queue, expiry,
Broker, or live route, and never dispatches.

The destination has the predecessor's exact base plus its
`native_returned_unprojected` contact inventory. Its native request is the
already-verified task bytes and its native response is the exact raw Grok
envelope. A separate proof file binds source and destination inventories, the
admission code/contract hashes, and all artifact hashes. Exclusive staging is
validated before destination publication and proof publication; failure cleans
only pre-publication, exclusively owned staging. A terminal mismatch preserves
the published destination and proof for reconciliation. Existing
source/destination/proof paths, reparse points, and partial outputs are
rejected rather than resumed or overwritten.

Each resulting descendant is not a metric result; projection remains owned by
the predecessor. A byte-identical copied source is the same evidence, not a
second observation: downstream consumers must deduplicate the bound
cell/contact/session/request/response commitments. The 20 Grok cells are early
diagnostic observations, not candidate selection, alignment, Grok/Sol
agreement, confirmation, or revision-gain evidence. Two once-launched exact
matched Sol diagnostics are terminally excluded without resend: v1 after a
Code Mode startup error, and v2 after a clean lifecycle failed its stderr-label
gate. The first verified matched Sol local lifecycle is documented in
[exec v3](../hbq-human-alignment-optimizer-v4-native-subscription-exec-v3/);
its local receipt does not prove provider identity, reasoning, native endpoint,
or cardinality.
