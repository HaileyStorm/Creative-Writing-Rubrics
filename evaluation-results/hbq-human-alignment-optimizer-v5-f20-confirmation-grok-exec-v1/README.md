# Confirmation Grok execution v1

This small execution wrapper consumes the frozen 38-cell confirmation schedule
byte-for-byte.  It pins confirmation-freeze commit
`08fd8bd4442cf524bf631566cf539f2dc317d146`, uses the reviewed broader Grok v3 lifecycle, loads and
freezes the current Grok route once per operation, and limits a wave to ten
simultaneous native runners.

`prepare-all` is provider-free.  Execution requires explicit `--allow-remote`.
The collector/replay path preserves receipts but does not select a candidate,
promote an outcome, alter runtime behavior, or claim native endpoint-contact
cardinality.
