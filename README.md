# Creative-Writing-Rubrics

**CWR 1.2.3 ships HBQ-RS 1.2.1**: a local-first toolkit for turning a review
brief into small, inspectable questions about creative work, then aggregating
the answers deterministically. It supports draft review, critique, model and
dataset evaluation, benchmarking, and synthetic-data workflows without hiding
the rubric, coverage, or uncertainty behind one opaque score. It does not turn
a literary judgment into an unquestionable truth.

The current HBQ-RS content contains **278 modules**, **2,145 atomic leaves**,
and **85 bundle presets**. A judge answers one yes/no leaf at a time;
aggregation is code, not another model call. Stable module, question, criterion,
and bundle IDs are the public contract.

## What the public evidence says

The strongest public evidence is deliberately bounded:

- In the [established-rubric repeatability study](evaluation-results/the-part-that-arrives-first-repeatability/established-v4/), one complete authorized story was judged five times with GPT-5.6 Sol. HBQ-RS had 91.01% all-five leaf agreement, 97.08% mean modal-label agreement, and no total-score ceiling; the comparison rubrics were more ceiling-bound on this case. This demonstrates repeatability and available headroom for one story, not general validity or literary superiority.
- The [Gray Blood full-book V9 aggregate](evaluation-results/hbq-gray-blood-full-book-qpc24-rebaseline-v9-public-result-v1/) is a settled full-fidelity aggregate for a work-in-progress manuscript, with no sampling: author-original `63.0202` (8 units / 1,817 positions) versus the explicitly labeled GPT-5.6 Pro rewrite `73.2369` (7 units / 1,589 positions), a difference of `+10.2167`. The non-statistical result is diagnostic for this rubric, scope, and frozen design, not a general ranking.
- The primary [Fresh88 generated-only HANNA analysis](evaluation-results/hbq-human-alignment-v3-fresh88-overlap-analysis-v1/) is negative: across 80 generated stories, final-score Spearman was `-0.0441` and the six-dimension macro was `-0.0361`. Current evidence does not demonstrate human-reference alignment.

![Five-run native-scale score distributions](evaluation-results/the-part-that-arrives-first-repeatability/established-v4/results/score-distributions.svg)

*Five repetitions of one story, keeping each rubric on its native scale. The
chart is a repeatability view, not a cross-rubric quality ranking; its numbers
and SVG are bound by the study's result manifest and verifier.*

These results show what the system can make inspectable today: repeatability,
scope-aware reports, explicit uncertainty, and bounded comparisons. They do
not complete human-alignment validation, establish reader outcomes, or create a
default hierarchy of literary quality.

## Active work, not results

The [V8 multisample continuation](evaluation-results/hbq-multisample-repeatability-v1-remainder-capacity-reset-successor-v8/)
is an **unpublished, paused operational checkpoint**, proceeding one settled,
trace-bound sequence at a time. Its exact live sequence count is not promoted
here; it becomes a public repeatability result only after completion and
integrity-checked analysis.

The committed study packages make the next questions reproducible without
pretending they have answers yet:

