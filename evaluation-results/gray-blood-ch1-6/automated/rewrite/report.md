# Long-form evaluation

College student Madison falls rapidly for Amelia, then discovers that her lover is a blood-drinking witch whose symbolic magic, lethal history, and morally gray community are as alluring as they are horrifying.

**Evaluated scope:** One blank front-matter unit followed by six substantive novel chapters, from Madison meeting Amelia through Madison beginning formal study of magical symbols.

## Reader orientation

- **Madison:** Nineteen-year-old programmer and first-person narrator whose romance with Amelia draws her into magic and moral danger.
- **Amelia:** Twenty-eight-year-old witch, former paramedic, and Madison's lover; powerful, affectionate, secretive, and morally compromised.
- **June:** One of Amelia's three mothers; an approximately 150-year-old witch with a nurturing manner.
- **Savannah:** Amelia's legal mother and family authority figure who monitors consequential magic.
- **Emma:** Amelia's third mother and her mothers' platonic life partner.
- **Mackenzie:** Combative FAWN witch and molecular-biology postdoc researching stored blood.
- **Miriam:** FAWN witch who develops spells and shares a protective bond with Zoe.
- **Zoe:** Human FAWN member who befriends Madison and explains additional magic mechanics.
- **Olivia:** Human FAWN member who wants to become a witch.
- **Evelyn:** Human FAWN member participating in its research and social circle.
- **Julia:** Madison's former girlfriend and continuing confidante, unaware of magic.
- **The climber:** Mortally injured stranger whose death exposes Amelia's witchcraft to Madison.

## How to read the results

- **Control state** reports only objective, explicit binding requirements and whether enough evidence exists to decide them. Author preferences and aesthetic goals are weighted criteria, not gates.
- **Coverage** is the weighted share of applicable selected criteria that received a YES or NO verdict.
- **Observed score** is the deterministic score from relevant criteria that received a YES or NO verdict.
- **Uncertainty bounds** are the non-statistical lowest and highest scores still possible if unassessed relevant criteria later resolve as failures or passes. They are not a confidence interval.
- Local unit scores are independent diagnostics. They remain separate unless an explicit hierarchical score profile is shown below.
- **Work-in-progress rule:** criteria that require an unavailable finished work are NOT_APPLICABLE, not failures. Craft, continuity, applicable explicit requirements, and weighted goals are still evaluated on the supplied scope.

## Route

Whole-work bundle `prose.novel` with 29 selected modules, 12 weighted author goals, and 6 binding requirements.
Local bundle `prose.chapter`; selection mode `scope_auto`.
Declared completion status: `work_in_progress`.
Local coverage is complete across all 6 substantive deterministic units.
1 brief non-prose front-matter unit(s) remain in the whole-work evaluation but are omitted from local diagnostics.

## Whole-work result

| Scope | Control state | Coverage | Observed score | Uncertainty bounds |
|---|---:|---:|---:|---:|
| Whole work | VALID | 97.8% | 74.1 | 72.2–74.4 |

### Whole-work components

| Component | Coverage | Observed score | Uncertainty bounds |
|---|---:|---:|---:|
| Task and scope | 83.8% | 5.3 | 4.5–5.6 |
| Character and arcs | 93.3% | 14.9 | 13.9–14.9 |
| Plot architecture and payoff | 100.0% | 18.8 | 18.8–18.8 |
| World and continuity | 100.0% | 10.4 | 10.4–10.4 |
| Pacing and information | 100.0% | 6.3 | 6.3–6.3 |
| Language and voice | 100.0% | 5.8 | 5.8–5.8 |
| Theme and effect | 100.0% | 6.5 | 6.5–6.5 |
| Freshness and economy | 100.0% | 2.4 | 2.4–2.4 |
| Mechanics | 100.0% | 1.6 | 1.6–1.6 |
| Holistic artistic success | 100.0% | 6.0 | 6.0–6.0 |

## Local units

| Unit | Control state | Coverage | Observed score | Uncertainty bounds |
|---|---:|---:|---:|---:|
| Chapter 1 | VALID | 99.7% | 77.4 | 77.1–77.4 |
| Chapter 2 | VALID | 100.0% | 78.6 | 78.6–78.6 |
| Chapter 3 | VALID | 99.7% | 84.0 | 83.7–84.0 |
| Chapter 4 | VALID | 99.5% | 92.2 | 91.8–92.3 |
| Chapter 5 | VALID | 100.0% | 90.7 | 90.7–90.7 |
| Chapter 6 | VALID | 99.2% | 88.4 | 87.7–88.4 |

