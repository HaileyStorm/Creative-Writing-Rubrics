# Proposed replacement after the Windows reboot

Status: **OWNER APPROVAL PENDING. No replacement contact is authorized.** Implementation and independent review are complete; this proposal is not an execution receipt.

The Windows update interrupted cohort 78. Requests 771 and 772 completed; request 773 has a lifecycle-start record but no retained response, event stream, checkpoint, accepted output, or settlement. The CLI used an ephemeral session. The reboot proves that the old local process stopped, but does not establish whether the provider received or completed request 773.

The frozen baseline permits one cumulative attempt per batch and stops on ambiguity (`baseline-measurement-v1.json`, attempt policy). Ordinary reboot recovery permits inspection and reconciliation; it does not authorize another attempt. The existing ordinal-221 adoption concerns an already-recorded result and cannot authorize this missing-result replacement.

## Proposed owner decision

Authorize exactly **one prospective replacement attempt for logical request 773**, after the exact implementation, manifest, and independent review are bound to the decision and fresh included-allowance receipts pass the existing gates. The original attempt may already have reached the provider. It remains permanently ambiguous and preserved. The replacement is an additional attempt under this named exception, never the original first attempt or a recovered original result.

Use a separate owner-local sibling evidence namespace named `sol773-replacement-execution-v1`, with its exact resolved location bound in the manifest. Preserve the original native root, lifecycle record, source, completed requests, and all prior reviews. Deliver the exact frozen prompt and schema to the unchanged Sol model/reasoning configuration. Do not contact any other ordinal during this replacement operation.

An exclusive start marker must make the replacement single-use, including after failure or another interruption. There is no automatic third attempt, fallback, imputation, or selection between outputs. Any later discovery of the original result requires reconciliation before admission. Request 774 and later remain stopped until the replacement is accepted under its exception and a separately reviewed continuation can compose that lineage.

## Fixed evidence and payload commitments

| Item | SHA-256 |
| --- | --- |
| Frozen plan | `edeadb93c485ba227153329b5ae420de1c9d08d95e920bac0635d197fd3dbd7f` |
| Original 773 lifecycle start | `92e959db6be2ad97df73fc1a14b110e361005dccff1f0953127b6c36e1c04a43` |
| Interruption audit | `4953eb48496d9571ffae5309cb5e4eb33daecaa43a6c513a17e45c4eadffdb4c` |
| Reboot observation | `2e9f96d92c5fb213078464bbaad44e4916b102c191e87fbd7d294a65f7be641e` |
| Completed prefix through 772 | `83e80e62f47f28a4aefef01f39c9455b16108029ab7e8395709b2f27c33ab6cd` |
| Story source, 793 bytes | `f5548847a5d566a17aeccb13a6fc8b1ebbc55e303cf54766b0de3ba2b6c80c7c` |
| Exact prompt, 7,743 bytes | `d3c8ffdfaaabf6cdfe55662da277c33d02aa1a04d68c8cb5cf9cbaa8b82c0c98` |
| Exact schema, 2,542 bytes | `6828735e3fc6e2ef61807588f0c66e5e355ec543647cd1c5e4902053b3f2cec9` |

Request 773 is batch 14 of `baseline8-v1/train/0034/dryad-28525e90bcce269ace039aa7`. The exact eight question IDs remain those in the frozen request. The stable manifest binds the story source, selected runtime/adapter/CLI, executor bytes, original evidence, and exact replacement root `C:/Users/Haile/Documents/sol773-replacement-execution-v1`. The independent review binds that manifest and implementation; the later owner decision binds the manifest and review. A renewable execution binding then binds those three records to current route and receipt commitments and its review validity window. This ordering avoids circular commitments and keeps an expired receipt from invalidating the durable owner decision.

## Required verification before an approval request

The versioned executor and admission adapter must be implemented and independently reviewed before asking the owner to adopt this exception. Offline checks must demonstrate unchanged payload bytes; no contact for 771, 772, or 774; rejection of missing or changed authority and commitments; rejection after any replacement start; no retry after an error or interruption; preservation of the original native tree; and rejection of changed or invalid admission evidence. Live receipt, route, CLI, source, and review-window checks must run again immediately before the sole authorized contact. Expiry checks use a fresh clock reading after slow frozen-file verification, retain the full 300-second response allowance, and record the actual contact authorization separately from the earlier start marker for later admission.

The implementation and provider-free checks are complete. Independent Astra review returned **GO FOR OWNER APPROVAL PACKET** at the exact executor and manifest below. This is implementation review, not owner approval or execution authority.

| Reviewed artifact | SHA-256 |
| --- | --- |
| `sol773_replacement_execution.py` | `2138e139599b17de719e55d49b0ba6d0d98e5f645427a3e79d564ae673d272ba` |
| `tests/test_dryad_sol773_replacement_execution.py` | `4579883fd09565f76724a576253e074a5c3ac6302d5266887b6e37d492750ed2` |
| Local stable manifest candidate v3 | `db0dd0c931f7f6230b132d65afa0a7c0f016c2e9ecb135f0488f7b434e2f0179` |
| Independent review record | `101a243b1205d3e167b2cb0f904305a9a4d3188c49acd17307f8dcfbeaa87460` |
| Preserved original native tree | `fe3e03b9db17c5f71a6c61c183cb520cf5336b2dfaccb06c0feffa93ba199e02` |

The local manifest is `C:/Users/Haile/Documents/cwr-dryad-sol773-replacement-authority-20260909-r1/manifest-candidate-v3.json`, with `independent-review-v1.json` beside it. Candidates v1 and v2 are retained as superseded review history and cannot authorize the revised executor. The obsolete preflight helper was removed after its replacement; original incident artifacts remain necessary provenance. The replacement output directory remains absent. No owner-decision or renewable execution-binding record exists.

Validation: `python -m py_compile evaluation-results/hbq-human-alignment-dryad-full-hbq-analysis-v1/sol773_replacement_execution.py` passed; with `PYTHONPATH=src`, `python -m pytest -q tests/test_dryad_sol773_replacement_execution.py` passed 29 tests and the existing `test_dryad_sol_existing_runtime.py`, `test_dryad_sol_measurement_execution.py`, and `test_dryad_sol_pass_admission.py` suites passed 25 tests. The actual manifest passed `_manifest` and `_frozen_payload`, including unchanged native-tree verification. These are offline correctness checks; native replacement execution remains unperformed.

## Unchanged limits

This proposal does not restore original one-attempt protocol compliance, waive the preserved pass-19 coverage failure (0.8607 below 0.88), grant complete-study admission, or establish alignment or release readiness. Preserve the sequencing amendment, ordinal-221 recovery limitations, count-correction history, requested-only identity evidence, and unproven native endpoint/internal-retry cardinality. No billing change, paid fallback, Grok activation, WPB cache cleanup, or terminal V17 resend is included.
