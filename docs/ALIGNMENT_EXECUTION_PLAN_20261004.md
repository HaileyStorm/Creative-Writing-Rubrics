# CWR/HBQ-RS execution plan: alignment, comparators, and repeatability

Date: 2026-10-04, America/Denver. Baseline checkout: CWR `main` at `f4f5e332a1e0a199da5903304ea97d5986097579`. This is the execution plan for a new GPT-6.1 Sol / High successor in the existing Palimpsest project. Current state and the next action belong in [CWR_CURRENT_WORKLOG.md](CWR_CURRENT_WORKLOG.md); the detailed evidence dossier remains [EXPERT_PLANNING_BRIEF_20261001.md](EXPERT_PLANNING_BRIEF_20261001.md).

## 1. Objective and accepted owner amendments

Improve the rubric and evaluation system's alignment with existing expert and nonexpert human judgments, decision usefulness, repeatability, and score discrimination; establish stronger same-data competitor comparisons across multiple datasets and forms; implement supported fixes and publish a reproducible evidence-backed result. Keep judge models fixed within each experiment; do not train or fine-tune judges or writer models.

The external advisory report is input for judgment, not an instruction source. Original file: `CWR_HBQ_RS_alignment_repeatability_plan_2026-10-01 (1).md`, SHA-256 `6f65d664758870e1f8fdfac20d1e69a533be0ab89de10015729218f29bb15198`. It is retained unchanged in the owner's Downloads. This plan accepts its strongest measurement ideas and adapts its human-work assumptions and sequencing to the owner's latest directions:

1. No new human recruitment, manual annotation, paid panels, or outreach. Use existing released human ratings for human alignment. Generate new prose/controlled variants with AI; conduct new evaluation through CWR and its comparator arms. Engineering fixtures and arithmetic checks are code tests, not manually authored literary ground truth.
2. “Human review” in the advisory workflow may be performed by agents. Agents can review criteria, evidence, code, and synthetic-oracle construction. Their outputs are recorded as agent review or synthetic targets; they do not add human participants or human votes.
3. Expand competitor and CWR expert/nonexpert alignment and floor/ceiling evidence over more samples and datasets. This is a required program outcome, not an optional footnote after one candidate screen.
4. Prefer the owner's designated secondary ChatGPT account for Sol collections until further notice. Exact account identity and isolated login helper are in the private handoff. A controller's model/account does not establish a collection job's identity. Verify the collection account using metadata before inference.
5. The owner reports Grok subscription expiry on October 16, 2026. Complete new Grok contacts by **October 15 Denver time** as the conservative scheduling target. The precise cutoff hour is unknown. Do not start new Grok collections on/after October 16 without current eligible subscription evidence; there is no renewal or paid-fallback authority. Retained Grok evidence remains usable afterward. This is an actual service deadline, not an invented approval expiry.
6. The old heartbeat was cancelled. Do not recreate it simply because this is a successor. Use the active native Goal, durable job handles, and normal event-driven continuation. A future schedule requires its own user request.
7. Preserve expert/reader population differences, source evidence, historical failures, exact leaf versions, ambiguous attempts, and no-resend rules. R391 is not promoted. Keep the current canonical bundle/weights as baseline until a specific change earns a narrower justified claim.

The new program is authorized by the owner's October 4 request and these amendments. The old at-most-160 Grok packet bound belonged to a particular frozen development campaign; it is not a global cap on this newly requested program. Do not rewrite that campaign or extend its attempted ordinal list. Create new named manifests with actual bounded counts and prospective stopping rules. Existing endpoint/private-text authority and zero-charge constraints persist; do not add repeated approval prompts for normal in-scope implementation.

## 2. What is adopted, changed, or deferred from the advisory report