## Hierarchical score (explicit profile)

Profile `balanced-wip-70-30` combines existing intervals only; it makes no model call and does not replace control states, completion handling, or the underlying whole-work and local results.
Local reducer: `weighted_mean`.

| Result | Observed score | Uncertainty bounds |
|---|---:|---:|
| Hierarchical score | 77.4 | 76.0–77.7 |

| Component | Requested weight | Effective weight | Observed score | Uncertainty bounds |
|---|---:|---:|---:|---:|
| Whole work | 7 | 70.0% | 74.1 | 72.2–74.4 |
| Local `weighted_mean` | 3 | 30.0% | 85.2 | 84.9–85.2 |

Ordinary units have equal weight 1. Shared unfinished and prologue/epilogue modifiers are normalized over the evaluated local units.

| Unit ID | Weight class | Class modifier | Effective local weight |
|---|---|---:|---:|
| `unit-0002-920c59af6477` | `ordinary` | 1 | 16.7% |
| `unit-0003-aa9f0ac01ee1` | `ordinary` | 1 | 16.7% |
| `unit-0004-39a17c40720a` | `ordinary` | 1 | 16.7% |
| `unit-0005-febc528a057c` | `ordinary` | 1 | 16.7% |
| `unit-0006-07454b12a420` | `ordinary` | 1 | 16.7% |
| `unit-0007-b80e8306ee58` | `ordinary` | 1 | 16.7% |

## Findings

### Observation: This is an unfinished six-chapter novel opening about Madison, a nineteen-year-old programmer whose rapid romance with Amelia exposes a world of blood-drinking witches, symbolic magic, FAWN research, lethal power, and contested consent. The supplied movement ends with Madison physically weakened but voluntarily entering magical study while the relationship remains loving and morally unstable.

The evaluation covers the supplied opening movement, not the planned novel. Revision should strengthen what these chapters establish without forcing final closure or resolving future arcs prematurely.
 Evidence: `evidence-0001`, `evidence-0002`, `evidence-0012`.
 Criteria: `core.task_and_brief_fidelity.completion_flag`, `craft.narrative.characterization.dimensionality`, `form.prose.general_prose_fiction.movement`.

### Observation: Every score report has control state VALID. The whole-work observed score is 74.0536, with non-statistical bounds of 72.2044–74.4024 and coverage 0.978. Independent local results are: Chapter One 77.3678 (77.0926–77.4448); Chapter Two 78.5622; Chapter Three 84.0157 (83.6775–84.0297); Chapter Four 92.2371 (91.7524–92.2595); Chapter Five 90.6757; and Chapter Six 88.4106 (87.6519–88.4443).

These chapter scores are separate diagnostics, not values to average. The whole-work result governs systemic conclusions, while each local result identifies where revision pressure is concentrated.
 Evidence: `evidence-0001`, `evidence-0002`, `evidence-0011`, `evidence-0012`, `evidence-0015`, `evidence-0016`.
 Criteria: `scope.long_context.overflow`, `core.holistic_artistic_success.threshold_1_functional`, `core.holistic_artistic_success.threshold_2_effective`, `core.holistic_artistic_success.threshold_3_keepworthy`, `core.holistic_artistic_success.threshold_4_exceptional`.

### Strength: All five applicable objective, non-negotiable canon gates pass: depicted witches are female, activation requires beginning consumption of a beating heart, engravings require and wholly consume one lifeblood source, and magic operates through drawn symbols. Witch–human-male offspring is NOT_APPLICABLE because that conception does not occur in scope.

These are the actual hard gates. Tightening tone, pacing, or prose should preserve these mechanisms exactly and should not manufacture a reproduction example merely to activate an otherwise inapplicable check.
 Evidence: `evidence-0003`, `evidence-0004`, `evidence-0005`, `evidence-0006`, `evidence-0007`.
 Criteria: `task.contract.gray-blood-ch1-6-comparison-v1.canon.witches_female_only`, `task.contract.gray-blood-ch1-6-comparison-v1.canon.activation_requires_heart`, `task.contract.gray-blood-ch1-6-comparison-v1.canon.witch_human_offspring_human`, `task.contract.gray-blood-ch1-6-comparison-v1.canon.engraving_requires_lifeblood`, `task.contract.gray-blood-ch1-6-comparison-v1.canon.engraving_consumes_one_source`, `task.contract.gray-blood-ch1-6-comparison-v1.canon.magic_uses_drawn_symbols`.

