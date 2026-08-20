# Research synthesis and rubric-design rationale

    ## Executive conclusion

    Creative-writing evaluation benefits from analytic decomposition, but it fails when the evaluator mistakes decomposition for objectivity. The strongest design is therefore hybrid: explicit constraints and observable craft are represented as atomic binary questions; genuinely holistic artistic success and personal taste remain small, clearly labeled components; long works are evaluated hierarchically; and close finalists receive position-controlled pairwise adjudication.

    The registry in this package is intentionally static and human-curated at its core. It can generate task-specific questions from a prompt, but those dynamic questions are limited to explicit requirements and must pass an atomicity, observability, duplication, and conflict check. This choice follows the finding that expert-authored rubrics remain substantially better than unconstrained model-generated rubrics on hard cases.

    ## 1. Existing creative-writing rubrics

    Vaezi and Rezaei developed a fiction rubric through literature review, a modified Delphi process, expert interviews, and review by distinguished creative-writing professors. Their final analytic rubric covered narrative voice, characterization, story, setting, mood and atmosphere, language and mechanics, dialogue, plot, and image, with inter-rater and intra-rater reliability testing. The present registry retains those areas but separates owner domains more sharply and adds scope, project state, operation, and AI-pattern controls.

    Carey, Davidow, and Williams argued for a craft-based post-NAPLAN rubric that treats narrative writing as an integrated artistic act rather than a school checklist. Gómez-Rodríguez and Williams later adapted that tradition to LLM creative-writing evaluation, combining holistic readability, narrative elements, mechanics, plot logic, originality and cliché avoidance, and prompt-specific style, genre, character, action, and humor criteria. Their work supports both a stable craft core and task-specific overlays.

    Educational rubrics are useful mainly for their repeated convergence on cohesion, voice, originality, genre/form awareness, language facility, mechanics, thematic insight, and whole-text function. Their common weakness is coarse rating bands and an assumption that every artifact is a complete school assignment. HBQ-RS replaces those broad bands with binary leaves, adds evidence and scope controls, and distinguishes excerpts from complete works.

    ## 2. Why binary questions

    BinEval reframes evaluation as a set of small, checkable questions rather than one broad score. Across summarization, dialogue, and factual-consistency benchmarks, it matched or exceeded strong baselines, produced score distributions closer to humans, and reduced ceiling effects. The important mechanism is not merely binary output: it is the reduction of criterion complexity, explicit failure-mode coverage, and aggregation of independently answered propositions.

    Binary questions are especially useful for creative-generation systems because they produce actionable diagnostics for writers, judges, and training pipelines. “Is the voice good, 7/10?” is difficult to repair. A set of questions about narrator ownership, register drift, generic assistant phrasing, sentence rhythm, and project-style fidelity can drive targeted regeneration or editing.

    There is a limit. Some qualities—overall artistic life, comic timing, felt inevitability, beauty, or whether a piece is worth keeping—cannot be made fully objective by multiplying questions. Over-decomposition can make an evaluator harsh in the wrong way, penalize legitimate ambiguity, and obscure interaction among parts. HBQ-RS therefore reserves one cumulative holistic ladder and keeps user taste separate from craft.

    ## 3. Curated registry versus generated rubrics

    RubricBench contains 1,147 difficult pairwise comparisons with expert-annotated atomic rubrics derived from instructions. It finds a substantial gap between human and model-generated rubrics. Related rubric surveys report an approximately 27-point improvement in judge performance when expert criteria replace generated ones on that benchmark. This is the principal reason a consumer should not ask a model to invent its full rubric for every request.

    Dynamic criteria still have a legitimate role. WritingBench shows value in query-dependent assessment of style, format, and length. The compromise used here is a stable, versioned registry plus an ephemeral task module generated only from the current brief, sources, and declared profiles. The dynamic module cannot create new taste preferences after inspecting candidates.

    Autorubric contributes production lessons: per-criterion evaluation, configurable weights, mixed criterion types, judge ensembles, verdict-balanced few-shot calibration, option shuffling, verbosity controls, and psychometric reliability metrics. HBQ-RS uses binary scored leaves as its default but preserves diagnostic and hard-gate types, supports judge ensembles, and includes reliability data in run reports.

    ## 4. Creative-writing judge reliability

    LitBench provides 43,827 training pairs and a 2,480-pair test set derived from human preferences. Its strongest tested off-the-shelf judge reached 73% agreement, while specialized reward models reached 78%. That is useful performance, but far from authority. Automated scores should support selection and diagnosis, not masquerade as ground truth.

    LitBench also reinforces the value of pairwise preference for finalists. Absolute criteria catch compliance and identifiable craft defects; pairwise comparison is often better at choosing between two competent pieces whose tradeoffs are hard to express as scalar deltas. HBQ-RS uses absolute binary evaluation first and pairwise adjudication only after eligibility and evidence checks.

    Reader preference is not identical to craft. Revealed-preference research indicates that readers differ substantially and that broad stated preferences predict actual choices imperfectly. The package therefore keeps a `User taste and project preference` overlay separate. The application can learn it from accepted suggestions, edits, rerolls, pairwise choices, and explicit current settings without retroactively redefining objective defects.

    ## 5. Long-form evaluation

    LongJudgeBench demonstrates that long-form judging is qualitatively different, not just longer. Candidate outputs average roughly 9,250 tokens and require organization, cross-section consistency, coverage, and depth. Current judges remain unstable; rubrics and references help but do not solve the problem. Position bias, context overflow, and safety rejection can invalidate runs.

    The full-manuscript protocol in this package therefore combines a whole-work map, thread and state ledgers, opening-to-ending comparison, stratified local sampling, recurring-pattern detection, and distant retrieval checks. It reports evidence coverage and score intervals. A manuscript grade is not the average of chapter grades, because a locally smooth manuscript can still have a broken global arc, missing payoff, repeated middle, or contradictory state.

    ## 6. Poetry and fixed form

    POEMetric evaluates form accuracy and theme alignment alongside creativity, lexical diversity, idiosyncrasy, emotional resonance, imagery, literary devices, overall quality, and likely authorship. In its study, leading models performed well on form and theme but remained well behind human poets on advanced creative dimensions and overall quality. This is a useful warning for an app: automatic syllable, meter, and rhyme checks are necessary for requested fixed forms, but they are not close to sufficient.

    The poetry system therefore includes a general poetry core, named fixed-form modules, poetry-scale overlays, and controlled penalties for purple language and empty repetition. It includes strict and contemporary English-haiku profiles. The strict profile enforces 5–7–5; the contemporary profile does not confuse Japanese morae with English syllables or require seventeen syllables by default. Both retain seasonal field, cut/juxtaposition, immediacy, and compression. The sonnet module supports Shakespearean, Petrarchan, Spenserian, Miltonic, and contemporary profiles with separate architecture, meter, rhyme, volta, and language groups.

    ## 7. Visual storytelling and illustration

    ViStoryBench evaluates character consistency, style similarity, prompt alignment, aesthetic quality, and generation artifacts such as copy-paste behavior, with human validation. Related visual-narrative work emphasizes time, space, character, event, style, theme, clothing/prop attributes, and background anchors across a sequence.

    The package adds rubrics for scene illustration, portraits, design sheets, environments, covers, maps, storyboards, comics, and sequence continuity. These are not generic “pretty image” ratings. They check narrative event, canon state, persistent attributes, spatial logic, production function, typography where relevant, and artifacts. Cross-modal canon has one owner so character eye color is not independently scored in three modules.

    ## 8. Narration, performance, and audio

    Voice evaluation increasingly separates linguistic content from paralinguistic competence. RW-Voice-EQ profiles acting and role fit, expressiveness, voice identity, language stability, reliability, long-form stability, and acoustic quality rather than collapsing them into one mean. Speech-prosody research additionally centers pitch, duration, intensity, rhythm, phrasing, and intelligibility.

    The audio registry therefore includes source-text fidelity, naturalness, prosody, role fit, character identity, pronunciation, long-form drift, audio-drama intelligibility, and mastering. A narration can be acoustically clean but dramatically wrong, or expressive but unstable over a chapter; the profile must preserve those distinctions. Multimodal packages add text–image and text–audio alignment, cross-modal canon, asset placement, and accessibility metadata.

    ## 9. Bias, calibration, and evidence

    LLM judges can prefer whichever candidate appears first, longer answers, more polished formatting, styles resembling their own output, or references placed in suggestive positions. Long inputs also create truncation and retrieval failure. Production evaluation should therefore shuffle pairwise order, blind irrelevant identity, record the exact judge and prompt version, repeat important judgments, and monitor agreement with human decisions.

    Evidence-grounded evaluation improves auditability. Every material NO verdict should point to a span or asset region; every YES on a hard gate should be supportable. The system requests concise evidence and explanation, not long chain-of-thought. Verbose rationales can become post hoc stories and consume context that should be used for the artifact itself.

    ## 10. Refinements over the earlier rubric family

    The new system makes the following structural changes:

    - replaces 1–5 or 1–10 line items with atomic positive binary leaves;
    - separates hard eligibility from artistic quality;
    - introduces N/A and cannot-assess control states;
    - reports coverage and score intervals;
    - gives every criterion one owner;
    - keeps a small cumulative holistic component;
    - separates user taste from craft;
    - treats excerpts and incomplete artifacts explicitly;
    - rewards form-appropriate length;
    - raises and formalizes purple-prose and repetition penalties;
    - adds AI-pattern, optionality-without-commitment, and sampler-artifact controls;
    - adds complete visual, audio, and multimodal registries;
    - adds long-context and full-manuscript protocols;
    - adds operation rubrics for ideation, outlining, continuation, critique, selection, revision, research, ingestion, and project maintenance;
    - adds meta-rubrics for rubric quality and judge behavior.

    ## 11. Limitations and validation plan

    This package is a researched design and implementation baseline, not a claim of universal psychometric validation. Most individual questions have not yet been calibrated against a large expert-labeled corpus. The next empirical stage should collect blinded human verdicts on representative application tasks, measure per-question prevalence and agreement, remove low-information or unreliable questions, fit bundle weights, and test selection accuracy against real user choices.

    Recommended measurements include balanced accuracy and macro-F1 for binary leaves, Cohen or Fleiss kappa for agreement, calibration error, score-distribution comparison, pairwise preference accuracy, position/length/style bias tests, test–retest stability, and downstream utility: whether selected or revised artifacts are actually accepted more often by users.

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