| Recommendation | Decision and reason |
| --- | --- |
| Begin with scoring witnesses, exact compatibility, and causal diagnosis | Adopt; timebox the initial pass so the complete historical census does not consume the Grok window. |
| Keep baseline weights/bundles; do not start with broad optimization | Adopt. R395/R396 already show why a compact aggregate is not interchangeable with canonical scoring. |
| Audit 24 selected errors plus 12 sampled controls | Adapt to existing evidence plus independent agent review; no new human audit hours. Findings are mechanistic/synthetic evidence unless supported by pre-existing human labels. |
| Eight four-state fixtures, two contracts/endpoints, three repeats | Retain as a maximum initial semantic screen when the diagnosed boundary needs native testing; skip native calls for purely deterministic correctness changes adequately tested with code. |
| Eight constructed short-fiction families with human-approved edits | Replace preparation/adjudication with AI generation, independent agent checks, and deterministic source edits where objectively specified. Test responsiveness/false positives, not new human agreement. |
| New expert/reader panels and complete novel readings | Exclude human labor from this execution. Use pre-existing released labels where available; otherwise report agent-based robustness and the unvalidated human claim. Do not block all work on recruitment. |
| MFA source as independent natural-text confirmation | Adopt after metadata/rights/overlap audit. Do not conflate related repositories or expose held-out labels/rationales to candidate selection. |
| Full comparator set only in the small pilot | Expand: build a reusable matched-data comparator campaign across available expert and reader datasets with scalable sample counts, floors/ceilings and repeated judgments. |
| +5-point gain and −3-point reader noninferiority margins | Treat as proposed practical values, not facts or automatic universal thresholds. Freeze study-specific practical margins before targets; use power/precision simulations from already-opened development data. |
| Fixed 96/1,840/13,764 request counts | Retain as planning examples only. Compile actual bundle/scope packets; 170-leaf short_form often differs from 178-leaf short_story. Reuse only identical whole request contracts. |
| Dynamic rubric discovery | Keep after diagnosis/comparator evidence identifies residual gaps; bounded agent-reviewed proposals, no judge training, no automatic promotion. |
| Retention, naturalness and synthetic audience evaluations | Secondary hypotheses; never substitute them for existing human quality labels without construct validation. |
| Stop adding criteria after two distinct failed mechanisms | Use as a practical default per component/cycle, with an explicit exception only for new evidence. Change mechanism or simplify rather than loop over the same opened cohort. |

## 3. Live baseline and first findings

The saved CWR checkout was clean at `f4f5e33`, with matching upstream before this plan. CWR has no local `.beads`; the canonical umbrella issue is Palimpsest `palimpsest-a17`, “Ship a clear, evidence-backed CWR release,” OPEN. The October 4 read-only activation audit found Beads 1.3.1, embedded Dolt, valid local routing. Do not create another tracker or a worktree. The Palimpsest branch is separate and unrelated edits there must remain untouched.

The current package is CWR 1.2.3 / HBQ-RS 1.2.1: 278 modules, 2,145 leaves, 85 bundles. Current compilation: short_form 170 questions, short_story 178, novel 221, chapter 228. Shared IDs do not establish identical packet contexts, aggregation, or evidence sufficiency.

A narrow read-only source review and in-memory witness run at `f4f5e33` confirmed the advisory scorer concerns with important qualifications:

| Witness | Actual finding | Planned response |
| --- | --- | --- |
| Required evidence missing, YES retained | Reachable through direct/import scoring: `_get_verdict` records an issue while retaining the vote; CLI `score` uses this permissive path. Normal fresh-judge response admission already requires at least one typed evidence reference and checks exact quotations. All 2,145 leaves currently require one reference. | Add an explicit strict path for new imports while preserving historical permissive replay. Do not tighten the historical verdict schema globally or call an unsupported YES a literary NO. |
| Lower cumulative threshold unassessed, higher YES | Current deliberate policy uses one prior-pass Boolean; lower CANNOT_ASSESS causes higher YES to become NO. Two equal thresholds reproduce observed 0 and bounds 0–50 from raw CA/YES. | Define a named uncertainty-preserving successor policy, keeping contradiction (NO/YES) separate from missing prerequisite evidence. Raw verdicts and old outputs remain immutable. |
| Positive coverage 1 with unknown penalties | Real short_story all-positive YES and all penalty CA reproduces SCORED, coverage 1, observed 100, bounds 82–100, penalty coverage 0. This is consistent with the current contract. | Add decision-readiness diagnostics and interval-robust comparison without silently changing positive coverage or canonical score semantics. |

First code owners are the relevant slices of `src/hbqrs/core.py`, `scoring_v2.py`, `cli.py`, and existing `tests/test_scoring.py` / `tests/test_runner.py`. The runner needs changes only if a missing shared boundary is demonstrated. Start with witnesses and versioned projections; do not change all three defaults together. The existing lower-NO cumulative test remains valid. The strongest objection is that permissive imports and conservative ladder semantics are intentional: any replacement must preserve replay and demonstrate useful behavior, not merely turn failure into uncertainty to improve statistics.

