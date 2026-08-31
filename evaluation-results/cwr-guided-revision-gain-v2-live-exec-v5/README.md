# CWR-guided revision-gain v2 live execution v5

V5 is the fresh, versioned successor to v4. It retains the frozen lean pilot,
route reauthentication, one-launch/no-resend discipline, exact raw stdout
capture, reconciliation-only recovery, sole receipt authority, judge
separation, and unpooled endpoint projection.

V3's four revision controls are immutable terminal lineage. They completed once
but V3 compared the ephemeral runtime command hash to a static route hash from
a different identity domain, so each terminalized without a receipt. V4 pins
the V3 executor and all four exact 11-file inventories. It compares the full
runtime command identity with the governed `grok_command_identity`, retains
the 64-hex runtime hash as observed invocation evidence, and never compares it
to a static route hash.

The V3 source root is never modified. Reconciliation writes one fresh V4
derived authority per source event below
`<output-root>/predecessor-reconciliation/revision_generation/<event-id>/`.
It revalidates the current governed route/proof, accepts no resend or provider
launch, and requires the frozen acknowledgement hash. All four authorities
must validate before a phase-specific revision ingest is permitted.

V5 imports those four V4 descendants into a fresh continuation root in the
pilot's exact seven-field record shape. The import is write-once: reopening is
allowed only after its complete, exact import inventory validates; a missing,
partial, extra, or reparsed artifact is rejected. The two inherited cycle-one
Sol feedback authorities remain explicitly local-lifecycle only: native
endpoint contact cardinality is unproven. Their immutable V3 receipt hashes
are pinned in `study-contract.json`; V5 never upgrades that evidence class.
Cycle-two feedback must instead be a normal pilot-authenticated receipt for
its own prepared cell. This keeps the one narrow historical-reader exception
from becoming a general receipt bypass.

The V4 executor, derived-root path, and complete source inventory are pinned
in the contract. Each imported Grok receipt is rederived from the exact pinned
V4 reconciled receipt and bound to it before it can become a pilot-shaped
record. V5 rejects V3/V4 root overlap and reparsed ancestry before any write.
The reconciliation implementation itself remains only in the committed V4
package: V5 consumes its immutable result and does not duplicate that path.

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

Before a launch intent, V4 accepts only the six plain prepared artifacts. Any
extra file, directory, reparse point, prior intent, raw/control artifact,
receipt, result, or reconciliation record fails before a subprocess starts.
Its later settled and reconciled inventories are separately exact, including
the one allowed phase-specific ingest record for safe rereads.

No fresh dispatch occurs without `allow_remote=True` and a newly revalidated
exact route. This package has no automatic retry, resend, confirmation,
pooling, or promotion path. Its provider-free fixtures exercise the frozen
pilot's receipt and full eight-revision/ten-target lineage logic; they are not
provider execution evidence or a revision-gain result.
