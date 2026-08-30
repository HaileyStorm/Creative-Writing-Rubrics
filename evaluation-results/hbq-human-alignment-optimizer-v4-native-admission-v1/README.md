# HANNA v4 completed-Grok admission v1

This provider-free descendant admits exactly one completed, independently
verified historical exec-v1 Grok cell into a new predecessor-shaped settled-cell root. It
never launches a process or provider. The source root remains untouched.

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

The resulting one-cell descendant is not a metric result; projection remains
owned by the predecessor. A byte-identical copied source is the same evidence,
not a second observation: downstream consumers must deduplicate the bound
cell/contact/session/request/response commitments.
