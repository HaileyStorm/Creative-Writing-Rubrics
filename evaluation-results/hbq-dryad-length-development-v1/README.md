# Dryad development: a simple length baseline

This retrospective diagnostic compares saved HBQ scores with a simple text-length baseline on the same 30 previously opened Dryad development stories. The reference is the original study's pooled evaluator means for well-written and enjoyed; these are separate outcomes. Length is the number of Unicode code points after UTF-8 decoding, without normalization. All 30 lengths are distinct. HBQ scores and lengths have Spearman rho −0.060.

| Existing human reference | HBQ rho | Length rho | HBQ minus length | Conditional 95% paired interval |
|---|---:|---:|---:|---|
| Well-written | 0.342 | 0.196 | 0.146 | −0.451 to 0.744 |
| Enjoyed | 0.377 | 0.328 | 0.049 | −0.482 to 0.578 |

The point comparison was declared before examining these lengths, after the original HBQ results had been observed. The paired story-bootstrap sensitivity was chosen after the point results. It uses 2,000 resamples, seed 20261114, average tied ranks and linearly interpolated percentile endpoints; both methods and outcomes use the same story indices. All draws were defined. An independent calculation reproduced the interval endpoints.

The intervals condition on this selected panel and its observed pooled means. They omit shared evaluator, topic and selection uncertainty, and do not establish a method winner, equivalence, causation or population performance. The original reduction followed partial model observation. The historical scores do not establish equivalence to current collection settings. No new human labels or provider calls were made; confirmation material stayed closed. Neither these findings nor the [prior HBQ analysis](../hbq-dryad-sol-dev30-development-20261023/README.md) promotes a candidate or completes the research program.

## Reproduction

The source panel, source manifest and story files remain private. `regenerate.py` requires their exact pinned bytes, matches the 30 stories, verifies each file's digest and byte count, and reproduces the published HBQ correlations before calculating the length comparison and bootstrap. The pinned historical correlation implementation and aggregate live in the adjacent published HBQ analysis. No individual texts, ratings, identifiers or resampled values enter `aggregate.json`.

```text
python regenerate.py --panel PRIVATE_PANEL --manifest PRIVATE_MANIFEST --story-root PRIVATE_STORY_ROOT --output NEW_AGGREGATE_JSON
```

The output path must not already exist. `aggregate.json` is the aggregate result of this reproduction; input commitments are recorded inside it. This comparison is an exploratory development diagnostic, not an independent confirmation set or a human ceiling.
