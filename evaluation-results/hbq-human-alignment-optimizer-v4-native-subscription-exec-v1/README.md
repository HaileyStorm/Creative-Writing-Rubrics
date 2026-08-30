# HANNA v4 native-subscription executable successor v1

This thin successor pins the provider-free v4 executor and the shared HBQ-RS native
runner at SHA-256 `de1dccd28c8ba544207b3b000d086948fa8c429a327b055762e8d7032e3fa938`.
From frozen source inputs it directly rederives the predecessor row and exact
task-payload/response-schema bytes; no caller predecessor payload or staged output is
accepted. Before execution it read-only validates the live `grok-build-grok-4.6` or
`codex-chatgpt-gpt-5.6-sol` registry entry through the model-work-queue Broker with
current command-identity, subscription, cost, and expiry checks.

The CLI exposes mutually exclusive `--prepare-only`, `--execute-one-grok`, and
`--execute-one-sol` modes. Preparation performs no subprocess or provider call. A live
one-cell mode additionally requires `--allow-remote`; the programmatic surfaces require
the explicit `allow_remote=True` keyword. Every mode binds the caller-supplied lowercase
SHA-256 authorization-acknowledgement reference.
Successful live CLI reporting emits a canonical JSON-safe summary. Raw byte fields are
not printed; each is represented by an explicit omission marker, byte count, and
SHA-256. Programmatic callers may retain the byte-bearing result, while persisted
execution artifacts remain authoritative. Reporting never retries contact.
Preparation persists the exact outbound text/bytes, destination, route identity,
tool-disabled policy, and, for Grok, the exact outbound system prompt and tool-free
argument vector, plus zero calls/launches, authorization reference, and current
Broker-validated zero-charge route proof. Execution rederives the exact frozen row and
payload and rejects copied or relabelled cell artifacts.
The programmatic Grok execution surface calls the pinned one-turn, tool-free
`hbqrs.runner._call_grok`. Its callback records process-launch intent, not native
contact. Only the pinned raw Grok envelope artifact proves native contact. The
independent receipt verifier binds exact request/schema bytes, route evidence hashes,
CLI version and command identity, and envelope model/request/session IDs.

The programmatic Sol surface calls pinned `hbqrs.runner._call_codex` with exact JSONL
capture enabled. A pinned copy of the queue Codex adapter's strict parser requires one
coherent thread and turn, no error or extra terminal event, a completed agent message,
and usage. The single completed agent-message text must byte-match the exact final JSON
response. The receipt binds the exact raw JSONL bytes, local thread/session lifecycle,
tool-disabled invocation, route/auth evidence, CLI/command identity,
and locally observed model/reasoning settings. Identity remains `openai_codex` over a
ChatGPT subscription and requested/local-effective only; it is never relabelled as
Chat Completions, OpenAI API transport, or provider model/reasoning attestation. Codex
thread events do not expose native endpoint contact or internal retry cardinality, so
the Sol receipt records both as unproven and cannot independently satisfy the
predecessor's exact-contact study gate.

Both routes revalidate current Broker evidence inside the launch callback. Known
execution-owned artifacts created before a zero-contact failure are removed only when
their exact names and bytes match the route contract. Completed verification accepts
only the exact route-specific inventory and rejects extras, directories, links, and
Windows reparse points. Any uncertainty after process-launch intent remains durable
`reconcile_required_after_process_launch` and cannot be resent.
Every completed receipt also binds the exact canonical launch-intent hash; verification
reconstructs the expected study, kind, cell, prepared-manifest hash, and false
native-contact label rather than trusting the intent file's mere presence.
