# HANNA v3 executor v1

This is the narrow execution successor for the frozen v3 schedule. It prepares one
Grok-primary or Sol-validation cell at a time, records an intent before its sole
native contact, and never opens confirmation. It is not a provider launcher by
itself: the private runner loader is intentionally disabled until a reviewed native
adapter is bound.

`prepare_cell` writes the exact outbound payload, local-first disclosure, external
acknowledgement, and zero-charge route proof with zero provider calls. The same
item/candidate produces identical payload bytes for Grok and Sol. `dispatch_prepared_cell`
can only use its private pinned-runner seam; a settled or ambiguous intent is never
sent again. `project_mandatory_cells` takes only persisted raw native responses and
uses the pinned v2 equal-group endpoint before freezing Grok selection and applying
the Sol gate.

DSPy and Optuna remain development-only and are not runtime dependencies here.
