# HBQ multisample repeatability v1: capacity-reset successor v6

This is a fresh successor for the untouched tail of the 330-cell multisample
study. It does not resume or modify the v4 live root.

The v4 root contains a valid-looking sequence-178 output but stopped after a
post-run session-validator failure, leaving an active claim and only the
`capacity-checked` and `attempt-intent` journal rows. The v5 owner settlement
is an offline recovery record, not a v4 completion row. `executor.py` admits
178 only after independently checking the immutable v4 manifest, run,
verdict, batch-session commitments, and exact v5 sidecar; it then creates a
new external work root whose fresh schedule is exactly 179–330.

Preparation and dry-run validation are contact-free. A real launch requires a
fresh local-host capacity observation (not provider acceptance or a promise of
future capacity), a clean checkout exactly at its upstream,
an exact owner acknowledgement of `preflight-disclosure.json`, and
`--allow-remote`. The frozen protocol is deliberately one worker and one
logical cell per epoch: capacity is checked immediately before intent, the
claim is removed after that cell's output and completion row are fully
validated, and an uncertain contact leaves the claim and intent as the
operator-visible stop marker. It also writes an immutable bounded-contact
recovery record; an operator may preserve it as nonvoting evidence or create a
distinct successor after offline adjudication, but may never resend or adopt
an output without a new immutable settlement. A receipt expiring after a clean
checkpoint pauses before the next claim, so rerunning with a fresh observation
continues only the untouched next sequence.

The external-work-root disclosure is the owner-review artifact. For every
cell it records the exact UTF-8 source/prompt/task excerpts that leave the
machine and each fully rendered provider request, including its structured
response schema, with SHA-256 commitments. It is deliberately not tracked in
this public package. The owner must review it and create the exact
acknowledgement object with `make_disclosure_ack()` before remote dispatch; the
executor recompiles and compares the payload immediately before intent.

If the HBQ runner records terminal rejected evidence and constructs a changed
validation-feedback retry prompt, V6 takes a second, known-safe pause before
that retry's attempt-start or provider contact. It writes a separate immutable
retry disclosure containing the exact hook context: request bytes and schema,
provider/model/reasoning, validation feedback, and rejected-chain commitment.
The original claim is released only for that documented pre-contact pause.
Continuing requires a non-placeholder acknowledgement bound to that precise
retry disclosure, a fresh later capacity observation, and a `retry-intent`
journal row before the same cell can resume. Other unresolved intents remain
strict no-resend stops. Rejected HBQ evidence is counted from the production
nested `responses/rejected/batch-####/attempt-####.json` records and their
`raw_content.text` fields.

V6 never removes an existing claim automatically, including a claim left by a
crash during a documented pre-contact pause. A concurrent or crash-left claim
blocks retry resume and dispatch; the only removal gate is the existing
explicit offline operator-settlement path, which preserves the evidence and
requires a distinct successor rather than adoption or resend.

The original study's logical protocol remains unchanged: 10 generated stories
plus one Human story, five repetitions, six arms, native scales kept separate,
and the original sequence/sample/arm/repetition mapping. The population is
primary `n=10 / 300 cells` plus secondary `n=1 / 30 cells`, total 330 cells.
The v6 suffix has 152 logical cells, a minimum 277 physical provider contacts
(25 HBQ cells require six batch contacts and 127 native cells require one),
and a three-attempt retry ceiling of 831. On completion, the journal records
the production runner's observed provider contacts for each settled cell,
including accepted retries, and recomputes that count from persisted attempt
evidence; it never relabels the minimum as an actual count. An unresolved
contact exposes only an exact observed lower bound and a retry-ceiling upper
bound, never an invented provider outcome. Accepted counts are based on
validated output files in the contiguous journal prefix, not on intents or
directory presence. Comparisons must disclose the one-worker v6 execution
boundary. No private prose or response bodies belong in this public package.

## Future launch shape

```powershell
python evaluation-results/hbq-multisample-repeatability-v1-remainder-capacity-reset-successor-v6/executor.py `
  --source-root C:\Users\Haile\Documents\cwr-multisample-repeatability-v1-20260821-44518ab `
  --closed-root C:\Users\Haile\Documents\cwr-multisample-repeatability-v1-successor-20260821-9422eff `
  --v4-root C:\Users\Haile\Documents\cwr-multisample-capacity-reset-v4-live-1c587bc-20260822 `
  --v5-settlement C:\Users\Haile\Documents\cwr-multisample-v5-owner-validated-settlement-20260822\offline-recovered-completion.json `
  --work-root C:\Users\Haile\Documents\cwr-multisample-capacity-reset-v6-live-unique `
  --capacity-evidence C:\path\to\fresh-capacity.json `
  --disclosure-ack C:\Users\Haile\Documents\cwr-multisample-capacity-reset-v6-live-unique\disclosure-acknowledgement.json `
  --allow-remote
```

After a retry-disclosure pause, create the hash-named immutable acknowledgement
under `retry-disclosure-acknowledgements/` with
`make_retry_disclosure_ack()` and add `--retry-disclosure-ack` plus a fresh,
later `--capacity-evidence` path to the rerun.

The command above is intentionally a launch template, not evidence that a
provider run has occurred. Run `--dry-run --preview-disclosure` first and
review the resulting binding, schedule, and private exact-payload disclosure before making
the exact acknowledgement artifact.
