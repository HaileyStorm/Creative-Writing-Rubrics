# Research synthesis and rubric-design rationale

## Executive conclusion

Creative-writing evaluation benefits from analytic decomposition, but it fails when the evaluator mistakes decomposition for objectivity. The strongest design is hybrid: explicit constraints and observable craft are represented as atomic binary questions; genuinely holistic artistic success and personal taste remain small, clearly labeled components; long works are evaluated hierarchically; and close finalists receive position-controlled pairwise adjudication.

The registry is intentionally static and human-curated at its core. It can generate task-specific questions from a prompt, but those dynamic questions are limited to explicit requirements and must pass an atomicity, observability, duplication, and conflict check. This choice follows the finding that expert-authored rubrics remain substantially better than unconstrained model-generated rubrics on hard cases.

## 1. Existing creative-writing rubrics

Vaezi and Rezaei developed a fiction rubric through literature review, a modified Delphi process, expert interviews, and review by distinguished creative-writing professors. Their final analytic rubric covered narrative voice, characterization, story, setting, mood and atmosphere, language and mechanics, dialogue, plot, and image, with inter-rater and intra-rater reliability testing. The present registry retains those areas but separates owner domains more sharply and adds scope, project state, operation, and AI-pattern controls.

Carey, Davidow, and Williams argued for a craft-based post-NAPLAN rubric that treats narrative writing as an integrated artistic act rather than a school checklist. Gómez-Rodríguez and Williams later adapted that tradition to LLM creative-writing evaluation, combining holistic readability, narrative elements, mechanics, plot logic, originality and cliché avoidance, and prompt-specific style, genre, character, action, and humor criteria. Their work supports both a stable craft core and task-specific overlays.

Educational rubrics are useful mainly for their repeated convergence on cohesion, voice, originality, genre/form awareness, language facility, mechanics, thematic insight, and whole-text function. Their common weakness is coarse rating bands and an assumption that every artifact is a complete school assignment. HBQ-RS replaces those broad bands with binary leaves, adds evidence and scope controls, and distinguishes excerpts from complete works.

## 2. Why binary questions

BinEval reframes evaluation as a set of small, checkable questions rather than one broad score. Across summarization, dialogue, and factual-consistency benchmarks, it matched or exceeded strong baselines, produced score distributions closer to humans, and reduced ceiling effects. The important mechanism is not merely binary output: it is the reduction of criterion complexity, explicit failure-mode coverage, and aggregation of independently answered propositions.

Binary questions are especially useful for creative-generation systems because they produce actionable diagnostics for writers, judges, and training pipelines. “Is the voice good, 7/10?” is difficult to repair. A set of questions about narrator ownership, register drift, generic assistant phrasing, sentence rhythm, and project-style fidelity can drive targeted regeneration or editing.

There is a limit. Some qualities—overall artistic life, comic timing, felt inevitability, beauty, or whether a piece is worth keeping—cannot be made fully objective by multiplying questions. Over-decomposition can make an evaluator harsh in the wrong way, penalize legitimate ambiguity, and obscure interaction among parts. HBQ-RS reserves one cumulative holistic ladder and keeps user taste separate from craft.

## 3. Curated registry versus generated rubrics

RubricBench contains 1,147 difficult pairwise comparisons with expert-annotated atomic rubrics derived from instructions. It finds a substantial gap between human and model-generated rubrics. Related rubric surveys report an approximately 27-point improvement in judge performance when expert criteria replace generated ones on that benchmark. This is the principal reason a consumer should not ask a model to invent its full rubric for every request.

Dynamic criteria still have a legitimate role. WritingBench shows value in query-dependent assessment of style, format, and length. The compromise used here is a stable, versioned registry plus an ephemeral task module generated only from the current brief, sources, and declared profiles. The dynamic module cannot create new taste preferences after inspecting candidates.

Autorubric contributes production lessons: per-criterion evaluation, configurable weights, mixed criterion types, judge ensembles, verdict-balanced few-shot calibration, option shuffling, verbosity controls, and psychometric reliability metrics. HBQ-RS uses binary scored leaves as its default but preserves diagnostic and hard-gate types, supports judge ensembles, and includes reliability data in run reports.

