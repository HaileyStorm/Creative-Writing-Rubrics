# Historical Artifact Disposition and Provenance

## Status and scope

This is the proposed public-safe index for the pre-existing historical CWR
artifact population with logical root ID
`cwr-historical-artifacts-20260820-v1`.  It deliberately does not add raw
historical artifacts to the public repository.

The private custody manifest is schema
`cwr-artifact-custody-manifest/v1`, snapshot
`2026-08-23T17:33:27.5861971Z`, SHA-256
`bbd2ddf6dc8d251c369019a6c259e6d1502497073537547263e7ce703abe9319`.
It records 112 direct entries, 17,147 files, 3,638 directories, and 20,785
custody entries.  The custodian is `Codex task
01a02ca3-5f2e-72f1-94cb-36ca6c525e91`.

The private receipt is held in the logical private-custody location
`cwr-artifact-custody-20260823`, in `custody-receipt.v1.json` beside
`custody-manifest.v1.jsonl`; these are not public repository paths.  No durable
former-834 membership ledger was available in scope, so every custody entry is
marked `UNPROVEN` rather than being treated as equivalent to an informal count.

Nothing in this record changes the disposition of active P1, S1, S2, L2, or
figurative packages in this checkout.  Their current untracked execution
packages remain owned by their active studies.

### Disposition terms

| Disposition | Meaning |
| --- | --- |
| **PROMOTE** | A small, public-safe index or regenerated result may enter the repository after normal review. |
| **RETAIN_PRIVATE** | Preserve outside the public checkout; it may contain run evidence, prompts, responses, or restricted data. |
| **SUPERSEDED_REGENERABLE** | Historical output/cache/install material. Keep until the stated replacement receipt exists, then remove only in its named cleanup batch. |
| **BLOCKED** | Do not publish, relocate, or delete until a provenance/privacy owner records the missing authority or source relationship. |

This uncommitted document is not promoted.  It becomes a public record only
after review, commit, and push; no historical raw artifact is thereby declared
public, current, or reproducible.

## Bound survivors

The following hashes bind the named files that must survive until their
corresponding disposition gate is met.  Hashing a file proves its identity, not
its scientific validity or publication eligibility.

