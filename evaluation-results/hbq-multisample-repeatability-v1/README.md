# Multi-sample repeatability and quality sensitivity

This study asks a narrower question than a head-to-head “best rubric” contest: across the same eleven publicly rated HANNA stories, how much does each scoring method vary when GPT-5.6 Sol High scores it five times, and how well do its within-method score ranks track the existing human ratings?

It includes HBQ-RS, the three established-rubric implementations, and the compact analytic and holistic anchors. The anchors are here because their coarse scales looked unusually stable in the earlier single-story study; this checks whether that apparent stability holds across different stories and whether it comes with useful sensitivity to the human-reference variation.

Scores stay on their own scales. The analysis reports each method separately, then compares scale-normalized within-story variation. It does not average raw totals across rubrics or treat stable scoring as proof of better literary judgment.

HBQ confidence stays diagnostic. The analysis separates raw confidence, same-input repeat behavior, and a reserved exact-fingerprint historical-prior slot. It reports stable and flipping leaves, penalties and hard gates as separate role strata, and calibration and selective-retention statistics against repeat consensus. That consensus is a proxy, not human truth. “Effective confidence mass” is never coverage, and none of these diagnostics changes canonical HBQ scores or coverage.

The sample is exactly the eleven-item repeatability slice already selected for the HANNA v3 study: one development story per source model, five repetitions per method. The full development slice fixes the quality-band cutpoints before any run begins. The primary sensitivity result is tie-aware Spearman association with HANNA’s published `human_overall`; the bands are supporting context because an eleven-story slice can leave some cells small.

Raw HANNA prose, prompts, and individual ratings stay in the external work directory. This directory contains only the protocol, runner, analyzer, and tests. To prepare an external run:

```powershell
python evaluation-results/hbq-multisample-repeatability-v1/prepare_study.py --data-dir <pinned-hanna-data> --work-dir <external-work-dir>
python evaluation-results/hbq-multisample-repeatability-v1/run_study.py --data-dir <pinned-hanna-data> --work-dir <external-work-dir> --allow-remote
python evaluation-results/hbq-multisample-repeatability-v1/analyze_study.py --data-dir <pinned-hanna-data> --work-dir <external-work-dir> --output-dir <external-analysis-dir>
```

The runner and analyzer both require the pinned HANNA data directory and re-derive the parent selection, published human ratings, full-development cutpoints, and sample bands from it before accepting any local frozen copy. The runner refuses to dispatch until its native `--allow-remote` gate is present. Immediately before every Codex dispatch it prints a machine-readable disclosure of the exact relative path, byte count, and SHA-256 of the outbound story and its originating prompt. Native arms also disclose their scoring-instruction and projected response-schema files plus the exact rendered-prompt byte count and SHA-256. The analyzer replays accepted and rejected provider artifacts, including the exact persisted gzip prompt and projected response schema for native passes. HBQ remains behind its normal runner gate; the study passes the same explicit approval through rather than bypassing it. The runner resumes only the predeclared schedule after every completed entry binds an existing final run manifest; a torn unterminated JSONL tail is safely discarded before the remaining valid committed prefix is atomically resealed. The analyzer verifies unique provider sessions when the source records attest session IDs, otherwise reports that check as unavailable while retaining a commitment over the verified artifact records. It reports undefined rank statistics as undefined rather than manufacturing a number from constant scores.