### Strength: The six chapters form a strong causal opening movement: concealed medical competence matters during the climber crisis; witnessed killing drives biological disclosure; campus magic leads to FAWN; independent access to magic changes Madison’s romantic choice; and engraving costs lead to quantified moral accounting. The relevant binary verdicts are YES for long causality, development, available payoff, local arc contribution, and progress.

This causal spine is the manuscript’s most reliable asset. Compress scenes around these irreversible turns while preserving the sequence of clue, decision, consequence, and changed state.
 Evidence: `evidence-0017`, `evidence-0018`, `evidence-0023`, `evidence-0024`, `evidence-0028`, `evidence-0029`, `evidence-0033`, `evidence-0002`.
 Criteria: `form.prose.novel.long_causality`, `form.prose.novel.development`, `form.prose.novel.payoff`, `craft.narrative.character_arc.local_contribution`, `craft.narrative.narrative_momentum.progress`.

### Strength: Several high-weight author goals score YES. Madison visibly grapples with killing, activation, coercion, and lifeblood; her programmer mindset becomes a method for modeling magic; fascination competes with alarm strongly enough to establish a darker trajectory; activation lands as lasting trauma; and Amelia’s affection coexists with addiction, lethal power, and morally uneasy attraction to blood.

These priorities give the project its distinctive long-range engine. Revision should retain Madison’s escalating system-building and ensure each new technical insight also creates an ethical or relational cost.
 Evidence: `evidence-0004`, `evidence-0050`, `evidence-0051`, `evidence-0052`.
 Criteria: `task.contract.gray-blood-ch1-6-comparison-v1.goal.madison_moral_grappling`, `task.contract.gray-blood-ch1-6-comparison-v1.goal.madison_programmer_lens`, `task.contract.gray-blood-ch1-6-comparison-v1.goal.madison_dark_path_setup`, `task.contract.gray-blood-ch1-6-comparison-v1.goal.activation_as_trauma`, `task.contract.gray-blood-ch1-6-comparison-v1.goal.amelia_power_attraction`, `task.contract.gray-blood-ch1-6-comparison-v1.goal.amelia_affection_power_balance`.

### Revision Priority: The largest systemic weighted-goal miss is tonal. Sustained giggling, reassurance, romantic comedy, guilt, and apology produce NO verdicts for grim-dark tone, controlled volatility, reduced apologetic framing, tonal fit, project fidelity, and characterization fidelity. Whether Amelia is darker than the earlier WIP is formally CANNOT_ASSESS because that baseline was not supplied, but her absolute presentation still conflicts with the stated direction.

Revise Amelia across all six chapters, not only at violent peaks: replace apology loops with concise factual admissions, darker amusement, pragmatic self-justification, or controlled silence. Preserve genuine affection, but make warmth a choice, mask, or costly exception rather than her default register.
 Evidence: `evidence-0004`, `evidence-0005`, `evidence-0011`, `evidence-0015`, `evidence-0016`, `evidence-0048`, `evidence-0049`.
 Criteria: `task.contract.gray-blood-ch1-6-comparison-v1.goal.grim_dark_tone`, `task.contract.gray-blood-ch1-6-comparison-v1.goal.amelia_darker`, `task.contract.gray-blood-ch1-6-comparison-v1.goal.amelia_volatility`, `task.contract.gray-blood-ch1-6-comparison-v1.goal.amelia_less_apologetic`, `core.audience_and_purpose_fit.tone`, `core.voice_and_stylistic_identity.project_fidelity`, `craft.narrative.characterization.canon`.

### Strength: The blood-magic system is specific, consistent, constrained, and consequential. Strongholds, blood potency, intent, activation, freework, engraving, stored blood, coercion, and programming analogies produce YES verdicts across rules, consistency, constraints, consequences, non-default worldbuilding, and unpredictable specificity.

