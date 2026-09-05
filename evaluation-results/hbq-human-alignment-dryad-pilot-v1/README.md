# Dryad source-freeze pilot

## Source plan

This package freezes a local, independently audited source corpus before any model work. `source.py` imports the exact hash-pinned Dryad audit program from commit `6cb64b2`, asks it to reconstruct the already pinned archive in memory, verifies its complete reconciliation, and writes a new external freeze root only when that root does not exist. It does not execute supplied upstream scripts or make provider calls.

The freeze has 293 unique story texts and unweighted per-story means for twelve blinded human-rating axes. It partitions stories within each of the nine topic-by-condition strata using a fixed source-only seed and creates no model, rubric, or cross-dataset result.

## Freeze boundary

The audited source program and all source hashes are pinned in [experiment-contract.json](experiment-contract.json). The freeze writer expects repeated rating rows for one canonical story ID, then aggregates them. It rejects duplicate text across different story IDs, text/stratum drift, missing axes, rating-range drift, and any mismatch with the audited 293-story/3,519-rating reconciliation.

It creates exact-byte local artifacts in a fresh external root:

- `local-targets.jsonl` contains source IDs, treatment/topic strata, rating counts, and twelve human means.
- `confirmation-targets.jsonl` contains only confirmation targets and is separate from training/development material.
- `public-inputs.json` contains only opaque IDs and story text for TRAIN and DEV.
- `split-manifest.jsonl` and `provenance.json` record the deterministic partition and hashes.

`load_public_inputs(freeze_root, expected_provenance_sha256)` first verifies the externally supplied provenance hash, the historical creation commit's source and contract bytes, every artifact hash/byte count, the exact target/split/confirmation subsets and order, and public text hashes. It then returns only TRAIN and DEV opaque IDs plus story text. It has no target, strata, rating, or confirmation-loading interface. The local artifacts must remain local until a separately reviewed experiment contract authorizes their use.

Actual freeze creation records the current exact Git commit plus runtime-computed generator-source and contract hashes, and requires those bytes to be committed at that HEAD. Later verification checks the recorded historical commit rather than requiring the verifier to run at the same current HEAD. Explicit `TEST_FIXTURE` identity is available only for isolated tests.

This is source-freeze evidence only. It does not establish model alignment, an HBQ-RS mapping, a pooled score with HANNA or WPB, or a runtime/profile promotion.
