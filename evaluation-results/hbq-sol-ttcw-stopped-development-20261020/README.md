# Sol / TTCW: stopped development comparison

20 October 2026. **Inconclusive partial development evidence.** Collection stopped at an account usage limit after 328 of 1,044 planned requests were accepted. Five occupied or unadmitted requests remain excluded; 711 requests remain untouched. No missing request was replaced or retried for this report.

The cohort contains 36 AI-written stories in 12 plot groups. Existing expert references supply 14 YES/NO judgments from each of three experts per story. The reference score is the mean of those 42 judgments. Twelve linked human-written source stories were excluded. This report contains aggregate results only.

## Coverage and expert-score association

Spearman rho measures rank association with the existing expert score. Each row uses its actual available stories. **These unequal subsets cannot establish a winning method.** No story has numeric scores from all five methods.

| Method | Accepted / planned requests | Numeric stories | Spearman rho |
|---|---:|---:|---:|
| HBQ | 244 / 828 | 7 / 36 | 0.607 |
| TTCW14 | 15 / 36 | 15 / 36 | 0.401 |
| Holistic | 11 / 36 | 11 / 36 | 0.405 |
| Compact | 15 / 36 | 15 / 36 | undefined |
| Oregon | 13 / 36 | 13 / 36 | 0.037 |

HBQ has 244 accepted packets representing 11 stories: seven complete 23-packet, 178-leaf banks and four incomplete banks. The four incomplete banks are excluded from the primary scalar analysis; 29 of 36 stories therefore lack an admitted HBQ scalar result. Six accepted HBQ packets are marked with abstention. Those packet flags are not six whole-story abstentions. The other methods have zero accepted requests marked with abstention. Pairwise collection has 30 of 72 orders, representing 25 of 36 pairs; only five pairs have both orders.

HBQ scores span 39.1308–52.4280 on a 0–100 scale, with seven distinct values. TTCW14 spans 3/14–8/14, with six distinct values among 15 stories. Holistic assigns 2 to ten stories and 3 to one on its 1–7 scale. Compact assigns 2 to all 15 stories on its 1–5 scale, leaving its correlation undefined. Oregon spans 19–23 on its 6–36 scale, with four distinct values among 13 stories. None of these observed scores reaches the method's defined floor or ceiling. These small, selected subsets do not establish population-level calibration.

## Test judgments and pair orders

TTCW14 matches the existing expert majority on 136/210 observed story/test cells (64.8%); 294 of the planned 504 cells are unassessed. Against individual expert ballots it matches 393/630 (62.4%), with 882 of 1,512 unassessed. Ballots and test cells are dependent observations, not independent stories.

Pairwise choices agree with the direction derived from mean expert scores on 25/30 observed orders (83.3%). Forty-two planned orders remain missing. Among the five pairs with both orders, all five retain the same actual story preference after reversal, and four agree with the expert-score-derived direction. One completed order pair spans different native CLI versions. This is a small descriptive order diagnostic, not a causal estimate of order effects or a same-order repeatability study. The expert-derived directions are not direct human preference ballots.

## Interpretation and next work

All original coverage decisions remain `inconclusive_missing_over_10_percent`. The frozen below-33-story rule suppresses bootstrap resampling; no confidence intervals or significance claims are reported. Within-plot derived comparisons and arithmetic missingness bounds remain in the aggregate JSON; those bounds are not confidence intervals. Paired method contrasts use identical story intersections and remain too small to select a method.

Predictions and the complete request census were sealed before opening this development reference. Further collection on these stories will be development continuation, not an unused confirmation set. No rubric candidate is promoted. Expert agreement, nonexpert agreement, repeatability, other literary forms and revision usefulness remain separate requirements.

The practical next step is to retain this report, finish the untouched frozen suffix when the designated account is eligible, then run the small preselected repeatability check. The compact score collapse warrants examination on additional already-planned stories before changing its prompt or interpreting it as a general model limitation. Existing strict-import and readiness improvements can ship on their engineering evidence independently of an alignment gain.

### Remaining-request feasibility

An offline join of the frozen request manifest and sealed stopped census shows that the five occupied no-resend requests belong to four distinct HBQ story banks. Even if all 711 untouched requests succeed, at most **32 of 36 HBQ banks**, and therefore **32 all-five-method banks**, can become request-complete. The original 33-story complete-bank coverage rule cannot be reached through this suffix alone. It remains unchanged; a later development report must retain the shortfall rather than resend failed samples.

