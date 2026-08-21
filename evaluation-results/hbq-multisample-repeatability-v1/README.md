# Multi-sample repeatability and quality sensitivity

This is not a “best rubric” contest. Across eleven publicly rated HANNA stories, it asks how much each method varies over five GPT-5.6 Sol High runs and how well its within-method ranks track the existing ratings.

It includes HBQ-RS, three established-rubric implementations, and compact analytic and holistic anchors. The anchors looked unusually stable in the earlier single-story study; this tests whether that holds across stories and retains useful sensitivity to reference-rating variation.

Scores stay on their own scales. The analysis reports each method separately, then compares scale-normalized within-story variation. It does not average raw totals across rubrics or treat stable scoring as proof of better literary judgment.

HBQ confidence is diagnostic. The analysis separates raw confidence, same-input repeat behavior, and a reserved exact-fingerprint historical-prior slot; it reports stable and flipping leaves, role strata, and calibration and selective-retention statistics against repeat consensus. Consensus is a proxy, not human truth. “Effective confidence mass” is never coverage, and these diagnostics do not change canonical scores or coverage.

The sample is the eleven-item repeatability slice selected for HANNA v3: one development story per source model and five repetitions per method. The full development slice fixes quality-band cutpoints before any run. The primary sensitivity result is tie-aware Spearman association with HANNA’s published `human_overall`; bands are supporting context because some eleven-story cells can be small.

Raw HANNA prose, prompts, and individual ratings stay in the external work directory. This directory contains only the protocol, runner, analyzer, and tests. To prepare an external run:

```powershell
python evaluation-results/hbq-multisample-repeatability-v1/prepare_study.py --data-dir <pinned-hanna-data> --work-dir <external-work-dir>
python evaluation-results/hbq-multisample-repeatability-v1/run_study.py --data-dir <pinned-hanna-data> --work-dir <external-work-dir> --allow-remote
python evaluation-results/hbq-multisample-repeatability-v1/analyze_study.py --data-dir <pinned-hanna-data> --work-dir <external-work-dir> --output-dir <external-analysis-dir>
```

The runner and analyzer re-derive the parent selection, published ratings, cutpoints, and bands from pinned HANNA data before accepting frozen copies. The runner needs its native `--allow-remote` gate and, before each Codex dispatch, discloses the outbound story and source prompt path, byte count, and SHA-256. Native arms also disclose scoring-instruction and projected-schema files plus rendered-prompt size and hash. The analyzer replays accepted and rejected artifacts, including persisted gzip prompts and schemas for native passes. HBQ keeps its normal runner gate. The runner resumes only the predeclared schedule after each completed entry binds a final run manifest; it discards a torn JSONL tail and atomically reseals the valid prefix. The analyzer verifies unique provider sessions when attested, otherwise records that check as unavailable and preserves commitments to the verified artifacts. Undefined rank statistics remain undefined.