## 4. Creative-writing judge reliability

LitBench provides 43,827 training pairs and a 2,480-pair test set derived from human preferences. Its strongest tested off-the-shelf judge reached 73% agreement, while specialized reward models reached 78%. That is useful performance, but far from authority. Automated scores should support selection and diagnosis, not masquerade as ground truth.

LitBench also reinforces the value of pairwise preference for finalists. Absolute criteria catch compliance and identifiable craft defects; pairwise comparison is often better at choosing between two competent pieces whose tradeoffs are hard to express as scalar deltas. HBQ-RS uses absolute binary evaluation first and pairwise adjudication only after eligibility and evidence checks.

Reader preference is not identical to craft. Revealed-preference research indicates that readers differ substantially and that broad stated preferences predict actual choices imperfectly. HBQ-RS keeps a `User taste and project preference` overlay separate. The application can learn it from accepted suggestions, edits, rerolls, pairwise choices, and explicit current settings without retroactively redefining objective defects.

## 5. Long-form evaluation

LongJudgeBench demonstrates that long-form judging is qualitatively different, not just longer. Candidate outputs average roughly 9,250 tokens and require organization, cross-section consistency, coverage, and depth. Current judges remain unstable; rubrics and references help but do not solve the problem. Position bias, context overflow, and safety rejection can invalidate runs.

The full-manuscript protocol combines a whole-work map, thread and state ledgers, opening-to-ending comparison, complete scope-correct local diagnostics by default, recurring-pattern detection, and distant retrieval checks. Sampling is an explicit mode, not the default for local diagnostics. It reports evidence coverage and score intervals. A manuscript grade is not the average of chapter grades, because a locally smooth manuscript can still have a broken global arc, missing payoff, repeated middle, or contradictory state.

## 6. Poetry and fixed form

POEMetric evaluates form accuracy and theme alignment alongside creativity, lexical diversity, idiosyncrasy, emotional resonance, imagery, literary devices, overall quality, and likely authorship. In its study, leading models performed well on form and theme but remained well behind human poets on advanced creative dimensions and overall quality. This is a useful warning for an app: automatic syllable, meter, and rhyme checks are necessary for requested fixed forms, but they are not close to sufficient.

The poetry registry includes a general poetry core, named fixed-form modules, poetry-scale overlays, and controlled penalties for purple language and empty repetition. It includes strict and contemporary English-haiku profiles. The strict profile enforces 5–7–5; the contemporary profile does not confuse Japanese morae with English syllables or require seventeen syllables by default. Both retain seasonal field, cut/juxtaposition, immediacy, and compression. The sonnet module supports Shakespearean, Petrarchan, Spenserian, Miltonic, and contemporary profiles with separate architecture, meter, rhyme, volta, and language groups.

## 7. Visual storytelling and illustration

ViStoryBench evaluates character consistency, style similarity, prompt alignment, aesthetic quality, and generation artifacts such as copy-paste behavior, with human validation. Related visual-narrative work emphasizes time, space, character, event, style, theme, clothing/prop attributes, and background anchors across a sequence.

The registry adds rubrics for scene illustration, portraits, design sheets, environments, covers, maps, storyboards, comics, and sequence continuity. These are not generic “pretty image” ratings. They check narrative event, canon state, persistent attributes, spatial logic, production function, typography where relevant, and artifacts. Cross-modal canon has one owner so character eye color is not independently scored in three modules.

## 8. Narration, performance, and audio

Voice evaluation increasingly separates linguistic content from paralinguistic competence. RW-Voice-EQ profiles acting and role fit, expressiveness, voice identity, language stability, reliability, long-form stability, and acoustic quality rather than collapsing them into one mean. Speech-prosody research additionally centers pitch, duration, intensity, rhythm, phrasing, and intelligibility.

The audio registry includes source-text fidelity, naturalness, prosody, role fit, character identity, pronunciation, long-form drift, audio-drama intelligibility, and mastering. A narration can be acoustically clean but dramatically wrong, or expressive but unstable over a chapter; the profile must preserve those distinctions. Multimodal packages add text–image and text–audio alignment, cross-modal canon, asset placement, and accessibility metadata.

## 9. Bias, calibration, and evidence

