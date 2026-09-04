# V13 remaining TRAIN expansion

This development-only package schedules the 44 frozen TRAIN items not used by
the V11 child20 screen, paired with the unchanged baseline and child20
candidate: 22 prompt groups and 88 Grok cells. It opens no DEV or confirmation
cells, makes no selection or promotion, dispatches no Sol work, and leaves all
earlier results unchanged.

`schedule` reconstructs exact source bindings from the pinned V1 eligibility
map and exact V10 candidate/payload bytes. `prepare_all` is provider-free.
`execute_one` and `execute_wave` require explicit remote authorization; the
wave is capped at ten concurrent cells and reuses the V11 native-Grok lifecycle for
disclosure, route, precontact, source/reparse, global-slot, and no-resend
gates. V13's precontact check accepts only byte-identical payloads from its
frozen schedule, rather than applying an arbitrary story-length cutoff. No
dispatch CLI is exposed.

`report` accepts only a complete, admitted, single-route receipt set with
unique native request and session identities. It keeps every finite 0–5 score,
including all-zero vectors and values whose coverage flag is false. Its primary
metric is six-dimension item MAE, then the mean within each of the 22 prompt
groups, then an equal mean across groups. Results are TRAIN development
measurement only and do not open an automatic follow-on action.