In the current ascending execution order, the first possible all-five request bank completes at ordinal 418, after 85 suffix requests. A targeted order could complete one such bank with just one untouched request. These are metadata-based planning counts, not guarantees of numeric scores or useful judgments. Execution order has not been changed, and no provider or collector was contacted. Reviewing a separately recorded completion-first order is a practical next step before eligible collection resumes.

The [aggregate feasibility record](remaining-request-feasibility.json) retains input and source commitments. Independent arithmetic review matched all request groups and 32 ascending-order milestones. The private reconstruction uses request identities and admission states only; it reads no response values, scores or human references. No original statistical result was recomputed.

### Prepared completion-first order

The [metadata-only compiler](completion_order.py) prepares a separate, unbound execution-order proposal. It sorts reachable scalar banks by the number of untouched requests needed to complete them, with stable metadata tie breaks. It then completes the remaining pair orders and retains the unfinished-bank remainders. No accepted or occupied request is included. All 711 untouched requests remain scheduled once; within-bank HBQ packet order and each pair request's frozen payload identity are preserved.

| Possible complete all-five request banks | Current ascending order: new requests | Proposed order: new requests |
|---|---:|---:|
| 1 | 85 | 1 |
| 4 | 260 | 8 |
| 8 | 403 | 42 |
| 16 | 563 | 239 |
| 32 | 711 | 654 |

The [aggregate plan summary](completion-first-summary.json) records all 32 milestones. The proposal allocates 654 requests to reachable scalar banks, 42 to remaining pair orders and 15 to incomplete-bank remainders. These counts assume every new request is accepted. Request count does not establish latency, token cost, numeric-score availability or judgment quality; early availability-selected subsets need not represent the cohort.

Reconstruct the proposal into a new **private** directory using the retained frozen inputs:

```text
python completion_order.py --manifest PATH_TO_MANIFEST216 --census PATH_TO_CENSUS290 --frontier PATH_TO_FRONTIER296 --output NEW_PRIVATE_DIRECTORY
```

The command pins all three inputs and writes a private sequence with frozen row hashes, an aggregate summary and an executed-source copy. It does not read response values, scores or human references, and does not contact a provider. The public package excludes the sequence's private request identities.

The proposal is `PREPARED_UNBOUND_NO_CONTACT`. The old collector's ascending-range selection and the old cache's prefix assumptions cannot consume this permutation unchanged: a new consumer must bind the order and track attempted and accepted request sets explicitly. Each request uses a separate native `exec`, but that does not establish backend cache or temporal equivalence. A separate execution-condition digest records the changed order without rewriting the parent scientific condition. Current account eligibility, tools-off, resource, ownership, no-resend and concurrency controls remain applicable. No live order or provider stop has changed.

Independent source and metadata review verified the complete permutation, frozen row identities, retained packet order, phase counts and all 32 milestones. It found no actionable issue. This review does not establish live eligibility, execution or scientific success.

### Explicit-ID progress adapter

`ordered_progress.py` provides provider-free `init`, `status` and `reserve` entry points for the private plan. The owning caller must serialize its run directory, reconcile other attempt roots and retain the existing endpoint reservation and provider guards. A sample reservation marks one identity occupied; it does not reserve endpoint capacity or authorize a model request.

```text
python ordered_progress.py init --plan PRIVATE_PLAN --manifest MANIFEST216 --census CENSUS290 --run-dir NEW_PRIVATE_REHEARSAL
python ordered_progress.py reserve --plan PRIVATE_PLAN --manifest MANIFEST216 --census CENSUS290 --run-dir NEW_PRIVATE_REHEARSAL
python ordered_progress.py status --plan PRIVATE_PLAN --manifest MANIFEST216 --census CENSUS290 --run-dir NEW_PRIVATE_REHEARSAL
```

The default purpose is `offline_rehearsal`. That purpose is bound into the run and attempt records; a future caller using `--purpose collector_progress` cannot reuse the rehearsal directory. Neither purpose grants provider authority. Keep rehearsals outside scientific admission and production attempt inventories.

The adapter binds the exact plan, parent manifest, census, execution condition and frozen row identities. Each journal also receives a persistent unique run ID. It creates and flushes an exclusive attempt marker before returning the selected request to its caller. An occupied directory or unfinished, missing or malformed marker cannot silently become untouched work. An unfinished attempt holds selection for reconciliation; it is never automatically resent. Progress uses explicit attempted and accepted sets rather than the greatest source ordinal.

