# Comparative HANNA judging on complete TRAIN groups

V15 found weak ranking with isolated integer scores and cumulative thresholds.
This experiment tests whether seeing comparable stories together, with decimal
scores, helps distinguish their qualities. It tests that combined method—not
the isolated effect of batching or decimals—and does not change CWR defaults.

The panel completes the five best-covered existing TRAIN prompt groups to all
ten original generated systems each. Selection uses item counts and hash order,
not human scores or model performance. Human-reference stories are excluded.

- **Individual arm:** 21 exact V15 judgments reused, plus 29 new judgments. The
  reused portion is historical, not a contemporaneous randomized control.
- **Comparative arm:** each ten-story group appears in two opposite orders.
  Average each story's two scores; never choose the more favorable order.
  This supplies two judgments per story and larger shared context, so any gain
  is not an equal-token-budget or batching-only claim.
- **Cost:** 39 new calls per endpoint. The first batch is a counted validity
  check; a malformed result blocks the remaining batches without automatic retry.
- **Endpoints:** Grok and Sol receive identical task payloads and remain separate.
  Human targets stay local. No DEV or confirmation examples are opened.

The [original HANNA analysis](https://github.com/dig-team/hanna-benchmark-asg/blob/coling/data_visualization.ipynb)
correlates ten systems within each prompt, then averages prompt correlations,
omitting undefined values. We report that calculation with retained/dropped
prompt counts, plus a strict all-five-prompts result. Constant scores are
undefined correlations, not zero or successful alignment. Global story-level
correlations, MAE, ties, and both order-specific results provide context.

Five development groups match the original estimator's structure, not the full
96-prompt benchmark. This package alone establishes no competitive alignment,
held-out gain, or runtime promotion. The schedule and arithmetic can run without
providers; native results require the separate executor and receipt checks.
