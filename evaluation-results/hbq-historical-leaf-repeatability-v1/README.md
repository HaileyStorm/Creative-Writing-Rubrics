# Historical four-state HBQ leaf repeatability

This retrospective analysis measures consistency of raw leaf decisions across
five registered model repeats. It does not measure correctness or human
alignment. The original and later cohorts contain different items and prompt
groups, so their differences do not estimate a version effect.

| Cohort | Items / prompt groups | Item-question subjects | Stable across all five | Pair agreement | Sample-margin expected agreement | Fleiss-form κ |
|---|---:|---:|---:|---:|---:|---:|
| Original, HBQ v1.0.0 | 6 / 6 | 1,074 | 819 (76.3%) | 9,457 / 10,740 (88.1%) | 45.5% | 0.7807 |
| Later, HBQ v1.2.1 | 5 / 4 | 895 | 730 (81.6%) | 8,102 / 8,950 (90.5%) | 55.4% | 0.7874 |

Although pair agreement is high, 152 original and 112 later subjects contain
both YES and NO across their five repeats. Stable aggregate scores therefore
do not establish stable individual leaf decisions. The later cohort's greater
NO prevalence raises the expected-agreement term; neither κ nor raw agreement
establishes better literary judgments.

## States and disagreements

All four states remain distinct and unweighted. Confidence, severity, notes,
rationales and human targets are excluded.

| Raw output state | Original (5,370 labels) | Later (4,475 labels) |
|---|---:|---:|
| YES | 1,270 | 662 |
| NO | 3,329 | 3,218 |
| NOT_APPLICABLE | 645 | 553 |
| CANNOT_ASSESS | 126 | 42 |

| Exhaustive five-repeat subject category | Original | Later |
|---|---:|---:|
| Stable YES | 175 | 75 |
| Stable NO | 550 | 563 |
| Stable NOT_APPLICABLE | 86 | 91 |
| Stable CANNOT_ASSESS | 8 | 1 |
| Changing, contains both YES and NO | 152 | 112 |
| Changing, without both YES and NO | 103 | 53 |

| Exhaustive repeat-pair category | Original | Later |
|---|---:|---:|
| Same label | 9,457 | 8,102 |
| YES ↔ NO | 708 | 506 |
| Assessed (YES/NO) ↔ other (NA/CA) | 516 | 328 |
| NOT_APPLICABLE ↔ CANNOT_ASSESS | 59 | 14 |

Applicability and assessability changes account for another 575 original and
342 later disagreeing pairs. These are distinct from strict YES/NO reversals.
Stable NO is not a measure of correctness or literary quality. Rare CA labels
are retained, without interpreting their frequency as canonical rubric coverage.

## Method and provenance

The panel has 55 runs: eleven items, five repeats, and 179 question positions per
run. This gives 1,969 subjects, 9,845 labels and 19,690 derived comparisons.
Each subject contributes the ten unordered pairs of registered repeat indices.
Cross-tabs in `result.json` put earlier indices on rows and later indices on
columns; this orientation does not imply causal time, synchronized judging or
a packet-order experiment.

For N subjects, observed agreement Po is the count of equal-label pairs divided
by 10N. Each category proportion pj is its count among the 5N raw outputs.
Expected agreement Pe = Σ pj², and descriptive Fleiss-form κ = (Po−Pe)/(1−Pe).
When Pe is one, κ is undefined and recorded as null. Exact numerator/denominator
fractions accompany the decimals. Cohort Po equals the equal-item macro because
each item has 179 positions; cohort κ is not the mean of per-item κ.

Five repeats from a model are not five independent human raters. Questions are
heterogeneous, outputs share items and prompts, and this particular chance
adjustment depends on the sample margins. Pe is a convention, not a measurement
of random judging. No confidence intervals or significance claims are made.

The pinned historical study contract requested `codex / gpt-5.6-sol / high`.
This is saved-task provenance, not fresh attestation of historical backend or
tool controls, nor evidence about today's collection model. Prior scalar,
rater, calibration and reversal results were already known; this is a
retrospective extension. Its method and repaired source were independently
reviewed and frozen before projecting these raw labels.

The prerequisite byte checkpoint verified all 55 registered historical run
trees. This execution rechecked every registered `run.json` and `verdicts.jsonl`
descriptor (110 files) before any manifest or label projection. The selective
reader materializes only `configuration.question_ids` and each row's
`question_id` and `verdict`. UTF-8 bytes are scanned, while skipped confidence,
note, rationale, input prose, native/session response and human target fields
are not semantically materialized. Every run must have exactly 179 unique
manifest positions, 179 newline-terminated rows in matching order, and identical
question order within an item. Unknown states, incomplete tails, changed bytes,
missing positions, duplicates and unsafe paths fail closed. No runs or states
are omitted to repair a result.

## Artifacts and verification

- `profile.json`: frozen scope, source commitments, formula and exclusions.
- `source.py`: selective projection, validation and exact-count analysis.
- `test_source.py`: two focused known-count and output-preservation guards.
- `result.json`: two cohort summaries and eleven anonymous per-item rows.
- `execution.json`: the single execution receipt and independent saved-label
  readback commitment.

The frozen analysis executed once and exited zero. Both focused guards passed.
An independent calculation from the saved private label ledger verified all 13
metric rows, partitions, margins, cross-tabs, exact fractions and null handling,
without reopening the original trees or rerunning the analysis. Private item
identifiers, question identifiers, sequences, source locators and failed
attempts remain retained outside the public package. Output guards preserve
source roots and reject overlap, traversal and unsafe ancestors.

This fills the historical intra-output leaf repeatability portion of the
research matrix. It does not qualify current collections, compare endpoints,
establish human validity, change scoring, train judges or promote the canonical
baseline or frozen candidates. The full prospective multi-dataset program
remains incomplete.
