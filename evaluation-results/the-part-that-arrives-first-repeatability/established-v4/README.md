# Established-rubric repeatability study v4

This completed study scores the authorized short story [The Part That Arrives First](../source.md) five times with GPT-5.6 Sol at high reasoning. Every accepted provider call used a fresh session: 30 HBQ batches and 15 native passes, all unique. The frozen near-Latin schedule alternates HBQ-RS with three original research implementations derived from published rubrics; the [study contract](study-contract.json) fixes the source, prompts, schemas, model settings, order, and stopping rule before execution.

## Results

| Method | Five results | Repeatability |
| --- | --- | --- |
| HBQ-RS `prose.short_story` | 88.5994, 92.7236, 86.5380, 94.8341, 90.6869 | 91.01% of 178 leaves agreed in all five runs; mean modal-label proportion 97.08%; nominal Krippendorff alpha 0.8617 |
| NAPLAN narrative implementation | 47, 47, 47, 47, 47 | All ten criteria agreed; three initial responses were rejected for non-contiguous quotations and corrected on retry |
| Cambridge IGCSE 0500 composition implementation | 40, 40, 39, 40, 39 | `style_and_accuracy` stayed at 24; `content_and_structure` varied between 15 and 16 |
| Oregon narrative implementation | 36, 36, 36, 36, 36 | All six traits agreed; three responses were rejected for non-contiguous quotations and corrected on retry |

The HBQ observed score averaged **90.6764**, with sample standard deviation **3.2756** and range **8.2961**. Its 91.01% all-run agreement is the strict measure: one differing label makes a leaf disagree. Sixteen leaves were non-unanimous: seven had a modal proportion of 0.8, eight were at 0.6, and one was at 0.4.

![Score distributions across five repetitions](results/score-distributions.svg)

![Exact all-run agreement by method](results/agreement.svg)

## What the comparison says

HBQ-RS was highly repeatable without collapsing to a fixed answer: 162 of 178 leaves agreed across every run, while its score still moved by about eight points from minimum to maximum. The Cambridge implementation showed a narrower version of the same boundary sensitivity: one of two components moved by one point.

NAPLAN and Oregon were perfectly repeatable here, but both saturated at their maximum. That is useful evidence of consistency on this story, not evidence that those implementations discriminate well among strong submissions. The native scales remain separate; a 47/47, 40/40, or 36/36 is not converted into, averaged with, or ranked against an HBQ percentage.

Evidence controls had a measurable cost. HBQ retained 854 grounded exact quotations and 266 summaries; 62 would-be quotations that were not byte-exact were deterministically relabeled as summaries, without changing their verdicts. The native implementations require a contiguous quotation for every component, so six non-contiguous quotations were rejected and required another model call: three in NAPLAN and three in Oregon. Cambridge needed no retry.

This is a one-story, five-repetition study. It measures repeatability under the frozen configuration, not validity, trained-marker equivalence, or general superiority. The native comparators are research implementations derived from their named public rubrics, not official scores.

## Files and verification

- [summary.json](results/summary.json) contains the calculated metrics and retry counts.
- [hbq-leaf-repeatability.json](results/hbq-leaf-repeatability.json) contains the 178 leaf-level label series and agreement measures.
- [provenance.json](results/provenance.json) binds the protocol, schedule, accepted provider identity, result hashes, retry records, and session commitments without exposing session identifiers.
- [publication-manifest.json](results/publication-manifest.json) hashes every published analysis artifact and commits to the complete external analyzer manifest.

Verify the public package with:

```console
python evaluation-results/the-part-that-arrives-first-repeatability/established-v4/results/verify_results.py
pytest -q tests/test_established_repeatability_v4_results.py
```