The producer terminal must commit to the exact entry, run ID, purpose, execution condition and attempt-marker hash, as well as the saved native-result, response and admission hashes. `reserve_next()` returns that `terminal_binding` for the producer to retain. This prevents a self-consistent receipt bundle copied from another request or run from being counted under the reserved identity. Inspection does not revalidate native controls, quotations or semantic correctness.

The recorded local CLI exercise initialized a private rehearsal, marked only source ordinal 701, read it back in a fresh process and rejected a second reservation. All 710 other requests, including ordinals 334–700, remained unattempted; the 328 parent admissions and five no-resend exclusions were retained. A clearly synthetic local receipt fixture tracked a correctly bound terminal, while copying the whole self-consistent bundle to a second reserved rehearsal run was rejected. These fixtures are excluded from scientific admission. No native call, new prediction, human-reference read or shared queue/ledger mutation occurred. This establishes local selection, interruption and receipt-identity behavior. A separate private native/admission composition is now prepared and disabled; its local launch check refuses before allocating an attempt. It remains subject to account eligibility, current source review and actual reservation reconciliation before a reviewed successor can launch.

### Explicit-ID saved-result reader

The [saved-result reader](ordered_results.py) returns the 328 immutable parent record objects plus accepted continuation records identified by the bound progress journal. It never treats a high source ordinal as evidence that lower requests were attempted. Semantic rejections, unfinished attempts, stopped no-resend attempts and remaining untouched identities remain separate in its summary. Complete request-bank counts are membership diagnostics, not numeric scores or human-alignment results.

```text
python ordered_results.py --parent-cache CACHE332_MANIFEST --manifest MANIFEST216 --census CENSUS290 --plan PRIVATE_PLAN --output NEW_PRIVATE_RESULT_JSON
```

Omit `--output` to print only the local summary. The optional output contains retained research responses and operational provenance; keep it private. To read an actual continuation, add `--run-dir COLLECTOR_PROGRESS_DIRECTORY --repo CWR_CHECKOUT`. The reader does not create or reserve that directory, and it rejects an `offline_rehearsal` journal. It does not dispatch work or establish contact authority.

For each new accepted result, it checks the frozen request descriptor, producer identity, run/entry/attempt-marker binding and stored admission commitments. It replays the saved raw native receipt against the exact prompt and expected model/effort, compares the native final with the admitted response, and rejects reused native thread/turn identities. The existing semantic validator is not rerun. The parent records retain their original qualification limits; the changed execution condition stays separate from the parent scientific condition. The owning caller still reconciles other attempt roots and serializes reads with its producer.

The actual parent-only CLI returned all 328 records unchanged, five occupied no-resend identities and 711 untouched requests. Request-complete banks remained HBQ 7, TTCW14 15, holistic 11, compact 15 and Oregon 13, with no all-five shared bank. A second CLI call rejected the retained offline rehearsal. No new native receipt, prediction, score or human-reference value was produced. The future accepted-continuation branch has source review, but no runtime proof using a real continuation result yet. Subsequent numeric-profile and analysis consumers must use the returned explicit identities rather than the historical cutoff scripts.

## Provenance and limits

Collection requested `gpt-6.1-sol` at high with every collection-model tool disabled. Saved execution receipts and local tool-catalog evidence support the observed route and zero tool activity; they do not establish full backend, auxiliary-path or production-wire attestation. Cached records lacking native CLI version fields remain unknown. The independent review reproduced associations and paired deltas from saved intersections; it did not independently revalidate ordinal 1's historical join because that record lacks an embedded condition descriptor.

This report reuses saved admitted outputs and scalar profiles: no provider request, canonical rescoring, semantic replay, new human label or judge training was performed. Independent agent review is not human validation. Raw stories, labels, assessor identities, account details and local operations logs are excluded.

Story-source pin: Salesforce/ttcw_creativity_eval at `278745280a0bfebf4151bfa687add38ba2c98d61`, CSV SHA-256 `28cf816670e73c82d3580c1e59edabcf872c60328727b007068429e22f0acbcb`. Expert annotations: [Salesforce creativity_eval, Art_or_Artifice](https://github.com/salesforce/creativity_eval/tree/3d029879df6878f611363db88cc02d465699bc51/Art_or_Artifice), `annotations/ttcw_annotations.json`, Git blob `502de8d779d7fb38b8df569e64c2a6d0d4ae6e51`. Source restrictions continue to apply; no underlying text or raw label redistribution is implied.

`aggregates.json` is a deterministic projection of the immutable local analysis and coverage addendum. Its source SHA-256 commitments identify those retained private inputs. The underlying private records are required to independently reproduce source joins and the original statistics; this aggregate-only package does not claim to provide those records.
