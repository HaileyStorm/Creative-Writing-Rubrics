# Native heldout execution composition (v1)

This versioned executor prepares and dispatches only the pinned 66-cell heldout schedule. Grok uses the pinned broker/capture-wrapper transport and is capped at ten independent cells. Sol uses a callback-safe local Codex lifecycle and is conservatively capped at one; its endpoint cardinality remains unproven.

Every root is fresh, local-first, exact-payload-bound, and no-resend. Preparation is provider-free. Post-intent failures are terminal reconciliation cases; a definite precontact failure is also preserved and requires a fresh root.

## Volatile route preflight

Route arming and zero-charge evidence are intentionally checked live and are not fixture claims. On 2026-08-30, a provider-free prepare against the current local route registry produced `prepared_no_contact` for `heldout-cell-391a0019df39f385` (Grok) and `heldout-cell-ad3411192bb7a35b` (Sol), with `[0, 0]` provider calls. That is only an adjacent local-route preflight; it does not authorize dispatch or establish native-contact evidence.