LLM judges can prefer whichever candidate appears first, longer answers, more polished formatting, styles resembling their own output, or references placed in suggestive positions. Long inputs also create truncation and retrieval failure. Production evaluation should shuffle pairwise order, blind irrelevant identity, record the exact judge and prompt version, repeat important judgments, and monitor agreement with human decisions.

Evidence-grounded evaluation improves auditability. Every material NO verdict should point to a span or asset region; every YES on a hard gate should be supportable. The system requests concise evidence and explanation, not long chain-of-thought. Verbose rationales can become post hoc stories and consume context that should be used for the artifact itself.

## 10. Refinements over the earlier rubric family

HBQ-RS turns the preceding findings into a static, owned registry of atomic binary leaves with explicit eligibility, applicability, coverage, evidence, and scope rules; it preserves a small holistic component and keeps taste separate from craft. The current standard—not this rationale—defines the operational details: [HBQ-RS standard](HBQ_RS_STANDARD.md), [Rubric Book](RUBRIC_BOOK.md), and the machine-readable registry are the controlling references for modules, penalties, long-form protocols, operation rubrics, and model-pattern controls.

## 11. Limitations and validation plan

This package is a researched design and implementation baseline, not a claim of universal psychometric validation. Most individual questions have not yet been calibrated against a large expert-labeled corpus. Further calibration should use existing licensed or public labeled data. Published repeatability studies measure test–retest stability; human-reference alignment work, after completion and publication, can measure agreement, inform removal of low-information or unreliable questions, and test bundle weights and selection accuracy against existing labeled preferences.

Recommended measurements include balanced accuracy and macro-F1 for binary leaves, Cohen or Fleiss kappa for agreement, calibration error, score-distribution comparison, pairwise preference accuracy, position/length/style bias tests, test–retest stability, and downstream utility: whether selected or revised artifacts are actually accepted more often by users.

Judge studies should vary one condition at a time: checkpoint, role, prompt, polarity, batch shape, or sampler. They should report raw model confidence beside same-input repeat behavior and human-reference agreement rather than treating confidence as truth. Positive and cleanly negated question forms deserve a paired held-out test; any polarity change should be model- and module-specific unless broader evidence supports it.

Local candidates such as Qwen3.8-27B and an Escha-derived checkpoint are evaluation targets, not package dependencies. If the same checkpoint initially fills two workflow roles, measure correlated errors instead of calling the pair an ensemble. Drafting may use a stronger creative sampler than grading; both profiles still need exact fingerprints and task-specific calibration before comparison or promotion.

A custom grader may also learn better confidence estimates, but confidence should mean uncertainty about its own verdict rather than resemblance to a benchmark score. Calibrate it first against repeated-verdict stability and available reference labels, then test whether spending a fixed retry budget on low-confidence leaves improves repeatability and held-out HANNA agreement. HANNA can supervise or select changes only where its dimensions overlap HBQ, with prompt-level holdouts kept untouched; it should not become a hidden training target for the rest of the rubric.

## Empirical evidence census (2026-10-01)

These counts use different units. A story, passage, human ranking, pair target,
native request, repeated score, and atomic HBQ-RS verdict are **not**
interchangeable. Source samples are counted once by stable identity/content
hash, while endpoint and repeat measurements remain separate. Private control
artifacts named below are retained outside this public repository; no source
prose, individual ratings, or raw model responses are included here.

### Human reference data already held

