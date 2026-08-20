# Established-rubric comparison v2 (frozen; not yet run)

This is the pre-registered runnable follow-up to the public five-repeat case study. It will send the same byte-identified, authorized story to four isolated fresh-session arms, once per explicit near-Latin block, for exactly five blocks:

| Arm | Native output |
| --- | --- |
| HBQ-RS `prose.short_story` | 178 binary leaves, deterministic score, typed evidence |
| NAPLAN Narrative Writing Marking Guide 2022 implementation | ten criterion ranges, total 0–47 |
| Cambridge IGCSE 0500/21 May/June 2024 implementation | content/structure 0–16; style/accuracy 0–24; total 0–40 |
| Oregon DOE Revised Narrative Writing Scoring Guide 2017 implementation | six traits 1–6, total 6–36 |

The three non-HBQ prompts are concise original paraphrases derived from published rubrics, not copied score tables. They are research implementations, not official scoring, trained-marker substitutes, or claims of endorsement. The official sources are the [NAPLAN 2022 guide](https://www.nap.edu.au/docs/default-source/naplan/narrative-writing-marking-guide.pdf?sfvrsn=c85435e_2), [Cambridge May/June 2024 mark scheme](https://www.cambridgeinternational.org/Images/521329-june-2024-mark-scheme-paper-21.pdf), and [Oregon 2017 scoring guide](https://www.oregon.gov/ode/educator-resources/essentialskills/ScoringGuides/wriscorguide_narrative_eng.pdf). Their copyright and reuse terms apply; this package deliberately does not reproduce their tables or exemplars.

NZQA AS91101 was considered and deliberately excluded: its published standard assesses a selection of at least two pieces, making a one-story comparison structurally invalid.

## Frozen protocol

`study-contract.json` pins the authorized source bytes, model (`gpt-5.6-sol`), high reasoning, five fresh repetitions, an explicit near-Latin serial schedule, HBQ question order, prompts, response schemas, registry, bundle, scoring/compiler code, and study-code hashes. `run_study.py` refuses to run if any of those values drift. It records all 20 planned slots before evaluation, then atomically appends each completion to a contract-bound schedule journal; the analyzer refuses a missing, duplicate, or reordered journal. Each comparator sees only its own prompt and the story; it never receives HBQ prompts, verdicts, scores, or reports.

Run only in an external disposable directory:

```powershell
$env:PYTHONPATH = 'src'
python evaluation-results/the-part-that-arrives-first-repeatability/established-v2/run_study.py --work-dir C:\path\outside-the-repo\established-v2-work
python evaluation-results/the-part-that-arrives-first-repeatability/established-v2/analyze_study.py --work-dir C:\path\outside-the-repo\established-v2-work --output-dir C:\path\outside-the-repo\established-v2-results
```

The analyzer refuses stale protocol bytes, partial/checkpoint-mismatched HBQ runs, invalid native results, ungrounded exact quotations, reused provider sessions, model/reasoning drift, recomputation mismatch, or an existing output directory. It preserves raw native-scale outputs separately and publishes only one global 20-session uniqueness/count commitment, never session IDs. It reports HBQ leaf agreement/modal agreement/nominal alpha/score dispersion and typed-evidence denominators and coverage rates, alongside analytic-rubric criterion agreement/modal proportions and native-total dispersion. The generated score and agreement charts retain their scale labels; no raw scores are subtracted, averaged, normalized on the study story, or ranked across rubrics.

Results are intentionally absent until the exact frozen study has run. Any conclusion about HBQ diagnostic resolution alongside coarser-scale stability belongs in the generated post-run comparison and remains descriptive for this story/provider window.
