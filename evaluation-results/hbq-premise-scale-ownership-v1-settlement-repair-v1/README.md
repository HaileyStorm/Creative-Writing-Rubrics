# Premise-scale ownership settlement repair v1

This provider-free successor repairs a settlement comparison defect in the
frozen execution package at `3258e6f44bb728ce17ebcd85b4964d472aaf87c2`.
Its only allowed transformation is canonicalizing checkpoint `CRLF` line endings
to `LF` before comparison with the already frozen rendered prompt.  A lone CR,
any non-newline difference, an unexpected slot count, or drift in the frozen
private root fails closed.  It retains raw and canonical prompt commitments for
all 72 slots, reuses the execution package's full production verifier, and does
not contact a provider or overwrite the original `INCOMPLETE` outputs.

The resulting private settlement is named `settlement-repair-v1.json`; the
separate aggregate-only publication is `public-aggregate-repair-v1.json`.
This repair never promotes wording, ownership, or weights.