| Path relative to artifact root | SHA-256 | Disposition |
| --- | --- | --- |
| `hanna-coling-review.pdf` | `977a0af449a2a2ddce960612f5b2e16ff4e6fccab6296280142a98987075accb` | BLOCKED |
| `scene-packet-final.json` | `6b31ed0c271bae1297edcf6be8372f3e6487f97e8e12f51961257e3ba33535b6` | BLOCKED |
| `scene-packet.json` | `ba31cd0d5e989e58d3dd384730ed66b4545c8dd7f9b27e08589d5364e632a1fc` | BLOCKED |
| `scene-packet-short.json` | `ba31cd0d5e989e58d3dd384730ed66b4545c8dd7f9b27e08589d5364e632a1fc` | BLOCKED |
| `git-install-scene.json` | `ba31cd0d5e989e58d3dd384730ed66b4545c8dd7f9b27e08589d5364e632a1fc` | BLOCKED |
| `scene-leaves.jsonl` | `2b59b5ac69c28399c8f86c39fff7586bd9f0590c4f37b00c1d69c8ae27695458` | BLOCKED |
| `wheel-scene.json` | `ba31cd0d5e989e58d3dd384730ed66b4545c8dd7f9b27e08589d5364e632a1fc` | BLOCKED |
| `questions.jsonl` | `c85c1e563f7b95be924137852245b70d6db83324c546ebf2ae39a6d1c29bcc37` | BLOCKED |
| `judge-prompt.txt` | `4eaaf0b5126014896eecd4375a327b4d9f4737c477b2bdc118c9f6332a2241ea` | BLOCKED |
| `score.json` | `03d631970dc10a046c3b62645f9c6f0ce682eca9d1127e81ff7fd16d01b55202` | BLOCKED |
| `wheel-judge.txt` | `a2a466a497a9d4bca6c5fc4454e8174e202e7810e7d375801023b0660612458a` | BLOCKED |
| `show-prose-scene.json` | `40e505ead1e2ad029155ba00bb7018175027bae50388c23604d49aa489093105` | BLOCKED |
| `show-prose-scene.yaml` | `40e505ead1e2ad029155ba00bb7018175027bae50388c23604d49aa489093105` | BLOCKED |
| `dist-final/creative_writing_rubrics-1.1.0-py3-none-any.whl` | `0bc3c4fe5f7022849678ab50208b7610174cbaa09c7b8bdf345989e06a571d6d` | SUPERSEDED_REGENERABLE |
| `dist-final/creative_writing_rubrics-1.1.0.tar.gz` | `d78f6ff02c65f519351f9281aded44f304adf2ab3461fc92cbf6d0c7d034cd64` | SUPERSEDED_REGENERABLE |
| `codex-tool-free-probe/run.json` | `a23004ff44abfd3f17f7abc934facd253de0ef8eb895219153b1e9320a263493` | RETAIN_PRIVATE |
| `pytest-hanna-binding-final/test_executed_confirmation_gat0/frozen-run-contract.json` | `f785207968dae6ba863dc979df5327095d5b8f2c79ffcc3981f588fd7309b84c` | RETAIN_PRIVATE |
| `bundles.txt` | `12b034d24568b0136dbcf5dc16191f385c80735f095d242391877e836cd6bc53` | SUPERSEDED_REGENERABLE |
| `modules.txt` | `be6b5f22db68ef2f1e79b7eadde180162623c0604de8e65bc7b6cad0f9c9119e` | SUPERSEDED_REGENERABLE |
| `wheel-fixed-validate.json` | `73ab17f9a4bb0b788b31bc2d8d8e88bd14b042e31e3bb3621e0d96189e68a1d2` | SUPERSEDED_REGENERABLE |

## Complete direct-root family map

This table classifies every direct entry by a non-overlapping name family.  A
glob is literal PowerShell-style name matching at the artifact-root level, not
a recursive match.

