# Native heldout execution composition (v1)

This versioned executor prepares and dispatches only the pinned 66-cell heldout schedule. Grok uses the pinned broker/capture-wrapper transport and is capped at ten independent cells. Sol uses a callback-safe local Codex lifecycle and is conservatively capped at one; its endpoint cardinality remains unproven.

Every root is fresh, local-first, exact-payload-bound, and no-resend. Preparation is provider-free. Post-intent failures are terminal reconciliation cases; a definite precontact failure is also preserved and requires a fresh root.

## Volatile route preflight

Route arming and zero-charge evidence are intentionally checked live and are not fixture claims. On 2026-08-30, the r2 provider-free prepare against the current local route registry produced `prepared_no_contact` for `heldout-cell-391a0019df39f385` (Grok) and `heldout-cell-ad3411192bb7a35b` (Sol), with `[0, 0]` provider calls; the disclosed Grok schema carried `$schema_version: 1`. That is only an adjacent local-route preflight; it does not authorize dispatch or establish native-contact evidence. The preserved r1 roots are never retried in place.

The preserved r2 wave is likewise never retried or adopted in place. Waves now dispatch one isolated Python child per cell, retaining the 10-Grok/1-Sol caps. A parent-only gate prevents the child from reaching provider code until Windows Job Object or POSIX process-group containment is established. Timeout, cancellation, failed containment, nonzero exit, malformed stdout, or any failed collection-grade root replay strands the root for fresh-root reconciliation rather than attempting another send.