| Source | Source items | Human judgments available / used | Qualification and boundary |
| --- | ---: | --- | --- |
| LAMP fiction, B1/B2/B3/B5/B4/B6 | 108 distinct triplets, 324 distinct passages (108 AI-generated, 108 AI-edited, 108 human-edited) | 94 admitted triplets: 282 assessor full rankings and 282 derived majority pair targets (846 derived individual pair ballots). Batches: B1 21/22, B2 14/14, B3+B5 25/29, B4 11/17, B6 23/26. | Domain-expert/professional-writer preferences, **not** proof that every rater is a publishing editor. The 14 unexamined triplets are residual members of the same source/rater pools, not a new independent editor panel. Batch 4's 11/17 paired screen was underpowered and exploratory. |
| TTCW | 36 AI stories in 12 plot groups, plus 12 URL-only professional-story references | 1,512 admitted binary expert judgments (36 × 14 tests × 3 assessors); the author file has 2,016 rows including 504 for the unscored references. | Creative-writing expert test judgments, not relative publishing-editor preferences. The paper says ten assessors; the released file has eleven numeric assessor codes, with person mapping unresolved. See the [aggregate](../evaluation-results/hbq-human-alignment-ttcw-expert-v1/). |
| Pron vs Prompt | 180 synopses (60 titles, Pron/Spanish GPT-4/English GPT-4) | 720 author-released expert evaluation rows with multiple rubric fields; our frozen Spanish-GPT-4 analysis admitted 180 rows (60 titles × 3 assessors). | Literary critics/university scholars, not a fresh cohort for this project; Spanish synopsis task. The other rows are not additional independent confirmation for the selected analysis. |
| Trained-RA scored stories | 64 frozen stories (32 development, 32 confirmation) | Development opened 32 stories × 2 trained psychology RAs × 4 facets = 256 scalar ratings; confirmation targets are not admitted here. | Trained research assistants, not literary professionals; the 23-story stopped-prefix analysis reuses the development labels. |
| Dryad | 293 stories | 3,519 blinded evaluation records from 600 general evaluators, with 9–14 evaluations per story and twelve raw scales. | Reader/evaluator population, not editors; the selected 100-story CWR measurement is a subset, not new source stories. See the [source audit](../evaluation-results/hbq-human-alignment-dryad-source-audit-v1/). |
| WritingPreferenceBench (WPB) | 1,200 English preference pairs across 51 categories | The 1,200 human pair labels exist; CWR selected 153, measured 105 TRAIN + 24 DEV = 129, and kept 24 confirmation pairs closed. | Eleven calibrated annotators are called experts by the authors, but professional-writing credentials are unproven. Do not count it as a verified publisher-editor cohort. See the [pilot](../evaluation-results/hbq-human-alignment-wpb-pilot-v1/). |
| HANNA | Published source has 1,056 stories × 3 raters × 6 dimensions = 19,008 ratings; CWR Fresh88 used 88 source items. | Crowdworker ratings; other v3 development/confirmation IDs are externally held and may overlap Fresh88. | Useful broad reader signal, not expert data or 1,056 new CWR-generated stories. |

The LAMP source-freeze identities are
`lamp-source-r225`, `batch2-source-r250`, `lamp-holdout-source-r340`,
`lamp-holdout-source-r304`, and `lamp-holdout-source-r325`. Their 324
passage SHA-256 values are distinct across freezes. Later cached-score grids
reuse the same human labels; their rows must not inflate this census.

### Prose samples we generated, and judgments we collected

The two CWR-guided revision ledgers document **16 logical revision-generation
receipts**: eight distinct event IDs from the completed v2 root and eight
held-back v6 revision receipts. The v8/v9 projections replay the v2 root and
add no new prose. Because the public v6 record omits source IDs and revision
content hashes, sixteen is a receipt count, **not** sixteen proven byte-unique
prose artifacts or a complete count of all external/private runs. Feedback,
native judge requests, and synthetic fixtures are not generated stories. See
the [held-out v6 result](../evaluation-results/cwr-guided-revision-gain-v6-heldout-result-v1/)
and the revision-gain V9 entry in [the validation journal](VALIDATION_AND_REPAIR_JOURNEY.md).

LAMP contributes 324 distinct **upstream** passage artifacts, not CWR-generated
revisions. Its admitted prediction manifests cover all 324 variants on both
Grok and Sol; they record 342 passage-pass response sets per endpoint (324
first instances plus 18 planned development repeat sets), **684 endpoint-pass
sets** total. These are model judgments of the same prose, not 684 new
passages. A separate Batch-3/5 repeat probe reuses twelve variants; its
72/72 Grok and 71/72 Sol accepted criterion packets add no human labels or
source samples (one Sol packet remains ambiguous). The eleven-item
multisample panel has 330 requested measurement cells (five repeats × six
arms), not 330 stories. Source IDs are suppressed in that public export, so
overlap with other corpora cannot be summed away.

### Exact-current-leaf judgment floor