| Root family | Direct entries covered | Disposition | Reason and settlement gate |
| --- | --- | --- | --- |
| `codex-sol-medium-smoke*`, `codex-tool-free-probe` | 6 directories | RETAIN_PRIVATE | Contains response, prompt, schema, run, and verdict records. Retain as development evidence; any public derivative needs a separate redaction/provenance review. |
| `pytest-hanna-*` | 13 directories | RETAIN_PRIVATE | Includes HANNA annotation CSV copies and execution-test material. Keep private until a data-rights/provenance owner maps each CSV to its authorized source and determines retention. |
| `pytest-longform-*` | 25 directories | RETAIN_PRIVATE | Repeated longform test runs may carry prompt/output material. Retain pending an evidence-only deduplication receipt; do not assume public safety from the directory name. |
| `pytest` and `pytest-*` excluding the two preceding rows | 22 directories | SUPERSEDED_REGENERABLE | Pytest temporary trees, caches, runner outputs, schema checks, packaging checks, and release-test outputs. Eligible only after a pinned-source regeneration receipt records command, commit, pass count, and replacement hash. |
| `exact-final-a4bf165804b8444ca417b38f865191b1`, `final-523109f6cf164d2b82fd218a99fe2669`, `focused-v3`, `longform-v5`, `targeted-release-20260820`, `cli-final`, `temp-verify` | 7 directories | SUPERSEDED_REGENERABLE | Test/output workspaces and caches. Their names do not substitute for a source revision or a verified final gate. Replace with one compact, current receipt before removal. |
| `isolated-install-final` | 1 directory | SUPERSEDED_REGENERABLE | Historical virtual environment/install tree (1,610 files). Replace with a current isolated-install receipt; never archive the environment as release evidence. |
| `dist`, `dist-fixed`, `dist-final`, `public-final`, `public-score-final`, `public-surface-final-20260820`, `public-448c461-installed-dry-run` | 7 directories | SUPERSEDED_REGENERABLE | Historical build/distribution and associated test outputs, including 1.1.0 wheels/sdists. A reproducible build from the identified source revision plus package hashes is required before deletion. |
| `full-af033eca873e49f0b62cbfd547a91868`, `full-exact-final`, `full-final`, `full-final-20260820` | 4 directories | SUPERSEDED_REGENERABLE | Large pytest/cache trees (449, 683, 683, and 877 files respectively). They are covered separately to make the large "final" families explicit. |
| `secondary-c722ca6c83e142ef8518d1c834a0a5f2`, `prov-a22b246dccd7485eb72aa7cc02b19eb4`, `privacy-fix-c69d3e5ce3194d9eb4297240165aaec4`, `glob-proof` | 4 directories | RETAIN_PRIVATE | Small provenance/privacy diagnostics. Keep until a reviewer binds them to an issue/commit and either promotes a redacted summary or supersedes them with a verified receipt. |
| `scene-packet.json`, `scene-packet-short.json`, `scene-packet-final.json`, `git-install-scene.json`, `show-prose-scene.json`, `show-prose-scene.yaml`, `scene-leaves.jsonl`, `questions.jsonl`, `judge-prompt.txt`, `score.json`, `wheel-scene.json`, `wheel-judge.txt` | 12 files | BLOCKED | Potentially source-derived prose, prompts, or model-facing packets. Preserve exactly; promotion requires explicit source/prose authorization and a provenance link. |
| `hanna-coling-review.pdf` | 1 file | BLOCKED | Third-party publication copy. Retain privately; link to the canonical publication instead of publishing a duplicate unless rights are confirmed. |
| `bundles.txt`, `modules.txt`, `cwr-help.txt`, `hbq-help.txt`, `module-help.txt`, `python-api.txt`, `validate.txt`, `wheel-bundles.json`, `wheel-fixed-validate.json`, `wheel-validate.json` | 10 files | SUPERSEDED_REGENERABLE | CLI/help/validation snapshots. Regenerate from a pinned current or historical source revision; retain only the command and digest in a compact receipt. |

The rows cover all 112 direct entries: 89 directories and 23 root files.  The
apparent 23-file difference in the listed root-file families is intentional:
the 12 BLOCKED, one HANNA, and ten regenerable rows total 23.

## Exact cleanup batches (proposed; not executed)

### Batch A — separate regenerable-family receipts

Each row must produce its own receipt with the exact proposed name below.  A
receipt must bind the logical root ID, all direct members in its row, full source
revision, commands, pass/fail count, output hashes, and the manifest digest
above.  A generic green test run cannot settle another family.