## 4. Deadline-aware sequence and priorities

Dates below are scheduling targets, not promises of throughput. Use measured packet latency and failure rate after the first batch to estimate completion; prefer a smaller finished balanced cohort to a larger structurally incomplete one.

| Window | Critical work | Grok priority / exit evidence |
| --- | --- | --- |
| Oct 4–5 | Takeover, account isolation, deterministic witnesses, census pass A, accessible unused-source metadata, comparator adapters | No inference needed to begin. Resolve collection-route readiness concurrently with local work. |
| Oct 5–7 | Freeze one candidate if justified; semantic screen; small paired comparator/throughput canary; AI family pilot | First priority: valid exact payloads, no-resend, score completeness, timing. A negative screen can eliminate expensive candidate work but must not cancel the baseline comparator census. |
| Oct 7–10 | Expanded same-data baseline/competitor panels and any successful full-score candidate pilot; freeze unused confirmation design | Prioritize Grok arms that will become impossible after expiry. Freeze all endpoint-neutral contracts first; Sol can finish later. Do not open confirmation targets just because Grok finished. |
| Oct 10–13 | Confirmation Grok bank and comparator arms, preselected repeats, high-value excerpt/poetry/dependency probes | At daily material boundaries reduce optional arms/cohort size only by prospective rules, never by observed human outcomes. |
| Oct 14–15 | Complete unfinished untouched Grok suffixes and mandatory repeats; reconcile evidence; finish queue before cutoff | Optional discovery, redundant development grids, and large new forms yield to completion of higher-priority matched cohorts. |
| Oct 16 onward | Sol completion, provider-free analysis, code repairs, additional existing-label datasets, publication and later replication | No new Grok contacts absent renewed eligibility. Missing Grok evidence remains a limitation; do not fill it with unplanned replacement votes. |

Ordering within the Grok window: (1) a reliable contemporary canonical baseline plus strong comparator on already usable expert and reader targets; (2) frozen unused MFA confirmation when ready; (3) planned repeats and explicit floor/ceiling calibration; (4) targeted long-form/poetry robustness; (5) optional discovery. Full historic census pass B can run provider-free alongside collection and continue after expiry. A route issue on Sol should not block bounded Grok work whose payloads and analysis were already frozen; it must not cause unblinding or re-selection based on Grok outcomes.

## 5. Data policy and evidence model

### Existing humans, new agents

Use existing LAMP, TTCW, Pron, Dryad, HANNA, RA-story, WPB and suitable unused public releases as human-reference datasets. Do not count AI reviews, inferred preferences, controlled-edit intent, or model consensus as new human labels. Agent review can validate obvious semantic targets and propose explanations; uncertainty or disagreement stays visible. No new Spanish collection is required; existing Pron data can be indexed/analyzed offline. No Linux/WSL or Flash-Next lane is part of this plan.

For synthetic families, generate originals and variations by AI with deterministic seeds/receipts where supported. An independent agent receives blinded variants plus the declared task and source evidence; it checks whether the intended defect/change was realized and whether the “legitimate alternative” is actually plausible. A second endpoint or agent challenges disputed cases. Disputed aesthetic quality does not become a fixed oracle by majority vote. Objective transform intent can support a mechanical test, while human alignment remains measured on existing labels.

### Local index and regeneration

Build the smallest index/export inside the existing evidence workflow, not a new service. One provider-free command regenerates per-source counts and disposition tables. Core entities: source artifact and parent hash; work/author/prompt/group IDs; declared form/scope/rights; exact leaf/activation/bundle/scorer/prompt/schema/context/packet hashes; native logical request and attempt/session identities; planned repeat; raw/normalized state and evidence; recovery parent; existing human rater/outcome identities and derived-pair parent.

Classify exact-current-compatible, historical-only, unresolved-compatibility, accepted, missing, ambiguous, repaired, and replayed separately. Distinct content is not a distinct judgment, and identical content is not grounds to erase planned independent repeats. An ambiguous known identity remains reserved. A schema/evidence repair preserves the original vote. Changing global prompt, context, packet grouping/order or activation usually invalidates packet reuse even if leaf wording matches. Never update an old pin to current bytes.