This system distinguishes the novel from generic vampire or witch fiction. Keep the rules and costs, but increasingly teach them through failed attempts, tactical choices, bodily effects, or disagreement rather than reference-style explanation.
 Evidence: `evidence-0002`, `evidence-0011`, `evidence-0016`, `evidence-0034`, `evidence-0036`, `evidence-0037`, `evidence-0038`.
 Criteria: `craft.narrative.worldbuilding.rules`, `craft.narrative.worldbuilding.consistency`, `craft.narrative.worldbuilding.constraints`, `craft.narrative.worldbuilding.consequences`, `craft.narrative.worldbuilding.no_default_furniture`, `core.freshness_and_non_genericness.unpredictable_specificity`.

### Revision Priority: Pacing and information management are the broadest systemic craft weakness. Binary NOs cluster around extended flirtation, the piano catalog, anatomy and mechanics lectures, repeated explanations, party reactions, reassurance loops, and low-consequence social beats. The whole-work pacing-and-information score is 6.3492, while freshness-and-economy is only 2.3913.

Perform a compression pass organized by dramatic yield: retain the first decisive instance of attraction, explanation, or reassurance; cut equivalent repetitions; convert later mechanics into obstacle-driven demonstrations; and give saved space to activation aftermath, the death-count confrontation, coercion, and Madison’s moral choices.
 Evidence: `evidence-0002`, `evidence-0011`, `evidence-0012`, `evidence-0015`, `evidence-0046`, `evidence-0047`.
 Criteria: `core.length_and_scope_fit.density`, `core.length_and_scope_fit.no_padding`, `craft.narrative.pacing_and_narrative_time.allocation`, `craft.narrative.pacing_and_narrative_time.local_global`, `craft.narrative.pacing_and_narrative_time.no_stall`, `craft.narrative.exposition_and_information_management.embedding`, `craft.narrative.exposition_and_information_management.priority`, `craft.narrative.exposition_and_information_management.no_redundancy`, `craft.narrative.exposition_and_information_management.no_dump`, `craft.narrative.dialogue.no_exposition`, `core.economy_and_relevance.earns_place`, `core.economy_and_relevance.no_restatement`, `core.economy_and_relevance.length_fit`.

### Revision Priority: Copy-level defects are systemic rather than isolated: the verdicts are NO for diction control, syntax, awkwardness, grammar, punctuation, spelling, and cleanliness. The evidence includes malformed constructions, tense and agreement slips, incorrect word choices, inconsistent names, stray characters, and markup debris; the whole-work mechanics score is 1.6.

Run a dedicated mechanical pass after structural cuts. Correct repeated lexical errors globally, normalize names and dialogue punctuation, remove debris, and then read each chapter aloud for missing words, duplicated clauses, and tense drift.
 Evidence: `evidence-0008`, `evidence-0011`, `evidence-0015`, `evidence-0016`.
 Criteria: `core.language_craft.diction`, `core.language_craft.syntax`, `core.language_craft.no_awkwardness`, `core.mechanics_and_presentation.grammar`, `core.mechanics_and_presentation.punctuation`, `core.mechanics_and_presentation.spelling`, `core.mechanics_and_presentation.cleanliness`.

### Risk: Original story-specific material is repeatedly filtered through familiar romantic shorthand, default metaphors, and explanatory emotional summaries. The manuscript therefore scores YES for unpredictable specificity but NO for avoiding clichés, default metaphors, and over-explanation of effects the scene has already conveyed.

Preserve concrete blood, code, medical, and symbolic perceptions while cutting transferable phrases and post-scene interpretation. Let touch, recoil, calculation, silence, or magical cost carry emotion before adding narration.
 Evidence: `evidence-0002`, `evidence-0008`, `evidence-0011`, `evidence-0015`, `evidence-0016`.
 Criteria: `core.freshness_and_non_genericness.no_cliche`, `core.freshness_and_non_genericness.no_default_metaphors`, `core.freshness_and_non_genericness.unpredictable_specificity`, `core.emotional_and_intellectual_effect.restraint`.

### Revision Priority: A localized canon defect remains in explicit ages, aging limits, and institutional demographic benchmarks. Both fact continuity and world continuity receive NO verdicts even though the core magic rules remain stable.

Reconcile the Chapter Four aging exchange and associated demographic figures against the controlling brief, then search the manuscript for every dependent calculation. This is a local canon repair, not a failure of the validated binding gates.
 Evidence: `evidence-0040`.
 Criteria: `craft.narrative.continuity_and_canon_integrity.facts`, `craft.narrative.continuity_and_canon_integrity.world`.

