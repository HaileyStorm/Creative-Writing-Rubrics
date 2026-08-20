# HANNA human-reference study (v2)

This is a frozen, prose-free validation harness for HBQ-RS using only
already-published HANNA ratings. It never recruits, contacts, or newly judges
human readers. HANNA supplies three published 1–5 ratings per story for
Relevance, Coherence, Empathy, Surprise, Engagement, and Complexity.

The upstream HANNA repository distributes its benchmark CSV under MIT, and this
repository retains that attribution in any published rating derivatives. The
underlying WritingPrompts material may have separate rights; this repository
republishes no HANNA story or prompt prose.

The direct source is pinned to `282f27536a5d05ad4ce14298abcd70c45668fed2`.
Only its direct CSV and LICENSE URLs are fetched; no archive is downloaded or
expanded. Raw inputs and runner checkpoints remain external. Public outputs hold
only IDs, hashes, published ratings, and derived metrics.

## Design

Before ratings are considered, seed `560820` hashes the 96 unique prompts into
48 development and 48 confirmatory prompt clusters. A shared prompt can never
cross that boundary. Within each partition and source Model, stories are ranked
by the published human-overall value and two are chosen from each
partition-relative quartile: 88 development and 88 confirmatory stories.

Every item uses the full 179-leaf `prose.short_story` bundle in ordered batches
of 32 leaves. The HANNA prompt is context and creates the non-gating dynamic goal
`hanna.prompt_response` (compiled as `task.contract.hanna.prompt_response`).
Judging is provenance-blinded (`strict_ai=False`), with the package commit,
compiler, runner, scoring core, prompts, schemas, mappings, and external inputs
all frozen and rechecked.

The workflow is phased: run and analyze `development`, create the immutable
confirmation gate that binds that analysis to the unchanged frozen protocol, then
run and analyze `repeatability` and `confirmatory`. Confirmatory refuses to run
without its exact gate.

The primary confirmatory measures are six pre-registered Spearman correlations
and their macro mean with prompt-cluster bootstrap intervals. Secondary reporting
includes Pearson values, coverage/unresolved counts, source-model strata, and a
permutation-invariant within-item ordinal agreement statistic for the published
three-rater slice. It is context, not a ceiling. The HANNA paper’s published
ICC(2,k) range (approximately .29–.56) is cited separately.

Repeatability uses one frozen development story per Model, each in five fresh run
directories. A repetition can span several Codex batch sessions; its session set
must be nonempty and globally disjoint from every other repetition. Published
repeatability output commits the per-repetition session counts and total distinct
session count. It reports per-item score SD/range and aggregate within-item spread;
it never pools scores across unrelated items. Typed evidence conformance,
exact-quote grounding, summary prevalence, untyped entries, and empty entries are
separate measures—summaries are not grounded-evidence proof.

## Run

```powershell
$env:PYTHONPATH = "src"
python evaluation-results/hbq-human-alignment-v2/prepare_hanna.py --data-dir C:\path\hanna --work-dir C:\path\hbq-hanna --fetch
python evaluation-results/hbq-human-alignment-v2/run_study.py --work-dir C:\path\hbq-hanna --phase development --workers 2
python evaluation-results/hbq-human-alignment-v2/analyze_study.py --data-dir C:\path\hanna --work-dir C:\path\hbq-hanna --phase development --output-dir C:\path\hbq-hanna\analysis\development
python evaluation-results/hbq-human-alignment-v2/confirmation_gate.py --work-dir C:\path\hbq-hanna --development-analysis-dir C:\path\hbq-hanna\analysis\development
python evaluation-results/hbq-human-alignment-v2/run_study.py --work-dir C:\path\hbq-hanna --phase repeatability --workers 2
python evaluation-results/hbq-human-alignment-v2/analyze_study.py --data-dir C:\path\hanna --work-dir C:\path\hbq-hanna --phase repeatability --output-dir C:\path\hbq-hanna\analysis\repeatability
python evaluation-results/hbq-human-alignment-v2/run_study.py --work-dir C:\path\hbq-hanna --phase confirmatory --workers 2
python evaluation-results/hbq-human-alignment-v2/analyze_study.py --data-dir C:\path\hanna --work-dir C:\path\hbq-hanna --phase confirmatory --output-dir C:\path\hbq-hanna\analysis\confirmatory
```

The runner discloses that each phase sends the external story, prompt, and task
contract to the authenticated OpenAI service through Codex. Review that
disclosure before launching it.

MIT attribution for rating derivatives: “HANNA benchmark repository,
dig-team/hanna-benchmark-asg, MIT License.”
