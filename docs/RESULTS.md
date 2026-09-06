# Results and evidence

This page is the short public map of what HBQ-RS has established, falsified,
and left open. Results are scoped to their named artifacts, rubric version,
prompt, batch geometry, and evidence boundary. `Positive` means a declared
product test succeeded; `Negative` means a proposed claim or treatment failed;
`Bounded` means the result is useful but does not support a broader promotion.

## Headline findings

| Finding | Status | Public result | What it supports |
| --- | --- | --- | --- |
| Direct HANNA anchors and ordinal thresholds still show weak rank alignment. | **Negative / bounded** | [V15 Grok TRAIN](https://github.com/HaileyStorm/Creative-Writing-Rubrics/blob/b4ba4c5d2963040ffc6f26010de089e21331a0b4/evaluation-results/hbq-human-alignment-optimizer-v15-rank-discrimination-v1/GROK_TRAIN.md) and [matched Sol](https://github.com/HaileyStorm/Creative-Writing-Rubrics/blob/b4ba4c5d2963040ffc6f26010de089e21331a0b4/evaluation-results/hbq-human-alignment-optimizer-v15-rank-discrimination-v1/SOL_TRAIN.md) | Across 48 TRAIN stories / 24 unequal prompt groups / 96 cells per endpoint, mean item-level Spearman changed from `0.203` to `0.173` on Grok and `0.167` to `0.264` on Sol. Thresholds helped Sol but not Grok; all four MAEs were worse than fixed-three. This is a reference-free development experiment, not the original HANNA per-prompt estimator or a full-CWR result. |
| The completed 330-cell multisample panel is repeatable but does not validate HBQ human alignment. | **Negative / bounded** | [Multisample aggregate](https://github.com/HaileyStorm/Creative-Writing-Rubrics/tree/b4ba4c5d2963040ffc6f26010de089e21331a0b4/evaluation-results/hbq-multisample-repeatability-v1-completed-result-v1) | Across 11 stories / 10 prompt clusters / five repetitions, HBQ's descriptive pooled rho was `-0.041`; NAPLAN and Cambridge were about `0.626` and `0.629`. HBQ combines six original-version and five later-version stories, without mixing versions within a story. Cohort differences are not version effects; repeatability is not quality. |
| HBQ-RS repeated consistently on the complete, authorized *The Part That Arrives First*, while retaining more headroom than the comparison rubrics. | **Positive** | [Established-rubric repeatability v4](https://github.com/HaileyStorm/Creative-Writing-Rubrics/tree/b4ba4c5d2963040ffc6f26010de089e21331a0b4/evaluation-results/the-part-that-arrives-first-repeatability/established-v4) | On one story across five HBQ runs, the score averaged `90.6764`; 162/178 leaves agreed in all five runs. NAPLAN and Oregon implementations were perfectly repeatable but ceiling-bound. |
| The tuned child20 HANNA prompt improved on untouched Fresh96 confirmation for both Grok and Sol. | **Bounded** | [Paired confirmation](#fresh96-confirmation-the-retained-smaller-edit-holds-on-sol) | Across 32 items / 16 prompt groups, MAE fell `28.65%` on Grok and `17.95%` on Sol, measured separately with identical frozen payloads. This supports the opt-in development profile, not automatic runtime promotion or general literary validity. |
| The unchanged child20 prompt reduced development MAE on both Grok and Sol, but did not beat a constant-3 diagnostic. | **Bounded** | [V12 Grok](https://github.com/HaileyStorm/Creative-Writing-Rubrics/tree/b4ba4c5d2963040ffc6f26010de089e21331a0b4/evaluation-results/hbq-human-alignment-optimizer-v12-development-grok-result-v1) and [matched Sol](https://github.com/HaileyStorm/Creative-Writing-Rubrics/tree/b4ba4c5d2963040ffc6f26010de089e21331a0b4/evaluation-results/hbq-human-alignment-optimizer-v12-development-sol-result-v1) | Across 13 development items / 7 groups / 26 cells per endpoint, paired equal-group MAE fell `31.87%` on Grok and `15.62%` on Sol. Sol improved six groups but only 2/6 item-level rank correlations. These are fresh calls on an existing development split, not new confirmation or general ranking success. |
| The unchanged child20 prompt again reduced Grok TRAIN error, but remained worse than a fixed-3 diagnostic and did not improve descriptive ranking. | **Bounded** | [V13 remaining TRAIN expansion](https://github.com/HaileyStorm/Creative-Writing-Rubrics/tree/b4ba4c5d2963040ffc6f26010de089e21331a0b4/evaluation-results/hbq-human-alignment-optimizer-v13-train-expansion-result-v1) | Across 44 remaining TRAIN items / 22 unequal groups / 88 cells, equal-group MAE fell `27.62%` (19 wins, 3 losses). Fixed-3 MAE was lower by `0.114899`; child20 improved only 2/6 item correlations and declined on all 6 group-mean correlations. This is development evidence, not confirmation, a Sol result, promotion, or general ranking success. |
| Optuna calibration reduced TRAIN cross-validation error, but did not broadly improve ranking. | **Bounded** | [V13 calibration](https://github.com/HaileyStorm/Creative-Writing-Rubrics/blob/b4ba4c5d2963040ffc6f26010de089e21331a0b4/evaluation-results/hbq-human-alignment-optimizer-v13-train-expansion-v1/CALIBRATION.md) and [aggregate](https://github.com/HaileyStorm/Creative-Writing-Rubrics/blob/b4ba4c5d2963040ffc6f26010de089e21331a0b4/evaluation-results/hbq-human-alignment-optimizer-v13-train-expansion-v1/calibration-result.json) | On 44 stories / 22 held-out prompt groups, MAE fell `15.98%` and was `3.54%` below fixed-3. Only 2/6 rank correlations improved. This used existing Grok scores with no new model calls; it is calibration research, not a validated new prompt or runtime profile. |
| One independently verified DSPy descendant changed only the instruction and moved the four-item TRAIN pilot, with endpoint-separated results and a larger Sol movement than Grok. | **Bounded** | [V14 DSPy TRAIN pilot](https://github.com/HaileyStorm/Creative-Writing-Rubrics/tree/b4ba4c5d2963040ffc6f26010de089e21331a0b4/evaluation-results/hbq-human-alignment-optimizer-v14-dspy-train-pilot-result-v1) | On the same 4 items / 4 groups / 8 cells per endpoint, Grok MAE moved `0.625` to `0.611111` (`2.22%`; 1 win, 2 ties, 1 loss), while Sol moved `1.163889` to `1.070139` (`8.05%`; 3 wins, 0 ties, 1 loss). The prior V11 child20 value was `0.708333`, a `0.083333` control-run shift. No ranking statistic was measured; this remains in-sample development evidence without confirmation, generalization, selection, promotion, runtime, or pooling authority. |
| The DSPy instruction reduced broader TRAIN error on both Grok and Sol. | **Bounded** | [V14 DSPy TRAIN expansion](https://github.com/HaileyStorm/Creative-Writing-Rubrics/tree/b4ba4c5d2963040ffc6f26010de089e21331a0b4/evaluation-results/hbq-human-alignment-optimizer-v14-dspy-train-expansion-result-v1) | Across 44 additional stories / 22 groups / 88 cells per endpoint, MAE fell a further `14.90%` on Grok and `12.41%` on Sol. Grok's new prompt beat fixed-3; Sol's did not. Ranking was mixed. These matched TRAIN measurements do not establish confirmation or general literary validity. |
| The DSPy instruction reduced error on a separate V12 development panel at both endpoints, but calibration and rank limits remain. | **Bounded** | [V14 DSPy development checkpoint](https://github.com/HaileyStorm/Creative-Writing-Rubrics/blob/b4ba4c5d2963040ffc6f26010de089e21331a0b4/evaluation-results/hbq-human-alignment-optimizer-v14-dspy-train-pilot-v1/DEVELOPMENT.md) | Across 13 development items / 7 groups / 26 cells per endpoint, Grok MAE moved `0.964286` to `0.763889` (`20.78%`; 5 wins, 2 losses) and Sol moved `1.190873` to `0.960714` (`19.33%`; 7 wins). Fixed-3 was `0.765873`: near the Grok DSPy result and better than both Sol candidates. Grok rank was higher in 2/6 dimensions; Sol was higher in 5/6 items and 4/6 groups. Coverage and endpoints remain separate; this is not confirmation or general ranking evidence. |
| CWR-guided revision showed a small held-back benefit over generic revision. | **Bounded** | [Four-item revision result](https://github.com/HaileyStorm/Creative-Writing-Rubrics/tree/b4ba4c5d2963040ffc6f26010de089e21331a0b4/evaluation-results/cwr-guided-revision-gain-v6-heldout-result-v1) | Guided-minus-generic means: Sol `+1.00` holistic / `+0.75` compact; Grok `+0.75` / `0.00`. Four items are encouraging, not broad effectiveness or judge-interchangeability evidence. |
| The original full-rubric Fresh88 generated-only HANNA comparison did not establish alignment. | **Negative** | [Primary reconstruction](https://github.com/HaileyStorm/Creative-Writing-Rubrics/tree/b4ba4c5d2963040ffc6f26010de089e21331a0b4/evaluation-results/hbq-human-alignment-v3-fresh88-analysis-v1) and [overlap views](https://github.com/HaileyStorm/Creative-Writing-Rubrics/tree/b4ba4c5d2963040ffc6f26010de089e21331a0b4/evaluation-results/hbq-human-alignment-v3-fresh88-overlap-analysis-v1) | Across 80 generated stories, the six-dimension macro Spearman was `-0.036142466350769044`; several dimensions were negative, including Surprise at `-0.2427665637523263`. Later prompt-level MAE gains do not retroactively validate this result. |
| Mapped-HBQ calibration did not demonstrate feature value beyond learned TRAIN target priors. | **Negative** | [Development calibration](https://github.com/HaileyStorm/Creative-Writing-Rubrics/blob/b4ba4c5d2963040ffc6f26010de089e21331a0b4/evaluation-results/hbq-human-alignment-v3-fresh88-analysis-v1/DEVELOPMENT_CALIBRATION.md) | Across 48 TRAIN items / 24 leave-one-group-out folds, ridge mapped-score MAE was `0.620607`, but a post-hoc no-feature prior reached `0.544950`. The prior is not a frozen arm or selector, yet it blocks a feature-value claim. This provider-free diagnostic changes no rubric weight, canonical score, runtime, promotion, or confirmation access. |
| A DSPy descendant improved the Grok development objective but reversed on the unchanged Sol check. | **Negative** | [Balanced held-out evaluation](https://github.com/HaileyStorm/Creative-Writing-Rubrics/tree/b4ba4c5d2963040ffc6f26010de089e21331a0b4/evaluation-results/hbq-human-alignment-optimizer-v4-balanced-dspy-heldout-eval-v1) and [executor](https://github.com/HaileyStorm/Creative-Writing-Rubrics/tree/b4ba4c5d2963040ffc6f26010de089e21331a0b4/evaluation-results/hbq-human-alignment-optimizer-v4-balanced-dspy-heldout-exec-v1) | `candidate-0ca942ad28cb4104` reduced Grok MAE from `1.069444` to `0.875` across four disjoint development groups, then increased Sol MAE from `1.368056` to `1.427778` across two matched groups. This is model-specific development improvement, not cross-endpoint gain. |
| QPC1's isolated figurative leaves passed everything and distinguished nothing. | **Negative** | [QPC1 aggregate](https://github.com/HaileyStorm/Creative-Writing-Rubrics/tree/b4ba4c5d2963040ffc6f26010de089e21331a0b4/evaluation-results/hbq-qpc1-figurative-treatment-v1) | 105/105 accepted verdicts were `YES`; the result blocked a split, reweight, or new density owner. |
| Full-rubric QPC24 separated the public control strongly but found only limited stable separation between the private drafts. | **Bounded** | [QPC24 V5 aggregate](https://github.com/HaileyStorm/Creative-Writing-Rubrics/tree/b4ba4c5d2963040ffc6f26010de089e21331a0b4/evaluation-results/hbq-qpc24-two-pass-product-confirmation-v5-public-result-v1) | Six complete 221-leaf passes; four differing leaves among 189 leaves stable in both author-original and GPT-5.6 Pro rewrite repetitions. |
| Four small wording repairs survived development, disjoint confirmation, and review without changing ownership or influence. | **Positive** | [Validation and repair journey](VALIDATION_AND_REPAIR_JOURNEY.md#repair-became-a-portfolio-not-a-reflex) | Recurrence/applicability, explicit excerpt scope, figurative semantic hinges, and material-context line breaks changed; IDs, owners, weights, and bundle influence did not. |
| The current *Gray Blood* work-in-progress manuscript rebaseline completed at full declared fidelity. | **Bounded** | [QPC24 V9 full-book aggregate](https://github.com/HaileyStorm/Creative-Writing-Rubrics/tree/b4ba4c5d2963040ffc6f26010de089e21331a0b4/evaluation-results/hbq-gray-blood-full-book-qpc24-rebaseline-v9-public-result-v1) | HBQ-RS `1.2.1`, CWR runtime `1.2.3`, 150/150 binary calls, 3,406 positions, no sampling, and no rubric promotion. The GPT-5.6 Pro rewrite scored `+10.2167` above the author-original under this protocol; bounds are non-statistical, with 8 units / 1,817 positions versus 7 / 1,589. |

## Current development checkpoints — descriptive readouts, no promotion

Latest: [V17 standalone Sol replication](#v17-standalone-sol-replication)
is complete; its paired Grok run is incomplete after quota exhaustion. The
later [WPB collection](#wpb-terminal-collection) stopped with 89 successful,
one ambiguous terminal, and 39 unstarted cells; it permits no subset metrics
or automatic resend. [Dryad preparation](#dryad-source-and-full-hbq-preparation)
is implemented. Its first live qualification attempt stopped after six contacts:
five accepted checkpoints and one semantically rejected response. It yields no
batch cap or alignment result and permits no automatic resend.

The [full-tree family-weight diagnostic](https://github.com/HaileyStorm/Creative-Writing-Rubrics/tree/b4ba4c5d2963040ffc6f26010de089e21331a0b4/evaluation-results/hbq-human-alignment-family-weighting-v1)
completed 3,072 provider-free Optuna trials over 48 TRAIN stories across 24
leave-one-prompt-group-out TRAIN folds. Fitted pooled Spearman remained negative (`-0.105024` to
`-0.092254`) and equal-group MAE worsened (`0.973766` to `0.991439`). Independent
reconstruction matched every out-of-fold score. This compares the rescaled
final HBQ score against the mean human rating; it does not support new runtime
weights or competitive human alignment.

These packages preserve the next questions, gates, and bounded descriptive
readouts. None authorize a rubric, model, or runtime promotion.

- [HANNA optimizer v3](https://github.com/HaileyStorm/Creative-Writing-Rubrics/tree/b4ba4c5d2963040ffc6f26010de089e21331a0b4/evaluation-results/hbq-human-alignment-optimizer-v3), [native-subscription v4](https://github.com/HaileyStorm/Creative-Writing-Rubrics/tree/b4ba4c5d2963040ffc6f26010de089e21331a0b4/evaluation-results/hbq-human-alignment-optimizer-v4-native-subscription-v1), [native execution v4](https://github.com/HaileyStorm/Creative-Writing-Rubrics/tree/b4ba4c5d2963040ffc6f26010de089e21331a0b4/evaluation-results/hbq-human-alignment-optimizer-v4-native-subscription-exec-v1), [native admission v4](https://github.com/HaileyStorm/Creative-Writing-Rubrics/tree/b4ba4c5d2963040ffc6f26010de089e21331a0b4/evaluation-results/hbq-human-alignment-optimizer-v4-native-admission-v1), the [lean development pilot](https://github.com/HaileyStorm/Creative-Writing-Rubrics/tree/b4ba4c5d2963040ffc6f26010de089e21331a0b4/evaluation-results/hbq-human-alignment-optimizer-v4-lean-development-v1), and the [33-pair Grok/Sol readout](https://github.com/HaileyStorm/Creative-Writing-Rubrics/tree/b4ba4c5d2963040ffc6f26010de089e21331a0b4/evaluation-results/hbq-human-alignment-optimizer-v4-grok-sol-readout-v1): all 65 Grok development cells completed with verified native envelopes and provider-free admissions. The original Sol schedule settled at 33 successful local lifecycles plus two immutable terminal exclusions; two versioned same-group descendants then completed without resend. Sol evidence remains `local_lifecycle_verified_native_endpoint_contact_cardinality_unproven`. Across 33 matched frozen pairs, the descriptive mean absolute difference is `0.4392` over `172` covered pair-by-dimension observations; this is not agreement, interchangeability, provider ranking, alignment, selection, generalization, confirmation, or revision-gain evidence. Real Optuna `4.9.0` search and DSPy `3.3.1` descendant generation have run development-only over independently verified persisted evidence. The later [balanced held-out evaluation](https://github.com/HaileyStorm/Creative-Writing-Rubrics/tree/b4ba4c5d2963040ffc6f26010de089e21331a0b4/evaluation-results/hbq-human-alignment-optimizer-v4-balanced-dspy-heldout-eval-v1) completed 44 Grok cells across four prompt-group-disjoint development groups and 22 unchanged-candidate Sol cells across two matched groups. Its Grok-selected descendant improved Grok MAE but reversed on Sol. Subsequent [three-group development](https://github.com/HaileyStorm/Creative-Writing-Rubrics/tree/b4ba4c5d2963040ffc6f26010de089e21331a0b4/evaluation-results/hbq-human-alignment-optimizer-v5-f20-nextwave-grok-score-result-v1), [broader development](https://github.com/HaileyStorm/Creative-Writing-Rubrics/tree/b4ba4c5d2963040ffc6f26010de089e21331a0b4/evaluation-results/hbq-human-alignment-optimizer-v5-f20-broader-development-grok-result-v2-v3-exec), and frozen [confirmation](https://github.com/HaileyStorm/Creative-Writing-Rubrics/tree/b4ba4c5d2963040ffc6f26010de089e21331a0b4/evaluation-results/hbq-human-alignment-optimizer-v5-f20-confirmation-freeze-v1) produced endpoint-separate improvement readouts; the [Grok confirmation replay](https://github.com/HaileyStorm/Creative-Writing-Rubrics/tree/b4ba4c5d2963040ffc6f26010de089e21331a0b4/evaluation-results/hbq-human-alignment-optimizer-v5-f20-confirmation-grok-replay-v2-native-json-normalization) and [Sol final-message recovery](https://github.com/HaileyStorm/Creative-Writing-Rubrics/tree/b4ba4c5d2963040ffc6f26010de089e21331a0b4/evaluation-results/hbq-human-alignment-optimizer-v5-f20-confirmation-sol-reconcile-v3-final-message) are measurement-only. Neither optimizer has runtime authority.
- [Desc18 Fresh96 development](https://github.com/HaileyStorm/Creative-Writing-Rubrics/tree/b4ba4c5d2963040ffc6f26010de089e21331a0b4/evaluation-results/hbq-human-alignment-optimizer-v9-desc18-broad-replication-sol-veto-result-v1) tested `broader-nextwave-20-missing_evidence_not_no-referent-evidence` unchanged across 32 public/open items and 16 prompt groups. Grok equal-group MAE moved from `0.7951389` to `0.7795139` (`1.965%` reduction); after that choice was frozen, the separate Sol veto moved from `1.1751736` to `1.0699653` (`8.9526%`) with `384/384` coverage flags true. The real Optuna grid completed `12/12` trials and DSPy recorded two replay-derived examples with zero LM calls. This is open development evidence only: endpoints are not pooled, native contact cardinality is unproven, and there is no new confirmation, generalization, promotion, or runtime claim.
- [CWR-guided revision gain](https://github.com/HaileyStorm/Creative-Writing-Rubrics/tree/b4ba4c5d2963040ffc6f26010de089e21331a0b4/evaluation-results/cwr-guided-revision-gain-v1), its reviewed [lean v2 pilot](https://github.com/HaileyStorm/Creative-Writing-Rubrics/tree/b4ba4c5d2963040ffc6f26010de089e21331a0b4/evaluation-results/cwr-guided-revision-gain-v2-lean-pilot), and [V9 historical-input replay result](https://github.com/HaileyStorm/Creative-Writing-Rubrics/tree/b4ba4c5d2963040ffc6f26010de089e21331a0b4/evaluation-results/cwr-guided-revision-gain-v2-live-exec-v9-historical-input-replay-result-v1): 40 endpoint judgments are independently recomputable only from the exact completed external V7 evidence root plus the pinned historical V6 executor; they include 16 guided-control and 32 arm-baseline comparisons. Guided-control means are positive for both endpoints: Sol `+2.25` holistic / `+2.25` compact and Grok `+1.75` / `+1.50`. Endpoints remain separate; Sol contact cardinality is unproven, and this establishes neither provider ranking nor generalization.
- [V14 matched Grok-primary/Sol development results](https://github.com/HaileyStorm/Creative-Writing-Rubrics/blob/b4ba4c5d2963040ffc6f26010de089e21331a0b4/evaluation-results/hbq-human-alignment-optimizer-v14-dspy-train-expansion-result-v1/README.md#what-this-says-about-development-judges) and the [separate DEV checkpoint](https://github.com/HaileyStorm/Creative-Writing-Rubrics/blob/b4ba4c5d2963040ffc6f26010de089e21331a0b4/evaluation-results/hbq-human-alignment-optimizer-v14-dspy-train-pilot-v1/DEVELOPMENT.md): actual receipt-derived 88-cell-per-endpoint TRAIN and 26-cell-per-endpoint DEV comparisons. Payload bytes match within each panel, while coverage and rank differ across endpoints; this supports separate Grok-primary development and Sol validation, not interchangeability or speed claims. The [historical public-synthetic screen](https://github.com/HaileyStorm/Creative-Writing-Rubrics/tree/b4ba4c5d2963040ffc6f26010de089e21331a0b4/evaluation-results/hbq-grok-sol-current-matched-v1) remains optional pre-execution context.
- [Flash-Next planning](https://github.com/HaileyStorm/Creative-Writing-Rubrics/tree/b4ba4c5d2963040ffc6f26010de089e21331a0b4/evaluation-results/hbq-supplemental-providers-flash-next-v1) and its [Linux portability diagnostic](https://github.com/HaileyStorm/Creative-Writing-Rubrics/tree/b4ba4c5d2963040ffc6f26010de089e21331a0b4/evaluation-results/hbq-supplemental-providers-flash-next-linux-portability-v1): planning and self-integrity evidence only; native Linux execution, attestation, pairing, and promotion remain NO-GO.

## HANNA prompt-development and held-out confirmation

Lower MAE is better. Grok-primary development selection was frozen before Sol
validation. Endpoint results were not pooled.

| Stage / endpoint | Prompt groups / cells | Baseline MAE | Descendant MAE | Outcome |
| --- | ---: | ---: | ---: | --- |
| Three-group development — Grok | 3 / development slice | `0.925926` | `0.750000` | `19.00%` MAE reduction. |
| Three-group development — Sol | 3 / matched slice | `1.252778` | `1.135185` | `9.39%` MAE reduction. |
| Broader development — Grok | 7 / development slice | `0.988095` | `0.738095` | `25.30%` MAE reduction. |
| Broader development — Sol | 7 / matched slice | `1.247619` | `1.067460` | `14.44%` baseline-to-descendant MAE reduction. |
| Fresh88 confirmation — Grok | 8 / 38 | `1.256944` | `0.937500` | `25.414%` MAE reduction. |
| Fresh88 confirmation — Sol | 8 / 38 | `1.426736` | `1.243924` | `12.813%` MAE reduction. |

The confirmation partition comprises 19 untouched Fresh88 items, eight prompt
groups, and 38 endpoint-neutral logical cells; each endpoint ran its own frozen
38-cell schedule. It is held out within Fresh88 only:
these measurements do not establish endpoint interchangeability, runtime or
prompt promotion, or general literary validity. The Grok baseline has two
cells with incomplete dimension coverage; both descendant cells are complete.
Native endpoint/contact cardinality remains unproven for both endpoints.
DSPy/Optuna remain development-only and have no runtime selection authority.

### Fresh96 confirmation: the retained smaller edit holds on Sol

The [frozen Fresh96 panel](https://github.com/HaileyStorm/Creative-Writing-Rubrics/tree/b4ba4c5d2963040ffc6f26010de089e21331a0b4/evaluation-results/hbq-human-alignment-optimizer-v10-fresh96-confirmation-candidates-v1)
compared the baseline with retained child20 on 32 untouched items in 16 prompt
groups. Both endpoints received the same 64 frozen payloads; no prompt was
retuned after the Grok result.

| Endpoint | Baseline MAE | Child20 MAE | Relative reduction | Group wins / ties / losses |
| --- | ---: | ---: | ---: | ---: |
| [Grok](https://github.com/HaileyStorm/Creative-Writing-Rubrics/tree/b4ba4c5d2963040ffc6f26010de089e21331a0b4/evaluation-results/hbq-human-alignment-optimizer-v10-fresh96-confirmation-grok-result-v1) | `1.045139` | `0.745660` | `28.6545%` | 15 / 1 / 0 |
| [Sol](https://github.com/HaileyStorm/Creative-Writing-Rubrics/tree/b4ba4c5d2963040ffc6f26010de089e21331a0b4/evaluation-results/hbq-human-alignment-optimizer-v10-fresh96-confirmation-sol-result-v1) | `1.350087` | `1.107813` | `17.9451%` | 15 / 0 / 1 |

Sol baseline coverage is 191/192 dimension flags; child20 is 192/192. The
baseline's flagged Empathy score remains in the frozen numeric-score MAE.
Grok coverage is complete for both candidates. These are separate
human-reference error measurements, not percentages of human agreement or
evidence that the two judges are interchangeable. They validate this prompt
comparison within Fresh96, not the original full-rubric HANNA correlation or
general literary quality. No runtime promotion follows automatically.

A later deterministic calibration check is post-hoc context, not a tuned or
preregistered comparator. A fixed, non-fitted constant-3 predictor has MAE
`0.750000`: child20 is only `0.004340278` lower on Grok (`0.745659722`) and is
worse on Sol (`1.1078125`). The paired MAE reductions remain real, but they do
not establish general ranking success; every frozen numeric score, including
the false-coverage Sol Empathy score, remains included. This check made no
provider calls.

The [opt-in child20 development profile](https://github.com/HaileyStorm/Creative-Writing-Rubrics/tree/b4ba4c5d2963040ffc6f26010de089e21331a0b4/evaluation-results/hbq-human-alignment-optimizer-v10-child20-development-profile-v1)
publishes the exact frozen instruction and profile text with a provider-free
verifier. It does not change a runtime default or establish Flash-Next support.

## Held-back revision comparison

The [four-item held-back result](https://github.com/HaileyStorm/Creative-Writing-Rubrics/tree/b4ba4c5d2963040ffc6f26010de089e21331a0b4/evaluation-results/cwr-guided-revision-gain-v6-heldout-result-v1)
compares CWR-guided and generic revisions under independent holistic and compact
judgments. All 60 receipts replay: four Sol feedback, eight Grok revisions,
and 48 endpoint judgments. Guided-minus-generic means are Sol `+1.00` holistic
and `+0.75` compact; Grok `+0.75` and `0.00`. These are score-point differences
on the holistic 1–7 and compact 1–5 scales, respectively. The compact Grok tie matters: this is a small,
endpoint-separated result, not universal revision superiority. Sol native
contact cardinality remains unproven.

## Exact HANNA generated-only result

Fresh88 is development evidence, not a held-out confirmation and not fresh
human judging. The primary slice contains 80 generated stories, excluding the
eight `Human`-labeled items from the 88-item corpus. Spearman intervals use
1,000 prompt-group-clustered bootstrap draws.

| HANNA dimension | Items | Spearman estimate |
| --- | ---: | ---: |
| Relevance | 80 | `0.095142690753166` |
| Coherence | 79 | `-0.1007272577837817` |
| Empathy | 80 | `0.03693678832042041` |
| Surprise | 80 | `-0.2427665637523263` |
| Engagement | 80 | `0.07538280924061605` |
| Complexity | 79 | `-0.08082326488270875` |
| **Unweighted six-dimension macro** | **80-story primary slice** | **`-0.036142466350769044`** |

The macro 95% interval is `[-0.15652275025323253,
0.10485700771548533]`; mean mapped-dimension coverage is
`0.8914680028129395`. Alternative descriptive aggregation did not rescue the
claim: the hierarchical dimension-to-macro estimate was
`-0.03775134336184484`, the unique 27-leaf overlap estimate was
`-0.09014775122983233`, and the occurrence-weighted 28-mapping estimate was
`-0.09215367277874827`. These views do not change verdicts, weights, or the
canonical HBQ score. See the bound
[machine-readable summary](https://github.com/HaileyStorm/Creative-Writing-Rubrics/blob/b4ba4c5d2963040ffc6f26010de089e21331a0b4/evaluation-results/hbq-human-alignment-v3-fresh88-overlap-analysis-v1/results-v2/summary.json).

## What changed besides repeatability

| Product change | Evidence-led conclusion |
| --- | --- |
| **Scope propagation** | The declared evaluation unit is rendered into judging context. A valid local issue remains a revision note unless proposition, activation, evidence, and materiality support a scope-level `NO`. Scene and chapter diagnostics do not average into manuscript scores. |
| **Quote-to-summary repair** | A non-verbatim but supported evidence item can be deterministically relabeled as a summary. That repair does not change the verdict, resend the prompt, or count as a new observation. |
| **Four-state handling** | `YES`, `NO`, `NOT_APPLICABLE`, and `CANNOT_ASSESS` remain distinct. Applicability and insufficient evidence are not partial failures or values to coerce into a binary result. |
| **Polarity** | Positive and reversed questions did not behave as interchangeable mirrors; averaging them did not improve the HANNA comparison. Positive wording remains canonical, with paired polarity only as an explicit diagnostic. |
| **Confidence** | Confidence remains visible diagnostic context. It does not reweight score or coverage, authorize promotion, or trigger automatic resampling; low-confidence allocation underperformed uniform allocation on the available repeat-consensus proxy. |
| **Content-treatment activation** | `modifier.style.authored_content_treatment_fidelity` activates only from an explicit treatment target such as directness, density, specificity, register, euphemism, or depiction scope. More explicit is not automatically better, and mature content does not activate it. |
| **Long-form/full-fidelity coverage** | A declared full-fidelity result keeps all applicable whole-work and local coverage. Diagnostic sampling is allowed only when labeled as sampling; the V9 rebaseline used none. |
| **Deterministic isolation and settlement** | Leaf judgments remain independent; aggregation, validation, and settlement are deterministic. A provider failure is not a craft verdict, a quote repair is not a replicate, and V9's zero-call validator correction is not a fresh evaluation. |
| **Ownership and leaf audit** | The public audit covers all 2,145 leaves and keeps one scoring owner per proposition. Its candidates are a review queue, not presumed defects; stockness remains owned by `no_default_metaphors`, while figurative density remains with purple-prose leaves. |

The normative boundaries are in [Judging](judging.md),
[Benchmarking](benchmarking.md), the
[leaf-decomposition policy](LEAF_DECOMPOSITION_POLICY.md), and the
[full-leaf structural audit](https://github.com/HaileyStorm/Creative-Writing-Rubrics/tree/b4ba4c5d2963040ffc6f26010de089e21331a0b4/evaluation-results/hbq-full-leaf-structural-audit-v1).

## Protocol-scoped chronology

Scores below are not one continuous scale. They changed with rubric content,
prompt framing, reasoning level, scope, and accepted-verdict geometry.

### *The Part That Arrives First*

| Version | Rubric/prompt | Result direction | Meaning |
| --- | --- | --- | --- |
| Initial batching study (`4d93dcf`) | GPT-5.6 Sol; HBQ-RS `prose.short_story`; 178 leaves; five runs at batch 24 and all-in-one | Batch 24 averaged `89.59896`; all-in-one averaged `87.77456`, but all-in-one was more repeatable. | Batch shape affects both score and applicability; freeze it as part of the method. |
| Established-rubric v4 (`a46c2fc`) | GPT-5.6 Sol high; strict schemas; HBQ batch 32; five runs each | HBQ averaged `90.6764` with 91.01% all-five leaf agreement. Comparison rubrics were at or near their ceilings. | Positive repeatability and headroom evidence, not proof that one rubric is universally better. |
| QPC1 control (`8970e09`) | Seven isolated purple-prose leaves; five repetitions | Every control cell, like every Gray Blood cell, was 5/5 `YES`. | Negative discrimination result. |
| QPC24 control (`3e840f3`, evaluated at `4ce1204`) | Two complete 221-leaf `prose.novel` passes | 214/221 within-story agreement; strong stable separation from both Gray Blood drafts. | Useful control separation, not a matched-form score comparison: this is a complete public short story used as the control. |

The complete story is [owner-authorized for publication](https://github.com/HaileyStorm/Creative-Writing-Rubrics/blob/b4ba4c5d2963040ffc6f26010de089e21331a0b4/evaluation-results/the-part-that-arrives-first-repeatability/source.md).

### *Gray Blood*

| Version | Rubric/prompt | Result direction | Meaning |
| --- | --- | --- | --- |
| Initial public extract (`3e65dae`) | Earlier long-form protocol; Luna-max whole-work and Sol-medium local subset | Author-original was numerically higher, `78.0767` vs `74.1946`, but states were `INELIGIBLE`/`UNRESOLVED`. | Historical diagnostic only; not a valid preference result. |
| CWR `1.1.0` comparison (`61bc33a`, expanded at `24df6c7`) | Sol-medium binary judging; complete whole-work passes, then full chapter-local expansion | Both became `VALID`; author-original led `78.9174` to `74.0536`. | Protocol-scoped result retained in Git history. |
| Current six-chapter comparison (`e2fc09b`) | HBQ-RS `1.0.0`; Sol high; complete current WIP protocol | Direction reversed: GPT-5.6 Pro rewrite `83.4127`, author-original `75.5214`. | Results are comparable only within this protocol; five authorized excerpts are public and the remaining manuscript is private. |
| Figurative QPC1 (`8970e09`) | HBQ-RS 1.2/content-treatment era; seven one-leaf requests | 105/105 `YES`; no separation. | The isolated prompt/scope treatment was insufficient and authorized no rubric change. |
| Full-rubric QPC24 V5 (`3e840f3`) | Six complete 221-leaf passes at exact CWR head `4ce1204` | Strong public-control separation, but only four stable author-original/GPT-5.6 Pro rewrite differences. | Bounded discrimination evidence; no wording or weight promotion. |
| Full-book V7/V8/V9 (`0110cc6`) | HBQ-RS `1.2.1`; CWR runtime `1.2.3`; full declared coverage of the work-in-progress manuscript | Author-original `63.0202`; GPT-5.6 Pro rewrite `73.2369`; difference `+10.2167`. | Strongest current execution-and-coverage evidence for this artifact pair, not a comparative inference beyond its WIP protocol. Bounds are non-statistical, with 8 units / 1,817 positions versus 7 / 1,589. V8 remains archived incomplete; V9 is a zero-call deterministic correction, not a new run. |

Public Gray Blood material is limited to aggregate reports and the five
owner-authorized excerpts in the
[six-chapter package](https://github.com/HaileyStorm/Creative-Writing-Rubrics/tree/b4ba4c5d2963040ffc6f26010de089e21331a0b4/evaluation-results/gray-blood-ch1-6). Authorship must
remain explicit: **author-original** and **GPT-5.6 Pro rewrite**.

## Evidence map

### Flagship evidence

- [Established-rubric repeatability v4](https://github.com/HaileyStorm/Creative-Writing-Rubrics/tree/b4ba4c5d2963040ffc6f26010de089e21331a0b4/evaluation-results/the-part-that-arrives-first-repeatability/established-v4)
- [Fresh88 primary analysis](https://github.com/HaileyStorm/Creative-Writing-Rubrics/tree/b4ba4c5d2963040ffc6f26010de089e21331a0b4/evaluation-results/hbq-human-alignment-v3-fresh88-analysis-v1) and [overlap views](https://github.com/HaileyStorm/Creative-Writing-Rubrics/tree/b4ba4c5d2963040ffc6f26010de089e21331a0b4/evaluation-results/hbq-human-alignment-v3-fresh88-overlap-analysis-v1)
- [Gray Blood six-chapter comparison](https://github.com/HaileyStorm/Creative-Writing-Rubrics/tree/b4ba4c5d2963040ffc6f26010de089e21331a0b4/evaluation-results/gray-blood-ch1-6)
- [QPC24 full-rubric confirmation](https://github.com/HaileyStorm/Creative-Writing-Rubrics/tree/b4ba4c5d2963040ffc6f26010de089e21331a0b4/evaluation-results/hbq-qpc24-two-pass-product-confirmation-v5-public-result-v1)
- [QPC24 V9 full-book aggregate](https://github.com/HaileyStorm/Creative-Writing-Rubrics/tree/b4ba4c5d2963040ffc6f26010de089e21331a0b4/evaluation-results/hbq-gray-blood-full-book-qpc24-rebaseline-v9-public-result-v1)

### Negative and diagnostic evidence

- [QPC1 figurative-treatment aggregate](https://github.com/HaileyStorm/Creative-Writing-Rubrics/tree/b4ba4c5d2963040ffc6f26010de089e21331a0b4/evaluation-results/hbq-qpc1-figurative-treatment-v1)
- [Paired-polarity analysis](https://github.com/HaileyStorm/Creative-Writing-Rubrics/tree/b4ba4c5d2963040ffc6f26010de089e21331a0b4/evaluation-results/hbq-hanna-polarity-paired-analysis-v1)
- [Four-state polarity/confidence decision](https://github.com/HaileyStorm/Creative-Writing-Rubrics/tree/b4ba4c5d2963040ffc6f26010de089e21331a0b4/evaluation-results/hbq-four-state-polarity-confidence-v1)
- [Confidence diagnostics](https://github.com/HaileyStorm/Creative-Writing-Rubrics/tree/b4ba4c5d2963040ffc6f26010de089e21331a0b4/evaluation-results/hbq-confidence-diagnostics-v1)
- [AI-writer preface analysis](https://github.com/HaileyStorm/Creative-Writing-Rubrics/tree/b4ba4c5d2963040ffc6f26010de089e21331a0b4/evaluation-results/hbq-ai-writer-preface-v1-analysis-v1)
- [Balanced DSPy held-out evaluation](https://github.com/HaileyStorm/Creative-Writing-Rubrics/tree/b4ba4c5d2963040ffc6f26010de089e21331a0b4/evaluation-results/hbq-human-alignment-optimizer-v4-balanced-dspy-heldout-eval-v1) and [versioned executor](https://github.com/HaileyStorm/Creative-Writing-Rubrics/tree/b4ba4c5d2963040ffc6f26010de089e21331a0b4/evaluation-results/hbq-human-alignment-optimizer-v4-balanced-dspy-heldout-exec-v1)
- [Full-leaf structural audit](https://github.com/HaileyStorm/Creative-Writing-Rubrics/tree/b4ba4c5d2963040ffc6f26010de089e21331a0b4/evaluation-results/hbq-full-leaf-structural-audit-v1) and [first-remedy portfolio](https://github.com/HaileyStorm/Creative-Writing-Rubrics/tree/b4ba4c5d2963040ffc6f26010de089e21331a0b4/evaluation-results/hbq-first-remedy-portfolio-v1)

### Guides

- [HBQ-RS standard](HBQ_RS_STANDARD.md)
- [Judging and score semantics](judging.md)
- [Benchmarking and confidence](benchmarking.md)
- [Leaf decomposition policy](LEAF_DECOMPOSITION_POLICY.md)
- [Validation and repair journey](VALIDATION_AND_REPAIR_JOURNEY.md)

## What remains genuinely unproven

- Full-rubric human alignment beyond the weak Fresh88 generated-only result. Bounded prompt-level confirmation exists, but no fresh or live human judging was performed.
- Reader outcomes, revision usefulness across representative projects, or a general literary-quality ranking.
- Superiority over established rubrics, other graders, or simpler controls on a held-out multi-story portfolio.
- Generalization of the Gray Blood author-original/GPT-5.6 Pro rewrite difference beyond that private WIP pair and its declared scope.
- A rubric promotion from the full-book result; V9 changed no wording, weight, criterion owner, or bundle influence.
- General figurative discrimination from QPC1, or universal validity of the content-treatment module.
- A universal batch-size recommendation; observed batch effects remain stack- and protocol-specific.
- Confidence-weighted scoring, low-confidence auto-resampling, or paired-polarity averaging as production defaults.
- Empirical resolution of every structural-audit candidate; the audit is not a defect backlog.

For the longer account of why negative evidence changed the product, see the
[validation and repair journey](VALIDATION_AND_REPAIR_JOURNEY.md).

## V16 comparative HANNA TRAIN measurement

The [V16 aggregate](https://github.com/HaileyStorm/Creative-Writing-Rubrics/blob/b4ba4c5d2963040ffc6f26010de089e21331a0b4/evaluation-results/hbq-human-alignment-optimizer-v16-comparative-train-v1/result.json)
records a useful but bounded direction: on 50 stories in five selected TRAIN
groups, scoring each ten-story prompt group in shared context twice in opposite
orders raised the HANNA-compatible drop-undefined six-axis
prompt-macro tied Spearman from `0.205269` to `0.337593` for Grok and from
`0.249094` to `0.329532` for Sol when the two comparison orders are averaged.
Mean six-axis MAE also fell from `1.121111` to `0.765333` for Grok and from
`0.993333` to `0.814722` for Sol. Independent raw-receipt arithmetic matched
both endpoint reports with zero mismatches. The direct strict all-five-prompt
result is undefined: retained prompt counts by axis were `5/5/5/1/4/5` for
Grok and `5/5/5/3/5/5` for Sol, while the mean comparative result retained all
five prompts on all six axes. That coverage difference limits the comparison.

The result is endpoint-separated, development-only, and not a full HANNA
comparison. It does not isolate comparison/batching/decimal/token effects:
comparative cells use two judgements per story and larger shared context, the
direct cells are historical rather than contemporaneous, and forward versus
reverse order still differs. Grok requested `grok-4.6` and reported
`grok-4.6-build`; Sol locally resolved requested `gpt-5.6-sol` at `high`.
Tools/subagents/web were disabled. Native contact cardinality remains unproven,
and Sol/provider reasoning attestation is absent; the independent check proves
receipt arithmetic, not those identities. It opens no confirmation,
generalization, selection, promotion, runtime, or endpoint-pooling claim. See the separate
[Grok](https://github.com/HaileyStorm/Creative-Writing-Rubrics/blob/b4ba4c5d2963040ffc6f26010de089e21331a0b4/evaluation-results/hbq-human-alignment-optimizer-v16-comparative-train-v1/GROK_TRAIN.md)
and [Sol](https://github.com/HaileyStorm/Creative-Writing-Rubrics/blob/b4ba4c5d2963040ffc6f26010de089e21331a0b4/evaluation-results/hbq-human-alignment-optimizer-v16-comparative-train-v1/SOL_TRAIN.md)
summaries.

## V17 standalone Sol replication

The [Sol result](https://github.com/HaileyStorm/Creative-Writing-Rubrics/blob/e1c6f3bd0d34325ff4806cad8d49afaa340c49ca/evaluation-results/hbq-human-alignment-optimizer-v17-comparative-train-replication-native-v1/sol-result.json)
independently replays 48 fresh cells plus 12 pinned V15 measurements across 50
stories and five additional TRAIN groups. The primary mean-of-both-orders
Spearman is `0.423961`, with all five groups retained on every axis; mean
six-axis MAE is `0.784167`. The direct arm's descriptive macro is `0.417514`,
but Surprise retains only three groups, leaving its strict-five macro
undefined. This does not establish a clean comparative-method gain or
full-HANNA competitiveness.

The [Grok settlement](https://github.com/HaileyStorm/Creative-Writing-Rubrics/blob/e1c6f3bd0d34325ff4806cad8d49afaa340c49ca/evaluation-results/hbq-human-alignment-optimizer-v17-comparative-train-replication-native-v1/grok-incomplete.json)
retains 23 response-backed cells and 25 terminal failures after a native quota
exhaustion observation. It is ineligible for subset metrics or an endpoint
performance comparison. Sol is a standalone TRAIN diagnostic, with no
confirmation, generalization, canonical full-HBQ, or runtime-promotion claim.

## WPB terminal collection

The later [WPB Grok settlement](https://github.com/HaileyStorm/Creative-Writing-Rubrics/blob/87ae86b1cde49177b43d5791483421888f2d5ec6/evaluation-results/hbq-human-alignment-wpb-compact-family-native-v1/grok-incomplete.json)
records 89 successful cells, one ambiguous terminal cell, and 39 unstarted
cells out of 129 planned. The failure is `unclassified_after_launch`; the
retained evidence does not establish quota exhaustion, HTTP 402, or a specific
validation cause. The campaign remains terminal: no automatic resend,
successor batch, subset alignment metrics, or fit is permitted. This coarse
family comparison is not a full-HBQ alignment result.

## Dryad source and full-HBQ preparation

The [Dryad source audit](https://github.com/HaileyStorm/Creative-Writing-Rubrics/blob/87ae86b1cde49177b43d5791483421888f2d5ec6/evaluation-results/hbq-human-alignment-dryad-source-audit-v1/README.md)
reconciles 293 stories and 3,519 blinded evaluations from 600 evaluators. The
[frozen analysis protocol and implementation](https://github.com/HaileyStorm/Creative-Writing-Rubrics/blob/87ae86b1cde49177b43d5791483421888f2d5ec6/evaluation-results/hbq-human-alignment-dryad-full-hbq-analysis-v1/README.md)
use 176 TRAIN and 60 DEV stories; 57 confirmation stories remain closed.
Source-defined novelty and usefulness are separate co-primary targets, with
all twelve raw axes also reported separately. There is no invented twelve-axis
human composite or sampled-leaf substitute for the full 178-question rubric.

The provider-free qualification plan covers 18 passes and 261 requests.
Governed cohort execution, complete native replay, the fixed 128-trial TRAIN
optimizer, and conditional DEV comparison are implemented and locally tested.
The [first live qualification attempt](https://github.com/HaileyStorm/Creative-Writing-Rubrics/blob/0b3437b022d4ed41418483ccab08eaca71c6cc08/evaluation-results/hbq-human-alignment-dryad-full-hbq-analysis-v1/qualification-attempt-1.json)
is terminal and invalid: six contacts produced five accepted HBQ checkpoints
and one response with an unexpected `question_id` of `pending`. Request 7
never started; 255 requests remain unstarted. All evidence is preserved, with
no automatic resend or subset metrics. Fresh alignment measurement and
unchanged-payload Sol validation remain pending. The empirical batch cap is
unset; synthetic tests and prepared targets establish neither alignment nor
generalization.

The separately frozen [v2 attempt](https://github.com/HaileyStorm/Creative-Writing-Rubrics/blob/868355f316a1b6fb559a3e365613a6d3ea8748c0/evaluation-results/hbq-human-alignment-dryad-full-hbq-analysis-v1/qualification-attempt-2.json)
constrained each batch's response IDs and retained the original stories,
questions and prompt bytes. It produced 27 accepted checkpoints, including
one complete 178-question pass whose 23 native identities replayed successfully.
Contact 28 then returned an ambiguous post-launch transport outcome with no
native receipt or recoverable completed result. The run is quarantined,
with 233 requests unstarted and no cap, alignment result, subset metrics or
automatic resend. The structured failure does not establish a quota, billing
or timeout cause.
