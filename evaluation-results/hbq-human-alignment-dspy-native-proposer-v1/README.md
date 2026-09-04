# DSPy native proposer v1

This development-only adapter has one job: turn the retained child20 instruction,
its unchanged profile, and replayed V11 TRAIN-only diagnostics into one modest
versioned instruction proposal. It is not an optimizer, evaluator, selection
mechanism, confirmation activation, or runtime authority.

`prepare_one` replays the pinned V11 receipt source, derives child20 from the
pinned V10 source, and uses installed DSPy 3.3.1's real `Predict` and
`ChatAdapter` with a local capture LM. That LM has zero retries and raises a
local sentinel after DSPy has rendered its single request. The exact resulting
request bytes are persisted in `prompt-request.bin`, with the TRAIN report,
request, schema, and local-first disclosure. The teaching input contains only
the four child20 TRAIN examples' scores, targets, and per-dimension signed and
absolute errors; DEV and confirmation inputs are rejected by the pinned V11
receipt replay.

Preparation makes no provider call. A caller must then supply a canonical
authorization acknowledgement whose `disclosure_sha256` matches the persisted
disclosure exactly; `bind_authorization` copies those immutable acknowledgement
bytes into the fresh root. `execute_one` refuses an unbound, launched, or
terminal root, reuses the pinned V4 Grok queue/capture control for one tool-free
nonvisual turn, and has no resend path. The shared route is first validated in
its live four-turn form; this adapter creates an explicit in-memory task-local
copy with `nonvisual_max_turns=1` for the sole dispatch. It never mutates the
queue route or treats the effective one-turn copy as live route evidence. Before launch it replays the frozen
TRAIN source and DSPy render again. It parses the native response through the
same DSPy `ChatAdapter`; the host, not the model, computes UTF-8, base64, and
the documented canonical-JSON candidate commitment. The child20 profile bytes
remain byte-identical in the resulting descendant.

The receipt records a locally observed completed adapter control response but
does **not** claim independently proven native-contact cardinality. Any failed
or ambiguous post-launch outcome is reconciliation-required and terminal.