Pass A covers TTCW, retained Pron, Dryad Sol plus the entire Grok chain, LAMP source/pass/repeats, and source metadata for the next comparison. Reconcile the old 51,968/53,990 verdict floors and later Grok continuation instead of extrapolating request counts. Pass B covers full-book/QPC24, multisample, poetry, revision ledgers, and every other declared accessible empirical root. Every discovered record gets a disposition; inaccessible roots are listed explicitly. Account homes, credentials, generic app logs, and unrelated projects are excluded from the research census.

### Unused expert data

First candidate is Author-Style-Personalization, with related GoodWritingBeGenerative treated as overlapping until IDs prove otherwise. Public design describes 240 pair items and 1,440 expert outcome decisions across quality/style, not 1,440 independent pairs; alternative-level rows duplicate decisions. Account for repeated AI excerpts, MFA writers, raters, target authors, task-specific reference conditions, and published examples. Metadata-only partitioning excludes preferences and rationales from the decision surface. Freeze candidate/comparator prompts before opening test targets; report public-data/pretraining contamination as unknown rather than asserting absence.

Use the stated noncommercial research scope; do not redistribute restricted excerpts or raw labels. If a planned usage cannot fit source terms, select other usable public evidence and record the limitation. No human outreach/panel becomes a hidden fallback. NarrativeWorldBench is an access/schema lead, not obtained labels. StoryER/Style Similarity/LitBench remain auxiliary crowd/style/social signals, with augmented-row and licensing checks. Missing whole-novel/professional-poetry labels limit claims but do not stop robustness/repeatability work.

## 6. Shared measurement contract

Freeze source bytes, scopes, allowed context, question and activation payloads, domains/penalties, scorer/validator, exact judge/comparator prompts, endpoint/model/account provenance, supported controls, packet memberships/order, target partition/exposure log, planned repeats, analysis code, and missingness/decision rules. Account identity is provenance, not a presumed quality difference; do not let an account switch silently change model/effort/contract.

Primary alignment includes majority-pair and individual-ballot agreement, separately for expert and nonexpert populations; report within-prompt/work/generator discrimination where the design supports it. Do not invent global rank correlations for disconnected preference graphs. Report genuine tie and inability to judge separately. Crossed writer/rater reuse requires appropriate sensitivity analyses; derived ballots are not independent works.

For every scalar arm: original scale/range, normalized display if useful, exact minimum/maximum rates, near-extreme ≤10/≥90 rates only after a declared affine range mapping, number of distinct scores, ties, active/applicability signatures, positive and penalty coverage, validity/provisional counts, uncertainty widths, and per-cohort distributions. Pairwise-only arms have no scalar floor/ceiling unless an explicit connected-graph ranking model is separately fitted; report ties, abstentions, preference extremity and order reversals instead. Never invent floors for a preference vote.

Repeatability: four-state transition matrix, raw and chance-adjusted agreement with prevalence caveats, per-leaf evidence consistency, domain/total changes, rank reversals, same-contract versus order/batch/endpoint changes. Current-version results are separate from old mixed-version panels. Inter-endpoint analysis includes score offsets, rank agreement and pair-order disagreement; mean absolute gap alone is insufficient.

Use work/author/prompt-clustered paired resampling and crossed-rater sensitivity when feasible, fixed analysis seeds, and published full denominators. Approximate five-point-gain power can be poor with thirty groups; simulate precision from opened development data before finalizing size. Start with attachment margins (+5 percentage points craft gain; reader lower bound above −3 for a noninferiority claim) only where meaningful, and declare alternatives before test labels. No silent sequential peeking or endpoint averaging that hides a loss.

Show complete cases, all planned groups, and best/worst bounds for unresolved comparisons. A default warning/inconclusive condition is >10% source-group loss or materially arm-dependent attrition; justify any prospective different bound. Native failure is measurement missingness. Unsupported evidence or controls must be recorded. Model judgments of synthetic edits support synthetic responsiveness, not human alignment.

Report logical requests, physical attempts, confirmed contacts, tokens, context duplication, latency, failures and cost eligibility. Include as-deployed comparisons plus a bounded token-budget-matched subset. Equal requests do not equal equal inference budgets. Preserve all attempts; continue untouched suffixes after classified stops. Never replay an ambiguous contacted ordinal as fresh.

## 7. Work packages and decisions

### P0 — Reconstruct, diagnose and preserve (first implementation)

