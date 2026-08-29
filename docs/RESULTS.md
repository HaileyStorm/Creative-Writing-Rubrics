# Results and evidence

This page is the short public map of what HBQ-RS has established, falsified,
and left open. Results are scoped to their named artifacts, rubric version,
prompt, batch geometry, and evidence boundary. `Positive` means a declared
product test succeeded; `Negative` means a proposed claim or treatment failed;
`Bounded` means the result is useful but does not support a broader promotion.

## Headline findings

| Finding | Status | Public result | What it supports |
| --- | --- | --- | --- |
| HBQ-RS repeated consistently on the complete, authorized *The Part That Arrives First*, while retaining more headroom than the comparison rubrics. | **Positive** | [Established-rubric repeatability v4](../evaluation-results/the-part-that-arrives-first-repeatability/established-v4/) | On one story across five HBQ runs, the score averaged `90.6764`; 162/178 leaves agreed in all five runs. NAPLAN and Oregon implementations were perfectly repeatable but ceiling-bound. |
| The Fresh88 generated-only HANNA comparison did not establish alignment. | **Negative** | [Primary reconstruction](../evaluation-results/hbq-human-alignment-v3-fresh88-analysis-v1/) and [overlap views](../evaluation-results/hbq-human-alignment-v3-fresh88-overlap-analysis-v1/) | Across 80 generated stories, the six-dimension macro Spearman was `-0.036142466350769044`; several dimensions were negative, including Surprise at `-0.2427665637523263`. |
| QPC1's isolated figurative leaves passed everything and distinguished nothing. | **Negative** | [QPC1 aggregate](../evaluation-results/hbq-qpc1-figurative-treatment-v1/) | 105/105 accepted verdicts were `YES`; the result blocked a split, reweight, or new density owner. |
| Full-rubric QPC24 separated the public control strongly but found only limited stable separation between the private drafts. | **Bounded** | [QPC24 V5 aggregate](../evaluation-results/hbq-qpc24-two-pass-product-confirmation-v5-public-result-v1/) | Six complete 221-leaf passes; four differing leaves among 189 leaves stable in both author-original and GPT-5.6 Pro rewrite repetitions. |
| Four small wording repairs survived development, disjoint confirmation, and review without changing ownership or influence. | **Positive** | [Validation and repair journey](VALIDATION_AND_REPAIR_JOURNEY.md#repair-became-a-portfolio-not-a-reflex) | Recurrence/applicability, explicit excerpt scope, figurative semantic hinges, and material-context line breaks changed; IDs, owners, weights, and bundle influence did not. |
| The current *Gray Blood* work-in-progress manuscript rebaseline completed at full declared fidelity. | **Bounded** | [QPC24 V9 full-book aggregate](../evaluation-results/hbq-gray-blood-full-book-qpc24-rebaseline-v9-public-result-v1/) | HBQ-RS `1.2.1`, CWR runtime `1.2.3`, 150/150 binary calls, 3,406 positions, no sampling, and no rubric promotion. The GPT-5.6 Pro rewrite scored `+10.2167` above the author-original under this protocol; bounds are non-statistical, with 8 units / 1,817 positions versus 7 / 1,589. |

## Current development checkpoints — no result yet

These packages preserve the next questions and their gates. They are not
empirical findings, and none authorize a rubric, model, or runtime promotion.

- [HANNA optimizer v3](../evaluation-results/hbq-human-alignment-optimizer-v3/), [native-subscription v4](../evaluation-results/hbq-human-alignment-optimizer-v4-native-subscription-v1/), and the [v4 development optimizer](../evaluation-results/hbq-human-alignment-optimizer-v4-development-optimizer-v1/): frozen 80-item, 39-prompt-group geometry with Grok-primary development and unchanged Sol validation; deterministic Optuna and a development-only DSPy program are implemented behind raw-evidence gates, but empirical optimization, native execution, and confirmation have not run.
- [CWR-guided revision gain](../evaluation-results/cwr-guided-revision-gain-v1/): blinded, non-CWR endpoint design for an independently measured revision-gain question.
- [Matched Grok/Sol calibration](../evaluation-results/hbq-grok-sol-current-matched-v1/): public-synthetic, provider-free pre-execution agreement screen; it does not establish judge interchangeability.
- [Flash-Next planning](../evaluation-results/hbq-supplemental-providers-flash-next-v1/) and its [Linux portability diagnostic](../evaluation-results/hbq-supplemental-providers-flash-next-linux-portability-v1/): planning and self-integrity evidence only; native Linux execution, attestation, pairing, and promotion remain NO-GO.
- [V8 multisample continuation](../evaluation-results/hbq-multisample-repeatability-v1-remainder-capacity-reset-successor-v8/): an unpublished, paused operational checkpoint; a public repeatability result awaits completion and integrity-checked analysis.

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
[machine-readable summary](../evaluation-results/hbq-human-alignment-v3-fresh88-overlap-analysis-v1/results-v2/summary.json).

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
[full-leaf structural audit](../evaluation-results/hbq-full-leaf-structural-audit-v1/).

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

The complete story is [owner-authorized for publication](../evaluation-results/the-part-that-arrives-first-repeatability/source.md).

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
[six-chapter package](../evaluation-results/gray-blood-ch1-6/). Authorship must
remain explicit: **author-original** and **GPT-5.6 Pro rewrite**.

## Evidence map

### Flagship evidence

- [Established-rubric repeatability v4](../evaluation-results/the-part-that-arrives-first-repeatability/established-v4/)
- [Fresh88 primary analysis](../evaluation-results/hbq-human-alignment-v3-fresh88-analysis-v1/) and [overlap views](../evaluation-results/hbq-human-alignment-v3-fresh88-overlap-analysis-v1/)
- [Gray Blood six-chapter comparison](../evaluation-results/gray-blood-ch1-6/)
- [QPC24 full-rubric confirmation](../evaluation-results/hbq-qpc24-two-pass-product-confirmation-v5-public-result-v1/)
- [QPC24 V9 full-book aggregate](../evaluation-results/hbq-gray-blood-full-book-qpc24-rebaseline-v9-public-result-v1/)

### Negative and diagnostic evidence

- [QPC1 figurative-treatment aggregate](../evaluation-results/hbq-qpc1-figurative-treatment-v1/)
- [Paired-polarity analysis](../evaluation-results/hbq-hanna-polarity-paired-analysis-v1/)
- [Four-state polarity/confidence decision](../evaluation-results/hbq-four-state-polarity-confidence-v1/)
- [Confidence diagnostics](../evaluation-results/hbq-confidence-diagnostics-v1/)
- [AI-writer preface analysis](../evaluation-results/hbq-ai-writer-preface-v1-analysis-v1/)
- [Full-leaf structural audit](../evaluation-results/hbq-full-leaf-structural-audit-v1/) and [first-remedy portfolio](../evaluation-results/hbq-first-remedy-portfolio-v1/)

### Guides

- [HBQ-RS standard](HBQ_RS_STANDARD.md)
- [Judging and score semantics](judging.md)
- [Benchmarking and confidence](benchmarking.md)
- [Leaf decomposition policy](LEAF_DECOMPOSITION_POLICY.md)
- [Validation and repair journey](VALIDATION_AND_REPAIR_JOURNEY.md)

## What remains genuinely unproven

- Human alignment beyond the weak Fresh88 development result; no fresh or live human judging was performed.
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
