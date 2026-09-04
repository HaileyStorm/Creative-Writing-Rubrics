# WritingPreferenceBench pairwise pilot v1

This is a provider-free, immutable source-freeze for a small broader human-preference pilot. It does not claim HANNA equivalence or a CWR improvement.

It pins the public English WritingPreferenceBench source at commit `c6ac5821582e77fb34d27f6b54aac937904ee112`: 1,200 pairs across 51 categories, under the source's documented ODC-BY terms. The pinned README and English JSON hashes are in [experiment-contract.json](experiment-contract.json).

`source.py freeze` verifies the exact source, joins rows sharing a prompt ID, exact prompt, or exact response, discards every cross-category component, then selects three rows per category from distinct components. Its selection keys never use chosen/rejected order, source scores, or source-model identity. Whole categories are deterministically assigned 35 TRAIN / 8 DEV / 8 confirmation.

The output is a fresh local descendant containing provenance and selection hashes, endpoint-neutral A/B/TIE payloads, separately stored local targets, and a TRAIN+DEV default schedule. A/B order is response-hash order. Grok is the primary development endpoint and Sol is a separate validation endpoint; each endpoint must receive identical frozen task bytes for any cell it judges. Confirmation is selected and committed locally but has no opening API or CLI here. A later real pairwise analyzer/profile-decision package must define that separate, bound transition.

Primary analysis is pairwise accuracy with win/tie/loss accounting, macro-averaged across categories. The 0–3 construction scores are targets, not a distance scale: no MAE is valid here. Any family weighting is TRAIN-only and DEV-selected; confirmation stays closed in this package. This package has no provider runner, runtime selection, promotion, endpoint pooling, or confirmation-opening surface.
