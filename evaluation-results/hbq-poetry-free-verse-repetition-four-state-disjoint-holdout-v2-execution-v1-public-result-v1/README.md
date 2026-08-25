# S1 four-state disjoint holdout v2: newline-mismatch no-result v1

This aggregate-only public package records the terminal outcome for
`hbq-poetry-free-verse-repetition-four-state-disjoint-holdout-v2-execution-v1`.
It contains no case identifiers, private paths or prose, prompt bodies,
quotations, sessions, or response payloads.

One first-attempt OpenAI `gpt-5.6-sol` high-reasoning response was accepted
with grounded exact-quote evidence. Before it could become a completed slot,
the driver detected that the accepted runner prompt did not byte-match its
frozen counterpart. The difference was newline transport only: canonical
CRLF-to-LF bytes were equal, but the declared raw byte check failed. Eleven
planned slots remained untouched.

The accepted semantic response is non-voting. The formal decision is
`NO_RESULT_PROMPT_BYTE_BINDING_FAILURE`; newline transport is its documented
cause, not a semantic holdout result or a wording, fixture, or model inference.
It authorizes no retry, resume, promotion, or DSPy follow-on.
