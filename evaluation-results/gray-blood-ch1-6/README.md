# Gray Blood, Chapters 1–6: current WIP comparison

This is a private-work-in-progress evaluation of two six-chapter drafts. It publishes the score structure and every accepted binary verdict, plus four provisionally selected short excerpts used to make the case study legible. The publication authorization is clear; the exact selection remains pending owner confirmation. It does not publish any other manuscript prose, evaluation evidence, prompts, model responses, local paths, or execution identifiers.

## Orientation

The opening follows Madison, a technically minded student drawn into blood-powered magic; Amelia, her witch partner; and FAWN, a research group that offers a second route into that world. The comparison asks how the two drafts handle that premise, the relationship, the rules and costs of power, and the opening's movement.

The rewrite leads the current complete whole-work view by 7.89 points. Both runs are `VALID` and `SCORED`; the difference is a diagnostic result for this rubric and scope, not a general verdict on either draft.

| Draft | Whole-work observed | Bounds | Coverage | WIP 70/30 composite |
| --- | ---: | ---: | ---: | ---: |
| Original | 75.52 | 75.52–75.52 | 100.00% | 78.67 |
| Rewrite | 83.41 | 82.95–83.54 | 99.42% | 83.53 |

`VALID` means every applicable objective control requirement was satisfied. **Coverage** is the weighted share of applicable criteria with a `YES` or `NO` verdict. **Observed** is the deterministic score from those assessed criteria after capped penalties. **Bounds** are the low/high results still possible if any `CANNOT_ASSESS` criteria resolve as failures/passes; they are not confidence intervals.

This is a WIP evaluation: completion-only leaves are `NOT_APPLICABLE`, while craft, continuity, and weighted author-goal leaves remain active for the supplied chapters. Author goals influence score but never determine `VALID`. The minimum score-coverage threshold is 80%.

The optional `balanced-wip-70-30` view uses 70% whole-work score and 30% equal-weight chapter mean. It is shown beside—not in place of—the whole-work and chapter views.

## Case study: four bounded moments

Gray Blood is a contemporary urban-fantasy WIP about Madison, Amelia, and the costs of blood-powered magic. These four short passages make the comparison concrete: an early move toward romance, the stated cost of power, an embodied magic rule, and a preserved-core/revised-middle relationship passage. They total 513 words. Content note: on-page kissing, strong language and profanity, blood magic, cutting/injury, and a direct description of eating a beating human heart.

- [Chapter 1: early relationship approach](excerpts/ch01-new-relationship.md)
- [Chapter 3: cost of magic](excerpts/ch03-new-magic-cost.md)
- [Chapter 4: engraved magic](excerpts/ch04-new-engraving.md)
- [Chapter 5: revision pair](excerpts/ch05-revision-pair.md)

The whole-work verdict ledgers include checks for the magic constraints represented here—activation requiring a heart and engraving requiring lifeblood—as well as author-goal and craft criteria around the relationship. That is useful context, not excerpt-level evidence: these passages were not individually scored, do not explain any individual leaf, and must not be read as causing the +7.89 whole-work difference. The Chapter 5 pair preserves shared material and exposes a revised middle; it is not a claim that either passage caused a score change.

The real tension is more interesting than a headline. The rewrite gains in character, language, effect, freshness, and mechanics at whole-work scale, while the original has stronger chapter-local scores in chapters 3–6 and leads in plot, world, and pacing totals. The passages show why a future reader or revision system needs both lenses: concise moments can make agency, cost, and physical process vivid, while a long-form evaluation still asks how those moments accumulate into movement and structure.

The selection is deliberately small and incomplete. It is not a representative sample of either chapter, draft, or manuscript, and it should not be used to make safety, quality, or style claims beyond the published protocol. A known original-Chapter-5 source typo is intentionally preserved in the passage.

## Whole-work domains

![Whole-work domain scores](figures/whole-work-domains.svg)

| Domain | Original | Rewrite | Rewrite − original |
| --- | ---: | ---: | ---: |
| task | 5.11 | 5.50 | +0.39 |
| character | 14.86 | 16.00 | +1.14 |
| plot | 18.82 | 18.75 | -0.07 |
| world | 12.00 | 11.45 | -0.55 |
| pacing | 7.78 | 7.30 | -0.48 |
| language | 7.01 | 8.57 | +1.56 |
| effect | 6.49 | 7.35 | +0.86 |
| fresh | 2.07 | 2.28 | +0.22 |
| mechanics | 0.53 | 1.07 | +0.53 |
| holistic | 6.00 | 6.00 | +0.00 |

The rewrite gains in task, character, language, theme/effect, freshness, and mechanics. The original retains the stronger plot, world, and pacing totals. Holistic score is unchanged. These domain totals keep the comparison useful without pretending that one compact number tells the whole story.

## Chapter view

![Complete chapter-local scores](figures/chapter-local-scores.svg)

| Chapter | Original | Rewrite | Rewrite − original |
| ---: | ---: | ---: | ---: |
| 1 | 77.14 | 78.26 | +1.12 |
| 2 | 83.06 | 83.54 | +0.48 |
| 3 | 88.95 | 84.87 | -4.08 |
| 4 | 89.27 | 85.75 | -3.52 |
| 5 | 89.15 | 85.71 | -3.44 |
| 6 | 88.59 | 84.69 | -3.90 |

Each chapter received the complete `prose.chapter` bundle. This local view is a second scale of evidence, while the complete six-chapter `prose.novel` pass remains the manuscript-level result.

## Reading the publication

- [`reports/original.json`](reports/original.json) and [`reports/rewrite.json`](reports/rewrite.json) contain current global, 70/30, chapter, and domain score reports.
- [`verdicts/original.jsonl`](verdicts/original.jsonl) and [`verdicts/rewrite.jsonl`](verdicts/rewrite.jsonl) contain every accepted verdict with stable criterion IDs, scope, and confidence—without evidence text.
- [`comparison.json`](comparison.json) provides machine-readable domain and chapter deltas.
- [`excerpts/provenance.json`](excerpts/provenance.json) binds the four permitted files to draft/chapter IDs, exact character and UTF-8 byte boundaries, input hashes, excerpt hashes, and word counts without disclosing source locations.
- [`targeted-evaluation-contract.json`](targeted-evaluation-contract.json) freezes a later, small excerpt-level Sol evaluation. It is offline-first and `not_run`: a future executor must disclose the exact public excerpt leaving the machine, receive an explicit allow-remote gate, validate verbatim spans, and use bounded per-leaf repair.
- [`privacy-audit.json`](privacy-audit.json) and [`verify_publication.py`](verify_publication.py) provide the audit and deterministic public-package checks.

This refresh uses a complete current protocol. It replaces the prior publication; it is **not** a sampled-to-full score comparison.

Results are comparable within this published protocol only. Do not compare its headline directly with an earlier headline: the protocol, reasoning configuration, and accepted-verdict set differ.

The extractor is deterministic and takes source inputs only as command arguments: [`extract_excerpts.py`](extract_excerpts.py). It has no model or network path. The publication verifier permits only these four named excerpt files; adding any prose, evaluation evidence, or execution material fails verification.
