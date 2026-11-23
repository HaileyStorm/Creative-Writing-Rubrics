# Strict offline projection of native receipts

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

This is an offline projection, **not** a new live collector policy. It does
not change the runner, make a provider call, establish receipt authenticity,
prove account or home identity, certify the complete enabled tool inventory, or
prove tools were disabled before dispatch. The v2 wrapper cannot be substituted
for a v1 checkpoint receipt. A future live integration needs an independently
supported launch-bound native attestation and the existing capacity, ownership,
and no-resend controls; a successful syntax check does not supply those gates.
