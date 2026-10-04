# MFA outcome-blind source audit

`project.py` seals four exact expert JSON blobs from Author-Style-Personalization revision `d7e4925307ebe354a376ca7f38d8bd014775b6f2`, then emits hashes, lengths and cohort counts. Preferences, winner fields, rationales, rater identities and excerpt prose never appear in the public projection. Unknown record fields remain sealed rather than becoming metadata. This is confirmation-design preparation, not an alignment result or candidate promotion.

The pinned [upstream README](https://raw.githubusercontent.com/tuhinjubcse/Author-Style-Personalization/d7e4925307ebe354a376ca7f38d8bd014775b6f2/README.md) restricts data use to non-commercial research because some passages are copyrighted. The [upstream parser](https://raw.githubusercontent.com/tuhinjubcse/Author-Style-Personalization/d7e4925307ebe354a376ca7f38d8bd014775b6f2/StatAnalysis/01_build_data.R) supplies the two/three-item judgment structure and field names; it is read as source evidence, not executed. Raw inputs and the blinded identifier ledger remain outside the repository.

Run from the repository root:

```powershell
.venv\Scripts\python.exe evaluation-results\hbq-mfa-metadata-seal-v1\project.py --metadata evaluation-results\hbq-evidence-census-pass-a-v1\unused-source-metadata-20261004.json --private-output <fresh-private-directory>
```

For provider-free reproduction, add `--source-root <prior-private-directory>\sealed-source`. Output must be fresh and outside the repository and retained inputs. Retrieval is bounded to the four pinned file sizes, with no automatic network retry. Git blob IDs and byte counts are checked before projection; raw SHA-256 receipts are retained.

`expert-summary-001.json` observes 1,440 judgment rows, 50 target-author groups, 28 writer identifiers and 28 rater identifiers. Quality contains 150 few-shot and 90 fine-tuned exact-text pairs. Style contains 150 and 95 exact-text pairs. Across tasks there are 246 exact-text pairs and 335 exact excerpt hashes. These are structural counts; repeated texts, raters and groups are not independent works or independently verified participants.

The private identifier-only audit found all 90 fine-tuned quality target/writer groups had one exact-text pair, whereas six of 90 fine-tuned style groups had two. Preserve the source differences; do not silently normalize, fuzzily merge, or equate the 95 style pairs with 95 independent generated comparisons. The nominal paper geometry must be reconciled before freezing confirmation rows. Lay geometry, related-release row overlap, original style-reference context and a suitable frozen target partition remain open. Candidate selection and target opening are separate decisions; this audit grants neither.