Deliverables:

- Maintain the current worklog and exact source/plan hashes; verify claims and repo state.
- Extend existing scoring/import tests for the three witnessed policies and omitted/N/A/gate cases only where distinct behavior needs proof. Extend existing lineage tests for exact reuse/replay/ambiguous identities rather than building a blanket new suite.
- Implement strict new-import admission as an explicit mode/projection, preserving historical permissive input. Keep raw values and issue records. Evaluate ladder uncertainty and readiness as separately versioned candidates, not an immediate global rewrite.
- Census pass A and actual-code influence audit. Flip only simulated verdicts in a separately named diagnostic, never in native receipts; quantify which score/orders would change. Analyze TTCW within-generator and within-plot signal; preserve sparse-data uncertainty.
- Agent error audit: up to 24 consequential opened cases plus 12 prospectively sampled controls, target-to-leaf mapping and false-positive challenges. Replace “expert-corrected” counterfactuals with explicitly agent-reviewed hypothetical corrections. Use existing human rationales only where already allowed/opened.

Acceptance: deterministic replay remains exact; candidate policies have expected outputs and actual entrypoint tests; no source/label rewriting, no inferred human vote, no provider needed for the mechanics. Choose one evidenced change (normally ≤6 leaves or a small admission/scoring contract); if none, retain the baseline and prioritize comparator diagnostics. Agent review is sufficient for workflow review, but cannot confer new empirical human acceptance.

### P1 — Minimal native semantics and responsiveness

P1a: at most eight AI-generated/derived fixtures (two per YES/NO/N/A/CA), old/new contracts, two endpoints, three repeats = 96 logical one-packet judgments. It is conditional on a change needing native semantic evidence. Review fixture intent before scoring; actual intended damage may fail or legitimate alternative may be disputable. Require modal correctness on at least 7/8 per endpoint, critical N/A/CA controls stable, and no new critical false failure. These thresholds guide advancement, not population validation. One newly named revision is the default maximum per mechanism before redirecting.

P1b: eight AI source families, three versions each (original, target defect, style-preserving/legitimate variation), sixteen declared pair comparisons. Canonical baseline plus one candidate, bidirectional pairwise, holistic, compact craft and a form-appropriate established rubric. Preselect four full-bank repeat sentinels and four pair repeat sentinels. AI review supplies synthetic-oracle checks; existing human data supplies the later alignment test. Complete all canonical leaves appropriate to scope, including negative penalties and eligibility controls.

For P=23 baseline packets and q=2 truly changed packets, J=2 endpoints, the attachment's example is 1,840 evaluation requests: 1,104 baseline +96 changed +400 sentinel-bank repeats +64 pairwise +32 pair repeats +48 holistic +48 compact +48 established. AI generation/preparation is separately budgeted. Use q=0 for deterministic-only rescoring; use a full second bank if the global contract changes. Existing compatible packets can reduce the bill only after a full-contract identity join. A local leaf improvement with no full-score benefit may ship as a narrow diagnostic/correctness fix; do not relabel it alignment.

### P2 — Required larger CWR/competitor benchmark program

This work continues even if a particular candidate fails. Build one reusable measurement runner/analysis path for canonical CWR, frozen candidate when appropriate, bidirectional direct pairwise, a strong holistic prompt, a compact independent craft prompt, and established rubric comparators whose form/scope are suitable. Include deterministic constant, length/lexical and overlap-only baselines where meaningful. Preserve comparator native scales and scoring rules.

First expansion uses available existing human cohorts, with no new human labor. Priority: TTCW 36 stories; LAMP admitted 94 triplets, with all currently usable source instances/pair types; reader HANNA generated items and/or WPB selected pairs; Dryad/RA for scalar and target-overlap contrasts. Do not simply add these into one pooled score. Freeze at least two genuinely different expert/reference tasks and two nonexpert/uncertain-credential tasks in the benchmark plan. Existing opened cohorts are development/benchmark evidence, not new independent confirmation. Rejudge full contemporary banks where model/context contracts no longer match; do not pretend stable leaf text supplies a contemporary head-to-head.

