# V7 endpoint continuation

V7 consumes only the immutable adopted V6 eight-record lineage and V6 frozen
ten-target manifest. It prepares exactly 40 blind endpoint cells: 20 Grok and
20 Sol. Each cell binds the unchanged target/measure payload, fresh governed
route proof, disclosure acknowledgement, exact source pins, and a versioned
outbound envelope.

`prepare_all` is provider-free. `execute_one` permits one explicit remote
attempt only; any post-launch failure is terminal and is never resent. Grok is
bounded at ten concurrent endpoint attempts, Sol at two. Both endpoints retain
separate identities and receipts. The projector independently replays all 40
receipt authorities against the pinned pilot schedule and V5 aggregation
semantics; it never pools endpoint evidence.

This package is NO-GO until its provider-free tests and independent review
pass. Sol evidence remains explicitly limited to a local lifecycle proof with
native endpoint-contact cardinality unproven.
