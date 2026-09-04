# V16 Sol TRAIN aggregate

This endpoint-separated aggregate covers the same 50 stories and five selected
frozen TRAIN prompt groups as the Grok measurement. It reuses 21 historical
direct cells and adds 39 fresh lifecycle records: 29 individual-direct cells
plus 10 ten-story comparative batch cells (five groups in two opposite orders).
Each condition's task bytes were identical across endpoints.

| Readout | Direct historical | Mean of comparative orders |
| --- | ---: | ---: |
| Six-axis prompt-macro tied Spearman | 0.249094 | 0.329532 |
| Mean six-axis global tied Spearman | 0.158502 | 0.305463 |
| Mean six-axis global MAE | 0.993333 | 0.814722 |

The comparative-order macro was 0.344500 forward and 0.291517 reverse. The
direct HANNA-compatible macro dropped undefined prompt correlations: retained
prompt counts for Relevance, Coherence, Empathy, Surprise, Engagement, and
Complexity were `5/5/5/3/5/5`, so its strict all-five result is undefined. The
mean comparative arm retained all five prompts on every axis. That coverage
change must accompany the apparent lift.

Fresh execution locally resolved requested `gpt-5.6-sol` at `high` reasoning
with tools/subagents/web disabled, but provider/model/reasoning attestation is
absent. The 39 local thread/session identities are unique, but native contact
cardinality remains unproven. Independent raw-receipt replay found zero
arithmetic mismatches; it does not prove provider contact or attestation. This
remains a positive but bounded combined-method TRAIN result, not an isolated
test of batching, decimals, or token budget: comparison uses two judgements per
story and larger shared context. The direct arm is noncontemporaneous and order
remains material. This opens no DEV/confirmation, generalization, runtime,
selection, promotion, endpoint-pooling, or full-HANNA claim.

See [the compact aggregate](result.json) and [the study contract](README.md).