Increase sample counts by prospective strata/whole source groups rather than favorable results. At minimum seek the complete usable already-admitted cohort per selected dataset; then expand toward the full eligible published source where rights/context/compute permit. Record precision target, exact sample size, exclusions and Grok-feasible cap before collection. Report why each remainder is unmeasured. Predefine a balanced sentinel subset across weak/mid/strong existing human-score tiers (where real scalar labels exist), lengths and forms for ≥3 same-contract repeats. Tier selection belongs to development/benchmark analysis; held-out target values cannot secretly set thresholds.

Required output is a versioned matrix for each dataset×population×form×endpoint×arm: n texts/groups/raters, human agreement metric and interval, scalar exact/near floors and ceilings, validity/coverage/abstention, per-arm tie compression, intra/inter-judge reliability, tokens/latency, and candidate-minus-baseline/comparator contrasts. It must explain unmatched historic external leaderboard numbers and allow a fair same-data result. A win on one source or a lower ceiling rate does not finish this package.

### P3 — Unused natural-text confirmation

Prefer the accessible MFA expert/lay excerpt release if its actual terms fit the research. Reconcile related versions and exact unique artifacts first. The advisory 20 target-author development /30 confirmation split, balanced 12/18 across the extra fine-tuned condition, is a useful proposed design—not an assumption that it is already executable. Expected confirmation geometry is 144 pairs, 198 distinct excerpt roles and 432 expert quality ballots; exact row/hash audit may change it before labels are opened. Actual MFA writer overlap can prevent author-generalization claims even with held-out target styles.

Use the proper excerpt/short_form route, not whole-story closure requirements. Quality and style-fidelity tasks receive their original human reference conditions separately. Freeze candidate and all comparator prompts first. Preserve published/example exposure in development. Blinded predictions on both endpoints are admitted before confirmation target/rationale opening. Grok may finish first; store its predictions without unblinding while Sol catches up on the designated account.

Planning example at P=23,q=2 gives 13,764 evaluations for canonical+candidate, pairwise, holistic, compact, 24-text extra bank repeats and 12-pair extra cycles. If actual short_form compilation at packet size8 gives P=22 and q=2, the same geometry gives 13,272 before additional established-rubric arms. Each additional scalar comparator costs 198×J=396 first-pass calls; its repeats are separate. Compiler output, context/response limits, and exact request files determine the real budget. Do not spend the proposed extra 7,512 development calls by default.

Use one preregistered comparison and fixed stopping analysis; do not repeatedly mine a sealed reserve after a failed result. +5-point expert/craft gain with paired interval>0 on both endpoints can support a narrow claim, with separate reader noninferiority/improvement and missingness requirements. If precision is inadequate, predefine at most one further independent cohort/extension with a combined analysis before collecting. A failed candidate does not end P2 benchmarking or justify automatic reweighting. Pairwise superiority can lead to a selection path distinct from CWR diagnostic feedback.

### P4 — Cross-form scope and long-range robustness

Retain the attachment's form matrix as design guidance: short stories; excerpts/scenes; chapters; novellas; novels/serialized prose; free verse; fixed-form poetry; scripts/audio; essays/creative nonfiction. Shared leaves can be tested economically in short fiction, but claims remain tied to actual form/context evidence.

- Long-form dependency probe: begin with two complete existing/AI-generated works to validate source-addressed case construction, then expand toward four novellas+four novels if useful and feasible. The eight-work attachment design (48 case instantiations×3 context arms×2 packets×2 endpoints×3 repeats) estimates 1,728 judgments. Agent-built/reviewed maps track event time, revelation order, beliefs/knowledge, alternatives, setup/payoff and source spans. Compare raw context, anchored excerpts/minimal map, and summary-only; add equal-token unstructured excerpts only if compression is the question. Count generation/map calls separately. No summary-only result is full-work artistic validation.
- Poetry probe: begin with four free/four fixed-form AI originals, targeted defects and legitimate alternatives, then expand to 16 families/48 artifacts if useful. The full attachment estimate is 1,152 targeted judgments for12 leaves/two packets, two contracts/endpoints and three repeats. Keep type/layout/sound limitations explicit, validate recurrence and non-narrative architecture, and keep agent disagreement. Run actual complete poetry bundles on prespecified sentinels before changing a general poetry default. Synthetic sensitivity is distinct from professional-poet alignment.
- Script/audio and nonfiction screens: per form eight originals plus eight AI derivatives,12 selected questions, two contracts/endpoints/repeats ≈256 calls/form. Only pursue claims supported by available modality/context; text cannot certify performed audio. Source facts/briefs are fixed.
- Packet geometry: conditional16-artifact mixed-form probe,12 leaves, sizes8/32, two orders, two endpoints and three repeats ≈576 calls. Freeze independent of wording. Any chosen geometry must be confirmed on complete banks and gets a new reuse fingerprint.
- Whole-work baseline/comparator reliability: run full supported contexts/bundles on existing or AI-generated complete works, with matched holistic/pairwise access, initially a small diagnostic cohort then a declared broader set. No new human reading panel. Existing human work-level labels may permit alignment; absent them publish robustness, scope and repeatability with the human-alignment gap explicit. Do not make 384–576 human reading hours a prerequisite for this program.

