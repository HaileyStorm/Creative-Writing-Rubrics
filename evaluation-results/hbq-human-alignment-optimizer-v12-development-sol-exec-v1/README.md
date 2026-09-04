# V12 matched development Sol-26 measurement

This package performs a separately authorized Sol measurement of the frozen
V12 development panel only after a complete, persisted V12 Grok report is
provided by path and expected SHA-256. It never creates or retries Grok work.

The V12 source schedule supplies 26 unchanged target-free payloads: the
baseline and retained child20 candidates over thirteen development items in
seven prompt groups. Each Sol request uses the source payload bytes exactly.
Targets remain local receipt-validation material.

`prepare_all` is provider-free. `execute_wave` requires explicit remote
authorization and uses at most ten concurrent, one-shot Sol calls through the
existing receipt lifecycle. It preserves the tool-free default Codex route,
common route/evidence checks, and unique local thread/session identities.

`report` admits all 26 native receipts independently. Its primary metric is
item six-dimension MAE, averaged within each group and then equally across the
seven groups. Item-13 and group-mean-7 tied Spearman values are separate
context, and finite numeric scores remain included even if coverage is false.

This is development measurement only: it opens no confirmation cells and has
no selection, promotion, runtime, generalization, or endpoint-pooling effect.