### Risk: The climber’s fatal fall beside a medically qualified witch is the principal isolated causality defect. The NO verdict reflects an unprepared convergence that chiefly exists to force the supernatural revelation.

Seed a causal reason for Amelia and Madison to be near the climber, connect the accident to an established hazard or magical disturbance, or make an earlier character decision materially create the convergence.
 Evidence: `evidence-0015`.
 Criteria: `craft.narrative.plot_and_causality.no_convenience`.

### Observation: The WIP is correctly flagged and ends at a deliberate chapter boundary. Whole-novel macrostructure, final resolution, and final character states are CANNOT_ASSESS rather than failures. Blood batteries, coercive magic, reproduction, Robin, retained lifeblood, activation aftermath, and Madison’s darker trajectory remain purposeful open threads.

Future revision should maintain visible causal pressure on these promises, but the current evaluation does not require their completion or penalize absent Katherine, grimoire, antagonist, or endgame material.
 Evidence: `evidence-0001`, `evidence-0002`, `evidence-0036`, `evidence-0058`.
 Criteria: `core.task_and_brief_fidelity.completion_flag`, `form.prose.novel.macro_structure`, `form.prose.novel.ending`, `craft.narrative.character_arc.end_state`, `craft.narrative.continuity_and_canon_integrity.threads`, `craft.narrative.theme_and_subtext.open_questions`, `penalty.unflagged_incomplete.status`, `penalty.unflagged_incomplete.truncation`.

### Observation: Two lower-weight priorities have different states: chapter-title relevance scores YES, while Katherine’s immediate-visit motivation is CANNOT_ASSESS because she does not appear or announce a visit in the supplied chapters.

Keep the title system where its computational or mathematical relation is legible. Defer judgment on Katherine until her entrance is drafted; her absence here is not a gate failure.
 Evidence: `evidence-0053`, `evidence-0054`.
 Criteria: `task.contract.gray-blood-ch1-6-comparison-v1.goal.katherine_motivation`, `task.contract.gray-blood-ch1-6-comparison-v1.goal.chapter_title_relevance`.

### Observation: Holistically, the manuscript is functional, effective, and keepworthy, but not yet exceptional. Its causal revelations, distinctive magic, moral-romantic conflict, and Madison’s analytical trajectory justify continued development; tonal mismatch, repetition, exposition, looseness, and mechanical defects prevent top-tier finish.

The highest-value revision order is: recalibrate Amelia and the grim-dark register; compress repetition and lectures; complete a rigorous copyedit; then repair the isolated age-canon and climber-convenience defects.
 Evidence: `evidence-0011`, `evidence-0012`, `evidence-0015`, `evidence-0016`.
 Criteria: `core.holistic_artistic_success.threshold_1_functional`, `core.holistic_artistic_success.threshold_2_effective`, `core.holistic_artistic_success.threshold_3_keepworthy`, `core.holistic_artistic_success.threshold_4_exceptional`.

## Limitations

- The evaluated artifact is a work in progress containing blank front matter and Chapters One through Six, not the planned complete novel.
- Future material involving Katherine Henot, Frieda's grimoire, the tracker antagonist, and later FAWN or Madison developments is unavailable; their eventual setup and payoff cannot be assessed here.
- The mechanism of creating witches, Katherine's immediate-visit motivation, and the recursion-versus-Turing-completeness question remain deliberately unresolved project decisions, not contradictions.
- The apparent discrepancy between Amelia's account of Robin's recent departure and FAWN's belief that Robin predates them is unresolved within the supplied scope.
- The opening retrospective frame implies later narration, but the temporal distance and narrator's ultimate circumstances are not supplied.
- Canon checks based on absence—such as no male witches, no activation without a beating heart, and no prohibited witch-human offspring—apply only to the material provided.
- The manuscript is an explicitly incomplete work in progress. Whole-novel ending, macrostructure, final character state, and unavailable future payoffs were not scored as failures.
- Observed scores are distinct from their non-statistical lower and upper bounds. Those bounds reflect unassessed relevant criteria, not sampling error or confidence intervals.
- Local chapter scores are independent diagnostics and were not averaged. Whole-work conclusions come from the global pass.
- Weighted author goals are revision priorities, not hard gates. Only the validated objective, non-negotiable canon requirements were treated as gates.
