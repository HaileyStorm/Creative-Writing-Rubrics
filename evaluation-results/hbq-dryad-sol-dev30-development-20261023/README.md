# Historical Sol / Dryad: 30-story baseline association

23 October 2026. **Retrospective development evidence.** This separate descendant uses saved canonical HBQ scores for the 30 DEV stories in the existing selected-100 Sol collection. It makes no new model request, fits no candidate and leaves the original Grok-dependent comparison and coverage gates unchanged.

All 30 scheduled DEV stories are present, with coverage from 0.9025 to 0.9819. Their scores span 23.7457–90.1097 on the captured scorer's 0–100 scale: 30 distinct values, no ties, no exact floor or ceiling, and one score at or above 90. The mean is 50.5246. This distribution describes the selected sample rather than population calibration.

The reference is the existing study's pooled blinded evaluator ratings. The 30 stories contribute 362 rating rows, with 10–13 per story. Those are rating events, not 362 independent people. This packet does not retain evaluator identities, so shared-evaluator uncertainty cannot be reconstructed here.

## Associations and conditional uncertainty

The new descendant declares `well_written` and `enjoyed` as its two primary axes before calculating these associations. The original study's novelty/usefulness co-primary targets remain unchanged. All axes retain their original 1–9 orientation; no twelve-axis composite is created.

| Human reference axis | Spearman rho | Pointwise conditional 95% story-bootstrap interval |
|---|---:|---|
| Well-written | 0.342 | −0.049 to 0.652 |
| Enjoyed | 0.377 | 0.003 to 0.669 |

Each interval uses 2,000 paired story resamples, seed 20261023, average tied ranks and linear percentile quantiles. Both axes use the same resampled story indices. All saved draws were defined; undefined draws would be retained and prevent interval reporting. An independent review reproduced the joins, all 12 point estimates, distribution hashes and interval endpoints without regenerating resamples.

The intervals condition on the selected stories and their observed pooled human means. They omit shared evaluators, topic/experimental-condition clustering, the subset-selection process and multiplicity correction. Enjoyment's barely positive lower endpoint is **not a corrected population-significance result**. Neither estimate establishes a human ceiling or a rubric improvement.

| Other original axes, exploratory | Spearman rho |
|---|---:|
| Novel | 0.441 |
| Original | 0.408 |
| Rare | 0.398 |
| Appropriate | 0.263 |
| Feasible | 0.278 |
| Publishable | 0.267 |
| Boring | −0.330 |
| Funny | 0.257 |
| Twist | 0.411 |
| Future | 0.338 |

`boring` retains its negative orientation. Humor, twist and future expectations are not universal measures of quality. The source audit does not supply full questionnaire wording; its documented well-written correction is retained without reversing that axis. See the [source audit](../hbq-human-alignment-dryad-source-audit-v1/README.md) and [human-agreement limitations](../hbq-human-agreement-story-bootstrap-v1/README.md).

## Original study and historical limits

The [selected-100 collection](../hbq-human-alignment-dryad-full-hbq-analysis-v1/README.md) retains 2,300 logical requests, 17,800 verdicts and 2,300 distinct local thread identities. Two TRAIN stories remain below the original 0.88 coverage floor, at 0.8607 and 0.8648. They are preserved as failures. Full-study admission remains false. Twenty-six unknown-exit commitments do not prove successful process exits or account-wide quiescence.

The reduction to 100 stories followed partial model observation. The selected 30 are descriptive development data. The new primary focus and Sol-only analysis are separate from the original Grok TRAIN selection and DEV comparison. No original gate, historical receipt or confirmation partition was rewritten. All 57 confirmation stories remain closed.

This analysis consumes the September replay's stored scores without rerunning native admission, semantic validation or canonical scoring. It does not qualify historical account, model, tool or sampler settings as equivalent to the contemporary tools-disabled Sol collection. Results must remain separate from current TTCW results. No matched comparator, causal improvement, candidate promotion, prospective confirmation or complete research-program claim follows.

## Reproduction

`analysis-profile.json` records the declared method, original pre-association profile/source commitments and input hashes. The portable consumer was constructed after the first calculation from its unchanged arithmetic. It reproduces `aggregates.json` from retained private inputs, without stories, raw ballots, work IDs, native identities or account details in its output:

```text
python analysis.py --replay SAVED_SELECTED100_REPLAY --schedule SELECTED100_SCHEDULE --targets PREPARED_DEV_TARGETS --target-provenance TARGET_PROVENANCE --profile analysis-profile.json --output NEW_AGGREGATE_JSON
```

The full prepared DEV packet contains 60 story-mean rows and was decoded; only the 30 exact opaque-ID matches enter this analysis. TRAIN targets and confirmation data are not inputs. Private panels and bootstrap draws remain local. The original frozen private profile hash is `0559fd0b537cdfbbfe18f1fd662557808b3e02cba1c6425f61b3bb94e7944a7d`; original result hash is `8fafae2020f06453f33dbdf01ebcb5c26fdf589113cba11efd069778aa3c272c`. The public projection labels their source/profile commitments explicitly as frozen provenance.