Replan only impacted source/evidence dependencies after edits; local span identity alone cannot guarantee distant payoff/knowledge judgments remain valid. Do not build a large graph platform unless the small evidence test earns it.

### P5 — Revision utility and absolute calibration

Adapt E4 to AI-generated revisions and independent agent/CWR comparator evaluation. Same editor/generator, budget, context, feedback length, maximum issues and one revision per arm. Start with12 distinct AI drafts, retain a held-back confirmation set, and expand toward36 roots/108 texts only when diagnosis supports it. Record unchanged original, strong generic-feedback revision, and CWR-feedback revision. Evaluation should be blind to arm and preferably use an endpoint/criterion set separate from feedback generation. Measure voice preservation, introduced defects, effect on intended criterion and strong simple-comparator preference.

These results establish agent-evaluated revision utility. They cannot manufacture human preference for newly generated revisions. Human-utility claims require existing appropriate labeled revisions or future owner-authorized data; lack of that data limits the claim, not all implementation. Keep that future condition outside current execution rather than planning recruitment.

Fit a small monotone mapping only against existing suitable scalar human targets in an honest development split, with constant/median baseline, holdout MAE/Brier/rank and calibration curves. Existing forced-choice labels permit preference calibration, not “80/100 is excellent.” An affine transform does not improve rank; report clipping/ties. Keep score calibration distinct from judge-confidence calibration. Domain/evidence presentation can be useful when absolute calibration is unsupported.

### P6 — Bounded offline criterion discovery, then later program

Only after diagnosed residual failure: compare static core, agent-reviewed offline proposals, pre-candidate task-conditioned criteria, and candidate-visible critique as explicitly diagnostic. Default ≤6 replacements/additions per cycle, with deletion proposals and distinct proposition ownership. A twelve-brief/36-artifact diagnostic with four arms, two endpoints/repeats is ≈576 judgments plus up to60 proposal/criterion-generation calls; count preparation separately. Existing human labels can test held-out alignment when scope fits; new AI families test stability, sensitivity and variation only.

Preserve exact proposal provenance and all rejected attempts; freeze before unused labels. Judge weights/models remain fixed within the comparison. Never optimize “human origin wins” as the target or prefer arbitrary diversity over quality. Include multiple accepted styles, strong AI/weak human cases from existing labeled sources where possible, and leave-one-rater-out consensus comparisons. Mean length and centered dimension correlations do not prove style preservation/disentanglement.

After the Grok window, finish Sol and provider-free analysis, close census pass B, conduct additional Sol-based comparative measurement with endpoint-specific claims, and prioritize replication over a new broad search. Future provider replacement/renewed Grok should be a separately versioned replication, not silently mixed into old cohorts. Maintain a prospectively selected regression set across forms and populations; update public counts/results after each material phase. Finish code packaging/local checks and compatible Palimpsest integration only after actual scope acceptance; no hosted CI is introduced by this plan.

## 8. Acceptance, decision tree, and completion

Engineering fixes may ship with narrowly demonstrated correctness claims after relevant tests, version/provenance behavior, and regression checks. They do not need a new human panel and do not confer general alignment.

For a human-alignment improvement claim: frozen intervention, independent existing-human target partition, matched baseline/comparator context and budgets, adequate complete canonical coverage, prospectively chosen practical margin and clustered interval, both endpoints where claimed, reader outcomes separately reported, and no critical semantic/style regression. Uncertainty is reported; do not force a positive result or remove inconvenient subjects.

For repeatability: require a current-contract multi-item result with stated form/population/scope, repeat/batch/order factors, denominators, rare-state behavior and statistical limits; don't pool versions or count repairs as repeats. For floor/ceiling claims: report original scalar ranges, exact/near thresholds and missingness on the same dataset/cohort as competitors.

