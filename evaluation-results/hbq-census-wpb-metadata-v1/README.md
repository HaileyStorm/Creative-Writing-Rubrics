# WPB completed metadata census

This provider-free reader joins the 129 historical completed Sol receipt commitments (four preserved and 125 successor measurements), thirteen completed successor settlements, and four separately namespaced ancestor settlement records. It checks the public result's provenance against the saved private final report and completion and joins the four retained reconciliation records. The finite recipe pins 29 static inputs by root ID, relative locator, SHA-256 and byte length. The pinned report supplies the exact receipt membership and byte commitments; fixed source-relative layout rules supply their paths. Preserved IDs are derived in frozen order from the pinned manifest and checked against the report. The private ledger retains all 158 descriptors and their byte lengths. It performs no discovery scan.

It reuses the pinned v2 canonicalization utility and extracts only `require` and `project_json` from the pinned lexical reader. Targets, prose, `human_score_projection`, prepared request bodies, sessions, raw responses and analysis outcomes are skipped. Native identities are decoded only as metadata, canonically committed with sorted compact JSON, UTF-8, `ensure_ascii=False`, `allow_nan=False` and a trailing LF, and retained as hashes in the private ledger. Logical cell IDs and namespaced ancestor occurrences stay in that private output; the public report contains aggregate counts and commitments.

From the repository root, run once with a fresh output directory:

```powershell
python -B evaluation-results/hbq-census-wpb-metadata-v1/census.py --documents-root "<DOCUMENTS_ROOT>" --control-root "<CONTROL_ROOT>" --output-root "<FRESH_CENSUS_OUTPUT_ROOT>"
```

`--dry-run` computes the same joins and verifies source commitments without writing outputs; it still reads the finite corpus. The implementation agent ran compilation and synthetic projection/path checks. The owner executed the census and independently verified the aggregate and source commitments. The first attempt stopped at an output guard before corpus access; its exact source snapshot remains retained. The corrected execution completed with 129 receipt joins, thirteen successor settlements, 158 committed files and four retained reconciliation records. The four ancestor namespaces contain 40 status occurrences over thirteen logical IDs; eleven IDs recur, and 36 occurrences over twelve IDs retain the generic `terminal_or_ambiguous` state.

The completed report SHA-256 is `a76d8cf5eae33c7d3e836e01a1c8be4aa3318f72c769d218b5ca7a28d4a1d60f`; its private-ledger commitment is `a34881ae00d56281943c0d7a1161f8312b362d6631de925be44d12665b5e0899`. The owner readback SHA-256 is `3a81302efc4c469266e6f197f799f00bc8cda4ad5d07488a0178cb54f551cf4b`. These prove the finite metadata census and source binding, with the limitations below.

The output is create-only, must be outside the repository and retained input directories, and includes `report.json`, `private-ledger.json`, `recipe.json`, `census.py` and a completion-last `terminal.json`. Source commitments and implementation/recipe bytes are checked again before writing. A failed or partial output remains retained and cannot be reused.

The completed census pins are frozen in `registry-v6.recipe.json`. The registry extension command is:

```powershell
python -B evaluation-results/hbq-census-pass-b-dispositions-v1/registry_v6.py --documents-root "<DOCUMENTS_ROOT>" --control-root "<CONTROL_ROOT>" --output-root "<FRESH_REGISTRY_OUTPUT_ROOT>"
```

V6 verifies saved v5 and the new census without rerunning either. It changes only the WPB declaration edge to metadata membership, appends a named completed metadata census and reduces unresolved declarations from 58 to 57. Historical observation, leaf and vote counts remain inherited. Ancestor `terminal_or_ambiguous` rows remain generic namespaced status occurrences: they do not establish failed contacts, unlaunched jobs or physical retries. Historical `gpt-5.6-sol`/high settings are requested-only; reasoning is unattested. Current native admission and scoring are not replayed, provider calls and new votes are zero, and physical contact/retry cardinality remains null. This census grants no promotion, release, quality or human-validation authority.

The owner executed v6 and independently verified that exactly one edge changed and all inherited counts remained unchanged. Its report SHA-256 is `d70d04b4504b65ff74d271778441e2f7f1a7afc6afa2759c258c12d147bb7dfd`; terminal SHA-256 is `60e51faf46f07a9599a4463670a04d24469b4e2b3d5cb9d9f8528fb1c2030a0f`; independent finite acceptance SHA-256 is `9cfbec2a2d2501dc0287d2d87c36be59040c8303f2f95cbda9fc9788154a9847`. The resulting inventory retains 76 declaration packages and 115 edges, with nine completed censuses, six qualified metadata-only packages and 57 unresolved declarations.
