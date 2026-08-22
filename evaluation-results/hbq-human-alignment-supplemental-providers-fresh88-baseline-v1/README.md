# Fresh88 baseline supplemental-provider analysis v1

This analysis-only successor compares the completed historical Grok development corpus with the separately verified Fresh88 GPT-5.6 Sol development output. It never sends a provider request and never rebrands the historical Grok v1 generation as Fresh88 generation.

`study.py` accepts only the sealed `hbq-human-alignment-v3-fresh88-analysis-v1` public schema: exactly `summary.json`, `items.jsonl`, and `manifest.json`, with the manifest binding the first two files and the primary evidence contract. It requires the separately sealed generic verifier-v2 manifest, re-verifies that manifest against the Grok raw corpus, then uses a score.

The successor requires the canonical 88 item IDs and output order, all 528 unique Grok receipt sessions, the exact Grok frozen contract and invocation, the six HANNA metric identities supplied by the primary output, and a prompt-group clustered (`560820 + 901`) bootstrap for the paired Grok-minus-Fresh88 score delta. It reports that every accepted historical Grok checkpoint has `reasoning_attested: false` with `not_reported_by_grok_build_cli`; this is provenance, not a quality adjustment. Published output remains aggregate and prose-free.

`python analyze.py --fresh88-output <primary-public-output> --grok-work <private-grok-work> --grok-verifier-manifest <sealed-grok-verifier-output> --generic-verifier-root <clean-exact-head-repository> --output-dir <empty-public-output>`

The successor refuses to run unless `analyze.py`, `study.py`, and `study-contract.json` are committed, clean, and byte-identical to `HEAD`. The generic verifier has the same requirement and was sealed with LF bytes; use a clean exact-HEAD clone for its replay when a shared checkout has unrelated source edits. This is a documented runtime selection, not a normalization of the verifier or its evidence.