- [HANNA optimizer v3](evaluation-results/hbq-human-alignment-optimizer-v3/)
  freezes five prompt candidates, the corrected 80-item/39-prompt-group
  Fresh88 geometry, and disjoint 48/13/19-item train/development/confirmation
  partitions. Its [native-subscription v4 successor](evaluation-results/hbq-human-alignment-optimizer-v4-native-subscription-v1/)
  keeps the exact prompt bytes while naming Grok Build and Codex ChatGPT
  subscription routes honestly. The mandatory development gate is 65 Grok
  cells followed by 35 unchanged Sol validation cells; the 360-cell training
  pool is optional and confirmation remains unopened.
  The separate [development optimizer](evaluation-results/hbq-human-alignment-optimizer-v4-development-optimizer-v1/)
  can run deterministic Optuna search only over independently verified raw
  training cells and exposes a development-only DSPy program for versioned
  prompt descendants. Empirical optimization and confirmation have not run;
  neither dependency is imported by the scoring runtime or makes provider
  calls.

  Thirty-five [receipt-verified native Grok development cells](evaluation-results/hbq-human-alignment-optimizer-v4-native-subscription-exec-v1/) now cover the first seven items across all five frozen candidates. Each has exactly one tool-free, zero-new-spend Grok Build subscription process launch and proven native envelope/contact, reports Grok CLI `1.0.13` and `grok-4.6-build`, requests `high` reasoning without independent attestation, and has a provider-free [admitted predecessor-shaped immutable descendant](evaluation-results/hbq-human-alignment-optimizer-v4-native-admission-v1/) with a proof file. Cells 31–35 are `v4-cell-bfe6152248d26a49`, `v4-cell-a903ff8203f0054c`, `v4-cell-6865daa01bda8457`, `v4-cell-d2c36ddc4d550480`, and `v4-cell-c6ef9be1c65a7ab6`; their independent parallel admissions all returned `accepted:true` with `provider_calls_made:0`. Score vectors vary, and this is only 35 of 100 mandatory development cells. The first cell's CLI nominal usage estimate was `$0.01221688`, but this was a zero-new-spend subscription route, not a charged cost.

  Two once-launched exact matched Sol diagnostics are terminal and excluded with no resend: v1 after a Code Mode startup error, and v2 after a clean lifecycle failed its stderr-label gate. [Exec v3](evaluation-results/hbq-human-alignment-optimizer-v4-native-subscription-exec-v3/) records the first verified matched Sol local lifecycle at pushed head `42ef2e9`: Sol cell `v4-cell-b389399871064622`, paired with Grok cell `v4-cell-037a2c5d23d72e2c`, request SHA-256 `e3749b90c087cd754f21ef1febc2a3c65ede9ba9bee2df79fd6ab198ebb76d9c`, events `08df87…e7936`, and final `f1972bd…25b29`. Sol scores were `1/1.5/1.5/2.5/1.5/2`; its Grok mate was `1/2/2/2/1/2`, for a descriptive mean absolute dimension difference of `1/3`. One pair does not establish Grok-as-Sol substitution, agreement, alignment, candidate selection, confirmation, or revision gain. The Sol receipt proves only local Codex process/thread lifecycle; provider identity, reasoning, native endpoint, and cardinality remain unproven. DSPy `3.3.1` and Optuna `4.9.0` remain development-only, and the optimizer cannot consume these 35 development cells as the frozen 360-cell training endpoint.
- [Matched Grok/Sol calibration](evaluation-results/hbq-grok-sol-current-matched-v1/)
  is a provider-free, public-synthetic pre-execution screen. It will measure
  a narrow matched-verdict agreement question, not declare judge
  interchangeability or literary quality.
- [CWR-guided revision gain](evaluation-results/cwr-guided-revision-gain-v1/)
  is a provider-free, pre-execution design for testing guided versus matched
  generic revision with blinded, non-CWR endpoint measures. It makes no
  revision-gain claim until independently measured outcomes exist.
- [Flash-Next/Linux planning](evaluation-results/hbq-supplemental-providers-flash-next-v1/)
  freezes portable study geometry and an offline, non-authoritative per-root
  request journal. Native Linux execution, trusted route evidence, and pairing
  remain future work.
- [Flash-Next Linux portability diagnostic](evaluation-results/hbq-supplemental-providers-flash-next-linux-portability-v1/)
  binds the exact predecessor contract, adapter, policy, asset manifest,
  study, and adapter tests. It adds an executable provider-free plan plus a
  Linux-only, exclusive-published self-integrity diagnostic. It remains
  explicit NO-GO evidence: no native Linux run, independent attestation,
  provider/runtime provenance, pairing, or promotion is claimed.

## Install and try it

```bash
pip install "git+https://github.com/HaileyStorm/Creative-Writing-Rubrics.git"
```

From a clone, install development dependencies with `pip install -e ".[dev]"`.
HANNA prompt-development work additionally uses
`pip install -e ".[dev,hanna-dev]"`; DSPy and Optuna remain development-only.
Python 3.10+ is supported. The CLI is `cwr` (with `hbq` as an alias).

Score the included example verdicts, inspect a bundle, or render a
provider-agnostic packet:

```bash
cwr score prose.scene examples/verdicts_example.jsonl
cwr list bundles
cwr show prose.scene
cwr render-judge --bundle prose.scene --artifact examples/sample_scene.md
```

For a real judge, bring a local OpenAI-compatible endpoint:

```bash
cwr judge examples/sample_scene.md --bundle prose.scene --provider openai \
  --base-url http://127.0.0.1:8000/v1 --model local-model \
  --output-dir ../cwr-runs/sample
```

See [Running a headless judge](docs/judging.md) for Codex, Grok Build, the
Windows Nous bridge, privacy disclosure, contracts, retries, resume, and
full-fidelity long-form runs. Sampling is always explicit; omit
`--local-sample-limit` when complete local coverage is intended.

## How it works

```text
artifact + brief → validated route → frozen task contract → stable map
→ per-leaf verdicts → deterministic score → report
```

