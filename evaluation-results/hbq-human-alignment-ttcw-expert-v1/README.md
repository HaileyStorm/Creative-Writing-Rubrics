# TTCW expert alignment: baseline holds, frozen weight change fails

This aggregate-only development result completed its public-redaction and
provenance audit on 2026-10-01. It contains no story text, individual
expert labels or explanations, assessor IDs, prompts, sessions, or raw model
responses. [summary.json](summary.json) pins the private local evidence by hash.

The [TTCW authors](https://github.com/salesforce/creativity_eval/tree/3d029879df6878f611363db88cc02d465699bc51/Art_or_Artifice)
released 14 binary creativity tests and three independent judgments per story.
The source [paper](https://arxiv.org/pdf/2309.14556) describes creative-writing
experts, unlike the regular-reader Dryad panel. This analysis uses the 36
AI-written stories in twelve matched plot groups; the twelve New Yorker
reference URLs were not fetched or scored. The exact author annotation blob
was opened locally **after** both endpoint replays and all pretarget scores
passed the unchanged 0.88 per-story coverage floor.

The all-one HBQ-RS baseline and one Dryad-derived trial-15 weight profile were
frozen before any TTCW expert labels opened. Each endpoint answered 828
identical user-payload requests covering 6,408 ordered HBQ-RS verdicts. The
Grok path comprises 821 original native broker envelopes, two accepted exact
second attempts after preserved no-answer sessions, and five saved native
sessions with complete answers but no broker envelopes. Those five underwent
a separate provider-free semantic replay. All 828 accepted request and
session hashes are distinct. Provider contact cardinality remains unproven;
the five local recoveries must not be described as ordinary broker-envelope
admission. Sol was evaluated independently without refitting.

| Endpoint | Baseline expert rho | Frozen candidate rho | Candidate − baseline | Plot-bootstrap 2.5% gain bound | Within-plot concordance |
| --- | ---: | ---: | ---: | ---: | ---: |
| Grok | 0.7479 | 0.6904 | −0.0575 | −0.1379 | 0.8333 → 0.8333 |
| Sol | 0.6956 | 0.6236 | −0.0720 | −0.1348 | 0.8333 → 0.8333 |

The target is each story’s expert YES fraction across 14 tests and three
assessors (42 judgments). The primary metric is Spearman across 36 stories,
separately by endpoint. A 2,000-replicate paired bootstrap samples plot
groups; the frozen rule requires a strictly positive lower gain bound for
both endpoints, plus the within-plot condition. Neither endpoint improves.
The candidate is **not retained or promoted**. Its slightly smaller Grok–Sol
score gap does not rescue the failed expert-alignment gate. The baseline’s
observed association is encouraging within this exact cohort, not a general
claim of literary validity or superiority over other rubrics.

Coverage minima were at least 0.9794 on Grok and 0.9885 on Sol for the
compared profiles. Neither profile/endpoint produced a score at or below 10
or at or above 90 on these 36 stories. Of 504 test/story cells, 280 had
unanimous expert votes and 224 split (pairwise agreement 0.7037).

Two explicitly post-target checks are **exploratory only**: eleven weaker or
combined cached-verdict profiles yielded no positive correlation gain on
both endpoints, and simple word count correlated negatively with the expert
target (rho −0.4760), unlike the baseline. They were not preregistered arms,
cannot retroactively change the frozen result, and require a new independent
expert holdout before any future promotion.

The paper reports ten recruited expert assessors, while the exact released
annotation file contains eleven distinct numeric `expert_idx` codes. Each
story and plot group still has three consistent assessor codes; the mapping
from codes to people is unresolved. We do not claim eleven people, pool Grok
and Sol, publish individual targets, or grant runtime/release authority from
this package.

The public audit matched the private comparison and source-admission hashes
in `summary.json` against the retained local files and checked this package
for story text, individual target values, assessor identities, prompts,
sessions, and model responses. Publishing these aggregate statistics does
not resolve the assessor-code mapping or establish product release.
