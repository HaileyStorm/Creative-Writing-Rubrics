# V17 native endpoint execution

This package is the provider-capable counterpart to the frozen V17 TRAIN-only
replication source.  It prepares 48 fresh calls per endpoint (38 individual
direct and 10 two-order ten-story comparative batches), then independently
admits those receipts before combining them with 12 exact V15 historical direct
measurements from the same endpoint.  It never pools Grok and Sol.

V17 source is pinned to commit `3715be8` and SHA-256
`3e0dee255b2631249c76fcc70baf99c5842be17550baafbe18e270ac9d52a827`.
The lower native lifecycle is pinned to V16 executor commit `3c1bec6` and
SHA-256 `554c6ab1e70a74a89c9b7cefab7c15ea66146a44aea7a8d38293ae6c2d4956db`.
Both are checked against their live Git blobs before use.

`prepare_all` is provider-free and writes one immutable prepared root per
endpoint.  It requires an acknowledgement and validated current route proof,
but reports zero provider calls and process launches.  `execute_one` and
`execute_wave` require explicit `allow_remote=True`; the inherited reviewed
lifecycle keeps tools, web, and subagents disabled, gates current route
evidence, limits concurrency to ten, and makes post-contact ambiguity terminal
rather than automatically resending a cell.

`report` rederives the V17 schedule from frozen inputs, re-admits all fresh
native receipts and the selected V15 receipt evidence, checks endpoint and
receipt identities, and supplies cell/payload/endpoint provenance to the V17
analyzer.  It does not prove native endpoint contact cardinality, provider
attestation, generalization, confirmation, selection, promotion, runtime use,
or any public-performance claim.  Grok remains the primary development route;
Sol uses identical frozen payload bytes as an independent endpoint check.

## Grok execution is incomplete

The [Grok settlement](grok-incomplete.json) retains 23 response-backed cells
(22 direct and one forward comparison) and 25 terminal provider-attempt
failures. Independent native re-admission verified all 23 successes and the
exact 48-cell inventory; no cells are unsettled. Native logs reported HTTP 402
usage-balance exhaustion during the wave. Individual terminal records retain
only the exception type, so they do not independently preserve each underlying
provider error message or prove endpoint-contact cardinality.

The route was revoked and no failed cell was resent. This incomplete,
non-random subset is ineligible for metrics or cross-endpoint performance
comparison. The complete Sol run below is a separate TRAIN diagnostic;
it cannot establish Grok performance from this partial execution.

## Standalone Sol TRAIN result

The [complete Sol aggregate](sol-result.json) includes all 48 fresh cells plus
12 pinned V15 direct measurements: 50 stories in five additional TRAIN prompt
groups. Independent raw-score arithmetic and receipt commitments match the
native report with zero mismatches.

| Condition | Prompt-macro Spearman | Mean six-axis MAE | Full five-group coverage |
| --- | ---: | ---: | --- |
| Historical/noncontemporaneous direct | 0.417514 | 0.814444 | No: Surprise retains 3/5 |
| Comparative forward | 0.407013 | 0.809222 | Yes |
| Comparative reverse | 0.410504 | 0.804667 | Yes |
| Per-story mean of both orders (primary) | 0.423961 | 0.784167 | Yes |

The primary correlation is defined on all five groups for all six axes.
The direct arm's strict-five macro is undefined, so its descriptive macro
cannot establish a clean comparative-method gain. The mean-order method uses
two judgments and larger shared context; direct receipts are partly historical.
This small development panel does not establish full-HANNA competitiveness,
canonical full-HBQ quality, confirmation, generalization, or runtime promotion.
Grok's incomplete run supplies no endpoint performance comparison. Local Sol
identities are distinct, but provider/model/reasoning attestation and native
endpoint-contact cardinality remain unproven.