| Family and exact members | Proposed receipt | Cleanup gate |
| --- | --- | --- |
| `pytest` and `pytest-*` excluding `pytest-hanna-*` and `pytest-longform-*` | `artifact-receipts/pytest-regenerable-output.v1.json` | Run the declared replacement tests from one full source SHA; the receipt must enumerate all 22 direct roots and have zero unexpected failures. |
| `full-af033eca873e49f0b62cbfd547a91868`, `full-exact-final`, `full-final`, `full-final-20260820` | `artifact-receipts/large-final-regenerable-output.v1.json` | Independently rerun the stated full/final gate from one full source SHA and verify its output hash set. Do not settle this family with the ordinary pytest receipt. |
| `exact-final-a4bf165804b8444ca417b38f865191b1`, `final-523109f6cf164d2b82fd218a99fe2669`, `focused-v3`, `longform-v5`, `targeted-release-20260820`, `cli-final`, `temp-verify` | `artifact-receipts/workspace-regenerable-output.v1.json` | Regenerate each named workspace class and map every old direct root to a replacement command/result/hash. |
| `isolated-install-final` | `artifact-receipts/isolated-install-regenerable-output.v1.json` | Create a clean temporary install from the declared source/package, run the designated smoke check, and retain only the receipt—not a virtual environment. |
| `dist`, `dist-fixed`, `dist-final`, `public-final`, `public-score-final`, `public-surface-final-20260820`, `public-448c461-installed-dry-run` | `artifact-receipts/distribution-regenerable-output.v1.json` | Rebuild the declared package revision, record wheel/sdist hashes and install verification, then compare against the bound historical 1.1.0 hashes where applicable. |
| `bundles.txt`, `modules.txt`, `cwr-help.txt`, `hbq-help.txt`, `module-help.txt`, `python-api.txt`, `validate.txt`, `wheel-bundles.json`, `wheel-fixed-validate.json`, `wheel-validate.json` | `artifact-receipts/cli-validation-regenerable-output.v1.json` | Re-run each declared CLI/help/validation command from a pinned source revision and bind the current output hashes. |

Only after its own receipt passes may a family enter a physical cleanup batch.
The physical command must consume an exact manifest-derived member list for
that one family; it must not use a broad parent-directory recursive delete.

### Batch B — private evidence settlement

For `codex-*`, `pytest-hanna-*`, `pytest-longform-*`, and the four small
provenance directories, produce a private-only manifest containing path,
SHA-256, source/revision (if known), data classification, and retain/delete
decision.  Do not copy the contents into this public repository.  The HANNA
annotation copies cannot enter a removal batch until their rights and expected
retention period are documented.

Batch B is now settled as `RETAIN_PRIVATE` for all 48 direct roots: six Codex,
13 HANNA, 25 longform, and four provenance roots. The private settlement
manifest commits to their custody records at
`5db3a11f6c7c8d193d58aed975adcf830f6028cc97738ee5149776064a71c1c0`.
Delete authorization remains zero, and each family has a named rights,
provenance, or supersession recheck condition.

### Batch C — blocked content decision

For the twelve scene/prompt/output files and `hanna-coling-review.pdf`, a
designated provenance owner must choose one of:

1. retain privately with a source/rights link;
2. create a redacted public aggregate; or
3. delete after a retained hash manifest and explicit authority.

No automatic regeneration or cleanup is appropriate because the inputs may be
creative source, third-party text, or model-facing prompts.

Batch C is now settled as `RETAIN_PRIVATE` for all 13 files. The private
manifest commits to 13/13 custody hashes at
`a7b152b0418db5f43a9e2f8660e6be74a2f9290d6ccd14216ee399a587f9d71a`;
the private receipt is committed at
`bd06221e9797ed8a914f0dbe5b6655c341109db75a548e82445716af99229342`.
No raw content was published, relocated, or deleted. Public release,
redaction, relocation, or deletion remains closed pending the source/prose or
third-party rights authority described above.

### Batch D — physical cleanup

For each one settled Batch-A family, verify that every bound survivor either
remains or has the successor receipt named above, then delete only that
manifest-derived member list.  Re-scan the logical root after every family and
append the new count, remaining direct roots, receipt ID, and operator to the
next custody receipt.  BLOCKED and RETAIN_PRIVATE entries never join this batch
without their separate Batch-B/C authority.

## Current non-goals and follow-up

- This record does not claim that historical test outputs validate the current
  HBQ-RS 1.2.0 package.
- It does not reopen or modify active validation packages.
- It does not replace the current project narrative or the public results
  packages.
- It is intentionally conservative: uncertain creative, HANNA, model-response,
  and third-party material stays private or blocked until an owner settles it.

The current task custodian should implement the six independent Batch-A
replacement-receipt verifiers listed above, then run each receipt's relevant
current checks. A validated receipt unlocks only its exact manifest-derived
family; directory names such as `final` never authorize cleanup.