Choose a bundle, optionally freeze an artifact-bound task contract, collect
`YES`, `NO`, `NOT_APPLICABLE`, or `CANNOT_ASSESS` verdicts, and score them with
the library. Objective, explicitly non-negotiable task requirements may become
gates; author goals remain weighted questions. Open-ended review can attach
findings, but it does not rewrite scores.

For long-form work, the global result and local chapter/section diagnostics are
separate. The default is full local coverage; an explicit sample is a
diagnostic subset and is labeled as such. Reports preserve observed scores,
coverage, unresolved bounds, evidence scope, and control states rather than
collapsing them into one unsupported quality claim.

The optional GUI is an offline helper, not a server or telemetry system:

<p>
  <img src="docs/images/workflow-setup.png" width="72%" alt="Local HBQ-RS workflow setup page">
</p>

Offline reports and scorecards keep the canonical whole-work result separate
from any custom weighted composite:

<p>
  <img src="docs/images/report-overview.png" width="88%" alt="HBQ-RS offline long-form report overview">
</p>

## What is in the box

| Path | Contents |
| --- | --- |
| `registry/` | Modules, generated aggregates, question index, and criterion ownership |
| `bundles/` | Bundle presets |
| `schema/` | Module, bundle, judge-response, verdict, score-report, and review schemas |
| `prompts/judge/` | Prefix, binary, decomposition, pairwise, long-form, multimodal, and import prompts |
| `prompts/review/` | Open-ended critique families; findings do not rewrite scores |
| `src/hbqrs/` | Library and CLI |
| `docs/HBQ_RS_STANDARD.md` | Normative HBQ-RS rules |
| `docs/RUBRIC_BOOK.md` | Human-readable rubric catalog |

Technique-specific model-build modules are optional. Literary judging does not
require them.

## Results, guides, and integration

Start with the [curated results hub](docs/RESULTS.md), which groups the public
evidence by purpose and labels repeatability, full-book comparisons, negative
or no-promotion results, exploratory work, and historical packages. It also
links the detailed preface, HANNA, figurative, L2, structural-audit,
exact-repeatability, and provider-supplement records rather than flattening
every study into this front page.

- [HBQ-RS standard](docs/HBQ_RS_STANDARD.md) and [rubric catalog](docs/RUBRIC_BOOK.md)
- [Using HBQ-RS inside another application](docs/apps.md)
- [Validation and repair journey](docs/VALIDATION_AND_REPAIR_JOURNEY.md)
- [Leaf decomposition policy](docs/LEAF_DECOMPOSITION_POLICY.md)
- [Benchmarking](docs/benchmarking.md), [model training](docs/training.md), and [synthetic data](docs/synthetic-data.md)
- [Palimpsest integration handoff](docs/PALIMPSEST_HANDOFF.md), including its exact-pinned submodule and compatibility boundary

## Boundaries that matter

- Keep the selected bundle and evidence scope appropriate to the task; do not attach every module by default.
- Treat `CANNOT_ASSESS` as unresolved evidence, not as `NO`.
- Keep user taste and post-candidate preferences separate from craft requirements.
- Do not reward length, verbosity, ornament, or bland compliance by default.
- Request concise evidence, not private chain-of-thought.
- Label author-original prose and model rewrites explicitly; public case studies expose only authorized excerpts and aggregates.

Scores are structured evidence, not literary truth. Calibrate before
consequential use.

## Python API

```python
from hbqrs import compile_bundle, load_bundles, load_modules, load_verdicts
from hbqrs import resolve_bundle, score_bundle

modules = load_modules("registry/all_modules.json")
bundle = resolve_bundle(load_bundles("bundles/all_bundles.json"), "prose.scene")
packet = compile_bundle(modules, bundle)
report = score_bundle(modules, bundle, load_verdicts("examples/verdicts_example.jsonl"))
print(report["status"], report["final_score"])
```

## Verification, license, and support

Release checks cover fresh-clone and isolated-wheel installation, CLI and
Python APIs, strict schemas, local endpoint transport, public-result verifiers,
and provider-adapter/evidence-validation paths. Actual remote-execution
evidence is package-specific and explicitly labeled. The
public case studies preserve their own contracts, manifests, aggregate outputs,
and privacy checks; private manuscript prose and raw model responses are not
distributed.

This project is Apache-2.0 licensed; see [LICENSE](LICENSE) and [NOTICE](NOTICE).
Optional donations and their safety notes are documented in
[docs/DONATIONS.md](docs/DONATIONS.md).
