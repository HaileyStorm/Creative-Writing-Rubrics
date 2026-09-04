# V16 Grok TRAIN aggregate

This endpoint-separated aggregate covers 50 stories in five selected frozen
TRAIN prompt groups. It reuses 21 historical direct cells and adds 39 fresh
lifecycle records: 29 individual-direct cells plus 10 ten-story comparative
batch cells (five groups in two opposite orders). Each condition's task bytes
were identical across endpoints.

| Readout | Direct historical | Mean of comparative orders |
| --- | ---: | ---: |
| Six-axis prompt-macro tied Spearman | 0.205269 | 0.337593 |
| Mean six-axis global tied Spearman | 0.172452 | 0.336687 |
| Mean six-axis global MAE | 1.121111 | 0.765333 |

The comparative-order macro was 0.353701 forward and 0.257558 reverse. The
direct HANNA-compatible macro dropped undefined prompt correlations: retained
prompt counts for Relevance, Coherence, Empathy, Surprise, Engagement, and
Complexity were `5/5/5/1/4/5`, so its strict all-five result is undefined. The
mean comparative arm retained all five prompts on every axis. That coverage
change must accompany the apparent lift.

Fresh execution requested xAI `grok-4.6`, reported `grok-4.6-build`, disabled
tools/subagents/web, and requested `high` reasoning without attestation. The 39
request/session identities are unique, but native contact cardinality remains
unproven. Independent raw-receipt replay found zero arithmetic mismatches; it
does not prove provider contact or attestation. This remains a positive but
bounded combined-method TRAIN result, not an isolated test of batching,
decimals, or token budget: comparison uses two judgements per story and larger
shared context. The direct arm is noncontemporaneous and order remains
material. This opens no DEV/confirmation, generalization, runtime, selection,
promotion, endpoint-pooling, or full-HANNA claim.

See [the compact aggregate](result.json) and [the study contract](README.md).
