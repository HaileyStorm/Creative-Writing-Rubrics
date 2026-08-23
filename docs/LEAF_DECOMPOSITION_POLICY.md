# Leaf decomposition policy

HBQ-RS has 278 modules, 2,145 leaves, and 85 bundles. A structural audit and
Sol High adjudication found useful *candidates* for refinement, not validated
leaf failures. This policy turns disputed binary verdicts into bounded
maintenance work without treating a single disagreement as proof that a
criterion should be split.

## The rule

A valid, localized issue is a revision note. It becomes a scope-level `NO`
only when the leaf's own proposition, activation, evidence policy, and
materiality threshold are all met at the evaluated scope. A whole-work leaf is
not failed merely because one sentence could be improved; a local leaf is not
excused because the surrounding work is strong.

When a leaf repeatedly forces reasonable reviewers to choose between distinct
propositions, separate those propositions rather than making one binary carry
both. When the dispute is instead about scope, evidence, or materiality,
repair that contract before adding leaves.

## Read disagreement by type

| Signal | First check | First remedy |
| --- | --- | --- |
| Same-input retry | Exact input, output validity, and quoted evidence | Bounded retry of the affected leaf or batch; retain all attempts. |
| Batch or carrier change | Same leaf alone versus a matched carrier | Route the leaf singly or at a validated smaller batch size. |
| Polarity change | Equivalent positive and flipped wording | Repair wording or use an explicitly configured paired mode; any averaging remains visible in provenance. |
| Prefix or framing change | A controlled frame comparison | Freeze the selected frame in provenance and calibrate materiality before changing the leaf. |
| Trusted cross-model disagreement | Prompt, scope, and evidence parity | Treat it as a model- and prompt-suitability signal; reproduce before rubric change. |
| Confidence disagreement | Calibration against observed outcomes | Resample low-confidence calls only if calibration shows that it helps. |
| Archived human-reference mismatch | Overlapping propositions and task/scoring alignment | Repair overlap wording and selection; do not shrink the book to the reference set. |
| Localized-versus-scope conflict | Declared evidence scope and source coverage | Keep a revision note, or move the judgment to the correct local/global leaf. |

These signals may agree, but they are not interchangeable. A model retry does
not establish human alignment; a human-reference mismatch does not prove that
the model was inconsistent.

## Split only through a promotion gate

A proposed split must show all of the following:

1. Repeated disagreement remains after the applicable first remedy, with at
   least two independent signals or a clear recurring scope/proposition clash.
2. The proposed children express separable propositions, each with explicit
   scope, activation, evidence, and materiality language.
3. Each child has one `criterion_key` owner. Existing leaves and bundles are
   checked for overlap so the same defect is not counted twice.
4. The parent is replaced, not shadowed. The replacement keeps the former
   total influence unless an explicit, separately tested reweighting decision
   says otherwise.
5. The candidate succeeds on a preregistered confirmation and a holdout that
   include a plausible non-problem control. The question is whether the split
   improves the targeted distinction without making unrelated work worse.

The bar is deliberately practical: it asks for a durable pattern and a useful
counterexample, not a paper-sized experiment.

## Identity and migration

Leaves are part of the public evidence contract. A replacement receives new
stable IDs and a new criterion ownership record. The removed leaf is retained
as a tombstone/compatibility record with its retirement reason and successor
IDs; it is removed from current source, generated aggregates, and bundles
unless a named compatibility obligation requires otherwise.

Historical runs retain their original question-set identity and score. They
are never silently reinterpreted through successors. Current scoring begins
with fresh runs under the new map; comparisons must name both maps.

## Current empirical first tier

The first tier is investigation, not a shipped structural change:

- `penalty.purple_prose.proportion` is the primary candidate to test for a
  cumulative-density or saturation distinction. Its current wording can be
  satisfied by judging one representative sentence when the reported concern
  is distributed across a longer scope.
- `core.freshness_and_non_genericness.no_llm_phrasing` owns generic LLM-like
  wording, rhetorical templates, and overfamiliar contrast patterns. It does
  not own every familiar metaphor.
- `core.freshness_and_non_genericness.no_default_metaphors` owns familiarity
  of figurative turns. It does not own their cumulative density or overall
  figurative load.

Single-leaf and matched-carrier runs should establish whether this is a
batching defect, a scope/materiality defect, or a genuine missing proposition
before any replacement is drafted.

## Deferred watchlist

The audit's remaining high-value hypotheses include cumulative image
repetition, figurative fatigue, rhetorical-template repetition, information
versus experiential density, local versus global pacing, kinds of restatement,
syntax integrity versus monotony, dialogue-exposition modes, manuscript thread
summaries, prose-mode proportion, and evidence grounding versus confidence
calibration. They remain hypotheses until the promotion gate is met. The book
should prefer a small number of well-owned leaves over a large set of
near-duplicates.

See the [HBQ-RS standard](HBQ_RS_STANDARD.md) for normative ownership,
scope, and scoring rules. This document governs when evidence justifies
changing that map.