The installed HBQ-RS 1.2.1 `prose.short_story` compilation has 178 question
IDs. Its compiled question-payload SHA-256
`d66c9a9e8471bb57d9ad80c4780349126464c177663b8dca012f44ff2ce52c11`
matches both the frozen TTCW and
Spanish expert plans; Dryad's full-HBQ contract pins the current module and
bundle aggregates. Thus these are exact current-wording leaf verdicts, not
merely reused IDs:

| Native cohort | Distinct source samples | Accepted requests | Valid atomic leaf-verdict occurrences | Status |
| --- | ---: | ---: | ---: | --- |
| TTCW | 36 | 828 Grok + 828 Sol | 6,408 + 6,408 = 12,816 | Expert reference, both endpoints admitted. |
| Spanish expert selected | 60 | 1,379 Grok + 1,380 Sol | 10,672 + 10,680 = 21,352 | Eight Grok verdict slots explicitly missing; no resend. |
| Dryad selected 100, Sol | 100 | 2,300 Sol | 17,800 | Completed model verdict collection; full original study not admitted. |
| Dryad selected 100, Grok early retained snapshot | Same 100 | 261 recognized requests | 2,022 | Lower-bound historical prefix, not a full-study result; later progress has no consolidated exact verdict count here. |

The first three rows establish **51,968 valid current-leaf verdict
occurrences** over 196 source samples and 6,715 endpoint requests. Including
the separate retained Grok prefix gives at least **53,990** occurrences, not
an all-time total. The LAMP cached challenge supplies 38 overlapping native
leaves on 48 triplets (288 provisional endpoint × variant scores), with
roughly 0.16–0.20 score coverage; it is not a full `prose.short_form`
judgment and cannot simply be multiplied into the floor. Selective older
studies, poetry, and repeat/replay copies remain outside this tally until
their logical sample/request identities and exact leaf-payload hashes are
joined. Keep old verdicts: a later leaf revert can make a historical
payload relevant again.

**Refresh rule:** count each source by stable content hash and cohort; count
an accepted leaf verdict by study, endpoint, logical sample, request/session,
question ID, and exact leaf-payload hash, deduplicating recovery and replay
copies. Join to the current payload hash for the present-version subtotal;
retain nonmatching historical hashes as a separate reversible archive.
Record missing/ambiguous attempts and full-versus-partial coverage separately.
Do not publish a single grand sample or judgment total until this join
covers every result family and external run root.

### Current human-alignment and reliability scorecard

No reweighting in this census is a shipped HBQ-RS improvement. The current
public CWR package is 1.2.3 with HBQ-RS 1.2.1; cohorts and scale definitions
differ, so a correlation on one row is not a competitor leaderboard.

| Reference / metric | Available baseline | Decisive limitation |
| --- | --- | --- |
| TTCW creative-writing experts, 36 AI stories, expert YES fraction over 14 tests | Story-rank Spearman: Grok 0.7479, Sol 0.6956. Frozen trial-15 weights fell to 0.6904/0.6236 and failed both gain bounds. | No competing rubric scored on these same expert labels in the public aggregate; source-assessor index mapping remains unresolved. |
| Spanish literary experts, 60 GPT-4 synopses | All-one baseline Spearman: Grok 0.30 (bootstrap lower 0.07), Sol 0.27 (lower 0.03). | Joint ≥0.30 endpoint criterion failed; Spanish synopsis judgment is not English publishing-editor confirmation. |
| Dryad regular readers, selected twelve DEV stories | Baseline novelty/usefulness Spearman: Grok 0.5245/0.4266; Sol 0.4476/0.3636. Trial-15 point estimates rose, but both frozen bootstrap gain lower bounds were zero, so the candidate was rejected. | Regular readers; owner-filtered DEV, not full-100 admission or independent confirmation. |
| LAMP professional-writer preferences | 94 triplets have usable opened judgments, but no full canonical `prose.short_form` expert-alignment improvement is established. | The five-module diagnostic is not the product bundle. A 38-leaf exact partial challenge on 48 triplets changed pair credit Grok 74→75/144 and Sol 81.5→79.5/144; all 288 scores are provisional at ≈0.16 candidate coverage, below 0.88. No promotion. |

