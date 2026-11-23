# Strict native receipt policy

`hbqrs.codex_receipts_v2.project` is an opt-in reader for already-retained
native event and rollout bytes. Before calling the historical v1 projector it
requires valid UTF-8 JSON lines with unique object keys at every nesting level
and finite JSON numbers. It preserves the v1 projection inside a separately
named v2 result, with both reader hashes. Historical v1 inputs, outputs and
replay remain unchanged.

The distinction matters because Python's default JSON parser keeps the last
value of a duplicate key. An invented event with both `tool_call` and
`agent_message` as values for the same nested `type` field is accepted by the
v1 reader as the latter. V2 rejects that ambiguous input. No historical native
receipt has been shown to contain this condition.

The Python runner accepts the explicit policy name
`codex_native_rollout_unique_json_v2` for newly configured runs. It captures
the original files, binds both reader implementations into run configuration,
and rechecks v2 receipts during resume. A duplicate or malformed receipt is
nonretryable; retained attempt evidence is not overwritten. V1 remains the
separately selected historical policy, and the v2 wrapper cannot be substituted
for a v1 checkpoint. As with any runner source change, an existing frozen run
whose configuration pins the earlier runner must retain that implementation;
this change does not authorize migrating, replaying or resending it.

This check does not establish receipt authenticity, prove account or home
identity, certify the complete enabled tool inventory, or prove tools were
disabled before dispatch. Actual collection still needs an independently
supported launch-bound native attestation and the existing capacity, ownership,
and no-resend controls; successful syntax checks do not supply those gates.

## Classified rollout items

The separate opt-in `codex_native_rollout_classified_items_v3` policy retains
the v2 JSON checks and rejects a rollout `item_started` or `item_completed`
event unless its `item` is an object with one of the supported non-tool item
types. It also rejects `item_updated`, whose rollout format has not been
qualified here. An incomplete event is unclassifiable; it is not evidence that
a tool was used. Events remain retained; if the rollout was reached and
copied, it is retained as well. The existing nonretryable/no-resend rule
applies on rejection.

This new policy binds the v1, v2, v3 and runner source hashes for new runs.
V1 and v2 receipts retain their original meaning and must use their original
pinned implementations for replay; do not relabel or migrate them. No
historical occurrence of the incomplete event is established. Even v3 does
not authenticate a receipt, prove its event stream is complete, establish the
effective tool inventory or account, or attest pre-dispatch tool settings.
