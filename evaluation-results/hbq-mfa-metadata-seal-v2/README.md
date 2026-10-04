# MFA full outcome-blind metadata seal

`project.py` extends the preserved v1 seal to both pinned releases, all four expert and four lay outcome files per release, and the identical-blob Human-AI reference catalogues. The exact 18 source locators, revisions, Git blob IDs and byte bounds are frozen in `source-recipe.json`; its canonical JSON digest is enforced by the CLI. There is no arbitrary URL or recipe argument. This is private non-commercial confirmation-design research, not an alignment result, candidate promotion or target-opening authorization.

The source [Author-Style README](https://raw.githubusercontent.com/tuhinjubcse/Author-Style-Personalization/d7e4925307ebe354a376ca7f38d8bd014775b6f2/README.md) restricts use to non-commercial research because some passages are copyrighted. Raw outcomes and copyrighted prose remain in a private destination outside the repository. The related [GoodWriting release](https://github.com/tuhinjubcse/GoodWritingBeGenerative/tree/4cc907c25ff6955bdeeb224385bb9fe513215043) is a related release, not an independent evidence cohort. No generation-prompt tree or other source is fetched.

Run from the repository root, supplying the already sealed v1 cache to avoid retrieving completed expert blobs again:

```powershell
.venv\Scripts\python.exe evaluation-results\hbq-mfa-metadata-seal-v2\project.py --private-output <fresh-private-directory> --cache-root <v1-private-directory>\sealed-source
```

Each missing blob receives one bounded request to its exact pinned raw GitHub URL. Redirects and automatic retries are disabled. Cache candidates come only from registered source paths; reuse requires the exact Git blob and byte count. The four prior expert SHA-256 receipts are also checked. Every source gets a SHA-256 receipt and sealed-file read-back check, including sources whose bytes were reused. Related releases retain their own repository/revision/path commitments and exact native filenames. Local retrieval origins remain only in private receipts.

For provider-free reproduction of a full run:

```powershell
.venv\Scripts\python.exe evaluation-results\hbq-mfa-metadata-seal-v2\project.py --private-output <new-private-directory> --source-root <prior-v2-private-directory>\sealed-source
```

`--source-root` never falls back to the network. A fresh output cannot contain, or be contained by, the repository or any source/cache root. Exclusive file creation preserves invocation, frozen recipe, both implementation receipts, pre-contact requests, received-byte receipts, sealed bytes, accepted per-source receipts and metadata parts, private metadata, count-only summary and terminal receipt. Received-byte receipts are not acceptance; pin-mismatched bytes remain private for reconciliation and never reach projection. On failure the completed prefix remains; do not rerun into that destination or infer that an ambiguous failed contact can be resent. The owner must reconcile any real transport failure before a new attempt.

Projection whitelists the known target → writer → two/three-item judgment structure. It records source positions, nonempty identifier hashes, exact ordered UTF-8 excerpt hashes/lengths, and explicit `Original` presence/hash/length. Winner, Preference, rationale, unknown fields, raw identifier values and all prose remain sealed. Missing rater, record, target, writer or original identity stays explicit; missing excerpts fail safely. The v1 pair identity excludes writer, task, panel and release. Ordered pair identity distinguishes presentation order. Nominal target/writer groups, their pair memberships and groups with multiple exact pairs are counted separately, preserving the previously observed six split fine-tuned style groups and 96 memberships versus 95 exact pairs without merging variants, selecting majority text or transferring votes.

Cross-release row overlap means equality of whitelisted metadata including source positions, not equality of raw judgment labels. Text/pair/rater/record overlap remains diagnostic under the declared source-label hash namespace. Equal rater hashes do not prove the same independently verified human, panel identity or independent labels. Repeated releases, labels, works, texts and pairs never become a new independent-work count.

The pinned [source parser](https://raw.githubusercontent.com/tuhinjubcse/Author-Style-Personalization/d7e4925307ebe354a376ca7f38d8bd014775b6f2/StatAnalysis/01_build_data.R) reads author records with explicit lowercase `writer` and `original` fields (lines 81–91). Its catalogue `writer` identifies the target author, so reference linkage compares that identifier hash with an outcome **target** hash. A bounded programmatic traversal commits lowercase `original` presence/hash/length and explicit `writer` identity; uppercase `Original` is retained as separately declared compatibility behavior. If both fields occur, both commitments survive. Exact UTF-8 bytes are preserved without upstream text cleaning. The released root shape remains unverified, and unknown outer keys never become inferred identities.

Reference reports separate text-only overlap from exact catalogue-writer ↔ outcome-target plus original-text hash matches. Missing identities or text, unmatched identifiers/text and multiple original variants remain explicit. Exact hash matches establish metadata links under the declared source-label namespace; they do not establish participant independence or quality outcomes. A catalogue with no recognized fields produces zero recognized reference records, not proof of absent references. The first private full-run implementation and output snapshots remain immutable evidence of the uppercase-only predecessor; fresh projection of the retained exact source bytes supplies corrected reference metadata.

Local checks:

```powershell
.venv\Scripts\python.exe -m pytest tests\test_mfa_metadata_seal_v2.py -q
```

Synthetic checks prove outcome blindness, exact order and variant geometry, duplicate accounting, lowercase catalogue linkage to outcome targets, explicit missingness and reference variants, immutable output failure, pin/recipe/SHA checks, retained partial failure and provider-free replay. Actual corrected catalogue geometry and reference matches require the owner's fresh provider-free projection of the retained sources. Candidates, comparator contracts, partition and confirmation plan must be frozen separately before target opening.
