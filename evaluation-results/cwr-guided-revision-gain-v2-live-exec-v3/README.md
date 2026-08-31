# CWR-guided revision-gain v2 live execution v3

V3 is the fresh, versioned successor to v2. It retains the frozen lean pilot,
route reauthentication, one-launch/no-resend discipline, exact raw stdout
capture, reconciliation-only recovery, sole receipt authority, judge
separation, and unpooled endpoint projection.

The v2 canary root is immutable terminal lineage: its one local adapter launch
returned `definitely_not_contacted` with `output schema needs
$schema_version=1`; provider and native contacts are both zero. V3 pins its
full plain-file inventory, all artifact hashes, exact control bytes, and absent
receipt/result/reconciliation artifacts. It cannot be reused, reconciled, or
resent.

The only compatibility change is transport schema decoration. For feedback,
revision, and endpoint phases, V3 binds the exact underlying pilot response
schema, then supplies the shared adapter an otherwise identical schema with
only `$schema_version: 1` added. The bound decoration rejects any change to
properties, required fields, or `additionalProperties`. The transmitted stdin
remains canonical `{"prompt": ...}` bytes containing the exact successor
outbound payload.

Provider-free tests directly invoke both installed shared adapters on all three
decorated schemas and prove they pass schema preflight without launching a
provider process; the v2 undecorated schema remains a zero-contact rejection.

Before a launch intent, V3 accepts only the six plain prepared artifacts. Any
extra file, directory, reparse point, prior intent, raw/control artifact,
receipt, result, or reconciliation record fails before a subprocess starts.
Its later settled and reconciled inventories are separately exact, including
the one allowed phase-specific ingest record for safe rereads.

No dispatch occurs without `allow_remote=True` and a newly revalidated exact
route. This package has no automatic retry, resend, confirmation, pooling, or
promotion path.
