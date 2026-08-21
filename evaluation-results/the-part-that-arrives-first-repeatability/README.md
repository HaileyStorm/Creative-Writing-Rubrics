# Initial batching study: *The Part That Arrives First*

This case study asks how stable one GPT-5.6 Sol judge is across repeated readings of the same complete story under different rubric shapes and HBQ batch sizes. For the stricter comparison against implementations derived from published rubrics, see the [established-rubric repeatability study v4](established-v4/).

The repository owner supplied the story and explicitly authorized publishing it in full. Read [the complete source](source.md), the [frozen study contract](study-contract.json), or any of the [published run outputs](results/).

## Design

The contract was frozen before execution. Each arm ran five times in a fresh Codex session with tools and network access disabled. Runs used `gpt-5.6-sol`: Medium reasoning for the 178 HBQ leaves and High reasoning for the two coarser comparators. There was no temperature or seed control and no result-driven stopping.

| Arm | Shape | Native output |
| --- | --- | --- |
| HBQ, 24 leaves per batch | `prose.short_story`, the same 178 leaves on every run | deterministic 0–100 aggregation |
| HBQ, one large batch | the same 178 leaves in the same order | deterministic 0–100 aggregation |
| Compact analytic | six independently synthesized anchored dimensions | six 1–5 ratings plus an overall 1–5 rating |
| Holistic anchored | one independently synthesized whole-story judgment | one 1–7 rating |

Comparator prompts borrow recurring constructs from established narrative-writing rubrics, but their wording and schemas are original. References: [NAPLAN narrative marking guide](https://www.nap.edu.au/docs/default-source/naplan/narrative-writing-marking-guide.pdf?sfvrsn=c85435e_2), [Oregon narrative writing scoring guide](https://www.oregon.gov/ode/educator-resources/essentialskills/ScoringGuides/wriscorguide_narrative_eng.pdf), [Cambridge English mark scheme](https://www.cambridgeinternational.org/Images/521329-june-2024-mark-scheme-paper-21.pdf), and [NZQA crafted writing standard](https://www.nzqa.govt.nz/nqfdocs/ncea-resource/achievements/2019/as91101.pdf).

## Results

| Method | Headline values across five runs | Repeatability |
| --- | --- | --- |
| HBQ, 24 per batch | 91.55, 89.99, 91.12, 86.36, 88.98 | 150/178 leaves agreed on all five runs (84.3%); mean modal agreement 95.3%; nominal Krippendorff α 0.771; score SD 2.072 |
| HBQ, one batch | 88.11, 88.11, 89.91, 87.47, 85.28 | 160/178 leaves agreed on all five runs (89.9%); mean modal agreement 97.2%; nominal α 0.869; score SD 1.665 |
| Compact analytic | overall 5, 5, 5, 5, 5 | five of six dimensions were identical; narrative architecture alternated between 4 and 5 |
| Holistic anchored | 6, 6, 6, 6, 6 | identical headline rating on every run |

“All-five agreement” means every repetition returned the same leaf verdict. Modal agreement gives partial credit when four of five agree; alpha also accounts for label prevalence. Native scales are not converted into one another.

![Five independent scores under each method](results/score-distributions.svg)

![HBQ leaf-level agreement](results/leaf-agreement.svg)

The coarse methods were perfectly stable at headline level but hit a ceiling: every holistic result was 6/7 and every analytic overall 5/5. HBQ exposes more of the judgment surface while retaining 95.3% or 97.2% mean modal agreement.

### Batching mattered

The one-batch arm was more repeatable here: 5.6 percentage points higher exact leaf agreement, 0.098 higher alpha, and 0.407 lower score SD. The modes agreed on 92.6% of leaves within paired repetitions, but 24-per-batch averaged 1.824 points higher; mean paired absolute difference was 2.272.

![Paired HBQ scores under the two batching choices](results/batching-comparison.svg)

This is a method effect worth controlling, not proof that larger batches are universally better. Benchmarks should freeze batch size and calibrate against the intended call shape.

## What HBQ caught

See [What HBQ caught in the story](hbq-findings.md) for the illustrated craft findings.

## Evidence discipline

Published result files preserve every rating and concise justification. An automated check tested whether each evidence `quote` was an exact source substring: 64.1% for 24-leaf HBQ, 71.0% for one-batch HBQ, 86.7% for compact analytic, and 80.0% for holistic. Misses include paraphrase, joined ellipses, and encoding substitutions; they are not treated as quotations. Evidence objects therefore need validation separate from verdict schemas.

## Reproduce and inspect

The public analysis is deterministic once the private raw run directories exist:

```bash
python evaluation-results/the-part-that-arrives-first-repeatability/analyze_study.py \
  --work-dir /path/to/completed-study-work \
  --output-dir /tmp/repeatability-results
```

The [runner](run_study.py), [strict comparator prompts and schemas](arms/), [summary](results/summary.json), [per-leaf repeatability table](results/leaf-repeatability.json), run outputs, hashes, and sanitized provider provenance are included. One story, one configuration, and five repetitions support a descriptive case study—not a universal ranking, a human gold standard, or proof that repeatability equals validity.