Private provider-free mapping audit R395 SHA-256
`ae737ede6b554f29d79be2b4fadfeea464c99a83a552583ef70069dea8bc3846`
and exact partial-score challenge R396 SHA-256
`b351c2a37028cd6206b53b059aec06c49cc76b9438b1fdc6cf663fb00b99f746`
bind the last row. They do not confer full-bundle or release authority.

Score extremes are threshold-specific: on TTCW, neither endpoint/profile had
a score ≤10 or ≥90 among 36 stories. The Spanish expert baseline had no
**exact** 0 or 100 among 60, which is not the same threshold. On Dryad's
selected twelve, baseline/candidate each had Grok one ≤10 and zero ≥90,
and Sol zero ≤10 and one ≥90. Mean absolute Grok–Sol score distance was
8.95 on TTCW baseline, 6.36 on Spanish, and 20.38 on Dryad's twelve
(22.15 for its rejected candidate). These are endpoint score gaps, **not**
inter-judge agreement coefficients. TTCW human test-level pairwise agreement
was 0.7037 across 504 story × test cells; no same-assessor repeat estimate
is available there.

The eleven-item/five-repeat/six-arm local panel is the only same-reference
competitor-rubric screen, but the HBQ-RS version **and item set** changed:
current 1.2.1 has five items (descriptive human-reference Spearman −0.8721);
old 1.0.0 has six (0.7143). Pooled eleven-item Cambridge 0.6287, NAPLAN
0.6256, Oregon 0.0320, compact 0.5000 and holistic 0.5000 are small,
version-mixed, often two-distinct-item summaries, **not** fair current
head-to-head expert results. The panel's pooled two-version HBQ-RS leaf
pairwise repeat agreement was 0.8918; a separate historical one-story
five-repeat Sol probe was 1695/1780 = 0.9522, with 0/5 HBQ score ceilings
versus NAPLAN 5/5, Oregon 5/5, Cambridge 3/5. No current-version-only
multi-item intra-judge estimate or same-expert-cohort competitor floor/
ceiling series is established. See the
[repeatability package](../evaluation-results/hbq-multisample-repeatability-v1-completed-result-v1/).
On the separate WPB compact-family development subset, Grok won 10/24
selected DEV pairs and unchanged-fit Sol won 11/24; confirmation stayed
closed. The [WPB authors' full 1,200-pair English leaderboard](https://github.com/WritingPreferenceBench/Writing-Preference-Bench)
reports Doubao 68.7%, Gemini 65.7%, Claude 61.0%, and o3 48.1% on a
different scope. These numbers share a *source* of human labels, not the
same selected pair set, full HBQ-RS rubric, or floor/ceiling measure; they
cannot rank CWR against those models.

### Additional open human-judgment sources to evaluate

“Open” means a public data location, not automatic permission to publish
source passages or train a commercial product. Counts below describe source
judgments, not new labels we collected; overlap, exact license, and artifact
schema must be checked before ingestion.

| Source and status | Scale and judgment type | Assessor qualification / reuse |
| --- | --- | --- |
| [MFA author-style pair study](https://github.com/tuhinjubcse/Author-Style-Personalization) — **new lead** | 240 human–AI excerpt pairs; **1,440 derived expert decisions** (150 + 90 pairs × 3 MFA readers × quality/style outcomes), within 10,920 total reader-level decisions. Pairwise quality and stylistic fidelity. | 28 MFA-trained readers in the study; three rate each pair. Public anonymized JSON explicitly restricted to non-commercial research because passages include copyrighted material. The 1,440 count is derived from the [paper design](https://arxiv.org/html/2510.13939v4), not yet verified against downloaded rows. Strong relative-quality fit, weak direct leaf supervision. |
| [Pron vs Prompt](https://github.com/grmarco/pron-vs-prompt) — **already held** | 180 synopses; 720 expert evaluation rows, with multiple 0–3 creativity/literary dimensions and authorship judgments; 180 selected rows admitted in our Spanish analysis. | Six critics/scholars ([paper](https://aclanthology.org/2024.emnlp-main.1096/)); no explicit source-data reuse license found. One author, synopsis task, Spanish/English; not new independent labels. |
| [WritingPreferenceBench](https://github.com/WritingPreferenceBench/Writing-Preference-Bench) — **1,200 English pairs already held**, 600 Chinese pairs not in our English selection | 1,800 retained preference pairs across 51 categories, 0–3 creativity ratings, three annotators per pair and at least two agreeing. | Eleven calibrated annotators described as experts, but their publishing/writing credentials are not established. Repository lists ODC-BY; English chosen/rejected mean lengths 1,450/840 words despite a length-matching claim, requiring control. |
| [HANNA](https://github.com/dig-team/hanna-benchmark-asg) — known auxiliary source | 1,056 stories × 3 raters × 6 dimensions = 19,008 crowd ratings. | Mechanical Turk, not professional writers; MIT repository license. Useful criterion overlap, not editor confirmation. |
| [StoryER](https://github.com/sairin1202/StoryER) — new auxiliary lead | 9,112 AMT submissions over 5,964 stories, with aspect ratings/comments; 100k Reddit-vote-derived pairs separately. Published 45,948 comment/rating rows include 17,849 augmented Reddit comments, not all direct human labels. | Crowd/Reddit rather than experts; [paper](https://aclanthology.org/2022.emnlp-main.114/). Check source rights and augmentation fields. |
| [Style Similarity Dataset](https://github.com/style-dataset/style-dataset) — new auxiliary lead | 21,630 excerpt triplets; 66,061 filtered good-faith crowd choices with style intensity/rationale (150,720 raw submissions). | Narrow style construct, not quality/editor labels; copyrighted Kindle-preview excerpts and no clear data license found. |
| [LitBench train/test](https://huggingface.co/datasets/SAA-Lab/LitBench-Train) — known weak proxy | Paper reports 43,827 training preference pairs and 2,480 test pairs; hosted test split currently shows 2,381 rows, unresolved. | Reddit votes, not expert judgments; source-comment rights and rehydration constraints remain. Do not infer professional alignment from its pair count. |

Only the MFA study adds clearly credentialed and readily located expert
*reader* pair judgments not already in this inventory. It does not replace
a clean independent publishing-editor panel. Pron is already used; WPB is
already present but its labeler credentials are weaker than its name implies.
This search did not verify a downloadable LiteraryTaste label file/license,
so that paper's described preferences are not counted as obtainable data.

## Bibliography

- **`cho_et_al_2026_bineval`** — Sangwoo Cho, Kushal Chawla, Pengshan Cai, Zefang Liu, Chenyang Zhu, Shi-Xiong Zhang, and Sambit Sahu (2026). [Ask, Don't Judge: Binary Questions for Interpretable LLM Evaluation and Self-Improvement](https://arxiv.org/abs/2606.27226). Atomic yes/no decomposition, interpretable aggregation, reduced ceiling effects, and question-level diagnostic feedback.
- **`zhang_et_al_2026_rubricbench`** — Qiyuan Zhang et al. (2026). [RubricBench: Aligning Model-Generated Rubrics with Human Standards](https://arxiv.org/abs/2603.01562). Expert-authored atomic rubrics outperform self-generated rubrics on hard comparisons; supports a curated registry and validation layer.
- **`rao_callison_burch_2026_autorubric`** — Autorubric authors (2026). [Autorubric: A Unified Framework for Rubric-Based LLM Evaluation](https://arxiv.org/abs/2603.00077). Weighted binary/ordinal/nominal criteria, judge ensembles, calibration, position shuffling, psychometric reliability, and production infrastructure.
- **`fein_et_al_2026_litbench`** — Daniel Fein, Sebastian Russo, Violet Xiang, Kabir Jolly, Rafael Rafailov, and Nick Haber (2026). [LitBench: A Benchmark and Dataset for Reliable Evaluation of Creative Writing](https://aclanthology.org/2026.eacl-long.362/). Creative-writing judge reliability, pairwise human preference, and caution against assuming zero-shot judges are authoritative.
- **`longjudgebench_2026`** — J. Chen et al. (2026). [Benchmarking LLM-as-a-Judge for Long-Form Output Evaluation](https://arxiv.org/abs/2606.01629). Long-form judging requires document-level organization, cross-section consistency, coverage, hierarchical evidence, and bias/overflow controls.
- **`wu_et_al_2025_writingbench`** — Yuning Wu et al. (2025). [WritingBench: A Comprehensive Benchmark for Generative Writing](https://arxiv.org/abs/2503.05244). Query-dependent style, format, and length criteria across varied writing operations.
- **`vaezi_rezaei_2018`** — Maryam Vaezi and Saeed Rezaei (2018). [Development of a rubric for evaluating creative writing: a multi-phase research](https://doi.org/10.1080/14790726.2018.1520894). Expert-informed, reliability-tested fiction rubric covering voice, characterization, story, setting, atmosphere, language, dialogue, plot, and image.
- **`carey_davidow_williams_2022`** — Michael D. Carey, Shelley Davidow, and Paul Williams (2022). [Re-imagining narrative writing and assessment: a post-NAPLAN craft-based rubric for creative writing](https://doi.org/10.1007/s44020-022-00004-4). Integrated craft-based assessment and a holistic whole-text orientation.
- **`gomez_rodriguez_williams_2023`** — Carlos Gómez-Rodríguez and Paul Williams (2023). [A Confederacy of Models: a Comprehensive Evaluation of LLMs on Creative Writing](https://aclanthology.org/2023.findings-emnlp.966/). Creative-writing dimensions, task-specific rubric adaptation, human evaluation, originality and humor findings.
- **`li_et_al_2026_poemetric`** — Bingru Li, Han Wang, and Hazel Wilkinson (2026). [POEMetric: The Last Stanza of Humanity](https://arxiv.org/abs/2604.03695). Poetry form accuracy, theme, creativity, lexical diversity, idiosyncrasy, emotional resonance, imagery, devices, and overall quality.
- **`zhuang_et_al_2025_vistorybench`** — C. Zhuang et al. (2025). [ViStoryBench: Comprehensive Benchmark Suite for Story Visualization](https://arxiv.org/abs/2505.24862). Character consistency, style similarity, prompt alignment, aesthetic quality, and copy-paste artifact detection.
- **`lin_et_al_2026_storybook_consistency`** — Visual narrative consistency researchers (2026). [Benchmarks for Faithful and Consistent Visual Narratives](https://arxiv.org/abs/2503.20871). Narrative alignment, time, space, character, event, style, and theme continuity across image sequences.
- **`galdino_et_al_2025_prosody_review`** — Speech prosody evaluation researchers (2025). [Prosody evaluation literature for speech synthesis](https://arxiv.org/search/?query=prosody+evaluation+speech+synthesis&searchtype=all). Pitch, timing, intensity, rhythm, intelligibility, naturalness, and context-appropriate delivery.
- **`real_world_voice_eq_bench_2026`** — Daniel Ayllon et al. (2026). [RW-Voice-EQ Bench: A Real World Benchmark for Evaluating Voice AI Systems](https://arxiv.org/abs/2607.14846). Acting/role fit, expressiveness, voice identity, language stability, reliability, long-form stability, and acoustic quality.
- **`chung_et_al_2025_literarytaste`** — LiteraryTaste authors (2025). [LiteraryTaste: Revealed Reader Preferences for Literary Text](https://arxiv.org/search/?query=LiteraryTaste&searchtype=all). Separating craft assessment from user-specific revealed taste and learning preference from actual choices.
- **`rubric_survey_2026`** — Rubric survey authors (2026). [From Holistic Evaluation to Structured Criteria: Rubrics Across the Evolving LLM Landscape](https://arxiv.org/abs/2606.08625). Taxonomy of rubrics, independent verifiability, and evidence that expert criteria outperform generated criteria.
- **`researchrubrics_2025`** — ResearchRubrics authors (2025). [ResearchRubrics: A Benchmark of Prompts and Rubrics for Deep Research](https://arxiv.org/abs/2511.07685). Expert fine-grained criteria and evidence that binary grading reduces partial-credit ambiguity.
- **`evidence_grounded_judges_2026`** — Rulers authors (2026). [Evidence-Grounded Text Evaluation with LLM Judges](https://arxiv.org/abs/2601.08654). Evidence grounding, stable score distributions, and robustness to rubric perturbation.