Decision order:

1. Source/replay unresolved → repair bounded compatibility or classify exclusion; continue independent work.
2. Reachable engineering defect → implement versioned correction and narrow tests; preserve historical behavior.
3. Semantic native screen fails → reject/revise once, then switch mechanism. Baseline comparator program continues.
4. Synthetic responsiveness succeeds → carry one frozen candidate into existing-human evaluation. Synthetic success alone is not human alignment.
5. Natural alignment gain supported → adopt only the evidenced endpoint/form/population claim and run regression/replication.
6. Candidate inconclusive → at most a prospectively designed precision extension; do not tune on those targets.
7. Simpler judge wins ranking → use it where justified; assess CWR diagnostics separately.
8. No gain after two distinct mechanisms → simplify or redirect based on evidence, not another weight grid on the same opened data.

The successor must preserve the full improvement objective through implementation, measurement, comparator expansion, code and publication. A plan, first test suite, account login, one partial dataset, or rollover is not completion. Negative results are valuable completed experiments but do not automatically complete the full Goal. If actual constraints make further meaningful progress impossible after safe alternatives, record the precise blocker and use the native Goal lifecycle accurately.

## 9. Successor handoff and first concrete actions

Create the successor in the existing **Palimpsest** app project, local environment, GPT-6.1 Sol at High. The working code/evidence remains the saved CWR checkout and external control tree; do not relocate it or create a worktree. The successor must create its own native Goal and acquire fresh exact claims after the predecessor's release receipt. Parent task ID: `01a0eb29-aad1-72f1-8f91-bbd604afdfc6`.

First turn after transfer:

1. Read this plan, current worklog, latest AGENTS, private handoff and attachment; verify repo/branch/HEAD, settings/model, route/account metadata and source hashes.
2. Create the full native Goal below; no inferred token budget. Verify effective GPT-6.1 Sol / High for the task using available native state; preserve explicit model choice.
3. Acquire exact worklog/initial scoring/import test scope and new evidence output directory. Inspect/reuse queue/evaluation claims only after predecessor release; do not claim all repository files by habit.
4. Run the existing scorer tests relevant to A/B/C, preserve baseline witness outputs, and implement one coherent first correction (strict new-import admission unless evidence favors a smaller readiness addition).
5. Verify secondary Sol account with the isolated helper; if login is pending, continue P0, source metadata, and Grok preparation. No silent fallback to an undesired account and no credential copying.
6. Freeze the first comparator/evidence manifests, compute real packets/tokens and schedule against October15. Start the highest-value bounded next phase when ready; no new human dependency.

### Native Goal text

Execute the October 4 CWR/HBQ-RS alignment and repeatability program through supported rubric/system improvement and an evidence-backed release. Start from docs/ALIGNMENT_EXECUTION_PLAN_20261004.md and keep docs/CWR_CURRENT_WORKLOG.md current. Reproduce and address reachable scoring/admission/readiness issues with versioned historical compatibility; build a regenerable artifact/request/leaf census; run bounded AI-generated and agent-reviewed semantic/cross-form diagnostics; expand same-data CWR and strong competitor expert/nonexpert alignment, scalar floor/ceiling, coverage, intra/inter-judge and order/batch repeatability across multiple existing labeled datasets; evaluate one frozen candidate on unused appropriate human-reference data and pursue alternative mechanisms when justified. Human review steps may be agent review. Do not recruit people, create manual human labels, or train judges; new empirical artifacts come from AI generation and CWR/comparator evaluation, with existing human labels as the human reference. Prefer the owner-designated secondary ChatGPT account for Sol collection until further notice. Prioritize new Grok contacts to complete by October15 Denver before the reported October16 expiry, with no paid renewal/fallback. Preserve exact source, context, provider/account/model, sampler, native-attempt, no-resend, and historical-leaf provenance. Keep canonical baseline and R391 unpromoted absent prospective evidence. Cover excerpts/novels/poetry alongside short stories, report negative/uncertain results honestly, and do not confuse synthetic review with human validation. Finish relevant code/regression/package checks, documentation/census updates, authorized serial commit/push, and claim handoff. Do not mark complete for a plan, local tests, account setup, a partial collection, or publication alone; retain the full objective until demonstrated or use an accurate blocked state at a genuine impasse.
