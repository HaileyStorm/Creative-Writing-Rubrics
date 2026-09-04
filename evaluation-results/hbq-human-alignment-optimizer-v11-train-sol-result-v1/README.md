# V11 matched Sol TRAIN result

Sol measured the same eight target-free payloads as the preceding Grok screen:
four TRAIN stories, each scored with the baseline and unchanged child20 profile.
Mean absolute error fell from **1.338889 to 1.125000 (15.98%)**. Three prompt
groups improved; one worsened by 0.033333 MAE. Grok's separate result was a
32% reduction; the endpoints are not pooled.

This is a small development measurement, not a new confirmation or runtime
promotion. A fixed, non-fitted midpoint-3 predictor scores 0.763889 MAE on these
targets, better than either Sol candidate; lower paired error does not establish
strong absolute alignment or ranking quality.

[result.json](result.json) is reconstructed from all eight normal native-response
receipts by the [committed executor](../hbq-human-alignment-optimizer-v11-train-sol-exec-v1/)
at `9858561`. Eight distinct local thread/session identities were retained.
Native endpoint contact cardinality and provider model attestation remain unproven.
Baseline coverage is 23/24 dimensions and child coverage is 24/24; all numeric
scores, including the false-coverage baseline score, remain in the calculation.
Tools, web search and subagents were disabled. Human targets were not sent in
provider prompts; numeric target means are included in this public report.

The [Grok result](../hbq-human-alignment-optimizer-v11-train-grok-result-v1/)
opened this matched measurement. No candidate edits, confirmation access,
automatic selection or retries were made.
