# V8 exact-one-event adapter v1

This is the one guard-owned entry point for the next V8 event. It binds the pushed V8 guard and a separately supplied frozen V8 package directory (the `evaluation-results/...-successor-v8` directory inside its clean runtime checkout), validates fresh native capacity evidence, the exact V8 disclosure acknowledgement, and the runtime's clean pushed state before the guard may record intent.

`dispatch_one` rechecks the guard-supplied event immediately before calling frozen V8 `_settle_one` once. The adapter itself never calls V8 `execute` or `_dispatch_event`, and has no public runner injection. The guard's postflight preserves the physical provider-session topology check. A V8 changed-payload retry-disclosure pause is terminal here: do not resend; a distinct reviewed guard successor is required.

This is the operator-selected guarded launch path, not a claim that V8's immutable historical executor has been technically disabled. That direct executor remains callable and is prohibited by this continuation procedure; enforcing sole technical reachability would require a distinct versioned V8 runtime successor.

The adapter has no provider default beyond V8's pinned native runner and is not a result claim. Tests inject a fake runner and make no provider contact.
