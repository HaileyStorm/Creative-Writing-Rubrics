# Outcome-blind MFA component partition candidate

`partition.py` reads only the corrected v2 seal's `private-metadata.json`, `summary.json` and `source-recipe.json`. It verifies the pinned recipe, whole cohort commitment and each source's metadata receipt without reading sealed sources, outcomes or prose. Source recipe **file SHA-256** and **canonical JSON with trailing LF SHA-256** remain separately named commitments. Author-Style is primary; GoodWriting is related-release sensitivity only.

Targets remain indivisible across releases, tasks, panels and conditions. Exact candidate excerpt and original reference UTF-8 hashes form one shared text namespace: any shared text connects targets, including catalogue references linked through their explicit writer-to-target identifier. Components have a deterministic sorted target-hash order. A bounded two-dimensional subset-sum seeks 20 development / 30 confirmation targets, including 12 / 18 primary fine-tuned targets. Declared exposure components are required in development. An impossible geometry produces `pending_design_decision` with all memberships unassigned; it never splits a component or relaxes counts.

Each style evaluation unit commits its exact candidate pair and the **row's** original reference hash, scoped to release, task, condition and panel. Missing row references are ineligible. Present references that differ from the catalogue remain distinct units. Exact row commitments, writer memberships and ordered-pair hashes remain in the private ledger, preserving fine expert variants and presentation order without selecting text variants or transferring votes. Count denominators preserve all rows, including ineligible rows; they are not independent-work counts.

From the repository root:

```powershell
.venv\Scripts\python.exe evaluation-results\hbq-mfa-confirmation-plan-v1\partition.py --source-root <corrected-v2-private-directory> --private-output <fresh-private-directory> --dry-run
```

Optional `--exposure-metadata <json>` accepts only `target_hashes`, `text_hashes` (arrays of exact metadata SHA-256 hashes), and `audit_complete` (Boolean). Exposure provenance must be reviewed by the owner; the flag is a supplied assertion. Unknown exposure identifiers and absent or empty exposure input leave the audit incomplete. No invocation certifies unused data or absence of public/pretraining contamination.

Without `--dry-run`, an exclusively created fresh directory receives `private-membership.json` and a public count-only `summary.json`, which binds the private ledger and exact input/implementation bytes. The destination must be outside the repository and inputs and must not already exist. Dry-run performs the same validation and emits only the public summary, with no writes or contacts. Keep the membership ledger private. This is an immutable design candidate, including when a decision is pending; it does not freeze a scoring candidate, authorize target opening or authorize provider contact.

Focused provider-free checks:

```powershell
.venv\Scripts\python.exe -m pytest tests\test_mfa_confirmation_partition.py -q
```
