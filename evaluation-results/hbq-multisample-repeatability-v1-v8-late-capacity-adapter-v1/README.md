# V8 late-capacity adapter

Why: the prior composition could age capacity evidence while repeating local
verification. This adapter removes only its redundant outer precontact pass;
the guard retains full preflight, one claim, and normal postflight validation.

After the delegate's final full V8 verification, an explicit per-invocation
capacity supplier provides one fresh external capacity-evidence file. The
adapter validates that file immediately and passes it to the unchanged frozen
V8 settlement primitive, which validates it again before dispatch. No TTL is
widened, no result is cached across invocations, and no frozen source is
rewritten.

Performance: the capacity observation is delayed until immediately after the
delegate's final verification, avoiding the removed duplicate pass. The
query-only dead-PID patch remains installed on every guard target reload.

Fallback: dispatch remains disabled by default. A missing, stale, changed, or
invalid supplied capacity file fails closed; this adapter has no retry or
alternate dispatch path.

Status: provider-free isolated tests have passed. **NO-GO for live capacity
timing and provider-dispatch evidence.** This is not a capacity probe,
provider dispatch authorization, or fallback path.
