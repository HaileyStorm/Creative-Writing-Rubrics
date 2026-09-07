# Proposed Sol collection sequencing amendment

Status: **unapproved proposal; no provider authority**. No Sol request beyond 120 may proceed under this proposal without an explicit owner decision and the usual independent cohort review and current route/receipt checks.

## Deviation and preserved cutoff

The inherited [comparison protocol](protocol-v2.json) requires Sol judging **after Grok TRAIN/DEV selection**. The [fixed-batch measurement contract](baseline-measurement-v1.json) inherits that comparison unchanged. Sol requests 1–120 were instead collected before Grok selection. The controlling task failed to enforce the ordering requirement; independent review confirmed the discrepancy on 2026-09-07.

The early results have native local-lifecycle and frozen-payload evidence, but they are not compliant validation under the original sequencing rule. Some Sol judgments and canonical story scores were observed before this proposal. They must not be retrospectively described as unobserved or as exact original preregistration. No Sol alignment comparison or weight fit has been produced by this task.

Collection is stopped at cohort 12: 120 batches, 930 leaf judgments, five complete story passes and 40 leaves from the sixth, with 120 distinct local CLI thread IDs. Request 121 has neither a completed response nor a native attempt-start record. Its precontact prompt cache, where present, is not a provider result.

Immutable commitments:

- Parent protocol SHA-256: `33e7dde670bf212da0ee7c4cd6cf628f9a43949dc597cea47b0d97aa4e158e2b`.
- Fixed-batch contract SHA-256: `6ae404e31ecafbeac0ef69814127c5222ac8da5fd24c2700f185ca2f8af5cf37`.
- Frozen plan SHA-256: `edeadb93c485ba227153329b5ae420de1c9d08d95e920bac0635d197fd3dbd7f`.
- Local prefix-admission record SHA-256: `0352316fcad9fe479fb270006cadd8a51838e5a5a3e4bad6f0dc707870d20e86`.
- Local cutoff record SHA-256: `0128ed0fb42c1103a2b22118f818448de87eec14cda204040ddb4bfa29d1a9ce`.
- Cutoff inventory: 1,151 files, 7,666,399 bytes; file-map SHA-256 `6e5bbbf3b8742c9ea1942009afe37ce5108a0424e6d346ab9e197fbe3b654e3f`.

The machine-local records are `cwr-dryad-sol8-cohort12-admission-20260907-r1.json` and `cwr-dryad-sol8-sequencing-cutoff-20260907-r1.json`. Original records, judgments, source, reviews and failure evidence remain unchanged.

## Requested owner decision

Adopt a versioned descendant that permits early or parallel **collection** of the already frozen Sol leaf judgments, while keeping comparative validation after the complete frozen Grok TRAIN/DEV selection. Explicitly carry forward the exact 120-request prefix above and continue once from request 121.

The amendment would require:

1. Preserve all 236 stories, all 178 criteria, all 5,428 requests per endpoint, data partitions, frozen prompt/schema bytes, source bindings, batch size and independent native checks. No filtering, favorable-pass selection, extra votes, or reconstruction of missing judgments.
2. Keep Grok fitting, trial enumeration, sampler, objective, tie-breaking, recovery decisions and winner selection independent of Sol outcomes. Do not use Sol results to tune or reconsider the Grok choice.
3. Freeze the complete Grok TRAIN winner and Grok DEV comparison before any Sol comparative analysis. Then rescore Sol's unchanged leaf judgments offline under the canonical baseline and that same selected weight profile. Do not put selected weights into the judge payload or refit on Sol.
4. Label eventual derived evidence `sequencing_amended_after_partial_sol_observation`, bind this amendment and the cutoff in its admission/analysis provenance, and disclose the temporal deviation in public reporting. Do not label it exact original preregistration or confirmation evidence.
5. Preserve requested-only model/reasoning identity, unproven native endpoint contact cardinality, the null empirical batch cap, and every other existing limitation. Early collection does not establish completed baseline, alignment, release, or promotion authority.
6. Bind each later Sol cohort's independent review to the approved amendment and its preserved cutoff before contact. Keep the existing per-contact route, receipt, timeout, immutable payload and terminal no-resend checks. No paid fallback, billing change, or new attempt on a terminal sample is authorized.

This proposal does not rearm Grok, change the separate request-51 recovery authorization, reopen V17/WPB or earlier qualification attempts, release confirmation, or change the original immutable protocol files. Adoption must be recorded separately against this proposal's exact committed bytes before continuation.

If the owner declines, preserve and quarantine this early prefix from comparison, retain the original sequence, and prepare a separately reviewed fresh post-selection Sol namespace with new identities after Grok selection. No automatic recontact is authorized now by that alternative.
